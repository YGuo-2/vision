# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

武术散打动作识别与评分系统。基于 MediaPipe 的实时姿态/手势识别，使用 DTW（动态时间规整）做动作模板匹配，支持双模板（正面+侧面）对比评分与规则引擎扣分。

两套桌面前端并存：

- **Tkinter GUI**（`apps/app_ui.py`，迁移期保留的旧入口）
- **Vue + Vite + Tauri 桌面前端**（`frontend/`，Windows-only），通过 `apps/ui_backend.py` 的 JSON bridge 调用既有 Python 后端

视觉后端的 **MediaPipe → YOLO 迁移已到 S6 决策门**：MediaPipe 仍是正式评分 / full tech_eval / CLI / Tkinter 的默认主链路；YOLO 仅在 Vue/Tauri 桌面以受控 body-only 形式落地（预览 + 离线内部分析，均不授权对外评分）。所有后端选择走 `core/backend_router.py` 这一唯一决策点。

> 与 `AGENTS.md` 配合阅读：`AGENTS.md` 含项目结构、网络代理约定（端口 `7890`）、Desktop Bridge Contracts 和 YOLO 迁移硬约束的**权威版本**。本文件聚焦 Claude Code 的日常工作指引，详尽清单以 `AGENTS.md` 为准。

## 默认工作范围

**除非用户明确说要在 Web UI / Vue+Tauri 前端上修改，所有改动默认只动 Python 后端部分**（`apps/`、`core/`、`analysis/`、`batch/`、`tests/`）。不要主动改 `frontend/`（Vue/Vite/Tauri/TS/Rust）。

## Common Commands

### Installation

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm --prefix frontend install
```

> 联网下载（pip 包、模型 `.task`/`.pt`、GitHub/HuggingFace）需走本地代理 `http://127.0.0.1:7890`（详见 `AGENTS.md`）。

### Run Tkinter Desktop UI (旧入口)

```powershell
.\.venv\Scripts\python.exe apps/app_ui.py
```

### Run Vue + Tauri Desktop UI (Windows, 开发模式)

```powershell
npm run dev:desktop              # 一键：自动补 Cargo PATH + tauri dev
```

等价的手动命令（如需）：

```powershell
$env:Path = "$env:USERPROFILE\.cargo\bin;$env:Path"
npm --prefix frontend run tauri dev
```

### Run CLI (camera)

```powershell
.\.venv\Scripts\python.exe apps/main.py --source 0
```

### Offline video with multi-threading

```powershell
.\.venv\Scripts\python.exe apps/main.py --source input.mp4 --pose heavy --out out.mp4 --no-show --workers 4
```

### Create / match pose template

```powershell
.\.venv\Scripts\python.exe apps/make_template.py --video action.mp4 --pose heavy --preview
.\.venv\Scripts\python.exe apps/match_template.py --template template.npz --video test.mp4 --preview
```

### Batch dual-template comparison

```powershell
.\.venv\Scripts\python.exe batch/batch_dual_compare.py --standard_dir "标准样本" --student_dir "学员样本" --pose full --out_dir "输出目录" --rules --action both
```

## Build, Test & Verify

本仓库已有 pytest 契约/回归套件（`tests/`），不再是「无测试」状态。按改动范围选择验证门。

### Python 测试

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

