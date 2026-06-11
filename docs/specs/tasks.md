# Design-First 任务清单 (Task Breakdown)

> **功能名称:** Vue/Tauri 高速帧通道与 MediaPipe/YOLO 后端路由架构
> **关联规范:** `docs/specs/design.md` · `docs/specs/requirements.md`
> **状态:** In Progress
> **当前任务:** T-009
> **进度:** 8 / 10 已完成
> **最后更新:** 2026-06-11 15:48:36

---

## 执行规则

1. **设计优先：** 任务必须首先满足 `design.md` 中已批准的约束与边界。
2. **受控入口：** 任务开始、完成、阻塞、跳过必须通过 `spec_progress.py` CLI 或 MCP 工具更新；工具会同步顶部状态、当前任务、进度和完成日志。
3. **需求从设计派生：** 若 `requirements.md` 与 `design.md` 冲突，必须暂停实现、更新文档、运行 sync-check 并重新获得批准。
4. **单任务约束：** 每个任务完成后必须记录验证证据，才可标记为完成。
5. **禁止越界：** 不得实现未在 `design.md` 明确支撑的能力。
6. **任务日志：** 每个任务完成时必须同步更新根目录 `change.md`，记录修改日期、问题描述、修改内容和验证方法。
7. **验收修复隔离：** final acceptance 发现的问题不得追加到本文件；修复项必须写入 `docs/specs/acceptance-fixes.md`。

---

## 阶段 1：契约与路由基础

- [x] **T-001:** 固化后端路由决策契约
  - 状态: done
  - 验证证据: cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_backend_routing_contract.py tests/test_ui_backend_contract.py tests/test_batch_backend_args.py -q => exit 0, 35 passed; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py -q => exit 0, 31 passed; cmd: git diff --check => exit 0 (line-ending warnings only)
  - 完成时间: 2026-06-11 13:58:19
  - 备注: 新增 core/backend_router.py 唯一路由决策点；UI bridge 和 batch helper 消费共享 router；更新 change.md。
  - 涉及文件: `core/backend_router.py`, `batch/backend_options.py`, `apps/ui_backend.py`, `core/feature_layout.py`, `core/yolo_adapter.py`, `tests/test_backend_routing_contract.py`, `tests/test_ui_backend_contract.py`, `tests/test_batch_backend_args.py`
  - 验证命令: `.\.venv\Scripts\python.exe -m pytest tests/test_backend_routing_contract.py tests/test_ui_backend_contract.py tests/test_batch_backend_args.py -q`
  - 依赖: 无
  - 风险: high
  - 覆盖: REQ-001, REQ-002, REQ-003, AC-001.1, AC-001.2, AC-002.1, AC-002.2, AC-002.3, AC-002.4, AC-002.5, AC-002.6, AC-002.7, AC-002.8, AC-003.1, AC-003.6
  - 可并行: 否
  - 验证标准: 新增 `core/backend_router.py` 作为唯一决策点；`apps/ui_backend.py` 和 `batch/backend_options.py` 只能调用共享 router，不得复制规则；路由函数不能只依赖 `enableHands`；`enableHands=false` + 手指指标必须走 MediaPipe pose-only partial 并标 `skippedCapabilities=fingers`，不得静默启用 hand landmarker；YOLO realtime 模型不可用时必须回退 MediaPipe 并记录 `fallbackReason/requestedBackend`；YOLO26L 离线高质量 body-only 模型不可用时必须返回结构化下载/安装错误，不静默回退；YOLO 路由必须输出 backend、modelProfile、rawLayout、featureLayout、capabilities、requiresCapabilities、calibrationStatus、布尔 scoreAuthorized、displayScope、evalCompleteness、reason。
  - 预估工程量: 4-6 小时

