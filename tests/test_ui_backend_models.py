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


def _yolo_spec(key: str, filename: str, label: str):
    return SimpleNamespace(
        key=key,
        filename=filename,
        label=label,
        approx_mb=None,
        url="",
        category="yolo",
        profile=key,
        downloadable=False,
        installed_supported=False,
        default_route_eligible=key != "yolo26x",
        note="当前安装版 sidecar 不打包 YOLO runtime",
    )


def _runtime_yolo_spec(key: str, filename: str, label: str):
    spec = _yolo_spec(key, filename, label)
    spec.installed_supported = True
    return spec


def _install_fake_url_opener(monkeypatch: pytest.MonkeyPatch, response) -> None:
    class FakeOpener:
        def open(self, req, timeout):
            return response

    monkeypatch.setattr(model_manager, "_url_opener", lambda *, proxy: FakeOpener())


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
        assert payload["models"][0]["license"]
        assert payload["models"][0]["purpose"]
        assert payload["models"][0]["proxy"]
        assert payload["models"][0]["offlineInstall"]
        assert payload["models"][0]["downloadHint"]
    finally:
        ui_backend.DEFAULT_MODEL_SERVICE = previous


def test_model_status_lists_yolo_profiles_without_marking_them_download_missing(tmp_path: Path) -> None:
    service = ui_backend.ModelManagementService(
        specs=(
            _spec("pose_full", "pose.task", "Pose Full"),
            _yolo_spec("yolo26n", "yolo26n-pose.pt", "YOLO26n"),
            _yolo_spec("yolo26l", "yolo26l-pose.pt", "YOLO26L"),
            _yolo_spec("yolo26x", "yolo26x-pose.pt", "YOLO26X"),
        ),
        models_dir_func=lambda: tmp_path,
        is_installed_func=lambda spec: False,
        installed_size_func=lambda spec: None,
        model_path_func=lambda spec: tmp_path / spec.filename,
    )
    previous = _install_model_service(service)
    try:
        response = ui_backend.handle_command(
            ui_backend.CommandRequest(
                command="model.status",
                request_id="req-yolo-model-status",
                payload={"poseVariant": "full", "enableHands": False},
            )
        )

        assert response["ok"] is True
        payload = response["payload"]
        by_key = {item["key"]: item for item in payload["models"]}
        assert payload["missingKeys"] == ["pose_full"]
        assert by_key["yolo26n"]["category"] == "yolo"
        assert by_key["yolo26n"]["downloadable"] is False
        assert by_key["yolo26l"]["installedSupported"] is False
        assert by_key["yolo26x"]["defaultRouteEligible"] is False
        assert payload["yoloRuntime"]["supported"] is False
        assert "YOLO runtime" in payload["yoloRuntime"]["message"]
        assert by_key["yolo26n"]["license"]
        assert by_key["yolo26n"]["proxy"]
        assert by_key["yolo26n"]["offlineInstall"]
    finally:
        ui_backend.DEFAULT_MODEL_SERVICE = previous


def test_model_status_keeps_installed_yolo_unroutable_when_runtime_not_packaged(tmp_path: Path) -> None:
    service = ui_backend.ModelManagementService(
        specs=(
            _spec("pose_full", "pose.task", "Pose Full"),
            _yolo_spec("yolo26n", "yolo26n-pose.pt", "YOLO26n"),
        ),
        models_dir_func=lambda: tmp_path,
        is_installed_func=lambda spec: spec.key == "yolo26n",
        installed_size_func=lambda spec: 6.0 if spec.key == "yolo26n" else None,
        model_path_func=lambda spec: tmp_path / spec.filename,
    )
    previous = _install_model_service(service)
    try:
        response = ui_backend.handle_command(
            ui_backend.CommandRequest(
                command="model.status",
                request_id="req-yolo-installed-status",
                payload={"poseVariant": "full", "enableHands": False},
            )
        )

        assert response["ok"] is True
        payload = response["payload"]
        by_key = {item["key"]: item for item in payload["models"]}
        assert by_key["yolo26n"]["installed"] is True
        assert by_key["yolo26n"]["installedSupported"] is False
        assert by_key["yolo26n"]["runtimeSupported"] is False
        assert payload["backendRoute"]["backend"] == "mediapipe"
        assert payload["backendRoute"]["fallbackReason"]
        assert payload["yoloRuntime"]["supported"] is False
    finally:
        ui_backend.DEFAULT_MODEL_SERVICE = previous


def test_model_status_routes_yolo26s_when_runtime_supported_and_only_s_is_installed(tmp_path: Path) -> None:
    service = ui_backend.ModelManagementService(
        specs=(
            _spec("pose_full", "pose.task", "Pose Full"),
            _runtime_yolo_spec("yolo26n", "yolo26n-pose.pt", "YOLO26n"),
            _runtime_yolo_spec("yolo26s", "yolo26s-pose.pt", "YOLO26s"),
        ),
        models_dir_func=lambda: tmp_path,
        is_installed_func=lambda spec: spec.key == "yolo26s",
        installed_size_func=lambda spec: 6.0 if spec.key == "yolo26s" else None,
        model_path_func=lambda spec: tmp_path / spec.filename,
        packaged_yolo_runtime=True,
    )
    previous = _install_model_service(service)
    try:
        response = ui_backend.handle_command(
            ui_backend.CommandRequest(
                command="model.status",
                request_id="req-yolo26s-installed-status",
                payload={"poseVariant": "full", "enableHands": False},
            )
        )

        assert response["ok"] is True
        payload = response["payload"]
        assert payload["backendRoute"]["backend"] == "yolo"
        assert payload["backendRoute"]["modelProfile"] == "yolo26s"
        assert payload["yoloRuntime"]["supported"] is True
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


