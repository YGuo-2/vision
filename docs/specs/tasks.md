# Bugfix 任务清单 (Task Breakdown)

> **问题名称：** Vue/Tauri 迁移最终验收缺口修复
> **关联规范：** `docs/specs/bugfix.md` · `docs/specs/design.md`
> **状态：** Completed
> **当前任务：** n/a
> **进度：** 20 / 20 已完成
> **最后更新：** 2026-06-09

---

## 执行规则

1. **先证据，后修复：** 第一项任务优先建立自动化复现或最强可用证据。
2. **受控入口：** 任务开始、完成、阻塞、跳过必须通过 `spec_progress.py` CLI 或 MCP 工具更新。
3. **最小变更：** 只修改解决当前最终验收缺口所必需的代码路径。
4. **必须防回归：** 每个功能面修复后必须覆盖至少一条不变行为或相邻路径测试。
5. **退回机制：** 如果根因或范围变化，暂停实现，更新 `bugfix.md` / `design.md` / `tasks.md`，运行验证并重新获得批准。
6. **后端边界：** 不得改写视觉算法、评分算法、YOLO 阶段边界或 Tkinter 旧入口。

---

## 阶段 1：复现与契约刻画 (Reproduction)

- [x] **B-001:** 固化最终验收缺口的失败证明
  - 状态: done
  - 验证证据: 新增 tests/test_vue_tauri_acceptance_gaps.py，并更新 bridge/job 契约测试；运行 .\\.venv\\Scripts\\python.exe -m pytest tests\\test_ui_backend_contract.py tests\\test_ui_backend_jobs.py tests\\test_vue_tauri_acceptance_gaps.py -q 得到 9 failed / 11 passed，失败点对应 final acceptance 缺口：manifest jobId/sessionId、bad request requestId、completed job stop、Vue analysis/model/download/dir picker/event/raw JSON/frontend test coverage。
  - 完成时间: 2026-06-09 18:49:49
  - 备注: n/a
  - 涉及文件: `tests/`, `frontend/src/`, `frontend/package.json`, `docs/specs/bugfix.md`
  - 验证命令: `rg` 静态检查；新增或更新的前端/bridge 失败测试；必要时记录 Windows GUI 替代证据
  - 依赖: 无
  - 风险: high
  - 覆盖: BUG-001, BUG-002, BUG-003, BUG-004, BUG-005, BUG-006
  - 可并行: 否
  - 验证标准: 修复前测试或证据能稳定指出协议、前端入口、事件过滤、模型管理、动作分析和文档状态缺口
  - 替代路径: GUI 启动和目录选择若无法自动化，必须记录手工步骤、日志/截图路径和证据限制
  - 预估工程量: 1-2 小时

---

## 阶段 2：Bridge 协议与任务生命周期 (Protocol Fix)

- [x] **B-002:** 修复 bridge envelope、错误 requestId、job stop 和 manifest 契约
  - 状态: done
  - 验证证据: 修复 apps/ui_backend.py 与 frontend/src-tauri/src/lib.rs 的 message contract、错误 requestId 保留和 active-only job.stop；更新阻塞式 job.stop 测试。验证：.\\.venv\\Scripts\\python.exe -m pytest tests\\test_ui_backend_contract.py tests\\test_ui_backend_jobs.py -q -> 15 passed；frontend/src-tauri cargo check passed。
  - 完成时间: 2026-06-09 18:54:12
  - 备注: n/a
  - 涉及文件: `apps/ui_backend.py`, `frontend/src/bridge.ts`, `frontend/src-tauri/src/lib.rs`, `tests/test_ui_backend_contract.py`, `tests/test_ui_backend_jobs.py`
  - 验证命令: `.\.venv\Scripts\python.exe -m pytest tests\test_ui_backend_contract.py tests\test_ui_backend_jobs.py -q`; `cargo check` from `frontend/src-tauri`
  - 依赖: B-001
  - 风险: high
  - 覆盖: BUG-001, FIX-001, SAFE-004
  - 可并行: 否
  - 验证标准: 错误响应保留可提取 `requestId`；已完成 job stop 不误报成功；manifest 包含 optional `jobId/sessionId` 语义；raw JSON envelope 可供前端显示
  - 预估工程量: 2-3 小时

---

## 阶段 3：实时主窗口与录制路径 (Session UI Fix)

- [x] **B-003:** 修复实时识别主窗口状态、事件过滤、帧节流和进度显示
  - 状态: done
  - 验证证据: 修复 Vue 输入源 none/camera/video 三态、完整 raw JSON envelope、当前 session/job 事件过滤、预览帧 UI 节流和实时流进度文案。验证：npm --prefix frontend run build passed；pytest tests\\test_ui_backend_sessions.py tests\\test_input_source_state.py -q -> 15 passed；tests\\test_vue_tauri_acceptance_gaps.py 中 event/raw JSON 覆盖项已转绿，剩余失败归属 B-004/B-005/B-006/B-007。
  - 完成时间: 2026-06-09 19:00:38
  - 备注: n/a
  - 涉及文件: `frontend/src/App.vue`, `frontend/src/bridge.ts`, `apps/ui_backend.py`, `tests/test_ui_backend_sessions.py`, `frontend/` 前端测试
  - 验证命令: `npm --prefix frontend run build`; 前端交互测试；`.\.venv\Scripts\python.exe -m pytest tests\test_ui_backend_sessions.py tests\test_input_source_state.py -q`
  - 依赖: B-002
  - 风险: high
  - 覆盖: BUG-002, FIX-002, SAFE-001
  - 可并行: 否
  - 验证标准: Vue 具备 `none/camera/video` 或等价无输入状态；只处理当前 session/job 事件；预览帧节流；未知总帧进度不显示误导性 `0%`
  - 预估工程量: 2-4 小时

