# YOLO / 实时管线性能优化方案

- 报告日期：2026-06-01
- 范围：YOLO 后端推理性能 + 实时预览管线（UI/CLI）+ GPU 复测口径
- 性质：**分析与优化方案（非实现）**。所有现状结论引用仓库内真实数据；所有优化项标注预期收益、风险、验证方法。
- 数据来源：
  - `outputs/gpu_recheck/annotate_fps_gpu_recheck.csv`（S5 真实 GPU 复测，#23）
  - `docs/yolo_baseline_report.md`（S0 CPU 基线，#2）
  - `analysis/bench_annotate_fps.py`、`core/yolo_adapter.py`、`core/vision_pipeline.py`、`apps/main.py`、`apps/app_ui.py`

---

## 0. TL;DR（给决策者）

1. **"换 YOLO 反而更慢"是真的，但原因不是 GPU/硬件不行，而是调用方式没优化 + 测量口径有偏差。**
2. 当前 YOLO 走的是 ultralytics 最朴素的 `model.predict()` 逐帧、单张、FP32 调用，且 **benchmark 没做 GPU warmup**——首个样本背了全进程 CUDA 冷启动，把"GPU YOLO"的代表数字压到了 22fps。
3. 真实稳定态下，YOLO 裸推理已是 **37–51fps**（见下表），但对 RTX 4060 跑 nano 模型仍偏慢（正常该上百 fps）——差距来自 FP32 + batch=1 + 每帧 Python 预/后处理外壳。
4. **现 no-go 结论是"在未优化实现下"成立，不能等同于"YOLO 在 GPU 上本质不划算"。** 要下硬结论，必须先按本方案修正测量口径与推理姿势再复测。
5. 优化按 ROI 排序：**先修测量（P0）→ 推理姿势 FP16/warmup（P1）→ TensorRT/ONNX 导出 spike（P2a）→ 管线架构解耦（P3）→ MediaPipe 侧 GPU delegate（P4）**。

---

## 1. 现状

### 1.1 代码路径现状（谁在用什么后端）

| 链路 | 入口 | 当前后端 | 设备 | 说明 |
|---|---|---|---|---|
| UI 实时预览 | `apps/app_ui.py::_worker_loop` | MediaPipe `PoseLandmarker`+`HandLandmarker` | CPU | 默认 `enable_hands=True`，每帧两套模型 |
| CLI 实时预览 | `apps/main.py::run` | MediaPipe | CPU | 同上；多线程仅离线视频可用 |
| 离线模板匹配 | `core/body_core_compare.py` | MediaPipe(默认) / YOLO(opt-in) | CPU | YOLO 仅 `body_core_v1`、`score_authorized=False` |
| GPU benchmark | `analysis/bench_annotate_fps.py` | 两后端对照 | YOLO=CUDA / MP=CPU | 仅复测用，不接主链路 |

**关键事实**：实时预览（UI/CLI）至今 100% 是 CPU 上的 MediaPipe，YOLO 从未进入实时主链路（这是 #23 no-go → #25/#26 关闭的既定结果，不是 bug）。

### 1.2 性能现状（真实数据）

**S0 CPU 基线（纯推理 FPS 均值，`docs/yolo_baseline_report.md`）**：

| 后端 | 纯推理 FPS | 对比 |
|---|---:|---|
| MediaPipe full（CPU） | 62.85 | — |
| YOLO11n-pose（CPU） | 25.52 | YOLO 慢约 2.5×（speedup 0.41×） |

**S5 GPU 复测（`annotate_fps_gpu_recheck.csv`，按执行顺序）**：

| 样本 | 帧 | MP pose-only annotate(CPU) | YOLO body-only annotate(CUDA) | YOLO 裸推理(CUDA) | body_core 有效率 | 抖动中位 |
|---|---:|---:|---:|---:|---:|---:|
| std_front | 250 | 34.2 | 20.0 | **22.4** ⚠️ | 1.00 | 0.0027 |
| std_side_long | 694 | 29.5 | 33.5 | 38.9 | 0.87 | 0.0040 |
| student_1 | 450 | 30.8 | 41.8 | 49.0 | 0.75 | 0.0104 |
| student_4_long | 618 | 40.4 | 43.4 | 51.1 | 0.72 | 0.0068 |
| punch_front | 283 | 37.7 | 42.0 | 49.1 | 1.00 | 0.0034 |
| punch_side | 129 | 46.8 | 32.8 | 37.6 | 0.97 | 0.0068 |

### 1.3 三个被数据暴露的关键异常

1. **warmup 污染（最严重的测量问题）**：std_front 是全进程第一个 YOLO 推理样本，裸推理仅 22.4fps；其后样本跃升到 37–51fps。差异来自一次性的 CUDA 上下文初始化 + cuDNN autotune，被全压在首个样本上。**`bench_annotate_fps.py` 没有 warmup 帧，也没有丢弃首样本**，导致最不利的数字被当作代表值。
2. **裸推理本身仍偏慢**：即便稳定态 37–51fps，对 RTX 4060 跑 yolo11n（最小 nano 变体）也明显偏低（正常预期上百 fps）。说明瓶颈在 FP32 + batch=1 + 每帧 Python 预/后处理，而非 GPU 算力。
3. **annotate 比裸推理还低一截**：如 student_4_long 裸推理 51fps、annotate 仅 43fps，差额是绘制 + `frame.copy()` + 逐点投影开销，串在同一线程里。

