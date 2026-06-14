from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND_SRC = ROOT / "frontend" / "src"


def _frontend_source_text() -> str:
    parts: list[str] = []
    for path in sorted(FRONTEND_SRC.rglob("*")):
        if path.suffix in {".ts", ".vue"}:
            parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def _frontend_smoke_text() -> str:
    return (ROOT / "frontend" / "scripts" / "frontend-smoke.mjs").read_text(encoding="utf-8")


def test_vue_frontend_exposes_analysis_and_tech_eval_commands():
    source = _frontend_source_text()

    for required in (
        "template.create",
        "analysis.run",
        "templatePath",
        "baseVideo",
        "targetVideo",
        "startFrame",
        "endFrame",
        "previewOut",
        "techEval",
        "stance",
        "viewHint",
        "debugVideo",
    ):
        assert required in source


def test_vue_frontend_exposes_settings_model_download_flow():
    source = _frontend_source_text()

    for required in (
        "model.download",
        "model.progress",
        "downloadAllMissing",
        "cancelModelDownload",
        "stopActiveJobsBeforeUnmount",
        "stopJobById",
        "重新下载",
        "modelsDir",
        "sizeMb",
        "path",
        "设置",
    ):
        assert required in source


def test_vue_frontend_exposes_record_directory_picker_and_default_semantics():
    source = _frontend_source_text()

    assert "选择…" in source
    assert "selectRecordDir" in source or "pickRecordDir" in source
    assert "outputsDir" in source or "defaultRecordDir" in source


def test_vue_frontend_filters_foreign_events_and_keeps_full_raw_json():
    source = _frontend_source_text()
    smoke = _frontend_smoke_text()

    assert "event.sessionId" in source
    assert "event.jobId" in source
    assert "jobId?: string | null" in source
    assert "sessionId?: string | null" in source
    assert "isCurrentBridgeEnvelope" in source or "shouldApplyBridgeEvent" in source
    assert "isBridgeEventForCurrentState" in source
    assert "analysis.status" in smoke
    assert "template.status" in smoke
    assert "model.status" in smoke
    assert "JSON.stringify(event, null, 2)" in source or "setRawJson(event)" in source
    assert "JSON.stringify(response, null, 2)" in source or "setRawJson(response)" in source


def test_frontend_smoke_exercises_behavior_not_only_static_markers():
    smoke = _frontend_smoke_text()

    for required in (
        "assertTemplateBinding",
        "isBridgeEventForCurrentState",
        "progressTextForSessionStatus",
        "progressTextForFrameProgress",
        "modelDownloadStatusFromJobEvent",
        "sessionStatusFromJobEvent",
        "shouldApplyModelDownloadStartResponse",
        "shouldApplySessionStartResponse",
        "bridgeCommandFailureResponse",
        "sessionStartFailureState",
        "foreign analysis.status must be ignored",
        "missing-id job.completed must be ignored",
        "null-id job.completed must be ignored",
        "current session job.failed must be accepted",
        "foreign session job.failed must be ignored",
        "current session job.failed must map to failed terminal status",
        "early session job.failed must prevent late session.start response from marking running",
        "early model download failure must keep failed status after late start response",
        "early model download stop must keep stopped status after late start response",
        "invoke failure must become an ok=false bridge envelope",
        "failed session.start must clear pending session id",
        "same-session newer latest-frame identity must be accepted",
        "same-session older drawn frame identity must not roll back",
        "preassigned current analysis.status must be accepted before response",
        "failed model download must be shown as failed",
        "job.failed model download must be shown as failed",
        "active model download unmount helper must stop exact job payload",
        "empty model download job id must not call bridge",
        "installed models must remain downloadable for redownload",
        "active analysis unmount helper must stop exact job payload",
        "raw JSON must keep jobId",
    ):
        assert required in smoke


def test_frontend_preview_uses_canvas_bitmap_without_reactive_frame_strings():
    source = _frontend_source_text()
    smoke = _frontend_smoke_text()

    assert "previewCanvas" in source
    assert "<canvas" in source
    assert "requestAnimationFrame" in source
    assert "createImageBitmap" in source
    assert "drawImage" in source
    assert "fetchLatestFrameBytes(frame.payload)" in source
    assert "previewImage" not in source
    assert "payload.image" not in source
    assert "URL.createObjectURL" not in source
    assert "<img" not in source
    assert "preview frames must not be stored in a reactive image string" in smoke


def test_verify_desktop_invokes_frontend_interaction_tests():
    root_package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    frontend_package = json.loads((ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
    verify_script = (ROOT / "scripts" / "verify-desktop-stack.ps1").read_text(encoding="utf-8")

    assert "test" in frontend_package["scripts"]
    assert "npm --prefix frontend run test" in verify_script
    assert "verify:desktop" in root_package["scripts"]
