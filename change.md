## 2026-07-10: [fix/test] Tkinter 双摄自动比对第四轮隔离与异常恢复修复

### 问题描述

第四轮对抗审查发现两项 P2：后处理只按 `segment_id` 去重，不同 ID 若复用同一规范化目录会依次完成并覆盖同一个 `result.json`；双摄 worker 的推理或 writer 异常虽能释放资源和终结片段，却会跳过 `_post_done()`，导致主界面保持运行态、Start 持续禁用。

### 修改内容

- `DualRecordingPostProcessor.submit()` 在锁外解析并按平台大小写规则规范化 `segment_dir`，锁内为目录原子登记唯一 `segment_id` 所有权并保留至处理器销毁；同目录、`..` 别名或大小写别名的其他 ID 在入队前直接拒绝，不产生回调、比对或结果覆盖。
- 双摄 worker 将 `_post_done()` 收敛到最外层 `finally`，在两套 pipeline、两路 capture、OpenCV 窗口和录制片段全部收尾后恰好投递一次；覆盖正常结束、第二设备失败、模型初始化失败、推理异常和双 writer 异常。
- 新增不同 ID 目录别名抢占与双摄运行时异常完成通知回归，验证首份 JSON 字节不变、无串段通知，且异常后主界面可恢复非运行态。

### 验证方法

- 自动比对完整定向回归：`205 passed`。
- 后处理子集：`41 passed`；双摄子集：`54 passed`。
- `py_compile` 与 `git diff --check` 通过，仅有 Windows 行尾提示。

## 2026-07-10: [fix/test] Tkinter 双摄自动比对第三轮回调验收修复

### 问题描述

第三轮对抗审查发现三个 P3 边界：协调器回调线程内调用公开 `close()` 会尝试自连接并抛错；片段已发布 `cancelled` 后，最终路径补写若失败会再发送一个 `failed/result_write_failed` 终态；第二轮关窗防护把普通主停止也视为不可刷新，导致 worker 已复位为 idle 后录制状态文案仍残留。

### 修改内容

- `DualRecordingPostProcessor.close()` 在协调器 worker 自身调用时仍完成取消和退出哨兵登记，但跳过当前线程 join，使回调余下逻辑正常执行，worker 随后按队列顺序退出。
- 已成功发布 `cancelled` 的路径 enrichment 写盘失败时保留原 `result.json`，不再抛到通用 `result_write_failed` 通知；首次结果写盘失败的既有错误语义保持不变。
- `_refresh_recording_status()` 只在真正 `_closing` 时提前返回；普通主停止虽已设置 stop event，仍可在 worker 收尾后读取 idle 快照、清空旧录制文案并禁用“结束录制”。`_on_record_stop()` 的 closing/stop 防阻塞守卫不变。
- 新增回调自关闭、取消补写失败和主停止 worker 收尾三条确定性回归。

### 验证方法

- 自动比对完整定向回归：`204 passed`。
- 后处理子集：`40 passed`；Tkinter 生命周期、控件与双摄子集：`101 passed`。
- `py_compile` 与 `git diff --check` 通过，仅有 Windows 行尾提示。

## 2026-07-10: [fix/test] Tkinter 双摄自动比对第二轮并发验收修复

### 问题描述

第二轮首波与对抗审查发现两处剩余并发边界：后处理在共享协调器锁内执行原子 JSON 写盘，慢磁盘会阻塞新的 `submit()` 和关窗 `cancel_all()`；关窗后已调度的录制状态刷新仍可能等待录制锁、按旧快照重新启用控件，而“结束录制”入口也可能等待终结锁并突破 3 秒关闭预算。

### 修改内容

- `DualRecordingPostProcessor` 新增独立持久化锁，协调器状态锁仅保护写盘前后的取消、终态和去重判断，不再覆盖文件 I/O 或回调；写盘后再次判定取消，取消与 queued/completed 写入竞态时抑制旧状态通知并最终原子覆盖为 `cancelled`。
- `_refresh_recording_status()` 和 `_on_record_stop()` 在 `_closing` 或 `_stop_evt` 已置位时于读取 Tk 状态、获取录制锁或终结锁前直接返回，保证控件保持禁用且关窗轮询不被旧回调拖住。
- 新增阻塞 JSON 写入、阻塞录制锁和阻塞终结锁的确定性并发回归，覆盖 `submit()` / `cancel_all()` 及时返回、取消终态胜出、无旧 completed 通知及关窗控件不复活。

### 验证方法

