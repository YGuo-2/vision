# Design-First 任务清单 (Task Breakdown)

> **功能名称：** 性能优化清单落地
> **关联规范：** `docs/specs/design.md` · `docs/specs/requirements.md`
> **状态：** Accepted
> **当前任务：** n/a
> **进度：** 10 / 10 已完成
> **最后更新：** 2026-06-15 00:10:27

---

## 执行规则

1. 设计优先：任务必须首先满足 `design.md` 中的默认路径保护、YOLO 授权边界和分轨执行约束。
2. 受控入口：批准后先运行 `spec_progress.py approve docs/specs/ --evidence "<批准依据>"` 或 MCP `spec_approve` 冻结基线；任务开始、完成、阻塞、跳过必须通过进度工具更新。
3. 需求从设计派生：若 `requirements.md` 与 `design.md` 冲突，必须暂停实现、运行 `sync-check --write` 标记 `reapproval-required`，更新文档并重新获得批准。
4. 单任务约束：每个任务完成后必须记录验证证据，才可标记完成。
5. 禁止越界：不得实现未在 `design.md` 明确支撑的能力。
6. 冻结边界：批准后 `design.md`、`requirements.md` 和任务计划被冻结；只允许通过工具更新进度字段、证据、阻塞原因、完成日志、`progress.md` 和当前任务索引。
7. 验收修复隔离：final acceptance 发现的问题不得追加到本文件；修复项必须写入 `docs/specs/acceptance-fixes.md`。
8. 高风险评分门禁：首次 `批准规范，启动执行` 不授权 `T-008` 的单次抽帧业务实现；`T-008` 只能产出风险评估和二次审批包。实施必须另等 `批准 T-008 高风险评分变更，启动执行`，并重新冻结基线或进入独立 Spce 规范。

---

## 验证标准与证据规则

- 每个任务的验证证据必须包含实际命令和结果摘要。
- 触碰评分语义、DTW、规则评分或 MediaPipe pipeline 的任务必须运行金标或合同测试。
- 触碰 Vue/Tauri bridge、raw frame 或 sidecar 的任务必须运行前端 smoke、相关 Python bridge 测试或 Windows packaging smoke。
- 触碰 Tauri Rust 或 capabilities 的任务必须运行 `npm run verify:tauri`，并说明 `frontend/src-tauri/capabilities/default.json` 是否发生权限漂移。
- 每批完成后更新 `change.md`，最新记录置顶。

---

## 阶段 1：基线与保护栏

- [x] **T-001:** 固化性能基线、合同边界和执行前证据
  - 状态: done
  - 验证证据: cmd: .\\.venv\\Scripts\\python.exe analysis\\offline_matching_profile.py --fixture-smoke --out outputs\\perf_baseline\\offline_fixture => exit 0, wrote offline_matching_profile.json/.csv; cmd: .\\.venv\\Scripts\\python.exe analysis\\bench_annotate_fps.py --env-only --out outputs\\perf_baseline\\gpu_env => exit 0, wrote gpu_recheck_env.json; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_backend_routing_contract.py::test_offline_high_quality_yolo26l_available_routes_internal_body_only tests/test_backend_routing_contract.py::test_high_quality_template_compare_stays_mediapipe_formal_compare -q => exit 0, 2 passed; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_s5_offline_profile.py tests/test_s5_gpu_recheck.py tests/test_pose33_v3_golden.py -q => exit 0, 31 passed
  - 完成时间: 2026-06-14 20:09:37
  - 备注: 解除 T-001 blocker：恢复 high_quality+YOLO26L available 既有 backend routing 合同；bench_annotate_fps.py 可从仓库根目录原命令运行；未实施 T-002 及后续性能优化。
  - 阻塞原因: T-001 采证已执行：offline profile 原命令通过并写入 outputs/perf_baseline/offline_fixture/offline_matching_profile.json 与 .csv；GPU/env 快照原命令失败，ModuleNotFoundError: No module named 'core'，使用临时 PYTHONPATH=仓库根目录后写入 outputs/perf_baseline/gpu_env/gpu_recheck_env.json；high_quality backend routing 子集原命令复现 1 failed / 1 passed，失败为 core/backend_router.py:249 TypeError: _mediapipe_body_core() got an unexpected keyword argument 'model_profile'；相关 pytest tests/test_s5_offline_profile.py tests/test_s5_gpu_recheck.py tests/test_pose33_v3_golden.py -q 通过，31 passed。按已批准规范与用户硬约束，T-001 阻塞性能优化实施，需先转 Bugfix 或重新审批，未修改业务代码。
  - 涉及文件: `docs/performance_optimization_inventory.md`, `analysis/offline_matching_profile.py`, `analysis/bench_annotate_fps.py`, `core/backend_router.py`, `tests/test_backend_routing_contract.py`, `tests/test_s5_offline_profile.py`, `tests/test_s5_gpu_recheck.py`, `tests/test_pose33_v3_golden.py`
  - 验证命令: `.\.venv\Scripts\python.exe analysis\offline_matching_profile.py --fixture-smoke --out outputs\perf_baseline\offline_fixture`; `.\.venv\Scripts\python.exe analysis\bench_annotate_fps.py --env-only --out outputs\perf_baseline\gpu_env`; `.\.venv\Scripts\python.exe -m pytest tests/test_backend_routing_contract.py::test_offline_high_quality_yolo26l_available_routes_internal_body_only tests/test_backend_routing_contract.py::test_high_quality_template_compare_stays_mediapipe_formal_compare -q`; `.\.venv\Scripts\python.exe -m pytest tests/test_s5_offline_profile.py tests/test_s5_gpu_recheck.py tests/test_pose33_v3_golden.py -q`
  - 依赖: 无
  - 风险: high
  - 覆盖: REQ-001, REQ-002, REQ-005, NFR-001
  - 可并行: 否
  - 验收口径: 记录执行前 profile 基线、GPU 环境快照和 backend routing 合同边界；若 high_quality 路由子集仍因 `core/backend_router.py` 的 `_mediapipe_body_core(..., model_profile=...)` 参数不匹配失败，则阻塞性能优化实施并先走 Bugfix 或重新审批；本任务不修改业务代码
  - 已知审查证据: 2026-06-14 使用 `.\.venv\Scripts\python.exe -m pytest tests/test_backend_routing_contract.py::test_offline_high_quality_yolo26l_available_routes_internal_body_only tests/test_backend_routing_contract.py::test_high_quality_template_compare_stays_mediapipe_formal_compare -q` 复现 1 failed / 1 passed，失败点为 `core/backend_router.py:249` 的 `TypeError`
  - 预估工程量: 1-2 小时

