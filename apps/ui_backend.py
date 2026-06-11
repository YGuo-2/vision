# -*- coding: utf-8 -*-
"""JSON bridge contract for the Vue/Tauri desktop frontend.

This module intentionally starts with protocol primitives only. The long-running
job execution layer is added on top of these helpers so tests can lock the
message shape before UI work depends on it.
"""

from __future__ import annotations

import json
import os
import secrets
import socket
import struct
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import threading
import time
import traceback
from uuid import uuid4
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apps.camera_enum import DEFAULT_SCAN_LIMIT, CameraEntry, InputSourceState, enumerate_cameras
from core.backend_router import (
    BACKEND_YOLO,
    CAPABILITY_FINGERS,
    ModelAvailability,
    QualityProfile,
    route_for_analysis,
    route_for_preview,
)


JsonDict = dict[str, Any]


BRIDGE_VERSION = "1.0"


ACTION_LABELS_ZH = {
    "V_SIGN": "✌（V 手势）",
    "HANDS_UP": "双手举起",
    "LEFT_HAND_UP": "左手举起",
    "RIGHT_HAND_UP": "右手举起",
    "SQUAT": "下蹲",
}


RECORD_BTN_TEXT = {
    "idle": "开始录制",
    "recording": "暂停录制",
    "paused": "继续录制",
}


CAP_PROP_FRAME_WIDTH = 3
CAP_PROP_FRAME_HEIGHT = 4
CAP_PROP_FPS = 5
CAP_PROP_FRAME_COUNT = 7


# 预览帧瘦身参数（仅影响送往前端的副本，不影响录制原画质）。
PREVIEW_JPEG_QUALITY = 70
PREVIEW_MAX_EDGE = 960
PREVIEW_FRAME_EVENT_MIN_INTERVAL_S = 1.0 / 30.0
PREVIEW_CAPTURE_IDLE_SLEEP_S = 0.001
FRAME_CHANNEL_HOST = "127.0.0.1"
FRAME_CHANNEL_TOKEN_BYTES = 16
FRAME_CHANNEL_ACCEPT_TIMEOUT_S = 0.2


COMMANDS: dict[str, JsonDict] = {
    "bridge.ping": {
        "description": "Return bridge liveness and protocol version.",
        "long_running": False,
    },
    "camera.list": {
        "description": "Enumerate Windows camera devices.",
        "long_running": False,
    },
    "model.status": {
        "description": "Return MediaPipe model install status.",
        "long_running": False,
    },
    "model.download": {
        "description": "Download one model or all missing models.",
        "long_running": True,
        "stoppable": True,
    },
    "session.start": {
        "description": "Start realtime camera or offline video preview.",
        "long_running": True,
        "stoppable": True,
    },
    "session.warmup": {
        "description": "Pre-build and cache the MediaPipe pipeline for faster session start.",
        "long_running": True,
        "stoppable": True,
    },
    "session.stop": {
        "description": "Stop a running preview session.",
        "long_running": False,
    },
    "record.toggle": {
        "description": "Toggle idle, recording, and paused state.",
        "long_running": False,
    },
    "record.stop": {
        "description": "Finalize the current recording segment.",
        "long_running": False,
    },
    "template.create": {
        "description": "Create a pose template from a reference video.",
        "long_running": True,
        "stoppable": True,
    },
    "analysis.run": {
        "description": "Run template comparison and/or tech evaluation.",
        "long_running": True,
        "stoppable": True,
    },
    "job.stop": {
        "description": "Stop any long-running bridge job.",
        "long_running": False,
    },
}


@dataclass(frozen=True)
class BridgeError:
    code: str
    message: str
    detail: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        return {
            "code": self.code,
            "message": self.message,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class CommandRequest:
    command: str
    request_id: str
    payload: JsonDict = field(default_factory=dict)
    job_id: str | None = None
    session_id: str | None = None


@dataclass
class JobContext:
    command: str
    job_id: str
    request_id: str
    payload: JsonDict
    session_id: str | None
    stop_event: threading.Event
    emit: Callable[[str, JsonDict | None, BridgeError | None], None]

    def stopped(self) -> bool:
        return self.stop_event.is_set()

    def progress(self, event: str, payload: JsonDict | None = None) -> None:
        self.emit(event, payload or {}, None)

    def fail(self, code: str, message: str, detail: JsonDict | None = None) -> BridgeError:
        error = BridgeError(code, message, detail or {})
        self.emit(f"{self.command}.failed", {"requestId": self.request_id}, error)
        return error


@dataclass
class JobRecord:
    command: str
    job_id: str
    request_id: str
    payload: JsonDict
    session_id: str | None
    stop_event: threading.Event = field(default_factory=threading.Event)
    status: str = "pending"
    result: JsonDict | None = None
    error: BridgeError | None = None
    started_at: str | None = None
    ended_at: str | None = None
    thread: threading.Thread | None = None

    def snapshot(self) -> JsonDict:
        return {
            "command": self.command,
            "jobId": self.job_id,
            "requestId": self.request_id,
            "sessionId": self.session_id,
            "status": self.status,
            "result": self.result,
            "error": None if self.error is None else self.error.to_dict(),
            "startedAt": self.started_at,
            "endedAt": self.ended_at,
            "stopRequested": self.stop_event.is_set(),
        }


class BridgeJobManager:
    def __init__(self, emit: Callable[[JsonDict], None] | None = None) -> None:
        self._emit = emit or (lambda message: None)
        self._lock = threading.Lock()
        self._jobs: dict[str, JobRecord] = {}

    def submit(
        self,
        command: str,
        payload: JsonDict,
        handler: Callable[[JobContext], JsonDict],
        *,
        request_id: str | None = None,
        job_id: str | None = None,
        session_id: str | None = None,
    ) -> JobRecord:
        record = JobRecord(
            command=command,
            job_id=job_id or uuid4().hex,
            request_id=request_id or uuid4().hex,
            payload=dict(payload),
            session_id=session_id,
        )
        record.started_at = utc_timestamp()

        def _emit(event: str, event_payload: JsonDict | None, error: BridgeError | None) -> None:
            self._emit(
                make_event(
                    event,
                    payload=event_payload or {},
                    error=error,
                    job_id=record.job_id,
                    session_id=record.session_id,
                )
            )

        context = JobContext(
            command=command,
            job_id=record.job_id,
            request_id=record.request_id,
            payload=record.payload,
            session_id=record.session_id,
            stop_event=record.stop_event,
            emit=_emit,
        )

        def _run() -> None:
            try:
                with self._lock:
                    record.status = "running"
                    self._jobs[record.job_id] = record
                _emit("job.started", {"command": command, "requestId": record.request_id}, None)
                result = handler(context)
                with self._lock:
                    if record.stop_event.is_set():
                        record.status = "stopped"
                        record.result = result or {}
                        _emit("job.stopped", {"result": record.result}, None)
                    else:
                        record.status = "succeeded"
                        record.result = result or {}
                        _emit("job.completed", {"result": record.result}, None)
            except Exception as exc:  # noqa: BLE001 - serialize all job failures.
                error = BridgeError(
                    "job_failed",
                    str(exc),
                    {
                        "command": command,
                        "jobId": record.job_id,
                        "requestId": record.request_id,
                        "traceback": traceback.format_exc(),
                    },
                )
                with self._lock:
                    record.status = "failed"
                    record.error = error
                _emit("job.failed", {"command": command}, error)
            finally:
                record.ended_at = utc_timestamp()

        thread = threading.Thread(target=_run, name=f"bridge-job-{record.job_id}", daemon=True)
        record.thread = thread
        with self._lock:
            self._jobs[record.job_id] = record
        thread.start()
        return record

    def stop(self, job_id: str) -> bool:
        with self._lock:
            record = self._jobs.get(job_id)
            if record is None:
                return False
            if record.status not in {"pending", "running"}:
                return False
            record.stop_event.set()
            return True

    def stop_session(self, session_id: str, *, command: str | None = None) -> list[str]:
        with self._lock:
            stopped: list[str] = []
            for job_id, record in self._jobs.items():
                if record.session_id != session_id:
                    continue
                if command is not None and record.command != command:
                    continue
                if record.status not in {"pending", "running"}:
                    continue
                record.stop_event.set()
                stopped.append(job_id)
            return stopped

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)

    def active_job_ids(self) -> list[str]:
        with self._lock:
            return [
                job_id
                for job_id, record in self._jobs.items()
                if record.status in {"pending", "running"}
            ]

    def wait(self, job_id: str, timeout: float | None = None) -> JobRecord | None:
        record = self.get(job_id)
        if record is None or record.thread is None:
            return record
        record.thread.join(timeout)
        return self.get(job_id)


class BridgeMessageWriter:
    """Serialize bridge JSON lines shared by the main thread and job threads."""

    def __init__(self, stream: Any) -> None:
        self._stream = stream
        self._lock = threading.Lock()

    def write(self, message: JsonDict) -> None:
        self.write_encoded(encode_message(message))

    def write_encoded(self, encoded: str) -> None:
        line = encoded.rstrip("\r\n")
        with self._lock:
            self._stream.write(line)
            self._stream.write("\n")
            flush = getattr(self._stream, "flush", None)
            if flush is not None:
                flush()


