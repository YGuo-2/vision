# -*- coding: utf-8 -*-
"""Tkinter 摄像头预打开、识别状态与转码关窗生命周期测试（无需真实 Tk/camera）。"""
from __future__ import annotations

import threading
from pathlib import Path
from queue import Queue
from types import SimpleNamespace

from apps import app_ui
from core.recording_controller import RecordingController


class _Var:
    def __init__(self, value=None) -> None:
        self.value = value

    def get(self):
        return self.value

    def set(self, value) -> None:
        self.value = value


class _Widget:
    def __init__(self) -> None:
        self.config: dict[str, object] = {}

    def configure(self, **kwargs) -> None:
        self.config.update(kwargs)


class _Cap:
    def __init__(self, *, opened: bool = True) -> None:
        self.opened = opened
        self.release_calls = 0

    def isOpened(self) -> bool:
        return self.opened

    def release(self) -> None:
        self.release_calls += 1


class _QueuedRoot:
    def __init__(self) -> None:
        self.after_calls: list[tuple[int, object]] = []
        self.destroy_calls = 0

    def after(self, delay: int, callback) -> None:
        self.after_calls.append((delay, callback))

    def destroy(self) -> None:
        self.destroy_calls += 1


def _preopen_app(index: int = 0):
    app = object.__new__(app_ui.App)
    app._preopen_lock = threading.Lock()
    app._preopen_cap = None
    app._preopen_index = None
    app._preopen_generation = 0
    app._worker = None
    app._source_state = app_ui.InputSourceState()
    app._source_state.select_camera(index)
    return app


def _closing_app():
    app = _preopen_app()
    app._transcode_lock = threading.Lock()
    app._transcode_workers = set()
    app._closing = False
    app._close_deadline = None
    app._stop_evt = threading.Event()
    app.root = _QueuedRoot()
    return app


def _enumeration_app():
    applied: list[tuple[list[object], bool]] = []
    app = SimpleNamespace(
        _enum_busy=threading.Event(),
        _closing=False,
        _camera_enum_result_queue=Queue(maxsize=1),
        _set_refresh_enabled=lambda: None,
        camera_combo=_Widget(),
        camera_choice_var=_Var(""),
        _apply_camera_entries=lambda entries, ok: applied.append((entries, ok)),
    )
    return app, applied


def test_preopen_late_generation_cannot_replace_newer_cap(monkeypatch):
    app = _preopen_app()
    pending = []

    class _PendingThread:
        def __init__(self, *, target, args, daemon) -> None:
            pending.append((target, args, daemon))

        def start(self) -> None:
            pass

    monkeypatch.setattr(app_ui.threading, "Thread", _PendingThread)

    app_ui.App._kick_preopen(app, 0)
    app_ui.App._kick_preopen(app, 0)
    assert pending[0][1][1] < pending[1][1][1]

    newest = _Cap()
    monkeypatch.setattr(app_ui, "open_camera", lambda _index: newest)
    pending[1][0](*pending[1][1])
    assert app._preopen_cap is newest

    late = _Cap()
    monkeypatch.setattr(app_ui, "open_camera", lambda _index: late)
    pending[0][0](*pending[0][1])

    assert app._preopen_cap is newest
    assert app._preopen_index == 0
    assert newest.release_calls == 0
    assert late.release_calls == 1


def test_camera_enumeration_result_is_applied_only_from_main_thread_queue(monkeypatch):
    app, applied = _enumeration_app()
    pending: list[object] = []
    entries = [object()]

    class _PendingThread:
        def __init__(self, *, target, daemon) -> None:
            pending.append(target)

        def start(self) -> None:
            pass

    monkeypatch.setattr(app_ui.threading, "Thread", _PendingThread)
    monkeypatch.setattr(app_ui, "enumerate_cameras", lambda: entries)

    app_ui.App._start_enumeration(app)
    pending[0]()

    assert applied == []
    app_ui.App._drain_camera_enum_results(app)
    assert applied == [(entries, True)]


def test_camera_enumeration_return_after_close_does_not_touch_tk(monkeypatch):
    app, applied = _enumeration_app()
    pending: list[object] = []

    class _PendingThread:
        def __init__(self, *, target, daemon) -> None:
            pending.append(target)

        def start(self) -> None:
            pass

    monkeypatch.setattr(app_ui.threading, "Thread", _PendingThread)
    monkeypatch.setattr(app_ui, "enumerate_cameras", lambda: [object()])

    app_ui.App._start_enumeration(app)
    app._closing = True
    pending[0]()
    app_ui.App._drain_camera_enum_results(app)

    assert applied == []
    assert app._camera_enum_result_queue.empty()


def test_preopen_rejects_unopened_cap_without_overwriting_valid_cap(monkeypatch):
    app = _preopen_app()
    app._preopen_generation = 4
    valid = _Cap()
    app._preopen_cap = valid
    app._preopen_index = 0
    failed = _Cap(opened=False)
    monkeypatch.setattr(app_ui, "open_camera", lambda _index: failed)

    app_ui.App._preopen_camera(app, 0, 4)

    assert app._preopen_cap is valid
    assert valid.release_calls == 0
    assert failed.release_calls == 1


