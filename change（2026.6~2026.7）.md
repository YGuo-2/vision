## 2026-07-08: [docs/test] 收尾 batch paired 与双摄骨架测试（issue #59/#62）

### 问题描述

双摄双面视图收尾 issue 中，#60/#61 已分别落地学员正/侧配对 helper 与 `batch_dual_compare.py --paired` 双流批处理入口。剩余 #62 要同步 `change.md`、`CLAUDE.md`、`AGENTS.md`；#59 最新评论已把测试范围裁剪为只守卫双摄 Tkinter 骨架，不再要求 Tkinter 接入 `PreviewLandmarkSmoother` / 在线 matcher。

### 修改内容

- `tests/test_app_ui_dual_camera.py`：新增无需真实 Tk root 的双摄测试，覆盖 `_collect_state` 的 `source2` 收集、同设备守卫、视频文件模式忽略第二摄像头，以及 `_worker_loop_dual_camera` 内双 `MediaPipePipeline` AST 守卫。
- `CLAUDE.md`：补充 `compare_dual_streams` 双独立流入口和 `batch_dual_compare.py --paired` 的边界：默认单视频模式不变、同目录正/侧关键词配对、CSV `video` 列写学员 id、`--export_raw` 跳过、`body_core_v1` 不接 paired。
- `AGENTS.md`：补 paired 批处理命令、后续 agent 硬约束和 batch paired / dual-stream 验证门。
- `change.md`：记录 #59/#62 收尾依据、修改内容和验证结果。

### 验证方法

- `py_compile apps/app_ui.py` → OK
- `pytest tests/test_app_ui_dual_camera.py -q` → 5 passed
- `pytest tests/test_batch_backend_args.py tests/test_compare_dual_streams.py -q` → 23 passed
- `git diff --check` → 仅 Windows 行尾提示，无 whitespace error

## 2026-07-08: [apps] 修复 PR #67 代码评审发现的两处问题（issue #58 后续）

### 问题描述

PR #67（issue #58 双摄双路预览）代码评审提出两处问题：

- **P1（真回归，已实测复现）**：`_build_ui` 给列 1 常驻 `columnconfigure(weight=1)`，仅靠 `preview2.grid_remove()` 隐藏第二 Label。Tk grid 按列权重分配额外宽度与 widget 是否隐藏无关——1000px 宽度下实测隐藏列仍占约 494px，主预览只剩约 506px，违反「单摄模式预览行为逐字不变」。
- **P2（潜在竞态）**：显示 `preview2`（`_start`，按 `state.source2`）与是否真正进入双摄 worker（`_worker_loop`，按 `state.source2 and not is_file`）用了两个不同条件判断，理论上可能显示第二预览但无生产者写入。

### 修改内容

- `apps/app_ui.py`：
  - **P1**：新增 `_set_dual_preview_visible(visible)`，把「显示/隐藏 `preview2`」与「列 1 grid 权重」绑在一起切换（隐藏时权重同步置 0）。`_build_ui` 初始调用一次（`False`），`_start` 里原地判断改为调用该方法。用真实 Tk 实例验证：1000px 宽度下单摄模式主预览恢复到 996px（此前约 506px），双摄模式两路各占约 498px。
  - **P2**：把「主输入源是否为摄像头」这一判断收敛进 `_collect_state`——`source2` 只在 `source.isdigit()`（摄像头模式）且第二下拉选中真实条目时才非空；视频文件模式下第二下拉即便有值也强制 `source2=None`。这样 `_start`/`_worker_loop` 只需检查 `state.source2` 是否非空这一个信号，显示、隐藏、分流三处不再各自重复判断、不会出现「显示但无生产者」的分裂状态。

### 验证方法

- `py_compile apps/app_ui.py` → OK
- `pytest tests/test_pose33_v3_golden.py -q` → 16 passed，零漂移
- `pytest tests -q` → 22 failed / 377 passed / 1 skipped，失败集合与改动前完全相同（既存 bug，与本次改动无关）
- 用真实 `tkinter.Tk()` 实例复现并验证修复：单摄模式主预览宽度从约 506px 恢复到 996px（1000px 总宽度下）；切换双摄模式两路各占约 498px

## 2026-07-08: [apps] _worker_loop_dual_camera 双路 VIDEO 循环 + 双 Label 独立渲染（issue #58）

### 问题描述

双摄像头双面视图（Milestone #7）apps 链下一环。#57 已落地第二摄像头下拉 + `UiState.source2`，但选中后并未真正跑双路预览。issue #58 原描述提到接「两个 `PreviewLandmarkSmoother`」+「在线 matcher 只喂正面流」，但核实当前 `apps/app_ui.py` 单摄路径本身并未接入 `core/preview_smoother.py`（One Euro 平滑）或 `core/online_matcher.py`（在线 DTW 识别）——这两个模块目前只接进了 `apps/ui_backend.py`（Vue/Tauri 桥接层），从未接入 Tkinter。经用户确认，本次范围裁剪为「只做双摄骨架」：两个独立 `MediaPipePipeline` + 两个单槽队列 + 两个 Label，忠实复刻单摄 `_worker_loop` 现有行为（包括它目前就没有的平滑/识别），smoother/matcher 接入 Tkinter 留给后续独立 issue。

### 修改内容