@dataclass(frozen=True)
class PreviewSessionOptions:
    source: str
    source_kind: str
    pose_variant: str = "full"
    workers: int = 1
    enable_hands: bool = True
    record_dir: str | None = None
    frame_limit: int | None = None
    backend_route: JsonDict = field(default_factory=dict)

    def to_payload(self) -> JsonDict:
        return {
            "source": self.source,
            "sourceKind": self.source_kind,
            "poseVariant": self.pose_variant,
            "workers": self.workers,
            "enableHands": self.enable_hands,
            "recordDir": self.record_dir,
            "frameLimit": self.frame_limit,
            "backendRoute": self.backend_route,
        }


@dataclass
class ActivePreviewSession:
    session_id: str
    job_id: str
    recorder: Any
    emit: Callable[[str, JsonDict], None]
    frame_channel: "LatestFrameChannel | None" = None
    last_record_error: str | None = None


@dataclass(frozen=True)
class _CapturedPreviewFrame:
    index: int
    frame: Any
    captured_at: float


class _LatestPreviewFrameBuffer:
    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._latest: _CapturedPreviewFrame | None = None
        self._closed = False
        self._captured = 0
        self._dropped = 0

    def put(self, item: _CapturedPreviewFrame) -> None:
        with self._condition:
            if self._latest is not None:
                self._dropped += 1
            self._latest = item
            self._captured += 1
            self._condition.notify()

    def get_latest(self, *, timeout: float) -> _CapturedPreviewFrame | None:
        with self._condition:
            if self._latest is None and not self._closed:
                self._condition.wait(timeout)
            if self._latest is None:
                return None
            item = self._latest
            self._latest = None
            return item

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._condition.notify_all()

    @property
    def closed(self) -> bool:
        with self._condition:
            return self._closed

    def snapshot(self) -> JsonDict:
        with self._condition:
            return {
                "capturedFrames": self._captured,
                "droppedFrames": self._dropped,
                "hasPendingFrame": self._latest is not None,
            }


class LatestFrameChannel:
    """Localhost latest-frame byte channel for Rust raw IPC fetches."""

    def __init__(self, *, session_id: str, host: str = FRAME_CHANNEL_HOST) -> None:
        self.session_id = session_id
        self.host = host
        self.token = secrets.token_hex(FRAME_CHANNEL_TOKEN_BYTES)
        self._lock = threading.Lock()
        self._latest: bytes = b""
        self._frame_id = 0
        self._payload_bytes = 0
        self._served = 0
        self._closed = threading.Event()
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind((self.host, 0))
        self.port = int(self._socket.getsockname()[1])
        self._socket.listen(4)
        self._thread = threading.Thread(
            target=self._serve,
            name=f"preview-frame-channel-{session_id}",
            daemon=True,
        )
        self._thread.start()

    def publish(self, payload: bytes) -> JsonDict:
        data = bytes(payload)
        with self._lock:
            self._frame_id += 1
            self._latest = data
            self._payload_bytes = len(data)
            frame_id = self._frame_id
        return {
            "sessionId": self.session_id,
            "frameHandle": f"{self.session_id}:{frame_id}",
            "frameHost": self.host,
            "framePort": self.port,
            "frameToken": self.token,
            "frameId": frame_id,
            "frameBytes": len(data),
            "frameTransport": "tcp-length-prefixed",
        }

    def snapshot(self) -> JsonDict:
        with self._lock:
            return {
                "frameHost": self.host,
                "framePort": self.port,
                "frameToken": self.token,
                "frameId": self._frame_id,
                "frameBytes": self._payload_bytes,
                "framesServed": self._served,
                "frameTransport": "tcp-length-prefixed",
            }

    def close(self) -> None:
        self._closed.set()
        try:
            self._socket.close()
        except OSError:
            pass
        self._thread.join(timeout=1.0)

    def _serve(self) -> None:
        while not self._closed.is_set():
            try:
                self._socket.settimeout(FRAME_CHANNEL_ACCEPT_TIMEOUT_S)
                conn, _addr = self._socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with conn:
                try:
                    conn.settimeout(1.0)
                    request = conn.recv(512).decode("utf-8", errors="replace").strip().split()
                    if len(request) < 3 or request[0] != "GET":
                        conn.sendall(struct.pack(">I", 0))
                        continue
                    session_id, token = request[1], request[2]
                    if session_id != self.session_id or token != self.token:
                        conn.sendall(struct.pack(">I", 0))
                        continue
                    with self._lock:
                        payload = self._latest
                        self._served += 1
                    conn.sendall(struct.pack(">I", len(payload)))
                    if payload:
                        conn.sendall(payload)
                except OSError:
                    continue


@dataclass(frozen=True)
class TemplateCreateOptions:
    video_path: str
    pose_variant: str = "heavy"
    start: int | None = None
    end: int | None = None
    out_path: str | None = None
    workers: int = 1
    preview: bool = False

    def to_payload(self) -> JsonDict:
        return {
            "videoPath": self.video_path,
            "poseVariant": self.pose_variant,
            "startFrame": self.start,
            "endFrame": self.end,
            "outPath": self.out_path,
            "workers": self.workers,
            "preview": self.preview,
        }


@dataclass(frozen=True)
class AnalysisRunOptions:
    video_path: str
    template_path: str | None = None
    pose_variant: str = "full"
    workers: int = 1
    preview_out: str | None = None
    do_compare: bool = True
    do_tech_eval: bool = False
    stance: str = "left"
    view_hint: str = "auto"
    enable_hands: bool = True
    quality_profile: str = QualityProfile.DEFAULT.value
    debug_video: bool = False
    debug_out_path: str | None = None
    backend_route: JsonDict = field(default_factory=dict)

    def to_payload(self) -> JsonDict:
        return {
            "videoPath": self.video_path,
            "templatePath": self.template_path,
            "poseVariant": self.pose_variant,
            "workers": self.workers,
            "previewOut": self.preview_out,
            "doCompare": self.do_compare,
            "doTechEval": self.do_tech_eval,
            "stance": self.stance,
            "viewHint": self.view_hint,
            "enableHands": self.enable_hands,
            "qualityProfile": self.quality_profile,
            "debugVideo": self.debug_video,
            "debugOutPath": self.debug_out_path,
            "backendRoute": self.backend_route,
        }


class TemplateAnalysisService:
    def __init__(
        self,
        *,
        job_manager: BridgeJobManager | None = None,
        create_template: Callable[..., Path] | None = None,
        compare_template: Callable[..., Any] | None = None,
        evaluate_detail: Callable[..., Any] | None = None,
        evaluate_assets: Callable[..., Any] | None = None,
        export_debug: Callable[..., Path] | None = None,
    ) -> None:
        self._job_manager = job_manager
        self._create_template = create_template or _default_create_template
        self._compare_template = compare_template or _default_compare_template
        self._evaluate_detail = evaluate_detail or _default_evaluate_detail
        self._evaluate_assets = evaluate_assets or _default_evaluate_assets
        self._export_debug = export_debug or _default_export_debug

    @property
    def manager(self) -> BridgeJobManager:
        return self._job_manager or DEFAULT_JOB_MANAGER

    def start_template_create(self, request: CommandRequest) -> JsonDict:
        try:
            options = normalize_template_create_options(request.payload)
        except ValueError as exc:
            return make_response(
                request.request_id,
                ok=False,
                error=BridgeError("bad_request", str(exc), {"command": request.command}),
            )
        record = self.manager.submit(
            "template.create",
            options.to_payload(),
            self.run_template_create,
            request_id=request.request_id,
            job_id=request.job_id,
        )
        return make_response(
            request.request_id,
            ok=True,
            payload={"state": "starting", "jobId": record.job_id, **options.to_payload()},
            job_id=record.job_id,
        )

    def start_analysis_run(self, request: CommandRequest) -> JsonDict:
        try:
            options = normalize_analysis_run_options(request.payload)
        except ValueError as exc:
            return make_response(
                request.request_id,
                ok=False,
                error=BridgeError("bad_request", str(exc), {"command": request.command}),
            )
        if not bool(options.backend_route.get("ok", True)):
            return make_response(
                request.request_id,
                ok=False,
                payload={"backendRoute": options.backend_route},
                error=BridgeError(
                    str(options.backend_route.get("errorCode") or "backend_unavailable"),
                    str(options.backend_route.get("userMessage") or options.backend_route.get("reason") or "backend unavailable"),
                    {"command": request.command, "backendRoute": options.backend_route},
                ),
            )
        record = self.manager.submit(
            "analysis.run",
            options.to_payload(),
            self.run_analysis,
            request_id=request.request_id,
            job_id=request.job_id,
        )
        return make_response(
            request.request_id,
            ok=True,
            payload={"state": "starting", "jobId": record.job_id, **options.to_payload()},
            job_id=record.job_id,
        )

    def run_template_create(self, ctx: JobContext) -> JsonDict:
        options = normalize_template_create_options(ctx.payload)
        ctx.progress("template.status", {"state": "running", **options.to_payload()})
        template_path = self._create_template(
            options.video_path,
            pose_variant=options.pose_variant,
            start=options.start,
            end=options.end,
            out_path=options.out_path,
            workers=options.workers,
            preview=options.preview,
            progress_cb=_progress_callback(ctx, "template"),
            stop_evt=ctx.stop_event,
        )
        payload = {
            "state": "stopped" if ctx.stopped() else "completed",
            "templatePath": str(template_path),
            "templateMeta": _load_template_meta(Path(template_path)),
        }
        ctx.progress("template.status", payload)
        return payload

    def run_analysis(self, ctx: JobContext) -> JsonDict:
        options = normalize_analysis_run_options(ctx.payload, trust_existing_route=True)
        ctx.progress("analysis.status", {"state": "running", **options.to_payload()})
        payload: JsonDict = {
            "state": "running",
            "videoPath": options.video_path,
            "backendRoute": options.backend_route,
        }

        def finish() -> JsonDict:
            payload["state"] = "stopped" if ctx.stopped() else "completed"
            ctx.progress("analysis.status", payload)
            return _to_jsonable(payload)

        if options.do_compare:
            if not options.template_path:
                raise ValueError("templatePath is required when doCompare is true")
            result = self._compare_template(
                options.template_path,
                options.video_path,
                pose_variant=options.pose_variant,
                workers=options.workers,
                preview_out=options.preview_out,
                progress_cb=_progress_callback(ctx, "analysis"),
                stop_evt=ctx.stop_event,
            )
            payload["compare"] = _compare_result_payload(result)
            if options.template_path:
                payload["compare"]["templateMeta"] = _load_template_meta(Path(options.template_path))
            if ctx.stopped():
                return finish()

        if options.do_tech_eval:
            if ctx.stopped():
                return finish()
            ctx.progress("analysis.progress", {"stage": "技术评估中", "done": 0, "total": 0, "percent": None})
            if ctx.stopped():
                return finish()
            payload["techEval"] = self._run_tech_eval(options)

        return finish()

    def _run_tech_eval(self, options: AnalysisRunOptions) -> JsonDict:
        video = Path(options.video_path)
        landmarks = view_scores = meta = None
        if options.debug_video:
            res, landmarks, view_scores, meta = self._evaluate_assets(
                video,
                pose_variant=options.pose_variant,
                stance=options.stance,
                view_hint=options.view_hint,
            )
        else:
            res = self._evaluate_detail(
                video,
                pose_variant=options.pose_variant,
                stance=options.stance,
                view_hint=options.view_hint,
            )

        payload = _tech_eval_payload(res, pose_variant=options.pose_variant)
        if options.debug_video and landmarks is not None and view_scores is not None and meta is not None:
            out_path = (
                Path(options.debug_out_path)
                if options.debug_out_path
                else _default_debug_video_path(video)
            )
            actual = self._export_debug(
                video,
                out_path,
                pose_variant=options.pose_variant,
                stance=options.stance,
                view_hint=options.view_hint,
                res=res,
                landmarks=landmarks,
                view_scores=view_scores,
                meta=meta,
            )
            payload["debugVideo"] = str(actual)
        return payload


