# -*- coding: utf-8 -*-
"""Tracking issue closure docs regression tests (YOLO migration Issue #12)."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

ISSUES_DOC = _REPO_ROOT / "docs" / "yolo_migration_issues.md"
S6_DECISION = _REPO_ROOT / "docs" / "yolo_default_switch_decision.md"


def test_tracking_doc_lists_final_m4_issues_and_decisions():
    text = ISSUES_DOC.read_text(encoding="utf-8")
    for keyword in (
        "Issue #12",
        "#1–#11、#23–#28 均已关闭",
        "| M4 决策与扩展 | #23 #24 #25 #26 #27 #28 |",
        "#23 GPU 复测决策门：no-go",
        "#24 batch backend/layout 参数",
        "#25 CLI 实时预览：按 #23 no-go 关闭 / 不实现",
        "#26 UI 后端选择：按 #23 / #25 no-go 关闭 / 不实现",
        "#27 Hybrid：默认不实现",
        "#28",
        "全部不切默认，仅保留离线 / 实验入口",
    ):
        assert keyword in text, f"总追踪清单缺少最终收尾状态：{keyword}"


def test_tracking_doc_no_longer_says_m4_is_pending_split():
    text = ISSUES_DOC.read_text(encoding="utf-8")
    stale_phrases = (
        "（空，S5/S6 待 S3 结论后开票）",
        "## 后置阶段（暂不拆细 Issue）",
        "暂不拆细原因",
        "S5 / S6（按需开 Issue）",
    )
    for phrase in stale_phrases:
        assert phrase not in text, f"总追踪清单仍保留旧待拆票表述：{phrase}"


def test_s6_decision_doc_exists_for_tracking_close():
    assert S6_DECISION.exists(), "Issue #12 收尾需要 S6 决策文档存在"
    text = S6_DECISION.read_text(encoding="utf-8")
    assert "YOLO 迁移 S6 默认切换决策（Issue #28）" in text
    assert "全部不切默认，仅保留离线 / 实验入口" in text
