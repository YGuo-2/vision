# 任务清单 (Task Breakdown)

> **功能名称：** Tkinter 双摄录制后自动比对
> **关联规范：** `product.md` · `architecture.md`
> **状态：** Completed
> **当前任务：** n/a
> **进度：** 4 / 4 已完成
> **最后更新：** 2026-07-10 02:01:18

---

## 执行规则

1. 批准后先运行 `spec_progress.py approve <specs_dir> --evidence "批准规范，启动执行"` 冻结基线。
2. 每个任务必须先通过 progress 工具 start，验证通过并记录证据后才能 complete。
3. 只能开始依赖已完成的第一个未完成任务；规范或任务计划变更必须重新批准。
4. 不覆盖当前工作区的用户修改，不使用宽泛暂存或破坏性 Git 命令。
5. final acceptance 问题写入 `acceptance-fixes.md`，不修改已冻结任务正文。

---

## 阶段 1：核心资源与取消语义

- [x] **T-001:** 加固转码取消和 MediaPipe 特征提取资源释放
  - 状态: done
  - 验证证据: pytest tests/test_video_writer_transcode.py tests/test_compare_dual_streams.py -q: 17 passed; py_compile passed; git diff --check passed
  - 完成时间: 2026-07-09 23:47:07
  - 备注: n/a
  - 涉及文件: `core/video_writer.py`, `core/action_compare.py`, `tests/test_video_writer_transcode.py`, `tests/test_compare_dual_streams.py`
  - 验证命令: `.\.venv\Scripts\python.exe -m pytest tests/test_video_writer_transcode.py tests/test_compare_dual_streams.py -q`
  - 依赖: 无
  - 风险: medium
  - 覆盖: AC-004.1, AC-004.2, NFR-005
  - 可并行: 否
  - 验证标准: ffmpeg 可被事件取消且无临时文件；单线程特征提取在成功、异常、取消时释放 cap/pipeline；取消不返回部分评分。
  - 预估工程量: 1-2 小时

---

## 阶段 2：后处理协调器与结果契约

- [x] **T-002:** 实现双摄片段 FIFO 后处理、固定模板预检和原子 `result.json`
  - 状态: done
  - 验证证据: pytest tests/test_recording_postprocess.py tests/test_template_metadata.py tests/test_compare_dual_streams.py -q: 26 passed; py_compile passed; git diff --check passed
  - 完成时间: 2026-07-09 23:57:51
  - 备注: n/a
  - 涉及文件: `apps/recording_postprocess.py`, `tests/test_recording_postprocess.py`, `.gitignore`, `templates/standard_front_full.npz`, `templates/standard_side_full.npz`
  - 验证命令: `.\.venv\Scripts\python.exe -m pytest tests/test_recording_postprocess.py tests/test_template_metadata.py tests/test_compare_dual_streams.py -q`
  - 依赖: T-001
  - 风险: medium
  - 覆盖: AC-001.3, AC-002.3, AC-003.1, AC-003.2, NFR-001, NFR-002, NFR-003
  - 可并行: 否
  - 验证标准: submit 非阻塞、严格 FIFO/单并发/去重；转码汇合与 AVI 回退正确；模板/model/video 校验正确；所有终态 JSON 原子且 schema 完整；一个任务失败后继续下一个。
  - 预估工程量: 2-3 小时

- [x] **T-003:** 接入 Tkinter 双摄骨架开关、统一片段收尾和最新结果 UI
  - 状态: done
  - 验证证据: pytest T-003 focused suite: 122 passed; py_compile passed; git diff --check passed; lifecycle and postprocess audits found no remaining P1/P2
  - 完成时间: 2026-07-10 01:43:27
  - 备注: n/a
  - 涉及文件: `apps/app_ui.py`, `tests/test_app_controls.py`, `tests/test_app_ui_dual_camera.py`, `tests/test_app_ui_lifecycle.py`
  - 验证命令: `.\.venv\Scripts\python.exe -m pytest tests/test_app_controls.py tests/test_app_ui_dual_camera.py tests/test_app_ui_lifecycle.py tests/test_recording_controller.py tests/test_recording_postprocess.py -q`
  - 依赖: T-002
  - 风险: high
  - 覆盖: US-001, US-002, US-003, US-004, NFR-001, NFR-002, NFR-004
  - 可并行: 否
  - 验证标准: 开关默认关闭且只影响双摄；原始/标注帧路由正确；显式结束、主停止、错误和 finally 统一收尾且只提交一次；下一段可立即开始；旧结果不覆盖新片段；关窗取消且无 Tk 晚回调。
  - 预估工程量: 3-4 小时

