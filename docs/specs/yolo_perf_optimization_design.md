# YOLO 性能优化 Design-First 规范

日期：2026-06-01

来源：`docs/yolo_perf_optimization_plan.md`

## 设计粒度

High Level Design。范围覆盖 benchmark、YOLO adapter、实时 CLI/UI 管线、MediaPipe GPU delegate 可行性与离线匹配 profile；不直接修改正式评分链路。

## 设计目标

1. 修正 #23 GPU 复测中 benchmark 口径不足的问题，建立 warmup 后稳定态二次决策门。
2. 验证 YOLO PyTorch FP16 / imgsz / warmup 与 TensorRT / ONNX 的真实性能上限。
3. 独立改善当前 MediaPipe 实时体验，优先提供 Hands 关闭开关。
4. 保持 MediaPipe 默认 `pose33_v3` 行为不变，所有默认路径以 golden 回归为准。
5. YOLO 性能优化不得改变 #10/#23/#28 的评分和默认切换边界。

## 不变量

- `MediaPipePipeline` 默认 CPU、默认 `enable_hands=True` 的行为在未显式 opt-in 时保持不变。
- YOLO-only 继续 `calibration_status=unvalidated`、`score_authorized=False`。
- COCO17 缺嘴角、手指、脚跟脚尖、眼细分这一结构性限制不因 GPU/TensorRT 变化而消失。
- 多人闸门必须继续阻断或降级，不允许静默最大框出正常分数。
- `valid_mask` 是唯一有效性判据；不得回退到散落的 `lm[..., 3] >= thr`。

## 方案分解

### P0 benchmark 口径修正

只修改 `analysis/bench_annotate_fps.py` 与报告。每个 sample/case/backend 支持 warmup 帧、正式计时帧、per-frame latency 分布、cold-start 指标。输出兼容 #23 现有 CSV/JSON 字段。P0 必测设备矩阵为 `mediapipe_cpu`、`yolo_cpu`、`yolo_cuda`；`mediapipe_gpu` 等 P4 成功后再作为可选复测。

### P1 YOLO PyTorch 推理姿势优化

在 `core/yolo_adapter.py::YoloPoseAdapter` 增加显式 opt-in 参数：`half`、`warmup`、可配置 `imgsz`。默认保持当前语义。benchmark 和 `extract_yolo_landmark_series` 共享同一 adapter 配置，避免只优化测量脚本。

任何新快路径只允许替换 `_predict` 的 raw result 获取层，后续必须复用 `yolo_result_to_arrays`、`yolo_result_to_frame`、`evaluate_multi_person_gate`。

### P2a TensorRT / ONNX spike

以独立文档/脚本验证 `models/yolo11n-pose.pt` 导出 engine/onnx 的可行性。导出产物不入库；失败也必须记录环境与可复现命令。本阶段只做 P2a export benchmark spike；生产 adapter opt-in 作为 P2b，只有 P2a 达标后另开。

### P3 实时管线优化

P3a 先提供 Hands 开关，默认开启，显式关闭时只跑 pose。P3b 再做 latest-frame 队列与采集/推理/渲染解耦 smoke，默认循环不改。

P3b 必须是 opt-in：先通过 `--realtime-latest-frame` 或实验函数接入，不替换默认 `apps/main.py::run` 热循环，也不默认替换 UI `_worker_loop`。

### P4 MediaPipe GPU delegate spike

以 opt-in 方式验证 Windows + MediaPipe Tasks GPU delegate 是否可用。先探测当前 `mediapipe` 版本是否暴露 `BaseOptions.Delegate.GPU` 或等价 API，默认 CPU 不变。

### P5 离线匹配 profile

先 profile `compare_video_to_dual_templates`、`match_body_core_template`、DTW 与序列提取耗时，再决定是否优化。P5 默认只产 profile/report，不修改 `subsequence_dtw`、baseline、阈值或评分输出。

## 接口契约