---

## 2. 原因深析（分层归因）

把单帧 YOLO 耗时拆开，慢的来源按贡献排序：

### A. 调用姿势：`model.predict()` 逐帧 + batch=1 + FP32（主因）
`core/yolo_adapter.py::_predict`：
```python
results = model.predict(frame, imgsz=self.imgsz, device=self.device, verbose=False)
```
- `predict()` 是 ultralytics 面向"批量图片/视频文件"的高层 API，每次调用带固定 Python 开销：参数解析、letterbox 缩放到 640、BGR→RGB、HWC→CHW、归一化、转 tensor、NMS、结果对象封装。
- 这些大多在 **CPU 上逐帧重复**；nano 模型真正在 GPU 上算只占几毫秒，外壳开销反而是大头。
- **batch=1**：GPU 靠批量并行才划算，单张图 + 每帧一次 CPU↔GPU 拷贝 + kernel 启动延迟，固定延迟占比极高。
- **未开 FP16**：默认 FP32，没用上 4060 的半精度强项。

### B. 测量口径：无 warmup（直接导致 no-go 数字偏差）
- 首次 CUDA 调用含上下文初始化、cuDNN autotune、模型搬到显存——一次性几百毫秒到秒级。
- benchmark 未跑 warmup、未丢弃首样本，std_front 被这笔一次性成本拉低近一半（22 vs 稳定态 ~45）。

### C. 对手是"深度优化的 CPU 专用管线"，不是裸 CPU 程序
- MediaPipe `PoseLandmarker` 是 Google 为 CPU/移动端优化的 TFLite + XNNPACK，预/后处理为原生 C++，Python 仅薄壳。
- 这是一场不公平对比：**优化过的 CPU 管线 vs 未优化的 GPU 高层调用**。MediaPipe CPU 30–47fps 是"全力优化后"的结果。

### D. 实时管线架构：采集—推理—渲染串行单线程
- `apps/app_ui.py::_worker_loop` 与 `apps/main.py::run` 都是 `read → annotate → draw → show` 串行循环。
- `annotate()` 内 `out = frame_bgr.copy()` + 逐点 `cv2.line/circle` 投影，都串在推理同一线程。
- UI 默认 `enable_hands=True`，每帧额外跑一套 HandLandmarker（CPU），是 heavy 档 15fps 的直接放大器。
- 离线多线程路径（IMAGE 模式 + worker 池）已存在，但**仅对视频文件、`workers>1` 生效；摄像头实时恒为单线程**。

### E. MediaPipe 未启用 GPU delegate
`core/vision_pipeline.py`：
```python
base_options=mp.tasks.BaseOptions(model_asset_path=str(pose_path))  # 无 delegate=GPU
```
- 当前 MediaPipe 也跑 CPU。即便不上 YOLO，给 MediaPipe 加 GPU delegate 也可能是更低风险的提速途径。

### 结论
慢 = **未优化的 YOLO 调用姿势（A）+ 测量口径偏差（B）+ 对手是优化过的 CPU 管线（C）**，叠加**串行单线程实时架构（D）**。"语言是 Python"只是 A 里的一部分，不是决定因素——同样用 Python 调的 MediaPipe 就不慢。

---

## 3. 优化方案（按 ROI 排序，每项含预期/风险/验证）

> 总原则（硬约束，全程不破）：
> - 不改 MediaPipe 默认 `pose33_v3` 路径行为，`tests/test_pose33_v3_golden.py` 必须保持全绿。
> - YOLO 出分仍受 #10 约束（`calibration_status=unvalidated` / `score_authorized=False`），性能优化**不等于**放开对外评分。
> - 优化先在独立 benchmark / 显式 opt-in 路径验证，达标并满足 #23 前置条件后才谈实时入口。

### P0：先修测量口径（最高优先，否则后续结论都不可信）
**问题**：warmup 污染 + 缺稳定态统计，使 no-go 依据有偏差。
**做法**（改 `analysis/bench_annotate_fps.py`，不动主链路）：
1. 每个后端正式计时前跑 N 帧（建议 10）warmup，结果丢弃。
2. 首个样本单独标注或排除出汇总均值。
3. 输出 per-frame 延迟分布（p50/p90/p99），而非只看整体 fps。
4. 输出明确设备矩阵：`mediapipe_cpu`、`yolo_cpu`、`yolo_cuda` 为 P0 必测；
   `mediapipe_gpu` 仅在 P4 验证 GPU delegate 成功后作为可选复测，不阻塞 P0。
   每条记录必须含 `backend`、`device`、`delegate` 字段，避免继续把 MP CPU vs YOLO CUDA
   当成唯一公平口径。
5. warmup 必须使用独立 capture 重放前 N 帧，或在同一 capture warmup 后 rewind 到 0 再正式计时；
   正式统计仍从原样本起点开始，VIDEO mode timestamp 在 warmup 与正式计时各自从 0 单调递增。

