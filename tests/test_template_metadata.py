# -*- coding: utf-8 -*-
"""模板 metadata 扩展 + 向后兼容回归（YOLO 迁移 S1 / Issue #6 Part B/C）。

覆盖
----
1. 新模板：通过 ``create_template_from_video``（确定性回放）生成模板，断言 7 个
   新增 metadata 字段齐全且取值正确，且既有 ``feature_layout`` 字符串未被改动。
2. 向后兼容：构造“缺新字段”的 legacy 模板（取已提交模板，剥掉新键后另存），
   断言 ``compare_video_to_template`` / ``compare_video_to_dual_templates`` 仍能加载并
   运行不报错，且 ``normalize_template_meta`` 能补齐默认值。

确定性
------
与 golden 回归一致，通过 ``tests/golden_harness.py`` 回放已提交的 ``(T,33,4)`` landmark
fixture，不依赖 MediaPipe 实际推理。

验收命令
--------
    .\\.venv\\Scripts\\python.exe -m pytest tests\\test_template_metadata.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.action_compare import (  # noqa: E402
    compare_video_to_dual_templates,
    compare_video_to_template,
    create_template_from_video,
    normalize_template_meta,
    template_meta_defaults,
)
from tests import golden_harness as H  # noqa: E402

FIX_DIR = Path(__file__).resolve().parent / "fixtures" / "pose33_v3"

FRONT_SRC = "golden://front_src.mp4"
SIDE_SRC = "golden://side_src.mp4"
STUDENT = "golden://student.mp4"
FPS = 30.0

# 既有 feature_layout 字符串（loader 按其 `_v3` 后缀分支）——绝不能被改动。
EXPECTED_FEATURE_LAYOUT = "pose_indices_11_32_xy_rot_scale_norm_v3"

# Issue #6 新增的 7 个增量字段（含取值）。
_NEW_FIELDS = {
    "backend": "mediapipe",
    "model_name": "pose_landmarker_full",
    "normalizer_version": "v3",
    "confidence_kind": "visibility",
    "validity_policy": "visibility_thr",
    "valid_conf_thr": 0.5,
    "feature_layout_name": "pose33_v3",
}


def _load_raw(name: str) -> np.ndarray:
    d = np.load(FIX_DIR / name, allow_pickle=True)
    return np.asarray(d["landmarks"], dtype=np.float32)


def _load_meta(path: Path) -> dict:
    d = np.load(path, allow_pickle=True)
    return dict(d["meta"].item())


# --------------------------------------------------------------------------- #
# 1) 新模板：7 个新字段齐全 + 既有 feature_layout 不变
# --------------------------------------------------------------------------- #
def test_new_template_has_all_metadata_fields(tmp_path):
    front_raw = _load_raw("front_src_raw.npz")
    out_path = tmp_path / "front_template_new.npz"

    H.clear_registry()
    H.register_video(FRONT_SRC, front_raw, fps=FPS)
    with H.replay_context():
        create_template_from_video(FRONT_SRC, pose_variant="full", out_path=out_path)
    H.clear_registry()

    meta = _load_meta(out_path)

    # 7 个新字段齐全且取值正确
    assert meta["backend"] == "mediapipe"
    assert meta["model_name"] == "pose_landmarker_full"
    assert meta["normalizer_version"] == "v3"
    assert meta["confidence_kind"] == "visibility"
    assert meta["validity_policy"] == "visibility_thr"
    assert float(meta["valid_conf_thr"]) == pytest.approx(0.5, abs=1e-9)
    assert meta["feature_layout_name"] == "pose33_v3"

    # 既有 feature_layout 字符串未被改动（loader 依赖其 _v3 后缀分支）
    assert meta["feature_layout"] == EXPECTED_FEATURE_LAYOUT
    # 既有字段仍在
    assert meta["pose_variant"] == "full"
    assert meta["running_mode"] == "video"


def test_template_meta_defaults_and_normalize():
    defaults = template_meta_defaults()
    # 默认值与字段集合一致
    for key, value in _NEW_FIELDS.items():
        assert key in defaults
        if isinstance(value, float):
            assert float(defaults[key]) == pytest.approx(value, abs=1e-9)
        else:
            assert defaults[key] == value

    # normalize 只补缺失键，不覆盖已存在的值
    legacy = {"feature_layout": "legacy_layout", "backend": "custom"}
    normalized = normalize_template_meta(dict(legacy))
    assert normalized["feature_layout"] == "legacy_layout"  # 未被改动
    assert normalized["backend"] == "custom"  # 已存在不覆盖
    assert normalized["model_name"] == "pose_landmarker_full"  # 缺失补默认
    assert normalized["normalizer_version"] == "v3"
    assert normalized["validity_policy"] == "visibility_thr"
    assert float(normalized["valid_conf_thr"]) == pytest.approx(0.5, abs=1e-9)


# --------------------------------------------------------------------------- #
# 2) 向后兼容：缺新字段的 legacy 模板仍能加载并比对
# --------------------------------------------------------------------------- #
def _make_legacy_template(src: Path, dst: Path) -> dict:
    """复制已提交模板，剥掉 Issue #6 新增的全部新字段，另存为 legacy 模板。"""
    d = np.load(src, allow_pickle=True)
    features = d["features"]
    meta = dict(d["meta"].item())
    for key in _NEW_FIELDS:
        meta.pop(key, None)
    np.savez_compressed(dst, features=features, meta=np.array(meta, dtype=object))
    return meta


