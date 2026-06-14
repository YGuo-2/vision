from __future__ import annotations

import sys
import threading
import time
import socket
import struct
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apps import ui_backend  # noqa: E402
from core.recording_controller import RecordingController  # noqa: E402


class FakeCapture:
    def __init__(self, frames: list[Any] | None = None, *, opened: bool = True) -> None:
        self.frames = list(frames or [])
        self.opened = opened
        self.released = False
        self.read_count = 0
        self.props = {
            ui_backend.CAP_PROP_FPS: 25.0,
            ui_backend.CAP_PROP_FRAME_COUNT: float(len(self.frames)),
            ui_backend.CAP_PROP_FRAME_WIDTH: 320.0,
            ui_backend.CAP_PROP_FRAME_HEIGHT: 240.0,
        }

    def isOpened(self) -> bool:
        return self.opened

    def get(self, prop: int) -> float:
        return self.props.get(prop, 0.0)

    def read(self):
        self.read_count += 1
        if self.frames:
            return True, self.frames.pop(0)
        return False, None

    def release(self) -> None:
        self.released = True


class InfiniteCapture(FakeCapture):
    def __init__(self) -> None:
        super().__init__([], opened=True)
        self.props[ui_backend.CAP_PROP_FRAME_COUNT] = 0.0

    def read(self):
        self.read_count += 1
        return True, {"frame": self.read_count}


class FakePipeline:
    def __init__(self, actions: list[str] | None = None) -> None:
        self.actions = actions or ["V_SIGN"]
        self.closed = False
        self.timestamps: list[int] = []

    def next_timestamp_ms(self, *, is_file: bool, fps_for_ts: float) -> int:
        value = len(self.timestamps) * int(1000 / max(fps_for_ts, 1.0))
        self.timestamps.append(value)
        return value

    def annotate(self, frame, *, timestamp_ms: int | None = None):
        return {"annotated": frame, "timestamp": timestamp_ms}, list(self.actions)

    def close(self) -> None:
        self.closed = True


class StepPipeline(FakePipeline):
    def __init__(self, *, steps: int) -> None:
        super().__init__(["V_SIGN"])
        self.annotating = [threading.Event() for _ in range(steps)]
        self.release = [threading.Event() for _ in range(steps)]
        self.calls = 0

    def annotate(self, frame, *, timestamp_ms: int | None = None):
        index = min(self.calls, len(self.annotating) - 1)
        self.calls += 1
        self.annotating[index].set()
        assert self.release[index].wait(1.0)
        return super().annotate(frame, timestamp_ms=timestamp_ms)


class BlockingParallelPipeline(FakePipeline):
    def __init__(self, *, started: threading.Event, release: threading.Event, worker_id: int) -> None:
        super().__init__(["V_SIGN", f"worker={worker_id}"])
        self.started = started
        self.release = release
        self.worker_id = worker_id

    def annotate(self, frame, *, timestamp_ms: int | None = None):
        self.started.set()
        assert self.release.wait(1.0)
        annotated, actions = super().annotate(frame, timestamp_ms=timestamp_ms)
        annotated["workerId"] = self.worker_id
        return annotated, actions


class FakeWriter:
    def __init__(self, *, fail_on_write: bool = False) -> None:
        self.fail_on_write = fail_on_write
        self.write_calls = 0
        self.release_calls = 0
        self.wrote = threading.Event()

    def write(self, frame) -> None:
        self.write_calls += 1
        self.wrote.set()
        if self.fail_on_write:
            raise RuntimeError("fake write failed")

    def release(self) -> None:
        self.release_calls += 1


class FakeWriterFactory:
    def __init__(self, writer: FakeWriter) -> None:
        self.writer = writer
        self.actual_path = Path("fake_outputs") / "record_fake.mp4"

    def __call__(self, path: Path, fps: float, size: tuple[int, int]):
        return self.writer, self.actual_path, "fake"