class ModelManagementService:
    def __init__(
        self,
        *,
        job_manager: BridgeJobManager | None = None,
        specs: tuple[Any, ...] | None = None,
        models_dir_func: Callable[[], Path] | None = None,
        is_installed_func: Callable[[Any], bool] | None = None,
        installed_size_func: Callable[[Any], float | None] | None = None,
        model_path_func: Callable[[Any], Path] | None = None,
        download_func: Callable[..., Path] | None = None,
    ) -> None:
        self._job_manager = job_manager
        self._specs = specs
        self._models_dir_func = models_dir_func or _default_models_dir
        self._is_installed = is_installed_func or _default_model_is_installed
        self._installed_size = installed_size_func or _default_installed_size_mb
        self._model_path = model_path_func or _default_model_path
        self._download = download_func or _default_download_model

    @property
    def manager(self) -> BridgeJobManager:
        return self._job_manager or DEFAULT_JOB_MANAGER

    @property
    def specs(self) -> tuple[Any, ...]:
        return self._specs if self._specs is not None else _default_model_specs()

    def status(self, request: CommandRequest) -> JsonDict:
        pose_variant = _pose_variant(request.payload, default="full")
        enable_hands = _payload_bool(request.payload.get("enableHands"), default=True)
        payload = self._status_payload(pose_variant=pose_variant, enable_hands=enable_hands)
        return make_response(request.request_id, ok=True, payload=payload)

    def start_download(self, request: CommandRequest) -> JsonDict:
        try:
            specs = self._download_specs(request.payload)
        except ValueError as exc:
            return make_response(
                request.request_id,
                ok=False,
                error=BridgeError("bad_request", str(exc), {"command": request.command}),
            )
        record = self.manager.submit(
            "model.download",
            {"modelKeys": [_spec_key(spec) for spec in specs]},
            self.run_download,
            request_id=request.request_id,
            job_id=request.job_id,
        )
        return make_response(
            request.request_id,
            ok=True,
            payload={"state": "starting", "jobId": record.job_id, "modelKeys": [_spec_key(spec) for spec in specs]},
            job_id=record.job_id,
        )

    def run_download(self, ctx: JobContext) -> JsonDict:
        specs = [self._spec_by_key(key) for key in ctx.payload.get("modelKeys", [])]
        completed: list[JsonDict] = []
        failed: list[JsonDict] = []
        for spec in specs:
            if ctx.stopped():
                break
            if not bool(getattr(spec, "downloadable", True)):
                failed.append(
                    {
                        "key": _spec_key(spec),
                        "error": str(getattr(spec, "note", "") or "该模型暂不支持自动下载"),
                        "interrupted": False,
                        "manualInstallRequired": True,
                    }
                )
                continue
            ctx.progress("model.status", {"state": "downloading", "modelKey": _spec_key(spec), "label": _spec_label(spec)})
            try:
                path = self._download(
                    spec,
                    progress_cb=lambda downloaded, total, spec=spec: self._emit_download_progress(
                        ctx, spec, downloaded, total
                    ),
                    should_stop=ctx.stop_event.is_set,
                )
                completed.append({"key": _spec_key(spec), "path": str(path)})
            except InterruptedError as exc:
                failed.append({"key": _spec_key(spec), "error": str(exc), "interrupted": True})
                ctx.stop_event.set()
                break
            except Exception as exc:  # noqa: BLE001 - per-model failures are reported together.
                failed.append({"key": _spec_key(spec), "error": str(exc), "interrupted": False})

        state = "stopped" if ctx.stopped() else ("failed" if failed else "completed")
        payload = {"state": state, "completed": completed, "failed": failed}
        ctx.progress("model.status", payload)
        return payload

    def _status_payload(self, *, pose_variant: str, enable_hands: bool) -> JsonDict:
        active_keys = {_pose_model_key(pose_variant)}
        if enable_hands:
            active_keys.add("hand")
        route = route_for_preview(
            enable_hands=enable_hands,
            model_availability=_default_route_model_availability(),
        )
        models = []
        missing = []
        for spec in self.specs:
            key = _spec_key(spec)
            installed = bool(self._is_installed(spec))
            item = {
                "key": key,
                "filename": str(getattr(spec, "filename", "")),
                "label": _spec_label(spec),
                "approxMb": getattr(spec, "approx_mb", None),
                "path": str(self._model_path(spec)),
                "installed": installed,
                "sizeMb": self._installed_size(spec),
                "active": key in active_keys,
                "category": str(getattr(spec, "category", "mediapipe")),
                "profile": str(getattr(spec, "profile", key)),
                "downloadable": bool(getattr(spec, "downloadable", True)),
                "installedSupported": bool(getattr(spec, "installed_supported", True)),
                "defaultRouteEligible": bool(getattr(spec, "default_route_eligible", True)),
                "note": str(getattr(spec, "note", "")),
            }
            if not installed and bool(getattr(spec, "downloadable", True)):
                missing.append(key)
            models.append(item)
        return {
            "modelsDir": str(self._models_dir_func()),
            "poseVariant": pose_variant,
            "enableHands": enable_hands,
            "activeKeys": sorted(active_keys),
            "missingKeys": missing,
            "backendRoute": route.to_camel_dict(),
            "yoloRuntime": {
                "supported": False,
                "packaged": False,
                "message": "当前安装版 sidecar 不打包 YOLO runtime；YOLO 档位仅展示状态，不进入正式评分默认路由。",
            },
            "models": models,
        }

    def _download_specs(self, payload: JsonDict) -> list[Any]:
        all_missing = _payload_bool(payload.get("allMissing", payload.get("all")), default=False)
        if all_missing:
            return [spec for spec in self.specs if not self._is_installed(spec)]
        key = str(payload.get("modelKey") or payload.get("key") or "").strip()
        if not key:
            raise ValueError("modelKey or allMissing is required")
        return [self._spec_by_key(key)]

    def _spec_by_key(self, key: str) -> Any:
        for spec in self.specs:
            if _spec_key(spec) == key:
                return spec
        raise ValueError(f"unknown model key: {key}")

    def _emit_download_progress(self, ctx: JobContext, spec: Any, downloaded: int, total: int | None) -> None:
        ctx.progress(
            "model.progress",
            {
                "modelKey": _spec_key(spec),
                "label": _spec_label(spec),
                "downloaded": int(downloaded),
                "total": None if total is None else int(total),
                "percent": (float(downloaded) / float(total) * 100.0) if total else None,
            },
        )


