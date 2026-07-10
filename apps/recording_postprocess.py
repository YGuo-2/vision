from __future__ import annotations

import json
import os
import queue
import tempfile
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

import cv2
import numpy as np

from analysis.tech_eval import to_jsonable
from core import action_compare, model_manager, video_writer
from core.paths import templates_dir

PostprocessStatus = Literal[
    "queued",
    "transcoding",
    "validating",
    "comparing",
    "completed",
    "failed",
    "skipped",
    "cancelled",
]

_TERMINAL_STATUSES = frozenset({"completed", "failed", "skipped", "cancelled"})
_QUEUE_SENTINEL = object()
_EXPECTED_TEMPLATE_LAYOUT = "pose_indices_11_32_xy_rot_scale_norm_v2"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def default_template_paths() -> tuple[Path, Path]:
    root = templates_dir()
    return root / "standard_front_full.npz", root / "standard_side_full.npz"


@dataclass(frozen=True)
class DualRecordingJob:
    segment_id: str
    segment_dir: Path
    front_source: Path
    side_source: Path
    front_frames: int
    side_frames: int
    front_template: Path
    side_template: Path
    record_skeleton: bool = False
    front_error: str | None = None
    side_error: str | None = None
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            object.__setattr__(self, "created_at", utc_timestamp())


@dataclass(frozen=True)
class PostprocessUpdate:
    segment_id: str
    status: PostprocessStatus
    message: str
    front_score: float | None = None
    side_score: float | None = None
    combined_percent: int | None = None
    error_code: str | None = None


@dataclass
class _ProcessContext:
    front_video: Path | None = None
    side_video: Path | None = None
    warnings: list[str] = field(default_factory=list)


class PostprocessError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


TranscodeFn = Callable[[Path, threading.Event], Path | None]
CompareFn = Callable[..., Any]
VideoValidator = Callable[[Path], bool]
ModelAvailable = Callable[[], bool]
UpdateCallback = Callable[[PostprocessUpdate], None]


def _default_transcode(path: Path, stop_evt: threading.Event) -> Path | None:
    return video_writer.transcode_to_h264(path, stop_evt=stop_evt)


def _default_video_validator(path: Path) -> bool:
    path = Path(path)
    if not path.is_file() or path.stat().st_size <= 0:
        return False
    cap = cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened():
            return False
        ok, frame = cap.read()
        return bool(ok and frame is not None and getattr(frame, "size", 0) > 0)
    finally:
        cap.release()


def _default_model_available() -> bool:
    spec = next((item for item in model_manager.MEDIAPIPE_MODELS if item.key == "pose_full"), None)
    return bool(spec is not None and model_manager.is_installed(spec))


def validate_template_pair(front_path: Path, side_path: Path) -> None:
    def _load(path: Path) -> tuple[np.ndarray, dict[str, Any]]:
        path = Path(path)
        if not path.is_file() or path.stat().st_size <= 0:
            raise PostprocessError("template_missing", f"固定模板不存在：{path}")
        try:
            with np.load(path, allow_pickle=True) as data:
                if "features" not in data or "meta" not in data:
                    raise ValueError("缺少 features/meta")
                features = np.asarray(data["features"], dtype=np.float32)
                meta = dict(data["meta"].item() or {})
        except PostprocessError:
            raise
        except Exception as exc:
            raise PostprocessError("template_invalid", f"无法读取固定模板 {path}：{exc}") from exc
        if features.ndim != 3 or features.shape[0] <= 0 or features.shape[1:] != (22, 2):
            raise PostprocessError(
                "template_invalid",
                f"固定模板特征形状无效：{path} -> {tuple(features.shape)}",
            )
        if not np.isfinite(features).all():
            raise PostprocessError("template_invalid", f"固定模板包含非有限特征：{path}")
        if str(meta.get("pose_variant") or "") != "full":
            raise PostprocessError("template_invalid", f"固定模板必须使用 full 模型：{path}")
        return features, meta

    _front_features, front_meta = _load(front_path)
    _side_features, side_meta = _load(side_path)
    front_layout = str(front_meta.get("feature_layout") or "")
    side_layout = str(side_meta.get("feature_layout") or "")
    if front_layout != side_layout or front_layout != _EXPECTED_TEMPLATE_LAYOUT:
        raise PostprocessError(
            "template_incompatible",
            f"正侧模板布局不兼容：front={front_layout or '?'} side={side_layout or '?'}",
        )


