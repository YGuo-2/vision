# MediaPipe GPU delegate opt-in 可行性报告（Issue #43）

日期：2026-06-02

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
