# 需求规范 (Requirements Derived from Design)

> **功能名称：** Vue + Tauri + Vite 桌面前端迁移
> **来源设计：** `docs/specs/design.md`
> **版本：** v1.0
> **状态：** 草稿
> **最后更新：** 2026-06-08

---

## 1. 概述

这些需求由 `docs/specs/design.md` 派生，用于把现有 Python/Tkinter 桌面前端迁移为 Windows-only 的 Vue + Vite + Tauri 应用。用户将获得与当前 Tkinter 完整等价的桌面操作能力，同时现有 Python 后端、视觉算法、评分逻辑和输出契约保持不变。

---

## 2. Analyze Requirements / 需求分析结论

- **歧义检查：** “后端不动”已定义为不重写、不替换、不改变现有 Python 核心行为；允许新增薄的 Python UI bridge 作为前端适配层。“完整覆盖”已定义为覆盖当前 Tkinter 主窗口、动作分析窗口、设置和模型管理窗口的用户可见能力。“只做 win”已定义为仅支持 Windows 本机开发、运行和打包验收。
- **设计一致性：** 下列需求均由 `design.md` 的三层结构、目标系统边界和强约束派生；未新增跨平台发布、算法迁移或评分授权能力。
- **冲突检查：** Vue/Tauri 前端迁移与 Python 后端不动不冲突，因为 Tauri 只管理窗口、命令、事件和进程，Python bridge 调用现有后端函数。完整覆盖与分阶段实施不冲突，因为任务拆分允许分阶段完成，但最终验收必须覆盖全部 Tkinter 功能。
- **失败路径：** 需求覆盖摄像头不可用、视频路径无效、模型缺失、下载失败、长任务停止、子进程退出、录制写盘失败、中文路径、打包路径和事件流中断。并发风险集中在 Python bridge job 管理、停止信号、帧事件节流和资源释放。权限和安全边界集中在 Tauri 文件选择、sidecar 启动和本地路径访问。
- **Quick Plan 跳过原因：** n/a

---

## 3. 功能需求与验收标准

### REQ-001: Windows-only Vue + Vite + Tauri 工程

**作为** 桌面用户，**我希望** 使用新的 Tauri 桌面应用，**以便** 获得替代 Tkinter 的现代前端。

#### 验收标准

- **AC-001.1:**
  - **GIVEN** 仓库根目录没有前端脚手架
  - **WHEN** 完成脚手架任务
  - **THEN** `frontend/` 包含 Vue、Vite、Tauri、TypeScript 和 Windows 桌面配置，并能在 Windows 开发模式启动。

- **AC-001.2:**
  - **GIVEN** 用户运行构建命令
  - **WHEN** 前端执行生产构建
  - **THEN** Vue 构建和 Tauri Rust 检查均通过，锁文件固定实际依赖版本。

### REQ-002: Python 后端保持不动

**作为** 项目维护者，**我希望** 新前端只通过 Python bridge 使用既有能力，**以便** 防止视觉算法和评分结果漂移。

#### 验收标准

- **AC-002.1:**
  - **GIVEN** 新前端需要姿态识别、模板匹配、技术评估、模型下载或录制能力
  - **WHEN** Vue/Tauri 发起操作
  - **THEN** Python bridge 调用现有 Python 模块完成工作，不在 Rust、TypeScript 或浏览器端重写算法。

- **AC-002.2:**
  - **GIVEN** 完成任一前端迁移任务
  - **WHEN** 运行 Python 回归验证
  - **THEN** `pose33_v3` golden、`valid_mask` 相关测试和被触及模块的 `py_compile` 通过。

### REQ-003: 主窗口实时识别完整覆盖

**作为** 桌面用户，**我希望** 在新前端完成摄像头或视频源选择、模型选择、开始停止、预览和状态查看，**以便** 替代 Tkinter 主窗口。

#### 验收标准

- **AC-003.1:**
  - **GIVEN** Windows 上存在可用摄像头
  - **WHEN** 用户刷新摄像头列表
  - **THEN** 前端展示由 `enumerate_cameras` 返回的 label 和 index，并保持 camera/video/none 输入源互斥。

