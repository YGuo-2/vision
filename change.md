## 2026-06-11: T-009 保持 MediaPipe 正式评分和 full tech_eval 默认边界

### 问题描述

T-007/T-008 已接入 YOLO realtime preview 与 YOLO26L 离线 high_quality body-only 路由后，
需要回归确认正式评分、完整技术评估和手指指标冲突场景仍停留在 MediaPipe 生产路径；
YOLO body_core 结果不得进入 full tech_eval、规则评分正式成绩或对外 pass/fail 判定。

### 修改内容

- 本任务按规范定位为回归门：复核 `core/backend_router.py` 中 formal score / full tech_eval 分支，
  `enableHands=false` 时仍返回 MediaPipe pose-only partial，并通过 `skippedCapabilities=fingers`
  标注手指指标跳过，不启用 hand landmarker，也不路由到 YOLO。
- 复核 `analysis/tech_eval.py` 与 `core/rule_scoring.py` 现有结构化状态测试覆盖：
  full tech_eval 主链路后端保持 MediaPipe，COCO17/YOLO 缺失能力只进入 skipped/missing_landmarks，
  不贡献正式扣分或合格/不合格判定。
- 未发现 YOLO 可进入正式评分或 full tech_eval 的缺口，因此未新增业务代码守卫，避免扰动
  MediaPipe `pose33_v3` golden 行为。

### 验证方法

- `.\.venv\Scripts\python.exe -m pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py tests/test_tech_eval_contract.py tests/test_rule_availability.py -q`
  → 49 passed

## 2026-06-11: T-008 接入 YOLO26L 离线高质量 body-only 分析路径

### 问题描述

T-001/T-003 已经规定 `enableHands=false` + `qualityProfile=high_quality` + YOLO26L 可用时必须选择
YOLO26L 离线高质量 body-only 路由；但 `analysis.run` 运行时还没有真正执行该内部分析路径，
batch/benchmark 侧显式 YOLO body_core 入口也仍容易沿用旧实验默认模型名，导致 YOLO26L 任务边界
只停留在路由 metadata，缺少可复现执行证据。

### 修改内容

- `apps/ui_backend.py` 为 `TemplateAnalysisService` 增加 YOLO body_core 内部分析分支：
  high_quality body-only YOLO 路由只返回 `bodyCoreAnalysis`，不生成 `compare` 或 `techEval`；
  payload 固定标识 `backend=yolo`、`rawLayout=pose33_like_coco17`、`featureLayout=body_core_v1`、
  `calibrationStatus=unvalidated`、`scoreAuthorized=false`、`displayScope=internal` 和 `score=null`。
- 默认 YOLO26L 分析调用 `core.body_core_compare.extract_body_core_features()`，模型档映射到
  `models/yolo26l-pose.pt`；YOLO26L 缺失/安装版不支持时继续由 router 返回
  `yolo26l_unavailable` 结构化错误，不静默回退 MediaPipe。
- `core/body_core_compare.py` 新增 `DEFAULT_YOLO26L_MODEL_NAME`，`batch/backend_options.py` 和
  `batch/batch_dual_compare.py` 的显式 YOLO body_core batch 默认使用 YOLO26L，同时保持
  `score_authorized=False` 与 `display_scope=internal`。
- `analysis/bench_annotate_fps.py` 的未显式 `--yolo-model` 默认改为 `models/yolo26l-pose.pt`，
  便于离线高质量 body-only 分析性能复核与任务路由一致。
- `tests/test_batch_backend_args.py` 和 `tests/test_s3_calibration.py` 增加 T-008 契约测试，覆盖
  UI 成功路径、缺模型结构化错误、batch 默认 YOLO26L 和 benchmark 默认模型。

### 验证方法

- `.\.venv\Scripts\python.exe -m pytest tests/test_body_core_layout.py tests/test_batch_backend_args.py tests/test_s3_calibration.py -q`
  → 40 passed
- `.\.venv\Scripts\python.exe -m pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py -q`
  → 31 passed
- `git diff --check`
  → 退出码 0（仅 Windows 换行提示，无空白错误）

## 2026-06-11: T-007 接入 YOLO26n/s 实时 body-only 预览路径

### 问题描述

T-001 已固化 `enableHands=false` 且 YOLO realtime 可用时必须选择 YOLO26n/s 的路由契约，
但桌面 `session.start` 运行时仍统一创建 MediaPipe pipeline；即使 `backendRoute.backend=yolo`，
实际预览帧也不会走 YOLO body-only adapter，且多人复核、评分授权、标定状态等 YOLO meta
没有随 `session.frame` 透传给前端。

### 修改内容

- `core/yolo_adapter.py` 为 `YoloPoseAdapter` 增加实时 `annotate()` 接口：逐帧推理后绘制
  body-core skeleton，返回 `(annotated, actions, meta)`，并透传 `backend=yolo`、
  `raw_layout=pose33_like_coco17`、`feature_layout=body_core_v1`、`score_authorized=False`、
  `calibration_status=unvalidated`、`display_scope=limited`、多人检测和 `target_policy`。
- `apps/ui_backend.py` 的默认 pipeline factory 根据 `backendRoute.backend` 选择 MediaPipe 或
  YOLO；YOLO realtime 档默认映射到 `models/yolo26n-pose.pt`，显式 yolo26s/yolo26l 才使用对应模型。
- 后台 job 执行时复用 start 阶段已计算的 `backendRoute`，避免内部二次 normalize 因默认安装版
  YOLO unsupported 而把已批准 YOLO 路由回退成 MediaPipe；外部 request 仍由 availability 重新计算。
- `session.frame` 增加 `backendMeta` camelCase 透传，并提升 `multiPersonDetected`、
  `personCount`、`reviewRequired`、`targetPolicy` 等前端可直接消费字段；MediaPipe 原二元
  `annotate()` 返回保持兼容。
- 增加 UI 会话路由接线测试和 YOLO realtime annotate 契约测试，证明 YOLO 可用时真实进入
  YOLO preview pipeline，且不授权正式评分。

### 验证方法

- `.\.venv\Scripts\python.exe -m pytest tests/test_backend_routing_contract.py tests/test_yolo_backend_contract.py -q`
  → 33 passed
- `.\.venv\Scripts\python.exe -m pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py -q`
  → 31 passed
- `git diff --check`
  → 退出码 0（仅 Windows 换行提示，无空白错误）

## 2026-06-11: T-003 建立模型档清单与配置状态

### 问题描述

桌面模型管理仍只展示 MediaPipe 可下载模型，缺少 YOLO26n/s、YOLO26L、YOLO26X 分档状态、
默认路由资格、安装版 sidecar 能力边界和开发侧代理下载约束。若模型清单继续缺位，后续
T-007/T-008 的 YOLO 路由会缺少可复用的模型状态、下载/安装错误和 UI 提示基础。

### 修改内容

- 在 `core/model_manager.py` 扩展 `ModelSpec` 元数据，新增 `category`、`profile`、`downloadable`、
  `installed_supported`、`default_route_eligible`、`note` 字段；统一导出 `MODEL_SPECS`。
- 补齐 YOLO26n、YOLO26s、YOLO26L、YOLO26X 模型档清单：YOLO26n/s 为实时 body-only 预览档，
  YOLO26L 为离线高质量 body-only 分析档，YOLO26X 标记为实验档且不进入默认路由。
- MediaPipe 模型下载默认走 `http://127.0.0.1:7890`，并支持 `VISION_MODEL_PROXY` 覆盖或置空；
  不可自动下载的 YOLO 档在下载入口直接返回结构化手动安装错误。
- `apps/ui_backend.py` 的 `model.status` 返回模型档元数据、只把可下载缺失项纳入 `missingKeys`，
  并暴露当前安装版 `yoloRuntime.supported=false` / `packaged=false` 提示。
- `frontend/src/App.vue` 展示 YOLO runtime 提示、模型分类/profile/默认路由资格和手动安装按钮；
  `frontend/scripts/frontend-smoke.mjs` 锁定这些前端契约。
- `tests/test_windows_packaging_smoke.py` 明确断言安装版 sidecar 未把 `torch`、`ultralytics`、
  `core.yolo_adapter` 放入 hiddenimports，而是保留在 heavy excludes 中。

### 验证方法

- `.\.venv\Scripts\python.exe -m pytest tests/test_ui_backend_models.py tests/test_windows_packaging_smoke.py -q`
  → 20 passed
- `npm --prefix frontend run test`
  → Frontend behavior smoke checks passed
- `.\.venv\Scripts\python.exe -m pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py -q`
  → 31 passed
- `git diff --check`
  → 退出码 0（仅 Windows 换行提示，无空白错误）

## 2026-06-11: T-006 打通 Rust/Python 双侧任务状态机和取消语义

### 问题描述

T-004/T-005 引入了独立帧通道和前端异步渲染队列后，session、analysis、model download 的主动停止
与晚到事件处理需要进一步收口：停止响应成功后若前端仍保留 active job/session id，后续晚到 job event
可能再次改写 UI；pending frame / canvas 也需要在停止和失败时明确清理。

### 修改内容

- 在 `frontend/src/App.vue` 增加 `markSessionStopped()`，统一主动 `session.stop`、`job.completed`、
  `job.stopped`、`job.failed` 下的 running/job/session/pending frame/canvas 清理；失败路径保留错误状态，
  正常停止清空 canvas。
- 主动取消模型下载成功后立即置 `modelDownloadStatus=已取消` 并清空 `modelDownloadJobId`/progress；
  主动停止 analysis 成功后立即置 `analysisStatus=已停止` 并清空 `analysisJobId`/progress。
- 扩展 frontend smoke，锁定卸载/主动停止会调用 `job.stop`，并要求 session/model/analysis 停止后清理
  active id 与 pending frame。
- 扩展 `tests/test_ui_backend_contract.py`，锁定 `job.stop` 缺失或未知 jobId 时返回结构化 `bad_request` /
  `not_found` envelope，不抛未包装异常。

### 验证方法

- `.\.venv\Scripts\python.exe -m pytest tests/test_ui_backend_sessions.py tests/test_ui_backend_contract.py -q` → 24 passed
- `npm --prefix frontend run test` → Frontend behavior smoke checks passed
- `git diff --check` → 退出码 0（仅 Windows 换行提示，无空白错误）

## 2026-06-11: T-005 将 Vue 预览迁移到 Canvas/bitmap 渲染

### 问题描述

T-004 已把大帧从 JSON/base64 主桥迁到本机二进制通道，但前端仍把拉到的帧 bytes 转成 blob URL，
再存进 `previewImage` reactive 字符串并通过 `<img>` 展示。该路径仍会让每帧 URL 进入 Vue reactive
状态，不符合 T-005 对 Canvas/bitmap、latest-frame 绘制和不保留大图字符串的约束。

### 修改内容

- 将 `frontend/src/App.vue` 的预览状态从 `previewImage` reactive 字符串改为 `previewCanvas` canvas ref；
  `session.frame` 到达后只保留一个非 reactive `pendingFrame`，通过 `requestAnimationFrame` 合并晚到帧，
  拉取最新 bytes 后使用 `createImageBitmap` + `drawImage` 绘制到 canvas。
- 移除 blob object URL 渲染路径，不再使用 `URL.createObjectURL` / `<img>` 展示预览帧；bitmap 绘制后立即
  `bitmap.close()`，卸载和 session restart 时清理 pending frame 与 canvas。
- 更新 `frontend/src/styles.css` 的 `.video-frame canvas` 样式，保持预览区域稳定尺寸和 contain 显示。
- 扩展 `frontend/scripts/frontend-smoke.mjs` 与 `tests/test_vue_tauri_acceptance_gaps.py`，阻断
  `previewImage`、`payload.image`、`URL.createObjectURL`、`<img>` 回归，并要求 Canvas/ImageBitmap/
  requestAnimationFrame 路径存在。

### 迁移前后记录型基线

- 丢帧率：继承 T-004 后端 latest-frame 统计；前端每个 animation frame 只处理最新 `pendingFrame`，晚到帧会被覆盖，不进入历史队列。
- 渲染帧率：由 `requestAnimationFrame` 驱动，最多跟随浏览器刷新节奏；后端 `fps` 显示仍保留，后续桌面验收可用真实摄像头观察渲染侧帧率。
- 前端内存增长：迁移前每帧创建 blob URL 并存入 reactive 字符串；迁移后不再保存大图字符串/URL，bitmap 绘制后立即关闭，仅保留一个 pending frame 引用。
- IPC payload 大小：沿用 T-004 二进制帧通道，`session.frame` JSON 继续只携带句柄/指标，不携带图片 bytes/base64。

### 验证方法

- `npm --prefix frontend run test` → Frontend behavior smoke checks passed
- `.\.venv\Scripts\python.exe -m pytest tests/test_vue_tauri_acceptance_gaps.py -q` → 7 passed
- `git diff --check` → 退出码 0（仅 Windows 换行提示，无空白错误）

## 2026-06-11: T-004 设计并实现二进制 latest-frame 预览帧通道

### 问题描述

Vue/Tauri 预览帧仍通过 `session.frame` JSON event 携带 `image=data:image/jpeg;base64,...`，
大图帧会进入 stdout JSON bridge、Rust event 和 Vue reactive 状态，容易造成 IPC payload 膨胀、旧帧积压、
前端内存压力和 session 串线风险。T-004 要求大帧改走本机二进制 latest-frame 通道，JSON bridge
只保留帧句柄、token、指标和业务状态。

### 修改内容

- 在 `apps/ui_backend.py` 新增 `LatestFrameChannel`：每个 preview session 绑定 `127.0.0.1` 随机端口，
  生成会话 token，通过长度前缀 TCP 协议按需返回最新 JPEG bytes；`session.frame` 不再写 `image`、
  base64 或图片 bytes，只写 `frameHost/framePort/frameToken/frameId/frameHandle/payloadBytes` 等小字段。
- 预览 session 的 running/status/result payload 增加 `frameChannel` 快照；摄像头实时路径继续 latest-frame
  丢旧帧策略，并记录 `capturedFrames/droppedFrames/renderedFrames/sourceFrameAgeMs/payloadBytes`。
- 在 `frontend/src-tauri/src/lib.rs` 新增 `latest_frame` Tauri command，Rust 只连接本机帧通道并用
  `tauri::ipc::Response` 返回 `ArrayBuffer` bytes；没有改视觉算法，也没有把算法搬进 Rust/TS。
- 在 `frontend/src/bridge.ts` 增加 `fetchLatestFrameBytes()`；`frontend/src/App.vue` 收到 `session.frame`
  后用 raw IPC 拉 bytes 生成 blob URL，并在卸载/换帧时释放旧 URL。T-005 会继续迁移到 Canvas/bitmap。
- 扩展 session、packaging 和 frontend smoke：测试实际从 TCP 通道读取 fake frame bytes，静态阻断
  `payload.image`，并锁定 Rust `latest_frame`/`Response::new(bytes)` 路径。

### 迁移前后记录型基线

- 丢帧率：同源合成摄像头样本采集 20 帧、渲染 2 帧，`droppedFrames > 0`，保持 latest-frame 丢旧帧策略。
- 渲染帧率：后端 `fps` 仍按已处理帧/耗时输出；T-004 未改前端绘制节流，T-005 Canvas 阶段继续记录真实渲染侧 fps。
- 前端内存增长：T-004 已移除 JSON/base64 大图进入 reactive 状态，前端仅保存当前 blob URL 并释放旧 URL；真实浏览器内存增长留到 T-005 Canvas 验证记录。
- IPC payload 大小：迁移前 `session.frame` JSON 含整帧 data URL/base64；迁移后 JSON 图片负载为 0，
  只含端口/token/handle/指标，实际 JPEG bytes 通过本机 TCP + Tauri raw IPC `ArrayBuffer` 按需获取。

### 验证方法

- `.\.venv\Scripts\python.exe -m pytest tests/test_ui_backend_sessions.py tests/test_windows_packaging_smoke.py -q` → 16 passed
- `npm run verify:tauri` → cargo check passed
- `npm --prefix frontend run test` → Frontend behavior smoke checks passed
- `git diff --check` → 退出码 0（仅 Windows 换行提示，无空白错误）

## 2026-06-11: T-002 补齐 YOLO 能力和评分授权元数据

### 问题描述

YOLO adapter 的边界帧与序列 artifact 已标注 `backend=yolo`、confidence 和标定状态，但缺少统一的
raw/feature layout、body-only capability、布尔评分授权和受限显示范围字段。若这些字段只在 router 或
batch helper 中补齐，真实 YOLO 产物仍可能被下游误读成完整 Pose33 能力或正式评分结果。

### 修改内容

- 在 `core/yolo_adapter.py` 新增 YOLO 授权/能力元数据片段，边界层 `FrameResult.meta` 和
  `extract_yolo_landmark_series()` 序列 meta 均写入 `raw_layout=pose33_like_coco17`、
  `feature_layout=body_core_v1`、`capability=body_only`、`score_authorized=False`、
  `calibration_status=unvalidated` 和 `display_scope=limited|internal`。
- 保持边界帧默认 `display_scope=limited`，离线/序列 artifact 默认 `display_scope=internal`；不引入
  `evalScope`、`internalUseOnly` 或其他同义显示字段。
- 扩展 YOLO adapter、COCO17 映射、规则可用性和 UI bridge 分析契约测试，覆盖 Python snake_case
  artifact、前端 camelCase `backendRoute`、布尔 `scoreAuthorized=false`、COCO17 结构性缺失点与
  missing capability 语义。

### 验证方法

- `.\.venv\Scripts\python.exe -m pytest tests/test_yolo_backend_contract.py tests/test_yolo_landmark_mapping.py tests/test_rule_availability.py tests/test_ui_backend_analysis.py -q` → 46 passed
- `.\.venv\Scripts\python.exe -m pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py -q` → 31 passed
- `git diff --check` → 退出码 0（仅 Windows 换行提示，无空白错误）

## 2026-06-11: T-001 固化后端路由决策契约

### 问题描述

Vue/Tauri 桌面端、batch CLI 与后续 YOLO 接入需要共享同一套 MediaPipe/YOLO 后端路由规则；
若各入口各自判断 `enableHands`、模型可用性、评分授权和能力缺失，容易导致 YOLO 被误接入正式评分
或 full tech_eval，也容易把 YOLO26L 缺失误处理成静默 MediaPipe 回退。

### 修改内容

- 新增 `core/backend_router.py`，集中定义 `BackendRouteRequest` / `BackendRouteDecision`、实时预览、
  离线高质量 body-only、正式评分/full tech_eval 的确定性路由规则，以及 snake_case/camelCase 序列化契约。
- 将 `batch/backend_options.py` 收编为共享 router 的 CLI 适配层，保留原有参数和 `BATCH_META_FIELDS` 兼容，
  同时补齐 `raw_layout`、`capability`、`display_scope` 等授权/能力元数据。
- 在 `apps/ui_backend.py` 的 `model.status`、`session.start`、`analysis.run` payload 中透传 `backendRoute`；
  默认未声明 YOLO runtime 可用时，无手部实时预览标注为 MediaPipe pose-only fallback；离线高质量
  body-only 缺 YOLO26L 时返回结构化 `yolo26l_unavailable` 错误，不启动静默回退任务。
- 补充 `tests/test_backend_routing_contract.py`，并扩展 UI bridge 与 batch 参数契约测试，覆盖
  hands-off partial、YOLO realtime fallback、YOLO26L 结构化错误、多人预览 review 标记和布尔授权字段。

### 验证方法

- `.\.venv\Scripts\python.exe -m pytest tests/test_backend_routing_contract.py tests/test_ui_backend_contract.py tests/test_batch_backend_args.py -q` → 35 passed
- `.\.venv\Scripts\python.exe -m pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py -q` → 31 passed
- `git diff --check` → 退出码 0（仅 Windows 换行提示，无空白错误）

## 2026-06-10: 修复 Web/Tauri 预览串线、积压追帧与首屏阻塞

### 问题描述

Web/Tauri 桌面端在打开和点击“开始”后仍可能出现卡顿、灰屏无响应、bridge response timeout / decode_error，
以及预览画面从旧帧高速追到实时画面的现象。进一步确认不是 Tauri 与 Python 后端“不兼容”，而是三类工程问题叠加：

- Python bridge 的后台 job event 与主线程 response 可能并发写 stdout，Tauri 按行解析时会遇到拼接 JSON。
- 摄像头预览按“读一帧、推理一帧、编码一帧、发送一帧”的顺序模型运行，下游慢时旧帧排队，恢复后表现为快进追帧。
- `onMounted` 等待摄像头枚举与模型状态刷新完成后才继续启动优化流程，慢摄像头探测会拖住首屏可交互状态。

### 修改内容

- **Bridge transport 串行化**（`apps/ui_backend.py`）：新增 `BridgeMessageWriter`，主线程 response 与后台 job event 共用同一个写锁输出 JSONL；`main()` 捕获协议 stdout 后将普通 `print`/第三方诊断输出重定向到 stderr，保证 stdout 只承载一行一个 JSON bridge 消息。
- **摄像头实时预览 backpressure**（`apps/ui_backend.py`）：视频源保留顺序处理；摄像头源改为采集线程持续覆盖 `_LatestPreviewFrameBuffer` 最新帧，推理/编码侧只取最新可用帧，并对 `session.frame` 做后端发送频率上限保护。首帧仍然是 `annotate()` 后的识别帧，不改成原始未识别帧；录制仍写 annotated 帧。
- **首屏启动解耦**（`frontend/src/App.vue`）：挂载 bridge 事件监听后立即返回渲染流程，`refreshCameras()` / `refreshModels()` 改为后台执行；模型状态刷新后再触发 `session.warmup`，失败只更新状态，不产生未处理 rejection。
- **回归覆盖**（`tests/test_ui_backend_contract.py`、`tests/test_ui_backend_sessions.py`、`frontend/scripts/frontend-smoke.mjs`）：新增并发 event/response JSONL 写入测试、慢推理高 FPS 假摄像头丢旧帧测试、首屏不再等待 `Promise.all([refreshCameras(), refreshModels()])` 的前端 smoke。

### 验证方法

- `.\.venv\Scripts\python.exe -m pytest tests/test_ui_backend_contract.py tests/test_ui_backend_sessions.py tests/test_windows_packaging_smoke.py -q` → 28 passed
- `npm --prefix frontend run test` → Frontend behavior smoke checks passed
- `npm --prefix frontend run build` → passed
- `npm run verify:desktop` → frontend build、frontend smoke、Tauri cargo check、Python compile smoke、122 desktop regression tests passed
- `.\.venv\Scripts\python.exe -m pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py -q` → 31 passed

## 2026-06-10: Web 前端预览性能优化（对齐 Tkinter 流畅度与启动速度）

### 问题描述

前端从 Tkinter 迁移到 Vue + Tauri 后出现两处体验回退：
1. 预览卡顿——同样 30fps 下 Web 端明显比 Tkinter 卡。
2. 启动慢——点击「开始」后要等较久才出现首帧。

根因定位：
- 卡顿主因是前端硬节流 `PREVIEW_FRAME_MIN_INTERVAL_MS = 100`（最多 10fps），后端发 30fps 也只画 10fps。
- 延迟主因是预览帧体积过大：`_default_frame_encoder` 用 OpenCV 默认 JPEG 质量 95，1280×720 单帧 50–100KB，base64 后更大，整帧走 stdout → Rust → Tauri，下游一慢即阻塞、旧帧排队累积延迟。
- 启动慢主因是 MediaPipe pipeline 在点「开始」后才同步创建，首帧前要等模型初始化数秒。

### 修改内容

