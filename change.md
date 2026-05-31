## 2026-05-31: YOLO 迁移 S5d — Hybrid 默认不实现决议（Issue #27）

### 问题描述

Issue #27 需要基于 #23 GPU 复测和 S0/S3 结论，决定是否实现离线 Hybrid
`yolo_body_mp_pose_supplement`。Hybrid 的本质是 YOLO body 后再跑 MediaPipe Pose 补脚 / 补脸；
如果没有数字证明其性能代价可接受，就会抵消 YOLO 的主要收益，还可能引入半成品路径。

### 修改内容

- `docs/yolo_gpu_recheck_report.md`：新增 “Hybrid 决议（Issue #27）” 小节，引用
  `torch.cuda.is_available()=False`、GPU 有效复测覆盖 0/6、S0 CPU speedup=0.41、COCO17 缺脚跟脚尖
  等数字 / 事实，明确结论为不实现 `yolo_body_mp_pose_supplement`。
- 明确未来重新评估 Hybrid 的触发条件：CUDA 有效复测、Hybrid 专用 benchmark、补点指标恢复证据，
  且仍只能作为离线显式模式，不能进入默认 / 实时路径。
- 新增 `tests/test_s5_hybrid_decision.py`：锁住 #27 报告必须含数字依据、默认不实现结论，并确认
  `apps/`、`batch/`、`core/`、`analysis/` 中不存在半成品 Hybrid runtime 代码路径。

### 验证方法

```powershell
E:\CodeProject\vision\.venv\Scripts\python.exe -m pytest tests\test_s5_hybrid_decision.py -q
E:\CodeProject\vision\.venv\Scripts\python.exe -m pytest tests\test_pose33_v3_golden.py -q
E:\CodeProject\vision\.venv\Scripts\python.exe -m py_compile tests\test_s5_hybrid_decision.py
git diff --check
```

---

## 2026-05-31: PR #30 审查补强 — batch_export_skeleton 已存在输出 meta 透传

### 问题描述

子 agent 审查 PR #30 时指出：`batch_export_skeleton.py` 在 `--backend yolo --feature-layout body_core_v1`
且目标 `.npz` 已存在时会走 skip 分支，该分支只写短 manifest 行，没有补齐 Issue #24 要求的
backend/layout/calibration/review meta；若同批次同时存在 skipped 行与新处理行，还可能因 CSV
header 取第一行字段导致后续行多字段写入失败。

### 修改内容

- `batch/batch_export_skeleton.py`：新增统一 `_manifest_row()` 与 union fieldnames 写 CSV；skip
  已存在 body_core npz 时读取现有 `.npz` meta 并透传 `backend` / `model_name` /
  `feature_layout` / `confidence_kind` / `validity_policy` / `valid_conf_thr` /
  `calibration_status` / `score_authorized` / `review_required`。
- `tests/test_batch_backend_args.py`：新增 skipped + processed 混合场景测试，确认 manifest
  两类行都含 #24 meta 字段且不会因字段不一致报错。

### 验证方法

```powershell
E:\CodeProject\vision\.venv\Scripts\python.exe -m pytest tests\test_batch_backend_args.py -q
E:\CodeProject\vision\.venv\Scripts\python.exe -m pytest tests -q
E:\CodeProject\vision\.venv\Scripts\python.exe -m py_compile batch\backend_options.py batch\batch_dual_compare.py batch\batch_export_skeleton.py batch\batch_tech_eval.py
git diff --check
```

---

## 2026-05-31: YOLO 迁移 S5a — batch backend/layout 参数与 metadata 透传（Issue #24）

### 问题描述

S5a 需要让三个 batch 入口显式支持 `--backend` / `--feature-layout`，使 YOLO
`body_core_v1` 能用于离线调试 / 标定对照，同时严格保持默认 MediaPipe `pose33_v3`
旧行为不变。YOLO body_core 分数未授权对外评分，输出必须带 `calibration_status=unvalidated`
与 `score_authorized=False`，多人视频必须标「需人工复核 / 拒绝」，不能混入正常评分列。

### 修改内容

- 新增 `batch/backend_options.py`：统一 backend/layout 参数、非法组合校验（YOLO 只允许
  `body_core_v1`）、Issue #24 要求的 meta 字段与 CSV 透传字段。
- `batch/batch_dual_compare.py`：默认 `mediapipe + pose33_v3` 路径保持旧逻辑；显式
  `body_core_v1` 时走 `core.body_core_compare` 闭环，输出 `front_debug_score` /
  `side_debug_score` 与 meta，不写 `front_score` / `combined_percent` 等对外评分列；多人结果标
  `review_status=需人工复核`。
- `batch/batch_export_skeleton.py`：默认导出 Pose33 `.npz` 与骨架视频逻辑不变；显式
  `body_core_v1` 时导出 `features[T,12,2]` 与 backend/layout/calibration/review meta，并在
  manifest 透传。
- `batch/batch_tech_eval.py`：默认 MediaPipe full tech_eval 不变；显式 `body_core_v1` 时不做对外
  技术评分，结构化写出 `无法判定` / `unvalidated_backend` / `score_authorized=False`，YOLO 多人标
  需人工复核。
- 新增 `tests/test_batch_backend_args.py`：覆盖默认参数、非法 YOLO+pose33、YOLO meta、调试分数
  与对外评分列分离、多人复核、NPZ/CSV/JSONL meta 透传。

### 验证方法

```powershell
E:\CodeProject\vision\.venv\Scripts\python.exe -m pytest tests\test_batch_backend_args.py -q
E:\CodeProject\vision\.venv\Scripts\python.exe -m pytest tests\test_pose33_v3_golden.py tests\test_body_core_layout.py tests\test_yolo_backend_contract.py -q
E:\CodeProject\vision\.venv\Scripts\python.exe -m py_compile batch\backend_options.py batch\batch_dual_compare.py batch\batch_export_skeleton.py batch\batch_tech_eval.py
git diff --check
```

---

## 2026-05-31: PR #29 审查补强 — S5 GPU 复测 harness 指标字段

### 问题描述

子 agent 审查 PR #29 时指出：当前 CUDA 不可用时报告可以产出 no-go 证据，但若后续换成
CUDA-enabled torch 复跑，`analysis/bench_annotate_fps.py` 的 CUDA 可用分支只写
`annotate_fps`，尚不能产出 #23 预注册表要求对照的 YOLO 裸推理 FPS、漏检 / 缺失帧率与
body_core 抖动指标。

### 修改内容

- `analysis/bench_annotate_fps.py`：YOLO 预览分支在每帧 `infer_frame()` 周围单独计时，输出
  `yolo_raw_infer_fps` / `yolo_raw_infer_sec`；统计 `yolo_miss_rate`、
  `yolo_body_core_full_valid_rate`、`yolo_body_core_missing_rate`；基于连续 full-valid
  body_core 帧计算 `yolo_body_core_jitter_median`。
- `docs/yolo_gpu_recheck_report.md`：补充说明 CUDA 可用时 harness 会写出上述字段，用于对照裸推理
  FPS、失败 / 漏检帧率与抖动阈值。
- `tests/test_s5_gpu_recheck.py`：新增 body_core 抖动 helper 与 CSV schema 回归，锁住 #23
  预注册指标字段不会被后续删掉。

### 验证方法

```powershell
E:\CodeProject\vision\.venv\Scripts\python.exe -m pytest tests\test_s5_gpu_recheck.py tests\test_yolo_backend_contract.py -q
E:\CodeProject\vision\.venv\Scripts\python.exe -m pytest tests -q
E:\CodeProject\vision\.venv\Scripts\python.exe -m py_compile analysis\bench_annotate_fps.py
git diff --check
```

---

## 2026-05-31: YOLO 迁移 S5 — GPU 复测决策门（Issue #23）

### 问题描述

S0 的 CPU spike 显示本机 CPU 上 YOLO 不提速（YOLO/MediaPipe 纯推理 FPS 比 0.41），而 S5
是否扩实时入口 / UI / 默认切换必须改看 GPU 上 `annotate()` 端到端链路。此前仓库没有独立
benchmark harness 能按 Hands 开 / 关两档复测 `apps/main.py` 同等预览链路，也没有 #23 的
GPU 复测决策报告。

### 修改内容

- 新增 `analysis/bench_annotate_fps.py`：独立 S5 benchmark harness，只读调用既有
  `MediaPipePipeline.annotate()` 与 `YoloPoseAdapter.infer_frame()`，支持 Hands 开 / 关两档、
  `--asset-root` 引用本地 gitignored 样本、`--device cuda`、环境探针与 JSON/CSV 输出；不接主链路。
