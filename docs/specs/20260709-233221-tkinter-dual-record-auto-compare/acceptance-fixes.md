# Acceptance Fixes

> **Source:** E:/CodeProject/vision/docs/specs/20260709-233221-tkinter-dual-record-auto-compare/acceptance_state.json
> **Round:** 1
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

## Deferred Issues

- n/a
