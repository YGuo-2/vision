# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

import numpy as np

from core.exam_clip import (
    align_frame_counts,
    estimate_action_range,
    estimate_action_range_from_feature_seq,
    prepare_exam_pair,
)


def test_align_frame_counts_min() -> None:
    n, warnings = align_frame_counts(100, 97)
    assert n == 97
    assert any("frame_align" in w for w in warnings)


def test_estimate_action_range_fallback_time() -> None:
    start, end, warnings = estimate_action_range(
        90, fps=30.0, energy=None, trim_head_s=0.5, trim_tail_s=0.8
    )
    assert start == 15  # 0.5*30
    assert end == 90 - 24  # 0.8*30
    assert end > start


def test_estimate_action_range_from_motion_features() -> None:
    # 头尾静止、中段运动
    t, j = 120, 4
    feats = np.zeros((t, j, 2), dtype=np.float32)
    for i in range(40, 80):
        feats[i, :, 0] = (i - 40) * 0.05
    start, end, _ = estimate_action_range_from_feature_seq(feats, fps=30.0)
    assert start < 50
    assert end > 70


def test_prepare_exam_pair_aligns_and_writes(tmp_path: Path) -> None:
    import cv2

    def write_video(path: Path, n: int, color: tuple[int, int, int]) -> None:
        w, h = 64, 48
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        wr = cv2.VideoWriter(str(path), fourcc, 30.0, (w, h))
        for i in range(n):
            # 中段加噪声形成能量
            fr = np.full((h, w, 3), color, dtype=np.uint8)
            if 20 <= i < 50:
                fr = (fr + np.random.randint(0, 40, fr.shape, dtype=np.uint8)).clip(0, 255).astype(
                    np.uint8
                )
            wr.write(fr)
        wr.release()

    front = tmp_path / "front.mp4"
    side = tmp_path / "side.mp4"
    write_video(front, 60, (10, 10, 10))
    write_video(side, 55, (20, 20, 20))
    out = tmp_path / "out"
    result = prepare_exam_pair(
        front,
        side,
        front_frames=60,
        side_frames=55,
        out_dir=out,
        trim_head_s=0.2,
        trim_tail_s=0.2,
    )
    assert result.front_frames == result.side_frames
    assert result.front_frames > 0
    assert result.front_path.is_file()
    assert result.side_path.is_file()
    assert any("frame_align" in w for w in result.warnings)
