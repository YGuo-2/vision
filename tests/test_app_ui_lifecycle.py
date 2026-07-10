# -*- coding: utf-8 -*-
"""Tkinter 摄像头预打开、识别状态与转码关窗生命周期测试（无需真实 Tk/camera）。"""
from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace

from apps import app_ui


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
