## 2026-07-13: [fix] 综合分改直接平均 + 低鞭腿去几何 + 低鞭腿夹角评分（试验后弃用）

### 问题描述

1. 同一人打同一套模板考出 38~60 分且波动大。综合分原口径 `combined=0.4×正面池均值+0.6×侧面池均值` 多套了一层池权重，用户要求改为**所有动作子分直接平均**。
2. 低鞭腿几何分（原「站立腿大腿高度三角峰」）实测异常：真实考试录像里所有踢腿动作张开角都在 95~127°（踢到水平以上），低鞭腿 DTW 窗口峰值帧算出 104°，按「踢过头」判 0，把该动作子分从 0.77(纯DTW) 拖到 0.38。根因是这次录像低/高鞭高度没拉开 + 高度基准（站立腿膝/髋）定位不稳。

### 修改内容

- **`apps/recording_postprocess.py`**：
  - `_run_auto_compare` 综合分改为 `combined = mean(所有动作子分)`（正+侧，含踢腿几何混合分），不再套 `w_front/w_side`。删除 `w_front/w_side` 参数。`front_score`/`side_score` 仍算各池均值供成绩表正/侧列。
  - `_KICK_KINDS` 移除「低鞭腿」——低鞭腿现自动只走纯 DTW（`name not in _KICK_KINDS` 则跳过几何）。高鞭腿/侧踹腿/正蹬腿仍几何+DTW 各半。
- **`core/kick_quality.py`**：低鞭腿 `_score_low_whip` 从「高度三角峰」重写为「两腿张开夹角梯形」（保留在库，`_KICK_KINDS` 不再引用，供后续需要时启用）。实测三张标准低鞭腿摆拍夹角 = 64/73/84°（画骨架量出），定 64~84° 满分平台、>90° 归零、<40° 归零。夹角用真实像素反归一化（`width`/`height` 来自 raw meta）抵消横竖画幅畸变，顶点用髋中点、不依赖踢腿/站立腿判定（比高度法稳）。`score_kick_quality` 新增 `width`/`height` 参数。旋钮 `LOW_WHIP_FULL_MIN/MAX=64/84`、`LOW_WHIP_ZERO_HIGH/LOW=90/40`。

### 验证方法

- `core/kick_quality.py` 自检：低鞭腿夹角 64/73/84°→1.0、87°→~0.5、≥90°/40°→0；高鞭/侧踹/正蹬高度映射不变。self-check OK。
- 画骨架核对：三张手机摆拍低鞭腿 MediaPipe heavy 检测准确，夹角 64/73/84°；record_024815 侧面视频低鞭腿 DTW 窗口峰值帧（绝对帧#403）实为踢到水平的动作（104°），确认「这次踢太高」非算法误判。
- `pytest tests/test_recording_postprocess.py -q`：51 passed。

---

## 2026-07-13: [fix] 考试录像自动裁剪把 34.8s 砍成 1.9s，评分崩坏（38 分事故根因）

### 问题描述

同一人打同一套散打模板考 3 遍，8 个动作分数在 25~80 之间乱蹦（本该都在 0.8 上下），综合分 38~60 不可信。只读排查确诊：原始考试录像 side.avi = 1044 帧 / 34.8s（完整 8 动作），经 `core/exam_clip.py` 的 `estimate_action_range` 裁剪后 side_exam.mp4 只剩 56 帧 / 1.9s——95% 的帧被当「走位/静止」删掉。8 个模板（46~149 帧）被硬塞进 56 帧里跑 subsequence DTW，多数模板比视频还长，窗口互相重叠乱锁，分数随机。

根因是 `estimate_action_range` 优先走 `find_active_range`，后者只取**最长单个连续活跃段**，对「连续打 8 个动作」的录像只保留能量最高的一小段。隔离实验：用裁剪前完整 34.8s 视频跑同样 7 个侧面模板，DTW 全部落在 0.75~0.83、窗口按动作时序干净铺开不互抢——证明评分方法/归一化/DTW 都没问题，唯一问题就是裁剪。（与上一条「建模板」防线是**不同链路**：那条防 `create_template_from_video`，本条防考试录像 `exam_clip`。）

### 修改内容

- **`core/exam_clip.py`**：`estimate_action_range` 加 `smart_crop: bool = False`（考试生产默认）与 `tail_quiet_pct: float = 40.0`。
  - `smart_crop=False`（考试默认）：进场已由 `presence_gate` 挡干净，头部只固定掐 `trim_head_s`（0.5s）；**中段一律不裁**（整段评，隔离实验结论）；尾部**不按时间硬掐、按能量从末尾回扫到最后一次超阈动作**，末动作后留 0.3s 余量。正常离场留下的 ~2s 空场能量低会被切掉；`force_finish` 强停时尾部仍是动作则一帧不切。区间过短（<max(15,0.5fps)）一律回退整段，绝不 raise。
  - `smart_crop=True`：完整保留旧的 `find_active_range` 活跃段 + 时间裁剪逻辑，供 `estimate_action_range_from_feature_seq`（sim/单测）显式使用。`find_active_range` 本体一字不动（pose33_v3 golden 不漂）。
  - 新增 `_smooth_1d`（移动平均，防单帧能量毛刺）。
- **`tests/test_exam_clip.py`**：旧的 `estimate_action_range` 时间裁剪测试显式传 `smart_crop=True`；新增考试默认路径 3 例（无 energy 保留整尾、尾部空场被回扫切掉、force_finish 末动作不被吞）。

### 校准旋钮（默认值，现场可调）

- `trim_head_s=0.5`（掐头固定）
- `tail_quiet_pct=40.0`（尾部回扫安静阈分位；越低越保守越少切尾）
- 末动作后余量 `0.3s`（硬编码）
- `smart_crop=False`（生产默认；sim/test 显式开旧逻辑）

### 验证方法

- 真实 34.8s / 1044 帧 side.avi + front.avi 跑 `prepare_exam_pair`（生产默认）：裁后 front_frames=1004 / trim=[15,1019] / **保留 96.2%**（不再砍到 56）；裁后 side_exam 跑 7 个侧面模板 DTW 全部 0.759~0.833（对齐隔离实验 0.75~0.83），窗口按动作时序铺开不互抢。
- `pytest tests/test_exam_clip.py tests/test_recording_postprocess.py tests/test_exam_session.py tests/test_presence_gate.py tests/test_pose33_v3_golden.py -q`：88 passed（golden 不漂）。

---

## 2026-07-13: [fix] 长视频生成模板时拦截异常短自动裁剪

### 问题描述

`find_active_range` 的既有语义是从运动能量高于 P70 的区间中只保留最长连续段。单动作视频可借此提取一次代表动作，但 80.73s 的整套动作视频包含多个活动组，默认结果仅为 1759..1825（67 帧 / 2.23s / 2.8%），会静默生成语义错误的模板。当前评分链和多模板池按“每个动作一个模板”工作，不能把整套长视频直接塞入单个 DTW 模板。

### 修改内容

- **`core/action_compare.py`**：新增 `TemplateAutoCropAnalysis`、`analyze_template_auto_crop` 和 `TemplateAutoCropReviewRequired`。保持 `find_active_range` 与原自动主段完全不变，仅增加模板专用诊断：按 0.3s 平滑、0.15s 最短活动、2s 间隔合并、0.5s 候选 padding 形成活动组。仅当输入不少于 30s、存在多个活动组且自动主段不超过 `max(5s, 原片10%)` 时阻止无边界生成，并返回输入/保留时长、比例和候选帧区间。显式 `start/end` 继续优先并可通过人工确认。
- 新模板 metadata 增加 `crop_selection`、`selected_retained_ratio`、`template_scope=single_action`、`auto_crop_strategy`、`auto_activity_group_count/groups`、`auto_review_required`，保留既有 `auto_start_frame/auto_end_frame`。
- **`apps/make_template.py`**：CLI 复用同一诊断和保护；异常时以清晰消息退出，显式 `--start/--end` 可继续；metadata 与核心入口对齐。
- **`apps/app_ui.py`**：Tkinter 模板生成完成后展示实际帧区间、时长和保留比例，并在原始结果中带回 template meta；长视频异常直接显示人工确认说明。
- **`frontend/src/App.vue`**：Vue/Tauri 从 bridge 已返回的 `templateMeta` 展示实际帧区间、时长和保留比例；异步 `job.failed` 沿既有路径展示长视频人工确认错误。
- **`tests/test_template_auto_crop.py`**：覆盖 120s 多活动视频拦截、短单动作旧行为、20s 双活动组不误拦、无显式边界不落错误模板、显式边界覆盖与诊断 metadata。
- 未修改共享 `find_active_range`，因此考试裁剪、学员活跃段、body_core 和既有评分行为不变。

### 验证方法

- `pytest tests/test_template_auto_crop.py tests/test_template_metadata.py tests/test_pose33_v3_golden.py tests/test_ui_backend_analysis.py -q`：39 passed。
- `pytest tests/test_template_auto_crop.py tests/test_template_metadata.py tests/test_pose33_v3_golden.py tests/test_batch_backend_args.py -q`：47 passed。
- `pytest tests/test_recording_postprocess.py -q`：51 passed。
- `npm --prefix frontend run build` 与 `npm --prefix frontend run test`：通过。
- `py_compile core/action_compare.py apps/make_template.py apps/app_ui.py`：通过；`git diff --check` 无空白错误（仅 Windows 行尾提示）。
- 真实缓存 `outputs/_tpl_energy_cache.npz`：80.73s / 自动 2.23s / 2.8% / 9 个活动组，`review=True`，正确阻止静默生成。
- `E:\测试视频\20260711` 的 8 个 1280x720@30fps 连续视频以 heavy 实测：输入 17.53..23.33s、自动主段 1.20..2.40s、活动组 1..2，全部 `review=False`，未误拦单动作连续素材。
- 扩展 Tkinter 基线 `pytest tests/test_app_ui_lifecycle.py tests/test_app_controls.py tests/test_app_ui_dual_camera.py -q` 为 135 passed / 18 failed；失败均位于开始本任务前已有的多模板池、录制控件和双摄 pipeline 未提交改动（测试桩缺 `_current_template_lists` / `_sync_record_stop_enabled` 等），与本次模板生成路径无关，未越界修改。

