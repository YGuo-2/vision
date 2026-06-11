# Spce workflow Progress

> **Workflow:** design-first
> **Mode:** strict
> **Status:** Draft
> **Current Task:** T-001
> **Approval:** pending
> **Last Checkpoint:** 2026-06-11 12:49:54
> **Branch:** main
> **Last Known Commit:** 7a45669

## Resume Summary
- Goal: 先审查 Vue/Tauri 高速帧通道与 MediaPipe/YOLO 后端路由 Design-First 规范；批准后从 T-001 后端路由决策契约开始实现。
- Approved specs: none yet; draft artifacts are design.md, requirements.md, tasks.md
- Current task: T-001
- Next safe action: 等待用户回复 `批准规范，启动执行`；批准前不得实现业务代码。
- Blockers: 等待用户批准规范；当前工作区包含无关既有改动，本轮不得回滚或混入业务实现。

## Active Task State
- Task ID: T-001
- Status: pending
- Started at: n/a
- Verification needed: 批准后运行 `.\.venv\Scripts\python.exe -m pytest tests/test_backend_routing_contract.py tests/test_ui_backend_contract.py -q`
- Files expected to change: `apps/ui_backend.py`, `core/feature_layout.py`, `core/yolo_adapter.py`, `tests/test_backend_routing_contract.py`, `tests/test_ui_backend_contract.py`

## Completed Work Log
| Task ID | Time | Commit/State | Verification | Notes |
|:---|:---|:---|:---|:---|
| - | - | - | - | - |

## Recovery Notes
- 当前规范状态为 Draft，approval=pending。用户已要求 5 个只读 agent 分别审查 design.md、requirements.md、tasks.md、progress.md、spec.yml；审查完成后如有 P0/P1/P2 需先修正文档并重新运行 Spce 校验。
- 五个只读 agent 已完成审查：design.md、requirements.md、tasks.md、progress.md 的 P1/P2 问题已修正；spec.yml 审查未发现 P0/P1/P2 阻断，P3 覆盖字段提醒已核对为当前 tasks.md 已显式覆盖。
- 用户追加问题清单后已补强批准前规范：采用 `enableHands=false` 开关优先，手指指标降级为 skip-aware partial；新增 `core/backend_router.py` 作为唯一路由点；收敛 `displayScope` 为唯一受限显示字段；定死二进制帧通道首选命名管道 + Tauri 自定义协议、回退 latest-frame 原子文件；补齐模型不可用回退、YOLO 实时多人、性能基线、Rust 验证和每任务同步 change.md。
- 当前工作区并非干净状态：main ahead 21，且存在多处既有前端、后端、测试和生成文件改动；本轮仅审查并修正 docs/specs 与 change.md，不得回滚无关改动。
- 关键边界：MediaPipe 保留正式评分和 full tech_eval；YOLO 只做 body-only 预览、离线分析、内部标定或快速筛查；`enableHands=false` 只是 YOLO 候选条件，不是直接路由条件。
- 关键帧通道目标：JSON bridge 只传状态、进度、分数和小型元数据；预览大帧改走二进制 latest-frame，Vue 只用 Canvas/bitmap 绘制最新帧。
