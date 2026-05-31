# -*- coding: utf-8 -*-
"""S5 GPU recheck decision gate regression tests (YOLO migration Issue #23)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from analysis import bench_annotate_fps  # noqa: E402


REPORT = _REPO_ROOT / "docs" / "yolo_gpu_recheck_report.md"


def test_gpu_recheck_report_has_preregistered_no_go_decision():
    assert REPORT.exists(), f"GPU 复测报告缺失：{REPORT}"
    text = REPORT.read_text(encoding="utf-8")

    for keyword in (
        "预注册阈值",
        "torch.cuda.is_available()",
        "0/6",
        "no-go",
        "#25",
        "#26",
        "#28",
        "全部不切默认",
    ):
        assert keyword in text, f"GPU 复测报告缺少关键口径：{keyword}"

    assert "analysis/bench_annotate_fps.py" in text
    assert "torch_cuda_unavailable" in text


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