- [x] **B-004:** 补齐录制目录选择和默认输出目录语义
  - 状态: done
  - 验证证据: 补齐录制目录选择：Vue selectRecordDir 调用受限 Tauri select_directory，Rust 使用 Windows Shell32 folder picker FFI，无新增依赖、不走任意 shell；recordDir 默认留空，让 Python bridge 回退 outputs_dir()。验证：cargo check passed；npm --prefix frontend run build passed；pytest tests\\test_ui_backend_sessions.py tests\\test_recording_controller.py tests\\test_vue_tauri_acceptance_gaps.py -q 中目录覆盖项转绿，剩余唯一失败为 B-007 前端测试入口。
  - 完成时间: 2026-06-09 19:20:06
  - 备注: n/a
  - 涉及文件: `frontend/src/App.vue`, `frontend/src-tauri/`, `frontend/package.json`, `apps/ui_backend.py`, `tests/test_ui_backend_sessions.py`, 前端测试
  - 验证命令: `npm --prefix frontend run build`; 前端交互测试；`.\.venv\Scripts\python.exe -m pytest tests\test_ui_backend_sessions.py tests\test_recording_controller.py -q`
  - 依赖: B-003
  - 风险: medium
  - 覆盖: BUG-003, FIX-003, SAFE-004
  - 可并行: 否
  - 验证标准: Vue 提供 Tkinter 等价目录选择入口；默认输出目录与 `outputs_dir()` 语义一致；写盘错误和停止状态仍正确展示
  - 预估工程量: 1-2 小时

---

## 阶段 4：动作分析与设置窗口 (Feature Coverage Fix)

- [x] **B-005:** 补齐动作分析、模板生成/比对和直拳技术评估 Vue 流程
  - 状态: done
  - 验证证据: 补齐 Vue 动作分析面板：template.create、analysis.run、模板路径/基准视频/目标视频/startFrame/endFrame/worker/previewOut、doTechEval、stance/viewHint/debugVideo、结果展示和 job.stop。验证：npm --prefix frontend run build passed；pytest tests\\test_ui_backend_analysis.py tests\\test_tech_eval_contract.py tests\\test_pose33_v3_golden.py -q -> 30 passed；tests\\test_vue_tauri_acceptance_gaps.py 中 analysis/tech eval 覆盖项已转绿。
  - 完成时间: 2026-06-09 19:10:10
  - 备注: n/a
  - 涉及文件: `frontend/src/App.vue`, `frontend/src/bridge.ts`, `apps/ui_backend.py`, `tests/test_ui_backend_analysis.py`, `tests/test_tech_eval_contract.py`, 前端测试
  - 验证命令: `npm --prefix frontend run build`; 前端交互测试；`.\.venv\Scripts\python.exe -m pytest tests\test_ui_backend_analysis.py tests\test_tech_eval_contract.py tests\test_pose33_v3_golden.py -q`
  - 依赖: B-002
  - 风险: high
  - 覆盖: BUG-004, FIX-004, SAFE-001, SAFE-002
  - 可并行: 否
  - 验证标准: Vue 可选择已有模板、基准视频、目标视频、起止帧、worker、预览输出；调用 `template.create` / `analysis.run`；展示匹配分数、片段、预览导出、完整 JSON、直拳四类指标、原因类型、失败环节和 debug video 路径
  - 预估工程量: 4-6 小时

- [x] **B-006:** 补齐设置窗口和 MediaPipe 模型管理 Vue 流程
  - 状态: done
  - 验证证据: 补齐 Vue 设置/模型管理面板：modelsDir/path/sizeMb/installed/active 展示、model.download 单模型/全部缺失、model.progress、cancelModelDownload/job.stop。验证：npm --prefix frontend run build passed；pytest tests\\test_ui_backend_models.py tests\\test_ui_backend_contract.py -q -> 14 passed；tests\\test_vue_tauri_acceptance_gaps.py 中 settings/model download 覆盖项已转绿。
  - 完成时间: 2026-06-09 19:14:02
  - 备注: n/a
  - 涉及文件: `frontend/src/App.vue`, `frontend/src/bridge.ts`, `apps/ui_backend.py`, `core/model_manager.py`, `tests/test_ui_backend_models.py`, 前端测试
  - 验证命令: `npm --prefix frontend run build`; 前端交互测试；`.\.venv\Scripts\python.exe -m pytest tests\test_ui_backend_models.py tests\test_ui_backend_contract.py -q`
  - 依赖: B-002
  - 风险: high
  - 覆盖: BUG-005, FIX-005, SAFE-004
  - 可并行: 否
  - 验证标准: Vue 提供 settings view/modal；展示模型目录、逐模型路径、安装状态、文件大小和缺失状态；支持刷新、单模型下载、全部缺失下载、字节进度、完成/失败展示和取消；`.part` 清理测试通过
  - 预估工程量: 3-5 小时

---

## 阶段 5：验证、打包与文档收尾 (Verification)