- `apps/app_ui.py`：
  - `__init__` 新增第二路预览状态：`self._queue2`（单槽队列，同构 `self._queue`）与 `self._photo2`。单摄模式下恒空/恒 None，现有路径零改动。
  - `_build_ui` 预览区新增第二 `ttk.Label self.preview2`（`grid(row=0, column=1)`），初始 `grid_remove()` 隐藏；`right` 增加列 1 的 grid 权重。
  - `_start()` 按 `state.source2` 是否非空切换 `preview2` 的显示/隐藏。
  - `_worker_loop` 在 `cap.isOpened()` 校验之后、单摄 VIDEO/并行分流之前插入分流：`state.source2` 非空且非文件模式时转入新方法 `_worker_loop_dual_camera(state, cap)`。
  - 新增 `_worker_loop_dual_camera`：仿单摄 VIDEO 分支，两个独立 `MediaPipePipeline`（VIDEO 模式有状态，不共享）+ 新开 `cap2 = open_camera(int(state.source2))`；循环内两路各自 `read → next_timestamp_ms → annotate`，任一路读失败则整体停止；只在正面路叠 FPS/提示文字、只录正面路（`self._rec.write_frame`，侧路预览不落盘，`# ponytail:` 注明升级路径）；分别推 `_post_frame`/新方法 `_post_frame2`。
  - 新增 `_post_frame2`：与 `_post_frame` 同构，操作 `self._queue2`。
  - `_tick` 追加非阻塞 drain `self._queue2` 并按现有 fit-to-window 缩放逻辑绘制到 `self.preview2`（重复一份缩放代码是最小必要重复，抽公共 helper 属过度设计）。
  - 不接 `PreviewLandmarkSmoother`/`OnlineActionMatcher`；不支持双路都存视频文件；`workers>1` 时双摄分支内部仍强制单线程跑两路 VIDEO pipeline（不复用并行摄像头路径）。
  - 未新增单测文件——AST 守卫等测试已单独列在 issue #59，随后续落地。

### 验证方法

- `py_compile apps/app_ui.py` → OK
- `pytest tests/test_pose33_v3_golden.py -q` → **16 passed，零漂移**
- `pytest tests -q`：改动前后各跑一遍全量对比（`git stash` 前后 22 failed / 377-378 passed，失败集合逐一相同），确认本次改动**零新增失败**；既存 22 个失败（`test_app_ui_online_matcher.py` 10 项、`test_s5_hands_toggle.py::test_ui_state_*` 2 项等）均在改动前的干净基线上已存在，与本次改动无关（`test_s5_hands_toggle.py` 的失败是 `_collect_state` 引用了不存在的 `self.save_var`/`self.out_var`，属既存 bug）
- 人眼验收待硬件到位后补：选两个摄像头 → 并排双骨架预览；只选一个 → 单摄行为不变（结构上保证，逐字复刻单摄分支）

## 2026-07-08: [apps] Tkinter 第二摄像头选择器 + UiState.source2（issue #57）

### 问题描述

双摄像头双面视图（Milestone #7）apps 链的起手 issue，为 #58（双路 VIDEO 循环 + 双 Label 独立渲染）打地基。现状 `apps/app_ui.py` 全链路单摄：一个 `camera_combo` + `UiState.source` 单字段，无法表达「第二路摄像头」。

### 修改内容

- `apps/app_ui.py`：
  - 新增模块级常量 `NO_SECOND_CAMERA = "无（单摄像头）"`（第二摄像头下拉的「不选」sentinel）。
  - `_build_ui` 在现有摄像头下拉之后加第二摄像头下拉 `self.camera_combo_2` + `self.camera_choice_var_2`，初始仅含 sentinel。
  - 新增 `_camera_index_for_label` helper（按 label 反查 `CameraEntry.index`），`_select_camera_by_label` 改为调用它，消除重复查找逻辑。
  - `_apply_camera_entries` 两个分支（空列表 / 正常枚举）都同步刷新 `camera_combo_2` 的候选值与选中态；已选项不在新列表中时回退 sentinel。
  - `UiState` 加字段 `source2: str | None = None`。
  - `_collect_state` 读取第二摄像头下拉：未选或选不到真实条目 → `source2=None`（即今天的单摄行为不变）；两路选到同一编号时抛 `ValueError("两个摄像头不能选同一个")`。
  - `_set_running_controls` 让 `camera_combo_2` 与主摄像头下拉同步禁用/恢复（运行中禁用，停止后按是否有摄像头列表恢复 readonly）。
  - 不实现双路 VIDEO 循环 / 双 Label 渲染（留 #58），不新增单测文件（roadmap 把测试放在 #59，随 #58 一起用 AST 守卫测）。

### 验证方法（干净 worktree 从远程分支 checkout 后实测，非本地脏工作区）

- `py_compile apps/app_ui.py` → OK
- `pytest tests/test_pose33_v3_golden.py -q` → **16 passed，零漂移**
- `pytest tests/test_s5_hands_toggle.py -q` → **6 passed**（`_collect_state` 相关既有测试用 `object.__new__(App)` 构造精简假对象，未初始化 `camera_choice_var_2`，靠 `getattr` 兜底为 `source2=None`，行为不变）
- `pytest tests -q` → **365 passed, 4 failed, 2 skipped**；4 个失败（`test_error_handling.py::test_browse_video_rejects_invalid_file_and_preserves_source`、`test_s6_default_switch_decision.py::test_s6_decision_has_per_chain_outcome_and_reopen_gates`、`test_tracking_issue_sync.py::test_tracking_doc_lists_final_m4_issues_and_decisions`、`test_tracking_issue_sync.py::test_s6_decision_doc_exists_for_tracking_close`）与本次改动无关，在 `main`（`b0bbe34`）干净基线上跑同一条命令同样失败、数量一致；`test_ui_backend_sessions.py::test_camera_preview_drops_stale_frames_when_inference_is_slow` 偶发因 Tk 线程计时抖动失败，单独重跑与全量重跑均 passed，非本次改动引入



## 2026-07-08: [test] 补全 compare_dual_streams 单测验收标准（issue #56）

### 问题描述

#55/#56 已在 PR #64 一并落地 `tests/test_compare_dual_streams.py`（3 个测试），但对照 #56 验收标准逐项核对，缺两项：未显式断言 `front_score`/`side_score`/`combined_percent` 的取值范围；未覆盖「正/侧模板 layout 版本不一致时抛 `ValueError`」（`compare_dual_streams` 内部沿用的 `layout_ver_f != layout_ver_s` 守卫，`core/action_compare.py:1205-1206`）。

### 修改内容

- `tests/test_compare_dual_streams.py`：
  - `test_no_split_and_high_score_for_matching_streams` 补充范围断言：`0.0 <= front_score/side_score <= 1.0`、`0 <= combined_percent <= 100`。
  - 新增 `test_layout_version_mismatch_raises_value_error`：复制 `front_template.npz`，把 `meta["feature_layout"]` 改成 `LEGACY_DEFAULT_FEATURE_LAYOUT`（v1）另存到 `tmp_path`，与保持 v3 的 `side_template.npz` 一起传入 `compare_dual_streams`，断言抛 `ValueError`。
  - 不新增产品代码，不新建 fixture，复用已提交的 raw fixture + `golden_harness` 回放。

