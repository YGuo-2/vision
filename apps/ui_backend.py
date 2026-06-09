# -*- coding: utf-8 -*-
"""JSON bridge contract for the Vue/Tauri desktop frontend.

This module intentionally starts with protocol primitives only. The long-running
job execution layer is added on top of these helpers so tests can lock the
message shape before UI work depends on it.
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import threading
import time
import traceback
from uuid import uuid4
from typing import Any, Callable

from apps.camera_enum import DEFAULT_SCAN_LIMIT, CameraEntry, InputSourceState, enumerate_cameras


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


@dataclass(frozen=True)
class PreviewSessionOptions:
    source: str
    source_kind: str
    pose_variant: str = "full"
    workers: int = 1
    enable_hands: bool = True
    record_dir: str | None = None
    frame_limit: int | None = None

    def to_payload(self) -> JsonDict:
        return {
            "source": self.source,
            "sourceKind": self.source_kind,
            "poseVariant": self.pose_variant,
            "workers": self.workers,
            "enableHands": self.enable_hands,
            "recordDir": self.record_dir,
            "frameLimit": self.frame_limit,
        }


@dataclass
class ActivePreviewSession:
    session_id: str
    job_id: str
    recorder: Any
    emit: Callable[[str, JsonDict], None]
    last_record_error: str | None = None


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
    debug_video: bool = False
    debug_out_path: str | None = None

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
            "debugVideo": self.debug_video,
            "debugOutPath": self.debug_out_path,
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
        options = normalize_analysis_run_options(ctx.payload)
        ctx.progress("analysis.status", {"state": "running", **options.to_payload()})
        payload: JsonDict = {
            "state": "running",
            "videoPath": options.video_path,
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
        models = []
        missing = []
        for spec in self.specs:
            installed = bool(self._is_installed(spec))
            item = {
                "key": _spec_key(spec),
                "filename": str(getattr(spec, "filename", "")),
                "label": _spec_label(spec),
                "approxMb": getattr(spec, "approx_mb", None),
                "path": str(self._model_path(spec)),
                "installed": installed,
                "sizeMb": self._installed_size(spec),
                "active": _spec_key(spec) in active_keys,
            }
            if not installed:
                missing.append(_spec_key(spec))
            models.append(item)
        return {
            "modelsDir": str(self._models_dir_func()),
            "poseVariant": pose_variant,
            "enableHands": enable_hands,
            "activeKeys": sorted(active_keys),
            "missingKeys": missing,
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
        frame_encoder: Callable[[Any], str] | None = None,
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

    @property
    def manager(self) -> BridgeJobManager:
        return self._job_manager or DEFAULT_JOB_MANAGER

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
        options = normalize_session_options(ctx.payload)
        cap = None
        pipe = None
        recorder = self._recording_factory(options)
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
            active = ActivePreviewSession(
                session_id=ctx.session_id or "",
                job_id=ctx.job_id,
                recorder=recorder,
                emit=lambda event, payload: ctx.progress(event, payload),
            )
            self._register_active_session(active)

            pipe = self._pipeline_factory(options)
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
                },
            )

            while not ctx.stopped():
                ok, frame = cap.read()
                if not ok:
                    break

                timestamp_ms = _next_timestamp_ms(
                    pipe,
                    is_file=is_file,
                    fps_for_ts=fps_for_ts,
                    frame_index=frame_count,
                    started_at=started_at,
                    monotonic=self._monotonic,
                )
                annotated, actions = pipe.annotate(frame, timestamp_ms=timestamp_ms)
                frame_count += 1

                elapsed = self._monotonic() - started_at
                fps = frame_count / max(1e-6, elapsed)
                actions_zh = [ACTION_LABELS_ZH.get(str(action), str(action)) for action in actions]
                frame_width, frame_height = _frame_size(annotated, fallback=(width, height))
                frame_payload: JsonDict = {
                    "image": self._frame_encoder(annotated),
                    "actions": list(actions),
                    "actionsZh": actions_zh,
                    "actionsText": ", ".join(actions_zh) if actions_zh else "-",
                    "frameIndex": frame_count,
                    "fps": fps,
                    "progress": _progress_payload(frame_count, total),
                    "size": {"width": frame_width, "height": frame_height},
                }
                ctx.progress("session.frame", frame_payload)
                recorder.write_frame(annotated)
                self._emit_recording_error_if_needed(active)

                if total > 0 and (frame_count % 5 == 0 or frame_count == total):
                    ctx.progress("session.progress", _progress_payload(frame_count, total))

                if options.frame_limit is not None and frame_count >= options.frame_limit:
                    break

            state = "stopped" if ctx.stopped() else "completed"
            ctx.progress(
                "session.status",
                {"state": state, "frames": frame_count, "totalFrames": total},
            )
            return {
                "state": state,
                "frames": frame_count,
                "totalFrames": total,
                "source": options.source,
                "sourceKind": options.source_kind,
            }
        finally:
            result_path = None
            try:
                result_path = recorder.close_session()
            finally:
                if ctx.session_id:
                    self._unregister_active_session(ctx.session_id)
            ctx.progress(
                "record.status",
                _recording_payload(
                    recorder.snapshot(),
                    session_id=ctx.session_id,
                    result_path=result_path,
                ),
            )
            _close_quietly(pipe)
            _release_quietly(cap)

    def _active_from_request(self, request: CommandRequest) -> ActivePreviewSession | None:
        session_id = str(request.payload.get("sessionId") or request.session_id or "").strip()
        if not session_id:
            return None
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


def normalize_session_options(payload: JsonDict) -> PreviewSessionOptions:
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
    return PreviewSessionOptions(
        source=state.value,
        source_kind=state.kind,
        pose_variant=pose_variant,
        workers=clamp_workers(payload.get("workers", 1)),
        enable_hands=_payload_bool(payload.get("enableHands", payload.get("enable_hands")), default=True),
        record_dir=_optional_str(payload.get("recordDir", payload.get("record_dir"))),
        frame_limit=frame_limit,
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


def normalize_analysis_run_options(payload: JsonDict) -> AnalysisRunOptions:
    video_path = _required_path(payload, "videoPath", "targetVideo", "video")
    do_compare = _payload_bool(
        payload.get("doCompare", payload.get("enableTemplateCompare")),
        default=True,
    )
    do_tech_eval = _payload_bool(
        payload.get("doTechEval", payload.get("enableTechEval")),
        default=False,
    )
    if not do_compare and not do_tech_eval:
        raise ValueError("at least one of doCompare or doTechEval must be true")
    template_path = _optional_str(payload.get("templatePath", payload.get("template")))
    if do_compare and not template_path:
        raise ValueError("templatePath is required when doCompare is true")
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
        debug_video=_payload_bool(payload.get("debugVideo"), default=False),
        debug_out_path=_optional_str(payload.get("debugOutPath", payload.get("debugVideoPath"))),
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
    from core.vision_pipeline import MediaPipePipeline, PipelineConfig

    return MediaPipePipeline(
        models_dir=models_dir(),
        cfg=PipelineConfig(
            pose_variant=options.pose_variant,
            running_mode="video",
            enable_hands=options.enable_hands,
        ),
    )


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
    from core.model_manager import MEDIAPIPE_MODELS

    return MEDIAPIPE_MODELS


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


def _default_frame_encoder(frame: Any) -> str:
    import cv2

    ok, encoded = cv2.imencode(".jpg", frame)
    if not ok:
        raise RuntimeError("无法编码预览帧")
    return "data:image/jpeg;base64," + base64.b64encode(encoded.tobytes()).decode("ascii")


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
    DEFAULT_JOB_MANAGER = BridgeJobManager(lambda message: print(encode_message(message), flush=True))

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        print(handle_line(line), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
