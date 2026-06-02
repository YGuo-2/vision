# 离线 DTW / 序列提取性能 profile 与优化决策（Issue #44）

日期：2026-06-02

## 结论

本轮只做 profile 和决策，不修改 `subsequence_dtw`、baseline、阈值或评分输出。

实测结论：

- 对真实本地视频 `学员样本/1.mp4` 前 90 帧，`compare_video_to_dual_templates` 拆段 profile 会按模板 metadata 选择生产同款 normalizer；本地 `templates/standard_front_full.npz` / `standard_side_full.npz` 为旧 v2 模板，因此该记录使用 `normalizer_version=v2`。该记录 stage 表显示 MediaPipe Pose 推理 86.98%、视频读取 11.16%、特征归一化 1.34%、view score 0.15%；双视角 DTW / fallback DTW 合计约 0.27%。
- 对 deterministic fixture，`pose33_v3` staged profile 与生产函数 `compare_video_to_dual_templates` 的 `combined_percent` 都为 38，说明 profile 拆段没有改变结果。
- 对 deterministic `body_core_v1` fixture，staged profile 与生产函数 `match_body_core_template` 的 score 都为 `0.8383146162`，说明 body_core profile 拆段没有改变结果。
- fixture 中 `body_core_v1` 单次 `subsequence_dtw` 占 staged 记录约 50%，但绝对耗时约 11ms；在真实视频 profile 中，模型推理和视频 I/O 压倒 DTW。

Go / no-go：

- **No-change**：本 PR 不优化 DTW，不引入 FastDTW / Numba / window constraint，不改缓存策略。
- **No-go**：不得在本 issue 内改动 `subsequence_dtw`、DTW baseline、匹配阈值、评分输出或 YOLO 授权状态。
- **Candidate**：若后续要提升 batch/offline 吞吐，优先另开 raw/feature cache issue，而不是近似 DTW。缓存不改变评分算法，收益也更贴近真实视频瓶颈。

## 工具与产物

新增脚本：`analysis/offline_matching_profile.py`

输出产物：

- `outputs/offline_matching_profile_issue44/offline_matching_profile.json`
- `outputs/offline_matching_profile_issue44/offline_matching_profile.csv`

命令：

```powershell
.\.venv\Scripts\python.exe -m analysis.offline_matching_profile `
  --fixture-smoke `
  --front-template templates\standard_front_full.npz `
  --side-template templates\standard_side_full.npz `
  --video "学员样本\1.mp4" `
  --pose-variant full `
  --limit-frames 90 `
  --out outputs/offline_matching_profile_issue44