- 自动比对完整定向回归：`201 passed`。
- 后处理并发子集：`38 passed`；Tkinter 生命周期、控件与双摄子集：`100 passed`。
- `py_compile` 与 `git diff --check` 通过，仅有 Windows 行尾提示。

## 2026-07-10: [fix/test/docs] Tkinter 双摄自动比对第一轮验收修复

### 问题描述

首轮多 agent 验收确认了 12 项取消、资源、并发和交付证据问题：DTW 评分阶段未贯穿取消，双摄 worker 异常路径未释放两路 native 资源，关窗轮询期间仍可开始新片段，后处理缺少片段目录隔离，`cancel_all()` 回调线程和终态通知不符合契约，转码异常错误码不准确；原实现提交还混入了规范开工前的双摄旋转/布局改动，任务完成日志指向不含实现的基线提交。

### 修改内容

- `subsequence_dtw()` / `subsequence_dtw_with_path()` 在代价矩阵、动态规划行、回溯和返回前响应取消；取消信号贯穿规则、正面评分、侧面评分与最终结果，正面评分取消后不再计算侧面或返回部分分数。
- 双摄 worker 在统一 `finally` 中关闭两套 MediaPipe pipeline、释放两路 capture 并清理 OpenCV 窗口；关窗立即禁用录制控件，录制 toggle 在 closing/stop 状态下于读取 Tk 状态前返回。
- 后处理在转码前校验正侧源路径均属于 `segment_dir`；`cancel_all()` 只置位并快速返回，所有回调由协调器线程触发，每片段只通知一次取消终态，同时允许内部补写最终转码路径；普通转码异常稳定归类为 `transcode_failed`。
- 用开工前 checkpoint 文件树重建独立提交 `8f0c9f8`，只保留既有双摄录制、旋转和自适应布局的 7 个路径；自动比对实现及首轮修复独立提交为 `09aa101`，旧混合提交 `b931222` 由安全分支保留。
- 仅修正 `tasks.md` / `progress.md` 的生成型完成日志和 `Last Known Commit` 为 `09aa101ea55421208e81739a6e88ccd6572f8656`，未改冻结任务正文、依赖、勾选状态或 task-plan hash。

### 验证方法

- 自动比对定向回归（后处理、控件、双摄、生命周期、录制控制器、转码、双流、模板 metadata、`pose33_v3` golden）：`196 passed`。
- 全量 `pytest tests -q`：`548 passed, 6 failed`；失败集合与接手基线一致，仍为 1 条 YOLO preview routing 和 5 条 `ui_backend` session，在本任务明确不修改的 Vue/Tauri/bridge 范围内。
- `py_compile`、`git diff --check` 和规范 `sync-check` 通过；提交父子关系、固定模板和后处理模块均通过 Git 对象校验。
- 实机待验：物理双摄连续两段、录制中主停止、骨架开启后跳过评分三条现场流程仍需接入真实摄像头执行。

## 2026-07-10: [feat/fix/test] Tkinter 双摄录制后自动后台比对

### 问题描述

Tkinter 双摄已能同步预览和录制，但片段结束后没有自动接入既有正面/侧面 DTW 比对；连续录制、主停止、writer 失败和关窗之间还缺少统一的片段终结、后台串行调度、结果留档与取消边界。带骨架录像若再次做姿态提取会产生失真分数，也需要明确跳过。

### 修改内容

- 新增无 Tk 依赖的 `DualRecordingPostProcessor`：按 `segment_id` 去重，单消费者 FIFO 顺序执行双路 H.264 转码、录像/固定模板/full 模型校验和 `compare_dual_streams()`；固定 `workers=1`、正侧权重 `0.4/0.6`、baseline `2.0`，规则与误差分析关闭。
- 每个片段目录通过临时文件原子替换生成 schema v1 `result.json`，完整记录成功、失败、跳过、取消、最终录像路径、转码 warning、三项分数和匹配区间；一次性写盘失败稳定归类为 `result_write_failed`，单任务失败不终止后续队列。
- Tkinter 双摄新增默认关闭且会话期间锁定的“录像写入骨架”开关；预览始终显示标注帧，关闭时 writer 保存旋转后的原始帧并自动比对，开启时保存标注帧、完成转码后写 `skipped/annotated_recording`。
- 显式“结束录制”、主“停止”、writer 错误、worker `finally` 和关窗统一经过串行终结器；锁内快照/释放、锁外非阻塞提交，零帧也提交为 `recording_empty`，每段最多提交一次，下一段可立即开始。
- 主窗口新增最近已提交片段的排队/转码/校验/比对状态、正面分、侧面分、综合百分比和稳定错误码；旧任务只更新自己的 JSON。后处理、双摄布局和摄像头枚举均用线程安全队列回到 Tk 主线程。
- 关窗先登记当前有效片段，再停止新提交并取消活动/排队任务；即使 3 秒等待预算耗尽也投递消费者退出哨兵。ffmpeg、VideoCapture 和 MediaPipe 在成功、失败、取消时统一释放。
- 交付并校验固定模板 `templates/standard_front_full.npz` 与 `templates/standard_side_full.npz`，保持现有 `full + v2` 兼容路径；Vue/Tauri、单摄、离线视频和评分算法不变。

