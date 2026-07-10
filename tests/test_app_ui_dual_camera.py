# -*- coding: utf-8 -*-
"""Tkinter 双摄骨架测试（issue #59 裁剪版）。

不创建真实 Tk root，只验证 source2 收敛点和双 VIDEO pipeline 结构。
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import numpy as np
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


class _GridWidget:
    """Headless ttk widget fake that preserves grid options across grid_remove()."""

    def __init__(self) -> None:
        self.grid_options: dict[str, object] = {}
        self.visible = False

    def grid(self, **kwargs) -> None:
        if kwargs:
            self.grid_options.update(kwargs)
        self.visible = True

    grid_configure = grid

    def grid_remove(self) -> None:
        self.visible = False


class _GridContainer:
    def __init__(self) -> None:
        self.row_weights: dict[int, int] = {}
        self.column_weights: dict[int, int] = {}

    def rowconfigure(self, index: int, *, weight: int) -> None:
        self.row_weights[index] = weight

    def columnconfigure(self, index: int, *, weight: int) -> None:
        self.column_weights[index] = weight


def _app_stub(
    *,
    source: str = "0",
    second_label: str = app_ui.NO_SECOND_CAMERA,
    rotate: str = "0°",
    rotate2: str = "0°",
):
    app = object.__new__(app_ui.App)
    app.source_var = _Var(source)
    app.pose_var = _Var("full")
    app.workers_var = _Var(2)
    app.enable_hands_var = _Var(True)
    app.save_var = _Var(False)
    app.out_var = _Var("")
    app.camera_choice_var_2 = _Var(second_label)
    app.rotate_var = _Var(rotate)
    app.rotate_var_2 = _Var(rotate2)
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


def _layout_stub():
    app = object.__new__(app_ui.App)
    app._preview_right = _GridContainer()
    app._dual_preview_visible = True
    app._dual_preview_layout = "stacked"
    app.preview = _GridWidget()
    app.preview2 = _GridWidget()
    app.preview.grid(row=0, column=0, sticky="nsew")
    app.preview2.grid(row=1, column=0, sticky="nsew")
    return app


def _function_node(name: str) -> ast.FunctionDef:
    tree = ast.parse(Path(app_ui.__file__).read_text(encoding="utf-8"))
    return next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def _named_calls(node: ast.AST, name: str) -> list[ast.Call]:
    return [
        item
        for item in ast.walk(node)
        if isinstance(item, ast.Call)
        and (
            (isinstance(item.func, ast.Name) and item.func.id == name)
            or (isinstance(item.func, ast.Attribute) and item.func.attr == name)
        )
    ]


@pytest.mark.parametrize(
    ("text", "expected"),
    [("0°", 0), ("90°", 90), ("180°", 180), ("270°", 270)],
)
def test_parse_rotate_accepts_only_supported_choices(text, expected):
    assert app_ui._parse_rotate(text) == expected


@pytest.mark.parametrize("text", ["", "45°", "360°", "-90°", "abc", None])
def test_parse_rotate_rejects_unsupported_values(text):
    assert app_ui._parse_rotate(text) == 0


@pytest.mark.parametrize(
    ("degrees", "turns"),
    [(90, -1), (180, 2), (270, 1)],
)
def test_apply_rotation_matches_clockwise_degree_contract(degrees, turns):
    frame = np.arange(18, dtype=np.uint8).reshape(2, 3, 3)

    rotated = app_ui._apply_rotation(frame, degrees)

    np.testing.assert_array_equal(rotated, np.rot90(frame, k=turns))


@pytest.mark.parametrize("degrees", [0, 45])
def test_apply_rotation_returns_original_frame_when_no_rotation_applies(degrees):
    frame = np.zeros((2, 3, 3), dtype=np.uint8)

    assert app_ui._apply_rotation(frame, degrees) is frame


@pytest.mark.parametrize(
    ("degrees", "expected"),
    [(0, (1280, 720)), (90, (720, 1280)), (180, (1280, 720)), (270, (720, 1280))],
)
def test_rotated_size_matches_rotated_frame_dimensions(degrees, expected):
    assert app_ui._rotated_size(1280, 720, degrees) == expected


@pytest.mark.parametrize(
    ("size1", "size2", "expected"),
    [
        ((720, 1280), (1080, 1920), "side_by_side"),
        ((1280, 720), (1920, 1080), "stacked"),
        ((720, 1280), (1920, 1080), "stacked"),
        ((1280, 720), (1080, 1920), "stacked"),
        ((720, 720), (720, 1280), "stacked"),
    ],
)
def test_choose_dual_preview_layout_handles_portrait_landscape_and_mixed(
    size1, size2, expected
):
    assert app_ui._choose_dual_preview_layout(size1, size2) == expected


def test_set_dual_preview_layout_places_portrait_views_side_by_side():
    app = _layout_stub()

    app_ui.App._set_dual_preview_layout(app, "side_by_side")

    assert app.preview.grid_options == {"row": 0, "column": 0, "sticky": "nsew"}
    assert app.preview2.grid_options == {"row": 0, "column": 1, "sticky": "nsew"}
    assert app._preview_right.row_weights == {0: 1, 1: 0}
    assert app._preview_right.column_weights == {0: 1, 1: 1}


def test_set_dual_preview_layout_places_landscape_and_mixed_views_stacked():
    app = _layout_stub()
    app_ui.App._set_dual_preview_layout(app, "side_by_side")

    app_ui.App._set_dual_preview_layout(app, "stacked")

    assert app.preview.grid_options == {"row": 0, "column": 0, "sticky": "nsew"}
    assert app.preview2.grid_options == {"row": 1, "column": 0, "sticky": "nsew"}
    assert app._preview_right.row_weights == {0: 1, 1: 1}
    assert app._preview_right.column_weights == {0: 1, 1: 0}


def test_hiding_second_preview_collapses_both_optional_grid_tracks():
    app = _layout_stub()
    app_ui.App._set_dual_preview_layout(app, "side_by_side")

    app_ui.App._set_dual_preview_visible(app, False)

    assert app.preview2.visible is False
    assert app._preview_right.row_weights[1] == 0
    assert app._preview_right.column_weights[1] == 0


def test_collect_state_sets_source2_when_two_distinct_cameras_selected():
    app = _app_stub(source="0", second_label="摄像头 1")

    state = app_ui.App._collect_state(app)

    assert state.source == "0"
    assert state.source2 == "1"
    assert state.enable_hands is True


def test_collect_state_captures_each_camera_rotation():
    app = _app_stub(
        source="0",
        second_label="摄像头 1",
        rotate="90°",
        rotate2="270°",
    )

    state = app_ui.App._collect_state(app)

    assert state.rotate == 90
    assert state.rotate2 == 270


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
    worker = _function_node("_worker_loop_dual_camera")

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


@pytest.mark.parametrize(
    ("worker_name", "expected_args"),
    [
        ("_worker_loop", [("frame", "state.rotate")]),
        (
            "_worker_loop_dual_camera",
            [("frame", "state.rotate"), ("frame2", "state.rotate2")],
        ),
        ("_worker_loop_parallel_camera", [("frame", "state.rotate")]),
    ],
)
def test_all_camera_capture_paths_apply_rotation(worker_name, expected_args):
    calls = _named_calls(_function_node(worker_name), "_apply_rotation")
    actual_args = sorted(
        (ast.unparse(call.args[0]), ast.unparse(call.args[1])) for call in calls
    )

    assert actual_args == sorted(expected_args)


def test_shared_single_worker_rotation_is_guarded_to_camera_sources():
    worker = _function_node("_worker_loop")
    guarded_calls = []
    for branch in ast.walk(worker):
        if not isinstance(branch, ast.If) or ast.unparse(branch.test) != "not is_file":
            continue
        for statement in branch.body:
            guarded_calls.extend(_named_calls(statement, "_apply_rotation"))

    assert len(guarded_calls) == 1


def test_parallel_video_path_does_not_apply_camera_rotation():
    worker = _function_node("_worker_loop_parallel_video")

    assert _named_calls(worker, "_apply_rotation") == []
    assert _named_calls(worker, "_rotated_size") == []
    assert _named_calls(worker, "update_session_size") == []


@pytest.mark.parametrize(
    ("worker_name", "expected"),
    [
        (
            "_worker_loop",
            [("self._rec", "(int(frame.shape[1]), int(frame.shape[0]))")],
        ),
        (
            "_worker_loop_dual_camera",
            [("self._rec", "actual_size"), ("self._rec2", "actual_size2")],
        ),
        (
            "_worker_loop_parallel_camera",
            [("self._rec", "(int(frame.shape[1]), int(frame.shape[0]))")],
        ),
    ],
)
def test_camera_paths_correct_writer_size_from_rotated_first_frame(worker_name, expected):
    calls = _named_calls(_function_node(worker_name), "update_session_size")
    actual = [
        (
            ast.unparse(call.func.value),
            ast.unparse(next(kw.value for kw in call.keywords if kw.arg == "size")),
        )
        for call in calls
    ]

    assert sorted(actual) == sorted(expected)

    if worker_name == "_worker_loop_dual_camera":
        source = ast.unparse(_function_node(worker_name))
        assert "actual_size = (int(frame.shape[1]), int(frame.shape[0]))" in source
        assert "actual_size2 = (int(frame2.shape[1]), int(frame2.shape[0]))" in source


@pytest.mark.parametrize(
    ("worker_name", "expected_args"),
    [
        ("_worker_loop", [("w", "h", "state.rotate")]),
        (
            "_worker_loop_dual_camera",
            [("w", "h", "state.rotate"), ("w2", "h2", "state.rotate2")],
        ),
        ("_worker_loop_parallel_camera", [("w", "h", "state.rotate")]),
    ],
)
def test_camera_writer_sizes_follow_rotation_before_session_start(worker_name, expected_args):
    worker = _function_node(worker_name)
    size_calls = _named_calls(worker, "_rotated_size")
    actual_args = sorted(tuple(ast.unparse(arg) for arg in call.args) for call in size_calls)
    begin_calls = _named_calls(worker, "begin_session")

    assert actual_args == sorted(expected_args)
    assert begin_calls
    nested_size_calls = {
        id(call)
        for begin_call in begin_calls
        for call in _named_calls(begin_call, "_rotated_size")
    }
    standalone_size_calls = [
        call for call in size_calls if id(call) not in nested_size_calls
    ]
    assert not standalone_size_calls or max(
        call.lineno for call in standalone_size_calls
    ) < min(call.lineno for call in begin_calls)
