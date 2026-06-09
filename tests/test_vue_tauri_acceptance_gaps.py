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
        "modelsDir",
        "sizeMb",
        "path",
        "设置",
    ):
        assert required in source


def test_vue_frontend_exposes_record_directory_picker_and_default_semantics():
    source = _frontend_source_text()

    assert "选择目录" in source
    assert "selectRecordDir" in source or "pickRecordDir" in source
    assert "outputsDir" in source or "defaultRecordDir" in source


def test_vue_frontend_filters_foreign_events_and_keeps_full_raw_json():
    source = _frontend_source_text()

    assert "event.sessionId" in source
    assert "event.jobId" in source
    assert "isCurrentBridgeEnvelope" in source or "shouldApplyBridgeEvent" in source
    assert "JSON.stringify(event, null, 2)" in source or "setRawJson(event)" in source
    assert "JSON.stringify(response, null, 2)" in source or "setRawJson(response)" in source


def test_verify_desktop_invokes_frontend_interaction_tests():
    root_package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    frontend_package = json.loads((ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
    verify_script = (ROOT / "scripts" / "verify-desktop-stack.ps1").read_text(encoding="utf-8")

    assert "test" in frontend_package["scripts"]
    assert "npm --prefix frontend run test" in verify_script
    assert "verify:desktop" in root_package["scripts"]
