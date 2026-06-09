# Repository Guidelines

## Project Structure & Module Organization

```
vision/
├── core/               # Core modules (MediaPipe pipeline, pose features, rules)
│   ├── vision_pipeline.py    # MediaPipe Tasks pipeline (PoseLandmarker + HandLandmarker)
│   ├── pose_features.py      # Pose normalization and DTW matching algorithms
│   ├── action_compare.py     # Template matching with dual-view comparison
│   ├── rule_scoring.py       # Rule-based scoring engine
│   └── video_writer.py       # Video output codec utilities
├── apps/               # Application entry points
│   ├── main.py               # CLI runner for camera/offline video processing
│   ├── app_ui.py             # Tkinter desktop UI (Chinese localized)
│   ├── ui_backend.py         # JSON bridge for the Vue/Tauri desktop frontend
│   ├── make_template.py      # Create pose templates from videos
│   └── match_template.py     # Match templates against videos
├── frontend/           # Windows-only Vue + Vite + Tauri desktop frontend
│   ├── src/                  # Vue UI and bridge client
│   └── src-tauri/            # Tauri Rust shell, resources, bundle config
├── scripts/            # Verification and Windows packaging helpers
├── packaging/          # PyInstaller runtime hooks for Tauri sidecars
├── batch/              # Batch processing tools
│   ├── batch_dual_compare.py # Dual-template comparison for directories
│   ├── batch_export_skeleton.py
│   └── batch_tech_eval.py
├── analysis/           # Analysis and evaluation tools
│   ├── tech_eval.py          # Technical evaluation core logic
│   ├── analyze_2mp4.py
│   └── ...
├── tests/              # Test scripts
├── models/             # Downloaded `.task` model files (gitignored)
└── requirements.txt    # Python dependencies
```

## Build, Test, and Development Commands

> **网络代理约定**：凡是需要联网下载、但国内无法正常访问的资源（pip 包、模型权重 `.task`/`.pt`、GitHub/HuggingFace 资源等），一律走本地代理，端口号为 `7890`。
>
> PowerShell（当前会话临时设置）：
> ```powershell
> $env:HTTP_PROXY  = "http://127.0.0.1:7890"
> $env:HTTPS_PROXY = "http://127.0.0.1:7890"
> ```
> pip 单次下载：
> ```powershell
> .\.venv\Scripts\python.exe -m pip install -r requirements.txt --proxy http://127.0.0.1:7890
> ```
> 下载模型/外部资源时同样需带上 `127.0.0.1:7890` 代理（`curl --proxy`、`git config --global http.proxy` 等）。

Create/install (from repo root):
```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Run UI:
```powershell
.\.venv\Scripts\python.exe apps/app_ui.py
```

Run Vue/Tauri UI in development mode:
```powershell
$env:Path = "$env:USERPROFILE\.cargo\bin;$env:Path"
npm --prefix frontend run tauri dev
```

Verify the desktop migration stack:
```powershell
npm run verify:desktop
```

Run the frontend behavior smoke checks only:
```powershell
npm --prefix frontend run test
```

Build the Windows Tauri package:
```powershell
npm run package:windows
```

Latest desktop migration validation (2026-06-09, after first-wave final-acceptance fixes):
- `npm run verify:desktop`: frontend build, Frontend behavior smoke, Tauri `cargo check`, Python `py_compile`, and 118 desktop regressions passed.
- `npm run package:windows`: NSIS installer generated.
- `pytest tests/test_windows_packaging_smoke.py -q`: 8 passed, including packaged sidecar `bridge.ping` and Shell32 COM initialization coverage.
- `pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py -q`: 31 passed.
- Regression coverage now includes bridge optional/nullable manifest semantics, TS null envelope typing, short HTTP model-download protection, and unmount-time model download cancellation.

Run CLI (camera `0`):
```powershell
.\.venv\Scripts\python.exe apps/main.py --source 0
```

Offline export + progress + multithreading (higher throughput, less temporal smoothing):
```powershell
.\.venv\Scripts\python.exe apps/main.py --source input.mp4 --pose heavy --out out.mp4 --no-show --workers 4
```

## Coding Style & Naming Conventions

- Python, 4-space indentation, keep functions small and typed where practical.
- Prefer clear module boundaries: UI code stays in `app_ui.py`, inference/logic stays in `vision_pipeline.py`.
- For the migrated frontend, keep Vue/Tauri code under `frontend/` and bridge adaptation in `apps/ui_backend.py`; do not move vision algorithms into Rust or TypeScript.
- Avoid committing large artifacts (models/videos). Keep `.gitignore` up to date.
- Do not commit generated desktop artifacts such as `dist/`, `build/`, `frontend/dist/`, `frontend/src-tauri/target/`, or `frontend/src-tauri/resources/*.exe`.

## Testing Guidelines

No formal test suite yet. Minimum checks before opening a PR:
```powershell
.\.venv\Scripts\python.exe -m py_compile .\apps\main.py .\apps\app_ui.py .\core\vision_pipeline.py
```

For Vue/Tauri frontend migration work, also run:
```powershell
npm run verify:desktop
```

## Commit & Pull Request Guidelines

- No commit history exists yet; use a simple Conventional Commits style going forward:
  - `feat: ...`, `fix: ...`, `refactor: ...`, `docs: ...`
- PRs should include: what changed, how to run it (CLI/UI commands), and screenshots for UI changes.

## 任务完成规范

- **每次完成任务后，必须将修改总结写入当前 `change.md` 文件；历史记录归档于 `change（start~2026.5）.md`**
- 记录内容应包括：修改日期、问题描述、修改内容、验证方法

## YOLO 迁移任务（进行中）

仓库正在推进 MediaPipe → YOLO 的视觉后端迁移，详见：

- 计划：`docs/yolo_migration_plan_optimized.md`（三审定稿）
- 任务细化：`docs/yolo_migration_issues.md`
- 仓库追踪：Issue #12（总追踪）+ Milestone M0–M4，实施 Issue #1–#11

阶段概览：

- **S0 决策门**（#1 #2）：先定许可、环境、样本，再用 spike 数据对照**预注册数字阈值**给 go/no-go。no-go 则转替代方案，不进 S1。
- **S1 MediaPipe 加固**（#3–#6）：先建 `pose33_v3` golden 回归基线（#3，安全网，最先做），再做 layout shape 参数化 + 周期裁切修复（#4）、`valid_mask` 契约迁移（#5）、artifact root 统一 + metadata 扩展（#6）。
- **S2 YOLO 离线闭环**（#7–#9）：YOLO adapter + COCO17 映射、`body_core_v1` 布局闭环、多人闸门。
- **S3 标定 / S4 评估分级**（#10 #11）：标定 baseline 与 YOLO 阈值；规则/技术评估补结构化状态。

给后续 agent 的硬约束：

- **不得改变 MediaPipe 旧默认路径行为**（`pose33_v3` 模板、`infer()`/`annotate()`）；以 #3 golden 回归不漂移为验收准绳。
- COCO17 缺嘴角/脚跟脚尖/手指，**YOLO-only 默认不是 full tech_eval 候选**，只做预览 / 模板匹配 / skip-aware partial eval。
- 缺失点不得伪造成有效点；有效性判据统一走 `valid_mask`，不再散落 `lm[idx,3] >= thr`。
- YOLO 侧阈值在 S3 标定前为待标定占位值，未标定分数不得进入对外报告。