def test_same_camera_kick_keeps_valid_cap_when_reopen_fails(monkeypatch):
    app = _preopen_app()
    valid = _Cap()
    app._preopen_cap = valid
    app._preopen_index = 0
    pending = []

    class _PendingThread:
        def __init__(self, *, target, args, daemon) -> None:
            pending.append((target, args, daemon))

        def start(self) -> None:
            pass

    monkeypatch.setattr(app_ui.threading, "Thread", _PendingThread)
    app_ui.App._kick_preopen(app, 0)
    assert app._preopen_cap is valid
    assert valid.release_calls == 0

    failed = _Cap(opened=False)
    monkeypatch.setattr(app_ui, "open_camera", lambda _index: failed)
    pending[0][0](*pending[0][1])

    assert app._preopen_cap is valid
    assert valid.release_calls == 0
    assert failed.release_calls == 1


def test_preopen_valid_replacement_releases_previous_handle(monkeypatch):
    app = _preopen_app()
    app._preopen_generation = 7
    previous = _Cap()
    replacement = _Cap()
    app._preopen_cap = previous
    app._preopen_index = 0
    monkeypatch.setattr(app_ui, "open_camera", lambda _index: replacement)

    app_ui.App._preopen_camera(app, 0, 7)

    assert app._preopen_cap is replacement
    assert previous.release_calls == 1
    assert replacement.release_calls == 0


def test_take_preopen_releases_mismatched_cached_handle():
    app = _preopen_app(index=1)
    cached = _Cap()
    app._preopen_cap = cached
    app._preopen_index = 0

    assert app_ui.App._take_preopen_cap(app, 1) is None
    assert cached.release_calls == 1
    assert app._preopen_cap is None
    assert app._preopen_index is None


def test_transcode_worker_is_non_daemon_tracked_and_removed(monkeypatch):
    app = _closing_app()
    entered = threading.Event()
    finish = threading.Event()

    def _transcode(_path: Path) -> None:
        entered.set()
        assert finish.wait(timeout=2.0)

    monkeypatch.setattr(app_ui.video_writer, "transcode_to_h264", _transcode)

    app_ui.App._transcode_async(app, Path("record.avi"))
    assert entered.wait(timeout=1.0)
    with app._transcode_lock:
        worker = next(iter(app._transcode_workers))
    assert worker.daemon is False

    finish.set()
    worker.join(timeout=1.0)
    assert not worker.is_alive()
    with app._transcode_lock:
        assert app._transcode_workers == set()


def test_close_waits_for_transcode_without_blocking_tk_loop(monkeypatch):
    app = _closing_app()
    entered = threading.Event()
    finish = threading.Event()

    def _transcode(_path: Path) -> None:
        entered.set()
        assert finish.wait(timeout=2.0)

    monkeypatch.setattr(app_ui.video_writer, "transcode_to_h264", _transcode)
    app_ui.App._transcode_async(app, Path("record.avi"))
    assert entered.wait(timeout=1.0)
    with app._transcode_lock:
        worker = next(iter(app._transcode_workers))

    app_ui.App._on_close(app)

    assert app._stop_evt.is_set()
    assert app.root.destroy_calls == 0
    assert app.root.after_calls[0][0] == app_ui._CLOSE_POLL_MS

    finish.set()
    worker.join(timeout=1.0)
    _delay, poll = app.root.after_calls.pop(0)
    poll()
    assert app.root.destroy_calls == 1


def test_close_destroys_window_after_bounded_deadline(monkeypatch):
    app = _closing_app()
    clock = [0.0]

    class _NeverEndingWorker:
        def __init__(self) -> None:
            self.join_timeouts: list[float] = []

        def is_alive(self) -> bool:
            return True

        def join(self, timeout=None) -> None:
            self.join_timeouts.append(timeout)

    worker = _NeverEndingWorker()
    app._transcode_workers.add(worker)
    monkeypatch.setattr(app_ui.time, "monotonic", lambda: clock[0])

    app_ui.App._on_close(app)
    assert app.root.destroy_calls == 0
    assert worker.join_timeouts == [app_ui._CLOSE_JOIN_SLICE_S]

    clock[0] = app_ui._CLOSE_JOIN_TIMEOUT_S + 0.1
    _delay, poll = app.root.after_calls.pop(0)
    poll()
    assert app.root.destroy_calls == 1