- [x] **B-007:** 强化自动化验证集合和 Windows 运行级证据
  - 状态: done
  - 验证证据: 强化验证集合：新增 frontend/scripts/frontend-smoke.mjs 与 npm --prefix frontend run test；verify-desktop-stack.ps1 接入前端 smoke、纳入 tests/test_vue_tauri_acceptance_gaps.py，并检查原生命令 exit code。验证：npm --prefix frontend run test passed；pytest tests\\test_vue_tauri_acceptance_gaps.py -q -> 5 passed；npm run verify:desktop -> frontend build/test, cargo check, py_compile, 114 desktop regression tests passed；pytest tests\\test_windows_packaging_smoke.py -q -> 6 passed；npm run package:windows produced NSIS installer。
  - 完成时间: 2026-06-09 19:28:41
  - 备注: n/a
  - 涉及文件: `scripts/verify-desktop-stack.ps1`, `package.json`, `frontend/package.json`, `tests/`, `frontend/src-tauri/`, `README.md`, `AGENTS.md`
  - 验证命令: `npm run verify:desktop`; `npm run package:windows`; `.\.venv\Scripts\python.exe -m pytest tests\test_windows_packaging_smoke.py -q`
  - 依赖: B-003, B-004, B-005, B-006
  - 风险: high
  - 覆盖: BUG-006, FIX-006, SAFE-003, SAFE-004
  - 可并行: 否
  - 验证标准: `verify:desktop` 覆盖 Vue 前端交互/协议测试、Tauri/Rust 检查、Python bridge 和核心回归；补 dev-mode 或等价启动证据；打包后 sidecar/缺模型下载入口 smoke 有记录
  - 预估工程量: 2-4 小时

- [x] **B-008:** 同步文档状态、`change.md` 和最终回归证据
  - 状态: done
  - 验证证据: 同步 README.md、AGENTS.md、change.md 与 bugfix 规范状态，记录前端 smoke、verify:desktop、packaging 和核心回归证据。验证：git diff --check 无 whitespace error（仅 LF/CRLF warning）；py_compile apps/app_ui.py apps/ui_backend.py core/vision_pipeline.py passed；pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py -q -> 31 passed；pytest tests/test_windows_packaging_smoke.py -q -> 6 passed；npm run verify:desktop -> frontend build/test, cargo check, py_compile, 114 desktop regression tests passed。
  - 完成时间: 2026-06-09 19:35:38
  - 备注: n/a
  - 涉及文件: `docs/specs/`, `README.md`, `AGENTS.md`, `change.md`
  - 验证命令: `git diff --check`; `.\.venv\Scripts\python.exe -m py_compile .\apps\app_ui.py .\apps\ui_backend.py .\core\vision_pipeline.py`; `.\.venv\Scripts\python.exe -m pytest tests\test_pose33_v3_golden.py tests\test_valid_mask_migration.py -q`; `npm run verify:desktop`
  - 依赖: B-007
  - 风险: medium
  - 覆盖: BUG-006, FIX-006, SAFE-001, SAFE-002, SAFE-003
  - 可并行: 否
  - 验证标准: docs/specs 头部状态、approval、current task、progress 和 commit 同步；README/AGENTS/change.md 记录最终命令和结果；核心 golden/valid_mask、Tkinter py_compile、Windows 打包 smoke 通过；随后重新进入 spec-acceptance
  - 预估工程量: 1-2 小时

- [x] **B-009:** 修复首轮验收发现的前端状态语义缺口
  - 状态: done
  - 验证证据: 修复 Vue 未知总帧进度、analysis/template/model status job 过滤和模型下载失败展示；新增 frontend/src/bridge-state.ts 行为助手与 behavior smoke；验证：npm --prefix frontend run test -> Frontend behavior smoke checks passed；npm --prefix frontend run build passed；pytest tests/test_ui_backend_models.py tests/test_vue_tauri_acceptance_gaps.py -q -> 11 passed。
  - 完成时间: 2026-06-09 20:18:46
  - 备注: n/a
  - 涉及文件: `frontend/src/App.vue`, `frontend/src/bridge-state.ts`, `frontend/scripts/frontend-smoke.mjs`, `tests/test_ui_backend_models.py`, `tests/test_vue_tauri_acceptance_gaps.py`
  - 验证命令: `npm --prefix frontend run test`; `npm --prefix frontend run build`; `.\.venv\Scripts\python.exe -m pytest tests\test_ui_backend_models.py tests\test_vue_tauri_acceptance_gaps.py -q`
  - 依赖: B-008
  - 风险: high
  - 覆盖: BUG-002, BUG-004, BUG-005, FIX-002, FIX-004, FIX-005
  - 可并行: 否
  - 验证标准: 启动未知总帧会话显示非百分比实时/等待文案；`template.status`、`analysis.status`、`model.status` 与 progress/job 事件一致按当前 `jobId` 过滤；模型下载 result/state 为 failed/stopped 时不展示“下载完成”；行为级前端 smoke 能喂入事件并断言状态语义。
  - 预估工程量: 2-3 小时

