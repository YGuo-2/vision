# Repository Guidelines

## Project Overview

本仓库是武术散打动作识别与评分系统。当前两套桌面入口并存：

- `apps/app_ui.py`：Tkinter 旧桌面入口，迁移期保留。
- `frontend/`：Windows-only Vue 3 + Vite + Tauri 2 新桌面前端，通过 `apps/ui_backend.py` 的 JSON bridge 调用 Python 后端。

视觉后端仍以 MediaPipe 为正式评分和 full tech_eval 默认链路。YOLO 已接入受控的 body-only 预览 / 内部分析 / 标定调试入口，但不授权对外评分。

## Project Structure & Module Organization

```
vision/
├── core/                       # 视觉与评分核心
│   ├── vision_pipeline.py      # MediaPipe Tasks pipeline (PoseLandmarker + HandLandmarker)
│   ├── backend_router.py       # 桌面 / batch 后端路由唯一决策点
│   ├── yolo_adapter.py         # YOLO-pose 适配入口，COCO17 -> BlazePose33-like
│   ├── feature_layout.py       # pose33_v3 / body_core_v1 layout 注册与 baseline
│   ├── body_core_compare.py    # body_core_v1 模板闭环和内部匹配
│   ├── pose_features.py        # 姿态归一化和 DTW 匹配
│   ├── action_compare.py       # 单 / 双模板视频对比
│   ├── rule_scoring.py         # 规则评分与结构化状态
│   ├── model_manager.py        # 模型清单、下载与状态
│   ├── paths.py                # artifact root 统一解析
│   ├── parallel_pose_engine.py # 离线多 worker IMAGE-mode 推理
│   └── video_writer.py         # 视频输出 codec 回退
├── apps/                       # Python 入口
│   ├── main.py                 # CLI runner
│   ├── app_ui.py               # Tkinter desktop UI
│   ├── ui_backend.py           # Vue/Tauri JSON bridge
│   ├── camera_enum.py          # Windows 摄像头枚举与输入源状态
│   ├── make_template.py        # 创建 pose 模板
│   └── match_template.py       # 模板匹配
├── frontend/                   # Vue + Vite + Tauri desktop frontend
│   ├── src/                    # Vue UI、bridge client、状态与 lifecycle
│   └── src-tauri/              # Tauri Rust shell、capabilities、bundle config
├── scripts/                    # 桌面验证、sidecar 构建和开发启动脚本
├── packaging/                  # PyInstaller runtime hooks for Tauri sidecar
├── batch/                      # batch_dual_compare / export_skeleton / tech_eval
├── analysis/                   # tech_eval、benchmark、标定、spike 和 profile
├── docs/                       # YOLO 迁移计划、决策报告、specs 与验收证据链
├── tests/                      # pytest 回归套件与 fixtures
├── models/                     # 下载的 `.task` / `.pt` 模型文件，gitignored
├── outputs/                    # 运行输出，gitignored
├── templates/                  # 模板样例 / 本地模板
└── requirements.txt            # Python runtime + test dependencies
```

## Build, Test, and Development Commands

> **网络代理约定**：凡是需要联网下载、但国内无法正常访问的资源（pip 包、模型权重 `.task` / `.pt`、GitHub / HuggingFace 资源等），一律走本地代理，端口号为 `7890`。
>
> PowerShell 当前会话临时设置：
> ```powershell
> $env:HTTP_PROXY  = "http://127.0.0.1:7890"
> $env:HTTPS_PROXY = "http://127.0.0.1:7890"
> ```
>
> pip 单次下载：
> ```powershell
> .\.venv\Scripts\python.exe -m pip install -r requirements.txt --proxy http://127.0.0.1:7890
> ```
>
> 下载模型 / 外部资源时同样需带上 `127.0.0.1:7890` 代理。

Install from repo root:
```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm --prefix frontend install
```

Run Tkinter UI:
```powershell
.\.venv\Scripts\python.exe apps/app_ui.py
```

Run Vue/Tauri UI in development mode:
```powershell
npm run dev:desktop
```

Direct Tauri dev command, if needed:
```powershell
$env:Path = "$env:USERPROFILE\.cargo\bin;$env:Path"
npm --prefix frontend run tauri dev
```

Verify the desktop migration stack:
```powershell
npm run verify:desktop
```

Useful focused checks:
```powershell
npm run verify:frontend
npm --prefix frontend run test
npm run verify:tauri
npm run build:sidecar
```

