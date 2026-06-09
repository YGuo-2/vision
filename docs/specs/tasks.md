# Bugfix 任务清单 (Task Breakdown)

> **问题名称：** Vue/Tauri 迁移最终验收缺口修复
> **关联规范：** `docs/specs/bugfix.md` · `docs/specs/design.md`
> **状态：** Completed
> **当前任务：** n/a
> **进度：** 8 / 8 已完成
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

---

## 风险标记

| 任务 ID | 风险类别 | 风险描述 | 审查要求 |
|:---|:---|:---|:---|
| B-002 | 协议/生命周期 | 错误 envelope 和 stop 语义影响全部长任务 | 需契约测试和 Tauri 边界检查 |
| B-003 | 性能/状态一致性 | 高频帧和 stale event 可能影响识别线程与 UI 状态 | 需节流和 stale event 测试 |
| B-005 | 评分边界 | 技术评估 UI 可能误触算法或 YOLO 边界 | 需 golden/valid_mask/tech_eval contract |
| B-006 | 下载/文件完整性 | 模型下载取消涉及 `.part` 清理和正式文件保护 | 需 model_manager 回归 |
| B-007 | 打包/安全 | Tauri sidecar、dialog 和 capabilities 不能扩大 shell 面 | 需 packaging smoke 和安全审查 |

---

## 完成日志

| 任务 ID | 完成时间 | Commit Hash | 验证证据 | 备注 |
|:---|:---|:---|:---|:---|
| — | — | — | — | 暂无完成任务 |