**预期**：YOLO GPU 代表值从被污染的 ~22fps 回到真实稳定态 ~45fps；给 #23 一个可信基准。
**风险**：低（仅测量脚本）。
**验证**：重跑 benchmark，确认首样本与后续样本裸推理 fps 趋于一致。

### P1：YOLO 推理姿势优化（FP16 + warmup + imgsz + 复用 model）
**做法**（`core/yolo_adapter.py`，opt-in，不改默认 CPU/精度语义）：
1. `_predict` 支持 `half=True`（GPU 时）：`model.predict(frame, half=True, ...)`。
2. 新增显式 `warmup=False` opt-in；只有 benchmark case 或调用方明确开启时才做 warmup。
   默认构造与 `import core.yolo_adapter` 不得触发 ultralytics 加载或推理。
3. `imgsz` 可调：实时预览可降到 480/512，离线保持 640，权衡精度/速度。
4. 评估用 `model.predict(..., stream=True)` 或直接 `model(tensor)` 绕开高层封装的逐帧开销时，
   只能替换 `_predict` 的 raw result 获取层；后续仍必须复用 `yolo_result_to_arrays` /
   `yolo_result_to_frame` / `evaluate_multi_person_gate`，禁止新建并行 COCO17→Pose33 映射逻辑。
5. 确认整段视频复用同一个 model 实例（已是如此，benchmark 里每 case 新建，需在实时路径保证常驻）。

**预期**：FP16 + 正确 imgsz 通常带来 1.5–3× 提速；nano 在 4060 上有望进入 100fps+ 量级。
**风险**：中。FP16 可能极小幅影响关键点精度（需对照 valid_mask/抖动回归）；`stream`/裸 tensor 路径要重做预处理，需测试守卫。
**验证**：P0 修正后的 benchmark 对照 FP32 vs FP16 vs 裸 tensor 的 fps 与抖动；`valid_mask` 有效率不下降。

### P2a：TensorRT / ONNX 导出（GPU 上 YOLO 的正确打开方式）
**做法**：
1. P2a 先做导出与 benchmark spike：`yolo export format=engine half=True`（TensorRT）
   或 `format=onnx` + onnxruntime-gpu；产出报告与复测数字。
2. 只有 P2a 达标后，另开 P2b 做 engine adapter opt-in；P2a 不要求生产 adapter 分支。
3. 引擎文件随设备生成、不入库。若放 `models/`，必须先补 `models/*.engine` 到 `.gitignore`；
   若放 `outputs/engines/`，验收必须检查 `git status --short` 不出现 engine/onnx 产物。
4. 复测同一 6 样本。

**预期**：TensorRT FP16 对 yolo11n 常见 5–10× 于朴素 pytorch predict，4060 上预计可达 200fps+ 裸推理。这才是判断"YOLO 在 GPU 上是否划算"的真正基准。
**风险**：中高。引擎与 CUDA/驱动/torch 版本强绑定，需固化环境；导出耗时；首次集成复杂度高。
**验证**：导出引擎复测，对照 P1 的 pytorch FP16 数字；确认关键点契约不变。

### P3：实时管线架构解耦（与后端无关的通用提速）
**做法**（`apps/app_ui.py` / `apps/main.py`，实时路径）：
1. 采集、推理、渲染拆成独立线程/队列，丢弃过期帧只渲染最新帧（UI 的 `_post_frame` 已有"只留最新帧"雏形，可扩展到推理侧）。
2. UI 暴露"实时预览关闭手部检测"开关（`enable_hands=False`）——对当前 heavy 15fps 是最直接的单点提速。
3. 渲染与推理分离，`frame.copy()` 与逐点绘制移出推理线程。
4. 实时场景以**延迟**为指标（p90 单帧延迟），而非吞吐 fps。

**预期**：关手部检测单项即可让 heavy 实时从 ~15fps 提升明显（省掉每帧一套 HandLandmarker）；线程解耦进一步降低端到端延迟。
**风险**：低–中。多线程需注意 MediaPipe VIDEO 模式的时间戳单调性；UI 线程安全。
**验证**：UI 实测 fps；开关手部检测前后对比。

### P4：MediaPipe GPU delegate（低风险的 MediaPipe 侧提速）
**做法**：先探测当前 MediaPipe Tasks Python 版本是否暴露 `BaseOptions.Delegate.GPU` 或等价 API，
报告记录实际 API / 异常；只有探测成功才在 `core/vision_pipeline.py` 增加 opt-in delegate 字段，
默认仍 CPU 保证 golden 不漂移。
**预期**：MediaPipe 自身在 GPU 上提速，可能直接解决"实时预览慢"，无需切 YOLO。
**风险**：中。Windows 上 MediaPipe Tasks 的 GPU delegate 支持有限，需实测可用性；不可改默认路径。
**验证**：opt-in 开关下对比 CPU/GPU delegate fps；golden 全绿。

---

## 4. 不变量与边界（明确不碰的）