## 2026-07-13: [feat] 四个腿法(低/高鞭腿、侧踹腿、正蹬腿)踢腿高度几何质量评分并入动作子分

### 问题描述

考试逐动作出分原只有 DTW 黑盒相似度,不评"踢得够不够高"。为四个踢腿动作加几何质量评分并入该动作子分:
- **低鞭腿**:踢到膝盖高=及格(0.6),大腿中点=满分(1.0),往上到髋关节递减回0.6,再高继续降(三角峰,端点 `Q_BOUND=0.6`)。
- **高鞭腿**:两腿夹角90°/踢到腰(髋)平=合格,踢到头(鼻)平=优秀。
- **侧踹腿 / 正蹬腿**:提到髋平=合格(0.6),越往上越高,到头(下巴)平=满分。同高鞭高度映射,但无分腿夹角门(伸腿动作,两踝张开角对其无意义)。

### 修改内容

- **新增 `core/kick_quality.py`**(纯几何,含 `__main__` assert 自检):`score_kick_quality(landmarks_window, valid_mask, kind)` → (0..1 或 None, detail)。步骤:定位踢腿(窗口内踝帧间位移大者)→ 峰值帧(踝 y 最小)→ 按 kind 评分。三种 kind:`low_whip` 三角峰(中点1.0/大腿端点 `Q_BOUND=0.85`);`high_whip` 高度映射(膝→0、髋=`Q_PASS=0.6`、鼻→1.0)+夹角90°提示门;`kick_up`(侧踹/正蹬)同高度映射但无夹角门。高度映射抽为共享 `_height_map_score`。用 raw Pose33(非 DTW 归一化特征——后者排除鼻子且旋转对齐扭曲高度);高度用 y 比值不受横拍长宽比影响。校准旋钮 `Q_BOUND/Q_PASS/PASS_ANGLE_DEG` 显式常量。
- **`apps/recording_postprocess.py`**:`_run_pool` 里 side 池含踢腿模板(动作名∈`_KICK_KINDS`={低鞭腿:low_whip,高鞭腿:high_whip,侧踹腿:kick_up,正蹬腿:kick_up})时,`extract_pose_raw_series` 对该视频提一次 raw 复用;每踢腿模板用其 DTW 窗口 `slice_pose_raw_series` 切片 → `score_kick_quality` → `blended = KICK_GEOM_WEIGHT*geom + (1-KICK_GEOM_WEIGHT)*dtw`(`KICK_GEOM_WEIGHT=0.5`);geom=None 退回纯 DTW。action_scores 每项增 `dtw_score`/`geom_score`/`geom_detail`,`score`=blended。非踢腿动作不变。
- 透传/成绩表**无需改**:`_result_payload` 整 dict `to_jsonable`、`PostprocessUpdate.action_scores` 已透传、exam_panel 读 `d["score"]`(=blended)、宽表用 blended。

### 验证方法

- `core/kick_quality.py` 自检通过(合成峰值帧:low中点→1.0、髋高→Q_BOUND、鼻高→1.0、膝下→0、帧不足→None;kick_up 髋→Q_PASS、鼻→1.0)。
- 真实侧面视频(record_20260713_013406_368237/side.mp4)跑 `_run_auto_compare`:高鞭腿几何1.00(头平)→0.879;侧踹腿几何1.00(头平)→0.889;正蹬腿几何0.916(过腰近头)→0.847;低鞭腿几何0.594(踝在大腿185%即踢过髋、偏离中点)→0.673;非踢腿动作几何列空、纯 DTW 不变。
- `pytest tests/test_recording_postprocess.py -q` 51 passed(action_scores 新增字段不破坏现有断言)。
- 待观察:低鞭"185%"提示这次低鞭踢偏高或侧面视角下踢腿/站立腿定位待复核;`KICK_GEOM_WEIGHT/Q_BOUND/Q_PASS` 为校准旋钮,待真实数据标定。

## 2026-07-12: [feat] 考试/一条龙支持正/侧多模板池 + 逐动作出分

### 问题描述

散打规定套路考核里学员连贯打一套多个动作（直拳/摆拳/勾拳/高低鞭腿/侧踹/正蹬=侧面机位，摇闪=正面机位）。原考试/一条龙链路每边只支持一个模板（`front_template`/`side_template` → `compare_dual_streams` 出单一正/侧/综合分），无法为"一条视频含多个动作"的套路各动作分别出分。需求：UI 给正/侧两个独立模板列表各可加多个模板；检测时正对正池、侧对侧池；每模板各出一个动作子分；各动作分入成绩表（宽表每动作一列）；考试+一条龙都改。

### 修改内容

核心原则：把"每边一个 Path"泛化为"每边一个 Path 列表"，列表长度 1 时行为等同旧单模板；旧 prefs 单值键、旧 job 单字段保留读取兼容。

- **`apps/recording_postprocess.py`**：
  - 新增复数 prefs 键 `auto_compare_front_templates`/`auto_compare_side_templates`；`load_configured_template_lists()`/`save_configured_template_lists()`/`validate_auto_compare_template_lists()`（每路径过 `_load_heavy_template` 校验，单个坏模板跳过不整体失败，两池都空才 `template_missing`）；`template_action_name()`（动作名=文件 stem）。
  - `DualRecordingJob` 增 `front_templates`/`side_templates` tuple，`__post_init__` 用单字段回填复数（旧构造兼容）。
  - **`_run_auto_compare` 重写**：正对正池、侧对侧池，每模板各跑一次 `self._compare`(=`compare_video_to_template`) 出一个子分；`front_score`/`side_score`=各池均值，`combined`=w_front0.4/w_side0.6 加权（仅一侧非空则退化为该侧）；结果新增 `action_scores` 逐动作明细。**弃用 `compare_dual_streams` 自动正侧拆分**——考试双机位视角固定，逐模板 subsequence DTW 更直接（行为变更，已验证单模板场景不劣化）。
  - 可注入比对 seam `compare` 默认从 `compare_dual_streams` 改为 `compare_video_to_template`（单模板形状）。
  - `_result_payload`/`PostprocessUpdate` 增 `action_scores` 字段并透传。
- **`core/exam_roster.py`**：`ExamResultRow` 增 `action_scores: dict`；`collect_action_names()` 按首次出现顺序去重；`write_scorebook_xlsx` 动作列追加表尾（表头 `<动作>分`，×100 一位小数，缺失留空），`row_to_export_values` 接动作名列表参数。
- **`apps/exam_panel.py`**：`apply_postprocess_update_to_scorebook` completed 分支把 `update.action_scores` 转 `{name:score}` 写入 row；更新说明文案。
- **`apps/app_ui.py`**：录制区两单行输入框改**正/侧两个 Listbox + 添加/移除按钮**（`_build_template_pool_ui`/`_add_pool_templates`/`_remove_pool_selected`/`_persist_template_pools`/`_current_template_lists`）；变更即落复数 prefs；提交 job 填 `front_templates`/`side_templates`；`_exam_preflight` 改用 `validate_auto_compare_template_lists`（至少一侧非空即可，不再强制正侧齐全）。
- **`scripts/match_segments_probe.py`**：新增诊断探针（提取一次特征复用给多模板，打印分辨率自检+逐动作窗口+重叠检测）。

测试同步（`tests/test_recording_postprocess.py`）：`compare` mock 与 `_result()` 改为单模板形状；`compare_calls==1`→`==2`（正/侧各一模板各比对一次）；FIFO order 断言含双模板；result key set 增 `action_scores`；模板覆盖重构点同步清空复数字段。

### 验证方法

- `pytest tests/test_recording_postprocess.py tests/test_exam_roster.py tests/test_exam_session.py -q` 全通过（51+26）。
- 成绩宽表导出：构造两行不同动作集 → 动作列追加表尾、按首现顺序、缺失留空、×100，验证通过。
- 多模板逐动作出分闭环：侧面池[直拳,侧踹腿] vs 直拳视频 → 直拳 0.879 / 侧踹腿 0.524，有区分度；正面池空则 front_score=None、综合退化侧面均值，验证通过。
- 全量 `py_compile` 通过。
- **性能优化（同批）**：新增 `core/action_compare.py:compare_video_to_templates`（一条视频 vs 多模板，**视频姿态只提取一次**复用给池内每个模板做 DTW）；`DualRecordingPostProcessor` 比对 seam 从单模板 `compare_video_to_template` 改为池级 `compare_video_to_templates`（`_run_auto_compare._run_pool` 每视角调一次）。实测 7 模板侧面池从"逐模板重复提取超 2 分钟" → **15.3s**。测试 mock 同步改池形状（`_pool_result`）。
- app_ui 5 个 UI 测试为改动前既有失败（`_sync_record_stop_enabled` 等，与本改动无关，已 stash 复核）。

## 2026-07-11: [feat] pose33_v3 评分 baseline 从 2.0 校准为 3.0

### 问题描述

baseline=2.0 是当初随手设定、未经真人数据校准的刻度常数。用同一人连打同一套两遍做实测，系统只给 84% 左右，而人工判断应在 90%。4 组"同人连打两遍"数据显示 avg_cost 中位数 ≈ 0.333，baseline=2.0 时对应 ~85.8%，需要上调。

### 修改内容

校准依据：4 组独立"同人两遍"样本（avg_cost：0.335 / 0.300 / 0.333 / 0.372），中位数 0.333；
要让该中位数映射到 0.90 分，需 baseline = 0.333 × 0.90 / 0.10 ≈ 3.0（取整、好解释）。

改动文件（pose33_v3 评分主路径，全部从 2.0 改为 3.0）：

