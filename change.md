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