### 验证方法

- T-003 Tk 生命周期与后处理定向套件：`122 passed`。
- 跨模块回归（含转码、双流比对、模板 metadata、录制控制器和 `pose33_v3` golden）：`177 passed`。
- 全量 `pytest tests -q`：`529 passed, 6 failed`；失败集合与接手基线一致，仍为 1 条 YOLO preview routing 和 5 条 `ui_backend` session 在制品，本任务未修改 Vue/Tauri/bridge 且未新增失败。
- 真实 ffmpeg/ffprobe 烟测：短 MJPG AVI 经实际 `transcode_to_h264()` 输出 `codec_name=h264` 的 1683-byte MP4，源 AVI 已删除且临时文件残留为 0。
- `py_compile` 与 `git diff --check` 通过（仅 Windows 行尾提示）。
- 实机待验：骨架关闭时连续录制两段并确认各自产生 `front/side` 视频及完成结果；录制中直接主“停止”并确认结果落盘；骨架开启时确认视频保留且结果明确为“带骨架录像未自动比对”。

## 2026-07-09: [feat/fix/test] 摄像头画面转正与双摄预览自适应

### 问题描述

USB 摄像头竖置后通常仍输出横向分辨率且不提供方向传感器，旧 Tkinter 入口没有逐路转正能力，姿态推理、预览和录制都会保留错误方向。双摄预览同时固定为上下堆叠，不能根据转正后的画面比例利用横向空间；90°/270° 旋转若不更新 writer 尺寸还会导致录制尺寸与帧不一致。

### 修改内容

- `apps/app_ui.py` 为两路摄像头分别增加 `0°/90°/180°/270°` 旋转下拉，严格解析四个合法角度，并在运行期间锁定控件；旋转只作用于实时摄像头，离线视频单/多 worker 路径保持原行为。
- 串行单摄、双摄两路和实时多 worker reader 均在 MediaPipe 推理前应用旋转，使 landmarks、在线匹配、预览与录制共用转正后的坐标系；90°/270° 先交换驱动上报尺寸，再由旋转后的首帧真实 shape 通过 `RecordingController.update_session_size()` 校正 writer，避免错误 `CAP_PROP` 造成空文件或坏文件。
- 双摄根据旋转后宽高比自动排布：两路都为竖画面时左右并排，横向/方形/混合方向时上下堆叠；先按设备尺寸切换，再用首帧真实尺寸校正，所有 Tk grid 更新通过主线程执行，单摄隐藏时同步清空第二行/列权重。
- 补齐双路录制一致性：共享录制锁覆盖片段级保存根目录/时间戳发布和两路 toggle/begin/write/stop/close，保证 front/side 的片段边界与目录一致；目录选择只更新 Tk 变量，真正的普通 `Path` 在下一次 `idle -> recording` 时锁内发布，worker 不再持锁读取 `StringVar`。UI 同时显示正面/侧面输出路径，任一路 writer 失败时结束两路片段并明确标注失败路。
- `core/recording_controller.py` 在片段停止/会话关闭时清理 `last_error`，且单摄模式忽略第二路错误，避免侧路失败污染同会话重试或下一次单摄/离线会话；worker 在 close 前把 Tk 尚未消费的错误转存到待提示队列，最后一帧失败也不会静默丢失。
- 新增 headless 回归，覆盖角度像素方向、非法值、writer 首帧尺寸校正、布局坐标/权重、状态采集、三条实时采集路径、离线视频隔离、运行态控件、第二路 writer 失败收敛，以及真实双线程下 toggle/时间戳/双写/stop 不交错。

### 验证方法

