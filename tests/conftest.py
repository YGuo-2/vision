# -*- coding: utf-8 -*-
"""全局测试隔离。

历史事故：部分测试（如 test_second_dual_segment_...）走真实 App 录制路径，
其中 ``_begin_recording_segment`` 会调 ``save_record_dir`` 把 pytest 临时目录
写进仓库根真实 ``user_prefs.json``，导致用户下次启动录制目录回退到不存在的
临时地址。这里 autouse 把 ``core.paths._prefs_path`` 钉到临时文件，任何测试都
无法再污染真实偏好文件——不必逐个测试补 monkeypatch。
"""
from __future__ import annotations

import pytest

from core import paths


@pytest.fixture(autouse=True)
def _isolate_user_prefs(tmp_path_factory, monkeypatch):
    prefs = tmp_path_factory.mktemp("user_prefs") / "user_prefs.json"
    monkeypatch.setattr(paths, "_prefs_path", lambda: prefs)
