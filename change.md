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
