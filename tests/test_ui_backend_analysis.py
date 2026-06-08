from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apps import ui_backend  # noqa: E402


def _install_analysis_service(service: ui_backend.TemplateAnalysisService):
    previous = ui_backend.DEFAULT_ANALYSIS_SERVICE
    ui_backend.DEFAULT_ANALYSIS_SERVICE = service
    return previous


def _write_template(path: Path) -> None:
    meta = {
        "pose_variant": "full",
        "feature_layout": "pose33_v3",
        "start_frame": 1,
        "end_frame": 3,
    }
    np.savez_compressed(
        path,
        features=np.zeros((3, 22, 2), dtype=np.float32),
        meta=np.array(meta, dtype=object),
    )


def test_template_create_command_runs_as_job_and_returns_template_meta(tmp_path: Path) -> None:
    events: list[dict] = []
    manager = ui_backend.BridgeJobManager(events.append)
    out_path = tmp_path / "generated_template.npz"

    def fake_create(video_path, **kwargs):
        assert video_path == "base.mp4"
        assert kwargs["pose_variant"] == "heavy"
        assert kwargs["start"] == 2
        assert kwargs["end"] == 8
        assert kwargs["workers"] >= 1
        kwargs["progress_cb"]("提取骨架特征", 1, 2)
        _write_template(out_path)
        return out_path

    service = ui_backend.TemplateAnalysisService(
        job_manager=manager,
        create_template=fake_create,
    )
    previous = _install_analysis_service(service)
    try:
        response = ui_backend.handle_command(
            ui_backend.CommandRequest(
                command="template.create",
                request_id="req-template",
                payload={
                    "baseVideo": "base.mp4",
                    "poseVariant": "heavy",
                    "startFrame": 2,
                    "endFrame": 8,
                    "outPath": str(out_path),
                    "workers": 2,
                },
            )
        )
        assert response["ok"] is True

        final = manager.wait(response["jobId"], 2.0)

        assert final is not None
        assert final.status == "succeeded"
        assert final.result["templatePath"] == str(out_path)
        assert final.result["templateMeta"]["feature_layout"] == "pose33_v3"
        assert any(event["event"] == "template.progress" for event in events)
        assert any(event["event"] == "template.status" for event in events)
    finally:
        ui_backend.DEFAULT_ANALYSIS_SERVICE = previous


def test_analysis_run_command_returns_template_compare_payload(tmp_path: Path) -> None:
    events: list[dict] = []
    manager = ui_backend.BridgeJobManager(events.append)
    template_path = tmp_path / "template.npz"
    _write_template(template_path)
    preview_path = tmp_path / "preview.avi"

    def fake_compare(template, video, **kwargs):
        assert str(template) == str(template_path)
        assert video == "student.mp4"
        assert kwargs["pose_variant"] == "full"
        assert kwargs["preview_out"] == str(preview_path)
        kwargs["progress_cb"]("计算相似度", 1, 1)
        return SimpleNamespace(
            template_path=Path(template),
            video_path=Path(video),
            pose_variant="full",
            fps=30.0,
            start_frame=10,
            end_frame=20,
            cost=5.0,
            avg_cost=0.5,
            score=0.8,
            preview_path=preview_path,
            workers_used=1,
        )

    service = ui_backend.TemplateAnalysisService(
        job_manager=manager,
        compare_template=fake_compare,
    )
    previous = _install_analysis_service(service)
    try:
        response = ui_backend.handle_command(
            ui_backend.CommandRequest(
                command="analysis.run",
                request_id="req-analysis",
                payload={
                    "videoPath": "student.mp4",
                    "templatePath": str(template_path),
                    "poseVariant": "full",
                    "workers": 4,
                    "previewOut": str(preview_path),
                },
            )
        )
        assert response["ok"] is True

        final = manager.wait(response["jobId"], 2.0)

        assert final is not None
        assert final.status == "succeeded"
        compare = final.result["compare"]
        assert compare["score"] == 0.8
        assert compare["startFrame"] == 10
        assert compare["endFrame"] == 20
        assert compare["previewPath"] == str(preview_path)
        assert compare["templateMeta"]["feature_layout"] == "pose33_v3"
        assert "帧 10..20" in compare["matchText"]
        assert any(event["event"] == "analysis.progress" for event in events)
    finally:
        ui_backend.DEFAULT_ANALYSIS_SERVICE = previous


