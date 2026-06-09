from __future__ import annotations

import json
import sys
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
