# Spce workflow Progress

> **Workflow:** design-first
> **Mode:** strict
> **Status:** Blocked
> **Current Task:** T-008
> **Approval:** approved
> **Last Checkpoint:** 2026-06-14 21:32:12
> **Branch:** main
> **Last Known Commit:** 8b1d0b9

## Resume Summary
- Goal: 产出单次抽帧复用的二次审批包
- Approved specs: design.md, requirements.md, tasks.md
- Current task: T-008
- Next safe action: Resolve blocker or revise specs before coding.
- Blockers: 已产出 docs/specs/t008_single_pass_frame_gate.md，并通过 validate_spec.py docs/specs/ --workflow design-first --color never 与 --sync-check --color never；因尚未收到独立批准短语『批准 T-008 高风险评分变更，启动执行』，按高风险评分门禁停止，未修改单次抽帧相关业务代码。

## Active Task State
- Task ID: T-008
- Status: blocked
- Started at: n/a
- Verification needed: `python C:\Users\ny\.codex\plugins\cache\Useful-marketplace\spce-workflow\0.2.0\scripts\validate_spec.py docs/specs/ --workflow design-first --color never`; `python C:\Users\ny\.codex\plugins\cache\Useful-marketplace\spce-workflow\0.2.0\scripts\validate_spec.py docs/specs/ --sync-check --color never`
- Files expected to change: `docs/specs/design.md`, `docs/specs/requirements.md`, `docs/specs/tasks.md`, `docs/specs/t008_single_pass_frame_gate.md`, `core/action_compare.py`, `core/rule_scoring.py`, `batch/batch_dual_compare.py`, `core/body_core_compare.py`

