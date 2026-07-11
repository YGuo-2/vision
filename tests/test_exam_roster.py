# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

import pytest

from core.exam_roster import (
    ExamCandidate,
    ExamResultRow,
    ExamScorebook,
    RosterError,
    import_roster_xlsx,
    write_import_template,
    write_scorebook_xlsx,
)


def test_import_template_and_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "roster.xlsx"
    write_import_template(path)
    cands = import_roster_xlsx(path)
    assert len(cands) == 2
    assert cands[0].student_id == "2026001"
    assert cands[0].name == "张三"


def test_reject_duplicate_order(tmp_path: Path) -> None:
    from openpyxl import Workbook

    path = tmp_path / "bad.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["序号", "学号", "姓名"])
    ws.append([1, "A", "甲"])
    ws.append([1, "B", "乙"])
    wb.save(path)
    wb.close()
    with pytest.raises(RosterError) as ei:
        import_roster_xlsx(path)
    assert ei.value.code == "duplicate_order"


def test_reject_merged_cells(tmp_path: Path) -> None:
    from openpyxl import Workbook

    path = tmp_path / "merged.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["序号", "学号", "姓名"])
    ws.append([1, "A", "甲"])
    ws.merge_cells("A1:B1")
    wb.save(path)
    wb.close()
    with pytest.raises(RosterError) as ei:
        import_roster_xlsx(path)
    assert ei.value.code == "merged_cells"


def test_student_id_float_integer_ok(tmp_path: Path) -> None:
    from openpyxl import Workbook

    path = tmp_path / "sid.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["序号", "学号", "姓名"])
    ws.append([1, 2026001.0, "甲"])
    wb.save(path)
    wb.close()
    cands = import_roster_xlsx(path)
    assert cands[0].student_id == "2026001"


def test_student_id_non_integer_float_rejected(tmp_path: Path) -> None:
    from openpyxl import Workbook

    path = tmp_path / "sid2.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["序号", "学号", "姓名"])
    ws.append([1, 1.5, "甲"])
    wb.save(path)
    wb.close()
    with pytest.raises(RosterError) as ei:
        import_roster_xlsx(path)
    assert ei.value.code == "student_id_not_text"


def test_export_score_scale(tmp_path: Path) -> None:
    path = tmp_path / "scores.xlsx"
    row = ExamResultRow(
        candidate=ExamCandidate(1, "S1", "张三", "一班"),
        status="completed",
        front_score=0.823,
        side_score=0.901,
        combined_score=0.86,
        combined_percent=86,
    )
    write_scorebook_xlsx(path, [row])
    from openpyxl import load_workbook

    wb = load_workbook(path)
    ws = wb.active
    values = [c.value for c in next(ws.iter_rows(min_row=2, max_row=2))]
    assert values[4] == 86
    assert values[5] == 82.3
    assert values[6] == 90.1
    wb.close()


def test_scoring_policy_last_completed_wins() -> None:
    book = ExamScorebook(path=None)
    c = ExamCandidate(1, "S1", "张三")
    book.load_candidates([c])
    r1 = book.rows[0]
    book.update_row(
        r1,
        status="completed",
        front_score=0.5,
        side_score=0.5,
        combined_score=0.5,
        combined_percent=50,
    )
    r2 = book.append_retest(c)
    book.update_row(
        r2,
        status="completed",
        front_score=0.9,
        side_score=0.9,
        combined_score=0.9,
        combined_percent=90,
    )
    scoring = book.scoring_rows()
    assert len(scoring) == 1
    assert scoring[0].combined_percent == 90
    assert r1.status == "superseded"
    assert r1.is_scoring_row is False
    assert r2.is_scoring_row is True
