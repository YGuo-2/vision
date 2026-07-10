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
