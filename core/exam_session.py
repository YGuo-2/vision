# -*- coding: utf-8 -*-
"""考试编排纯状态机（无 Tk / 无 OpenCV）。

契约见 docs/exam_system_design.md §6.6。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from core.exam_roster import ExamCandidate, ExamResultRow, local_timestamp

ExamPhase = Literal[
    "idle",
    "ready",
    "calling",
    "wait_enter",
    "recording",
    "finishing",
    "completed",
    "paused",
    "aborted",
]

ExamCommandKind = Literal[
    "ANNOUNCE",
    "ARM_OCCUPANCY",
    "DISARM_OCCUPANCY",
    "BEGIN_SEGMENT",
    "END_SEGMENT",
    "DISCARD_SEGMENT",
    "UPDATE_ROW",
    "SCHEDULE_CALL_GUARD",
    "SCHEDULE_INTER_GAP",
    "ADVANCE_POINTER",
    "EXPORT",
    "UI_LOCK_MANUAL_RECORD",
    "UI_UNLOCK_MANUAL_RECORD",
    "BIND_SEGMENT_PENDING",
]


@dataclass(frozen=True)
class ExamCommand:
    kind: ExamCommandKind
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExamSessionConfig:
    post_call_guard_s: float = 1.5
    inter_student_gap_s: float = 2.0
    enter_stable_s: float = 0.8
    empty_hold_s: float = 2.0
    min_record_s: float = 3.0


@dataclass
class ExamSession:
    config: ExamSessionConfig = field(default_factory=ExamSessionConfig)
    phase: ExamPhase = "idle"
    rows: list[ExamResultRow] = field(default_factory=list)
    pointer: int = 0
    paused_from: ExamPhase | None = None
    # 定时：单调时钟由外部驱动
    call_guard_deadline: float | None = None
    inter_gap_deadline: float | None = None
    record_started_mono: float | None = None
    run_id: str = ""
    locked: bool = False

    def load_roster(self, candidates: list[ExamCandidate]) -> list[ExamCommand]:
        self.rows = [
            ExamResultRow(candidate=c, attempt_index=1, is_scoring_row=True)
            for c in candidates
        ]
        self.pointer = 0
        self.phase = "ready" if self.rows else "idle"
        self.paused_from = None
        self.call_guard_deadline = None
        self.inter_gap_deadline = None
        self.record_started_mono = None
        return []

    @property
    def current(self) -> ExamResultRow | None:
        if 0 <= self.pointer < len(self.rows):
            return self.rows[self.pointer]
        return None

    def handle(self, event: str, **kw: Any) -> list[ExamCommand]:
        handler = {
            "start_exam": self._on_start_exam,
            "call_guard_elapsed": self._on_call_guard_elapsed,
            "enter_stable": self._on_enter_stable,
            "empty_stable": self._on_empty_stable,
            "record_started": self._on_record_started,
            "record_stopped": self._on_record_stopped,
            "skip_current": self._on_skip,
            "force_finish_current": self._on_force_finish,
            "pause": self._on_pause,
            "resume": self._on_resume,
            "abort_exam": self._on_abort,
            "tick": self._on_tick,
            "begin_failed": self._on_begin_failed,
        }.get(event)
        if handler is None:
            return []
        return handler(**kw)

    # --- events ---

    def _first_pending_index(self) -> int | None:
        """下一个可叫号行：优先已有 pointer 上的 pending，否则扫描首个 pending。"""
        if 0 <= self.pointer < len(self.rows) and self.rows[self.pointer].status == "pending":
            return self.pointer
        for i, row in enumerate(self.rows):
            if row.status == "pending":
                return i
        return None

    def _on_start_exam(self, *, now: float, run_id: str = "", **_: Any) -> list[ExamCommand]:
        if self.phase != "ready" or not self.rows:
            return []
        start_at = self._first_pending_index()
        if start_at is None:
            return []
        if run_id:
            self.run_id = run_id
        elif not self.run_id:
            self.run_id = local_timestamp().replace(":", "")
        # 不得无条件 pointer=0：整场结束后追加重考时 pointer 已指向队尾 pending 行
        self.pointer = start_at
        self.locked = True
        cmds = [ExamCommand("UI_LOCK_MANUAL_RECORD"), *self._start_call(now)]
        return cmds

    def _start_call(self, now: float) -> list[ExamCommand]:
        row = self.current
        if row is None:
            self.phase = "completed"
            return [
                ExamCommand("DISARM_OCCUPANCY"),
                ExamCommand("ANNOUNCE", {"text": "本场考试已全部结束"}),
                ExamCommand("EXPORT"),
                ExamCommand("UI_UNLOCK_MANUAL_RECORD"),
            ]
        self.phase = "calling"
        self.call_guard_deadline = now + self.config.post_call_guard_s
        self.inter_gap_deadline = None
        # 仅刷新叫号时间；已 completed 的行不应被 _start_call 碰到
        if row.status not in {"completed", "superseded", "skipped"}:
            row.status = "pending"
        row.called_at = local_timestamp()
        text = f"请{row.candidate.order}号 {row.candidate.name} 上场考试"
        return [
            ExamCommand("DISARM_OCCUPANCY"),
            ExamCommand("ANNOUNCE", {"text": text}),
            ExamCommand("SCHEDULE_CALL_GUARD", {"deadline": self.call_guard_deadline}),
            ExamCommand("UPDATE_ROW", {"row_id": row.row_id, "status": row.status}),
        ]

    def _on_call_guard_elapsed(self, **_: Any) -> list[ExamCommand]:
        if self.phase != "calling":
            return []
        self.phase = "wait_enter"
        self.call_guard_deadline = None
        return [ExamCommand("ARM_OCCUPANCY")]

    def _on_enter_stable(self, *, now: float, **_: Any) -> list[ExamCommand]:
        if self.phase != "wait_enter":
            return []
        row = self.current
        if row is None:
            return []
        self.phase = "recording"
        self.record_started_mono = now
        row.status = "recording"
        row.record_started_at = local_timestamp()
        return [
            ExamCommand("ANNOUNCE", {"text": "考试开始"}),
            ExamCommand("BEGIN_SEGMENT", {"row_id": row.row_id}),
            ExamCommand(
                "UPDATE_ROW",
                {"row_id": row.row_id, "status": "recording"},
            ),
        ]

    def _on_empty_stable(self, **_: Any) -> list[ExamCommand]:
        if self.phase != "recording":
            return []
        return self._finish_recording(discard=False)

    def _on_force_finish(self, **_: Any) -> list[ExamCommand]:
        if self.phase != "recording":
            return []
        # bypass min_record_s — PresenceGate 不参与
        return self._finish_recording(discard=False)

    def _finish_recording(self, *, discard: bool) -> list[ExamCommand]:
        row = self.current
        if row is None:
            return []
        self.phase = "finishing"
        cmds: list[ExamCommand] = [
            ExamCommand("ANNOUNCE", {"text": "考试结束"}),
            ExamCommand("DISARM_OCCUPANCY"),
        ]
        if discard:
            cmds.append(ExamCommand("DISCARD_SEGMENT", {"row_id": row.row_id}))
            row.status = "skipped"
            row.record_ended_at = local_timestamp()
            cmds.append(
                ExamCommand(
                    "UPDATE_ROW",
                    {"row_id": row.row_id, "status": "skipped"},
                )
            )
        else:
            cmds.append(ExamCommand("END_SEGMENT", {"row_id": row.row_id}))
            row.status = "processing"
            row.record_ended_at = local_timestamp()
            cmds.append(
                ExamCommand(
                    "UPDATE_ROW",
                    {"row_id": row.row_id, "status": "processing"},
                )
            )
        return cmds

    def _on_record_started(self, **_: Any) -> list[ExamCommand]:
        return []

    def _on_record_stopped(
        self, *, now: float, discarded: bool = False, **_: Any
    ) -> list[ExamCommand]:
        if self.phase != "finishing":
            return []
        self.record_started_mono = None
        self.pointer += 1
        if self.pointer >= len(self.rows):
            self.phase = "completed"
            self.locked = False
            return [
                ExamCommand("ANNOUNCE", {"text": "本场考试已全部结束"}),
                ExamCommand("EXPORT"),
                ExamCommand("UI_UNLOCK_MANUAL_RECORD"),
            ]
        # 下一位前 inter-gap
        self.phase = "calling"  # 先进入 calling 前的 gap：用 inter_gap_deadline 挡住 call_guard
        # 设计：gap 结束后再 _start_call。这里用 phase 临时保持 finishing 已结束。
        # 用 dedicated：phase 回到特殊 — 简化：直接 schedule gap，phase=ready-like internal
        self.inter_gap_deadline = now + self.config.inter_student_gap_s
        self.phase = "calling"
        # 在 gap 期间 phase 用 "calling" 但 call_guard 未设；tick 到 gap 后再真正 start_call
        # 为避免重复叫号，用 flag：call_guard_deadline is None and inter_gap set 表示 gap 中
        self.call_guard_deadline = None
        return [
            ExamCommand(
                "SCHEDULE_INTER_GAP",
                {"deadline": self.inter_gap_deadline},
            )
        ]

    def _on_tick(self, *, now: float, **_: Any) -> list[ExamCommand]:
        cmds: list[ExamCommand] = []
        if (
            self.phase == "calling"
            and self.inter_gap_deadline is not None
            and now >= self.inter_gap_deadline
        ):
            self.inter_gap_deadline = None
            # 真正叫下一位
            cmds.extend(self._start_call(now))
            return cmds
        if (
            self.phase == "calling"
            and self.call_guard_deadline is not None
            and now >= self.call_guard_deadline
        ):
            cmds.extend(self._on_call_guard_elapsed())
        return cmds

    def _on_skip(self, *, now: float, **_: Any) -> list[ExamCommand]:
        row = self.current
        if row is None:
            return []
        if self.phase in {"calling", "wait_enter"}:
            row.status = "skipped"
            row.record_ended_at = local_timestamp()
            cmds = [
                ExamCommand("DISARM_OCCUPANCY"),
                ExamCommand(
                    "UPDATE_ROW",
                    {"row_id": row.row_id, "status": "skipped"},
                ),
            ]
            self.pointer += 1
            return cmds + self._after_skip_or_done(now)
        if self.phase == "recording":
            cmds = self._finish_recording(discard=True)
            # record_stopped 会 advance；这里标记 discarded 路径由执行层在 stop 后发 record_stopped(discarded=True)
            return cmds
        return []

    def _after_skip_or_done(self, now: float) -> list[ExamCommand]:
        if self.pointer >= len(self.rows):
            self.phase = "completed"
            self.locked = False
            return [
                ExamCommand("ANNOUNCE", {"text": "本场考试已全部结束"}),
                ExamCommand("EXPORT"),
                ExamCommand("UI_UNLOCK_MANUAL_RECORD"),
            ]
        self.inter_gap_deadline = now + self.config.inter_student_gap_s
        self.phase = "calling"
        self.call_guard_deadline = None
        return [
            ExamCommand(
                "SCHEDULE_INTER_GAP",
                {"deadline": self.inter_gap_deadline},
            )
        ]

    def _on_begin_failed(self, *, now: float, message: str = "", **_: Any) -> list[ExamCommand]:
        if self.phase != "recording":
            return []
        row = self.current
        if row is None:
            return []
        row.status = "failed"
        row.error_code = "begin_failed"
        row.error_message = message or "开录失败"
        self.phase = "finishing"
        # 当作 discard 后 advance
        self.pointer += 1
        cmds = [
            ExamCommand("DISARM_OCCUPANCY"),
            ExamCommand(
                "UPDATE_ROW",
                {
                    "row_id": row.row_id,
                    "status": "failed",
                    "error_code": row.error_code,
                    "error_message": row.error_message,
                },
            ),
        ]
        # 直接走 gap / done
        self.phase = "calling" if self.pointer < len(self.rows) else "completed"
        if self.phase == "completed":
            self.locked = False
            cmds.extend(
                [
                    ExamCommand("ANNOUNCE", {"text": "本场考试已全部结束"}),
                    ExamCommand("EXPORT"),
                    ExamCommand("UI_UNLOCK_MANUAL_RECORD"),
                ]
            )
            return cmds
        self.inter_gap_deadline = now + self.config.inter_student_gap_s
        self.call_guard_deadline = None
        cmds.append(
            ExamCommand(
                "SCHEDULE_INTER_GAP",
                {"deadline": self.inter_gap_deadline},
            )
        )
        return cmds

    def _on_pause(self, **_: Any) -> list[ExamCommand]:
        if self.phase in {"idle", "ready", "completed", "aborted", "paused", "finishing"}:
            return []
        self.paused_from = self.phase
        self.phase = "paused"
        return [ExamCommand("DISARM_OCCUPANCY")]

    def _on_resume(self, *, now: float, **_: Any) -> list[ExamCommand]:
        if self.phase != "paused" or self.paused_from is None:
            return []
        prev = self.paused_from
        self.paused_from = None
        self.phase = prev
        cmds: list[ExamCommand] = []
        if prev in {"wait_enter", "recording"}:
            cmds.append(ExamCommand("ARM_OCCUPANCY"))
        return cmds

    def _on_abort(self, **_: Any) -> list[ExamCommand]:
        if self.phase in {"idle", "aborted", "completed"}:
            return []
        cmds: list[ExamCommand] = [ExamCommand("DISARM_OCCUPANCY")]
        if self.phase == "recording":
            cmds.append(ExamCommand("DISCARD_SEGMENT", {"row_id": self.current.row_id if self.current else ""}))
        self.phase = "aborted"
        self.locked = False
        cmds.append(ExamCommand("UI_UNLOCK_MANUAL_RECORD"))
        return cmds

    def append_retest_row(self, candidate: ExamCandidate) -> ExamResultRow:
        attempts = [
            r.attempt_index
            for r in self.rows
            if r.candidate.student_id == candidate.student_id
        ]
        next_attempt = (max(attempts) if attempts else 0) + 1
        row = ExamResultRow(
            candidate=candidate,
            attempt_index=next_attempt,
            is_scoring_row=True,
        )
        self.rows.append(row)
        if self.phase == "completed":
            self.phase = "ready"
        return row