class PreviewSessionService:
    def __init__(
        self,
        *,
        job_manager: BridgeJobManager | None = None,
        capture_factory: Callable[[str], Any] | None = None,
        pipeline_factory: Callable[[PreviewSessionOptions], Any] | None = None,
        frame_encoder: Callable[[Any], bytes] | None = None,
        recording_factory: Callable[[PreviewSessionOptions], Any] | None = None,
        monotonic: Callable[[], float] | None = None,
    ) -> None:
        self._job_manager = job_manager
        self._capture_factory = capture_factory or _default_capture_factory
        self._pipeline_factory = pipeline_factory or _default_pipeline_factory
        self._frame_encoder = frame_encoder or _default_frame_encoder
        self._recording_factory = recording_factory or _default_recording_factory
        self._monotonic = monotonic or time.monotonic
        self._sessions_lock = threading.Lock()
        self._sessions: dict[str, ActivePreviewSession] = {}
        # 预热缓存：按配置键复用 MediaPipe pipeline，避免每次「开始」重建模型。
        # 仅摄像头会话复用（其时间戳基于单调时钟，跨会话单调递增）；视频文件不缓存复用，
        # 因其时间戳按 frame_index 计算，跨文件会回退，违反 VIDEO 模式时间戳单调约束。
        self._pipeline_cache_lock = threading.Lock()
        self._pipeline_cache: dict[tuple[str, bool], Any] = {}

    @property
    def manager(self) -> BridgeJobManager:
        return self._job_manager or DEFAULT_JOB_MANAGER

    @staticmethod
    def _pipeline_cache_key(options: PreviewSessionOptions) -> tuple[str, str, bool]:
        route = options.backend_route or {}
        backend = str(route.get("backend") or "mediapipe")
        model_profile = str(route.get("modelProfile") or options.pose_variant)
        return (backend, model_profile, bool(options.enable_hands))

    def _acquire_pipeline(self, options: PreviewSessionOptions) -> tuple[Any, bool]:
        """返回 (pipeline, cached)。摄像头命中缓存则复用；否则新建。

        cached=True 表示该实例归缓存所有，会话结束时不得关闭它。
        """
        if options.source_kind == "camera":
            key = self._pipeline_cache_key(options)
            with self._pipeline_cache_lock:
                pipe = self._pipeline_cache.get(key)
                if pipe is not None:
                    return pipe, True
            pipe = self._pipeline_factory(options)
            with self._pipeline_cache_lock:
                existing = self._pipeline_cache.get(key)
                if existing is not None:
                    # 并发预热/启动竞争：丢弃本次新建，复用已入缓存实例。
                    _close_quietly(pipe)
                    return existing, True
                self._pipeline_cache[key] = pipe
            return pipe, True
        # 视频文件：每次新建独立实例，会话结束时关闭。
        return self._pipeline_factory(options), False

    def warmup(self, request: CommandRequest) -> JsonDict:
        """后台预建并缓存 MediaPipe pipeline，使后续「开始」命中缓存、首帧更快。"""
        try:
            pose_variant = str(
                request.payload.get("poseVariant") or request.payload.get("pose_variant") or "full"
            ).strip().lower()
            if pose_variant not in {"lite", "full", "heavy"}:
                raise ValueError("poseVariant must be one of: lite, full, heavy")
            enable_hands = _payload_bool(
                request.payload.get("enableHands", request.payload.get("enable_hands")), default=True
            )
        except ValueError as exc:
            return make_response(
                request.request_id,
                ok=False,
                error=BridgeError("bad_request", str(exc), {"command": request.command}),
            )

        warmup_options = PreviewSessionOptions(
            source="0",
            source_kind="camera",
            pose_variant=pose_variant,
            enable_hands=enable_hands,
        )

        def _run(ctx: JobContext) -> JsonDict:
            self._acquire_pipeline(warmup_options)
            return {"state": "ready", "poseVariant": pose_variant, "enableHands": enable_hands}

        record = self.manager.submit(
            "session.warmup",
            {"poseVariant": pose_variant, "enableHands": enable_hands},
            _run,
            request_id=request.request_id,
            job_id=request.job_id,
        )
        return make_response(
            request.request_id,
            ok=True,
            payload={
                "state": "warming",
                "jobId": record.job_id,
                "poseVariant": pose_variant,
                "enableHands": enable_hands,
            },
            job_id=record.job_id,
        )

    def start(self, request: CommandRequest) -> JsonDict:
        try:
            options = normalize_session_options(request.payload)
        except ValueError as exc:
            return make_response(
                request.request_id,
                ok=False,
                error=BridgeError("bad_request", str(exc), {"command": request.command}),
            )

        session_id = request.session_id or str(request.payload.get("sessionId") or uuid4().hex)
        record = self.manager.submit(
            "session.start",
            options.to_payload(),
            self.run,
            request_id=request.request_id,
            job_id=request.job_id,
            session_id=session_id,
        )
        return make_response(
            request.request_id,
            ok=True,
            payload={
                "state": "starting",
                "jobId": record.job_id,
                "sessionId": session_id,
                "source": options.source,
                "sourceKind": options.source_kind,
                "poseVariant": options.pose_variant,
                "workers": options.workers,
                "enableHands": options.enable_hands,
                "backendRoute": options.backend_route,
                "recordDir": options.record_dir,
            },
            job_id=record.job_id,
            session_id=session_id,
        )

    def stop(self, request: CommandRequest) -> JsonDict:
        job_id = str(request.payload.get("jobId") or request.job_id or "").strip()
        session_id = str(request.payload.get("sessionId") or request.session_id or "").strip()
        stopped_job_ids: list[str] = []

        if job_id:
            if self.manager.stop(job_id):
                stopped_job_ids = [job_id]
        elif session_id:
            stopped_job_ids = self.manager.stop_session(session_id, command="session.start")
        else:
            return make_response(
                request.request_id,
                ok=False,
                error=BridgeError("bad_request", "jobId or sessionId is required to stop a session"),
            )

        if not stopped_job_ids:
            return make_response(
                request.request_id,
                ok=False,
                error=BridgeError(
                    "not_found",
                    "session job not found",
                    {"jobId": job_id or None, "sessionId": session_id or None},
                ),
                job_id=job_id or None,
                session_id=session_id or None,
            )
        return make_response(
            request.request_id,
            ok=True,
            payload={
                "stopped": True,
                "jobIds": stopped_job_ids,
                "sessionId": session_id or request.session_id,
            },
            job_id=job_id or stopped_job_ids[0],
            session_id=session_id or request.session_id,
        )

    def record_toggle(self, request: CommandRequest) -> JsonDict:
        active = self._active_from_request(request)
        if active is None:
            return make_response(
                request.request_id,
                ok=False,
                error=BridgeError(
                    "not_found",
                    "recording session not found",
                    {"sessionId": request.payload.get("sessionId") or request.session_id},
                ),
                session_id=request.payload.get("sessionId") or request.session_id,
            )
        state = active.recorder.request_toggle()
        payload = _recording_payload(active.recorder.snapshot(), session_id=active.session_id)
        active.emit("record.status", payload)
        return make_response(
            request.request_id,
            ok=True,
            payload={**payload, "buttonText": RECORD_BTN_TEXT[state]},
            job_id=active.job_id,
            session_id=active.session_id,
        )

    def record_stop(self, request: CommandRequest) -> JsonDict:
        active = self._active_from_request(request)
        if active is None:
            return make_response(
                request.request_id,
                ok=False,
                error=BridgeError(
                    "not_found",
                    "recording session not found",
                    {"sessionId": request.payload.get("sessionId") or request.session_id},
                ),
                session_id=request.payload.get("sessionId") or request.session_id,
            )
        result_path = active.recorder.stop_recording()
        payload = _recording_payload(
            active.recorder.snapshot(),
            session_id=active.session_id,
            result_path=result_path,
        )
        active.emit("record.status", payload)
        return make_response(
            request.request_id,
            ok=True,
            payload=payload,
            job_id=active.job_id,
            session_id=active.session_id,
        )

    def run(self, ctx: JobContext) -> JsonDict:
        options = normalize_session_options(ctx.payload, trust_existing_route=True)
        cap = None
        pipe = None
        pipe_cached = False
        recorder = self._recording_factory(options)
        frame_channel: LatestFrameChannel | None = None
        frame_count = 0
        total = 0
        fps_for_ts = 30.0
        is_file = options.source_kind == "video"

        ctx.progress(
            "session.status",
            {
                "state": "opening",
                "source": options.source,
                "sourceKind": options.source_kind,
                "backendRoute": options.backend_route,
            },
        )

        try:
            cap = self._capture_factory(options.source)
            if not _capture_is_opened(cap):
                raise RuntimeError(f"无法打开输入源：{options.source}")

            src_fps = _capture_float(cap, CAP_PROP_FPS, 0.0)
            fps_for_ts = src_fps if is_file and src_fps > 1e-3 else 30.0
            total = int(_capture_float(cap, CAP_PROP_FRAME_COUNT, 0.0)) if is_file else 0
            width = int(_capture_float(cap, CAP_PROP_FRAME_WIDTH, 1280.0))
            height = int(_capture_float(cap, CAP_PROP_FRAME_HEIGHT, 720.0))
            recorder.begin_session(fps=fps_for_ts, size=(width, height))
            if ctx.session_id:
                frame_channel = LatestFrameChannel(session_id=ctx.session_id)
            active = ActivePreviewSession(
                session_id=ctx.session_id or "",
                job_id=ctx.job_id,
                recorder=recorder,
                frame_channel=frame_channel,
                emit=lambda event, payload: ctx.progress(event, payload),
            )
            self._register_active_session(active)

            pipe, pipe_cached = self._acquire_pipeline(options)
            started_at = self._monotonic()
            ctx.progress(
                "session.status",
                {
                    "state": "running",
                    "source": options.source,
                    "sourceKind": options.source_kind,
                    "fpsForTimestamp": fps_for_ts,
                    "totalFrames": total,
                    "size": {"width": width, "height": height},
                    "frameChannel": None if frame_channel is None else frame_channel.snapshot(),
                    "backendRoute": options.backend_route,
                },
            )

            realtime_stats: JsonDict = {}
            if is_file:
                frame_count = self._run_sequential_preview_loop(
                    ctx=ctx,
                    options=options,
                    cap=cap,
                    pipe=pipe,
                    recorder=recorder,
                    active=active,
                    width=width,
                    height=height,
                    fps_for_ts=fps_for_ts,
                    total=total,
                    started_at=started_at,
                )
            else:
                frame_count, realtime_stats = self._run_realtime_camera_loop(
                    ctx=ctx,
                    options=options,
                    cap=cap,
                    pipe=pipe,
                    recorder=recorder,
                    active=active,
                    width=width,
                    height=height,
                    fps_for_ts=fps_for_ts,
                    total=total,
                    started_at=started_at,
                )

            state = "stopped" if ctx.stopped() else "completed"
            status_payload: JsonDict = {
                "state": state,
                "frames": frame_count,
                "totalFrames": total,
                "backendRoute": options.backend_route,
            }
            if frame_channel is not None:
                status_payload["frameChannel"] = frame_channel.snapshot()
            status_payload.update(realtime_stats)
            ctx.progress(
                "session.status",
                status_payload,
            )
            result: JsonDict = {
                "state": state,
                "frames": frame_count,
                "totalFrames": total,
                "source": options.source,
                "sourceKind": options.source_kind,
                "backendRoute": options.backend_route,
            }
            if frame_channel is not None:
                result["frameChannel"] = frame_channel.snapshot()
            result.update(realtime_stats)
            return result
        finally:
            result_path = None
            try:
                result_path = recorder.close_session()
            finally:
                if ctx.session_id:
                    self._unregister_active_session(ctx.session_id)
                if frame_channel is not None:
                    frame_channel.close()
            ctx.progress(
                "record.status",
                _recording_payload(
                    recorder.snapshot(),
                    session_id=ctx.session_id,
                    result_path=result_path,
                ),
            )
            if not pipe_cached:
                _close_quietly(pipe)
            _release_quietly(cap)

    def _run_sequential_preview_loop(
        self,
        *,
        ctx: JobContext,
        options: PreviewSessionOptions,
        cap: Any,
        pipe: Any,
        recorder: Any,
        active: ActivePreviewSession,
        width: int,
        height: int,
        fps_for_ts: float,
        total: int,
        started_at: float,
    ) -> int:
        frame_count = 0
        while not ctx.stopped():
            ok, frame = cap.read()
            if not ok:
                break

            timestamp_ms = _next_timestamp_ms(
                pipe,
                is_file=True,
                fps_for_ts=fps_for_ts,
                frame_index=frame_count,
                started_at=started_at,
                monotonic=self._monotonic,
            )
            annotated_result = pipe.annotate(frame, timestamp_ms=timestamp_ms)
            annotated, actions, frame_meta = _normalize_annotate_result(annotated_result)
            frame_count += 1
            self._emit_preview_frame(
                ctx=ctx,
                annotated=annotated,
                actions=actions,
                frame_count=frame_count,
                total=total,
                width=width,
                height=height,
                started_at=started_at,
                frame_meta=frame_meta,
            )
            recorder.write_frame(annotated)
            self._emit_recording_error_if_needed(active)

            if total > 0 and (frame_count % 5 == 0 or frame_count == total):
                ctx.progress("session.progress", _progress_payload(frame_count, total))

            if options.frame_limit is not None and frame_count >= options.frame_limit:
                break
        return frame_count

    def _run_realtime_camera_loop(
        self,
        *,
        ctx: JobContext,
        options: PreviewSessionOptions,
        cap: Any,
        pipe: Any,
        recorder: Any,
        active: ActivePreviewSession,
        width: int,
        height: int,
        fps_for_ts: float,
        total: int,
        started_at: float,
    ) -> tuple[int, JsonDict]:
        buffer = _LatestPreviewFrameBuffer()
        capture_stop = threading.Event()
        capture_errors: list[BaseException] = []

        def _capture_latest() -> None:
            source_index = 0
            try:
                while not capture_stop.is_set() and not ctx.stopped():
                    ok, frame = cap.read()
                    if not ok:
                        break
                    source_index += 1
                    buffer.put(
                        _CapturedPreviewFrame(
                            index=source_index,
                            frame=frame,
                            captured_at=self._monotonic(),
                        )
                    )
                    time.sleep(PREVIEW_CAPTURE_IDLE_SLEEP_S)
            except BaseException as exc:  # noqa: BLE001 - surface capture failures through the job envelope.
                capture_errors.append(exc)
            finally:
                buffer.close()

        capture_thread = threading.Thread(target=_capture_latest, name=f"preview-capture-{ctx.job_id}", daemon=True)
        capture_thread.start()

        frame_count = 0
        last_frame_event_at: float | None = None
        try:
            while not ctx.stopped():
                item = buffer.get_latest(timeout=0.05)
                if item is None:
                    if buffer.closed:
                        break
                    continue

                timestamp_ms = _next_timestamp_ms(
                    pipe,
                    is_file=False,
                    fps_for_ts=fps_for_ts,
                    frame_index=frame_count,
                    started_at=started_at,
                    monotonic=self._monotonic,
                )
                annotated_result = pipe.annotate(item.frame, timestamp_ms=timestamp_ms)
                annotated, actions, frame_meta = _normalize_annotate_result(annotated_result)
                frame_count += 1

                now = self._monotonic()
                if last_frame_event_at is None or now - last_frame_event_at >= PREVIEW_FRAME_EVENT_MIN_INTERVAL_S:
                    self._emit_preview_frame(
                        ctx=ctx,
                        annotated=annotated,
                        actions=actions,
                        frame_count=frame_count,
                        total=total,
                        width=width,
                        height=height,
                        started_at=started_at,
                        frame_meta=frame_meta,
                        extra_payload={
                            "sourceFrameIndex": item.index,
                            "sourceFrameAgeMs": int(max(0.0, (now - item.captured_at) * 1000.0)),
                        },
                    )
                    last_frame_event_at = now

                recorder.write_frame(annotated)
                self._emit_recording_error_if_needed(active)

                if options.frame_limit is not None and frame_count >= options.frame_limit:
                    break

            if capture_errors and not ctx.stopped():
                raise RuntimeError(f"摄像头采集失败：{capture_errors[0]}")
            stats = buffer.snapshot()
            stats["renderedFrames"] = frame_count
            return frame_count, stats
        finally:
            capture_stop.set()
            buffer.close()
            capture_thread.join(timeout=1.0)

    def _emit_preview_frame(
        self,
        *,
        ctx: JobContext,
        annotated: Any,
        actions: list[str],
        frame_count: int,
        total: int,
        width: int,
        height: int,
        started_at: float,
        frame_meta: JsonDict | None = None,
        extra_payload: JsonDict | None = None,
    ) -> None:
        elapsed = self._monotonic() - started_at
        fps = frame_count / max(1e-6, elapsed)
        actions_zh = [ACTION_LABELS_ZH.get(str(action), str(action)) for action in actions]
        frame_width, frame_height = _frame_size(annotated, fallback=(width, height))
        encoded = self._frame_encoder(annotated)
        if isinstance(encoded, str):
            encoded = encoded.encode("utf-8")
        channel_payload: JsonDict = {}
        active = None if ctx.session_id is None else self._active_session(ctx.session_id)
        if active is not None and active.frame_channel is not None:
            channel_payload = active.frame_channel.publish(bytes(encoded))
        frame_payload: JsonDict = {
            "actions": list(actions),
            "actionsZh": actions_zh,
            "actionsText": ", ".join(actions_zh) if actions_zh else "-",
            "frameIndex": frame_count,
            "fps": fps,
            "progress": _progress_payload(frame_count, total),
            "size": {"width": frame_width, "height": frame_height},
            "payloadBytes": len(encoded),
            "frameTransport": "tcp-length-prefixed",
        }
        if frame_meta:
            frame_payload["backendMeta"] = _to_camel_meta(frame_meta)
            backend = frame_meta.get("backend")
            if backend:
                frame_payload["backend"] = str(backend)
            for source_key, target_key in (
                ("multi_person_detected", "multiPersonDetected"),
                ("person_count", "personCount"),
                ("review_required", "reviewRequired"),
                ("target_policy", "targetPolicy"),
            ):
                if source_key in frame_meta:
                    frame_payload[target_key] = frame_meta[source_key]
        frame_payload.update(channel_payload)
        if extra_payload:
            frame_payload.update(extra_payload)
        ctx.progress("session.frame", frame_payload)

    def _active_from_request(self, request: CommandRequest) -> ActivePreviewSession | None:
        session_id = str(request.payload.get("sessionId") or request.session_id or "").strip()
        if not session_id:
            return None
        return self._active_session(session_id)

    def _active_session(self, session_id: str) -> ActivePreviewSession | None:
        with self._sessions_lock:
            return self._sessions.get(session_id)

    def _register_active_session(self, active: ActivePreviewSession) -> None:
        if not active.session_id:
            return
        with self._sessions_lock:
            self._sessions[active.session_id] = active
        active.emit(
            "record.status",
            _recording_payload(active.recorder.snapshot(), session_id=active.session_id),
        )

    def _unregister_active_session(self, session_id: str) -> None:
        with self._sessions_lock:
            self._sessions.pop(session_id, None)

    def _emit_recording_error_if_needed(self, active: ActivePreviewSession) -> None:
        snapshot = active.recorder.snapshot()
        if not snapshot.last_error or snapshot.last_error == active.last_record_error:
            return
        active.last_record_error = snapshot.last_error
        active.emit(
            "record.status",
            _recording_payload(snapshot, session_id=active.session_id),
        )


