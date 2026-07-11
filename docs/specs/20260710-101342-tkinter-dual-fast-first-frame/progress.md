# Spec workflow Progress

> **Workflow:** requirements-first
> **Mode:** strict
> **Status:** Completed
> **Current Task:** n/a
> **Approval:** approved
> **Last Checkpoint:** 2026-07-10 18:52:40
> **Branch:** main
> **Last Known Commit:** 0b24519

## Resume Summary
- Goal: 完成回归、真实性能验收说明和 change.md 交付记录
- Approved specs: product.md, architecture.md, tasks.md
- Current task: n/a
- Next safe action: Run pre-acceptance, then final acceptance.
- Blockers: n/a

## Active Task State
- Task ID: n/a
- Status: done
- Started at: n/a
- Verification needed: Final targeted Tkinter/MediaPipe/valid-mask regression 192 passed; earlier warmup/UI/recording suite 164 passed and delegate/benchmark/golden gate 35 passed; py_compile passed; git diff --check passed with CRLF warnings only; change.md updated at top; physical dual-camera 20-run P95 <=0.5s remains explicit hardware acceptance item with built-in timing logs
- Files expected to change: `change.md`, 本 spec progress/evidence

## Completed Work Log
| Task ID | Time | Commit/State | Verification | Notes |
|:---|:---|:---|:---|:---|
| — | — | — | — | 暂无完成任务 |
| T-001 | 2026-07-10 11:14:12 | 0b24519 | apps/camera_warmup.py + tests/test_camera_warmup.py；pytest 17 passed；py_compile 通过；git diff --check 通过；P1/P2 对抗审查问题已修复 | n/a |
| T-002 | 2026-07-10 11:47:58 | 0b24519 | CameraWarmupPool dual selector/lifecycle integration; deterministic forward/reverse same-index ownership tests; nonblocking cancel reaper; startup wait uses stop_event and one 5s deadline; pytest 121 passed with 2 known T-003 cases deselected; py_compile and git diff --check passed; adversarial review found no remaining T-002 blocker | n/a |
| T-003 | 2026-07-10 18:36:50 | 0b24519 | Atomic DualPreviewPacket queue and same-tick Tk render; generation/stage/render barriers; live raw pump during serial pipeline init; recording gate and zero raw writes; startup metrics; stop/close/failure exactly-once; claim bound to expected generations and stop_event; all retirement paths reaped with thread-start rollback; pytest 164 passed; py_compile and diff-check passed; adversarial P1/P2 findings fixed | n/a |
| T-004 | 2026-07-10 18:51:33 | 0b24519 | Isolated Python 3.13.9 venv A/B on 6 real videos, 5 warmup + 60 timed frames per case; 0.10.35 CPU failed >=10% gate and peak RSS increased 15-19%; all 12 GPU requests fell back to CPU because Windows build disables GPU; retained mediapipe 0.10.31 and no GPU UI; delegate/S5/golden pytest 35 passed; py_compile and diff-check passed | n/a |
| T-005 | 2026-07-10 18:52:40 | 0b24519 | Final targeted Tkinter/MediaPipe/valid-mask regression 192 passed; earlier warmup/UI/recording suite 164 passed and delegate/benchmark/golden gate 35 passed; py_compile passed; git diff --check passed with CRLF warnings only; change.md updated at top; physical dual-camera 20-run P95 <=0.5s remains explicit hardware acceptance item with built-in timing logs | n/a |

## Recovery Notes
- Completed T-005