class DualRecordingPostProcessor:
    def __init__(
        self,
        *,
        on_update: UpdateCallback | None = None,
        transcode: TranscodeFn = _default_transcode,
        compare: CompareFn = action_compare.compare_dual_streams,
        video_validator: VideoValidator = _default_video_validator,
        model_available: ModelAvailable = _default_model_available,
    ) -> None:
        self._on_update = on_update
        self._transcode = transcode
        self._compare = compare
        self._video_validator = video_validator
        self._model_available = model_available
        self._queue: queue.Queue[DualRecordingJob | object] = queue.Queue()
        self._lock = threading.RLock()
        self._persistence_lock = threading.Lock()
        self._submitted: set[str] = set()
        self._segment_dir_owners: dict[str, str] = {}
        self._cancelled_segments: set[str] = set()
        self._terminal_status: dict[str, PostprocessStatus] = {}
        self._closed = False
        self._sentinel_queued = False
        self._active_stop_evt: threading.Event | None = None
        self._active_job: DualRecordingJob | None = None
        self._active_context: _ProcessContext | None = None
        self._worker = threading.Thread(
            target=self._run,
            name="dual-recording-postprocess",
            daemon=True,
        )
        self._worker.start()

    def submit(self, job: DualRecordingJob) -> bool:
        try:
            segment_dir_key = os.path.normcase(
                str(Path(job.segment_dir).resolve(strict=False))
            )
        except (OSError, RuntimeError):
            return False
        with self._lock:
            if self._closed or job.segment_id in self._submitted:
                return False
            if segment_dir_key in self._segment_dir_owners:
                return False
            self._submitted.add(job.segment_id)
            self._segment_dir_owners[segment_dir_key] = job.segment_id
            self._queue.put(job)
        return True

    def cancel_all(self) -> None:
        with self._lock:
            self._closed = True
            active = self._active_stop_evt
            self._cancelled_segments.update(
                segment_id
                for segment_id in self._submitted
                if segment_id not in self._terminal_status
            )
        if active is not None:
            active.set()

    def close(self, timeout: float) -> None:
        self.cancel_all()
        with self._lock:
            if self._worker.is_alive() and not self._sentinel_queued:
                self._sentinel_queued = True
                self._queue.put(_QUEUE_SENTINEL)
        if threading.current_thread() is self._worker:
            return
        self._worker.join(max(0.0, float(timeout)))

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            if item is _QUEUE_SENTINEL:
                self._queue.task_done()
                return
            job = item
            stop_evt = threading.Event()
            context = _ProcessContext()
            with self._lock:
                closed = self._closed
                self._active_stop_evt = stop_evt
                self._active_job = job
                self._active_context = context
            try:
                if closed:
                    self._publish_terminal_safely(
                        job,
                        "cancelled",
                        message="应用关闭，后台比对已取消",
                        error_code="app_closing",
                    )
                else:
                    self._process(job, stop_evt, context)
            except InterruptedError:
                self._publish_cancelled(job, context)
            except PostprocessError as exc:
                if self._is_cancelled(job):
                    self._publish_cancelled(job, context)
                else:
                    self._publish_terminal_safely(
                        job,
                        "failed",
                        message=str(exc),
                        error_code=exc.code,
                        front_video=context.front_video,
                        side_video=context.side_video,
                        warnings=context.warnings,
                    )
            except Exception as exc:  # noqa: BLE001 - 后台任务必须失败隔离
                if self._is_cancelled(job):
                    self._publish_cancelled(job, context)
                else:
                    self._publish_terminal_safely(
                        job,
                        "failed",
                        message=f"后台比对失败：{exc}",
                        error_code="compare_failed",
                        front_video=context.front_video,
                        side_video=context.side_video,
                        warnings=context.warnings,
                    )
            finally:
                with self._lock:
                    if self._active_stop_evt is stop_evt:
                        self._active_stop_evt = None
                    if self._active_job is job:
                        self._active_job = None
                        self._active_context = None
                self._queue.task_done()

    def _is_cancelled(self, job: DualRecordingJob) -> bool:
        with self._lock:
            return job.segment_id in self._cancelled_segments

    def _publish_cancelled(
        self,
        job: DualRecordingJob,
        context: _ProcessContext,
    ) -> None:
        app_closing = self._is_cancelled(job)
        self._publish_terminal_safely(
            job,
            "cancelled",
            message=(
                "应用关闭，后台比对已取消" if app_closing else "后台比对已取消"
            ),
            error_code="app_closing" if app_closing else "cancelled",
            front_video=context.front_video,
            side_video=context.side_video,
            warnings=context.warnings,
        )

    def _process(
        self,
        job: DualRecordingJob,
        stop_evt: threading.Event,
        context: _ProcessContext,
    ) -> None:
        self._validate_recording_snapshot(job)
        self._publish(job, "queued", "已进入后台比对队列")
        self._publish(job, "transcoding", "正在顺序完成正侧录像转码")

        context.front_video = self._transcode_one(
            job.front_source, stop_evt, "正面", context.warnings
        )
        context.side_video = self._transcode_one(
            job.side_source, stop_evt, "侧面", context.warnings
        )

        self._raise_if_cancelled(stop_evt)
        self._publish(
            job,
            "validating",
            "正在校验录像、模板和模型",
            front_video=context.front_video,
            side_video=context.side_video,
            warnings=context.warnings,
        )
        self._validate_video(context.front_video, "正面")
        self._validate_video(context.side_video, "侧面")

        self._raise_if_cancelled(stop_evt)
        if job.record_skeleton:
            self._publish_terminal(
                job,
                "skipped",
                message="带骨架录像未自动比对，请关闭骨架后重新录制",
                error_code="annotated_recording",
                front_video=context.front_video,
                side_video=context.side_video,
                warnings=context.warnings,
            )
            return

        validate_template_pair(job.front_template, job.side_template)
        if not self._model_available():
            raise PostprocessError(
                "model_missing",
                "缺少 pose_landmarker_full.task，请先在模型管理中安装 full 模型",
            )

        self._raise_if_cancelled(stop_evt)
        self._publish(
            job,
            "comparing",
            "正在执行正侧双流 DTW 比对",
            front_video=context.front_video,
            side_video=context.side_video,
            warnings=context.warnings,
        )
        result = self._compare(
            job.front_template,
            job.side_template,
            context.front_video,
            context.side_video,
            pose_variant=None,
            workers=1,
            w_front=0.4,
            w_side=0.6,
            baseline=2.0,
            enable_rules=False,
            enable_error_analysis=False,
            stop_evt=stop_evt,
        )
        self._raise_if_cancelled(stop_evt)
        result_payload = self._result_payload(result)
        self._publish_terminal(
            job,
            "completed",
            message="后台双流比对完成",
            front_video=context.front_video,
            side_video=context.side_video,
            warnings=context.warnings,
            result=result_payload,
        )

    @staticmethod
    def _validate_recording_snapshot(job: DualRecordingJob) -> None:
        if job.front_error:
            raise PostprocessError("front_recording_failed", f"正面录像失败：{job.front_error}")
        if job.side_error:
            raise PostprocessError("side_recording_failed", f"侧面录像失败：{job.side_error}")
        if not job.front_source or not job.side_source:
            raise PostprocessError("recording_missing", "正面或侧面录像路径缺失")
        segment_dir = Path(job.segment_dir).resolve(strict=False)
        for label, source in (
            ("正面", job.front_source),
            ("侧面", job.side_source),
        ):
            try:
                Path(source).resolve(strict=False).relative_to(segment_dir)
            except (OSError, ValueError) as exc:
                raise PostprocessError(
                    "recording_path_mismatch",
                    f"{label}录像路径不属于当前片段目录：{source}",
                ) from exc
        if job.front_frames <= 0 or job.side_frames <= 0:
            raise PostprocessError("recording_empty", "正面或侧面录像没有有效帧")
        if job.front_frames != job.side_frames:
            raise PostprocessError(
                "frame_count_mismatch",
                f"正侧录像帧数不一致：front={job.front_frames} side={job.side_frames}",
            )

    def _transcode_one(
        self,
        source: Path,
        stop_evt: threading.Event,
        label: str,
        warnings: list[str],
    ) -> Path:
        self._raise_if_cancelled(stop_evt)
        source = Path(source)
        try:
            final_path = self._transcode(source, stop_evt)
        except InterruptedError:
            raise
        except Exception as exc:
            raise PostprocessError(
                "transcode_failed", f"{label}录像转码失败：{exc}"
            ) from exc
        if final_path is None:
            raise PostprocessError("transcode_failed", f"{label}录像转码未返回文件路径")
        final_path = Path(final_path)
        if source.suffix.lower() == ".avi" and final_path.suffix.lower() == ".avi":
            warnings.append(f"{label}录像 H.264 转码失败，已回退使用 AVI")
        return final_path

    def _validate_video(self, path: Path, label: str) -> None:
        try:
            valid = self._video_validator(Path(path))
        except Exception as exc:
            raise PostprocessError("video_unreadable", f"{label}录像无法读取：{exc}") from exc
        if not valid:
            raise PostprocessError("video_unreadable", f"{label}录像不存在、为空或无法读取：{path}")

    @staticmethod
    def _raise_if_cancelled(stop_evt: threading.Event) -> None:
        if stop_evt.is_set():
            raise InterruptedError("后台比对已取消")

    @staticmethod
    def _result_payload(result: Any) -> dict[str, Any]:
        def _segment(value: Any) -> dict[str, int] | None:
            if value is None:
                return None
            return {"start": int(value[0]), "end": int(value[1])}

        return {
            "front_score": float(result.front_score),
            "side_score": float(result.side_score),
            "combined_score": float(result.combined_score),
            "combined_percent": int(result.combined_percent),
            "front_matches": to_jsonable(result.front_matches),
            "side_matches": to_jsonable(result.side_matches),
            "front_segment": _segment(result.front_segment),
            "side_segment": _segment(result.side_segment),
        }

    def _publish(
        self,
        job: DualRecordingJob,
        status: PostprocessStatus,
        message: str,
        *,
        front_video: Path | None = None,
        side_video: Path | None = None,
        warnings: list[str] | None = None,
        result: dict[str, Any] | None = None,
        error_code: str | None = None,
        notify: bool = True,
    ) -> None:
        payload = {
            "schema_version": 1,
            "status": status,
            "segment_id": job.segment_id,
            "created_at": job.created_at,
            "completed_at": utc_timestamp() if status in _TERMINAL_STATUSES else None,
            "record_skeleton": bool(job.record_skeleton),
            "front_video_path": str(front_video or job.front_source),
            "side_video_path": str(side_video or job.side_source),
            "front_template_path": str(job.front_template),
            "side_template_path": str(job.side_template),
            "warnings": list(warnings or []),
            "result": result,
            "error": None if error_code is None else {"code": error_code, "message": message},
        }
        update: PostprocessUpdate | None = None
        with self._persistence_lock:
            with self._lock:
                existing_terminal = self._terminal_status.get(job.segment_id)
                cancelled_enrichment = (
                    existing_terminal == "cancelled" and status == "cancelled"
                )
                if existing_terminal is not None and not cancelled_enrichment:
                    return
                if (
                    job.segment_id in self._cancelled_segments
                    and status != "cancelled"
                ):
                    raise InterruptedError("后台比对已取消")
            try:
                self._write_json_atomic(job.segment_dir / "result.json", payload)
            except Exception as exc:
                if cancelled_enrichment:
                    return
                raise PostprocessError(
                    "result_write_failed", f"结果文件写入失败：{exc}"
                ) from exc
            with self._lock:
                existing_terminal = self._terminal_status.get(job.segment_id)
                cancelled_enrichment = (
                    existing_terminal == "cancelled" and status == "cancelled"
                )
                if existing_terminal is not None and not cancelled_enrichment:
                    return
                if (
                    job.segment_id in self._cancelled_segments
                    and status != "cancelled"
                ):
                    raise InterruptedError("后台比对已取消")
                if status in _TERMINAL_STATUSES:
                    self._terminal_status[job.segment_id] = status
                if notify and not cancelled_enrichment:
                    update = self._update_from_payload(payload, message)
        if update is not None:
            self._notify(update)

    def _publish_terminal(
        self,
        job: DualRecordingJob,
        status: Literal["completed", "failed", "skipped", "cancelled"],
        *,
        message: str,
        error_code: str | None = None,
        front_video: Path | None = None,
        side_video: Path | None = None,
        warnings: list[str] | None = None,
        result: dict[str, Any] | None = None,
    ) -> None:
        self._publish(
            job,
            status,
            message,
            front_video=front_video,
            side_video=side_video,
            warnings=warnings,
            result=result,
            error_code=error_code,
        )

    def _publish_terminal_safely(
        self,
        job: DualRecordingJob,
        status: Literal["completed", "failed", "skipped", "cancelled"],
        *,
        message: str,
        error_code: str | None = None,
        front_video: Path | None = None,
        side_video: Path | None = None,
        warnings: list[str] | None = None,
        result: dict[str, Any] | None = None,
    ) -> None:
        try:
            self._publish_terminal(
                job,
                status,
                message=message,
                error_code=error_code,
                front_video=front_video,
                side_video=side_video,
                warnings=warnings,
                result=result,
            )
        except InterruptedError:
            try:
                self._publish_terminal(
                    job,
                    "cancelled",
                    message="应用关闭，后台比对已取消",
                    error_code="app_closing",
                    front_video=front_video,
                    side_video=side_video,
                    warnings=warnings,
                )
            except Exception as exc:  # noqa: BLE001 - 持久化失败不得杀死 FIFO worker
                self._notify(
                    PostprocessUpdate(
                        segment_id=job.segment_id,
                        status="failed",
                        message=f"结果文件写入失败：{exc}",
                        error_code="result_write_failed",
                    )
                )
        except Exception as exc:  # noqa: BLE001 - 持久化失败不得杀死 FIFO worker
            self._notify(
                PostprocessUpdate(
                    segment_id=job.segment_id,
                    status="failed",
                    message=f"结果文件写入失败：{exc}",
                    error_code="result_write_failed",
                )
            )

    @staticmethod
    def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                prefix=f".{path.stem}.",
                suffix=".tmp",
                dir=path.parent,
                delete=False,
            ) as temporary:
                json.dump(payload, temporary, ensure_ascii=False, indent=2)
                temporary.write("\n")
                temporary_path = Path(temporary.name)
            temporary_path.replace(path)
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass

    @staticmethod
    def _update_from_payload(payload: dict[str, Any], message: str) -> PostprocessUpdate:
        result = payload.get("result") or {}
        error = payload.get("error") or {}
        return PostprocessUpdate(
            segment_id=str(payload["segment_id"]),
            status=payload["status"],
            message=message,
            front_score=result.get("front_score"),
            side_score=result.get("side_score"),
            combined_percent=result.get("combined_percent"),
            error_code=error.get("code"),
        )

    def _notify(self, update: PostprocessUpdate) -> None:
        if self._on_update is None:
            return
        try:
            self._on_update(update)
        except Exception:
            pass