- **`core/feature_layout.py`**：`POSE33_V3.default_baseline` 2.0 → 3.0（权威来源，补校准注释）
- **`core/online_matcher.py`**：`_POSE33_V3_BASELINE` 2.0 → 3.0
- **`core/action_compare.py`**：4 处（`_multi_subsequence_matches` 默认参数、单次 DTW 局部赋值、`compare_action_to_template` 默认参数、`compare_dual_streams` 默认参数）
- **`apps/match_template.py`**：局部 `baseline = 2.0` → 3.0
- **`apps/recording_postprocess.py`**：`compare_dual_streams` 调用处显式参数 2.0 → 3.0
- **`analysis/offline_matching_profile.py`**：`POSE33_BASELINE` 2.0 → 3.0（同步离线分析口径）

测试同步更新：

- `tests/test_s3_calibration.py`：`assert POSE33_V3.default_baseline == 3.0`
- `tests/test_recording_postprocess.py`：比对调用 kwargs 断言 `baseline: 3.0`
- `tests/test_s5_offline_profile.py`：`assert offline_matching_profile.POSE33_BASELINE == 3.0`
- `tests/fixtures/pose33_v3/golden.json`：重新生成（single_template score 0.837→0.885，dual combined_percent 38→46）

不动的：`analysis/calibrate_body_core.py`（body_core 历史标定参照，独立口径）。

### 验证方法

- 核心套件 130 passed（`test_s3_calibration` / `test_recording_postprocess` / `test_body_core_layout` / `test_s5_offline_profile` / `test_pose33_v3_golden` / `test_rule_availability` / `test_tech_eval_contract`）全绿。
- 剩余失败均为改动前预存（`test_app_ui_lifecycle` / `test_yolo_backend_contract` / `test_ui_backend_sessions` 等，用 git stash 前后对比确认）。
- 新刻度下同人两遍中位数得分：`3.0/(3.0+0.333) ≈ 90%`，符合预期。

## 2026-07-11: [chore] 生成整套动作 heavy 标准模板（record_20260711_191628_631417）

### 问题描述

需要把 `E:\测试视频\20260711\record_20260711_191628_631417.mp4` 处理为 heavy + pose33_v3 标准模板，且要求纳入「整套动作」的有效帧（从整套开始到结束），仅裁掉前后准备/静止时间——而非某个单一动作段。

### 修改内容

- 无代码改动，仅用既有 `apps/make_template.py` 生成模板产物（gitignored，不入库）。
- 首跑默认自动分段（`find_active_range`）只取到「能量最高的最长连续段」1759..1825（67 帧 ≈2.2s），属单个动作而非整套，不满足需求。
- 逐帧计算 `motion_energy` 曲线（heavy + `normalize_pose_xy_v3`）定位整套边界：视频共 2422 帧/80.7s；帧 0–79 站定静止（能量 ≈0.001），帧 80 起运动爬升；结尾动作持续到 ≈2360，帧 2370 起归零。
- 以 `--pose heavy --start 80 --end 2370` 手动覆盖范围生成模板：
  `templates/record_20260711_191628_631417_heavy.npz`（features `(2291, 22, 2)`，`start_frame=80`/`end_frame=2370`/`fps=30`/`feature_layout=pose33_v3`/`backend=mediapipe`/`normalizer_version=v3`），并出 `*.preview.mp4`（codec avc1）供人工核对。

### 验证方法

- 载入 npz 校验 `features.shape=(2291,22,2)` 与 meta 字段（pose_variant=heavy、feature_layout=pose33_v3、start/end=80/2370）均正确。
- 导出带骨架标注预览视频，用于人工确认整套动作首尾裁剪合理。
- 未改动任何源码，`pose33_v3` 默认路径行为不变。

## 2026-07-11: [feat] 一条龙正/侧模板填入 UI；仅双缺报错

### 问题描述

自动比对（检测一条龙）硬编码 `standard_*_heavy.npz`，主界面无法填入/查看模板；缺一侧即失败，侧摄线不够时无法单侧试跑。

### 修改内容

- **UI**（`apps/app_ui.py` 录制区）：「正面模板 / 侧面模板」两条路径 +「填入…」；状态行显示 ✓/✗；路径持久化 `user_prefs`（`auto_compare_front_template` / `auto_compare_side_template`）。
- **一条龙契约**（`recording_postprocess`）：`validate_auto_compare_templates` — **仅正/侧都不可用** 才 `template_missing`；仅一侧可用则单流 DTW（`compare_video_to_template`），另一侧分显示 `-`。
- 考试 preflight 仍要求两侧齐全（`validate_template_pair`）。
- 提交 job 改用 UI 当前路径；比分展示支持单侧 `None`。

### 验证方法

- `pytest tests/test_recording_postprocess.py -q` → **51 passed**
- 定向：`test_auto_compare_runs_with_only_side_template`、双缺 `template_missing`

---

## 2026-07-11: [templates] 从实测视频生成 standard_front_heavy

### 问题描述

考试黑盒需 heavy+pose33_v3 标准正模板；用户提供 `E:\测试视频\20260711\record_20260711_191628_631417.mp4`。

### 修改内容

- `make_template.py --pose heavy --preview` 生成 `templates/standard_front_heavy.npz`
- 自动动作段：帧 1759..1825（len=67，fps=30）；预览 `templates/standard_front_heavy.preview.mp4`
- 侧模板 `standard_side_heavy.npz` 仍缺，双摄比对/考试需另补侧面标准视频

### 验证方法

- 命令 exit 0；npz 落盘；meta 含 pose heavy / pose33_v3

---

## 2026-07-11: [docs] 导入直拳+摆拳+踢腿场地实测数据

### 问题描述

场地本子测好的机位 / 考台尺寸此前只在手绘图 `直拳+摆拳+踢腿场地.jpg`，系统内无结构化记录，装机与 ROI 标定缺少可查数字。

### 修改内容

- 新增 `docs/venue_直拳摆拳踢腿.json`：考台上/下边界 102、左/右边界 89；**正摄正对上边界**（高 100 / 距台 216 / 投影距右边界 35.6）；**侧摄正对侧边界**（高 83 / 距台 249 / 投影距上边界 21.5）。
- `user_prefs.json` 写入同套 `venue_layout` 摘要 + 文档路径（本地偏好，gitignore）。
- 语义按用户确认：草图正/侧均旋转画法；21.5 / 35.6 为投影落点到框边距离；**不**从厘米推导 `exam_roi_norm`。
- 纠错：曾误把上边当 89、右边当 102，且正/侧机位对边反了；侧摄再纠为**左侧**边界（非右侧）。
- 再纠：机位距离=到对应边界的**直线垂直距离**；正摄→上边界 **216**；侧摄→左边界 **241**（草图曾误读为 249）。
- 「高」语义固定为**摄像机镜头对地垂直高度**（正 100 / 侧 83），非到考台斜距。
- 记忆与 JSON 强调：**源图正/侧位置均旋转画法，禁止按图面方向装机**，只认 `docs/venue_直拳摆拳踢腿.json`。

### 验证方法

- 通读 JSON 字段与源图标注一致；`python -c "json.load(...)"` 可解析。

---

## 2026-07-11: [ui] 删除主界面两路「旋转」下拉

### 问题描述

旋转已改为点击预览 +90°，摄像头行旁的两个旋转下拉多余且占位。

### 修改内容

- 移除 `rotate_combo` / `rotate_combo_2` 及「旋转：」标签与 combobox 事件。
- 保留内部 `rotate_var*` 与 `_runtime_rotate*`（点击预览仍同步角度，供 collect_state / 考试 ROI）。
- `_set_running_controls` 不再联动旋转控件；控件测试去掉对应断言。

### 验证方法

- `pytest tests/test_app_controls.py tests/test_app_ui_dual_camera.py -q`（相关子集）

---

## 2026-07-11: [feat] 预览点击旋转 / 自动比对滑块 / 黑盒固定 heavy

### 问题描述

1. 旋转依赖下拉且会话运行中锁定，必须停止才能改角度。
2. 「录制后自动比对」仅 Checkbutton，运行中锁定，切换不便。
3. 预览模型档与后端黑盒评分档语义混用。

### 修改内容

- **点击预览旋转**：主/侧预览 `Button-1` 各自顺时针 +90°（互不干扰）；`_runtime_rotate*` 线程安全，worker 每帧读取；下拉同步且运行中可改；录制 writer 未建时 `update_session_size`，已建则写盘 `resize` 适配。
- **自动比对滑块**：`仅录制 ⟷ 自动比对` Scale；运行中可快速切换；主线程写入 `_dual_auto_compare` 缓存，片段开录/提交读取；考试仍强制开并禁用滑块。
- **模型分轨**：主界面文案改为「预览姿态模型」；`CompareWindow` 模板生成/比对/tech_eval 强制 `heavy`；双摄后处理本已 heavy，保持契约。
- `RecordingController.session_size` 属性供写盘适配读取。

### 验证方法

- `py_compile apps/app_ui.py core/recording_controller.py` 通过。
- 定向回归（排除 5 条既有基线失败）：`test_app_ui_dual_camera` + `test_app_controls` + `test_app_ui_lifecycle` → **148 passed, 5 deselected**。
- 新增：`_next_rotate_cw` / `_fit_frame_to_size` / runtime 两路隔离单测。

---

## 2026-07-11: [feat] 全局骨架开关：默认关，预览与录制均不带骨架

### 问题描述

录制区「双摄录像写入骨架」仅在双摄路径生效；单摄始终叠骨架推理，且文案暗示只影响双摄写盘。需要统一为**全局骨架开关**：默认关闭，关闭时预览与录制都不带骨架。

### 修改内容

- 勾选文案改为「开启骨架（预览与录制；双摄开启后不自动比对）」。
- `_collect_state`：`record_skeleton` 单摄/双摄/文件源一律透传 UI 勾选（默认 `False`）；`auto_compare` 仍仅双摄有效。
- 单摄串行 worker：摄像头且未开骨架时不建 MediaPipe、不在线匹配，预览与录像写裸帧（仅 FPS 字）；离线文件仍始终 annotate。
- 单摄多 worker：仅「开骨架」时才走 `ParallelPoseEngine`；关骨架落入串行裸帧路径。
- 双摄既有门控保持不变（关骨架双路裸帧 + 不自动比对语义仍在「开骨架」时优先 `annotated_recording`）。
- 考试 preflight 文案同步为「开启骨架」。

