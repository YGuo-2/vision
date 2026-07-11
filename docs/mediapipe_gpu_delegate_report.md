# MediaPipe GPU delegate opt-in 可行性报告（Issue #43）

日期：2026-06-02

## 2026-07-10：MediaPipe 0.10.31 / 0.10.35 双摄首屏优化门控复测

### 结论

- **版本升级 no-go：** 保持 `mediapipe==0.10.31`。`0.10.35` 未在当前 VIDEO-mode Pose/Hands 链路达到相关指标改善 `>=10%`，同时绝对进程峰值 RSS 明显增加。
- **GPU UI no-go：** 不增加 Tkinter GPU 开关。Windows 的 `0.10.35` wheel 对 12 次 GPU pipeline 请求全部回退 CPU，错误为 `ImageCloneCalculator: GPU processing is disabled in build flags`，不满足 `active_delegate=gpu` 的前置条件。
- **发布说明不直接转化为本项目性能收益：** 0.10.35 的 API3、calculator、构建和跨平台修复可以作为未来升级候选信息，但本次真实样本 A/B 没有证明它能缩短 Tkinter 双摄点击开始到预览出现的时间。当前首屏优化继续依赖摄像头预热、原子双帧交付和模型加载期裸帧过渡。

### 隔离环境和方法

- Windows / Python `3.13.9`，两套独立 venv。
- 两边统一 OpenCV `4.13.0`、NumPy `2.4.4`、相同 `.task` 模型和 `docs/yolo_eval_samples.json` 的 6 段真实视频。
- 每个样本每档先跑 5 帧 warmup，再计时 60 帧；CPU 版本对比串行执行，避免两个 benchmark 进程互相争用。
- 指标为 6 个样本的中位数；峰值内存为 benchmark 进程 RSS 峰值。

| case | version | init s | first annotate s | FPS | P90 ms | P99 ms | peak RSS MB |
|:---|:---|---:|---:|---:|---:|---:|---:|
| pose-only CPU | 0.10.31 | 0.077 | 0.026 | 70.183 | 14.857 | 21.441 | 231.758 |
| pose-only CPU | 0.10.35 | 0.074 | 0.026 | 69.375 | 15.035 | 20.017 | 273.830 |
| pose+hands CPU | 0.10.31 | 0.095 | 0.043 | 31.416 | 37.335 | 41.890 | 295.340 |
| pose+hands CPU | 0.10.35 | 0.097 | 0.039 | 31.979 | 38.094 | 41.199 | 338.529 |

当前锁定版本 `0.10.31` 的同批 6 视频 GPU 门控结果：

| case | requested | active | GPU/CPU FPS 中位数 | 门槛 | decision |
|:---|:---|:---|---:|---:|:---|
| pose-only | gpu | gpu (6/6) | 1.0020x | >=1.30x | no-go |
| pose+hands | gpu | gpu (6/6) | 1.0126x | >=1.20x | no-go |

因此即使 `0.10.31` 在本机能够保持 `active_delegate=gpu`，实际端到端吞吐也只是在 CPU 附近波动，远未达到增加 UI 开关的门槛；`0.10.35` 则更早在 active delegate 前置条件上失败。

逐样本比值的中位数显示：

- pose-only：`0.10.35 / 0.10.31` FPS `0.984x`，P90 `1.025x`，峰值 RSS `1.187x`。
- pose+hands：`0.10.35 / 0.10.31` FPS `0.983x`，P90 `1.029x`，峰值 RSS `1.152x`。
- `0.10.35` GPU 请求实际均为 `active_delegate=cpu`，因此不计算或宣称 GPU 加速比；回退后观察到的约 `1.01x` FPS 波动不属于 GPU 收益。

### 证据与复现

本地原始结果位于 gitignored 的：

- `outputs/mediapipe_ab/mp_031_cpu_serial/`
- `outputs/mediapipe_ab/mp_035_cpu_serial/`
- `outputs/mediapipe_ab/mp_031/`
- `outputs/mediapipe_ab/mp_035/`

benchmark 新增 `--mediapipe-only`，并记录 `active_delegate`、`delegate_fallback_reason`、`peak_rss_mb` 和 `rss_delta_mb`，用于避免混入 YOLO case 或把 GPU 回退误判为 GPU 成功。

## 结论

本机 `mediapipe==0.10.31` 的 Tasks Python API 暴露 `BaseOptions(delegate=...)`，且 `BaseOptions.Delegate` 包含 `CPU` / `GPU`。在 Windows 11 + RTX 4060 Laptop GPU 环境下，`PoseLandmarker` 与 `HandLandmarker` 使用 `BaseOptions.Delegate.GPU` 均可初始化并完成一帧 `detect_for_video()` smoke。

但短帧实测没有证明 GPU delegate 对当前桌面实时链路有收益：

| case | hands | delegate | timed frames | init_sec | annotate_fps | p50 ms | p90 ms | p99 ms | status |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `mediapipe_pose_only` | false | cpu | 30 | 0.0875 | 65.162 | 15.012 | 15.720 | 23.056 | ok |
| `mediapipe_pose_hands` | true | cpu | 30 | 0.1072 | 34.862 | 26.073 | 32.797 | 44.863 | ok |
| `mediapipe_gpu_pose_only` | false | gpu | 30 | 0.0833 | 65.008 | 14.881 | 16.140 | 23.248 | ok |
| `mediapipe_gpu_pose_hands` | true | gpu | 30 | 0.1231 | 34.757 | 26.828 | 32.331 | 44.740 | ok |

