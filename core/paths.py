# -*- coding: utf-8 -*-
"""仓库级 artifact 根目录统一解析（YOLO 迁移 S1 / Issue #6）。

为什么需要它
------------
此前 ``models`` / ``templates`` / ``outputs`` 三个顶层产物目录散落在各模块里，
各自用 ``Path(__file__).resolve().parent / "models"`` 之类的写法推导。由于
``__file__`` 锚点随所在包不同（``core/`` 解析成 ``core/models``、``apps/`` 解析成
``apps/models`` ……），同一类产物会指向不同位置，既容易踩坑又难以维护。

本模块把三个根目录的解析集中收口到唯一入口，统一锚定到**仓库根**
（即 ``core/`` 包目录的父目录，``Path(__file__).resolve().parents[1]``）：
  - ``models_dir()``     → ``<repo_root>/models``
  - ``templates_dir()``  → ``<repo_root>/templates``
  - ``outputs_dir()``    → ``<repo_root>/outputs``

约束
----
- 仅依赖标准库 ``pathlib``，不导入 ``pose_features`` / ``action_compare`` 等业务模块，
  避免循环依赖；任何入口（core/apps/batch/analysis）都能安全 import。
- ``templates_dir`` / ``outputs_dir`` 在返回前 ``mkdir(parents=True, exist_ok=True)``。
- ``models_dir`` 仅保证目录存在（``mkdir(exist_ok=True)``），**不会删除/移动**任何已有
  模型文件；MediaPipe 缺失的 ``.task`` 由 ``MediaPipePipeline`` 自动下载补齐。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


_CAMERA_SELECTION_PREF_KEY = "camera_selection"


def repo_root() -> Path:
    """返回 artifact 根目录。

    - 源码运行：``core/`` 包目录的父目录（仓库根）。
    - PyInstaller 冻结运行：可执行文件所在目录。此时 ``__file__`` 指向临时解压目录
      （``sys._MEIPASS``），不能用来定位 models/templates/outputs，否则运行结束目录被清空。
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def models_dir() -> Path:
    """返回 ``<repo_root>/models`` 并确保其存在（不触碰已有模型文件）。"""
    d = repo_root() / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d


def templates_dir() -> Path:
    """返回 ``<repo_root>/templates`` 并确保其存在。"""
    d = repo_root() / "templates"
    d.mkdir(parents=True, exist_ok=True)
    return d


def outputs_dir() -> Path:
    """返回 ``<repo_root>/outputs`` 并确保其存在。"""
    d = repo_root() / "outputs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _prefs_path() -> Path:
    return repo_root() / "user_prefs.json"


def _load_user_prefs() -> dict[str, Any]:
    try:
        data = json.loads(_prefs_path().read_text(encoding="utf-8"))
        return dict(data) if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_user_prefs(data: dict[str, Any]) -> None:
    try:
        _prefs_path().write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass


def _camera_index(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def load_camera_selection() -> tuple[int | None, int | None]:
    """读取主/次摄像头索引；损坏或旧格式配置按未设置处理。"""
    raw = _load_user_prefs().get(_CAMERA_SELECTION_PREF_KEY)
    if not isinstance(raw, dict):
        return None, None
    return (
        _camera_index(raw.get("primary_index")),
        _camera_index(raw.get("secondary_index")),
    )


def save_camera_selection(
    primary_index: int | None,
    secondary_index: int | None,
) -> None:
    """持久化主/次摄像头索引并保留其他用户偏好。"""
    data = _load_user_prefs()
    data[_CAMERA_SELECTION_PREF_KEY] = {
        "primary_index": _camera_index(primary_index),
        "secondary_index": _camera_index(secondary_index),
    }
    _save_user_prefs(data)


def load_record_dir() -> Path:
    """读取用户上次选择的录制保存目录；无记录或无效时回退 ``outputs_dir()``。"""
    data = _load_user_prefs()
    saved = str(data.get("record_dir") or "")
    if saved and Path(saved).is_dir():
        return Path(saved)
    return outputs_dir()


def save_record_dir(directory: Path | str) -> None:
    """持久化录制保存目录到 ``user_prefs.json``（尽力而为，失败静默）。"""
    data = _load_user_prefs()
    data["record_dir"] = str(directory)
    _save_user_prefs(data)