### 验证方法

- `py_compile apps/app_ui.py` 通过。
- 骨架相关定向：`test_collect_state_captures_*_skeleton*`、`test_app_initializes_dual_record_skeleton_toggle_disabled`、`test_exam_preflight_rejects_skeleton_session` + 控件回归（排除既有 toggle 基线失败）→ **15 passed**。
- 双摄/生命周期全量（排除 2 条既有基线失败：`creates_two_mediapipe_pipelines` 计 occupancy 第三处构造、`pipeline_loading_keeps_raw_pair` write 断言）→ 预期通过。
- 既有基线失败与本改无关：`test_app_controls` 三条 `_sync_record_stop_enabled` stub 缺失、上述双摄两条。

---

## 2026-07-11: [docs] CLAUDE.md 同步考试系统与近期 commit

### 问题描述

考试系统（PR #72，`exam_*` 五模块 + `exam_panel` + `presence_gate` + `recording_postprocess` 透传）及双流评分等近期改动落地后，CLAUDE.md 未记录，新会话无法感知考务编排入口与硬约束。

### 修改内容

1. Core 模块职责补 `exam_session` / `exam_roster` / `exam_clip` / `exam_announcer` / `presence_gate` 五项。
2. Apps 入口补 `exam_panel.py`、`recording_postprocess.py`，并在 `app_ui.py` 说明「考试模式…」入口与 occupancy/begin-end 录制原语。
3. Architecture 新增「Exam System」小节：编排流程 + v1 成绩含义 / 全局模板 / 0..1 分数口径 / 增量落盘 / 不破坏手动录制快路径等契约（依据 `docs/exam_system_design.md` v0.2 S1–S7）。
4. Common Commands 增 `sim_exam_flow.py`；测试区增考试系统回归命令。

依据：`docs/exam_system_design.md` v0.2、commit `bf8c908` 及其后审查修复链（`be3a7fc`→`a4fab22`）、`requirements.txt` 新增 `openpyxl`。

### 验证方法

- `py_compile` 全部考试模块 + `sim_exam_flow.py` → OK。
- `pytest tests/test_exam_session.py tests/test_exam_roster.py -q` → **26 passed**。

## 2026-07-11: [fix] 考试系统审查第五轮（关窗停播报 / 纯#零值）

### 问题描述

主窗 `prepare_for_app_close` 未 `_announcer.close()`，语音线程可能残留；纯 `#` 格式下数值 0 被导入为 `"0"`，与 Excel 空显示不符。

### 修改内容

1. `prepare_for_app_close` 与普通关面板一致调用 `_announcer.close()`。
2. 无必选 `0` 位时数值 0 显示为空串，导入按 `empty_student_id` 拒绝（`#0` 仍为 `"0"`）。

### 验证方法

- `pytest tests/test_exam_roster.py tests/test_exam_session.py tests/test_app_ui_lifecycle.py::test_app_close_registers_open_panel_scorebook_for_flush_close -q` → **27 passed**。

---

## 2026-07-11: [fix] 考试系统审查第四轮（主窗关面板台账 / # 占位符）

### 问题描述

主窗 `root.destroy` 不触发考试面板 `_on_close`，当前 `panel.scorebook` 未进 sinks 导致不 flush/close；Excel `#` 被当成 `0` 强制补零，超宽时丢掉字面量前缀。

### 修改内容

1. **`ExamPanel.prepare_for_app_close`**：中止考试、flush 台账、登记 `_exam_scorebook_sinks`；主窗 `_on_close` 优先调用它，并把 sinks（含刚移交面板）计入关窗额外预算。
2. **学号格式**：`0` 必选补零、`#` 可选不补零（`###000`+123→`123`）；超出占位宽度时保留字面量（`"ID-"000`+12345→`ID-12345`）。

### 验证方法

- `pytest tests/test_exam_*.py tests/test_presence_gate.py tests/test_app_ui_lifecycle.py tests/test_recording_controller.py -q` → **104 passed**。

---

## 2026-07-11: [fix] 考试系统审查第三轮（begin 不 advance / discard 关窗 / multi-sink）

### 问题描述

PR 复核：开录失败仍自动跳过；关主窗 `_closing` 导致 discard 被跳过并正常评分；重开面板覆盖 sink 丢延迟成绩；3s 关窗预算截断裁剪；自定义学号格式静默裸数字；Scorebook close 后 writer 永久重试。

### 修改内容

1. **begin_failed**：不 advance，回 `wait_enter`+ARM，可重试/skip（符合设计 §6.6）。
2. **关窗顺序**：先 `on_session_stop`/discard，再 `_closing=True`；`_end_recording_segment(discard=True)` 在 closing 时仍执行。
3. **multi-sink**：`_exam_scorebook_sinks` 列表登记，新面板未匹配时继续投递旧 sink。
4. **关窗预算**：有考试裁剪/sink 时 deadline 额外 +30s/+8s；prepare 内 join clip 28s。
5. **学号格式**：支持 `000\-000`、`"ID-"000000`；无法解析的自定义格式整表拒绝。
6. **Scorebook.close**：有限次终刷后清 dirty 并退出 writer，文件锁定不永久重试。

### 验证方法

- `pytest tests/test_exam_*.py tests/test_presence_gate.py tests/test_app_ui_lifecycle.py tests/test_recording_controller.py -q` → **102 passed**。

---

## 2026-07-11: [fix] 考试系统审查第二轮 P1/P2（begin_failed / 暂停中止 / sink / 主停）

### 问题描述

PR #72 复核 head 后仍有：开录失败被 UPDATE recording 盖回、暂停后中止不停 writer、关面板丢后台成绩、主窗口停止不同步考试、裁剪线程未纳入关窗、裁剪帧假元数据、失败补考双计分、学号 `000-000` 格式。

### 修改内容

1. **begin_failed**：`enter_stable` 不再附带 `UPDATE_ROW(recording)`；成功开录后由面板写 recording；`update_row` 拒绝终态被弱状态覆盖。
2. **abort**：`paused_from==recording` / finishing 也发 `DISCARD_SEGMENT` 并标记 skipped；abort 后不再走 `record_stopped`。
3. **关面板 sink**：有 `processing` 行时把 Scorebook 交给 `App._exam_scorebook_sink`，后台比对继续回填；应用关闭时 flush/close。
4. **主窗口停止**：`_stop` / `_on_close` 调用 `ExamPanel.on_session_stop()` 中止考试。
5. **裁剪线程**：登记 `_exam_clip_threads`，关窗先 join 再 cancel postprocessor；关窗期考试更新仍入队。
6. **clip 帧一致**：写出帧数不等时 re-trim 文件，禁止假元数据。
7. **计分行**：有成功分时补考默认不计分；失败后重算仅成功行计分。
8. **学号格式**：支持 `000-000` 等 0/# + 分隔符掩码。

### 验证方法

- `pytest tests/test_exam_*.py tests/test_presence_gate.py tests/test_app_ui_lifecycle.py tests/test_recording_controller.py -q` → **99 passed**。

---

## 2026-07-11: [fix] 考试系统审查 P1/P2 缺陷修复（成绩不丢 / 关窗 / 裁剪 / 开考闸）

### 问题描述

PR 审查发现 7 个 P1 + 2 个 P2：旧片段成绩被丢、Scorebook 旧快照覆盖、重考清空整场、主线程整段重编码 OOM、骨架会话能开考却检测不到人、关面板不停录、双路状态分叉、学号丢补零、ROI 校验失败仍开考。

### 修改内容

1. **旧片段成绩回填**：`_drain_recording_compare_updates` 主界面比对条仍只跟最新片段，但考试面板按 `segment_id` 始终接收所有更新。
2. **Scorebook 写盘竞态**：`_write_lock` + `generation`/`written_generation`，旧快照不得覆盖更新代；flush/close 走 `_persist_latest(force=True)`。
3. **重考不重开整场**：已有 Scorebook 时 `_start_exam` 不再 `load_candidates`；`start_exam` 从首个 `pending` 叫号，不强制 pointer=0。
4. **裁剪内存/线程**：`prepare_exam_pair` 改为流式扫帧/写出（峰值 O(1 帧)）；考试派发在后台线程裁剪后再 submit，不堵 Tk。
5. **骨架会话 preflight 拒绝**；关考试面板先 `abort_exam`（录制中 discard）。
6. **双路 begin/toggle**：分叉/错误先 finalize 旧片段；双路须同态 recording，失败回滚 idle。
7. **学号按 number_format 显示文本**（如 123+`000000`→`000123`）；ROI 保存失败则中止开考。

### 验证方法

- `pytest tests/test_exam_roster.py tests/test_exam_session.py tests/test_exam_clip.py tests/test_presence_gate.py tests/test_app_ui_lifecycle.py tests/test_recording_controller.py -q` → **94 passed**。

---

## 2026-07-11: [test] 考试流程无摄像头模拟 + 成绩 flush 加固

### 问题描述

需要验证考试状态机/占用闸门/名单/裁剪链路是否流畅；模拟中发现 `ExamScorebook.flush` 仅靠后台线程时可能漏落盘。

### 修改内容

- 新增 `scripts/sim_exam_flow.py`：3 人闭环、skip/force/重考、10 人压力、裁剪、Excel、闸门防误触共 6 场景。
- `ExamScorebook.flush` 改为调用线程同步写盘兜底；临时 xlsx 用 ASCII 名。

### 验证方法

- `.\.venv\Scripts\python.exe scripts\sim_exam_flow.py` → **57 passed, SIMULATION_OK**（模拟钟约 34s/3 人、31s/10 人；墙钟 <2ms 量级，无摄像头/无 DTW）。

---

