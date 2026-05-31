# -*- coding: utf-8 -*-
"""
body_core_v1 离线模板闭环（YOLO 迁移 Issue #8 / S2）。

定位
----
本模块打通**一条** YOLO ``body_core_v1`` 离线模板闭环（生成 → 匹配），并让
MediaPipe 也能生成同一布局模板（供 #10 三方对比）。它是 ``body_core_v1`` 这个共享
布局（12 点躯干四肢核心）的唯一消费者入口，故 normalizer / baseline 的「真正用途」
都在此体现（见 docs/yolo_migration_plan_optimized.md 三审拆层说明）。

硬约束（来自 AGENTS.md / 迁移计划，必须守住）
--------------------------------------------
- **不动 MediaPipe 默认 ``pose33_v3`` 路径**：``apps/make_template.py`` /
  ``compare_video_to_template`` 等旧默认行为完全不变；本模块是显式 opt-in 的独立入口。
- **YOLO 只允许 ``body_core_v1``**：本模块的 YOLO 路径只产出 / 匹配该布局。
- **未标定不得对外评分**：``body_core_v1`` baseline 本期为占位值
  （``BODY_CORE_V1_PLACEHOLDER_BASELINE``，正式标定在 #10），YOLO 侧 ``valid_conf_thr``
  同样是占位值。因此本模块产出的所有分数 meta 一律标
  ``calibration_status="unvalidated"``，仅供调试 / S3 标定，**不得进入用户报告 / 正式评分**。
- **不同 layout 比对报清晰错误**：复用 ``action_compare._assert_feature_layout_match``，
  绝不静默把 ``body_core_v1`` 模板与 ``pose33_v3`` 序列比对。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from .action_compare import _assert_feature_layout_match
from .feature_layout import BODY_CORE_V1, get_layout
from .paths import templates_dir
from .pose_features import (
    find_active_range,
    motion_energy,
    normalize_pose_body_core_v1,
    subsequence_dtw,
)

# body_core_v1 的 DTW baseline 本期为**待标定占位值**（正式标定在 #10）。
# 刻意不沿用 pose33_v3 的 2.0「已标定」语义——它只是让闭环能产出一个可比较的调试分数。
BODY_CORE_V1_PLACEHOLDER_BASELINE: float = 2.0

# 未标定状态标记：写入所有闭环输出 meta，下游据此拒绝把分数当对外评分。
CALIBRATION_STATUS_UNVALIDATED: str = "unvalidated"
BODY_CORE_CALIBRATION_NOTE: str = (
    "body_core_v1 baseline 与（YOLO 路径下的）valid_conf_thr 本期均为待标定占位值"
    "（calibrated in #10）。本分数仅供调试 / S3 标定使用，不得进入用户报告或正式评分。"
)

# 支持的后端。YOLO 只允许 body_core_v1（在本模块内强制）。
BACKEND_MEDIAPIPE = "mediapipe"
BACKEND_YOLO = "yolo"


class MultiPersonReviewRequiredError(RuntimeError):
    """多人场景闸门拒绝出分（YOLO 迁移 Issue #9 / S2）。

    YOLO 检出 ``num_persons>1`` 时「最大框取单人」可能稳定选错实例——这是正确性风险。
    默认（``reject_multi_person=True``）下，``match_body_core_template`` 直接抛本异常，
    确保多人视频**不混入正常评分结果**，必须人工复核。
    """

    def __init__(self, message: str, *, max_persons: int = 0, multi_person_frames: int = 0) -> None:
        super().__init__(message)
        self.max_persons = int(max_persons)
        self.multi_person_frames = int(multi_person_frames)


@dataclass(frozen=True)
class BodyCoreMatchResult:
    """body_core_v1 单模板匹配结果（未标定，仅供调试 / 标定）。

    多人场景下（``review_required=True``）``score`` 为 ``None``——降级模式不产出分数，
    避免多人视频混入正常评分结果。默认拒绝模式则根本不返回结果（抛
    ``MultiPersonReviewRequiredError``）。
    """

    template_path: Path
    video_path: Path
    backend: str
    feature_layout: str
    fps: float
    start_frame: int
    end_frame: int
    cost: float
    avg_cost: float
    score: float | None
    baseline: float
    calibration_status: str
    valid_frame_ratio: float | None = None
    # 多人闸门信息（Issue #9）。
    review_required: bool = False
    multi_person_detected: bool = False
    max_persons: int = 0
    multi_person_frames: int = 0


# --------------------------------------------------------------------------- #
# 特征提取（两后端共享 body_core_v1 normalizer）
# --------------------------------------------------------------------------- #
def _extract_body_core_mediapipe(
    video_path: Path,
    *,
    pose_variant: str = "full",
    start_frame: int | None = None,
    end_frame: int | None = None,
) -> tuple[np.ndarray, float]:
    """MediaPipe 路径：抽取 ``body_core_v1`` ``(T,12,2)`` 特征。

    复用既有 ``rule_scoring.extract_pose_raw``（与旧链路同款 VIDEO-mode 管线）拿到
    ``(T,33,4)`` 原始关键点与 ``valid_mask``，再逐帧套用共享
    ``normalize_pose_body_core_v1``。缺帧/核心点无效帧按 layout shape 补零或沿用上一帧，
    与旧路径风格一致。

    复用 ``extract_pose_raw`` 而非自建 cv2 循环，既减少重复，也让 golden harness
    （patch ``rule_scoring.MediaPipePipeline``）能确定性回放本路径。
    """
    from .rule_scoring import extract_pose_raw

    landmarks, meta = extract_pose_raw(
        video_path,
        pose_variant=pose_variant,
        start_frame=start_frame,
        end_frame=end_frame,
    )
    fps = float(meta.get("fps") or 30.0)

    feats, _valid_core_frames = _normalize_body_core_sequence(
        landmarks,
        valid_mask=meta.get("valid_mask"),
    )

    if feats.shape[0] == 0:
        raise RuntimeError(f"未能从视频提取 body_core_v1 特征：{video_path}")
    return feats, float(fps)


def _normalize_body_core_sequence(
    landmarks: np.ndarray,
    *,
    valid_mask: np.ndarray | None = None,
) -> tuple[np.ndarray, int]:
    """Normalize BlazePose33-like rows into ``body_core_v1`` features.

    When ``valid_mask`` is present, a frame is usable only if all 12 body-core source
    points are valid. Invalid frames are gap-filled with the previous usable feature
    (or zeros for a leading gap), so low-confidence coordinates never enter DTW.
    """
    arr = np.asarray(landmarks)
    if arr.ndim != 3 or arr.shape[1] < 33 or arr.shape[2] < 2:
        raise ValueError(f"body_core_v1 期望 landmarks shape (T,33,>=2)，实际 {arr.shape}")

    mask = None if valid_mask is None else np.asarray(valid_mask, dtype=bool)
    if mask is not None and (mask.ndim != 2 or mask.shape[0] != arr.shape[0] or mask.shape[1] < 33):
        raise ValueError(f"body_core_v1 期望 valid_mask shape (T,33)，实际 {mask.shape}")

    zero = np.zeros(tuple(int(x) for x in BODY_CORE_V1.shape), dtype=np.float32)
    core_idx = np.asarray(BODY_CORE_V1.source_indices, dtype=int)
    feats: list[np.ndarray] = []
    valid_core_frames = 0

    for t in range(int(arr.shape[0])):
        core_valid = True if mask is None else bool(np.all(mask[t, core_idx]))
        f = normalize_pose_body_core_v1(arr[t]) if core_valid else None
        if f is None:
            f = feats[-1].copy() if feats else zero.copy()
        else:
            valid_core_frames += 1
        feats.append(f)

    if not feats:
        return np.zeros((0, *BODY_CORE_V1.shape), dtype=np.float32), 0
    return np.stack(feats, axis=0).astype(np.float32), int(valid_core_frames)


def _extract_body_core_yolo(
    video_path: Path,
    *,
    yolo_model=None,
    valid_conf_thr: float | None = None,
    start_frame: int | None = None,
    end_frame: int | None = None,
) -> tuple[np.ndarray, float, dict]:
    """YOLO 路径：抽取 ``body_core_v1`` ``(T,12,2)`` 特征。

    先用 ``extract_yolo_landmark_series`` 拿到序列层 ``(T,33,4)`` + ``valid_mask[T,33]``
    （只返回 numpy，遵守序列层契约），先按 ``valid_mask`` 判定核心 12 点是否可用，
    再逐帧套用共享 ``normalize_pose_body_core_v1``。

    返回 ``(features[T,12,2], fps, yolo_meta)``；``yolo_meta`` 含
    ``valid_conf_thr`` / ``calibration_status`` / 多人信息，供闭环 meta 透传。

    缺帧（无人帧零行 / 核心点无效 / normalizer 返回 None）按 layout shape 补零或沿用上一帧。
    body_core_v1 的 12 点全部落在 COCO17 可映射点，因此该布局在 YOLO 路径下是真实点。
    """
    from .yolo_adapter import (
        DEFAULT_YOLO_VALID_CONF_THR,
        extract_yolo_landmark_series,
    )

    thr = float(DEFAULT_YOLO_VALID_CONF_THR if valid_conf_thr is None else valid_conf_thr)
    landmarks, valid_mask, yolo_meta = extract_yolo_landmark_series(
        video_path,
        yolo_model=yolo_model,
        valid_conf_thr=thr,
        start_frame=start_frame,
        end_frame=end_frame,
    )
    fps = float(yolo_meta.get("fps") or 30.0)

    features, valid_core_frames = _normalize_body_core_sequence(landmarks, valid_mask=valid_mask)
    yolo_meta = dict(yolo_meta)
    yolo_meta["body_core_valid_frame_ratio"] = (
        float(valid_core_frames) / float(features.shape[0]) if features.shape[0] else 0.0
    )
    # 多人闸门字段（multi_person_detected / review_required / gate_status /
    # max_persons / multi_person_frames）已由 extract_yolo_landmark_series 落进 yolo_meta，
    # 此处随 backend_meta 透传给评分入口（match_body_core_template）做拒绝/降级。
    return features, fps, yolo_meta


def extract_body_core_features(
    video_path: str | Path,
    *,
    backend: str,
    pose_variant: str = "full",
    yolo_model=None,
    valid_conf_thr: float | None = None,
    start_frame: int | None = None,
    end_frame: int | None = None,
) -> tuple[np.ndarray, float, dict]:
    """按后端抽取 ``body_core_v1`` ``(T,12,2)`` 特征，返回 ``(features, fps, backend_meta)``。"""
    backend = str(backend).lower()
    video_path = Path(video_path)
    if backend == BACKEND_MEDIAPIPE:
        features, fps = _extract_body_core_mediapipe(
            video_path,
            pose_variant=pose_variant,
            start_frame=start_frame,
            end_frame=end_frame,
        )
        return features, fps, {"backend": BACKEND_MEDIAPIPE}
    if backend == BACKEND_YOLO:
        return _extract_body_core_yolo(
            video_path,
            yolo_model=yolo_model,
            valid_conf_thr=valid_conf_thr,
            start_frame=start_frame,
            end_frame=end_frame,
        )
    raise ValueError(
        f"未知 backend：{backend!r}（body_core_v1 闭环仅支持 "
        f"{BACKEND_MEDIAPIPE!r} / {BACKEND_YOLO!r}）"
    )


# --------------------------------------------------------------------------- #
# 模板生成
# --------------------------------------------------------------------------- #
def create_body_core_template(
    video_path: str | Path,
    *,
    backend: str,
    pose_variant: str = "full",
    start: int | None = None,
    end: int | None = None,
    out_path: str | Path | None = None,
    yolo_model=None,
    valid_conf_thr: float | None = None,
) -> Path:
    """从视频生成 ``body_core_v1`` 模板（YOLO 或 MediaPipe）。

    模板 metadata 写 ``feature_layout=body_core_v1`` 与
    ``calibration_status=unvalidated``——明确该模板分数未标定、不得对外评分。
    """
    backend = str(backend).lower()
    video_path = Path(video_path)
    features, fps, backend_meta = extract_body_core_features(
        video_path,
        backend=backend,
        pose_variant=pose_variant,
        yolo_model=yolo_model,
        valid_conf_thr=valid_conf_thr,
    )
    if features.shape[0] == 0:
        raise RuntimeError(f"视频未产出任何 body_core_v1 帧：{video_path}")

    seq = features.reshape(features.shape[0], -1)
    if features.shape[0] >= 2:
        energy = motion_energy(seq)
        auto_start, auto_end = find_active_range(energy, pad=10)
    else:
        auto_start, auto_end = 0, int(features.shape[0] - 1)

    start_i = int(start) if start is not None else int(auto_start)
    end_i = int(end) if end is not None else int(auto_end)
    start_i = max(0, min(start_i, features.shape[0] - 1))
    end_i = max(start_i, min(end_i, features.shape[0] - 1))

    out_dir = templates_dir()
    out_path = (
        Path(out_path)
        if out_path
        else (out_dir / f"{video_path.stem}_{backend}_body_core_v1.npz")
    )

    meta: dict = {
        "video": str(video_path),
        "fps": float(fps),
        "frame_count": int(features.shape[0]),
        "start_frame": int(start_i),
        "end_frame": int(end_i),
        "auto_start_frame": int(auto_start),
        "auto_end_frame": int(auto_end),
        "backend": backend,
        "feature_layout": BODY_CORE_V1.name,
        "normalizer_version": "body_core_v1",
        "running_mode": "video",
        # 未标定标记：本模板分数不得对外评分（正式标定在 #10）。
        "calibration_status": CALIBRATION_STATUS_UNVALIDATED,
        "calibration_note": BODY_CORE_CALIBRATION_NOTE,
        "baseline": float(BODY_CORE_V1_PLACEHOLDER_BASELINE),
        "baseline_calibrated": False,
    }
    if backend == BACKEND_MEDIAPIPE:
        meta["pose_variant"] = pose_variant
        meta["model_name"] = f"pose_landmarker_{pose_variant}"
        meta["confidence_kind"] = "visibility"
    else:  # YOLO
        meta["model_name"] = str(backend_meta.get("model_name", "yolo"))
        meta["confidence_kind"] = str(backend_meta.get("confidence_kind", "yolo_conf"))
        meta["validity_policy"] = str(backend_meta.get("validity_policy", "confidence_thr"))
        meta["valid_conf_thr"] = float(backend_meta.get("valid_conf_thr", 0.5))
        # 透传 YOLO 多人闸门 / track 信息，供 #9 拒绝/降级与 #10 标定参考。
        for k in (
            "max_persons",
            "multi_person_frames",
            "multi_person_detected",
            "review_required",
            "gate_status",
            "track_reset_note",
        ):
            if k in backend_meta:
                meta[k] = backend_meta[k]
        if "body_core_valid_frame_ratio" in backend_meta:
            meta["body_core_valid_frame_ratio"] = float(backend_meta["body_core_valid_frame_ratio"])

    np.savez_compressed(
        out_path,
        features=features[start_i : end_i + 1],
        meta=np.array(meta, dtype=object),
    )
    return Path(out_path)


# --------------------------------------------------------------------------- #
# 模板匹配
# --------------------------------------------------------------------------- #
def match_body_core_template(
    template_path: str | Path,
    video_path: str | Path,
    *,
    backend: str | None = None,
    pose_variant: str | None = None,
    yolo_model=None,
    valid_conf_thr: float | None = None,
    reject_multi_person: bool = True,
) -> BodyCoreMatchResult:
    """用 ``body_core_v1`` 模板匹配视频，产出**未标定**调试分数。

    - 校验模板 ``feature_layout`` 必须是 ``body_core_v1``；非该布局直接报清晰错误
      （不静默套用 pose33_v3 路径）。
    - 用模板自身 ``feature_layout`` 与视频提取序列做 ``_assert_feature_layout_match``，
      确保 shape / layout 一致。
    - 返回结果与 meta 都标 ``calibration_status=unvalidated``。

    多人场景闸门（Issue #9 / S2）
    -----------------------------
    YOLO 路径下检出 ``num_persons>1`` 时「最大框取单人」可能稳定选错实例（正确性风险）：
      - ``reject_multi_person=True``（默认）：抛 ``MultiPersonReviewRequiredError``，
        多人视频**不混入正常评分结果**，必须人工复核。
      - ``reject_multi_person=False``：降级——返回 ``score=None`` 且
        ``review_required=True`` 的结果，仍不产出分数，供 batch 标「需人工复核」。
    单人 / MediaPipe 路径不受影响。
    """
    template_path = Path(template_path)
    video_path = Path(video_path)

    tpl = np.load(template_path, allow_pickle=True)
    query = tpl["features"]
    meta = dict(tpl["meta"].item() or {})

    tpl_layout = str(meta.get("feature_layout", ""))
    if tpl_layout != BODY_CORE_V1.name:
        raise ValueError(
            f"body_core_v1 闭环只接受 feature_layout={BODY_CORE_V1.name!r} 的模板，"
            f"实际模板 {template_path} 的 feature_layout={tpl_layout!r}；"
            "请勿与 pose33_v3 模板混用。"
        )
    # 校验布局存在（防御性：拼写错误的布局名应尽早报错）。
    get_layout(BODY_CORE_V1.name)

    eff_backend = str(backend or meta.get("backend") or BACKEND_MEDIAPIPE).lower()
    pv = pose_variant or meta.get("pose_variant", "full")

    seq, fps, backend_meta = extract_body_core_features(
        video_path,
        backend=eff_backend,
        pose_variant=pv,
        yolo_model=yolo_model,
        valid_conf_thr=valid_conf_thr,
    )

    # 多人闸门（Issue #9）：YOLO 路径透传 review_required / multi_person_detected。
    # MediaPipe 路径无该字段，默认单人，不受影响。
    review_required = bool(backend_meta.get("review_required", False))
    multi_person_detected = bool(backend_meta.get("multi_person_detected", False))
    max_persons = int(backend_meta.get("max_persons", 0))
    multi_person_frames = int(backend_meta.get("multi_person_frames", 0))

    if review_required and reject_multi_person:
        raise MultiPersonReviewRequiredError(
            f"多人场景闸门拒绝出分：{video_path} 检出多人"
            f"（max_persons={max_persons}，multi_person_frames={multi_person_frames}）。"
            "YOLO「最大框取单人」可能稳定选错实例，该视频需人工复核，不得进入正常评分。",
            max_persons=max_persons,
            multi_person_frames=multi_person_frames,
        )

    # 不同 layout / shape 不允许静默比对。
    _assert_feature_layout_match(
        query,
        seq,
        left_label=f"template {template_path}",
        right_label=f"video {video_path}",
        left_layout=tpl_layout,
        right_layout=BODY_CORE_V1.name,
    )

    if seq.shape[0] == 0:
        raise RuntimeError(f"视频未产出任何 body_core_v1 帧：{video_path}")

    baseline = float(meta.get("baseline", BODY_CORE_V1_PLACEHOLDER_BASELINE))
    cost, start, end = subsequence_dtw(query, seq)
    avg_cost = float(cost) / max(1, int(query.shape[0]))

    # 降级模式（reject_multi_person=False）：多人时不产出分数（score=None），
    # 仍计算 cost/avg_cost 供调试，但绝不把多人分数当对外评分。
    score: float | None
    if review_required:
        score = None
    else:
        score = float(baseline / (baseline + avg_cost))

    return BodyCoreMatchResult(
        template_path=template_path,
        video_path=video_path,
        backend=eff_backend,
        feature_layout=BODY_CORE_V1.name,
        fps=float(fps),
        start_frame=int(start),
        end_frame=int(end),
        cost=float(cost),
        avg_cost=float(avg_cost),
        score=score,
        baseline=float(baseline),
        # 未标定：分数仅供调试 / 标定，不得对外评分。
        calibration_status=CALIBRATION_STATUS_UNVALIDATED,
        valid_frame_ratio=(
            float(backend_meta["body_core_valid_frame_ratio"])
            if "body_core_valid_frame_ratio" in backend_meta
            else None
        ),
        review_required=review_required,
        multi_person_detected=multi_person_detected,
        max_persons=max_persons,
        multi_person_frames=multi_person_frames,
    )