- [x] **B-010:** 补足交互级验证、Windows 运行级证据和文档同步
  - 状态: done
  - 验证证据: 补足前端 behavior smoke、verify 文案、packaged sidecar ping 和文档证据；验证：npm run verify:desktop -> frontend build, Frontend behavior smoke, cargo check, py_compile, 116 desktop regression tests passed；py_compile apps/app_ui.py apps/ui_backend.py core/vision_pipeline.py passed；pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py -q -> 31 passed；git diff --check -> only CRLF warnings；npm run package:windows produced NSIS installer；pytest tests/test_windows_packaging_smoke.py -q -> 7 passed including generated sidecar bridge.ping.
  - 完成时间: 2026-06-09 20:28:51
  - 备注: n/a
  - 涉及文件: `frontend/scripts/frontend-smoke.mjs`, `scripts/verify-desktop-stack.ps1`, `tests/test_windows_packaging_smoke.py`, `docs/specs/`, `change.md`
  - 验证命令: `npm run verify:desktop`; `.\.venv\Scripts\python.exe -m pytest tests\test_windows_packaging_smoke.py -q`; `npm run package:windows`; `git diff --check`; `.\.venv\Scripts\python.exe -m py_compile .\apps\app_ui.py .\apps\ui_backend.py .\core\vision_pipeline.py`; `.\.venv\Scripts\python.exe -m pytest tests\test_pose33_v3_golden.py tests\test_valid_mask_migration.py -q`
  - 依赖: B-009
  - 风险: high
  - 覆盖: BUG-006, FIX-006, SAFE-001, SAFE-002, SAFE-003, SAFE-004
  - 可并行: 否
  - 验证标准: `verify:desktop` 明确区分 frontend build 与 behavior smoke；前端 smoke 验证按钮绑定、事件过滤、raw JSON、未知总帧和模型失败状态；Windows packaged sidecar/installer 证据写入 progress 与 change.md；docs/specs 不再含非具体 commit 占位或旧完成日志占位；随后重新进入 spec-acceptance。
  - 预估工程量: 2-4 小时

- [x] **B-011:** 修复首轮复验发现的协议、事件过滤、竞态和模型保护缺口
  - 状态: done
  - 验证证据: 修复 manifest request optional jobId/sessionId、Rust decode_error envelope、strict scoped-event filtering、长任务预分配 job/session id 和既有模型文件保护测试；验证：npm --prefix frontend run test -> Frontend behavior smoke checks passed；npm --prefix frontend run build passed；pytest tests/test_ui_backend_contract.py tests/test_ui_backend_models.py tests/test_vue_tauri_acceptance_gaps.py tests/test_windows_packaging_smoke.py -q -> 29 passed；frontend/src-tauri cargo check passed。
  - 完成时间: 2026-06-09 21:03:12
  - 备注: n/a
  - 涉及文件: `apps/ui_backend.py`, `frontend/src-tauri/src/lib.rs`, `frontend/src/App.vue`, `frontend/src/bridge-state.ts`, `frontend/scripts/frontend-smoke.mjs`, `tests/test_ui_backend_contract.py`, `tests/test_windows_packaging_smoke.py`, `tests/test_ui_backend_models.py`, `tests/test_vue_tauri_acceptance_gaps.py`
  - 验证命令: `npm --prefix frontend run test`; `npm --prefix frontend run build`; `.\.venv\Scripts\python.exe -m pytest tests\test_ui_backend_contract.py tests\test_ui_backend_models.py tests\test_vue_tauri_acceptance_gaps.py tests\test_windows_packaging_smoke.py -q`; `cargo check` from `frontend/src-tauri`
  - 依赖: B-010
  - 风险: high
  - 覆盖: BUG-001, BUG-002, BUG-004, BUG-005, FIX-001, FIX-002, FIX-004, FIX-005
  - 可并行: 否
  - 验证标准: Python/Rust manifest request 契约都列出 optional `jobId/sessionId`；Rust decode_error event 保持完整 event envelope；当前 session/job 存在时 missing-id scoped events 不得污染 UI；长任务在发送前预分配 job/session id，早到事件不被过滤；中断下载删除 `.part` 且不改动已有正式模型文件。
  - 预估工程量: 2-4 小时

- [x] **B-012:** 同步复验后的 docs/specs、README/AGENTS 和 commit 证据
  - 状态: done
  - 验证证据: 同步 requirements.md 状态/审批记录、README/AGENTS 最终验证结果、change.md 和 commit 证据；验证：rg 检查无草稿/非具体提交占位/旧完成日志占位；npm run verify:desktop -> 117 desktop regression tests passed；pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py -q -> 31 passed；py_compile apps/app_ui.py apps/ui_backend.py core/vision_pipeline.py passed；pytest tests/test_windows_packaging_smoke.py -q -> 7 passed；npm run package:windows produced NSIS installer；git diff --check -> only CRLF warnings。
  - 完成时间: 2026-06-09 21:14:41
  - 备注: n/a
  - 涉及文件: `docs/specs/requirements.md`, `docs/specs/tasks.md`, `docs/specs/progress.md`, `docs/specs/spec.yml`, `README.md`, `AGENTS.md`, `change.md`
  - 验证命令: `rg` 检查草稿/占位；`python <plugin-root>\scripts\validate_spec.py docs\specs --resume`; `python <plugin-root>\scripts\validate_spec.py docs\specs --pre-acceptance`
  - 依赖: B-011
  - 风险: medium
  - 覆盖: BUG-006, FIX-006
  - 可并行: 否
  - 验证标准: active `docs/specs` 不再出现与当前工作流冲突的草稿状态；README/AGENTS/change.md 记录最终命令与结果；任务/进度日志使用具体提交或可复查提交范围，不再使用非具体提交占位文本；pre-acceptance 通过后再进入 final acceptance。
  - 预估工程量: 1-2 小时

---

## 阶段 6：第一波最终验收回路修复 (Acceptance Bugfix Loop)