---

## 阶段 2：低数值风险的预览、编排与打包优化

- [x] **T-002:** 落地预览默认降载与预览常量调档
  - 状态: done
  - 验证证据: cmd: npm --prefix frontend run test => exit 0, Frontend behavior smoke checks passed; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_ui_backend_sessions.py tests/test_s5_hands_toggle.py tests/test_s5_realtime_latest_frame.py -q => exit 0, 25 passed
  - 完成时间: 2026-06-14 20:15:28
  - 备注: 实时预览默认降载为 lite + hands off；预览 JPEG/尺寸/FPS/idle sleep 常量调低；保持正式评分/CLI/Tkinter 默认路径不变，并恢复 Tkinter UiState.out_path 兼容字段以通过既有测试。
  - 涉及文件: `apps/ui_backend.py`, `frontend/src/App.vue`, `frontend/scripts/frontend-smoke.mjs`, `tests/test_ui_backend_sessions.py`, `tests/test_s5_hands_toggle.py`, `tests/test_s5_realtime_latest_frame.py`
  - 验证命令: `npm --prefix frontend run test`; `.\.venv\Scripts\python.exe -m pytest tests/test_ui_backend_sessions.py tests/test_s5_hands_toggle.py tests/test_s5_realtime_latest_frame.py -q`
  - 依赖: T-001
  - 风险: medium
  - 覆盖: REQ-003, AC-003.1, AC-003.2, NFR-001
  - 可并行: 是
  - 验收口径: 只影响预览副本和预览能力声明，不改变正式评分默认链路
  - 预估工程量: 2-4 小时

- [x] **T-003:** 将实时 camera preview 接入 `ParallelPoseEngine`
  - 状态: done
  - 验证证据: cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_parallel_pose_engine.py tests/test_ui_backend_sessions.py tests/test_s5_realtime_latest_frame.py -q => exit 0, 25 passed; cmd: git diff --check -- apps/ui_backend.py tests/test_ui_backend_sessions.py core/parallel_pose_engine.py tests/test_parallel_pose_engine.py tests/test_s5_realtime_latest_frame.py => exit 0, only CRLF warnings
  - 完成时间: 2026-06-14 20:56:06
  - 备注: 实时 camera preview 在 MediaPipe 路由且 workers>1 时接入 ParallelPoseEngine，每个 worker 使用独立 IMAGE-mode pipeline factory；默认 workers=1、视频文件和 YOLO 路由继续走既有单管线路径；late stop 通过 ctx.stopped/capture_stop/engine.close 保持终态不复活。
  - 涉及文件: `apps/ui_backend.py`, `core/parallel_pose_engine.py`, `tests/test_parallel_pose_engine.py`, `tests/test_ui_backend_sessions.py`, `tests/test_s5_realtime_latest_frame.py`
  - 验证命令: `.\.venv\Scripts\python.exe -m pytest tests/test_parallel_pose_engine.py tests/test_ui_backend_sessions.py tests/test_s5_realtime_latest_frame.py -q`
  - 依赖: T-002
  - 风险: medium
  - 覆盖: REQ-003, NFR-004
  - 可并行: 否
  - 验收口径: `workers>1` 时启用多 worker，默认 workers=1 行为保守不变，late response 不复活终态
  - 预估工程量: 4-6 小时

