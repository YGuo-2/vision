# -*- coding: utf-8 -*-
"""
compare_dual_streams 单测（issue #55，为 #56 打底）。

复用 tests/fixtures/pose33_v3 的已提交 raw fixture + golden_harness 确定性回放，
不新建 fixture。front_src_raw.npz / side_src_raw.npz 本身就是各自单视角的独立源，
正好当作“两路独立同步流”的输入，不需要 frontness 拆分。

覆盖 review 指出的三个回归风险：
1. 正/侧路径调反（channel routing reversed）；
2. 误重新启用 view split（segment 应恒为整段 (0, n-1)）；
3. raw cache 串流（每路 extract_pose_raw_series 只应各自调用一次）。
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import core.action_compare as ac  # noqa: E402
from tests import golden_harness as H  # noqa: E402

FIX_DIR = Path(__file__).resolve().parent / "fixtures" / "pose33_v3"
FRONT_TPL = FIX_DIR / "front_template.npz"
SIDE_TPL = FIX_DIR / "side_template.npz"

FRONT_SRC = "golden://front_src.mp4"
SIDE_SRC = "golden://side_src.mp4"
FPS = 30.0


def _load_raw(name: str) -> np.ndarray:
    d = np.load(FIX_DIR / name, allow_pickle=True)
    return np.asarray(d["landmarks"], dtype=np.float32)


@pytest.fixture()
def registered_videos():
    assert FRONT_TPL.exists() and SIDE_TPL.exists(), (
        "缺少模板 fixture，请先运行 tests/fixtures/regen_pose33_v3_golden.py 生成。"
    )
    H.clear_registry()
    H.register_video(FRONT_SRC, _load_raw("front_src_raw.npz"), fps=FPS)
    H.register_video(SIDE_SRC, _load_raw("side_src_raw.npz"), fps=FPS)
    yield
    H.clear_registry()


def test_no_split_and_high_score_for_matching_streams(registered_videos):
    front_n = int(_load_raw("front_src_raw.npz").shape[0])
    side_n = int(_load_raw("side_src_raw.npz").shape[0])

    with H.replay_context():
        res = ac.compare_dual_streams(
            FRONT_TPL,
            SIDE_TPL,
            FRONT_SRC,
            SIDE_SRC,
            pose_variant="full",
            enable_rules=True,
            enable_error_analysis=True,
        )

    # 无 frontness 拆分：segment 恒为整段 (0, n-1)，两路长度可各不相同。
    assert res.front_segment == (0, front_n - 1)
    assert res.side_segment == (0, side_n - 1)
    # 模板正是从这两段源视频生成，同源比对应接近满分。
    assert res.front_score > 0.9
    assert res.side_score > 0.9
    assert res.front_rule_violations is not None
    assert res.side_rule_violations is not None
    assert res.front_joint_errors is not None
    assert res.side_joint_errors is not None


def test_swapped_streams_score_worse_than_correct_pairing(registered_videos):
    """正确配对应明显优于把 front/side 视频喂反，防止通道接反的回归。"""
    with H.replay_context():
        correct = ac.compare_dual_streams(FRONT_TPL, SIDE_TPL, FRONT_SRC, SIDE_SRC, pose_variant="full")
        swapped = ac.compare_dual_streams(FRONT_TPL, SIDE_TPL, SIDE_SRC, FRONT_SRC, pose_variant="full")

    assert correct.front_score > swapped.front_score
    assert correct.side_score > swapped.side_score


def test_raw_series_extracted_once_per_stream_no_cross_contamination(registered_videos, monkeypatch):
    """独立 raw_series 闭包必须分别绑定各自视频路径：各调用一次、路径不串流。"""
    calls: list[Path] = []
    orig = ac.extract_pose_raw_series

    def spy(video_path, *, pose_variant):
        calls.append(Path(video_path))
        return orig(video_path, pose_variant=pose_variant)

    monkeypatch.setattr(ac, "extract_pose_raw_series", spy)

    with H.replay_context():
        ac.compare_dual_streams(
            FRONT_TPL,
            SIDE_TPL,
            FRONT_SRC,
            SIDE_SRC,
            pose_variant="full",
            enable_rules=True,
            enable_error_analysis=True,
        )

    assert calls.count(Path(FRONT_SRC)) == 1
    assert calls.count(Path(SIDE_SRC)) == 1