- MediaPipe 默认 `pose33_v3` 路径、`infer()`/`annotate()`、旧模板比对行为**逐字不变**，golden 全绿。
- YOLO 性能优化**不放开评分授权**：COCO17 结构性缺点（嘴角/手指/脚跟脚尖）+ #10 标定"仅预览"两条结论与性能无关，GPU/TensorRT 也补不回缺失关键点。
- 实时入口（#25/#26）的重开仍需先满足 #23 前置条件（CUDA 可用 + 6/6 样本达标），本方案是"让复测口径正确、让 YOLO 用对姿势"，不是绕过决策门。

---

## 5. 建议执行顺序与验收门

```
P0 修测量口径 ──► 重跑 #23 基准（得到可信稳定态数字）
   │
   ├─ 若稳定态 YOLO 已显著优于 MP 同设备 ──► 继续 P1/P2a 量化上限
   └─ 若仍不达标 ──► no-go 结论升级为"含 warmup 修正的真实 GPU no-go"（比现版更硬）
P1 FP16+warmup ──► 对照 fps/抖动/有效率
P2a TensorRT/ONNX spike ──► 得到 YOLO 在 4060 的真实性能天花板
P3 管线解耦/关手部 ──► 独立于后端，直接改善现有实时体验（建议可立即做，收益确定）
P4 MP GPU delegate ──► 评估"不切 YOLO 也能提速"的可行性
```

**优先建议**：P0 和 P3 收益确定、风险低，可优先推进——P0 让结论可信，P3（尤其"实时关手部检测"开关）能立刻改善你看到的 15fps 体验，且与 YOLO 决策完全解耦。P1/P2a 决定是否要进入二次评估门。

---

## 6. 附：关键数字速查

- S0 CPU 纯推理：MP 62.85 / YOLO 25.52 fps（speedup 0.41）。
- S5 GPU YOLO 裸推理：首样本 22.4（未 warmup，含 CUDA/model cold-start）→ 稳定态 37–51 fps。
- S5 MP pose-only(CPU)：29–47 fps；MP pose+hands(CPU)：18–23 fps。
- YOLO body_core 有效率：正面 1.00、侧面/学员 0.72–0.97（conf 阈值 0.6 在侧面丢点较多）。
- 抖动中位：YOLO 0.0027–0.0104；预注册阈值 0.006（部分样本超标）。

> 本方案为分析与计划，未改动任何运行时代码。落地任一项前应建分支、补测试守卫，并在 `change.md` 记录。

---

## 7. 代码链路复核结论（2026-06-01）

本节基于当前仓库代码复核，不只依赖前文 benchmark 数字。

### 7.1 视觉主链路

| 链路 | 关键代码 | 当前行为 | 性能含义 |
|---|---|---|---|
| MediaPipe 默认实时 | `core/vision_pipeline.py::MediaPipePipeline.__init__/infer/annotate` | `PoseLandmarker` + 可选 `HandLandmarker`，CPU `BaseOptions(model_asset_path=...)`，无 GPU delegate | 默认路径成熟，Python 只做薄封装；Hands 是实时重负载 |
| CLI 实时 | `apps/main.py::run` | `read → pipe.annotate → draw/write/show` 串行 | 端到端 FPS 同时受推理、绘制、写视频、显示影响 |
| UI 实时 | `apps/app_ui.py::_worker_loop` | 摄像头实时串行；离线视频 `workers>1` 才走 IMAGE 模式并行 | UI 已有“只保留最新帧”的显示队列雏形，但推理侧未解耦 |
| YOLO adapter | `core/yolo_adapter.py::YoloPoseAdapter._predict` | 每帧 `model.predict(frame, imgsz=self.imgsz, device=self.device, verbose=False)` | 当前是高层逐帧 API，无 FP16/warmup/batch/engine opt-in |
| YOLO 序列提取 | `core/yolo_adapter.py::extract_yolo_landmark_series` | 逐帧 `cv2.VideoCapture.read()` + adapter 推理 | 离线 body_core 也不会自动获得 batch/stream 收益 |
| body_core 闭环 | `core/body_core_compare.py` | YOLO / MediaPipe 共享 `body_core_v1`，低置信帧按 `valid_mask` gap-fill，不授权评分 | 可用于内部调试与复测，不进入对外评分 |
| full tech_eval | `analysis/tech_eval.py` | 仍围绕 MediaPipe raw landmarks；没有 YOLO full tech_eval 入口 | 性能优化不得绕过 #10/#11 评分边界 |

### 7.2 性能瓶颈排序

1. **YOLO 调用姿势**：逐帧 `model.predict()` + batch=1 + FP32 + 无 warmup，是当前 YOLO raw FPS 偏低的首要嫌疑。
2. **实时串行架构**：采集、推理、绘制、显示/写出在同一热循环，端到端 FPS 不能直接解释成模型推理 FPS。
3. **Hands 负载**：`PipelineConfig.enable_hands=True` 是默认配置；实时入口没有用户级“只跑人体姿态”开关。
4. **视频 I/O / 渲染**：`frame.copy()`、OpenCV line/circle、`VideoWriter.write`、`imshow/waitKey` 均在热路径。
5. **离线 DTW / 多段匹配**：`compare_video_to_dual_templates → _multi_subsequence_matches → subsequence_dtw` 会重复跑长序列 DTW；它不解释实时预览慢，但会影响 batch/offline 吞吐。

