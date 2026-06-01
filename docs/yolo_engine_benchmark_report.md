# YOLO P2a TensorRT / ONNX 导出与 benchmark spike 报告（Issue #40）

来源：GitHub Issue #40 `S5：P2a TensorRT / ONNX 导出与 engine benchmark spike`
报告日期：2026-06-01
关联脚本：`analysis/bench_annotate_fps.py`
关联样本：`docs/yolo_eval_samples.json`（6 段 S0 同批样本）

> **结论先行：P2a 不建议直接开启 P2b TensorRT production adapter。**
> 本轮 `models/yolo11n-pose.pt` 可导出 ONNX，且 ONNXRuntime CUDA smoke 在 6/6 样本上跑通；
> 但 TensorRT engine 导出仍被本机 Python 依赖阻断，`tensorrt` 模块缺失。已尝试 NVIDIA
> 官方 `tensorrt-cu12` pip 路径，但依赖包体为 2.2GB，走本地代理长时间未完成。本 issue
> 只保留 export + benchmark + report，不把 engine/ONNX 接入生产 adapter，不放开任何 YOLO
> 对外评分或默认入口。

---

## 一、环境与依赖状态

| 项 | 值 |
|---|---|
| 操作系统 | Windows 11（10.0.26200） |
| Python | 3.13.9（仓库 `.venv`） |
| OpenCV | 4.13.0 |
| MediaPipe | 0.10.31 |
| Ultralytics | 8.4.57 |
| Torch | 2.11.0+cu128 |
| `torch.cuda.is_available()` | True |
| `torch.version.cuda` | 12.8 |
| GPU | NVIDIA GeForce RTX 4060 Laptop GPU |
| NVIDIA Driver | 581.08 |
| Driver CUDA | 13.0 |
| ONNX | 1.21.0 |
| ONNX Runtime | 1.26.0（`onnxruntime-gpu`） |
| ONNX Runtime providers | `TensorrtExecutionProvider`, `CUDAExecutionProvider`, `CPUExecutionProvider` |
| TensorRT Python | 缺失：`ModuleNotFoundError("No module named 'tensorrt'")` |

环境探针来源：

```powershell
.\.venv\Scripts\python.exe -m analysis.bench_annotate_fps `
  --samples docs\yolo_eval_samples.json `
  --asset-root E:\CodeProject\vision `
  --models-dir E:\CodeProject\vision\models `
  --yolo-model E:\CodeProject\vision\models\yolo11n-pose.onnx `
  --device cuda `
  --yolo-delegate onnxruntime `
  --limit-frames 1 `
  --warmup-frames 1 `
  --out outputs\engine_recheck_issue40_onnx_smoke