- [x] **T-004:** 为 batch dual-compare 与 skeleton export 增加跨视频并行
  - 状态: done
  - 验证证据: cmd: .\\.venv\\Scripts\\python.exe -m py_compile batch\\batch_dual_compare.py batch\\batch_export_skeleton.py => exit 0; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_batch_backend_args.py tests/test_yolo_backend_contract.py -q => exit 0, 38 passed
  - 完成时间: 2026-06-14 20:24:52
  - 备注: 为 batch dual-compare 与 skeleton export 增加 --workers 跨视频并行；每个 worker 独立执行视频处理，主线程按输入 index 排序写 CSV/JSONL/manifest；YOLO body_core 授权元数据保持 score_authorized=False/internal/unvalidated；未实现单次抽帧复用。
  - 涉及文件: `batch/batch_dual_compare.py`, `batch/batch_export_skeleton.py`, `tests/test_batch_backend_args.py`, `tests/test_yolo_backend_contract.py`
  - 验证命令: `.\.venv\Scripts\python.exe -m py_compile batch\batch_dual_compare.py batch\batch_export_skeleton.py`; `.\.venv\Scripts\python.exe -m pytest tests/test_batch_backend_args.py tests/test_yolo_backend_contract.py -q`
  - 依赖: T-001
  - 风险: medium
  - 覆盖: REQ-001, REQ-002, NFR-004
  - 可并行: 是
  - 验收口径: 每线程独立 pipeline，manifest/CSV 输出顺序与输入顺序稳定，YOLO 授权元数据不漂移；测试必须覆盖并行结果排序
  - 预估工程量: 3-5 小时

- [x] **T-005:** 将 sidecar 从 PyInstaller onefile 改为 onedir
  - 状态: done
  - 验证证据: cmd: npm run build:sidecar => exit 0, PyInstaller onedir copied to frontend\\src-tauri\\resources\\vision-ui-backend; cmd: npm run verify:tauri => exit 0, cargo check finished; cmd: npm run package:windows => exit 0, NSIS installer generated at frontend\\src-tauri\\target\\release\\bundle\\nsis\\Vision 动作识别与评分_0.1.0_x64-setup.exe; cmd: git diff --exit-code -- frontend/src-tauri/capabilities/default.json => exit 0; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_windows_packaging_smoke.py -q => exit 0, 10 passed
  - 完成时间: 2026-06-14 20:39:06
  - 备注: 将 Python bridge sidecar 从 PyInstaller onefile 切换为 onedir COLLECT；构建脚本清理旧 exe 并复制整个 onedir 到 Tauri resources；Rust 安装版路径解析为 resource_dir/vision-ui-backend/vision-ui-backend.exe；heavy excludes 未放宽，capabilities 无权限漂移。
  - 涉及文件: `ui_backend_sidecar.spec`, `scripts/build-tauri-sidecar.ps1`, `frontend/src-tauri/tauri.conf.json`, `frontend/src-tauri/src/lib.rs`, `tests/test_windows_packaging_smoke.py`
  - 验证命令: `npm run build:sidecar`; `npm run verify:tauri`; `npm run package:windows`; `git diff --exit-code -- frontend/src-tauri/capabilities/default.json`; `.\.venv\Scripts\python.exe -m pytest tests/test_windows_packaging_smoke.py -q`
  - 依赖: T-001
  - 风险: medium
  - 覆盖: REQ-006, AC-006.1, NFR-005
  - 可并行: 是
  - 验收口径: Windows 安装包能找到 onedir sidecar，heavy excludes 不放宽，打包产物不提交，Tauri Rust 编译通过且 capabilities 不发生权限漂移
  - 预估工程量: 4-6 小时

---

## 阶段 3：数值等价离线优化