class FakeRustFrameSink:
    def __init__(self, *, session_id: str, token: str = "fake-token") -> None:
        self.session_id = session_id
        self.token = token
        self.frames: dict[int, bytes] = {}
        self.handles: dict[int, str] = {}
        self.dropped = 0
        self.served = 0
        self._closed = threading.Event()
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind(("127.0.0.1", 0))
        self.port = int(self._socket.getsockname()[1])
        self._socket.listen(4)
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def payload(self) -> dict[str, Any]:
        return {
            "frameHost": "127.0.0.1",
            "framePort": self.port,
            "frameToken": self.token,
        }

    def close(self) -> None:
        self._closed.set()
        try:
            with socket.create_connection(("127.0.0.1", self.port), timeout=0.2) as conn:
                conn.sendall(f"CLOSE {self.session_id} {self.token}\n".encode("utf-8"))
        except OSError:
            pass
        try:
            self._socket.close()
        except OSError:
            pass
        self._thread.join(timeout=1.0)

    def _serve(self) -> None:
        while not self._closed.is_set():
            try:
                conn, _addr = self._socket.accept()
            except OSError:
                break
            with conn:
                while not self._closed.is_set():
                    header = b""
                    while not header.endswith(b"\n"):
                        chunk = conn.recv(1)
                        if not chunk:
                            break
                        header += chunk
                    if not header:
                        break
                    parts = header.decode("utf-8", errors="replace").strip().split()
                    if len(parts) >= 3 and parts[0] == "CLOSE":
                        self.frames.clear()
                        self.handles.clear()
                        self._closed.set()
                        break
                    if len(parts) < 5 or parts[0] != "PUT":
                        conn.sendall(b"ERR bad_request\n")
                        continue
                    session_id, token, raw_frame_id, frame_handle = parts[1:5]
                    if session_id != self.session_id or token != self.token:
                        conn.sendall(b"ERR unauthorized\n")
                        continue
                    length_buf = b""
                    while len(length_buf) < 4:
                        chunk = conn.recv(4 - len(length_buf))
                        if not chunk:
                            break
                        length_buf += chunk
                    if len(length_buf) != 4:
                        break
                    length = struct.unpack(">I", length_buf)[0]
                    payload = b""
                    while len(payload) < length:
                        chunk = conn.recv(length - len(payload))
                        if not chunk:
                            break
                        payload += chunk
                    if len(payload) != length:
                        break
                    if self.frames:
                        self.dropped += 1
                    frame_id = int(raw_frame_id)
                    self.frames[frame_id] = payload
                    self.handles[frame_id] = frame_handle
                    conn.sendall(f"OK droppedFrames={self.dropped} servedFrames={self.served}\n".encode("utf-8"))


def _install_preview_service(service: ui_backend.PreviewSessionService):
    previous = ui_backend.DEFAULT_PREVIEW_SERVICE
    ui_backend.DEFAULT_PREVIEW_SERVICE = service
    return previous


def _fetch_frame_payload(payload: dict[str, Any], sink: FakeRustFrameSink) -> bytes:
    assert payload["frameToken"] == sink.token
    assert payload["frameHandle"] == sink.handles[payload["frameId"]]
    return sink.frames[payload["frameId"]]


def _wait_frame_events(events: list[dict], count: int = 1, timeout: float = 1.0) -> list[dict]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        frame_events = [event for event in events if event["event"] == "session.frame"]
        if len(frame_events) >= count:
            return frame_events
        time.sleep(0.01)
    return [event for event in events if event["event"] == "session.frame"]


def test_latest_frame_channel_reuses_persistent_connection() -> None:
    sink = FakeRustFrameSink(session_id="session-channel")
    channel = ui_backend.LatestFrameChannel.from_payload(session_id="session-channel", payload=sink.payload())
    assert channel is not None
    try:
        first = channel.publish(b"frame-1")
        second = channel.publish(b"frame-2")

        assert first["frameId"] == 1
        assert second["frameId"] == 2
        assert sink.frames[1] == b"frame-1"
        assert sink.frames[2] == b"frame-2"
        assert channel.snapshot()["publishedFrames"] == 2
        assert channel.snapshot()["lastError"] is None
    finally:
        channel.close()
        sink.close()