---

## 阶段 3：回归与交付证据

- [x] **T-004:** 执行跨模块回归、现场验收准备并更新变更记录
  - 状态: done
  - 验证证据: targeted regression: 177 passed; full pytest: 529 passed and the same 6 unrelated ui_backend baseline failures; real ffmpeg/ffprobe H.264 smoke passed; py_compile and git diff checks passed; change.md updated; fixed templates staged
  - 完成时间: 2026-07-10 02:01:18
  - 备注: n/a
  - 涉及文件: `change.md`, 本任务相关测试文件
  - 验证命令: `.\.venv\Scripts\python.exe -m pytest tests/test_recording_postprocess.py tests/test_app_controls.py tests/test_app_ui_dual_camera.py tests/test_app_ui_lifecycle.py tests/test_recording_controller.py tests/test_video_writer_transcode.py tests/test_compare_dual_streams.py tests/test_template_metadata.py tests/test_pose33_v3_golden.py -q`; `.\.venv\Scripts\python.exe -m pytest tests -q`; `git diff --check`
  - 依赖: T-003
  - 风险: medium
  - 覆盖: 全部 US/AC/NFR
  - 可并行: 否
  - 验证标准: 定向套件全绿；全量测试相对接手基线零新增失败；语法与 whitespace 检查通过；`change.md` 置顶记录修改、验证和实机待验事项；准备双摄连续两段、主停止、骨架跳过三条实机脚本。
  - 预估工程量: 1-2 小时

---

## 执行 Waves

| Wave | 任务 | 说明 |
|:---|:---|:---|
| 1 | T-001 | 先冻结取消和资源释放契约 |
| 2 | T-002 | 基于稳定核心实现独立后处理服务 |
| 3 | T-003 | 接入共享 `app_ui.py`，单独审查并发状态机 |
| 4 | T-004 | 统一回归、文档和现场验收准备 |

---

## 风险标记

| 任务 ID | 风险类别 | 风险描述 | 审查要求 |
|:---|:---|:---|:---|
| T-001 | 进程/资源 | ffmpeg、VideoCapture、MediaPipe 取消和释放 | 覆盖成功/失败/取消路径 |
| T-002 | 并发/数据一致性 | FIFO、去重、JSON 原子性、失败隔离 | 单消费者并发测试 |
| T-003 | UI/并发 | Tk 主线程、录制锁、多个停止入口和 late callback | 单独执行并跑生命周期测试 |
| T-004 | 回归 | 当前分支已有在制品和已知全量失败 | 对比接手基线，禁止误清理用户修改 |

---

## 完成日志

| 任务 ID | 完成时间 | Commit Hash | 验证证据 | 备注 |
|:---|:---|:---|:---|:---|
| T-001 | 2026-07-09 23:47:07 | 2776ddb | pytest tests/test_video_writer_transcode.py tests/test_compare_dual_streams.py -q: 17 passed; py_compile passed; git diff --check passed | n/a |
| T-002 | 2026-07-09 23:57:52 | 2776ddb | pytest tests/test_recording_postprocess.py tests/test_template_metadata.py tests/test_compare_dual_streams.py -q: 26 passed; py_compile passed; git diff --check passed | n/a |
| T-003 | 2026-07-10 01:43:27 | 2776ddb | pytest T-003 focused suite: 122 passed; py_compile passed; git diff --check passed; lifecycle and postprocess audits found no remaining P1/P2 | n/a |
| T-004 | 2026-07-10 02:01:18 | 2776ddb | targeted regression: 177 passed; full pytest: 529 passed and the same 6 unrelated ui_backend baseline failures; real ffmpeg/ffprobe H.264 smoke passed; py_compile and git diff checks passed; change.md updated; fixed templates staged | n/a |
