# -*- coding: utf-8 -*-
"""Shared backend/layout CLI helpers for batch entry points."""

from __future__ import annotations

import argparse
from typing import Any

from core.body_core_compare import CALIBRATION_STATUS_UNVALIDATED
from core.feature_layout import BODY_CORE_V1, POSE33_V3
from core.yolo_adapter import (
    DEFAULT_YOLO_MODEL_NAME,
    DEFAULT_YOLO_VALID_CONF_THR,
    YOLO_CONFIDENCE_KIND,
    YOLO_VALIDITY_POLICY,
)

BACKEND_MEDIAPIPE = "mediapipe"
BACKEND_YOLO = "yolo"
FEATURE_LAYOUT_POSE33 = POSE33_V3.name
FEATURE_LAYOUT_BODY_CORE = BODY_CORE_V1.name

BATCH_META_FIELDS: tuple[str, ...] = (
    "backend",
    "model_name",
    "feature_layout",
    "confidence_kind",
    "validity_policy",
    "valid_conf_thr",
    "calibration_status",
    "score_authorized",
    "review_required",
)


def add_backend_layout_args(ap: argparse.ArgumentParser) -> None:
    ap.add_argument(
        "--backend",
        default=BACKEND_MEDIAPIPE,
        choices=[BACKEND_MEDIAPIPE, BACKEND_YOLO],
        help="Pose backend (default: mediapipe). YOLO is debug/calibration only.",
    )
    ap.add_argument(
        "--feature-layout",
        dest="feature_layout",
        default=FEATURE_LAYOUT_POSE33,
        choices=[FEATURE_LAYOUT_POSE33, FEATURE_LAYOUT_BODY_CORE],
        help="Feature layout (default: pose33_v3).",
    )


def normalize_backend_layout(backend: str, feature_layout: str) -> tuple[str, str]:
    backend = str(backend or BACKEND_MEDIAPIPE).lower()
    feature_layout = str(feature_layout or FEATURE_LAYOUT_POSE33)
    if backend == BACKEND_YOLO and feature_layout != FEATURE_LAYOUT_BODY_CORE:
        raise ValueError("YOLO 后端仅支持 --feature-layout body_core_v1；不得使用 YOLO + pose33_v3")
    if backend not in {BACKEND_MEDIAPIPE, BACKEND_YOLO}:
        raise ValueError(f"未知 backend：{backend!r}")
    if feature_layout not in {FEATURE_LAYOUT_POSE33, FEATURE_LAYOUT_BODY_CORE}:
        raise ValueError(f"未知 feature_layout：{feature_layout!r}")
    return backend, feature_layout


def is_default_pose33_path(backend: str, feature_layout: str) -> bool:
    backend, feature_layout = normalize_backend_layout(backend, feature_layout)
    return backend == BACKEND_MEDIAPIPE and feature_layout == FEATURE_LAYOUT_POSE33


def yolo_batch_meta(source_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    source_meta = dict(source_meta or {})
    return {
        "backend": BACKEND_YOLO,
        "model_name": str(source_meta.get("model_name") or DEFAULT_YOLO_MODEL_NAME),
        "feature_layout": FEATURE_LAYOUT_BODY_CORE,
        "confidence_kind": str(source_meta.get("confidence_kind") or YOLO_CONFIDENCE_KIND),
        "validity_policy": str(source_meta.get("validity_policy") or YOLO_VALIDITY_POLICY),
        "valid_conf_thr": float(source_meta.get("valid_conf_thr", DEFAULT_YOLO_VALID_CONF_THR)),
        "calibration_status": str(
            source_meta.get("calibration_status") or CALIBRATION_STATUS_UNVALIDATED
        ),
        "score_authorized": False,
        "review_required": bool(source_meta.get("review_required", False)),
    }


def mediapipe_body_core_meta(source_meta: dict[str, Any] | None = None, *, pose_variant: str = "full") -> dict[str, Any]:
    source_meta = dict(source_meta or {})
    return {
        "backend": BACKEND_MEDIAPIPE,
        "model_name": str(source_meta.get("model_name") or f"pose_landmarker_{pose_variant}"),
        "feature_layout": FEATURE_LAYOUT_BODY_CORE,
        "confidence_kind": str(source_meta.get("confidence_kind") or "visibility"),
        "validity_policy": str(source_meta.get("validity_policy") or "valid_mask"),
        "valid_conf_thr": source_meta.get("valid_conf_thr", ""),
        "calibration_status": str(
            source_meta.get("calibration_status") or CALIBRATION_STATUS_UNVALIDATED
        ),
        "score_authorized": False,
        "review_required": bool(source_meta.get("review_required", False)),
    }


def meta_for_backend(backend: str, source_meta: dict[str, Any] | None = None, *, pose_variant: str = "full") -> dict[str, Any]:
    if backend == BACKEND_YOLO:
        return yolo_batch_meta(source_meta)
    return mediapipe_body_core_meta(source_meta, pose_variant=pose_variant)


def csv_meta_fields(meta: dict[str, Any]) -> dict[str, Any]:
    return {field: meta.get(field, "") for field in BATCH_META_FIELDS}
