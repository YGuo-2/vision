# Spce workflow Progress

> **Workflow:** bugfix
> **Mode:** strict
> **Status:** Completed
> **Current Task:** n/a
> **Approval:** approved
> **Last Checkpoint:** 2026-06-09 20:28:51
> **Branch:** main
> **Last Known Commit:** 当前最终提交

## Resume Summary
- Goal: 补足交互级验证、Windows 运行级证据和文档同步
- Approved specs: bugfix.md, design.md, tasks.md
- Current task: n/a
- Next safe action: Run pre-acceptance, then final acceptance.
- Blockers: n/a

## Active Task State
- Task ID: n/a
- Status: done
- Started at: n/a
- Verification needed: 补足前端 behavior smoke、verify 文案、packaged sidecar ping 和文档证据；验证：npm run verify:desktop -> frontend build, Frontend behavior smoke, cargo check, py_compile, 116 desktop regression tests passed；py_compile apps/app_ui.py apps/ui_backend.py core/vision_pipeline.py passed；pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py -q -> 31 passed；git diff --check -> only CRLF warnings；npm run package:windows produced NSIS installer；pytest tests/test_windows_packaging_smoke.py -q -> 7 passed including generated sidecar bridge.ping.
- Files expected to change: `frontend/scripts/frontend-smoke.mjs`, `scripts/verify-desktop-stack.ps1`, `tests/test_windows_packaging_smoke.py`, `docs/specs/`, `change.md`

