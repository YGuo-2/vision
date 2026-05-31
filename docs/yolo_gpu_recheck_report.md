# YOLO 迁移 S5 GPU 复测决策报告（Issue #23）

来源：GitHub Issue #23 `S5：GPU 复测决策门 + YOLO 价值再评估（前置闸门）`
日期：2026-05-31
关联脚本：`analysis/bench_annotate_fps.py`（独立 benchmark harness，不接主链路）
关联样本：`docs/yolo_eval_samples.json`（6 段 S0 同批样本）

> **结论先行：no-go（当前环境不启动 #25 / #26）。**
> 本机硬件层能被 `nvidia-smi` 看到：NVIDIA GeForce RTX 4060 Laptop GPU，Driver 581.08，
> Driver CUDA 13.0。但当前 `.venv` 内 `torch=2.12.0+cpu`，`torch.cuda.is_available() = False`，
> `torch_cuda_device_count = 0`。因此本 issue 的 GPU 复测前置门未通过：0/6 个样本产生有效 GPU
> `annotate()` 端到端 FPS 结果，不能把实时入口或默认切换建立在不存在的 GPU 数字上。

---

## 一、实验环境固定

| 项 | 值 |
|---|---|
| 操作系统 | Windows 11（10.0.26200） |
| Python | 3.13.9（复用仓库 `.venv`） |
| OpenCV | 4.13.0 |
| MediaPipe | 0.10.31 |
| Ultralytics | 8.4.57 |
| Torch | 2.12.0+cpu |
| `torch.cuda.is_available()` | **False** |
| `torch_cuda_device_count` | **0** |
| `torch.version.cuda` | `None` |
| `nvidia-smi` | 可用 |
| GPU 硬件 | NVIDIA GeForce RTX 4060 Laptop GPU |
| NVIDIA Driver | 581.08 |
| Driver CUDA | 13.0 |
| YOLO 模型文件 | `models/yolo11n-pose.pt`（本地存在，6,255,593 bytes） |
| MediaPipe Pose 模型 | `models/pose_landmarker_full.task`（本地存在，9,398,198 bytes） |
| MediaPipe Hand 模型 | `models/hand_landmarker.task`（本地存在，7,819,105 bytes） |

环境探针命令：

```powershell
nvidia-smi
@'
import torch
print(torch.__version__)
print(torch.cuda.is_available())
print(torch.cuda.device_count() if torch.cuda.is_available() else 0)
'@ | E:\CodeProject\vision\.venv\Scripts\python.exe -
```

---

## 二、预注册阈值（先写数字，再判定）

本 issue 是 S5 前置闸门，目标是判断是否值得扩实时入口 / UI / 默认切换。与 S0 不同，本轮必须看
`annotate()` 端到端链路，而不是只看裸 keypoint FPS。

| 指标 | 预注册阈值 | 判定方向 | 本次实测 | 是否达标 |
|---|---:|---|---:|---|
| GPU runtime 可用性 | `torch.cuda.is_available() == True` 且 device_count >= 1 | 不满足则不跑实时扩展 | `False`，device_count=0 | ❌ |
| S0 同批样本 GPU 有效复测覆盖 | 6/6 个样本都有有效 GPU benchmark 行 | 少于 6 段则不得 go | 0/6 | ❌ |
| `annotate()` Hands 关：YOLO body 预览 / MediaPipe pose-only FPS 比 | >= 1.30 | 低于则实时提速动机不成立 | 无有效 GPU 行 | ❌ |
| `annotate()` Hands 开：YOLO body + MediaPipe Hands / MediaPipe Pose+Hands FPS 比 | >= 1.20 | 低于则 UI/实时扩展不成立 | 无有效 GPU 行 | ❌ |
| YOLO 裸推理 GPU FPS | >= MediaPipe full CPU S0 均值 62.85 FPS，且 YOLO/MP >= 1.0 | 低于则不作为提速依据 | 无有效 GPU 行 | ❌ |
| YOLO 失败 / 漏检帧率 | <= 2% | 高于则 no-go | 无有效 GPU 行 | ❌ |
| body_core 抖动中位数（归一化坐标） | <= 0.006 | 高于则 no-go | 无有效 GPU 行 | ❌ |

解释：本轮没有把缺失 GPU 行当成“未知可乐观推进”。实时入口会改变用户可见路径，必须先有完整
GPU 数字；当前有效 GPU benchmark 行为 0，所以按预注册阈值判 no-go。

---

## 三、benchmark harness 边界

新增 `analysis/bench_annotate_fps.py`，只做以下事情：

- 读取 `docs/yolo_eval_samples.json` 的 6 段样本。
- MediaPipe 路径调用 `MediaPipePipeline.annotate()`，分 Hands 开 / 关两档。
- YOLO 路径调用 `YoloPoseAdapter.infer_frame()`，只绘制 `body_core_v1` 有效点；Hands 开时只额外调用
  MediaPipe HandLandmarker，不调用 MediaPipe Pose 补点。
