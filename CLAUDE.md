# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

武术散打动作识别与评分系统。基于 MediaPipe 的实时姿态/手势识别，使用 DTW（动态时间规整）做动作模板匹配，支持双模板（正面+侧面）对比评分与规则引擎扣分。

两套桌面前端并存：
- **Tkinter GUI**（`apps/app_ui.py`，迁移期保留的旧入口）
- **Vue + Vite + Tauri 桌面前端**（`frontend/`，Windows-only），通过 `apps/ui_backend.py` 的 JSON bridge 调用既有 Python 后端

视觉后端正在推进 **MediaPipe → YOLO 迁移**（见下方专节）；MediaPipe 仍是默认主链路。

> 与 `AGENTS.md` 配合阅读：`AGENTS.md` 含项目结构、网络代理约定（端口 `7890`）和 YOLO 迁移硬约束的权威版本。

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

本仓库已有 pytest 测试套件（`tests/`），不再是「无测试」状态。

### Python 测试
```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```
关键回归（YOLO 迁移安全网 + 桌面迁移）：
```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_pose33_v3_golden.py tests/test_valid_mask_migration.py -q
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
.\.venv\Scripts\python.exe -m py_compile .\apps\main.py .\apps\app_ui.py .\apps\ui_backend.py .\core\vision_pipeline.py .\core\pose_features.py .\core\action_compare.py
```

## Architecture

### Core 模块职责

- **core/vision_pipeline.py**: MediaPipe 封装（`MediaPipePipeline`），处理 pose/hand landmarking、帧标注、动作分类（HANDS_UP / SQUAT / V-sign）
- **core/pose_features.py**: 姿态归一化（平移/缩放/旋转不变）与 DTW 子序列匹配
- **core/feature_layout.py**: 特征布局注册表（`FeatureLayoutSpec`），把热路径里散落的 `(22, 2)` 硬编码收敛到显式布局对象（补零/mirror/误差统计/周期裁切按 layout 取值）；YOLO 迁移 S1/Issue #4
- **core/action_compare.py**: 高层模板匹配 — 从视频建模板并与目标对比，含双模板（正面+侧面）对比与自动视角拆分
- **core/body_core_compare.py**: YOLO `body_core_v1`（12 点躯干四肢核心）离线模板闭环（生成→匹配），MediaPipe 亦可生成同布局模板供三方对比；YOLO 迁移 S2/Issue #8
- **core/yolo_adapter.py**: YOLO 进入主链路的**唯一入口**，ultralytics YOLO-pose 的 COCO17 → BlazePose33-like 映射。结构性缺失点（嘴角/手指/脚跟脚尖/眼细分）在序列层 `valid_mask=False`、边界层 `synthetic=True`/`visibility=0.0`，**不得伪造成有效点**；YOLO 迁移 S2/Issue #7
- **core/rule_scoring.py**: 规则扣分引擎，基于原始 Pose33 关键点计算违规比例与扣分
- **core/parallel_pose_engine.py**: 多核并行姿态推理引擎（IMAGE 模式）
- **core/recording_controller.py**: 录制/暂停运行时控制状态机（与 Tkinter 解耦，可独立单元/属性测试）
- **core/model_manager.py**: MediaPipe 模型清单与下载管理（供 UI「设置 → 模型管理」）
- **core/paths.py**: 仓库级 artifact 根目录统一解析；YOLO 迁移 S1/Issue #6
- **core/video_writer.py**: 编解码器自适应视频输出，回退链 H.264 → MJPEG → XVID

### Apps 入口

- **apps/main.py**: CLI 入口，支持摄像头/视频源 + 可选导出
- **apps/app_ui.py**: Tkinter GUI（主预览窗 + 对比对话框），线程化非阻塞处理
- **apps/ui_backend.py**: Vue/Tauri 桌面前端的 JSON bridge 契约层，调用既有 Python 后端（模型管理、会话、作业、分析、模板等）
- **apps/camera_enum.py**: 摄像头枚举与输入源状态模型（Windows DirectShow 友好名）
- **apps/make_template.py / match_template.py**: 模板创建/匹配 CLI

### Frontend (Vue + Tauri)

- **frontend/src/**: Vue 3 + Vite 前端 — `App.vue`、bridge 客户端（`bridge.ts` / `bridge-state.ts` / `bridge-lifecycle.ts`）
- **frontend/src-tauri/**: Tauri 2 Rust 壳、capabilities、bundle 配置；sidecar 为打包后的 Python bridge
- **scripts/**: `verify-desktop-stack.ps1`（一键验证）、`build-tauri-sidecar.ps1`（构建 sidecar）、`start-tauri-dev.ps1`
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

## YOLO 迁移任务（进行中）

仓库正在推进 MediaPipe → YOLO 视觉后端迁移。权威计划与硬约束见 `AGENTS.md` 与 `docs/`：

- 计划：`docs/yolo_migration_plan_optimized.md`（三审定稿）；任务细化 `docs/yolo_migration_issues.md`
- 阶段：S0 决策门 → S1 MediaPipe 加固（golden 回归基线先行）→ S2 YOLO 离线闭环 → S3 标定 / S4 评估分级

硬约束（务必遵守）：

- **不得改变 MediaPipe 旧默认路径行为**；以 `pose33_v3` golden 回归不漂移为验收准绳
- COCO17 缺嘴角/脚跟脚尖/手指，**YOLO-only 默认不是 full tech_eval 候选**，只做预览 / 模板匹配 / skip-aware partial eval
- 缺失点不得伪造成有效点；有效性判据统一走 `valid_mask`，不散落 `lm[idx,3] >= thr`
- YOLO 侧阈值在 S3 标定前为待标定占位值，未标定分数不得进入对外报告

## Coding Conventions

- Python 4-space 缩进，函数尽量小且带类型标注
- 模块边界清晰：UI 逻辑留在 `app_ui.py`，推理逻辑留在 `vision_pipeline.py`；前端 Vue/Tauri 代码留在 `frontend/`，bridge 适配在 `apps/ui_backend.py`。**不要把视觉算法搬进 Rust 或 TypeScript**
- 模型首次运行自动下载到 `models/`（gitignored）
- 不提交大产物（models/videos）与生成产物（`dist/`、`build/`、`frontend/dist/`、`frontend/src-tauri/target/`、`frontend/src-tauri/resources/*.exe`）
- Conventional Commits：`feat:`、`fix:`、`refactor:`、`docs:`

## 任务完成规范

- **每次完成任务后，必须将修改总结写入当前 `change.md` 文件；历史记录归档于 `change（start~2026.5）.md`**
- 记录内容应包括：修改日期、问题描述、修改内容、验证方法
