# -*- coding: utf-8 -*-
"""摄像头枚举器测试：Property 1/2/3 属性测试 + probe_camera 示例测试。

probe 通过注入，不接触真实摄像头硬件，保证确定性。
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest
from hypothesis import given, settings, strategies as st

# 确保仓库根目录在 sys.path 上（与项目其它入口一致）。
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apps.camera_enum import (  # noqa: E402
    SCAN_LIMIT_MAX,
    SCAN_LIMIT_MIN,
    CameraEntry,
    clamp_scan_limit,
    enumerate_cameras,
    make_label,
    probe_camera,
)


def _clamp(n: int) -> int:
    return max(SCAN_LIMIT_MIN, min(n, SCAN_LIMIT_MAX))


# Feature: camera-dropdown-selection, Property 1: 枚举结果等于可用编号与扫描范围的交集（升序、去重）
@settings(max_examples=200)
@given(
    available=st.sets(st.integers(min_value=0, max_value=40)),
    scan_limit=st.integers(min_value=-10, max_value=50),
)
def test_property1_enumerate_equals_intersection(available: set[int], scan_limit: int) -> None:
    probe = lambda i: i in available  # noqa: E731
    no_names = lambda: []  # noqa: E731
    result = [e.index for e in enumerate_cameras(scan_limit, probe, no_names)]
    expected = sorted(i for i in available if 0 <= i <= _clamp(scan_limit))
    assert result == expected
    # 无设备名时 CameraEntry 的 label 回退为 make_label(index)。
    for e in enumerate_cameras(scan_limit, probe, no_names):
        assert isinstance(e, CameraEntry)
        assert e.label == make_label(e.index)


# Feature: camera-dropdown-selection, enumerate_cameras 注入设备名时 label 含友好名
def test_enumerate_uses_device_names() -> None:
    probe = lambda i: True  # noqa: E731
    names = lambda: ["前置摄像头", "USB 外接"]  # noqa: E731
    entries = enumerate_cameras(3, probe, names)
    assert entries[0].label == "摄像头 0: 前置摄像头"
    assert entries[1].label == "摄像头 1: USB 外接"
    # 设备名列表越界的索引回退为无名格式。
    assert entries[2].label == "摄像头 2"


# Feature: camera-dropdown-selection, Property 2: 扫描上限被钳制到 [1, 32]
@settings(max_examples=200, deadline=None)
@given(scan_limit=st.integers(min_value=-1000, max_value=1000))
def test_property2_scan_limit_clamped(scan_limit: int) -> None:
    probed: list[int] = []

    def spy(i: int) -> bool:
        probed.append(i)
        return False

    no_names = lambda: []  # noqa: E731
    enumerate_cameras(scan_limit, spy, no_names)
    assert probed  # 至少探测了一个编号
    assert min(probed) == 0
    assert max(probed) == _clamp(scan_limit)
    assert _clamp(scan_limit) == max(1, min(scan_limit, 32))


# Feature: camera-dropdown-selection, Property 3: 显示文本与编号一一对应且非空
@settings(max_examples=200)
@given(indices=st.lists(st.integers(min_value=0, max_value=1000), unique=True))
def test_property3_make_label_injective_nonempty(indices: list[int]) -> None:
    labels = [make_label(i) for i in indices]
    for lbl in labels:
        assert isinstance(lbl, str) and lbl.strip() != ""
    # 单射：不同编号产生不同文本。
    assert len(set(labels)) == len(indices)


# ---- probe_camera 示例测试（mock cv2.VideoCapture，不接触真实硬件） ----


def _make_cap(opened: bool, read_return):
    cap = mock.MagicMock()
    cap.isOpened.return_value = opened
    cap.read.return_value = read_return
    return cap


def test_probe_camera_not_opened() -> None:
    import numpy as np

    cap = _make_cap(False, (False, None))
    with mock.patch("cv2.VideoCapture", return_value=cap):
        assert probe_camera(0) is False
    cap.release.assert_called_once()


def test_probe_camera_opened_empty_frame() -> None:
    import numpy as np

    # frame 为 None
    cap1 = _make_cap(True, (True, None))
    with mock.patch("cv2.VideoCapture", return_value=cap1):
        assert probe_camera(0) is False
    cap1.release.assert_called_once()

    # frame 存在但 size==0
    empty = np.empty((0,), dtype="uint8")
    cap2 = _make_cap(True, (True, empty))
    with mock.patch("cv2.VideoCapture", return_value=cap2):
        assert probe_camera(0) is False
    cap2.release.assert_called_once()


def test_probe_camera_opened_valid_frame() -> None:
    import numpy as np

    frame = np.zeros((4, 4, 3), dtype="uint8")
    cap = _make_cap(True, (True, frame))
    with mock.patch("cv2.VideoCapture", return_value=cap):
        assert probe_camera(0) is True
    cap.release.assert_called_once()


def test_probe_camera_timeout() -> None:
    import time

    import numpy as np

    cap = mock.MagicMock()
    cap.isOpened.return_value = True

    def slow_read():
        time.sleep(5.0)
        return (True, np.zeros((4, 4, 3), dtype="uint8"))

    cap.read.side_effect = slow_read
    with mock.patch("cv2.VideoCapture", return_value=cap):
        # 超时阈值很短：应判不可用且不阻塞过久。
        start = time.perf_counter()
        result = probe_camera(0, timeout_s=0.2)
        elapsed = time.perf_counter() - start
    assert result is False
    assert elapsed < 2.0


def test_probe_camera_exception_released() -> None:
    cap = mock.MagicMock()
    cap.isOpened.return_value = True
    cap.read.side_effect = RuntimeError("driver error")
    with mock.patch("cv2.VideoCapture", return_value=cap):
        assert probe_camera(0) is False
    cap.release.assert_called_once()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