- [x] **T-002:** 补齐 YOLO 能力和评分授权元数据
  - 状态: done
  - 验证证据: cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_yolo_backend_contract.py tests/test_yolo_landmark_mapping.py tests/test_rule_availability.py tests/test_ui_backend_analysis.py -q => exit 0, 46 passed; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py -q => exit 0, 31 passed; cmd: git diff --check => exit 0 (line-ending warnings only)
  - 完成时间: 2026-06-11 14:12:26
  - 备注: YOLO adapter 边界层与序列 artifact 统一补齐 raw_layout/feature_layout/capability/score_authorized/display_scope；UI camelCase route 与 COCO17 missing capability 测试上锁；更新 change.md。
  - 涉及文件: `core/yolo_adapter.py`, `batch/batch_dual_compare.py`, `batch/batch_tech_eval.py`, `apps/ui_backend.py`, `tests/test_yolo_backend_contract.py`, `tests/test_rule_availability.py`, `tests/test_ui_backend_analysis.py`
  - 验证命令: `.\.venv\Scripts\python.exe -m pytest tests/test_yolo_backend_contract.py tests/test_yolo_landmark_mapping.py tests/test_rule_availability.py tests/test_ui_backend_analysis.py -q`
  - 依赖: T-001
  - 风险: high
  - 覆盖: REQ-003, AC-003.1, AC-003.2, AC-003.3, AC-003.4, AC-003.5, AC-003.6, NFR-003
  - 可并行: 否
  - 验证标准: 任意 YOLO payload/artifact 均显式标识 `backend=yolo`、raw layout、`featureLayout=body_core_v1`、`capability=body_only`、`calibrationStatus=unvalidated`、布尔 `scoreAuthorized=false`；受限显示只使用 `displayScope=limited|internal` / `display_scope=limited|internal`，不得引入等价字段；Python snake_case 与前端 camelCase 字段一一映射；缺失点继续通过 `valid_mask=False` 和 missing capability 呈现。
  - 预估工程量: 2-4 小时

- [x] **T-003:** 建立模型档清单与配置状态
  - 状态: done
  - 验证证据: cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_ui_backend_models.py tests/test_windows_packaging_smoke.py -q => exit 0, 20 passed; cmd: npm --prefix frontend run test => exit 0, Frontend behavior smoke checks passed; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py -q => exit 0, 31 passed; cmd: git diff --check => exit 0 (line-ending warnings only)
  - 完成时间: 2026-06-11 15:13:21
  - 备注: 补齐 MediaPipe/YOLO26 模型档元数据、默认代理下载、YOLO 手动安装错误、安装版 sidecar YOLO runtime 排除边界和前端展示；更新 change.md。
  - 涉及文件: `apps/ui_backend.py`, `core/model_manager.py`, `ui_backend_sidecar.spec`, `frontend/src/App.vue`, `frontend/src/bridge-state.ts`, `tests/test_ui_backend_models.py`, `tests/test_windows_packaging_smoke.py`, `frontend/scripts/frontend-smoke.mjs`
  - 验证命令: 分步运行 `.\.venv\Scripts\python.exe -m pytest tests/test_ui_backend_models.py tests/test_windows_packaging_smoke.py -q` 和 `npm --prefix frontend run test`，每步必须退出码 0
  - 依赖: T-001
  - 风险: medium
  - 覆盖: REQ-007, AC-007.1, AC-007.2, AC-007.3
  - 可并行: 否
  - 验证标准: Python 侧负责模型清单、下载执行和代理/离线提示；开发侧模型下载走 `http://127.0.0.1:7890` 代理，安装版用户侧需处理下载源不可达提示；Rust 侧只负责资源路径、sidecar 打包和安装版资源发现；模型状态区分 MediaPipe pose full/heavy + hands、YOLO26n/s、YOLO26L、YOLO26X；YOLO26X 不进入默认路由；YOLO realtime 模型不可用时 router 能产生可见回退/下载提示，YOLO26L 缺失时能产生结构化下载/安装错误；安装版是否支持 YOLO 与 sidecar 依赖策略一致；下载/取消事件仍保持现有 envelope 契约。
  - 预估工程量: 2-3 小时

---

## 阶段 2：高速帧通道和前端渲染

