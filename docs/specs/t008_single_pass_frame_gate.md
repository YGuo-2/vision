# T-008 单次抽帧复用二次审批包

> 生成日期：2026-06-14
> 当前状态：仅产出门禁与验证设计，不实施业务代码
> 独立批准短语：`批准 T-008 高风险评分变更，启动执行`

---

## 1. 门禁结论

`T-008` 评估的优化项来自 `docs/performance_optimization_inventory.md` 的 B2 / C1 / C4 / C5：通过一次性提取同一视频的 raw Pose33 / valid_mask 或 body_core 特征，复用给规则评分、关节误差、批处理导出和 body_core 前后模板匹配，减少同一视频 2-5 次重复推理。

本包结论：

- 当前首次 `批准规范，启动执行` 只授权本文档，不授权修改 `core/action_compare.py`、`core/rule_scoring.py`、`batch/batch_dual_compare.py` 或 `core/body_core_compare.py` 的单次抽帧实现。
- 单次抽帧收益明确，但它触碰 MediaPipe VIDEO-mode 时序态、规则评分、误差分析和 batch 输出，属于评分语义高风险项。
- 若后续未收到独立批准短语 `批准 T-008 高风险评分变更，启动执行`，应将 T-008 停在人工门禁，不继续进入依赖它的 `T-009`。

---

## 2. 当前重复推理边界

| 范围 | 当前行为 | 可复用对象 | 风险点 |
|:---|:---|:---|:---|
| pose33 双模板主匹配 | `compare_video_to_dual_templates()` 先用 `_extract_pose_features()` 对学员视频提取 normalized features 和 view scores | 无 raw Pose33；只够 DTW 和视角切分 | 不能直接从 normalized features 反推规则评分所需的 33 点与 valid_mask |
| 规则评分 | `enable_rules=True` 时 front / side 各调用一次 `extract_pose_raw()`，再调用 `score_rules()` | 全视频 raw Pose33 + valid_mask 的切片 | VIDEO-mode 必须与当前从帧 0 推理到 `end_frame` 的状态一致 |
| 关节误差分析 | `enable_error_analysis=True` 时对 active segment 再调用 `extract_pose_raw()` | 同一全视频 raw Pose33 + valid_mask 的 active segment 切片 | path 索引、mirror 后左右关节名、valid_mask 过滤必须逐项等价 |
| batch raw 导出 | `--export_raw` 后按 JSONL 中 front / side segment 再调用 `extract_pose_raw()` | 已提取 raw 的 front / side 切片 | NPZ metadata 的 `start_frame` / `end_frame` / `segment_kind` 必须保持兼容 |
| body_core MediaPipe | `_extract_body_core_mediapipe()` 通过 `extract_pose_raw()` 再归一化为 body_core；front / side 模板匹配会重复抽同一视频 | body_core feature sequence 或 raw Pose33 sequence | body_core `valid_mask`、gap-fill、`calibration_status=unvalidated` 不得漂移 |
| body_core YOLO | `_extract_body_core_yolo()` 依赖 `extract_yolo_landmark_series()` 与 YOLO meta | body_core feature sequence | 必须保留 `score_authorized=False`、`display_scope=internal`、多人闸门和模型元数据 |

特别说明：`rule_scoring.extract_pose_raw(video, start_frame=s, end_frame=e)` 当前虽然只返回 `[s, e]`，但推理循环从视频第 0 帧跑到 `e`，不是直接 seek 到 `s` 后冷启动。因此，最保守的单次复用方案应复用“从第 0 帧开始的完整 VIDEO-mode 推理序列”，不能把它替换为“seek 到片段起点 + 短 warm-up”的新语义。后者属于另一个高风险评分变更。

---

## 3. 后续允许的最小实现形态

独立批准后，建议只允许以下窄范围实现：