def test_close_resnapshots_transcode_spawned_by_capture_finally(monkeypatch):
    app = _closing_app()
    transcode_entered = threading.Event()
    transcode_finish = threading.Event()

    def _transcode(_path: Path) -> None:
        transcode_entered.set()
        assert transcode_finish.wait(timeout=2.0)

    monkeypatch.setattr(app_ui.video_writer, "transcode_to_h264", _transcode)

    class _CaptureFinishingWorker:
        def __init__(self) -> None:
            self.alive = True

        def is_alive(self) -> bool:
            return self.alive

        def join(self, timeout=None) -> None:
            self.alive = False
            app_ui.App._transcode_async(app, Path("capture-finally.avi"))

    app._worker = _CaptureFinishingWorker()
    app_ui.App._on_close(app)

    assert transcode_entered.wait(timeout=1.0)
    assert app.root.destroy_calls == 0
    assert app.root.after_calls[0][0] == app_ui._CLOSE_POLL_MS

    with app._transcode_lock:
        transcode_worker = next(iter(app._transcode_workers))
    transcode_finish.set()
    transcode_worker.join(timeout=1.0)
    _delay, poll = app.root.after_calls.pop(0)
    poll()
    assert app.root.destroy_calls == 1


def test_start_resets_stale_match_text(monkeypatch):
    app = object.__new__(app_ui.App)
    app._worker = None
    app._stop_evt = threading.Event()
    app._collect_state = lambda: SimpleNamespace(source2=None)
    app.start_btn = _Widget()
    app.stop_btn = _Widget()
    app.status_var = _Var()
    app.actions_var = _Var()
    app.match_var = _Var("识别到：直拳 (0.91)")
    app.progress_var = _Var()
    app.progress_text_var = _Var()
    app.progress_bar = _Widget()
    app._set_refresh_enabled = lambda: None
    app._set_dual_preview_visible = lambda _visible: None
    app._set_running_controls = lambda _running: None
    app._worker_loop = lambda _state: None

    class _StartOnlyThread:
        def __init__(self, *, target, args, daemon) -> None:
            self.target = target
            self.args = args
            self.daemon = daemon
            self.started = False

        def start(self) -> None:
            self.started = True

        def is_alive(self) -> bool:
            return self.started

    monkeypatch.setattr(app_ui.threading, "Thread", _StartOnlyThread)

    app_ui.App._start(app)

    assert app.match_var.get() == "识别：待机"
    assert app._worker.started is True


def test_second_camera_recording_failure_stops_pair_without_polluting_single_mode(
    monkeypatch, tmp_path
):
    class _Writer:
        def __init__(self) -> None:
            self.released = False

        def write(self, _frame) -> None:
            pass

        def release(self) -> None:
            self.released = True

    primary_writer = _Writer()

    def _primary_factory(path, _fps, _size):
        return primary_writer, Path(path), "fake"

    def _failing_factory(_path, _fps, _size):
        raise RuntimeError("side writer unavailable")

    rec = RecordingController(
        writer_factory=_primary_factory,
        path_provider=lambda: tmp_path / "front.mp4",
    )
    rec2 = RecordingController(
        writer_factory=_failing_factory,
        path_provider=lambda: tmp_path / "side.mp4",
    )
    for controller in (rec, rec2):
        controller.begin_session(fps=30.0, size=(4, 3))
        assert controller.request_toggle() == "recording"
    rec.write_frame(object())
    rec2.write_frame(object())
    assert rec.state == "recording"
    assert rec2.state == "idle"

    errors: list[tuple] = []
    transcodes: list[Path | None] = []
    app = SimpleNamespace(
        _rec=rec,
        _rec2=rec2,
        _record_pair_lock=threading.Lock(),
        _pending_record_errors=[],
        _record_error_shown=False,
        _dual_active=True,
        _transcode_async=lambda path: transcodes.append(path) if path is not None else None,
        _sync_record_stop_enabled=lambda _state: None,
        recording_status_var=_Var("录制中"),
        record_btn=_Widget(),
    )
    monkeypatch.setattr(
        app_ui.messagebox,
        "showerror",
        lambda *args, **kwargs: errors.append((args, kwargs)),
    )

    app_ui.App._refresh_recording_status(app)

    assert rec.state == "idle"
    assert rec2.state == "idle"
    assert rec.snapshot().last_error is None
    assert rec2.snapshot().last_error is None
    assert primary_writer.released is True
    assert transcodes == [tmp_path / "front.mp4"]
    assert len(errors) == 1
    assert "第二路：side writer unavailable" in errors[0][0][1]

    # 错误已被 stop_recording 消费；下一次刷新只复位弹框守卫，不重复提示。
    app_ui.App._refresh_recording_status(app)
    assert app._record_error_shown is False
    assert len(errors) == 1

    # 双摄会话结束后只启动主路，旧侧路错误不得误停或污染单摄录制状态。
    rec.close_session()
    rec2.close_session()
    app._dual_active = False
    rec.begin_session(fps=30.0, size=(4, 3))
    assert rec.request_toggle() == "recording"

    app_ui.App._refresh_recording_status(app)

    assert rec.state == "recording"
    assert len(errors) == 1
    assert app.recording_status_var.get().startswith("录制中：")