关键回归（MediaPipe 安全网 + YOLO 路由/授权契约）：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_backend_routing_contract.py tests/test_yolo_backend_contract.py tests/test_yolo_landmark_mapping.py tests/test_tech_eval_contract.py tests/test_rule_availability.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_windows_packaging_smoke.py -q
```

### 桌面栈一键验证（前端 build + behavior smoke + Tauri cargo check + py_compile + 桌面回归）

```powershell
npm run verify:desktop
```

### 单独验证项

```powershell
npm run verify:frontend        # 前端 build (vue-tsc + vite build)
npm --prefix frontend run test # 前端 behavior smoke (frontend/scripts/frontend-smoke.mjs)
npm run verify:tauri           # cargo check
npm run build:sidecar          # 构建 Python bridge sidecar (PyInstaller)
```

### Windows 打包（先构建 sidecar，再生成 NSIS 安装包）

```powershell
npm run package:windows
# 产物：frontend/src-tauri/target/release/bundle/nsis/
```

### Syntax check (轻量)

```powershell
.\.venv\Scripts\python.exe -m py_compile .\apps\main.py .\apps\app_ui.py .\apps\ui_backend.py .\core\vision_pipeline.py .\core\backend_router.py .\core\yolo_adapter.py
```

## Architecture

### Core 模块职责

- **core/vision_pipeline.py**: MediaPipe 封装（`MediaPipePipeline`），处理 pose/hand landmarking、帧标注、动作分类（HANDS_UP / SQUAT / V-sign）；`PipelineConfig` 支持 `enable_hands` 与 `delegate="cpu"|"gpu"`（GPU 仅显式 opt-in）
- **core/backend_router.py**: **UI bridge / batch / 离线分析共享的后端路由唯一决策点**。纯函数、零重依赖（不 import MediaPipe/YOLO/UI），按 `TaskType`（realtime_preview / offline_body_analysis / formal_score / full_tech_eval / batch_body_core）+ `QualityProfile` + 模型可用性 + 请求能力，决定后端、评分授权与显示范围，并产出 snake_case/camelCase 序列化契约。**不要在入口层复制分叉路由逻辑**
- **core/pose_features.py**: 姿态归一化（平移/缩放/旋转不变）与 DTW 子序列匹配
- **core/feature_layout.py**: 特征布局注册表（`FeatureLayoutSpec`），把热路径里散落的 `(22, 2)` 硬编码收敛到显式布局对象（补零/mirror/误差统计/周期裁切按 layout 取值）。注册 `pose33_v3`（baseline 2.0）与 `body_core_v1`（12 点躯干四肢核心，baseline 已标定为 `1.2826`）
- **core/action_compare.py**: 高层模板匹配 — 从视频建模板并与目标对比，含双模板（正面+侧面）对比、自动视角拆分，以及 `compare_dual_streams` 双独立流评分入口
- **core/body_core_compare.py**: `body_core_v1`（12 点）模板闭环（生成→匹配），YOLO 与 MediaPipe 均可生成同布局模板供对照；提供离线 high-quality body-only 分析入口（`DEFAULT_YOLO26L_MODEL_NAME`）。结果恒 `score_authorized=False` / `display_scope=internal`
- **core/yolo_adapter.py**: YOLO 进入主链路的**唯一入口**，ultralytics YOLO-pose 的 COCO17 → BlazePose33-like 映射；提供边界 `infer_frame()` 与实时 `annotate()`。结构性缺失点（嘴角/手指/脚跟脚尖/眼细分）在序列层 `valid_mask=False`、边界层 `synthetic=True`/`visibility=0.0`，**不得伪造成有效点**。所有 artifact 经 `_yolo_authorization_meta()` 强制写入 `raw_layout=pose33_like_coco17` / `feature_layout=body_core_v1` / `capability` / `score_authorized=False` / `calibration_status=unvalidated` / `display_scope=limited|internal`
- **core/rule_scoring.py**: 规则扣分引擎，基于原始 Pose33 关键点计算违规比例与扣分；缺失能力进入 skipped/missing，不贡献正式扣分
- **core/parallel_pose_engine.py**: 多核并行姿态推理引擎（IMAGE 模式）
- **core/recording_controller.py**: 录制/暂停运行时控制状态机（与 Tkinter 解耦，可独立单元/属性测试）
- **core/model_manager.py**: 模型清单（`MODEL_SPECS`）与下载管理。MediaPipe 模型可自动下载；YOLO26n/s/L/X 为分档元数据 + 手动安装（不可自动下载）
- **core/paths.py**: 仓库级 artifact 根目录统一解析（含 PyInstaller 冻结模式锚定到 exe 同级目录）
- **core/video_writer.py**: 编解码器自适应视频输出，回退链 H.264 → MJPEG → XVID

### Apps 入口

- **apps/main.py**: CLI 入口，支持摄像头/视频源 + 可选导出；摄像头 + `--workers>1` 走多核并行实时路径
- **apps/app_ui.py**: Tkinter GUI（主预览窗 + 单视频「动作分析」对话框 + 设置/模型管理），线程化非阻塞处理
- **apps/ui_backend.py**: Vue/Tauri 桌面前端的 JSON bridge 契约层，调用既有 Python 后端（模型管理、会话、作业、分析、模板等）；含 latest-frame 二进制通道与 router 路由透传
- **apps/camera_enum.py**: 摄像头枚举与输入源状态模型（Windows DirectShow 友好名、`open_camera()` 高帧率协商）
- **apps/make_template.py / match_template.py**: 模板创建/匹配 CLI

### Analysis & Batch（离线工具，不接默认生产路径）

- **analysis/**: 离线分析、标定与 benchmark harness，**不接入默认 CLI/UI 生产评分路径**
  - `tech_eval.py`：full 技术评估（直拳技术指标）实现，主链路后端保持 MediaPipe
  - `calibrate_body_core.py`：`body_core_v1` S3 标定（baseline/conf sweep/多人闸门），产出带授权元数据的 CSV/JSONL/NPZ
  - `bench_annotate_fps.py`：MediaPipe/YOLO 端到端 FPS 与 GPU delegate / FP16 / imgsz benchmark
  - `offline_matching_profile.py`：离线 DTW / 序列提取 profile（先 profile 后优化）
  - `spike_yolo_baseline.py`：YOLO 实验 spike；tech_eval 自检已迁入 `tests/test_selfcheck_tech_eval.py`
- **batch/**: 离线批处理 CLI
  - `backend_options.py`：共享 `backend_router` 的 CLI 适配层（`--backend` / `--feature-layout` 校验与 meta 透传）
  - `batch_dual_compare.py` / `batch_export_skeleton.py` / `batch_tech_eval.py`：默认 MediaPipe `pose33_v3`；显式 `body_core_v1` 时走 YOLO 调试闭环，输出与对外评分列分离、多人标「需人工复核」。`batch_dual_compare.py --paired` 仅在默认 `pose33_v3` 路径中按学员正/侧文件名配对并调用 `compare_dual_streams`

### Frontend (Vue + Tauri)

- **frontend/src/**: Vue 3 + Vite 前端 — `App.vue`、bridge 客户端（`bridge.ts` / `bridge-state.ts` / `bridge-lifecycle.ts`）；预览走 Canvas/ImageBitmap，**不保留大图 base64 / blob URL 历史**
- **frontend/src-tauri/**: Tauri 2 Rust 壳、capabilities、bundle 配置；持有 per-session 单槽 latest-frame store；sidecar 为打包后的 Python bridge
- **scripts/**: `verify-desktop-stack.ps1`（一键验证）、`build-tauri-sidecar.ps1`（构建 sidecar）、`start-tauri-dev.ps1`（`npm run dev:desktop`）
- **packaging/pyinstaller/**: Tauri sidecar 的 PyInstaller runtime hook

### Processing Modes

- **VIDEO mode**: 实时摄像头/流的时序跟踪 + 平滑，单线程、有状态
- **IMAGE mode**: 离线批处理的无状态逐帧处理，多线程提升吞吐

### Threading Model (offline)

1. Reader 线程填充输入帧队列
2. Worker 线程独立处理帧（IMAGE 模式）
3. Main 线程重排结果并写输出

### Pose Normalization Pipeline (pose_features.py)

Landmarks 11-32（排除脸部）→ 以髋部中心平移 → 按躯干长度（v3）或肩宽（v1/v2）缩放 → 旋转对齐肩/躯干 → 输出 (22, 2) 张量。

存在多版本 normalizer（`normalize_pose_xy_v1` / `_v3`）；模板记录 `feature_layout`，对比时自动选用匹配的 normalizer。**不得改变 MediaPipe 旧默认路径行为**（`pose33_v3` 模板、`infer()`/`annotate()`），以 `tests/test_pose33_v3_golden.py` 不漂移为准绳。

### Dual-Template Comparison Pipeline

学员视频（含正面+侧面）对标准正/侧模板：

1. 提取学员视频姿态特征 + 逐帧「frontness」分
2. 按 frontness 中位阈值自动拆分正面/侧面段
3. 用 motion-energy 自相关从各标准模板提取代表性周期
4. 各段多匹配子序列 DTW；trimmed mean 聚合（≥3 次时丢弃 max/min）
5. 正/侧分加权平均 → 整数百分制（0-100）
6. 可选规则扣分（`rule_scoring.py`）

批处理的默认模式仍按上述单学员单视频自动拆分。显式 `batch_dual_compare.py --paired` 时，`student_dir` 内同一目录下同一学员的正面/侧面文件按 `_FRONT_KEYS` / `_SIDE_KEYS` 关键词配对，并与标准正/侧模板一起送入 `compare_dual_streams(front_tpl, side_tpl, front_video, side_video)`；CSV `video` 列写学员 id，`--export_raw` 在 paired 模式跳过并提示，`body_core_v1` 调试路径不接 paired。

### Desktop Bridge Contracts（要点，权威版见 `AGENTS.md`）

- `apps/ui_backend.py` 对外输出 JSON bridge envelope；异常也要归一为带 `ok=false`、`requestId`、`jobId`/`sessionId` 的结构化响应，不抛裸异常
- `doCompare=true` 的模板比对请求**优先于** `qualityProfile=high_quality`；不要让声明模板对比的请求被高质量分析路由抢走
- 大预览帧走本机二进制 latest-frame 通道：Rust 持有 per-session 单槽 JPEG bytes，Python 复用本机 TCP 长连接写入，`session.frame` JSON 只携带 `frameId`/`frameHandle`/`frameToken` 与指标，**不含 base64 图片**；前端 raw IPC 按实际返回 `frameId` 做会话隔离与单调不回退检查后再绘制 canvas 和更新指标
- 停止/卸载时取消 active session / analysis / template / model download job；late response **不得复活终态**
- 安装版 sidecar **不打包 YOLO runtime**（`torch`/`ultralytics`/`core.yolo_adapter` 在 excludes）；所有桌面 YOLO 路由必须能表达 runtime/model 不可用时的 fallback 或结构化错误

## YOLO 迁移状态与硬约束（S6 决策已定）

迁移已走完决策门。权威文档：`docs/yolo_migration_plan_optimized.md`（三审定稿）、`docs/yolo_migration_issues.md`、`docs/yolo_default_switch_decision.md`（S6 决策）、`docs/yolo_body_core_calibration.md`（标定）、`docs/yolo_gpu_recheck_report.md`（GPU 复测）。

**S6 结论**：

- 正式评分、规则评分、full tech_eval、CLI 默认路径、Tkinter 默认路径**全部不切 YOLO**，继续 MediaPipe
- Vue/Tauri 桌面可在受控条件使用 body-only YOLO：
  - `enableHands=false` 且 YOLO26n/s 可用 → 实时 body-only preview，`displayScope=limited`、`scoreAuthorized=false`
  - `enableHands=false` 且 YOLO26L 可用 → 离线 high-quality body-only 内部分析，`displayScope=internal`、`scoreAuthorized=false`、`calibrationStatus=unvalidated`
  - 缺模型 / 安装版 runtime 不支持时：实时 preview 回退 MediaPipe 并展示 fallback；离线 high-quality 返回结构化不可用/下载错误，**不静默冒充成功**
- `apps/main.py` 不新增 `--backend yolo` 实时入口；`apps/app_ui.py` 不新增 YOLO 后端选择
- Hybrid（`yolo_body_mp_pose_supplement`）不实现，不保留半成品 runtime

**硬约束（务必遵守）**：

- **不得改变 MediaPipe 旧默认路径行为**：`pose33_v3` 模板、`infer()`/`annotate()`、旧模板兼容，以 `tests/test_pose33_v3_golden.py` 不漂移为准绳
- COCO17 缺嘴角/脚跟脚尖/手指，**YOLO-only 不进入 full tech_eval、不进入对外正式评分**，只做预览 / 模板匹配 / skip-aware partial eval
- 缺失点不得伪造成有效点；有效性判据统一走 `valid_mask`，不散落 `lm[idx,3] >= thr`
- `body_core_v1` 标定参数已落库（baseline `1.2826`、YOLO `valid_conf_thr=0.6`），但状态仍是 `calibration_status=unvalidated`、`score_authorized=False`，未标定分数不得进入对外报告
- `enableHands=false` 但请求手指能力时，走 MediaPipe pose-only partial 并标注 skipped capabilities，**不静默启用手部检测，也不误走 YOLO**
- `qualityProfile=high_quality` + body-only + `enableHands=true` 应返回 `bad_request`，要求显式 `enableHands=false` 后再进入 YOLO26L 内部分析
- YOLO artifact 必须携带后端与授权元数据：`backend` / `raw_layout` / `feature_layout` / `capability` / `score_authorized` / `calibration_status` / `display_scope`

## Coding Conventions

- Python 4-space 缩进，函数尽量小且带类型标注
- 模块边界清晰：UI 逻辑留在 `apps/app_ui.py` / `frontend/`，bridge 适配在 `apps/ui_backend.py`，推理与评分留在 `core/` / `analysis/`。**不要把视觉算法搬进 Rust 或 TypeScript**
- 后端路由只走 `core/backend_router.py`，不要在 CLI/UI/batch 入口层复制分叉判断
- 前端不存大图 base64/blob URL 历史；实时预览用 Rust-owned latest-frame 通道 + 帧身份单调不回退 guard
- **视频导出默认 H.264**：本机 OpenCV 构建不含 H.264 编码器，`open_video_writer` 会回退成 MJPG/XVID AVI。导出/离线出片后统一用系统 `ffmpeg` 转 H.264 MP4（`-c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p`），转码完成删掉临时 AVI。不要把回退 AVI 当最终产物交付
- MediaPipe 模型首次运行自动下载到 `models/`（gitignored）；YOLO 权重需手动安装到 `models/`
- 不提交大产物（models/videos）与生成产物（`dist/`、`build/`、`frontend/dist/`、`frontend/src-tauri/target/`、`frontend/src-tauri/resources/*.exe`）
- Conventional Commits：`feat:`、`fix:`、`refactor:`、`docs:`、`test:`、`chore:`

## 任务完成规范

- **每次完成任务后，必须将修改总结写入当前 `change.md` 文件（最新记录置顶）。`change.md` 累积过长时，用 `git mv` 将其按时间段归档为 `change（<起>~<止月>）.md` 并重建空 `change.md`，把「归档与重建」本身作为新 `change.md` 的首条记录，并同步更新本规则的归档清单。历史归档：`change（start~2026.5）.md`、`change（2026.5~2026.6）.md`、`change（2026.6~2026.7）.md`**
- 记录内容应包括：修改日期、问题描述、修改内容、验证方法
- 如果只改文档，也要记录文档同步依据和至少一次轻量验证