### 验证方法

- `pytest tests/test_compare_dual_streams.py -q` → **4 passed**
- `pytest tests/test_pose33_v3_golden.py -q` → **16 passed，golden 零漂移**



## 2026-07-08: [core] 提取 _score_view_seq 模块级 helper（issue #54，纯机械 lift）

### 问题描述

双摄像头双面视图（Milestone #7）的下一步 #55 要新增 `compare_dual_streams`（正流↔正模板、侧流↔侧模板各跑一次评分），但评分逻辑 `score_view`（`core/action_compare.py`）是 `compare_video_to_dual_templates` 内的嵌套闭包，绑定了单视频局部变量 `seq`/`fps`/`_raw_slice`/`baseline` 等，无法在函数外部对两路独立流复用。本 issue 只做纯机械 lift，不改任何行为，为 #55 铺路。

### 修改内容

- `core/action_compare.py`：
  - `_swap_lr`（纯字符串 helper，无闭包状态）原样提到模块级，紧邻 `_trimmed_mean` 之后。
  - `score_view` 函数体提升为模块级函数 `_score_view_seq(seq, raw_slice_fn, tpl_features, tpl_meta, seg, *, fps, baseline, enable_error_analysis, joint_names, src_idx, num_joints)`，自由变量全部变成参数，语句顺序/取值逐字不变；`_raw_slice(...)` 调用改为 `raw_slice_fn(...)`。
  - `compare_video_to_dual_templates` 内 `score_view` 收缩成一行 delegate，调用 `_score_view_seq(...)`；调用点 `score_view(feat_f, meta_f, front_seg)` / `score_view(feat_s, meta_s, side_seg)` 不变。
  - 不新增双流入口（留给 #55），不动单视频 frontness 拆分逻辑。

### 验证方法

- `py_compile core/action_compare.py` → OK
- `pytest tests/test_pose33_v3_golden.py -q` → **16 passed，golden 零漂移**（含 `test_dual_scores`/`test_dual_segments`/`test_dual_rule_scores`/`test_dual_rule_violations`/`test_dual_joint_errors`，覆盖 `DualCompareResult` 全部字段）



## 2026-06-15: 完成 Spce final acceptance 并冻结 accepted 状态

### 问题描述

T-001 至 T-010 已全部完成并推送后，Spce workflow 仍需通过 final acceptance 才能宣告整条设计优先流程结束。第一轮验收修复已提交到 `9e68097`，随后需要继续第二轮定向复审 U-005/T-007 与 U-008/T-010，确认 GPU fallback 元数据、完成态规范校验和 acceptance 可恢复状态均已收敛。

### 修改内容

- 通过 `spec_progress.py acceptance-next-round` 启动第二轮定向验收，仅复审第一轮受影响的 U-005/T-007 与 U-008/T-010。
- 记录第二轮 first-wave 与 adversarial 四个 agent 的 PASS 报告，确认无新增 open issues、无 pending fixes。
- 通过 `spec_progress.py acceptance-finish docs\specs` 将 `docs/specs/acceptance_state.json` 状态推进为 `accepted`，并同步 `progress.md`、`tasks.md`、`spec.yml` 的最终验收时间与状态。

### 验证方法

- `python C:\Users\ny\.codex\plugins\cache\Useful-marketplace\spce-workflow\0.2.0\scripts\validate_spec.py docs\specs --pre-acceptance --color never`：通过，pre-acceptance passed。
- `.\.venv\Scripts\python.exe -m pytest tests/test_parallel_pose_engine.py tests/test_ui_backend_sessions.py::test_session_start_uses_parallel_pose_engine_when_workers_gt_one tests/test_ui_backend_sessions.py::test_pipeline_delegate_payload_reports_cpu_fallback -q`：通过，`7 passed`。
- `python C:\Users\ny\.codex\plugins\cache\Useful-marketplace\spce-workflow\0.2.0\scripts\validate_spec.py docs\specs --workflow design-first --color never`：通过，`36` 项检查全部通过。
- `python C:\Users\ny\.codex\plugins\cache\Useful-marketplace\spce-workflow\0.2.0\scripts\spec_progress.py acceptance-status docs\specs`：通过，`status=accepted`，open issues `0`，pending fixes `0`，pending agents `0`。

## 2026-06-14: 修复 final acceptance 第一轮发现的问题

### 问题描述

Spce final acceptance 第一轮 review/adversarial 审查发现 5 个收尾问题：完成态下 `validate_spec --workflow design-first` 因空 execution waves 无法复现 T-010 证据；T-010 文档中存在上一提交号和完成前措辞；并行 camera preview 显式 `delegate=gpu` 后 worker CPU fallback 的元数据未回传到 bridge；`docs/specs/acceptance_state.json` 未纳入提交；`docs/specs/acceptance-fixes.md` 仍是 pre-acceptance 占位文本。

### 修改内容

- 修复 Spce workflow 插件本机 `validate_spec.py`：当所有任务均为 done/skipped 时，空 execution waves 视为合法完成态。
- 在 `core/parallel_pose_engine.py` 中记录并合并 worker pipeline delegate 元数据，`apps/ui_backend.py` 在并行预览的 running 状态避免误报 `active=gpu`，并在 frame/final payload 中暴露真实 fallback。
- 更新 `tests/test_ui_backend_sessions.py`，覆盖并行预览 `delegate=gpu` 回退 CPU 时的 running/frame/final 元数据。
- 刷新 `docs/specs/acceptance-fixes.md` 为真实修复队列，并将 `docs/specs/acceptance_state.json` 纳入版本控制以保证 final acceptance 可恢复。

### 验证方法

- `.\.venv\Scripts\python.exe -m pytest tests/test_parallel_pose_engine.py tests/test_ui_backend_sessions.py::test_session_start_uses_parallel_pose_engine_when_workers_gt_one tests/test_ui_backend_sessions.py::test_pipeline_delegate_payload_reports_cpu_fallback -q`：通过，`7 passed`。
- `python C:\Users\ny\.codex\plugins\cache\Useful-marketplace\spce-workflow\0.2.0\scripts\validate_spec.py docs\specs --workflow design-first --color never`：通过，`36` 项检查全部通过。
- `python C:\Users\ny\.codex\plugins\cache\Useful-marketplace\spce-workflow\0.2.0\scripts\validate_spec.py docs\specs --resume --color never`：通过，`status=ready`，freeze ok。