- [x] **B-013:** 固化第一波最终验收新增问题清单
  - 状态: done
  - 验证证据: 新增 B-013..B-017 任务并在 bugfix/design 记录第一波 B-002/B-004/B-006/B-008/B-010 ACTIONABLE_ISSUES；validate_spec.py docs\specs --workflow bugfix -> 34 passed；git status 仅 docs/specs 变更。
  - 完成时间: 2026-06-09 21:51:10
  - 备注: 第一波存在 actionable issues，未启动对抗审查。
  - 涉及文件: `docs/specs/bugfix.md`, `docs/specs/design.md`, `docs/specs/tasks.md`, `docs/specs/progress.md`, `docs/specs/spec.yml`
  - 验证命令: `python <plugin-root>\scripts\validate_spec.py docs\specs --workflow bugfix`; `python <plugin-root>\scripts\spec_progress.py resume docs\specs`
  - 依赖: B-012
  - 风险: medium
  - 覆盖: BUG-001, BUG-003, BUG-005, BUG-006, FIX-001, FIX-003, FIX-005, FIX-006
  - 可并行: 否
  - 验证标准: 记录第一波 B-002/B-004/B-006/B-008/B-010 的 ACTIONABLE_ISSUES；任务图出现 B-013..B-017；不启动第二波对抗审查。
  - 预估工程量: 0.5 小时

- [x] **B-014:** 补齐 manifest optional 语义和 TS null envelope 契约
  - 状态: done
  - 验证证据: 补齐 Python/Rust manifest optional/nullable 元数据和 TS null envelope 类型；验证：pytest tests\test_ui_backend_contract.py tests\test_windows_packaging_smoke.py -q -> 17 passed；npm --prefix frontend run test -> Frontend behavior smoke checks passed；C:\Users\ny\.cargo\bin\cargo.exe check -> passed。
  - 完成时间: 2026-06-09 21:57:29
  - 备注: cargo 未在当前 PATH，使用本机绝对路径 C:\Users\ny\.cargo\bin\cargo.exe。
  - 涉及文件: `apps/ui_backend.py`, `frontend/src/bridge.ts`, `frontend/src-tauri/src/lib.rs`, `tests/test_ui_backend_contract.py`, `tests/test_windows_packaging_smoke.py`, `frontend/scripts/frontend-smoke.mjs`
  - 验证命令: `.\.venv\Scripts\python.exe -m pytest tests\test_ui_backend_contract.py tests\test_windows_packaging_smoke.py -q`; `npm --prefix frontend run test`; `cargo check` from `frontend/src-tauri`
  - 依赖: B-013
  - 风险: high
  - 覆盖: BUG-001, FIX-001, SAFE-004
  - 可并行: 否
  - 验证标准: Python/Rust manifest 同时保留字段列表并显式声明 `jobId/sessionId` optional；TS `BridgeEnvelope`/`BridgeCommandRequest` 与 Python/Rust 的 `null` envelope 对齐；前端 smoke 覆盖 null envelope。
  - 预估工程量: 1-2 小时

- [x] **B-015:** 修复 Windows Shell32 目录选择器 COM 初始化
  - 状态: done
  - 验证证据: Rust Shell32 picker 增加 OleInitialize/OleUninitialize；MTA RPC_E_CHANGED_MODE 时禁用 BIF_NEWDIALOGSTYLE 降级；验证：C:\Users\ny\.cargo\bin\cargo.exe check -> passed；pytest tests\test_windows_packaging_smoke.py -q -> 8 passed；npm --prefix frontend run test -> Frontend behavior smoke checks passed。
  - 完成时间: 2026-06-09 22:00:45
  - 备注: 依据 Microsoft SHBrowseForFolder COM 初始化要求修复。
  - 涉及文件: `frontend/src-tauri/src/lib.rs`, `tests/test_windows_packaging_smoke.py`, `frontend/scripts/frontend-smoke.mjs`
  - 验证命令: `cargo check` from `frontend/src-tauri`; `.\.venv\Scripts\python.exe -m pytest tests\test_windows_packaging_smoke.py -q`; `npm --prefix frontend run test`
  - 依赖: B-014
  - 风险: medium
  - 覆盖: BUG-003, FIX-003, SAFE-004
  - 可并行: 否
  - 验证标准: `SHBrowseForFolderW` 前执行 STA/OLE 初始化并在本调用拥有初始化时释放；测试锁定 `OleInitialize`/`OleUninitialize` 与 marker 顺序。
  - 预估工程量: 1 小时

- [x] **B-016:** 修复模型下载截断误安装和窗口关闭取消下载
  - 状态: done
  - 验证证据: download_model 校验已知 Content-Length 的截断 EOF 并清理 .part；Vue onBeforeUnmount 复用 cancelModelDownload 停止 active 下载；验证：pytest tests\test_ui_backend_models.py tests\test_vue_tauri_acceptance_gaps.py -q -> 13 passed；npm --prefix frontend run test -> Frontend behavior smoke checks passed；npm --prefix frontend run build -> passed。
  - 完成时间: 2026-06-09 22:04:56
  - 备注: 正式模型文件在中断和截断下载时均保持不变。
  - 涉及文件: `core/model_manager.py`, `frontend/src/App.vue`, `frontend/scripts/frontend-smoke.mjs`, `tests/test_ui_backend_models.py`, `tests/test_vue_tauri_acceptance_gaps.py`
  - 验证命令: `.\.venv\Scripts\python.exe -m pytest tests\test_ui_backend_models.py tests\test_vue_tauri_acceptance_gaps.py -q`; `npm --prefix frontend run test`; `npm --prefix frontend run build`
  - 依赖: B-015
  - 风险: high
  - 覆盖: BUG-005, FIX-005, SAFE-004
  - 可并行: 否
  - 验证标准: HTTP `Content-Length` 已知但读取字节不足时抛错并删除 `.part`、不替换正式模型；Vue unmount 会对 active `modelDownloadJobId` 发起 `job.stop`。
  - 预估工程量: 1-2 小时