class _ObservedPairLock:
    """真实互斥锁包装：第二个线程开始等待时发信号，避免靠 sleep 猜时序。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._count_lock = threading.Lock()
        self._enter_count = 0
        self.waiter_entered = threading.Event()

    def __enter__(self):
        with self._count_lock:
            self._enter_count += 1
            if self._enter_count >= 2:
                self.waiter_entered.set()
        self._lock.acquire()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self._lock.release()


def _run_captured(target, errors: list[BaseException]) -> None:
    try:
        target()
    except BaseException as exc:  # noqa: BLE001 - 子线程异常必须回传给测试线程
        errors.append(exc)


def test_record_toggle_waits_for_pair_write_and_publishes_stamp_before_both_toggles():
    order: list[str] = []
    first_write_entered = threading.Event()
    allow_first_write = threading.Event()
    observed_stamps: dict[str, str | None] = {}
    observed_bases: dict[str, Path] = {}
    old_base = Path("old-base")
    new_base = Path("new-base")

    class _Recorder:
        def __init__(self, name: str, *, block_write: bool = False) -> None:
            self.name = name
            self.block_write = block_write
            self.state = "idle"

        def write_frame(self, _frame) -> None:
            observed_bases[self.name] = app._record_base_dir
            order.append(f"{self.name}:write:start")
            if self.block_write:
                first_write_entered.set()
                if not allow_first_write.wait(timeout=2.0):
                    raise TimeoutError("测试未释放第一路 write")
            order.append(f"{self.name}:write:end")

        def request_toggle(self) -> str:
            observed_stamps[self.name] = app._record_stamp
            order.append(f"{self.name}:toggle")
            self.state = "recording"
            return self.state

    lock = _ObservedPairLock()
    primary = _Recorder("primary", block_write=True)
    secondary = _Recorder("secondary")
    app = SimpleNamespace(
        _rec=primary,
        _rec2=secondary,
        _record_pair_lock=lock,
        _record_stamp="old-stamp",
        _record_base_dir=old_base,
        record_dir_var=_Var(str(new_base)),
        record_btn=_Widget(),
        _sync_record_stop_enabled=lambda _state: None,
    )
    errors: list[BaseException] = []
    write_thread = threading.Thread(
        target=lambda: _run_captured(
            lambda: app_ui.App._write_recording_pair(app, object(), object()), errors
        )
    )
    toggle_thread = threading.Thread(
        target=lambda: _run_captured(lambda: app_ui.App._on_record_toggle(app), errors)
    )

    write_thread.start()
    assert first_write_entered.wait(timeout=1.0)
    toggle_thread.start()
    assert lock.waiter_entered.wait(timeout=1.0)
    assert not any(item.endswith(":toggle") for item in order)
    assert app._record_base_dir == old_base

    allow_first_write.set()
    write_thread.join(timeout=2.0)
    toggle_thread.join(timeout=2.0)

    assert not write_thread.is_alive()
    assert not toggle_thread.is_alive()
    assert errors == []
    assert order == [
        "primary:write:start",
        "primary:write:end",
        "secondary:write:start",
        "secondary:write:end",
        "primary:toggle",
        "secondary:toggle",
    ]
    assert observed_stamps["primary"] != "old-stamp"
    assert observed_stamps["secondary"] == observed_stamps["primary"]
    assert observed_bases == {"primary": old_base, "secondary": old_base}
    assert app._record_base_dir == new_base


def test_record_stop_waits_until_both_writes_finish():
    order: list[str] = []
    first_write_entered = threading.Event()
    allow_first_write = threading.Event()

    class _Recorder:
        def __init__(self, name: str, *, block_write: bool = False) -> None:
            self.name = name
            self.block_write = block_write

        def write_frame(self, _frame) -> None:
            order.append(f"{self.name}:write:start")
            if self.block_write:
                first_write_entered.set()
                if not allow_first_write.wait(timeout=2.0):
                    raise TimeoutError("测试未释放第一路 write")
            order.append(f"{self.name}:write:end")

        def stop_recording(self) -> Path:
            order.append(f"{self.name}:stop")
            return Path(f"{self.name}.mp4")

        def snapshot(self):
            return SimpleNamespace(
                state="recording",
                result_path=Path(f"{self.name}.mp4"),
                frames_written=1,
                last_error=None,
            )

    lock = _ObservedPairLock()
    app = SimpleNamespace(
        _rec=_Recorder("primary", block_write=True),
        _rec2=_Recorder("secondary"),
        _record_pair_lock=lock,
        _transcode_async=lambda _path: None,
        _sync_record_stop_enabled=lambda _state: None,
        record_btn=_Widget(),
    )
    errors: list[BaseException] = []
    write_thread = threading.Thread(
        target=lambda: _run_captured(
            lambda: app_ui.App._write_recording_pair(app, object(), object()), errors
        )
    )
    stop_thread = threading.Thread(
        target=lambda: _run_captured(lambda: app_ui.App._on_record_stop(app), errors)
    )

    write_thread.start()
    assert first_write_entered.wait(timeout=1.0)
    stop_thread.start()
    assert lock.waiter_entered.wait(timeout=1.0)
    assert not any(item.endswith(":stop") for item in order)

    allow_first_write.set()
    write_thread.join(timeout=2.0)
    stop_thread.join(timeout=2.0)

    assert not write_thread.is_alive()
    assert not stop_thread.is_alive()
    assert errors == []
    assert order == [
        "primary:write:start",
        "primary:write:end",
        "secondary:write:start",
        "secondary:write:end",
        "primary:stop",
        "secondary:stop",
    ]


def test_dual_close_preserves_unseen_side_error_for_next_tk_tick(monkeypatch, tmp_path):
    rec = RecordingController(
        writer_factory=lambda path, _fps, _size: (object(), Path(path), "fake"),
        path_provider=lambda: tmp_path / "front.mp4",
    )

    def _failing_factory(_path, _fps, _size):
        raise RuntimeError("side failed on final frame")

    rec2 = RecordingController(
        writer_factory=_failing_factory,
        path_provider=lambda: tmp_path / "side.mp4",
    )
    for controller in (rec, rec2):
        controller.begin_session(fps=30.0, size=(4, 3))
        controller.request_toggle()
    rec2.write_frame(object())

    errors: list[str] = []
    app = SimpleNamespace(
        _rec=rec,
        _rec2=rec2,
        _record_pair_lock=threading.Lock(),
        _pending_record_errors=[],
        _record_error_shown=False,
        _dual_active=True,
        _transcode_async=lambda _path: None,
        _sync_record_stop_enabled=lambda _state: None,
        recording_status_var=_Var(""),
        record_btn=_Widget(),
    )
    monkeypatch.setattr(
        app_ui.messagebox,
        "showerror",
        lambda _title, message: errors.append(message),
    )

    app_ui.App._close_recording_pair(app)
    assert app._dual_active is False
    assert rec2.snapshot().last_error is None

    app_ui.App._refresh_recording_status(app)

    assert errors == ["录制发生错误：\n第二路：side failed on final frame"]
    assert app._pending_record_errors == []


def _dual_submission_app(tmp_path: Path, *, write_frames: bool = True):
    stamp = "20260709_120000_123456"
    segment_dir = tmp_path / stamp[:8] / f"record_{stamp}"

    class _Writer:
        def __init__(self) -> None:
            self.frames: list[object] = []

        def write(self, frame) -> None:
            self.frames.append(frame)

        def release(self) -> None:
            pass

    def _controller(name: str):
        return RecordingController(
            writer_factory=lambda path, _fps, _size: (_Writer(), Path(path), "fake"),
            path_provider=lambda: segment_dir / f"{name}.mp4",
        )

    rec = _controller("front")
    rec2 = _controller("side")
    for controller in (rec, rec2):
        controller.begin_session(fps=30.0, size=(4, 3))
        controller.request_toggle()
        if write_frames:
            controller.write_frame(object())

    class _Processor:
        def __init__(self) -> None:
            self.jobs = []
            self.close_calls: list[float] = []
            self.cancel_calls = 0

        def submit(self, job) -> bool:
            self.jobs.append(job)
            return True

        def close(self, timeout: float) -> None:
            self.close_calls.append(timeout)

        def cancel_all(self) -> None:
            self.cancel_calls += 1

    processor = _Processor()
    app = SimpleNamespace(
        _rec=rec,
        _rec2=rec2,
        _record_pair_lock=threading.Lock(),
        _record_finalize_lock=threading.RLock(),
        _pending_record_errors=[],
        _dual_active=True,
        _dual_record_skeleton=False,
        _record_stamp=stamp,
        _record_base_dir=tmp_path,
        _record_postprocessor=processor,
        _submitted_record_segments=set(),
        _latest_compare_segment_id=None,
        _transcode_async=lambda _path: (_ for _ in ()).throw(
            AssertionError("dual recording must use the postprocessor")
        ),
        _sync_record_stop_enabled=lambda _state: None,
        record_btn=_Widget(),
    )
    return app, processor, segment_dir


def test_dual_record_stop_submits_exactly_once_and_allows_next_segment(tmp_path):
    app, processor, segment_dir = _dual_submission_app(tmp_path)

    app_ui.App._on_record_stop(app)

    assert app._rec.state == "idle"
    assert app._rec2.state == "idle"
    assert len(processor.jobs) == 1
    job = processor.jobs[0]
    assert job.segment_id == segment_dir.name
    assert job.front_source == segment_dir / "front.mp4"
    assert job.side_source == segment_dir / "side.mp4"
    assert job.front_frames == job.side_frames == 1
    assert job.record_skeleton is False

    app_ui.App._close_recording_pair(app)
    assert len(processor.jobs) == 1
    assert app._dual_active is False


def test_compare_update_ignores_old_segment_and_formats_latest_score():
    app = SimpleNamespace(
        _closing=False,
        _latest_compare_segment_id="record_new",
        _compare_update_queue=Queue(),
        root=_QueuedRoot(),
        compare_segment_var=_Var("片段：record_new"),
        compare_status_var=_Var("自动比对：排队中"),
        compare_score_var=_Var("unchanged"),
        compare_error_var=_Var(""),
    )

    old = app_ui.PostprocessUpdate(
        segment_id="record_old",
        status="completed",
        message="done",
        front_score=0.1,
        side_score=0.2,
        combined_percent=15,
    )
    app_ui.App._post_recording_compare_update(app, old)
    assert app.root.after_calls == []
    app_ui.App._drain_recording_compare_updates(app)
    assert app.compare_score_var.get() == "unchanged"

    latest = app_ui.PostprocessUpdate(
        segment_id="record_new",
        status="completed",
        message="done",
        front_score=0.823,
        side_score=0.891,
        combined_percent=86,
    )
    app_ui.App._post_recording_compare_update(app, latest)
    assert app.root.after_calls == []
    app_ui.App._drain_recording_compare_updates(app)

    assert app.compare_status_var.get() == "自动比对：已完成"
    assert app.compare_score_var.get() == "正面：82.3%　侧面：89.1%　综合：86%"
    assert app.compare_error_var.get() == ""

    app._closing = True
    app_ui.App._post_recording_compare_update(app, latest)
    app_ui.App._drain_recording_compare_updates(app)
    assert app.root.after_calls == []


def test_compare_update_formats_failed_skipped_and_cancelled_states():
    app = SimpleNamespace(
        _closing=False,
        _latest_compare_segment_id="record_terminal",
        _compare_update_queue=Queue(),
        compare_segment_var=_Var("片段：record_terminal"),
        compare_status_var=_Var("自动比对：排队中"),
        compare_score_var=_Var("stale score"),
        compare_error_var=_Var(""),
    )
    cases = (
        ("failed", "失败", "video_unreadable", "录像无法读取"),
        ("skipped", "已跳过", "annotated_recording", "带骨架录像未自动比对"),
        ("cancelled", "已取消", "app_closing", "应用关闭"),
    )

    for status, label, code, message in cases:
        app_ui.App._post_recording_compare_update(
            app,
            app_ui.PostprocessUpdate(
                "record_terminal",
                status,
                message,
                error_code=code,
            ),
        )
        app_ui.App._drain_recording_compare_updates(app)
        assert app.compare_status_var.get() == f"自动比对：{label}"
        assert app.compare_score_var.get() == "正面：-　侧面：-　综合：-"
        assert app.compare_error_var.get() == f"{code}：{message}"


def test_compare_update_already_queued_is_discarded_after_close_starts():
    app = SimpleNamespace(
        _closing=False,
        _latest_compare_segment_id="record_latest",
        _compare_update_queue=Queue(),
        compare_segment_var=_Var("片段：record_latest"),
        compare_status_var=_Var("自动比对：排队中"),
        compare_score_var=_Var("unchanged"),
        compare_error_var=_Var(""),
    )
    app_ui.App._post_recording_compare_update(
        app,
        app_ui.PostprocessUpdate(
            "record_latest",
            "completed",
            "done",
            front_score=0.9,
            side_score=0.9,
            combined_percent=90,
        ),
    )

    app._closing = True
    app_ui.App._drain_recording_compare_updates(app)

    assert app.compare_score_var.get() == "unchanged"


def test_dual_layout_update_uses_queue_and_never_touches_tk_after_close():
    applied: list[str] = []
    app = SimpleNamespace(
        _closing=False,
        _dual_layout_queue=Queue(maxsize=1),
        _set_dual_preview_layout=lambda layout: applied.append(layout),
    )

    app_ui.App._post_dual_preview_layout(app, "stacked")
    app_ui.App._post_dual_preview_layout(app, "side_by_side")
    app_ui.App._drain_dual_preview_layout(app)
    assert applied == ["side_by_side"]

    app._closing = True
    app_ui.App._post_dual_preview_layout(app, "stacked")
    app_ui.App._drain_dual_preview_layout(app)
    assert applied == ["side_by_side"]


def test_main_stop_finally_submits_current_dual_segment_once(tmp_path):
    app, processor, _segment_dir = _dual_submission_app(tmp_path)
    app._stop_evt = threading.Event()
    app.stop_btn = _Widget()
    app.status_var = _Var()

    app_ui.App._stop(app)
    app_ui.App._close_recording_pair(app)
    app_ui.App._close_recording_pair(app)

    assert app._stop_evt.is_set()
    assert app.status_var.get() == "正在停止…"
    assert len(processor.jobs) == 1


def test_zero_frame_dual_segment_is_submitted_from_explicit_and_main_stop(tmp_path):
    for mode in ("explicit", "main_stop"):
        app, processor, _segment_dir = _dual_submission_app(
            tmp_path / mode, write_frames=False
        )
        if mode == "explicit":
            app_ui.App._on_record_stop(app)
        else:
            app._stop_evt = threading.Event()
            app.stop_btn = _Widget()
            app.status_var = _Var()
            app_ui.App._stop(app)
            app_ui.App._close_recording_pair(app)

        assert len(processor.jobs) == 1
        assert processor.jobs[0].front_frames == 0
        assert processor.jobs[0].side_frames == 0


def test_second_dual_segment_can_start_before_first_result_finishes(tmp_path):
    app, processor, _first_dir = _dual_submission_app(tmp_path)
    app_ui.App._on_record_stop(app)
    first_job = processor.jobs[0]

    app_ui.App._on_record_toggle(app)
    second_stamp = app._record_stamp
    second_dir = tmp_path / second_stamp[:8] / f"record_{second_stamp}"
    app._rec._path_provider = lambda: second_dir / "front.mp4"
    app._rec2._path_provider = lambda: second_dir / "side.mp4"
    app_ui.App._write_recording_pair(app, object(), object())
    app_ui.App._on_record_stop(app)

    assert len(processor.jobs) == 2
    second_job = processor.jobs[1]
    assert second_job.segment_id != first_job.segment_id
    assert second_job.front_source == second_dir / "front.mp4"
    assert second_job.side_source == second_dir / "side.mp4"
    assert second_job.front_frames == second_job.side_frames == 1


def test_dual_submit_runs_outside_record_pair_lock(tmp_path):
    app, processor, _segment_dir = _dual_submission_app(tmp_path)
    original_submit = processor.submit
    pair_lock_was_free: list[bool] = []

    def submit(job) -> bool:
        acquired = app._record_pair_lock.acquire(blocking=False)
        pair_lock_was_free.append(acquired)
        if acquired:
            app._record_pair_lock.release()
        return original_submit(job)

    processor.submit = submit
    app_ui.App._on_record_stop(app)

    assert pair_lock_was_free == [True]


def test_writer_error_submits_formal_job_once_without_modal(tmp_path, monkeypatch):
    app, processor, _segment_dir = _dual_submission_app(tmp_path)
    app._record_error_shown = False
    app.recording_status_var = _Var("录制中")
    errors: list[str] = []
    monkeypatch.setattr(
        app_ui.messagebox,
        "showerror",
        lambda _title, message: errors.append(message),
    )
    with app._rec2._lock:
        app._rec2._last_error = "side writer unavailable"
        app._rec2._state = "idle"

    app_ui.App._refresh_recording_status(app)
    app_ui.App._close_recording_pair(app)

    assert errors == []
    assert len(processor.jobs) == 1
    assert processor.jobs[0].side_error == "side writer unavailable"


def test_toggle_after_primary_writer_failure_finalizes_old_pair_before_new_stamp(
    tmp_path,
):
    app, processor, segment_dir = _dual_submission_app(tmp_path)
    old_stamp = app._record_stamp
    with app._rec._lock:
        app._rec._last_error = "front writer unavailable"
        app._rec._state = "idle"

    app_ui.App._on_record_toggle(app)

    assert app._record_stamp == old_stamp
    assert app._rec.state == "idle"
    assert app._rec2.state == "idle"
    assert len(processor.jobs) == 1
    job = processor.jobs[0]
    assert job.segment_id == segment_dir.name
    assert job.front_source == segment_dir / "front.mp4"
    assert job.side_source == segment_dir / "side.mp4"
    assert job.front_error == "front writer unavailable"


def test_submit_callback_sees_segment_as_latest_before_submit_returns(tmp_path):
    app, _processor, _segment_dir = _dual_submission_app(tmp_path)
    app._compare_update_queue = Queue()
    app.compare_segment_var = _Var("片段：-")
    app.compare_status_var = _Var("自动比对：待机")
    app.compare_score_var = _Var("正面：-　侧面：-　综合：-")
    app.compare_error_var = _Var("")
    observed_latest: list[str | None] = []

    class _ImmediateProcessor:
        def submit(self, job) -> bool:
            update = app_ui.PostprocessUpdate(job.segment_id, "queued", "queued")
            app_ui.App._post_recording_compare_update(app, update)
            app_ui.App._drain_recording_compare_updates(app)
            observed_latest.append(app._latest_compare_segment_id)
            return True

    app._record_postprocessor = _ImmediateProcessor()
    app_ui.App._on_record_stop(app)

    processor_job_id = app._latest_compare_segment_id
    assert observed_latest == [processor_job_id]
    assert processor_job_id is not None
    assert app.compare_segment_var.get() == f"片段：{processor_job_id}"


def test_close_finalizes_current_dual_segment_then_cancels_postprocessor(tmp_path):
    app, processor, _segment_dir = _dual_submission_app(tmp_path)
    app._closing = False
    app._stop_evt = threading.Event()
    app._release_preopen_cap = lambda: None
    app._poll_close_workers = lambda: None
    app._close_deadline = None

    app_ui.App._on_close(app)
    app._close_prepare_worker.join(1.0)

    assert app._closing is True
    assert app._stop_evt.is_set()
    assert len(processor.jobs) == 1
    assert processor.cancel_calls == 1


def test_close_returns_while_inflight_finalize_finishes_before_cancelling(tmp_path):
    app, processor, _segment_dir = _dual_submission_app(tmp_path)
    app._closing = False
    app._stop_evt = threading.Event()
    app._release_preopen_cap = lambda: None
    app._poll_close_workers = lambda: None
    app._close_deadline = None
    submit_started = threading.Event()
    release_submit = threading.Event()
    original_submit = processor.submit
    errors: list[BaseException] = []

    def submit(job) -> bool:
        accepted = original_submit(job)
        submit_started.set()
        assert release_submit.wait(2.0)
        return accepted

    processor.submit = submit

    def run(target) -> None:
        try:
            target()
        except BaseException as exc:  # noqa: BLE001 - thread failures must reach test
            errors.append(exc)

    finalize_thread = threading.Thread(
        target=lambda: run(lambda: app_ui.App._close_recording_pair(app))
    )
    finalize_thread.start()
    assert submit_started.wait(1.0)

    app_ui.App._on_close(app)

    assert processor.cancel_calls == 0
    assert app._close_deadline is not None
    assert app._close_prepare_worker.is_alive()
    release_submit.set()
    finalize_thread.join(2.0)
    app._close_prepare_worker.join(2.0)

    assert not finalize_thread.is_alive()
    assert not app._close_prepare_worker.is_alive()
    assert errors == []
    assert len(processor.jobs) == 1
    assert processor.cancel_calls == 1


def test_close_deadline_is_set_before_blocking_cancel_work(tmp_path):
    app, processor, _segment_dir = _dual_submission_app(tmp_path)
    app._closing = False
    app._stop_evt = threading.Event()
    app._release_preopen_cap = lambda: None
    app._poll_close_workers = lambda: None
    app._close_deadline = None
    cancel_started = threading.Event()
    release_cancel = threading.Event()
    original_cancel = processor.cancel_all

    def cancel_all() -> None:
        cancel_started.set()
        assert release_cancel.wait(2.0)
        original_cancel()

    processor.cancel_all = cancel_all

    app_ui.App._on_close(app)

    assert app._close_deadline is not None
    assert cancel_started.wait(1.0)
    assert app._close_prepare_worker.is_alive()
    release_cancel.set()
    app._close_prepare_worker.join(2.0)
    assert not app._close_prepare_worker.is_alive()


def test_close_poll_window_disables_recording_controls_and_rejects_toggle():
    app = _closing_app()
    release_prepare = threading.Event()
    controls = {
        name: _Widget()
        for name in (
            "record_btn",
            "record_stop_btn",
            "record_skeleton_check",
            "record_dir_entry",
            "record_dir_btn",
        )
    }
    for name, control in controls.items():
        setattr(app, name, control)

    class _UnexpectedTkRead:
        def get(self):
            raise AssertionError("closing toggle must return before reading Tk state")

    app.record_dir_var = _UnexpectedTkRead()
    app._release_preopen_cap = lambda: release_prepare.wait(2.0)

    try:
        app_ui.App._on_close(app)

        assert app._close_prepare_worker.is_alive()
        assert app.root.after_calls[0][0] == app_ui._CLOSE_POLL_MS
        assert all(control.config["state"] == "disabled" for control in controls.values())
        app_ui.App._on_record_toggle(app)
    finally:
        release_prepare.set()
        app._close_prepare_worker.join(2.0)

    assert not app._close_prepare_worker.is_alive()


def test_close_poll_waits_for_postprocessor_worker(monkeypatch):
    app = _closing_app()
    clock = [0.0]

    class _Worker:
        def __init__(self) -> None:
            self.alive = True

        def is_alive(self) -> bool:
            return self.alive

    class _Processor:
        def __init__(self) -> None:
            self._worker = _Worker()
            self.close_calls: list[float] = []

        def close(self, timeout: float) -> None:
            self.close_calls.append(timeout)

    processor = _Processor()
    app._record_postprocessor = processor
    app._close_deadline = app_ui._CLOSE_JOIN_TIMEOUT_S
    monkeypatch.setattr(app_ui.time, "monotonic", lambda: clock[0])

    app_ui.App._poll_close_workers(app)

    assert processor.close_calls == [app_ui._CLOSE_JOIN_SLICE_S]
    assert app.root.destroy_calls == 0
    assert app.root.after_calls[0][0] == app_ui._CLOSE_POLL_MS

    processor._worker.alive = False
    _delay, poll = app.root.after_calls.pop(0)
    poll()
    assert app.root.destroy_calls == 1


def test_close_poll_enqueues_postprocessor_sentinel_after_deadline(monkeypatch):
    app = _closing_app()

    class _Worker:
        def is_alive(self) -> bool:
            return False

    class _Processor:
        def __init__(self) -> None:
            self._worker = _Worker()
            self.close_calls: list[float] = []

        def close(self, timeout: float) -> None:
            self.close_calls.append(timeout)

    processor = _Processor()
    app._record_postprocessor = processor
    app._close_deadline = 1.0
    monkeypatch.setattr(app_ui.time, "monotonic", lambda: 2.0)

    app_ui.App._poll_close_workers(app)

    assert processor.close_calls == [0.0]
    assert app.root.destroy_calls == 1
