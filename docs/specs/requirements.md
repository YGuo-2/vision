# 需求规范 (Requirements Derived from Design)

> **功能名称：** 性能优化清单落地
> **来源设计：** `docs/specs/design.md`
> **版本：** v1.0
> **状态：** 审查中
> **最后更新：** 2026-06-14

---

## 1. 概述

本需求规范从 `docs/specs/design.md` 派生，用于把性能优化清单转化为可执行、可验证、可恢复的 Spce 任务图。用户将获得一套按风险分层的性能优化实施规范，而不是未分批、未校验、可能破坏评分边界的代码改动。

---

## 2. Analyze Requirements / 需求分析结论

- **歧义检查：** “性能优化”被拆成预览与编排、数值等价、GPU opt-in、高风险评分、传输与打包五条轨道；“不改变评分语义”定义为 `pose33_v3` 金标、规则评分合同、tech_eval 合同和 YOLO 授权元数据均不漂移。
- **设计一致性：** 本文件所有需求均由 `design.md` 的分轨方案、默认路径保护、验证策略和非目标派生；不新增清单外产品能力。
- **冲突检查：** 预览默认 pose-only 或 lite 与正式评分默认 MediaPipe CPU VIDEO-mode 不冲突，因为二者处于不同入口和授权范围；GPU opt-in 与默认 CPU 不冲突，因为 GPU 不进入默认正式评分链路。
- **失败路径：** GPU delegate 不可用时必须结构化回退 CPU；缺 YOLO runtime 或模型时维持现有 fallback 或结构化不可用；并发任务必须隔离 pipeline；打包 resources 缺失时 packaging smoke 失败；金标或合同测试漂移时必须停止任务并要求重新审批。`T-001` 若复现 high_quality backend routing 失败，则性能优化实施阻塞，先修复或单独走 Bugfix。
- **权限、安全与数据风险：** 本次不涉及认证、授权、隐私数据落库或数据库迁移；主要风险来自并发、缓存、路径解析和评分语义。任何新增文件访问、模型下载或外部资源下载仍需遵守本仓库代理约定。
- **并发与数据一致性：** batch 并行和 preview 多 worker 必须保证 session/job/frame 身份隔离，late response 不得复活终态，latest-frame 单槽语义不改为队列。
- **Intake 未决项归类：** 未决项为“具体实施批次是否全部执行”，归入任务审批边界；本轮只生成规范，不自动实施。`T-008` 的单次抽帧实现不包含在首次总审批内，必须以二次审批包和独立批准短语解锁。
- **Quick Plan 跳过原因：** n/a，本规范为 strict 模式，未启用 Quick Plan。

---

## 3. Intake Handoff / 澄清交接

- **Status:** assumptions-accepted
- **Confirmed facts:** 用户要求基于 `docs/performance_optimization_inventory.md` 生成对应 Spce 文档；当前仓库需要新建 `docs/specs/` 工件集；性能清单自身声明为纯清单，未改任何代码。
- **Scope:** 生成 `design.md`、`requirements.md`、`tasks.md`、`progress.md`、`spec.yml`；把本次文档生成记录到 `change.md`。
- **Non-goals:** 不实现性能优化项；不改 Python、Vue、Rust、打包脚本的业务行为；不重生金标；不改变正式评分后端或 YOLO 授权边界。
- **Decision boundaries:** Codex 可按清单优先级拆分任务图；涉及评分语义、正式默认路径、GPU 默认启用、YOLO 对外评分或金标变更的决策必须回到用户审批。`批准规范，启动执行` 不授权 `T-008` 单次抽帧实现；该实现需要 `批准 T-008 高风险评分变更，启动执行`。
- **Success criteria:** Spce 文档结构完整，插件结构校验通过，任务图包含验证命令、证据字段、风险标注和执行依赖。
- **Assumptions:** 该清单是技术设计输入，因此走 Design-First；后续实施需用户回复 `批准规范，启动执行`。
- **Risks:** 黄色风险项需要单独任务和单独验证，不可与纯展示、打包或编排任务混合完成。当前已知审查证据显示 high_quality backend routing 子集存在 1 个失败用例，T-001 必须将其作为实施阻塞判据记录。

---

## 4. 功能需求与验收标准

