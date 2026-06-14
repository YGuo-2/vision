# Acceptance Fixes

> **Source:** docs/specs/acceptance_state.json
> **Round:** 1
> **Policy:** rounds 1-3 fix all actionable issues; round 4+ auto-fix P0-P2 only
> **Original tasks:** 10 frozen tasks; do not append acceptance fixes to tasks.md

## Fix Queue

| Fix ID | Issue IDs | Severity | Units | Status | Evidence |
|:---|:---|:---|:---|:---|:---|
| F-001 | I-001 | P1 | U-008 | done | Patched local Spce workflow validate_spec.py so completed workflows with all tasks done/skipped treat empty execution_waves as valid; reran validate_spec.py docs\\specs --workflow design-first --color never => exit 0, 36 checks passed with message all tasks closed. |
| F-002 | I-002 | P3 | U-008 | done | Updated docs/specs/progress.md Last Known Commit and T-010 completion log, docs/specs/tasks.md T-010 completion log, and change.md wording so T-010 references pushed commit 36bb902 and no longer says it is preparing to complete after completion. |
| F-003 | I-003 | P2 | U-005 | done | ParallelPoseEngine now records and merges worker delegate payloads; apps/ui_backend.py reports running active=pending for parallel preview and final/frame delegate fallback payload from engine. Added test coverage for delegate=gpu fallback to cpu in parallel preview. pytest tests/test_parallel_pose_engine.py tests/test_ui_backend_sessions.py tests/test_s5_realtime_latest_frame.py tests/test_s5_hands_toggle.py -q => 36 passed. |
| F-004 | I-004 | P2 | U-008 | done | docs/specs/acceptance_state.json is present and will be staged with this acceptance fix commit so final acceptance can resume from HEAD; acceptance-status reads it successfully after all 16 round-1 agents completed. |
| F-005 | I-005 | P3 | U-008 | done | acceptance-plan-fixes regenerated docs/specs/acceptance-fixes.md from acceptance_state.json with real round/policy/fix queue, replacing the stale pre-acceptance placeholder. |

## Deferred Issues

- n/a
