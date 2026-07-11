# -*- coding: utf-8 -*-
from __future__ import annotations

from core.exam_roster import ExamCandidate
from core.exam_session import ExamSession, ExamSessionConfig


def _cands(n: int = 2) -> list[ExamCandidate]:
    return [
        ExamCandidate(i + 1, f"S{i+1}", f"名{i+1}")
        for i in range(n)
    ]


def _kinds(cmds) -> list[str]:
    return [c.kind for c in cmds]


def test_happy_path_two_students() -> None:
    s = ExamSession(ExamSessionConfig(post_call_guard_s=1.0, inter_student_gap_s=0.5))
    s.load_roster(_cands(2))
    assert s.phase == "ready"
    cmds = s.handle("start_exam", now=0.0, run_id="r1")
    assert s.phase == "calling"
    assert "ANNOUNCE" in _kinds(cmds)
    assert "SCHEDULE_CALL_GUARD" in _kinds(cmds)

    cmds = s.handle("tick", now=1.0)
    assert s.phase == "wait_enter"
    assert "ARM_OCCUPANCY" in _kinds(cmds)

    cmds = s.handle("enter_stable", now=2.0)
    assert s.phase == "recording"
    assert "BEGIN_SEGMENT" in _kinds(cmds)

    cmds = s.handle("empty_stable", now=10.0)
    assert s.phase == "finishing"
    assert "END_SEGMENT" in _kinds(cmds)

    cmds = s.handle("record_stopped", now=10.1)
    assert s.pointer == 1
    # gap then call
    cmds = s.handle("tick", now=10.1 + 0.5)
    assert s.phase == "calling"
    assert any("名2" in (c.payload.get("text") or "") for c in cmds if c.kind == "ANNOUNCE")


def test_skip_before_record() -> None:
    s = ExamSession(ExamSessionConfig(inter_student_gap_s=0.0, post_call_guard_s=0.0))
    s.load_roster(_cands(2))
    s.handle("start_exam", now=0.0)
    s.handle("tick", now=0.0)  # guard 0 → wait_enter
    cmds = s.handle("skip_current", now=1.0)
    assert s.rows[0].status == "skipped"
    assert s.pointer == 1
    # gap 0 → immediate next on tick
    cmds = s.handle("tick", now=1.0)
    assert s.phase == "calling"
    assert s.current.candidate.student_id == "S2"


def test_skip_while_recording_discards() -> None:
    s = ExamSession()
    s.load_roster(_cands(1))
    s.handle("start_exam", now=0.0)
    s.handle("call_guard_elapsed", now=2.0)
    s.handle("enter_stable", now=3.0)
    cmds = s.handle("skip_current", now=4.0)
    assert "DISCARD_SEGMENT" in _kinds(cmds)
    assert s.phase == "finishing"


def test_force_finish_from_recording() -> None:
    s = ExamSession()
    s.load_roster(_cands(1))
    s.handle("start_exam", now=0.0)
    s.handle("call_guard_elapsed", now=1.5)
    s.handle("enter_stable", now=2.0)
    cmds = s.handle("force_finish_current", now=2.1)  # < min_record 也允许
    assert "END_SEGMENT" in _kinds(cmds)
    assert s.phase == "finishing"


def test_pause_resume_wait_enter() -> None:
    s = ExamSession()
    s.load_roster(_cands(1))
    s.handle("start_exam", now=0.0)
    s.handle("call_guard_elapsed", now=2.0)
    assert s.phase == "wait_enter"
    s.handle("pause", now=3.0)
    assert s.phase == "paused"
    cmds = s.handle("resume", now=4.0)
    assert s.phase == "wait_enter"
    assert "ARM_OCCUPANCY" in _kinds(cmds)


def test_complete_exports() -> None:
    s = ExamSession(ExamSessionConfig(inter_student_gap_s=0.0, post_call_guard_s=0.0))
    s.load_roster(_cands(1))
    s.handle("start_exam", now=0.0)
    s.handle("tick", now=0.0)
    s.handle("enter_stable", now=1.0)
    s.handle("empty_stable", now=5.0)
    cmds = s.handle("record_stopped", now=5.1)
    assert s.phase == "completed"
    assert "EXPORT" in _kinds(cmds)
