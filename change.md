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
  - 新增 `tests/test_body_core_layout.py`（14 用例）：layout shape/mirror pairs/joint names、
    共享 normalizer 接受 MediaPipe landmark 与 YOLO `(33,4)` 行、layout mismatch 报错、
    **YOLO body_core_v1 离线闭环生成→匹配同一视频产出分数且标 unvalidated**、YOLO 拒绝
    pose33_v3 模板、MediaPipe 也能生成 body_core_v1 模板。全程用 fake adapter + golden harness，
    无网络、不下载模型、不读真实视频。
  - 更新 `tests/test_layout_shape_param.py`：`body_core_v1` 现已注册（断言改为 `has_layout` 为真）；
    无法解析 shape 的用例从 `(12,2)` 改为仍未注册的 `(15,2)`，保留原意。

### 验证方法

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_body_core_layout.py -q          # 14 passed
.\.venv\Scripts\python.exe -m pytest tests\test_pose33_v3_golden.py -q          # 16 passed（MediaPipe 默认不漂移）
.\.venv\Scripts\python.exe -m pytest tests\test_yolo_landmark_mapping.py tests\test_yolo_backend_contract.py -q  # YOLO 契约不变
.\.venv\Scripts\python.exe -m pytest tests -q                                   # 102 passed
.\.venv\Scripts\python.exe -m py_compile core\feature_layout.py core\pose_features.py core\yolo_adapter.py core\body_core_compare.py apps\make_template.py apps\match_template.py  # exit 0
```

- `tests/test_pose33_v3_golden.py` 全绿 → MediaPipe 旧 `pose33_v3` 路径行为不漂移（行为不变硬门槛）。
- `tests/test_body_core_layout.py` 全绿 → 布局正确、闭环可生成可匹配、分数标 unvalidated、layout mismatch 报错。
- 全量 102 passed（此前 88 + 本期 14 新增，含 1 处 S1 测试随注册状态变化的适配）→ 无回归。

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