- [x] **T-004:** 设计并实现二进制 latest-frame 预览帧通道
  - 状态: done
  - 验证证据: cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_ui_backend_sessions.py tests/test_windows_packaging_smoke.py -q => exit 0, 16 passed; cmd: npm run verify:tauri => exit 0, cargo check passed; cmd: npm --prefix frontend run test => exit 0, Frontend behavior smoke checks passed; cmd: git diff --check => exit 0 (line-ending warnings only)
  - 完成时间: 2026-06-11 14:35:56
  - 备注: 实现 Python 127.0.0.1 TCP length-prefixed latest-frame 通道与 Tauri raw IPC latest_frame；session.frame JSON 不再携带 image/base64/bytes，仅传 frame handle、token 和指标；更新 change.md 基线记录。
  - 涉及文件: `frontend/src-tauri/src/lib.rs`, `apps/ui_backend.py`, `tests/test_ui_backend_sessions.py`, `tests/test_windows_packaging_smoke.py`, `frontend/scripts/frontend-smoke.mjs`
  - 验证命令: 分步运行 `.\.venv\Scripts\python.exe -m pytest tests/test_ui_backend_sessions.py tests/test_windows_packaging_smoke.py -q`、`npm run verify:tauri` 和 `npm --prefix frontend run test`，每步必须退出码 0
  - 依赖: T-001
  - 风险: high
  - 覆盖: REQ-004, AC-004.1, AC-004.2, AC-004.3, NFR-001, NFR-006
  - 可并行: 否
  - 验证标准: 首选实现为 Python->Rust 仅绑定 `127.0.0.1` 的 TCP 长度前缀帧流（随机端口 + 会话 token 经 JSON bridge 握手下发）+ Rust->Vue Tauri 2 raw IPC `tauri::ipc::Response` 二进制 `ArrayBuffer`；Windows named pipe / Tauri custom protocol 仅作备选，切换原因必须写入任务证据和 `change.md`；禁止以 JSON/base64 回传大帧兜底；`session.frame` JSON event 不再携带大图 base64/bytes；同一 session 只保留最新帧并记录 dropped/rendered/payload/age 指标；迁移前后基线证据覆盖丢帧率、渲染帧率、前端内存增长、IPC payload 大小。
  - 预估工程量: 8-12 小时

- [x] **T-005:** 将 Vue 预览迁移到 Canvas/bitmap 渲染
  - 状态: done
  - 验证证据: cmd: npm --prefix frontend run test => exit 0, Frontend behavior smoke checks passed; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_vue_tauri_acceptance_gaps.py -q => exit 0, 7 passed; cmd: git diff --check => exit 0 (line-ending warnings only)
  - 完成时间: 2026-06-11 14:44:51
  - 备注: Vue 预览迁移到 Canvas/ImageBitmap；requestAnimationFrame 合并 latest frame；移除 previewImage、object URL 和 img 帧展示路径；更新 change.md 基线记录。
  - 涉及文件: `frontend/src/App.vue`, `frontend/src/bridge.ts`, `frontend/src/bridge-state.ts`, `frontend/scripts/frontend-smoke.mjs`, `tests/test_vue_tauri_acceptance_gaps.py`
  - 验证命令: 分步运行 `npm --prefix frontend run test` 和 `.\.venv\Scripts\python.exe -m pytest tests/test_vue_tauri_acceptance_gaps.py -q`，每步必须退出码 0
  - 依赖: T-004
  - 风险: high
  - 覆盖: REQ-005, AC-005.1, AC-005.2, AC-005.3, NFR-001, NFR-006
  - 可并行: 否
  - 验证标准: 前端不再用 `previewImage` 或等价 reactive 大图字符串保存每帧；Canvas/bitmap 只绘制最新帧；通过 `requestAnimationFrame` 节流拉取最新帧并经 `createImageBitmap` 绘制 canvas；session/job/frame id 可过滤晚到帧；frontend smoke 需证明 frame handle 不进入历史数组或 reactive 队列；任务证据和 `change.md` 需记录迁移前后丢帧率、渲染帧率、前端内存增长、IPC payload 大小。
  - 预估工程量: 4-6 小时

- [x] **T-006:** 打通 Rust/Python 双侧任务状态机和取消语义
  - 状态: done
  - 验证证据: cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_ui_backend_sessions.py tests/test_ui_backend_contract.py -q => exit 0, 24 passed; cmd: npm --prefix frontend run test => exit 0, Frontend behavior smoke checks passed; cmd: git diff --check => exit 0 (line-ending warnings only)
  - 完成时间: 2026-06-11 14:54:00
  - 备注: 统一 session/model download/analysis 主动停止和晚到事件清理；job.stop 缺失/未知 jobId 结构化错误测试；更新 change.md。
  - 涉及文件: `frontend/src-tauri/src/lib.rs`, `apps/ui_backend.py`, `frontend/src/bridge-state.ts`, `frontend/src/bridge-lifecycle.ts`, `tests/test_ui_backend_sessions.py`, `tests/test_ui_backend_contract.py`, `frontend/scripts/frontend-smoke.mjs`
  - 验证命令: 分步运行 `.\.venv\Scripts\python.exe -m pytest tests/test_ui_backend_sessions.py tests/test_ui_backend_contract.py -q` 和 `npm --prefix frontend run test`，每步必须退出码 0
  - 依赖: T-004
  - 风险: high
  - 覆盖: REQ-006, AC-006.1, AC-006.2, NFR-006
  - 可并行: 否
  - 验证标准: session、analysis、model download 的停止和晚到事件处理一致；sidecar 异常、decode error、timeout 都返回结构化错误；窗口卸载不留下活动任务。
  - 预估工程量: 3-5 小时