- [x] **T-006:** 向量化 DTW 局部代价、姿态归一化和误差聚合
  - 状态: done
  - 验证证据: cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py tests/test_rule_availability.py tests/test_tech_eval_contract.py -q => exit 0, 49 passed; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_body_core_layout.py tests/test_layout_shape_param.py tests/test_s5_offline_profile.py -q => exit 0, 39 passed; cmd: .\\.venv\\Scripts\\python.exe -m py_compile core\\pose_features.py core\\action_compare.py core\\rule_scoring.py => exit 0; cmd: git diff --check -- core/pose_features.py core/action_compare.py core/rule_scoring.py tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py tests/test_rule_availability.py tests/test_tech_eval_contract.py => exit 0, only CRLF warnings
  - 完成时间: 2026-06-14 21:04:53
  - 备注: 向量化 DTW 局部代价矩阵、pose normalizer 坐标变换、双模板关节误差统计；规则评分缓存模块级 _RULES 并批量计算 valid_mask 行有效性。金标、规则状态、valid_mask 语义和误差统计验证不漂移。
  - 涉及文件: `core/pose_features.py`, `core/action_compare.py`, `core/rule_scoring.py`, `tests/test_pose33_v3_golden.py`, `tests/test_valid_mask_migration.py`, `tests/test_rule_availability.py`, `tests/test_tech_eval_contract.py`
  - 验证命令: `.\.venv\Scripts\python.exe -m pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py tests/test_rule_availability.py tests/test_tech_eval_contract.py -q`
  - 依赖: T-003, T-004, T-005
  - 风险: high
  - 覆盖: REQ-002, REQ-005, AC-005.1, AC-005.2
  - 可并行: 否
  - 验收口径: 金标、规则状态、valid_mask 语义和误差统计不漂移；若漂移则停止并要求重新审批
  - 预估工程量: 4-8 小时

---

## 阶段 4：显式 GPU 与评分语义风险项

- [x] **T-007:** 贯通 MediaPipe GPU delegate opt-in 与 CPU fallback
  - 状态: done
  - 验证证据: cmd: .\\.venv\\Scripts\\python.exe -m py_compile core\\vision_pipeline.py apps\\main.py apps\\ui_backend.py core\\backend_router.py => exit 0; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_mediapipe_delegate_config.py tests/test_s5_gpu_recheck.py tests/test_backend_routing_contract.py tests/test_pose33_v3_golden.py -q => exit 0, 48 passed; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_ui_backend_sessions.py tests/test_s5_realtime_latest_frame.py tests/test_s5_hands_toggle.py -q => exit 0, 31 passed; cmd: git diff --check -- core/vision_pipeline.py apps/main.py apps/ui_backend.py core/backend_router.py core/parallel_pose_engine.py tests/test_mediapipe_delegate_config.py tests/test_s5_gpu_recheck.py tests/test_backend_routing_contract.py tests/test_ui_backend_sessions.py tests/test_s5_realtime_latest_frame.py => exit 0, only CRLF warnings
  - 完成时间: 2026-06-14 21:20:10
  - 备注: MediaPipe delegate 仍默认 cpu；CLI/bridge/parallel preview 仅在显式 delegate=gpu 时请求 GPU；MediaPipePipeline 在 GPU 初始化失败时回退 CPU 并暴露 requested/active/fallbackReason 元数据；正式评分和 full tech_eval 默认路径不进入 GPU。
  - 涉及文件: `core/vision_pipeline.py`, `apps/main.py`, `apps/ui_backend.py`, `core/backend_router.py`, `tests/test_mediapipe_delegate_config.py`, `tests/test_s5_gpu_recheck.py`, `tests/test_backend_routing_contract.py`
  - 验证命令: `.\.venv\Scripts\python.exe -m py_compile core\vision_pipeline.py apps\main.py apps\ui_backend.py core\backend_router.py`; `.\.venv\Scripts\python.exe -m pytest tests/test_mediapipe_delegate_config.py tests/test_s5_gpu_recheck.py tests/test_backend_routing_contract.py tests/test_pose33_v3_golden.py -q`
  - 依赖: T-006
  - 风险: high
  - 覆盖: REQ-002, REQ-004, AC-004.1, AC-004.2
  - 可并行: 否
  - 验收口径: GPU 只可显式启用，默认 CPU 不变；正式评分和 full tech_eval 不进入 GPU 默认链路；测试必须覆盖 GPU delegate 不可用时的结构化 fallback 或 CPU fallback
  - 预估工程量: 4-6 小时