### 7.3 文档与代码一致性修正

- `analysis/bench_annotate_fps.py::YoloPreviewAnnotator` 是独立 benchmark 路径，**不是**产品实时入口；因此“当前 UI/CLI 100% MediaPipe”仍成立。
- P3 的实时解耦不能直接复用离线 IMAGE-mode worker：摄像头 VIDEO mode 必须保持时间戳单调，并明确丢帧策略。
- P4 MediaPipe GPU delegate 必须保持 opt-in；Windows + MediaPipe Tasks 支持情况需实测，不能作为默认低风险改动。
- 离线 YOLO 优化不能只改 benchmark；若 P1/P2a 证实有效，应同步让 `extract_yolo_landmark_series` 通过同一 adapter 选项受益。

---

## 8. 候选方案对比与择优策略

本轮不直接重开 #25/#26，而是建立“二次决策门”：先修正测量，再分支验证候选方案，最后只把达标方案推进到用户可见入口。

| 方案 | 触达范围 | 预期收益 | 风险 | 采用策略 |
|---|---|---:|---|---|
| A. benchmark warmup + latency 分布 | `analysis/bench_annotate_fps.py` | 结论可信，消除 CUDA 冷启动污染 | 低 | **必做 P0** |
| B. YOLO PyTorch FP16 + warmup + imgsz opt-in | `core/yolo_adapter.py` + benchmark | 中高，验证最便宜 | 中：FP16/低分辨率可能影响有效率/抖动 | **P1 优先验证**，默认保持 FP32/640 |
| C. Ultralytics stream/batch 路径 | adapter / benchmark | 中，减少 Python 调用开销 | 中：结果顺序、内存、实时延迟需量化 | 作为 P1 的实验分支，不先接 UI/CLI |
| D. TensorRT / ONNX Runtime | export benchmark spike，条件后续 adapter | 高，上限最大 | 中高：环境强绑定、导出耗时、Windows 兼容与模型产物管理 | **P2a 只做 spike**；达标后另开 P2b adapter |
| E. 实时 Hands 开关 | `apps/main.py` / `apps/app_ui.py` / `PipelineConfig` | 高且确定，独立于 YOLO | 低：需守住默认行为 | **P3a 立即做**，默认仍 Hands 开 |
| F. 实时采集/推理/渲染解耦 | CLI/UI runtime | 中：降低延迟抖动 | 中：线程安全、丢帧、VIDEO 时间戳 | P3b，先做 smoke + 延迟指标 |
| G. MediaPipe GPU delegate | `core/vision_pipeline.py` opt-in | 未知，可能直接改善默认后端 | 中：Windows 支持与行为漂移风险 | P4 spike，默认 CPU 不变 |
| H. DTW / 离线匹配优化 | `core/pose_features.py` / `core/action_compare.py` | 只改善离线 batch | 中：易影响分数 | P5，先 profile，需 golden 全绿 |

官方能力核对（2026-06-01 查阅）：

- Ultralytics `predict` 支持 `imgsz`、`device`、`half` 等推理参数，且 `half=True` 是面向支持 GPU 的 FP16 推理开关；长视频/流式输入可用 `stream=True` 管理内存。参考：<https://docs.ultralytics.com/modes/predict/>
- Ultralytics `export` 支持 `format='onnx'` 与 `format='engine'`；TensorRT engine 支持 `imgsz`、`half`、`batch`、`device` 等导出参数。参考：<https://docs.ultralytics.com/modes/export/>、<https://docs.ultralytics.com/integrations/tensorrt/>
- 因此 P1/P2a 是可执行实验项，但本仓必须额外验证 `valid_mask` 有效率、body_core 抖动、多人数闸门与 `score_authorized=False` 不变量。

择优规则：

1. 任何方案先看 **质量守卫**：`miss_rate <= 2%`、`body_core_jitter_median <= 0.006`、
   `body_core_full_valid_rate` 不低于当前 CUDA 基准同样本结果、`max_persons` /
   `multi_person_frames` / `review_required` 不得从多人复核降级为正常评分。
2. 再看 **端到端收益**：Hands 关 FPS 比 ≥ 1.30；Hands 开 FPS 比 ≥ 1.20；YOLO raw FPS ≥ 62.85。
3. 最后看 **工程成本**：默认路径不漂移、依赖可安装、产物可忽略、失败时能清晰回退。
4. 若 P1/P2a 达不到质量 + 性能双门槛，则维持 #23 no-go，但结论升级为“含 warmup/FP16/engine 验证后的 no-go”。

---

## 9. 细分 Issue Plan（拟推送到 GitHub）

以下条目按以往 issue 风格编写，可直接拆成 GitHub issue。新路线图建议挂新 Milestone：**M5 YOLO 性能优化与二次决策门**。

### Issue P0 — benchmark warmup、稳定态延迟分布与二次决策基线

**标签**：`yolo-migration` `S5` `spike`　**依赖**：无　**阻塞**：P1 P2a

