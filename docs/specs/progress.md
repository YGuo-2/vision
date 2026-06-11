# Spce workflow Progress

> **Workflow:** design-first
> **Mode:** strict
> **Status:** In Progress
> **Current Task:** T-003
> **Approval:** approved
> **Last Checkpoint:** 2026-06-11 14:54:00
> **Branch:** main
> **Last Known Commit:** b795674

## Resume Summary
- Goal: 打通 Rust/Python 双侧任务状态机和取消语义
- Approved specs: design.md, requirements.md, tasks.md
- Current task: T-003
- Next safe action: Run spec_status, then continue the current task.
- Blockers: n/a

## Active Task State
- Task ID: T-003
- Status: pending
- Started at: n/a
- Verification needed: cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_ui_backend_sessions.py tests/test_ui_backend_contract.py -q => exit 0, 24 passed; cmd: npm --prefix frontend run test => exit 0, Frontend behavior smoke checks passed; cmd: git diff --check => exit 0 (line-ending warnings only)
- Files expected to change: `frontend/src-tauri/src/lib.rs`, `apps/ui_backend.py`, `frontend/src/bridge-state.ts`, `frontend/src/bridge-lifecycle.ts`, `tests/test_ui_backend_sessions.py`, `tests/test_ui_backend_contract.py`, `frontend/scripts/frontend-smoke.mjs`

## Completed Work Log
| Task ID | Time | Commit/State | Verification | Notes |
|:---|:---|:---|:---|:---|
| - | - | - | - | - |
| T-001 | 2026-06-11 13:58:19 | 60f3a66 | cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_backend_routing_contract.py tests/test_ui_backend_contract.py tests/test_batch_backend_args.py -q => exit 0, 35 passed; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py -q => exit 0, 31 passed; cmd: git diff --check => exit 0 (line-ending warnings only) | 新增 core/backend_router.py 唯一路由决策点；UI bridge 和 batch helper 消费共享 router；更新 change.md。 |
| T-002 | 2026-06-11 14:12:26 | 4541e61 | cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_yolo_backend_contract.py tests/test_yolo_landmark_mapping.py tests/test_rule_availability.py tests/test_ui_backend_analysis.py -q => exit 0, 46 passed; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py -q => exit 0, 31 passed; cmd: git diff --check => exit 0 (line-ending warnings only) | YOLO adapter 边界层与序列 artifact 统一补齐 raw_layout/feature_layout/capability/score_authorized/display_scope；UI camelCase route 与 COCO17 missing capability 测试上锁；更新 change.md。 |
| T-004 | 2026-06-11 14:35:56 | f3e50db | cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_ui_backend_sessions.py tests/test_windows_packaging_smoke.py -q => exit 0, 16 passed; cmd: npm run verify:tauri => exit 0, cargo check passed; cmd: npm --prefix frontend run test => exit 0, Frontend behavior smoke checks passed; cmd: git diff --check => exit 0 (line-ending warnings only) | 实现 Python 127.0.0.1 TCP length-prefixed latest-frame 通道与 Tauri raw IPC latest_frame；session.frame JSON 不再携带 image/base64/bytes，仅传 frame handle、token 和指标；更新 change.md 基线记录。 |
| T-005 | 2026-06-11 14:44:51 | 7bfe692 | cmd: npm --prefix frontend run test => exit 0, Frontend behavior smoke checks passed; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_vue_tauri_acceptance_gaps.py -q => exit 0, 7 passed; cmd: git diff --check => exit 0 (line-ending warnings only) | Vue 预览迁移到 Canvas/ImageBitmap；requestAnimationFrame 合并 latest frame；移除 previewImage、object URL 和 img 帧展示路径；更新 change.md 基线记录。 |
| T-006 | 2026-06-11 14:54:00 | b795674 | cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_ui_backend_sessions.py tests/test_ui_backend_contract.py -q => exit 0, 24 passed; cmd: npm --prefix frontend run test => exit 0, Frontend behavior smoke checks passed; cmd: git diff --check => exit 0 (line-ending warnings only) | 统一 session/model download/analysis 主动停止和晚到事件清理；job.stop 缺失/未知 jobId 结构化错误测试；更新 change.md。 |

## Recovery Notes
- Completed T-006
