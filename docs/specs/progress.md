# Spce workflow Progress

> **Workflow:** design-first
> **Mode:** strict
> **Status:** In Progress
> **Current Task:** T-002
> **Approval:** approved
> **Last Checkpoint:** 2026-06-11 13:58:19
> **Branch:** main
> **Last Known Commit:** 60f3a66

## Resume Summary
- Goal: 固化后端路由决策契约
- Approved specs: design.md, requirements.md, tasks.md
- Current task: T-002
- Next safe action: Run spec_status, then continue the current task.
- Blockers: n/a

## Active Task State
- Task ID: T-002
- Status: pending
- Started at: n/a
- Verification needed: cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_backend_routing_contract.py tests/test_ui_backend_contract.py tests/test_batch_backend_args.py -q => exit 0, 35 passed; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py -q => exit 0, 31 passed; cmd: git diff --check => exit 0 (line-ending warnings only)
- Files expected to change: `core/backend_router.py`, `batch/backend_options.py`, `apps/ui_backend.py`, `core/feature_layout.py`, `core/yolo_adapter.py`, `tests/test_backend_routing_contract.py`, `tests/test_ui_backend_contract.py`, `tests/test_batch_backend_args.py`

## Completed Work Log
| Task ID | Time | Commit/State | Verification | Notes |
|:---|:---|:---|:---|:---|
| - | - | - | - | - |
| T-001 | 2026-06-11 13:58:19 | 60f3a66 | cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_backend_routing_contract.py tests/test_ui_backend_contract.py tests/test_batch_backend_args.py -q => exit 0, 35 passed; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py -q => exit 0, 31 passed; cmd: git diff --check => exit 0 (line-ending warnings only) | 新增 core/backend_router.py 唯一路由决策点；UI bridge 和 batch helper 消费共享 router；更新 change.md。 |

## Recovery Notes
- Completed T-001