- `.\.venv\Scripts\python.exe -m pytest tests/test_app_ui_dual_camera.py tests/test_app_controls.py tests/test_app_ui_lifecycle.py tests/test_recording_controller.py -q`：`80 passed`。
- `.\.venv\Scripts\python.exe -m pytest tests/test_pose33_v3_golden.py tests/test_s5_hands_toggle.py tests/test_error_handling.py tests/test_input_source_state.py -q`：`34 passed`。
- 全量 `.\.venv\Scripts\python.exe -m pytest tests -q`：`468 passed, 6 failed, 5 warnings`；失败集合与接手前记录一致，仍为 1 条 YOLO preview routing 和 5 条 `ui_backend` session 在制品，本次未新增失败。
- `.\.venv\Scripts\python.exe -m py_compile apps\app_ui.py core\recording_controller.py tests\test_app_ui_dual_camera.py tests\test_app_controls.py tests\test_app_ui_lifecycle.py tests\test_recording_controller.py` 通过。
- `git diff --check` 通过，无 whitespace error（仅 Windows 行尾提示）。
- 自动化验证不依赖真实摄像头；两台物理摄像头的竖置方向与驱动尺寸仍需现场快速目视确认。

## 2026-07-09: [feat] 双摄双面视图两路同步落盘 + 按日期/录制段归档

### 问题描述

双摄双面视图（issue #58）录制时只有第一路（正面）落盘，第二路（侧面）仅预览不存储（`apps/app_ui.py` 原 `ponytail:` 注释标注的推迟点）。同时单一录制路径无法区分双摄两路来源。

### 修改内容

- `apps/app_ui.py` 新增第二路录制控制器 `self._rec2`（`path_provider=_record_path_cam2`），在 `_worker_loop_dual_camera` 中与第一路各自 `begin_session` / `write_frame` / `close_session`；`_on_record_toggle` / `_on_record_stop` 同步切换两路。`_rec2` 在单摄/文件模式恒 idle no-op。
- 录制路径按日期和片段归档：单摄/文件写入 `<保存目录>/<YYYYMMDD>/record_<时间戳>.mp4`；双摄两路共用同一时间戳与片段目录，分别写入 `<保存目录>/<YYYYMMDD>/record_<时间戳>/front.mp4` 和 `side.mp4`。`_dual_active` 在双摄循环进入时置 True、finally 复位。

### 验证方法

- `py_compile apps/app_ui.py` 通过。
- `pytest tests/test_app_ui_lifecycle.py tests/test_recording_controller.py -q`：`20 passed`。

## 2026-07-09: [fix/test/docs] 修复 PR #71 五项审查问题并对齐最新 main

### 问题描述

PR #71 存在五项场地前阻塞：在线直拳模板未交付、`mp4v` 回退可以产出非 H.264 MP4、摄像头预打开存在重叠任务竞态、新会话保留旧识别文案，以及未跟踪的 daemon 转码线程可在关窗时被截断。同时 PR 分支落后 `origin/main`，且夹带了 main 已有的 batch paired 重复提交。

### 修改内容

- 从最新 `origin/main` 重建 PR 分支，只重放 Tkinter、change 归档和 bridge 在制品三个有效提交，移除重复 batch commit；冲突以 main 的同目录 paired 行为和最新文档为准。
- `.gitignore` 只白名单放行 `templates/online/直拳_左手.npz` 与 `直拳_右手.npz`，其他本地模板仍忽略；新增默认模板库加载契约测试。
- `core/video_writer.py` 移除 `mp4v -> .mp4` 路径：H.264 不可用时只回退 `MJPG/XVID -> .avi`，再由 ffmpeg 转 H.264；转码先写同目录唯一临时 MP4，校验非空后原子替换，失败保留 AVI 和已有 MP4。
- `apps/app_ui.py` 为预打开请求增加 generation token，只接受最新且 `isOpened()` 的 cap，原子替换时释放旧 handle；新会话重置 `识别：待机`。
- H.264 转码改为受跟踪的 non-daemon worker；关窗按 50 ms 分片等待采集/转码任务，最多保留 GUI 3 秒，之后转码可在后台继续，ffmpeg 最长 30 分钟硬超时并在失败时保留 AVI。
- 按最新仓库事实源同步 `AGENTS.md` / `CLAUDE.md` 归档和 analysis 清单，并更新仍指向已删 `_browse_video` 或旧 YOLO 文案的回归测试。

### 验证方法

- Tkinter matcher / 平滑 / 并行 / 双摄 / 录制 / MediaPipe golden 定向安全网：`97 passed`。
- 最新文档与错误处理契约：`9 passed`。
- 全量 `pytest tests -q`：`421 passed, 6 failed, 1 skipped, 5 warnings`；剩余 5 条为 PR 第 4 个 commit 已标注的 `ui_backend` session 在制品，1 条为本轮明确暂不处理的 YOLO preview routing。
- 真实 ffmpeg + ffprobe 探测：MJPG AVI 转码后 `codec_name=h264`、MP4 `2769` bytes、源 AVI 已删除。
- `py_compile apps/app_ui.py core/video_writer.py tests/test_app_ui_lifecycle.py` 通过；`git diff --check` 无 whitespace error（仅 Windows 行尾提示）。