- [x] **T-008:** 产出单次抽帧复用的二次审批包
  - 状态: done
  - 验证证据: 用户明确批准 T-008 高风险评分变更并要求启动执行；实现最小单次抽帧复用：新增 Pose33RawSeries/extract_pose_raw_series/slice_pose_raw_series，compare_video_to_dual_templates 的规则评分与关节误差分析复用一次 full-video raw Pose33+valid_mask；body_core match 支持 precomputed_features，batch body_core front/side 复用一次 feature extraction；未修改 DTW、规则阈值、YOLO 授权元数据或 golden。验证：py_compile core\\rule_scoring.py core\\action_compare.py core\\body_core_compare.py batch\\batch_dual_compare.py tests\\test_t008_single_pass_reuse.py => exit 0；pytest tests/test_t008_single_pass_reuse.py -q => 4 passed；pytest tests/test_batch_backend_args.py tests/test_body_core_layout.py -q => 37 passed；pytest tests/test_pose33_v3_golden.py -q => 16 passed；pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py tests/test_rule_availability.py tests/test_tech_eval_contract.py -q => 49 passed；pytest tests/test_body_core_layout.py tests/test_batch_backend_args.py tests/test_yolo_backend_contract.py -q => 59 passed；analysis/offline_matching_profile.py --fixture-smoke --out outputs\\perf_baseline\\t008_after => exit 0, wrote json/csv。
  - 完成时间: 2026-06-14 23:06:39
  - 备注: T-008 已在二次审批后实施；输出仍保持 score_authorized=False/internal/unvalidated 等授权边界。
  - 涉及文件: `docs/specs/design.md`, `docs/specs/requirements.md`, `docs/specs/tasks.md`, `docs/specs/t008_single_pass_frame_gate.md`, `core/action_compare.py`, `core/rule_scoring.py`, `batch/batch_dual_compare.py`, `core/body_core_compare.py`
  - 验证命令: `python C:\Users\ny\.codex\plugins\cache\Useful-marketplace\spce-workflow\0.2.0\scripts\validate_spec.py docs/specs/ --workflow design-first --color never`; `python C:\Users\ny\.codex\plugins\cache\Useful-marketplace\spce-workflow\0.2.0\scripts\validate_spec.py docs/specs/ --sync-check --color never`
  - 依赖: T-007
  - 风险: high
  - 覆盖: REQ-002, REQ-005, AC-002.2, AC-005.2
  - 可并行: 否
  - 验收口径: 本任务不得实现单次抽帧复用，只能读取相关业务代码并产出 `docs/specs/t008_single_pass_frame_gate.md`，其中必须包含真实 MediaPipe VIDEO-mode 验证矩阵、fixture replay 验证矩阵、回滚方案和二次审批建议；若用户未明确回复 `批准 T-008 高风险评分变更，启动执行`，必须用 `spec_progress.py block` 或 `spec_progress.py skip` 记录人工决策，不能修改单次抽帧相关业务代码
  - 预估工程量: 2-4 小时

---

## 阶段 5：传输、前端绘制与最终验收

- [x] **T-009:** 优化 raw frame 传输、canvas 绘制和 Rust latest-frame clone
  - 状态: done
  - 验证证据: cmd: npm --prefix frontend run test => exit 0, Frontend behavior smoke checks passed; cmd: npm run verify:tauri => exit 0, cargo check finished; cmd: git diff --exit-code -- frontend/src-tauri/capabilities/default.json => exit 0; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_vue_tauri_acceptance_gaps.py tests/test_ui_backend_sessions.py -q => exit 0, 24 passed
  - 完成时间: 2026-06-14 23:10:03
  - 备注: raw frame 前端读取改为 Uint8Array response view 避免 slice 拷贝；App.vue 缓存 canvas 2D context；Rust latest-frame store 改为 Arc<Vec<u8>>，保持 session/job/frameId 身份隔离与 latest-wins 语义。
  - 涉及文件: `frontend/src/App.vue`, `frontend/src/bridge.ts`, `frontend/src/bridge-state.ts`, `frontend/scripts/frontend-smoke.mjs`, `frontend/src-tauri/src/lib.rs`, `tests/test_vue_tauri_acceptance_gaps.py`, `tests/test_ui_backend_sessions.py`
  - 验证命令: `npm --prefix frontend run test`; `npm run verify:tauri`; `git diff --exit-code -- frontend/src-tauri/capabilities/default.json`; `.\.venv\Scripts\python.exe -m pytest tests/test_vue_tauri_acceptance_gaps.py tests/test_ui_backend_sessions.py -q`
  - 依赖: T-003, T-005, T-008
  - 风险: medium
  - 覆盖: REQ-003, REQ-006, AC-006.2
  - 可并行: 是
  - 验收口径: session/job/frame 身份隔离不变，`frameId` 单调不回退，latest-wins 背压不改为队列；Rust 编译通过；`frontend/src-tauri/capabilities/default.json` 不发生权限漂移
  - 预估工程量: 3-5 小时

