# -*- coding: utf-8 -*-
"""S5 GPU recheck decision gate regression tests (YOLO migration Issue #23)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from analysis import bench_annotate_fps  # noqa: E402
from core.yolo_adapter import BODY_CORE_V1_VALID_INDICES, FrameResult, Landmark  # noqa: E402


REPORT = _REPO_ROOT / "docs" / "yolo_gpu_recheck_report.md"


def test_gpu_recheck_report_has_cuda_fixed_no_go_decision():
    assert REPORT.exists(), f"GPU 复测报告缺失：{REPORT}"
    text = REPORT.read_text(encoding="utf-8")

    for keyword in (
        "预注册阈值",
        "CUDA 修正版",
        "torch=2.11.0+cu128",
        "torch.cuda.is_available() = True",
        "6/6 样本真实 GPU 复测",
        "Hands 关 FPS 比仅 1/6",
        "Hands 开 FPS 比 0/6",
        "YOLO raw FPS 0/6",
        "body_core 抖动 3/6",
        "真实 GPU 数据 no-go",
        "no-go",
        "#25",
        "#26",
        "#28",
        "全部不切默认",
    ):
        assert keyword in text, f"GPU 复测报告缺少关键口径：{keyword}"

    assert "analysis/bench_annotate_fps.py" in text
    assert "yolo_raw_infer_fps" in text
    assert "旧 CPU torch 前提已纠正" in text

    stale_final_claims = (
        "0/6 个样本产生有效 GPU",
        "skip_reason = torch_cuda_unavailable",
        "GPU runtime 可用性：`False`",
    )
    for stale in stale_final_claims:
        assert stale not in text, f"GPU 复测报告仍保留 CPU torch 无效前提作为最终结论：{stale}"


def test_benchmark_env_only_writes_probe_json(tmp_path, monkeypatch):
    monkeypatch.setattr(
        bench_annotate_fps,
        "collect_env",
        lambda: {
            "python": "test",
            "opencv": "test",
            "torch_cuda_available": False,
        },
    )

    out_dir = tmp_path / "gpu_recheck"
    rc = bench_annotate_fps.main(["--out", str(out_dir), "--env-only"])

    assert rc == 0
    env_path = out_dir / "gpu_recheck_env.json"
    assert env_path.exists()
    env = json.loads(env_path.read_text(encoding="utf-8"))
    for key in ("python", "opencv", "torch_cuda_available"):
        assert key in env


def test_body_core_jitter_helper_uses_only_consecutive_full_valid_frames():
    row_0 = bench_annotate_fps._body_core_xy_from_frame(_frame_with_shift(0.0), 0.6)
    row_1 = bench_annotate_fps._body_core_xy_from_frame(_frame_with_shift(0.01), 0.6)
    assert row_0 is not None
    assert row_1 is not None

    jitter = bench_annotate_fps._body_core_jitter_median([row_0, row_1, None, row_1])
    assert jitter == pytest.approx(0.01, abs=1e-6)


def test_csv_schema_contains_gpu_recheck_metric_fields(tmp_path):
    csv_path = tmp_path / "bench.csv"
    bench_annotate_fps._write_csv(
        csv_path,
        [
            {
                "sample_id": "s",
                "case": "yolo_body_only",
                "backend": "yolo",
                "status": "ok",
                "frames": 1,
                "yolo_raw_infer_fps": 99.0,
                "yolo_miss_rate": 0.0,
                "yolo_body_core_jitter_median": 0.01,
            }
        ],
    )

    text = csv_path.read_text(encoding="utf-8-sig")
    assert "yolo_raw_infer_fps" in text
    assert "yolo_miss_rate" in text
    assert "yolo_body_core_jitter_median" in text


def _frame_with_shift(shift: float) -> FrameResult:
    landmarks = [
        Landmark(x=0.0, y=0.0, confidence=None, synthetic=True)
        for _ in range(33)
    ]
    for order, idx in enumerate(BODY_CORE_V1_VALID_INDICES):
        landmarks[idx] = Landmark(
            x=0.1 + shift + order * 0.001,
            y=0.2 + order * 0.001,
            confidence=0.9,
            synthetic=False,
        )
    return FrameResult(pose33=tuple(landmarks), meta={"num_persons": 1})
