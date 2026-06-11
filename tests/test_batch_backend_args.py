# -*- coding: utf-8 -*-
"""Batch backend/layout argument contract tests (YOLO migration Issue #24)."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from batch import batch_dual_compare, batch_export_skeleton, batch_tech_eval  # noqa: E402
from batch.backend_options import meta_for_backend, normalize_backend_layout, yolo_batch_meta  # noqa: E402


def test_backend_layout_defaults_preserve_pose33_path():
    assert normalize_backend_layout("mediapipe", "pose33_v3") == ("mediapipe", "pose33_v3")


def test_yolo_pose33_combination_rejected():
    with pytest.raises(ValueError, match="YOLO 后端仅支持"):
        normalize_backend_layout("yolo", "pose33_v3")


def test_yolo_meta_marks_unvalidated_and_unauthorized():
    meta = yolo_batch_meta(
        {
            "model_name": "fake-yolo.pt",
            "valid_conf_thr": 0.6,
            "review_required": True,
        }
    )
    assert meta["backend"] == "yolo"
    assert meta["raw_layout"] == "pose33_like_coco17"
    assert meta["feature_layout"] == "body_core_v1"
    assert meta["capability"] == "body_only"
    assert meta["calibration_status"] == "unvalidated"
    assert meta["score_authorized"] is False
    assert meta["display_scope"] in {"limited", "internal"}
    assert meta["review_required"] is True


def test_meta_for_backend_uses_shared_router_contract_for_mediapipe_body_core():
    meta = meta_for_backend("mediapipe", {"review_required": True}, pose_variant="heavy")

    assert meta["backend"] == "mediapipe"
    assert meta["raw_layout"] == "pose33_v3"
    assert meta["feature_layout"] == "body_core_v1"
    assert meta["capability"] == "body_only"
    assert meta["calibration_status"] == "unvalidated"
    assert meta["score_authorized"] is False
    assert meta["display_scope"] == "internal"
    assert meta["review_required"] is True


def test_dual_compare_body_core_row_keeps_debug_scores_out_of_outward_columns(tmp_path):
    meta = yolo_batch_meta({"review_required": False})
    front = SimpleNamespace(
        score=0.42,
        avg_cost=1.2,
        valid_frame_ratio=0.9,
        review_required=False,
        max_persons=1,
        multi_person_frames=0,
    )
    side = SimpleNamespace(
        score=0.52,
        avg_cost=1.1,
        valid_frame_ratio=0.8,
        review_required=False,
        max_persons=1,
        multi_person_frames=0,
    )

    row = batch_dual_compare._body_core_row(tmp_path / "student.mp4", front, side, meta=meta)

    assert row["backend"] == "yolo"
    assert row["feature_layout"] == "body_core_v1"
    assert row["calibration_status"] == "unvalidated"
    assert row["score_authorized"] is False
    assert row["front_debug_score"] == pytest.approx(0.42)
    assert "front_score" not in row
    assert "combined_percent" not in row


def test_dual_compare_body_core_row_marks_multi_person_review(tmp_path):
    meta = yolo_batch_meta({"review_required": False})
    front = SimpleNamespace(
        score=None,
        avg_cost=1.2,
        valid_frame_ratio=0.9,
        review_required=True,
        max_persons=3,
        multi_person_frames=4,
    )
    side = SimpleNamespace(
        score=0.52,
        avg_cost=1.1,
        valid_frame_ratio=0.8,
        review_required=False,
        max_persons=1,
        multi_person_frames=0,
    )

    row = batch_dual_compare._body_core_row(tmp_path / "student.mp4", front, side, meta=meta)

    assert row["review_required"] is True
    assert row["review_status"] == "需人工复核"
    assert row["front_debug_score"] == ""
    assert row["max_persons"] == 3
    assert row["multi_person_frames"] == 4


def test_export_skeleton_body_core_npz_meta_contains_issue24_fields(tmp_path, monkeypatch):
    src = tmp_path / "src"
    src.mkdir()
    video = src / "demo.mp4"
    video.write_bytes(b"fake")

    def fake_iter(_root: Path, *, skip_keywords: tuple[str, ...]):
        return [video]

    def fake_extract(video_path: Path, *, backend: str, pose_variant: str):
        assert backend == "yolo"
        assert pose_variant == "full"
        features = np.zeros((2, 12, 2), dtype=np.float32)
        meta = yolo_batch_meta({"model_name": "fake-yolo.pt"})
        meta.update(
            {
                "video": str(video_path),
                "name": video_path.stem,
                "fps": 30.0,
                "frame_count": 2,
                "width": 1280,
                "height": 720,
                "landmark_layout": "body_core_v1_normalized_xy",
                "skeleton_video": None,
            }
        )
        return features, meta

    monkeypatch.setattr(batch_export_skeleton, "_iter_videos", fake_iter)
    monkeypatch.setattr(batch_export_skeleton, "_extract_body_core_features", fake_extract)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "batch_export_skeleton.py",
            "--source_dir",
            str(src),
            "--out_dir",
            str(tmp_path / "out"),
            "--backend",
            "yolo",
            "--feature-layout",
            "body_core_v1",
        ],
    )

    batch_export_skeleton.main()

    npz_path = next((tmp_path / "out").rglob("*_yolo_body_core_v1.npz"))
    data = np.load(npz_path, allow_pickle=True)
    meta = dict(data["meta"].item())
    assert data["features"].shape == (2, 12, 2)
    assert meta["backend"] == "yolo"
    assert meta["feature_layout"] == "body_core_v1"
    assert meta["calibration_status"] == "unvalidated"
    assert meta["score_authorized"] is False

    manifest = next((tmp_path / "out").rglob("manifest.csv"))
    rows = list(csv.DictReader(manifest.open(encoding="utf-8-sig")))
    assert rows[0]["backend"] == "yolo"
    assert rows[0]["score_authorized"] == "False"


def test_export_skeleton_skip_existing_body_core_keeps_manifest_meta(tmp_path, monkeypatch):
    src = tmp_path / "src"
    src.mkdir()
    old_video = src / "a_old.mp4"
    new_video = src / "b_new.mp4"
    old_video.write_bytes(b"fake")
    new_video.write_bytes(b"fake")
    out_dir = tmp_path / "out"
    existing_npz = out_dir / "a_old_yolo_body_core_v1.npz"
    existing_npz.parent.mkdir(parents=True)
    existing_meta = yolo_batch_meta({"model_name": "existing-yolo.pt"})
    existing_meta.update({"fps": 24.0, "frame_count": 3, "width": 640, "height": 480})
    np.savez_compressed(
        existing_npz,
        features=np.zeros((3, 12, 2), dtype=np.float32),
        meta=np.array(existing_meta, dtype=object),
    )

    def fake_iter(_root: Path, *, skip_keywords: tuple[str, ...]):
        return [old_video, new_video]

    def fake_extract(video_path: Path, *, backend: str, pose_variant: str):
        features = np.zeros((2, 12, 2), dtype=np.float32)
        meta = yolo_batch_meta({"model_name": "new-yolo.pt"})
        meta.update(
            {
                "video": str(video_path),
                "name": video_path.stem,
                "fps": 30.0,
                "frame_count": 2,
                "width": 1280,
                "height": 720,
                "landmark_layout": "body_core_v1_normalized_xy",
                "skeleton_video": None,
            }
        )
        return features, meta

    monkeypatch.setattr(batch_export_skeleton, "_iter_videos", fake_iter)
    monkeypatch.setattr(batch_export_skeleton, "_extract_body_core_features", fake_extract)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "batch_export_skeleton.py",
            "--source_dir",
            str(src),
            "--out_dir",
            str(out_dir),
            "--backend",
            "yolo",
            "--feature-layout",
            "body_core_v1",
        ],
    )

    batch_export_skeleton.main()

    manifest = out_dir / "manifest.csv"
    rows = list(csv.DictReader(manifest.open(encoding="utf-8-sig")))
    assert len(rows) == 2
    assert rows[0]["video_name"] == "a_old.mp4"
    assert rows[0]["backend"] == "yolo"
    assert rows[0]["model_name"] == "existing-yolo.pt"
    assert rows[0]["score_authorized"] == "False"
    assert rows[1]["video_name"] == "b_new.mp4"
    assert rows[1]["backend"] == "yolo"
    assert rows[1]["model_name"] == "new-yolo.pt"


def test_tech_eval_yolo_body_core_skips_outward_scoring(tmp_path):
    meta = yolo_batch_meta({"review_required": True})
    meta.update({"max_persons": 2, "multi_person_frames": 5})

    row = batch_tech_eval._body_core_unvalidated_row(tmp_path / "multi.mp4", meta)

    assert row["backend"] == "yolo"
    assert row["feature_layout"] == "body_core_v1"
    assert row["calibration_status"] == "unvalidated"
    assert row["score_authorized"] is False
    assert row["review_required"] is True
    assert row["review_status"] == "需人工复核"
    assert row["重心(侧面优先)"] == "无法判定"
    assert row["发力顺序"] == "无法判定"


def test_tech_eval_full_jsonl_meta_marks_unvalidated(tmp_path, monkeypatch):
    video = tmp_path / "student.mp4"
    video.write_bytes(b"fake")

    monkeypatch.setattr(
        batch_tech_eval,
        "_body_core_meta_for_video",
        lambda v, *, backend, pose_variant: yolo_batch_meta({"model_name": "fake-yolo.pt"}),
    )

    args = SimpleNamespace(full=True, pose="full")
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    batch_tech_eval._run_unvalidated_body_core_batch(
        videos=[video],
        out_dir=out_dir,
        args=args,
        backend="yolo",
    )

    line = (out_dir / "tech_report_full.jsonl").read_text(encoding="utf-8").splitlines()[0]
    payload = json.loads(line)
    assert payload["tech_eval_status"] == "skipped"
    assert payload["skip_reason"] == "unvalidated_body_core_v1"
    assert payload["score_authorized"] is False
    assert payload["meta"]["calibration_status"] == "unvalidated"
