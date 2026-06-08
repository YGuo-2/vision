# Design-First 任务清单 (Task Breakdown)

> **功能名称：** Vue + Tauri + Vite 桌面前端迁移
> **关联规范：** `docs/specs/design.md` · `docs/specs/requirements.md`
> **状态：** Draft
> **当前任务：** T-001
> **进度：** 0 / 12 已完成
> **最后更新：** 2026-06-08

---

## 执行规则

1. **设计优先：** 任务必须首先满足 `design.md` 中已批准的约束与边界。
2. **受控入口：** 任务开始、完成、阻塞、跳过必须通过 `spec_progress.py` CLI 或 MCP 工具更新。
3. **需求从设计派生：** 若 `requirements.md` 与 `design.md` 冲突，必须暂停实现、更新文档、运行 sync-check 并重新获得批准。
4. **单任务约束：** 每个任务完成后必须记录验证证据，才可标记为完成。
5. **禁止越界：** 不得实现未在 `design.md` 明确支撑的能力。

---

## 阶段 1：脚手架与协议基础 (Design Foundations)

- [x] **T-001:** 建立 Windows-only Vue + Vite + Tauri 前端工程
  - 状态: done
  - 验证证据: npm run build passed in frontend; cargo check passed in frontend/src-tauri after installing Rustup and adding icons/icon.ico
  - 完成时间: 2026-06-08 22:49:11
  - 备注: n/a
  - 涉及文件: `frontend/package.json`, `frontend/vite.config.ts`, `frontend/src/`, `frontend/src-tauri/`
  - 验证命令: `npm run build` from `frontend`; `cargo check` from `frontend/src-tauri`
  - 依赖: 无
  - 风险: medium
  - 覆盖: REQ-001, AC-001.1, AC-001.2, NFR-001
  - 可并行: 否
  - 验证标准: 前端工程能在 Windows 环境构建，且不引入 Python 后端行为变更。
  - 预估工程量: 2-3 小时

- [x] **T-002:** 定义 Python bridge 与 Tauri command 协议
  - 状态: done
  - 验证证据: pytest tests/test_ui_backend_contract.py -q passed (8 tests); cargo check passed with no warnings after public protocol structs
  - 完成时间: 2026-06-08 22:53:56
  - 备注: n/a
  - 涉及文件: `docs/specs/design.md`, `frontend/src-tauri/src/`, `apps/ui_backend.py`, `tests/test_ui_backend_contract.py`
  - 验证命令: `.\.venv\Scripts\python.exe -m pytest tests\test_ui_backend_contract.py -q`
  - 依赖: T-001
  - 风险: high
  - 覆盖: REQ-002, REQ-007, AC-002.1, AC-007.1, AC-007.2, AC-007.3, NFR-003
  - 可并行: 否
  - 验证标准: 命令、事件、错误、jobId、sessionId、停止语义和 raw JSON 字段均有契约测试。
  - 预估工程量: 2-4 小时

- [x] **T-003:** 实现 Python UI bridge 进程和 job 生命周期
  - 状态: done
  - 验证证据: pytest tests/test_ui_backend_contract.py tests/test_ui_backend_jobs.py -q passed (12 tests); cargo check passed
  - 完成时间: 2026-06-08 22:58:31
  - 备注: n/a
  - 涉及文件: `apps/ui_backend.py`, `tests/test_ui_backend_contract.py`, `tests/test_ui_backend_jobs.py`
  - 验证命令: `.\.venv\Scripts\python.exe -m pytest tests\test_ui_backend_contract.py tests\test_ui_backend_jobs.py -q`
  - 依赖: T-002
  - 风险: high
  - 覆盖: REQ-002, REQ-007, AC-002.1, AC-007.1, AC-007.2, AC-007.3
  - 可并行: 否
  - 验证标准: bridge 可启动、执行假任务、发出进度、处理停止、序列化错误并释放 job。
  - 预估工程量: 3-5 小时

---

## 阶段 2：核心桌面能力 (Core Implementation)