- **前端节流放开**（`frontend/src/App.vue`）：`PREVIEW_FRAME_MIN_INTERVAL_MS` 100 → 16（~60fps 上限），对 30fps 源不再限速；取 16 而非 33，避免与 30fps 帧到达相位抖动导致周期性丢帧。仅作上限保护。
- **预览帧瘦身**（`apps/ui_backend.py` `_default_frame_encoder`）：新增模块常量 `PREVIEW_JPEG_QUALITY = 70`、`PREVIEW_MAX_EDGE = 960`；编码前对长边超 960 的帧用 `INTER_AREA` 下采样，并以质量 70 编码 JPEG。仅作用于送往前端的副本，**不影响录制原画质**（recorder 写的是原始 annotated）。
- **pipeline 预热与缓存复用**（`apps/ui_backend.py`）：`PreviewSessionService` 新增按 `(pose_variant, enable_hands)` 缓存的 pipeline；`_acquire_pipeline()` 对摄像头会话命中缓存则复用，会话结束时不关闭缓存实例（`run()` 的 finally 按 `pipe_cached` 跳过 `_close_quietly`）。视频文件不缓存复用（其时间戳按 frame_index 计算，跨文件回退会违反 VIDEO 模式时间戳单调约束）。新增 `session.warmup` 命令（`COMMANDS` / `handlers` / `_handle_session_warmup` / `PreviewSessionService.warmup` 四处接线），在后台 job 内预建 pipeline 入缓存。
- **前端触发预热**（`frontend/src/App.vue`）：`onMounted` 完成后触发一次 `session.warmup`；`poseVariant`/`enableHands` 变化且未运行时重新预热；预热失败静默，退回懒加载路径。

### 验证方法

- `npm run verify:frontend` → built（vue-tsc 类型检查通过）
- `npm --prefix frontend run test` → Frontend behavior smoke checks passed
- `pytest tests/test_ui_backend_contract.py tests/test_vue_tauri_acceptance_gaps.py tests/test_windows_packaging_smoke.py` → 26 passed
- `pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py` → 31 passed（MediaPipe 旧路径未漂移）
- 端到端手测（30fps 外接摄像头）：界面就绪后即后台预热，点「开始」首帧明显更快；预览帧率接近 30fps、延迟下降；录制导出仍为原分辨率/画质；切换 pose 变体后再开始正常（缓存按变体失效并重新预热）。

## 2026-06-10: 简化 Vue/Tauri 桌面端启动命令

### 问题描述

Vue/Tauri 开发启动需要先临时补 Cargo PATH，再执行 `npm --prefix frontend run tauri dev`，
每次手动输入较长，容易忘记或输错。

### 修改内容

- 根目录 `package.json` 新增 `npm run dev:desktop`，一条命令启动 Vue/Tauri 桌面端。
- 新增 `scripts/start-tauri-dev.ps1`，自动切到仓库根目录、补 `~\.cargo\bin` 到 PATH，
  再运行 `npm --prefix frontend run tauri dev`。
- 新增根目录 `start-desktop-dev.cmd`，可双击启动；失败时保留窗口并显示退出码。
- 启动脚本支持 dry-run：`scripts/start-tauri-dev.ps1 -DryRun`、`start-desktop-dev.cmd --dry-run`
  或 `npm run dev:desktop -- -DryRun`。

### 验证方法

- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-tauri-dev.ps1 -DryRun` → passed
- `cmd /c start-desktop-dev.cmd --dry-run` → passed
- `npm run dev:desktop -- -DryRun` → passed

## 2026-06-10: 修复 Tauri bridge 启动超时导致开始后长时间无预览

### 问题描述

Vue/Tauri 主窗口点击“开始”后，前端可能长时间等不到首个预览画面。排查发现模型文件已存在，
真正的阻塞点是 Python sidecar 在某些启动路径下缺少仓库根目录 `PYTHONPATH`，直接运行
`apps/ui_backend.py` 会报 `ModuleNotFoundError: No module named 'apps'` 并退出；Tauri 端因此一直等待
bridge response，直到 30 秒超时，前端还会出现 unhandled rejection。

### 修改内容

- 在 `apps/ui_backend.py` 导入 `apps.camera_enum` 前主动把仓库根目录加入 `sys.path`，让 sidecar
  直接以脚本方式启动时也能解析项目包。
- 保留 Tauri dev 启动时设置 `PYTHONPATH` / `PYTHONUTF8` / `PYTHONIOENCODING` 的现有保护。
- 在前端 bridge 中将 Tauri `invoke` 异常转换为统一 `ok=false` response envelope，保留
  `requestId/jobId/sessionId` 和原始错误信息，避免 Vue native handler unhandled rejection。
- 抽出 `sessionStartFailureState()`，让 `session.start` 失败时稳定清理 pending `sessionId/jobId`、
  复位运行态并显示“启动失败”。
- 新会话开始时重置预览帧节流计时，保证第一条有效 `session.frame` 不会被节流丢弃。
- 补充 sidecar 无 `PYTHONPATH` 启动 smoke、bridge invoke 失败 envelope、启动失败状态清理和首帧
  立即渲染的前端行为回归。

### 验证方法

- `npm --prefix frontend run test` → Frontend behavior smoke checks passed
- `npm --prefix frontend run build` → passed
- `.\.venv\Scripts\python.exe -m pytest tests/test_windows_packaging_smoke.py tests/test_vue_tauri_acceptance_gaps.py -q` → 15 passed
- `npm run verify:desktop` → frontend build、frontend smoke、Tauri cargo check、Python compile smoke、120 desktop regression tests passed

## 2026-06-10: 补齐当前 docs commit `7a45669` 的 active 证据链

### 问题描述

首轮最终验收复验时，`B-012+B-013` 仍指出当前 docs-only 提交 `7a45669` 没有进入 active 证据链，
导致 `docs/specs/progress.md` 的 Last Known Commit 仍停留在 `7d44b21`，复查者无法稳定重建当前文档状态。

### 修改内容

- 将 `docs/specs/progress.md` 的 Last Known Commit 更新为 `7a45669`，并同步刷新 checkpoint。
- 在 `docs/specs/tasks.md` 中追加 B-026，补入当前 docs commit 的证据链收口说明、波次、风险和完成日志。
- 在 `docs/specs/spec.yml` 中把 task_ids / task_graph 扩展到 B-026，确保机器索引与任务清单一致。
- 记录这次 docs-only 收口，避免后续复验继续看到旧的 moving-range 证据。

### 验证方法

- `.\.venv\Scripts\python.exe C:\Users\ny\.codex\plugins\cache\Useful-marketplace\spce-workflow\0.2.0\scripts\validate_spec.py docs\specs --resume`
- `.\.venv\Scripts\python.exe C:\Users\ny\.codex\plugins\cache\Useful-marketplace\spce-workflow\0.2.0\scripts\validate_spec.py docs\specs --pre-acceptance`
- `rg -n -- "7a45669" docs\specs change.md`
- `powershell -NoProfile -Command "$patterns = @('5526945' + '..HEAD', 'pending' + ' commit', '当前实现' + '提交', '- ' + '[ ]'); foreach ($p in $patterns) { rg --fixed-strings $p docs\specs README.md AGENTS.md change.md }"`
- `npm --prefix frontend run test`
- `pytest tests\test_windows_packaging_smoke.py -q`

## 2026-06-09: 修复 Vue/Tauri 迁移最终验收缺口

### 问题描述

Spce workflow final acceptance 的第一轮与对抗审查发现：已提交的 Vue/Tauri 迁移虽然通过构建、
后端 bridge 测试和打包 smoke，但 Vue 端尚未完整覆盖 Tkinter 用户可见功能，且 bridge 错误
`requestId`、job 停止语义、实时事件过滤、录制目录选择、动作分析/直拳技术评估、模型管理、
前端交互验证和 docs/specs 状态同步均存在缺口。

### 修改内容

- 修复 `apps/ui_backend.py` bridge 契约：manifest 补 `jobId/sessionId` 字段，错误路径保留原
  `requestId`，`job.stop` 仅对 pending/running job 成功。
- 强化 Vue 主窗口状态：新增 `none/camera/video` 三态、完整 raw JSON envelope 展示、当前
  `sessionId/jobId` 事件过滤、预览帧 UI 节流和实时流进度文案。
- 补齐 Vue 动作分析面板：支持模板生成、模板比对、起止帧、worker、预览导出、直拳技术评估
  的 stance/viewHint/debugVideo，并展示匹配分数、匹配片段、预览路径、技术指标、原因类型和失败环节。
- 补齐设置/模型管理面板：展示模型目录、逐模型路径、安装状态、文件大小，支持单模型下载、
  下载全部缺失、下载进度和取消。
- 补齐录制目录选择：Vue 调用 Tauri `select_directory`，Rust 侧使用 Windows Shell32 folder picker
  FFI；默认录制目录留空时回退 Python `outputs_dir()`，不再固定传相对 `outputs`。
- 新增 `tests/test_vue_tauri_acceptance_gaps.py` 与 `frontend/scripts/frontend-smoke.mjs`，并将
  `npm --prefix frontend run test` 接入 `npm run verify:desktop`；修复验证脚本未检查原生命令
  exit code 的问题。
- 将前端 smoke 从静态 marker 扫描升级为 behavior smoke：解析 Vue SFC 模板验证关键按钮绑定，
  并直接执行 `frontend/src/bridge-state.ts` 状态助手，覆盖 stale session/job 过滤、raw JSON envelope、
  未知总帧实时文案和模型下载失败展示。
- 修复首轮验收发现的状态语义缺口：启动未知总帧时不再显示 `0%`，`analysis.status` /
  `template.status` / `model.status` 统一按当前 `jobId` 隔离，模型下载失败不会被 `job.completed`
  误显示为“下载完成”。
- 修复复验发现的协议与竞态缺口：Python/Rust manifest request 契约补 `jobId/sessionId`，
  Rust `bridge.decode_error` 事件补完整 envelope；长任务发送前预分配 job/session id，避免
  快速任务事件早于 response 时被前端误过滤；缺失 ID 的 scoped event 不再污染当前 UI。
- 修复第一波最终验收新增缺口：manifest 显式声明 `jobId/sessionId` optional/nullable 语义，
  TS bridge envelope 支持 `null`；Windows Shell32 目录选择器增加 `OleInitialize` /
  `OleUninitialize`，并在 MTA 场景下禁用 `BIF_NEWDIALOGSTYLE` 降级。
- 修复模型下载完整性与关闭窗口清理：`download_model()` 在已知 `Content-Length` 但 EOF
  字节不足时抛错并删除 `.part`，不替换正式模型；Vue unmount 时复用 `cancelModelDownload`
  对 active 下载任务发送 `job.stop`。
- 补模型下载正式文件保护回归：中断下载时删除 `.part`，并断言已有正式 `.task` 文件字节不变。
- 将 `requirements.md`、README、AGENTS、`docs/specs/` 与 `change.md` 同步到复验后的最终证据链，
  并将旧的 moving HEAD 证据固化为 `5526945..3d6441b`。
- 将 `docs/specs/` 切换到 Bugfix 工作流并记录 B-001 至 B-017 的受控执行证据。
- 第一波最终验收回路修复实现范围：`3d6441b..8764f86`。
- 第一波重跑 B-008 复查发现 docs sync commit `3aa2578` 未纳入 active 证据链；本轮追加
  B-018 文档修复，记录 `3aa2578` 并将 grep 命令改为完整 HEAD 字符串拼接，避免自匹配。
- 第三轮第一波 B-016 复查发现卸载取消模型下载仅有 marker 覆盖；本轮追加 B-019，
  新增 `frontend/src/bridge-lifecycle.ts`，让 `App.vue` 卸载路径复用 `stopJobById`，
  并在 frontend behavior smoke 中用 stub 断言 `job.stop` 的 command、payload 和 options。
- 第四轮第一波 B-003 复查发现当前实时识别 job 异步失败后 UI 仍可能保持运行态；本轮追加
  B-020，让当前 session `job.failed` 映射为“运行失败”终态并清理运行状态，同时补充
  current/foreign failed event 的 behavior smoke 断言。
- 第五轮第一波 B-003 复查发现早到 `job.failed` 会被后到 `session.start` response 覆盖为运行态；
  本轮追加 B-021，让 response 只有在 pending `sessionId/jobId` 仍匹配时才可置为运行，并补充
  `shouldApplySessionStartResponse` 行为断言。同时将 B-019/B-020 证据固化为 `920b06d` / `2e94534`，
  修正 B-018 PowerShell grep 命令为单引号 `-Command`，并将 B-013 完成态证据改为 resume/pre-acceptance。
- 第六轮第一波 B-014 复查发现 request-side `jobId/sessionId` nullable 语义未写入 Python/Rust
  manifest；本轮追加 B-022，在两端 manifest 的 `nullable.request` 中显式声明 `jobId/sessionId`，
  并用 Python contract test 和 Rust source smoke 锁定该契约。同时清理 B-013/B-018 详细任务证据中的
  stale wording，避免最终验收继续把历史结构检查当成完成态证明。
- 第七轮第一波 B-005 复查发现组合 `analysis.run` 在 compare 后收到 `job.stop` 仍会继续执行
  tech eval/debug export；本轮追加 B-023，在 compare 后和 tech eval/debug export 前检查停止标记，
  并补充 compare+tech eval 组合停止回归。同时将 README/AGENTS/change/specs 的最新桌面验证证据
  同步到当前 `npm run verify:desktop` 结果。
- 第二波对抗审查发现 B-003/B-006/B-009/B-019+B-020 仍有四个前端生命周期和覆盖缺口：
  预览帧节流缺少行为测试、模型下载 early failed/stopped 可能被 late start response 覆盖为“下载中”、
  已安装模型无法像 Tkinter 一样“重新下载”、窗口卸载未停止 active analysis/template job。本轮追加
  B-024（实现提交 `eab6894`，docs sync 提交 `2b4ae3d`）：抽出 `shouldRenderPreviewFrameAt` 与
  `shouldApplyModelDownloadStartResponse` 行为 helper，Vue 只在 pending model job 仍匹配时应用
  start response；已安装模型按钮显示“重新下载”并复用固定 `modelKey` 下载；unmount 复用
  `stopJobById` 停止 active analysis/template job；frontend smoke 增加对应行为断言。
- B-024 后首轮复验 B-007 发现 sidecar 构建脚本未检查 PyInstaller 退出码，且旧
  `dist\vision-ui-backend.exe` 可能在失败构建后继续被复制进 Tauri resources。本轮追加 B-025
  （实现提交 `7d44b21`）：`scripts/build-tauri-sidecar.ps1` 在运行 PyInstaller 前删除旧 sidecar，
  运行后检查 `$LASTEXITCODE`，非零即失败；只有新产物存在才复制。`tests/test_windows_packaging_smoke.py`
  锁定删除旧产物、退出码检查和复制顺序。

### 验证方法

- `npm --prefix frontend run test` → Frontend behavior smoke checks passed；覆盖 B-019 的 active model download unmount helper 精确 `job.stop` 断言。
- `pytest tests/test_vue_tauri_acceptance_gaps.py -q` → 6 passed（B-019），第一波新增修复后随组合测试为 13 passed。
- `npm --prefix frontend run build` → passed。
- `npm --prefix frontend run test` → Frontend behavior smoke checks passed；覆盖 B-020 的 current/foreign `job.failed` 和 session failed terminal status。
- `pytest tests/test_ui_backend_sessions.py tests/test_input_source_state.py tests/test_vue_tauri_acceptance_gaps.py -q` → 21 passed。
- `pytest tests/test_ui_backend_models.py tests/test_vue_tauri_acceptance_gaps.py -q` → 13 passed。
- `npm --prefix frontend run test` → Frontend behavior smoke checks passed；覆盖 B-021 的早到 failed 阻止 late response 复活运行态。
- `npm run verify:desktop` → Desktop stack verification passed，含 120 条 Python desktop regression tests。
- `npm --prefix frontend run test` → Frontend behavior smoke checks passed；覆盖 B-024 的预览帧节流、
  模型下载 early terminal late response guard、已安装模型重新下载 marker 和 analysis/template unmount stop helper。
- `npm --prefix frontend run build` → passed（B-024 后重新验证）。
- `pytest tests/test_vue_tauri_acceptance_gaps.py tests/test_ui_backend_models.py tests/test_ui_backend_sessions.py tests/test_input_source_state.py -q` → 28 passed。
- `npm run package:windows` → 重新生成 NSIS 安装包：
  `frontend/src-tauri/target/release/bundle/nsis/Vision 动作识别与评分_0.1.0_x64-setup.exe`。
- `pytest tests/test_windows_packaging_smoke.py -q` → 8 passed；覆盖 B-025 sidecar 构建脚本的旧产物删除、PyInstaller 退出码检查和复制顺序。
- `npm run package:windows` → 在 B-025 hardened sidecar 脚本下重新生成 NSIS 安装包。
- `npm run verify:desktop` → Desktop stack verification passed，含 120 条 Python desktop regression tests（B-025 后）。
- `pytest tests/test_ui_backend_contract.py tests/test_windows_packaging_smoke.py -q` → 19 passed；覆盖 B-022 request nullable manifest/parity。
- `C:\Users\ny\.cargo\bin\cargo.exe check`（`frontend/src-tauri`）→ passed；覆盖 B-022 Rust manifest 更新。
- `pytest tests/test_ui_backend_contract.py tests/test_windows_packaging_smoke.py -q` → 17 passed。
- `pytest tests/test_ui_backend_contract.py tests/test_ui_backend_models.py tests/test_vue_tauri_acceptance_gaps.py tests/test_windows_packaging_smoke.py -q` → 29 passed（前序复验组合）。
- `C:\Users\ny\.cargo\bin\cargo.exe check`（`frontend/src-tauri`）→ passed。
- `py_compile apps/app_ui.py apps/ui_backend.py core/vision_pipeline.py` → passed。
- `pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py -q` → 31 passed。
- `pytest tests/test_ui_backend_analysis.py -q` → 5 passed；覆盖 B-023 组合动作分析停止后跳过 tech eval/debug export。
- `pytest tests/test_ui_backend_analysis.py tests/test_ui_backend_contract.py tests/test_windows_packaging_smoke.py tests/test_vue_tauri_acceptance_gaps.py -q` → 30 passed。
- `npm run verify:desktop` → 前端 build/test、Tauri `cargo check`、Python py_compile、120 个桌面回归测试通过。
- `pytest tests/test_windows_packaging_smoke.py -q` → 8 passed；其中 `frontend/src-tauri/resources/vision-ui-backend.exe`
  实际响应 `bridge.ping`，返回 bridge version `1.0` 且包含 `model.download` 命令。
- `npm run package:windows` → 生成
  `frontend/src-tauri/target/release/bundle/nsis/Vision 动作识别与评分_0.1.0_x64-setup.exe`。
- `git diff --check` → 仅 LF/CRLF warning，无 whitespace error。

---

## 2026-06-09: 迁移前端到 Windows-only Vue + Tauri + Vite，并保留 Python 后端契约

### 问题描述

需要把现有 Tkinter 前端迁移到 Vue + Tauri + Vite，同时满足三条边界：后端不动、完整覆盖
现有 Tkinter 用户可见功能、只做 Windows。迁移还需要能在本机开发、验证和打包，且不能破坏
MediaPipe 默认 `pose33_v3`、`infer()`/`annotate()`、golden 回归、`valid_mask` 与 YOLO 未授权
评分边界。

### 修改内容

- 新增 `frontend/`：Vue + Vite + Tauri + TypeScript 工程，提供主窗口、预览区、状态区、
  录制控制、动作分析入口、模型状态/下载入口与 raw JSON 展示。
- 新增 `apps/ui_backend.py`：JSON bridge 进程，封装摄像头枚举、识别会话、录制三态、
  模板生成、模板比对、直拳技术评估、模型状态和模型下载；调用既有 Python 后端，不把算法迁移到
  Rust/TypeScript。
- 新增 Tauri Rust bridge：管理持久 Python bridge 子进程，转发 `bridge-event` / `bridge-stderr`，
  开发期使用 `.venv\Scripts\python.exe -u apps/ui_backend.py`，打包期优先启动
  `vision-ui-backend.exe` sidecar。
- 新增 Windows 打包链路：`ui_backend_sidecar.spec`、`scripts/build-tauri-sidecar.ps1`、
  `packaging/pyinstaller/pyi_rth_video_writer_alias.py`，并在 Tauri `resources/` 中打包 Python bridge
  sidecar；新增根目录脚本 `verify:desktop`、`build:sidecar`、`package:windows`。
- 新增迁移验证测试：bridge 契约、job 生命周期、实时会话、动作分析、模型管理、Windows packaging
  smoke；补充 `requirements-dev.txt` 中 Hypothesis 测试依赖。
- 旧 `apps/app_ui.py` 保留为 Tkinter 入口，仅做测试 stub 兼容的小范围修补，避免既有 UI 控件测试失败。
- 更新 `README.md` 与 `AGENTS.md`，说明新前端开发、验证和 Windows 打包命令。

### 验证方法

- `npm run verify:desktop` 通过：前端 build、Tauri `cargo check`、`py_compile apps/app_ui.py apps/ui_backend.py core/vision_pipeline.py`、
  106 个桌面迁移相关 Python 回归测试通过。
- `npm run package:windows` 通过，生成
  `frontend/src-tauri/target/release/bundle/nsis/Vision 动作识别与评分_0.1.0_x64-setup.exe`。
- `pytest tests/test_windows_packaging_smoke.py -q` → 6 passed。
- `frontend/src-tauri/resources/vision-ui-backend.exe` 使用 `bridge.ping` 返回协议版本 `1.0`。

---

## 2026-06-07: 移除主界面「选择视频…」功能

### 问题描述

主界面「次要选项」里的「选择视频…」按钮用于把输入源从摄像头切换为本地视频文件，
但实际使用中暂无明确场景（离线视频分析有独立的 CLI 与「动作分析」窗口承担），保留
该入口反而增加界面复杂度，故移除。

### 修改内容

- `apps/app_ui.py`：
  - 删除「次要选项」分组里的「选择视频…」按钮；保留其下方的输入源提示 Label
    （摄像头选择仍复用 `source_hint_var` 显示当前选中的摄像头）。
  - 删除 `_browse_video` 方法（约 24 行）：文件选择对话框、文件存在/可打开校验、
    切换到 video 输入源的逻辑。
  - 删除 `_start_enumeration` 中「若当前已选视频则不抢占输入源」的死分支
    （`if self._source_state.kind == "video": return`），因不再可能选中视频。
  - 保留 `cv2` / `filedialog` 导入（其它处仍在使用）；`camera_enum.InputSourceState`
    的 `select_video`/`"video"` 分支保留（不影响摄像头路径，且 CLI 仍可走文件源）。

### 验证方法

- `py_compile apps/app_ui.py` 通过。
- 摄像头枚举/选择、启动处理流程不受影响（仅移除视频输入入口）。

---

## 2026-06-07: 将「直拳检测」融合进「动作比对」（合并为单视频「动作分析」窗口）

### 问题描述

主界面同时存在「动作比对…」和「直拳检测…」两个入口，功能高度重合（都吃动作/拳击
视频、都跑 MediaPipe 姿态分析、都给质量评估），但分属两个独立 Toplevel 窗口，输入口
径不一致（模板比对单视频 vs 直拳检测目录批量），用户需要在两个窗口间来回切换。

### 修改内容

- `apps/app_ui.py`：
  - `CompareWindow` 重构为单视频「动作分析」窗口（标题改为「动作分析（模板比对 +
    直拳技术评估）」）：选**一个**目标视频，按勾选一次性得到「模板相似度」与
    「直拳技术指标」。
  - 「① 准备模板」分组加「启用模板比对」开关（`do_compare_var`）：关闭时隐藏模板
    准备区/预览行/大号相似度显示，仅做技术评估，因此模板变为可选。
  - 新增「② 直拳技术评估」选项区（`do_tech_var` 开关 + 站姿/视角下拉 + 导出调试视频），
    融合自原 `TechEvalWindow` 但改为针对单视频；结果区新增「直拳技术指标」明细文本框。
  - `_start_compare` 重写为按开关顺序执行模板比对（`compare_video_to_template`）与
    技术评估（`evaluate_video_detail`/`evaluate_video_assets`），合并输出到统一 JSON
    详情；新增 `_run_tech_eval`、`_set_detail`、`_toggle_compare_section`、
    `_toggle_tech_section` 方法。
  - **删除** `TechEvalWindow` 类（约 420 行）及其入口：`_open_tech_eval` 方法、
    `_tech_eval_win` 字段、「次要选项」里的「直拳检测…」按钮。
  - 主操作面板按钮文案「动作比对…」→「动作分析…」。
  - 移除原直拳检测的「目录批量 / CSV+JSONL 报告」能力（按用户确认弱化为单视频）；
    调试视频改为可选项，落盘到 `outputs_dir()/<stem>_debug_<ts>.mp4`。

### 验证方法

- `python -m py_compile apps/app_ui.py` 通过。
- AST 静态检查：`CompareWindow` 引用的方法全部存在，`TechEvalWindow` 已不存在。
- GUI 冒烟：构造 `CompareWindow`，在 do_compare/do_tech 三种开关组合下切换显隐与
  `_set_detail` 均不抛异常。
- `pytest tests/test_ui_controls.py tests/test_layout_structure.py
  tests/test_recording_controller.py` → 20 passed（解释器退出阶段相机枚举线程的
  access violation 为既有 flaky 噪声，改动前后一致，不影响测试结果与退出码）。

---

## 2026-06-07: 移除「导出结果视频」选项，新增录制视频保存目录

### 问题描述

主界面「次要选项」里的「导出结果视频」勾选项 + 「选择保存位置…」整行已无实际消费方
（识别会话的落盘完全由 `RecordingController` 负责，`UiState.save_output/out_path`
没有任何读取点），属于冗余 UI。同时「录制」功能此前固定写到 `outputs_dir()`，用户
无法自选保存目录。

### 修改内容

- `apps/app_ui.py`：
  - 删除「次要选项」中的「导出结果视频」`Checkbutton` 及其「选择保存位置…」行
    （`out_row`/`out_entry`/`out_btn`），以及配套的 `save_var`/`out_var` 变量、
    `_toggle_out()` 与 `_choose_out()` 方法。
  - `UiState` 移除不再被消费的 `save_output` / `out_path` 字段；`_collect_state()`
    同步去掉相关校验与赋值。
  - 「录制」分组新增「保存目录：」`Entry` + 「选择…」按钮，绑定新变量
    `record_dir_var`（默认 `str(outputs_dir())`），按钮回调 `_choose_record_dir()`
    使用 `filedialog.askdirectory` 选目录。
  - `RecordingController` 改为注入 `path_provider=self._record_path`：在用户选择的
    目录下按 `record_<timestamp>.mp4` 时间戳生成文件名，目录为空时回退 `outputs_dir()`。

### 验证方法

- `python -m py_compile apps/app_ui.py` 通过。
- `pytest tests/test_recording_controller.py tests/test_ui_controls.py
  tests/test_layout_structure.py` → 18 passed, 2 skipped。
- `test_app_controls.py` 的 6 个失败为既有问题（stub 缺 `_sync_record_stop_enabled`
  等属性），与本次改动无关（改动前 stash 后复现同样 6 failed）。

---

## 2026-06-09: 设置面板（模型管理）+ onefile 单文件打包（用户自助下载模型）

### 问题描述

希望只分发单个 `vision_ui.exe`，模型由使用者自行下载安装。需要：(1) UI 增加「设置」入口，
内含「当前模型」展示与缺失模型「下载」按钮（本期只放 MediaPipe）；(2) 把 UI 打包成单文件
exe，且不能因 CUDA 版 torch 把体积撑到 GB 级。

### 修改内容

- 新增 `core/model_manager.py`：MediaPipe 模型清单与下载工具（仅依赖标准库 + `core.paths`）。
  - `MEDIAPIPE_MODELS`：pose lite/full/heavy + hand 四个 `ModelSpec`（key/filename/官方 url/label/approx_mb）。
  - `is_installed` / `installed_size_mb` / `model_path` 状态查询。
  - `download_model(progress_cb, should_stop)`：下载到 `.part` 临时文件后原子改名，可中断、带进度；
    网络异常向上抛出由 UI 提示。下载源固定官方直链 `storage.googleapis.com`（国内无稳定免代理镜像，
    经实测官方源可达，决定让用户自行配置代理）。
- `core/vision_pipeline.py`：`_pose_model_url()` 改为复用 `core.model_manager` 的清单，消除 URL 重复。
- `apps/app_ui.py`：
  - 主操作面板右上角新增「⚙ 设置」按钮（`_open_settings`），打开时传入当前 pose 档位与 hands 开关。
  - 新增 `SettingsWindow`：顶部「当前模型」区汇总当前使用的姿态模型 + 手部检测开关及就绪/缺失状态；
    下方 MediaPipe 模型列表逐行显示安装状态（使用中的行标注「● 使用中」）+ 下载/重新下载按钮；
    支持「下载全部缺失模型」「刷新状态」，后台线程下载 + 进度条，失败弹框提示多为网络问题。
- 新增 `app_ui_onefile.spec`：PyInstaller 单文件打包。
  - 不用 `collect_submodules` 粗放收集 analysis/batch（会顺着 `core.yolo_adapter` 的
    `from ultralytics import YOLO` 把 CUDA 版 torch≈4.2GB 整条链打进来，导致 exe 膨胀到 3GB）。
  - 改为显式列出 UI 实际用到的内部模块，并通过 `excludes` 切断 torch/torchvision/ultralytics/
    onnx*/tensorrt/nvidia*/yolo_adapter 等重依赖。

### 构建步骤

```powershell
.\.venv\Scripts\python.exe -m PyInstaller app_ui_onefile.spec --noconfirm --clean
```

产物：`dist/vision_ui.exe`（单文件，117 MB，可单独分发）。

### 验证方法

- 编译：`.\.venv\Scripts\python.exe -m py_compile .\apps\app_ui.py .\core\model_manager.py .\core\vision_pipeline.py .\core\paths.py`（通过）。
- SettingsWindow 逻辑 smoke：full+hands 激活 `{pose_full, hand}`、heavy+无 hands 激活 `{pose_heavy}`，
  「当前模型」汇总与「● 使用中」标注正确。
- onefile 体积从误打 torch 的 3033 MB 降到 117 MB（torch 成功排除）。
- 干净临时目录（无 models）启动 `vision_ui.exe` ≥25 秒未崩溃，且 exe 旁自动创建 `models/` 目录
  （冻结模式路径解析锚定到 exe 所在目录，用户下载的模型落到此处）。

### 分发说明

- 只需分发 `dist/vision_ui.exe` 一个文件。
- 用户首次运行后，打开「设置 → MediaPipe 模型」下载所需模型（pose full ≈9MB + hand ≈7.5MB 即可用）。
- 下载走 Google 官方源，国内用户需自备代理；也可手动下载后放入 exe 同级 `models/` 目录。
- onefile 首次启动需解压运行时到临时目录，比 onedir（`app_ui.spec`）略慢，属正常现象。

---

## 2026-06-09: PyInstaller 打包桌面 UI 为 Windows 可执行程序

### 问题描述

需要将项目打包成可独立分发的 Windows 可执行程序（.exe），便于在没有 Python 环境的机器上运行桌面 UI（`apps/app_ui.py`）。

### 修改内容

- `core/paths.py`：`repo_root()` 增加 PyInstaller 冻结模式判定。当 `sys.frozen` 为真时，artifact 根目录（models/templates/outputs）锚定到**可执行文件所在目录**而非临时解压目录 `sys._MEIPASS`，避免运行结束后目录被清空、模型/输出找不到。源码运行行为保持不变。
- 新增 `app_ui.spec`：PyInstaller 打包配置（onedir 模式）。
  - `collect_all("mediapipe")` 整包收集 MediaPipe 的数据文件（`.binarypb` / modules 等）与二进制。
  - `collect_submodules` 收集 core/apps/analysis/batch 内部包，并补齐 `pygrabber`、`PIL._tkinter_finder`、`cv2` 等隐藏导入。
  - `console=False`（GUI 程序，无控制台窗口）；排除 `hypothesis`/`pytest` 测试依赖。
  - 模型文件不嵌入二进制，构建后复制到 exe 同级 `models/`，便于替换/增量更新，并与冻结模式路径解析一致。
- 安装构建工具：`pyinstaller 6.20.0`（经本地代理 `127.0.0.1:7890`）。

### 构建步骤

```powershell
.\.venv\Scripts\python.exe -m PyInstaller app_ui.spec --noconfirm
Copy-Item -Path .\models -Destination .\dist\vision_ui\models -Recurse -Force
```

产物：`dist/vision_ui/`（入口 `vision_ui.exe`，含 models 共约 5.0 GB）。

### 验证方法

- 构建成功，`Build complete`。
- 启动 `dist/vision_ui/vision_ui.exe`，进程持续运行 ≥12 秒未崩溃，UI 正常加载（Tkinter 窗口启动成功）。

---

## 2026-06-06: 实时多核并行姿态推理（heavy CPU 提速 ~11fps → 30+fps）

### 问题描述

用户用 heavy 模型实时识别时 FPS 低、且 CPU 利用率只有 ~10% 拉不上去。前序排查已排除采集端
（外接摄像头 30fps 不是瓶颈）。用真人画面实测：heavy 单帧 ~56ms（~15-18fps）、heavy pose-only
~41ms（~24fps），是真·CPU 算力瓶颈。但单条 MediaPipe VIDEO 管线只用到底层少数线程，在 32
逻辑核机器上整机利用率极低——一个满载核心仅占 ~3%，其余 ~28 核闲置。

GPU delegate 复测（含 heavy，补齐 `docs/mediapipe_gpu_delegate_report.md` 之前只测 full 的空白）
确认对 heavy 无收益（中位延迟基本持平，仅延迟更稳定）：桌面 MediaPipe GPU delegate 走
OpenGL/CL，每帧上传/下载图像的传输开销抵消了计算节省，且无法切到 Vulkan / 用 Rust 绕开
（推理本就是 native C++，Python 非瓶颈）。因此选择 CPU 多核并行方案。

### 修改内容

- 新增 `core/parallel_pose_engine.py`：可复用、可测试的多 worker 并行姿态推理引擎。
  - 每个 worker 独立持有一条 IMAGE 模式 `MediaPipePipeline`（landmarker 非线程安全）。
  - reader→有界输入队列→N worker→collector 按帧序号重排→有序输出队列。
  - 实时模式 `drop_when_full=True`：输入队列满则丢弃新帧以约束端到端延迟；离线模式
    `drop_when_full=False`：阻塞背压保证每帧都处理。
  - `signal_input_done()` 与 worker / collector 的入队均改为可中断（非阻塞哨兵 + 带超时
    重试 + stop 检查），修复了 reader/worker/collector/consumer 四方背压死锁。
  - `default_pipeline_factory()` 工厂、`InferResult` 结果结构、`stats`（submitted/dropped/
    emitted）、`take_error()` 错误传播。
- `apps/main.py`：新增 `run_realtime_parallel()`，摄像头源 + `--workers>1` 时走多核并行实时
  路径（满则丢帧）；`main()` 路由补充摄像头并行分支；`--workers` 帮助文案更新为同时适用于
  离线视频与实时摄像头。
- `apps/app_ui.py`：新增 `_worker_loop_parallel_camera()`，摄像头 + 线程数>1 时走并行引擎；
  `_worker_loop` 增加摄像头并行分支；线程数控件标签由「离线线程数（视频文件）」改为
  「线程数（>1：多核并行，关闭时序平滑）」。
- 默认行为不变：线程数=1 时仍走单线程 VIDEO 模式（保留时序跟踪/平滑）。并行模式为显式
  opt-in，代价是失去 VIDEO 时序平滑（骨架更抖）。
- 修复 `tests/test_s5_hands_toggle.py` 两个陈旧用例：补上 `_source_state` 构造，使其与
  camera-dropdown 后的 `_collect_state` 实现一致。

### 验证方法

- 编译：`.\.venv\Scripts\python.exe -m py_compile .\apps\main.py .\apps\app_ui.py .\core\parallel_pose_engine.py`（通过）。
- 引擎测试：`.\.venv\Scripts\python.exe -m pytest tests\test_parallel_pose_engine.py -q`（5 passed：
  有序完整性、多 worker 单调有序、丢帧无空洞、错误传播、资源释放）。
- 相关回归：`tests\test_s5_hands_toggle.py tests\test_s5_realtime_latest_frame.py tests\test_camera_enum.py tests\test_s5_ui_no_go.py`（30 passed）。
- 真实人物视频吞吐实测（heavy + hands）：workers=1 → 10.8fps，2 → 19.0fps，4 → 31.8fps，
  6 → 40.9fps，近线性扩展；heavy 实时从 ~11fps 提升到 4 worker 30+fps。

### 备注

- 全量 `pytest tests` 中存在两类与本改动无关的预存在失败：`test_camera_enum.py` 真实 DShow
  摄像头并发探测偶发 native access violation；`test_app_controls.py` 6 例属于尚未完成的录制/
  UI 重构功能（`_sync_record_stop_enabled` 桩缺失）。二者均非本次并行引擎引入。

---

## 2026-06-06: 修复摄像头实时帧率低（YUY2 带宽瓶颈）+ heavy 模型 CPU 利用率低

### 问题描述

用户用 heavy 模型实时识别时反馈：FPS 很低，且 CPU 利用率只有 ~10% 拉不上去。

经定位，这是典型的「等待型瓶颈」——瓶颈不在算力而在采集端：

- 单帧推理实测（合成帧）：heavy pose-only ~10ms（~100fps）、heavy+hands ~18ms（~54fps），
  与 full 几乎一致。模型并非瓶颈。
- 摄像头实测：原代码用 `cv2.CAP_DSHOW` 打开摄像头并请求 720p，设备退回到未压缩的
  **YUY2** 像素格式，受 USB 带宽限制，720p 仅 ~10fps（640x480 也才 15fps）。
- 主循环大部分时间阻塞在 `cap.read()` 等待下一帧，因此 CPU 长期空闲、整体 FPS 被采集端钉死。
- 后端对比：`cv2.CAP_MSMF` 能协商到压缩格式，720p 直接跑满 **30fps**；DSHOW 即便强制
  MJPG 在本机也未生效（仍 YUY2）。

### 修改内容

- `apps/camera_enum.py`：新增 `open_camera(index, *, width=1280, height=720)` 共享 helper。
  按 `CAP_MSMF`（最优）→ `CAP_DSHOW + 强制 MJPG`（压缩格式回退）→ 朴素 `CAP_DSHOW`（兜底出图）
  的顺序协商高帧率采集格式，并设置请求分辨率。
- `apps/main.py`：`_open_capture()` 摄像头分支改用 `open_camera()`；移除 `run()` 与
  realtime-latest-frame smoke 路径里多余的 `cap.set(FRAME_WIDTH/HEIGHT)`（helper 已处理）。
- `apps/app_ui.py`：`_worker_loop()` 摄像头打开改用 `open_camera()`。
- 视频文件路径（非数字源）行为保持不变，仍走 `cv2.VideoCapture(source)`。

### 验证方法

- 编译检查：`.\.venv\Scripts\python.exe -m py_compile .\apps\main.py .\apps\app_ui.py .\apps\camera_enum.py`（通过）。
- 端到端实测（摄像头 0）：`open_camera(0)` 协商到 720p/30fps；原始采集 30.0fps；
  heavy+hands 端到端 18.4fps（瓶颈转移到 hand landmarker，符合预期，采集不再拖后腿）。
- 提速幅度：摄像头采集 10fps → 30fps（3x）；实时识别 FPS 不再被采集端限制。

### 备注

- 若仍想进一步提速 heavy+hands，可关闭 hands（`--no-hands` / UI 选项），pose-only 端到端可达 ~30fps（受采集上限）。
- 与 `docs/mediapipe_gpu_delegate_report.md` 结论一致：本机 MediaPipe GPU delegate 对实时链路无明显收益，未改默认 CPU 路径。

---

## 2026-06-06: 录制控制拆分为「开始/暂停/继续 + 结束录制」并独立成组

### 问题描述

桌面 UI（`apps/app_ui.py`）主操作面板里，录制只有一个三态切换按钮（开始录制→暂停录制
→继续录制），而「结束录制」被隐式合并进会话级的「停止」按钮。用户反馈布局不直观：
录制看不到独立的「结束录制」入口，且录制按钮与会话级「开始/停止」混在同一列，难以区分。

### 修改内容

- `core/recording_controller.py`：新增 `stop_recording()` 方法。
  - 结束当前录制片段：释放 writer、状态复位 `idle`、清空 `_result_path`/`_frames_written`，
    但**保持会话运行**（`_session_active` 不变），使用户可在同一识别会话内重新「开始录制」
    生成新的文件片段。与 `close_session()`（结束整个会话）区分开。
  - 会话未运行时为 no-op；返回本片段实际落盘路径或 `None`。
- `apps/app_ui.py`：
  - 主操作面板新增独立的「录制」`Labelframe` 分组，把录制相关按钮与会话级「开始/停止」
    在视觉上分开。组内含：三态切换按钮（`record_btn`）+ 新增「结束录制」按钮（`record_stop_btn`）。
  - 新增 `_on_record_stop()` 回调：调用 `stop_recording()`，复位切换按钮文本为「开始录制」、
    禁用「结束录制」。
  - 新增 `_sync_record_stop_enabled(state)`：录制中/已暂停时启用「结束录制」，idle 时禁用；
    在 `_on_record_toggle`、`_refresh_recording_status`（覆盖 worker 端错误复位）、
    `_set_running_controls` 中联动调用。
  - 导入补充 `RecordingState` 类型。

### 验证方法

- 编译检查：`.\.venv\Scripts\python.exe -m py_compile .\apps\app_ui.py .\core\recording_controller.py`（通过）。
- 属性测试：`.\.venv\Scripts\python.exe -m pytest tests\test_recording_controller.py -q`（10 passed）。
- UI 交互（录制三连按钮可用性、结束录制后可重新开始）需手动运行 `apps/app_ui.py` 验证。

---

## 2026-06-06: UI 摄像头下拉选择（camera-dropdown-selection）

### 问题描述

桌面 UI（`apps/app_ui.py`）原先通过自由文本框手动输入摄像头编号（数字），不直观，
用户无法预知系统上有哪些可用摄像头。需求改为：从“当前可调用的摄像头列表”中以下拉菜单
直观选择，同时保留对视频文件路径输入的支持。spec 见
`.kiro/specs/camera-dropdown-selection/`（requirements / design / tasks）。

### 修改内容

- 新增 `apps/camera_enum.py`（不依赖 tkinter，可独立测试）：
  - `CameraEntry`、`make_label`（编号→显示文本，单射）、`clamp_scan_limit`（钳制到 [1,32]）。
  - `probe_camera`：DSHOW 后端探测单个编号，判定可用 = `isOpened()` 且能 `read()` 到非空帧；
    子线程 + `join(timeout)` 实现 2s 超时保护，`finally` 释放资源；异常视为不可用。
  - `enumerate_cameras`：注入式 `probe`，从 0 扫描至钳制后上限（默认 5），返回升序去重条目列表。
  - `InputSourceState`：camera / video / none 三态互斥状态模型，维护“任一时刻至多一个生效源”不变式。
- 改造 `apps/app_ui.py` 的 `App` 输入区：
  - 用只读 `ttk.Combobox` 替代原摄像头编号 `ttk.Entry`（移除自由文本框）；保留“选择视频…”；
    新增“刷新”按钮与“当前输入源”指示标签。
  - 启动时后台线程枚举摄像头，结果经 `root.after` 回写；空列表禁用下拉并提示“未检测到可用摄像头”。
  - `_on_camera_selected` / `_browse_video`（含视频可打开校验）/ `_refresh_cameras` /
    `_start_enumeration` / `_apply_camera_entries` / `_set_refresh_enabled`。
  - 采集运行中与枚举进行中禁用刷新；`_collect_state` 在无输入源时报错；`_worker_loop` 沿用
    `source.isdigit()` 分支保持兼容（数字→DSHOW 摄像头，否则按路径打开）。
- 新增测试：`tests/test_camera_enum.py`（Property 1/2/3 + probe_camera 示例：未打开/空帧/非空帧/超时/release）、
  `tests/test_input_source_state.py`（Property 4 互斥不变式 + 状态切换示例 + 刷新门控）。
- `requirements.txt`：补充测试依赖 `hypothesis`、`pytest`。

### 验证方法

- 编译检查：`.\.venv\Scripts\python.exe -m py_compile .\apps\app_ui.py .\apps\camera_enum.py`（通过）。
- 单元/属性测试：`.\.venv\Scripts\python.exe -m pytest tests/test_camera_enum.py tests/test_input_source_state.py`（18 passed）。
- 模块导入：`python -c "import apps.app_ui"`（OK）。
- 真实硬件（下拉枚举、刷新、采集打开摄像头/视频）需手动运行 `apps/app_ui.py` 验证。

### 后续补充（设备友好名）

- 下拉项原为“摄像头 N”，应用户要求改为显示 Windows 设备友好名，如
  “摄像头 0: USB2.0 HD UVC WebCam”。
- `apps/camera_enum.py` 新增 `list_device_names()`：通过 `pygrabber`（DirectShow）读取
  摄像头友好名，顺序与 OpenCV DSHOW 索引一致；任何失败（含缺依赖/非 Windows）回退空列表。
- `make_label(index, name=None)` 支持带设备名格式，缺名时回退“摄像头 N”；
  `enumerate_cameras` 新增可注入的 `names` 回调，按索引合并设备名（越界回退无名）。
- `requirements.txt` 补充 `pygrabber`。新增测试覆盖设备名合并与越界回退。

---

## 2026-06-02: 完成 #44 离线 DTW / 序列提取 profile 与优化决策

### 问题描述

Issue #44 要求对 batch/offline 匹配链路做 profile，区分模型推理、特征归一化、DTW、
多段匹配和视频 I/O 的耗时占比，再决定是否优化 DTW 或缓存。本 issue 明确要求先 profile
后优化；若没有证据，不得修改 `subsequence_dtw`、baseline、阈值或评分输出。

### 修改内容

- `analysis/offline_matching_profile.py`：
  - 新增独立 profile harness，不接入默认 CLI/UI 或生产评分路径。
  - 支持 `--fixture-smoke` 使用 `tests/fixtures/pose33_v3` 与 golden harness 做无模型回放。
  - 支持传入 `--front-template/--side-template/--video` 对真实本地视频做 staged profile。
  - staged profile 会按双模板 metadata 选择与生产入口一致的 normalizer；本地
    `templates/standard_front_full.npz` / `standard_side_full.npz` 为旧 v2 模板，因此真实视频
    profile 明确记录 `normalizer_version=v2`。
  - 对视频读取和 MediaPipe pipeline 初始化失败路径补齐资源释放，避免 profile 异常时遗留句柄。
  - 输出 JSON/CSV，记录 `compare_video_to_dual_templates` 与 `match_body_core_template`
    的分段耗时、summary 与决策表。
- `docs/offline_matching_perf_profile.md`：
  - 记录 fixture profile、本地 90 帧视频 profile、DTW/序列提取占比和决策表。
  - 本地真实视频前 90 帧记录显示 MediaPipe Pose 推理 86.98%、视频读取 11.16%、
    特征归一化 1.34%、view score 0.15%，DTW / fallback DTW 合计约 0.27%；全局
    5 条 records 汇总的 `sequence_percent` 为 94.52%。
  - 结论为本 PR 不改 DTW；若后续优化，优先另开 raw/feature cache issue。
- `tests/test_s5_offline_profile.py`：
  - 覆盖 fixture profile 写出 JSON/CSV、schema、stage 字段。
  - 校验 staged profile 与生产函数 fixture 输出一致：`pose33_v3 combined_percent=38`、
    `combined_score`、双视角分、匹配区间、match 数量，以及 `body_core_v1 score=0.8383146162`、
    `avg_cost`、`start_frame`、`end_frame`。
  - 覆盖双模板 metadata normalizer 选择，避免 staged profile 与生产入口使用不同归一化版本。
  - 覆盖决策表对 FastDTW / cache 的方向判断。

### 验证方法

```powershell
.\.venv\Scripts\python.exe -m py_compile .\analysis\offline_matching_profile.py .\tests\test_s5_offline_profile.py
.\.venv\Scripts\python.exe -m pytest tests\test_s5_offline_profile.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_pose33_v3_golden.py tests\test_body_core_layout.py -q
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe -m analysis.offline_matching_profile --fixture-smoke --front-template templates\standard_front_full.npz --side-template templates\standard_side_full.npz --video "学员样本\1.mp4" --pose-variant full --limit-frames 90 --out outputs/offline_matching_profile_issue44
git diff --check
```

结果：专项测试 4 passed，`pose33_v3` golden + body_core 回归 37 passed，全量 `tests` 196 passed；
profile 命令写出 JSON/CSV，`git diff --check` 通过（仅 Windows 行尾提示）。

---

## 2026-06-02: 完成 #43 MediaPipe GPU delegate opt-in 可行性 spike

### 问题描述

Issue #43 要求验证当前 Windows + MediaPipe Tasks 环境是否能启用 GPU delegate，并比较
pose-only / pose+hands 的端到端表现。该阶段必须保持 MediaPipe 默认 CPU 路径不变，GPU delegate
只能显式 opt-in；若不可用，需要记录实际异常和 fallback 口径。

### 修改内容

- `core/vision_pipeline.py`：
  - `PipelineConfig` 新增 `delegate="cpu"` 字段，默认 CPU 保持旧 `BaseOptions(model_asset_path=...)`
    构造方式。
  - 新增 `_base_options()`，仅在显式 `delegate="gpu"` 时传入
    `BaseOptions.Delegate.GPU`，并对未知 delegate / 缺失 GPU API 给出明确异常。
  - `MediaPipePipeline` 新增 `close()`，便于 benchmark 多 case 释放 Pose / Hand landmarker。
- `analysis/bench_annotate_fps.py`：
  - 新增 `--include-mediapipe-gpu` 显式开关。
  - benchmark 默认 case 不变；仅 opt-in 时增加 `mediapipe_gpu_pose_only` 与
    `mediapipe_gpu_pose_hands`，并透传到 `PipelineConfig(delegate=...)`。
- `docs/mediapipe_gpu_delegate_report.md`：
  - 记录 MediaPipe API 探针、Pose / Hand GPU 初始化 smoke、短帧 CPU/GPU benchmark、fallback
    语义与 go/no-go 结论。
  - 本机 `mediapipe==0.10.31` 可初始化 GPU delegate，但 30 帧短测未证明 FPS 优于 CPU；
    因此保留 opt-in，不切默认。
- `tests/test_mediapipe_delegate_config.py` / `tests/test_s5_gpu_recheck.py`：
  - 覆盖 CPU 默认不显式传 delegate、GPU opt-in 才传 `Delegate.GPU`。
  - 覆盖 benchmark 默认不含 MediaPipe GPU case，显式开关才加入并透传。

### 验证方法

```powershell
.\.venv\Scripts\python.exe -m py_compile .\core\vision_pipeline.py .\analysis\bench_annotate_fps.py .\tests\test_mediapipe_delegate_config.py .\tests\test_s5_gpu_recheck.py
.\.venv\Scripts\python.exe -m pytest tests\test_mediapipe_delegate_config.py tests\test_s5_gpu_recheck.py -q
$sample = @'
{
  "schema_version": 1,
  "samples": [
    {
      "id": "std_front_short",
      "path": "标准样本/正面.mp4",
      "frames": 250
    }
  ]
}
'@
$tmp = Join-Path $env:TEMP "vision_issue43_sample.json"
Set-Content -Path $tmp -Value $sample -Encoding UTF8
.\.venv\Scripts\python.exe -m analysis.bench_annotate_fps --samples $tmp --asset-root E:\CodeProject\vision --device cpu --include-mediapipe-gpu --limit-frames 30 --warmup-frames 5 --out outputs/mediapipe_gpu_delegate_issue43_smoke
```

---

## 2026-06-01: 完成 #42 latest-frame 实时解耦 smoke

### 问题描述

Issue #42 要求在不替换默认实时循环、不改变 MediaPipe 默认路径语义的前提下，提供一个 opt-in
实时采集 / 推理 / 渲染解耦 smoke：采集侧只保留最新帧，推理消费最新帧，输出 p90 latency 与丢帧计数，
不能只报告 FPS。

### 修改内容

- `apps/main.py`：
  - 新增 `LatestFrameQueue` / `LatestFrameItem`，单槽保存最新帧，旧帧被覆盖时累计
    `dropped_frames`。
  - 新增 `RealtimeLatestFrameMetrics`，输出 `capture_fps`、`infer_fps`、`render_fps`、
    `latency_p90_ms`、`dropped_frames` 等 smoke 指标。
  - 新增 `run_realtime_latest_frame_smoke()`，使用独立 capture / inference 线程和最新帧队列，
    VIDEO mode 时间戳保持单调；仅通过 `--realtime-latest-frame` 显式进入。
  - CLI 新增 `--realtime-latest-frame` 与 `--limit-frames`；默认 `run()` 热循环不被替换。
- `tests/test_s5_realtime_latest_frame.py`：
  - 覆盖 latest-frame 队列丢弃旧帧语义、metrics schema、CLI opt-in、默认 CLI 仍走 `run()`、
    fake capture/pipeline smoke，以及源码级确认默认 `run()` / UI `_worker_loop` 未被 latest-frame
    实验路径替换。

### 验证方法

```powershell
.\.venv\Scripts\python.exe -m py_compile .\apps\main.py .\tests\test_s5_realtime_latest_frame.py
.\.venv\Scripts\python.exe -m pytest tests\test_s5_realtime_latest_frame.py -q
```

---

## 2026-06-01: 完成 #41 实时预览 Hands 开关

### 问题描述

Issue #41 要求在不引入 YOLO 后端选择、不改变 MediaPipe 默认行为的前提下，为 CLI / UI
实时预览增加显式 Hands 关闭开关，用于当前 MediaPipe 链路的 pose-only 提速 smoke。默认仍必须保持
Hands 开启，避免既有 V 手势识别与手部骨架显示体验突变。

### 修改内容

- `apps/main.py`：
  - 新增 `run(..., enable_hands=True)` 参数，默认保持 Hands 开启。
  - CLI 新增 `--no-hands`，显式关闭时将 `PipelineConfig(enable_hands=False)` 透传到单线程
    VIDEO 路径与离线多线程 IMAGE 路径。
- `apps/app_ui.py`：
  - 主 UI 选项区新增默认开启的“启用手部检测（V 手势 / 手部骨架）”复选框。
  - `UiState` 增加 `enable_hands` 字段，单线程实时路径与离线多线程路径均从 UI 状态透传到
    `PipelineConfig`。
  - 清理 `UiState` 中重复的 `pose_variant` 字段。
- `tests/test_s5_hands_toggle.py`：
  - 覆盖 CLI 默认 Hands 开启、`--no-hands` 显式关闭、离线多线程路径透传。
  - 覆盖 UI state 默认开启 / 显式关闭，以及 worker pipeline 使用 `state.enable_hands`。

### 验证方法

```powershell
.\.venv\Scripts\python.exe -m py_compile .\apps\main.py .\apps\app_ui.py .\tests\test_s5_hands_toggle.py
.\.venv\Scripts\python.exe -m pytest tests\test_s5_hands_toggle.py -q
```

---

## 2026-06-01: 完成 #40 TensorRT / ONNX engine benchmark spike

### 问题描述

Issue #40 要求验证 `models/yolo11n-pose.pt` 导出 TensorRT engine / ONNXRuntime 的可行性，
并形成是否另开 P2b engine adapter opt-in 的决策。该阶段必须保证 `.engine/.onnx` 产物不入库，
失败也要记录缺失依赖、安装命令与替代路径，同时不得将 engine/ONNX 结果接入对外评分或默认入口。

### 修改内容

- `analysis/bench_annotate_fps.py`：
  - `collect_env()` 增加 ONNX、ONNXRuntime、ONNXSlim、TensorRT 版本 / provider 探针。
  - 新增 `--yolo-delegate` 与模型后缀推断：`.pt=pytorch`、`.onnx=onnxruntime`、`.engine=tensorrt`。
  - 非 PyTorch delegate 只保留 MediaPipe CPU baseline 与 exported model CUDA case，避免 ONNX/TensorRT
    spike 误跑 PyTorch-only CPU baseline 与 FP16 640/512 case。
- `.gitignore`：新增 `models/*.engine`，与既有 `models/*.onnx` 一起防止导出产物入库。
- `tests/test_s5_gpu_recheck.py`：补充 exported model delegate 推断与非 PyTorch delegate case
  矩阵测试。
- 新增 `docs/yolo_engine_benchmark_report.md`：
  - 记录 TensorRT 导出命令、失败原因 `ModuleNotFoundError("No module named 'tensorrt'")`。
  - 记录已尝试 `tensorrt-cu12 --extra-index-url https://pypi.nvidia.com`，但 2.2GB wheel 经本地代理
    长时间未完成，故本轮不产出 `.engine`。
  - 记录 ONNXRuntime CUDA 6 样本 smoke：body-only raw infer FPS 均值 63.075，body+hands raw infer
    FPS 均值 68.336，所有行 `status=ok`，但仍仅作为 smoke，不建议立即创建 P2b production adapter。

### 验证方法

```powershell
.\.venv\Scripts\python.exe -m py_compile .\analysis\bench_annotate_fps.py .\tests\test_s5_gpu_recheck.py
.\.venv\Scripts\python.exe -m pytest tests\test_s5_gpu_recheck.py -q
$env:HTTP_PROXY  = "http://127.0.0.1:7890"
$env:HTTPS_PROXY = "http://127.0.0.1:7890"
.\.venv\Scripts\python.exe -c "from ultralytics import YOLO; m=YOLO('models/yolo11n-pose.pt'); m.export(format='engine', half=True, imgsz=640, device=0, workspace=2, verbose=False)"
.\.venv\Scripts\python.exe -m analysis.bench_annotate_fps --samples docs\yolo_eval_samples.json --asset-root E:\CodeProject\vision --models-dir E:\CodeProject\vision\models --yolo-model E:\CodeProject\vision\models\yolo11n-pose.onnx --device cuda --yolo-delegate onnxruntime --limit-frames 1 --warmup-frames 1 --out outputs\engine_recheck_issue40_onnx_smoke
git status --short --ignored models outputs
```

---

## 2026-06-01: 推进 #39 YOLO FP16 / imgsz / warmup opt-in

### 问题描述

Issue #39 要求在 #38 benchmark 口径修正后，继续验证 YOLO PyTorch FP16、不同 `imgsz`
与 adapter 内部 warmup 的真实性能上限，同时保持默认 FP32 / 640 / 无 warmup 行为不变，
并确保优化参数不仅作用于 benchmark，也能透传到 `extract_yolo_landmark_series`。

### 修改内容

- `core/yolo_adapter.py`：
  - `YoloPoseAdapter` 增加 `half=False`、`warmup=False`、`warmup_shape=None` 显式 opt-in
    参数；默认构造仍不加载 ultralytics、不推理。
  - `_predict()` 向 ultralytics `model.predict()` 透传 `half=self.half`；CPU / MPS 请求
    half 时自动降级为 `False`，CUDA / 数字设备才启用 FP16。
  - adapter warmup 只在显式 `warmup=True` 且首次真实推理前执行一次，随后复用现有
    `yolo_result_to_arrays` / `map_coco17_person` / 多人闸门链路。
  - `extract_yolo_landmark_series` 透传 `imgsz`、`device`、`half`、`warmup`、
    `warmup_shape`，并在 meta 中记录实验参数。
- `analysis/bench_annotate_fps.py`：
  - `BenchCase` 增加 `imgsz`、`half`、`adapter_warmup` 字段。
  - `--device cuda` 时保留 #38 FP32 baseline，并新增 FP16 640 / FP16 512 的 body-only
    与 body+hands case。
  - CSV/JSON 输出新增 `imgsz`、`half`、`adapter_warmup`、`warmup_shape`、`max_persons`、
    `multi_person_frames`、`review_required`、`gate_status`，同时观察性能与多人质量守卫。
- `tests/test_yolo_backend_contract.py`：补充 half 参数透传、CPU fallback、warmup 只执行一次、
  序列提取参数透传与 meta 字段测试。
- `tests/test_s5_gpu_recheck.py`：补充 benchmark FP16/imgsz case、CSV schema 与质量守卫字段测试。
- `docs/yolo_gpu_recheck_report.md`：补充 #39 PyTorch FP16 / imgsz / adapter warmup 实验口径说明。

### 验证方法

```powershell
.\.venv\Scripts\python.exe -m py_compile .\core\yolo_adapter.py .\analysis\bench_annotate_fps.py .\tests\test_yolo_backend_contract.py .\tests\test_s5_gpu_recheck.py
.\.venv\Scripts\python.exe -m pytest tests\test_yolo_backend_contract.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_s5_gpu_recheck.py -q
```

---

## 2026-06-01: 完成 #38 benchmark warmup 与稳定态延迟口径

### 问题描述

Issue #38 要求修正 #23 GPU 复测 benchmark 的测量口径：原脚本没有 warmup、缺少
per-frame latency 分布，并且 `--device cuda` 时一旦 CUDA 不可用会跳过整个矩阵，导致
MediaPipe CPU / YOLO CPU 基线无法在同一份输出中保留。旧口径容易把 CUDA/model 首帧
初始化成本当成代表性 FPS，影响后续 P1/P2a 二次决策。

### 修改内容

- `analysis/bench_annotate_fps.py`：
  - 新增 `--warmup-frames`（默认 10）与 `FrameLoopStats`，正式 FPS 和 p50/p90/p99
    只统计 timed frames。
  - 输出新增 `delegate`、`warmup_frames`、`timed_frames`、`cold_first_infer_sec`、
    `cold_first_annotate_sec`、`timed_latency_ms_p50/p90/p99`、
    `yolo_raw_infer_latency_ms_p50/p90/p99`，保留旧字段。
  - `--device cuda` 时固定输出 MediaPipe CPU、YOLO CPU、YOLO CUDA 矩阵；CUDA 不可用时
    只跳过需要 CUDA 的 YOLO case，不再跳过整轮 benchmark。
  - YOLO warmup 复用同一个 `YoloPoseAdapter` 做原始推理，然后重置指标与 tracker，
    避免 CUDA/model cold-start 污染正式计时；MediaPipe warmup 使用独立 VIDEO runner，
    避免正式段 timestamp 从 0 开始时发生倒退。
- `tests/test_s5_gpu_recheck.py`：补充 CSV schema、设备矩阵与 warmup/timed 指标口径测试。
- `docs/yolo_gpu_recheck_report.md`：补充 Issue #38 benchmark 口径修正说明，保留 #23
  CUDA 修正版历史 no-go 结果。

### 验证方法

```powershell
.\.venv\Scripts\python.exe -m py_compile .\analysis\bench_annotate_fps.py .\tests\test_s5_gpu_recheck.py
.\.venv\Scripts\python.exe -m pytest tests\test_s5_gpu_recheck.py -q
.\.venv\Scripts\python.exe -m analysis.bench_annotate_fps --samples docs\yolo_eval_samples.json --asset-root E:\CodeProject\vision --models-dir E:\CodeProject\vision\models --yolo-model E:\CodeProject\vision\models\yolo11n-pose.pt --device cuda --limit-frames 1 --warmup-frames 1 --out outputs/gpu_recheck_issue38_smoke
```

---

## 2026-06-01: YOLO 性能优化路线图文档准备

### 问题描述

`docs/yolo_perf_optimization_plan.md` 已指出 #23 GPU 复测 no-go 可能受到 warmup、逐帧
`model.predict()`、FP32、串行渲染等因素影响，但原文还停留在分析方案层，缺少可直接推送到
GitHub 的细分 issue、路线图 issue 草案、方案择优规则与代码链路复核证据。

### 修改内容

- 细读并复核 `docs/yolo_perf_optimization_plan.md`、`core/yolo_adapter.py`、
  `analysis/bench_annotate_fps.py`、`core/vision_pipeline.py`、`apps/main.py`、
  `apps/app_ui.py`、`core/body_core_compare.py` 等关键链路。
- `docs/yolo_perf_optimization_plan.md`：新增代码链路复核、性能瓶颈排序、候选方案对比、
  择优规则、P0–P5 细分 issue 草案与新路线图 issue 草案。
- 新增 `docs/specs/yolo_perf_optimization_design.md`：按 Design-First 方式记录设计目标、
  不变量、方案分解、验收要求和任务清单。
- 已启动独立子 agent 进行视觉链路与算法现状只读分析；后续还会启动独立文档审查子 agent，
  按审查意见继续迭代文档。
- 子 agent 文档审查指出 P0 同设备口径、warmup 帧语义、P1 快路径契约复用、P2 spike/adapter
  粒度、P3 默认不改、P4 GPU delegate API 探测、P5 只 profile 不改分数等边界需要补强。
- 已按审查意见补强文档：P0 增加 MP CPU / YOLO CPU / YOLO CUDA 设备矩阵与 warmup rewind
  语义；P1 明确新快路径必须复用既有解析 / 映射 / 多人闸门；P2 拆为 P2a export benchmark
  spike 与条件 P2b adapter；路线图拆成 YOLO 二次决策和现有实时体验优化两条泳道。

### 验证方法

```powershell
Get-Content -Raw docs\yolo_perf_optimization_plan.md
Get-Content -Raw docs\specs\yolo_perf_optimization_design.md
git diff --check
```

---

## 2026-06-01: 修复 YOLO GPU 复测环境误判并重跑 #23

### 问题描述

本机有 NVIDIA GeForce RTX 4060 Laptop GPU，但此前 `.venv` 中安装的是 CPU 版 torch，
导致 `torch.cuda.is_available()=False`，#23 GPU 复测按 0/6 有效 GPU 行判定 no-go，
并连锁影响 #25 CLI 实时入口、#26 UI 后端选择、#27 Hybrid 与 #28 默认切换决策。该 no-go
依据属于环境前提错误，不能作为最终 S5/S6 结论。

### 修改内容

- 将 `.venv` 中 torch / torchvision 修正为 CUDA 版：`torch=2.11.0+cu128`、
  `torchvision=0.26.0+cu128`，确认 `torch.cuda.is_available()=True` 且设备为 RTX 4060。
- 重新运行 `analysis.bench_annotate_fps`，6/6 S0 样本均产生有效 GPU benchmark 行。
- `docs/yolo_gpu_recheck_report.md`：重写为 CUDA 修正版报告，撤销“CPU torch / 0 行 GPU 数据”
  作为最终依据；记录真实 GPU 复测后仍 no-go：Hands 关 FPS 比仅 1/6 达到 1.30，Hands 开
  0/6 达到 1.20，YOLO raw FPS 0/6 达到 62.85，body_core 抖动 3/6 超阈值。
- `docs/yolo_gpu_readiness_review.md`：从核查 / 待修复文档更新为修复结果复盘。
- `docs/yolo_default_switch_decision.md`、`docs/yolo_migration_plan*.md`、
  `docs/yolo_migration_issues.md`：同步 #23 新依据，保持 #25/#26/#28 当前不切默认 / 不实现，
  但不再引用 CPU torch 无效环境作为最终结论。
- 同步 GitHub Issue #23/#25/#26/#27/#28 正文：公开追踪口径改为“CUDA 已修复 + 真实 GPU 数据
  no-go”，并明确 #25/#26/#27 继续关闭不是因为 RTX 4060 不可用。
- PR #36 子 agent 审查结论：未发现 P0/P1/P2 阻塞问题；按非阻塞建议补强 PR body 的 issue
  关联说明，明确本 PR 是修正已关闭 issue 的公开口径，不重新打开实现范围。
- PR #36 已合并到 `main`（merge commit `b4c3631`），远端分支与本地修复分支已清理；本地
  `main` 已快进到 `origin/main`。
- `requirements-spike.txt`：显式加入 PyTorch `cu128` wheel 索引与版本，避免后续裸装 PyPI torch
  又得到 CPU wheel。
- 更新 S5/S6/tracking 回归测试，锁住“CUDA 已修复 + 真实 GPU 数据 no-go”的口径。

### 验证方法

```powershell
E:\CodeProject\vision\.venv\Scripts\python.exe -c "import torch, torchvision; print(torch.__version__, torchvision.__version__, torch.cuda.is_available(), torch.version.cuda, torch.cuda.get_device_name(0))"
E:\CodeProject\vision\.venv\Scripts\python.exe -m analysis.bench_annotate_fps --samples docs/yolo_eval_samples.json --asset-root E:\CodeProject\vision --models-dir E:\CodeProject\vision\models --yolo-model E:\CodeProject\vision\models\yolo11n-pose.pt --device cuda --out outputs/gpu_recheck
E:\CodeProject\vision\.venv\Scripts\python.exe -m pytest tests\test_s5_gpu_recheck.py tests\test_s5_cli_no_go.py tests\test_s5_ui_no_go.py tests\test_s5_hybrid_decision.py tests\test_s6_default_switch_decision.py tests\test_tracking_issue_sync.py -q
E:\CodeProject\vision\.venv\Scripts\python.exe -m pytest tests\test_yolo_landmark_mapping.py tests\test_yolo_backend_contract.py tests\test_body_core_layout.py tests\test_batch_backend_args.py -q
E:\CodeProject\vision\.venv\Scripts\python.exe -m pytest tests\test_pose33_v3_golden.py -q
E:\CodeProject\vision\.venv\Scripts\python.exe -m pytest tests -q
E:\CodeProject\vision\.venv\Scripts\python.exe -m py_compile analysis\bench_annotate_fps.py tests\test_s5_gpu_recheck.py tests\test_s5_cli_no_go.py tests\test_s5_ui_no_go.py tests\test_s5_hybrid_decision.py tests\test_s6_default_switch_decision.py tests\test_tracking_issue_sync.py
git diff --check
```

---

## 2026-05-31: YOLO 迁移总追踪收尾（Issue #12）

### 问题描述

Issue #12 是 YOLO 迁移总追踪 / 作战地图。当前 #1–#11、#23–#28 已全部完成并关闭，但
`docs/yolo_migration_issues.md` 仍停留在 M4 “S5/S6 待 S3 结论后开票 / 暂不拆细 Issue”的旧状态，
与仓库真实 issue 状态不一致。

### 修改内容

- `docs/yolo_migration_issues.md`：将仓库追踪索引更新为 #1–#11、#23–#28 均已关闭，M4
  包含 #23 #24 #25 #26 #27 #28，并写明 S5 / S6 各决策结果。
- 新增 `tests/test_tracking_issue_sync.py`：锁住总追踪文档必须列出 M4 最终 issue 与决策，
  并禁止旧的“待开票 / 暂不拆细 / 按需开 Issue”表述回流。
- PR #35 审查补强：同步 GitHub Issue #12 正文，将旧 M4 待拆票清单改为最终关闭清单，
  并写明 S5 / S6 最终结论与关闭依据。

### 验证方法

```powershell
E:\CodeProject\vision\.venv\Scripts\python.exe -m pytest tests\test_tracking_issue_sync.py tests\test_s6_default_switch_decision.py -q
E:\CodeProject\vision\.venv\Scripts\python.exe -m pytest tests -q
E:\CodeProject\vision\.venv\Scripts\python.exe -m py_compile tests\test_tracking_issue_sync.py
gh issue view 12 --repo YGuo-2/vision --json state,body
git diff --check
```

---

## 2026-05-31: YOLO 迁移 S6 — 默认切换决策（Issue #28）

### 问题描述

Issue #28 是纯决策阶段，需要基于 #1 许可、#10 标定、#23 GPU 复测、#24 batch、#25 CLI、
#26 UI、#27 Hybrid 的结果，分别决定实时预览、模板匹配、规则 / 技术评估三条链路是否默认使用
YOLO。当前 #23/#25/#26/#27 均走 no-go / 不实现分支，#10 也仅授权预览，不能把 YOLO 切成默认。

### 修改内容

- 新增 `docs/yolo_default_switch_decision.md`：汇总 #1/#10/#23/#24/#25/#26/#27 输入，明确
  S6 结论为“全部不切默认，仅保留离线 / 实验入口”。
- `docs/yolo_migration_plan_optimized.md`：将 S6 小节从“可能结论”更新为 Issue #28 当前决策，
  并列出未来重新评估默认切换的前置条件。
- `docs/yolo_gpu_recheck_report.md`：同步 #28 已执行，指向 S6 决策文档。
- 新增 `tests/test_s6_default_switch_decision.py`：锁住三条链路默认继续 MediaPipe、Hybrid 不实现、
  离线实验入口 `score_authorized=False`、未来重开需许可 / GPU / 标定 / 回滚 / 来源可见性条件。

### 验证方法

```powershell
E:\CodeProject\vision\.venv\Scripts\python.exe -m pytest tests\test_s6_default_switch_decision.py tests\test_s5_gpu_recheck.py -q
E:\CodeProject\vision\.venv\Scripts\python.exe -m pytest tests -q
E:\CodeProject\vision\.venv\Scripts\python.exe -m py_compile tests\test_s6_default_switch_decision.py
git diff --check
```

---

## 2026-05-31: YOLO 迁移 S5c — UI 后端选择入口关闭决议（Issue #26）

### 问题描述

Issue #26 仅在 #25 落地后启动，目标是在 `apps/app_ui.py` 增加 YOLO 后端选择和规则完整度提示。
当前 #23 GPU 复测已判定 no-go，#25 也已关闭 / 不实现 `apps/main.py --backend yolo` 实时预览入口；
因此 UI 没有可用的实时 YOLO 后端可选择，不能预先暴露 YOLO-only 入口、完整度提示或未标定评分展示。

### 修改内容

- `docs/yolo_gpu_recheck_report.md`：新增 “UI 后端选择决议（Issue #26）” 小节，明确
  `apps/app_ui.py` 当前不实现 YOLO 后端选择控件 / 规则完整度提示，并逐条引用 #23 / #25 的
  no-go 事实。
- `docs/yolo_migration_plan.md` 与 `docs/yolo_migration_plan_optimized.md`：同步 #26 决议，
  移除会误导后续实现 UI YOLO 后端选择的旧计划承诺；保留既有 MediaPipe UI。
- 新增 `tests/test_s5_ui_no_go.py`：锁住 #26 报告必须包含 no-go 数字和边界，两个计划文档
  必须同步 Issue #26 / GPU 复测报告，且 `apps/app_ui.py` 不出现 YOLO 后端选择、`body_core_v1`
  布局选择、未标定评分或 YOLO runtime import。

### 验证方法

```powershell
E:\CodeProject\vision\.venv\Scripts\python.exe -m pytest tests\test_s5_ui_no_go.py tests\test_s5_cli_no_go.py tests\test_s5_gpu_recheck.py -q
E:\CodeProject\vision\.venv\Scripts\python.exe -m pytest tests\test_pose33_v3_golden.py -q
E:\CodeProject\vision\.venv\Scripts\python.exe -m py_compile apps\app_ui.py tests\test_s5_ui_no_go.py
git diff --check
```

---

## 2026-05-31: PR #33 审查补强 — 最小完成定义同步 #26 no-go

### 问题描述

子 agent 审查 PR #33 时指出：`docs/yolo_migration_plan.md` 末尾“最小完成定义”仍写着
“CLI、UI、batch 都能选择后端并记录结果来源”。虽然前文已明确 Issue #26 no-go、不实现 UI
YOLO 后端选择，但该完成定义可能误导后续 agent 把 UI 后端选择当成当前迁移完成硬条件。

### 修改内容

- `docs/yolo_migration_plan.md`：将最小完成定义改为“已授权入口能记录结果来源；CLI / UI
  后端选择按 #25 / #26 / #28 决策，no-go 分支不作为完成硬条件”。
- `tests/test_s5_ui_no_go.py`：将旧完成定义语句加入禁止回流断言。

### 验证方法

```powershell
E:\CodeProject\vision\.venv\Scripts\python.exe -m pytest tests\test_s5_ui_no_go.py -q
E:\CodeProject\vision\.venv\Scripts\python.exe -m pytest tests -q
E:\CodeProject\vision\.venv\Scripts\python.exe -m py_compile apps\app_ui.py tests\test_s5_ui_no_go.py
git diff --check
```

---

## 2026-05-31: YOLO 迁移 S5b — CLI 实时预览入口关闭决议（Issue #25）

### 问题描述

Issue #25 仅在 #23 GPU 复测 = go 时启动，目标是给 `apps/main.py` 增加 YOLO 实时预览
`--backend` / `--feature-layout` 入口。当前 #23 已按预注册阈值判定 no-go：
`.venv` 内 `torch.cuda.is_available()=False`、device_count=0、6 段样本有效 GPU benchmark
覆盖 0/6，Hands 开 / 关两档端到端 FPS 比均无有效 GPU 行。因此本期不能把 YOLO 实时入口接入
用户可见 CLI 主链路。

### 修改内容

- `docs/yolo_gpu_recheck_report.md`：新增 “CLI 实时预览决议（Issue #25）” 小节，明确
  `apps/main.py --backend yolo` / `--feature-layout body_core_v1` 当前关闭不实现，并逐条引用
  #23 的 no-go 数字。
- `docs/yolo_migration_plan.md` 与 `docs/yolo_migration_plan_optimized.md`：同步 #25 决议，
  移除会误导后续实现 CLI YOLO 实时入口的旧计划承诺；保留既有 MediaPipe CLI 默认路径。
- 新增 `tests/test_s5_cli_no_go.py`：锁住 #25 报告必须包含 no-go 数字和边界，两个计划文档
  必须同步 Issue #25 / GPU 复测报告，且 `apps/main.py` 不出现 `--backend` /
  `--feature-layout` / YOLO realtime runtime。

### 验证方法

```powershell
E:\CodeProject\vision\.venv\Scripts\python.exe -m pytest tests\test_s5_cli_no_go.py tests\test_s5_gpu_recheck.py -q
E:\CodeProject\vision\.venv\Scripts\python.exe -m pytest tests\test_pose33_v3_golden.py -q
E:\CodeProject\vision\.venv\Scripts\python.exe -m py_compile apps\main.py tests\test_s5_cli_no_go.py
git diff --check
```

---

## 2026-05-31: PR #32 审查补强 — 顶层影响面表同步 #25 no-go

### 问题描述

子 agent 审查 PR #32 时指出：`docs/yolo_migration_plan.md` 顶部“当前代码影响面”表仍把
`apps/main.py` / `apps/app_ui.py` 概括为“增加 backend/layout/rules 完整度配置和提示”。虽然后文
已经写明 Issue #25 no-go、不实现 `apps/main.py --backend yolo`，但顶部摘要位置显眼，后续只扫表格
时仍可能误导。

### 修改内容

- `docs/yolo_migration_plan.md`：将顶部影响面表同步为 `apps/main.py` 按 Issue #25 no-go
  当前保持 MediaPipe CLI，UI / 后续入口另按 #26 / #28 决策。
- `tests/test_s5_cli_no_go.py`：将该旧表格行加入禁止回流断言，防止摘要层再次承诺 CLI YOLO
  实时入口。

### 验证方法

```powershell
E:\CodeProject\vision\.venv\Scripts\python.exe -m pytest tests\test_s5_cli_no_go.py -q
E:\CodeProject\vision\.venv\Scripts\python.exe -m pytest tests -q
E:\CodeProject\vision\.venv\Scripts\python.exe -m py_compile apps\main.py tests\test_s5_cli_no_go.py
git diff --check
```

---

## 2026-05-31: YOLO 迁移 S5d — Hybrid 默认不实现决议（Issue #27）

### 问题描述

Issue #27 需要基于 #23 GPU 复测和 S0/S3 结论，决定是否实现离线 Hybrid
`yolo_body_mp_pose_supplement`。Hybrid 的本质是 YOLO body 后再跑 MediaPipe Pose 补脚 / 补脸；
如果没有数字证明其性能代价可接受，就会抵消 YOLO 的主要收益，还可能引入半成品路径。

### 修改内容

- `docs/yolo_gpu_recheck_report.md`：新增 “Hybrid 决议（Issue #27）” 小节，引用
  `torch.cuda.is_available()=False`、GPU 有效复测覆盖 0/6、S0 CPU speedup=0.41、COCO17 缺脚跟脚尖
  等数字 / 事实，明确结论为不实现 `yolo_body_mp_pose_supplement`。
- 明确未来重新评估 Hybrid 的触发条件：CUDA 有效复测、Hybrid 专用 benchmark、补点指标恢复证据，
  且仍只能作为离线显式模式，不能进入默认 / 实时路径。
- 新增 `tests/test_s5_hybrid_decision.py`：锁住 #27 报告必须含数字依据、默认不实现结论，并确认
  `apps/`、`batch/`、`core/`、`analysis/` 中不存在半成品 Hybrid runtime 代码路径。

### 验证方法

```powershell
E:\CodeProject\vision\.venv\Scripts\python.exe -m pytest tests\test_s5_hybrid_decision.py -q
E:\CodeProject\vision\.venv\Scripts\python.exe -m pytest tests\test_pose33_v3_golden.py -q
E:\CodeProject\vision\.venv\Scripts\python.exe -m py_compile tests\test_s5_hybrid_decision.py
git diff --check
```

---

## 2026-05-31: PR #31 审查补强 — Hybrid 决议同步迁移计划文档

### 问题描述

子 agent 审查 PR #31 时指出：虽然 GPU 复测报告已明确 Issue #27 当前不实现
`yolo_body_mp_pose_supplement`，但 `docs/yolo_migration_plan.md` 与
`docs/yolo_migration_plan_optimized.md` 仍保留“后置实现 Hybrid / 离线显式 Hybrid”的旧计划表述，
可能误导后续 agent 或开发者继续实现已被 supersede 的路径。

### 修改内容

- `docs/yolo_migration_plan.md`：将 Hybrid 命名、P4、P6 中的旧实现表述同步为 Issue #27
  决议：当前不实现，不保留半成品 runtime；未来必须另开实现子任务并满足 CUDA 有效复测、
  Hybrid 专用 benchmark、补点指标恢复证据等触发条件。
- `docs/yolo_migration_plan_optimized.md`：将 S5 与“审批后删减 / 后置项”表格同步为
  Issue #27 supersede 结论，避免继续描述为“后置到 S5 且离线显式开启”。
- `tests/test_s5_hybrid_decision.py`：新增计划文档一致性回归，锁住两个计划文档必须引用
  Issue #27 / GPU 复测报告、写明当前不实现和未来另开实现子任务，并禁止旧 Hybrid 实现承诺回流。

### 验证方法

```powershell
E:\CodeProject\vision\.venv\Scripts\python.exe -m pytest tests\test_s5_hybrid_decision.py -q
E:\CodeProject\vision\.venv\Scripts\python.exe -m pytest tests -q
E:\CodeProject\vision\.venv\Scripts\python.exe -m py_compile tests\test_s5_hybrid_decision.py
git diff --check
```

---

## 2026-05-31: PR #30 审查补强 — batch_export_skeleton 已存在输出 meta 透传

### 问题描述

子 agent 审查 PR #30 时指出：`batch_export_skeleton.py` 在 `--backend yolo --feature-layout body_core_v1`
且目标 `.npz` 已存在时会走 skip 分支，该分支只写短 manifest 行，没有补齐 Issue #24 要求的
backend/layout/calibration/review meta；若同批次同时存在 skipped 行与新处理行，还可能因 CSV
header 取第一行字段导致后续行多字段写入失败。

### 修改内容

- `batch/batch_export_skeleton.py`：新增统一 `_manifest_row()` 与 union fieldnames 写 CSV；skip
  已存在 body_core npz 时读取现有 `.npz` meta 并透传 `backend` / `model_name` /
  `feature_layout` / `confidence_kind` / `validity_policy` / `valid_conf_thr` /
  `calibration_status` / `score_authorized` / `review_required`。
- `tests/test_batch_backend_args.py`：新增 skipped + processed 混合场景测试，确认 manifest
  两类行都含 #24 meta 字段且不会因字段不一致报错。

### 验证方法

```powershell
E:\CodeProject\vision\.venv\Scripts\python.exe -m pytest tests\test_batch_backend_args.py -q
E:\CodeProject\vision\.venv\Scripts\python.exe -m pytest tests -q
E:\CodeProject\vision\.venv\Scripts\python.exe -m py_compile batch\backend_options.py batch\batch_dual_compare.py batch\batch_export_skeleton.py batch\batch_tech_eval.py
git diff --check
```

---

## 2026-05-31: YOLO 迁移 S5a — batch backend/layout 参数与 metadata 透传（Issue #24）

### 问题描述

S5a 需要让三个 batch 入口显式支持 `--backend` / `--feature-layout`，使 YOLO
`body_core_v1` 能用于离线调试 / 标定对照，同时严格保持默认 MediaPipe `pose33_v3`
旧行为不变。YOLO body_core 分数未授权对外评分，输出必须带 `calibration_status=unvalidated`
与 `score_authorized=False`，多人视频必须标「需人工复核 / 拒绝」，不能混入正常评分列。

### 修改内容

- 新增 `batch/backend_options.py`：统一 backend/layout 参数、非法组合校验（YOLO 只允许
  `body_core_v1`）、Issue #24 要求的 meta 字段与 CSV 透传字段。
- `batch/batch_dual_compare.py`：默认 `mediapipe + pose33_v3` 路径保持旧逻辑；显式
  `body_core_v1` 时走 `core.body_core_compare` 闭环，输出 `front_debug_score` /
  `side_debug_score` 与 meta，不写 `front_score` / `combined_percent` 等对外评分列；多人结果标
  `review_status=需人工复核`。
- `batch/batch_export_skeleton.py`：默认导出 Pose33 `.npz` 与骨架视频逻辑不变；显式
  `body_core_v1` 时导出 `features[T,12,2]` 与 backend/layout/calibration/review meta，并在
  manifest 透传。
- `batch/batch_tech_eval.py`：默认 MediaPipe full tech_eval 不变；显式 `body_core_v1` 时不做对外
  技术评分，结构化写出 `无法判定` / `unvalidated_backend` / `score_authorized=False`，YOLO 多人标
  需人工复核。
- 新增 `tests/test_batch_backend_args.py`：覆盖默认参数、非法 YOLO+pose33、YOLO meta、调试分数
  与对外评分列分离、多人复核、NPZ/CSV/JSONL meta 透传。

### 验证方法

```powershell
E:\CodeProject\vision\.venv\Scripts\python.exe -m pytest tests\test_batch_backend_args.py -q
E:\CodeProject\vision\.venv\Scripts\python.exe -m pytest tests\test_pose33_v3_golden.py tests\test_body_core_layout.py tests\test_yolo_backend_contract.py -q
E:\CodeProject\vision\.venv\Scripts\python.exe -m py_compile batch\backend_options.py batch\batch_dual_compare.py batch\batch_export_skeleton.py batch\batch_tech_eval.py
git diff --check
```

---

## 2026-05-31: PR #29 审查补强 — S5 GPU 复测 harness 指标字段

### 问题描述

子 agent 审查 PR #29 时指出：当前 CUDA 不可用时报告可以产出 no-go 证据，但若后续换成
CUDA-enabled torch 复跑，`analysis/bench_annotate_fps.py` 的 CUDA 可用分支只写
`annotate_fps`，尚不能产出 #23 预注册表要求对照的 YOLO 裸推理 FPS、漏检 / 缺失帧率与
body_core 抖动指标。

### 修改内容

- `analysis/bench_annotate_fps.py`：YOLO 预览分支在每帧 `infer_frame()` 周围单独计时，输出
  `yolo_raw_infer_fps` / `yolo_raw_infer_sec`；统计 `yolo_miss_rate`、
  `yolo_body_core_full_valid_rate`、`yolo_body_core_missing_rate`；基于连续 full-valid
  body_core 帧计算 `yolo_body_core_jitter_median`。
- `docs/yolo_gpu_recheck_report.md`：补充说明 CUDA 可用时 harness 会写出上述字段，用于对照裸推理
  FPS、失败 / 漏检帧率与抖动阈值。
- `tests/test_s5_gpu_recheck.py`：新增 body_core 抖动 helper 与 CSV schema 回归，锁住 #23
  预注册指标字段不会被后续删掉。

### 验证方法

```powershell
E:\CodeProject\vision\.venv\Scripts\python.exe -m pytest tests\test_s5_gpu_recheck.py tests\test_yolo_backend_contract.py -q
E:\CodeProject\vision\.venv\Scripts\python.exe -m pytest tests -q
E:\CodeProject\vision\.venv\Scripts\python.exe -m py_compile analysis\bench_annotate_fps.py
git diff --check
```

---

## 2026-05-31: YOLO 迁移 S5 — GPU 复测决策门（Issue #23）

### 问题描述

S0 的 CPU spike 显示本机 CPU 上 YOLO 不提速（YOLO/MediaPipe 纯推理 FPS 比 0.41），而 S5
是否扩实时入口 / UI / 默认切换必须改看 GPU 上 `annotate()` 端到端链路。此前仓库没有独立
benchmark harness 能按 Hands 开 / 关两档复测 `apps/main.py` 同等预览链路，也没有 #23 的
GPU 复测决策报告。

### 修改内容

- 新增 `analysis/bench_annotate_fps.py`：独立 S5 benchmark harness，只读调用既有
  `MediaPipePipeline.annotate()` 与 `YoloPoseAdapter.infer_frame()`，支持 Hands 开 / 关两档、
  `--asset-root` 引用本地 gitignored 样本、`--device cuda`、环境探针与 JSON/CSV 输出；不接主链路。
- 新增 `docs/yolo_gpu_recheck_report.md`：固定本机环境、预注册 GPU runtime / 6 样本覆盖 /
  Hands 开关 FPS 比 / 漏检 / 抖动阈值，并按实测 `torch=2.12.0+cpu`、
  `torch.cuda.is_available()=False`、有效 GPU benchmark rows=0 判定 **no-go**。
- 分流结论：#25 / #26 在当前环境关闭不实现；#24 可独立推进；#27 默认不实现；#28 仍需执行但
  no-go 分支下简化为“全部不切默认，仅保留离线 / 实验入口”。

### 验证方法

```powershell
E:\CodeProject\vision\.venv\Scripts\python.exe -m analysis.bench_annotate_fps --samples docs/yolo_eval_samples.json --asset-root E:\CodeProject\vision --models-dir E:\CodeProject\vision\models --yolo-model E:\CodeProject\vision\models\yolo11n-pose.pt --device cuda --out outputs/gpu_recheck  # 写出 status=skipped / skip_reason=torch_cuda_unavailable
E:\CodeProject\vision\.venv\Scripts\python.exe -m py_compile analysis\bench_annotate_fps.py
E:\CodeProject\vision\.venv\Scripts\python.exe -m pytest tests\test_pose33_v3_golden.py -q
```

---

## 2026-05-31: PR #22 审查补强 — S4 结构化状态

### 问题描述

审查 PR #22 时发现两处结构化契约细节需要补强：`core/pose_features.py` 的 COCO17
能力分组把 `left_eye/right_eye` 也当成结构性缺失，和 `core/yolo_adapter.py` 已有映射契约
不一致；`batch/batch_tech_eval.py` 的 CSV 只给部分技术指标写出“缺失关键点”列，重心侧面/
正面/CoM 分项缺少对应列。

### 修改内容

- `core/pose_features.py`：将眼部能力拆成 `eyes`（2/5，COCO17 有近似映射）与
  `eye_details`（1/3/4/6，COCO17 结构性缺失），`COCO17_SUPPORTED_CAPABILITIES`
  纳入 `eyes`，避免未来能力判定误报。
- `batch/batch_tech_eval.py`：CSV 补齐 `重心_侧面缺失关键点`、`重心_正面缺失关键点`、
  `重心_CoM缺失关键点`，使报告列与每个重心分项的结构化契约一致。
- `tests/test_rule_availability.py`：新增 COCO17 眼部能力映射回归，锁住左右眼中心可用、
  眼细分缺失的契约。

### 验证方法

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_rule_availability.py tests\test_tech_eval_contract.py -q  # 17 passed
.\.venv\Scripts\python.exe -m pytest tests\test_pose33_v3_golden.py tests\test_valid_mask_migration.py tests\test_yolo_landmark_mapping.py -q  # 42 passed
.\.venv\Scripts\python.exe -m pytest tests -q  # 136 passed
.\.venv\Scripts\python.exe -m py_compile core\pose_features.py core\rule_scoring.py analysis\tech_eval.py batch\batch_tech_eval.py batch\batch_dual_compare.py  # exit 0
```

---

## 2026-05-31: YOLO 迁移 S4 — 规则与技术评估分级（结构化状态，Issue #11）

### 问题描述

评估链路要能诚实输出「能评估什么、不能评估什么」。此前 `core/rule_scoring.py` 的
`RuleViolation` 三态（已评估 / 合格 / 未评估）只靠中文 `detail` 字符串拼
（`（合格）` / `（有效帧不足，未评估）`），下游无法用稳定字段判断；`analysis/tech_eval.py`
各指标也没有声明「依赖哪些关键点、运行时缺了哪些点、来自哪个后端」。本期按 #11 任务规范
**补结构化字段，不推倒重来**。

**范围分流（按 #10 结论，硬约束）**：Issue #10 标定结论为「**仅用于预览**」
（`docs/yolo_body_core_calibration.md` 第八节：跨视频 J1 corr=0.280、J4 一致率=0.50 未达标）。
据 #11 前置条件，本期**只做 MediaPipe 侧结构化状态改造**，**不启用 YOLO partial tech_eval
指标**。MediaPipe 默认 `pose33_v3` 路径与 golden 不得漂移。

### 修改内容

- **`core/pose_features.py` 新增集中式关键点命名 + 能力分组（Issue #11）**：
  - `BLAZE33_LANDMARK_NAMES`（33 点英文名表）、`landmark_names()` / `landmark_capabilities()`。
  - 能力分组常量 `CAP_FACE_CENTER/EYES/EYE_DETAILS/EARS/MOUTH/ARMS/HANDS/LEGS/FEET` 与
    `COCO17_SUPPORTED_CAPABILITIES`（COCO17 结构性支持 = face_center/eyes/ears/arms/legs，
    缺 eye_details/mouth/hands/feet，对应 adapter 映射与 S0 降级清单）。
  - `landmarks_missing_for_capabilities(indices, supported)`：按能力分组判定后端结构性缺点；
    `supported=None`（MediaPipe full）视为全部支持、返回空（行为不变）。
- **`core/rule_scoring.py` 规则三态结构化（Issue #11）**：
  - 新增三态常量：`RULE_STATE_EVALUATED/SKIPPED`、`SKIP_MISSING_LANDMARKS/LOW_CONFIDENCE/
    INSUFFICIENT_VALID_FRAMES`。
  - `Rule` 新增 `required_indices`（与各 `_rule_*` 内 `_valid_frame(...)` 关键点集合一致）；
    `RuleViolation` 新增 `state` / `skip_reason` / `required_landmarks` / `required_capabilities`
    / `missing_landmarks`（均带默认值，向后兼容）。
  - `score_rules` 新增可选 `supported_capabilities` 形参（默认 `None`=MediaPipe full）：
    后端缺所需能力时该规则直接 `state=skipped` + `skip_reason=missing_landmarks` 并列出缺失点，
    不当合格/不合格；有效帧 0 → `low_confidence`，0<cnt<min_valid → `insufficient_valid_frames`，
    充足 → `evaluated`。**`detail` 中文逐字保留**，故 golden 不漂移。
- **`analysis/tech_eval.py` 指标契约字段（Issue #11）**：
  - `IndicatorResult` 新增 `required_landmarks` / `missing_landmarks` / `backend`（默认 mediapipe，
    带默认值向后兼容）。
  - 新增每指标 `*_REQUIRED_INDICES` 声明、`_runtime_missing_landmarks()`（整段从未有效的点）、
    `_attach_contract()`（装配层统一补齐契约字段，**不改各 `eval_*` 内部 status/reason/detail
    判定**）。在 `_evaluate_from_arrays` 末尾对七个指标按各自所需关键点与所在段 mask 补齐；
    `keep_detail=False` 与 `evaluate_video` 的 strip 改用 `dataclasses.replace`，保留契约字段。
- **报告输出补缺失关键点 / backend（Issue #11，仅 MediaPipe 侧）**：
  - `batch/batch_tech_eval.py`：CSV 新增「重心（侧面优先/侧面/正面/CoM）/回收速度/
    发力顺序/拳面角度 缺失关键点」列与 `backend` 列；JSONL 经 `to_jsonable` 自动带上新字段。
  - `batch/batch_dual_compare.py`：`error_rules.csv` 新增 `state` / `skip_reason` /
    `missing_landmarks` 列；JSONL 经 `_jsonable`(asdict) 自动带上新字段。
- **新增测试**：
  - `tests/test_rule_availability.py`：覆盖三种 `skip_reason`（low_confidence /
    insufficient_valid_frames / missing_landmarks）、COCO17 缺点规则（feet/mouth）被 skipped、
    required_landmarks/capabilities 声明正确、默认不传 `supported_capabilities` 时无 backend 级缺点，
    并回归 COCO17 左右眼中心可用、眼细分缺失的 adapter 契约。
  - `tests/test_tech_eval_contract.py`：`evaluate_video_full` 每指标含 `status/reason/
    required_landmarks/missing_landmarks/backend`；`_attach_contract` 不改 status/reason/detail；
    人为遮挡脚部后 `missing_landmarks` 如实含脚跟/脚尖；契约字段 JSON 可序列化。
- **`docs/yolo_migration_issues.md`**：Issue #11 顶部勾选「仅预览 → 仅 MediaPipe 结构化改造」分支，
  任务清单 / 验收标准按本期实现状态更新（YOLO partial eval 标注「不适用」）。

### 范围守住（未做）

- 未启用任何 YOLO partial tech_eval 指标（#10 = 仅预览）；`supported_capabilities` 仅预留接口。
- 未改各 `eval_*` / 各 `_rule_*` 的判定逻辑与阈值；未重标定。
- MediaPipe 默认 `pose33_v3` 路径行为不变（golden 全绿）。

### 验证方法

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_rule_availability.py tests\test_tech_eval_contract.py -q  # 17 passed
.\.venv\Scripts\python.exe -m pytest tests\test_pose33_v3_golden.py tests\test_valid_mask_migration.py tests\test_yolo_landmark_mapping.py -q  # 42 passed（MediaPipe 默认不漂移 + adapter 契约）
.\.venv\Scripts\python.exe -m pytest tests -q                                                              # 136 passed（此前 119 + 本期 17 新增）
.\.venv\Scripts\python.exe -m py_compile core\pose_features.py core\rule_scoring.py analysis\tech_eval.py batch\batch_tech_eval.py batch\batch_dual_compare.py core\action_compare.py apps\main.py apps\app_ui.py  # exit 0
```

- `tests/test_pose33_v3_golden.py` 全绿 → 规则 `detail` 中文逐字保留、各指标判定未改动，MediaPipe
  旧路径行为不漂移（行为不变硬门槛）。
- `tests/test_rule_availability.py` / `tests/test_tech_eval_contract.py` 全绿 → 结构化三态与指标契约
  字段齐全、缺点判定正确、不可评估不当合格/不合格。
- 全量 136 passed（此前 119 + 本期 17 新增）→ 无回归。

---

## 2026-05-31: YOLO 迁移 S3 — 标定与基准报告（Issue #10）

### 问题描述

S3 需要在同一批样本上跑三路对照（MediaPipe `pose33_v3` / MediaPipe `body_core_v1` /
YOLO `body_core_v1`），据**预注册数字判据**确定：① `body_core_v1` 是否可用于评分；
② 重标定 `body_core_v1` DTW baseline（替换全局占位 `2.0`）；③ 标定 YOLO 侧
`valid_conf_thr`（替换 #7 占位 `0.5`；是否允许出分由 S3 go/no-go 判据决定）。结论必须对照
预注册数字、不能是「可用/不建议」这类感觉。硬约束：先预注册阈值与 pass/fail 口径再跑数据；
多人样本（闸门 `review_required=True`）不得进入标定；MediaPipe 默认 `pose33_v3` 路径与
golden 不漂移。

### 修改内容

- **新增 `analysis/calibrate_body_core.py`（独立标定脚本，组合既有生产函数，不改主链路默认行为）**：
  - 每段样本每后端**只推理一次**并缓存到 `outputs/calib_body_core/raw_cache/*.npz`；
    `valid_conf_thr` 扫描只对缓存 conf 重新阈值化派生 `valid_mask`，不重复推理。
  - 由 MediaPipe `(T,33,4)` 缓存同时派生 `pose33_v3`（`normalize_pose_xy_v3`）与
    `body_core_v1`（`normalize_pose_body_core_v1`）；YOLO `(T,33,4)` 缓存派生 YOLO `body_core_v1`。
  - **成对匹配矩阵**（视角组内，跨视频）：self-match 恒为满分、无方差，故只取跨样本对统计
    相关性 / baseline / pass-fail，避免 self-match 把相关性虚高成 1.0。
  - 多人样本由 YOLO 多人闸门（`evaluate_multi_person_gate`，沿用 #9 逻辑不改）排除出标定集。
- **`core/feature_layout.py`**：`BODY_CORE_V1.default_baseline` 由占位 `None` 标定为 **1.2826**
  （尺度对齐：`2.0 × median(bodycore_avg_cost)/median(pose33_avg_cost) = 2.0 × 0.6413`），
  使 body_core 分数与 pose33 同尺度、可共享 pass/fail 阈值。
- **`core/yolo_adapter.py`**：`DEFAULT_YOLO_VALID_CONF_THR` 由占位 `0.5` 定为 **0.6**；
  `YOLO_CALIBRATION_STATUS` 保持 `unvalidated`；`CALIBRATION_NOTE` 改写为「参数已落库，
  但跨视频 go/no-go 未通过，仅预览 / 内部标定参考，不得对外评分」。
- **`core/body_core_compare.py`**：baseline 取自 layout（`BODY_CORE_V1_CALIBRATED_BASELINE`），
  移除占位 `BODY_CORE_V1_PLACEHOLDER_BASELINE`；模板/匹配结果 `calibration_status` 仍标
  `unvalidated`，模板 meta 额外写 `score_authorized=False`，明确不得进入用户报告 / 正式评分。
- **`apps/make_template.py` / `apps/match_template.py`**：更新 body_core 路径打印文案为「仅预览 /
  内部标定参考，不得对外评分」。
- **新增 `docs/yolo_body_core_calibration.md`（标定报告）**：头部预注册 pass/fail 判定口径
  （模板分数阈值口径、pose33 分数 ≥ 0.55、样本范围=4 段单人）与 7 条数字判据（J1–J7）；
  正文逐条引用实测数字；**结论四选一 = 「仅预览」**（跨视频 J1 corr 0.280 未达标、
  J4 一致率 0.50 未达标；J2 corr 0.980、J3 MAE 0.0468、J5 有效率 0.875、J7 失败率 0 达标），
  并说明含 self-match 的 0.838/0.990/0.0234 只作健全性检查、不可作为验收判据。
- **新增 `tests/test_s3_calibration.py`**：守卫标定值入库（baseline=1.2826、thr=0.6、状态字符串）、
  报告存在且头部含预注册数字与四选一结论。
- **更新既有测试**：`test_body_core_layout.py`（baseline 已标定、`baseline_calibrated=True`）、
  `test_yolo_backend_contract.py` / `test_yolo_landmark_mapping.py`（`calibration_status` /
  `valid_conf_thr`=0.6）随标定语义同步。

### 关键结论（详见 docs/yolo_body_core_calibration.md）

- **body_core_v1 仅预览 / 内部标定参考，不授权模板匹配对外出分**：baseline=1.2826、YOLO
  `valid_conf_thr`=0.6 已落库，但 `calibration_status=unvalidated`、`score_authorized=False`。
- **不进 full tech_eval**：跨视频 body_core 与 pose33 参照分歧（J1=0.280、J4=0.50）+
  COCO17 结构性缺点。
- **阈值标定核心证据**：thr 0.5→0.6 时跨视频 corr(YOLO,MP body_core) 0.105→0.980、
  MAE 0.1466→0.0468；thr=0.7 无收益反丢帧（有效率最小 0.784）。故取满足 J2/J3 的最小阈值 0.6。
- **侧面发现**：MediaPipe `visibility>=0.5` 在侧面把远侧关节判为不可见（punch_side body_core
  有效率仅 0.147），YOLO `conf>=0.6` 在侧面保留更多帧（~0.92–1.0）。
- **对 #11 分流**：结论 =「仅预览」→ #11 只做 MediaPipe 侧结构化状态改造，
  不启用 YOLO partial tech_eval。

### 验证方法

```powershell
.\.venv\Scripts\python.exe -m analysis.calibrate_body_core --calib-conf-thr 0.6 --out outputs/calib_body_core
.\.venv\Scripts\python.exe -m pytest tests\test_s3_calibration.py -q                              # 5 passed
.\.venv\Scripts\python.exe -m pytest tests\test_body_core_layout.py tests\test_yolo_backend_contract.py tests\test_yolo_landmark_mapping.py -q  # 含本期标定语义更新
.\.venv\Scripts\python.exe -m pytest tests\test_pose33_v3_golden.py -q                            # 16 passed（MediaPipe 默认不漂移）
.\.venv\Scripts\python.exe -m pytest tests -q                                                     # 119 passed（此前 114 + 本期 5 新增）
.\.venv\Scripts\python.exe -m py_compile core\feature_layout.py core\yolo_adapter.py core\body_core_compare.py analysis\calibrate_body_core.py apps\make_template.py apps\match_template.py  # exit 0
```

- `tests/test_pose33_v3_golden.py` 全绿 → MediaPipe 旧 `pose33_v3` 路径行为不漂移（行为不变硬门槛）。
- `tests/test_s3_calibration.py` 全绿 → baseline/阈值/状态已入库、报告头部预注册数字齐全。
- 全量 119 passed（此前 114 + 本期 5 新增）→ 无回归。

---

## 2026-05-31: YOLO 迁移 S2 — 多人场景闸门（Issue #9）

### 问题描述

`batch_tech_eval` / `batch_dual_compare` 跑的是学员视频，教练、镜面反射、路人入镜常见
（S0 spike 已实证：学员样本最多检出 8 人、单视频 274 帧多人）。YOLO「最大框/最高分取单人」
可能**稳定选错实例**——这是正确性风险，不是鲁棒性优化。MVP 必须能识别并拒绝/降级，
**不允许静默选最大框**。本期依赖 #7（YOLO adapter，已合并 main），在序列层判定多人并写
meta，在 YOLO 评分入口（#8 的 `body_core_compare` 闭环）强制拒绝/降级出分。硬约束：
单人样本不受影响；MediaPipe 默认路径与 `pose33_v3` golden 不漂移；完整多人鲁棒策略
（中心最近、tie-break、跨段 track 延续）本期不做。

### 修改内容

- **`core/yolo_adapter.py` 新增多人闸门判定**：
  - 新增纯函数 `evaluate_multi_person_gate(num_persons_per_frame)`，返回
    `multi_person_detected` / `max_persons` / `multi_person_frames` / `gate_status` /
    `review_required` / `gate_note`。语义铁律：`review_required=True` 的视频不得进入对外评分。
  - 新增常量 `GATE_STATUS_OK="ok"`、`GATE_STATUS_MULTI_PERSON="multi_person_review_required"`、
    `MULTI_PERSON_GATE_NOTE`（说明多人 = 正确性风险、必须人工复核）。
  - `extract_yolo_landmark_series` 的 meta 在原有 `num_persons_per_frame`/`max_persons`/
    `multi_person_frames` 基础上新增 `multi_person_detected`/`gate_status`/`review_required`/
    `gate_note`（检出 `num_persons>1` 即标 `review_required=True`）。
  - 更新模块/函数 docstring：闸门已落地（不再是「留给 #9」），`select_main_person` 注明仅单人
    场景可信、多人由闸门拒绝/降级。
- **`core/body_core_compare.py` 在 YOLO 评分入口强制拒绝/降级**：
  - 新增异常 `MultiPersonReviewRequiredError`（携带 `max_persons`/`multi_person_frames`）。
  - `BodyCoreMatchResult` 新增 `review_required`/`multi_person_detected`/`max_persons`/
    `multi_person_frames` 字段；`score` 类型放宽为 `float | None`（降级模式不产出分数）。
  - `match_body_core_template` 新增 `reject_multi_person: bool = True` 参数：
    默认多人抛 `MultiPersonReviewRequiredError`（不混入正常评分）；
    `reject_multi_person=False` 时降级——返回 `score=None` + `review_required=True`。
    单人 / MediaPipe 路径不受影响。
  - 审查补强：`match_body_core_template` 同时检查模板 meta 与目标视频 meta；YOLO 模板若由
    多人视频生成，默认也会拒绝出分，降级时 `score=None`，避免多人来源模板继续参与正常评分。
  - `_extract_body_core_yolo` 随 `backend_meta` 透传闸门字段；`create_body_core_template`
    把多人闸门字段（`multi_person_detected`/`review_required`/`gate_status` 等）一并写入模板 meta。
- **`apps/match_template.py` CLI 接线**：新增 `--allow-multi-person`（降级而非拒绝）；
  body_core 匹配捕获 `MultiPersonReviewRequiredError` 打印「需人工复核、拒绝出分」，
  降级时 `score=N/A` 且打印多人复核提示，避免格式化 `None` 崩溃。
- **测试**：
  - `tests/test_yolo_backend_contract.py` 增补：`evaluate_multi_person_gate` 单人/多人/空序列
    判定；序列层多人帧触发 `multi_person_detected`/`review_required`/`gate_status`，单人样本不触发。
  - `tests/test_body_core_layout.py` 增补：默认多人视频抛 `MultiPersonReviewRequiredError`、
    `--allow-multi-person` 降级返回 `score=None`+`review_required=True`、单人不受影响、
    多人来源模板 meta 透传 `review_required`，并补充多人来源模板默认拒绝出分回归。
    全程用 fake adapter + `patch_cv2_capture`，无网络、不下载模型、不读真实视频。

### 验证方法

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_yolo_backend_contract.py tests\test_body_core_layout.py -q   # 39 passed（含本期多人闸门用例）
.\.venv\Scripts\python.exe -m pytest tests\test_pose33_v3_golden.py -q                                        # 16 passed（MediaPipe 默认不漂移）
.\.venv\Scripts\python.exe -m pytest tests -q                                                                 # 114 passed（此前 104 + 本期 10 新增）
.\.venv\Scripts\python.exe -m py_compile core\yolo_adapter.py core\body_core_compare.py apps\match_template.py apps\make_template.py apps\app_ui.py apps\main.py   # exit 0
```

- `tests/test_pose33_v3_golden.py` 全绿 → MediaPipe 旧 `pose33_v3` 路径行为不漂移（行为不变硬门槛）。
- 多人帧触发 `multi_person_detected`/`review_required` 并被拒绝/降级，不静默选最大框（验收①）。
- 多人视频明确标「需人工复核/拒绝」，不混入正常评分结果（验收②）。
- 单人样本照常出分、不受闸门影响（验收③）。
- 全量 114 passed（此前 104 + 本期 10 新增）→ 无回归。

---

## 2026-05-31: YOLO 迁移 S2 — body_core_v1 布局引入 + 离线模板闭环（Issue #8）

### 问题描述

S2 需要引入 `body_core_v1`(12,2) 共享布局（YOLO/MediaPipe 都能产出的躯干四肢核心 12 点），
新增其 normalizer，并打通**一条** YOLO `body_core_v1` 离线模板闭环（生成 → 匹配）。该布局
此前在 S1 被刻意推迟（Issue #4 注释明确写「`body_core_v1` 在 #8 才注册」），因为只有真接
YOLO 时才有消费者。硬约束：不动 MediaPipe 默认 `pose33_v3` 路径（`infer()`/`annotate()`/
旧模板比对、golden 全绿）；YOLO 只允许 `body_core_v1`；`body_core_v1` baseline 与 YOLO 侧
`valid_conf_thr` 本期均为**待标定占位值**（正式标定在 #10），闭环输出 metadata 必须标
`calibration_status=unvalidated`、不得进入用户报告 / 正式评分；不同 layout 比对报清晰错误；
不实现 UI 后端选择 / Hybrid / 默认切换。

### 修改内容

- **`core/feature_layout.py` 注册 `body_core_v1`**：12 点 `source_indices=(11,12,13,14,15,16,
  23,24,25,26,27,28)`（肩/肘/腕 + 髋/膝/踝，全部落在 COCO17 可映射点），`shape=(12,2)`，
  `mirror_pairs` 为相邻对 `(0,1)…(10,11)`，`joint_names` L/R 交替。`default_baseline=None`
  （待标定占位，刻意区别于 pose33_v3 的已标定 2.0）。模块 docstring 同步更新范围说明。
- **`core/pose_features.py` 新增共享 normalizer `normalize_pose_body_core_v1()`**：归一化策略
  与 `normalize_pose_xy_v3` 同构（躯干长度为主尺度 + front/side 自适应旋转），但索引/输出
  shape/关节顺序全部取自 `BODY_CORE_V1` layout。新增 `_blaze33_xy_getter()` 统一两类输入——
  MediaPipe landmark 对象序列 与 YOLO `(33,4)` numpy 行——因此**同一 normalizer 跨后端共享**，
  供 #10 三方对比。
- **`core/yolo_adapter.py` 新增 `BODY_CORE_V1_VALID_INDICES`**：body_core_v1 在 BlazePose33 中
  的源索引（与 layout.source_indices 一致，冗余定义避免 adapter 反向依赖 feature_layout 触发
  循环 import；一致性由测试守卫）。供闭环按 `valid_mask` 统计 body_core 有效帧率。
- **新增 `core/body_core_compare.py`（离线闭环唯一入口）**：
  - `extract_body_core_features(backend=...)`：MediaPipe 路径复用 `rule_scoring.extract_pose_raw`
    拿 `(T,33,4)` 后逐帧套共享 normalizer（也让 golden harness 能确定性回放）；YOLO 路径用
    `extract_yolo_landmark_series` 拿序列层 `(T,33,4)`+`valid_mask` 后同样逐帧 normalize。
    缺帧按 layout shape 补零或沿用上一帧。
  - `create_body_core_template()`：生成 `body_core_v1` 模板，metadata 写
    `feature_layout=body_core_v1`、`calibration_status=unvalidated`、`baseline_calibrated=False`、
    占位 `baseline` 与 `calibration_note`；YOLO 路径透传 `valid_conf_thr`/多人/track 信息。
  - `match_body_core_template()`：匹配前强制校验模板 `feature_layout` 必须为 `body_core_v1`
    （否则报清晰错误，不与 pose33_v3 混用），复用 `_assert_feature_layout_match` 守卫 shape/layout，
    返回 `BodyCoreMatchResult`（标 `calibration_status=unvalidated`，分数仅供调试/标定）。
- **CLI 接线（显式 opt-in，默认 pose33_v3 路径完全不变）**：
  - `apps/make_template.py`：新增 `--backend {mediapipe,yolo}`、`--feature-layout {pose33_v3,
    body_core_v1}`；选 body_core_v1 或 yolo 时走 `_make_body_core_template`，否则走原
    `_make_pose33_v3_template`（原逻辑零改动）。YOLO 强制 body_core_v1。
  - `apps/match_template.py`：新增同名参数；按模板 `meta.feature_layout` 或显式参数判定是否走
    `_match_body_core`，否则走原 `_match_pose33_v3`。打印明确标注分数未标定、不得对外评分。
- **测试**：
  - 新增 `tests/test_body_core_layout.py`（16 用例）：layout shape/mirror pairs/joint names、
    共享 normalizer 接受 MediaPipe landmark 与 YOLO `(33,4)` 行、layout mismatch 报错、
    **YOLO body_core_v1 离线闭环生成→匹配同一视频产出分数且标 unvalidated**、YOLO 拒绝
    pose33_v3 模板、MediaPipe 也能生成 body_core_v1 模板。PR #19 审查补充两条回归：YOLO
    低置信 body_core 核心点帧必须按 `valid_mask` 视为无效并沿用上一帧特征；`start/end`
    显式裁剪必须在完整序列上切片，避免先裁后再用原始帧号二次裁剪导致模板退化为单帧。
    全程用 fake adapter + golden harness，无网络、不下载模型、不读真实视频。
  - 更新 `tests/test_layout_shape_param.py`：`body_core_v1` 现已注册（断言改为 `has_layout` 为真）；
    无法解析 shape 的用例从 `(12,2)` 改为仍未注册的 `(15,2)`，保留原意。
- **PR #19 审查修复**：
  - `core/body_core_compare.py` 新增统一 `_normalize_body_core_sequence()`：YOLO / MediaPipe
    body_core 序列在 normalizer 前先读 `valid_mask`，只有 12 个核心点全 valid 的帧才参与归一化；
    无效帧按缺帧处理（沿用上一帧或前导零帧），防止低置信坐标绕过 `valid_mask` 进入 DTW。
  - `create_body_core_template()` 不再把 `start/end` 传入提取器提前截断视频，而是先抽取完整序列、
    再按原始帧号切模板片段，与旧 `pose33_v3` CLI 语义保持一致。

### 验证方法

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_body_core_layout.py -q          # 16 passed
.\.venv\Scripts\python.exe -m pytest tests\test_pose33_v3_golden.py -q          # 16 passed（MediaPipe 默认不漂移）
.\.venv\Scripts\python.exe -m pytest tests\test_yolo_landmark_mapping.py tests\test_yolo_backend_contract.py -q  # YOLO 契约不变
.\.venv\Scripts\python.exe -m pytest tests -q                                   # 104 passed
.\.venv\Scripts\python.exe -m py_compile core\feature_layout.py core\pose_features.py core\yolo_adapter.py core\body_core_compare.py apps\make_template.py apps\match_template.py  # exit 0
```

- `tests/test_pose33_v3_golden.py` 全绿 → MediaPipe 旧 `pose33_v3` 路径行为不漂移（行为不变硬门槛）。
- `tests/test_body_core_layout.py` 全绿 → 布局正确、闭环可生成可匹配、分数标 unvalidated、layout mismatch 报错，且 PR #19 审查发现的 `valid_mask` 与 `start/end` 裁剪问题均有回归覆盖。
- 全量 104 passed（此前 88 + 本期 16 新增，含 1 处 S1 测试随注册状态变化的适配）→ 无回归。

---



### 问题描述

审查 PR #18（Issue #7）时发现本次 YOLO adapter 任务记录误写为未来日期 `2026-06-01`，
与当前任务完成日期不一致，后续追踪 issue、PR 与归档记录时容易造成时间线混乱。

### 修改内容

- 将本条 YOLO 迁移 S2 记录日期从 `2026-06-01` 校正为 `2026-05-31`。
- 保持原有 YOLO adapter 功能记录、验证命令与范围说明不变。

### 验证方法

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_yolo_landmark_mapping.py tests\test_yolo_backend_contract.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_pose33_v3_golden.py -q
.\.venv\Scripts\python.exe -m py_compile core\yolo_adapter.py apps\main.py apps\app_ui.py core\vision_pipeline.py
```

---

## 2026-05-31: YOLO 迁移 S2 — YOLO adapter + COCO17→Pose33-like 映射（Issue #7）

### 问题描述

S2 需要让 YOLO 进入主链路，但 COCO17 缺嘴角/手指/脚跟脚尖/眼细分点，绝不能伪造成完整
Pose33。本期新增轻量 YOLO adapter，把 COCO17 诚实映射到 BlazePose33-like 容器：缺失点在
序列层一律 `valid_mask=False`、在边界层一律 `synthetic=True`/`visibility=0.0`。硬约束：
不得改变 MediaPipe 旧默认路径（`pose33_v3` 模板、`infer()`/`annotate()`、`extract_pose_raw`），
`tests/test_pose33_v3_golden.py` 必须保持全绿；ultralytics 必须懒加载，未安装时不影响
MediaPipe 路径与既有测试；YOLO 侧 `valid_conf_thr` 本期为待标定占位值（#10 标定），仅供
预览/调试 + S3 标定，不得对外评分。

### 修改内容

- **新增 `core/yolo_adapter.py`（懒加载 ultralytics）**：
  - **边界容器**：`@dataclass(frozen=True)` 的 `Landmark`（含 `confidence`/`synthetic`）与
    `FrameResult`（`pose33`/`hands`/`track_id`/`meta`）。`synthetic=True` 只活在该边界层，
    绝不进入 `(T,33,4)` 序列数组。
  - **映射表**：`COCO17_TO_BLAZE33`（17 项）与 `BLAZE33_MISSING_IN_COCO17`（16 项），
    数值与已验证的 `analysis/spike_yolo_baseline.py` 完全一致（键=BlazePose33 idx、值=COCO17 idx）。
  - **纯映射函数**：`map_coco17_to_blaze33` 产出 `(33,4)` 行 `(x,y,z=0,conf)` + `(33,)` bool 行
    （映射点 `conf>=valid_conf_thr` 才有效，缺失点强制 `False`）；`coco17_to_landmarks` 产出
    边界层 33 元组（缺失点 `synthetic=True`/`visibility=0.0`，映射点带 `confidence`）；
    `map_coco17_person` 一次性返回「序列行 + 有效行 + FrameResult」三件套。
  - **结果解析**：`extract_persons`/`select_main_person`（单人 MVP=最大框，退化时取最高分）/
    `yolo_result_to_arrays`/`yolo_result_to_frame`，容忍 torch tensor 或 numpy，便于测试注入
    fake result。
  - **单目标 tracker**：`SingleTargetTracker`，段内连续分配 track_id，未检出超 `max_missed` 帧丢弃；
    `reset()` 归零（段边界语义）。
  - **adapter 类 `YoloPoseAdapter`**：`from ultralytics import YOLO` 仅在 `_load()` 内执行；
    默认模型路径走 `core.paths.models_dir()/yolo11n-pose.pt`；`valid_conf_thr` 占位默认 + 文档化
    为待标定；`confidence_kind="yolo_conf"`；`infer_arrays`（序列热路径，只回 numpy）与
    `infer_frame`（边界层 FrameResult）；暴露 `last_num_persons`/`num_persons`（供 #9 多人闸门），
    本期不实现闸门；`reset_tracker()` 控制段边界。
  - **序列层 `extract_yolo_landmark_series`**：返回 `landmarks[T,33,4]` + `valid_mask[T,33]`
    （**仅 numpy，不逐帧返回冻结对象**）+ `meta`。每次调用开头 `reset_tracker()`，故 track_id
    段边界必然重置。无人帧/空结果优雅降级为零行 + 全 False mask（不抛异常）。`meta` 含
    `backend="yolo"`、`model_name`、`running_mode`、`confidence_kind="yolo_conf"`、
    `validity_policy="confidence_thr"`、`valid_conf_thr`（占位）、`calibration_status="unvalidated"`、
    `calibration_note`（标注 preview/debug-only）、`frame_count`、`fps`、`num_persons_per_frame`、
    `max_persons`、`multi_person_frames`、`track_ids`、`track_reset_note`。
- **测试（无网络、不下载模型、不读真实视频）**：
  - 新增 `tests/yolo_fakes.py`：`make_coco17` 合成关键点、`FakeYoloResult`（single/multi/empty）
    模拟 ultralytics 结果、`FakeYoloAdapter` 替身 adapter（复用真实解析/ tracker 逻辑，鸭子类型注入）、
    `FakeCapture`+`patch_cv2_capture` 回放固定帧数。
  - `tests/test_yolo_landmark_mapping.py`：边界层缺失点 `synthetic=True`/`visibility=0.0`
    （含嘴角 9/10、手指 17-22、脚跟脚尖 29-32、眼细分 1/3/4/6）；序列层同索引 `valid_mask=False`、
    长度恰 33、COCO 对应点 confidence 正确传入 channel-3；序列层输出是 numpy 数组。
  - `tests/test_yolo_backend_contract.py`：无人帧/空结果零行+全 False mask 不崩；tracker 段边界
    重置语义；序列层只回 numpy + meta 字段齐全；`num_persons` 被如实暴露（多人不静默吞，
    闸门留 #9）；adapter 默认路径解析且构造/导入不触发 ultralytics。
- **依赖声明**：ultralytics/torch 仍只在 `requirements-spike.txt` 声明，**未**加入核心 `requirements.txt`。
- **范围守住**：未引入 `body_core_v1`（#8）、未实现多人闸门（#9）、未标定（#10）、未做规则分级（#11），
  无 UI/CLI/batch 接线，无默认后端切换。

### 验证方法

```powershell
.\.venv\Scripts\python.exe -m py_compile core\yolo_adapter.py                          # exit 0
.\.venv\Scripts\python.exe -c "import core.yolo_adapter"                               # import_ok，ultralytics/torch 均未加载
.\.venv\Scripts\python.exe -m pytest tests\test_yolo_landmark_mapping.py tests\test_yolo_backend_contract.py -q   # 24 passed
.\.venv\Scripts\python.exe -m pytest tests\test_pose33_v3_golden.py -q                 # 16 passed（MediaPipe 默认不变）
.\.venv\Scripts\python.exe -m pytest tests -q                                          # 88 passed
```

- `import core.yolo_adapter` 后 `sys.modules` 不含 `ultralytics`/`torch` → 懒加载成立，未安装 ultralytics
  也不影响 MediaPipe 路径与既有测试。
- `tests/test_pose33_v3_golden.py` 全绿 → MediaPipe 旧默认路径行为不漂移（行为不变硬门槛）。
- 全量 88 passed（此前 64 + 本期 24 新增）→ 无回归。

---

## 2026-05-31: YOLO 迁移 S1 — artifact root 统一 + 模板 metadata 扩展（Issue #6）

### 问题描述

此前 `models` / `templates` / `outputs` 三个顶层产物目录散落在各包里，统一用
`Path(__file__).resolve().parent / "models"` 之类写法推导（`core`/`apps`/`batch`/`analysis`
均有）。由于 `__file__` 锚点随所在包不同，同一类产物可能指向不同位置，难维护、易踩坑。
同时模板 metadata 缺少后端/布局/有效性信息，无法为 S2 接入 YOLO 做铺垫。本次将三个根目录
收口到唯一 helper，并以「增量、向后兼容」方式扩展模板 metadata。验收硬门槛：`pose33_v3`
golden 不漂移、旧模板仍可加载比对。

### 修改内容

- **集中式根目录解析**：新增 `core/paths.py`（仅依赖 `pathlib`，不导入业务模块避免循环），
  统一锚定仓库根（`core/` 包父目录）：`repo_root()` / `models_dir()` / `templates_dir()` /
  `outputs_dir()`。`templates_dir`/`outputs_dir` 返回前 `mkdir(parents=True, exist_ok=True)`；
  `models_dir` 仅保证目录存在，**不删除/移动**任何已有模型文件（缺失 `.task` 由
  `MediaPipePipeline` 自动下载）。
- **替换全部散落写法**：约定 `from core.paths import models_dir`（`core/` 内用相对 import），
  局部变量改名 `models_dir_path = models_dir()` 后透传；模板与 outputs 同理。覆盖：
  - models（9 处）：`core/action_compare.py`(3)、`core/rule_scoring.py`、`analysis/tech_eval.py`、
    `apps/main.py`(2)、`apps/app_ui.py`(2)、`apps/make_template.py`、`apps/match_template.py`(2)、
    `batch/batch_export_skeleton.py`。
  - templates（3 处）：`core/action_compare.py::create_template_from_video`、
    `apps/make_template.py`、`apps/match_template.py`(preview)。
  - outputs（4 处）：`apps/app_ui.py`、`batch/batch_tech_eval.py`、`batch/batch_export_skeleton.py`、
    `batch/batch_dual_compare.py`（均保留 `--out_dir` 覆盖分支）。
- **模板 metadata 扩展（增量字段）**：在两处写模板入口
  （`core/action_compare.py::create_template_from_video`、`apps/make_template.py`）的 `meta`
  新增 `backend="mediapipe"`、`model_name="pose_landmarker_<variant>"`、`feature_layout="pose33_v3"`、
  `normalizer_version="v3"`、`confidence_kind="visibility"`、`validity_policy=MEDIAPIPE_VALIDITY_POLICY`、
  `valid_conf_thr=DEFAULT_VALID_CONF_THR`（后两者复用 `core.pose_features` 集中式常量）。
  旧模板里的历史 `feature_layout="pose_indices_11_32_xy_rot_scale_norm_v3"` 作为 legacy alias 兼容读取，
  新模板统一写 #4 注册表布局名，便于 #7/#8 后续直接读取同一字段。
- **旧模板兼容加载**：`core/action_compare.py` 新增 `template_meta_defaults()` 与
  `normalize_template_meta()`（`setdefault` 补默认、不覆盖已有键），在
  `compare_video_to_template` / `compare_video_to_dual_templates` 的 `meta = tpl["meta"].item()`
  之后统一补齐，缺字段的旧模板照常加载比对。
- **审查修复**：规范 metadata 字段名，移除新模板写入 `feature_layout_name` 的分叉；双模板比较时
  canonical 化旧/新 `pose33_v3` alias，避免一个旧模板搭配一个新模板时被误判为 layout mismatch。
- **.gitignore**：补充 Issue #6 统一根目录注释块，保留 `templates/`、`outputs/`、
  `models/*.task|*.pt|*.onnx`，并保留 `core/models/*.task`、`analysis/models/*.task`（旧拷贝仍在磁盘）。
- **测试**：新增 `tests/test_artifact_roots.py`（各入口解析到同一 models/templates/outputs root，
  且生产文件不再出现 `parent / "models|templates|outputs"` 字面量）与
  `tests/test_template_metadata.py`（新模板 7 字段齐全；剥离新字段的旧模板仍可加载比对）。

### 验证方法

```powershell
.\.venv\Scripts\python.exe -m py_compile apps\main.py apps\app_ui.py apps\make_template.py apps\match_template.py core\vision_pipeline.py core\action_compare.py core\rule_scoring.py core\pose_features.py core\paths.py analysis\tech_eval.py batch\batch_tech_eval.py batch\batch_export_skeleton.py batch\batch_dual_compare.py
.\.venv\Scripts\python.exe -m pytest tests\test_artifact_roots.py tests\test_template_metadata.py -q   # 13 passed
.\.venv\Scripts\python.exe -m pytest tests\test_pose33_v3_golden.py -q                                  # 16 passed（行为不漂移）
.\.venv\Scripts\python.exe -m pytest tests -q                                                           # 64 passed
```

- `tests/test_pose33_v3_golden.py` 全绿 → metadata 扩展未改动 features / 分数 / golden（行为不变硬门槛）。
- `tests/test_artifact_roots.py` 全绿 → 各入口收口到同一顶层 root，生产代码无残留散落字面量。
- `tests/test_template_metadata.py` 全绿 → 新模板字段齐全、旧模板向后兼容可加载。

---

## 2026-05-31: YOLO 迁移 S1 — valid_mask 契约迁移 + 逐位等价回归（Issue #5）

### 问题描述

把“此点是否可用”的判据从散落在 `analysis/tech_eval.py` 的 `_valid()`/`_lm_vis(...) >= thr`
与 `core/rule_scoring.py` 的 `_valid_frame()`（`lm[idx,3] >= thr` 风格、调用面几十处）统一
收口到集中式 `valid_mask`，为后续 YOLO 缺失点接入做防护。验收硬指标：同一 fixture 下三种调用
方式（旧式不传 mask / 显式传 mask / 改造前 golden）逐位一致；`pose33_v3` golden 不漂移。

### 修改内容

- **集中式 helper**：`core/pose_features.py` 新增 `derive_valid_mask(landmarks, thr=0.5)`，
  返回 `landmarks[...,3] >= thr`（单帧 `(33,)` / 序列 `(T,33)` bool）；新增常量
  `DEFAULT_VALID_CONF_THR=0.5`、`MEDIAPIPE_VALIDITY_POLICY="visibility_thr"`。阈值只存在于此处。
- **rule_scoring.py**：`_valid_frame` 改为读传入的单帧 mask 切片；删除已无用的 `_lm_vis`；
  全部 `_rule_*` 与 `Rule.check_fn` 签名加 `valid_mask`；`score_rules` 新增
  `valid_mask: np.ndarray | None = None`（None 时回退 `derive_valid_mask`）。
  `extract_pose_raw` 产出端在 `meta` 落地 `validity_policy`/`valid_conf_thr`/`valid_mask`。
- **tech_eval.py**：`_valid` 重写为读 mask 切片；新增 `_resolve_mask` 统一回退逻辑；
  `_center_x`/`_frame_dir`/`_foot_edges_x`/`_infer_front_leg_side`/`_compute_segment_center`/
  `_compute_body_com_single` 等单帧 helper 改吃 mask_row；`eval_cog_side`/`eval_cog_front`/
  `eval_cog_com`/`eval_retract_speed_side`/`eval_wrist_angle`/`eval_force_sequence`、
  `_detect_retract_events_side`/`_detect_extension_events`/`_subset_by_intervals`/
  `_eval_cog_side_prefer_punch_windows`、视频级入口 `evaluate_video_assets/detail/full/video`
  与 `_evaluate_from_arrays` 全部新增 `valid_mask`（None 时按 meta 的 `valid_conf_thr` 现场推导）。
  `extract_pose_and_view_scores` 产出端 `meta` 落地 `validity_policy`/`valid_conf_thr`（其 meta 会
  进 JSON 报告，故只落标量，mask 由下游同阈值现场推导，逐位等价）。
- **测试**：新增 `tests/test_valid_mask_migration.py`，验证 `derive_valid_mask` 与旧式阈值逐位一致、
  `score_rules` 与各 `eval_*` 在“不传 mask vs 显式传 mask”下逐位一致、`evaluate_video_full`
  两种调用方式全指标一致。

### 验证方法

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_valid_mask_migration.py tests\test_pose33_v3_golden.py tests\test_layout_shape_param.py tests\test_representative_cycle_layout.py -q
# 51 passed
.\.venv\Scripts\python.exe -m py_compile apps\main.py apps\app_ui.py core\vision_pipeline.py core\action_compare.py batch\batch_tech_eval.py batch\batch_dual_compare.py analysis\tech_eval.py core\rule_scoring.py core\pose_features.py
```

- `tests/test_pose33_v3_golden.py` 全绿 → 迁移后行为 == 改造前 golden（验收①③）。
- `tests/test_valid_mask_migration.py` 全绿 → 旧式不传 mask == 显式传 mask（验收①②）。
- 源码扫描确认 `tech_eval`/`rule_scoring` 评分路径不再出现散落的 `lm[idx,3] >=` / `_lm_vis(...) >=`
  （仅 `_draw_pose33` 渲染阈值与 docstring 保留，非评分路径）。

---

## 2026-05-30: PR #16 审查补强 - 双模板关节误差接入 valid_mask

### 问题描述

审查 PR #16 时发现 `core/action_compare.py` 的双模板关节误差统计仍直接读取
`raw[..., 3]` 并在局部使用 `0.5` 阈值过滤可见点；规则评分入口虽已兼容 `valid_mask`，
但外层调用没有把 `extract_pose_raw` 产出的 mask 传入。这会让 #5 的有效性合约在双模板路径
留下一个绕行点。

### 修改内容

- 在 `core/action_compare.py` 新增 `_valid_mask_from_raw()`，优先使用 `extract_pose_raw` 的
  `meta["valid_mask"]`，仅兼容旧 meta 时才按 `valid_conf_thr`/默认阈值调用 `derive_valid_mask`。
- 双模板规则评分显式把 raw mask 传给 `score_rules`。
- 双模板关节误差统计改为读取 raw mask 的 `source_indices` 切片，不再局部读取
  `raw[..., 3]` 或维护独立可见度阈值。

### 验证方法

- `.\.venv\Scripts\python.exe -m pytest tests\test_valid_mask_migration.py tests\test_pose33_v3_golden.py`
  → 31 passed。
- `.\.venv\Scripts\python.exe -m py_compile .\apps\main.py .\apps\app_ui.py .\core\vision_pipeline.py .\core\pose_features.py .\core\rule_scoring.py .\core\action_compare.py .\analysis\tech_eval.py`
  → 通过。
- `.\.venv\Scripts\python.exe -m pytest tests` → 51 passed。

---

## 2026-05-30: 变更日志归档与重建

### 问题描述

当前 `change.md` 累积过长，需要将既有记录归档并重建当前日志入口。

### 修改内容

- 将旧 `change.md` 重命名为 `change（start~2026.5）.md`。
- 新建当前 `change.md`，作为后续任务记录入口。
- 更新 `AGENTS.md`、`CLAUDE.md` 和 YOLO 迁移文档中的相关说明。

### 验证方法

- 使用 `git status -sb`、`rg -n "change.md|change（start~2026.5）.md"` 确认重命名与引用更新。

---

## 2026-05-30: YOLO 迁移 S0 决策门（Issue #1 + #2）

### 问题描述

推进 YOLO 迁移 M0 决策门。需在动主代码前完成 S0：固定许可结论与实验环境、建立基线样本集（#1），
并用独立 spike 脚本对照 YOLO 与 MediaPipe，产出核心指标降级清单与预注册阈值的 go/no-go 结论（#2）。

### 修改内容

- 配置实验环境：新建 `.venv`（Python 3.13.9），按 `requirements.txt` 安装 mediapipe/opencv/numpy/pillow；
  另装 ultralytics 8.4.57 + torch 2.12.0+cpu（CPU 推理），下载 `models/yolo11n-pose.pt`。
- 新增 `analysis/spike_yolo_baseline.py`：独立 spike 脚本，**不接主链路、不改主代码**。
  跑 YOLO 与 MediaPipe 同样本对照，导出 FPS、漏检率、关键点抖动、跨后端 body_core 位置差、多人帧统计；
  COCO17→BlazePose33 映射严格遵循迁移计划，缺失点一律 `valid=False`，不伪造。
- 新增 `docs/yolo_eval_samples.json`：6 段基线样本（正面/侧面/长视频/学员边界），仅登记元信息，视频本体不入库。
- 新增 `docs/yolo_baseline_report.md`：S0 决策基线报告。含许可结论（可用-限内部研发/评估）、环境表、
  预注册阈值表（建议值，待业务确认）、实测结果、核心指标降级清单、go/no-go 结论（有条件 GO，进入 S1）。
- 新增 `requirements-spike.txt`：记录 spike 专用依赖（ultralytics/torch/torchvision）。
- 更新 `.gitignore`：新增 `models/*.pt`、`models/*.onnx`、`vision_old/`、`_pip_*.log`。

### 关键结论

- 许可：AGPL-3.0 下内部研发/评估可用；闭源/商业部署须采购 Enterprise（决策推到 S6）。
- FPS：本 CPU 上 YOLO11n-pose（25.5fps 均值）比 MediaPipe full（62.8fps 均值）慢约 2.5×，"提速"动机不成立。
- 多人风险已实证：学员样本最多检出 8 人、单视频 274 帧多人 → S2 多人闸门为必做正确性项。
- 核心降级：重心（支撑面/分段质心）+ 发力顺序（蹬地/脚旋转）依赖脚跟脚尖，COCO17 结构性失效，
  YOLO-only 默认排除 full tech_eval，定位收敛为预览/模板匹配/skip-aware partial eval。
- go/no-go：**有条件 GO**，进入 S1（S1 工作无论 YOLO 成败都有价值），但严格限定 YOLO 定位。

### 验证方法

- `.\.venv\Scripts\python.exe -m py_compile .\analysis\spike_yolo_baseline.py` 通过。
- `.\.venv\Scripts\python.exe -m analysis.spike_yolo_baseline --samples docs/yolo_eval_samples.json --yolo-model models/yolo11n-pose.pt --pose-variant full --out outputs/spike` 跑通，
  产出 `outputs/spike/spike_baseline.json` 与 `.csv`（6 段样本全部成功，无报错）。

---

## 2026-05-30: PR #13 审查补强 - spike 原始 keypoints 与 track_id 导出

### 问题描述

审查 PR #13 时发现 Issue #2 清单要求 spike 导出 YOLO keypoints 与 `track_id`，原实现只保留汇总指标，
缺少逐帧原始 keypoints/选中目标 ID，后续 S3 标定与审计难以复核。

### 修改内容

- 更新 `analysis/spike_yolo_baseline.py`：默认写出 `outputs/spike/spike_keypoints.jsonl`，逐帧记录
  MediaPipe / YOLO 的 Pose33-like keypoints、`valid_mask`、YOLO `person_count`、选中实例索引、归一化 bbox 与 `track_id`。
- 新增 spike-only 简易目标 ID 策略（最大框 + IoU/中心距离），仅用于 S0 数据审计；生产多人闸门仍归 S2。
- 更新 `docs/yolo_baseline_report.md`，补充 keypoints JSONL 输出与 `track_id` 策略说明。

### 验证方法

- `e:\CodeProject\vision\.venv\Scripts\python.exe -m py_compile .\analysis\spike_yolo_baseline.py`
- `e:\CodeProject\vision\.venv\Scripts\python.exe -m analysis.spike_yolo_baseline --help`

---

## 2026-05-30: YOLO 迁移 S1 起点（Issue #3：pose33_v3 golden 回归基线，安全网先行）

### 问题描述

S1 后续 Issue（#4 layout shape 参数化 + 周期裁切修复、#5 valid_mask 契约迁移）会改动
`_extract_pose_features()` 缺帧补零、`mirror_pose_features()`、`_select_representative_cycle()`、
双模板关节误差统计、`tech_eval._valid` / `rule_scoring._valid_frame` 等热路径。
`py_compile` 对“行为不变”零保证，必须在动这些代码前先把 pose33_v3 默认路径的现状冻结成
golden，作为重构“行为不变”的唯一硬门槛。

### 修改内容

- **测试框架（方案 A，pytest）落地**：新增 `requirements-dev.txt`（`pytest==8.4.2`）。
  后续所有 Issue 的新增测试统一沿用 pytest 风格，验收命令
  `.\.venv\Scripts\python.exe -m pytest tests\xxx.py`。
- **确定性回放 harness**：新增 `tests/golden_harness.py`，把 `cv2.VideoCapture` 与
  `MediaPipePipeline` 替换为读取已保存 `(T,33,4)` landmark 序列的假对象。所有上层入口
  （`compare_video_to_template` / `compare_video_to_dual_templates` / `evaluate_video_full`
  / `extract_pose_raw` / `score_rules` / `extract_pose_and_view_scores`）都走真实代码路径，
  但输入确定，golden 只反映本仓库代码行为，不受 MediaPipe 模型版本影响。
- **fixture 入库**：`tests/fixtures/pose33_v3/` 下提交小体积确定性数据——
  `front_src_raw.npz` / `side_src_raw.npz` / `student_raw.npz`（裁剪自本地骨架序列，
  约 170KB），以及由其生成的 `front_template.npz` / `side_template.npz` / `golden.json`。
  - `tests/fixtures/_build_raw_fixtures.py`：从本地（gitignored）`outputs/` 裁剪 raw fixture，
    仅在源样本/裁剪范围有意调整时运行。
  - `tests/fixtures/regen_pose33_v3_golden.py`：用已提交 raw fixture 重生成模板与 golden，
    仅在“有意变更行为”且确认正确后运行。
- **golden 回归测试**：新增 `tests/test_pose33_v3_golden.py`（16 个用例），覆盖三类输出：
  1. 单模板 `compare_video_to_template` 分数；
  2. 双模板 `compare_video_to_dual_templates` 的 `combined_percent` + 各视角分（含规则扣分
     明细、关节误差统计，关节顺序敏感以冻结 mirror 的 L/R 交换）；
  3. `tech_eval` 各指标 `status` + 关键 `detail`。
  数值断言用 `pytest.approx(abs=1e-4)`，状态/分类/整数（percent、rule_score、segment、
  primary_cause 等）用精确相等。
- **.gitignore**：补 `core/models/*.task`，避免误提交本地模型权重。

### 验证方法

- `.\.venv\Scripts\python.exe -m pytest tests\test_pose33_v3_golden.py` → 16 passed（未改动代码全绿）。
- 安全网有效性自检：临时在 `mirror_pose_features()` 注入 `+0.001` 扰动 → `test_dual_joint_errors[side]`
  如期失败；还原后重新全绿，证明 golden 能捕获热路径漂移。
- `git check-ignore` 确认 fixtures/golden/模板均不被忽略、会随提交入库；`core/models/*.task` 已被忽略。

---

## 2026-05-30: YOLO 迁移 S1（Issue #4：FeatureLayoutSpec 注册表 + layout shape 参数化 + 周期裁切修复）

### 问题描述

S1 热路径里把 `(22, 2)` / 22 点配对硬编码散落在多处：`_extract_pose_features()` 缺帧补零、
`mirror_pose_features()` 的 L/R 配对、双模板关节误差统计的关节名表。更危险的是
`core/action_compare.py` 的 `_select_representative_cycle()` 守卫写死
`if features.shape[1:] != (22, 2): return features`——任意非 22 点布局会**静默跳过周期裁切**，
DTW query 退化成整段模板，不报错、最难查。本 Issue 把这些 shape 魔法值收敛到显式 layout 注册，
**只做参数化、默认仍走 22 点路径**，不引入 `body_core_v1`（下移 #8）。

### 修改内容

- **新增 `core/feature_layout.py`**：`FeatureLayoutSpec` dataclass
  （`name`/`source_indices`/`shape`/`mirror_pairs`/`joint_names`/`default_baseline`）+ 注册表
  （`register_layout`/`get_layout`/`has_layout`/`resolve_layout_by_shape`/`is_valid_feature_shape`）。
  - **本期只注册生产用 `pose33_v3`**（BlazePose 11..32 → 22 点，mirror_pairs 即相邻对
    (0,1)…(20,21)，joint_names 与原 `joint_names_11_32` 完全一致，baseline=2.0）。
  - **不注册 `body_core_v1`**（留到 #8 真有消费者时），**不引入 `required_landmarks`** 字段
    （S4 才消费，避免提前建模）。
- **`core/pose_features.py::mirror_pose_features()`**：新增可选 `layout` 形参，按 layout 的
  `mirror_pairs` 做 L/R 互换，去掉写死的 `range(0, 22, 2)`。未传 layout 时按单帧 shape 反查
  唯一已注册布局（`(22,2)` 即命中 `pose33_v3`，行为不变）；无法解析时报清晰错误，不静默按 22 点处理。
- **`core/action_compare.py::_extract_pose_features()`**：新增 `layout=POSE33_V3` 形参，
  缺帧补零（单线程 / 多线程 / `feat_arr` 预分配）全部按 `layout.shape` 生成，去掉三处
  `np.zeros((22, 2))` 与一处 `np.zeros((total, 22, 2))` 字面量；单线程回退递归透传 layout。
- **`_select_representative_cycle()` 守卫泛化**：改为
  `if features.ndim != 3 or not is_valid_feature_shape(features.shape[1:]): return features`，
  按 `(J, 2)` 合法布局（`J >= 4`）判定，使任意 `(T, J, 2)` 输入都能正常裁切，修复静默退化 bug。
- **双模板关节误差统计**：删除写死的 `joint_names_11_32` 列表与 `range(22)`/`raw[..., 11:33, 3]`，
  改从 `POSE33_V3` 取 `joint_names`/`source_indices`/`num_joints`，行为不变。
- **layout mismatch 显式校验**：单模板 / 双模板进入 DTW 前先核对单帧 feature shape，shape 不一致时
  抛出包含模板路径、视频路径、metadata `feature_layout` 与实际 shape 的 `ValueError`，避免不同 layout
  静默比对或落入低层 numpy 广播异常。
- **新增测试**：
  - `tests/test_layout_shape_param.py`：断言注册表范围（仅 pose33_v3、无 body_core_v1、无
    required_landmarks）、mirror 与旧实现逐位等价、缺帧补零按 layout shape、无法解析 shape 报错、
    不同 layout/shape 比对会清晰报错，并用 AST 静态扫描确认 `action_compare`/`pose_features` 热路径
    不再出现 `(22,2)` 字面量或 `range(...,22,...)` 魔法值（注册定义里的 `(22,2)` 合法）。
  - `tests/test_representative_cycle_layout.py`：用 test-only `(T,12,2)` 强周期输入验证周期裁切
    不再静默整段返回、能正常裁短；并覆盖 22 点、短序列、非法 shape、关节数过少等边界。

### 验证方法

- `.\.venv\Scripts\python.exe -m py_compile`（13 个目标文件 + `core/feature_layout.py`）→ 全通过。
- `.\.venv\Scripts\python.exe -m pytest tests\test_pose33_v3_golden.py` → 16 passed（**默认行为不变**，硬门槛）。
- `.\.venv\Scripts\python.exe -m pytest tests\` → 34 passed（含两个新增测试文件）。
- 全程对照 Issue #4 验收标准逐条核对：golden 全绿、layout shape 参数化、周期裁切修复、py_compile 通过、change.md 已记录。

## 2026-06-08: UI 控制区分隔与 Secondary_Options 分组（ui-layout-redesign 任务 9.3）

### 问题描述

任务 9.2 在 `apps/app_ui.py` 的 `_build_ui` 中建立了 Primary_Controls（"主要操作"）分组，
但次要选项仍暂留于旧的"选项"（opts）卡片，主/次分区无显式视觉分隔，且
`recording_status_var`（录制状态/路径文本）尚无对应控件展示。需求 1.2/1.4/7.x。

### 修改内容

- 在 Primary_Controls 之后插入显式水平分隔线 `ttk.Separator(orient="horizontal")`，
  存为 `self.primary_secondary_separator` 供布局测试定位（需求 1.2）。
- 新建 `ttk.Labelframe(text="次要选项")` 分组，置于分隔线之后、Compare_Control 之下，
  迁移（非复制）原"选项"卡片中的全部次要控件：选择视频…/输入源提示、离线线程数
  Spinbox（`self.workers_spin`）、启用手部检测 Checkbutton、导出结果视频 Checkbutton +
  保存位置行（`self.out_entry`/`self.out_btn`）、直拳检测…（需求 1.4/7.1/7.2/7.3/7.4）。
- 移除旧的"选项"（opts）Labelframe，控件均迁移无重复、无遗漏。
- Status_Area（"状态" info）保留在控制区底部，新增绑定 `self.recording_status_var`
  的 Label（紧邻 status_var）以展示录制状态/路径（需求 5.9/5.10 surfacing）；
  保留识别结果、进度文本、`self.progress_bar`（需求 7.6/7.7/7.8）。

### 验证方法

```powershell
.\.venv\Scripts\python.exe -m py_compile .\apps\app_ui.py
```
退出码 0，编译通过。

## 2026-06-08: UI 布局重构 - 任务 9.3（添加可见分隔并构建 Secondary_Options 分组）

### 问题描述

`ui-layout-redesign` spec 任务 9.3：在 `apps/app_ui.py` 的 `App._build_ui` 中，
显式强化主/次操作分区——在 Primary_Controls 与次要选项之间插入可见水平分隔线，
并将原 “选项” 分组规范为 “次要选项”（Secondary_Options），统一置于 Compare_Control 之后；
Status_Area 固定保留在控制区底部，并补充录制状态/路径显示控件。

### 修改内容（`apps/app_ui.py` `_build_ui`，父容器 `self.controls_inner` = `left`）

- 在 Primary_Controls（“主要操作” Labelframe）之后插入可见水平分隔：
  `self.primary_secondary_separator = ttk.Separator(left, orient="horizontal")`，
  `pack(fill="x", pady=8)`，供布局测试定位。
- 新建 Secondary_Options 分组 `ttk.Labelframe(left, text="次要选项")`，置于分隔线之后，含：
  选择视频…（`_browse_video`，7.1）+ 输入源提示（`source_hint_var`）、离线线程数
  `self.workers_spin`（from_=1 to=16，7.2）、启用手部检测 Checkbutton（`enable_hands_var`，7.3）、
  导出结果视频 Checkbutton（`save_var` + `_toggle_out`）及 `self.out_entry`/`self.out_btn` 行、
  直拳检测…（`_open_tech_eval`，7.4）。属性名保持不变，未重复或遗失控件。
- Status_Area（“状态” Labelframe）固定于控制区底部，含 status_var、识别结果 actions_var、
  progress_text_var、`self.progress_bar`（7.6/7.7/7.8）；并在 status_var 之后新增绑定
  `self.recording_status_var` 的 Label，用于显示录制状态/Result_Video 路径（需求 5.9/5.10）。

控制区自上而下结构：主要操作（Primary_Controls）→ 可见水平分隔线 → 次要选项
（Secondary_Options）→ 状态（Status_Area）。

### 验证方法

```powershell
.\.venv\Scripts\python.exe -m py_compile .\apps\app_ui.py   # 退出码 0
```

## 2026-06-08: UI 布局重组与录制/暂停运行时控制（ui-layout-redesign 全量完成）

### 问题描述

`apps/app_ui.py` 的桌面 UI 将控件分散在「输入/选项/运行/状态」四张卡片中，主次不分、布局凌乱；
且录制只能在启动前预先勾选导出，无法在识别会话运行期间按需开始/暂停。spec 见
`.kiro/specs/ui-layout-redesign/`（requirements / design / tasks）。本次实现两条主线：
与 Tkinter 解耦的录制状态机 `RecordingController`，以及左侧控制区的可滚动重组（主/次分组）。

### 修改内容

- 新增 `core/recording_controller.py`（与 tkinter 解耦、可独立属性测试）：
  - `RecordingState` / `WriterFactory` 类型别名、`RecordingSnapshot` 不可变快照、`VideoWriterLike` 协议。
  - `RecordingController`：`begin_session` / `request_toggle`（idle→recording→paused→recording 循环）/
    `write_frame`（仅 recording 写盘 + 首帧懒创建 + 错误收敛复位）/ `close_session`（无条件释放复位）/
    `snapshot`；单把 `threading.Lock` 串行化所有状态/写盘操作；默认 writer 工厂绑定
    `open_video_writer`，默认路径 `outputs_dir()/record_<timestamp>.mp4`。
- 改造 `apps/app_ui.py`：
  - `App.__init__` 创建 `self._rec = RecordingController()`；新增 `recording_status_var`、`_record_error_shown`。
  - `_worker_loop` / `_worker_loop_parallel_video`：去除内联 `cv2.VideoWriter` 逻辑，改为 `begin_session` +
    `write_frame` + `finally: close_session`，录制不再依赖 `UiState.save_output/out_path`。
  - 新增 `_on_record_toggle`（三态按钮文本映射 `RECORD_BTN_TEXT`）、`_refresh_recording_status`（由 `_tick`
    每 tick 调用，刷新状态/路径文本，错误弹框并复位）、`_set_running_controls`（运行态控件 enable/disable 联动）。
  - `clamp_workers(n)` 将离线线程数钳制到 `[1, os.cpu_count()]`，在 Spinbox 读取处复用。
  - `_build_ui` 重构：左侧改为 `Canvas + Scrollbar + inner` 可滚动容器，`root.minsize(800, 600)`；
    Primary_Controls 分组（摄像头→模型→开始→录制/暂停→动作比对，固定顺序）+ 可见 `ttk.Separator` +
    Secondary_Options 分组（选择视频/离线线程数/手部检测/直拳检测）+ 底部 Status_Area。
  - 错误处理：无输入源弹「请先选择摄像头或视频」、无效视频拒绝并保留先前选择、比对窗口创建失败 try/except 弹框。
- 新增测试：`tests/test_recording_controller.py`（Property 1–6 + 夹具/引用模型）、`tests/test_clamp_workers.py`
  （Property 7）、`tests/test_app_controls.py`（按钮文本映射与控件联动）、`tests/test_layout_structure.py`
  （布局结构断言）、`tests/test_error_handling.py`（错误处理场景）。

### 验证方法

- 编译检查：`.\.venv\Scripts\python.exe -m py_compile .\apps\main.py .\apps\app_ui.py .\core\recording_controller.py`（通过）。
- 全量测试：`.\.venv\Scripts\python.exe -m pytest tests/test_recording_controller.py tests/test_clamp_workers.py tests/test_app_controls.py tests/test_layout_structure.py tests/test_error_handling.py -q`
  → 27 passed, 1 skipped（布局测试在无显示环境下跳过）。
- 真实窗口的最小尺寸/滚动/端到端预览与录制写盘为冒烟/人工验证项。

## 2026-06-10: Vue/Tauri 前端 dev 启动链路修复

### 问题描述

Vue/Tauri 窗口可编译启动，但首次 mounted 自动刷新会遇到 Tauri v2 事件权限缺失、
debug 模式误用旧打包 sidecar、Python bridge 导入路径/Windows stdout 编码不稳定等问题，
导致前端可能走 mock fallback 或出现 `event.listen not allowed` / `bridge response timeout`。

### 修改内容

- 新增 `frontend/src-tauri/capabilities/default.json`，为主窗口声明 `core:default`、
  `core:event:default` 与 `core:event:allow-listen`。
- `frontend/src/bridge.ts` 改用 `@tauri-apps/api/core` 的 `isTauri()` 判断真实 Tauri 运行时。
- `frontend/src-tauri/src/lib.rs`：
  - debug 构建下优先使用源码 bridge，避免 dev 模式误用旧 PyInstaller sidecar；
  - 启动 Python bridge 时注入 `PYTHONPATH`、`PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8`，
    保证 `apps.ui_backend` 可导入且中文 JSON 响应按 UTF-8 进入 Rust reader。

### 验证方法

- `npm --prefix frontend run build`：通过。
- `cargo check`（`frontend/src-tauri`）：通过。
- `npm --prefix frontend run tauri dev`：已启动，窗口标题为 `Vision 动作识别与评分`。
- mounted 自动刷新后日志未再出现 `not allowed`、`Unhandled`、`bridge response timeout`；
  真实 Python bridge 进程由 Tauri 窗口拉起：`.venv\Scripts\python.exe -u apps\ui_backend.py`。

## 2026-06-11: Vue/Tauri 高速帧通道与 MediaPipe/YOLO 后端路由 Spce 规范

### 问题描述

基于新的架构讨论，需要先按 Spce workflow 生成可审查规范，而不是直接进入实现。讨论结论涉及
Vue 前端、Tauri/Rust 桌面壳、Python MediaPipe 后端、YOLO body-only 后端、二进制预览帧通道、
模型分档、任务取消状态机、打包安装和评分授权边界，是跨模块高风险改造。

### 修改内容

- 新建 Design-First 规范主文档：
  - `docs/specs/design.md`：固化四层职责、后端路由规则、JSON bridge 与二进制 latest-frame
    通道边界、MediaPipe/full tech_eval 可信路径、YOLO body-only 能力标识、sidecar 打包风险和
    三阶段演进路线。
  - `docs/specs/requirements.md`：从设计派生 REQ-001 至 REQ-008、AC-001.1 至 AC-008.3、
    NFR-001 至 NFR-006，并记录 Analyze Requirements 结论。
  - `docs/specs/tasks.md`：拆分 10 个受控任务，覆盖路由契约、YOLO 元数据、模型清单、
    二进制帧通道、Canvas 渲染、状态机、YOLO26n/s、YOLO26L、MediaPipe 回归门和打包收口。
- 通过 Spce 工具生成并同步：
  - `docs/specs/progress.md`
  - `docs/specs/spec.yml`
- 子 agent 只读审查补充的关键边界已写入规范：
  - 安装版 sidecar 当前排除 `torch`、`ultralytics`、`core.yolo_adapter`，若安装版支持 YOLO
    必须同步调整依赖和验证。
  - YOLO raw adapter 的 Pose33-like 容器不等同于 `pose33_v3`，需区分 `rawLayout` 与
    `featureLayout=body_core_v1`。
  - Python snake_case 与前端 camelCase 字段必须保持一一映射。
- 按用户要求开启 5 个只读 agent 分别审查 `design.md`、`requirements.md`、`tasks.md`、
  `progress.md`、`spec.yml`，并完成审查后文档修正：
  - `design.md`：统一 YOLO `scoreAuthorized=false` 为布尔授权字段，受限展示改用
    `displayScope` / `evalScope` / `internalUseOnly`；明确 MediaPipe 与 YOLO 预览帧都走二进制
    latest-frame 通道；路由输出补齐 `rawLayout`、`featureLayout`、`calibrationStatus`。
  - `requirements.md`：区分前端/JSON camelCase 与 Python artifact snake_case；补齐
    `calibrationStatus=unvalidated`、正式评分 / full tech_eval / 必需关键点的 MediaPipe 边界，
    并阻断 `displayScope=limited` 进入正式报告或 pass/fail 判定。
  - `tasks.md`：将验证命令改为分步 fail-fast；修正 T-007/T-009 依赖与执行 waves；补齐
    `AC-001.2`、`AC-008.2`、`AC-008.3` 覆盖字段；把 YOLO landmark mapping 回归纳入 T-002/T-010。
  - `progress.md` / `spec.yml`：记录 approval=pending、等待 `批准规范，启动执行`、dirty worktree
    保护说明和五 agent 审查结论，并刷新 Kiro 兼容索引。

### 验证方法

- `.\.venv\Scripts\python.exe C:\Users\ny\.codex\plugins\cache\Useful-marketplace\spce-workflow\0.2.0\scripts\validate_spec.py docs/specs/ --workflow design-first --color never`
  → 36 项检查全部通过。
- `.\.venv\Scripts\python.exe C:\Users\ny\.codex\plugins\cache\Useful-marketplace\spce-workflow\0.2.0\scripts\validate_spec.py docs/specs/ --resume --color never`
  → `status=ready`，`current_task=T-001`，`next_executable=["T-001"]`，无 issues/warnings。
- `.\.venv\Scripts\python.exe C:\Users\ny\.codex\plugins\cache\Useful-marketplace\spce-workflow\0.2.0\scripts\validate_spec.py docs/specs/ --sync-check --color never`
  → 无 issues/suggestions。

## 2026-06-11: 补强高速帧通道与 MediaPipe/YOLO 路由 Spce 审查问题

### 问题描述

批准前复审继续指出当前 Spce 文档仍存在若干路由、职责、验证和性能边界不够硬的问题：
`enableHands=false` 与手指指标冲突未定、路由器落点未固定、batch 后端选择逻辑可能分叉、
YOLO 可用/不可用路径断言偏弱、实时多人预览未定义、模型管理职责写得过宽、二进制通道方案
留到实现期才收敛、`displayScope` 等授权字段仍存在“等价字段”空间，以及 T-004/T-009 验证边界不够清晰。

### 修改内容

- `docs/specs/design.md`：
  - 明确采用 `enableHands=false` 开关优先：不得静默启用 hand landmarker；含手指指标时走
    MediaPipe pose-only partial，结果标注 `skippedCapabilities`、`evalCompleteness=partial` 和原因。
  - 固定新增 `core/backend_router.py` 作为唯一后端路由决策点；`apps/ui_backend.py` 与
    `batch/backend_options.py` 只能调用共享 router，batch 不得反向 import `apps`。
  - 收敛受限显示字段为单一 `displayScope=limited|internal`，移除 `evalScope` /
    `internalUseOnly` / “等价字段”空间。
  - 定死二进制帧通道首选方案为 Python→Rust Windows 命名管道 + Rust→Vue Tauri 自定义协议，
    回退方案为 latest-frame 原子文件 + Tauri 自定义协议。
  - 补齐 YOLO 实时多人预览策略、模型不可用回退、Rust/Python 模型职责边界、Tkinter 旧入口不在范围、
    性能与内存基线阈值。
- `docs/specs/requirements.md`：
  - 将 AC-002.2 / AC-002.3 从“可以选择 YOLO”改为“模型可用时必须选择 YOLO26n/s 或 YOLO26L”。
  - 新增 AC-002.6、AC-002.7、AC-002.8，覆盖手指指标 partial、YOLO 模型不可用回退和实时多人预览。
  - 新增 AC-003.6，要求 UI bridge、batch CLI 和离线分析统一调用 `core/backend_router.py`。
  - 新增 AC-004.3、AC-005.3，覆盖性能基线、payload 阈值、内存增长、Canvas/bitmap 迁移行为证明。
  - 修正 AC-001.1 中 Rust/Python 模型职责：Rust 管资源路径和打包，Python 管清单与下载执行。
- `docs/specs/tasks.md`：
  - T-001 增加 `core/backend_router.py` 和 batch 适配，覆盖新增路由 AC。
  - T-003 改为串行任务，补代理/离线安装提示和模型不可用回退要求。
  - T-004 增加 `npm run verify:tauri` 与前端 smoke，工程量调整为 8-12 小时。
  - T-007/T-008 增加模型不可用回退、多人预览和 `displayScope` 验证。
  - T-009 明确为回归门为主，仅在发现 YOLO 可进入正式评分/full tech_eval 时增加阻断守卫。
  - 执行规则新增每任务完成必须同步 `change.md`。
- `docs/specs/progress.md` / `docs/specs/spec.yml`：
  - 记录本轮批准前补强决策，并刷新 Kiro 兼容索引、requirements 列表和 artifact hash。

### 验证方法

- `.\.venv\Scripts\python.exe C:\Users\ny\.codex\plugins\cache\Useful-marketplace\spce-workflow\0.2.0\scripts\validate_spec.py docs/specs/ --workflow design-first --color never`
  → 36 项检查全部通过。
- `.\.venv\Scripts\python.exe C:\Users\ny\.codex\plugins\cache\Useful-marketplace\spce-workflow\0.2.0\scripts\validate_spec.py docs/specs/ --resume --color never`
  → `status=ready`，`current_task=T-001`，`next_executable=["T-001"]`，无 issues/warnings。
- `.\.venv\Scripts\python.exe C:\Users\ny\.codex\plugins\cache\Useful-marketplace\spce-workflow\0.2.0\scripts\validate_spec.py docs/specs/ --sync-check --color never`
  → 无 issues/suggestions。