#### 任务明细
修正 `analysis/bench_annotate_fps.py` 的测量口径：为每个 backend/case/sample 增加 warmup、正式计时区间、per-frame latency 分布，避免 CUDA 冷启动污染代表数字。

#### 任务规范
- 只改 benchmark 与报告，不接主链路。
- warmup 帧不得计入正式 FPS、p50/p90/p99。
- warmup 必须使用独立 capture 重放前 N 帧，或 rewind 到 0 后再正式计时；正式统计仍覆盖原样本起点，VIDEO timestamp 在 warmup/正式计时各自从 0 单调递增。
- 保留 cold-start 指标，避免完全丢失初始化成本。
- 设备矩阵必须包含 `mediapipe_cpu`、`yolo_cpu`、`yolo_cuda`；`mediapipe_gpu` 只在 P4 成功后可选。
- 输出必须继续包含 #23 现有字段，保证旧测试/报告可读。
- 字段边界：`init_sec`=runner 构造；`cold_first_infer_sec`=首次真实/独立 warmup 推理；`timed_latency_ms_*`=剔除 warmup 后正式帧。

#### 任务清单
- [ ] 增加 `--warmup-frames`、`--discard-first-sample` 或等价参数，默认 warmup 10 帧。
- [ ] 记录 `timed_latency_ms_p50/p90/p99`、`cold_first_infer_sec`、`timed_frames`、`warmup_frames`。
- [ ] YOLO raw infer 与 annotate wall 分别统计 latency。
- [ ] 输出 `backend`、`device`、`delegate`，并覆盖 MP CPU / YOLO CPU / YOLO CUDA 三类记录。
- [ ] 更新 `docs/yolo_gpu_recheck_report.md` 或新增 `docs/yolo_perf_recheck_report.md`。
- [ ] 补测试锁住 CSV/JSON schema 与 warmup 不计入正式统计。

#### 验收标准
- [ ] `tests/test_s5_gpu_recheck.py` 或新增测试覆盖 warmup 与 latency schema。
- [ ] `--limit-frames` smoke 可跑通并写出新字段。
- [ ] 旧字段 `yolo_raw_infer_fps`、`yolo_miss_rate`、`yolo_body_core_jitter_median` 不消失。
- [ ] schema 测试断言 `init_sec`、`cold_first_infer_sec`、`timed_latency_ms_p50/p90/p99` 均存在且含义不互相替代。
- [ ] `change.md` 已记录。

### Issue P1 — YOLO PyTorch FP16 / imgsz / warmup opt-in 与质量守卫

**标签**：`yolo-migration` `S5` `feature`　**依赖**：P0　**阻塞**：P2a / 二次决策

#### 任务明细
给 `YoloPoseAdapter` 增加显式 opt-in 推理参数，验证 FP16、不同 `imgsz`、adapter warmup 对 raw FPS、端到端 FPS 和 body_core 质量指标的影响。

#### 任务规范
- 默认行为必须保持当前 FP32 / `imgsz=640` / 无自动 warmup 的兼容语义，除非调用方显式开启。
- 新参数必须透传到 benchmark 与 `extract_yolo_landmark_series`，避免只优化 benchmark。
- 任何新推理路径只允许替换 `_predict` 的 raw result 获取层；后续必须复用现有解析 / 映射 / 闸门函数，禁止新建并行 COCO17→Pose33 映射逻辑。
- `warmup=False` 是默认值；`import core.yolo_adapter` 与默认构造不得触发 ultralytics 加载或推理。
- 不授权 YOLO 分数，不打开 CLI/UI 实时 YOLO 入口。

#### 任务清单
- [ ] `YoloPoseAdapter.__init__` 增加 `half: bool=False`、`warmup: bool=False`、可选 `warmup_shape`。
- [ ] `_predict()` 透传 `half=self.half`，并确保 CPU 下不会误用 FP16。
- [ ] adapter 初始化或首次调用前支持显式 warmup。
- [ ] benchmark 增加 case：FP32 640、FP16 640、FP16 512/480（按可行性）。
- [ ] 报告同时输出 FPS、latency、miss、valid rate、jitter、`max_persons`、`multi_person_frames`、`review_required`。

#### 验收标准
- [ ] YOLO adapter 单元测试覆盖 half 参数透传、CPU fallback、warmup 只执行一次。
- [ ] 多人 fake result、COCO17 缺失点 `valid_mask=False`、`score_authorized=False` / `calibration_status=unvalidated` 回归仍全绿。
- [ ] 每个 imgsz case 输出多人闸门字段，且多人样本不得从 review 降为正常评分。
- [ ] `tests/test_yolo_backend_contract.py`、`tests/test_body_core_layout.py` 全绿。
- [ ] `tests/test_pose33_v3_golden.py` 全绿。
- [ ] CUDA smoke 输出各实验分支指标；若不能跑 CUDA，报告必须写明原因。
- [ ] `change.md` 已记录。

### Issue P2a — TensorRT / ONNX 导出与 engine benchmark spike

**标签**：`yolo-migration` `S5` `spike`　**依赖**：P0 P1　**阻塞**：二次决策

