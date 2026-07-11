# 任务清单 (Task Breakdown)

> **功能名称：** Tkinter 双摄快速首屏性能优化
> **关联规范：** `product.md` · `architecture.md`
> **状态：** Completed
> **当前任务：** n/a
> **进度：** 5 / 5 已完成
> **最后更新：** 2026-07-10 18:52:40

---

## 执行规则

1. 批准后先通过 `spec_progress.py approve` 冻结基线，再逐任务 `start` / `complete`。
2. 每个任务完成后必须记录验证证据；规范/任务计划需修改时进入 reapproval-required。
3. 骨架加载期的裸帧不得写盘；正式评分、文件 VIDEO 和前端路径不得改变。
4. final acceptance 发现的问题写入 `acceptance-fixes.md`，不得修改已冻结任务计划。

---

## 阶段 1：预热基础设施

- [x] **T-001:** 实现角色级摄像头预热池与确定性单元测试
  - 状态: done
  - 验证证据: apps/camera_warmup.py + tests/test_camera_warmup.py；pytest 17 passed；py_compile 通过；git diff --check 通过；P1/P2 对抗审查问题已修复
  - 完成时间: 2026-07-10 11:14:12
  - 备注: n/a
  - 涉及文件: `apps/camera_warmup.py`, `tests/test_camera_warmup.py`
  - 验证命令: `.\.venv\Scripts\python.exe -m pytest tests/test_camera_warmup.py -q`; `.\.venv\Scripts\python.exe -m py_compile apps/camera_warmup.py`
  - 依赖: 无
  - 风险: medium
  - 覆盖: US-001, AC-001.1, AC-001.2, AC-001.3, NFR-002, NFR-003, NFR-005
  - 可并行: 否
  - 验证标准: 双 role 并发打开并持续 latest-only；相同 role/index 幂等；选择变化、超时、stop、claim、close 和 generation 全部可确定性验证，无重复 open 或 capture 泄漏。
  - 预估工程量: 2-3 小时

---

## 阶段 2：Tkinter 双摄接入

- [x] **T-002:** 接入双路选择预热、会话复用和结束后重新预热
  - 状态: done
  - 验证证据: CameraWarmupPool dual selector/lifecycle integration; deterministic forward/reverse same-index ownership tests; nonblocking cancel reaper; startup wait uses stop_event and one 5s deadline; pytest 121 passed with 2 known T-003 cases deselected; py_compile and git diff --check passed; adversarial review found no remaining T-002 blocker
  - 完成时间: 2026-07-10 11:47:58
  - 备注: n/a
  - 涉及文件: `apps/app_ui.py`, `tests/test_app_ui_lifecycle.py`, `tests/test_app_ui_dual_camera.py`
  - 验证命令: `.\.venv\Scripts\python.exe -m pytest tests/test_camera_warmup.py tests/test_app_ui_lifecycle.py tests/test_app_ui_dual_camera.py -q`
  - 依赖: T-001
  - 风险: medium
  - 覆盖: US-001, AC-001.1, AC-001.2, AC-001.3, NFR-002, NFR-003
  - 可并行: 否
  - 验证标准: 两个下拉框独立预热；视频/刷新/关窗释放；启动复用 in-flight/ready slot；双摄不再在 worker 内串行 `open_camera`；会话结束后重新预热当前选择。
  - 预估工程量: 2-3 小时

- [x] **T-003:** 实现原子双帧首屏、骨架裸帧过渡、录制门禁和启动指标
  - 状态: done
  - 验证证据: Atomic DualPreviewPacket queue and same-tick Tk render; generation/stage/render barriers; live raw pump during serial pipeline init; recording gate and zero raw writes; startup metrics; stop/close/failure exactly-once; claim bound to expected generations and stop_event; all retirement paths reaped with thread-start rollback; pytest 164 passed; py_compile and diff-check passed; adversarial P1/P2 findings fixed
  - 完成时间: 2026-07-10 18:36:50
  - 备注: n/a
  - 涉及文件: `apps/app_ui.py`, `tests/test_app_ui_dual_camera.py`, `tests/test_app_ui_lifecycle.py`, `tests/test_app_controls.py`
  - 验证命令: `.\.venv\Scripts\python.exe -m pytest tests/test_camera_warmup.py tests/test_app_ui_dual_camera.py tests/test_app_ui_lifecycle.py tests/test_app_controls.py tests/test_recording_controller.py -q`
  - 依赖: T-002
  - 风险: high
  - 覆盖: US-001, US-002, AC-001.1, AC-002.1, AC-002.2, AC-002.3, NFR-001, NFR-003, NFR-004
  - 可并行: 否
  - 验证标准: 两路只通过单个 pair packet 在同一 `_tick` 更新；pipeline 阻塞时裸帧持续；ready 后无晚到裸帧；加载期录制禁用且零写帧；修正骨架关闭却期待 pipeline 的既有测试矛盾。
  - 预估工程量: 3-4 小时

---

## 阶段 3：依赖实验与交付