- CUDA 可用时，YOLO 记录 `yolo_raw_infer_fps`、`yolo_miss_rate`、
  `yolo_body_core_missing_rate`、`yolo_body_core_jitter_median`，用于对照第二节裸推理 FPS、
  失败 / 漏检帧率与抖动阈值。
- 写出 `outputs/gpu_recheck/gpu_recheck_env.json`、
  `outputs/gpu_recheck/annotate_fps_gpu_recheck.json`、CSV；`outputs/` 受 `.gitignore` 排除。
- 不修改 `apps/main.py`、不改 `MediaPipePipeline` 默认行为、不接入主链路。

本次执行命令（因 CUDA runtime 不可用，脚本按预期跳过 GPU benchmark）：

```powershell
E:\CodeProject\vision\.venv\Scripts\python.exe -m analysis.bench_annotate_fps `
  --samples docs/yolo_eval_samples.json `
  --asset-root E:\CodeProject\vision `
  --models-dir E:\CodeProject\vision\models `
  --yolo-model E:\CodeProject\vision\models\yolo11n-pose.pt `
  --device cuda `
  --out outputs/gpu_recheck
```

得到的关键事实：

- `torch.cuda.is_available() = False`
- `torch_cuda_device_count = 0`
- `requested_device = cuda`
- `samples_total = 6`
- `status = skipped`
- `skip_reason = torch_cuda_unavailable`
- 有效 GPU benchmark rows = 0

---

## 四、go / no-go 判定

**判定：no-go。**

逐条对照：

1. GPU runtime 可用性：`False`，低于预注册门槛 `True` → no-go。
2. S0 同批样本 GPU 覆盖：0/6，低于预注册门槛 6/6 → no-go。
3. Hands 关 `annotate()` FPS 比：无有效 GPU 行，无法证明 >= 1.30 → no-go。
4. Hands 开 `annotate()` FPS 比：无有效 GPU 行，无法证明 >= 1.20 → no-go。
5. 裸推理 GPU FPS / 漏检 / 抖动：无有效 GPU 行，无法作为扩入口依据。

注意：这不是说 RTX 4060 硬件没有价值，而是当前仓库 `.venv` 软件栈不能把 YOLO 推理放到 CUDA
设备上。S5 实时 / UI 扩展不能以“未来可能能跑 GPU”为依据进入实现。

---

## 五、对 S5 / S6 的分流结论

- #25（CLI `apps/main.py --backend yolo` 实时预览）：**关闭 / 不实现**，除非后续单独换成 CUDA-enabled
  torch 环境并重新跑满 6/6 GPU benchmark，且 Hands 开 / 关 FPS 比分别达到 1.20 / 1.30。
- #26（UI 后端选择 + 完整度提示）：**关闭 / 不实现**，因为它依赖 #25 与实时 go 结论。
- #24（batch backend/layout 参数 + metadata 透传）：**可独立推进**。它服务离线调试 / 标定分数接线，
  不依赖 #23 的实时 go 结论；仍必须保持 `calibration_status=unvalidated` 与
  `score_authorized=False`。
- #27（Hybrid）：**默认不实现**；若未来要推翻，必须先有 GPU 环境下 Hybrid 补点代价的数字依据。
- #28（S6 默认切换决策）：**已执行**，见 `docs/yolo_default_switch_decision.md`。当前 no-go 分支下结论为
  **全部不切默认，仅保留离线 / 实验入口**。

---

## 六、CLI 实时预览决议（Issue #25）

**结论：不实现 `apps/main.py --backend yolo` / `--feature-layout body_core_v1` 实时预览入口。**

Issue #25 的启动条件是 #23 GPU 复测 = go；当前 #23 已按预注册阈值判定 no-go，因此本期不把
YOLO 接入 `apps/main.py` 的实时预览主链路，也不新增会被用户误认为可用的 `--backend yolo`
参数。`apps/main.py` 继续保持 MediaPipe 旧默认行为：`--source` / `--pose` / `--workers` 等既有
参数不变，实时预览仍由 `MediaPipePipeline.annotate()` 负责。

本决议按 Issue #25 的验收标准逐条对照：

| 判据 | Issue #25 要求 | 当前数字 / 事实 | 结论 |
|---|---|---|---|
| 前置条件 | #23 GPU 复测 = go 才启动 | #23 判定 no-go | 不启动 |
| GPU runtime | CUDA runtime 可用 | `torch.cuda.is_available() = False`，device_count=0 | 不满足 |
| 样本覆盖 | 6/6 个样本有有效 GPU benchmark 行 | 0/6 | 不满足 |
| Hands 关实时提速 | YOLO body 预览 / MP pose-only FPS 比 >= 1.30 | 无有效 GPU 行 | 不满足 |
| Hands 开实时提速 | YOLO body + MP Hands / MP Pose+Hands FPS 比 >= 1.20 | 无有效 GPU 行 | 不满足 |
| 评分边界 | YOLO-only 不产出规则 / tech_eval 对外评分 | #24 仅保留离线 batch 调试 / 标定入口，`score_authorized=False` | 满足边界 |

