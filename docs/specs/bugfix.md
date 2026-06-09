# 缺陷修复规范 (Bugfix Specification)

> **问题名称：** Vue/Tauri 迁移最终验收缺口修复
> **版本：** v1.0
> **状态：** 已批准
> **严重级别：** P1
> **影响环境：** 本地 Windows 桌面开发与打包验证
> **最后更新：** 2026-06-09

---

## 1. 问题概述

Vue + Tauri + Vite 前端迁移在 `docs/specs/tasks.md` 中已被标记为完成，但 Spce workflow 最终验收的 12 个审查单元均发现可执行缺口或证据同步问题。主要影响是新 Vue/Tauri 前端尚未完整覆盖现有 Tkinter 用户可见功能，且 bridge 协议、停止语义、前端交互和 Windows 启动/打包证据不足。

本次修复目标是恢复已批准设计中的预期行为：后端核心算法不迁移、不改变 MediaPipe 默认路径，前端通过 Tauri bridge 调用既有 Python 后端，并在 Windows-only 范围内补齐 Tkinter 功能覆盖、协议可靠性和验证证据。

---

## 2. 证据与复现

### 2.1 观察到的现象

- 最终验收第一轮和第二轮子 agent 审查确认 T-001 至 T-012 均存在缺口或证据不足。
- `frontend/src/App.vue` 中“动作分析...”按钮不可触发，缺少 `template.create`、`analysis.run`、直拳技术评估、模型下载、下载取消和完整设置窗口流程。
- `apps/ui_backend.py` 的错误解析路径会把可恢复的原始 `requestId` 改成 `"unknown"`，Tauri pending 请求无法匹配。
- `BridgeJobManager.stop()` 对已完成 job 仍返回成功，停止语义与契约不一致。
- 实时会话未做帧预览节流，Vue 事件处理未按当前 `sessionId/jobId` 过滤，`job.completed` 可能错误影响运行态。
- `tasks.md`、`progress.md`、`design.md`、`requirements.md` 的头部状态与实际批准/完成状态不同步。

### 2.2 复现路径

1. 查看 `frontend/src/App.vue`，确认动作分析按钮没有 `@click`，且搜索不到前端 `template.create` / `analysis.run` 调用。
2. 查看 `frontend/src/App.vue` 和 `frontend/src`，确认模型区域只刷新 `model.status`，没有 `model.download`、下载全部、进度和取消入口。
3. 向 `apps.ui_backend.handle_line()` 输入带 `requestId` 的错误命令或非对象 payload，响应会返回 `requestId: "unknown"`。
4. 创建已完成 job 后调用 `BridgeJobManager.stop()`，当前会返回 `True` 并设置 stop flag。
5. 查看 Vue 事件处理，确认 `session.status`、`session.frame`、`record.status`、`job.completed/job.stopped` 未过滤当前会话或任务。
6. 查看 `docs/specs/tasks.md` 头部，确认仍显示 `Draft`、`T-001`、`0 / 12`，与正文完成记录冲突。

### 2.3 自动复现状态与替代证据

- **自动复现状态：** 部分可自动复现。
- **不可自动复现原因：** Tauri dev-mode 启动、安装后主窗口启动、目录选择对话框和完整前端交互需要 Windows GUI 或等价 Playwright/Vite/Tauri smoke；当前缺口先由只读静态审查和已有测试缺失证明约束。
- **替代证据：** 12 个子 agent 对抗审查结论、`rg` 静态检索、现有 backend tests 通过但前端路径缺失、已有 `npm run verify:desktop` 只构建 Vue 不测交互。
- **证据强度与限制：** 证据足以证明已声明完成的功能不可触达或验证不足；实现后仍必须补自动化测试和至少一条 Windows 运行级证据，降低 GUI smoke 的人工判断风险。

### 2.4 第一波最终验收新增发现

