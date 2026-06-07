# -*- coding: utf-8 -*-
"""摄像头枚举与输入源状态模型。

本模块不依赖 tkinter，便于独立单元测试与属性测试：
- `enumerate_cameras` 的探测函数 `probe` 可注入，给定 probe 后输出完全确定。
- `InputSourceState` 是纯状态结构，维护摄像头/视频/无 三态互斥不变式。

真实的 OpenCV DSHOW I/O 集中在 `probe_camera`，单测时可被替换。
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable

# 扫描上限与探测超时（见 requirements.md 需求 1.5 / 1.7）
DEFAULT_SCAN_LIMIT = 5
SCAN_LIMIT_MIN = 1
SCAN_LIMIT_MAX = 32
PROBE_TIMEOUT_S = 2.0


@dataclass(frozen=True)
class CameraEntry:
    """下拉菜单中的单个摄像头条目。"""

    label: str  # 面向用户的显示文本，如 "摄像头 0"
    index: int  # 传给 cv2.VideoCapture 的非负整数编号


def make_label(index: int, name: str | None = None) -> str:
    """由编号（及可选设备名）生成显示文本。需求 2.2。

    - 提供设备名时返回如 ``"摄像头 0: 1080P USB Camera"``；
    - 缺省（拿不到设备名）时回退为 ``"摄像头 0"``。
    编号与文本保持一一对应（同一组枚举内编号唯一即可保证文本唯一）。
    """
    name = (name or "").strip()
    if name:
        return f"摄像头 {index}: {name}"
    return f"摄像头 {index}"


def list_device_names() -> list[str]:
    """读取 Windows DirectShow 摄像头友好名列表，顺序与 DSHOW 索引一致。

    依赖 pygrabber（仅 Windows）。任何失败都返回空列表，由调用方回退到
    "摄像头 N" 命名，保证枚举功能在缺少该依赖时仍可用。
    """
    try:
        from pygrabber.dshow_graph import FilterGraph

        return list(FilterGraph().get_input_devices())
    except Exception:
        return []


def clamp_scan_limit(scan_limit: int) -> int:
    """将扫描上限钳制到 [SCAN_LIMIT_MIN, SCAN_LIMIT_MAX]。需求 1.7。"""
    return max(SCAN_LIMIT_MIN, min(int(scan_limit), SCAN_LIMIT_MAX))


def probe_camera(index: int, timeout_s: float = PROBE_TIMEOUT_S) -> bool:
    """探测单个编号是否可用。

    判定可用 = `isOpened()` 为真且能 `read()` 到非空帧；带超时与资源释放。
    需求 1.2、1.3、1.5、1.6。该函数封装真实 cv2 I/O，单测时可被替换。
    """
    import cv2  # 延迟导入，避免无 cv2 环境下导入本模块失败

    result: dict[str, bool] = {"ok": False}

    def _work() -> None:
        cap = None
        try:
            cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
            if not cap.isOpened():
                result["ok"] = False
                return
            ok, frame = cap.read()
            result["ok"] = bool(
                ok and frame is not None and getattr(frame, "size", 0) > 0
            )
        except Exception:
            # 驱动错误等：视为不可用（需求 1.3）。
            result["ok"] = False
        finally:
            # 无论成功与否都释放资源（需求 1.6）。
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass

    worker = threading.Thread(target=_work, daemon=True)
    worker.start()
    worker.join(timeout_s)
    if worker.is_alive():
        # 探测超时：判不可用并继续（需求 1.5）。底层线程为 daemon，
        # 会在打开/读取返回后自行结束并释放资源。
        return False
    return bool(result["ok"])


def open_camera(index: int, *, width: int = 1280, height: int = 720):
    """打开摄像头并协商一个高帧率的采集格式。

    背景：在 Windows 上用 ``cv2.CAP_DSHOW`` 打开摄像头，请求 720p 时很多设备会
    退回到未压缩的 YUY2 像素格式。YUY2 受 USB 带宽限制，720p 往往只能跑到 ~10fps，
    导致主循环长时间阻塞在 ``cap.read()`` 上、CPU 利用率极低、整体 FPS 被采集端拖死。

    本 helper 优先用 ``CAP_MSMF`` 后端（通常能协商到压缩格式，720p 满 30fps），
    失败再回退到 ``CAP_DSHOW`` + 强制 MJPG，最后回退到朴素 DSHOW。返回已打开的
    ``cv2.VideoCapture``；若全部失败则返回最后一次尝试的 cap（由调用方检查
    ``isOpened()``）。
    """
    import cv2  # 延迟导入，保持本模块在无 cv2 环境下可被导入/测试

    def _try(backend: int, *, mjpg: bool):
        cap = cv2.VideoCapture(int(index), backend)
        if not cap.isOpened():
            return None
        if mjpg:
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(width))
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(height))
        return cap

    # 1) MSMF 默认（最优：本机实测 720p 30fps）。
    cap = _try(cv2.CAP_MSMF, mjpg=False)
    if cap is not None:
        return cap
    # 2) DSHOW + 强制 MJPG（压缩格式，避免 YUY2 带宽瓶颈）。
    cap = _try(cv2.CAP_DSHOW, mjpg=True)
    if cap is not None:
        return cap
    # 3) 最后回退：朴素 DSHOW（即便慢，也优先保证能出图）。
    return cv2.VideoCapture(int(index), cv2.CAP_DSHOW)


def enumerate_cameras(
    scan_limit: int = DEFAULT_SCAN_LIMIT,
    probe: Callable[[int], bool] = probe_camera,
    names: Callable[[], list[str]] = list_device_names,
) -> list[CameraEntry]:
    """从 0 起按编号递增探测至 scan_limit（含），返回升序可用条目列表。

    需求 1.1、1.4、1.7、1.8。
    - scan_limit 被钳制到 [SCAN_LIMIT_MIN, SCAN_LIMIT_MAX]。
    - probe 可注入，便于在不接触真实硬件的情况下做属性测试。
    - names 可注入，返回与 DSHOW 索引顺序一致的设备友好名列表；
      索引越界或拿不到名字时回退为 "摄像头 N"。
    - 返回列表按 index 升序，每个可用 index 至多出现一次。
    """
    upper = clamp_scan_limit(scan_limit)
    try:
        device_names = names()
    except Exception:
        device_names = []
    entries: list[CameraEntry] = []
    for index in range(0, upper + 1):
        if probe(index):
            name = device_names[index] if index < len(device_names) else None
            entries.append(CameraEntry(make_label(index, name), index))
    return entries


class InputSourceState:
    """输入源状态模型：camera / video / none 三态互斥。

    需求 3.3、3.4。不变式：
    - kind == "camera" ⇒ value.isdigit()
    - kind == "video"  ⇒ not value.isdigit()
    - kind == "none"   ⇒ value == ""
    任一时刻至多存在一个生效输入源。
    """

    __slots__ = ("kind", "value")

    def __init__(self) -> None:
        self.kind: str = "none"
        self.value: str = ""

    def select_camera(self, index: int) -> None:
        """选择摄像头编号，清除任何视频残留。需求 3.3。"""
        self.kind = "camera"
        self.value = str(int(index))

    def select_video(self, path: str) -> None:
        """选择视频文件路径，清除摄像头选中语义。需求 3.4。"""
        self.kind = "video"
        self.value = path

    def clear(self) -> None:
        """清除输入源（无生效源）。"""
        self.kind = "none"
        self.value = ""

    def hint_text(self) -> str:
        """当前输入源的指示文本。需求 3.5。"""
        if self.kind == "camera":
            return f"当前输入源：摄像头 {self.value}"
        if self.kind == "video":
            return f"当前输入源：视频文件 {self.value}"
        return "当前输入源：未选择"