## 2026-07-11: [feat] 考试系统 v1 初版实现（按设计 v0.2）

### 问题描述

现场需要「导入名单 → 叫号 → ROI 到场 → 自动双路录制 → 空场 2s 结束 → 后台比对 → 写 Excel 成绩」闭环；设计见 `docs/exam_system_design.md` v0.2。

### 修改内容

- **核心**：`core/exam_roster.py`（openpyxl 导入/导出/台账/补考/异步写盘）、`core/presence_gate.py`、`core/exam_session.py`（状态机）、`core/exam_clip.py`（派发前帧截齐+动作裁剪）、`core/exam_announcer.py`（异步 TTS）。
- **UI**：`apps/exam_panel.py`；`apps/app_ui.py` 增加「考试模式…」、`_begin/_end_recording_segment` 原语、occupancy 第三条路径（lite、阶段性、裸帧录制）、考试派发元数据与裁剪。
- **后处理**：`DualRecordingJob` / `result.json` 可选 exam 字段；非考试帧数硬校验不变。
- **依赖**：`requirements.txt` 增加 `openpyxl`。
- 参数采用设计默认值（0.8s 进场 / 2s 空场 / 防串场等），实测后再调。

### 验证方法

- `pytest tests/test_exam_roster.py tests/test_presence_gate.py tests/test_exam_session.py tests/test_exam_clip.py -q` → **22 passed**。
- `py_compile` 相关模块通过；exam 元数据 smoke 通过。
- 现场待验：双摄 + heavy 正/侧模板 + 考试面板跑 2～10 人；`templates/` 须事先备好模板。

---

## 2026-07-11: [docs] 考试系统设计 v0.2（吸收审查 A/B/C/D）

### 问题描述

v0.1 设计在占用路径、帧数硬失败、走位污染 DTW、toggle 三态、S2 不可测、补考/防串场/合规等方面会被返工；审查给出 A（阻塞）/ B（产品）/ C（工程）/ D（v2）清单。

### 修改内容

- 升级 `docs/exam_system_design.md` → **v0.2**，主要落入：
  - **A1** occupancy 第三条路径（lite、阶段性、裸帧录制、非考试零推理不变）
  - **A2** 考试派发前 `min` 帧截齐，不改现网 postprocess 硬校验
  - **A3** 派发前 motion/首尾裁剪防走位污染
  - **A4** ROI = primary + 旋转后坐标
  - **A5** `_begin/_end_recording_segment` 原语
  - **A6** S2 量化门闩
  - **B1–B6** 分数 0..1、补考最后成功、防串场参数、force/skip、转换表、合规 §14
  - **C1–C5** 写盘占用/线程、Excel 学号与合并格、错归风险、模板须预置
  - **D** → §18 已知局限
- 仍无业务代码与依赖变更。

### 验证方法

- 通读 `docs/exam_system_design.md` 目录与 §6.6 / §8.6 / §10.2–10.3 是否覆盖清单条目。
- 无需 pytest。

---

## 2026-07-11: [docs] 考试系统设计文档（供审查）

### 问题描述

需要现场「叫号 → ROI 到场 → 自动录制 → 空场 2s 结束 → 后台比对 → 写 Excel 成绩」的考试流程。实现前先沉淀可独立审查的设计，避免直接改代码方向跑偏。

### 修改内容

- 新增 `docs/exam_system_design.md`（v0.1）：产品决策、非目标、复用边界、状态机、Excel 导入/导出契约、Presence 闸门参数、播报、与双摄后处理集成、模块清单、风险、验收与实现分期。
- 已确认决策写入文档：Tkinter、双摄、全局 heavy 模板、固定 ROI + 姿态、空场 2s。
- **本轮无业务代码、无依赖变更、无 UI 改动**；实现以审查结论为准。

### 验证方法

- 确认文件存在：`docs/exam_system_design.md`。
- 文档可独立阅读（含 mermaid 流程、表头契约、成功标准）；无需 pytest。

---

## 2026-07-10: [feat] 双摄录制/录制+检测一条龙开关

### 问题描述

Tkinter 双摄结束录制后默认总是进入「录制 + 黑盒检测」一条龙（后台转码 + heavy DTW 比对）。部分场景只想落盘录像、不触发检测，此前没有独立开关。

### 修改内容

- 录制分组新增勾选框「录制后自动比对（检测一条龙）」，默认开启，兼容现有一条龙行为；会话运行中与骨架开关一并锁定。
- `UiState.auto_compare` / `_dual_auto_compare` 在双摄会话启动时捕获；片段终结后经 `_RecordingPairFinalization` 写入 `DualRecordingJob.auto_compare`。
- `DualRecordingPostProcessor`：`auto_compare=False` 时仍顺序转码并校验录像，随后以 `skipped` / `auto_compare_disabled` 终态落 `result.json`，不读模板、不装 heavy 模型、不跑比对。骨架开启时仍优先 `annotated_recording` 跳过。
- 开录状态文案：开启比对显示「自动比对：录制中」，关闭显示「仅录制：录制中」。
- 回归：控件启停、collect_state 单/双摄、submit 透传、postprocess 仅录制跳过。

### 验证方法

- `.\.venv\Scripts\python.exe -m pytest tests/test_recording_postprocess.py tests/test_app_controls.py tests/test_app_ui_dual_camera.py tests/test_app_ui_lifecycle.py -q`：`186 passed`。
- 实机待验：双摄勾选/取消「录制后自动比对」各录一段，确认开启出分、关闭仅转码跳过比对。

---

## 2026-07-10: [perf/test] Tkinter 双摄快速首屏、裸帧过渡与 MediaPipe 门控复测

### 问题描述

Tkinter 双摄点击“开始”后，第二摄像头仍需现场打开且两路首帧串行等待；开启骨架录像时，两条 MediaPipe VIDEO pipeline 还会在任何画面出现前串行初始化，造成明显黑屏。旧异常测试同时存在“关闭骨架却期待创建两条 pipeline”的自相矛盾。MediaPipe `0.10.35` 和 GPU 是否值得进入 UI 也缺少同样本、同参数的门控证据。

### 修改内容

- 新增 `apps/camera_warmup.py`：按 `primary` / `secondary` 角色并发预热摄像头、持续保存 latest-only 帧，以 generation 隔离选择变化和旧会话，并支持两路原子 claim、超时/停止/关闭释放及异步 reaper。
- `apps/app_ui.py` 接入双摄选择预热和会话结束后重新预热；启动时复用 ready/in-flight capture，不再串行重复打开。预览改用单槽 `DualPreviewPacket`，Tk 主线程同一次 `_tick` 更新两路 Label，任一路失败时不残留单路画面。
- 开启骨架时，pipeline 仍由正式 worker 原线程串行创建，预热线程在加载期持续发布同步裸帧；两条 pipeline 全部 ready 后才整体切换到骨架帧。加载期录制按钮禁用，裸帧绝不进入 `_write_recording_pair`。
- 增加会话 stage/generation/render barrier、启动阶段六个计时点和 exactly-once 收敛，覆盖启动期停止、关窗、模型失败和快速重启。
- 修正双摄异常测试语义：骨架推理异常使用 `record_skeleton=True` 并验证两条 pipeline；无骨架写盘异常使用 `record_skeleton=False` 并验证零 pipeline。
- `analysis/bench_annotate_fps.py` 新增 `--mediapipe-only`，并输出实际 `active_delegate`、fallback 原因、峰值 RSS 和 RSS 增量。
- 隔离 venv 使用 6 段真实视频对比 MediaPipe `0.10.31` / `0.10.35`。`0.10.35` 未达到 10% 性能门槛，CPU FPS 中位数约低 1.6%-1.7%，峰值 RSS 高约 15%-19%；12 次 GPU 请求全部因 Windows build 禁用 GPU 而回退 CPU。因此保持 `mediapipe==0.10.31`、CPU 默认且不增加 GPU UI，结果置顶写入 `docs/mediapipe_gpu_delegate_report.md`。
- Spec acceptance 第一轮修复资源边界：禁止在 native `read()` 活跃时由其他线程强制 `release()`，仅使用 capture 显式 `interrupt()` 协作退出；无法取消的旧 open/read 进入退役隔离，同 index 在其收敛前禁止重复 open；release 异常保留资源并重试，不再静默标记完成。
- Legacy 单摄预开对相同 index 的 ready/in-flight 请求改为幂等；pool 的同 index 互斥锁获取支持 stop_event 取消，避免停止后留下排队 open。
- 启动计时日志只在 `running/failed/stopped` 终态输出，claim 失败不再被早先的 `starting` 覆盖；会话完成后清理对应 metrics，避免长期增长。
- 第二轮验收继续收口异常路径：positional-only factory 不再被误判为支持 `stop_event`；重复 `close()` 会继续重试 retained capture；legacy 单摄同步 open 和预开对设备锁使用 5 秒有界等待，永久 release 失败时明确拒绝而不是无限挂起。
- 报告补充当前锁定 `0.10.31` 的六视频 active-GPU 门控：pose-only `1.0020x`、pose+hands `1.0126x`，均远低于 `1.30x` / `1.20x`。

### 验证方法

- 双摄预热、UI、生命周期、控件和录制定向回归：`174 passed`。
- delegate、benchmark 和 pose33_v3 golden 门控：`35 passed`。
- 最终 Tkinter / MediaPipe / valid-mask 定向回归：`198 passed`。
- `py_compile apps/app_ui.py apps/camera_warmup.py core/vision_pipeline.py analysis/bench_annotate_fps.py` 通过。
- `git diff --check` 通过，仅有 Windows CRLF 提示。
- 真实双摄骨架关/开各 20 次、点击到两路实际 Tk 渲染 P95 `<=0.5s` 仍需连接物理双摄人工验收；程序已输出结构化启动计时点用于采集。

---

## 2026-07-10: [feat] Tkinter 录制保存目录持久化

### 问题描述

Tkinter「录制」分组的保存目录每次启动都回到默认 `outputs_dir()`，用户上次选择的目录不会被记住。

