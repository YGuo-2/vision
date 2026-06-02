# -*- coding: utf-8 -*-
"""MediaPipe delegate opt-in contract tests (YOLO migration Issue #43)."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core import vision_pipeline  # noqa: E402


def test_base_options_keeps_legacy_cpu_default(monkeypatch):
    calls = []

    class FakeBaseOptions:
        Delegate = SimpleNamespace(GPU="GPU")

        def __init__(self, **kwargs) -> None:
            calls.append(kwargs)

    monkeypatch.setattr(vision_pipeline.mp.tasks, "BaseOptions", FakeBaseOptions)

    vision_pipeline._base_options(Path("pose.task"), delegate="cpu")

    assert calls == [{"model_asset_path": "pose.task"}]


def test_base_options_uses_gpu_delegate_only_when_explicit(monkeypatch):
    calls = []

    class FakeBaseOptions:
        Delegate = SimpleNamespace(GPU="GPU")

        def __init__(self, **kwargs) -> None:
            calls.append(kwargs)

    monkeypatch.setattr(vision_pipeline.mp.tasks, "BaseOptions", FakeBaseOptions)

    vision_pipeline._base_options(Path("pose.task"), delegate="gpu")

    assert calls == [{"model_asset_path": "pose.task", "delegate": "GPU"}]


def test_base_options_rejects_unknown_delegate():
    with pytest.raises(ValueError, match="Unsupported MediaPipe delegate"):
        vision_pipeline._base_options(Path("pose.task"), delegate="metal")


def test_pipeline_config_delegate_defaults_to_cpu():
    assert vision_pipeline.PipelineConfig().delegate == "cpu"


def test_pipeline_closes_pose_landmarker_when_hand_creation_fails(tmp_path, monkeypatch):
    closed = []

    class FakePoseLandmarker:
        def close(self) -> None:
            closed.append("pose")

    class FakePoseFactory:
        @staticmethod
        def create_from_options(options):
            return FakePoseLandmarker()

    class FakeHandFactory:
        @staticmethod
        def create_from_options(options):
            raise RuntimeError("hand init failed")

    monkeypatch.setattr(vision_pipeline, "_ensure_file", lambda url, path: None)
    monkeypatch.setattr(
        vision_pipeline.mp.tasks,
        "BaseOptions",
        lambda **kwargs: SimpleNamespace(**kwargs),
    )
    monkeypatch.setattr(
        vision_pipeline.mp.tasks,
        "vision",
        SimpleNamespace(
            RunningMode=SimpleNamespace(VIDEO="VIDEO", IMAGE="IMAGE"),
            PoseLandmarker=FakePoseFactory,
            PoseLandmarkerOptions=lambda **kwargs: SimpleNamespace(**kwargs),
            HandLandmarker=FakeHandFactory,
            HandLandmarkerOptions=lambda **kwargs: SimpleNamespace(**kwargs),
        ),
    )

    with pytest.raises(RuntimeError, match="hand init failed"):
        vision_pipeline.MediaPipePipeline(
            models_dir=tmp_path,
            cfg=vision_pipeline.PipelineConfig(enable_hands=True),
        )

    assert closed == ["pose"]