def test_model_download_all_missing_skips_non_downloadable_yolo_profiles(tmp_path: Path) -> None:
    events: list[dict] = []
    manager = ui_backend.BridgeJobManager(events.append)
    specs = (
        _spec("pose_full", "pose.task", "Pose Full"),
        _yolo_spec("yolo26l", "yolo26l-pose.pt", "YOLO26L"),
    )
    downloaded: list[str] = []

    def fake_download(spec, *, progress_cb, should_stop):
        downloaded.append(spec.key)
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
                request_id="req-missing-yolo-filter",
                payload={"allMissing": True},
            )
        )
        final = manager.wait(response["jobId"], 2.0)

        assert final is not None
        assert final.status == "succeeded"
        assert downloaded == ["pose_full"]
        assert final.result["failed"] == []
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


def test_model_download_yolo_profile_reports_manual_install_required(tmp_path: Path) -> None:
    events: list[dict] = []
    manager = ui_backend.BridgeJobManager(events.append)
    specs = (_yolo_spec("yolo26l", "yolo26l-pose.pt", "YOLO26L"),)
    service = ui_backend.ModelManagementService(
        job_manager=manager,
        specs=specs,
        models_dir_func=lambda: tmp_path,
        is_installed_func=lambda spec: False,
        installed_size_func=lambda spec: None,
        model_path_func=lambda spec: tmp_path / spec.filename,
    )
    previous = _install_model_service(service)
    try:
        response = ui_backend.handle_command(
            ui_backend.CommandRequest(
                command="model.download",
                request_id="req-yolo-download",
                payload={"modelKey": "yolo26l"},
            )
        )
        final = manager.wait(response["jobId"], 2.0)

        assert final is not None
        assert final.status == "succeeded"
        assert final.result["state"] == "failed"
        assert final.result["failed"][0]["key"] == "yolo26l"
        assert final.result["failed"][0]["manualInstallRequired"] is True
    finally:
        ui_backend.DEFAULT_MODEL_SERVICE = previous


def test_model_download_proxy_defaults_to_local_proxy_and_allows_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VISION_MODEL_PROXY", raising=False)
    assert model_manager.model_download_proxy() == "http://127.0.0.1:7890"

    monkeypatch.setenv("VISION_MODEL_PROXY", " http://127.0.0.1:9999 ")
    assert model_manager.model_download_proxy() == "http://127.0.0.1:9999"

    monkeypatch.setenv("VISION_MODEL_PROXY", "")
    assert model_manager.model_download_proxy() == ""


def test_url_opener_uses_proxy_handler_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeProxyHandler:
        def __init__(self, proxies):
            captured["proxies"] = proxies

    class FakeOpener:
        pass

    def fake_build_opener(*handlers):
        captured["handler_count"] = len(handlers)
        return FakeOpener()

    monkeypatch.delenv("VISION_MODEL_PROXY", raising=False)
    monkeypatch.setattr(model_manager.urllib.request, "ProxyHandler", FakeProxyHandler)
    monkeypatch.setattr(model_manager.urllib.request, "build_opener", fake_build_opener)

    opener = model_manager._url_opener(proxy=None)

    assert isinstance(opener, FakeOpener)
    assert captured["handler_count"] == 1
    assert captured["proxies"] == {
        "http": "http://127.0.0.1:7890",
        "https": "http://127.0.0.1:7890",
    }


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

    _install_fake_url_opener(monkeypatch, FakeResponse())
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


def test_download_model_interruption_preserves_existing_model_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = model_manager.ModelSpec(
        key="fake",
        filename="fake.task",
        url="https://example.test/fake.task",
        label="Fake",
    )
    monkeypatch.setattr(model_manager, "models_dir", lambda: tmp_path)
    existing = tmp_path / "fake.task"
    existing.write_bytes(b"existing-model")

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

    _install_fake_url_opener(monkeypatch, FakeResponse())
    progress_calls = 0

    def progress(downloaded: int, total: int | None) -> None:
        nonlocal progress_calls
        progress_calls += 1

    def should_stop() -> bool:
        return progress_calls >= 2

    with pytest.raises(InterruptedError):
        model_manager.download_model(spec, progress_cb=progress, should_stop=should_stop)

    assert not (tmp_path / "fake.task.part").exists()
    assert existing.read_bytes() == b"existing-model"


def test_download_model_short_content_length_removes_part_and_preserves_existing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = model_manager.ModelSpec(
        key="fake",
        filename="fake.task",
        url="https://example.test/fake.task",
        label="Fake",
    )
    monkeypatch.setattr(model_manager, "models_dir", lambda: tmp_path)
    existing = tmp_path / "fake.task"
    existing.write_bytes(b"existing-model")

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

    _install_fake_url_opener(monkeypatch, FakeResponse())

    with pytest.raises(OSError, match="下载不完整"):
        model_manager.download_model(spec)

    assert not (tmp_path / "fake.task.part").exists()
    assert existing.read_bytes() == b"existing-model"