def test_legacy_template_missing_fields_normalized():
    # 直接验证 normalize 能把“剥光新字段”的 meta 补齐。
    stripped = {
        k: v
        for k, v in _load_meta(FIX_DIR / "front_template.npz").items()
        if k not in _NEW_FIELDS
    }
    for key in _NEW_FIELDS:
        assert key not in stripped
    normalized = normalize_template_meta(dict(stripped))
    for key in _NEW_FIELDS:
        assert key in normalized, f"normalize 未补齐 {key}"


def test_legacy_single_template_still_loads(tmp_path):
    legacy_tpl = tmp_path / "legacy_front_template.npz"
    legacy_meta = _make_legacy_template(FIX_DIR / "front_template.npz", legacy_tpl)
    # 确认 legacy 模板确实缺新字段
    for key in _NEW_FIELDS:
        assert key not in legacy_meta

    student_raw = _load_raw("student_raw.npz")
    H.clear_registry()
    H.register_video(STUDENT, student_raw, fps=FPS)
    with H.replay_context():
        res = compare_video_to_template(legacy_tpl, STUDENT, pose_variant="full")
    H.clear_registry()

    # 数值断言保持宽松：只要返回结果对象、分数有限即可。
    assert res is not None
    assert np.isfinite(float(res.score))
    assert np.isfinite(float(res.avg_cost))


def test_legacy_dual_templates_still_load(tmp_path):
    legacy_front = tmp_path / "legacy_front.npz"
    legacy_side = tmp_path / "legacy_side.npz"
    _make_legacy_template(FIX_DIR / "front_template.npz", legacy_front)
    _make_legacy_template(FIX_DIR / "side_template.npz", legacy_side)

    student_raw = _load_raw("student_raw.npz")
    H.clear_registry()
    H.register_video(STUDENT, student_raw, fps=FPS)
    with H.replay_context():
        res = compare_video_to_dual_templates(
            legacy_front,
            legacy_side,
            STUDENT,
            pose_variant="full",
            enable_rules=True,
            enable_error_analysis=True,
        )
    H.clear_registry()

    assert res is not None
    assert 0 <= int(res.combined_percent) <= 100
    assert np.isfinite(float(res.front_score))
    assert np.isfinite(float(res.side_score))