Go / no-go：

- **Go**：保留 `PipelineConfig(delegate="gpu")` 与 benchmark `--include-mediapipe-gpu` 作为显式 opt-in spike / 复测入口。
- **No-go**：不得默认启用 MediaPipe GPU delegate；当前数据不支持把它作为默认实时提速方案。
- **No-go**：不得借此放宽 YOLO 侧 `score_authorized=False`、`calibration_status=unvalidated` 或默认入口约束。

## 环境

来源：`outputs/mediapipe_gpu_delegate_issue43_smoke/gpu_recheck_env.json`

- OS：Windows 11 `10.0.26200`
- Python：`3.13.9`
- MediaPipe：`0.10.31`
- OpenCV：`4.13.0`
- GPU：`NVIDIA GeForce RTX 4060 Laptop GPU`
- NVIDIA driver：`581.08`
- driver CUDA：`13.0`
- torch：`2.11.0+cu128`
- `torch.cuda.is_available()`：`True`

## API 探针

命令：

```powershell
$env:PYTHONIOENCODING='utf-8'
.\.venv\Scripts\python.exe -c "import mediapipe as mp, inspect; Base=mp.tasks.BaseOptions; print('mediapipe', mp.__version__); print('signature', inspect.signature(Base)); Delegate=getattr(Base, 'Delegate', None); print('Delegate', Delegate); print('members', list(getattr(Delegate, '__members__', {}).items()) if Delegate is not None else None)"
```

结果摘要：

```text
mediapipe 0.10.31
signature (model_asset_path: Optional[str] = None, model_asset_buffer: Optional[bytes] = None, delegate: Optional[mediapipe.tasks.python.core.base_options.BaseOptions.Delegate] = None) -> None
Delegate <enum 'Delegate'>
members [('CPU', <Delegate.CPU: 0>), ('GPU', <Delegate.GPU: 1>)]
```

## 初始化 smoke

对 `models/pose_landmarker_full.task` 与 `models/hand_landmarker.task` 分别构造 CPU / GPU delegate 的 VIDEO mode landmarker，并对一帧 480x640 空图调用 `detect_for_video()`。

结果：

| probe | status | init_sec | infer_sec | exception |
| --- | --- | ---: | ---: | --- |
| `pose_cpu` | ok | 0.089465 | 0.013924 | 无 |
| `hand_cpu` | ok | 0.027235 | 0.012311 | 无 |
| `pose_gpu` | ok | 0.087258 | 0.011819 | 无 |
| `hand_gpu` | ok | 0.025752 | 0.011813 | 无 |

本机未复现 GPU delegate 初始化异常。若其他环境缺少 `BaseOptions.Delegate.GPU`，`core.vision_pipeline._base_options()` 会在显式 `delegate="gpu"` 时抛出 `RuntimeError`；默认 `delegate="cpu"` 仍走旧 `BaseOptions(model_asset_path=...)` 路径。

## benchmark 复测

命令：

```powershell
$sample = @'
{
  "schema_version": 1,
  "samples": [
    {
      "id": "std_front_short",
      "path": "标准样本/正面.mp4",
      "frames": 250
    }
  ]
}
'@
$tmp = Join-Path $env:TEMP "vision_issue43_sample.json"
Set-Content -Path $tmp -Value $sample -Encoding UTF8
$env:PYTHONIOENCODING='utf-8'
.\.venv\Scripts\python.exe -m analysis.bench_annotate_fps `
  --samples $tmp `
  --asset-root E:\CodeProject\vision `
  --device cpu `
  --include-mediapipe-gpu `
  --limit-frames 30 `
  --warmup-frames 5 `
  --out outputs/mediapipe_gpu_delegate_issue43_smoke
```

说明：

- `--include-mediapipe-gpu` 是显式 opt-in；不传该参数时 benchmark 仍只包含 MediaPipe CPU baseline。
- `--device cpu` 只影响 YOLO case；MediaPipe GPU case 由 `delegate="gpu"` 控制。
- 输出目录受 `.gitignore` 的 `outputs/` 规则保护，不入库。

## fallback 与默认路径

- 默认 `PipelineConfig().delegate == "cpu"`。
- CPU 默认路径保持旧行为：不显式传 `BaseOptions.Delegate.CPU`，仍构造 `BaseOptions(model_asset_path=...)`。
- GPU 仅通过 `PipelineConfig(delegate="gpu")` 或 benchmark `--include-mediapipe-gpu` 进入。
- benchmark 对单个 case 的异常会写入对应 CSV/JSON 记录，不会伪造成成功。
- 本阶段不做自动 GPU->CPU 静默 fallback；显式 GPU 失败应暴露，调用方可回到默认 CPU 配置继续运行。

## 后续建议

1. 默认继续使用 CPU MediaPipe；#41 的 Hands 关闭开关仍是当前更直接、收益更明确的实时提速路径。
2. 若未来升级 MediaPipe / GPU driver / TFLite runtime，可复用 `--include-mediapipe-gpu` 对同一批样本复测。
3. 只有当多样本长视频复测显示 GPU delegate 在 pose-only 与 pose+hands 均稳定优于 CPU，才应另开决策 issue 讨论是否扩大入口；不得在 #43 内切默认。