---

## 阶段 3：后端路径接入和阶段演进保护

- [x] **T-007:** 接入 YOLO26n/s 实时 body-only 预览路径
  - 状态: done
  - 验证证据: cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_backend_routing_contract.py tests/test_yolo_backend_contract.py -q => exit 0, 33 passed; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py -q => exit 0, 31 passed; cmd: git diff --check => exit 0 (line-ending warnings only)
  - 完成时间: 2026-06-11 15:28:06
  - 备注: 接入 YOLO26n/s realtime body-only preview pipeline；session.frame 透传 YOLO 授权/多人 meta；保持 MediaPipe 旧默认路径和正式评分边界；更新 change.md。
  - 涉及文件: `apps/ui_backend.py`, `core/backend_router.py`, `core/yolo_adapter.py`, `tests/test_backend_routing_contract.py`, `tests/test_yolo_backend_contract.py`
  - 验证命令: `.\.venv\Scripts\python.exe -m pytest tests/test_backend_routing_contract.py tests/test_yolo_backend_contract.py -q`
  - 依赖: T-002, T-003, T-004
  - 风险: high
  - 覆盖: REQ-002, REQ-003, AC-002.2, AC-002.7, AC-002.9, AC-003.1, NFR-003
  - 可并行: 否
  - 验证标准: 无手部实时预览在 YOLO26n/s 可用时必须选择 YOLO26n/s；模型不可用或安装版不支持时必须回退 MediaPipe 并输出 `fallbackReason/requestedBackend` 与 UI fallback 提示；实时多人时沿用 `core/yolo_adapter.py` 既有 `select_main_person` 最大框/最高分策略，只渲染 primary target，输出 `multiPersonDetected/personCount/reviewRequired/targetPolicy`；完整 track 延续/中心最近/tie-break 策略本期不做；需要手部或缺失关键点时回退 MediaPipe 或 partial，不得启用 YOLO。
  - 预估工程量: 4-6 小时

- [x] **T-008:** 接入 YOLO26L 离线高质量 body-only 分析路径
  - 状态: done
  - 验证证据: cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_body_core_layout.py tests/test_batch_backend_args.py tests/test_s3_calibration.py -q => exit 0, 40 passed; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py -q => exit 0, 31 passed; cmd: git diff --check => exit 0 (line-ending warnings only)
  - 完成时间: 2026-06-11 15:48:36
  - 备注: 接入 analysis.run YOLO26L high_quality body-only 内部分析 payload；batch/benchmark 默认 YOLO body_core 模型收敛到 yolo26l-pose.pt；保持 scoreAuthorized=false、calibration_status=unvalidated、displayScope=internal；更新 change.md。
  - 涉及文件: `apps/ui_backend.py`, `batch/batch_dual_compare.py`, `analysis/bench_annotate_fps.py`, `tests/test_body_core_layout.py`, `tests/test_batch_backend_args.py`, `tests/test_s3_calibration.py`
  - 验证命令: `.\.venv\Scripts\python.exe -m pytest tests/test_body_core_layout.py tests/test_batch_backend_args.py tests/test_s3_calibration.py -q`
  - 依赖: T-002, T-003
  - 风险: high
  - 覆盖: REQ-002, REQ-003, REQ-008, AC-002.3, AC-002.8, AC-008.1, NFR-003
  - 可并行: 否
  - 验证标准: 离线高质量 body-only 分析在 YOLO26L 可用时必须选择 YOLO26L；模型不可用、安装版不支持或模型下载未完成时必须返回结构化下载/安装错误，不静默回退 MediaPipe，并输出 `requestedBackend=yolo`、缺失模型档和用户可见提示；结果不进入 full tech_eval；`scoreAuthorized=false` 和 `calibration_status=unvalidated` 不被放宽，受限显示只用 `displayScope=internal` / `display_scope=internal`。
  - 预估工程量: 4-6 小时

