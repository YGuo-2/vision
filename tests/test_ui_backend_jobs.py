from __future__ import annotations

import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apps import ui_backend  # noqa: E402


def test_submit_emits_lifecycle_events_and_finishes_successfully():
    events: list[dict] = []
    manager = ui_backend.BridgeJobManager(events.append)
    ready = threading.Event()
    release = threading.Event()

    def handler(ctx: ui_backend.JobContext) -> dict:
        ctx.progress("job.progress", {"stage": "warming"})
        ready.set()
        release.wait(1.0)
        if ctx.stopped():
            return {"stopped": True}
        return {"done": True, "jobId": ctx.job_id}

    record = manager.submit(
        "analysis.run",
        {"video": "demo.mp4"},
        handler,
        request_id="req-1",
        job_id="job-1",
        session_id="session-1",
    )

    assert ready.wait(1.0)
    assert record.status == "running"
    assert manager.active_job_ids() == ["job-1"]
    assert any(item["event"] == "job.started" for item in events)
    assert any(item["event"] == "job.progress" for item in events)

    release.set()
    final = manager.wait("job-1", 2.0)

    assert final is not None
    assert final.status == "succeeded"
    assert final.result == {"done": True, "jobId": "job-1"}
    assert final.error is None
    assert manager.active_job_ids() == []
    assert any(item["event"] == "job.completed" for item in events)


def test_stop_requests_are_visible_to_the_handler_and_emit_stopped():
    events: list[dict] = []
    manager = ui_backend.BridgeJobManager(events.append)
    started = threading.Event()
    release = threading.Event()

    def handler(ctx: ui_backend.JobContext) -> dict:
        started.set()
        release.wait(1.0)
        if ctx.stopped():
            ctx.progress("job.progress", {"stage": "stopping"})
            return {"stopped": True}
        return {"done": True}

    record = manager.submit(
        "session.start",
        {"source": "0"},
        handler,
        request_id="req-2",
        job_id="job-2",
        session_id="session-2",
    )

    assert started.wait(1.0)
    assert manager.stop("job-2") is True
    release.set()
    final = manager.wait("job-2", 2.0)

    assert final is not None
    assert final.status == "stopped"
    assert final.result == {"stopped": True}
    assert record.snapshot()["stopRequested"] is True
    assert any(item["event"] == "job.stopped" for item in events)


def test_submit_serializes_job_failure_with_traceback_detail():
    events: list[dict] = []
    manager = ui_backend.BridgeJobManager(events.append)

    def handler(_: ui_backend.JobContext) -> dict:
        raise RuntimeError("boom")

    record = manager.submit(
        "template.create",
        {"video": "base.mp4"},
        handler,
        request_id="req-3",
        job_id="job-3",
        session_id="session-3",
    )

    final = manager.wait("job-3", 2.0)

    assert final is not None
    assert final.status == "failed"
    assert final.error is not None
    assert final.error.code == "job_failed"
    assert final.error.message == "boom"
    assert final.error.detail["jobId"] == "job-3"
    assert "traceback" in final.error.detail
    assert record.snapshot()["error"]["code"] == "job_failed"
    assert any(item["event"] == "job.failed" for item in events)


def test_job_stop_command_uses_the_default_manager():
    events: list[dict] = []
    manager = ui_backend.BridgeJobManager(events.append)
    started = threading.Event()
    release = threading.Event()
    previous = ui_backend.DEFAULT_JOB_MANAGER
    ui_backend.DEFAULT_JOB_MANAGER = manager
    try:
        assert manager.submit(
            "analysis.run",
            {"video": "demo.mp4"},
            lambda ctx: (started.set(), release.wait(1.0), {"stopped": ctx.stopped()})[-1],
            request_id="req-4",
            job_id="job-4",
            session_id="session-4",
        )
        assert started.wait(1.0)
        response = ui_backend.handle_command(
            ui_backend.CommandRequest(
                command="job.stop",
                request_id="req-stop",
                payload={"jobId": "job-4"},
            )
        )
        assert response["ok"] is True
        assert response["payload"] == {"jobId": "job-4", "stopped": True}
        release.set()
        final = manager.wait("job-4", 2.0)
        assert final is not None
        assert final.status == "stopped"
    finally:
        release.set()
        ui_backend.DEFAULT_JOB_MANAGER = previous


def test_stop_completed_job_returns_false_and_keeps_snapshot_unchanged():
    manager = ui_backend.BridgeJobManager()

    manager.submit(
        "analysis.run",
        {"video": "demo.mp4"},
        lambda ctx: {"done": True, "stopped": ctx.stopped()},
        request_id="req-completed",
        job_id="job-completed",
    )
    final = manager.wait("job-completed", 2.0)

    assert final is not None
    assert final.status == "succeeded"
    assert final.snapshot()["stopRequested"] is False
    assert manager.stop("job-completed") is False
    assert final.snapshot()["stopRequested"] is False
