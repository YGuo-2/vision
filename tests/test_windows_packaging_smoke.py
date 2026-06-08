from __future__ import annotations

import json
from pathlib import Path

from apps import ui_backend


ROOT = Path(__file__).resolve().parents[1]
TAURI_CONF = ROOT / "frontend" / "src-tauri" / "tauri.conf.json"
TAURI_LIB = ROOT / "frontend" / "src-tauri" / "src" / "lib.rs"
SIDECAR_SPEC = ROOT / "ui_backend_sidecar.spec"
SIDECAR_SCRIPT = ROOT / "scripts" / "build-tauri-sidecar.ps1"
SIDECAR_RUNTIME_HOOK = ROOT / "packaging" / "pyinstaller" / "pyi_rth_video_writer_alias.py"
RESOURCE_KEEP = ROOT / "frontend" / "src-tauri" / "resources" / ".gitkeep"


def test_tauri_windows_bundle_includes_sidecar_resources() -> None:
    config = json.loads(TAURI_CONF.read_text(encoding="utf-8"))

    assert config["build"]["beforeBuildCommand"] == "npm run build && npm run build:sidecar"
    assert config["bundle"]["active"] is True
    assert config["bundle"]["targets"] == ["nsis"]
    assert config["bundle"]["resources"] == {"resources/": ""}
    assert RESOURCE_KEEP.exists()


def test_rust_bridge_prefers_packaged_sidecar_and_keeps_dev_fallback() -> None:
    source = TAURI_LIB.read_text(encoding="utf-8")

    assert 'BRIDGE_SIDECAR_NAME: &str = "vision-ui-backend.exe"' in source
    assert "packaged_bridge_executable" in source
    assert "resource_dir" in source
    assert ".venv" in source
    assert "apps" in source and "ui_backend.py" in source
    assert "creation_flags(0x08000000)" in source


def test_sidecar_spec_targets_bridge_without_yolo_or_tkinter_entry() -> None:
    source = SIDECAR_SPEC.read_text(encoding="utf-8")

    assert '["apps/ui_backend.py"]' in source
    assert 'name="vision-ui-backend"' in source
    assert '"apps.app_ui"' not in source
    assert '"core.yolo_adapter"' in source
    assert '"ultralytics"' in source
    assert '"torch"' in source
    assert '"analysis.tech_eval"' in source
    assert '"core.model_manager"' in source
    assert '"apps.camera_enum"' in source
    assert "pyi_rth_video_writer_alias.py" in source


def test_sidecar_build_script_copies_exe_into_tauri_resources() -> None:
    source = SIDECAR_SCRIPT.read_text(encoding="utf-8")

    assert "ui_backend_sidecar.spec" in source
    assert "dist\\vision-ui-backend.exe" in source
    assert "frontend\\src-tauri\\resources" in source
    assert "Copy-Item" in source


def test_sidecar_runtime_hook_aliases_video_writer(monkeypatch) -> None:
    import runpy
    import sys

    monkeypatch.delitem(sys.modules, "video_writer", raising=False)
    runpy.run_path(str(SIDECAR_RUNTIME_HOOK))

    import core.video_writer as core_video_writer

    assert sys.modules["video_writer"].open_video_writer is core_video_writer.open_video_writer


def test_bridge_json_preserves_chinese_and_space_paths() -> None:
    path = r"E:\样本 数据\直拳 视频.mp4"
    message = ui_backend.make_response(
        "req-path",
        ok=True,
        payload={"path": path},
    )
    encoded = ui_backend.encode_message(message)
    decoded = json.loads(encoded)

    assert "样本 数据" in encoded
    assert decoded["payload"]["path"] == path