## 2026-06-14: T-010 完成性能优化任务收尾与桌面整体验证

### 问题描述

T-010 要求在 T-002 至 T-009 全部关闭后完成收尾验证、进度同步和变更日志记录，并确认任务证据、Spce resume 状态、桌面整体验证和文本卫生门均可通过。收尾期间发现 Spce validator 在最后一个任务已 `active` 且无 `pending` 任务时无法计算 execution waves；同时 `LatestFrameBytes.bytes` 的 `Uint8Array` 类型需要收窄为 DOM `BlobPart` 可接受的 `ArrayBuffer` view，才能通过 Vue 类型检查。

### 修改内容

- 补齐 `frontend/src/bridge.ts` 中 `LatestFrameBytes.bytes` 的类型为 `Uint8Array<ArrayBuffer>`，保持 `new Uint8Array(response, 8)` 免拷贝视图语义不变。
- 按 T-010 验证门完成规范结构校验、resume 校验、`git diff --check` 和 `npm run verify:desktop`。
- 通过 `spec_progress.py start docs\specs T-010` 恢复当前任务 active 状态，并随后使用 `spec_progress.py complete docs\specs T-010` 记录最终证据。
- 更新本 `change.md` 置顶记录，作为本轮任务链的收尾审计入口。

### 验证方法

- `python C:\Users\ny\.codex\plugins\cache\Useful-marketplace\spce-workflow\0.2.0\scripts\validate_spec.py docs\specs --workflow design-first --color never`：通过，`36` 项检查全部通过。
- `python C:\Users\ny\.codex\plugins\cache\Useful-marketplace\spce-workflow\0.2.0\scripts\validate_spec.py docs\specs --resume --color never`：通过，`status=ready`，`current_task=T-010`，freeze ok。
- `git diff --check`：通过，仅有 Windows CRLF 提示，无空白错误。
- `npm run verify:desktop`：通过，frontend build、frontend smoke、Tauri cargo check、Python compile smoke 和 Python desktop regression tests；桌面回归 `152 passed`。

## 2026-06-14: T-009 优化 raw frame 传输、canvas 绘制与 latest-frame clone

### 问题描述

T-009 要求在保持 session/job/frameId 身份隔离、`frameId` 单调不回退和 latest-wins 背压语义不变的前提下，减少 raw frame 传输与绘制热路径上的额外拷贝和重复查找。

### 修改内容

- 在 `frontend/src/bridge.ts` 中将 latest-frame payload 从 `response.slice(8)` 改为 `new Uint8Array(response, 8)`，避免每帧额外复制 JPEG bytes。
- 在 `frontend/src/App.vue` 中缓存 preview canvas 的 2D context，停止/取消预览时重置缓存；保持 `createImageBitmap(blob)`、`drawImage()`、`lastDrawnFrameId` 与 `isDrawableFrame()` 守卫不变。
- 在 `frontend/src-tauri/src/lib.rs` 中将 latest-frame store 的 bytes 改为 `Arc<Vec<u8>>`，服务端取帧时 clone slot 只增加引用计数，减少锁内深拷贝。
- 更新 `frontend/scripts/frontend-smoke.mjs`，锁定 Uint8Array view、canvas context cache 和 `Arc<Vec<u8>>` 优化点。
- 通过 `spec_progress.py complete docs\specs T-009` 记录任务证据。

### 验证方法

- `npm --prefix frontend run test`：通过，`Frontend behavior smoke checks passed`。
- `npm run verify:tauri`：通过，`cargo check` finished。
- `git diff --exit-code -- frontend/src-tauri/capabilities/default.json`：通过，capabilities 无权限漂移。
- `.\.venv\Scripts\python.exe -m pytest tests/test_vue_tauri_acceptance_gaps.py tests/test_ui_backend_sessions.py -q`：通过，`24 passed`。

## 2026-06-14: T-008 实施单次 raw / body_core 特征复用

### 问题描述

用户独立批准 `T-008` 高风险评分变更后，可以实施单次抽帧复用。原路径在双模板规则评分、关节误差分析和 body_core front/side 模板匹配中会对同一视频重复打开 `VideoCapture` 并重复推理。该优化必须保持 MediaPipe VIDEO-mode 全程状态、`valid_mask`、规则评分、body_core 授权元数据和 golden 输出不漂移。

### 修改内容

- 在 `core/rule_scoring.py` 新增 `Pose33RawSeries`、`extract_pose_raw_series()` 和 `slice_pose_raw_series()`，保留 `extract_pose_raw()` 外部兼容行为。
- 在 `core/action_compare.py` 中让 `compare_video_to_dual_templates()` 的规则评分和关节误差分析复用一次 full-video raw Pose33 + `valid_mask`，再按 front/side 或 active segment 只读切片。
- 在 `core/body_core_compare.py` 中为 `match_body_core_template()` 增加 `precomputed_features` 参数，并校验预抽 backend 与请求 backend 一致。
- 在 `batch/batch_dual_compare.py` 的 body_core 调试批处理中，每个学生视频只调用一次 `extract_body_core_features()`，front/side 两个模板匹配共享该结果。
- 新增 `tests/test_t008_single_pass_reuse.py`，覆盖 raw series 切片等价、双模板只抽一次 raw、body_core 预抽特征复用和 backend mismatch 拒绝。
- 通过 `spec_progress.py complete docs\specs T-008` 记录二次审批、实现范围和验证证据。

### 验证方法

