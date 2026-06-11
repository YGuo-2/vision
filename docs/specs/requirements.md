# 需求规范 (Requirements Derived from Design)

> **功能名称：** Vue/Tauri 高速帧通道与 MediaPipe/YOLO 后端路由架构
> **来源设计：** `docs/specs/design.md`
> **版本：** v1.0
> **状态：** 已批准
> **最后更新：** 2026-06-11

---

## 1. 概述

这些需求从 `docs/specs/design.md` 的 Design-First 架构派生，用于指导后续实现。目标是把 Vue/Tauri/Rust/Python MediaPipe/YOLO 的系统边界、数据通道、后端路由和评分授权写成可测试能力，同时保持 MediaPipe 可信完整能力不漂移。

---

## 2. Analyze Requirements / 需求分析结论

- **歧义检查：** 已消除“关手部就走 YOLO”的歧义；`enableHands=false` 只是 YOLO 候选准入条件，正式路由还必须检查任务类型、评分模式、关键点能力和模型档。`enableHands=false` 同时也是禁止静默启用 hand landmarker 的硬约束；当 full tech_eval 请求手指指标时，系统走 MediaPipe pose-only 生产路径并将手指指标标为 skip-aware partial。`YOLO26L` 被定义为高质量 body-only 离线分析模型，不被定义为 full tech_eval 后端。`scoreAuthorized` 是布尔授权字段，YOLO 未获独立批准前只能是 `false`；内部分析或受限显示必须使用 `displayScope` 表达。YOLO raw Pose33-like 容器不等于 `pose33_v3` 生产布局，必须区分 raw layout 与最终 feature layout。
- **设计一致性：** 本文件只从 `design.md` 派生职责边界、路由规则、帧通道、模型策略、状态机、标识契约和验证要求；没有新增超出设计的产品能力。
- **冲突检查：** 与既有 `docs/yolo_default_switch_decision.md` 的“全部不切默认”不冲突，因为本规范要求 MediaPipe 继续承担正式评分和完整技术评估，YOLO 仅在显式 body-only 场景使用。与 `core/yolo_adapter.py` 的 `calibration_status=unvalidated` 不冲突，因为本规范不授权 YOLO 对外评分。
- **失败路径：** 需要覆盖模型缺失、模型下载取消、模型下载源/代理不可达、sidecar 启动失败、JSON bridge 超时、二进制帧通道断开、late event、session 切换、旧帧污染、多人检测、YOLO 缺失能力、打包资源缺失、安装版 sidecar 排除 YOLO 依赖、权限不足、并发停止和 Windows 安装路径差异。实时预览所需 YOLO 模型不可用时允许自动回退 MediaPipe pose-only 并显式标注 fallback；离线高质量 body-only 分析所需 YOLO26L 不可用时必须返回结构化下载/安装错误，不得静默回退。
- **Quick Plan 跳过原因：** n/a，本任务使用 strict 模式；跨前端、Rust、Python、模型、性能和打包链路，不能跳过需求分析。

---

## 3. 功能需求与验收标准

### REQ-001: 四层职责边界

**作为** 桌面应用维护者，**我希望** Vue、Tauri/Rust、Python MediaPipe 和 YOLO 后端职责清晰，**以便** 后续实现不会把 UI、系统层和视觉算法混在一起。

#### 验收标准

- **AC-001.1:**
  - **GIVEN** 开发者阅读规范和架构图
  - **WHEN** 判断某项逻辑应放在哪一层
  - **THEN** Vue 只负责交互、状态展示和 Canvas/bitmap 渲染；Tauri/Rust 负责 sidecar 生命周期、IPC、资源路径、帧通道、状态机、取消和打包；Python 负责模型清单、下载执行、视觉后端、评分和分析。

- **AC-001.2:**
  - **GIVEN** 后续实现涉及视觉算法
  - **WHEN** 评审代码路径
  - **THEN** MediaPipe/YOLO 推理和评分逻辑不得迁入 Vue 或第一阶段 Rust 原生代码。

### REQ-002: 后端路由规则

