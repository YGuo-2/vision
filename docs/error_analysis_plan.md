# 误差分析方案计划（A+B）

> 2026-09-18 更新：旧版学生练习现已改为 MediaPipe Lite CPU 关键点与几何/时序规则，不再使用本机 Qwen 服务。下文 C 节记录历史实验；当前实现及验收边界见《学生练习动作问题说明实施.md》。


目标：在不改变现有比对算法结果的前提下，新增“误差分析”产出，帮助定位具体哪条规则与哪个身体部位导致分数偏低。

范围：先实现 A 规则层误差分析 + B 关节/肢段误差分析，默认输出到批处理结果目录。

---

## A. 规则层误差分析（Rule Error Analysis）

### 输出文件
- error_rules.csv

### 输出字段
- video：视频文件名
- view：front/side
- rule_id：规则 ID（如 stance_elbow）
- rule_name：规则中文名
- violation_ratio：违规占比
- penalty：扣分（0/规则分）
- valid_frames：有效帧数（可见度满足要求）
- total_frames：该视角分段总帧数

### 计算逻辑
1. 使用现有规则引擎的“违规帧占比”结果。
2. 记录每条规则的有效帧数与违规占比。
3. 只要启用规则评分，默认输出 error_rules.csv。

### 价值
直接回答“哪条规则最拉分”，适合一眼定位问题点。

---

## B. 关节/肢段误差分析（Joint Error Analysis）

### 输出文件
- error_joints.csv

### 输出字段
- video
- view
- joint：关节名称（如 L_SHOULDER）
- mean_dist：平均偏差
- p90_dist：90 分位偏差
- max_dist：最大偏差
- valid_frames

### 计算逻辑
1. 使用模板与学员的 DTW 匹配路径，对齐后对每帧计算关节差异。
2. 关节集合：BlazePose 11..32（去脸部点，和现有特征一致）。
3. 对每个关节统计 mean / p90 / max 偏差。
4. 仅统计可见度足够的帧，记录 valid_frames。

### 价值
回答“哪个部位差”（例如手臂、下肢等），用于动作纠正。

---

## 集成方式

### 新增输出
在批处理输出目录内新增：
- error_rules.csv
- error_joints.csv

### 开关
新增 CLI 参数：
- --error-analysis（默认关闭）
  - 仅开启 A+B 分析，不影响现有相似度输出。

---

## 验证方式

1. 运行批处理并开启误差分析开关：
   .\.venv\Scripts\python.exe .\batch_dual_compare.py --standard_dir ... --student_dir ... --rules --action both --error-analysis
2. 检查输出目录存在 error_rules.csv 与 error_joints.csv。
3. 随机抽取 1 个视频，确认：
   - error_rules.csv 里有规则违规占比与扣分。
   - error_joints.csv 里有多个关节的误差统计值。

---

## 风险与边界

- 如果视角分段不稳定，误差分析可能被“转身帧”污染；可复用现有分段边界收缩逻辑。
- 当姿态检测质量差时，有效帧会很少，统计波动变大；需保留 valid_frames 作为可读性提示。

---

## C. Qwen3-VL 粗粒度视觉点评 + LoRA 微调

### 定位与边界

- 目标是对录制完成后的短视频给出「手臂未充分伸直、护手偏低、抬腿过高或过低、躯干倾斜、
  站姿不稳」等肉眼可见的粗粒度点评和修正建议。
- **不输出分数，不改变现有评分、模板比对、规则评分或 full tech_eval 结果。**
- 不要求模型计算精确角度、力量、肌肉发力或重心数值；证据不足时允许返回
  `unable_to_judge`。
- 每个动作使用独立的检查项白名单，禁止开放式发现任意问题。

### 已验证基线（2026-07-16）

- 本机 RTX 4060 Laptop 8GB 已在 `E:\AI\qwen3-vl\` 跑通
  `Qwen3-VL-4B-Instruct-Q4_K_M` + Q8 mmproj + `llama.cpp b10043`。
- 单图点评：6.42s，显存峰值 3900MiB。
- 4秒/24帧直拳视频点评：7.63s，显存峰值 4810MiB。
- `llama-server` 本地 HTTP API 启动与健康检查通过，服务常驻显存约 4606MiB。
- 开放提示能输出有效建议，但会混入「面部表情」等无关内容；严格提示又可能过度拒答。
  因此本机推理可行，产品可靠性仍需动作专属数据和微调解决。

### 学生练习 UI v1（prompt-only 实验版，2026-07-20）

面向**学生端**的极简练习入口（教师考试/模板评分路径不变）：

| 项 | 决策 |
|:---|:---|
| 入口 | `apps/app_ui.py` →「学生练习…」模式（非独立 exe、非 Vue） |
| 摄像头 | 双摄正 + 侧（复用现有 dual 预览/录制） |
| 交互 | **开始** = 开预览并开录；**结束** = 停录；**动作评判** = 手动触发 Qwen |
| 动作 | 仅直拳；中文问题/建议；**不打分** |
| 实现 | `core/qwen_coach.py`（抽帧 contact sheet + HTTP `llama-server`） |
| 服务 | 默认 `http://127.0.0.1:8091`；`scripts/start_qwen_server.ps1` |
| 落盘 | 片段目录可选写 `coach.json`（无分数字段）；**不写**考试台账 |

硬边界：学生模式强制 `auto_compare=False`、关骨架/手部推理；UI 标明「练习建议，非正式成绩」。  
**本版为 prompt-only 实验接入**，不替代后续 LoRA 验收门；正式教练一致性仍以微调+留出集为准。

直拳 v1 检查项白名单（`issue.code`）：

- `arm_not_extended` 出拳手臂未充分伸直  
- `guard_hand_low` 护手偏低  
- `torso_lean` 躯干过度倾斜  
- `stance_unstable` 站姿/重心不稳  
- `shoulder_hip_no_rotate` 发力转体不足  
- `punch_path_off` 出拳轨迹明显偏离  

### 微调路线

- 首选监督式 LoRA/QLoRA，不做全参数微调。
- 当前 Q4 GGUF 仅用于推理；训练使用官方可训练权重，完成后把 LoRA adapter 带回本机部署。
- 当前 8GB 笔记本用于推理和回归测试；4B 多帧/视频训练使用外部 GPU，24GB 作为实际起点，
  48GB 更适合增加帧数或 batch。
- 第一阶段只训练直拳，重点学习：检查项分类、拒答边界、中文教练建议和稳定 JSON 契约。

### 待办清单

- [x] 冻结第一阶段动作范围：只做直拳（学生 UI v1）。
- [x] 为直拳定义允许的问题类别、严重程度、建议模板和 `unable_to_judge` 契约（`core/qwen_coach.py`）。
- [x] 学生练习 UI v1（prompt-only）接入 Tk `app_ui`（开始/结束/动作评判/预览）。
- [ ] 建立未微调 baseline 评测集，覆盖合格、明显错误、遮挡、错误机位和模糊样本。
- [ ] 收集首批 300-500 条教练复核样本；必须包含足量合格样本与无法观察样本。
- [ ] 在外部 GPU 上训练第一版 Qwen3-VL-4B LoRA/QLoRA adapter。
- [ ] 在留出集评测教练一致率、误报率、拒答率、重复运行一致性、JSON 合法率、耗时和显存。
- [ ] adapter 明显优于 prompt-only baseline 且通过教练审核后，再升级学生 UI 默认推理路径。
- [ ] 直拳验收通过后，再扩展摆拳和腿法；不同动作不得共用无边界的开放提示。