- `.\.venv\Scripts\python.exe -m py_compile core\rule_scoring.py core\action_compare.py core\body_core_compare.py batch\batch_dual_compare.py tests\test_t008_single_pass_reuse.py`：通过。
- `.\.venv\Scripts\python.exe -m pytest tests/test_t008_single_pass_reuse.py -q`：通过，`4 passed`。
- `.\.venv\Scripts\python.exe -m pytest tests/test_batch_backend_args.py tests/test_body_core_layout.py -q`：通过，`37 passed`。
- `.\.venv\Scripts\python.exe -m pytest tests/test_pose33_v3_golden.py -q`：通过，`16 passed`。
- `.\.venv\Scripts\python.exe -m pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py tests/test_rule_availability.py tests/test_tech_eval_contract.py -q`：通过，`49 passed`。
- `.\.venv\Scripts\python.exe -m pytest tests/test_body_core_layout.py tests/test_batch_backend_args.py tests/test_yolo_backend_contract.py -q`：通过，`59 passed`。
- `.\.venv\Scripts\python.exe analysis\offline_matching_profile.py --fixture-smoke --out outputs\perf_baseline\t008_after`：通过，写入 `offline_matching_profile.json` / `.csv`。

## 2026-06-14: 发布前排除 Tauri sidecar onedir 生成目录

### 问题描述

T-005 将 sidecar 切换为 PyInstaller onedir 后，本地构建会生成 `frontend/src-tauri/resources/vision-ui-backend/` 目录。该目录包含大量 Python runtime、MediaPipe、OpenCV、numpy/scipy 等打包产物，属于本地生成资源，不应纳入 Git 提交。

### 修改内容

- 在 `.gitignore` 中新增 `frontend/src-tauri/resources/vision-ui-backend/`，防止 onedir sidecar resources 被误提交。
- 保持 `scripts/build-tauri-sidecar.ps1` 与 Tauri resources 配置不变；构建时仍会生成并复制该目录，源码仓库只提交构建规则和 smoke 测试。

### 验证方法

- `git status --short --untracked-files=all`：确认 onedir resources 目录从待提交未跟踪列表中排除。
- `git diff --check`：通过，仅有 Windows CRLF 提示，无空白错误。

## 2026-06-14: T-008 产出单次抽帧复用二次审批包并停在门禁

### 问题描述

性能优化清单中的 B2 / C1 / C4 / C5 指向同一类高收益优化：同一视频在双模板匹配、规则评分、关节误差分析、batch raw 导出和 body_core front/side 匹配中存在 2-5 次重复推理。但该优化会触碰 MediaPipe VIDEO-mode 时序态、`valid_mask`、规则评分和 body_core 授权元数据，首次 `批准规范，启动执行` 不授权实现单次抽帧业务代码。

### 修改内容

- 新增 `docs/specs/t008_single_pass_frame_gate.md`，作为 T-008 二次审批包。
- 审批包梳理当前重复推理边界：`compare_video_to_dual_templates()` 主匹配、`extract_pose_raw()` 规则评分与误差分析、`batch_dual_compare.py --export_raw`、`body_core_compare.py` MediaPipe / YOLO 调试路径。
- 明确后续若独立批准，最小实现只能新增 raw 序列载体、只读切片 helper 和受控复用调用点，不得合并 seek+短 warm-up、DTW 语义变更、规则阈值变更、YOLO 授权元数据变更或 golden 重生。
- 写入真实 MediaPipe VIDEO-mode 验证矩阵、fixture replay 验证矩阵、回滚方案和二次审批建议。
- 通过 `spec_progress.py block docs\specs T-008` 记录门禁：因尚未收到独立批准短语 `批准 T-008 高风险评分变更，启动执行`，T-008 停在人工审批，不修改单次抽帧相关业务代码，也不继续 T-009。

### 验证方法

- `python C:\Users\ny\.codex\plugins\cache\Useful-marketplace\spce-workflow\0.2.0\scripts\validate_spec.py docs/specs/ --workflow design-first --color never`：通过，`36` 项检查全部通过。
- `python C:\Users\ny\.codex\plugins\cache\Useful-marketplace\spce-workflow\0.2.0\scripts\validate_spec.py docs/specs/ --sync-check --color never`：通过，`issues=[]`、`suggestions=[]`。
- `python C:\Users\ny\.codex\plugins\cache\Useful-marketplace\spce-workflow\0.2.0\scripts\spec_progress.py status docs\specs`：`progress_status=Blocked`，`current_task=T-008`，`blocked=1`，冻结基线 `ok=true`。

## 2026-06-14: T-007 贯通 MediaPipe GPU delegate 显式 opt-in 与 CPU fallback

### 问题描述

性能优化清单指出 `PipelineConfig.delegate` 虽已存在，但生产入口没有显式传递 GPU delegate，也缺少统一的 GPU 初始化失败回退证据。T-007 要求 GPU 只能显式 opt-in，默认 CPU 不变，正式评分和 full tech_eval 不进入 GPU 默认链路。

### 修改内容

- 在 `core/vision_pipeline.py` 中统一校验 `delegate=cpu|gpu`，并让 `MediaPipePipeline` 在显式 GPU 初始化失败时回退 CPU，记录 `requested_delegate`、`active_delegate` 和 `delegate_fallback_reason`。
- 在 `apps/main.py` 增加 `--delegate cpu|gpu`，默认 `cpu`；单线程、latest-frame smoke、离线多 worker 和实时并行路径只在显式传入时请求 GPU。
- 在 `apps/ui_backend.py` 增加 bridge `delegate` 参数解析与非法值拒绝；缓存键加入 delegate，状态和结果暴露 delegate requested/active/fallback 元数据。
- 在 `core/parallel_pose_engine.py` 的默认 pipeline factory 中透传 delegate，避免多 worker 预览路径遗漏显式 GPU 请求。
- 补充回归测试：锁定默认 CPU、显式 GPU、GPU 创建失败回 CPU、bridge delegate 解析与元数据、CLI 显式 opt-in。
- 通过 `spec_progress.py complete docs\specs T-007` 记录任务证据。

### 验证方法

- `.\.venv\Scripts\python.exe -m py_compile core\vision_pipeline.py apps\main.py apps\ui_backend.py core\backend_router.py`：通过。
- `.\.venv\Scripts\python.exe -m pytest tests/test_mediapipe_delegate_config.py tests/test_s5_gpu_recheck.py tests/test_backend_routing_contract.py tests/test_pose33_v3_golden.py -q`：通过，`48 passed`。
- `.\.venv\Scripts\python.exe -m pytest tests/test_ui_backend_sessions.py tests/test_s5_realtime_latest_frame.py tests/test_s5_hands_toggle.py -q`：通过，`31 passed`。
- `git diff --check -- core/vision_pipeline.py apps/main.py apps/ui_backend.py core/backend_router.py core/parallel_pose_engine.py tests/test_mediapipe_delegate_config.py tests/test_s5_gpu_recheck.py tests/test_backend_routing_contract.py tests/test_ui_backend_sessions.py tests/test_s5_realtime_latest_frame.py`：通过，仅有 Windows CRLF 提示，无空白错误。

