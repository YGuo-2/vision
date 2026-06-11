# /goal 运行指令扩展（goal-directives）

> 本文件是 /goal 提示词的扩展部分，与提示词同等效力。执行者必须先完整阅读本文件再开始第 0 步。
> 生成日期：2026-06-11。批准范围 = 按本文件 R1~R10 修订后的 docs/specs/ 规范。

## 一、规范修订清单 R1~R10（修订阶段逐条落实，禁止重新设计）

- **R1 路由优先级（决策 D1）：** 用户手部开关优先于指标能力。`enableHands=false` 时任何任务（含正式评分/完整技术评估）一律不启用 hand landmarker，走 MediaPipe pose-only；手指类指标按既有 skip-aware partial 机制跳过并在结果显式标注 partial。嘴角/脚跟/脚尖是 pose 点，不受手部开关影响。AC-002.5 改写为「依赖手指 且 `enableHands=true` 才启用 hand landmarker」；design.md 4.3 表第 4 行「按指标能力启用必要配置」改为「pose-only + 手指指标 skip-aware 标注」。
- **R2 路由器落点（决策 D2）：** 新建 `core/backend_router.py` 作为全仓唯一路由决策点；`apps/ui_backend.py` 与 batch 链路只消费它；`batch/backend_options.py` 收编为调用该路由器做校验的 CLI 适配层，保持现有参数与 `BATCH_META_FIELDS` 兼容。T-001 涉及文件加入 `core/backend_router.py`。
- **R3 确定性路由断言（决策 D3）：** AC-002.2/AC-002.3 的「可以选择」改为确定性规则——候选条件满足且模型可用时必须选择对应 YOLO 档并在 reason 记录；实时预览 YOLO 模型不可用时自动回退 MediaPipe pose-only 预览，路由 reason 与 UI 标注 fallback；离线高质量 body-only 分析 YOLO26L 不可用时返回结构化错误提示下载，不静默回退。为这两种失败路径各补一条 AC。
- **R4 实时预览多人策略（决策 D4）：** 沿用 `core/yolo_adapter.py` 既有 `select_main_person`（最大框/最高分）渲染主体，meta 透传 `multi_person_detected`，前端预览显示「检测到多人」提示；离线链路维持 `review_required` 闸门；完整多人鲁棒策略（track 延续/中心最近/tie-break）写明本期不做。
- **R5 层职责修正：** AC-001.1 中 Tauri/Rust 职责改为进程/IPC/帧通道/打包/资源路径；模型清单与下载执行明确留在 Python（`core/model_manager.py` + `apps/ui_backend.py`）。
- **R6：** T-004 验证命令追加 `npm run verify:tauri`。
- **R7 性能基线：** T-004/T-005 验证标准增加迁移前后对比记录（丢帧率、渲染帧率、前端内存增长、IPC payload 大小），记录型即可，结果写入任务证据与 change.md。
- **R8 帧通道选型（决策 D5，写入 design.md 4.4）：** Python→Rust 采用仅绑定 127.0.0.1 的 TCP 帧流（随机端口 + 会话 token 经 JSON bridge 握手下发，长度前缀二进制帧协议，Rust 侧每 session 单槽只存最新帧）；Rust→Vue 采用 Tauri 2 raw IPC（invoke 返回 `tauri::ipc::Response` 二进制 ArrayBuffer），前端 requestAnimationFrame 节流拉取最新帧，经 createImageBitmap 绘制 canvas。备选：Windows named pipe / Tauri custom protocol。遇硬阻碍可换备选并在 change.md 记录原因，禁止以 JSON/base64 回传大帧兜底。
- **R9 受限显示字段收敛（决策 D6）：** 统一为单一字段 `displayScope`（枚举 limited|internal；snake_case 为 `display_scope`），删除 `evalScope`/`internalUseOnly` 及「或等价字段」措辞，AC-003.1/AC-003.4 同步收紧。
- **R10 杂项：** T-009 性质写明「新增 YOLO 进入 tech_eval/正式评分的阻断守卫测试 + 重跑全部金标回归，不改变 MediaPipe 评分行为」；design.md 3.1 注明「保持兼容」含义（可改文件，行为以 golden 为准）；3.2 增加 `apps/app_ui.py`（Tkinter 旧入口）不在范围；tasks.md 执行规则增加「每任务完成同步 change.md」；T-003 验证标准提及开发侧模型下载走代理 `http://127.0.0.1:7890`、安装版用户侧需处理下载源不可达提示。

## 二、硬约束红线（任何时候违反即目标失败，必须先修复）

1. `tests/test_pose33_v3_golden.py` 任何时候全绿；MediaPipe 旧默认路径（`pose33_v3` 模板、`infer()`、`annotate()`、正式评分、full tech_eval）行为不漂移。
2. YOLO 永不进入正式评分与 full tech_eval；`score_authorized` 恒布尔 False、`calibration_status` 恒 unvalidated；YOLO26X 不进默认路由。
3. COCO17 缺失点（嘴角/手指/脚跟脚尖）不得伪造为有效点，统一 `valid_mask=False` + 结构化 missing capability。
4. T-004 完成后大图帧不得经 JSON/base64 主桥；前端不得把帧存入 ref/reactive/历史数组。
5. 视觉算法不迁入 Rust 或 TypeScript；Rust 只做系统层、IPC、帧通道、任务生命周期。
6. 任务状态只经 Spec Progress MCP 工具或 `spec_progress.py` 变更；需要超出 R1~R10 修改规范时立即停码、置 reapproval-required 并暂停 goal 等人。
7. 不提交大产物与生成物（`models/`、`dist/`、`build/`、`frontend/dist/`、`frontend/src-tauri/target/`、`*.exe`、`tauri-dev*.log`）。
8. 一切联网下载（pip、YOLO/MediaPipe 模型、GitHub/HuggingFace）走 `http://127.0.0.1:7890`。

## 三、暂停协议

- 同一任务验证连续 3 次自愈失败：`spec_block_task` 记录原因，暂停 goal，输出诊断与候选方案。
- 触发 reapproval-required，或遇 R1~R10 未覆盖的方向性决策（评分授权、对外报告口径、许可合规）：暂停等待人类，不得自行拍板。
- 预算接近耗尽：停止实质编码，提交已完成任务，跑 `spec_progress.py resume` 确认一致后输出「已完成 / 当前任务与证据 / 阻塞 / 下一步」并停止。预算耗尽 ≠ 目标达成。

## 四、环境与命令

- Windows 11 + PowerShell；Python 一律 `.\.venv\Scripts\python.exe`；前端 `npm --prefix frontend`；cargo 先 `$env:Path = "$env:USERPROFILE\.cargo\bin;$env:Path"`。
- Spce 插件脚本目录：`E:\CodeProject\spec-coding-marketplace\plugins\spce-workflow\scripts\`（validate_spec.py / spec_progress.py）。
- 各任务验证命令以 tasks.md 字段为准；「分步运行」的命令每步退出码必须为 0。
- 批准生效时同步状态字段：progress.md Approval=approved、spec.yml approval=approved、tasks.md 状态=Approved、design.md/requirements.md 状态=已批准并在审批记录表补行（审批人：用户；备注：经 /goal 指令预批准，范围限 R1~R10 修订后版本）。