### REQ-001: 建立分轨性能优化任务图

**作为** 项目维护者，**我希望** 将性能清单拆成按风险和依赖排序的任务图，**以便** 后续可以逐批审批、执行、验证和恢复。

#### 验收标准

- **AC-001.1:**
  - **GIVEN** `docs/performance_optimization_inventory.md` 已存在
  - **WHEN** 生成 Spce 文档
  - **THEN** `docs/specs/tasks.md` 包含预览与编排、数值等价、GPU opt-in、高风险评分、传输与打包、最终验收任务

- **AC-001.2:**
  - **GIVEN** `docs/specs/tasks.md` 中存在任务依赖
  - **WHEN** 运行 Spce 校验
  - **THEN** 工具可以计算执行 waves，且当前任务指向第一个可执行任务

### REQ-002: 保护正式评分默认路径

**作为** 评分系统维护者，**我希望** 性能优化不改变正式评分、full tech_eval、模板提取和旧模板兼容默认行为，**以便** 性能收益不会破坏既有评分可信度。

#### 验收标准

- **AC-002.1:**
  - **GIVEN** 某任务触碰 `core/pose_features.py`、`core/action_compare.py`、`core/rule_scoring.py` 或 `core/vision_pipeline.py`
  - **WHEN** 完成该任务
  - **THEN** 必须提供 `tests/test_pose33_v3_golden.py` 和受影响合同测试的通过证据

- **AC-002.2:**
  - **GIVEN** 某优化会改变评分结果、DTW 对齐语义或代表周期选择
  - **WHEN** 实施前评估该优化
  - **THEN** 必须停止当前任务并要求重新审批，不能静默重生 `tests/fixtures/pose33_v3/golden.json`

- **AC-002.3:**
  - **GIVEN** `T-008` 准备进入单次抽帧复用实现
  - **WHEN** 只有首次 `批准规范，启动执行` 的批准证据
  - **THEN** 只能产出风险评估和二次审批包，不得修改单次抽帧相关业务代码

### REQ-003: 限定预览优化的授权边界

**作为** 桌面前端使用者，**我希望** 实时预览可以获得更高帧率和更低延迟，**以便** 操作体验改善，同时不把预览结果误认为正式评分。

#### 验收标准

- **AC-003.1:**
  - **GIVEN** 预览任务改动 `apps/ui_backend.py` 或 `frontend/`
  - **WHEN** 预览输出来自 body-only、lite 或多 worker IMAGE-mode
  - **THEN** 输出必须显式保持 `scoreAuthorized=false`，并根据场景使用 `displayScope=limited` 或 `displayScope=internal`，同时维持 session/job/frame 身份隔离

- **AC-003.2:**
  - **GIVEN** `enableHands=false` 且存在手部能力请求
  - **WHEN** bridge 路由请求
  - **THEN** 不得静默启用手部检测，也不得误走 YOLO full scoring 路径

### REQ-004: GPU delegate 只能显式启用并可回退

**作为** Windows 桌面维护者，**我希望** GPU delegate 作为 opt-in 能力贯通，**以便** 有 GPU 的机器可测试性能收益，而默认评分链路仍保持 CPU 可复现性。

#### 验收标准

- **AC-004.1:**
  - **GIVEN** 用户未显式请求 GPU delegate
  - **WHEN** 创建正式评分、tech_eval 或默认 CLI/Tkinter pipeline
  - **THEN** `PipelineConfig.delegate` 仍为 `cpu`

- **AC-004.2:**
  - **GIVEN** GPU delegate 初始化失败
  - **WHEN** 创建 opt-in GPU pipeline
  - **THEN** 系统返回结构化 fallback 或回退 CPU，并记录可见证据

### REQ-005: 数值等价优化必须可证明

**作为** 算法维护者，**我希望** DTW、归一化、规则表和误差聚合优化都能证明数值等价，**以便** 性能提升不改变评分输出。

#### 验收标准

- **AC-005.1:**
  - **GIVEN** 对 DTW 局部代价矩阵或姿态归一化进行向量化
  - **WHEN** 跑金标和单元测试
  - **THEN** 分数、区间、规则状态和误差统计在既有容差内不漂移

