# YOLO 后端 GPU 就绪复盘与修复结果

- 报告日期：2026-06-01
- 核查范围：YOLO 视觉后端是否可用、RTX 4060 是否被 torch 调用、#23–#28 决策是否需要修正
- 核查方式：实跑验证 + CUDA 版 torch 安装 + #23 GPU benchmark 复测
- 关联材料：`docs/yolo_gpu_recheck_report.md`、`docs/yolo_default_switch_decision.md`、`change.md`

---

## 一、结论先行

**根因已修复：此前 `.venv` 安装了 CPU 版 torch，导致 RTX 4060 没被调用；现在已换成 CUDA 版
`torch=2.11.0+cu128` / `torchvision=0.26.0+cu128`，`torch.cuda.is_available() == True`，
设备为 NVIDIA GeForce RTX 4060 Laptop GPU。**

**决策也已重判：#23 不再用“CPU torch / 0 行 GPU 数据”作为依据。真实 GPU 复测已跑满 6/6 样本，
但端到端实时阈值仍未通过，因此 #25 / #26 继续关闭，#28 继续全部不切默认。**

这次修复推翻的是错误环境前提，不是直接打开 YOLO 实时/UI/default。模板匹配、规则评分和对外报告仍受
#10 标定结论与 COCO17 缺点约束，`score_authorized` 不因 GPU 修复自动变为 True。

---

## 二、修复前问题

旧状态：

| 项 | 旧值 | 问题 |
|---|---|---|
| GPU 硬件 | NVIDIA GeForce RTX 4060 Laptop GPU | 硬件存在 |
| NVIDIA Driver | 581.08（Driver CUDA 13.0） | 驱动正常 |
| torch | `2.12.0+cpu` | 纯 CPU wheel |
| `torch.cuda.is_available()` | `False` | 无法调用 RTX 4060 |
| #23 GPU benchmark | 0/6 有效 GPU 行 | 环境错误导致无数据 |

错误链路：

```text
torch CPU wheel
  -> torch.cuda.is_available() = False
  -> #23 0/6 GPU 行 no-go
  -> #25/#26/#28 被 CPU torch 前提连锁锁死
```

这个前提不应作为最终 S5/S6 决策依据，必须先修环境、再重跑真实 GPU 数据。

---

## 三、环境修复

Python 3.13 下 `cu121` 索引没有可安装的 torch wheel；实际可用组合是官方 `cu128` wheel。

安装命令：

```powershell
$env:HTTP_PROXY  = "http://127.0.0.1:7890"
$env:HTTPS_PROXY = "http://127.0.0.1:7890"
E:\CodeProject\vision\.venv\Scripts\python.exe -m pip install --upgrade --force-reinstall `
  torch==2.11.0+cu128 torchvision==0.26.0+cu128 `
  --index-url https://download.pytorch.org/whl/cu128 `
  --proxy http://127.0.0.1:7890
```

验证命令：

```powershell
E:\CodeProject\vision\.venv\Scripts\python.exe -c "import torch, torchvision; print(torch.__version__); print(torchvision.__version__); print(torch.cuda.is_available()); print(torch.version.cuda); print(torch.cuda.get_device_name(0))"
```

实测结果：

| 项 | 修复后值 |
|---|---|
| torch | `2.11.0+cu128` |
| torchvision | `0.26.0+cu128` |
| `torch.cuda.is_available()` | `True` |
| `torch.version.cuda` | `12.8` |
| device | `NVIDIA GeForce RTX 4060 Laptop GPU` |

---

## 四、#23 GPU 复测结果

复测命令：

```powershell
E:\CodeProject\vision\.venv\Scripts\python.exe -m analysis.bench_annotate_fps `
  --samples docs/yolo_eval_samples.json `
  --asset-root E:\CodeProject\vision `
  --models-dir E:\CodeProject\vision\models `
  --yolo-model E:\CodeProject\vision\models\yolo11n-pose.pt `
  --device cuda `
  --out outputs/gpu_recheck
```

结果摘要：

| 指标 | 阈值 | 实测 | 结论 |
|---|---:|---:|---|
| GPU 有效样本覆盖 | 6/6 | 6/6 | 达标 |
| Hands 关 FPS 比 | >= 1.30 | min=0.586，mean=0.994，仅 1/6 达标 | 不达标 |
| Hands 开 FPS 比 | >= 1.20 | min=0.735，mean=0.904，0/6 达标 | 不达标 |
| YOLO raw FPS | >= 62.85 | min=22.363，mean=41.343，0/6 达标 | 不达标 |
| YOLO 漏检率 | <= 2% | max=0.0% | 达标 |
| body_core 抖动 | <= 0.006 | max=0.0104，3/6 超阈值 | 不达标 |

结论：CUDA 环境修好了，真实 GPU 复测也跑满了；但 #23 的实时入口 go 条件仍不满足。

---

## 五、决策修正

- #23：从“CPU torch 导致无 GPU 数据 no-go”修正为“CUDA 可用、6/6 有效，但真实性能 / 抖动阈值 no-go”。
- #25：继续不实现 `apps/main.py --backend yolo` 实时入口；依据改为真实 GPU benchmark 不达标。
- #26：继续不实现 UI 后端选择；因为 #25 没有可供 UI 选择的实时入口。
- #27：继续不实现 Hybrid；CUDA 可用不等于 Hybrid 价值成立，仍缺 Hybrid 专用 benchmark 和补点收益证据。
- #28：继续全部不切默认；实时链路依据 #23 CUDA 实测 no-go，模板/评分链路仍依据 #10 标定与 COCO17 缺点。

---

## 六、仍需守住的边界

- 不得把 YOLO-only 分数用于对外评分，`score_authorized=False` 仍成立。
- 不得伪造 COCO17 缺失的嘴角、手指、脚跟、脚尖。
- MediaPipe 旧默认路径（`pose33_v3`、`infer()`、`annotate()`）不得改变。
- 若未来要重开 #25/#26，必须先有新的 GPU 优化复测通过，并另开实现子任务。