def test_analysis_run_requires_template_when_compare_enabled() -> None:
    response = ui_backend.handle_command(
        ui_backend.CommandRequest(
            command="analysis.run",
            request_id="req-bad-analysis",
            payload={"videoPath": "student.mp4", "doCompare": True},
        )
    )

    assert response["ok"] is False
    assert response["error"]["code"] == "bad_request"
    assert "templatePath" in response["error"]["message"]


def test_analysis_run_can_return_tech_eval_payload_and_debug_video(tmp_path: Path) -> None:
    events: list[dict] = []
    manager = ui_backend.BridgeJobManager(events.append)
    debug_out = tmp_path / "debug.mp4"
    actual_debug = tmp_path / "debug.actual.mp4"

    failed = SimpleNamespace(
        status="不合格",
        reason="发力顺序：蹬地动作检测率偏低",
        detail={"primary_cause": "蹬地检测率低", "failed_stage": "push_off"},
        required_landmarks=("left_heel", "right_heel"),
        missing_landmarks=("left_heel",),
        backend="mediapipe",
    )
    ok = SimpleNamespace(
        status="合格",
        reason="达标",
        detail={"primary_cause": "达标"},
        required_landmarks=("left_wrist",),
        missing_landmarks=(),
        backend="mediapipe",
    )
    result = SimpleNamespace(
        video_path="student.mp4",
        pose_variant="heavy",
        fps=30.0,
        view_mode="mixed",
        front_segment=(0, 10),
        side_segment=(11, 20),
        cog_final=ok,
        cog_side=ok,
        cog_front=ok,
        cog_com=None,
        retract_speed=ok,
        force_sequence=failed,
        wrist_angle=ok,
    )

    def fake_assets(video, **kwargs):
        assert str(video) == "student.mp4"
        assert kwargs["pose_variant"] == "heavy"
        assert kwargs["stance"] == "right"
        assert kwargs["view_hint"] == "auto"
        return result, object(), object(), {"fps": 30.0}

    def fake_export(video, out_path, **kwargs):
        assert Path(out_path) == debug_out
        assert kwargs["res"] is result
        return actual_debug

    service = ui_backend.TemplateAnalysisService(
        job_manager=manager,
        evaluate_assets=fake_assets,
        export_debug=fake_export,
    )
    previous = _install_analysis_service(service)
    try:
        response = ui_backend.handle_command(
            ui_backend.CommandRequest(
                command="analysis.run",
                request_id="req-tech",
                payload={
                    "videoPath": "student.mp4",
                    "doCompare": False,
                    "doTechEval": True,
                    "poseVariant": "heavy",
                    "stance": "right",
                    "viewHint": "auto",
                    "debugVideo": True,
                    "debugOutPath": str(debug_out),
                },
            )
        )
        assert response["ok"] is True

        final = manager.wait(response["jobId"], 2.0)

        assert final is not None
        assert final.status == "succeeded"
        assert "compare" not in final.result
        tech = final.result["techEval"]
        assert tech["debugVideo"] == str(actual_debug)
        assert tech["forceSequence"]["primaryCause"] == "蹬地检测率低"
        assert tech["forceSequence"]["failedStage"] == "push_off"
        assert tech["forceSequence"]["missingLandmarks"] == ["left_heel"]
        assert tech["indicators"]["wristAngle"]["status"] == "合格"
        assert any(event["event"] == "analysis.progress" for event in events)
    finally:
        ui_backend.DEFAULT_ANALYSIS_SERVICE = previous
