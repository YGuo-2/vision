# -*- coding: utf-8 -*-
"""core.qwen_coach 契约与 mock HTTP 测试（不依赖本机 llama-server）。"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from core import qwen_coach as qc


def _solid_frame(color: tuple[int, int, int], size: tuple[int, int] = (120, 160)) -> np.ndarray:
    h, w = size
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:] = color
    return img


def _write_tiny_video(path: Path, frames: int = 12, fps: float = 6.0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    h, w = 96, 128
    fourcc = cv2.VideoWriter_fourcc(*"MJPG")
    writer = cv2.VideoWriter(str(path), fourcc, fps, (w, h))
    assert writer.isOpened(), "VideoWriter failed to open"
    try:
        for i in range(frames):
            frame = _solid_frame((i * 10 % 255, 40, 80), size=(h, w))
            writer.write(frame)
    finally:
        writer.release()
    assert path.is_file() and path.stat().st_size > 0
    return path


def test_even_indices_basic():
    assert qc._even_indices(10, 1) == [5]
    assert qc._even_indices(5, 5) == [0, 1, 2, 3, 4]
    idxs = qc._even_indices(100, 6)
    assert len(idxs) == 6
    assert idxs == sorted(idxs)
    assert idxs[0] >= 0 and idxs[-1] < 100


def test_make_contact_sheet_and_jpeg():
    frames = [_solid_frame((i * 20, 10, 200)) for i in range(6)]
    sheet = qc.make_contact_sheet(frames, cols=3)
    assert sheet is not None
    assert sheet.ndim == 3
    blob = qc.encode_jpeg_bgr(sheet)
    assert blob[:2] == b"\xff\xd8"  # JPEG SOI


def test_sample_video_frames(tmp_path: Path):
    video = _write_tiny_video(tmp_path / "clip.avi", frames=15)
    frames = qc.sample_video_frames(video, num_frames=4, max_long_edge=64)
    assert 1 <= len(frames) <= 4
    assert frames[0].shape[0] <= 64 or frames[0].shape[1] <= 64


def test_sample_dual_contact_sheets(tmp_path: Path):
    front = _write_tiny_video(tmp_path / "front.avi")
    side = _write_tiny_video(tmp_path / "side.avi")
    images = qc.sample_dual_contact_sheets(front, side, frames_per_view=4)
    assert len(images) == 1
    assert images[0][:2] == b"\xff\xd8"


def test_resolve_segment_videos(tmp_path: Path):
    d = tmp_path / "record_x"
    d.mkdir()
    _write_tiny_video(d / "front.mp4")
    _write_tiny_video(d / "side.avi")
    front, side = qc.resolve_segment_videos(d)
    assert front is not None and front.name.startswith("front")
    assert side is not None and side.name.startswith("side")


def test_extract_json_object_variants():
    obj = qc.extract_json_object('{"action":"jab","issues":[]}')
    assert obj["action"] == "jab"

    fenced = '好的\n```json\n{"action":"unable_to_judge","issues":[]}\n```\n'
    obj2 = qc.extract_json_object(fenced)
    assert obj2["action"] == "unable_to_judge"

    noisy = '说明：{"action":"jab","summary":"ok","confidence":"high","issues":[]} 结束'
    obj3 = qc.extract_json_object(noisy)
    assert obj3["summary"] == "ok"

    with pytest.raises(ValueError):
        qc.extract_json_object("不是 json")


def test_normalize_whitelist_filter():
    payload = {
        "action": "jab",
        "summary": "有问题",
        "confidence": "medium",
        "issues": [
            {
                "code": "arm_not_extended",
                "problem": "肘未伸直",
                "severity": "轻微",
                "suggestion": "伸直手臂",
                "view_hint": "front",
            },
            {
                "code": "facial_expression",  # 白名单外，应丢弃
                "problem": "表情不对",
                "severity": "轻微",
                "suggestion": "微笑",
                "view_hint": "front",
            },
            {
                "code": "guard_hand_low",
                "problem": "护手低",
                "severity": "中等",
                "suggestion": "抬高护手",
                "view_hint": "side",
            },
        ],
    }
    result = qc.normalize_coach_payload(payload, raw_text="{}")
    assert result.ok
    assert result.action == "jab"
    assert [i.code for i in result.issues] == ["arm_not_extended", "guard_hand_low"]
    assert any("dropped_issues" in w for w in result.warnings)
    text = result.format_display()
    assert "非正式成绩" in text
    assert "分数" not in text
    assert "护手" in text
    # to_dict 不得带模型原文 raw_text
    assert "raw_text" not in result.to_dict()


def test_normalize_unknown_action_fail_closed():
    """非直拳 action 不得显示为成功直拳。"""
    payload = {
        "action": "roundhouse_kick",
        "summary": "看起来不错",
        "confidence": "high",
        "issues": [],
    }
    result = qc.normalize_coach_payload(payload)
    assert result.ok
    assert result.action == "unable_to_judge"
    assert result.issues == []
    assert any("unexpected_action" in w for w in result.warnings)
    text = result.format_display()
    assert "无法评判" in text
    assert "未发现" not in text


def test_normalize_missing_action_fail_closed():
    result = qc.normalize_coach_payload(
        {"summary": "ok", "confidence": "low", "issues": []}
    )
    assert result.action == "unable_to_judge"


def test_normalize_bans_score_and_face_text():
    payload = {
        "action": "jab",
        "summary": "本次得分 95 分，面部表情不自然",
        "confidence": "high",
        "issues": [
            {
                "code": "arm_not_extended",
                "problem": "肘未伸直，得分偏低",
                "severity": "轻微",
                "suggestion": "伸直手臂，不要看面部表情",
                "view_hint": "front",
            }
        ],
    }
    result = qc.normalize_coach_payload(
        payload, raw_text='{"summary":"得分 95 分，面部表情不自然"}'
    )
    assert result.action == "jab"
    assert len(result.issues) == 1
    # 自由摘要含分数/面部 → 丢弃，改用受控模板
    assert "95" not in result.summary
    assert "分" not in result.summary or "改进" in result.summary or "关注" in result.summary
    assert "面部" not in result.summary
    assert "95" not in result.issues[0].problem
    assert "面部" not in result.issues[0].suggestion
    assert "得分" not in result.format_display()
    assert "面部" not in result.format_display()
    # raw 不落盘；内存 raw 也应被清空（含禁用词）
    assert result.raw_text == ""
    dumped = json.dumps(result.to_dict(), ensure_ascii=False)
    assert "95" not in dumped
    assert "raw_text" not in dumped


def test_normalize_jab_with_only_invalid_issues_fail_closed():
    payload = {
        "action": "jab",
        "summary": "表情不好",
        "confidence": "medium",
        "issues": [
            {
                "code": "facial_expression",
                "problem": "表情",
                "severity": "轻微",
                "suggestion": "微笑",
            }
        ],
    }
    result = qc.normalize_coach_payload(payload)
    assert result.action == "unable_to_judge"
    assert result.issues == []


def test_normalize_unable_to_judge_clears_issues():
    payload = {
        "action": "unable_to_judge",
        "summary": "看不清",
        "confidence": "low",
        "issues": [
            {
                "code": "arm_not_extended",
                "problem": "x",
                "severity": "轻微",
                "suggestion": "y",
            }
        ],
    }
    result = qc.normalize_coach_payload(payload)
    assert result.action == "unable_to_judge"
    assert result.issues == []
    assert "无法评判" in result.format_display()


def test_analyze_jab_images_mock_success():
    def fake_http(method, url, body=None, timeout_s=30.0):
        assert method == "POST"
        assert url.endswith("/v1/chat/completions")
        assert body is not None
        assert body["messages"][0]["role"] == "system"
        content = json.dumps(
            {
                "action": "jab",
                "summary": "护手偏低",
                "confidence": "high",
                "issues": [
                    {
                        "code": "guard_hand_low",
                        "problem": "非击打侧手过低",
                        "severity": "中等",
                        "suggestion": "抬至下颌高度",
                        "view_hint": "side",
                    }
                ],
            },
            ensure_ascii=False,
        )
        return {
            "choices": [{"message": {"content": content}}],
        }

    img = qc.encode_jpeg_bgr(_solid_frame((10, 20, 30)))
    result = qc.analyze_jab_images([img], http_json=fake_http)
    assert result.ok
    assert result.action == "jab"
    assert len(result.issues) == 1
    assert result.issues[0].code == "guard_hand_low"
    assert result.latency_s is not None


def test_analyze_jab_images_service_unavailable():
    def boom(method, url, body=None, timeout_s=30.0):
        raise ConnectionError("unreachable:refused")

    result = qc.analyze_jab_images(
        [qc.encode_jpeg_bgr(_solid_frame((1, 2, 3)))],
        http_json=boom,
    )
    assert not result.ok
    assert result.error_code == "service_unavailable"
    assert "8091" in (result.error_message or "")


def test_analyze_jab_images_empty_media():
    result = qc.analyze_jab_images([])
    assert not result.ok
    assert result.error_code == "empty_media"


def test_analyze_jab_images_bad_json():
    def fake_http(method, url, body=None, timeout_s=30.0):
        return {"choices": [{"message": {"content": "完全不是 JSON"}}]}

    result = qc.analyze_jab_images(
        [qc.encode_jpeg_bgr(_solid_frame((1, 2, 3)))],
        http_json=fake_http,
    )
    assert not result.ok
    assert result.error_code == "bad_json"


def test_analyze_jab_segment_writes_coach_json(tmp_path: Path):
    d = tmp_path / "record_1"
    d.mkdir()
    _write_tiny_video(d / "front.avi")
    _write_tiny_video(d / "side.avi")

    def fake_http(method, url, body=None, timeout_s=30.0):
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "action": "jab",
                                "summary": "合格",
                                "confidence": "medium",
                                "issues": [],
                            },
                            ensure_ascii=False,
                        )
                    }
                }
            ]
        }

    result = qc.analyze_jab_segment(d, http_json=fake_http, save_coach_json=True)
    assert result.ok
    coach_path = d / "coach.json"
    assert coach_path.is_file()
    data = json.loads(coach_path.read_text(encoding="utf-8"))
    assert data["ok"] is True
    assert "score" not in data
    assert data["issues"] == []


def test_analyze_jab_segment_missing_videos(tmp_path: Path):
    d = tmp_path / "empty"
    d.mkdir()
    result = qc.analyze_jab_segment(d)
    assert not result.ok
    assert result.error_code == "invalid_video"


def test_prompt_contains_whitelist_and_no_score_instruction():
    sys_p = qc.build_jab_system_prompt()
    for code in qc.JAB_ISSUE_CODES:
        assert code in sys_p
    assert "分数" in sys_p
    assert "unable_to_judge" in sys_p


def test_resolve_base_url_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("QWEN_COACH_BASE_URL", raising=False)
    assert qc.resolve_base_url() == qc.DEFAULT_BASE_URL
    monkeypatch.setenv("QWEN_COACH_BASE_URL", "http://127.0.0.1:9000/")
    assert qc.resolve_base_url() == "http://127.0.0.1:9000"
    assert qc.resolve_base_url("http://x:1/") == "http://x:1"
