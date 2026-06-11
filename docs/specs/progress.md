# Spce workflow Progress

> **Workflow:** design-first
> **Mode:** strict
> **Status:** In Progress
> **Current Task:** T-005
> **Approval:** approved
> **Last Checkpoint:** 2026-06-11 14:35:56
> **Branch:** main
> **Last Known Commit:** f3e50db

## Resume Summary
- Goal: 设计并实现二进制 latest-frame 预览帧通道
- Approved specs: design.md, requirements.md, tasks.md
- Current task: T-005
- Next safe action: Run spec_status, then continue the current task.
- Blockers: n/a

## Active Task State
- Task ID: T-005
- Status: pending
- Started at: n/a
- Verification needed: cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_ui_backend_sessions.py tests/test_windows_packaging_smoke.py -q => exit 0, 16 passed; cmd: npm run verify:tauri => exit 0, cargo check passed; cmd: npm --prefix frontend run test => exit 0, Frontend behavior smoke checks passed; cmd: git diff --check => exit 0 (line-ending warnings only)
- Files expected to change: `frontend/src-tauri/src/lib.rs`, `apps/ui_backend.py`, `tests/test_ui_backend_sessions.py`, `tests/test_windows_packaging_smoke.py`, `frontend/scripts/frontend-smoke.mjs`

## Completed Work Log
| Task ID | Time | Commit/State | Verification | Notes |
|:---|:---|:---|:---|:---|
| - | - | - | - | - |
| T-001 | 2026-06-11 13:58:19 | 60f3a66 | cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_backend_routing_contract.py tests/test_ui_backend_contract.py tests/test_batch_backend_args.py -q => exit 0, 35 passed; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py -q => exit 0, 31 passed; cmd: git diff --check => exit 0 (line-ending warnings only) | 新增 core/backend_router.py 唯一路由决策点；UI bridge 和 batch helper 消费共享 router；更新 change.md。 |
| T-002 | 2026-06-11 14:12:26 | 4541e61 | cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_yolo_backend_contract.py tests/test_yolo_landmark_mapping.py tests/test_rule_availability.py tests/test_ui_backend_analysis.py -q => exit 0, 46 passed; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py -q => exit 0, 31 passed; cmd: git diff --check => exit 0 (line-ending warnings only) | YOLO adapter 边界层与序列 artifact 统一补齐 raw_layout/feature_layout/capability/score_authorized/display_scope；UI camelCase route 与 COCO17 missing capability 测试上锁；更新 change.md。 |
| T-004 | 2026-06-11 14:35:56 | f3e50db | cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_ui_backend_sessions.py tests/test_windows_packaging_smoke.py -q => exit 0, 16 passed; cmd: npm run verify:tauri => exit 0, cargo check passed; cmd: npm --prefix frontend run test => exit 0, Frontend behavior smoke checks passed; cmd: git diff --check => exit 0 (line-ending warnings only) | 实现 Python 127.0.0.1 TCP length-prefixed latest-frame 通道与 Tauri raw IPC latest_frame；session.frame JSON 不再携带 image/base64/bytes，仅传 frame handle、token 和指标；更新 change.md 基线记录。 |

## Recovery Notes
- Completed T-004
