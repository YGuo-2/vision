# -*- coding: utf-8 -*-
"""Tkinter 双摄骨架测试（issue #59 裁剪版）。

不创建真实 Tk root，只验证 source2 收敛点和双 VIDEO pipeline 结构。
"""
from __future__ import annotations

import ast
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

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
    record_skeleton: bool = False,
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
    app.record_skeleton_var = _Var(record_skeleton)
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


def _app_method_node(name: str) -> ast.FunctionDef:
    tree = ast.parse(Path(app_ui.__file__).read_text(encoding="utf-8"))
    app_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "App"
    )
    return next(
        node
        for node in app_class.body
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


def test_collect_state_captures_dual_record_skeleton_choice():
    app = _app_stub(
        source="0",
        second_label="摄像头 1",
        record_skeleton=True,
    )

    state = app_ui.App._collect_state(app)

    assert state.record_skeleton is True


def test_app_initializes_dual_record_skeleton_toggle_disabled():
    init = _app_method_node("__init__")
    assignments = [
        node
        for node in ast.walk(init)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Attribute)
            and target.attr == "record_skeleton_var"
            for target in node.targets
        )
    ]

    assert len(assignments) == 1
    value = assignments[0].value
    assert isinstance(value, ast.Call)
    assert any(
        keyword.arg == "value"
        and isinstance(keyword.value, ast.Constant)
        and keyword.value.value is False
        for keyword in value.keywords
    )


def test_collect_state_ignores_record_skeleton_for_single_camera():
    app = _app_stub(
        source="0",
        second_label=app_ui.NO_SECOND_CAMERA,
        record_skeleton=True,
    )

    state = app_ui.App._collect_state(app)

    assert state.record_skeleton is False


def test_collect_state_leaves_source2_none_for_single_camera_mode():
    app = _app_stub(source="0", second_label=app_ui.NO_SECOND_CAMERA)

    state = app_ui.App._collect_state(app)

    assert state.source2 is None


def test_collect_state_ignores_second_camera_for_video_file_source():
    app = _app_stub(
        source="input.mp4",
        second_label="摄像头 1",
        record_skeleton=True,
    )

    state = app_ui.App._collect_state(app)

    assert state.source == "input.mp4"
    assert state.source2 is None
    assert state.record_skeleton is False


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


def test_dual_recording_frame_selector_defaults_to_raw_frames():
    frame = np.zeros((2, 3, 3), dtype=np.uint8)
    frame2 = np.ones((2, 3, 3), dtype=np.uint8)
    annotated = np.full((2, 3, 3), 2, dtype=np.uint8)
    annotated2 = np.full((2, 3, 3), 3, dtype=np.uint8)

    selected = app_ui._select_dual_recording_frames(
        frame,
        frame2,
        annotated,
        annotated2,
        record_skeleton=False,
    )

    assert selected[0] is frame
    assert selected[1] is frame2


def test_dual_recording_frame_selector_can_write_annotated_frames():
    frame = np.zeros((2, 3, 3), dtype=np.uint8)
    frame2 = np.ones((2, 3, 3), dtype=np.uint8)
    annotated = np.full((2, 3, 3), 2, dtype=np.uint8)
    annotated2 = np.full((2, 3, 3), 3, dtype=np.uint8)

    selected = app_ui._select_dual_recording_frames(
        frame,
        frame2,
        annotated,
        annotated2,
        record_skeleton=True,
    )

    assert selected[0] is annotated
    assert selected[1] is annotated2


def test_dual_worker_writes_selected_frames_but_previews_annotated_frames():
    worker = _function_node("_worker_loop_dual_camera")
    select_calls = _named_calls(worker, "_select_dual_recording_frames")
    write_calls = _named_calls(worker, "_write_recording_pair")
    preview_calls = _named_calls(worker, "_post_frame")
    preview2_calls = _named_calls(worker, "_post_frame2")

    assert len(select_calls) == 1
    assert [ast.unparse(arg) for arg in select_calls[0].args] == [
        "frame",
        "frame2",
        "annotated",
        "annotated2",
    ]
    assert [ast.unparse(arg) for arg in write_calls[0].args] == [
        "record_frame",
        "record_frame2",
    ]
    assert ast.unparse(preview_calls[0].args[0]) == "annotated"
    assert ast.unparse(preview2_calls[0].args[0]) == "annotated2"


