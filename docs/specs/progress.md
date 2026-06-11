# Spce workflow Progress

> **Workflow:** design-first
> **Mode:** strict
> **Status:** Completed
> **Current Task:** n/a
> **Approval:** approved
> **Last Checkpoint:** 2026-06-11 16:10:57
> **Branch:** main
> **Last Known Commit:** 3c41f33

## Resume Summary
- Goal: 完成桌面栈、打包和迁移文档验收
- Approved specs: design.md, requirements.md, tasks.md
- Current task: n/a
- Next safe action: Run pre-acceptance, then final acceptance.
- Blockers: n/a

## Active Task State
- Task ID: n/a
- Status: done
- Started at: n/a
- Verification needed: cmd: npm run verify:desktop => exit 0, frontend build + frontend smoke + cargo check + py_compile + desktop regression 133 passed; cmd: npm run package:windows => exit 0, NSIS installer generated at frontend/src-tauri/target/release/bundle/nsis/Vision 动作识别与评分_0.1.0_x64-setup.exe; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_windows_packaging_smoke.py tests/test_yolo_landmark_mapping.py tests/test_yolo_backend_contract.py tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py -q => exit 0, 73 passed; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py tests/test_yolo_backend_contract.py tests/test_yolo_landmark_mapping.py tests/test_rule_availability.py tests/test_tech_eval_contract.py -q => exit 0, 82 passed; cmd: git diff --check => exit 0 (line-ending warnings only)
- Files expected to change: `scripts/verify-desktop-stack.ps1`, `scripts/build-tauri-sidecar.ps1`, `frontend/src-tauri/tauri.conf.json`, `docs/yolo_default_switch_decision.md`, `docs/yolo_migration_issues.md`, `change.md`