- `YoloPoseAdapter.__init__` 新增参数必须保持默认兼容：`imgsz=640`、`device="cpu"`、`half=False`、`warmup=False`。默认构造不得加载 ultralytics 或执行推理。
- `YoloPoseAdapter._predict` 可以替换 raw result 获取方式，但输出仍交给既有 `yolo_result_to_arrays` / `yolo_result_to_frame`。
- `extract_yolo_landmark_series` 必须透传 `imgsz`、`device`、`half`、`warmup` 等 adapter 选项，并继续返回 `landmarks[T,33,4]`、`valid_mask[T,33]`、`meta`。
- benchmark CSV/JSON 新字段至少包含：`backend`、`device`、`delegate`、`warmup_frames`、`timed_frames`、`init_sec`、`cold_first_infer_sec`、`timed_latency_ms_p50`、`timed_latency_ms_p90`、`timed_latency_ms_p99`。
- P3a CLI 建议参数为 `--no-hands` 或 `--pose-only`；默认不传时 `enable_hands=True`。UI 默认状态同样为 Hands 开启。
- P3b 只能通过 `--realtime-latest-frame` 或实验函数 opt-in；默认 `run()` 与默认 UI `_worker_loop` 不替换。
- P4 delegate 字段只能 opt-in；默认 `delegate="cpu"` 或等价语义。

## 质量门槛表

P0/P1/P2a 报告必须输出并判定以下字段：

| 指标 | 阈值 / 规则 | 说明 |
|---|---|---|
| YOLO miss rate | `<= 0.02` | 高于则不得重开实时入口 |
| `yolo_body_core_jitter_median` | `<= 0.006` | 沿用 #23 预注册稳定性阈值 |
| `yolo_body_core_full_valid_rate` | 不低于当前 CUDA 基准同样本结果 | 避免靠降低分辨率牺牲有效帧 |
| YOLO raw FPS | `>= 62.85` | 至少不低于 S0 MediaPipe full CPU 均值 |
| Hands 关端到端 FPS 比 | `>= 1.30` | YOLO body preview vs MediaPipe pose-only |
| Hands 开端到端 FPS 比 | `>= 1.20` | YOLO body + MP hands vs MP pose+hands |
| 多人闸门 | `review_required` 不得从 True 降为 False | 低分辨率 / engine 不得绕过多人复核 |
| 授权字段 | `score_authorized=False`、`calibration_status=unvalidated` | 性能达标也不授权对外评分 |

## 需求与验收

- P0 完成后，benchmark 输出 `warmup_frames`、`timed_frames`、`timed_latency_ms_p50/p90/p99`，旧字段不消失，并覆盖 MP CPU / YOLO CPU / YOLO CUDA。
- P1/P2a 任一性能方案要进入二次决策，必须同时满足 FPS 阈值和质量守卫：miss rate、body_core valid rate、jitter、多人闸门。
- P3a 必须默认保持 Hands 开启；显式关闭时 V_SIGN 不误报，pose 动作仍可用。
- P3b 必须记录 p90 latency 与 dropped frame，不只报告 FPS。
- P4 成功或失败都要落报告；失败不得影响默认 CPU。
- P5 若只做决策不改代码，必须写明 no-change 原因。

## 任务清单

- [ ] P0 benchmark warmup、稳定态延迟分布与二次决策基线。
- [ ] P1 YOLO PyTorch FP16 / imgsz / warmup opt-in 与质量守卫。
- [ ] P2a TensorRT / ONNX 导出与 engine benchmark spike。
- [ ] P3a 实时预览 Hands 开关。
- [ ] P3b 实时采集 / 推理 / 渲染解耦 smoke。
- [ ] P4 MediaPipe GPU delegate opt-in 可行性 spike。
- [ ] P5 离线 DTW / 序列提取 profile 与优化决策。

## 验证基线

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_pose33_v3_golden.py tests\test_valid_mask_migration.py tests\test_body_core_layout.py tests\test_yolo_backend_contract.py tests\test_tech_eval_contract.py -q
.\.venv\Scripts\python.exe -m py_compile .\apps\main.py .\apps\app_ui.py .\core\vision_pipeline.py .\core\yolo_adapter.py .\core\body_core_compare.py .\analysis\bench_annotate_fps.py
git diff --check
```
