"""规则边界、证据门、历史生命周期与真实Tk入口的针对性回归。"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import threading
import time

import cv2
import numpy as np
import pytest

from core import action_feedback as af
from core import feedback_geometry as fg
from core.feedback_history import FeedbackHistory, validate_identity


def pose_series(n=32):
    lm = np.zeros((n, 33, 4), dtype=np.float32)
    lm[:, :, 3] = 1
    points = {0:(.5,.15), 9:(.47,.2), 10:(.53,.2), 11:(.4,.3), 12:(.6,.3),
              13:(.4,.45), 14:(.6,.45), 15:(.55,.45), 16:(.75,.45),
              23:(.43,.6), 24:(.57,.6), 25:(.4,.78), 26:(.6,.78),
              27:(.35,.96), 28:(.65,.96), 29:(.38,.98), 30:(.68,.98),
              31:(.3,.96), 32:(.6,.96)}
    for index, xy in points.items():
        lm[:, index, :2] = xy
    return {"landmarks": lm, "valid_mask": np.ones((n,33), bool),
            "frames": list(range(n)), "times": [i/12 for i in range(n)]}


def result(action="front_straight", stance="left"):
    return fg.evaluate_series(action, stance, {"front": pose_series()})


def fake_analyzer(action, stance, front, side, **kwargs):
    return result(action, stance)


def video(path: Path):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 8, (96, 96))
    assert writer.isOpened()
    for i in range(16):
        writer.write(np.full((96, 96, 3), i * 10, dtype=np.uint8))
    writer.release()
    return path


@pytest.mark.parametrize("action", list(af.ACTIONS))
def test_catalog_covers_phases_sides_sources_and_no_scores(action):
    checks = af.build_checks(action, "left")
    assert len({c["id"] for c in checks}) == len(checks)
    assert checks[0]["phase"] == "start" and checks[-1]["phase"] == "end"
    assert all(c["source"] and c["standard"] and c["bodyPart"] for c in checks)
    assert all("score" not in c and "penalty" not in c for c in checks)
    right = af.build_checks(action, "right")
    assert next(c for c in checks if c["code"] == "stance_elbow")["bodyPart"].endswith("（左）")
    assert next(c for c in right if c["code"] == "stance_elbow")["bodyPart"].endswith("（右）")
    if action.endswith("combo"):
        segments = list(dict.fromkeys(c["segment"] for c in checks if c["phase"] in {"motion", "finish"}))
        assert segments[0].startswith("front_") and segments[1].startswith("rear_")


def test_rules_use_selected_front_arm_and_keep_uncalibrated_checks_pending():
    series = pose_series()
    series["landmarks"][:, 15, :2] = (.4, .6)  # 左肘180度；右肘90度。
    left = fg.evaluate_series("stance", "left", {"front": series})
    right = fg.evaluate_series("stance", "right", {"front": series})
    get = lambda data, code: next(c for c in data["checks"] if c["code"] == code)
    assert get(left, "stance_elbow")["status"] == "candidate"
    assert get(right, "stance_elbow")["status"] == "not_observed"
    assert get(left, "stance_height")["status"] == "pending_rule"
    assert get(left, "stance_width")["status"] == "pending_rule"
    assert left["backend"] == "mediapipe" and left["delegate"] == "cpu"
    assert not left["scoreAuthorized"]


def test_missing_landmarks_or_view_or_motion_are_not_a_pass():
    series = pose_series()
    series["valid_mask"][:] = False
    data = fg.evaluate_series("front_straight", "left", {"front": series})
    assert data["needsRerecord"]
    assert all(c["status"] in {"unable", "pending_rule"} for c in data["checks"])
    data = result()
    assert all(c["status"] in {"unable", "pending_rule"} for c in data["checks"] if c["phase"] == "motion")


def test_movement_windows_require_return_and_keep_front_rear_order():
    series = pose_series(40)
    # 每只手一次明确离开并回收：起峰后回到初始护位。
    for start, wrist in ((7,15),(23,16)):
        series["landmarks"][start:start+7, wrist, 0] += np.array([.10,.16,.22,.28,.22,.16,.10])
    windows = fg.phase_windows(series, "straight_combo", "left", fg.FeedbackConfig())
    assert windows[("front_straight","finish")][1] == 10
    assert windows[("rear_straight","finish")][1] == 26
    assert fg.phase_windows(series, "straight_combo", "right", fg.FeedbackConfig()).keys() == {("stance","start"),("stance","end")}
    series["valid_mask"][10,15] = False  # 不能跨遮挡拼成完整动作。
    assert ("front_straight","motion") not in fg.phase_windows(series,"straight_combo","left",fg.FeedbackConfig())


def test_actual_video_sampling_uses_pipeline_and_does_not_repeat_lost_pose(tmp_path):
    from types import SimpleNamespace
    path = video(tmp_path / "front.avi")
    calls = []
    closed = []

    class Pipeline:
        def infer(self, frame, *, timestamp_ms):
            calls.append(timestamp_ms)
            if len(calls) == 2:
                return None, []
            return [SimpleNamespace(x=.5,y=.5,z=0,visibility=1) for _ in range(33)], []
        def close(self):
            closed.append(True)

    data = fg.extract_series(path, fg.FeedbackConfig(), lambda: False, Pipeline)
    assert data["frames"][0] == 0 and data["frames"][-1] == 15
    assert data["valid_mask"][0].all() and not data["valid_mask"][1].any()
    assert calls == sorted(set(calls)) and closed == [True]
    with pytest.raises(InterruptedError):
        af.analyze_feedback("stance", "left", path, None, stopped=lambda: True, pipeline_factory=Pipeline)


def test_feedback_pipeline_is_lite_cpu_without_hands(monkeypatch, tmp_path):
    (tmp_path / "pose_landmarker_lite.task").write_bytes(b"fixture")
    monkeypatch.setattr(fg, "models_dir", lambda: tmp_path)
    captured = []
    monkeypatch.setattr(fg, "MediaPipePipeline", lambda **kw: captured.append(kw))
    fg._pipeline()
    config = captured[0]["cfg"]
    assert config.pose_variant == "lite" and config.delegate == "cpu" and not config.enable_hands


def test_completed_hip_turn_and_arm_swing_are_not_missing_actions():
    series = pose_series(32)
    series["landmarks"][7:14, 27, 0] += np.array([.10,.16,.22,.28,.22,.16,.10])
    series["landmarks"][10, 15, 1] += .2  # 高峰处已甩手
    series["landmarks"][10, 24, 2] += .1  # 高峰处已翻胯
    data = fg.evaluate_series("front_low_kick", "left", {"front": series})
    checked = [c for c in data["checks"] if c["code"] in {"hip_turn", "arm_swing"}]
    assert checked and all(c["status"] == "not_observed" for c in checked)


def test_personal_history_review_export_reanalysis_and_retention(tmp_path):
    now = [datetime(2026, 9, 18, tzinfo=timezone.utc)]
    store = FeedbackHistory(tmp_path / "history", clock=lambda: now[0])
    source = tmp_path / "source.avi"
    source.write_bytes(b"mock video, inference is injected")
    identity = validate_identity("001", "张同学", "front_straight", "left")
    saved = store.add(identity, source, None, analyzer=fake_analyzer)
    assert store.list("002") == [] and len(store.list("001")) == 1
    issue = next(c for c in saved["result"]["checks"] if c["status"] == "candidate")
    changed = store.review(saved["id"], issue["id"], "confirmed", "李老师", "已核对")
    assert changed["result"]["reviewHistory"][-1]["before"] == "pending"
    out = store.export(saved["id"], tmp_path / "报告.txt")
    assert "教师已确认" in out.read_text(encoding="utf-8-sig")
    store.review(saved["id"], issue["id"], "revoked", "李老师", "误报")
    assert "教师已确认" not in af.format_report(store.get(saved["id"]))
    now[0] += timedelta(days=1)
    updated = store.reanalyze(saved["id"], analyzer=fake_analyzer)
    assert updated["expiresAt"] == saved["expiresAt"]
    assert len(updated["previousResults"]) == 1
    assert all(c["review"] == "pending" for c in updated["result"]["checks"])
    now[0] += timedelta(days=13)
    assert store.list("001") == []
    assert source.is_file() and not (store.root / saved["id"]).exists()


def test_cancel_failure_and_invalid_path_never_publish_history(tmp_path):
    store = FeedbackHistory(tmp_path / "history")
    source = tmp_path / "source.mp4"
    source.write_bytes(b"mock")
    identity = validate_identity("001", "", "stance", "right")
    with pytest.raises(InterruptedError):
        store.add(identity, source, None, stopped=lambda: True)
    assert store.list("001") == [] and list(store.root.iterdir()) == []
    with pytest.raises(ValueError):
        store.get("../source")
    with pytest.raises(ValueError):
        validate_identity("../other", "", "stance", "left")
    saved = store.add(identity, source, None, analyzer=fake_analyzer)
    with pytest.raises(ValueError):
        store.export(saved["id"], store.root / "report.txt")
    (store.root / saved["id"] / saved["videos"]["front"]).unlink()
    with pytest.raises(ValueError, match="原视频"):
        store.reanalyze(saved["id"], analyzer=fake_analyzer)


def test_real_tk_panel_background_analysis_history_and_identity_switch(tmp_path):
    import tkinter as tk
    from apps.feedback_panel import FeedbackControls

    root = tk.Tk()
    root.withdraw()
    messages, statuses = [], []
    busy = []
    controls = FeedbackControls(root, root=root, set_busy=busy.append, show_result=messages.append,
                                set_status=statuses.append, can_analyze=lambda: True)
    controls.store = FeedbackHistory(tmp_path / "history")
    controls.student_id.set("001")
    source = tmp_path / "source.mp4"
    source.write_bytes(b"mock")
    identity = controls.identity()
    try:
        controls._start(lambda: controls.store.add(identity, source, None, analyzer=fake_analyzer))
        deadline = time.monotonic() + 5
        while controls.busy and time.monotonic() < deadline:
            root.update()
            time.sleep(.01)
        assert not controls.busy and busy == [True, False]
        assert messages and "动作问题说明" in messages[-1]
        controls.open_history()
        root.update()
        assert len(controls.history_tree.get_children()) == 1
        controls.history_tree.selection_set(controls.current["id"])
        root.update()
        assert controls.check_tree.get_children()
        controls.student_id.set("002")
        assert controls.current is None and str(controls.export_button.cget("state")) == "disabled"
    finally:
        controls.close()
        root.destroy()


def test_late_cancel_does_not_write_or_replace_result(tmp_path):
    store = FeedbackHistory(tmp_path / "history")
    source = tmp_path / "source.mp4"
    source.write_bytes(b"mock")
    identity = validate_identity("001", "", "stance", "left")
    stop = threading.Event()

    def cancel_after_inference(*args, **kwargs):
        stop.set()
        return fake_analyzer(*args, **kwargs)

    with pytest.raises(InterruptedError):
        store.add(identity, source, None, analyzer=cancel_after_inference, stopped=stop.is_set)
    assert store.list("001") == []
    stop.clear()
    saved = store.add(identity, source, None, analyzer=fake_analyzer)
    with pytest.raises(InterruptedError):
        store.reanalyze(saved["id"], analyzer=cancel_after_inference, stopped=stop.is_set)
    assert store.get(saved["id"])["revision"] == 1


@pytest.mark.parametrize("waiting", [False, True])
def test_app_judges_identity_bound_at_recording_start(waiting):
    from types import SimpleNamespace
    from apps.app_ui import App

    captured = []
    identity = validate_identity("recorded_student", "", "rear_low_kick", "right")
    app = SimpleNamespace(_student_practice_active=True, _student_judging=False, _student_segment_ready=True,
        _student_pending_record=waiting,
        _rec=SimpleNamespace(state="idle"), _student_feedback_identity=identity, _student_feedback_record_id=None,
        _student_front_video=Path("front.mp4"), _student_side_video=Path("side.mp4"),
        feedback_controls=SimpleNamespace(analyze_recording=lambda *args, **kw: captured.append((args, kw))))
    App._student_judge(app)
    if waiting:
        assert captured == []
        return
    assert captured[0][0][0] == identity
    captured[0][1]["on_saved"]({"id": "saved_id"})
    assert app._student_feedback_record_id == "saved_id"


def test_corrupt_record_is_reported_without_deleting_unmanaged_files(tmp_path):
    store = FeedbackHistory(tmp_path / "history")
    folder = store.root / ("a" * 32)
    folder.mkdir()
    (folder / "record.json").write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="格式损坏"):
        store.list("001")
    assert (folder / "record.json").is_file()