def test_dual_worker_finally_always_closes_recording_pair():
    worker = _function_node("_worker_loop_dual_camera")
    finally_calls = [
        call
        for node in ast.walk(worker)
        if isinstance(node, ast.Try)
        for statement in node.finalbody
        for call in _named_calls(statement, "_close_recording_pair")
    ]

    assert len(finally_calls) == 1


@pytest.mark.parametrize("failure_phase", ["annotate", "write"])
def test_dual_worker_releases_captures_and_pipelines_after_runtime_error(
    failure_phase, monkeypatch
):
    frame = np.zeros((4, 6, 3), dtype=np.uint8)

    class _Capture:
        def __init__(self) -> None:
            self.release_calls = 0

        def isOpened(self) -> bool:
            return True

        def get(self, prop) -> int:
            return 6 if prop == app_ui.cv2.CAP_PROP_FRAME_WIDTH else 4

        def read(self):
            return True, frame.copy()

        def release(self) -> None:
            self.release_calls += 1

    class _RecordingSession:
        def begin_session(self, **_kwargs) -> None:
            pass

        def update_session_size(self, **_kwargs) -> None:
            pass

    class _Pipeline:
        def __init__(self, *, fail_annotate: bool) -> None:
            self.fail_annotate = fail_annotate
            self.close_calls = 0

        def next_timestamp_ms(self, **_kwargs) -> int:
            return 1

        def annotate(self, current_frame, **_kwargs):
            if self.fail_annotate:
                raise RuntimeError("annotate failed")
            return current_frame.copy(), []

        def close(self) -> None:
            self.close_calls += 1

    front_cap = _Capture()
    side_cap = _Capture()
    pipelines: list[_Pipeline] = []

    def pipeline_factory(**_kwargs):
        pipeline = _Pipeline(
            fail_annotate=failure_phase == "annotate" and not pipelines
        )
        pipelines.append(pipeline)
        return pipeline

    close_pair_calls: list[bool] = []
    done_calls: list[bool] = []

    def write_pair(_front, _side) -> None:
        if failure_phase == "write":
            raise RuntimeError("write failed")

    app = SimpleNamespace(
        _record_pair_lock=threading.Lock(),
        _rec=_RecordingSession(),
        _rec2=_RecordingSession(),
        _stop_evt=threading.Event(),
        _post_dual_preview_layout=lambda _layout: None,
        _post_status=lambda _status: None,
        _post_progress=lambda _current, _total: None,
        _post_done=lambda: done_calls.append(True),
        _post_frame=lambda _frame, _actions: None,
        _post_frame2=lambda _frame, _actions: None,
        _write_recording_pair=write_pair,
        _close_recording_pair=lambda: close_pair_calls.append(True),
    )
    state = SimpleNamespace(
        source2="1",
        pose_variant="full",
        enable_hands=True,
        rotate=0,
        rotate2=0,
        record_skeleton=False,
    )
    monkeypatch.setattr(app_ui, "open_camera", lambda _index: side_cap)
    monkeypatch.setattr(app_ui, "models_dir", lambda: Path("models"))
    monkeypatch.setattr(app_ui, "MediaPipePipeline", pipeline_factory)
    monkeypatch.setattr(app_ui.cv2, "putText", lambda image, *_args, **_kwargs: image)
    monkeypatch.setattr(app_ui.cv2, "destroyAllWindows", lambda: None)

    with pytest.raises(RuntimeError, match=f"{failure_phase} failed"):
        app_ui.App._worker_loop_dual_camera(app, state, front_cap)

    assert front_cap.release_calls == 1
    assert side_cap.release_calls == 1
    assert len(pipelines) == 2
    assert [pipeline.close_calls for pipeline in pipelines] == [1, 1]
    assert close_pair_calls == [True]
    assert done_calls == [True]


def test_main_stop_does_not_cancel_background_compare_queue():
    stop = _app_method_node("_stop")

    assert _named_calls(stop, "cancel_all") == []


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
