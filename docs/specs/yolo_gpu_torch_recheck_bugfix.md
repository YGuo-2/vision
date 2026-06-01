# YOLO GPU torch 环境误判修复规范

日期：2026-06-01
分支：`codex/fix-yolo-gpu-torch-recheck`
模式：Bugfix
依据：`docs/yolo_gpu_readiness_review.md`

## Bug 分析

### 问题

本机有 NVIDIA GeForce RTX 4060 Laptop GPU，但仓库 `.venv` 内安装的是 `torch=2.12.0+cpu`，
导致 `torch.cuda.is_available() == False`。此前 #23 GPU 复测把“CUDA runtime 不可用”判为
no-go，并连锁关闭 / 不实现 #25 CLI 实时预览、#26 UI 后端选择、#27 Hybrid、#28 默认切换。

### 根因

环境安装时未显式使用 PyTorch CUDA wheel 索引源，Windows 上得到 CPU 版 torch。错误前提是
“当前软件栈不能调用 GPU”，不是“RTX 4060 不具备价值”。

### 影响范围

- 必须重装 CUDA-enabled torch 并重新采集 #23 GPU benchmark。
- 必须用真实 GPU 结果修正 `docs/yolo_gpu_recheck_report.md`、S5/S6 决策文档、相关测试和 `change.md`。
- #10 标定结论与 COCO17 缺点仍独立存在；GPU 修复不得自动授权 YOLO 对外评分。
- MediaPipe 旧默认路径不得改变，`pose33_v3` golden 必须保持通过。

## 修复设计

1. 环境修复
   - 记录当前 torch / torchvision 状态。
   - 通过本地代理 `127.0.0.1:7890` 安装 CUDA 版 torch / torchvision。
   - 验证 `torch.cuda.is_available() == True`，设备名包含 RTX 4060。

2. GPU 复测
   - 使用 `analysis.bench_annotate_fps` 对 `docs/yolo_eval_samples.json` 复跑 #23。
   - 输出仍写入 gitignored `outputs/gpu_recheck/`，不提交原始产物。
   - 对照 #23 预注册阈值：6/6 样本覆盖、Hands 关 FPS 比 >= 1.30、Hands 开 FPS 比 >= 1.20、
     YOLO 失败 / 漏检率 <= 2%、body_core 抖动中位数 <= 0.006。

3. 文档与决策修正
   - 若 GPU 复测达标：撤销“因 CUDA 不可用导致 no-go”的结论，改为 GPU go，并把 #25/#26/#28 标为需要重开 / 重新决策。
   - 若 GPU 复测不达标：保留 no-go，但必须改为“CUDA 可用后的真实 GPU 数据 no-go”，不得再引用 CPU torch 无效前提作为最终依据。
   - 无论 go/no-go，都必须保留“YOLO 对外评分仍未授权”的边界。

4. 回归防护
   - 更新相关测试，禁止再把 `torch=...+cpu` 或 `torch.cuda.is_available()=False` 当作最终 #23 结论依据。
   - 保留或新增对 GPU 修复报告、S5/S6 决策边界、MediaPipe golden 的验证。

## 任务清单

- [x] 建立修复分支并保留 `docs/yolo_gpu_readiness_review.md`。
- [x] 验证当前 `.venv` 原为 CPU torch。
- [x] 安装 CUDA 版 torch / torchvision。
- [x] 验证 RTX 4060 可被 torch 识别。
- [x] 复跑 #23 GPU benchmark。
- [x] 根据真实 GPU 结果修正文档、测试与 `change.md`。
- [x] 跑 targeted tests、YOLO 相关测试、golden、全量测试与 `py_compile`。
- [x] 推送 PR，并交给子 agent 审查。
- [ ] 合并 PR 并清理分支。

## 验收证据

- `torch.cuda.is_available()` 当前输出。
- `analysis.bench_annotate_fps` 真实 GPU 复测输出摘要。
- 文档中不再把 CPU torch 无效环境作为最终 S5/S6 决策证据。
- 相关测试和全量测试通过。
- `change.md` 记录问题、修改内容、验证方法。

## 当前验证结果

- CUDA 探针：`torch=2.11.0+cu128`、`torchvision=0.26.0+cu128`、
  `torch.cuda.is_available()=True`，设备为 NVIDIA GeForce RTX 4060 Laptop GPU。
- #23 复测：6/6 样本有效，24/24 benchmark 记录成功；真实 GPU 数据仍 no-go。
- 目标测试：S5/S6/tracking 相关 19 项通过。
- YOLO 契约测试：59 项通过。
- `pose33_v3` golden：16 项通过。
- 全量测试：164 项通过。