**作为** 评分系统，**我希望** 后端选择由任务类型、手部开关和能力需求共同决定，**以便** YOLO 只在 body-only 场景使用。

#### 验收标准

- **AC-002.1:**
  - **GIVEN** `enableHands=true`
  - **WHEN** 启动实时预览、模板分析或评分任务
  - **THEN** 路由结果必须为 MediaPipe full，使用 pose full/heavy + hand landmarker，并允许正式评分和 full tech_eval。

- **AC-002.2:**
  - **GIVEN** `enableHands=false` 且任务为实时预览
  - **WHEN** YOLO26n/s 模型可用且不需要手指、嘴角、脚跟、脚尖
  - **THEN** 路由必须选择 YOLO26n/s 轻量档，输出 `featureLayout=body_core_v1`、`capability=body_only`、`scoreAuthorized=false`、`calibrationStatus=unvalidated`、`displayScope=limited` 和选择原因。

- **AC-002.3:**
  - **GIVEN** `enableHands=false` 且任务为离线高质量身体分析
  - **WHEN** 用户选择 body-only 分析而不是正式评分，且 YOLO26L 模型可用
  - **THEN** 路由必须选择 YOLO26L，输出 body-only 元数据、`scoreAuthorized=false`、`displayScope=internal`，不得进入 full tech_eval。

- **AC-002.4:**
  - **GIVEN** 任务为正式评分或完整技术评估
  - **WHEN** `enableHands=false`
  - **THEN** 路由仍必须选择 MediaPipe pose-only 生产路径，并在原因中说明 YOLO 不具备正式评分或完整技术评估授权；若指标需要手指，则该指标必须进入 skip-aware partial，不得静默启用 hand landmarker。

- **AC-002.5:**
  - **GIVEN** 任务依赖手指、嘴角、脚跟或脚尖
  - **WHEN** `enableHands=true`
  - **THEN** 路由必须选择能提供对应点的 MediaPipe 配置；依赖手指时必须启用 MediaPipe hand landmarker；YOLO 不得作为该任务后端。

- **AC-002.6:**
  - **GIVEN** 任务依赖手指
  - **WHEN** `enableHands=false`
  - **THEN** 路由必须选择 MediaPipe pose-only partial，结果包含 `evalCompleteness=partial`、`skippedCapabilities` 包含 `fingers`、`reason` 说明用户关闭手部检测，不得静默启用 hand landmarker。

- **AC-002.7:**
  - **GIVEN** `enableHands=false` 且任务为实时预览
  - **WHEN** YOLO26n/s 模型不可用、安装版不支持 YOLO 或模型下载未完成
  - **THEN** 路由必须自动回退到 MediaPipe pose-only 预览，输出 `backend=mediapipe`、`fallbackReason`、`requestedBackend=yolo`、`reason` 和 UI 可见 fallback 提示；不得无提示失败或静默伪装为 YOLO。

- **AC-002.8:**
  - **GIVEN** `enableHands=false` 且任务为离线高质量 body-only 分析
  - **WHEN** YOLO26L 模型不可用、安装版不支持 YOLO 或模型下载未完成
  - **THEN** 路由必须返回结构化错误，提示下载/安装 YOLO26L，不得静默回退 MediaPipe，也不得伪装为已完成 YOLO 分析。

- **AC-002.9:**
  - **GIVEN** YOLO 实时预览检测到多人
  - **WHEN** 输出预览骨架
  - **THEN** 系统必须只渲染 primary target，并输出 `multiPersonDetected=true`、`personCount`、`reviewRequired=true`、`targetPolicy` 和提示；不得把多人实时预览结果标为正式评分。

### REQ-003: YOLO 输出能力标识和授权边界

**作为** 报告和 UI 消费者，**我希望** YOLO 结果带有明确来源和授权标识，**以便** 不把内部 body-only 分析误当正式评分。

#### 验收标准