def clamp_workers(value: Any) -> int:
    upper = os.cpu_count() or 1
    upper = max(1, int(upper))
    try:
        workers = int(value)
    except (TypeError, ValueError):
        workers = 1
    return max(1, min(workers, upper))


def normalize_session_options(payload: JsonDict, *, trust_existing_route: bool = False) -> PreviewSessionOptions:
    source = str(payload.get("source") or "").strip()
    source_kind = str(payload.get("sourceKind") or payload.get("source_kind") or "").strip().lower()
    state = InputSourceState()

    if source:
        if source_kind == "camera":
            if not source.isdigit():
                raise ValueError("camera source must be a numeric index")
            state.select_camera(int(source))
        elif source_kind == "video":
            if source.isdigit():
                raise ValueError("video source must be a non-numeric path")
            state.select_video(source)
        elif source.isdigit():
            state.select_camera(int(source))
        else:
            state.select_video(source)
    elif source_kind == "camera":
        raw_index = payload.get("cameraIndex", payload.get("camera_index"))
        if raw_index in (None, ""):
            raise ValueError("cameraIndex is required for camera source")
        state.select_camera(int(raw_index))
    elif source_kind == "video":
        video_path = str(payload.get("videoPath") or payload.get("video_path") or "").strip()
        if not video_path:
            raise ValueError("videoPath is required for video source")
        if video_path.isdigit():
            raise ValueError("video source must be a non-numeric path")
        state.select_video(video_path)
    else:
        raise ValueError("source, cameraIndex, or videoPath is required")

    pose_variant = str(payload.get("poseVariant") or payload.get("pose_variant") or "full").strip().lower()
    if pose_variant not in {"lite", "full", "heavy"}:
        raise ValueError("poseVariant must be one of: lite, full, heavy")

    frame_limit = _optional_positive_int(payload.get("frameLimit", payload.get("frame_limit")))
    enable_hands = _payload_bool(payload.get("enableHands", payload.get("enable_hands")), default=True)
    route_payload = payload.get("backendRoute") if trust_existing_route else None
    if isinstance(route_payload, dict):
        route_dict = dict(route_payload)
    else:
        route_dict = route_for_preview(
            enable_hands=enable_hands,
            model_availability=_route_model_availability_from_payload(payload),
        ).to_camel_dict()
    return PreviewSessionOptions(
        source=state.value,
        source_kind=state.kind,
        pose_variant=pose_variant,
        workers=clamp_workers(payload.get("workers", 1)),
        enable_hands=enable_hands,
        record_dir=_optional_str(payload.get("recordDir", payload.get("record_dir"))),
        frame_limit=frame_limit,
        backend_route=route_dict,
    )