- B-002 agent 发现 manifest 仍只列 flat request 字段，未显式表达 `jobId/sessionId` 可选语义；TS envelope 类型未允许 Python/Rust 实际输出的 `null`。
- B-004 agent 发现 Rust Shell32 目录选择器使用 `BIF_NEWDIALOGSTYLE` 和 `SHBrowseForFolderW`，但调用前缺少 COM/OLE 初始化，Windows 打包运行时可能静默失败。
- B-006 agent 发现 `core/model_manager.py` 在 HTTP `Content-Length` 已知但实际读取不足时仍会 `os.replace(.part, dest)`，半成品可能被误判为已安装；Vue unmount 只停止 session，未取消 active 模型下载。
- B-008/B-010 agent 发现 active spec 仍有以 moving HEAD 表达的提交范围，最终验收证据不可稳定复查。
- 重新进入 final acceptance 后，B-008 agent 发现 docs sync commit `3aa2578` 未纳入 active progress/task 证据链，且 B-017 grep 命令使用了不完整写法，仍影响文档可追溯性。
- 第三轮第一波 B-016 agent 发现 Vue unmount 取消 active 模型下载虽然已实现，但测试仍停留在 marker 覆盖，缺少真实 `job.stop` payload/options 行为断言。
- 第四轮第一波 B-003 agent 发现当前实时识别 job 若异步发出 `job.failed`，Vue 只写错误文本，不会清理 `isRunning` 与运行态文案。

### 2.5 影响范围

- **受影响模块：** `frontend/src/`, `frontend/src-tauri/src/lib.rs`, `apps/ui_backend.py`, `scripts/verify-desktop-stack.ps1`, `tests/`, `docs/specs/`, `change.md`
- **受影响用户：** 使用新 Vue/Tauri Windows 桌面前端的本地用户和维护者
- **受影响版本：** commit `3657f7a` (`feat: add vue tauri desktop frontend`)

---

## 3. 当前错误行为 (Current Behavior)

### BUG-001: Bridge 协议和停止语义不可靠

- **WHEN** Python bridge 遇到解析错误或未知命令
- **THEN** 响应可能丢失原始 `requestId`，Tauri pending 请求无法归位。
- **WHEN** 用户停止已完成 job
- **THEN** `job.stop` 仍可能返回成功，停止语义被误报。
- **WHEN** 前端展示 raw JSON
- **THEN** 只展示 payload，缺少完整 envelope、error、jobId/sessionId、timestamp。

### BUG-002: 实时会话状态和前端运行态可能被污染

- **WHEN** bridge 高频发送 `session.frame`
- **THEN** Vue 每帧渲染，违反 NFR-002 的节流要求。
- **WHEN** 旧会话或非当前 job 事件迟到
- **THEN** Vue 可能更新当前预览、录制状态或运行态。
- **WHEN** 摄像头或未知总帧输入运行
- **THEN** 进度文本可能长期停在 `0%`，给出误导性状态。

### BUG-003: 录制目录未完整迁移 Tkinter 能力

- **WHEN** 用户想选择录制保存目录
- **THEN** Vue 只允许手动输入目录，没有 Tkinter 等价的目录选择按钮。
- **WHEN** 使用默认录制目录
- **THEN** Vue 默认传入相对路径 `outputs`，可能偏离 Tkinter 的绝对 artifact 目录默认值。

### BUG-004: 动作分析和直拳技术评估在 Vue 端不可触达

- **WHEN** 用户需要创建模板、选择已有模板、设置目标视频、起止帧、worker 或导出匹配预览
- **THEN** Vue 没有对应表单和 `template.create` / `analysis.run` 调用。
- **WHEN** 用户需要启用直拳技术评估、设置站姿/视角/调试视频并查看四类指标、原因类型、失败环节
- **THEN** Vue 没有可见入口和结构化结果展示。

### BUG-005: 设置窗口和模型管理能力未完整迁移

- **WHEN** 用户打开设置或查看模型状态
- **THEN** Vue 未提供 settings view/modal，且不展示模型目录、逐模型路径、文件大小和安装状态。
- **WHEN** 用户下载单模型或全部缺失模型
- **THEN** Vue 没有下载、下载全部、字节进度、完成/失败展示和取消入口。

### BUG-006: 验证集合、Windows 启动证据和文档状态不同步

- **WHEN** 运行 `npm run verify:desktop`
- **THEN** 只构建 Vue，不验证 Vue 用户交互、Tauri 协议边界或完整 raw JSON 语义。
- **WHEN** 查看任务记录和规范状态
- **THEN** 部分文档仍显示 Draft、0/12、草稿或旧 commit，和完成/批准状态冲突。
- **WHEN** 审查 Windows 打包证据
- **THEN** 已有证据证明 installer 和 sidecar ping，但未证明 dev-mode 启动、安装后主窗口启动或缺模型时 packaged UI 下载入口。

---

## 4. 修复后的期望行为 (Expected Behavior)

### FIX-001: Bridge envelope、错误和停止语义稳定