- 新增 `docs/yolo_gpu_recheck_report.md`：固定本机环境、预注册 GPU runtime / 6 样本覆盖 /
  Hands 开关 FPS 比 / 漏检 / 抖动阈值，并按实测 `torch=2.12.0+cpu`、
  `torch.cuda.is_available()=False`、有效 GPU benchmark rows=0 判定 **no-go**。
- 分流结论：#25 / #26 在当前环境关闭不实现；#24 可独立推进；#27 默认不实现；#28 仍需执行但
  no-go 分支下简化为“全部不切默认，仅保留离线 / 实验入口”。

### 验证方法

```powershell
E:\CodeProject\vision\.venv\Scripts\python.exe -m analysis.bench_annotate_fps --samples docs/yolo_eval_samples.json --asset-root E:\CodeProject\vision --models-dir E:\CodeProject\vision\models --yolo-model E:\CodeProject\vision\models\yolo11n-pose.pt --device cuda --out outputs/gpu_recheck  # 写出 status=skipped / skip_reason=torch_cuda_unavailable
E:\CodeProject\vision\.venv\Scripts\python.exe -m py_compile analysis\bench_annotate_fps.py
E:\CodeProject\vision\.venv\Scripts\python.exe -m pytest tests\test_pose33_v3_golden.py -q
```

---

## 2026-05-31: PR #22 审查补强 — S4 结构化状态

### 问题描述

审查 PR #22 时发现两处结构化契约细节需要补强：`core/pose_features.py` 的 COCO17
能力分组把 `left_eye/right_eye` 也当成结构性缺失，和 `core/yolo_adapter.py` 已有映射契约
不一致；`batch/batch_tech_eval.py` 的 CSV 只给部分技术指标写出“缺失关键点”列，重心侧面/
正面/CoM 分项缺少对应列。

### 修改内容

- `core/pose_features.py`：将眼部能力拆成 `eyes`（2/5，COCO17 有近似映射）与
  `eye_details`（1/3/4/6，COCO17 结构性缺失），`COCO17_SUPPORTED_CAPABILITIES`
  纳入 `eyes`，避免未来能力判定误报。
- `batch/batch_tech_eval.py`：CSV 补齐 `重心_侧面缺失关键点`、`重心_正面缺失关键点`、
  `重心_CoM缺失关键点`，使报告列与每个重心分项的结构化契约一致。
- `tests/test_rule_availability.py`：新增 COCO17 眼部能力映射回归，锁住左右眼中心可用、
  眼细分缺失的契约。

### 验证方法

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_rule_availability.py tests\test_tech_eval_contract.py -q  # 17 passed
.\.venv\Scripts\python.exe -m pytest tests\test_pose33_v3_golden.py tests\test_valid_mask_migration.py tests\test_yolo_landmark_mapping.py -q  # 42 passed
.\.venv\Scripts\python.exe -m pytest tests -q  # 136 passed
.\.venv\Scripts\python.exe -m py_compile core\pose_features.py core\rule_scoring.py analysis\tech_eval.py batch\batch_tech_eval.py batch\batch_dual_compare.py  # exit 0
```

---

## 2026-05-31: YOLO 迁移 S4 — 规则与技术评估分级（结构化状态，Issue #11）

### 问题描述

评估链路要能诚实输出「能评估什么、不能评估什么」。此前 `core/rule_scoring.py` 的
`RuleViolation` 三态（已评估 / 合格 / 未评估）只靠中文 `detail` 字符串拼
（`（合格）` / `（有效帧不足，未评估）`），下游无法用稳定字段判断；`analysis/tech_eval.py`
各指标也没有声明「依赖哪些关键点、运行时缺了哪些点、来自哪个后端」。本期按 #11 任务规范
**补结构化字段，不推倒重来**。

**范围分流（按 #10 结论，硬约束）**：Issue #10 标定结论为「**仅用于预览**」
（`docs/yolo_body_core_calibration.md` 第八节：跨视频 J1 corr=0.280、J4 一致率=0.50 未达标）。
据 #11 前置条件，本期**只做 MediaPipe 侧结构化状态改造**，**不启用 YOLO partial tech_eval
指标**。MediaPipe 默认 `pose33_v3` 路径与 golden 不得漂移。

### 修改内容

- **`core/pose_features.py` 新增集中式关键点命名 + 能力分组（Issue #11）**：
  - `BLAZE33_LANDMARK_NAMES`（33 点英文名表）、`landmark_names()` / `landmark_capabilities()`。
  - 能力分组常量 `CAP_FACE_CENTER/EYES/EYE_DETAILS/EARS/MOUTH/ARMS/HANDS/LEGS/FEET` 与
    `COCO17_SUPPORTED_CAPABILITIES`（COCO17 结构性支持 = face_center/eyes/ears/arms/legs，
    缺 eye_details/mouth/hands/feet，对应 adapter 映射与 S0 降级清单）。
  - `landmarks_missing_for_capabilities(indices, supported)`：按能力分组判定后端结构性缺点；
    `supported=None`（MediaPipe full）视为全部支持、返回空（行为不变）。
- **`core/rule_scoring.py` 规则三态结构化（Issue #11）**：
  - 新增三态常量：`RULE_STATE_EVALUATED/SKIPPED`、`SKIP_MISSING_LANDMARKS/LOW_CONFIDENCE/
    INSUFFICIENT_VALID_FRAMES`。
  - `Rule` 新增 `required_indices`（与各 `_rule_*` 内 `_valid_frame(...)` 关键点集合一致）；
    `RuleViolation` 新增 `state` / `skip_reason` / `required_landmarks` / `required_capabilities`
    / `missing_landmarks`（均带默认值，向后兼容）。
  - `score_rules` 新增可选 `supported_capabilities` 形参（默认 `None`=MediaPipe full）：
    后端缺所需能力时该规则直接 `state=skipped` + `skip_reason=missing_landmarks` 并列出缺失点，
    不当合格/不合格；有效帧 0 → `low_confidence`，0<cnt<min_valid → `insufficient_valid_frames`，
    充足 → `evaluated`。**`detail` 中文逐字保留**，故 golden 不漂移。
- **`analysis/tech_eval.py` 指标契约字段（Issue #11）**：
  - `IndicatorResult` 新增 `required_landmarks` / `missing_landmarks` / `backend`（默认 mediapipe，
    带默认值向后兼容）。
  - 新增每指标 `*_REQUIRED_INDICES` 声明、`_runtime_missing_landmarks()`（整段从未有效的点）、
    `_attach_contract()`（装配层统一补齐契约字段，**不改各 `eval_*` 内部 status/reason/detail
    判定**）。在 `_evaluate_from_arrays` 末尾对七个指标按各自所需关键点与所在段 mask 补齐；
    `keep_detail=False` 与 `evaluate_video` 的 strip 改用 `dataclasses.replace`，保留契约字段。
- **报告输出补缺失关键点 / backend（Issue #11，仅 MediaPipe 侧）**：
  - `batch/batch_tech_eval.py`：CSV 新增「重心（侧面优先/侧面/正面/CoM）/回收速度/
    发力顺序/拳面角度 缺失关键点」列与 `backend` 列；JSONL 经 `to_jsonable` 自动带上新字段。
  - `batch/batch_dual_compare.py`：`error_rules.csv` 新增 `state` / `skip_reason` /
    `missing_landmarks` 列；JSONL 经 `_jsonable`(asdict) 自动带上新字段。
- **新增测试**：
  - `tests/test_rule_availability.py`：覆盖三种 `skip_reason`（low_confidence /
    insufficient_valid_frames / missing_landmarks）、COCO17 缺点规则（feet/mouth）被 skipped、
    required_landmarks/capabilities 声明正确、默认不传 `supported_capabilities` 时无 backend 级缺点，
    并回归 COCO17 左右眼中心可用、眼细分缺失的 adapter 契约。
  - `tests/test_tech_eval_contract.py`：`evaluate_video_full` 每指标含 `status/reason/
    required_landmarks/missing_landmarks/backend`；`_attach_contract` 不改 status/reason/detail；
    人为遮挡脚部后 `missing_landmarks` 如实含脚跟/脚尖；契约字段 JSON 可序列化。
- **`docs/yolo_migration_issues.md`**：Issue #11 顶部勾选「仅预览 → 仅 MediaPipe 结构化改造」分支，
  任务清单 / 验收标准按本期实现状态更新（YOLO partial eval 标注「不适用」）。

### 范围守住（未做）

- 未启用任何 YOLO partial tech_eval 指标（#10 = 仅预览）；`supported_capabilities` 仅预留接口。
- 未改各 `eval_*` / 各 `_rule_*` 的判定逻辑与阈值；未重标定。
- MediaPipe 默认 `pose33_v3` 路径行为不变（golden 全绿）。

### 验证方法

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_rule_availability.py tests\test_tech_eval_contract.py -q  # 17 passed
.\.venv\Scripts\python.exe -m pytest tests\test_pose33_v3_golden.py tests\test_valid_mask_migration.py tests\test_yolo_landmark_mapping.py -q  # 42 passed（MediaPipe 默认不漂移 + adapter 契约）
.\.venv\Scripts\python.exe -m pytest tests -q                                                              # 136 passed（此前 119 + 本期 17 新增）
.\.venv\Scripts\python.exe -m py_compile core\pose_features.py core\rule_scoring.py analysis\tech_eval.py batch\batch_tech_eval.py batch\batch_dual_compare.py core\action_compare.py apps\main.py apps\app_ui.py  # exit 0
```