- [x] **B-017:** 同步第一波修复后的文档、验证和 commit 证据
  - 状态: done
  - 验证证据: README/AGENTS/change.md 与 docs/specs 已同步；rg '5526945\\.\\.HEAD' docs/specs README.md AGENTS.md change.md -> no matches；npm run verify:desktop -> 118 passed；pytest tests/test_windows_packaging_smoke.py -q -> 8 passed；pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py -q -> 31 passed；npm run package:windows -> NSIS installer generated；git diff --check -> only LF/CRLF warnings。
  - 完成时间: 2026-06-09 22:17:40
  - 备注: pre-acceptance 已在实现提交 8764f86 后用干净工作树通过；文档证据提交后需再次复查。
  - 涉及文件: `docs/specs/`, `README.md`, `AGENTS.md`, `change.md`
  - 验证命令: `powershell -NoProfile -Command "$p = '5526945..' + 'HEAD'; rg --fixed-strings $p docs\specs README.md AGENTS.md change.md"`; `npm run verify:desktop`; `python <plugin-root>\scripts\validate_spec.py docs\specs --pre-acceptance`
  - 依赖: B-016
  - 风险: medium
  - 覆盖: BUG-006, FIX-006
  - 可并行: 否
  - 验证标准: active docs 不再使用 moving HEAD 这类移动提交证据；README/AGENTS/change.md 记录新增修复与最终验证；pre-acceptance 通过后重新进入 final acceptance。
  - 预估工程量: 1 小时

- [x] **B-018:** 修复第一波 B-008 文档追踪复查缺口
  - 状态: done
  - 验证证据: 记录 docs sync commit 3aa2578 并修复 B-017/B-018 grep 命令为完整 HEAD 字符串拼接，避免自匹配；PowerShell 构造 fixed-string 检查目标模式（`5526945..` + `HEAD`）-> no matches；change.md 已记录 B-018；validate_spec.py docs\specs --resume/--pre-acceptance 将在 docs-only 提交后重跑。
  - 完成时间: 2026-06-09 22:50:10
  - 备注: 当前 docs-only 证据提交的最终 hash 通过 git log -1 复查，避免提交内容自引用 hash。
  - 涉及文件: `docs/specs/tasks.md`, `docs/specs/progress.md`, `docs/specs/spec.yml`, `change.md`
  - 验证命令: `powershell -NoProfile -Command "$p = '5526945..' + 'HEAD'; rg --fixed-strings $p docs\specs README.md AGENTS.md change.md"`; `python <plugin-root>\scripts\validate_spec.py docs\specs --pre-acceptance`
  - 依赖: B-017
  - 风险: medium
  - 覆盖: BUG-006, FIX-006
  - 可并行: 否
  - 验证标准: active docs 明确记录 docs sync commit `3aa2578`；B-017/B-018 证据说明当前 docs-only 证据提交通过 `git log -1` 复查；检查命令不再使用不完整 grep 写法且不造成自匹配。
  - 预估工程量: 0.5 小时

- [x] **B-019:** 补充模型下载卸载取消的行为级回归测试
  - 状态: done
  - 验证证据: Added bridge-lifecycle stopJobById helper and behavior smoke assertions for exact job.stop command/payload/options; npm --prefix frontend run test -> passed; npm --prefix frontend run build -> passed; pytest tests/test_vue_tauri_acceptance_gaps.py -q -> 6 passed.
  - 完成时间: 2026-06-09 23:24:53
  - 备注: n/a
  - 涉及文件: `frontend/src/App.vue`, `frontend/src/bridge-lifecycle.ts`, `frontend/scripts/frontend-smoke.mjs`, `tests/test_vue_tauri_acceptance_gaps.py`, `docs/specs/`, `change.md`
  - 验证命令: `npm --prefix frontend run test`; `npm --prefix frontend run build`; `.\.venv\Scripts\python.exe -m pytest tests\test_vue_tauri_acceptance_gaps.py -q`
  - 依赖: B-018
  - 风险: medium
  - 覆盖: BUG-005, FIX-005, SAFE-004
  - 可并行: 否
  - 验证标准: 前端行为测试用 stub 直接断言 active `modelDownloadJobId` 会调用 `job.stop`，且 payload 和 options 均携带相同 `jobId`；空 job 不发送停止命令；`App.vue` 卸载路径复用该行为助手。
  - 预估工程量: 0.5-1 小时

- [x] **B-020:** 修复实时会话 `job.failed` 不清运行态
  - 状态: done
  - 验证证据: Handled current session job.failed as a terminal UI state and added frontend behavior smoke for current/foreign job.failed; npm --prefix frontend run test -> passed; npm --prefix frontend run build -> passed; pytest tests/test_vue_tauri_acceptance_gaps.py -q -> 6 passed; pytest tests/test_ui_backend_sessions.py tests/test_input_source_state.py tests/test_vue_tauri_acceptance_gaps.py -q -> 21 passed; pytest tests/test_ui_backend_models.py tests/test_vue_tauri_acceptance_gaps.py -q -> 13 passed; npm run verify:desktop -> 118 passed.
  - 完成时间: 2026-06-10 00:02:13
  - 备注: n/a
  - 涉及文件: `frontend/src/App.vue`, `frontend/src/bridge-state.ts`, `frontend/scripts/frontend-smoke.mjs`, `tests/test_vue_tauri_acceptance_gaps.py`, `docs/specs/`, `change.md`
  - 验证命令: `npm --prefix frontend run test`; `npm --prefix frontend run build`; `.\.venv\Scripts\python.exe -m pytest tests\test_vue_tauri_acceptance_gaps.py -q`
  - 依赖: B-019
  - 风险: medium
  - 覆盖: BUG-002, FIX-002, SAFE-001
  - 可并行: 否
  - 验证标准: 当前 `sessionJobId` 的 `job.failed` 被 scoped event 过滤接受，并作为实时会话终态清理 `isRunning`、设置失败状态；外来 `job.failed` 不污染当前会话；前端 smoke 覆盖 current/foreign failed event 行为。
  - 预估工程量: 0.5-1 小时

