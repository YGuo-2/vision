# Acceptance Fixes

> **Source:** E:/CodeProject/vision/docs/specs/20260709-233221-tkinter-dual-record-auto-compare/acceptance_state.json
> **Round:** 4
> **Policy:** rounds 1-3 fix all actionable issues; round 4+ auto-fix P0-P2 only
> **Original tasks:** 4 frozen tasks; do not append acceptance fixes to tasks.md

## Fix Queue

| Fix ID | Issue IDs | Severity | Units | Status | Evidence |
|:---|:---|:---|:---|:---|:---|
| F-001 | I-001 | P3 | U-001 | done | Moved cancellation check after legacy pass-through classification; pre-cancelled None/missing AVI/MP4 return unchanged; existing AVI still cancels before ffmpeg; test_video_writer_transcode.py 11 passed. |
| F-002 | I-002 | P3 | U-002 | done | submit now only deduplicates/enqueues and returns; worker atomically writes queued before callback on dual-recording-postprocess thread; blocking callback regression verifies <0.1s submit and correct thread; postprocess suite 29 passed. |
| F-003 | I-003 | P2 | U-003 | done | Dual toggle now atomically detects errors/state divergence and finalizes old pair without new stamp or toggling peer; deterministic primary writer failure retains old segment paths/id and submits once; lifecycle+controls 41 passed. |
| F-004 | I-004 | P2 | U-003 | done | Close deadline now set before all potentially blocking work; daemon app-close-prepare serializes finalize/cancel/release while Tk only bounded-polls and skips processor close until prep finishes; deterministic blocked submit/cancel tests prove immediate return/deadline; lifecycle 33 passed. |
| F-005 | I-005 | P2 | U-001 | done | DTW cancellation now propagates through local-cost, DP rows, traceback, rules, front/side scoring and final return; cancellation during front score skips side score and raises InterruptedError; compare_dual_streams plus pose33_v3 golden: 31 passed. |
| F-006 | I-006 | P2 | U-003 | done | Dual worker outer finally now closes both MediaPipe pipelines, releases both captures and destroys OpenCV windows before unified recording finalization on annotate/write exceptions; dual/lifecycle/control suites: 98 passed. |
| F-007 | I-007 | P3 | U-003 | done | Record toggle now returns before Tk reads when closing or stop is set, and close immediately disables all recording controls during bounded polling; dual/lifecycle/control suites: 98 passed. |
| F-008 | I-008 | P2 | U-004 | done | Rebuilt history from checkpoint evidence: 8f0c9f8 contains only seven verified pre-spec dual-camera paths and no temp artifacts; implementation 09aa101 has parent 8f0c9f8 and isolates the approved auto-compare delta plus acceptance repairs; b931222 remains on safety branch. |
| F-009 | I-009 | P3 | U-004 | done | Because v0.2.0 has no historical log-rebind command, only generated completion metadata was repaired: tasks/progress task bodies and digest remain frozen, all four completion rows and Last Known Commit now point to implementation 09aa101ea55421208e81739a6e88ccd6572f8656; sync-check has no issues. |
| F-010 | I-010 | P2 | U-002 | done | Snapshot validation resolves both sources under segment_dir and rejects cross-segment front or side paths as recording_path_mismatch before transcode/compare; recording_postprocess suite: 35 passed. |
| F-011 | I-011 | P3 | U-002 | done | cancel_all now only marks cancellation and returns promptly; coordinator thread publishes exactly one terminal callback per segment while cancelled JSON may enrich converted paths without re-notifying; recording_postprocess suite: 35 passed. |
| F-012 | I-012 | P3 | U-002 | done | Transcode dependency exceptions are wrapped as transcode_failed while InterruptedError remains cancellation; OSError regression confirms compare is not called; recording_postprocess suite: 35 passed. |
| F-013 | I-013 | P3 | U-002 | done | Added dedicated persistence lock; coordinator state lock now only guards pre/post state checks, never disk I/O or callbacks. Post-write cancellation recheck suppresses stale queued/completed notifications and finalizes cancelled. Deterministic blocked-write submit/cancel races pass; postprocess suite 38 passed. |
| F-014 | I-014 | P2 | U-003 | done | _on_record_stop and _refresh_recording_status now return before Tk or recording/finalize locks when closing or stop is set, so scheduled ticks cannot re-enable controls or exceed close budget. Held-lock lifecycle regressions pass; lifecycle/control/dual suites 100 passed. |
| F-015 | I-015 | P3 | U-002 | done | close() now detects coordinator worker callbacks, completes cancel/sentinel setup and returns without self-join; callback remainder executes and worker later exits normally. Deterministic callback reentrancy regression passes; postprocess suite 40 passed. |
| F-016 | I-016 | P3 | U-002 | done | Cancelled enrichment write failures now preserve the already-published cancelled result and are suppressed without failed/result_write_failed notification; initial write failures remain unchanged. Byte-for-byte preservation and exactly-one terminal regression pass; postprocess suite 40 passed. |
| F-017 | I-017 | P3 | U-003 | done | Recording status refresh now guards only closing before pair lock/Tk access; with stop_evt set but non-closing it reads worker-finalized idle state, clears stale recording text and disables stop control. Explicit record-stop retains closing/stop guard. Tk lifecycle/control/dual suites: 101 passed. |
| F-018 | I-018 | P2 | U-002 | done | submit resolves and normcases segment_dir outside the state lock, then atomically reserves canonical directory ownership for one segment_id for processor lifetime. Distinct IDs using the same directory or .. alias are rejected before queue/callback/write; first result remains byte-identical. Postprocess suite: 41 passed; py_compile/diff passed. |
| F-019 | I-019 | P2 | U-003 | done | Dual-camera worker now posts done exactly once from the outermost finally after pipeline/capture/OpenCV cleanup and recording-pair finalization, covering normal, device/init failure, annotate and writer exceptions; runtime-error regression asserts both resource cleanup and done notification. Dual-camera suite: 54 passed; py_compile passed. |

## Deferred Issues

- n/a
