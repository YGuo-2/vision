# -*- coding: utf-8 -*-
"""S5 Hybrid decision regression tests (YOLO migration Issue #27)."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

REPORT = _REPO_ROOT / "docs" / "yolo_gpu_recheck_report.md"


def test_hybrid_decision_report_records_no_implementation():
    assert REPORT.exists(), f"GPU / Hybrid 决议报告缺失：{REPORT}"
    text = REPORT.read_text(encoding="utf-8")

    for keyword in (
        "Hybrid 决议（Issue #27）",
        "不实现 `yolo_body_mp_pose_supplement`",
        "0/6",
        "0.41",
        "torch.cuda.is_available() == True",
        "score_authorized=False",
        "另开实现子任务",
    ):
        assert keyword in text, f"Hybrid 决议缺少关键证据或边界：{keyword}"


def test_no_hybrid_runtime_code_path_exists():
    runtime_roots = ("apps", "batch", "core", "analysis")
    hits: list[Path] = []
    for root_name in runtime_roots:
        root = _REPO_ROOT / root_name
        for path in root.rglob("*.py"):
            if "yolo_body_mp_pose_supplement" in path.read_text(encoding="utf-8"):
                hits.append(path.relative_to(_REPO_ROOT))
    assert hits == []
