# Acceptance Fixes

> **Source:** E:/CodeProject/vision/docs/specs/20260710-101342-tkinter-dual-fast-first-frame/acceptance_state.json
> **Round:** 1
> **Policy:** rounds 1-3 fix all actionable issues; round 4+ auto-fix P0-P2 only
> **Original tasks:** 5 frozen tasks; do not append acceptance fixes to tasks.md

## Fix Queue

| Fix ID | Issue IDs | Severity | Units | Status | Evidence |
|:---|:---|:---|:---|:---|:---|
| F-001 | I-001 | P1 | U-001 | done | Removed all cross-thread force-release paths; reapers request optional interrupt and only the owner reader releases; strict active-read test passes. |
| F-002 | I-002 | P2 | U-001 | done | Retired same-index open/read is quarantined and immediate retry is rejected without new factory calls; app exclusive lock acquisition is stop_event-cancellable; blocked-open test passes. |
| F-003 | I-003 | P3 | U-003 | done | Metrics now require terminal outcome before normal emission; running emits after claim and failed claim emits once from finally; regression test passes. |
| F-004 | I-004 | P3 | U-001 | done | Release is marked complete only after success; failures retain cap/error for reaper/close retry; fail-once release test passes. |
| F-005 | I-005 | P2 | U-002 | done | Legacy preopen tracks pending index and returns for same-index ready/in-flight requests; idempotency tests pass. |
| F-006 | I-006 | P4 | U-003 | done | _post_done removes both render event and startup metrics for completed generation; lifecycle test asserts empty mappings. |
| F-007 | I-007 | P2 | U-004 | done | tasks.md completion log and progress.md Last Known Commit now reference implementation commit a3a605f. |
| F-008 | I-008 | P3 | U-004 | done | Report now includes 0.10.31 six-video active=gpu ratios 1.0020x pose-only and 1.0126x pose+hands against thresholds. |

## Deferred Issues

- n/a