- **AC-003.1:**
  - **GIVEN** 任意 YOLO 路径向前端 JSON payload 或 UI 展示分析结果
  - **WHEN** 展示结果来源和能力边界
  - **THEN** 必须包含 `backend=yolo`、`rawLayout=pose33_like_coco17`、`featureLayout=body_core_v1`、`capability=body_only`、`scoreAuthorized=false`、`calibrationStatus=unvalidated`，内部显示范围只能由 `displayScope=limited` 或 `displayScope=internal` 表达。

- **AC-003.2:**
  - **GIVEN** YOLO COCO17 输出缺失嘴角、手指、脚跟、脚尖
  - **WHEN** 规则评分或技术评估读取关键点有效性
  - **THEN** 缺失点必须通过 `valid_mask=False` 和结构化 missing capability 体现，不得伪造成有效点。

- **AC-003.3:**
  - **GIVEN** Python artifact 与前端 JSON payload 都展示 YOLO 结果
  - **WHEN** 字段在 snake_case 和 camelCase 之间转换
  - **THEN** `score_authorized/scoreAuthorized`、`feature_layout/featureLayout`、`raw_layout/rawLayout`、`calibration_status/calibrationStatus`、`display_scope/displayScope` 必须一一映射，不得产生同义双字段。

- **AC-003.4:**
  - **GIVEN** 任意 YOLO 路径写入 Python artifact、CSV、JSONL 或 NPZ metadata
  - **WHEN** 下游读取结果来源和授权状态
  - **THEN** 必须使用 snake_case 字段 `backend=yolo`、`raw_layout=pose33_like_coco17`、`feature_layout=body_core_v1`、`capability=body_only`、`score_authorized=False`、`calibration_status=unvalidated`；内部显示范围只能使用 `display_scope=limited` 或 `display_scope=internal`。

- **AC-003.5:**
  - **GIVEN** YOLO 结果包含 `displayScope=limited|internal` 或 `display_scope=limited|internal`
  - **WHEN** 生成对外报告、正式评分字段、pass/fail 判定或正式成绩 CSV/JSONL
  - **THEN** 不得把该结果写入正式成绩字段，不得把 `scoreAuthorized` 或 `score_authorized` 改为 true。

- **AC-003.6:**
  - **GIVEN** UI bridge、batch CLI 或离线分析需要判断后端
  - **WHEN** 计算路由决策
  - **THEN** 必须调用 `core/backend_router.py` 的共享决策函数；`apps/ui_backend.py` 和 `batch/backend_options.py` 不得各自维护独立规则。

### REQ-004: JSON bridge 与二进制帧通道分离

**作为** 实时预览用户，**我希望** 预览帧不再挤占 JSON 主桥，**以便** 状态和控制消息稳定且预览渲染顺畅。

#### 验收标准

- **AC-004.1:**
  - **GIVEN** session 正在输出预览帧
  - **WHEN** 后端发送帧数据
  - **THEN** JSON bridge 只发送 frame id、尺寸、动作、进度、时间戳、握手端口/token 和错误等小型元数据；Python -> Rust 大帧 bytes 通过仅绑定 `127.0.0.1` 的 TCP 长度前缀帧流传输，Rust -> Vue 通过 Tauri 2 raw IPC `tauri::ipc::Response` 返回二进制 `ArrayBuffer`；若首选方案遇硬阻碍，只能切换到 Windows named pipe 或 Tauri custom protocol 备选，并在任务证据和 `change.md` 记录原因。

- **AC-004.2:**
  - **GIVEN** 后端帧率高于前端渲染能力
  - **WHEN** 多帧积压
  - **THEN** 系统只保留最新帧，旧帧可被丢弃，状态统计必须能记录 dropped 或 skipped 帧。

- **AC-004.3:**
  - **GIVEN** 同一视频源在迁移前后进行预览 smoke
  - **WHEN** 采集 payload、渲染帧率和内存指标
  - **THEN** `session.frame` JSON metadata p95 payload 必须小于 8KB 且不含图片 bytes/base64；30fps 源渲染帧率不得低于迁移前基线 10% 以上；3 分钟预览前端内存增长不得超过基线 20% 或 50MB 中较大值；任务证据和 `change.md` 必须记录迁移前后丢帧率、渲染帧率、前端内存增长、IPC payload 大小，若阈值待标定必须记录环境和原因。

