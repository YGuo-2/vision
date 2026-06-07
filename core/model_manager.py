# -*- coding: utf-8 -*-
"""MediaPipe 模型清单与下载管理（供 UI「设置 → 模型管理」使用）。

为什么需要它
------------
打包成单文件 exe 后，模型文件不再随程序分发。用户首次使用前需要把 MediaPipe 的
``.task`` 模型放到可执行文件同级的 ``models/`` 目录下（见 ``core.paths.models_dir()``）。
本模块集中维护：

- 每个模型的官方下载地址（``storage.googleapis.com``，Google 官方资产）。
- 模型在本地的目标路径与「是否已安装」状态查询。
- 带进度回调、可中断的下载实现（下载到 ``.part`` 临时文件后原子改名，避免半成品被
  误判为已安装）。

约束
----
- 仅依赖标准库 + ``core.paths``，不导入 mediapipe / cv2 等重依赖，便于 UI 早期加载与单测。
- 下载源固定使用官方直链；国内访问受限属于用户网络环境问题，由 UI 文案提示用户自行解决
  （代理 / 加速等），本模块不内置镜像。
"""

from __future__ import annotations

import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from core.paths import models_dir

# MediaPipe 官方模型资产基址。
_MP_BASE = "https://storage.googleapis.com/mediapipe-models"

# 进度回调签名：progress_cb(downloaded_bytes, total_bytes_or_None)。
ProgressCb = Callable[[int, int | None], None]


@dataclass(frozen=True)
class ModelSpec:
    """单个可下载模型的描述。

    - key:       稳定标识（用于 UI 选择 / 日志）。
    - filename:  落盘到 ``models/`` 下的文件名（与 ``vision_pipeline`` 加载时一致）。
    - url:       官方下载直链。
    - label:     UI 显示名。
    - approx_mb: 体积估计（仅用于 UI 提示，可为 None）。
    """

    key: str
    filename: str
    url: str
    label: str
    approx_mb: float | None = None


# 目前仅提供 MediaPipe 模型（按用户要求，本期只放 MediaPipe 下载选项）。
MEDIAPIPE_MODELS: tuple[ModelSpec, ...] = (
    ModelSpec(
        key="pose_lite",
        filename="pose_landmarker_lite.task",
        url=f"{_MP_BASE}/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task",
        label="人体姿态 - lite（轻量，最快）",
        approx_mb=5.5,
    ),
    ModelSpec(
        key="pose_full",
        filename="pose_landmarker_full.task",
        url=f"{_MP_BASE}/pose_landmarker/pose_landmarker_full/float16/latest/pose_landmarker_full.task",
        label="人体姿态 - full（默认，均衡）",
        approx_mb=9.0,
    ),
    ModelSpec(
        key="pose_heavy",
        filename="pose_landmarker_heavy.task",
        url=f"{_MP_BASE}/pose_landmarker/pose_landmarker_heavy/float16/latest/pose_landmarker_heavy.task",
        label="人体姿态 - heavy（最准，最慢）",
        approx_mb=29.2,
    ),
    ModelSpec(
        key="hand",
        filename="hand_landmarker.task",
        url=f"{_MP_BASE}/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task",
        label="手部关键点 - hand_landmarker（V 手势 / 手部骨架）",
        approx_mb=7.5,
    ),
)


def model_path(spec: ModelSpec) -> Path:
    """返回模型在本地 ``models/`` 目录下的目标路径。"""
    return models_dir() / spec.filename


def is_installed(spec: ModelSpec) -> bool:
    """模型是否已安装（文件存在且非空）。"""
    p = model_path(spec)
    return p.exists() and p.stat().st_size > 0


def installed_size_mb(spec: ModelSpec) -> float | None:
    """返回已安装模型的大小（MB）；未安装返回 None。"""
    p = model_path(spec)
    if p.exists() and p.stat().st_size > 0:
        return round(p.stat().st_size / (1024 * 1024), 1)
    return None


def download_model(
    spec: ModelSpec,
    *,
    progress_cb: ProgressCb | None = None,
    should_stop: Callable[[], bool] | None = None,
    chunk_size: int = 64 * 1024,
    timeout: float = 30.0,
) -> Path:
    """下载单个模型到 ``models/``。

    - 先写入同目录下的 ``<filename>.part`` 临时文件，完成后原子改名为正式文件名，
      避免中断产生的半成品被 ``is_installed`` 误判为已安装。
    - ``progress_cb(downloaded, total)``：total 可能为 None（服务器未返回 Content-Length）。
    - ``should_stop()`` 返回 True 时中断下载并删除 ``.part``，抛出 ``InterruptedError``。

    返回正式文件路径。任何网络异常向上抛出，由调用方（UI）展示并提示用户自行处理网络问题。
    """
    dest = model_path(spec)
    part = dest.with_suffix(dest.suffix + ".part")
    dest.parent.mkdir(parents=True, exist_ok=True)

    req = urllib.request.Request(spec.url, headers={"User-Agent": "vision-ui/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec - official model asset
            total: int | None
            cl = resp.headers.get("Content-Length")
            total = int(cl) if cl and cl.isdigit() else None
            downloaded = 0
            if progress_cb:
                progress_cb(0, total)
            with open(part, "wb") as fh:
                while True:
                    if should_stop is not None and should_stop():
                        raise InterruptedError("下载已取消")
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    fh.write(chunk)
                    downloaded += len(chunk)
                    if progress_cb:
                        progress_cb(downloaded, total)
    except BaseException:
        # 清理半成品。
        try:
            if part.exists():
                part.unlink()
        except OSError:
            pass
        raise

    # 原子替换为正式文件。
    os.replace(part, dest)
    return dest