## Completed Work Log
| Task ID | Time | Commit/State | Verification | Notes |
|:---|:---|:---|:---|:---|
| B-001 | 2026-06-09 18:49:49 | f0b0cf1 | 新增 tests/test_vue_tauri_acceptance_gaps.py，并更新 bridge/job 契约测试；运行 .\\.venv\\Scripts\\python.exe -m pytest tests\\test_ui_backend_contract.py tests\\test_ui_backend_jobs.py tests\\test_vue_tauri_acceptance_gaps.py -q 得到 9 failed / 11 passed，失败点对应 final acceptance 缺口：manifest jobId/sessionId、bad request requestId、completed job stop、Vue analysis/model/download/dir picker/event/raw JSON/frontend test coverage。 | 首轮缺口复现 |
| B-002 | 2026-06-09 18:54:12 | f0b0cf1 | 修复 apps/ui_backend.py 与 frontend/src-tauri/src/lib.rs 的 message contract、错误 requestId 保留和 active-only job.stop；更新阻塞式 job.stop 测试。验证：.\\.venv\\Scripts\\python.exe -m pytest tests\\test_ui_backend_contract.py tests\\test_ui_backend_jobs.py -q -> 15 passed；frontend/src-tauri cargo check passed。 | 协议修复 |
| B-003 | 2026-06-09 19:00:38 | f0b0cf1 | 修复 Vue 输入源 none/camera/video 三态、完整 raw JSON envelope、当前 session/job 事件过滤、预览帧 UI 节流和实时流进度文案。验证：npm --prefix frontend run build passed；pytest tests\\test_ui_backend_sessions.py tests\\test_input_source_state.py -q -> 15 passed；tests\\test_vue_tauri_acceptance_gaps.py 中 event/raw JSON 覆盖项已转绿，剩余失败归属 B-004/B-005/B-006/B-007。 | 初轮状态修复 |
| B-005 | 2026-06-09 19:10:10 | f0b0cf1 | 补齐 Vue 动作分析面板：template.create、analysis.run、模板路径/基准视频/目标视频/startFrame/endFrame/worker/previewOut、doTechEval、stance/viewHint/debugVideo、结果展示和 job.stop。验证：npm --prefix frontend run build passed；pytest tests\\test_ui_backend_analysis.py tests\\test_tech_eval_contract.py tests\\test_pose33_v3_golden.py -q -> 30 passed；tests\\test_vue_tauri_acceptance_gaps.py 中 analysis/tech eval 覆盖项已转绿。 | 动作分析迁移 |
| B-006 | 2026-06-09 19:14:02 | f0b0cf1 | 补齐 Vue 设置/模型管理面板：modelsDir/path/sizeMb/installed/active 展示、model.download 单模型/全部缺失、model.progress、cancelModelDownload/job.stop。验证：npm --prefix frontend run build passed；pytest tests\\test_ui_backend_models.py tests\\test_ui_backend_contract.py -q -> 14 passed；tests\\test_vue_tauri_acceptance_gaps.py 中 settings/model download 覆盖项已转绿。 | 模型管理迁移 |
| B-004 | 2026-06-09 19:20:07 | f0b0cf1 | 补齐录制目录选择：Vue selectRecordDir 调用受限 Tauri select_directory，Rust 使用 Windows Shell32 folder picker FFI，无新增依赖、不走任意 shell；recordDir 默认留空，让 Python bridge 回退 outputs_dir()。验证：cargo check passed；npm --prefix frontend run build passed；pytest tests\\test_ui_backend_sessions.py tests\\test_recording_controller.py tests\\test_vue_tauri_acceptance_gaps.py -q 中目录覆盖项转绿，剩余唯一失败为 B-007 前端测试入口。 | 录制目录迁移 |
| B-007 | 2026-06-09 19:28:42 | f0b0cf1 | 强化验证集合：新增 frontend/scripts/frontend-smoke.mjs 与 npm --prefix frontend run test；verify-desktop-stack.ps1 接入前端 smoke、纳入 tests/test_vue_tauri_acceptance_gaps.py，并检查原生命令 exit code。验证：npm --prefix frontend run test passed；pytest tests\\test_vue_tauri_acceptance_gaps.py -q -> 5 passed；npm run verify:desktop -> frontend build/test, cargo check, py_compile, 114 desktop regression tests passed；pytest tests\\test_windows_packaging_smoke.py -q -> 6 passed；npm run package:windows produced NSIS installer。 | 初轮验证集合 |
| B-008 | 2026-06-09 19:35:38 | f0b0cf1 | 同步 README.md、AGENTS.md、change.md 与 bugfix 规范状态，记录前端 smoke、verify:desktop、packaging 和核心回归证据。验证：git diff --check 无 whitespace error（仅 LF/CRLF warning）；py_compile apps/app_ui.py apps/ui_backend.py core/vision_pipeline.py passed；pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py -q -> 31 passed；pytest tests/test_windows_packaging_smoke.py -q -> 6 passed；npm run verify:desktop -> frontend build/test, cargo check, py_compile, 114 desktop regression tests passed。 | 初轮文档同步 |
| B-009 | 2026-06-09 20:18:46 | 当前最终提交 | 修复 Vue 未知总帧进度、analysis/template/model status job 过滤和模型下载失败展示；新增 frontend/src/bridge-state.ts 行为助手与 behavior smoke；验证：npm --prefix frontend run test -> Frontend behavior smoke checks passed；npm --prefix frontend run build passed；pytest tests/test_ui_backend_models.py tests/test_vue_tauri_acceptance_gaps.py -q -> 11 passed。 | 首轮验收追加修复 |
| B-010 | 2026-06-09 20:28:51 | 当前最终提交 | 补足前端 behavior smoke、verify 文案、packaged sidecar ping 和文档证据；验证：npm run verify:desktop -> frontend build, Frontend behavior smoke, cargo check, py_compile, 116 desktop regression tests passed；py_compile apps/app_ui.py apps/ui_backend.py core/vision_pipeline.py passed；pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py -q -> 31 passed；git diff --check -> only CRLF warnings；npm run package:windows produced NSIS installer；pytest tests/test_windows_packaging_smoke.py -q -> 7 passed including generated sidecar bridge.ping. | 证据链收口 |

## Recovery Notes
- Completed B-010