Build the Windows Tauri package:
```powershell
npm run package:windows
```

Run CLI with camera `0`:
```powershell
.\.venv\Scripts\python.exe apps/main.py --source 0
```

Offline export with progress and multithreading:
```powershell
.\.venv\Scripts\python.exe apps/main.py --source input.mp4 --pose heavy --out out.mp4 --no-show --workers 4
```

Create and match templates:
```powershell
.\.venv\Scripts\python.exe apps/make_template.py --video action.mp4 --pose heavy --preview
.\.venv\Scripts\python.exe apps/match_template.py --template template.npz --video test.mp4 --preview
```

Batch dual-template comparison:
```powershell
.\.venv\Scripts\python.exe batch/batch_dual_compare.py --standard_dir "标准样本" --student_dir "学员样本" --pose full --out_dir "输出目录" --rules --action both
```

Latest known desktop acceptance evidence, 2026-06-11:

- `npm run verify:desktop` passed: frontend build, frontend smoke, Tauri `cargo check`, Python `py_compile`, and 139 desktop regression tests.
- `npm run package:windows` regenerated the NSIS installer under `frontend/src-tauri/target/release/bundle/nsis/`.
- `.\.venv\Scripts\python.exe -m pytest tests/test_windows_packaging_smoke.py -q` passed with 9 tests.
- `.\.venv\Scripts\python.exe -m pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py tests/test_yolo_backend_contract.py tests/test_yolo_landmark_mapping.py tests/test_rule_availability.py tests/test_tech_eval_contract.py -q` passed with 82 tests.

## Testing Guidelines

本仓库已有 pytest 回归套件，不再是“无正式测试套件”状态。按改动范围选择验证门：

- Python 核心 / 算法：运行相关 `tests/test_*.py`，至少包含 `tests/test_pose33_v3_golden.py` 和受影响模块的契约测试。
- YOLO / layout / scoring：同时跑 `test_yolo_backend_contract.py`、`test_yolo_landmark_mapping.py`、`test_body_core_layout.py`、`test_tech_eval_contract.py`、`test_valid_mask_migration.py` 中相关子集。
- Vue/Tauri / bridge：运行 `npm run verify:desktop`；小改也至少跑 `npm --prefix frontend run test` 和相关 `tests/test_ui_backend_*.py`。
- 打包 / sidecar：运行 `npm run package:windows` 和 `.\.venv\Scripts\python.exe -m pytest tests/test_windows_packaging_smoke.py -q`。
- 轻量语法检查：
  ```powershell
  .\.venv\Scripts\python.exe -m py_compile .\apps\main.py .\apps\app_ui.py .\apps\ui_backend.py .\core\vision_pipeline.py .\core\backend_router.py .\core\yolo_adapter.py
  ```

提交或交付前尽量运行 `git diff --check`。Windows 行尾提示可以接受，空白错误不接受。

## Coding Style & Naming Conventions

- Python 4-space indentation，函数保持小而清晰，公共边界尽量带类型标注。
- 模块边界要清楚：UI 逻辑留在 `apps/app_ui.py` / `frontend/`，bridge 适配留在 `apps/ui_backend.py`，视觉推理和评分留在 `core/` / `analysis/`。
- `core/backend_router.py` 是 UI bridge、batch、离线分析共享的后端路由决策点；不要在入口层复制分叉逻辑。
- Vue/Tauri 代码留在 `frontend/`；Rust 负责桌面壳、进程 / 文件 / 打包资源、原生 IPC，不承接视觉算法。
- Python 保持模型清单、模型下载执行、MediaPipe / YOLO 推理与评分契约。
- 不提交大文件和生成产物：models、videos、`outputs/`、`dist/`、`build/`、`frontend/dist/`、`frontend/src-tauri/target/`、`frontend/src-tauri/resources/*.exe`。
- 前端状态不要存大图 base64 / blob URL 历史；实时预览使用 Rust-owned latest-frame 通道和帧身份单调不回退 guard。

## Desktop Bridge Contracts