- **AC-003.2:**
  - **GIVEN** 用户选择输入源、pose 模型、线程数和手部检测开关
  - **WHEN** 用户点击开始
  - **THEN** Python bridge 启动识别会话，前端展示预览帧、动作中文标签、状态、FPS 或进度。

- **AC-003.3:**
  - **GIVEN** 识别会话正在运行
  - **WHEN** 用户点击停止或关闭窗口
  - **THEN** Python bridge 停止 worker、释放摄像头或视频资源，前端控件恢复可操作状态。

### REQ-004: 录制控制完整覆盖

**作为** 桌面用户，**我希望** 在识别会话中开始、暂停、继续和结束录制，**以便** 保存识别过程视频。

#### 验收标准

- **AC-004.1:**
  - **GIVEN** 识别会话未运行
  - **WHEN** 用户查看录制控件
  - **THEN** 录制按钮不可用，文本为“开始录制”。

- **AC-004.2:**
  - **GIVEN** 识别会话正在运行
  - **WHEN** 用户连续点击录制按钮
  - **THEN** 状态按 idle、recording、paused、recording 循环，按钮文本分别为“开始录制”、“暂停录制”、“继续录制”、“暂停录制”。

- **AC-004.3:**
  - **GIVEN** 用户选择了录制保存目录且有录制帧写入
  - **WHEN** 用户点击结束录制或停止识别
  - **THEN** 后端释放 writer，前端展示实际保存路径或写盘错误。

### REQ-005: 动作分析完整覆盖

**作为** 桌面用户，**我希望** 在新前端完成模板生成、模板比对和直拳技术评估，**以便** 替代 Tkinter 动作分析窗口。

#### 验收标准

- **AC-005.1:**
  - **GIVEN** 用户启用模板比对并选择已有模板
  - **WHEN** 用户选择目标视频并开始分析
  - **THEN** 前端展示匹配分数、匹配片段、可选预览导出路径和原始 JSON。

- **AC-005.2:**
  - **GIVEN** 用户选择从基准视频生成模板
  - **WHEN** 用户设置 pose 模型、线程数、起始帧和结束帧后提交
  - **THEN** Python bridge 调用 `create_template_from_video`，前端展示模板路径和进度。

- **AC-005.3:**
  - **GIVEN** 用户启用直拳技术评估
  - **WHEN** 用户选择站姿、视角和调试视频选项后提交
  - **THEN** 前端展示重心、回收速度、发力顺序、拳面角度、原因类型、失败环节和可选调试视频路径。

- **AC-005.4:**
  - **GIVEN** 用户同时启用模板比对和直拳技术评估
  - **WHEN** 分析完成
  - **THEN** 单次结果 payload 同时包含 match 与 tech_eval 数据，前端可复制格式化 JSON。

### REQ-006: 设置与模型管理完整覆盖

**作为** 桌面用户，**我希望** 在新前端查看当前模型状态并下载缺失模型，**以便** 替代 Tkinter 设置窗口。

#### 验收标准

- **AC-006.1:**
  - **GIVEN** 用户打开设置
  - **WHEN** 前端请求模型状态
  - **THEN** 展示当前模型目录、MediaPipe 模型安装状态、文件大小和缺失状态。

- **AC-006.2:**
  - **GIVEN** 存在未安装模型
  - **WHEN** 用户下载单个模型或全部缺失模型
  - **THEN** Python bridge 使用 `model_manager.download_model` 下载，前端展示字节进度、完成路径或失败原因。

- **AC-006.3:**
  - **GIVEN** 下载中窗口关闭或用户触发取消
  - **WHEN** Python bridge 收到停止请求
  - **THEN** `.part` 半成品被清理，正式模型文件不会被误判为已安装。

### REQ-007: Bridge 命令、事件与错误契约

**作为** 前端和后端维护者，**我希望** 有稳定的 JSON 命令和事件协议，**以便** 前端迁移可测试、可恢复、可打包。

#### 验收标准

- **AC-007.1:**
  - **GIVEN** Tauri 发起 bridge 命令
  - **WHEN** Python bridge 返回成功、进度、帧事件或错误
  - **THEN** 所有消息都包含 type、jobId 或 sessionId、payload、timestamp 和 error 字段语义。