- [x] **T-004:** 在隔离环境执行 MediaPipe 0.10.31/0.10.35 与 GPU 门控 A/B
  - 状态: done
  - 验证证据: Isolated Python 3.13.9 venv A/B on 6 real videos, 5 warmup + 60 timed frames per case; 0.10.35 CPU failed >=10% gate and peak RSS increased 15-19%; all 12 GPU requests fell back to CPU because Windows build disables GPU; retained mediapipe 0.10.31 and no GPU UI; delegate/S5/golden pytest 35 passed; py_compile and diff-check passed
  - 完成时间: 2026-07-10 18:51:33
  - 备注: n/a
  - 涉及文件: `requirements.txt`（仅达标时）, `docs/mediapipe_gpu_delegate_report.md`, `analysis/bench_annotate_fps.py`（仅测量缺口需要时）, `tests/test_mediapipe_delegate_config.py`（仅契约变化时）
  - 验证命令: `.\.venv\Scripts\python.exe -m analysis.bench_annotate_fps --help`; 隔离 venv 复跑既有样本清单；`.\.venv\Scripts\python.exe -m pytest tests/test_mediapipe_delegate_config.py tests/test_s5_gpu_recheck.py tests/test_pose33_v3_golden.py -q`
  - 依赖: T-003
  - 风险: medium
  - 覆盖: US-003, AC-003.1, AC-003.2, NFR-004
  - 可并行: 否
  - 验证标准: 形成同环境对照表；只有 CPU 相关指标改善 >=10%、退化 <=5% 才升级；只有 GPU 达到 1.30x/1.20x 且 active=gpu 才新增 UI，否则明确 no-go 并保持当前锁定。
  - 预估工程量: 2-3 小时

- [x] **T-005:** 完成回归、真实性能验收说明和 change.md 交付记录
  - 状态: done
  - 验证证据: Final targeted Tkinter/MediaPipe/valid-mask regression 192 passed; earlier warmup/UI/recording suite 164 passed and delegate/benchmark/golden gate 35 passed; py_compile passed; git diff --check passed with CRLF warnings only; change.md updated at top; physical dual-camera 20-run P95 <=0.5s remains explicit hardware acceptance item with built-in timing logs
  - 完成时间: 2026-07-10 18:52:40
  - 备注: n/a
  - 涉及文件: `change.md`, 本 spec progress/evidence
  - 验证命令: `.\.venv\Scripts\python.exe -m py_compile apps/app_ui.py apps/camera_warmup.py core/vision_pipeline.py`; `.\.venv\Scripts\python.exe -m pytest tests/test_s5_hands_toggle.py tests/test_app_ui_dual_camera.py tests/test_app_ui_online_matcher.py tests/test_app_ui_lifecycle.py tests/test_app_controls.py tests/test_recording_controller.py tests/test_mediapipe_delegate_config.py tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py -q`; `git diff --check`
  - 依赖: T-004
  - 风险: medium
  - 覆盖: US-001, US-002, US-003, NFR-001, NFR-003, NFR-004
  - 可并行: 否
  - 验证标准: 自动化回归全绿；真实双摄骨架关/开各 20 次 P95 <=0.5 秒，若当前环境无物理设备则明确保留人工验收项并提供内置计时日志；change.md 最新置顶记录问题、修改和验证。
  - 预估工程量: 1-2 小时

---

## 执行 Waves

| Wave | 任务 | 说明 |
|:---|:---|:---|
| 1 | T-001 | 独立预热基础设施 |
| 2 | T-002 | 接入选择与生命周期 |
| 3 | T-003 | 高风险共享 UI/录制状态改动，单独执行 |
| 4 | T-004 | 依赖实验必须基于稳定实现 |
| 5 | T-005 | 最终回归与交付 |

---

## 风险标记

| 任务 ID | 风险类别 | 风险描述 | 审查要求 |
|:---|:---|:---|:---|
| T-001 | 并发/资源 | reader 取消、capture 转移、generation 竞态 | 确定性并发测试 |
| T-003 | UI/录制/生命周期 | 晚到裸帧、双路非原子显示、加载期误录 | 单独执行并跑完整 Tkinter 定向回归 |
| T-004 | 依赖/兼容性 | Windows wheel、GPU 支持、数值与打包漂移 | 阈值门控，不达标不得落地 |

---

## 完成日志

| 任务 ID | 完成时间 | Commit Hash | 验证证据 | 备注 |
|:---|:---|:---|:---|:---|
| T-001 | 2026-07-10 11:14:12 | a3a605f | apps/camera_warmup.py + tests/test_camera_warmup.py；pytest 17 passed；py_compile 通过；git diff --check 通过；P1/P2 对抗审查问题已修复 | n/a |
| T-002 | 2026-07-10 11:47:58 | a3a605f | CameraWarmupPool dual selector/lifecycle integration; deterministic forward/reverse same-index ownership tests; nonblocking cancel reaper; startup wait uses stop_event and one 5s deadline; pytest 121 passed with 2 known T-003 cases deselected; py_compile and git diff --check passed; adversarial review found no remaining T-002 blocker | n/a |
| T-003 | 2026-07-10 18:36:50 | a3a605f | Atomic DualPreviewPacket queue and same-tick Tk render; generation/stage/render barriers; live raw pump during serial pipeline init; recording gate and zero raw writes; startup metrics; stop/close/failure exactly-once; claim bound to expected generations and stop_event; all retirement paths reaped with thread-start rollback; pytest 164 passed; py_compile and diff-check passed; adversarial P1/P2 findings fixed | n/a |
| T-004 | 2026-07-10 18:51:33 | a3a605f | Isolated Python 3.13.9 venv A/B on 6 real videos, 5 warmup + 60 timed frames per case; 0.10.35 CPU failed >=10% gate and peak RSS increased 15-19%; all 12 GPU requests fell back to CPU because Windows build disables GPU; retained mediapipe 0.10.31 and no GPU UI; delegate/S5/golden pytest 35 passed; py_compile and diff-check passed | n/a |
| T-005 | 2026-07-10 18:52:40 | a3a605f | Final targeted Tkinter/MediaPipe/valid-mask regression 192 passed; earlier warmup/UI/recording suite 164 passed and delegate/benchmark/golden gate 35 passed; py_compile passed; git diff --check passed with CRLF warnings only; change.md updated at top; physical dual-camera 20-run P95 <=0.5s remains explicit hardware acceptance item with built-in timing logs | n/a |