- `tests/test_pose33_v3_golden.py` 全绿 → 规则 `detail` 中文逐字保留、各指标判定未改动，MediaPipe
  旧路径行为不漂移（行为不变硬门槛）。
- `tests/test_rule_availability.py` / `tests/test_tech_eval_contract.py` 全绿 → 结构化三态与指标契约
  字段齐全、缺点判定正确、不可评估不当合格/不合格。
- 全量 136 passed（此前 119 + 本期 17 新增）→ 无回归。

---

## 2026-05-31: YOLO 迁移 S3 — 标定与基准报告（Issue #10）

### 问题描述

S3 需要在同一批样本上跑三路对照（MediaPipe `pose33_v3` / MediaPipe `body_core_v1` /
YOLO `body_core_v1`），据**预注册数字判据**确定：① `body_core_v1` 是否可用于评分；
② 重标定 `body_core_v1` DTW baseline（替换全局占位 `2.0`）；③ 标定 YOLO 侧
`valid_conf_thr`（替换 #7 占位 `0.5`；是否允许出分由 S3 go/no-go 判据决定）。结论必须对照
预注册数字、不能是「可用/不建议」这类感觉。硬约束：先预注册阈值与 pass/fail 口径再跑数据；
多人样本（闸门 `review_required=True`）不得进入标定；MediaPipe 默认 `pose33_v3` 路径与
golden 不漂移。

### 修改内容

- **新增 `analysis/calibrate_body_core.py`（独立标定脚本，组合既有生产函数，不改主链路默认行为）**：
  - 每段样本每后端**只推理一次**并缓存到 `outputs/calib_body_core/raw_cache/*.npz`；
    `valid_conf_thr` 扫描只对缓存 conf 重新阈值化派生 `valid_mask`，不重复推理。
  - 由 MediaPipe `(T,33,4)` 缓存同时派生 `pose33_v3`（`normalize_pose_xy_v3`）与
    `body_core_v1`（`normalize_pose_body_core_v1`）；YOLO `(T,33,4)` 缓存派生 YOLO `body_core_v1`。
  - **成对匹配矩阵**（视角组内，跨视频）：self-match 恒为满分、无方差，故只取跨样本对统计
    相关性 / baseline / pass-fail，避免 self-match 把相关性虚高成 1.0。
  - 多人样本由 YOLO 多人闸门（`evaluate_multi_person_gate`，沿用 #9 逻辑不改）排除出标定集。
- **`core/feature_layout.py`**：`BODY_CORE_V1.default_baseline` 由占位 `None` 标定为 **1.2826**
  （尺度对齐：`2.0 × median(bodycore_avg_cost)/median(pose33_avg_cost) = 2.0 × 0.6413`），
  使 body_core 分数与 pose33 同尺度、可共享 pass/fail 阈值。
- **`core/yolo_adapter.py`**：`DEFAULT_YOLO_VALID_CONF_THR` 由占位 `0.5` 定为 **0.6**；
  `YOLO_CALIBRATION_STATUS` 保持 `unvalidated`；`CALIBRATION_NOTE` 改写为「参数已落库，
  但跨视频 go/no-go 未通过，仅预览 / 内部标定参考，不得对外评分」。
- **`core/body_core_compare.py`**：baseline 取自 layout（`BODY_CORE_V1_CALIBRATED_BASELINE`），
  移除占位 `BODY_CORE_V1_PLACEHOLDER_BASELINE`；模板/匹配结果 `calibration_status` 仍标
  `unvalidated`，模板 meta 额外写 `score_authorized=False`，明确不得进入用户报告 / 正式评分。
- **`apps/make_template.py` / `apps/match_template.py`**：更新 body_core 路径打印文案为「仅预览 /
  内部标定参考，不得对外评分」。
- **新增 `docs/yolo_body_core_calibration.md`（标定报告）**：头部预注册 pass/fail 判定口径
  （模板分数阈值口径、pose33 分数 ≥ 0.55、样本范围=4 段单人）与 7 条数字判据（J1–J7）；
  正文逐条引用实测数字；**结论四选一 = 「仅预览」**（跨视频 J1 corr 0.280 未达标、
  J4 一致率 0.50 未达标；J2 corr 0.980、J3 MAE 0.0468、J5 有效率 0.875、J7 失败率 0 达标），
  并说明含 self-match 的 0.838/0.990/0.0234 只作健全性检查、不可作为验收判据。
- **新增 `tests/test_s3_calibration.py`**：守卫标定值入库（baseline=1.2826、thr=0.6、状态字符串）、
  报告存在且头部含预注册数字与四选一结论。
- **更新既有测试**：`test_body_core_layout.py`（baseline 已标定、`baseline_calibrated=True`）、
  `test_yolo_backend_contract.py` / `test_yolo_landmark_mapping.py`（`calibration_status` /
  `valid_conf_thr`=0.6）随标定语义同步。

### 关键结论（详见 docs/yolo_body_core_calibration.md）

- **body_core_v1 仅预览 / 内部标定参考，不授权模板匹配对外出分**：baseline=1.2826、YOLO
  `valid_conf_thr`=0.6 已落库，但 `calibration_status=unvalidated`、`score_authorized=False`。
- **不进 full tech_eval**：跨视频 body_core 与 pose33 参照分歧（J1=0.280、J4=0.50）+
  COCO17 结构性缺点。
- **阈值标定核心证据**：thr 0.5→0.6 时跨视频 corr(YOLO,MP body_core) 0.105→0.980、
  MAE 0.1466→0.0468；thr=0.7 无收益反丢帧（有效率最小 0.784）。故取满足 J2/J3 的最小阈值 0.6。
- **侧面发现**：MediaPipe `visibility>=0.5` 在侧面把远侧关节判为不可见（punch_side body_core
  有效率仅 0.147），YOLO `conf>=0.6` 在侧面保留更多帧（~0.92–1.0）。
- **对 #11 分流**：结论 =「仅预览」→ #11 只做 MediaPipe 侧结构化状态改造，
  不启用 YOLO partial tech_eval。

### 验证方法

```powershell
.\.venv\Scripts\python.exe -m analysis.calibrate_body_core --calib-conf-thr 0.6 --out outputs/calib_body_core
.\.venv\Scripts\python.exe -m pytest tests\test_s3_calibration.py -q                              # 5 passed
.\.venv\Scripts\python.exe -m pytest tests\test_body_core_layout.py tests\test_yolo_backend_contract.py tests\test_yolo_landmark_mapping.py -q  # 含本期标定语义更新
.\.venv\Scripts\python.exe -m pytest tests\test_pose33_v3_golden.py -q                            # 16 passed（MediaPipe 默认不漂移）
.\.venv\Scripts\python.exe -m pytest tests -q                                                     # 119 passed（此前 114 + 本期 5 新增）
.\.venv\Scripts\python.exe -m py_compile core\feature_layout.py core\yolo_adapter.py core\body_core_compare.py analysis\calibrate_body_core.py apps\make_template.py apps\match_template.py  # exit 0
```

- `tests/test_pose33_v3_golden.py` 全绿 → MediaPipe 旧 `pose33_v3` 路径行为不漂移（行为不变硬门槛）。
- `tests/test_s3_calibration.py` 全绿 → baseline/阈值/状态已入库、报告头部预注册数字齐全。
- 全量 119 passed（此前 114 + 本期 5 新增）→ 无回归。

---

## 2026-05-31: YOLO 迁移 S2 — 多人场景闸门（Issue #9）

### 问题描述

`batch_tech_eval` / `batch_dual_compare` 跑的是学员视频，教练、镜面反射、路人入镜常见
（S0 spike 已实证：学员样本最多检出 8 人、单视频 274 帧多人）。YOLO「最大框/最高分取单人」
可能**稳定选错实例**——这是正确性风险，不是鲁棒性优化。MVP 必须能识别并拒绝/降级，
**不允许静默选最大框**。本期依赖 #7（YOLO adapter，已合并 main），在序列层判定多人并写
meta，在 YOLO 评分入口（#8 的 `body_core_compare` 闭环）强制拒绝/降级出分。硬约束：
单人样本不受影响；MediaPipe 默认路径与 `pose33_v3` golden 不漂移；完整多人鲁棒策略
（中心最近、tie-break、跨段 track 延续）本期不做。