### 修改内容

- `core/paths.py`：新增 `load_record_dir()` / `save_record_dir()`，持久化到仓库根 `user_prefs.json`（单一 key `record_dir`）。读取时校验目录仍存在，缺失或坏 JSON 均回退 `outputs_dir()`；写入尽力而为，失败静默。仅用标准库 `json`，无新依赖、无配置框架。
- `apps/app_ui.py`：`record_dir_var` / `_record_base_dir` 初始值改为 `load_record_dir()`；`_choose_record_dir` 选目录后 `save_record_dir(d)`；`_on_record_toggle` 在 idle→recording 开录生效那一刻 `save_record_dir(next_base_dir)`（覆盖用户手打路径的情况）。

### 验证方法

- `py_compile apps/app_ui.py core/paths.py` 通过。
- paths 读写往返自测（临时 repo_root）：保存后读回一致、无效目录回退、坏 JSON 回退，全通过。
- `pytest tests/test_app_ui_lifecycle.py -q`：37 passed。

---

## 2026-07-10: [feat] 黑盒检测统一 heavy+pose33_v3 + 未勾选骨架时预览跳过推理

### 问题描述

「录制＋检测一条龙」两处需求：

1. 录制后自动比对（黑盒检测）此前锁定在 MediaPipe **full + v2 布局**（`standard_front/side_full.npz`），精度非最高，且与在线识别的 heavy+pose33_v3 模板格式分裂。用户要求黑盒检测全部改用精度最高的 heavy 链路（模板后续重录）。
2. 双摄 worker 每帧无条件跑双路 `annotate()` 实时推理，即便未勾选「双摄录像写入骨架」也照跑，heavy 双路实时推理开销大且对录后黑盒检测无用（黑盒检测会在录像上重新提特征）。

### 修改内容

- `apps/recording_postprocess.py`：`_EXPECTED_TEMPLATE_LAYOUT` 从 `pose_indices_11_32_xy_rot_scale_norm_v2` 改为 `pose33_v3`；新增 `_EXPECTED_TEMPLATE_POSE_VARIANT="heavy"`。默认模板路径改为 `standard_front_heavy.npz` / `standard_side_heavy.npz`。模型可用性检查 `pose_full`→`pose_heavy`，`model_missing` 文案同步。模板校验由「必须 full」改为「必须 heavy」。`compare_dual_streams` 调用 `pose_variant=None`→`"heavy"`（不再回退推断）。
- `apps/app_ui.py` 双摄 worker（`_worker_loop_dual`）：新增 `draw_skeleton = bool(state.record_skeleton)`。仅当勾选骨架时才创建 `MediaPipePipeline` 并跑 `annotate()`；未勾选时 `pipe/pipe2=None`，每帧用原始帧副本作预览（FPS 文字画在副本上），录像仍写原始帧，完全跳过双路 heavy 实时推理。finally 已有 `if pipeline is not None` 守护，安全。
- `templates/`：用现有标准 `正面.mp4`/`侧面.mp4` 生成占位默认模板 `standard_front_heavy.npz`/`standard_side_heavy.npz`（heavy+pose33_v3），满足 `test_fixed_templates_are_delivered_and_compatible` 契约；**用户后续用直拳标准视频重录并覆盖同名文件即可**。
- `tests/test_recording_postprocess.py`：`_write_template` 默认 `pose_variant="heavy"`/`layout="pose33_v3"`；invalid-pose_variant 变异改用 `full`（现为被拒项）；compare mock 断言 `pose_variant` `None`→`"heavy"`。

### 验证方法

- `py_compile apps/app_ui.py apps/recording_postprocess.py` 通过。
- `pytest tests/test_recording_postprocess.py -q`：`49 passed`。
- 双摄/控件/生命周期回归（分文件跑，规避多文件后台通道挂起）：`test_app_ui_dual_camera.py 45 passed`、`test_app_controls.py 10 passed`、`test_app_ui_lifecycle.py 37 passed`。
- 实机待验：未勾选骨架时双摄预览为无骨架原始画面且帧率提升、录制后黑盒检测走 heavy 模板出分；需接真实双摄执行。用户重录直拳标准模板后再确认相似度合理。

## 2026-07-10: [fix/test] Tkinter 双摄自动比对目录身份最终收口

### 问题描述