### REQ-005: Vue Canvas/bitmap 渲染

**作为** 前端维护者，**我希望** 大帧不进入 Vue reactive state，**以便** 降低内存和响应式更新压力。

#### 验收标准

- **AC-005.1:**
  - **GIVEN** 前端收到二进制帧或 frame handle
  - **WHEN** 渲染预览
  - **THEN** 应通过 Canvas、ImageBitmap 或等价非大对象 reactive 方式绘制最新帧，不得把每帧图片字符串保存到 `ref`、`reactive` 或历史数组。

- **AC-005.2:**
  - **GIVEN** session 停止或切换
  - **WHEN** 晚到帧抵达前端
  - **THEN** 前端必须基于 `sessionId/jobId/frameId` 丢弃晚到帧。

- **AC-005.3:**
  - **GIVEN** 前端完成 Canvas/bitmap 迁移
  - **WHEN** 运行前端 smoke 或等价行为测试
  - **THEN** 测试必须证明 `previewImage` 或等价大图字符串状态已移除，且 frame handle 不会被保存到历史数组或 reactive 队列。

### REQ-006: 任务取消和状态机

**作为** 桌面应用用户，**我希望** 预览、模型下载和离线分析能被可靠取消，**以便** 关闭窗口或切换任务时不会留下后台任务。

#### 验收标准

- **AC-006.1:**
  - **GIVEN** session、analysis 或 model download 正在运行
  - **WHEN** 用户点击停止、取消下载或窗口卸载
  - **THEN** Tauri/Rust 与 Python sidecar 必须协同进入 stopping/stopped 状态，并阻止晚到 terminal response 覆盖新任务状态。

- **AC-006.2:**
  - **GIVEN** Python sidecar 崩溃、超时或输出非 JSON 行
  - **WHEN** Rust bridge 读取 stdout/stderr
  - **THEN** UI 必须收到结构化错误 envelope 或 `bridge.decode_error`，且 pending request 不得无限等待。

### REQ-007: 模型策略和配置管理

**作为** 维护者，**我希望** MediaPipe 与 YOLO 模型分档可配置、可验证、可打包，**以便** 不同任务使用正确模型。

#### 验收标准

- **AC-007.1:**
  - **GIVEN** 模型清单被读取
  - **WHEN** 查询 MediaPipe 与 YOLO 模型状态
  - **THEN** Python 模型清单应区分 MediaPipe pose full/heavy + hand landmarker、YOLO26n/s、YOLO26L 和 YOLO26X，并展示安装、下载、许可、用途、代理/离线安装提示；Rust 只负责资源路径、sidecar 打包和安装版资源发现。

- **AC-007.2:**
  - **GIVEN** YOLO26X 未被明确选为极限测试
  - **WHEN** 系统进行默认路由
  - **THEN** 不得选择 YOLO26X。

- **AC-007.3:**
  - **GIVEN** Windows 安装包由 `ui_backend_sidecar.spec` 构建
  - **WHEN** 安装版声明支持 YOLO body-only
  - **THEN** sidecar 必须包含对应 YOLO 运行依赖并通过 packaged smoke；否则 UI 和模型状态必须清楚标明安装版不提供 YOLO body-only。

### REQ-008: 阶段化演进

**作为** 项目负责人，**我希望** 迁移按阶段推进，**以便** 每阶段都有回归边界和验收证据。

#### 验收标准

- **AC-008.1:**
  - **GIVEN** 第一阶段实施
  - **WHEN** 引入 YOLO 路由和帧通道
  - **THEN** MediaPipe 和 YOLO 都继续在 Python 后端运行，Rust 只负责系统层、IPC、帧通道和任务管理。

- **AC-008.2:**
  - **GIVEN** 第二阶段评估开始
  - **WHEN** YOLO 离线分析性能需要进一步提升
  - **THEN** 才评估从 ultralytics/PyTorch 迁移到 ONNXRuntime 或 TensorRT。