### 修改内容

- **`core/yolo_adapter.py` 新增多人闸门判定**：
  - 新增纯函数 `evaluate_multi_person_gate(num_persons_per_frame)`，返回
    `multi_person_detected` / `max_persons` / `multi_person_frames` / `gate_status` /
    `review_required` / `gate_note`。语义铁律：`review_required=True` 的视频不得进入对外评分。
  - 新增常量 `GATE_STATUS_OK="ok"`、`GATE_STATUS_MULTI_PERSON="multi_person_review_required"`、
    `MULTI_PERSON_GATE_NOTE`（说明多人 = 正确性风险、必须人工复核）。
  - `extract_yolo_landmark_series` 的 meta 在原有 `num_persons_per_frame`/`max_persons`/
    `multi_person_frames` 基础上新增 `multi_person_detected`/`gate_status`/`review_required`/
    `gate_note`（检出 `num_persons>1` 即标 `review_required=True`）。
  - 更新模块/函数 docstring：闸门已落地（不再是「留给 #9」），`select_main_person` 注明仅单人
    场景可信、多人由闸门拒绝/降级。
- **`core/body_core_compare.py` 在 YOLO 评分入口强制拒绝/降级**：
  - 新增异常 `MultiPersonReviewRequiredError`（携带 `max_persons`/`multi_person_frames`）。
  - `BodyCoreMatchResult` 新增 `review_required`/`multi_person_detected`/`max_persons`/
    `multi_person_frames` 字段；`score` 类型放宽为 `float | None`（降级模式不产出分数）。
  - `match_body_core_template` 新增 `reject_multi_person: bool = True` 参数：
    默认多人抛 `MultiPersonReviewRequiredError`（不混入正常评分）；
    `reject_multi_person=False` 时降级——返回 `score=None` + `review_required=True`。
    单人 / MediaPipe 路径不受影响。
  - 审查补强：`match_body_core_template` 同时检查模板 meta 与目标视频 meta；YOLO 模板若由
    多人视频生成，默认也会拒绝出分，降级时 `score=None`，避免多人来源模板继续参与正常评分。
  - `_extract_body_core_yolo` 随 `backend_meta` 透传闸门字段；`create_body_core_template`
    把多人闸门字段（`multi_person_detected`/`review_required`/`gate_status` 等）一并写入模板 meta。
- **`apps/match_template.py` CLI 接线**：新增 `--allow-multi-person`（降级而非拒绝）；
  body_core 匹配捕获 `MultiPersonReviewRequiredError` 打印「需人工复核、拒绝出分」，
  降级时 `score=N/A` 且打印多人复核提示，避免格式化 `None` 崩溃。
- **测试**：
  - `tests/test_yolo_backend_contract.py` 增补：`evaluate_multi_person_gate` 单人/多人/空序列
    判定；序列层多人帧触发 `multi_person_detected`/`review_required`/`gate_status`，单人样本不触发。
  - `tests/test_body_core_layout.py` 增补：默认多人视频抛 `MultiPersonReviewRequiredError`、
    `--allow-multi-person` 降级返回 `score=None`+`review_required=True`、单人不受影响、
    多人来源模板 meta 透传 `review_required`，并补充多人来源模板默认拒绝出分回归。
    全程用 fake adapter + `patch_cv2_capture`，无网络、不下载模型、不读真实视频。

### 验证方法

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_yolo_backend_contract.py tests\test_body_core_layout.py -q   # 39 passed（含本期多人闸门用例）
.\.venv\Scripts\python.exe -m pytest tests\test_pose33_v3_golden.py -q                                        # 16 passed（MediaPipe 默认不漂移）
.\.venv\Scripts\python.exe -m pytest tests -q                                                                 # 114 passed（此前 104 + 本期 10 新增）
.\.venv\Scripts\python.exe -m py_compile core\yolo_adapter.py core\body_core_compare.py apps\match_template.py apps\make_template.py apps\app_ui.py apps\main.py   # exit 0
```

- `tests/test_pose33_v3_golden.py` 全绿 → MediaPipe 旧 `pose33_v3` 路径行为不漂移（行为不变硬门槛）。
- 多人帧触发 `multi_person_detected`/`review_required` 并被拒绝/降级，不静默选最大框（验收①）。
- 多人视频明确标「需人工复核/拒绝」，不混入正常评分结果（验收②）。
- 单人样本照常出分、不受闸门影响（验收③）。
- 全量 114 passed（此前 104 + 本期 10 新增）→ 无回归。

---

## 2026-05-31: YOLO 迁移 S2 — body_core_v1 布局引入 + 离线模板闭环（Issue #8）

### 问题描述

S2 需要引入 `body_core_v1`(12,2) 共享布局（YOLO/MediaPipe 都能产出的躯干四肢核心 12 点），
新增其 normalizer，并打通**一条** YOLO `body_core_v1` 离线模板闭环（生成 → 匹配）。该布局
此前在 S1 被刻意推迟（Issue #4 注释明确写「`body_core_v1` 在 #8 才注册」），因为只有真接
YOLO 时才有消费者。硬约束：不动 MediaPipe 默认 `pose33_v3` 路径（`infer()`/`annotate()`/
旧模板比对、golden 全绿）；YOLO 只允许 `body_core_v1`；`body_core_v1` baseline 与 YOLO 侧
`valid_conf_thr` 本期均为**待标定占位值**（正式标定在 #10），闭环输出 metadata 必须标
`calibration_status=unvalidated`、不得进入用户报告 / 正式评分；不同 layout 比对报清晰错误；
不实现 UI 后端选择 / Hybrid / 默认切换。

### 修改内容

- **`core/feature_layout.py` 注册 `body_core_v1`**：12 点 `source_indices=(11,12,13,14,15,16,
  23,24,25,26,27,28)`（肩/肘/腕 + 髋/膝/踝，全部落在 COCO17 可映射点），`shape=(12,2)`，
  `mirror_pairs` 为相邻对 `(0,1)…(10,11)`，`joint_names` L/R 交替。`default_baseline=None`
  （待标定占位，刻意区别于 pose33_v3 的已标定 2.0）。模块 docstring 同步更新范围说明。
- **`core/pose_features.py` 新增共享 normalizer `normalize_pose_body_core_v1()`**：归一化策略
  与 `normalize_pose_xy_v3` 同构（躯干长度为主尺度 + front/side 自适应旋转），但索引/输出
  shape/关节顺序全部取自 `BODY_CORE_V1` layout。新增 `_blaze33_xy_getter()` 统一两类输入——
  MediaPipe landmark 对象序列 与 YOLO `(33,4)` numpy 行——因此**同一 normalizer 跨后端共享**，
  供 #10 三方对比。
- **`core/yolo_adapter.py` 新增 `BODY_CORE_V1_VALID_INDICES`**：body_core_v1 在 BlazePose33 中
  的源索引（与 layout.source_indices 一致，冗余定义避免 adapter 反向依赖 feature_layout 触发
  循环 import；一致性由测试守卫）。供闭环按 `valid_mask` 统计 body_core 有效帧率。
- **新增 `core/body_core_compare.py`（离线闭环唯一入口）**：
  - `extract_body_core_features(backend=...)`：MediaPipe 路径复用 `rule_scoring.extract_pose_raw`
    拿 `(T,33,4)` 后逐帧套共享 normalizer（也让 golden harness 能确定性回放）；YOLO 路径用
    `extract_yolo_landmark_series` 拿序列层 `(T,33,4)`+`valid_mask` 后同样逐帧 normalize。
    缺帧按 layout shape 补零或沿用上一帧。
  - `create_body_core_template()`：生成 `body_core_v1` 模板，metadata 写
    `feature_layout=body_core_v1`、`calibration_status=unvalidated`、`baseline_calibrated=False`、
    占位 `baseline` 与 `calibration_note`；YOLO 路径透传 `valid_conf_thr`/多人/track 信息。
  - `match_body_core_template()`：匹配前强制校验模板 `feature_layout` 必须为 `body_core_v1`
    （否则报清晰错误，不与 pose33_v3 混用），复用 `_assert_feature_layout_match` 守卫 shape/layout，
    返回 `BodyCoreMatchResult`（标 `calibration_status=unvalidated`，分数仅供调试/标定）。
- **CLI 接线（显式 opt-in，默认 pose33_v3 路径完全不变）**：
  - `apps/make_template.py`：新增 `--backend {mediapipe,yolo}`、`--feature-layout {pose33_v3,
    body_core_v1}`；选 body_core_v1 或 yolo 时走 `_make_body_core_template`，否则走原
    `_make_pose33_v3_template`（原逻辑零改动）。YOLO 强制 body_core_v1。
  - `apps/match_template.py`：新增同名参数；按模板 `meta.feature_layout` 或显式参数判定是否走
    `_match_body_core`，否则走原 `_match_pose33_v3`。打印明确标注分数未标定、不得对外评分。
- **测试**：
  - 新增 `tests/test_body_core_layout.py`（16 用例）：layout shape/mirror pairs/joint names、
    共享 normalizer 接受 MediaPipe landmark 与 YOLO `(33,4)` 行、layout mismatch 报错、
    **YOLO body_core_v1 离线闭环生成→匹配同一视频产出分数且标 unvalidated**、YOLO 拒绝
    pose33_v3 模板、MediaPipe 也能生成 body_core_v1 模板。PR #19 审查补充两条回归：YOLO
    低置信 body_core 核心点帧必须按 `valid_mask` 视为无效并沿用上一帧特征；`start/end`
    显式裁剪必须在完整序列上切片，避免先裁后再用原始帧号二次裁剪导致模板退化为单帧。
    全程用 fake adapter + golden harness，无网络、不下载模型、不读真实视频。
  - 更新 `tests/test_layout_shape_param.py`：`body_core_v1` 现已注册（断言改为 `has_layout` 为真）；
    无法解析 shape 的用例从 `(12,2)` 改为仍未注册的 `(15,2)`，保留原意。
- **PR #19 审查修复**：
  - `core/body_core_compare.py` 新增统一 `_normalize_body_core_sequence()`：YOLO / MediaPipe
    body_core 序列在 normalizer 前先读 `valid_mask`，只有 12 个核心点全 valid 的帧才参与归一化；
    无效帧按缺帧处理（沿用上一帧或前导零帧），防止低置信坐标绕过 `valid_mask` 进入 DTW。
  - `create_body_core_template()` 不再把 `start/end` 传入提取器提前截断视频，而是先抽取完整序列、
    再按原始帧号切模板片段，与旧 `pose33_v3` CLI 语义保持一致。

### 验证方法

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_body_core_layout.py -q          # 16 passed
.\.venv\Scripts\python.exe -m pytest tests\test_pose33_v3_golden.py -q          # 16 passed（MediaPipe 默认不漂移）
.\.venv\Scripts\python.exe -m pytest tests\test_yolo_landmark_mapping.py tests\test_yolo_backend_contract.py -q  # YOLO 契约不变
.\.venv\Scripts\python.exe -m pytest tests -q                                   # 104 passed
.\.venv\Scripts\python.exe -m py_compile core\feature_layout.py core\pose_features.py core\yolo_adapter.py core\body_core_compare.py apps\make_template.py apps\match_template.py  # exit 0
```