def normalize_template_create_options(payload: JsonDict) -> TemplateCreateOptions:
    video_path = _required_path(payload, "videoPath", "baseVideo", "video")
    pose_variant = _pose_variant(payload, default="heavy")
    return TemplateCreateOptions(
        video_path=video_path,
        pose_variant=pose_variant,
        start=_optional_int(payload.get("startFrame", payload.get("start"))),
        end=_optional_int(payload.get("endFrame", payload.get("end"))),
        out_path=_optional_str(payload.get("outPath", payload.get("templateOut"))),
        workers=clamp_workers(payload.get("workers", 1)),
        preview=_payload_bool(payload.get("preview"), default=False),
    )


def normalize_analysis_run_options(payload: JsonDict, *, trust_existing_route: bool = False) -> AnalysisRunOptions:
    video_path = _required_path(payload, "videoPath", "targetVideo", "video")
    do_compare = _payload_bool(
        payload.get("doCompare", payload.get("enableTemplateCompare")),
        default=True,
    )
    do_tech_eval = _payload_bool(
        payload.get("doTechEval", payload.get("enableTechEval")),
        default=False,
    )
    quality_profile = str(
        payload.get("qualityProfile") or payload.get("quality_profile") or QualityProfile.DEFAULT.value
    ).strip().lower() or QualityProfile.DEFAULT.value
    if not do_compare and not do_tech_eval and quality_profile != QualityProfile.HIGH_QUALITY.value:
        raise ValueError("at least one of doCompare or doTechEval must be true")
    template_path = _optional_str(payload.get("templatePath", payload.get("template")))
    if do_compare and not template_path:
        raise ValueError("templatePath is required when doCompare is true")
    enable_hands = _payload_bool(payload.get("enableHands", payload.get("enable_hands")), default=True)
    requires_capabilities = tuple(payload.get("requiresCapabilities") or payload.get("requires_capabilities") or ())
    route_payload = payload.get("backendRoute") if trust_existing_route else None
    if isinstance(route_payload, dict):
        route_dict = dict(route_payload)
    else:
        route_dict = route_for_analysis(
            enable_hands=enable_hands,
            do_compare=do_compare,
            do_tech_eval=do_tech_eval,
            quality_profile=quality_profile,
            model_availability=_route_model_availability_from_payload(payload),
            requires_capabilities=tuple(str(item) for item in requires_capabilities),
        ).to_camel_dict()
    return AnalysisRunOptions(
        video_path=video_path,
        template_path=template_path,
        pose_variant=_pose_variant(payload, default="full"),
        workers=clamp_workers(payload.get("workers", 1)),
        preview_out=_optional_str(payload.get("previewOut", payload.get("previewPath"))),
        do_compare=do_compare,
        do_tech_eval=do_tech_eval,
        stance=str(payload.get("stance") or "left").strip() or "left",
        view_hint=str(payload.get("viewHint") or payload.get("view_hint") or "auto").strip() or "auto",
        enable_hands=enable_hands,
        quality_profile=quality_profile,
        debug_video=_payload_bool(payload.get("debugVideo"), default=False),
        debug_out_path=_optional_str(payload.get("debugOutPath", payload.get("debugVideoPath"))),
        backend_route=route_dict,
    )


def _required_path(payload: JsonDict, *keys: str) -> str:
    for key in keys:
        value = _optional_str(payload.get(key))
        if value:
            return value
    raise ValueError(f"{'/'.join(keys)} is required")


def _pose_variant(payload: JsonDict, *, default: str) -> str:
    pose_variant = str(payload.get("poseVariant") or payload.get("pose_variant") or default).strip().lower()
    if pose_variant not in {"lite", "full", "heavy"}:
        raise ValueError("poseVariant must be one of: lite, full, heavy")
    return pose_variant


def _default_route_model_availability() -> ModelAvailability:
    return ModelAvailability(
        yolo_realtime=False,
        yolo26l=False,
        yolo_supported=False,
        reason="YOLO runtime is not enabled for this bridge path yet",
    )


def _route_model_availability_from_payload(payload: JsonDict) -> ModelAvailability:
    raw = payload.get("modelAvailability") or payload.get("model_availability")
    if not isinstance(raw, dict):
        return _default_route_model_availability()
    return ModelAvailability(
        yolo_realtime=_payload_bool(raw.get("yoloRealtime", raw.get("yolo_realtime")), default=False),
        yolo26l=_payload_bool(raw.get("yolo26L", raw.get("yolo26l")), default=False),
        yolo_supported=_payload_bool(raw.get("yoloSupported", raw.get("yolo_supported")), default=False),
        reason=str(raw.get("reason") or raw.get("message") or ""),
    )


def _normalize_annotate_result(value: Any) -> tuple[Any, list[str], JsonDict]:
    if isinstance(value, tuple) and len(value) == 3:
        annotated, actions, meta = value
        return annotated, list(actions or []), dict(meta or {})
    annotated, actions = value
    return annotated, list(actions or []), {}


