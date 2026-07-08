# -*- coding: utf-8 -*-
"""Tkinter 双摄骨架测试（issue #59 裁剪版）。

不创建真实 Tk root，只验证 source2 收敛点和双 VIDEO pipeline 结构。
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from apps import app_ui  # noqa: E402
from apps.camera_enum import CameraEntry  # noqa: E402


class _Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def _app_stub(*, source: str = "0", second_label: str = app_ui.NO_SECOND_CAMERA):
    app = object.__new__(app_ui.App)
    app.source_var = _Var(source)
    app.pose_var = _Var("full")
    app.workers_var = _Var(2)
    app.enable_hands_var = _Var(True)
    app.save_var = _Var(False)
    app.out_var = _Var("")
    app.camera_choice_var_2 = _Var(second_label)
    app._source_state = app_ui.InputSourceState()
    if source.isdigit():
        app._source_state.select_camera(int(source))
    else:
        app._source_state.select_video(source)
    app._camera_entries = [
        CameraEntry(label="摄像头 0", index=0),
        CameraEntry(label="摄像头 1", index=1),
    ]
    return app


def test_collect_state_sets_source2_when_two_distinct_cameras_selected():
    app = _app_stub(source="0", second_label="摄像头 1")

    state = app_ui.App._collect_state(app)

    assert state.source == "0"
    assert state.source2 == "1"
    assert state.enable_hands is True


def test_collect_state_leaves_source2_none_for_single_camera_mode():
    app = _app_stub(source="0", second_label=app_ui.NO_SECOND_CAMERA)

    state = app_ui.App._collect_state(app)

    assert state.source2 is None


def test_collect_state_ignores_second_camera_for_video_file_source():
    app = _app_stub(source="input.mp4", second_label="摄像头 1")

    state = app_ui.App._collect_state(app)

    assert state.source == "input.mp4"
    assert state.source2 is None


def test_collect_state_rejects_same_camera_for_both_views():
    app = _app_stub(source="0", second_label="摄像头 0")

    with pytest.raises(ValueError, match="两个摄像头不能选同一个"):
        app_ui.App._collect_state(app)


def test_dual_camera_worker_creates_two_mediapipe_pipelines():
    tree = ast.parse(Path(app_ui.__file__).read_text(encoding="utf-8"))
    worker = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_worker_loop_dual_camera"
    )

    calls = [
        node
        for node in ast.walk(worker)
        if isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Name) and node.func.id == "MediaPipePipeline")
            or (isinstance(node.func, ast.Attribute) and node.func.attr == "MediaPipePipeline")
        )
    ]

    assert len(calls) == 2