## 2026-06-14: T-006 向量化 DTW、normalizer 与误差聚合热路径

### 问题描述

性能优化清单指出 DTW 局部代价、姿态归一化、规则表构建和双模板关节误差统计存在 Python 层热循环。T-006 要求只做数值等价优化，金标、规则状态、`valid_mask` 语义和误差统计不得漂移。

### 修改内容

- 在 `core/pose_features.py` 中预计算 DTW 局部代价矩阵，保留原动态规划 tie-break 与回溯逻辑。
- 将 `normalize_pose_xy_v1` / `normalize_pose_xy` / `normalize_pose_xy_v3` / `normalize_pose_body_core_v1` 的坐标归一化、旋转和裁剪改为批量矩阵计算。
- 在 `core/action_compare.py` 中将双模板 `enable_error_analysis` 的 path 关节距离统计改为批量距离矩阵 + `valid_mask` 过滤，输出字段和顺序保持不变。
- 在 `core/rule_scoring.py` 中将规则表缓存为模块级 `_RULES`，并用 `valid_mask[:, idxs].all(axis=1)` 预计算每条规则的帧有效性；出拳类规则仍保留“伸展明显才计有效帧”的原语义。
- 通过 `spec_progress.py complete docs\specs T-006` 记录任务证据。

### 验证方法

- `.\.venv\Scripts\python.exe -m pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py tests/test_rule_availability.py tests/test_tech_eval_contract.py -q`：通过，`49 passed`。
- `.\.venv\Scripts\python.exe -m pytest tests/test_body_core_layout.py tests/test_layout_shape_param.py tests/test_s5_offline_profile.py -q`：通过，`39 passed`。
- `.\.venv\Scripts\python.exe -m py_compile core\pose_features.py core\action_compare.py core\rule_scoring.py`：通过。
- `git diff --check -- core/pose_features.py core/action_compare.py core/rule_scoring.py tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py tests/test_rule_availability.py tests/test_tech_eval_contract.py`：通过，仅有 Windows CRLF 提示，无空白错误。

## 2026-06-14: T-003 将实时 camera preview 接入 ParallelPoseEngine

### 问题描述

性能优化任务要求在不改变默认预览路径的前提下，让实时 camera preview 在 `workers>1` 时可以使用多 worker 推理；同时必须保证默认 `workers=1` 保守不变、MediaPipe pipeline 不跨线程共享，停止后的 late response 不复活终态。

### 修改内容

- 在 `apps/ui_backend.py` 中增加并行 camera preview 路径：仅当 `sourceKind=camera`、`workers>1` 且 backend route 为 MediaPipe 时启用 `ParallelPoseEngine`。
- 默认 `workers=1`、视频文件预览和 YOLO 路由继续走既有单管线 VIDEO-mode 路径；并行路径使用独立 IMAGE-mode pipeline factory，每个 worker 独占实例。
- 并行 camera loop 保留 latest-wins/低延迟语义，记录 `parallelPreview`、`workersUsed`、`capturedFrames`、`submittedFrames`、`droppedFrames`、`renderedFrames` 等证据字段。
- 补充 `tests/test_ui_backend_sessions.py` 回归：锁定单 worker 不启用并行、多 worker 不调用旧单管线且创建独立 worker pipeline。
- 通过 `spec_progress.py complete docs\specs T-003` 记录任务证据。

### 验证方法

- `.\.venv\Scripts\python.exe -m pytest tests/test_parallel_pose_engine.py tests/test_ui_backend_sessions.py tests/test_s5_realtime_latest_frame.py -q`：通过，`25 passed`。
- `git diff --check -- apps/ui_backend.py tests/test_ui_backend_sessions.py core/parallel_pose_engine.py tests/test_parallel_pose_engine.py tests/test_s5_realtime_latest_frame.py`：通过，仅有 Windows CRLF 提示，无空白错误。

## 2026-06-14: T-005 将 Tauri sidecar 从 onefile 改为 onedir

### 问题描述

性能优化清单指出安装版 Python bridge sidecar 使用 PyInstaller onefile，会在冷启动时自解压 MediaPipe 等运行时文件。T-005 要求改为 onedir 打包，确保 Tauri 安装包能找到 sidecar，同时不得放宽 `torch` / `ultralytics` / `core.yolo_adapter` 等 heavy excludes，也不能引入 Tauri capabilities 权限漂移。

### 修改内容

- 将 `ui_backend_sidecar.spec` 切换为 PyInstaller onedir：`EXE(... exclude_binaries=True)` + `COLLECT(...)`，输出 `dist/vision-ui-backend/vision-ui-backend.exe`。
- 更新 `scripts/build-tauri-sidecar.ps1`：构建前清理旧 onedir、旧 `dist\vision-ui-backend.exe`、旧 resources 单文件 exe；构建后复制整个 `dist\vision-ui-backend` 目录到 `frontend\src-tauri\resources\vision-ui-backend`。
- 更新 `frontend/src-tauri/src/lib.rs`：安装版 bridge 路径解析改为 `resource_dir/vision-ui-backend/vision-ui-backend.exe`；开发模式仍回退到 `.venv\Scripts\python.exe -u apps/ui_backend.py`。
- 保持 `frontend/src-tauri/tauri.conf.json` 资源根映射，确保 `npm run verify:tauri` 在未生成 sidecar 目录的干净环境也能 `cargo check`；实际构建脚本仍只放入 onedir 资源。
- 更新 `tests/test_windows_packaging_smoke.py`，覆盖 onedir spec、脚本清理/复制、Rust onedir 路径、heavy excludes 和 packaged sidecar ping。
- 通过 `spec_progress.py complete docs\specs T-005` 记录任务证据；生成的 `dist/`、`frontend/dist/`、`frontend/src-tauri/target/` 和 resources sidecar 产物不纳入源码提交范围。

