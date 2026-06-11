# Spce workflow Progress

> **Workflow:** design-first
> **Mode:** strict
> **Status:** In Progress
> **Current Task:** T-004
> **Approval:** approved
> **Last Checkpoint:** 2026-06-11 14:12:26
> **Branch:** main
> **Last Known Commit:** 4541e61

## Resume Summary
- Goal: 补齐 YOLO 能力和评分授权元数据
- Approved specs: design.md, requirements.md, tasks.md
- Current task: T-004
- Next safe action: Run spec_status, then continue the current task.
- Blockers: n/a

## Active Task State
- Task ID: T-004
- Status: pending
- Started at: n/a
- Verification needed: cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_yolo_backend_contract.py tests/test_yolo_landmark_mapping.py tests/test_rule_availability.py tests/test_ui_backend_analysis.py -q => exit 0, 46 passed; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py -q => exit 0, 31 passed; cmd: git diff --check => exit 0 (line-ending warnings only)
- Files expected to change: `core/yolo_adapter.py`, `batch/batch_dual_compare.py`, `batch/batch_tech_eval.py`, `apps/ui_backend.py`, `tests/test_yolo_backend_contract.py`, `tests/test_rule_availability.py`, `tests/test_ui_backend_analysis.py`

## Completed Work Log
| Task ID | Time | Commit/State | Verification | Notes |
|:---|:---|:---|:---|:---|
| - | - | - | - | - |
| T-001 | 2026-06-11 13:58:19 | 60f3a66 | cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_backend_routing_contract.py tests/test_ui_backend_contract.py tests/test_batch_backend_args.py -q => exit 0, 35 passed; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py -q => exit 0, 31 passed; cmd: git diff --check => exit 0 (line-ending warnings only) | 新增 core/backend_router.py 唯一路由决策点；UI bridge 和 batch helper 消费共享 router；更新 change.md。 |
| T-002 | 2026-06-11 14:12:26 | 4541e61 | cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_yolo_backend_contract.py tests/test_yolo_landmark_mapping.py tests/test_rule_availability.py tests/test_ui_backend_analysis.py -q => exit 0, 46 passed; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py -q => exit 0, 31 passed; cmd: git diff --check => exit 0 (line-ending warnings only) | YOLO adapter 边界层与序列 artifact 统一补齐 raw_layout/feature_layout/capability/score_authorized/display_scope；UI camelCase route 与 COCO17 missing capability 测试上锁；更新 change.md。 |

## Recovery Notes
- Completed T-002
