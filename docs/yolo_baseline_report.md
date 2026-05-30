# YOLO 迁移 S0 决策基线报告（go/no-go）

来源：`docs/yolo_migration_plan_optimized.md`（三审定稿）/ `docs/yolo_migration_issues.md` Issue #1、#2
日期：2026-05-30
覆盖范围：S0a（许可 + 环境 + 样本集，Issue #1）+ S0b（技术 spike + 核心指标降级清单 + 预注册阈值，Issue #2）
关联 spike 脚本：`analysis/spike_yolo_baseline.py`（独立脚本，不接主链路）
关联原始数据：`outputs/spike/spike_baseline.json`、`outputs/spike/spike_baseline.csv`、`outputs/spike/spike_keypoints.jsonl`

> **方法论提醒**：本报告严格遵循"先预注册阈值、后对照数据"。下文阈值表在跑数据前确定方向；
> 由于本仓暂无业务给定的硬性目标值，阈值数值按"基于本次 CPU 实测 MediaPipe 基线反推"的方式给出，
> 并显式标注 `建议值（待业务确认）`。每条 go/no-go 结论引用具体数字，不使用"明显劣于/可接受"这类主观措辞。

---

## 一、许可结论（Issue #1，四选一）

**结论：可用（限定条件）** —— 当前阶段以 **AGPL-3.0** 许可在 **内部研发 / 评估（S0–S3 spike 与离线对照）** 范围内使用 Ultralytics YOLO 是允许的；
**但若最终产品需闭源分发或商业部署，则必须改为"需采购 Enterprise License"，否则触发 AGPL-3.0 的全量开源义务。**

判定依据（外部事实，使用前请按固定版本再核验一次）：