### 验证方法

- `npm run build:sidecar`：通过，PyInstaller onedir 已复制到 `frontend\src-tauri\resources\vision-ui-backend`。
- `npm run verify:tauri`：通过，`cargo check` finished。
- `npm run package:windows`：通过，NSIS 安装器生成于 `frontend\src-tauri\target\release\bundle\nsis\Vision 动作识别与评分_0.1.0_x64-setup.exe`。
- `git diff --exit-code -- frontend/src-tauri/capabilities/default.json`：通过，capabilities 无权限漂移。
- `.\.venv\Scripts\python.exe -m pytest tests/test_windows_packaging_smoke.py -q`：通过，`10 passed`。

## 2026-06-14: T-004 为 batch dual-compare 与 skeleton export 增加跨视频并行

### 问题描述

性能优化清单指出 `batch_dual_compare.py` 与 `batch_export_skeleton.py` 仍按视频串行处理，MediaPipe / YOLO 推理期间多核利用不足。该任务只允许做跨视频编排并行，不能共享 MediaPipe pipeline，也不能实现 T-008 的单次抽帧复用或改变 YOLO 授权语义。

### 修改内容

- 为 `batch/batch_dual_compare.py` 增加 `--workers`，在 pose33 默认路径和 body_core_v1 调试路径中使用跨视频 `ThreadPoolExecutor`。
- 保持每个 worker 独立处理单个视频，`compare_video_to_dual_templates(... workers=1)` 不共享视频内 pipeline；主线程按输入 index 排序写 `compare_results.csv` / `compare_results.jsonl`。
- 为 `batch/batch_export_skeleton.py` 增加 `--workers`，先在主线程分配稳定输出路径和去重文件名，再跨视频并发导出，最终按输入顺序写 `manifest.csv`。
- 补充回归测试：覆盖 dual-compare 并发完成乱序时的 CSV/JSONL 稳定顺序、body_core/Yolo 元数据不漂移，以及 skeleton export 并发 manifest 顺序稳定。
- 通过 `spec_progress.py complete docs\specs T-004` 记录任务证据；未修改单次抽帧复用业务代码。

### 验证方法

- `.\.venv\Scripts\python.exe -m py_compile batch\batch_dual_compare.py batch\batch_export_skeleton.py`：通过，退出码 0。
- `.\.venv\Scripts\python.exe -m pytest tests/test_batch_backend_args.py tests/test_yolo_backend_contract.py -q`：通过，`38 passed`。

## 2026-06-14: T-002 落地预览默认降载与常量调档

### 问题描述

性能优化清单指出 Vue/Tauri 实时预览仍默认使用 `full` 姿态模型并开启手部检测，同时预览帧 JPEG 质量、长边和发布频率偏高。该问题只影响桌面预览体验，不应改变正式评分、CLI/Tkinter 默认评分链路或模板/tech_eval 档位。

### 修改内容

- 将 Vue/Tauri 预览默认改为 `poseVariant=lite`、`enableHands=false`，手部检测仍保留为显式可开启开关。
- 将 bridge 预览默认保持一致：缺省 `session.start` / `session.warmup` 使用 lite + hands off。
- 调低预览副本常量：JPEG 质量 58、长边 720、帧事件最小间隔 1/20s、capture idle sleep 3ms；录制与正式评分输入不受影响。
- 补充回归：锁定预览默认、预览瘦身常量和前端默认值；恢复 Tkinter `UiState.out_path` 兼容字段以通过既有 hands toggle 测试。
- 通过 `spec_progress.py complete docs\specs T-002` 记录任务证据。

### 验证方法

- `npm --prefix frontend run test`：通过，`Frontend behavior smoke checks passed`。
- `.\.venv\Scripts\python.exe -m pytest tests/test_ui_backend_sessions.py tests/test_s5_hands_toggle.py tests/test_s5_realtime_latest_frame.py -q`：通过，`25 passed`。

## 2026-06-14: T-001 解除 high_quality routing 阻塞并完成基线采证

### 问题描述

用户批准当前性能优化 Spce 规范并要求启动执行。`T-001` 初次采证时复现 high_quality backend routing 子集失败：`core/backend_router.py:249` 调用 `_mediapipe_body_core(..., model_profile=...)` 触发 `TypeError`，阻止后续性能优化任务继续推进。用户随后批准按 Bugfix / 恢复既有预期行为解除该 blocker，范围限定为恢复既有 backend routing 合同测试。

### 修改内容

- 在 `core/backend_router.py` 中让 `_mediapipe_body_core` 接受可选 `model_profile`，消除 helper 签名与调用点不匹配。
- 保持 high_quality + YOLO26L available 的既有合同：`route_for_analysis(... quality_profile=high_quality, enable_hands=false, yolo26l=true)` 路由到 YOLO internal body-only，`doCompare=true` 仍优先 MediaPipe formal compare。
- 在 `analysis/bench_annotate_fps.py` 补齐与 `analysis/offline_matching_profile.py` 一致的 repo-root `sys.path` 注入，使 T-001 规范中的 `--env-only` 原命令可从仓库根目录直接运行。
- 通过 `spec_progress.py complete docs\specs T-001 --evidence ...` 记录 T-001 完成证据；未实施 T-002 及后续性能优化。

### 验证方法

- `.\.venv\Scripts\python.exe analysis\offline_matching_profile.py --fixture-smoke --out outputs\perf_baseline\offline_fixture`：通过，写入 `outputs\perf_baseline\offline_fixture\offline_matching_profile.json` 与 `.csv`。
- `.\.venv\Scripts\python.exe analysis\bench_annotate_fps.py --env-only --out outputs\perf_baseline\gpu_env`：通过，写入 `outputs\perf_baseline\gpu_env\gpu_recheck_env.json`。
- `.\.venv\Scripts\python.exe -m pytest tests/test_backend_routing_contract.py::test_offline_high_quality_yolo26l_available_routes_internal_body_only tests/test_backend_routing_contract.py::test_high_quality_template_compare_stays_mediapipe_formal_compare -q`：通过，`2 passed`。
- `.\.venv\Scripts\python.exe -m pytest tests/test_s5_offline_profile.py tests/test_s5_gpu_recheck.py tests/test_pose33_v3_golden.py -q`：通过，`31 passed`。

