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

from pathlib import Path


def repo_root() -> Path:
    """返回仓库根目录（``core/`` 包目录的父目录）。"""
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