---

## 执行 Waves

| Wave | 任务 | 说明 |
|:---|:---|:---|
| 1 | B-001 | 先建立失败证明和证据边界 |
| 2 | B-002 | 修复协议与生命周期基础 |
| 3 | B-003, B-004 | 主窗口状态和录制目录依赖协议基础 |
| 4 | B-005, B-006 | 动作分析/技术评估与设置/模型管理依赖协议基础 |
| 5 | B-007 | 汇总验证和 Windows 运行级证据 |
| 6 | B-008 | 文档、change.md 和最终回归证据 |
| 7 | B-009 | 首轮验收前端状态语义修复 |
| 8 | B-010 | 交互验证、运行级证据和文档同步 |
| 9 | B-011 | 复验协议、过滤、竞态和模型保护修复 |
| 10 | B-012 | 复验文档和 commit 证据同步 |
| 11 | B-013 | 第一波最终验收新增问题固化 |
| 12 | B-014 | 协议 optional/null 契约修复 |
| 13 | B-015 | Windows 目录选择器 COM 初始化 |
| 14 | B-016 | 模型下载完整性和卸载取消 |
| 15 | B-017 | 验证、文档和 commit 证据同步 |
| 16 | B-018 | B-008 文档追踪复查缺口修复 |
| 17 | B-019 | 模型下载卸载取消行为级回归 |
| 18 | B-020 | 实时会话 job.failed 终态收口 |

---

## 风险标记

| 任务 ID | 风险类别 | 风险描述 | 审查要求 |
|:---|:---|:---|:---|
| B-002 | 协议/生命周期 | 错误 envelope 和 stop 语义影响全部长任务 | 需契约测试和 Tauri 边界检查 |
| B-003 | 性能/状态一致性 | 高频帧和 stale event 可能影响识别线程与 UI 状态 | 需节流和 stale event 测试 |
| B-005 | 评分边界 | 技术评估 UI 可能误触算法或 YOLO 边界 | 需 golden/valid_mask/tech_eval contract |
| B-006 | 下载/文件完整性 | 模型下载取消涉及 `.part` 清理和正式文件保护 | 需 model_manager 回归 |
| B-007 | 打包/安全 | Tauri sidecar、dialog 和 capabilities 不能扩大 shell 面 | 需 packaging smoke 和安全审查 |
| B-009 | 状态一致性/下载失败 | 旧任务事件和失败下载可能污染当前 UI 或误报成功 | 需行为级前端 smoke 和模型失败语义测试 |
| B-010 | 验证/证据链 | 静态 smoke 或占位文档可能让 final acceptance 误判完成 | 需 verify:desktop、packaging smoke、docs 同步和 change.md 审查 |
| B-011 | 协议/竞态/文件保护 | 缺失 ID 或早到事件可能污染/丢失当前任务状态，取消下载可能破坏正式模型 | 需 behavior smoke、contract/parity 测试和 model_manager 回归 |
| B-012 | 文档/可追溯性 | active specs 草稿或 commit 占位会让 final acceptance 无法复查 | 需 docs grep、resume/pre-acceptance |
| B-014 | 协议/类型契约 | manifest 缺 optional 语义或 TS 不接受 null 会让前后端契约继续漂移 | 需 Python/Rust/TS parity 测试 |
| B-015 | Windows COM/打包 | Shell32 目录选择器未初始化 COM 可能在打包运行时静默失败 | 需 Rust marker 与 cargo check |
| B-016 | 下载/文件完整性 | HTTP 截断或关闭窗口可能导致半成品模型被误安装或下载任务泄漏 | 需截断下载和 unmount 取消回归 |
| B-017 | 文档/可追溯性 | 移动 `HEAD` 证据会让最终验收不可复查 | 需 docs grep、pre-acceptance |
| B-018 | 文档/可追溯性 | docs sync commit 未纳入证据链会让最终验收无法重建当前文档状态 | 需 docs grep、resume/pre-acceptance |
| B-019 | 下载/生命周期测试 | unmount 取消 active 模型下载若只有 marker 覆盖，可能让 `job.stop` payload 漂移而不被发现 | 需行为级前端 smoke |
| B-020 | 状态一致性 | 当前实时识别 job 失败若不清运行态，UI 可能继续显示运行/停止可用 | 需 job.failed 终态行为测试 |

---

## 完成日志