#### 任务明细
验证 `models/yolo11n-pose.pt` 导出 TensorRT engine / ONNX Runtime 的可行性与真实性能上限，形成是否另开 P2b engine adapter opt-in 的决策。

#### 任务规范
- 导出产物（`.engine` / `.onnx`）不得入库。
- 若本机环境不满足 TensorRT，必须给出缺失依赖、安装命令和替代 ONNX 路径。
- engine/ONNX 结果不得进入对外评分。
- 本 issue 只做 export + benchmark + report，不实现生产 adapter 分支。

#### 任务清单
- [ ] 新增独立脚本或文档命令：`yolo export format=engine half=True imgsz=...` / `format=onnx`。
- [ ] 将导出产物写入 gitignored `models/` 或 `outputs/engines/`。
- [ ] benchmark 支持读取 exported model 做同样 6 样本对照。
- [ ] 报告比较 PyTorch FP32、PyTorch FP16、TensorRT/ONNX 三组。
- [ ] 记录环境绑定：CUDA、driver、torch、ultralytics、TensorRT/onnxruntime 版本。

#### 验收标准
- [ ] `docs/yolo_engine_benchmark_report.md` 存在，含成功/失败命令、版本、数字与 go/no-go。
- [ ] 产物未入库：若放 `models/`，`.gitignore` 已覆盖 `models/*.engine`；若放 `outputs/engines/`，`git status --short` 不出现 engine/onnx 产物。
- [ ] 若 TensorRT 成功，至少跑 `--limit-frames` smoke；若失败，ONNX 或失败复盘可复现。
- [ ] 报告明确是否建议另开 P2b engine adapter opt-in；P2a PR 不包含生产 adapter 分支。
- [ ] `change.md` 已记录。

### 条件 Issue P2b — engine adapter opt-in（仅 P2a 达标后创建）

**标签**：`yolo-migration` `S5` `feature`　**依赖**：P2a 达标　**阻塞**：二次决策

P2b 不在首轮开票中实现。只有 P2a 证明 TensorRT/ONNX 同时满足性能阈值与质量守卫后，才另开
adapter opt-in 子任务；届时仍不得接默认 CLI/UI 或对外评分。

### Issue P3a — 实时预览 Hands 开关（MediaPipe 默认提速，不改 YOLO 决策）

**标签**：`yolo-migration` `S5` `feature`　**依赖**：无　**阻塞**：P3b

#### 任务明细
为 CLI/UI 增加显式“只跑人体姿态 / 关闭手部检测”选项，先改善当前 MediaPipe 默认实时体验。这与 YOLO 是否 go 解耦。

#### 任务规范
- 默认仍保持现有 Hands 开启行为，避免用户体验突变。
- 不传新参数时，`apps/main.py::run` 与 `apps/app_ui.py::_worker_loop` 仍构造
  `PipelineConfig(... enable_hands=True)`；显式关闭才为 False。
- 关闭 Hands 时动作标签中 V_SIGN 不应误报；pose 类动作仍工作。
- 不引入 YOLO 后端选择。

#### 任务清单
- [ ] `apps/main.py` 增加 `--no-hands` 或 `--pose-only`。
- [ ] `apps/app_ui.py` 增加清晰的 Hands 开关，默认开启。
- [ ] `PipelineConfig(enable_hands=...)` 从入口透传。
- [ ] benchmark 或 smoke 记录 hands on/off 的端到端 FPS。

#### 验收标准
- [ ] CLI 参数解析测试覆盖默认开、显式关。
- [ ] UI 状态收集测试或轻量 AST/函数测试确认开关透传。
- [ ] 默认参数 / 默认 UI 状态保持 Hands 开启。
- [ ] `tests/test_pose33_v3_golden.py` 全绿。
- [ ] `py_compile` 通过。
- [ ] `change.md` 已记录。

### Issue P3b — 实时采集 / 推理 / 渲染解耦 smoke

**标签**：`yolo-migration` `S5` `feature`　**依赖**：P3a　**阻塞**：无

#### 任务明细
在不改变默认路径结果语义的前提下，验证实时场景的低延迟队列架构：采集只保留最新帧，推理线程消费最新帧，UI/CLI 渲染线程显示最新结果。

#### 任务规范
- 仅 opt-in，默认实时循环不改。
- 先新增 `--realtime-latest-frame` 或实验函数；默认 `run()` 热循环逐行语义不改。
- UI 只文档化或独立实验开关，不得替换默认 `_worker_loop`。
- VIDEO mode 时间戳必须单调；丢帧策略要写入文档。
- 指标以 p90 latency 和 dropped frame 计数为主，不只看 FPS。

#### 任务清单
- [ ] 设计 `LatestFrameQueue` 或等价小组件。
- [ ] CLI 先接 smoke 模式，UI 后接或仅文档化。
- [ ] 输出 `capture_fps`、`infer_fps`、`render_fps`、`latency_p90_ms`、`dropped_frames`。
- [ ] 保留停止/释放资源可靠性。

#### 验收标准
- [ ] 单元测试覆盖 latest-frame 队列丢弃旧帧语义。
- [ ] `--limit-frames` 或离线模拟 smoke 可跑通。
- [ ] 默认 `apps/main.py` 行为不变，golden 全绿。
- [ ] 源码/测试证明默认 `run()` 与默认 UI `_worker_loop` 未被 latest-frame 实验路径替换。
- [ ] `change.md` 已记录。