- [x] **T-010:** 完成任务收尾、文档同步和变更日志
  - 状态: done
  - 验证证据: cmd: python C:\Users\ny\.codex\plugins\cache\Useful-marketplace\spce-workflow\0.2.0\scripts\validate_spec.py docs\specs --workflow design-first --color never => exit 0, 36 checks passed; cmd: python C:\Users\ny\.codex\plugins\cache\Useful-marketplace\spce-workflow\0.2.0\scripts\validate_spec.py docs\specs --resume --color never => exit 0, status=ready current_task=T-010 freeze ok; cmd: git diff --check => exit 0, only CRLF warnings; cmd: npm run verify:desktop => exit 0, frontend build/smoke, Tauri cargo check, Python compile smoke and desktop regression tests passed, 152 passed
  - 完成时间: 2026-06-14 23:19:08
  - 备注: 完成任务收尾、change.md 置顶同步和桌面整体验证；未修改冻结规范语义。
  - 涉及文件: `docs/performance_optimization_inventory.md`, `docs/specs/design.md`, `docs/specs/requirements.md`, `docs/specs/tasks.md`, `change.md`
  - 验证命令: `python C:\Users\ny\.codex\plugins\cache\Useful-marketplace\spce-workflow\0.2.0\scripts\validate_spec.py docs/specs/ --workflow design-first --color never`; `python C:\Users\ny\.codex\plugins\cache\Useful-marketplace\spce-workflow\0.2.0\scripts\validate_spec.py docs/specs/ --resume --color never`; `git diff --check`; `npm run verify:desktop`
  - 依赖: T-002, T-003, T-004, T-005, T-006, T-007, T-008, T-009
  - 风险: high
  - 覆盖: REQ-001, REQ-002, REQ-003, REQ-004, REQ-005, REQ-006, NFR-006
  - 可并行: 否
  - 验收口径: 所有任务有证据，`change.md` 已置顶同步，规范结构与 resume 检查通过；本任务不宣称 final acceptance，通过后才进入下方“任务完成后的验收入口”
  - 预估工程量: 2-4 小时

---

## 执行 Waves

| Wave | 任务 | 说明 |
|:---|:---|:---|
| 1 | T-001 | 先锁定基线、合同和 profile 证据 |
| 2 | T-002, T-004, T-005 | 低数值风险轨道可并行，但每项仍需独立验证 |
| 3 | T-003 | 与 T-002 共享 bridge 文件，必须串行 |
| 4 | T-006 | 数值等价离线优化单独执行 |
| 5 | T-007 | GPU opt-in 单独执行，默认 CPU 不变 |
| 6 | T-008 | 只产出单次抽帧二次审批包，不实施评分语义变更 |
| 7 | T-009 | 与 T-005 共享 Rust 文件，依赖 onedir 路径稳定后执行 |
| 8 | T-010 | 任务收尾和文档同步；final acceptance 在任务完成后独立启动 |

---

## 风险标记

| 任务 ID | 风险类别 | 风险描述 | 审查要求 |
|:---|:---|:---|:---|
| T-001 | 性能证据 | 基线错误会污染后续收益判断 | 人类审查 profile 与合同范围 |
| T-006 | 评分语义 | DTW、归一化、规则和误差聚合可能引入数值漂移 | 金标与合同测试必须通过 |
| T-007 | 平台差异 | GPU delegate 可能不可用或输出存在差异 | 默认 CPU 不变，GPU 仅 opt-in |
| T-008 | 时序态 / 审批 | 单次抽帧可能改变 VIDEO-mode 子段推理状态 | 首轮批准只允许产出二次审批包；实施需独立批准 |
| T-010 | 收尾 | 多轨道改动可能产生组合回归 | 只做任务收尾；pre-acceptance 与 final acceptance 在任务全完成后独立启动 |

---

## 任务完成后的验收入口

当且仅当 `tasks.md` 中所有任务均通过 `spec_progress.py complete` 或带人工证据的 `spec_progress.py skip` 关闭后，才能启动以下验收入口。该入口不是 `T-010` 的完成条件，也不得在仍有 unchecked task 时运行：

```powershell
python C:\Users\ny\.codex\plugins\cache\Useful-marketplace\spce-workflow\0.2.0\scripts\validate_spec.py docs/specs/ --pre-acceptance --color never
python C:\Users\ny\.codex\plugins\cache\Useful-marketplace\spce-workflow\0.2.0\scripts\spec_progress.py acceptance-init docs/specs
```

`pre-acceptance` 只代表本地预检，不等于 final acceptance。严格结尾验收必须按 `spec-acceptance` 编排 first-wave 与 adversarial 子 agent；验收发现的问题只能进入 `docs/specs/acceptance-fixes.md`，不得追加到本任务清单。

---

## 完成日志