```

输出文件：

- `outputs/engine_recheck_issue40_onnx_smoke/gpu_recheck_env.json`
- `outputs/engine_recheck_issue40_onnx_smoke/annotate_fps_gpu_recheck.json`
- `outputs/engine_recheck_issue40_onnx_smoke/annotate_fps_gpu_recheck.csv`

`outputs/`、`models/*.onnx`、`models/*.engine` 均受 `.gitignore` 排除，导出产物不入库。

---

## 二、TensorRT engine 导出尝试

执行命令：

```powershell
$env:HTTP_PROXY  = "http://127.0.0.1:7890"
$env:HTTPS_PROXY = "http://127.0.0.1:7890"
.\.venv\Scripts\python.exe -c "from ultralytics import YOLO; m=YOLO('models/yolo11n-pose.pt'); out=m.export(format='engine', half=True, imgsz=640, device=0, workspace=2, verbose=False); print(out)"
```

结果：

- ONNX 中间产物导出成功：`models\yolo11n-pose.onnx`，约 11.3MB。
- TensorRT engine 转换失败，失败点为 Python runtime 缺失：

```text
ERROR TensorRT: export failure 1.1s: No module named 'tensorrt'
ModuleNotFoundError: No module named 'tensorrt'
```

补依赖尝试：

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade tensorrt-cu12 `
  --extra-index-url https://pypi.nvidia.com `
  --proxy http://127.0.0.1:7890
```

结果：命令进入 `tensorrt_cu12_libs-11.0.0.114-py3-none-win_amd64.whl`
下载阶段，wheel 大小约 2.2GB；本轮走代理长时间未完成，已中止以保持 P2a spike 有界。
因此本 PR 不生成 `.engine`，不做 TensorRT smoke 数字。

参考资料：

- Ultralytics export 文档列出 `engine`、`onnx` 格式，并支持 `imgsz`、`half`、`device`、`workspace` 等导出参数：<https://docs.ultralytics.com/modes/export/>
- NVIDIA TensorRT 安装文档提供 Python pip 包路径，CUDA 12 线使用 `tensorrt-cu12`：<https://docs.nvidia.com/deeplearning/tensorrt/latest/installing-tensorrt/installing.html>

---

## 三、ONNXRuntime CUDA smoke

为避免 ONNX/TensorRT exported model 被不适用的 PyTorch-only CPU/FP16 case 污染，本轮 benchmark
增加 `--yolo-delegate` 标签与模型后缀自动推断：

- `.pt`：`pytorch`
- `.onnx`：`onnxruntime`
- `.engine`：`tensorrt`

对于非 PyTorch delegate，benchmark 只保留 MediaPipe CPU baseline 与 exported model CUDA case；
PyTorch-only 的 CPU baseline、FP16 640/512 opt-in case 仍只在 `.pt` benchmark 中出现。

ONNXRuntime CUDA smoke 结果（`--limit-frames 1 --warmup-frames 1`，6 个样本）：

| 方案 | 样本数 | annotate FPS 均值 | raw infer FPS 均值 | p50 延迟均值(ms) | miss 均值 | body_core valid 均值 | 多人复核 |
|---|---:|---:|---:|---:|---:|---:|---|
| PyTorch FP32 | 6 | 43.456 | 45.432 | 25.740 | 0.000 | 1.000 | 否 |
| PyTorch FP16 640 | 6 | 53.160 | 56.304 | 20.500 | 0.000 | 1.000 | 否 |
| PyTorch FP16 512 | 6 | 51.655 | 54.669 | 21.235 | 0.000 | 1.000 | 否 |
| ONNXRuntime CUDA | 6 | 59.173 | 63.075 | 21.674 | 0.000 | 1.000 | 否 |
| PyTorch FP32 + Hands | 6 | 18.515 | 37.102 | 59.186 | 0.000 | 1.000 | 否 |
| PyTorch FP16 640 + Hands | 6 | 18.039 | 41.426 | 62.696 | 0.000 | 1.000 | 否 |
| PyTorch FP16 512 + Hands | 6 | 20.613 | 51.532 | 50.847 | 0.000 | 1.000 | 否 |
| ONNXRuntime CUDA + Hands | 6 | 28.568 | 68.336 | 40.044 | 0.000 | 1.000 | 否 |

逐样本 ONNXRuntime CUDA 行：

| 样本 | case | annotate FPS | raw infer FPS | p50 延迟(ms) | miss | body_core valid | gate |
|---|---|---:|---:|---:|---:|---:|---|
| std_front | yolo_body_only | 81.141 | 87.789 | 12.324 | 0.000 | 1.000 | ok |
| std_front | yolo_body_mp_hands | 42.545 | 85.846 | 23.505 | 0.000 | 1.000 | ok |
| std_side_long | yolo_body_only | 67.045 | 71.565 | 14.915 | 0.000 | 1.000 | ok |
| std_side_long | yolo_body_mp_hands | 42.844 | 89.105 | 23.340 | 0.000 | 1.000 | ok |
| student_1 | yolo_body_only | 85.658 | 92.009 | 11.674 | 0.000 | 1.000 | ok |
| student_1 | yolo_body_mp_hands | 26.290 | 96.323 | 38.037 | 0.000 | 1.000 | ok |
| student_4_long | yolo_body_only | 68.717 | 73.201 | 14.552 | 0.000 | 1.000 | ok |
| student_4_long | yolo_body_mp_hands | 25.120 | 84.802 | 39.808 | 0.000 | 1.000 | ok |
| punch_front | yolo_body_only | 28.017 | 29.050 | 35.693 | 0.000 | 1.000 | ok |
| punch_front | yolo_body_mp_hands | 17.399 | 28.367 | 57.473 | 0.000 | 1.000 | ok |
| punch_side | yolo_body_only | 24.460 | 24.836 | 40.884 | 0.000 | 1.000 | ok |
| punch_side | yolo_body_mp_hands | 17.212 | 25.573 | 58.099 | 0.000 | 1.000 | ok |

解释：

- ONNXRuntime CUDA 在 body-only smoke 均值上高于 PyTorch FP16 640，但 `--limit-frames 1`
  仍是 smoke，不足以作为 P2b production adapter 的唯一依据。
- Hands 开启时端到端性能主要受 MediaPipe Hands 与串行渲染限制，ONNXRuntime 提升裸推理后仍不能代表实时 UI 总体验已经达标。
- 质量守卫在本轮 1 帧 smoke 中没有触发：`miss=0`、`body_core valid=1.0`、多人闸门未要求复核。
  这只能说明短 smoke 未暴露问题，不能替代全量质量回归。

---

## 四、go / no-go

本 issue 的 go/no-go 只回答“是否另开 P2b engine adapter opt-in”：

| 条件 | 本轮结论 |
|---|---|
| TensorRT engine 可导出 | 否，缺 `tensorrt` Python runtime；补依赖下载未完成 |
| ONNXRuntime CUDA 可运行 | 是，6/6 样本 smoke 全部 `status=ok` |
| 导出产物未入库 | 是，`.onnx/.engine` 与 `outputs/` 均被 ignore |
| 是否建议立即另开 P2b TensorRT adapter | 否 |
| 是否建议另开 ONNX adapter | 暂不建议；需先补全量 benchmark 与质量守卫验证 |

最终判定：

1. 不创建 P2b TensorRT production adapter issue，直到 TensorRT Python runtime 安装成功并跑出至少
   6 样本稳定态 engine benchmark。
2. ONNXRuntime CUDA 可作为后续候选，但本轮只证明 smoke 可行；若要进入生产 adapter，需另开
   “ONNXRuntime full benchmark + adapter spike” 并跑完整帧数、body_core jitter、多人闸门与
   `score_authorized=False` 不变量。
3. #23 no-go 仍不被推翻。YOLO/ONNX 性能优化不改变 COCO17 缺点，也不授权 YOLO-only 进入
   full tech_eval 或对外报告。