- Ultralytics 采用 **AGPL-3.0 与 Enterprise 双许可**。官方明确：不希望开源整个项目时，需要 Enterprise License。参考：[Ultralytics License](https://www.ultralytics.com/license)、[Ultralytics Docs](https://docs.ultralytics.com/)。
- AGPL-3.0 的核心义务：基于受许可作品的"更大作品"在分发或通过网络提供服务时，须以同一许可公开完整源码（含修改）。参考：[Roboflow: YOLOv8 license](https://roboflow.com/model-licenses/yolov8)。
- 模型权重经由官方资产分发（本次使用 `yolo11n-pose.pt`，由 ultralytics 自动下载）。

风险与后续动作：

| 部署形态 | AGPL-3.0 是否可用 | 后续动作 |
|---|---|---|
| 内部研发 / 离线评估（S0–S3） | ✅ 可用 | 维持现状即可推进 |
| 闭源桌面分发 / 商业 SaaS | ❌ 不满足 | 进入"需采购 Enterprise"决策，或转替代方案（RTMPose/MMPose 等） |

> 因此本 Issue 的四选一判定为 **可用（限内部研发/评估）**；商业化形态的最终许可决策推到 S6"默认切换决策"，不阻塞 S0–S3。
> 内容已按许可合规要求改写，未逐字摘录许可原文。

---

## 二、迁移首要动机（决定 spike 测什么）

**首要动机：离线吞吐 / 精度为主。**（与本仓 `batch_tech_eval` / `batch_dual_compare` 的学员视频离线评估主用例一致。）

据此 spike 重点测：离线关键点提取 FPS、漏检帧率、与 MediaPipe 的关键点抖动差、躯干四肢核心点（`body_core_v1`）跨后端位置差；
实时 `annotate()` 全链路入口按计划留到 S5/S6。当前环境为 **CPU-only 且无摄像头**，故未测真实摄像头实时帧率（与动机一致，不属本期缺口）。

---

## 三、实验环境（Issue #1，固定并可复现）

| 项 | 值 |
|---|---|
| 操作系统 | Windows 11（10.0.26200） |
| CPU | Intel64 Family 6 Model 183（Raptor Lake 级别），逻辑核 32 |
| GPU / CUDA | **无可用 CUDA**，`torch.cuda.is_available()=False`，推理设备 `cpu` |
| Python | 3.13.9（`.venv` 虚拟环境） |
| numpy | 2.4.1 |
| opencv-python | 4.13.0 |
| mediapipe | 0.10.31 |
| ultralytics | 8.4.57 |
| torch | 2.12.0+cpu |
| MediaPipe 模型 | `models/pose_landmarker_full.task`（变体 `full`） |
| YOLO 模型 | `models/yolo11n-pose.pt`（COCO17 keypoints，官方资产 v8.4.0） |
| 代理 | pip / 模型下载经本地代理 `127.0.0.1:7890`（见 AGENTS.md） |

> 说明：本次为 **CPU 基线**。GPU 环境下两后端 FPS 量级会变化，结论中的 FPS 项需在目标部署硬件上复测；
> 但"YOLO COCO17 结构性缺点"（第六节）与硬件无关，GPU 也无法补回缺失关键点。

---

## 四、基线样本集（Issue #1）

清单文件：`docs/yolo_eval_samples.json`（视频本体受 `.gitignore` 排除，不入库，仅登记元信息）。共 6 段，覆盖正面 / 侧面 / 长视频 / 边界（学员视频多人风险）：

| id | 路径 | 视角 | 帧数 | 场景 |
|---|---|---|---:|---|
| std_front | 标准样本/正面.mp4 | 正面 | 250 | 标准-正面基线 |
| std_side_long | 标准样本/侧面.mp4 | 侧面 | 694 | 标准-侧面 + 长视频边界（最长样本） |
| student_1 | 学员样本/1.mp4 | 混合 | 450 | 学员-边界（多人风险） |
| student_4_long | 学员样本/4.mp4 | 混合 | 618 | 学员-较长 + 边界（多人风险） |
| punch_front | 标准动作视频--分解版/直拳/直拳 正面.mp4 | 正面 | 283 | 直拳-正面（依赖脚部/嘴角的典型动作） |
| punch_side | 标准动作视频--分解版/直拳/直拳 左侧.mp4 | 侧面 | 129 | 直拳-侧面（发力顺序/蹬地依赖脚跟脚尖） |

样本满足 Issue #1 的"≥3 段、覆盖正面/侧面/长视频/边界"要求。

---

## 五、预注册阈值表（Issue #2，先填数字，后对照）

> 阈值方向在跑数据前固定；数值为 `建议值（待业务确认）`，基于本次 CPU 实测 MediaPipe 基线反推。
> S0 的 go/no-go 用本表；模板匹配/评分一致性的更细阈值在 S3 标定时进一步收紧。

| 指标 | 预注册阈值（建议值，待业务确认） | 判定方向 | 实测值（本次） | 是否达标 |
|---|---|---|---|---|
| 离线端到端 FPS 提升比例（YOLO/MediaPipe，纯推理） | ≥ 1.0（至少不慢于 MediaPipe full） | 低于则"提速"动机不成立 | **0.41**（YOLO 更慢） | ❌ 不达标 |
| 关键点失败 / 漏检帧率 | ≤ 2% | 高于则 no-go | YOLO 0.0% / MP 0.07% | ✅ 达标 |
| 单人标准动作关键点抖动（body_core 逐帧位移中位数，归一化坐标） | ≤ 0.006 | 高于则 no-go | YOLO 0.0061 / MP 0.0035 | ⚠️ 临界（YOLO 略超） |
| YOLO 与 MediaPipe body_core 跨后端位置差中位数（归一化坐标） | ≤ 0.02 | 高于则模板匹配可替代性存疑（留 S3 细化） | 0.0147（均值） | ✅ 达标（单条学员样本 0.021–0.024 偏高） |
| 初始化 / 模型加载耗时 | ≤ 2.0s | 仅记录，超标记风险 | YOLO ~0.04s / MP ~0.11s | ✅ 达标 |

---

## 六、技术 spike 实测结果（Issue #2）

命令（仓库根，`.venv`）：

```powershell
.\.venv\Scripts\python.exe -m analysis.spike_yolo_baseline `
  --samples docs/yolo_eval_samples.json `
  --yolo-model models/yolo11n-pose.pt `
  --pose-variant full --out outputs/spike
```

默认会额外写出 `outputs/spike/spike_keypoints.jsonl`：逐帧保存 MediaPipe / YOLO 的 Pose33-like keypoints、`valid_mask`、YOLO 选中目标的 `track_id`、`person_count` 与归一化 bbox。`track_id` 由 spike 内部的最大框 + IoU/中心距离简易策略生成，仅用于 S0 数据审计和后续标定复核；S2 多人闸门仍需实现正式策略。

### 6.1 汇总（6 段样本均值）

| 指标 | MediaPipe full | YOLO11n-pose | 对比 |
|---|---:|---:|---|
| 纯推理 FPS（均值） | **62.85** | **25.52** | YOLO 慢约 2.5×（speedup 0.41×） |
| 漏检帧率（均值） | 0.07% | 0.00% | 二者都很低 |
| body_core 抖动（均值，归一化） | 0.0035 | 0.0061 | YOLO 抖动约 1.7× |
| 跨后端 body_core 位置差中位数（均值） | — | — | 0.0147 |

### 6.2 逐样本要点（完整数据见 `outputs/spike/spike_baseline.json`；逐帧 keypoints / track_id 见 `outputs/spike/spike_keypoints.jsonl`）

| 样本 | 帧 | MP FPS | YOLO FPS | speedup | 跨后端差(中位/ P90) | YOLO 多人帧 / 最大人数 |
|---|---:|---:|---:|---:|---|---:|
| 标准-正面 | 250 | 60.2 | 27.5 | 0.46 | 0.013 / 0.025 | 0 / 1 |
| 标准-侧面(长) | 694 | 67.3 | 24.0 | 0.36 | 0.010 / 0.021 | 0 / 1 |
| 学员-1 | 450 | 57.7 | 26.0 | 0.45 | 0.021 / 0.051 | **23 / 4** |
| 学员-4(长) | 618 | 65.2 | 22.6 | 0.35 | 0.024 / 0.051 | **274 / 8** |
| 直拳-正面 | 283 | 65.9 | 26.7 | 0.40 | 0.009 / 0.018 | 0 / 1 |
| 直拳-侧面 | 129 | 60.9 | 26.3 | 0.43 | 0.011 / 0.025 | 0 / 1 |

关键观察：

1. **FPS：本 CPU 上 YOLO11n-pose 比 MediaPipe full 慢约 2.5×。** 离线吞吐动机下，YOLO-only 在本硬件无提速收益。
   （注：YOLO11n 是最小变体，更大变体只会更慢；GPU 下需复测，但需衡量 GPU 成本。）
2. **漏检：两后端都很低（≤0.07%）。** YOLO 在单人/多人帧均能稳定输出关键点。
3. **多人闸门是真实正确性风险，已被实证：** 学员样本 1、4 分别检出最多 4 人、8 人，学员-4 有 **274/618 帧** 为多人。
   YOLO 的"最大框取单人"在这类学员视频里极易选错实例 —— 印证迁移计划 S2 多人闸门的必要性（本期 spike 仅统计，不做闸门）。
4. **抖动 / 跨后端差：** YOLO 抖动约为 MediaPipe 的 1.7×；标准单人样本跨后端差小（0.009–0.013），学员样本偏大（0.021–0.024，与多人/遮挡相关）。

---

## 七、核心指标降级清单（Issue #2，静态代码分析，COCO17 结构性失效）

COCO17 缺少 **嘴角（9/10）、脚跟脚尖（29–32）、手指（17–22）、眼细分（1/3/4/6）**。下表对照 `analysis/tech_eval.py` 与 `core/rule_scoring.py` 实际代码，列出 YOLO-only 下结构性失效/退化的核心评分能力。这是"能力消失"，与硬件/精度无关，GPU 也补不回。

| 指标 / 规则 | 代码位置 | 依赖的缺失点 | YOLO-only 后果 | 业务可接受性 |
|---|---|---|---|---|
| 重心-支撑面（侧面） | `tech_eval.eval_cog_side` → `_foot_edges_x`（约 340 行） | HEEL / FOOT_INDEX | 支撑面边界退化为单踝点，前/后/居中判定基准失真 | **不可接受**（重心是核心评分项） |
| 重心-分段质心 | `tech_eval.eval_cog_com` → `_compute_body_com_single`（约 654 行）foot_l/foot_r 段 | ANKLE+HEEL+FOOT_INDEX | 足部段缺失 → 全身质心(CoM)偏移、可见质量比下降，判定偏差 | **不可接受** |
| 发力顺序-蹬地 | `tech_eval.eval_force_sequence` → `_push_off_ok` / `_calc_heel_lift`（约 1555/1597 行） | HEEL / FOOT_INDEX | 脚跟抬高检测失效，蹬地判定基本不可用 | **不可接受**（发力顺序是核心评分项） |
| 发力顺序-脚旋转 | `eval_force_sequence` → `_foot_angle_deg` / `_rotation_fail_front`（约 1427/1438 行） | HEEL / FOOT_INDEX | 脚旋转角无法计算，正面旋转异常闸门失效 | **不可接受** |
| 后手贴近（护肋/护颌） | `rule_scoring._rule_back_arm_close`（约 207 行） | MOUTH_L / MOUTH_R | 手腕-嘴部距离无法计算，规则无法判定 | 退化为 skipped |
| 护手位置 | `rule_scoring._rule_guard_hand`（约 302 行） | MOUTH_L / MOUTH_R | 同上，护颌距离无法判定 | 退化为 skipped |
| 脚尖平行 | `rule_scoring._rule_feet_parallel`（约 260 行） | HEEL / FOOT_INDEX | 脚尖方向向量无法计算，规则无法判定 | 退化为 skipped |

COCO17 仍可支撑的指标（S4 可做 skip-aware partial eval）：肘角、膝角、站距、鼻尖-手腕相对高度等仅依赖肩/肘/腕/髋/膝/踝的几何量。

**业务结论：YOLO-only(COCO17) 无法承担 full tech_eval。** 重心（支撑面 + 分段质心）与发力顺序（蹬地 + 脚旋转）这两类核心评分项结构性失效，缺失不可接受。
这与迁移计划首页"默认前提"一致：YOLO-only 合理定位是 **实时预览 / 模板匹配(body_core_v1) / skip-aware partial eval**，不进 full tech_eval。

---

## 八、go/no-go 结论（每条引用数字）

**总体结论：有条件 GO —— 进入 S1，但严格限定 YOLO 的定位，不追求"YOLO 替代 MediaPipe full"。**

逐条对照预注册阈值：

1. **离线 FPS 提升比例 0.41 < 1.0 → 未达标。** 本 CPU 上 YOLO 无提速收益，因此 **不以"YOLO 提速替代 MediaPipe"为 S1+ 目标**；YOLO 的价值需在 GPU 复测或定位为 body_core 模板匹配后端时再评估。
2. **漏检率 YOLO 0.0% ≤ 2% → 达标。** 关键点输出稳定，不构成 no-go。
3. **抖动 0.0061，临界略超 0.006 建议值。** 不单独构成 no-go，但说明 YOLO body_core 分数在 S3 标定前不可直接用于对外评分。
4. **跨后端位置差均值 0.0147 ≤ 0.02 → 达标；** 但学员样本 0.021–0.024 偏高，模板匹配可替代性留 S3 用更细阈值收紧判定。
5. **多人风险已实证（最多 8 人、单视频 274 帧多人）→ S2 多人闸门为必做正确性项**，非可选优化。
6. **核心指标降级（第七节）：重心 + 发力顺序结构性失效，不可接受 → YOLO-only 默认排除 full tech_eval（与计划默认前提一致）。**

因此：

- ✅ 进入 **S1（布局隔离 + valid_mask 迁移 + golden 回归）**，因为 S1 工作"无论 YOLO 成不成都有价值"。
- ⚠️ YOLO 定位收敛为：**实时预览 / `body_core_v1` 模板匹配（待 S3 标定）/ skip-aware partial eval**；**不进 full tech_eval**。
- ⚠️ "YOLO 提速"动机在本 CPU **不成立**；是否上 YOLO 的最终理由需在 S3（模板匹配精度）后结合 GPU 复测再定。
- ⛔ 未触发"直接停在 S0 转替代方案"：许可在评估范围内可用、漏检低、核心降级虽严重但 YOLO 定位已主动避开 full eval。

> 若后续目标转为闭源/商业部署且不采购 Enterprise，或 S3 模板匹配精度不达标，则按计划进入"替代方案决策"。

---

## 九、复现实验步骤

```powershell
# 1. 激活环境（依赖见 requirements.txt + ultralytics/torch）
$env:HTTP_PROXY  = "http://127.0.0.1:7890"
$env:HTTPS_PROXY = "http://127.0.0.1:7890"
.\.venv\Scripts\python.exe -m pip install -r requirements.txt --proxy http://127.0.0.1:7890
.\.venv\Scripts\python.exe -m pip install ultralytics torch torchvision --proxy http://127.0.0.1:7890

# 2. 跑 spike（不接主链路）
.\.venv\Scripts\python.exe -m analysis.spike_yolo_baseline `
  --samples docs/yolo_eval_samples.json `
  --yolo-model models/yolo11n-pose.pt `
  --pose-variant full --out outputs/spike

# 输出：
# - outputs/spike/spike_baseline.json
# - outputs/spike/spike_baseline.csv
# - outputs/spike/spike_keypoints.jsonl
```

---

## 十、附：待业务确认 / 后续阶段事项

- 预注册阈值数值目前为"基于 CPU 基线反推的建议值"，请业务在 S1 启动前确认或替换为硬性目标值。
- 若存在 GPU 目标硬件，需在该硬件复测第六节 FPS（结构性降级清单无需复测）。
- YOLO `valid_conf_thr` 本期为占位值 0.5（`calibration_status=unvalidated`），正式标定在 S3（Issue #10），标定前 YOLO 分数不得对外评分。