## Completed Work Log
| Task ID | Time | Commit/State | Verification | Notes |
|:---|:---|:---|:---|:---|
| - | - | - | - | - |
| T-001 | 2026-06-11 13:58:19 | 60f3a66 | cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_backend_routing_contract.py tests/test_ui_backend_contract.py tests/test_batch_backend_args.py -q => exit 0, 35 passed; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py -q => exit 0, 31 passed; cmd: git diff --check => exit 0 (line-ending warnings only) | 新增 core/backend_router.py 唯一路由决策点；UI bridge 和 batch helper 消费共享 router；更新 change.md。 |
| T-002 | 2026-06-11 14:12:26 | 4541e61 | cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_yolo_backend_contract.py tests/test_yolo_landmark_mapping.py tests/test_rule_availability.py tests/test_ui_backend_analysis.py -q => exit 0, 46 passed; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py -q => exit 0, 31 passed; cmd: git diff --check => exit 0 (line-ending warnings only) | YOLO adapter 边界层与序列 artifact 统一补齐 raw_layout/feature_layout/capability/score_authorized/display_scope；UI camelCase route 与 COCO17 missing capability 测试上锁；更新 change.md。 |
| T-004 | 2026-06-11 14:35:56 | f3e50db | cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_ui_backend_sessions.py tests/test_windows_packaging_smoke.py -q => exit 0, 16 passed; cmd: npm run verify:tauri => exit 0, cargo check passed; cmd: npm --prefix frontend run test => exit 0, Frontend behavior smoke checks passed; cmd: git diff --check => exit 0 (line-ending warnings only) | 实现 Python 127.0.0.1 TCP length-prefixed latest-frame 通道与 Tauri raw IPC latest_frame；session.frame JSON 不再携带 image/base64/bytes，仅传 frame handle、token 和指标；更新 change.md 基线记录。 |
| T-005 | 2026-06-11 14:44:51 | 7bfe692 | cmd: npm --prefix frontend run test => exit 0, Frontend behavior smoke checks passed; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_vue_tauri_acceptance_gaps.py -q => exit 0, 7 passed; cmd: git diff --check => exit 0 (line-ending warnings only) | Vue 预览迁移到 Canvas/ImageBitmap；requestAnimationFrame 合并 latest frame；移除 previewImage、object URL 和 img 帧展示路径；更新 change.md 基线记录。 |
| T-006 | 2026-06-11 14:54:00 | b795674 | cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_ui_backend_sessions.py tests/test_ui_backend_contract.py -q => exit 0, 24 passed; cmd: npm --prefix frontend run test => exit 0, Frontend behavior smoke checks passed; cmd: git diff --check => exit 0 (line-ending warnings only) | 统一 session/model download/analysis 主动停止和晚到事件清理；job.stop 缺失/未知 jobId 结构化错误测试；更新 change.md。 |
| T-003 | 2026-06-11 15:13:21 | 7a1390e | cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_ui_backend_models.py tests/test_windows_packaging_smoke.py -q => exit 0, 20 passed; cmd: npm --prefix frontend run test => exit 0, Frontend behavior smoke checks passed; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py -q => exit 0, 31 passed; cmd: git diff --check => exit 0 (line-ending warnings only) | 补齐 MediaPipe/YOLO26 模型档元数据、默认代理下载、YOLO 手动安装错误、安装版 sidecar YOLO runtime 排除边界和前端展示；更新 change.md。 |
| T-007 | 2026-06-11 15:28:06 | 38474bf | cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_backend_routing_contract.py tests/test_yolo_backend_contract.py -q => exit 0, 33 passed; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py -q => exit 0, 31 passed; cmd: git diff --check => exit 0 (line-ending warnings only) | 接入 YOLO26n/s realtime body-only preview pipeline；session.frame 透传 YOLO 授权/多人 meta；保持 MediaPipe 旧默认路径和正式评分边界；更新 change.md。 |
| T-008 | 2026-06-11 15:48:36 | 2e5051e | cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_body_core_layout.py tests/test_batch_backend_args.py tests/test_s3_calibration.py -q => exit 0, 40 passed; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py -q => exit 0, 31 passed; cmd: git diff --check => exit 0 (line-ending warnings only) | 接入 analysis.run YOLO26L high_quality body-only 内部分析 payload；batch/benchmark 默认 YOLO body_core 模型收敛到 yolo26l-pose.pt；保持 scoreAuthorized=false、calibration_status=unvalidated、displayScope=internal；更新 change.md。 |
| T-009 | 2026-06-11 15:52:42 | 0ac08d6 | cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py tests/test_tech_eval_contract.py tests/test_rule_availability.py -q => exit 0, 49 passed | 回归确认 formal score/full tech_eval 仍走 MediaPipe；enableHands=false + fingers 为 pose-only partial/skippedCapabilities，不启用 hands；未发现 YOLO 越界进入正式评分或 full tech_eval，更新 change.md。 |
| T-010 | 2026-06-11 16:10:57 | 3c41f33 | cmd: npm run verify:desktop => exit 0, frontend build + frontend smoke + cargo check + py_compile + desktop regression 133 passed; cmd: npm run package:windows => exit 0, NSIS installer generated at frontend/src-tauri/target/release/bundle/nsis/Vision 动作识别与评分_0.1.0_x64-setup.exe; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_windows_packaging_smoke.py tests/test_yolo_landmark_mapping.py tests/test_yolo_backend_contract.py tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py -q => exit 0, 73 passed; cmd: .\\.venv\\Scripts\\python.exe -m pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py tests/test_yolo_backend_contract.py tests/test_yolo_landmark_mapping.py tests/test_rule_availability.py tests/test_tech_eval_contract.py -q => exit 0, 82 passed; cmd: git diff --check => exit 0 (line-ending warnings only) | 修复 packaged release Manager import 和 sidecar router 对 YOLO runtime 的硬依赖；同步 yolo_default_switch_decision 与 yolo_migration_issues 最终口径；更新 change.md。 |

## Recovery Notes
- Completed T-010