## 2026-07-09: [chore] change.md 归档与重建

### 问题描述

`change.md` 累积至 586 行（覆盖 2026-06-14 ~ 2026-07-09），按任务完成规范需归档并重建空文件。

### 修改内容

- `git mv change.md "change（2026.6~2026.7）.md"`，重建空 `change.md`，本条为首条记录。
- 同步更新 `CLAUDE.md` 归档清单：新增 `change（2026.6~2026.7）.md`。
- 历史归档：`change（start~2026.5）.md`、`change（2026.5~2026.6）.md`、`change（2026.6~2026.7）.md`。

### 验证方法

- `ls change*.md` → 三份归档 + 空 `change.md`。
- `git mv` 保留文件历史（非删除重建）。

## 2026-07-09: [apps/core] 接通 Tkinter 实时直拳识别、预览平滑与录制 H.264 转码

### 问题描述

`core/online_matcher.py`、`templates/online/` 左右手直拳模板与 `core/preview_smoother.py` 均已就绪且单测全绿，但 `apps/app_ui.py` 未接线：Tkinter 实时预览无法显示在线识别结果，预览骨架未平滑，录制回退的 MJPG AVI 也未转 H.264。

### 修改内容

- `apps/app_ui.py`：
  - 新增默认开启的「实时动作识别」开关 + `match_var` 命中/分数显示，以及 `_build_online_matcher`/`_feed_online_matcher`/`_post_match` 三个接入边界；模板缺失/不兼容安全降级为无 matcher，关窗/停止竞态不刷新已销毁 UI。
  - 开关值经 Tk 主线程收进 `UiState.online_match_enabled`，worker 不跨线程读 `BooleanVar`；matcher 仅接单摄实时流，双摄/离线不接。
  - 单线程摄像头按 `infer(raw) → matcher(raw) → smoother → draw` 执行；文件 VIDEO 路径保留原 `annotate()`，帧序号/时间戳语义不变。
  - 并行摄像头启用 `ParallelPoseEngine(defer_draw=True)`，在有序出口喂 raw matcher、平滑并绘制，用采集 monotonic 时间戳保留满队列丢帧的真实间隔（顺带消除原「时序平滑关闭」抖动）。
  - 绘制均以 raw landmarks 做动作分类、smoothed landmarks 画骨架，smoother 不回流识别/评分序列。
  - 新增 `_transcode_async`，接入手动结束录制与单线程/双摄/并行视频/并行摄像头四个会话收敛点；录制文件名加微秒防同秒重录与后台转码争用。
- `core/vision_pipeline.py`：`draw_pose_frame` / `MediaPipePipeline.draw` 新增可选 `action_pose_landmarks`（默认沿用绘制 landmarks，旧行为不变），平滑预览显式传 raw 做分类。
- `core/video_writer.py`：新增 `transcode_to_h264`，仅把 AVI 用 `libx264/medium/CRF20/yuv420p` 转 MP4；成功且目标非空才删 AVI，ffmpeg 缺失/失败保留原录像。
- `core/parallel_pose_engine.py`：`ParallelPoseEngine` 新增 `defer_draw`，`InferResult` 携带 raw `pose_landmarks`/`hands`/`frame` 供重排出口单线程平滑+绘制。
- 新增 `tests/test_online_matcher.py`、`tests/test_app_ui_online_matcher.py`、`tests/test_preview_smoother.py`、`tests/test_preview_draw_contract.py`、`tests/test_video_writer_transcode.py`。

### 验证方法

- 定向 + 安全网 **68 passed**：在线 matcher、Tkinter 接入、预览平滑/绘制边界、转码、`pose33_v3` golden、`valid_mask`、双摄、手部开关全绿。
- 首轮全量 `pytest tests -q` 为 **403 passed / 10 failed**。后续 PR 审查确认：其中 5 条 `ui_backend` session 与 1 条 YOLO preview routing 由 PR 第 4 个在制品提交引入，其余为落后最新文档/接口的旧测试；最终验证结果见本文件置顶记录。
- `py_compile apps/app_ui.py core/vision_pipeline.py core/video_writer.py core/parallel_pose_engine.py` → OK。
- 待场地人员按实际机位人工确认左右手命中、平滑观感、录制全链路，并现场标定 `MatcherConfig` 阈值。
