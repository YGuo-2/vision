from __future__ import annotations

import io
import json
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apps import ui_backend  # noqa: E402


def test_protocol_manifest_lists_required_message_fields():
    manifest = ui_backend.protocol_manifest()

    assert manifest["version"] == ui_backend.BRIDGE_VERSION
    assert "session.start" in manifest["commands"]
    assert "analysis.run" in manifest["commands"]
    assert manifest["message_contract"]["request"] == [
        "type",
        "command",
        "requestId",
        "jobId",
        "sessionId",
        "payload",
    ]
    assert manifest["message_contract"]["response"] == [
        "type",
        "requestId",
        "ok",
        "jobId",
        "sessionId",
        "payload",
        "error",
        "timestamp",
    ]
    assert manifest["message_contract"]["event"] == [
        "type",
        "event",
        "jobId",
        "sessionId",
        "payload",
        "error",
        "timestamp",
    ]
    assert manifest["message_contract"]["optional"] == {
        "request": ["jobId", "sessionId"],
        "response": ["jobId", "sessionId"],
        "event": ["jobId", "sessionId"],
    }
    assert manifest["message_contract"]["nullable"] == {
        "request": ["jobId", "sessionId"],
        "response": ["jobId", "sessionId", "error"],
        "event": ["jobId", "sessionId", "error"],
    }


def test_request_null_job_and_session_ids_match_manifest_contract():
    manifest = ui_backend.protocol_manifest()["message_contract"]

    assert manifest["optional"]["request"] == ["jobId", "sessionId"]
    assert manifest["nullable"]["request"] == ["jobId", "sessionId"]

    req = ui_backend.parse_command(
        {
            "type": "command",
            "command": "job.stop",
            "requestId": "req-null-ids",
            "jobId": None,
            "sessionId": None,
            "payload": {},
        }
    )

    assert req.job_id is None
    assert req.session_id is None


def test_parse_command_requires_known_command_and_object_payload():
    req = ui_backend.parse_command(
        {
            "type": "command",
            "command": "session.start",
            "requestId": "req-1",
            "sessionId": "session-1",
            "payload": {"source": "0"},
        }
    )

    assert req.command == "session.start"
    assert req.request_id == "req-1"
    assert req.session_id == "session-1"
    assert req.payload == {"source": "0"}


def test_parse_command_rejects_unknown_command():
    try:
        ui_backend.parse_command(
            {
                "type": "command",
                "command": "unknown.command",
                "requestId": "req-1",
                "payload": {},
            }
        )
    except ValueError as exc:
        assert "unknown bridge command" in str(exc)
    else:
        raise AssertionError("unknown command should be rejected")


def test_response_shape_always_contains_payload_error_and_timestamp():
    response = ui_backend.make_response(
        "req-1",
        ok=True,
        payload={"pong": True},
        job_id="job-1",
        session_id="session-1",
        timestamp="2026-06-08T00:00:00.000Z",
    )

    assert response == {
        "type": "response",
        "requestId": "req-1",
        "ok": True,
        "jobId": "job-1",
        "sessionId": "session-1",
        "payload": {"pong": True},
        "error": None,
        "timestamp": "2026-06-08T00:00:00.000Z",
    }


def test_event_shape_always_contains_payload_error_and_timestamp():
    event = ui_backend.make_event(
        "session.frame",
        payload={"fps": 30},
        session_id="session-1",
        timestamp="2026-06-08T00:00:00.000Z",
    )

    assert event["type"] == "event"
    assert event["event"] == "session.frame"
    assert event["sessionId"] == "session-1"
    assert event["payload"] == {"fps": 30}
    assert event["error"] is None
    assert event["timestamp"] == "2026-06-08T00:00:00.000Z"


def test_bridge_error_serializes_detail_for_frontend_debugging():
    error = ui_backend.BridgeError("boom", "失败", {"stage": "unit"})
    response = ui_backend.make_response("req-1", ok=False, error=error)

    assert response["payload"] == {}
    assert response["error"] == {
        "code": "boom",
        "message": "失败",
        "detail": {"stage": "unit"},
    }


def test_handle_line_serializes_ping_response():
    line = json.dumps(
        {
            "type": "command",
            "command": "bridge.ping",
            "requestId": "req-1",
            "payload": {},
        },
        ensure_ascii=False,
    )

    response = json.loads(ui_backend.handle_line(line))

    assert response["type"] == "response"
    assert response["requestId"] == "req-1"
    assert response["ok"] is True
    assert response["payload"]["version"] == ui_backend.BRIDGE_VERSION
    assert "session.start" in response["payload"]["commands"]


def test_bridge_message_writer_serializes_concurrent_json_lines():
    stream = io.StringIO()
    writer = ui_backend.BridgeMessageWriter(stream)
    thread_count = 8
    messages_per_thread = 80

    def write_many(thread_index: int) -> None:
        for message_index in range(messages_per_thread):
            writer.write(
                ui_backend.make_event(
                    "stress.event",
                    payload={"thread": thread_index, "index": message_index},
                    job_id=f"job-{thread_index}",
                )
            )
            writer.write(
                ui_backend.make_response(
                    f"req-{thread_index}-{message_index}",
                    ok=True,
                    payload={"thread": thread_index, "index": message_index},
                    job_id=f"job-{thread_index}",
                )
            )

    threads = [threading.Thread(target=write_many, args=(index,)) for index in range(thread_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(2.0)
        assert not thread.is_alive()

    lines = stream.getvalue().splitlines()
    assert len(lines) == thread_count * messages_per_thread * 2
    seen_events = set()
    seen_responses = set()
    for line in lines:
        payload = json.loads(line)
        if payload["type"] == "event":
            assert payload["event"] == "stress.event"
            seen_events.add((payload["payload"]["thread"], payload["payload"]["index"]))
        else:
            assert payload["type"] == "response"
            assert payload["ok"] is True
            assert payload["requestId"].startswith("req-")
            seen_responses.add((payload["payload"]["thread"], payload["payload"]["index"]))
    assert len(seen_events) == thread_count * messages_per_thread
    assert len(seen_responses) == thread_count * messages_per_thread


def test_handle_line_preserves_request_id_on_parse_errors():
    line = json.dumps(
        {
            "type": "command",
            "command": "unknown.command",
            "requestId": "req-bad-command",
            "payload": {},
        },
        ensure_ascii=False,
    )

    response = json.loads(ui_backend.handle_line(line))

    assert response["type"] == "response"
    assert response["requestId"] == "req-bad-command"
    assert response["ok"] is False
    assert response["error"]["code"] == "bad_request"


def test_handle_line_preserves_request_id_on_bad_payload_shape():
    line = json.dumps(
        {
            "type": "command",
            "command": "bridge.ping",
            "requestId": "req-bad-payload",
            "payload": [],
        },
        ensure_ascii=False,
    )

    response = json.loads(ui_backend.handle_line(line))

    assert response["requestId"] == "req-bad-payload"
    assert response["ok"] is False
    assert response["error"]["code"] == "bad_request"


def test_model_status_known_command_dispatches_successfully():
    req = ui_backend.parse_command(
        {
            "type": "command",
            "command": "model.status",
            "requestId": "req-2",
            "payload": {"poseVariant": "full", "enableHands": True},
        }
    )

    response = ui_backend.handle_command(req)

    assert response["ok"] is True
    assert response["payload"]["activeKeys"] == ["hand", "pose_full"]
    assert response["payload"]["models"]