### Issue P4 — MediaPipe GPU delegate opt-in 可行性 spike

**标签**：`yolo-migration` `S5` `spike`　**依赖**：P0　**阻塞**：无

#### 任务明细
验证 MediaPipe Tasks 在本机 Windows 环境下是否能启用 GPU delegate，并比较 pose-only / pose+hands 端到端表现。

#### 任务规范
- 默认仍 CPU；GPU delegate 只通过显式参数启用。
- 若环境不支持，报告要写清异常和 fallback。
- 不改变 `pose33_v3` golden。

#### 任务清单
- [ ] `PipelineConfig` 增加 opt-in delegate 字段或先在独立 spike 中验证。
- [ ] benchmark 增加 MediaPipe CPU vs GPU delegate case。
- [ ] 报告记录初始化成功率、FPS、异常、是否支持 hands。

#### 验收标准
- [ ] `docs/mediapipe_gpu_delegate_report.md` 存在，含实际 API / 异常 / fallback 与明确 go/no-go。
- [ ] 默认 CPU 路径 golden 全绿。
- [ ] `py_compile` 通过。
- [ ] 失败 fallback smoke 或测试证明默认 CPU 可继续运行。
- [ ] `change.md` 已记录。

### Issue P5 — 离线 DTW / 序列提取 profile 与优化决策

**标签**：`yolo-migration` `S5` `spike`　**依赖**：无（若复用 P0 latency schema 则可选依赖 P0）　**阻塞**：无

#### 任务明细
对 batch/offline 进行 profile，区分模型推理、特征归一化、DTW、多段匹配、视频 I/O 的耗时占比，再决定是否优化 DTW 或缓存。

#### 任务规范
- 先 profile，后优化；没有证据不改 DTW。
- 本 issue 默认只产 profile/report；不得修改 scoring、DTW baseline 或匹配阈值。
- 任何 DTW 优化必须保持 `pose33_v3` golden 与 body_core tests 全绿。
- 若报告建议 FastDTW / Numba / 窗口约束 / 缓存等实现，必须另开实现 issue，并以
  `tests/test_pose33_v3_golden.py` 与 body_core fixture 分数逐值一致作为前置验收。

#### 任务清单
- [ ] 增加离线 profile 脚本或 benchmark 模式。
- [ ] 对 `compare_video_to_dual_templates`、`match_body_core_template` 分段计时。
- [ ] 输出是否需要 FastDTW/Numba/缓存/窗口约束的决策表。

#### 验收标准
- [ ] `docs/offline_matching_perf_profile.md` 存在。
- [ ] 若只做决策不改代码，明确列出 no-change 原因。
- [ ] 本 PR 不修改 `subsequence_dtw`、baseline、阈值或评分输出。
- [ ] `change.md` 已记录。

---

## 10. 新路线图 Issue 草案

标题建议：`[Tracking] YOLO 性能优化路线图 / 二次决策门`

正文建议：

```markdown
本 issue 跟踪 YOLO / 实时管线性能优化的二次决策门。它不推翻 #23 的 CUDA 实测 no-go，而是在修正测量口径、验证 FP16/engine/实时管线候选方案后，决定是否有资格重开 #25/#26。

- 计划来源：docs/yolo_perf_optimization_plan.md
- 既有约束：#10 仅预览；#23 真实 CUDA no-go；#25/#26/#27/#28 当前关闭 / 不实现 / 不切默认

强约束：
- MediaPipe 默认 pose33_v3、infer()/annotate() 默认行为不得改变。
- YOLO-only 继续 score_authorized=False，calibration_status=unvalidated。
- COCO17 结构性缺点不因性能优化而消失，不进入 full tech_eval。

## 进度清单

### A. YOLO 性能二次决策

- [ ] P0 benchmark warmup、稳定态延迟分布与二次决策基线
- [ ] P1 YOLO PyTorch FP16 / imgsz / warmup opt-in 与质量守卫
- [ ] P2a TensorRT / ONNX 导出与 engine benchmark spike

### B. 现有实时体验 / 离线性能优化

- [ ] P3a 实时预览 Hands 开关（MediaPipe 默认提速）
- [ ] P3b 实时采集 / 推理 / 渲染解耦 smoke
- [ ] P4 MediaPipe GPU delegate opt-in 可行性 spike
- [ ] P5 离线 DTW / 序列提取 profile 与优化决策

## 二次决策门

三段式门禁：

1. P0/P1/P2a 至少一条 YOLO 优化路径同时满足性能阈值与质量守卫。
2. 达标后只允许新开“重新评估 CLI/UI YOLO 实时入口”的评估 issue，不自动重开或实现 #25/#26。
3. 即使性能达标，仍必须保留 `score_authorized=False` / 不进 full tech_eval / 不切默认；默认切换只能另走 S6 决策。

若 P1/P2a 仍不达标，则 #23 no-go 升级为“含 warmup/FP16/engine 验证后的 no-go”。
```