## Completed Work Log
| Task ID | Time | Commit/State | Verification | Notes |
|:---|:---|:---|:---|:---|
| - | - | - | - | - |
| T-001 | 2026-06-14 20:09:37 | 8b1d0b9 | cmd: .\\.venv\\Scripts\\python.exe analysis\\offline_matching_profile.py --fixture-smoke --out outputs\\perf_baseline\\offline_fixture => exit 0, wrote offline_matching_profile.json/.csv; cmd: .\\.venv\\Scripts\\python.exe analysis\\bench_annotate_fps.py --env-only --out outputs\\perf_baseline\\gpu_env => exit 0, wrote gpu_recheck_env.json; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_backend_routing_contract.py::test_offline_high_quality_yolo26l_available_routes_internal_body_only tests/test_backend_routing_contract.py::test_high_quality_template_compare_stays_mediapipe_formal_compare -q => exit 0, 2 passed; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_s5_offline_profile.py tests/test_s5_gpu_recheck.py tests/test_pose33_v3_golden.py -q => exit 0, 31 passed | 解除 T-001 blocker：恢复 high_quality+YOLO26L available 既有 backend routing 合同；bench_annotate_fps.py 可从仓库根目录原命令运行；未实施 T-002 及后续性能优化。 |
| T-002 | 2026-06-14 20:15:28 | 8b1d0b9 | cmd: npm --prefix frontend run test => exit 0, Frontend behavior smoke checks passed; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_ui_backend_sessions.py tests/test_s5_hands_toggle.py tests/test_s5_realtime_latest_frame.py -q => exit 0, 25 passed | 实时预览默认降载为 lite + hands off；预览 JPEG/尺寸/FPS/idle sleep 常量调低；保持正式评分/CLI/Tkinter 默认路径不变，并恢复 Tkinter UiState.out_path 兼容字段以通过既有测试。 |
| T-004 | 2026-06-14 20:24:52 | 8b1d0b9 | cmd: .\\.venv\\Scripts\\python.exe -m py_compile batch\\batch_dual_compare.py batch\\batch_export_skeleton.py => exit 0; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_batch_backend_args.py tests/test_yolo_backend_contract.py -q => exit 0, 38 passed | 为 batch dual-compare 与 skeleton export 增加 --workers 跨视频并行；每个 worker 独立执行视频处理，主线程按输入 index 排序写 CSV/JSONL/manifest；YOLO body_core 授权元数据保持 score_authorized=False/internal/unvalidated；未实现单次抽帧复用。 |
| T-005 | 2026-06-14 20:39:06 | 8b1d0b9 | cmd: npm run build:sidecar => exit 0, PyInstaller onedir copied to frontend\\src-tauri\\resources\\vision-ui-backend; cmd: npm run verify:tauri => exit 0, cargo check finished; cmd: npm run package:windows => exit 0, NSIS installer generated at frontend\\src-tauri\\target\\release\\bundle\\nsis\\Vision 动作识别与评分_0.1.0_x64-setup.exe; cmd: git diff --exit-code -- frontend/src-tauri/capabilities/default.json => exit 0; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_windows_packaging_smoke.py -q => exit 0, 10 passed | 将 Python bridge sidecar 从 PyInstaller onefile 切换为 onedir COLLECT；构建脚本清理旧 exe 并复制整个 onedir 到 Tauri resources；Rust 安装版路径解析为 resource_dir/vision-ui-backend/vision-ui-backend.exe；heavy excludes 未放宽，capabilities 无权限漂移。 |
| T-003 | 2026-06-14 20:56:06 | 8b1d0b9 | cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_parallel_pose_engine.py tests/test_ui_backend_sessions.py tests/test_s5_realtime_latest_frame.py -q => exit 0, 25 passed; cmd: git diff --check -- apps/ui_backend.py tests/test_ui_backend_sessions.py core/parallel_pose_engine.py tests/test_parallel_pose_engine.py tests/test_s5_realtime_latest_frame.py => exit 0, only CRLF warnings | 实时 camera preview 在 MediaPipe 路由且 workers>1 时接入 ParallelPoseEngine，每个 worker 使用独立 IMAGE-mode pipeline factory；默认 workers=1、视频文件和 YOLO 路由继续走既有单管线路径；late stop 通过 ctx.stopped/capture_stop/engine.close 保持终态不复活。 |
| T-006 | 2026-06-14 21:04:53 | 8b1d0b9 | cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py tests/test_rule_availability.py tests/test_tech_eval_contract.py -q => exit 0, 49 passed; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_body_core_layout.py tests/test_layout_shape_param.py tests/test_s5_offline_profile.py -q => exit 0, 39 passed; cmd: .\\.venv\\Scripts\\python.exe -m py_compile core\\pose_features.py core\\action_compare.py core\\rule_scoring.py => exit 0; cmd: git diff --check -- core/pose_features.py core/action_compare.py core/rule_scoring.py tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py tests/test_rule_availability.py tests/test_tech_eval_contract.py => exit 0, only CRLF warnings | 向量化 DTW 局部代价矩阵、pose normalizer 坐标变换、双模板关节误差统计；规则评分缓存模块级 _RULES 并批量计算 valid_mask 行有效性。金标、规则状态、valid_mask 语义和误差统计验证不漂移。 |
| T-007 | 2026-06-14 21:20:10 | 8b1d0b9 | cmd: .\\.venv\\Scripts\\python.exe -m py_compile core\\vision_pipeline.py apps\\main.py apps\\ui_backend.py core\\backend_router.py => exit 0; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_mediapipe_delegate_config.py tests/test_s5_gpu_recheck.py tests/test_backend_routing_contract.py tests/test_pose33_v3_golden.py -q => exit 0, 48 passed; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_ui_backend_sessions.py tests/test_s5_realtime_latest_frame.py tests/test_s5_hands_toggle.py -q => exit 0, 31 passed; cmd: git diff --check -- core/vision_pipeline.py apps/main.py apps/ui_backend.py core/backend_router.py core/parallel_pose_engine.py tests/test_mediapipe_delegate_config.py tests/test_s5_gpu_recheck.py tests/test_backend_routing_contract.py tests/test_ui_backend_sessions.py tests/test_s5_realtime_latest_frame.py => exit 0, only CRLF warnings | MediaPipe delegate 仍默认 cpu；CLI/bridge/parallel preview 仅在显式 delegate=gpu 时请求 GPU；MediaPipePipeline 在 GPU 初始化失败时回退 CPU 并暴露 requested/active/fallbackReason 元数据；正式评分和 full tech_eval 默认路径不进入 GPU。 |

## Recovery Notes
- Blocked T-008