## 2026-06-14: 补强性能优化 Spce 规范门禁

### 问题描述

针对性能优化 Spce 文档的 P1/P2/P3 审查意见，初稿存在语义级门禁不足：`T-008` 高风险评分任务仍被放入一次总审批链，`T-001` 缺少真实 profile 采证命令，`T-010` 将 pre-acceptance/final acceptance 写成任务内循环，部分任务并行标记与共享文件冲突，且预览授权、GPU fallback、Tauri 权限漂移和 acceptance 修复队列约束不够硬。

### 修改内容

- 补强 `docs/specs/design.md` / `requirements.md`：明确 `T-008` 首次批准只允许产出二次审批包，不授权单次抽帧业务实现；正式实施需独立批准短语 `批准 T-008 高风险评分变更，启动执行`。
- 补强 `docs/specs/tasks.md`：为 `T-001` 增加 `offline_matching_profile.py --fixture-smoke`、`bench_annotate_fps.py --env-only` 与 high_quality backend routing 子集采证；记录已知 `core/backend_router.py:249` `_mediapipe_body_core(..., model_profile=...)` 参数不匹配失败为实施阻塞判据。
- 修正任务依赖与并行标记：`T-003` 依赖 `T-002`，`T-009` 依赖 `T-005` 和 `T-008`；`T-002/T-003`、`T-005/T-009` 不再被同 wave 并行执行。
- 将 final acceptance 从 `T-010` 中拆出为“任务完成后的验收入口”，补充 `--pre-acceptance` 命令和 `docs/specs/acceptance-fixes.md` 修复队列占位。
- 补强 `scoreAuthorized=false` / `displayScope=limited|internal`、batch 输出顺序、GPU fallback、`npm run verify:tauri` 与 `frontend/src-tauri/capabilities/default.json` 权限漂移检查。
- 更新 `docs/specs/spec.yml`：同步新 task graph、hash，并增加 `manual_gates` 显式记录 `T-008` 二次审批门禁；更新 `progress.md`，避免 “Approved specs” 误导。

### 验证方法

- `.\.venv\Scripts\python.exe -m pytest tests/test_backend_routing_contract.py::test_offline_high_quality_yolo26l_available_routes_internal_body_only tests/test_backend_routing_contract.py::test_high_quality_template_compare_stays_mediapipe_formal_compare -q`：复现 1 failed / 1 passed，失败点为 `core/backend_router.py:249`，已作为 `T-001` 阻塞判据写入规范。
- `python C:\Users\ny\.codex\plugins\cache\Useful-marketplace\spce-workflow\0.2.0\scripts\validate_spec.py docs\specs --workflow design-first --color never`：36 项检查全部通过。
- `python C:\Users\ny\.codex\plugins\cache\Useful-marketplace\spce-workflow\0.2.0\scripts\validate_spec.py docs\specs --resume --color never`：`status=ready`，`current_task=T-001`，无 issues / warnings，freeze ok。
- `python C:\Users\ny\.codex\plugins\cache\Useful-marketplace\spce-workflow\0.2.0\scripts\validate_spec.py docs\specs --sync-check --color never`：无 issues / suggestions。

## 2026-06-14: 基于性能优化清单生成 Spce 规范

### 问题描述

需要根据 `docs/performance_optimization_inventory.md` 生成对应的 Spce workflow 文档，把性能优化清单转化为可审批、可恢复、可验收的设计与任务图。本轮只生成规范，不进入业务代码实施。

### 修改内容

- 新建 `docs/specs/design.md`：按 Design-First 高层设计整理性能优化执行轨道、系统边界、默认评分保护、YOLO 授权边界、风险与验证策略。
- 新建 `docs/specs/requirements.md`：从设计派生 REQ/AC/NFR，并记录 intake handoff、需求分析结论、非目标和审批边界。
- 新建 `docs/specs/tasks.md`：拆分 10 个 Spce 任务，覆盖基线证据、预览/编排/打包、数值等价优化、GPU opt-in、高风险抽帧、传输优化和最终验收。
- 新建并同步 `docs/specs/progress.md`、`docs/specs/spec.yml`：记录 `design-first`、`strict`、`approval=pending`、当前任务 `T-001` 和可计算任务图。

### 验证方法

- `python C:\Users\ny\.codex\plugins\cache\Useful-marketplace\spce-workflow\0.2.0\scripts\validate_spec.py docs\specs --workflow design-first --color never`：36 项检查全部通过。
- `python C:\Users\ny\.codex\plugins\cache\Useful-marketplace\spce-workflow\0.2.0\scripts\validate_spec.py docs\specs --resume --color never`：`status=ready`，`current_task=T-001`，无 issues / warnings，freeze ok。
- `python C:\Users\ny\.codex\plugins\cache\Useful-marketplace\spce-workflow\0.2.0\scripts\validate_spec.py docs\specs --sync-check --color never`：无 issues / suggestions。

## 2026-06-14: 变更日志归档与重建

### 问题描述

当前 `change.md` 累积过长（约 3000 行，覆盖 2026-05-30 ~ 2026-06-14），需要将既有记录归档并重建当前日志入口。沿用上次（2026-05-30）「归档 + 重建」的做法。

### 修改内容

- 将旧 `change.md`（2026-05-30 ~ 2026-06-14，含 YOLO 迁移 S0–S6、Vue/Tauri 迁移与桌面验收、性能优化清单等记录）通过 `git mv` 重命名为 `change（2026.5~2026.6）.md`。
- 新建当前 `change.md`，作为后续任务记录入口（最新记录置顶）。
- 更新 `CLAUDE.md`、`AGENTS.md`「任务完成规范」中的 change.md 归档规则：明确 `change.md` 累积过长时按时间段归档为 `change（<起>~<止>）.md` 并重建空 `change.md`；历史归档现为 `change（start~2026.5）.md`、`change（2026.5~2026.6）.md`。

### 验证方法

- `git status -sb` 确认重命名（R）与新建文件。
- `rg -n "change（2026.5~2026.6）.md|change（start~2026.5）.md" CLAUDE.md AGENTS.md` 确认两处规则引用已更新到新归档清单。