- [ ] **T-009:** 保持 MediaPipe 正式评分和 full tech_eval 默认边界
  - 状态: pending
  - 涉及文件: `analysis/tech_eval.py`, `core/rule_scoring.py`, `core/action_compare.py`, `tests/test_pose33_v3_golden.py`, `tests/test_valid_mask_migration.py`, `tests/test_tech_eval_contract.py`, `tests/test_rule_availability.py`
  - 验证命令: `.\.venv\Scripts\python.exe -m pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py tests/test_tech_eval_contract.py tests/test_rule_availability.py -q`
  - 验证证据: pending
  - 依赖: T-007, T-008
  - 风险: high
  - 覆盖: REQ-002, REQ-003, AC-002.1, AC-002.4, AC-002.5, AC-002.6, AC-003.2, NFR-002
  - 可并行: 否
  - 验证标准: 本任务以回归门为主，仅在发现 YOLO 可进入正式评分/full tech_eval 时增加阻断守卫；任何守卫改动都必须保持 MediaPipe `pose33_v3` golden 不漂移；正式评分和 full tech_eval 不选择 YOLO；`enableHands=false` + 手指指标必须是 MediaPipe pose-only partial 并记录 skipped capability，不能静默打开 hands。
  - 预估工程量: 2-4 小时

---

## 阶段 4：验收、打包和文档同步

- [ ] **T-010:** 完成桌面栈、打包和迁移文档验收
  - 状态: pending
  - 涉及文件: `scripts/verify-desktop-stack.ps1`, `scripts/build-tauri-sidecar.ps1`, `frontend/src-tauri/tauri.conf.json`, `docs/yolo_default_switch_decision.md`, `docs/yolo_migration_issues.md`, `change.md`
  - 验证命令: 分步运行 `npm run verify:desktop`、`npm run package:windows`、`.\.venv\Scripts\python.exe -m pytest tests/test_windows_packaging_smoke.py tests/test_yolo_landmark_mapping.py tests/test_yolo_backend_contract.py tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py -q`，每步必须退出码 0
  - 验证证据: pending
  - 依赖: T-005, T-006, T-007, T-008, T-009
  - 风险: high
  - 覆盖: REQ-001, REQ-004, REQ-006, REQ-007, REQ-008, AC-008.2, AC-008.3, NFR-004, NFR-005
  - 可并行: 否
  - 验证标准: 桌面验证栈、Windows 打包、packaged sidecar、文档和 `change.md` 均反映最终行为；若安装版支持 YOLO，sidecar 必须包含并验证 YOLO 运行依赖；若不支持，UI 和文档必须明确安装版能力边界；三阶段演进边界和 YOLO 非默认评分边界保持一致。
  - 预估工程量: 3-5 小时

---

## 执行 Waves

| Wave | 任务 | 说明 |
|:---|:---|:---|
| 1 | T-001 | 先固化路由契约，避免后续实现分叉 |
| 2 | T-002 | 高风险能力元数据先落地 |
| 3 | T-004 | 二进制帧通道是前端渲染和 YOLO 预览的基础 |
| 4 | T-005 | Canvas 渲染在帧通道完成后执行 |
| 5 | T-006 | Rust/Python 状态机在帧通道完成后执行 |
| 6 | T-003 | 模型档清单在后端接入前补齐 |
| 7 | T-007 | 接入 YOLO26n/s 实时 body-only 预览路径 |
| 8 | T-008 | 接入 YOLO26L 离线高质量 body-only 分析路径 |
| 9 | T-009 | 在 YOLO 路径接入后重跑 MediaPipe 正式评分和 full tech_eval 边界 |
| 10 | T-010 | 最后做桌面栈、打包、关键契约回归和文档收口 |

---

## 风险标记

| 任务 ID | 风险类别 | 风险描述 | 审查要求 |
|:---|:---|:---|:---|
| T-001 | 架构 / 评分授权 | 路由契约写错会导致 YOLO 误入评分路径 | 人类深度审查 |
| T-004 | 性能 / IPC | 二进制通道和 JSON bridge 双通道可能产生帧归属错误 | 人类深度审查和桌面 smoke |
| T-005 | 前端性能 | Vue reactive 大帧迁移不彻底会保留内存压力 | 浏览器/桌面截图和内存观察 |
| T-007 | 视觉后端 | YOLO 实时预览可能被误读为正式评分 | 必须检查 `scoreAuthorized` |
| T-008 | 标定 / 授权 | YOLO26L body-only 质量提升不能补齐 COCO17 缺失点 | 必须检查 full tech_eval 阻断 |
| T-010 | 打包 / 发布 | 安装包环境可能与开发环境 sidecar 或模型路径不一致 | 必须跑 packaged sidecar 验证 |

---

## 完成日志

