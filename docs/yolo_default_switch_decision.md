# YOLO 迁移 S6 默认切换决策（Issue #28）

来源：GitHub Issue #28 `S6：默认切换决策（纯决策，无实现）`
日期：2026-05-31
阶段：S6（默认切换决策）　依赖：#1 #10 #23 #24 #25 #26 #27

> **结论先行：全部不切默认。**
> 当前只保留已授权的离线 / 实验入口：batch 显式 `body_core_v1` 调试 / 标定输出继续保留
> `score_authorized=False`，`apps/main.py` 与 `apps/app_ui.py` 均保持 MediaPipe 默认路径。
> 本决策不引入业务代码，不改变 CLI / UI / batch 的默认行为。

---

## 一、决策输入汇总

| 输入 | 当前结论 | 对默认切换的影响 |
|---|---|---|
| #1 许可 | Ultralytics AGPL-3.0 仅适合内部研发 / 评估；闭源 / 商业部署需 Enterprise 或替代方案 | 不满足对外默认切换前置条件 |
| #10 标定 | `body_core_v1` 结论为“仅预览 / 内部标定参考”；J1 corr=0.280 < 0.70，J4 一致率=0.50 < 0.75 | 模板匹配默认不切 YOLO / body_core |
| #23 GPU 复测 | no-go；`torch.cuda.is_available()=False`，GPU 有效复测覆盖 0/6 | 实时预览和 UI 默认不切 |
| #24 batch | 只授权离线显式 `body_core_v1` 调试 / 标定入口；`calibration_status=unvalidated`，`score_authorized=False` | 可保留实验入口，不作为默认评分 |
| #25 CLI | `apps/main.py --backend yolo` 实时预览入口关闭 / 不实现 | CLI 默认不切 |
| #26 UI | `apps/app_ui.py` YOLO 后端选择关闭 / 不实现 | UI 默认不切 |
| #27 Hybrid | `yolo_body_mp_pose_supplement` 不实现，不保留半成品 runtime | Hybrid 不进入默认 / 离线路径 |

---

## 二、三条链路默认决策

| 链路 | 默认决策 | 数字 / 事实依据 | 允许保留的入口 |
|---|---|---|---|
| 实时预览（CLI / UI） | **不切默认，继续 MediaPipe** | #23 GPU runtime False、0/6 有效 GPU benchmark；#25 / #26 已关闭 | 无 YOLO 实时 / UI 入口 |
| 模板匹配 | **不切默认，继续 `pose33_v3` / MediaPipe** | #10 J1 corr=0.280、J4 一致率=0.50，`score_authorized=False` | 显式离线 `body_core_v1` 调试 / 标定入口 |
| 规则 / 技术评估 | **不切默认，继续 MediaPipe full** | COCO17 缺嘴角、脚跟脚尖、手指；#10 仅预览；#11 只做 MediaPipe 侧结构化状态 | YOLO 不进入 full tech_eval / 对外评分 |
| Hybrid | **不实现，不参与默认切换** | #27 未满足 CUDA / Hybrid benchmark / 补点价值触发条件 | 无 |

---

## 三、默认切换前置条件

若未来要重新评估任何默认切换，必须先另开实现 / 决策子任务，并同时满足：

1. 许可路径可用于目标部署形态：闭源 / 商业部署需 Enterprise license 或替代模型方案。
2. CUDA-enabled 环境下 #23 GPU 复测 6/6 样本有效，Hands 关 / Hands 开端到端 FPS 比分别达到 1.30 / 1.20。
3. #10 或后续标定在目标样本集上重新通过，模板匹配分数相关性、pass/fail 一致率和误判样例均达标。
4. 规则 / 技术评估未评估比例、缺失能力和误判样例可接受，且仍不得把缺失点伪造成有效点。
5. CLI / UI / batch 均能显示结果来源、`feature_layout`、`calibration_status`、`score_authorized`。
6. 有一键回滚配置，可在 YOLO 入口异常时恢复 MediaPipe 默认路径。

---

## 四、当前收尾结论

- `apps/main.py`：默认保持 MediaPipe；不新增 `--backend yolo` 实时预览入口。
- `apps/app_ui.py`：默认保持 MediaPipe；不新增 YOLO 后端选择或未标定评分提示入口。
- `apps/make_template.py` / `apps/match_template.py` / batch：保留显式实验 / 标定入口，但输出必须标明
  `calibration_status=unvalidated` 与 `score_authorized=False`，不得进入用户对外评分。
- `analysis/tech_eval.py` / `core/rule_scoring.py`：默认继续 MediaPipe full；YOLO-only 不进入 full tech_eval。
- `yolo_body_mp_pose_supplement`：不实现。

因此 Issue #28 的 S6 决策为：**全部不切默认，仅保留离线 / 实验入口**。