第六轮验收发现：文件系统返回零 inode 时，普通路径与 Windows `\\?\` / `\\?\UNC` namespace 未经过同一规范化回退。修复后的对抗复核又确认，同一目录若在相邻提交间从 `stat` 失败或零 inode 恢复为非零 inode，所有权键会在文本键与 `(st_dev, st_ino)` 键之间切换，仍可能让不同片段 ID 绕过去重并覆盖首份 `result.json`。

### 修改内容

- 新增统一、大小写不敏感的 Windows namespace 文本规范化，`stat` 失败和零 inode 均复用同一回退，兼容普通盘符路径、`\\?\` 与 `\\?\UNC`。
- 每次提交始终计算并登记规范文本键；文件系统提供非零 inode 时额外登记 stat 键。锁外完成路径解析和文件系统查询，锁内对最多两个键原子求交并登记，任一身份已被占用即拒绝。
- 新增零 inode namespace 回归，以及 `stat_error -> inode`、`zero_inode -> inode`、`inode -> stat_error`、`inode -> zero_inode` 四种切换回归；均覆盖任务执行中和完成后的重复提交，验证只比对一次且首份结果字节不变。

### 验证方法

- 后处理完整套件：`49 passed`；自动比对完整定向回归：`213 passed`。
- 全量 `pytest tests -q`：`564 passed, 1 skipped, 6 failed`；失败集合与接手基线一致，仍为 1 条 YOLO preview routing 和 5 条 `ui_backend` session，本任务未修改 Vue/Tauri/bridge 且未新增失败。
- 两路独立 post-fix 审查均为 PASS，未发现剩余 P0-P4；`py_compile`、`git diff --check` 和规范 `sync-check` 通过。
- Requirements-First 最终 `acceptance-finish` 返回 `accepted`：22 个验收问题全部关闭，无未决问题、修复或审查 agent。
- 实机待验：物理双摄连续两段、录制中主停止、骨架开启后跳过评分三条现场流程仍需接入真实摄像头执行。

## 2026-07-10: [fix/test] Tkinter 双摄自动比对第五轮 Windows 路径身份修复

### 问题描述

第五轮审查在 Windows 实机确认：普通 `C:\...`、扩展 `\\?\C:\...` 及可能的共享别名可指向同一物理目录，但 `resolve() + normcase()` 仍会生成不同字符串键，导致不同片段 ID 绕过目录所有权并覆盖同一 `result.json`。

### 修改内容

- 已存在的片段目录改用 `(st_dev, st_ino)` 文件系统身份作为所有权键，使普通路径、Win32 长路径 namespace、符号链接和共享别名在指向同一实体时统一归并。
- 文件系统身份计算保持在协调器锁外；锁内仍只做 O(1) 所有权检查和登记。目录不存在或文件系统不提供 inode 时，回退到移除 `\\?\` / `\\?\UNC\` 前缀后的平台规范化文本键。
- 新增 Windows 普通路径与扩展路径的集成回归，覆盖首次任务进行中和完成后两种抢占时机，验证仅执行一次比对且首份结果字节不变。

### 验证方法

- 自动比对完整定向回归：`206 passed`。
- 后处理子集：`42 passed`，包含 Windows namespace 别名用例。
- `py_compile` 与 `git diff --check` 通过，仅有 Windows 行尾提示。

## 2026-07-10: [fix/test] Tkinter 双摄自动比对第四轮隔离与异常恢复修复

### 问题描述

第四轮对抗审查发现两项 P2：后处理只按 `segment_id` 去重，不同 ID 若复用同一规范化目录会依次完成并覆盖同一个 `result.json`；双摄 worker 的推理或 writer 异常虽能释放资源和终结片段，却会跳过 `_post_done()`，导致主界面保持运行态、Start 持续禁用。

### 修改内容

- `DualRecordingPostProcessor.submit()` 在锁外解析并按平台大小写规则规范化 `segment_dir`，锁内为目录原子登记唯一 `segment_id` 所有权并保留至处理器销毁；同目录、`..` 别名或大小写别名的其他 ID 在入队前直接拒绝，不产生回调、比对或结果覆盖。
- 双摄 worker 将 `_post_done()` 收敛到最外层 `finally`，在两套 pipeline、两路 capture、OpenCV 窗口和录制片段全部收尾后恰好投递一次；覆盖正常结束、第二设备失败、模型初始化失败、推理异常和双 writer 异常。
- 新增不同 ID 目录别名抢占与双摄运行时异常完成通知回归，验证首份 JSON 字节不变、无串段通知，且异常后主界面可恢复非运行态。

### 验证方法

- 自动比对完整定向回归：`205 passed`。
- 后处理子集：`41 passed`；双摄子集：`54 passed`。
- `py_compile` 与 `git diff --check` 通过，仅有 Windows 行尾提示。

## 2026-07-10: [fix/test] Tkinter 双摄自动比对第三轮回调验收修复

### 问题描述

第三轮对抗审查发现三个 P3 边界：协调器回调线程内调用公开 `close()` 会尝试自连接并抛错；片段已发布 `cancelled` 后，最终路径补写若失败会再发送一个 `failed/result_write_failed` 终态；第二轮关窗防护把普通主停止也视为不可刷新，导致 worker 已复位为 idle 后录制状态文案仍残留。

### 修改内容

- `DualRecordingPostProcessor.close()` 在协调器 worker 自身调用时仍完成取消和退出哨兵登记，但跳过当前线程 join，使回调余下逻辑正常执行，worker 随后按队列顺序退出。
- 已成功发布 `cancelled` 的路径 enrichment 写盘失败时保留原 `result.json`，不再抛到通用 `result_write_failed` 通知；首次结果写盘失败的既有错误语义保持不变。
- `_refresh_recording_status()` 只在真正 `_closing` 时提前返回；普通主停止虽已设置 stop event，仍可在 worker 收尾后读取 idle 快照、清空旧录制文案并禁用“结束录制”。`_on_record_stop()` 的 closing/stop 防阻塞守卫不变。
- 新增回调自关闭、取消补写失败和主停止 worker 收尾三条确定性回归。

### 验证方法

- 自动比对完整定向回归：`204 passed`。
- 后处理子集：`40 passed`；Tkinter 生命周期、控件与双摄子集：`101 passed`。
- `py_compile` 与 `git diff --check` 通过，仅有 Windows 行尾提示。

## 2026-07-10: [fix/test] Tkinter 双摄自动比对第二轮并发验收修复

### 问题描述

第二轮首波与对抗审查发现两处剩余并发边界：后处理在共享协调器锁内执行原子 JSON 写盘，慢磁盘会阻塞新的 `submit()` 和关窗 `cancel_all()`；关窗后已调度的录制状态刷新仍可能等待录制锁、按旧快照重新启用控件，而“结束录制”入口也可能等待终结锁并突破 3 秒关闭预算。

### 修改内容

- `DualRecordingPostProcessor` 新增独立持久化锁，协调器状态锁仅保护写盘前后的取消、终态和去重判断，不再覆盖文件 I/O 或回调；写盘后再次判定取消，取消与 queued/completed 写入竞态时抑制旧状态通知并最终原子覆盖为 `cancelled`。
- `_refresh_recording_status()` 和 `_on_record_stop()` 在 `_closing` 或 `_stop_evt` 已置位时于读取 Tk 状态、获取录制锁或终结锁前直接返回，保证控件保持禁用且关窗轮询不被旧回调拖住。
- 新增阻塞 JSON 写入、阻塞录制锁和阻塞终结锁的确定性并发回归，覆盖 `submit()` / `cancel_all()` 及时返回、取消终态胜出、无旧 completed 通知及关窗控件不复活。

### 验证方法

- 自动比对完整定向回归：`201 passed`。
- 后处理并发子集：`38 passed`；Tkinter 生命周期、控件与双摄子集：`100 passed`。
- `py_compile` 与 `git diff --check` 通过，仅有 Windows 行尾提示。

## 2026-07-10: [fix/test/docs] Tkinter 双摄自动比对第一轮验收修复

### 问题描述

首轮多 agent 验收确认了 12 项取消、资源、并发和交付证据问题：DTW 评分阶段未贯穿取消，双摄 worker 异常路径未释放两路 native 资源，关窗轮询期间仍可开始新片段，后处理缺少片段目录隔离，`cancel_all()` 回调线程和终态通知不符合契约，转码异常错误码不准确；原实现提交还混入了规范开工前的双摄旋转/布局改动，任务完成日志指向不含实现的基线提交。

### 修改内容

- `subsequence_dtw()` / `subsequence_dtw_with_path()` 在代价矩阵、动态规划行、回溯和返回前响应取消；取消信号贯穿规则、正面评分、侧面评分与最终结果，正面评分取消后不再计算侧面或返回部分分数。
- 双摄 worker 在统一 `finally` 中关闭两套 MediaPipe pipeline、释放两路 capture 并清理 OpenCV 窗口；关窗立即禁用录制控件，录制 toggle 在 closing/stop 状态下于读取 Tk 状态前返回。
- 后处理在转码前校验正侧源路径均属于 `segment_dir`；`cancel_all()` 只置位并快速返回，所有回调由协调器线程触发，每片段只通知一次取消终态，同时允许内部补写最终转码路径；普通转码异常稳定归类为 `transcode_failed`。
- 用开工前 checkpoint 文件树重建独立提交 `8f0c9f8`，只保留既有双摄录制、旋转和自适应布局的 7 个路径；自动比对实现及首轮修复独立提交为 `09aa101`，旧混合提交 `b931222` 由安全分支保留。
- 仅修正 `tasks.md` / `progress.md` 的生成型完成日志和 `Last Known Commit` 为 `09aa101ea55421208e81739a6e88ccd6572f8656`，未改冻结任务正文、依赖、勾选状态或 task-plan hash。

### 验证方法

- 自动比对定向回归（后处理、控件、双摄、生命周期、录制控制器、转码、双流、模板 metadata、`pose33_v3` golden）：`196 passed`。
- 全量 `pytest tests -q`：`548 passed, 6 failed`；失败集合与接手基线一致，仍为 1 条 YOLO preview routing 和 5 条 `ui_backend` session，在本任务明确不修改的 Vue/Tauri/bridge 范围内。
- `py_compile`、`git diff --check` 和规范 `sync-check` 通过；提交父子关系、固定模板和后处理模块均通过 Git 对象校验。
- 实机待验：物理双摄连续两段、录制中主停止、骨架开启后跳过评分三条现场流程仍需接入真实摄像头执行。

## 2026-07-10: [feat/fix/test] Tkinter 双摄录制后自动后台比对

### 问题描述

Tkinter 双摄已能同步预览和录制，但片段结束后没有自动接入既有正面/侧面 DTW 比对；连续录制、主停止、writer 失败和关窗之间还缺少统一的片段终结、后台串行调度、结果留档与取消边界。带骨架录像若再次做姿态提取会产生失真分数，也需要明确跳过。

### 修改内容

- 新增无 Tk 依赖的 `DualRecordingPostProcessor`：按 `segment_id` 去重，单消费者 FIFO 顺序执行双路 H.264 转码、录像/固定模板/full 模型校验和 `compare_dual_streams()`；固定 `workers=1`、正侧权重 `0.4/0.6`、baseline `2.0`，规则与误差分析关闭。
- 每个片段目录通过临时文件原子替换生成 schema v1 `result.json`，完整记录成功、失败、跳过、取消、最终录像路径、转码 warning、三项分数和匹配区间；一次性写盘失败稳定归类为 `result_write_failed`，单任务失败不终止后续队列。
- Tkinter 双摄新增默认关闭且会话期间锁定的“录像写入骨架”开关；预览始终显示标注帧，关闭时 writer 保存旋转后的原始帧并自动比对，开启时保存标注帧、完成转码后写 `skipped/annotated_recording`。
- 显式“结束录制”、主“停止”、writer 错误、worker `finally` 和关窗统一经过串行终结器；锁内快照/释放、锁外非阻塞提交，零帧也提交为 `recording_empty`，每段最多提交一次，下一段可立即开始。
- 主窗口新增最近已提交片段的排队/转码/校验/比对状态、正面分、侧面分、综合百分比和稳定错误码；旧任务只更新自己的 JSON。后处理、双摄布局和摄像头枚举均用线程安全队列回到 Tk 主线程。
- 关窗先登记当前有效片段，再停止新提交并取消活动/排队任务；即使 3 秒等待预算耗尽也投递消费者退出哨兵。ffmpeg、VideoCapture 和 MediaPipe 在成功、失败、取消时统一释放。
- 交付并校验固定模板 `templates/standard_front_full.npz` 与 `templates/standard_side_full.npz`，保持现有 `full + v2` 兼容路径；Vue/Tauri、单摄、离线视频和评分算法不变。

### 验证方法

- T-003 Tk 生命周期与后处理定向套件：`122 passed`。
- 跨模块回归（含转码、双流比对、模板 metadata、录制控制器和 `pose33_v3` golden）：`177 passed`。
- 全量 `pytest tests -q`：`529 passed, 6 failed`；失败集合与接手基线一致，仍为 1 条 YOLO preview routing 和 5 条 `ui_backend` session 在制品，本任务未修改 Vue/Tauri/bridge 且未新增失败。
- 真实 ffmpeg/ffprobe 烟测：短 MJPG AVI 经实际 `transcode_to_h264()` 输出 `codec_name=h264` 的 1683-byte MP4，源 AVI 已删除且临时文件残留为 0。
- `py_compile` 与 `git diff --check` 通过（仅 Windows 行尾提示）。
- 实机待验：骨架关闭时连续录制两段并确认各自产生 `front/side` 视频及完成结果；录制中直接主“停止”并确认结果落盘；骨架开启时确认视频保留且结果明确为“带骨架录像未自动比对”。

## 2026-07-09: [feat/fix/test] 摄像头画面转正与双摄预览自适应

### 问题描述

USB 摄像头竖置后通常仍输出横向分辨率且不提供方向传感器，旧 Tkinter 入口没有逐路转正能力，姿态推理、预览和录制都会保留错误方向。双摄预览同时固定为上下堆叠，不能根据转正后的画面比例利用横向空间；90°/270° 旋转若不更新 writer 尺寸还会导致录制尺寸与帧不一致。

### 修改内容

- `apps/app_ui.py` 为两路摄像头分别增加 `0°/90°/180°/270°` 旋转下拉，严格解析四个合法角度，并在运行期间锁定控件；旋转只作用于实时摄像头，离线视频单/多 worker 路径保持原行为。
- 串行单摄、双摄两路和实时多 worker reader 均在 MediaPipe 推理前应用旋转，使 landmarks、在线匹配、预览与录制共用转正后的坐标系；90°/270° 先交换驱动上报尺寸，再由旋转后的首帧真实 shape 通过 `RecordingController.update_session_size()` 校正 writer，避免错误 `CAP_PROP` 造成空文件或坏文件。
- 双摄根据旋转后宽高比自动排布：两路都为竖画面时左右并排，横向/方形/混合方向时上下堆叠；先按设备尺寸切换，再用首帧真实尺寸校正，所有 Tk grid 更新通过主线程执行，单摄隐藏时同步清空第二行/列权重。
- 补齐双路录制一致性：共享录制锁覆盖片段级保存根目录/时间戳发布和两路 toggle/begin/write/stop/close，保证 front/side 的片段边界与目录一致；目录选择只更新 Tk 变量，真正的普通 `Path` 在下一次 `idle -> recording` 时锁内发布，worker 不再持锁读取 `StringVar`。UI 同时显示正面/侧面输出路径，任一路 writer 失败时结束两路片段并明确标注失败路。
- `core/recording_controller.py` 在片段停止/会话关闭时清理 `last_error`，且单摄模式忽略第二路错误，避免侧路失败污染同会话重试或下一次单摄/离线会话；worker 在 close 前把 Tk 尚未消费的错误转存到待提示队列，最后一帧失败也不会静默丢失。
- 新增 headless 回归，覆盖角度像素方向、非法值、writer 首帧尺寸校正、布局坐标/权重、状态采集、三条实时采集路径、离线视频隔离、运行态控件、第二路 writer 失败收敛，以及真实双线程下 toggle/时间戳/双写/stop 不交错。

### 验证方法

- `.\.venv\Scripts\python.exe -m pytest tests/test_app_ui_dual_camera.py tests/test_app_controls.py tests/test_app_ui_lifecycle.py tests/test_recording_controller.py -q`：`80 passed`。
- `.\.venv\Scripts\python.exe -m pytest tests/test_pose33_v3_golden.py tests/test_s5_hands_toggle.py tests/test_error_handling.py tests/test_input_source_state.py -q`：`34 passed`。
- 全量 `.\.venv\Scripts\python.exe -m pytest tests -q`：`468 passed, 6 failed, 5 warnings`；失败集合与接手前记录一致，仍为 1 条 YOLO preview routing 和 5 条 `ui_backend` session 在制品，本次未新增失败。
- `.\.venv\Scripts\python.exe -m py_compile apps\app_ui.py core\recording_controller.py tests\test_app_ui_dual_camera.py tests\test_app_controls.py tests\test_app_ui_lifecycle.py tests\test_recording_controller.py` 通过。
- `git diff --check` 通过，无 whitespace error（仅 Windows 行尾提示）。
- 自动化验证不依赖真实摄像头；两台物理摄像头的竖置方向与驱动尺寸仍需现场快速目视确认。

## 2026-07-09: [feat] 双摄双面视图两路同步落盘 + 按日期/录制段归档

### 问题描述

双摄双面视图（issue #58）录制时只有第一路（正面）落盘，第二路（侧面）仅预览不存储（`apps/app_ui.py` 原 `ponytail:` 注释标注的推迟点）。同时单一录制路径无法区分双摄两路来源。

### 修改内容

- `apps/app_ui.py` 新增第二路录制控制器 `self._rec2`（`path_provider=_record_path_cam2`），在 `_worker_loop_dual_camera` 中与第一路各自 `begin_session` / `write_frame` / `close_session`；`_on_record_toggle` / `_on_record_stop` 同步切换两路。`_rec2` 在单摄/文件模式恒 idle no-op。
- 录制路径按日期和片段归档：单摄/文件写入 `<保存目录>/<YYYYMMDD>/record_<时间戳>.mp4`；双摄两路共用同一时间戳与片段目录，分别写入 `<保存目录>/<YYYYMMDD>/record_<时间戳>/front.mp4` 和 `side.mp4`。`_dual_active` 在双摄循环进入时置 True、finally 复位。

### 验证方法

- `py_compile apps/app_ui.py` 通过。
- `pytest tests/test_app_ui_lifecycle.py tests/test_recording_controller.py -q`：`20 passed`。

## 2026-07-09: [fix/test/docs] 修复 PR #71 五项审查问题并对齐最新 main

### 问题描述

PR #71 存在五项场地前阻塞：在线直拳模板未交付、`mp4v` 回退可以产出非 H.264 MP4、摄像头预打开存在重叠任务竞态、新会话保留旧识别文案，以及未跟踪的 daemon 转码线程可在关窗时被截断。同时 PR 分支落后 `origin/main`，且夹带了 main 已有的 batch paired 重复提交。

### 修改内容

- 从最新 `origin/main` 重建 PR 分支，只重放 Tkinter、change 归档和 bridge 在制品三个有效提交，移除重复 batch commit；冲突以 main 的同目录 paired 行为和最新文档为准。
- `.gitignore` 只白名单放行 `templates/online/直拳_左手.npz` 与 `直拳_右手.npz`，其他本地模板仍忽略；新增默认模板库加载契约测试。
- `core/video_writer.py` 移除 `mp4v -> .mp4` 路径：H.264 不可用时只回退 `MJPG/XVID -> .avi`，再由 ffmpeg 转 H.264；转码先写同目录唯一临时 MP4，校验非空后原子替换，失败保留 AVI 和已有 MP4。
- `apps/app_ui.py` 为预打开请求增加 generation token，只接受最新且 `isOpened()` 的 cap，原子替换时释放旧 handle；新会话重置 `识别：待机`。
- H.264 转码改为受跟踪的 non-daemon worker；关窗按 50 ms 分片等待采集/转码任务，最多保留 GUI 3 秒，之后转码可在后台继续，ffmpeg 最长 30 分钟硬超时并在失败时保留 AVI。
- 按最新仓库事实源同步 `AGENTS.md` / `CLAUDE.md` 归档和 analysis 清单，并更新仍指向已删 `_browse_video` 或旧 YOLO 文案的回归测试。

### 验证方法

- Tkinter matcher / 平滑 / 并行 / 双摄 / 录制 / MediaPipe golden 定向安全网：`97 passed`。
- 最新文档与错误处理契约：`9 passed`。
- 全量 `pytest tests -q`：`421 passed, 6 failed, 1 skipped, 5 warnings`；剩余 5 条为 PR 第 4 个 commit 已标注的 `ui_backend` session 在制品，1 条为本轮明确暂不处理的 YOLO preview routing。
- 真实 ffmpeg + ffprobe 探测：MJPG AVI 转码后 `codec_name=h264`、MP4 `2769` bytes、源 AVI 已删除。
- `py_compile apps/app_ui.py core/video_writer.py tests/test_app_ui_lifecycle.py` 通过；`git diff --check` 无 whitespace error（仅 Windows 行尾提示）。

## 2026-07-09: [chore] change.md 归档与重建

### 问题描述

`change.md` 累积至 586 行（覆盖 2026-06-14 ~ 2026-07-09），按任务完成规范需归档并重建空文件。

### 修改内容

- `git mv change.md "change（2026.6~2026.7）.md"`，重建空 `change.md`，本条为首条记录。
- 同步更新 `CLAUDE.md` 归档清单：新增 `change（2026.6~2026.7）.md`。
- 历史归档：`change（start~2026.5）.md`、`change（2026.5~2026.6）.md`、`change（2026.6~2026.7）.md`。

### 验证方法

- `ls change*.md` → 三份归档 + 空 `change.md`。
- `git mv` 保留文件历史（非删除重建）。

## 2026-07-09: [apps/core] 接通 Tkinter 实时直拳识别、预览平滑与录制 H.264 转码

### 问题描述

`core/online_matcher.py`、`templates/online/` 左右手直拳模板与 `core/preview_smoother.py` 均已就绪且单测全绿，但 `apps/app_ui.py` 未接线：Tkinter 实时预览无法显示在线识别结果，预览骨架未平滑，录制回退的 MJPG AVI 也未转 H.264。

### 修改内容

- `apps/app_ui.py`：
  - 新增默认开启的「实时动作识别」开关 + `match_var` 命中/分数显示，以及 `_build_online_matcher`/`_feed_online_matcher`/`_post_match` 三个接入边界；模板缺失/不兼容安全降级为无 matcher，关窗/停止竞态不刷新已销毁 UI。
  - 开关值经 Tk 主线程收进 `UiState.online_match_enabled`，worker 不跨线程读 `BooleanVar`；matcher 仅接单摄实时流，双摄/离线不接。
  - 单线程摄像头按 `infer(raw) → matcher(raw) → smoother → draw` 执行；文件 VIDEO 路径保留原 `annotate()`，帧序号/时间戳语义不变。
  - 并行摄像头启用 `ParallelPoseEngine(defer_draw=True)`，在有序出口喂 raw matcher、平滑并绘制，用采集 monotonic 时间戳保留满队列丢帧的真实间隔（顺带消除原「时序平滑关闭」抖动）。
  - 绘制均以 raw landmarks 做动作分类、smoothed landmarks 画骨架，smoother 不回流识别/评分序列。
  - 新增 `_transcode_async`，接入手动结束录制与单线程/双摄/并行视频/并行摄像头四个会话收敛点；录制文件名加微秒防同秒重录与后台转码争用。
- `core/vision_pipeline.py`：`draw_pose_frame` / `MediaPipePipeline.draw` 新增可选 `action_pose_landmarks`（默认沿用绘制 landmarks，旧行为不变），平滑预览显式传 raw 做分类。
- `core/video_writer.py`：新增 `transcode_to_h264`，仅把 AVI 用 `libx264/medium/CRF20/yuv420p` 转 MP4；成功且目标非空才删 AVI，ffmpeg 缺失/失败保留原录像。
- `core/parallel_pose_engine.py`：`ParallelPoseEngine` 新增 `defer_draw`，`InferResult` 携带 raw `pose_landmarks`/`hands`/`frame` 供重排出口单线程平滑+绘制。
- 新增 `tests/test_online_matcher.py`、`tests/test_app_ui_online_matcher.py`、`tests/test_preview_smoother.py`、`tests/test_preview_draw_contract.py`、`tests/test_video_writer_transcode.py`。

### 验证方法

- 定向 + 安全网 **68 passed**：在线 matcher、Tkinter 接入、预览平滑/绘制边界、转码、`pose33_v3` golden、`valid_mask`、双摄、手部开关全绿。
- 首轮全量 `pytest tests -q` 为 **403 passed / 10 failed**。后续 PR 审查确认：其中 5 条 `ui_backend` session 与 1 条 YOLO preview routing 由 PR 第 4 个在制品提交引入，其余为落后最新文档/接口的旧测试；最终验证结果见本文件置顶记录。
- `py_compile apps/app_ui.py core/vision_pipeline.py core/video_writer.py core/parallel_pose_engine.py` → OK。
- 待场地人员按实际机位人工确认左右手命中、平滑观感、录制全链路，并现场标定 `MatcherConfig` 阈值。
