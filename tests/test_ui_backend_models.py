from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apps import ui_backend  # noqa: E402
from core import model_manager  # noqa: E402


def _install_model_service(service: ui_backend.ModelManagementService):
    previous = ui_backend.DEFAULT_MODEL_SERVICE
    ui_backend.DEFAULT_MODEL_SERVICE = service
    return previous


def _spec(key: str, filename: str, label: str):
    return SimpleNamespace(
        key=key,
        filename=filename,
        label=label,
        approx_mb=1.5,
        url=f"https://example.test/{filename}",
    )


def test_model_status_returns_active_missing_and_path_payload(tmp_path: Path) -> None:
    specs = (
        _spec("pose_full", "pose.task", "Pose Full"),
        _spec("hand", "hand.task", "Hand"),
    )
    installed = {"pose_full"}
    service = ui_backend.ModelManagementService(
        specs=specs,
        models_dir_func=lambda: tmp_path,
        is_installed_func=lambda spec: spec.key in installed,
        installed_size_func=lambda spec: 9.0 if spec.key in installed else None,
        model_path_func=lambda spec: tmp_path / spec.filename,
    )
    previous = _install_model_service(service)
    try:
        response = ui_backend.handle_command(
            ui_backend.CommandRequest(
                command="model.status",
                request_id="req-model-status",
                payload={"poseVariant": "full", "enableHands": True},
            )
        )

        assert response["ok"] is True
        payload = response["payload"]
        assert payload["modelsDir"] == str(tmp_path)
        assert payload["activeKeys"] == ["hand", "pose_full"]
        assert payload["missingKeys"] == ["hand"]
        assert payload["models"][0]["installed"] is True
        assert payload["models"][1]["installed"] is False
    finally:
        ui_backend.DEFAULT_MODEL_SERVICE = previous


def test_model_download_command_emits_progress_and_completed_path(tmp_path: Path) -> None:
    events: list[dict] = []
    manager = ui_backend.BridgeJobManager(events.append)
    specs = (_spec("pose_full", "pose.task", "Pose Full"),)

    def fake_download(spec, *, progress_cb, should_stop):
        progress_cb(0, 100)
        assert should_stop() is False
        progress_cb(100, 100)
        return tmp_path / spec.filename

    service = ui_backend.ModelManagementService(
        job_manager=manager,
        specs=specs,
        models_dir_func=lambda: tmp_path,
        is_installed_func=lambda spec: False,
        installed_size_func=lambda spec: None,
        model_path_func=lambda spec: tmp_path / spec.filename,
        download_func=fake_download,
    )
    previous = _install_model_service(service)
    try:
        response = ui_backend.handle_command(
            ui_backend.CommandRequest(
                command="model.download",
                request_id="req-model-download",
                payload={"modelKey": "pose_full"},
            )
        )
        assert response["ok"] is True

        final = manager.wait(response["jobId"], 2.0)

        assert final is not None
        assert final.status == "succeeded"
        assert final.result["state"] == "completed"
        assert final.result["completed"] == [{"key": "pose_full", "path": str(tmp_path / "pose.task")}]
        progress = [event for event in events if event["event"] == "model.progress"]
        assert progress[-1]["payload"]["percent"] == 100.0
    finally:
        ui_backend.DEFAULT_MODEL_SERVICE = previous


def test_model_download_all_missing_skips_installed_models(tmp_path: Path) -> None:
    events: list[dict] = []
    manager = ui_backend.BridgeJobManager(events.append)
    specs = (
        _spec("pose_full", "pose.task", "Pose Full"),
        _spec("hand", "hand.task", "Hand"),
    )
    downloaded: list[str] = []

    def fake_download(spec, *, progress_cb, should_stop):
        downloaded.append(spec.key)
        return tmp_path / spec.filename

    service = ui_backend.ModelManagementService(
        job_manager=manager,
        specs=specs,
        models_dir_func=lambda: tmp_path,
        is_installed_func=lambda spec: spec.key == "pose_full",
        installed_size_func=lambda spec: 9.0 if spec.key == "pose_full" else None,
        model_path_func=lambda spec: tmp_path / spec.filename,
        download_func=fake_download,
    )
    previous = _install_model_service(service)
    try:
        response = ui_backend.handle_command(
            ui_backend.CommandRequest(
                command="model.download",
                request_id="req-missing",
                payload={"allMissing": True},
            )
        )
        final = manager.wait(response["jobId"], 2.0)

        assert final is not None
        assert final.status == "succeeded"
        assert downloaded == ["hand"]
    finally:
        ui_backend.DEFAULT_MODEL_SERVICE = previous


def test_model_download_reports_failed_state_on_download_exception(tmp_path: Path) -> None:
    events: list[dict] = []
    manager = ui_backend.BridgeJobManager(events.append)
    specs = (_spec("pose_full", "pose.task", "Pose Full"),)

    def fake_download(spec, *, progress_cb, should_stop):
        raise RuntimeError("network unavailable")

    service = ui_backend.ModelManagementService(
        job_manager=manager,
        specs=specs,
        models_dir_func=lambda: tmp_path,
        is_installed_func=lambda spec: False,
        installed_size_func=lambda spec: None,
        model_path_func=lambda spec: tmp_path / spec.filename,
        download_func=fake_download,
    )
    previous = _install_model_service(service)
    try:
        response = ui_backend.handle_command(
            ui_backend.CommandRequest(
                command="model.download",
                request_id="req-model-download-failed",
                payload={"modelKey": "pose_full"},
            )
        )
        assert response["ok"] is True

        final = manager.wait(response["jobId"], 2.0)

        assert final is not None
        assert final.status == "succeeded"
        assert final.result["state"] == "failed"
        assert final.result["completed"] == []
        assert final.result["failed"] == [
            {"key": "pose_full", "error": "network unavailable", "interrupted": False}
        ]
        status_events = [event for event in events if event["event"] == "model.status"]
        assert status_events[-1]["payload"]["state"] == "failed"
    finally:
        ui_backend.DEFAULT_MODEL_SERVICE = previous


def test_download_model_interruption_removes_part_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    spec = model_manager.ModelSpec(
        key="fake",
        filename="fake.task",
        url="https://example.test/fake.task",
        label="Fake",
    )
    monkeypatch.setattr(model_manager, "models_dir", lambda: tmp_path)

    class FakeResponse:
        headers = {"Content-Length": "10"}

        def __init__(self) -> None:
            self.read_calls = 0

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self, chunk_size: int) -> bytes:
            self.read_calls += 1
            return b"12345" if self.read_calls == 1 else b""

    monkeypatch.setattr(model_manager.urllib.request, "urlopen", lambda req, timeout: FakeResponse())
    progress_calls = 0

    def progress(downloaded: int, total: int | None) -> None:
        nonlocal progress_calls
        progress_calls += 1

    def should_stop() -> bool:
        return progress_calls >= 2

    with pytest.raises(InterruptedError):
        model_manager.download_model(spec, progress_cb=progress, should_stop=should_stop)

    assert not (tmp_path / "fake.task.part").exists()
    assert not (tmp_path / "fake.task").exists()