- **AC-007.2:**
  - **GIVEN** Python bridge 遇到异常
  - **WHEN** 异常被序列化到前端
  - **THEN** 前端展示中文错误摘要，并保留 raw JSON 供调试。

- **AC-007.3:**
  - **GIVEN** 长任务正在执行
  - **WHEN** 用户停止任务
  - **THEN** bridge 设置 stop event，任务结束后回传 stopped 或 error，不留下活动 job。

### REQ-008: Windows 打包与路径兼容

**作为** Windows 用户，**我希望** 安装或运行包能调用 Python 后端并访问模型、模板和输出目录，**以便** 新前端能独立使用。

#### 验收标准

- **AC-008.1:**
  - **GIVEN** Windows 打包产物已生成
  - **WHEN** 用户启动应用
  - **THEN** Tauri 能找到 Python bridge 或 sidecar，并能显示主窗口。

- **AC-008.2:**
  - **GIVEN** 路径包含中文或空格
  - **WHEN** 用户选择视频、模板、输出目录或模型目录
  - **THEN** bridge 正确接收路径并完成对应操作。

- **AC-008.3:**
  - **GIVEN** 用户缺少模型文件
  - **WHEN** 应用运行
  - **THEN** 前端给出模型缺失状态和下载入口，不因模型缺失导致主窗口崩溃。

---

## 4. 非功能性需求

| ID | 类别 | 描述 | 来源设计约束 |
|:---|:---|:---|:---|
| NFR-001 | 兼容性 | 仅要求 Windows 本机开发、运行和打包通过 | `design.md` 2.2 |
| NFR-002 | 性能 | 帧预览事件必须节流，避免 Vue 高频渲染阻塞识别 worker | `design.md` 6.1 |
| NFR-003 | 安全边界 | Tauri 文件访问和 sidecar 启动只开放迁移所需能力，不开放任意 shell 命令入口 | `design.md` 4.1 |
| NFR-004 | 可维护性 | Python bridge 协议必须有 headless 契约测试，前端组件应能独立构建验证 | `design.md` 6.2 |
| NFR-005 | 回归稳定性 | MediaPipe 默认路径、golden、valid_mask、YOLO 未授权边界保持不变 | `design.md` 2.2 |

---

## 5. 设计映射

| 需求 ID | 设计章节 | 说明 |
|:---|:---|:---|
| REQ-001 | 4.1、3.1 | 由新增 `frontend/` 与 Tauri 壳派生 |
| REQ-002 | 2.2、3.2、4.1 | 由 Python 后端不动和算法不迁移派生 |
| REQ-003 | 4.3、4.4 | 由主会话、摄像头、预览帧和输入源状态派生 |
| REQ-004 | 4.3、4.4 | 由录制状态机保持三态语义派生 |
| REQ-005 | 4.3、4.4 | 由动作分析窗口完整覆盖派生 |
| REQ-006 | 4.3、4.4 | 由设置和模型管理覆盖派生 |
| REQ-007 | 4.2、4.3、6.1 | 由 Tauri 与 Python bridge 调用链派生 |
| REQ-008 | 2.2、6.1、6.2 | 由 Windows-only 打包和路径风险派生 |

---

## 6. 约束、假设与超出范围

### 约束

- 只做 Windows。
- Python 后端核心行为不动。
- 完整覆盖当前 Tkinter 用户可见能力。
- 先批准规范，再实施业务代码。

### 假设

- 开发期可使用仓库 `.venv` 启动 Python bridge。
- 打包期允许新增 sidecar 或等价的 Python bridge 启动方式。
- 用户接受迁移完成前 Tkinter 与新 Tauri 前端并存。

### 超出范围

- 跨平台发布。
- 删除 Tkinter 入口。
- 算法迁移到 Rust、TypeScript 或浏览器。
- 修改评分阈值、模板格式或 YOLO 对外评分授权。

---

## 7. 审批记录

| 日期 | 审批人 | 决定 | 备注 |
|:---|:---|:---|:---|
| 2026-06-08 | 用户 | 未审批 | 等待用户回复 `批准规范，启动执行` |