| 任务 ID | 完成时间 | Commit Hash | 验证证据 | 备注 |
|:---|:---|:---|:---|:---|
| T-001 | 2026-06-11 13:58:19 | 60f3a66 | cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_backend_routing_contract.py tests/test_ui_backend_contract.py tests/test_batch_backend_args.py -q => exit 0, 35 passed; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py -q => exit 0, 31 passed; cmd: git diff --check => exit 0 (line-ending warnings only) | 新增 core/backend_router.py 唯一路由决策点；UI bridge 和 batch helper 消费共享 router；更新 change.md。 |
| T-002 | 2026-06-11 14:12:26 | 4541e61 | cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_yolo_backend_contract.py tests/test_yolo_landmark_mapping.py tests/test_rule_availability.py tests/test_ui_backend_analysis.py -q => exit 0, 46 passed; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py -q => exit 0, 31 passed; cmd: git diff --check => exit 0 (line-ending warnings only) | YOLO adapter 边界层与序列 artifact 统一补齐 raw_layout/feature_layout/capability/score_authorized/display_scope；UI camelCase route 与 COCO17 missing capability 测试上锁；更新 change.md。 |
| T-004 | 2026-06-11 14:35:56 | f3e50db | cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_ui_backend_sessions.py tests/test_windows_packaging_smoke.py -q => exit 0, 16 passed; cmd: npm run verify:tauri => exit 0, cargo check passed; cmd: npm --prefix frontend run test => exit 0, Frontend behavior smoke checks passed; cmd: git diff --check => exit 0 (line-ending warnings only) | 实现 Python 127.0.0.1 TCP length-prefixed latest-frame 通道与 Tauri raw IPC latest_frame；session.frame JSON 不再携带 image/base64/bytes，仅传 frame handle、token 和指标；更新 change.md 基线记录。 |
| T-005 | 2026-06-11 14:44:51 | 7bfe692 | cmd: npm --prefix frontend run test => exit 0, Frontend behavior smoke checks passed; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_vue_tauri_acceptance_gaps.py -q => exit 0, 7 passed; cmd: git diff --check => exit 0 (line-ending warnings only) | Vue 预览迁移到 Canvas/ImageBitmap；requestAnimationFrame 合并 latest frame；移除 previewImage、object URL 和 img 帧展示路径；更新 change.md 基线记录。 |
| T-006 | 2026-06-11 14:54:00 | b795674 | cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_ui_backend_sessions.py tests/test_ui_backend_contract.py -q => exit 0, 24 passed; cmd: npm --prefix frontend run test => exit 0, Frontend behavior smoke checks passed; cmd: git diff --check => exit 0 (line-ending warnings only) | 统一 session/model download/analysis 主动停止和晚到事件清理；job.stop 缺失/未知 jobId 结构化错误测试；更新 change.md。 |
| T-003 | 2026-06-11 15:13:21 | 7a1390e | cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_ui_backend_models.py tests/test_windows_packaging_smoke.py -q => exit 0, 20 passed; cmd: npm --prefix frontend run test => exit 0, Frontend behavior smoke checks passed; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py -q => exit 0, 31 passed; cmd: git diff --check => exit 0 (line-ending warnings only) | 补齐 MediaPipe/YOLO26 模型档元数据、默认代理下载、YOLO 手动安装错误、安装版 sidecar YOLO runtime 排除边界和前端展示；更新 change.md。 |
| T-007 | 2026-06-11 15:28:06 | 38474bf | cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_backend_routing_contract.py tests/test_yolo_backend_contract.py -q => exit 0, 33 passed; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py -q => exit 0, 31 passed; cmd: git diff --check => exit 0 (line-ending warnings only) | 接入 YOLO26n/s realtime body-only preview pipeline；session.frame 透传 YOLO 授权/多人 meta；保持 MediaPipe 旧默认路径和正式评分边界；更新 change.md。 |
| T-008 | 2026-06-11 15:48:36 | 2e5051e | cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_body_core_layout.py tests/test_batch_backend_args.py tests/test_s3_calibration.py -q => exit 0, 40 passed; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py -q => exit 0, 31 passed; cmd: git diff --check => exit 0 (line-ending warnings only) | 接入 analysis.run YOLO26L high_quality body-only 内部分析 payload；batch/benchmark 默认 YOLO body_core 模型收敛到 yolo26l-pose.pt；保持 scoreAuthorized=false、calibration_status=unvalidated、displayScope=internal；更新 change.md。 |