| 任务 ID | 完成时间 | Commit Hash | 验证证据 | 备注 |
|:---|:---|:---|:---|:---|
| B-001..B-008 | 2026-06-09 | `f0b0cf1` | 已完成首轮 bugfix 提交前的 bridge、Vue 入口、模型管理、打包和核心回归验证；首轮 final acceptance 随后发现 B-009/B-010 追加缺口。 | 详见各任务“验证证据”字段 |
| B-009 | 2026-06-09 20:18:46 | `5526945` | `npm --prefix frontend run test`、`npm --prefix frontend run build`、`pytest tests/test_ui_backend_models.py tests/test_vue_tauri_acceptance_gaps.py -q -> 11 passed`。 | 修复首轮验收前端状态语义缺口 |
| B-010 | 2026-06-09 20:28:51 | `5526945` | `npm run verify:desktop -> 116 passed`、`npm run package:windows`、`pytest tests/test_windows_packaging_smoke.py -q -> 7 passed`、`pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py -q -> 31 passed`、`py_compile` passed、`git diff --check` 仅 CRLF warning。 | 补足 behavior smoke、sidecar ping 和文档证据 |
| B-011 | 2026-06-09 21:03:12 | `5526945..3d6441b` | `npm --prefix frontend run test`、`npm --prefix frontend run build`、`pytest tests/test_ui_backend_contract.py tests/test_ui_backend_models.py tests/test_vue_tauri_acceptance_gaps.py tests/test_windows_packaging_smoke.py -q -> 29 passed`、`cargo check` passed。 | 修复复验协议、过滤、竞态和模型保护缺口 |
| B-012 | 2026-06-09 21:14:41 | `5526945..3d6441b` | `npm run verify:desktop -> 117 passed`、`npm run package:windows`、`pytest tests/test_windows_packaging_smoke.py -q -> 7 passed`、`pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py -q -> 31 passed`、`py_compile` passed、`git diff --check` 仅 CRLF warning。 | 同步复验文档和 commit 证据 |
| B-013 | 2026-06-09 21:51:10 | `3d6441b..8764f86` | 新增 B-013..B-017 任务并在 bugfix/design 记录第一波 B-002/B-004/B-006/B-008/B-010 ACTIONABLE_ISSUES；validate_spec.py docs\specs --workflow bugfix -> 34 passed；git status 仅 docs/specs 变更。 | 第一波存在 actionable issues，未启动对抗审查。 |
| B-014 | 2026-06-09 21:57:29 | `3d6441b..8764f86` | 补齐 Python/Rust manifest optional/nullable 元数据和 TS null envelope 类型；验证：pytest tests\test_ui_backend_contract.py tests\test_windows_packaging_smoke.py -q -> 17 passed；npm --prefix frontend run test -> Frontend behavior smoke checks passed；C:\Users\ny\.cargo\bin\cargo.exe check -> passed。 | cargo 未在当前 PATH，使用本机绝对路径 C:\Users\ny\.cargo\bin\cargo.exe。 |
| B-015 | 2026-06-09 22:00:45 | `3d6441b..8764f86` | Rust Shell32 picker 增加 OleInitialize/OleUninitialize；MTA RPC_E_CHANGED_MODE 时禁用 BIF_NEWDIALOGSTYLE 降级；验证：C:\Users\ny\.cargo\bin\cargo.exe check -> passed；pytest tests/test_windows_packaging_smoke.py -q -> 8 passed；npm --prefix frontend run test -> Frontend behavior smoke checks passed。 | 依据 Microsoft SHBrowseForFolder COM 初始化要求修复。 |
| B-016 | 2026-06-09 22:04:56 | `3d6441b..8764f86` | download_model 校验已知 Content-Length 的截断 EOF 并清理 .part；Vue onBeforeUnmount 复用 cancelModelDownload 停止 active 下载；验证：pytest tests/test_ui_backend_models.py tests/test_vue_tauri_acceptance_gaps.py -q -> 13 passed；npm --prefix frontend run test -> Frontend behavior smoke checks passed；npm --prefix frontend run build -> passed。 | 正式模型文件在中断和截断下载时均保持不变。 |
| B-017 | 2026-06-09 22:17:40 | `3d6441b..8764f86` | README/AGENTS/change.md 与 docs/specs 已同步；rg '5526945\\.\\.HEAD' docs/specs README.md AGENTS.md change.md -> no matches；npm run verify:desktop -> 118 passed；pytest tests/test_windows_packaging_smoke.py -q -> 8 passed；pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py -q -> 31 passed；npm run package:windows -> NSIS installer generated；validate_spec.py docs\specs --resume 和 --pre-acceptance -> OK。 | 文档证据提交后再次复查 resume/pre-acceptance。 |
| B-018 | 2026-06-09 22:50:10 | `3aa2578` | 记录 docs sync commit 3aa2578 并修复 B-017/B-018 grep 命令为完整 HEAD 字符串拼接，避免自匹配；PowerShell 构造 fixed-string 检查目标模式（`5526945..` + `HEAD`）-> no matches；change.md 已记录 B-018。 | 当前 docs-only 证据提交的最终 hash 通过 git log -1 复查，避免提交内容自引用 hash。 |
| B-019 | 2026-06-09 23:24:53 | 当前实现提交通过 `git log -1` 复查 | Added bridge-lifecycle stopJobById helper and behavior smoke assertions for exact job.stop command/payload/options; npm --prefix frontend run test -> passed; npm --prefix frontend run build -> passed; pytest tests/test_vue_tauri_acceptance_gaps.py -q -> 6 passed. | 修复第三轮第一波 B-016 验收发现 |
| B-020 | 2026-06-10 00:02:13 | 当前实现提交通过 `git log -1` 复查 | Handled current session job.failed as a terminal UI state and added frontend behavior smoke for current/foreign job.failed; npm --prefix frontend run test/build -> passed; pytest tests/test_vue_tauri_acceptance_gaps.py -q -> 6 passed; pytest tests/test_ui_backend_sessions.py tests/test_input_source_state.py tests/test_vue_tauri_acceptance_gaps.py -q -> 21 passed; pytest tests/test_ui_backend_models.py tests/test_vue_tauri_acceptance_gaps.py -q -> 13 passed; npm run verify:desktop -> 118 passed. | 修复第四轮第一波 B-003 验收发现 |