def test_latest_frame_channel_reconnects_once_after_disconnect() -> None:
    sink = FakeRustFrameSink(session_id="session-reconnect")
    channel = ui_backend.LatestFrameChannel.from_payload(session_id="session-reconnect", payload=sink.payload())
    assert channel is not None
    try:
        first = channel.publish(b"before-close")
        assert first["frameId"] == 1
        with channel._lock:  # noqa: SLF001 - unit-test forced transport failure path.
            channel._drop_connection_locked()  # noqa: SLF001

        second = channel.publish(b"after-close")

        assert second["frameId"] == 2
        assert sink.frames[2] == b"after-close"
        assert channel.snapshot()["lastError"] is None
    finally:
        channel.close()
        sink.close()


def test_preview_publish_buffer_keeps_only_newest_and_counts_drops() -> None:
    buffer = ui_backend._LatestPreviewPublishBuffer()  # noqa: SLF001
    buffer.put(
        ui_backend._PreviewPublishFrame(  # noqa: SLF001
            annotated={"frame": 1},
            actions=["V_SIGN"],
            frame_count=1,
            total=0,
            width=320,
            height=240,
            started_at=0.0,
        )
    )
    buffer.put(
        ui_backend._PreviewPublishFrame(  # noqa: SLF001
            annotated={"frame": 2},
            actions=["SQUAT"],
            frame_count=2,
            total=0,
            width=320,
            height=240,
            started_at=0.0,
        )
    )

    latest = buffer.get_latest(timeout=0.01)
    assert latest is not None
    assert latest.frame_count == 2
    buffer.mark_published()
    snapshot = buffer.snapshot()
    assert snapshot["submittedFrames"] == 2
    assert snapshot["publishedPreviewFrames"] == 1
    assert snapshot["droppedPreviewFrames"] == 1