- **AC-005.2:**
  - **GIVEN** 使用缓存减少重复计算
  - **WHEN** 输入包含 invalid landmark 或 `valid_mask`
  - **THEN** 缺失点不得被伪造成有效点，所有有效性判据仍走 `valid_mask`

### REQ-006: 打包与传输优化必须保持会话隔离

**作为** 桌面应用维护者，**我希望** onefile 冷启动、JPEG/IPC/canvas 消耗和 latest-frame clone 成本被削减，**以便** 桌面启动和预览更流畅。

#### 验收标准

- **AC-006.1:**
  - **GIVEN** sidecar 从 onefile 改为 onedir
  - **WHEN** 运行 Windows 打包验证
  - **THEN** Tauri resources、Rust 路径解析和 PyInstaller heavy excludes 均通过 smoke 测试

- **AC-006.2:**
  - **GIVEN** 前端或 Rust 修改 raw frame 传输
  - **WHEN** 连续收到相同、乱序或跨 session 帧
  - **THEN** canvas 只绘制当前 session 且 `frameId` 单调不回退

---

## 5. 非功能性需求

| ID | 类别 | 描述 | 来源设计约束 |
|:---|:---|:---|:---|
| NFR-001 | 性能证据 | 每批优化必须记录执行前后命令、profile 或 smoke 证据 | `design.md` 6.2 |
| NFR-002 | 兼容性 | 默认正式评分、CLI、Tkinter、full tech_eval 行为保持 MediaPipe CPU 链路 | `design.md` 2.2 |
| NFR-003 | 可恢复性 | 所有任务开始和完成必须通过 Spce progress 工具记录 | `design.md` 2.2 |
| NFR-004 | 并发安全 | 多 worker 和 batch 并行不得共享 MediaPipe pipeline 实例 | `design.md` 6.1 |
| NFR-005 | 打包可靠性 | onedir 资源路径必须被 packaging smoke 覆盖 | `design.md` 4.4 |
| NFR-006 | 可审计性 | 每次完成任务后更新 `change.md`，最新记录置顶 | `AGENTS.md` 任务完成规范 |
| NFR-007 | 验收隔离 | final acceptance 的修复队列必须进入 `docs/specs/acceptance-fixes.md`，不得追加到原始 `tasks.md` | `spec-acceptance` 规则 |

---

## 6. 设计映射

| 需求 ID | 设计章节 | 说明 |
|:---|:---|:---|
| REQ-001 | 4.1、4.2 | 从五条执行轨道和拓扑派生 |
| REQ-002 | 2.2、6.2 | 从 MediaPipe 默认路径和金标保护派生 |
| REQ-003 | 3.1、4.3、4.4 | 从预览 bridge、ParallelPoseEngine 和 latest-frame 约束派生 |
| REQ-004 | 4.3、5 | 从 GPU opt-in 轨道和默认不启用取舍派生 |
| REQ-005 | 4.1、6.2 | 从数值等价轨道和验证策略派生 |
| REQ-006 | 4.3、4.4、6.2 | 从 raw frame IPC、sidecar resources 和 packaging 验证派生 |
| NFR-007 | 6.2 | 从 final acceptance 修复隔离规则派生 |

---

## 7. 约束、假设与超出范围

### 约束

- 后续实施必须从 `T-001` 开始，先固化基线证据。
- 任何业务代码实施前必须收到 `批准规范，启动执行` 并冻结基线。
- 黄色风险项必须独立提交、独立验证、独立记录；`T-008` 还必须独立批准。
- `git diff --check` 是每批交付前的最低文本卫生门。

### 假设

- 性能清单中的现状和行号与当前工作区足够接近；若发现漂移，先同步规范再执行。
- 当前用户目标是规划 Spce 文档，不要求本轮实现优化。

### 超出范围

- 默认 YOLO 正式评分。
- 默认 GPU 正式评分。
- Rust/TypeScript 视觉算法迁移。
- 未经审批的金标重生。
- 模型大文件、输出文件、bundle 产物提交。

---

## 8. 审批记录

| 日期 | 审批人 | 决定 | 备注 |
|:---|:---|:---|:---|
| 2026-06-14 | Codex | 待审批 | 已从设计派生需求；实施需用户回复 `批准规范，启动执行` |