- `apps/ui_backend.py` 对外输出 JSON bridge envelope；异常也要归一为带 `ok=false`、`requestId`、`jobId` / `sessionId` 的结构化响应。
- `doCompare=true` 的模板比对请求优先于 `qualityProfile=high_quality`；不要让请求声明模板对比却被高质量分析路由抢走。
- 最新帧通道由 `frontend/src-tauri/src/lib.rs` 持有 per-session 单槽 store；Python 复用本机 TCP 长连接按 token / `frameId` / `frameHandle` 写入 JPEG bytes，前端 raw IPC 必须保持会话隔离并按实际返回 `frameId` 单调不回退后再更新 canvas 和指标。
- 停止或卸载时要取消 active session / analysis / template / model download job，late response 不得复活终态。
- 安装版 sidecar 当前不打包 YOLO runtime；所有桌面 YOLO 路由必须能表达 runtime/model 不可用时的 fallback 或结构化错误。

## YOLO Migration Status and Hard Constraints

权威文档：

- `docs/yolo_migration_plan_optimized.md`
- `docs/yolo_migration_issues.md`
- `docs/yolo_default_switch_decision.md`
- `docs/yolo_body_core_calibration.md`
- `docs/yolo_gpu_recheck_report.md`

当前 S6 决策结论：

- 正式评分、规则评分、full tech_eval、CLI 默认路径、Tkinter 默认路径全部不切 YOLO，继续 MediaPipe。
- Vue/Tauri 新桌面可在受控条件下使用 body-only YOLO：
  - `enableHands=false` 且 YOLO26n / YOLO26s 模型与 runtime 可用时，可走实时 body-only preview，结果必须 `displayScope=limited`、`scoreAuthorized=false`。
  - `enableHands=false` 且 YOLO26L 可用时，可走离线 high-quality body-only 内部分析，结果必须 `displayScope=internal`、`scoreAuthorized=false`、`calibrationStatus=unvalidated`。
  - 缺模型或安装版 runtime 不支持时，实时 preview 回退 MediaPipe 并展示 fallback；离线 high-quality 返回结构化不可用 / 下载错误，不静默冒充成功。
- `apps/main.py` 不新增 `--backend yolo` 实时入口；`apps/app_ui.py` 不新增 YOLO 后端选择。
- `yolo_body_mp_pose_supplement` / Hybrid 不实现，不保留半成品 runtime。

给后续 agent 的硬约束：

- **不得改变 MediaPipe 旧默认路径行为**：`pose33_v3` 模板、`infer()` / `annotate()`、旧模板兼容都以 `tests/test_pose33_v3_golden.py` 不漂移为准绳。
- COCO17 缺嘴角、脚跟脚尖、手指；YOLO-only 不进入 full tech_eval，不进入对外正式评分。
- 缺失点不得伪造成有效点；有效性判据统一走 `valid_mask`，不要重新散落 `lm[idx, 3] >= thr`。
- `body_core_v1` 标定参数已落库：baseline `1.2826`，YOLO `valid_conf_thr=0.6`；但状态仍是 `calibration_status=unvalidated`，`score_authorized=False`。
- `enableHands=false` 但请求手指能力时，不要静默启用手部检测，也不要误走 YOLO；应走 MediaPipe pose-only partial 并标注 skipped capabilities。
- `qualityProfile=high_quality` + body-only + `enableHands=true` 应返回 `bad_request`，要求用户显式 `enableHands=false` 后再进入 YOLO26L 内部分析。
- YOLO artifact 必须携带后端与授权元数据，例如 `backend` / `raw_layout` / `feature_layout` / `capability` / `score_authorized` / `calibration_status` / `display_scope`。

## Commit & Pull Request Guidelines

- 仓库已有 `main` 分支和 Git 历史；继续使用 Conventional Commits：`feat:`、`fix:`、`refactor:`、`docs:`、`test:`、`chore:`。
- PR / issue 文案默认中文，说明问题、改动、验证命令和结果；UI 改动附截图或说明可见行为。
- 提交或推送前确认 GitHub / Git 身份：`gh auth status`、`gh api user`、`git config user.name`、`git config user.email`。
- 私有仓库 GitHub connector 可能不可用时，优先使用本地 `gh pr view` / `gh issue view` / `gh pr checks` / `gh pr merge`。

## 任务完成规范

- **每次完成任务后，必须将修改总结写入当前 `change.md` 文件（最新记录置顶）。`change.md` 累积过长时，用 `git mv` 将其按时间段归档为 `change（<起>~<止月>）.md` 并重建空 `change.md`，把「归档与重建」本身作为新 `change.md` 的首条记录，并同步更新本规则的归档清单。历史归档：`change（start~2026.5）.md`、`change（2026.5~2026.6）.md`。**
- 记录内容应包括：修改日期、问题描述、修改内容、验证方法。
- 如果只改文档，也要记录文档同步依据和至少一次轻量验证。