因此 #25 当前只能关闭，不做实现。若未来要重新打开 CLI 实时预览入口，必须先满足第九节 GPU
复测前置条件，并另开新的实现子任务；在此之前，不得预先写入 YOLO realtime runtime 或参数入口。

---

## 七、UI 后端选择决议（Issue #26）

**结论：不实现 `apps/app_ui.py` 的 YOLO 后端选择控件 / 规则完整度提示。**

Issue #26 的启动条件是 #25 已落地；当前 #25 已按 #23 no-go 关闭，不存在可供 UI 选择的
`apps/main.py --backend yolo` 实时预览入口。因此本期不在 Tkinter UI 中增加 YOLO 后端选择、
`body_core_v1` 布局选择、YOLO-only 规则完整度提示或未标定评分展示。`apps/app_ui.py` 继续保持
MediaPipe 旧默认界面与行为。

本决议按 Issue #26 的验收标准逐条对照：

| 判据 | Issue #26 要求 | 当前数字 / 事实 | 结论 |
|---|---|---|---|
| 前置条件 | #25 落地后启动 | #25 已关闭 / 不实现 | 不启动 |
| GPU runtime | 实时 UI 扩展需 #23 go | `torch.cuda.is_available() = False`，device_count=0 | 不满足 |
| 样本覆盖 | 6/6 个样本有有效 GPU benchmark 行 | 0/6 | 不满足 |
| CLI 依赖 | UI 后端选择依赖 `apps/main.py --backend yolo` | #25 不实现该入口 | 不满足 |
| 评分边界 | YOLO-only 不显示对外评分 / 合格判定 | #24 仅保留离线 batch 调试 / 标定入口，`score_authorized=False` | 满足边界 |

因此 #26 当前只能关闭，不做实现。若未来要重新打开 UI 后端选择，必须先满足第九节 GPU
复测前置条件，并在 #25 后续实现子任务真正落地后另开 UI 实现子任务；在此之前，不得预先写入
YOLO UI control、YOLO-only 完整度展示或未标定评分入口。

---

## 八、Hybrid 决议（Issue #27）

**结论：不实现 `yolo_body_mp_pose_supplement`，代码库不保留半成品 Hybrid 路径。**

本决议按 Issue #27 的触发条件逐条对照：

| 判据 | 触发实现所需条件 | 当前数字 / 事实 | 结论 |
|---|---|---|---|
| GPU runtime | `torch.cuda.is_available() == True` 且 device_count >= 1 | `False`，device_count=0 | 不满足 |
| S0 同批样本 GPU 覆盖 | 6/6 个样本跑完有效 GPU benchmark | 0/6 | 不满足 |
| 实时 / 默认入口提速 | Hands 关 FPS 比 >= 1.30；Hands 开 FPS 比 >= 1.20 | 无有效 GPU 行 | 不满足 |
| CPU 基线收益 | 至少不慢于 MediaPipe full | S0 CPU 纯推理 speedup = 0.41（YOLO 更慢） | 不满足 |
| 补点价值 | 补回重心 / 发力顺序所需脚跟脚尖，且性能代价可接受 | COCO17 缺脚跟脚尖；靠 MediaPipe Pose 补脚/脸本质仍需跑完整 PoseLandmarker | 不满足 |

因此，Hybrid 的唯一触发条件没有满足：既没有 GPU 有效复测数字证明补点代价可接受，也没有证据证明
“YOLO body + MediaPipe Pose supplement”比直接使用 MediaPipe full 更有工程收益。当前更稳妥的边界是：

- 实时 / UI：按 #23 no-go，#25 / #26 不实现。
- 离线 batch：按 #24，只保留显式 `body_core_v1` 调试 / 标定入口，且 `score_authorized=False`。
- full tech_eval / 规则评分：默认仍 MediaPipe full；YOLO-only / Hybrid 不进入对外评分。

若未来要重新评估 Hybrid，必须先单独满足以下全部条件，再另开实现子任务：

1. CUDA-enabled torch 环境下 `analysis/bench_annotate_fps.py --device cuda` 对 6/6 样本跑完。
2. 新增 Hybrid 专用 benchmark，明确记录第二个 PoseLandmarker 的额外耗时、内存 / 显存占用。
3. 证明补回的脚跟脚尖 / 嘴角能让重心、发力顺序等核心指标恢复评估，且误判样例可接受。
4. Hybrid 仍只能作为离线显式模式，不能进入默认 / 实时路径，直到 S6 重新决策。

---

## 九、后续若要复测 GPU 的前置条件

若之后要重新打开 #25 / #26，先不要改主链路，先满足以下条件并复跑本报告命令：

1. `.venv` 内安装 CUDA-enabled torch，使 `torch.cuda.is_available() == True`。
2. `analysis/bench_annotate_fps.py --device cuda` 对 `docs/yolo_eval_samples.json` 6/6 样本跑完。
3. 报告 Hands 关 / Hands 开两档 `annotate()` FPS 比、YOLO 裸推理 FPS、漏检率、抖动，并逐条对照第二节阈值。
4. 只有全部通过，才允许重新开实时 / UI 扩展 issue。