- **WHEN** bridge 出错或任务停止
- **THEN** 前端收到可匹配的 `requestId`、明确错误摘要和完整 raw JSON envelope；`job.stop` 只对活动 job 成功。

### FIX-002: 实时会话 UI 与当前会话一致

- **WHEN** 多个 session/job 事件交错到达
- **THEN** Vue 只处理当前 `sessionId/jobId` 的相关事件，高频帧预览被节流，未知总帧进度显示为非误导性状态。

### FIX-003: 录制目录行为等价 Tkinter

- **WHEN** 用户选择录制目录或使用默认目录
- **THEN** Vue 提供目录选择能力，并默认使用与 Tkinter 一致的 artifact 输出目录语义。

### FIX-004: 动作分析和技术评估可在 Vue 中完成

- **WHEN** 用户执行模板生成、模板比对或直拳技术评估
- **THEN** Vue 提供完整表单、调用 Python bridge、展示匹配分数/片段/预览导出/JSON 和技术评估指标。

### FIX-005: 设置窗口和模型下载流程可用

- **WHEN** 用户打开设置
- **THEN** Vue 展示模型目录、逐模型安装状态、路径、大小、缺失状态，并支持刷新、单模型下载、全部缺失下载、进度和取消。

### FIX-006: 验证与文档证据可信

- **WHEN** 运行桌面验证与最终验收
- **THEN** 验证集合包含 Vue 交互/协议测试、Python 回归、Tauri/Rust 检查、Windows 打包 smoke 和明确运行级证据；文档状态与实际审批/任务状态一致。

---

## 5. 必须保持不变的行为 (Unchanged Behavior)

### SAFE-001: Python 后端核心算法不迁移

- **WHEN** 修复前端或 bridge 问题
- **THEN** `core/vision_pipeline.py`、`core/action_compare.py`、`analysis/tech_eval.py` 的 MediaPipe 默认路径、`pose33_v3` golden、`infer()` / `annotate()` 默认行为保持不变。

### SAFE-002: YOLO 边界保持不变

- **WHEN** 修复动作分析或技术评估前端
- **THEN** 不把 YOLO-only 接入正式 tech_eval 分数，不改变 YOLO 迁移阶段边界。

### SAFE-003: Tkinter 旧入口继续可用

- **WHEN** 用户运行 `.\.venv\Scripts\python.exe apps/app_ui.py`
- **THEN** 旧 Tkinter UI 仍可启动，不因新前端修复被删除或破坏。

### SAFE-004: Windows-only 和安全边界不扩大

- **WHEN** Tauri 调用 Python bridge、文件选择或 sidecar
- **THEN** 只开放迁移所需能力，不引入任意 shell 命令入口或跨平台承诺。

---

## 6. 范围与约束

### 修复范围内

- Python bridge 的协议 envelope、错误 `requestId` 保留、job stop 活动态语义和 manifest/parity 测试。
- Vue/Tauri 前端的主窗口、录制目录、动作分析、技术评估、设置/模型管理、raw JSON 和事件过滤。
- 验证脚本、前端测试、Windows 打包/启动 smoke、文档状态和 `change.md`。

### 明确不在范围内

- 重写视觉算法、评分算法、模板匹配算法或 MediaPipe pipeline。
- 新增跨平台支持。
- 将 YOLO adapter 接入正式技术评估或对外评分。
- 删除 Tkinter UI。

### 约束与假设

- 修复前必须获得审批短语 `批准规范，启动执行`。
- 本地缺少依赖可安装，但联网下载按仓库代理约定走 `127.0.0.1:7890`。
- 对 GUI 无法完全自动化的验证，必须记录替代证据和限制，不能把 pre-acceptance 当 final acceptance。

---

## 7. 风险与回滚提示

- **主要风险：** 前端补齐多个 Tkinter 功能面，可能引入状态耦合、事件过滤错误、路径兼容或打包资源缺失。
- **回滚方式：** 回退本次 bugfix commit；旧 Tkinter 入口保留作为运行替代；不回退后端核心算法。
- **观察指标：** `npm run verify:desktop`、前端交互测试、Python bridge tests、golden/valid_mask 回归、Windows packaging smoke、final acceptance 子 agent 审查。

---

## 8. 审批记录

| 日期 | 审批人 | 决定 | 备注 |
|:---|:---|:---|:---|
| 2026-06-09 | 用户 | 批准 | `批准规范，启动执行` |