| 任务 ID | 完成时间 | Commit Hash | 验证证据 | 备注 |
|:---|:---|:---|:---|:---|
| T-001 | 2026-06-14 20:09:37 | 8b1d0b9 | cmd: .\\.venv\\Scripts\\python.exe analysis\\offline_matching_profile.py --fixture-smoke --out outputs\\perf_baseline\\offline_fixture => exit 0, wrote offline_matching_profile.json/.csv; cmd: .\\.venv\\Scripts\\python.exe analysis\\bench_annotate_fps.py --env-only --out outputs\\perf_baseline\\gpu_env => exit 0, wrote gpu_recheck_env.json; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_backend_routing_contract.py::test_offline_high_quality_yolo26l_available_routes_internal_body_only tests/test_backend_routing_contract.py::test_high_quality_template_compare_stays_mediapipe_formal_compare -q => exit 0, 2 passed; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_s5_offline_profile.py tests/test_s5_gpu_recheck.py tests/test_pose33_v3_golden.py -q => exit 0, 31 passed | 解除 T-001 blocker：恢复 high_quality+YOLO26L available 既有 backend routing 合同；bench_annotate_fps.py 可从仓库根目录原命令运行；未实施 T-002 及后续性能优化。 |
| T-002 | 2026-06-14 20:15:28 | 8b1d0b9 | cmd: npm --prefix frontend run test => exit 0, Frontend behavior smoke checks passed; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_ui_backend_sessions.py tests/test_s5_hands_toggle.py tests/test_s5_realtime_latest_frame.py -q => exit 0, 25 passed | 实时预览默认降载为 lite + hands off；预览 JPEG/尺寸/FPS/idle sleep 常量调低；保持正式评分/CLI/Tkinter 默认路径不变，并恢复 Tkinter UiState.out_path 兼容字段以通过既有测试。 |
| T-004 | 2026-06-14 20:24:52 | 8b1d0b9 | cmd: .\\.venv\\Scripts\\python.exe -m py_compile batch\\batch_dual_compare.py batch\\batch_export_skeleton.py => exit 0; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_batch_backend_args.py tests/test_yolo_backend_contract.py -q => exit 0, 38 passed | 为 batch dual-compare 与 skeleton export 增加 --workers 跨视频并行；每个 worker 独立执行视频处理，主线程按输入 index 排序写 CSV/JSONL/manifest；YOLO body_core 授权元数据保持 score_authorized=False/internal/unvalidated；未实现单次抽帧复用。 |
| T-005 | 2026-06-14 20:39:06 | 8b1d0b9 | cmd: npm run build:sidecar => exit 0, PyInstaller onedir copied to frontend\\src-tauri\\resources\\vision-ui-backend; cmd: npm run verify:tauri => exit 0, cargo check finished; cmd: npm run package:windows => exit 0, NSIS installer generated at frontend\\src-tauri\\target\\release\\bundle\\nsis\\Vision 动作识别与评分_0.1.0_x64-setup.exe; cmd: git diff --exit-code -- frontend/src-tauri/capabilities/default.json => exit 0; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_windows_packaging_smoke.py -q => exit 0, 10 passed | 将 Python bridge sidecar 从 PyInstaller onefile 切换为 onedir COLLECT；构建脚本清理旧 exe 并复制整个 onedir 到 Tauri resources；Rust 安装版路径解析为 resource_dir/vision-ui-backend/vision-ui-backend.exe；heavy excludes 未放宽，capabilities 无权限漂移。 |
| T-003 | 2026-06-14 20:56:06 | 8b1d0b9 | cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_parallel_pose_engine.py tests/test_ui_backend_sessions.py tests/test_s5_realtime_latest_frame.py -q => exit 0, 25 passed; cmd: git diff --check -- apps/ui_backend.py tests/test_ui_backend_sessions.py core/parallel_pose_engine.py tests/test_parallel_pose_engine.py tests/test_s5_realtime_latest_frame.py => exit 0, only CRLF warnings | 实时 camera preview 在 MediaPipe 路由且 workers>1 时接入 ParallelPoseEngine，每个 worker 使用独立 IMAGE-mode pipeline factory；默认 workers=1、视频文件和 YOLO 路由继续走既有单管线路径；late stop 通过 ctx.stopped/capture_stop/engine.close 保持终态不复活。 |
| T-006 | 2026-06-14 21:04:53 | 8b1d0b9 | cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py tests/test_rule_availability.py tests/test_tech_eval_contract.py -q => exit 0, 49 passed; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_body_core_layout.py tests/test_layout_shape_param.py tests/test_s5_offline_profile.py -q => exit 0, 39 passed; cmd: .\\.venv\\Scripts\\python.exe -m py_compile core\\pose_features.py core\\action_compare.py core\\rule_scoring.py => exit 0; cmd: git diff --check -- core/pose_features.py core/action_compare.py core/rule_scoring.py tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py tests/test_rule_availability.py tests/test_tech_eval_contract.py => exit 0, only CRLF warnings | 向量化 DTW 局部代价矩阵、pose normalizer 坐标变换、双模板关节误差统计；规则评分缓存模块级 _RULES 并批量计算 valid_mask 行有效性。金标、规则状态、valid_mask 语义和误差统计验证不漂移。 |
| T-007 | 2026-06-14 21:20:10 | 8b1d0b9 | cmd: .\\.venv\\Scripts\\python.exe -m py_compile core\\vision_pipeline.py apps\\main.py apps\\ui_backend.py core\\backend_router.py => exit 0; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_mediapipe_delegate_config.py tests/test_s5_gpu_recheck.py tests/test_backend_routing_contract.py tests/test_pose33_v3_golden.py -q => exit 0, 48 passed; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_ui_backend_sessions.py tests/test_s5_realtime_latest_frame.py tests/test_s5_hands_toggle.py -q => exit 0, 31 passed; cmd: git diff --check -- core/vision_pipeline.py apps/main.py apps/ui_backend.py core/backend_router.py core/parallel_pose_engine.py tests/test_mediapipe_delegate_config.py tests/test_s5_gpu_recheck.py tests/test_backend_routing_contract.py tests/test_ui_backend_sessions.py tests/test_s5_realtime_latest_frame.py => exit 0, only CRLF warnings | MediaPipe delegate 仍默认 cpu；CLI/bridge/parallel preview 仅在显式 delegate=gpu 时请求 GPU；MediaPipePipeline 在 GPU 初始化失败时回退 CPU 并暴露 requested/active/fallbackReason 元数据；正式评分和 full tech_eval 默认路径不进入 GPU。 |
| T-008 | 2026-06-14 23:06:39 | 943f1c0 | 用户明确批准 T-008 高风险评分变更并要求启动执行；实现最小单次抽帧复用：新增 Pose33RawSeries/extract_pose_raw_series/slice_pose_raw_series，compare_video_to_dual_templates 的规则评分与关节误差分析复用一次 full-video raw Pose33+valid_mask；body_core match 支持 precomputed_features，batch body_core front/side 复用一次 feature extraction；未修改 DTW、规则阈值、YOLO 授权元数据或 golden。验证：py_compile core\\rule_scoring.py core\\action_compare.py core\\body_core_compare.py batch\\batch_dual_compare.py tests\\test_t008_single_pass_reuse.py => exit 0；pytest tests/test_t008_single_pass_reuse.py -q => 4 passed；pytest tests/test_batch_backend_args.py tests/test_body_core_layout.py -q => 37 passed；pytest tests/test_pose33_v3_golden.py -q => 16 passed；pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py tests/test_rule_availability.py tests/test_tech_eval_contract.py -q => 49 passed；pytest tests/test_body_core_layout.py tests/test_batch_backend_args.py tests/test_yolo_backend_contract.py -q => 59 passed；analysis/offline_matching_profile.py --fixture-smoke --out outputs\\perf_baseline\\t008_after => exit 0, wrote json/csv。 | T-008 已在二次审批后实施；输出仍保持 score_authorized=False/internal/unvalidated 等授权边界。 |
| T-009 | 2026-06-14 23:10:03 | 943f1c0 | cmd: npm --prefix frontend run test => exit 0, Frontend behavior smoke checks passed; cmd: npm run verify:tauri => exit 0, cargo check finished; cmd: git diff --exit-code -- frontend/src-tauri/capabilities/default.json => exit 0; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_vue_tauri_acceptance_gaps.py tests/test_ui_backend_sessions.py -q => exit 0, 24 passed | raw frame 前端读取改为 Uint8Array response view 避免 slice 拷贝；App.vue 缓存 canvas 2D context；Rust latest-frame store 改为 Arc<Vec<u8>>，保持 session/job/frameId 身份隔离与 latest-wins 语义。 |
| T-010 | 2026-06-14 23:19:08 | 36bb902 | cmd: python C:\Users\ny\.codex\plugins\cache\Useful-marketplace\spce-workflow\0.2.0\scripts\validate_spec.py docs\specs --workflow design-first --color never => exit 0, 36 checks passed; cmd: python C:\Users\ny\.codex\plugins\cache\Useful-marketplace\spce-workflow\0.2.0\scripts\validate_spec.py docs\specs --resume --color never => exit 0, status=ready current_task=T-010 freeze ok; cmd: git diff --check => exit 0, only CRLF warnings; cmd: npm run verify:desktop => exit 0, frontend build/smoke, Tauri cargo check, Python compile smoke and desktop regression tests passed, 152 passed | 完成任务收尾、change.md 置顶同步和桌面整体验证；未修改冻结规范语义。 |