- [x] **T-004:** 接入摄像头枚举、输入源状态与实时识别会话
  - 状态: done
  - 验证证据: pytest tests/test_camera_enum.py tests/test_input_source_state.py tests/test_ui_backend_contract.py tests/test_ui_backend_jobs.py tests/test_ui_backend_sessions.py -q passed (34 tests); npm run build passed; cargo check passed
  - 完成时间: 2026-06-08 23:23:50
  - 备注: n/a
  - 涉及文件: `apps/ui_backend.py`, `frontend/src/`, `frontend/src-tauri/src/`, `tests/test_camera_enum.py`, `tests/test_input_source_state.py`
  - 验证命令: `.\.venv\Scripts\python.exe -m pytest tests\test_camera_enum.py tests\test_input_source_state.py -q`; `npm run build`
  - 依赖: T-003
  - 风险: high
  - 覆盖: REQ-003, AC-003.1, AC-003.2, AC-003.3, NFR-002
  - 可并行: 否
  - 验证标准: 摄像头刷新、输入源互斥、开始停止、预览帧事件和资源释放在 headless 契约与前端构建中通过。
  - 预估工程量: 4-6 小时

- [x] **T-005:** 迁移主窗口控制区、预览区、状态区和运行态控件联动
  - 状态: done
  - 验证证据: npm run build passed; cargo check passed; pytest tests/test_app_controls.py tests/test_ui_controls.py -q passed (13 tests); py_compile apps/ui_backend.py apps/app_ui.py passed; Playwright screenshot output/playwright/t005-main.png inspected nonblank with main controls, preview, status areas
  - 完成时间: 2026-06-09 00:21:05
  - 备注: n/a
  - 涉及文件: `frontend/src/`, `tests/test_app_controls.py`, `tests/test_ui_controls.py`
  - 验证命令: `npm run build`; `.\.venv\Scripts\python.exe -m pytest tests\test_app_controls.py tests\test_ui_controls.py -q`
  - 依赖: T-004
  - 风险: medium
  - 覆盖: REQ-003, AC-003.2, AC-003.3
  - 可并行: 否
  - 验证标准: 模型选择、线程数、手部检测开关、开始停止、状态、动作中文标签和进度均可见且状态联动正确。
  - 预估工程量: 3-5 小时

- [x] **T-006:** 接入录制目录、录制三态、结束录制和写盘错误展示
  - 状态: done
  - 验证证据: pytest tests/test_ui_backend_contract.py tests/test_ui_backend_jobs.py tests/test_ui_backend_sessions.py tests/test_recording_controller.py tests/test_app_controls.py -q passed (36 tests); py_compile apps/app_ui.py apps/ui_backend.py core/recording_controller.py passed; npm run build passed
  - 完成时间: 2026-06-08 23:42:28
  - 备注: n/a
  - 涉及文件: `apps/ui_backend.py`, `frontend/src/`, `core/recording_controller.py`, `tests/test_recording_controller.py`, `tests/test_app_controls.py`
  - 验证命令: `.\.venv\Scripts\python.exe -m pytest tests\test_recording_controller.py tests\test_app_controls.py -q`; `npm run build`
  - 依赖: T-004
  - 风险: high
  - 覆盖: REQ-004, AC-004.1, AC-004.2, AC-004.3
  - 可并行: 是
  - 验证标准: idle、recording、paused 三态和保存路径展示与 Tkinter 行为一致。
  - 预估工程量: 2-4 小时

---

## 阶段 3：动作分析与模型管理 (Full Feature Coverage)

- [x] **T-007:** 迁移动作分析窗口的模板生成与模板比对能力
  - 状态: done
  - 验证证据: pytest tests/test_ui_backend_analysis.py tests/test_ui_backend_contract.py tests/test_ui_backend_jobs.py -q passed (15 tests); pytest tests/test_pose33_v3_golden.py tests/test_template_metadata.py -q passed (24 tests); py_compile apps/ui_backend.py core/action_compare.py passed; npm run build passed
  - 完成时间: 2026-06-08 23:49:12
  - 备注: n/a
  - 涉及文件: `apps/ui_backend.py`, `frontend/src/`, `core/action_compare.py`, `tests/test_pose33_v3_golden.py`, `tests/test_template_metadata.py`
  - 验证命令: `.\.venv\Scripts\python.exe -m pytest tests\test_pose33_v3_golden.py tests\test_template_metadata.py -q`; `npm run build`
  - 依赖: T-003
  - 风险: high
  - 覆盖: REQ-005, AC-005.1, AC-005.2, AC-005.4, NFR-005
  - 可并行: 是
  - 验证标准: 模板选择、模板生成、起止帧、worker、匹配分数、匹配片段、预览导出和 JSON 展示可用。
  - 预估工程量: 4-6 小时