```

说明：

- `--fixture-smoke` 使用 `tests/fixtures/pose33_v3` 与 golden harness，不依赖 MediaPipe 模型和真实视频。
- 同时传入 `--front-template/--side-template/--video` 时，会额外对本地真实视频跑 90 帧 staged profile。
- 脚本位于 `analysis/`，不会接入默认 CLI/UI 或生产评分路径。

## Profile 汇总

来源：`outputs/offline_matching_profile_issue44/offline_matching_profile.json`

| 指标 | 数值 |
| --- | ---: |
| records | 5 |
| 覆盖目标 | `compare_video_to_dual_templates` / `match_body_core_template` |
| total staged seconds | 1.733576 |
| sequence seconds | 1.638641 |
| sequence percent | 94.52% |
| DTW seconds | 0.019491 |
| DTW percent | 1.12% |
| MediaPipe model inference seconds | 1.389640 |
| video I/O seconds | 0.178350 |

## 关键记录

### 1. 真实视频双模板 staged profile（本地模板 v2 normalizer）

输入：

- template front：`templates/standard_front_full.npz`
- template side：`templates/standard_side_full.npz`
- video：`学员样本/1.mp4`
- limit：90 frames
- normalizer：`v2`（由模板 metadata 解析，与生产入口一致）

输出：

| stage | seconds | percent | count |
| --- | ---: | ---: | ---: |
| `model_inference_mediapipe_pose` | 1.389640 | 86.98% | 90 |
| `video_io_read` | 0.178350 | 11.16% | 90 |
| `feature_normalization_pose33` | 0.021366 | 1.34% | 90 |
| `side_multi_subsequence_dtw` | 0.002682 | 0.17% | 1 |
| `front_fallback_subsequence_dtw` | 0.001646 | 0.10% | 1 |
| `front_multi_subsequence_dtw` | 0.000031 | 0.00% | 1 |

该记录说明：真实视频离线匹配的主要耗时在序列提取，尤其是 MediaPipe 推理；当前样本不支持优先改 DTW。

### 2. deterministic `pose33_v3` fixture

| record | result |
| --- | --- |
| production `compare_video_to_dual_templates` | `combined_percent=38` |
| staged `compare_video_to_dual_templates` | `combined_percent=38` |

staged 记录中的主要耗时：

| stage | seconds | percent |
| --- | ---: | ---: |
| `feature_normalization_pose33` | 0.033412 | 74.66% |
| `front_multi_subsequence_dtw` | 0.003079 | 6.88% |
| `side_multi_subsequence_dtw` | 0.002134 | 4.77% |

fixture 不包含模型推理和视频读取，因此它主要用于证明 profile 拆段逻辑与生产输出一致。

### 3. deterministic `body_core_v1` fixture

| record | result |
| --- | --- |
| production `match_body_core_template` | `score=0.8383146162` |
| staged `match_body_core_template` | `score=0.8383146162` |

staged 记录：

| stage | seconds | percent |
| --- | ---: | ---: |
| `subsequence_dtw_body_core` | 0.009919 | 51.44% |
| `feature_normalization_body_core` | 0.008807 | 45.67% |
| `template_load_body_core` | 0.000523 | 2.71% |

解释：body_core fixture 是无模型、单次匹配的小样本，DTW 占比高但绝对耗时低。该结果不足以支持在本 issue 修改 exact DTW。

## 决策表

| 方案 | 决策 | 原因 | 必要守卫 |
| --- | --- | --- | --- |
| FastDTW | defer | 当前 profile 中 DTW 不是主瓶颈；近似算法可能改变 start/end 和分数。 | 必须另开实现 issue；要求 `pose33_v3` golden 与 body_core fixture 分数逐值一致，除非明确接受评分变化。 |
| Numba exact DTW | defer | 精确加速比近似更安全，但引入依赖 / 打包复杂度；当前 DTW 占比不足。 | 另开 issue；可选依赖策略；exact score/path 回归。 |
| DTW window constraint | defer | window 会改变 subsequence 搜索空间，可能改变用户可见分数和匹配区间。 | 另开 issue；逐 fixture 分数与区间一致，或单独产品决策允许评分变化。 |
| Raw / feature cache | candidate separate issue | 真实视频 profile 中序列提取占比极高，缓存能复用推理/归一化结果且不改评分算法。 | cache key 必须包含 backend、model、pose_variant、feature_layout、normalizer、valid_conf_thr、源文件路径/mtime/size。 |
| Template query cache | low priority | 模板 load / representative query selection 占比很低。 | 未来 batch profile 证明重复 query selection 成本后，可并入 feature cache。 |

## No-change 原因

本 PR 不修改核心算法，原因如下：

1. 真实视频 profile 中 DTW / fallback DTW 合计约 0.27%，改 DTW 对离线总耗时收益很小。
2. `subsequence_dtw` 与 `_multi_subsequence_matches` 会影响匹配区间、平均 cost、分数和误差分析路径，属于高风险评分面。
3. FastDTW / window constraint 都可能引入近似误差；Numba exact DTW 虽相对安全，但当前收益证据不足。
4. raw/feature cache 的收益更贴近真实瓶颈，并且可以在不改评分语义的前提下单独设计。

## 后续建议

建议新开独立 issue：`P5a raw/feature cache for offline batch`。

建议范围：

- 对 `pose33_v3` MediaPipe raw landmarks 与 normalized features 做只读缓存。
- 对 `body_core_v1` features 做显式 opt-in cache。
- cache key 包含源视频路径、mtime、size、backend、model 名、pose variant、feature layout、normalizer version、validity policy、valid conf threshold。
- 验收要求：
  - `tests/test_pose33_v3_golden.py` 分数逐值不变；
  - `tests/test_body_core_layout.py` / `tests/test_valid_mask_migration.py` 全绿；
  - 缓存命中与未命中的 `avg_cost`、score、start/end 完全一致；
  - 缓存文件继续落 `outputs/` 或显式 cache root，不入库。