def test_camera_list_command_uses_camera_enumerator(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_enumerate_cameras(*, scan_limit: int):
        assert scan_limit == 3
        return [
            ui_backend.CameraEntry("摄像头 0", 0),
            ui_backend.CameraEntry("摄像头 2: USB", 2),
        ]

    monkeypatch.setattr(ui_backend, "enumerate_cameras", fake_enumerate_cameras)

    response = ui_backend.handle_command(
        ui_backend.CommandRequest(
            command="camera.list",
            request_id="req-camera",
            payload={"scanLimit": 3},
        )
    )

    assert response["ok"] is True
    assert response["payload"]["count"] == 2
    assert response["payload"]["cameras"] == [
        {"label": "摄像头 0", "index": 0},
        {"label": "摄像头 2: USB", "index": 2},
    ]


def test_session_start_emits_frame_events_and_releases_capture() -> None:
    events: list[dict] = []
    manager = ui_backend.BridgeJobManager(events.append)
    cap = FakeCapture([{"frame": 1}, {"frame": 2}, {"frame": 3}])
    pipe = StepPipeline(steps=2)
    pipe.actions = ["V_SIGN", "SQUAT"]
    service = ui_backend.PreviewSessionService(
        job_manager=manager,
        capture_factory=lambda source: cap,
        pipeline_factory=lambda options: pipe,
        frame_encoder=lambda frame: b"fake-frame-bytes",
    )
    previous = _install_preview_service(service)
    sink = FakeRustFrameSink(session_id="session-frame")
    try:
        response = ui_backend.handle_command(
            ui_backend.CommandRequest(
                command="session.start",
                request_id="req-start",
                session_id="session-frame",
                payload={
                    "sourceKind": "camera",
                    "cameraIndex": 0,
                    "poseVariant": "heavy",
                    "workers": 1,
                    "enableHands": False,
                    "frameLimit": 2,
                    "frameChannel": sink.payload(),
                },
            )
        )
        assert response["ok"] is True
        assert response["sessionId"]
        assert pipe.annotating[0].wait(1.0)
        pipe.release[0].set()
        assert pipe.annotating[1].wait(1.0)
        frame_events = _wait_frame_events(events)
        assert frame_events
        assert _fetch_frame_payload(frame_events[0]["payload"], sink) == b"fake-frame-bytes"
        pipe.release[1].set()

        final = manager.wait(response["jobId"], 2.0)

        assert final is not None
        assert final.status == "succeeded"
        assert final.result["state"] == "completed"
        assert final.result["frames"] == 2
        frame_events = _wait_frame_events(events, count=2)
        assert _fetch_frame_payload(frame_events[-1]["payload"], sink) == b"fake-frame-bytes"
        assert cap.released is True
        assert pipe.closed is False
        assert frame_events[0]["payload"]["actions"] == ["V_SIGN", "SQUAT"]
        assert frame_events[0]["payload"]["actionsZh"] == ["✌（V 手势）", "下蹲"]
        assert "image" not in frame_events[0]["payload"]
        assert frame_events[0]["payload"]["frameTransport"] == "tcp-length-prefixed"
        assert frame_events[0]["payload"]["frameHost"] == "127.0.0.1"
        assert frame_events[0]["payload"]["framePort"] > 0
        assert frame_events[0]["payload"]["frameToken"]
        assert frame_events[0]["payload"]["frameId"] == 1
        assert frame_events[0]["payload"]["frameHandle"] == "session-frame:1"
        assert frame_events[0]["payload"]["payloadBytes"] == len(b"fake-frame-bytes")
        assert frame_events[0]["payload"]["frameStore"]["droppedFrames"] >= 0
        assert frame_events[0]["payload"]["frameStore"]["lastFrameAgeMs"] is not None
        assert frame_events[0]["payload"].get("parallelPreview") in (None, False)
        running_status = next(
            event for event in events if event["event"] == "session.status" and event["payload"]["state"] == "running"
        )
        assert running_status["payload"]["parallelPreview"] is False
        assert running_status["payload"]["frameChannel"]["frameToken"] == frame_events[0]["payload"]["frameToken"]
        assert any(event["event"] == "session.status" for event in events)
    finally:
        pipe.release[0].set()
        pipe.release[1].set()
        sink.close()
        ui_backend.DEFAULT_PREVIEW_SERVICE = previous


def test_session_start_uses_parallel_pose_engine_when_workers_gt_one() -> None:
    events: list[dict] = []
    manager = ui_backend.BridgeJobManager(events.append)
    cap = FakeCapture([{"frame": 1}, {"frame": 2}, {"frame": 3}])
    started = [threading.Event(), threading.Event()]
    releases = [threading.Event(), threading.Event()]
    created: list[BlockingParallelPipeline] = []
    created_lock = threading.Lock()

    def pipeline_factory(options: ui_backend.PreviewSessionOptions):
        pytest.fail("legacy sequential pipeline should not be used when workers > 1")

    def parallel_factory(options: ui_backend.PreviewSessionOptions):
        assert options.workers == 2

        def _factory() -> BlockingParallelPipeline:
            with created_lock:
                worker_idx = len(created)
                pipeline = BlockingParallelPipeline(
                    started=started[worker_idx],
                    release=releases[worker_idx],
                    worker_id=worker_idx + 1,
                )
                created.append(pipeline)
                return pipeline

        return _factory

    service = ui_backend.PreviewSessionService(
        job_manager=manager,
        capture_factory=lambda source: cap,
        pipeline_factory=pipeline_factory,
        parallel_pipeline_factory=parallel_factory,
        frame_encoder=lambda frame: b"parallel-frame-bytes",
    )
    previous = _install_preview_service(service)
    sink = FakeRustFrameSink(session_id="session-parallel")
    try:
        response = ui_backend.handle_command(
            ui_backend.CommandRequest(
                command="session.start",
                request_id="req-parallel",
                session_id="session-parallel",
                payload={
                    "sourceKind": "camera",
                    "cameraIndex": 0,
                    "poseVariant": "heavy",
                    "workers": 2,
                    "enableHands": False,
                    "frameLimit": 2,
                    "frameChannel": sink.payload(),
                },
            )
        )
        assert response["ok"] is True
        assert started[0].wait(1.0)
        assert started[1].wait(1.0)
        releases[0].set()
        releases[1].set()

        final = manager.wait(response["jobId"], 2.0)

        assert final is not None
        assert final.status == "succeeded"
        assert final.result["state"] == "completed"
        assert final.result["frames"] == 2
        assert final.result["parallelPreview"] is True
        assert final.result["workersUsed"] == 2
        assert final.result["capturedFrames"] >= 2
        assert final.result["submittedFrames"] >= 2
        assert final.result["emittedInferenceFrames"] == 2
        assert final.result["pendingInferenceFrames"] >= 0
        assert len(created) == 2
        assert all(p.closed for p in created)
        parallel_events = [event for event in events if event["event"] == "session.frame"]
        assert parallel_events
        assert parallel_events[0]["payload"]["parallelPreview"] is True
        assert parallel_events[0]["payload"]["workersUsed"] == 2
        assert parallel_events[0]["payload"]["inferenceFrameIndex"] == 0
        assert parallel_events[0]["payload"]["sourceFrameIndex"] == 1
        assert parallel_events[0]["payload"]["frameStore"]["publishedFrames"] >= 1
        assert parallel_events[0]["payload"]["frameStore"]["droppedFrames"] >= 0
        assert parallel_events[0]["payload"]["frameStore"]["lastFrameAgeMs"] is not None
    finally:
        releases[0].set()
        releases[1].set()
        sink.close()
        ui_backend.DEFAULT_PREVIEW_SERVICE = previous


def test_session_stop_by_session_id_requests_running_job_stop() -> None:
    events: list[dict] = []
    manager = ui_backend.BridgeJobManager(events.append)
    cap = InfiniteCapture()
    annotating = threading.Event()
    release = threading.Event()

    class SlowPipeline(FakePipeline):
        def annotate(self, frame, *, timestamp_ms: int | None = None):
            annotating.set()
            assert release.wait(1.0)
            return super().annotate(frame, timestamp_ms=timestamp_ms)

    pipe = SlowPipeline(["HANDS_UP"])
    service = ui_backend.PreviewSessionService(
        job_manager=manager,
        capture_factory=lambda source: cap,
        pipeline_factory=lambda options: pipe,
        frame_encoder=lambda frame: b"slow-frame",
    )
    previous = _install_preview_service(service)
    try:
        start = ui_backend.handle_command(
            ui_backend.CommandRequest(
                command="session.start",
                request_id="req-start",
                session_id="session-stop",
                payload={"source": "0", "frameLimit": 10},
            )
        )
        assert start["ok"] is True
        assert annotating.wait(1.0)

        stop = ui_backend.handle_command(
            ui_backend.CommandRequest(
                command="session.stop",
                request_id="req-stop",
                payload={"sessionId": "session-stop"},
            )
        )
        assert stop["ok"] is True
        assert stop["payload"]["stopped"] is True

        release.set()
        final = manager.wait(start["jobId"], 2.0)

        assert final is not None
        assert final.status == "stopped"
        assert final.result["state"] == "stopped"
        assert cap.released is True
        assert pipe.closed is False
        assert any(event["event"] == "job.stopped" for event in events)
    finally:
        release.set()
        ui_backend.DEFAULT_PREVIEW_SERVICE = previous


def test_camera_preview_drops_stale_frames_when_inference_is_slow() -> None:
    events: list[dict] = []
    manager = ui_backend.BridgeJobManager(events.append)

    class CoordinatedBurstCapture(FakeCapture):
        def __init__(self, *, frame_count: int) -> None:
            super().__init__([], opened=True)
            self.frame_count = frame_count
            self.next_frame = 0
            self.allow_burst = threading.Event()
            self.props[ui_backend.CAP_PROP_FRAME_COUNT] = 0.0

        def read(self):
            self.read_count += 1
            if self.next_frame == 0:
                self.next_frame = 1
                return True, {"frame": self.next_frame}
            assert self.allow_burst.wait(1.0)
            if self.next_frame >= self.frame_count:
                return False, None
            self.next_frame += 1
            return True, {"frame": self.next_frame}

    cap = CoordinatedBurstCapture(frame_count=20)

    class SlowFirstFramePipeline(FakePipeline):
        def __init__(self) -> None:
            super().__init__(["HANDS_UP"])
            self.seen_frames: list[int] = []

        def annotate(self, frame, *, timestamp_ms: int | None = None):
            self.seen_frames.append(int(frame["frame"]))
            if len(self.seen_frames) == 1:
                cap.allow_burst.set()
                time.sleep(0.08)
            return super().annotate(frame, timestamp_ms=timestamp_ms)

    pipe = SlowFirstFramePipeline()
    service = ui_backend.PreviewSessionService(
        job_manager=manager,
        capture_factory=lambda source: cap,
        pipeline_factory=lambda options: pipe,
        frame_encoder=lambda frame: b"realtime-frame",
    )
    previous = _install_preview_service(service)
    sink = FakeRustFrameSink(session_id="session-realtime")
    try:
        response = ui_backend.handle_command(
            ui_backend.CommandRequest(
                command="session.start",
                request_id="req-realtime",
                session_id="session-realtime",
                payload={"source": "0", "frameLimit": 2, "frameChannel": sink.payload()},
            )
        )
        assert response["ok"] is True

        final = manager.wait(response["jobId"], 2.0)

        assert final is not None
        assert final.status == "succeeded"
        assert final.result["frames"] == 2
        assert final.result["capturedFrames"] == 20
        assert final.result["droppedFrames"] > 0
        assert final.result["renderedFrames"] == 2
        assert pipe.seen_frames == [1, 20]
        frame_events = [event for event in events if event["event"] == "session.frame"]
        assert frame_events[0]["payload"]["sourceFrameIndex"] == 1
        assert frame_events[0]["payload"]["sourceFrameAgeMs"] >= 0
        assert "image" not in frame_events[0]["payload"]
        assert frame_events[0]["payload"]["payloadBytes"] == len(b"realtime-frame")
        assert frame_events[0]["payload"]["frameStore"]["droppedFrames"] >= 0
        assert frame_events[0]["payload"]["frameStore"]["lastFrameAgeMs"] is not None
    finally:
        sink.close()
        ui_backend.DEFAULT_PREVIEW_SERVICE = previous


def test_session_start_rejects_missing_source() -> None:
    response = ui_backend.handle_command(
        ui_backend.CommandRequest(
            command="session.start",
            request_id="req-bad",
            payload={"poseVariant": "full"},
        )
    )

    assert response["ok"] is False
    assert response["error"]["code"] == "bad_request"
    assert "source" in response["error"]["message"]


def test_preview_session_defaults_to_lite_pose_only() -> None:
    options = ui_backend.normalize_session_options({"source": "0"})

    assert options.pose_variant == "lite"
    assert options.enable_hands is False
    assert options.delegate == "cpu"
    assert options.backend_route["backend"] in {"mediapipe", "yolo"}
    assert options.backend_route["scoreAuthorized"] is False


def test_preview_session_accepts_explicit_gpu_delegate() -> None:
    options = ui_backend.normalize_session_options({"source": "0", "delegate": "gpu"})

    assert options.delegate == "gpu"


def test_preview_session_rejects_unknown_delegate() -> None:
    with pytest.raises(ValueError, match="delegate must be one of"):
        ui_backend.normalize_session_options({"source": "0", "delegate": "metal"})


def test_preview_slimming_constants_are_low_load() -> None:
    assert ui_backend.PREVIEW_JPEG_QUALITY <= 60
    assert ui_backend.PREVIEW_MAX_EDGE <= 720
    assert ui_backend.PREVIEW_FRAME_EVENT_MIN_INTERVAL_S >= 1.0 / 20.0
    assert ui_backend.PREVIEW_CAPTURE_IDLE_SLEEP_S >= 0.003


def test_default_pipeline_factory_passes_explicit_delegate_to_mediapipe(monkeypatch, tmp_path) -> None:
    from core import paths, vision_pipeline

    captured = []

    class FakePipeline:
        def __init__(self, *, models_dir, cfg) -> None:
            captured.append((models_dir, cfg))

    monkeypatch.setattr(paths, "models_dir", lambda: tmp_path)
    monkeypatch.setattr(vision_pipeline, "MediaPipePipeline", FakePipeline)

    options = ui_backend.normalize_session_options({"source": "0", "delegate": "gpu"})

    ui_backend._default_pipeline_factory(options)  # noqa: SLF001

    assert captured
    assert captured[0][0] == tmp_path
    assert captured[0][1].delegate == "gpu"
    assert captured[0][1].enable_hands is False


def test_pipeline_delegate_payload_reports_cpu_fallback() -> None:
    class FakePipelineWithFallback:
        requested_delegate = "gpu"
        active_delegate = "cpu"
        delegate_fallback_reason = "gpu unavailable"

    assert ui_backend._pipeline_delegate_payload(FakePipelineWithFallback()) == {  # noqa: SLF001
        "requested": "gpu",
        "active": "cpu",
        "fallback": True,
        "fallbackReason": "gpu unavailable",
    }


def test_record_toggle_and_stop_share_session_recording_controller() -> None:
    events: list[dict] = []
    manager = ui_backend.BridgeJobManager(events.append)
    cap = InfiniteCapture()
    pipe = StepPipeline(steps=2)
    writer = FakeWriter()
    writer_factory = FakeWriterFactory(writer)
    service = ui_backend.PreviewSessionService(
        job_manager=manager,
        capture_factory=lambda source: cap,
        pipeline_factory=lambda options: pipe,
        frame_encoder=lambda frame: b"record-frame",
        recording_factory=lambda options: RecordingController(
            writer_factory=writer_factory,
            path_provider=lambda: Path("fake_outputs") / "record_requested.mp4",
        ),
    )
    previous = _install_preview_service(service)
    try:
        start = ui_backend.handle_command(
            ui_backend.CommandRequest(
                command="session.start",
                request_id="req-start-record",
                session_id="session-record",
                payload={"source": "0", "frameLimit": 2},
            )
        )
        assert start["ok"] is True
        assert pipe.annotating[0].wait(1.0)

        toggle = ui_backend.handle_command(
            ui_backend.CommandRequest(
                command="record.toggle",
                request_id="req-toggle",
                payload={"sessionId": "session-record"},
            )
        )
        assert toggle["ok"] is True
        assert toggle["payload"]["state"] == "recording"
        assert toggle["payload"]["buttonText"] == "暂停录制"

        pipe.release[0].set()
        assert writer.wrote.wait(1.0)
        assert pipe.annotating[1].wait(1.0)

        stop_record = ui_backend.handle_command(
            ui_backend.CommandRequest(
                command="record.stop",
                request_id="req-record-stop",
                payload={"sessionId": "session-record"},
            )
        )
        assert stop_record["ok"] is True
        assert stop_record["payload"]["state"] == "idle"
        assert stop_record["payload"]["resultPath"] == str(writer_factory.actual_path)
        assert stop_record["payload"]["stopEnabled"] is False

        pipe.release[1].set()
        final = manager.wait(start["jobId"], 2.0)

        assert final is not None
        assert final.status == "succeeded"
        assert writer.write_calls == 1
        assert writer.release_calls >= 1
        assert any(
            event["event"] == "record.status" and event["payload"]["state"] == "recording"
            for event in events
        )
    finally:
        pipe.release[0].set()
        pipe.release[1].set()
        ui_backend.DEFAULT_PREVIEW_SERVICE = previous


def test_recording_write_error_is_reported_as_record_status() -> None:
    events: list[dict] = []
    manager = ui_backend.BridgeJobManager(events.append)
    cap = InfiniteCapture()
    pipe = StepPipeline(steps=1)
    writer = FakeWriter(fail_on_write=True)
    service = ui_backend.PreviewSessionService(
        job_manager=manager,
        capture_factory=lambda source: cap,
        pipeline_factory=lambda options: pipe,
        frame_encoder=lambda frame: b"error-frame",
        recording_factory=lambda options: RecordingController(
            writer_factory=FakeWriterFactory(writer),
            path_provider=lambda: Path("fake_outputs") / "record_requested.mp4",
        ),
    )
    previous = _install_preview_service(service)
    try:
        start = ui_backend.handle_command(
            ui_backend.CommandRequest(
                command="session.start",
                request_id="req-start-error",
                session_id="session-error",
                payload={"source": "0", "frameLimit": 1},
            )
        )
        assert pipe.annotating[0].wait(1.0)
        toggle = ui_backend.handle_command(
            ui_backend.CommandRequest(
                command="record.toggle",
                request_id="req-toggle-error",
                payload={"sessionId": "session-error"},
            )
        )
        assert toggle["payload"]["state"] == "recording"

        pipe.release[0].set()
        final = manager.wait(start["jobId"], 2.0)

        assert final is not None
        assert final.status == "succeeded"
        error_events = [
            event
            for event in events
            if event["event"] == "record.status" and event["payload"]["lastError"]
        ]
        assert error_events
        assert "fake write failed" in error_events[-1]["payload"]["lastError"]
        assert error_events[-1]["payload"]["state"] == "idle"
    finally:
        pipe.release[0].set()
        ui_backend.DEFAULT_PREVIEW_SERVICE = previous