- [x] **T-008:** 迁移动作分析窗口的直拳技术评估能力
  - 状态: done
  - 验证证据: pytest tests/test_ui_backend_analysis.py tests/test_tech_eval_contract.py tests/test_pose33_v3_golden.py -q passed (30 tests); py_compile apps/ui_backend.py analysis/tech_eval.py passed; npm run build passed
  - 完成时间: 2026-06-08 23:53:56
  - 备注: n/a
  - 涉及文件: `apps/ui_backend.py`, `frontend/src/`, `analysis/tech_eval.py`, `tests/test_tech_eval_contract.py`, `tests/test_pose33_v3_golden.py`
  - 验证命令: `.\.venv\Scripts\python.exe -m pytest tests\test_tech_eval_contract.py tests\test_pose33_v3_golden.py -q`; `npm run build`
  - 依赖: T-003
  - 风险: high
  - 覆盖: REQ-005, AC-005.3, AC-005.4, NFR-005
  - 可并行: 是
  - 验证标准: 站姿、视角、调试视频、四类指标、原因类型、失败环节和 payload 展示与后端输出一致。
  - 预估工程量: 3-5 小时

- [x] **T-009:** 迁移设置窗口和 MediaPipe 模型管理能力
  - 状态: done
  - 验证证据: pytest tests/test_ui_backend_models.py tests/test_ui_backend_contract.py -q passed (12 tests); py_compile apps/ui_backend.py core/model_manager.py passed; npm run build passed
  - 完成时间: 2026-06-09 00:01:48
  - 备注: n/a
  - 涉及文件: `apps/ui_backend.py`, `frontend/src/`, `core/model_manager.py`, `tests/test_ui_backend_models.py`
  - 验证命令: `.\.venv\Scripts\python.exe -m pytest tests\test_ui_backend_models.py -q`; `npm run build`
  - 依赖: T-003
  - 风险: medium
  - 覆盖: REQ-006, AC-006.1, AC-006.2, AC-006.3
  - 可并行: 是
  - 验证标准: 当前模型摘要、单模型下载、全部缺失下载、刷新状态、进度、取消和 `.part` 清理通过测试。
  - 预估工程量: 3-5 小时

---

## 阶段 4：验证、打包与旧入口并存 (Verification)

- [x] **T-010:** 建立前端、Tauri、Python bridge 的自动化验证集合
  - 状态: done
  - 验证证据: npm run verify:desktop passed: frontend build, Tauri cargo check, py_compile apps/app_ui.py apps/ui_backend.py core/vision_pipeline.py, and 106 desktop regression tests passed
  - 完成时间: 2026-06-09 00:25:43
  - 备注: n/a
  - 涉及文件: `frontend/`, `tests/`, `requirements-dev.txt`, `package.json`
  - 验证命令: `npm run build`; `cargo check`; `.\.venv\Scripts\python.exe -m pytest tests -q`
  - 依赖: T-005, T-006, T-007, T-008, T-009
  - 风险: medium
  - 覆盖: REQ-001, REQ-002, REQ-007, NFR-004, NFR-005
  - 可并行: 否
  - 验证标准: 前端构建、Rust 检查、bridge 测试、现有 Python 回归在同一验证清单中通过。
  - 预估工程量: 2-4 小时