- `tests/test_pose33_v3_golden.py` 全绿 → MediaPipe 旧 `pose33_v3` 路径行为不漂移（行为不变硬门槛）。
- `tests/test_body_core_layout.py` 全绿 → 布局正确、闭环可生成可匹配、分数标 unvalidated、layout mismatch 报错，且 PR #19 审查发现的 `valid_mask` 与 `start/end` 裁剪问题均有回归覆盖。
- 全量 104 passed（此前 88 + 本期 16 新增，含 1 处 S1 测试随注册状态变化的适配）→ 无回归。

---



### 问题描述

审查 PR #18（Issue #7）时发现本次 YOLO adapter 任务记录误写为未来日期 `2026-06-01`，
与当前任务完成日期不一致，后续追踪 issue、PR 与归档记录时容易造成时间线混乱。

### 修改内容

- 将本条 YOLO 迁移 S2 记录日期从 `2026-06-01` 校正为 `2026-05-31`。
- 保持原有 YOLO adapter 功能记录、验证命令与范围说明不变。

### 验证方法

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_yolo_landmark_mapping.py tests\test_yolo_backend_contract.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_pose33_v3_golden.py -q
.\.venv\Scripts\python.exe -m py_compile core\yolo_adapter.py apps\main.py apps\app_ui.py core\vision_pipeline.py
```

---

## 2026-05-31: YOLO 迁移 S2 — YOLO adapter + COCO17→Pose33-like 映射（Issue #7）

### 问题描述

S2 需要让 YOLO 进入主链路，但 COCO17 缺嘴角/手指/脚跟脚尖/眼细分点，绝不能伪造成完整
Pose33。本期新增轻量 YOLO adapter，把 COCO17 诚实映射到 BlazePose33-like 容器：缺失点在
序列层一律 `valid_mask=False`、在边界层一律 `synthetic=True`/`visibility=0.0`。硬约束：
不得改变 MediaPipe 旧默认路径（`pose33_v3` 模板、`infer()`/`annotate()`、`extract_pose_raw`），
`tests/test_pose33_v3_golden.py` 必须保持全绿；ultralytics 必须懒加载，未安装时不影响
MediaPipe 路径与既有测试；YOLO 侧 `valid_conf_thr` 本期为待标定占位值（#10 标定），仅供
预览/调试 + S3 标定，不得对外评分。

### 修改内容

- **新增 `core/yolo_adapter.py`（懒加载 ultralytics）**：
  - **边界容器**：`@dataclass(frozen=True)` 的 `Landmark`（含 `confidence`/`synthetic`）与
    `FrameResult`（`pose33`/`hands`/`track_id`/`meta`）。`synthetic=True` 只活在该边界层，
    绝不进入 `(T,33,4)` 序列数组。
  - **映射表**：`COCO17_TO_BLAZE33`（17 项）与 `BLAZE33_MISSING_IN_COCO17`（16 项），
    数值与已验证的 `analysis/spike_yolo_baseline.py` 完全一致（键=BlazePose33 idx、值=COCO17 idx）。
  - **纯映射函数**：`map_coco17_to_blaze33` 产出 `(33,4)` 行 `(x,y,z=0,conf)` + `(33,)` bool 行
    （映射点 `conf>=valid_conf_thr` 才有效，缺失点强制 `False`）；`coco17_to_landmarks` 产出
    边界层 33 元组（缺失点 `synthetic=True`/`visibility=0.0`，映射点带 `confidence`）；
    `map_coco17_person` 一次性返回「序列行 + 有效行 + FrameResult」三件套。
  - **结果解析**：`extract_persons`/`select_main_person`（单人 MVP=最大框，退化时取最高分）/
    `yolo_result_to_arrays`/`yolo_result_to_frame`，容忍 torch tensor 或 numpy，便于测试注入
    fake result。
  - **单目标 tracker**：`SingleTargetTracker`，段内连续分配 track_id，未检出超 `max_missed` 帧丢弃；
    `reset()` 归零（段边界语义）。
  - **adapter 类 `YoloPoseAdapter`**：`from ultralytics import YOLO` 仅在 `_load()` 内执行；
    默认模型路径走 `core.paths.models_dir()/yolo11n-pose.pt`；`valid_conf_thr` 占位默认 + 文档化
    为待标定；`confidence_kind="yolo_conf"`；`infer_arrays`（序列热路径，只回 numpy）与
    `infer_frame`（边界层 FrameResult）；暴露 `last_num_persons`/`num_persons`（供 #9 多人闸门），
    本期不实现闸门；`reset_tracker()` 控制段边界。
  - **序列层 `extract_yolo_landmark_series`**：返回 `landmarks[T,33,4]` + `valid_mask[T,33]`
    （**仅 numpy，不逐帧返回冻结对象**）+ `meta`。每次调用开头 `reset_tracker()`，故 track_id
    段边界必然重置。无人帧/空结果优雅降级为零行 + 全 False mask（不抛异常）。`meta` 含
    `backend="yolo"`、`model_name`、`running_mode`、`confidence_kind="yolo_conf"`、
    `validity_policy="confidence_thr"`、`valid_conf_thr`（占位）、`calibration_status="unvalidated"`、
    `calibration_note`（标注 preview/debug-only）、`frame_count`、`fps`、`num_persons_per_frame`、
    `max_persons`、`multi_person_frames`、`track_ids`、`track_reset_note`。
- **测试（无网络、不下载模型、不读真实视频）**：
  - 新增 `tests/yolo_fakes.py`：`make_coco17` 合成关键点、`FakeYoloResult`（single/multi/empty）
    模拟 ultralytics 结果、`FakeYoloAdapter` 替身 adapter（复用真实解析/ tracker 逻辑，鸭子类型注入）、
    `FakeCapture`+`patch_cv2_capture` 回放固定帧数。
  - `tests/test_yolo_landmark_mapping.py`：边界层缺失点 `synthetic=True`/`visibility=0.0`
    （含嘴角 9/10、手指 17-22、脚跟脚尖 29-32、眼细分 1/3/4/6）；序列层同索引 `valid_mask=False`、
    长度恰 33、COCO 对应点 confidence 正确传入 channel-3；序列层输出是 numpy 数组。
  - `tests/test_yolo_backend_contract.py`：无人帧/空结果零行+全 False mask 不崩；tracker 段边界
    重置语义；序列层只回 numpy + meta 字段齐全；`num_persons` 被如实暴露（多人不静默吞，
    闸门留 #9）；adapter 默认路径解析且构造/导入不触发 ultralytics。
- **依赖声明**：ultralytics/torch 仍只在 `requirements-spike.txt` 声明，**未**加入核心 `requirements.txt`。
- **范围守住**：未引入 `body_core_v1`（#8）、未实现多人闸门（#9）、未标定（#10）、未做规则分级（#11），
  无 UI/CLI/batch 接线，无默认后端切换。

### 验证方法

```powershell
.\.venv\Scripts\python.exe -m py_compile core\yolo_adapter.py                          # exit 0
.\.venv\Scripts\python.exe -c "import core.yolo_adapter"                               # import_ok，ultralytics/torch 均未加载
.\.venv\Scripts\python.exe -m pytest tests\test_yolo_landmark_mapping.py tests\test_yolo_backend_contract.py -q   # 24 passed
.\.venv\Scripts\python.exe -m pytest tests\test_pose33_v3_golden.py -q                 # 16 passed（MediaPipe 默认不变）
.\.venv\Scripts\python.exe -m pytest tests -q                                          # 88 passed
```

- `import core.yolo_adapter` 后 `sys.modules` 不含 `ultralytics`/`torch` → 懒加载成立，未安装 ultralytics
  也不影响 MediaPipe 路径与既有测试。
- `tests/test_pose33_v3_golden.py` 全绿 → MediaPipe 旧默认路径行为不漂移（行为不变硬门槛）。
- 全量 88 passed（此前 64 + 本期 24 新增）→ 无回归。

---

## 2026-05-31: YOLO 迁移 S1 — artifact root 统一 + 模板 metadata 扩展（Issue #6）

### 问题描述

此前 `models` / `templates` / `outputs` 三个顶层产物目录散落在各包里，统一用
`Path(__file__).resolve().parent / "models"` 之类写法推导（`core`/`apps`/`batch`/`analysis`
均有）。由于 `__file__` 锚点随所在包不同，同一类产物可能指向不同位置，难维护、易踩坑。
同时模板 metadata 缺少后端/布局/有效性信息，无法为 S2 接入 YOLO 做铺垫。本次将三个根目录
收口到唯一 helper，并以「增量、向后兼容」方式扩展模板 metadata。验收硬门槛：`pose33_v3`
golden 不漂移、旧模板仍可加载比对。

### 修改内容

- **集中式根目录解析**：新增 `core/paths.py`（仅依赖 `pathlib`，不导入业务模块避免循环），
  统一锚定仓库根（`core/` 包父目录）：`repo_root()` / `models_dir()` / `templates_dir()` /
  `outputs_dir()`。`templates_dir`/`outputs_dir` 返回前 `mkdir(parents=True, exist_ok=True)`；
  `models_dir` 仅保证目录存在，**不删除/移动**任何已有模型文件（缺失 `.task` 由
  `MediaPipePipeline` 自动下载）。
- **替换全部散落写法**：约定 `from core.paths import models_dir`（`core/` 内用相对 import），
  局部变量改名 `models_dir_path = models_dir()` 后透传；模板与 outputs 同理。覆盖：
  - models（9 处）：`core/action_compare.py`(3)、`core/rule_scoring.py`、`analysis/tech_eval.py`、
    `apps/main.py`(2)、`apps/app_ui.py`(2)、`apps/make_template.py`、`apps/match_template.py`(2)、
    `batch/batch_export_skeleton.py`。
  - templates（3 处）：`core/action_compare.py::create_template_from_video`、
    `apps/make_template.py`、`apps/match_template.py`(preview)。
  - outputs（4 处）：`apps/app_ui.py`、`batch/batch_tech_eval.py`、`batch/batch_export_skeleton.py`、
    `batch/batch_dual_compare.py`（均保留 `--out_dir` 覆盖分支）。
- **模板 metadata 扩展（增量字段）**：在两处写模板入口
  （`core/action_compare.py::create_template_from_video`、`apps/make_template.py`）的 `meta`
  新增 `backend="mediapipe"`、`model_name="pose_landmarker_<variant>"`、`feature_layout="pose33_v3"`、
  `normalizer_version="v3"`、`confidence_kind="visibility"`、`validity_policy=MEDIAPIPE_VALIDITY_POLICY`、
  `valid_conf_thr=DEFAULT_VALID_CONF_THR`（后两者复用 `core.pose_features` 集中式常量）。
  旧模板里的历史 `feature_layout="pose_indices_11_32_xy_rot_scale_norm_v3"` 作为 legacy alias 兼容读取，
  新模板统一写 #4 注册表布局名，便于 #7/#8 后续直接读取同一字段。
- **旧模板兼容加载**：`core/action_compare.py` 新增 `template_meta_defaults()` 与
  `normalize_template_meta()`（`setdefault` 补默认、不覆盖已有键），在
  `compare_video_to_template` / `compare_video_to_dual_templates` 的 `meta = tpl["meta"].item()`
  之后统一补齐，缺字段的旧模板照常加载比对。
- **审查修复**：规范 metadata 字段名，移除新模板写入 `feature_layout_name` 的分叉；双模板比较时
  canonical 化旧/新 `pose33_v3` alias，避免一个旧模板搭配一个新模板时被误判为 layout mismatch。
- **.gitignore**：补充 Issue #6 统一根目录注释块，保留 `templates/`、`outputs/`、
  `models/*.task|*.pt|*.onnx`，并保留 `core/models/*.task`、`analysis/models/*.task`（旧拷贝仍在磁盘）。
- **测试**：新增 `tests/test_artifact_roots.py`（各入口解析到同一 models/templates/outputs root，
  且生产文件不再出现 `parent / "models|templates|outputs"` 字面量）与
  `tests/test_template_metadata.py`（新模板 7 字段齐全；剥离新字段的旧模板仍可加载比对）。

### 验证方法

```powershell
.\.venv\Scripts\python.exe -m py_compile apps\main.py apps\app_ui.py apps\make_template.py apps\match_template.py core\vision_pipeline.py core\action_compare.py core\rule_scoring.py core\pose_features.py core\paths.py analysis\tech_eval.py batch\batch_tech_eval.py batch\batch_export_skeleton.py batch\batch_dual_compare.py
.\.venv\Scripts\python.exe -m pytest tests\test_artifact_roots.py tests\test_template_metadata.py -q   # 13 passed
.\.venv\Scripts\python.exe -m pytest tests\test_pose33_v3_golden.py -q                                  # 16 passed（行为不漂移）
.\.venv\Scripts\python.exe -m pytest tests -q                                                           # 64 passed
```

- `tests/test_pose33_v3_golden.py` 全绿 → metadata 扩展未改动 features / 分数 / golden（行为不变硬门槛）。
- `tests/test_artifact_roots.py` 全绿 → 各入口收口到同一顶层 root，生产代码无残留散落字面量。
- `tests/test_template_metadata.py` 全绿 → 新模板字段齐全、旧模板向后兼容可加载。

---

## 2026-05-31: YOLO 迁移 S1 — valid_mask 契约迁移 + 逐位等价回归（Issue #5）

### 问题描述

把“此点是否可用”的判据从散落在 `analysis/tech_eval.py` 的 `_valid()`/`_lm_vis(...) >= thr`
与 `core/rule_scoring.py` 的 `_valid_frame()`（`lm[idx,3] >= thr` 风格、调用面几十处）统一
收口到集中式 `valid_mask`，为后续 YOLO 缺失点接入做防护。验收硬指标：同一 fixture 下三种调用
方式（旧式不传 mask / 显式传 mask / 改造前 golden）逐位一致；`pose33_v3` golden 不漂移。

### 修改内容

- **集中式 helper**：`core/pose_features.py` 新增 `derive_valid_mask(landmarks, thr=0.5)`，
  返回 `landmarks[...,3] >= thr`（单帧 `(33,)` / 序列 `(T,33)` bool）；新增常量
  `DEFAULT_VALID_CONF_THR=0.5`、`MEDIAPIPE_VALIDITY_POLICY="visibility_thr"`。阈值只存在于此处。
- **rule_scoring.py**：`_valid_frame` 改为读传入的单帧 mask 切片；删除已无用的 `_lm_vis`；
  全部 `_rule_*` 与 `Rule.check_fn` 签名加 `valid_mask`；`score_rules` 新增
  `valid_mask: np.ndarray | None = None`（None 时回退 `derive_valid_mask`）。
  `extract_pose_raw` 产出端在 `meta` 落地 `validity_policy`/`valid_conf_thr`/`valid_mask`。
- **tech_eval.py**：`_valid` 重写为读 mask 切片；新增 `_resolve_mask` 统一回退逻辑；
  `_center_x`/`_frame_dir`/`_foot_edges_x`/`_infer_front_leg_side`/`_compute_segment_center`/
  `_compute_body_com_single` 等单帧 helper 改吃 mask_row；`eval_cog_side`/`eval_cog_front`/
  `eval_cog_com`/`eval_retract_speed_side`/`eval_wrist_angle`/`eval_force_sequence`、
  `_detect_retract_events_side`/`_detect_extension_events`/`_subset_by_intervals`/
  `_eval_cog_side_prefer_punch_windows`、视频级入口 `evaluate_video_assets/detail/full/video`
  与 `_evaluate_from_arrays` 全部新增 `valid_mask`（None 时按 meta 的 `valid_conf_thr` 现场推导）。
  `extract_pose_and_view_scores` 产出端 `meta` 落地 `validity_policy`/`valid_conf_thr`（其 meta 会
  进 JSON 报告，故只落标量，mask 由下游同阈值现场推导，逐位等价）。
- **测试**：新增 `tests/test_valid_mask_migration.py`，验证 `derive_valid_mask` 与旧式阈值逐位一致、
  `score_rules` 与各 `eval_*` 在“不传 mask vs 显式传 mask”下逐位一致、`evaluate_video_full`
  两种调用方式全指标一致。

### 验证方法

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_valid_mask_migration.py tests\test_pose33_v3_golden.py tests\test_layout_shape_param.py tests\test_representative_cycle_layout.py -q
# 51 passed
.\.venv\Scripts\python.exe -m py_compile apps\main.py apps\app_ui.py core\vision_pipeline.py core\action_compare.py batch\batch_tech_eval.py batch\batch_dual_compare.py analysis\tech_eval.py core\rule_scoring.py core\pose_features.py
```

- `tests/test_pose33_v3_golden.py` 全绿 → 迁移后行为 == 改造前 golden（验收①③）。
- `tests/test_valid_mask_migration.py` 全绿 → 旧式不传 mask == 显式传 mask（验收①②）。
- 源码扫描确认 `tech_eval`/`rule_scoring` 评分路径不再出现散落的 `lm[idx,3] >=` / `_lm_vis(...) >=`
  （仅 `_draw_pose33` 渲染阈值与 docstring 保留，非评分路径）。

---

## 2026-05-30: PR #16 审查补强 - 双模板关节误差接入 valid_mask

### 问题描述

审查 PR #16 时发现 `core/action_compare.py` 的双模板关节误差统计仍直接读取
`raw[..., 3]` 并在局部使用 `0.5` 阈值过滤可见点；规则评分入口虽已兼容 `valid_mask`，
但外层调用没有把 `extract_pose_raw` 产出的 mask 传入。这会让 #5 的有效性合约在双模板路径
留下一个绕行点。

### 修改内容

- 在 `core/action_compare.py` 新增 `_valid_mask_from_raw()`，优先使用 `extract_pose_raw` 的
  `meta["valid_mask"]`，仅兼容旧 meta 时才按 `valid_conf_thr`/默认阈值调用 `derive_valid_mask`。
- 双模板规则评分显式把 raw mask 传给 `score_rules`。
- 双模板关节误差统计改为读取 raw mask 的 `source_indices` 切片，不再局部读取
  `raw[..., 3]` 或维护独立可见度阈值。

### 验证方法

- `.\.venv\Scripts\python.exe -m pytest tests\test_valid_mask_migration.py tests\test_pose33_v3_golden.py`
  → 31 passed。
- `.\.venv\Scripts\python.exe -m py_compile .\apps\main.py .\apps\app_ui.py .\core\vision_pipeline.py .\core\pose_features.py .\core\rule_scoring.py .\core\action_compare.py .\analysis\tech_eval.py`
  → 通过。
- `.\.venv\Scripts\python.exe -m pytest tests` → 51 passed。

---

## 2026-05-30: 变更日志归档与重建

### 问题描述

当前 `change.md` 累积过长，需要将既有记录归档并重建当前日志入口。

### 修改内容

- 将旧 `change.md` 重命名为 `change（start~2026.5）.md`。
- 新建当前 `change.md`，作为后续任务记录入口。
- 更新 `AGENTS.md`、`CLAUDE.md` 和 YOLO 迁移文档中的相关说明。

### 验证方法

- 使用 `git status -sb`、`rg -n "change.md|change（start~2026.5）.md"` 确认重命名与引用更新。

---

## 2026-05-30: YOLO 迁移 S0 决策门（Issue #1 + #2）

### 问题描述

推进 YOLO 迁移 M0 决策门。需在动主代码前完成 S0：固定许可结论与实验环境、建立基线样本集（#1），
并用独立 spike 脚本对照 YOLO 与 MediaPipe，产出核心指标降级清单与预注册阈值的 go/no-go 结论（#2）。

### 修改内容

- 配置实验环境：新建 `.venv`（Python 3.13.9），按 `requirements.txt` 安装 mediapipe/opencv/numpy/pillow；
  另装 ultralytics 8.4.57 + torch 2.12.0+cpu（CPU 推理），下载 `models/yolo11n-pose.pt`。
- 新增 `analysis/spike_yolo_baseline.py`：独立 spike 脚本，**不接主链路、不改主代码**。
  跑 YOLO 与 MediaPipe 同样本对照，导出 FPS、漏检率、关键点抖动、跨后端 body_core 位置差、多人帧统计；
  COCO17→BlazePose33 映射严格遵循迁移计划，缺失点一律 `valid=False`，不伪造。
- 新增 `docs/yolo_eval_samples.json`：6 段基线样本（正面/侧面/长视频/学员边界），仅登记元信息，视频本体不入库。
- 新增 `docs/yolo_baseline_report.md`：S0 决策基线报告。含许可结论（可用-限内部研发/评估）、环境表、
  预注册阈值表（建议值，待业务确认）、实测结果、核心指标降级清单、go/no-go 结论（有条件 GO，进入 S1）。
- 新增 `requirements-spike.txt`：记录 spike 专用依赖（ultralytics/torch/torchvision）。
- 更新 `.gitignore`：新增 `models/*.pt`、`models/*.onnx`、`vision_old/`、`_pip_*.log`。

### 关键结论

- 许可：AGPL-3.0 下内部研发/评估可用；闭源/商业部署须采购 Enterprise（决策推到 S6）。
- FPS：本 CPU 上 YOLO11n-pose（25.5fps 均值）比 MediaPipe full（62.8fps 均值）慢约 2.5×，"提速"动机不成立。
- 多人风险已实证：学员样本最多检出 8 人、单视频 274 帧多人 → S2 多人闸门为必做正确性项。
- 核心降级：重心（支撑面/分段质心）+ 发力顺序（蹬地/脚旋转）依赖脚跟脚尖，COCO17 结构性失效，
  YOLO-only 默认排除 full tech_eval，定位收敛为预览/模板匹配/skip-aware partial eval。
- go/no-go：**有条件 GO**，进入 S1（S1 工作无论 YOLO 成败都有价值），但严格限定 YOLO 定位。

### 验证方法

- `.\.venv\Scripts\python.exe -m py_compile .\analysis\spike_yolo_baseline.py` 通过。
- `.\.venv\Scripts\python.exe -m analysis.spike_yolo_baseline --samples docs/yolo_eval_samples.json --yolo-model models/yolo11n-pose.pt --pose-variant full --out outputs/spike` 跑通，
  产出 `outputs/spike/spike_baseline.json` 与 `.csv`（6 段样本全部成功，无报错）。

---

## 2026-05-30: PR #13 审查补强 - spike 原始 keypoints 与 track_id 导出

### 问题描述

审查 PR #13 时发现 Issue #2 清单要求 spike 导出 YOLO keypoints 与 `track_id`，原实现只保留汇总指标，
缺少逐帧原始 keypoints/选中目标 ID，后续 S3 标定与审计难以复核。

### 修改内容

- 更新 `analysis/spike_yolo_baseline.py`：默认写出 `outputs/spike/spike_keypoints.jsonl`，逐帧记录
  MediaPipe / YOLO 的 Pose33-like keypoints、`valid_mask`、YOLO `person_count`、选中实例索引、归一化 bbox 与 `track_id`。
- 新增 spike-only 简易目标 ID 策略（最大框 + IoU/中心距离），仅用于 S0 数据审计；生产多人闸门仍归 S2。
- 更新 `docs/yolo_baseline_report.md`，补充 keypoints JSONL 输出与 `track_id` 策略说明。

### 验证方法

- `e:\CodeProject\vision\.venv\Scripts\python.exe -m py_compile .\analysis\spike_yolo_baseline.py`
- `e:\CodeProject\vision\.venv\Scripts\python.exe -m analysis.spike_yolo_baseline --help`

---

## 2026-05-30: YOLO 迁移 S1 起点（Issue #3：pose33_v3 golden 回归基线，安全网先行）

### 问题描述

S1 后续 Issue（#4 layout shape 参数化 + 周期裁切修复、#5 valid_mask 契约迁移）会改动
`_extract_pose_features()` 缺帧补零、`mirror_pose_features()`、`_select_representative_cycle()`、
双模板关节误差统计、`tech_eval._valid` / `rule_scoring._valid_frame` 等热路径。
`py_compile` 对“行为不变”零保证，必须在动这些代码前先把 pose33_v3 默认路径的现状冻结成
golden，作为重构“行为不变”的唯一硬门槛。

### 修改内容

- **测试框架（方案 A，pytest）落地**：新增 `requirements-dev.txt`（`pytest==8.4.2`）。
  后续所有 Issue 的新增测试统一沿用 pytest 风格，验收命令
  `.\.venv\Scripts\python.exe -m pytest tests\xxx.py`。
- **确定性回放 harness**：新增 `tests/golden_harness.py`，把 `cv2.VideoCapture` 与
  `MediaPipePipeline` 替换为读取已保存 `(T,33,4)` landmark 序列的假对象。所有上层入口
  （`compare_video_to_template` / `compare_video_to_dual_templates` / `evaluate_video_full`
  / `extract_pose_raw` / `score_rules` / `extract_pose_and_view_scores`）都走真实代码路径，
  但输入确定，golden 只反映本仓库代码行为，不受 MediaPipe 模型版本影响。
- **fixture 入库**：`tests/fixtures/pose33_v3/` 下提交小体积确定性数据——
  `front_src_raw.npz` / `side_src_raw.npz` / `student_raw.npz`（裁剪自本地骨架序列，
  约 170KB），以及由其生成的 `front_template.npz` / `side_template.npz` / `golden.json`。
  - `tests/fixtures/_build_raw_fixtures.py`：从本地（gitignored）`outputs/` 裁剪 raw fixture，
    仅在源样本/裁剪范围有意调整时运行。
  - `tests/fixtures/regen_pose33_v3_golden.py`：用已提交 raw fixture 重生成模板与 golden，
    仅在“有意变更行为”且确认正确后运行。
- **golden 回归测试**：新增 `tests/test_pose33_v3_golden.py`（16 个用例），覆盖三类输出：
  1. 单模板 `compare_video_to_template` 分数；
  2. 双模板 `compare_video_to_dual_templates` 的 `combined_percent` + 各视角分（含规则扣分
     明细、关节误差统计，关节顺序敏感以冻结 mirror 的 L/R 交换）；
  3. `tech_eval` 各指标 `status` + 关键 `detail`。
  数值断言用 `pytest.approx(abs=1e-4)`，状态/分类/整数（percent、rule_score、segment、
  primary_cause 等）用精确相等。
- **.gitignore**：补 `core/models/*.task`，避免误提交本地模型权重。

### 验证方法

- `.\.venv\Scripts\python.exe -m pytest tests\test_pose33_v3_golden.py` → 16 passed（未改动代码全绿）。
- 安全网有效性自检：临时在 `mirror_pose_features()` 注入 `+0.001` 扰动 → `test_dual_joint_errors[side]`
  如期失败；还原后重新全绿，证明 golden 能捕获热路径漂移。
- `git check-ignore` 确认 fixtures/golden/模板均不被忽略、会随提交入库；`core/models/*.task` 已被忽略。

---

## 2026-05-30: YOLO 迁移 S1（Issue #4：FeatureLayoutSpec 注册表 + layout shape 参数化 + 周期裁切修复）

### 问题描述

S1 热路径里把 `(22, 2)` / 22 点配对硬编码散落在多处：`_extract_pose_features()` 缺帧补零、
`mirror_pose_features()` 的 L/R 配对、双模板关节误差统计的关节名表。更危险的是
`core/action_compare.py` 的 `_select_representative_cycle()` 守卫写死
`if features.shape[1:] != (22, 2): return features`——任意非 22 点布局会**静默跳过周期裁切**，
DTW query 退化成整段模板，不报错、最难查。本 Issue 把这些 shape 魔法值收敛到显式 layout 注册，
**只做参数化、默认仍走 22 点路径**，不引入 `body_core_v1`（下移 #8）。

### 修改内容

- **新增 `core/feature_layout.py`**：`FeatureLayoutSpec` dataclass
  （`name`/`source_indices`/`shape`/`mirror_pairs`/`joint_names`/`default_baseline`）+ 注册表
  （`register_layout`/`get_layout`/`has_layout`/`resolve_layout_by_shape`/`is_valid_feature_shape`）。
  - **本期只注册生产用 `pose33_v3`**（BlazePose 11..32 → 22 点，mirror_pairs 即相邻对
    (0,1)…(20,21)，joint_names 与原 `joint_names_11_32` 完全一致，baseline=2.0）。
  - **不注册 `body_core_v1`**（留到 #8 真有消费者时），**不引入 `required_landmarks`** 字段
    （S4 才消费，避免提前建模）。
- **`core/pose_features.py::mirror_pose_features()`**：新增可选 `layout` 形参，按 layout 的
  `mirror_pairs` 做 L/R 互换，去掉写死的 `range(0, 22, 2)`。未传 layout 时按单帧 shape 反查
  唯一已注册布局（`(22,2)` 即命中 `pose33_v3`，行为不变）；无法解析时报清晰错误，不静默按 22 点处理。
- **`core/action_compare.py::_extract_pose_features()`**：新增 `layout=POSE33_V3` 形参，
  缺帧补零（单线程 / 多线程 / `feat_arr` 预分配）全部按 `layout.shape` 生成，去掉三处
  `np.zeros((22, 2))` 与一处 `np.zeros((total, 22, 2))` 字面量；单线程回退递归透传 layout。
- **`_select_representative_cycle()` 守卫泛化**：改为
  `if features.ndim != 3 or not is_valid_feature_shape(features.shape[1:]): return features`，
  按 `(J, 2)` 合法布局（`J >= 4`）判定，使任意 `(T, J, 2)` 输入都能正常裁切，修复静默退化 bug。
- **双模板关节误差统计**：删除写死的 `joint_names_11_32` 列表与 `range(22)`/`raw[..., 11:33, 3]`，
  改从 `POSE33_V3` 取 `joint_names`/`source_indices`/`num_joints`，行为不变。
- **layout mismatch 显式校验**：单模板 / 双模板进入 DTW 前先核对单帧 feature shape，shape 不一致时
  抛出包含模板路径、视频路径、metadata `feature_layout` 与实际 shape 的 `ValueError`，避免不同 layout
  静默比对或落入低层 numpy 广播异常。
- **新增测试**：
  - `tests/test_layout_shape_param.py`：断言注册表范围（仅 pose33_v3、无 body_core_v1、无
    required_landmarks）、mirror 与旧实现逐位等价、缺帧补零按 layout shape、无法解析 shape 报错、
    不同 layout/shape 比对会清晰报错，并用 AST 静态扫描确认 `action_compare`/`pose_features` 热路径
    不再出现 `(22,2)` 字面量或 `range(...,22,...)` 魔法值（注册定义里的 `(22,2)` 合法）。
  - `tests/test_representative_cycle_layout.py`：用 test-only `(T,12,2)` 强周期输入验证周期裁切
    不再静默整段返回、能正常裁短；并覆盖 22 点、短序列、非法 shape、关节数过少等边界。

### 验证方法

- `.\.venv\Scripts\python.exe -m py_compile`（13 个目标文件 + `core/feature_layout.py`）→ 全通过。
- `.\.venv\Scripts\python.exe -m pytest tests\test_pose33_v3_golden.py` → 16 passed（**默认行为不变**，硬门槛）。
- `.\.venv\Scripts\python.exe -m pytest tests\` → 34 passed（含两个新增测试文件）。
- 全程对照 Issue #4 验收标准逐条核对：golden 全绿、layout shape 参数化、周期裁切修复、py_compile 通过、change.md 已记录。
