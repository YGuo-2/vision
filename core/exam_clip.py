# -*- coding: utf-8 -*-
"""考试派发前：正侧帧截齐 + 走位/动作段裁剪。

不修改 DualRecordingPostProcessor 的现网 frame_count_mismatch 语义；
考试路径在 submit 前调用本模块。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from core.pose_features import find_active_range, motion_energy


@dataclass
class ClipResult:
    front_path: Path
    side_path: Path
    front_frames: int
    side_frames: int
    warnings: list[str] = field(default_factory=list)
    trim_start: int = 0
    trim_end: int = 0  # exclusive
    meta: dict[str, Any] = field(default_factory=dict)


def align_frame_counts(front_n: int, side_n: int) -> tuple[int, list[str]]:
    """返回截齐后的目标帧数 n = min(front, side)。"""
    warnings: list[str] = []
    front_n = int(front_n)
    side_n = int(side_n)
    if front_n <= 0 or side_n <= 0:
        return 0, ["empty_recording"]
    n = min(front_n, side_n)
    if front_n != side_n:
        warnings.append(
            f"frame_align: front={front_n} side={side_n} -> n={n} (trim longer tail)"
        )
    return n, warnings


def estimate_action_range(
    frame_count: int,
    *,
    fps: float = 30.0,
    energy: np.ndarray | None = None,
    trim_head_s: float = 0.5,
    trim_tail_s: float = 0.8,
) -> tuple[int, int, list[str]]:
    """返回 [start, end) 帧区间（end 不含）。

    优先用 motion energy 活跃段；过平则 fallback 首尾时间裁剪。
    """
    warnings: list[str] = []
    n = int(frame_count)
    if n <= 0:
        return 0, 0, ["empty"]
    fps = float(fps or 30.0)

    if energy is not None and energy.size >= 5:
        # find_active_range 基于 T-1 的 energy，返回含端点；转半开
        s, e_incl = find_active_range(np.asarray(energy, dtype=np.float32), pad=10)
        # energy 长度 T-1 → 帧索引约 s..e_incl+1
        start = max(0, int(s))
        end = min(n, int(e_incl) + 2)
        if end - start >= max(8, int(0.5 * fps)):
            return start, end, warnings
        warnings.append("motion_range_too_short_fallback_time_trim")

    head = int(round(trim_head_s * fps))
    tail = int(round(trim_tail_s * fps))
    start = min(head, max(0, n // 4))
    end = max(start + 1, n - tail)
    if end <= start:
        start, end = 0, n
        warnings.append("trim_collapsed_use_full")
    else:
        warnings.append(f"time_trim: drop head~{head}f tail~{tail}f -> [{start},{end})")
    return start, end, warnings


def energy_from_gray_frames(frames: list[np.ndarray]) -> np.ndarray:
    """简易帧差能量，供无 pose 特征时裁剪。"""
    if len(frames) < 2:
        return np.zeros(0, dtype=np.float32)
    diffs: list[float] = []
    prev = cv2.cvtColor(frames[0], cv2.COLOR_BGR2GRAY).astype(np.float32)
    for fr in frames[1:]:
        g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY).astype(np.float32)
        d = float(np.mean((g - prev) ** 2) ** 0.5)
        diffs.append(d)
        prev = g
    return np.asarray(diffs, dtype=np.float32)


def _read_first_n_frames(path: Path, n: int) -> tuple[list[np.ndarray], float]:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"无法打开视频：{path}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0) or 30.0
    frames: list[np.ndarray] = []
    try:
        while len(frames) < n:
            ok, fr = cap.read()
            if not ok or fr is None:
                break
            frames.append(fr)
    finally:
        cap.release()
    return frames, fps


def _write_frames(path: Path, frames: list[np.ndarray], fps: float) -> Path:
    if not frames:
        raise RuntimeError("无帧可写")
    h, w = frames[0].shape[:2]
    path.parent.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, float(fps), (w, h))
    out = path
    if not writer.isOpened():
        out = path.with_suffix(".avi")
        fourcc = cv2.VideoWriter_fourcc(*"XVID")
        writer = cv2.VideoWriter(str(out), fourcc, float(fps), (w, h))
    if not writer.isOpened():
        raise RuntimeError(f"无法创建视频写出：{path}")
    try:
        for fr in frames:
            writer.write(fr)
    finally:
        writer.release()
    return out

def prepare_exam_pair(
    front_source: Path,
    side_source: Path,
    *,
    front_frames: int,
    side_frames: int,
    out_dir: Path,
    trim_head_s: float = 0.5,
    trim_tail_s: float = 0.8,
    use_pixel_energy: bool = True,
) -> ClipResult:
    """截齐 + 裁剪，写出 front_exam / side_exam。"""
    front_source = Path(front_source)
    side_source = Path(side_source)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    n, warnings = align_frame_counts(front_frames, side_frames)
    if n <= 0:
        raise RuntimeError("录制帧数为 0，无法派发")

    front_frames_list, fps_f = _read_first_n_frames(front_source, n)
    side_frames_list, fps_s = _read_first_n_frames(side_source, n)
    if len(front_frames_list) == 0 or len(side_frames_list) == 0:
        raise RuntimeError("无法读取录制帧")
    # 再按实际读到的帧数二次截齐
    n2 = min(len(front_frames_list), len(side_frames_list))
    if n2 < n:
        warnings.append(f"read_short: expected {n} got front={len(front_frames_list)} side={len(side_frames_list)}")
    front_frames_list = front_frames_list[:n2]
    side_frames_list = side_frames_list[:n2]
    fps = float(fps_f or fps_s or 30.0)

    energy = None
    if use_pixel_energy:
        energy = energy_from_gray_frames(front_frames_list)
    start, end, trim_warnings = estimate_action_range(
        n2,
        fps=fps,
        energy=energy,
        trim_head_s=trim_head_s,
        trim_tail_s=trim_tail_s,
    )
    warnings.extend(trim_warnings)
    front_clip = front_frames_list[start:end]
    side_clip = side_frames_list[start:end]
    if not front_clip or not side_clip:
        front_clip = front_frames_list
        side_clip = side_frames_list
        start, end = 0, n2
        warnings.append("clip_empty_fallback_full")

    front_out = _write_frames(out_dir / "front_exam.mp4", front_clip, fps)
    side_out = _write_frames(out_dir / "side_exam.mp4", side_clip, fps)
    return ClipResult(
        front_path=front_out,
        side_path=side_out,
        front_frames=len(front_clip),
        side_frames=len(side_clip),
        warnings=warnings,
        trim_start=start,
        trim_end=end,
        meta={
            "aligned_n": n2,
            "fps": fps,
            "source_front_frames": front_frames,
            "source_side_frames": side_frames,
        },
    )


def estimate_action_range_from_feature_seq(
    features: np.ndarray,
    *,
    fps: float = 30.0,
    trim_head_s: float = 0.5,
    trim_tail_s: float = 0.8,
) -> tuple[int, int, list[str]]:
    """对 (T, J, 2) 特征序列估活跃区间（单测 / 可选路径）。"""
    if features.ndim != 3 or features.shape[0] < 2:
        return 0, int(getattr(features, "shape", [0])[0] or 0), ["bad_features"]
    seq = features.reshape(features.shape[0], -1).astype(np.float32)
    energy = motion_energy(seq)
    return estimate_action_range(
        features.shape[0],
        fps=fps,
        energy=energy,
        trim_head_s=trim_head_s,
        trim_tail_s=trim_tail_s,
    )