def _to_camel_meta(meta: JsonDict) -> JsonDict:
    key_map = {
        "raw_layout": "rawLayout",
        "feature_layout": "featureLayout",
        "score_authorized": "scoreAuthorized",
        "calibration_status": "calibrationStatus",
        "display_scope": "displayScope",
        "confidence_kind": "confidenceKind",
        "validity_policy": "validityPolicy",
        "valid_conf_thr": "validConfThr",
        "calibration_note": "calibrationNote",
        "num_persons": "numPersons",
        "selected_index": "selectedIndex",
        "track_reset_note": "trackResetNote",
        "model_name": "modelName",
        "running_mode": "runningMode",
        "multi_person_detected": "multiPersonDetected",
        "multi_person_frames": "multiPersonFrames",
        "person_count": "personCount",
        "review_required": "reviewRequired",
        "gate_status": "gateStatus",
        "gate_note": "gateNote",
        "target_policy": "targetPolicy",
        "track_id": "trackId",
    }
    return {key_map.get(str(key), str(key)): value for key, value in meta.items()}


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _optional_str(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _payload_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def _optional_positive_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    parsed = int(value)
    if parsed < 1:
        raise ValueError("frameLimit must be a positive integer")
    return parsed


def _default_capture_factory(source: str) -> Any:
    if source.isdigit():
        from apps.camera_enum import open_camera

        return open_camera(int(source))
    import cv2

    return cv2.VideoCapture(source)


def _default_pipeline_factory(options: PreviewSessionOptions) -> Any:
    from core.paths import models_dir

    route = options.backend_route or {}
    if str(route.get("backend") or "").lower() == BACKEND_YOLO:
        from core.yolo_adapter import YoloPoseAdapter

        model_profile = str(route.get("modelProfile") or "yolo26n/s")
        model_name = _yolo_model_name_for_profile(model_profile)
        return YoloPoseAdapter(model_path=models_dir() / model_name, warmup=True)

    from core.vision_pipeline import MediaPipePipeline, PipelineConfig

    return MediaPipePipeline(
        models_dir=models_dir(),
        cfg=PipelineConfig(
            pose_variant=options.pose_variant,
            running_mode="video",
            enable_hands=options.enable_hands,
        ),
    )


def _yolo_model_name_for_profile(model_profile: str) -> str:
    normalized = str(model_profile or "").strip().lower()
    if normalized in {"yolo26s", "yolo26s-pose.pt"}:
        return "yolo26s-pose.pt"
    if normalized in {"yolo26l", "yolo26l-pose.pt"}:
        return "yolo26l-pose.pt"
    return "yolo26n-pose.pt"


def _default_create_template(*args: Any, **kwargs: Any) -> Path:
    from core.action_compare import create_template_from_video

    return create_template_from_video(*args, **kwargs)


def _default_compare_template(*args: Any, **kwargs: Any) -> Any:
    from core.action_compare import compare_video_to_template

    return compare_video_to_template(*args, **kwargs)


def _default_evaluate_detail(*args: Any, **kwargs: Any) -> Any:
    from analysis.tech_eval import evaluate_video_detail

    return evaluate_video_detail(*args, **kwargs)


def _default_evaluate_assets(*args: Any, **kwargs: Any) -> Any:
    from analysis.tech_eval import evaluate_video_assets

    return evaluate_video_assets(*args, **kwargs)


def _default_export_debug(*args: Any, **kwargs: Any) -> Path:
    from analysis.tech_eval import export_debug_video

    return export_debug_video(*args, **kwargs)


def _default_model_specs() -> tuple[Any, ...]:
    from core.model_manager import MODEL_SPECS

    return MODEL_SPECS


def _default_models_dir() -> Path:
    from core.paths import models_dir

    return models_dir()


def _default_model_path(spec: Any) -> Path:
    from core.model_manager import model_path

    return model_path(spec)


def _default_model_is_installed(spec: Any) -> bool:
    from core.model_manager import is_installed

    return is_installed(spec)


def _default_installed_size_mb(spec: Any) -> float | None:
    from core.model_manager import installed_size_mb

    return installed_size_mb(spec)


def _default_download_model(*args: Any, **kwargs: Any) -> Path:
    from core.model_manager import download_model

    return download_model(*args, **kwargs)


def _pose_model_key(pose_variant: str) -> str:
    return {"lite": "pose_lite", "full": "pose_full", "heavy": "pose_heavy"}.get(pose_variant, "pose_full")


def _spec_key(spec: Any) -> str:
    return str(getattr(spec, "key"))


def _spec_label(spec: Any) -> str:
    return str(getattr(spec, "label", _spec_key(spec)))


def _default_recording_factory(options: PreviewSessionOptions) -> Any:
    from core.recording_controller import RecordingController

    return RecordingController(path_provider=lambda: _record_path(options.record_dir))


def _record_path(record_dir: str | None) -> Path:
    if record_dir:
        directory = Path(record_dir)
        directory.mkdir(parents=True, exist_ok=True)
    else:
        from core.paths import outputs_dir

        directory = outputs_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return directory / f"record_{timestamp}.mp4"


def _default_debug_video_path(video: Path) -> Path:
    from core.paths import outputs_dir

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return outputs_dir() / f"{video.stem}_debug_{timestamp}.mp4"


def _recording_payload(snapshot: Any, *, session_id: str | None, result_path: Path | None = None) -> JsonDict:
    current_path = result_path if result_path is not None else getattr(snapshot, "result_path", None)
    state = str(getattr(snapshot, "state", "idle"))
    return {
        "sessionId": session_id,
        "state": state,
        "buttonText": RECORD_BTN_TEXT.get(state, RECORD_BTN_TEXT["idle"]),
        "stopEnabled": state in {"recording", "paused"},
        "resultPath": None if current_path is None else str(current_path),
        "framesWritten": int(getattr(snapshot, "frames_written", 0) or 0),
        "lastError": getattr(snapshot, "last_error", None),
    }


def _indicator_payload(indicator: Any) -> JsonDict | None:
    if indicator is None:
        return None
    detail = getattr(indicator, "detail", None)
    primary_cause = detail.get("primary_cause") if isinstance(detail, dict) else None
    failed_stage = detail.get("failed_stage") if isinstance(detail, dict) else None
    return _to_jsonable(
        {
            "status": getattr(indicator, "status", ""),
            "reason": getattr(indicator, "reason", ""),
            "primaryCause": primary_cause,
            "failedStage": failed_stage,
            "requiredLandmarks": getattr(indicator, "required_landmarks", ()),
            "missingLandmarks": getattr(indicator, "missing_landmarks", ()),
            "backend": getattr(indicator, "backend", ""),
            "detail": detail,
        }
    )


def _tech_eval_payload(result: Any, *, pose_variant: str) -> JsonDict:
    indicators = {
        "cogFinal": _indicator_payload(getattr(result, "cog_final", None)),
        "cogSide": _indicator_payload(getattr(result, "cog_side", None)),
        "cogFront": _indicator_payload(getattr(result, "cog_front", None)),
        "cogCom": _indicator_payload(getattr(result, "cog_com", None)),
        "retractSpeed": _indicator_payload(getattr(result, "retract_speed", None)),
        "forceSequence": _indicator_payload(getattr(result, "force_sequence", None)),
        "wristAngle": _indicator_payload(getattr(result, "wrist_angle", None)),
    }
    return _to_jsonable(
        {
            "poseVariant": str(getattr(result, "pose_variant", pose_variant)),
            "fps": float(getattr(result, "fps", 0.0) or 0.0),
            "viewMode": str(getattr(result, "view_mode", "")),
            "frontSegment": getattr(result, "front_segment", None),
            "sideSegment": getattr(result, "side_segment", None),
            "indicators": indicators,
            **indicators,
        }
    )


def _progress_callback(ctx: JobContext, prefix: str) -> Callable[[str, int, int], None]:
    def _emit(stage: str, done: int, total: int) -> None:
        payload = {
            "stage": stage,
            "done": int(done),
            "total": int(total),
            "percent": (float(done) / float(total) * 100.0) if int(total) > 0 else None,
        }
        ctx.progress("job.progress", payload)
        ctx.progress(f"{prefix}.progress", payload)

    return _emit


def _load_template_meta(path: Path) -> JsonDict:
    try:
        import numpy as np

        with np.load(path, allow_pickle=True) as data:
            meta = data["meta"].item()
        return _to_jsonable(dict(meta or {}))
    except Exception:
        return {}


def _compare_result_payload(result: Any) -> JsonDict:
    start_frame = int(getattr(result, "start_frame"))
    end_frame = int(getattr(result, "end_frame"))
    fps = float(getattr(result, "fps"))
    payload = {
        "score": float(getattr(result, "score")),
        "avgCost": float(getattr(result, "avg_cost")),
        "cost": float(getattr(result, "cost")),
        "startFrame": start_frame,
        "endFrame": end_frame,
        "fps": fps,
        "poseVariant": str(getattr(result, "pose_variant")),
        "workersUsed": getattr(result, "workers_used", None),
        "templatePath": str(getattr(result, "template_path")),
        "videoPath": str(getattr(result, "video_path")),
        "previewPath": None
        if getattr(result, "preview_path", None) is None
        else str(getattr(result, "preview_path")),
        "matchText": (
            f"匹配片段：帧 {start_frame}..{end_frame}  "
            f"时间 {start_frame / fps:.2f}s ~ {end_frame / fps:.2f}s"
        ),
    }
    return _to_jsonable(payload)


def _to_jsonable(value: Any) -> Any:
    try:
        from analysis.tech_eval import to_jsonable

        return to_jsonable(value)
    except Exception:
        if isinstance(value, dict):
            return {str(k): _to_jsonable(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [_to_jsonable(v) for v in value]
        if isinstance(value, Path):
            return str(value)
        return value


def _default_frame_encoder(frame: Any) -> bytes:
    import cv2

    # 预览帧瘦身:仅作用于送往前端的副本，不影响录制（recorder 写的是原始 annotated）。
    # 下采样长边到 PREVIEW_MAX_EDGE 并降低 JPEG 质量，显著减小单帧体积与 stdout/IPC 压力。
    preview = frame
    shape = getattr(frame, "shape", None)
    if shape is not None and len(shape) >= 2:
        height, width = int(shape[0]), int(shape[1])
        longest = max(height, width)
        if longest > PREVIEW_MAX_EDGE:
            scale = PREVIEW_MAX_EDGE / float(longest)
            new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
            preview = cv2.resize(frame, new_size, interpolation=cv2.INTER_AREA)

    ok, encoded = cv2.imencode(".jpg", preview, [cv2.IMWRITE_JPEG_QUALITY, PREVIEW_JPEG_QUALITY])
    if not ok:
        raise RuntimeError("无法编码预览帧")
    return encoded.tobytes()


def _capture_is_opened(cap: Any) -> bool:
    if cap is None:
        return False
    opened = getattr(cap, "isOpened", None)
    if opened is None:
        return True
    return bool(opened())


def _capture_float(cap: Any, prop: int, default: float) -> float:
    getter = getattr(cap, "get", None)
    if getter is None:
        return default
    try:
        value = float(getter(prop) or 0.0)
    except Exception:
        return default
    return value if value > 0 else default


def _next_timestamp_ms(
    pipe: Any,
    *,
    is_file: bool,
    fps_for_ts: float,
    frame_index: int,
    started_at: float,
    monotonic: Callable[[], float],
) -> int:
    next_ts = getattr(pipe, "next_timestamp_ms", None)
    if next_ts is not None:
        return int(next_ts(is_file=is_file, fps_for_ts=fps_for_ts))
    if is_file:
        return int(frame_index * 1000.0 / max(1e-6, fps_for_ts))
    return int((monotonic() - started_at) * 1000.0)


def _frame_size(frame: Any, *, fallback: tuple[int, int]) -> tuple[int, int]:
    shape = getattr(frame, "shape", None)
    if shape is not None and len(shape) >= 2:
        return int(shape[1]), int(shape[0])
    return fallback


def _progress_payload(done: int, total: int) -> JsonDict:
    percent = (done / total * 100.0) if total > 0 else None
    return {"done": done, "total": total, "percent": percent}


def _release_quietly(cap: Any) -> None:
    release = getattr(cap, "release", None)
    if release is None:
        return
    try:
        release()
    except Exception:
        pass


def _close_quietly(resource: Any) -> None:
    close = getattr(resource, "close", None)
    if close is None:
        return
    try:
        close()
    except Exception:
        pass


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def protocol_manifest() -> JsonDict:
    return {
        "version": BRIDGE_VERSION,
        "commands": COMMANDS,
        "message_contract": {
            "request": ["type", "command", "requestId", "jobId", "sessionId", "payload"],
            "response": ["type", "requestId", "ok", "jobId", "sessionId", "payload", "error", "timestamp"],
            "event": ["type", "event", "jobId", "sessionId", "payload", "error", "timestamp"],
            "optional": {
                "request": ["jobId", "sessionId"],
                "response": ["jobId", "sessionId"],
                "event": ["jobId", "sessionId"],
            },
            "nullable": {
                "request": ["jobId", "sessionId"],
                "response": ["jobId", "sessionId", "error"],
                "event": ["jobId", "sessionId", "error"],
            },
        },
    }


def make_response(
    request_id: str,
    *,
    ok: bool,
    payload: JsonDict | None = None,
    error: BridgeError | None = None,
    job_id: str | None = None,
    session_id: str | None = None,
    timestamp: str | None = None,
) -> JsonDict:
    return {
        "type": "response",
        "requestId": request_id,
        "ok": bool(ok),
        "jobId": job_id,
        "sessionId": session_id,
        "payload": payload or {},
        "error": None if error is None else error.to_dict(),
        "timestamp": timestamp or utc_timestamp(),
    }


def make_event(
    event: str,
    *,
    payload: JsonDict | None = None,
    error: BridgeError | None = None,
    job_id: str | None = None,
    session_id: str | None = None,
    timestamp: str | None = None,
) -> JsonDict:
    return {
        "type": "event",
        "event": event,
        "jobId": job_id,
        "sessionId": session_id,
        "payload": payload or {},
        "error": None if error is None else error.to_dict(),
        "timestamp": timestamp or utc_timestamp(),
    }


def parse_command(raw: JsonDict) -> CommandRequest:
    if raw.get("type") != "command":
        raise ValueError("bridge request type must be 'command'")
    command = str(raw.get("command") or "").strip()
    if not command:
        raise ValueError("bridge command is required")
    if command not in COMMANDS:
        raise ValueError(f"unknown bridge command: {command}")
    request_id = str(raw.get("requestId") or "").strip()
    if not request_id:
        raise ValueError("bridge requestId is required")
    payload = raw.get("payload")
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise ValueError("bridge payload must be an object")
    job_id = raw.get("jobId")
    session_id = raw.get("sessionId")
    return CommandRequest(
        command=command,
        request_id=request_id,
        payload=payload,
        job_id=None if job_id in (None, "") else str(job_id),
        session_id=None if session_id in (None, "") else str(session_id),
    )


def encode_message(message: JsonDict) -> str:
    return json.dumps(message, ensure_ascii=False, separators=(",", ":"))


def decode_message(line: str) -> JsonDict:
    data = json.loads(line)
    if not isinstance(data, dict):
        raise ValueError("bridge message must be a JSON object")
    return data


def error_context_from_line(line: str) -> tuple[str, str | None, str | None, JsonDict]:
    try:
        raw = json.loads(line)
    except Exception:  # noqa: BLE001 - best effort context for malformed JSON.
        return "unknown", None, None, {}
    if not isinstance(raw, dict):
        return "unknown", None, None, {"rawType": type(raw).__name__}

    request_id = str(raw.get("requestId") or "").strip() or "unknown"
    job_id = str(raw.get("jobId") or "").strip() or None
    session_id = str(raw.get("sessionId") or "").strip() or None
    detail: JsonDict = {}
    command = str(raw.get("command") or "").strip()
    if command:
        detail["command"] = command
    return request_id, job_id, session_id, detail


def handle_command(request: CommandRequest) -> JsonDict:
    handlers: dict[str, Callable[[CommandRequest], JsonDict]] = {
        "bridge.ping": _handle_ping,
        "camera.list": _handle_camera_list,
        "session.start": _handle_session_start,
        "session.warmup": _handle_session_warmup,
        "session.stop": _handle_session_stop,
        "record.toggle": _handle_record_toggle,
        "record.stop": _handle_record_stop,
        "template.create": _handle_template_create,
        "analysis.run": _handle_analysis_run,
        "model.status": _handle_model_status,
        "model.download": _handle_model_download,
        "job.stop": _handle_stop_job,
    }
    handler = handlers.get(request.command)
    if handler is None:
        return make_response(
            request.request_id,
            ok=False,
            error=BridgeError(
                "not_implemented",
                f"命令尚未实现: {request.command}",
                {"command": request.command},
            ),
        )
    return handler(request)


def _handle_ping(request: CommandRequest) -> JsonDict:
    return make_response(
        request.request_id,
        ok=True,
        payload={"version": BRIDGE_VERSION, "commands": sorted(COMMANDS)},
    )


def _handle_camera_list(request: CommandRequest) -> JsonDict:
    try:
        scan_limit = int(request.payload.get("scanLimit", DEFAULT_SCAN_LIMIT))
    except (TypeError, ValueError):
        return make_response(
            request.request_id,
            ok=False,
            error=BridgeError("bad_request", "scanLimit must be an integer"),
        )
    entries = enumerate_cameras(scan_limit=scan_limit)
    cameras = [_camera_entry_payload(entry) for entry in entries]
    return make_response(
        request.request_id,
        ok=True,
        payload={"cameras": cameras, "count": len(cameras), "scanLimit": scan_limit},
    )


def _camera_entry_payload(entry: CameraEntry) -> JsonDict:
    return {"label": entry.label, "index": entry.index}


def _handle_session_start(request: CommandRequest) -> JsonDict:
    return DEFAULT_PREVIEW_SERVICE.start(request)


def _handle_session_warmup(request: CommandRequest) -> JsonDict:
    return DEFAULT_PREVIEW_SERVICE.warmup(request)


def _handle_session_stop(request: CommandRequest) -> JsonDict:
    return DEFAULT_PREVIEW_SERVICE.stop(request)


def _handle_record_toggle(request: CommandRequest) -> JsonDict:
    return DEFAULT_PREVIEW_SERVICE.record_toggle(request)


def _handle_record_stop(request: CommandRequest) -> JsonDict:
    return DEFAULT_PREVIEW_SERVICE.record_stop(request)


def _handle_template_create(request: CommandRequest) -> JsonDict:
    return DEFAULT_ANALYSIS_SERVICE.start_template_create(request)


def _handle_analysis_run(request: CommandRequest) -> JsonDict:
    return DEFAULT_ANALYSIS_SERVICE.start_analysis_run(request)


def _handle_model_status(request: CommandRequest) -> JsonDict:
    return DEFAULT_MODEL_SERVICE.status(request)


def _handle_model_download(request: CommandRequest) -> JsonDict:
    return DEFAULT_MODEL_SERVICE.start_download(request)


def _handle_stop_job(request: CommandRequest) -> JsonDict:
    job_id = str(request.payload.get("jobId") or request.job_id or "").strip()
    if not job_id:
        return make_response(
            request.request_id,
            ok=False,
            error=BridgeError("bad_request", "jobId is required to stop a job"),
        )
    stopped = DEFAULT_JOB_MANAGER.stop(job_id)
    if not stopped:
        return make_response(
            request.request_id,
            ok=False,
            error=BridgeError("not_found", f"job not found: {job_id}", {"jobId": job_id}),
        )
    return make_response(
        request.request_id,
        ok=True,
        payload={"jobId": job_id, "stopped": True},
        job_id=job_id,
    )


def handle_line(line: str) -> str:
    try:
        request = parse_command(decode_message(line))
        response = handle_command(request)
    except Exception as exc:  # noqa: BLE001 - bridge must serialize all failures.
        request_id, job_id, session_id, detail = error_context_from_line(line)
        response = make_response(
            request_id,
            ok=False,
            error=BridgeError("bad_request", str(exc), detail),
            job_id=job_id,
            session_id=session_id,
        )
    return encode_message(response)


DEFAULT_JOB_MANAGER = BridgeJobManager()
DEFAULT_PREVIEW_SERVICE = PreviewSessionService()
DEFAULT_ANALYSIS_SERVICE = TemplateAnalysisService()
DEFAULT_MODEL_SERVICE = ModelManagementService()


def main() -> int:
    import sys

    global DEFAULT_JOB_MANAGER
    protocol_stdout = sys.stdout
    writer = BridgeMessageWriter(protocol_stdout)
    # Keep any third-party or legacy diagnostic print() calls away from the
    # stdout JSONL protocol. Tauri reads stdout line-by-line as bridge messages.
    sys.stdout = sys.stderr
    DEFAULT_JOB_MANAGER = BridgeJobManager(writer.write)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        writer.write_encoded(handle_line(line))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