- **AC-008.3:**
  - **GIVEN** 第三阶段评估开始
  - **WHEN** Rust 原生推理收益有明确证据
  - **THEN** 才考虑 Rust + ort 调用 ONNXRuntime。

---

## 4. 非功能性需求

| ID | 类别 | 描述 | 来源设计约束 |
|:---|:---|:---|:---|
| NFR-001 | 性能 | 实时预览大帧不得通过 JSON/base64 主桥；二进制帧通道采用 latest-frame 单槽语义 | `design.md` 2.2, 4.4 |
| NFR-002 | 兼容性 | MediaPipe `pose33_v3`、`infer()`、`annotate()`、正式评分和 full tech_eval 默认行为不漂移 | `design.md` 2.2, 3.2 |
| NFR-003 | 可观测性 | 路由结果、帧丢弃、score authorization、capability、model profile、session/job 状态必须可记录或展示 | `design.md` 4.3, 4.5 |
| NFR-004 | 打包 | Windows Tauri 包必须包含可启动 sidecar、模型资源管理和 packaged `bridge.ping` 验证 | `design.md` 2.2, 6.2 |
| NFR-005 | 安全和权限 | 本地 IPC 不暴露网络服务给外部访问；模型下载和资源路径必须处理 Windows 权限不足和安装目录差异 | `design.md` 6.1 |
| NFR-006 | 数据一致性 | session/job/frame id 必须阻止旧事件和旧帧污染新任务 | `design.md` 4.5, 6.1 |

---

## 5. 设计映射

| 需求 ID | 设计章节 | 说明 |
|:---|:---|:---|
| REQ-001 | 3.1, 4.1 | 四层职责来自目标系统边界和总体方案 |
| REQ-002 | 4.3 | 后端路由规则和能力匹配直接派生 |
| REQ-003 | 2.2, 4.5 | YOLO 输出授权、raw layout、feature layout 和能力标识派生 |
| REQ-004 | 2.2, 4.4 | JSON bridge 与二进制帧通道分离派生 |
| REQ-005 | 4.1, 4.5 | Vue Canvas/bitmap 渲染边界派生 |
| REQ-006 | 4.6, 6.1 | 任务取消、状态机和失败路径派生 |
| REQ-007 | 4.3, 4.5 | 模型策略和配置管理派生 |
| REQ-008 | 3.2, 5 | 阶段化演进和备选方案派生 |

---

## 6. 约束、假设与超出范围

### 约束

- 正式评分和完整技术评估继续使用 MediaPipe。
- `enableHands=false` 时不得静默启用 hand landmarker；依赖手指的指标必须 skip-aware partial。
- YOLO-only 输出必须标识 body-only、`body_core_v1`、`scoreAuthorized=false`，受限显示由 `displayScope` 表达。
- 二进制帧通道实现后，JSON 主桥不得继续承载大图帧。
- 所有实现必须保留 Windows 桌面打包和 packaged sidecar 验证。

### 假设

- 二进制通道首选仅绑定 `127.0.0.1` 的 TCP 长度前缀帧流 + Tauri 2 raw IPC `ArrayBuffer`；Windows named pipe / Tauri custom protocol 只作为备选，切换须记录到任务证据和 `change.md`；实现不得在 T-004 中换成未经重新批准的新通道方案或以 JSON/base64 回传大帧。
- YOLO 模型下载源、许可提示和资源路径会在模型清单任务中落实。
- 现有 `.venv`、Cargo、Node 和 Tauri 工具链可继续用于验证。

### 超出范围

- YOLO 替代 MediaPipe full tech_eval。
- YOLO26X 默认启用。
- 第一阶段 Rust 原生推理。
- 对外评分授权策略变更。
- 将每帧预览图片存入 Vue reactive state。

---

## 7. 审批记录

| 日期 | 审批人 | 决定 | 备注 |
|:---|:---|:---|:---|
| 2026-06-11 | 用户 | 已批准 | 经 /goal 指令预批准，范围限 R1~R10 修订后版本 |