- [x] **T-011:** 完成 Windows 打包配置与 sidecar smoke
  - 状态: done
  - 验证证据: npm run package:windows passed and produced frontend/src-tauri/target/release/bundle/nsis/Vision 动作识别与评分_0.1.0_x64-setup.exe; pytest tests/test_windows_packaging_smoke.py -q passed (6 tests); packaged sidecar frontend/src-tauri/resources/vision-ui-backend.exe bridge.ping returned protocol version 1.0
  - 完成时间: 2026-06-09 00:41:40
  - 备注: n/a
  - 涉及文件: `frontend/src-tauri/`, `app_ui.spec`, `app_ui_onefile.spec`, `docs/`, `tests/test_windows_packaging_smoke.py`
  - 验证命令: `npm run tauri build`; `.\.venv\Scripts\python.exe -m pytest tests\test_windows_packaging_smoke.py -q`
  - 依赖: T-010
  - 风险: high
  - 覆盖: REQ-008, AC-008.1, AC-008.2, AC-008.3, NFR-001, NFR-003
  - 可并行: 否
  - 验证标准: Windows 包能启动，sidecar 或 Python bridge 路径正确，中文路径、模型目录和输出目录可用。
  - 预估工程量: 4-8 小时

- [x] **T-012:** 更新文档、`change.md` 和最终回归证据
  - 状态: done
  - 验证证据: README.md AGENTS.md and change.md updated; git diff --check passed with only LF-to-CRLF warnings; py_compile apps/app_ui.py apps/ui_backend.py core/vision_pipeline.py passed; pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py -q passed (31 tests); npm run verify:desktop passed (106 desktop tests); pytest tests/test_windows_packaging_smoke.py -q passed (6 tests)
  - 完成时间: 2026-06-09 00:45:27
  - 备注: n/a
  - 涉及文件: `README.md`, `AGENTS.md`, `change.md`, `docs/specs/`, `frontend/`
  - 验证命令: `git diff --check`; `.\.venv\Scripts\python.exe -m py_compile .\apps\app_ui.py .\apps\ui_backend.py .\core\vision_pipeline.py`; `.\.venv\Scripts\python.exe -m pytest tests\test_pose33_v3_golden.py tests\test_valid_mask_migration.py -q`
  - 依赖: T-011
  - 风险: medium
  - 覆盖: REQ-001, REQ-002, REQ-008, NFR-005
  - 可并行: 否
  - 验证标准: 文档说明新前端运行和打包方式，`change.md` 记录修改日期、问题、修改内容和验证方法，核心回归通过。
  - 预估工程量: 1-2 小时

---

## 执行 Waves

| Wave | 任务 | 说明 |
|:---|:---|:---|
| 1 | T-001 | 先建立前端工程骨架 |
| 2 | T-002 | 固化 bridge 协议 |
| 3 | T-003 | 实现 Python bridge 和 job 生命周期 |
| 4 | T-004 | 接入实时识别会话 |
| 5 | T-005, T-006, T-007, T-008, T-009 | 在 T-004 或 T-003 依赖满足后并行迁移功能面 |
| 6 | T-010 | 汇总自动化验证 |
| 7 | T-011 | Windows 打包和 sidecar smoke |
| 8 | T-012 | 文档、change.md 和最终回归证据 |

---

## 风险标记

| 任务 ID | 风险类别 | 风险描述 | 审查要求 |
|:---|:---|:---|:---|
| T-002 | 架构 / 权限 | Tauri 命令和 Python bridge 决定本地进程、文件路径和错误暴露边界 | 人类深度审查 |
| T-003 | 并发 / 资源释放 | bridge job 生命周期若错误会泄漏进程、线程或摄像头资源 | 单独执行并验证停止路径 |
| T-004 | 性能 / 资源释放 | 高频帧预览和摄像头 worker 可能造成卡顿或资源不释放 | 单独执行并做 smoke |
| T-007 | 回归 / 评分 | 模板匹配必须保持 pose33_v3 golden 不漂移 | 必跑 golden |
| T-008 | 回归 / 评分 | 技术评估指标展示必须只反映后端授权结果 | 必跑 tech_eval 契约 |
| T-011 | 打包 / 路径 | Windows sidecar、模型目录、中文路径和输出目录风险集中 | 人类深度审查 |

---

## 完成日志

| 任务 ID | 完成时间 | Commit Hash | 验证证据 | 备注 |
|:---|:---|:---|:---|:---|
| — | — | — | — | 暂无完成任务 |