1. 新增内部 raw 序列载体，例如 `Pose33RawSeries`，包含 `landmarks[T,33,4]`、`valid_mask[T,33]`、`fps`、`frame_count`、`width`、`height`、`pose_variant`、`validity_policy`、`valid_conf_thr`。
2. 新增只读切片 helper，按当前 `extract_pose_raw()` metadata 形态生成 segment raw 与 segment meta。
3. `compare_video_to_dual_templates()` 在一次全视频 raw 提取后，仅把 raw 切片传给规则评分、关节误差分析和 batch raw 导出；DTW 主匹配输出、视角切分和代表周期选择不改。
4. body_core 优先支持“同一视频、同一 backend、同一 pose_variant”的预抽 feature 复用；不得把 YOLO meta、多人闸门、授权状态或 calibration 状态丢失。
5. 默认正式评分、CLI、Tkinter、full tech_eval 仍保持 MediaPipe CPU VIDEO-mode 默认链路，不引入 GPU 或 YOLO 默认切换。

不建议在同一审批中合并以下内容：

- seek 到片段起点后只用短 warm-up 重建 VIDEO-mode 状态。
- 默认启用 DTW 带宽、代表周期算法替换或 golden 重生。
- 修改规则阈值、valid_mask 判据、YOLO 授权元数据或 body_core baseline。

---

## 4. 真实 MediaPipe VIDEO-mode 验证矩阵

独立批准后的实现必须新增真实 MediaPipe VIDEO-mode 验证，而不只依赖 fixture replay。建议矩阵如下：

| ID | 场景 | 输入要求 | 对比对象 | 必须保持 |
|:---|:---|:---|:---|:---|
| MP-01 | 双模板 + 规则评分 | 至少 1 个真实学员视频，`pose_variant=full`，`enable_rules=True` | 旧路径 front / side 各自 `extract_pose_raw()` vs 新路径全视频 raw 切片 | front / side rule score、deduction、violation `rule_id`、`state`、`skip_reason`、`valid_frames`、`total_frames` 精确一致；ratio 容差 `1e-6` |
| MP-02 | 双模板 + 关节误差 | 同一真实视频，`enable_error_analysis=True` | 旧路径 active segment 重抽 vs 新路径 raw 切片 | front / side joint 列表顺序、`valid_frames` 精确一致；`mean_dist` / `p90_dist` / `max_dist` 容差 `1e-6` |
| MP-03 | 边界片段 | front 或 side segment 为空、很短、靠近视频开头或结尾的视频 | 旧路径回退整段 / shrink 后 segment vs 新路径切片 | segment 起止、combined_percent、front_score、side_score 不漂移 |
| MP-04 | low-confidence / no-person | 含无人帧、遮挡或低 visibility 的真实视频 | 旧路径 `derive_valid_mask()` vs 新路径缓存 valid_mask | 缺失点不得伪造成有效点；skipped / insufficient_valid_frames 判定一致 |
| MP-05 | batch pose33 | `batch_dual_compare.py --rules --error-analysis --export_raw --workers 1` 与 `--workers 2` | 旧路径 CSV/JSONL/NPZ vs 新路径输出 | CSV/JSONL 排序稳定；raw NPZ landmarks、valid_mask、segment metadata 兼容；并发不共享 pipeline |
| MP-06 | body_core MediaPipe | 同一学生视频分别匹配 front / side body_core 模板 | 旧路径两次抽取 vs 新路径一次 feature/raw 复用 | 分数、start/end、avg_cost、valid_frame_ratio、`calibration_status=unvalidated` 不漂移 |
| MP-07 | body_core YOLO 调试路径 | YOLO runtime/model 可用时的 body_core batch | 旧路径两次 YOLO series vs 新路径一次 feature 复用 | `score_authorized=False`、`display_scope=internal`、model_name、valid_conf_thr、多人闸门字段不漂移 |

建议执行命令模板：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_t008_single_pass_reuse.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py tests/test_rule_availability.py tests/test_tech_eval_contract.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_body_core_layout.py tests/test_batch_backend_args.py tests/test_yolo_backend_contract.py -q
.\.venv\Scripts\python.exe analysis\offline_matching_profile.py --fixture-smoke --out outputs\perf_baseline\t008_after
```

验收原则：任一真实 MediaPipe VIDEO-mode case 出现评分、segment、规则状态或 valid_mask 漂移，应停止实现并回到独立 Bugfix / reapproval，而不是更新 golden。

---

## 5. Fixture replay 验证矩阵

fixture replay 负责证明索引、切片、metadata 和数组复用没有工程错误；它不能单独证明真实模型时序态安全。

| ID | 场景 | 现有基础 | 必须新增 / 保持 |
|:---|:---|:---|:---|
| FR-01 | pose33_v3 golden 双模板 | `tests/golden_harness.py` + `tests/test_pose33_v3_golden.py` | `combined_percent`、front/side score、segment、rule score、rule violations、joint errors 与 `golden.json` 精确/容差一致 |
| FR-02 | raw series 切片等价 | `student_raw.npz`、`front_src_raw.npz`、`side_src_raw.npz` | 新 helper 对 `[start_frame, end_frame]` 的 landmarks / valid_mask 与现有 `extract_pose_raw()` replay 输出逐元素一致 |
| FR-03 | valid_mask 迁移 | `tests/test_valid_mask_migration.py` | legacy 与 explicit valid_mask 调用方式仍等价；低 confidence 点不进入有效帧 |
| FR-04 | body_core MediaPipe fixture | `tests/test_body_core_layout.py::test_mediapipe_can_generate_body_core_v1_template` | 预抽 raw / feature 复用后 shape、layout、backend、calibration_status 不漂移 |
| FR-05 | batch 输出排序 | `tests/test_batch_backend_args.py` | 并发完成乱序时 CSV / JSONL / manifest 仍按输入顺序输出 |
| FR-06 | 回滚保护 | golden fixtures | 不允许运行 `tests/fixtures/regen_pose33_v3_golden.py` 作为通过手段；若 golden diff 出现，必须解释并重新审批 |

建议新增测试命名：

```text
tests/test_t008_single_pass_reuse.py
```

该测试文件应优先覆盖 fixture replay 下的精确等价，再用真实 MediaPipe smoke 覆盖 VIDEO-mode 风险。

---

## 6. 回滚方案

若独立批准后实施出现任一验收失败：

1. 立即关闭或移除单次抽帧复用入口，恢复 `compare_video_to_dual_templates()`、`extract_pose_raw()`、`match_body_core_template()` 的当前重复推理路径。
2. 不重生 `tests/fixtures/pose33_v3/golden.json`，除非另开评分语义变更审批。
3. 保留 T-001 到 T-007 已完成的低风险优化；T-008 回滚应只触碰本任务新增的 raw 序列载体、切片 helper、调用点和测试。
4. 清理 `outputs/perf_baseline/t008_after` 等采证输出，不提交 `outputs/`、模型、bundle 或 sidecar 生成产物。
5. 用 `spec_progress.py block docs\specs T-008 --reason "<失败证据>"` 或独立 Bugfix 规范记录失败原因，等待人工决策。

---

## 7. 二次审批建议

建议当前不继续实现单次抽帧复用。下一步有两种安全路径：

| 路径 | 适用条件 | 处理方式 |
|:---|:---|:---|
| 等待二次审批 | 用户接受上方验证矩阵与回滚方案 | 用户明确回复 `批准 T-008 高风险评分变更，启动执行` 后，再运行 sync-check / 重新冻结或独立 Spce 规范 |
| 放弃本轮实现 | 用户不愿承担评分语义风险或暂不需要该收益 | 用 `spec_progress.py skip` 记录人工放弃，后续 `T-009` 是否继续需重新确认依赖关系 |

本包推荐：将当前 `T-008` 停在人工门禁，等待独立批准短语：

```text
批准 T-008 高风险评分变更，启动执行
```

在该短语出现前，不应修改单次抽帧相关业务代码，也不应继续执行依赖 `T-008` 的传输优化任务。
