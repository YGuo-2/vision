# 性能优化清单（Performance Optimization Inventory）

> 生成日期：2026-06-14
> 范围：**忽略「该不该加大 Rust」这一框架问题，只列「能提升性能」的具体改动**。涵盖推理侧、离线分析 CPU 热循环、批处理 / 视频 I/O、预览传输 / 前端 canvas / 打包启动四大块。
> 方法：基于三轮并行只读代码调研（预览帧链路、非预览 bridge/作业/启动、四块性能旋钮）综合而成，所有条目均带 `file:line` 与当前默认值。
> 性质：**纯清单，未改任何代码**。落地需逐条按下文「风险分级」验证。

---

## 风险分级图例

| 标记 | 含义 |
|---|---|
| 🟢 | 不动评分语义，代数/数值等价或纯重构，改完跑一次金标确认即可 |
| 🟡 | **会碰 `pose33_v3` 金标**（`tests/test_pose33_v3_golden.py` / `tests/fixtures/golden.json`：score `ABS_TOL=1e-4`，`combined_percent`/`rule_score`/`segments`/`joint_errors` 精确断言）。必须证明结果不漂移，或作为「评分变更」单独决策 |
| ⚪ | 纯展示 / 打包 / 编排 / 传输，无数值风险 |

**贯穿性硬约束**（来自 `CLAUDE.md` / `AGENTS.md`）：
- 不得改变 MediaPipe 旧默认路径行为（`pose33_v3` 模板、`infer()`/`annotate()`），以金标不漂移为准绳。
- 正式评分 / full tech_eval / 模板提取的后端与模型档位（VIDEO-mode CPU、`full`/`heavy`、`enable_hands=False`）不许动。
- 不把视觉/编解码算法搬进 Rust 或 TS；后端路由只走 `core/backend_router.py`。
- 安装版 sidecar 不打包 YOLO runtime；YOLO body-only 路由保持 `score_authorized=False` / `display_scope=limited|internal`。

---

## 优先级总览（按性价比）

| # | 优化项 | 区域 | 收益 | 成本 | 风险 |
|---|---|---|---|---|---|
| 1 | 实时预览接 `ParallelPoseEngine`（多核） | 推理 | 高 | 中 | ⚪ |
| 2 | GPU delegate 接入（opt-in + 回退） | 推理 | 高 | 中 | 🟡仅默认时 |
| 3 | 预览 `enable_hands` 默认关 | 推理 | 中 | 低 | 🟢 |
| 4 | 预览默认 `lite` 档模型 | 推理 | 中 | 低 | 🟡仅预览 |
| 5 | DTW 局部代价矩阵向量化 | 离线CPU | 高 | 中 | 🟢代数等价 |
| 6 | 单次抽帧（消 2–5× 重复推理） | 离线CPU/批 | 高 | 中 | 🟡需验证 |
| 7 | 批处理跨视频并行化 | 批处理 | 高 | 中 | ⚪ |
| 8 | PyInstaller onefile→onedir | 打包/启动 | 高 | 中 | ⚪ |
| 9 | 每帧归一化向量化 | 离线CPU | 中 | 低 | 🟢代数等价 |
| 10 | 预览常量调档（FPS/质量/分辨率） | 预览 | 中 | 低 | ⚪ |
| 11 | 前端 `bitmaprenderer` + 缓存 context | 前端 | 中 | 中 | ⚪ |
| 12 | sidecar 预热预拉起 | 启动 | 中 | 中 | ⚪ |

---

## A. 推理侧（每帧最大杠杆）

| ID | 优化项 | 位置 | 现状 | 改法 | 收益/成本/风险 |
|---|---|---|---|---|---|
| **A1** | 实时预览不吃 `workers` | `ui_backend.py:1465,1625-1726`；对比 `main.py:508-596 run_realtime_parallel` | 桌面预览恒用单条 VIDEO 管线串行 `annotate`，`workers` 被捕获但从不用于并行。`parallel_pose_engine.py:6-9` 自述：单管线 heavy ~15-18fps，4-6 worker ~45-57fps | `source==camera && workers>1` 时改走已有 `ParallelPoseEngine(..., drop_when_full=True)`，默认 `workers=1` 不变 | 高 / 中 / ⚪（预览 `scoreAuthorized=false`）。代价：IMAGE 模式无时序平滑→骨架抖 |
| **A2** | GPU delegate 全程未接 | `vision_pipeline.py:172-193`；`ui_backend.py:2184-2191`；各 `main.py` factory；`parallel_pose_engine.py:69-77` | `delegate` 默认 `"cpu"`，GPU 路径已实现且有测试，但无任何生产 factory 传过 `delegate="gpu"`，等于全暗 | opt-in 贯通 `PipelineConfig.delegate` + `--delegate gpu`，捕获 `:180` RuntimeError 自动回退 CPU；默认保持 cpu | 高 / 中。有 GPU 时 full/heavy 快 2-4×。🟡：**正式评分/tech_eval 绝不走 GPU**，否则金标漂移 |
| **A3** | 预览 `enable_hands` 默认 True | `vision_pipeline.py:192`；`ui_backend.py:376,990,1238,2004`；推理 `:286,289` | 每帧双模型（Pose + Hand×2）；离线特征提取已强制 `enable_hands=False`（`action_compare.py:192,274`） | 预览默认改 pose-only，手部做 UI 显式开关 | 中 / 低。砍掉每帧一整次 landmarker。🟢。需改 `test_ui_backend_sessions` 默认断言 |
| **A4** | 预览用 `full`，`lite` 从不用 | `vision_pipeline.py:187`；`ui_backend.py:374,2052`；模板侧 `:686,1974` 用 `heavy`；`model_manager.py:82-89`（heavy ~29MB / full ~9MB / lite ~5.5MB） | 预览 `full`、模板/tech_eval `heavy`，`lite` 哪都没默认 | 仅预览默认 `lite`（或无 GPU+高 FPS 时自动选 lite）；模板/评分维持 heavy/full | 中 / 低。lite 约翻倍 fps。🟡：只改预览默认，评分档位 pinned 不许动 |
| **A5** | 满分辨率喂模型 | `ui_backend.py:1688,2526-2544`；`camera_enum.py:227` | 1280×720 原帧直接喂 `infer`，960 下采样只作用于发前端的 JPEG | 预览路径在 `mp.Image` 前把输入降到 ~640-720 长边（MediaPipe 内部本就会再缩放，landmark 归一化不变） | 低 / 低。🟡：评分路径不许降输入 |
| **A6** | `annotate` 满分辨率 copy+draw | `vision_pipeline.py:260-275` | 每帧 `frame_bgr.copy()`（满分辨率）+ 33 点抗锯齿绘制，跑在推理关键线程 | 预览加「在已下采样帧上绘制」轻量变体；离线导出维持原 `annotate` | 低 / 中 / ⚪（纯像素），但录制收到的帧不能变 |
| **A7** | warmup 只热相机管线 | `ui_backend.py:1230-1276,1190-1228` | warmup 写死 `source="0"`，视频/模板/tech_eval 每次冷建管线，heavy `.task` ~29MB 每次冷加载 | warmup 接受即将运行任务的 variant，预热对应模型文件/图 | 低 / 中 / ⚪（仅首帧延迟） |
| **A8** | 管线缓存 key 类型陈旧 | `ui_backend.py:1194 vs 1200-1205` | 注解写 2-tuple，实际返回 3-tuple `(backend, model_profile, enable_hands)` | 修注解为 3-tuple + 单测断言不同 variant 不撞 key | 低 / 低 / ⚪（防未来误用错模型，反保护金标） |

---

## B. 离线分析 CPU 热循环（DTW / 特征 / 规则）

> `analysis/offline_matching_profile.py` 已有 stage 计时与 decision_table（不实现优化，仅定位）。**B7/B8 先 profile 再做**；B1/B3/B4①/B5 是已确认安全的即取即得项。

| ID | 优化项 | 位置 | 改法 | 收益/成本/风险 |
|---|---|---|---|---|
| **B1** | DTW 逐格 `np.linalg.norm`（离线最大头） | `pose_features.py:653-669`，重复于 `:700-716` | 一次性向量化局部代价矩阵 `C=np.sqrt(((q[:,None]-s[None])**2).sum(-1))`（float32），DP 循环只剩加法+分支 | 高 / 中 / 🟢（与 norm 差 <1e-6，DP 顺序不变） |
| **B2** | 单次抽帧（消重复推理） | `action_compare.py:918-929,1024-1029`；`rule_scoring.py:136-217` | 全视频抽一次 raw Pose33+valid_mask，规则/误差分析切片复用，不再重开 `VideoCapture` 重推理 | 高 / 中 / 🟡（真实 VIDEO-mode 有时序态，子段 vs 全程推理可能微差；金标 replay 下相同，需真模型验证规则分一致） |
| **B3** | 每帧归一化 Python 循环 | `pose_features.py:452-460`（v3）等 | 整帧向量化：`out=np.clip(((pts-center)/scale)@R.T,-5,5)`，1 次 matmul/clip/alloc 取代 22 次 | 中 / 低 / 🟢（`pts@R.T` 与逐行 `R@p` 数学等价，需保 float32 与失效判定 `:461-463`） |
| **B4** | 规则评分每帧循环 + `_build_rules()` 每次重建 | `rule_scoring.py:431` + 各 `:224-366` | ①`_RULES=_build_rules()` 提到模块级（frozen dataclass，零风险）；②有效性 `valid_mask[:,idxs].all(axis=1)`、角度/距离用 `np.arctan2/einsum` 沿 T 轴向量化 | 中 / 中 / 🟡（①安全；②比例边界 `>=trigger_ratio` 必须金标验证） |
| **B5** | 关节误差聚合逐元素 append | `action_compare.py:1031-1064`（仅 `enable_error_analysis`） | 按 path 向量化 `D=sqrt(((A-B)**2).sum(-1))` 一把算，掩码做 masked reduction | 中 / 低 / 🟡（mean/p90/max 顺序无关，只需纳入谓词「可见 AND 有限」完全一致） |
| **B6** | mirror DTW 每轮重算 + query 反复 reshape | `action_compare.py:556-567,543`；`pose_features.py:645-646` | query reshape/astype 提出循环；按段 memoize DTW，仅对被排除步切分过的段重算 | 中 / 中 / 🟡（缓存失效须精确镜像排除逻辑 `:599-608`，否则 combined_percent 漂移） |
| **B7** | 自相关周期估计逐 lag 循环 | `action_compare.py:452-466` | 改 FFT 自相关 `np.correlate`/rfft；保留同一归一化分母与 `best_corr<0.15`/`period<8` 阈值与 keep-first tie | 低 / 中 / 🟡（影响所选代表周期→金标；~90 lag 收益小、相对风险高，**profile 证明热点再做**） |
| **B8** | 无 Sakoe-Chiba 带 | `pose_features.py:649-688`；profiler `:711-718` 已标 defer | **不要静默加默认带**——会改子序列起止与分数。如做，须按 fixture score+interval 等价门控，视为评分变更 | 中 / 高 / 🟡（直接改 DTW 语义） |

---

## C. 批处理 + 视频 I/O

| ID | 优化项 | 位置 | 改法 | 收益/成本/风险 |
|---|---|---|---|---|
| **C1** | dual-compare 每视频重抽 2-5× | `action_compare.py:918-929,1024-1029`；`batch_dual_compare.py:139-147` | 同 B2 单次抽帧（`--rules --error-analysis both` 现状最多 5 趟） | 高 / 高 / 🟡 |
| **C2** | `batch_dual_compare` 全串行 | `batch_dual_compare.py:138-147`（`workers=1` 写死） | 仿 `batch_tech_eval.py:200-205` 用 `ThreadPoolExecutor` 跨视频并行，每线程独立管线（MediaPipe 非线程安全），结果按序写；加 `--workers` | 高 / 中 / ⚪（单管线 ~90% 核空闲） |
| **C3** | `batch_export_skeleton` 全串行 | `batch_export_skeleton.py:276-338,86-94` | 加 `--workers` + 线程池，每 worker 一管线，manifest 按输入序排 | 高 / 中 / ⚪ |
| **C4** | body_core 调试批每视频抽两次 | `batch_dual_compare.py:372-388`；`body_core_compare` match 路径 | 抽一次特征序列，对 front/side 两模板各跑（廉价的）DTW；`match_body_core_template` 接受预抽特征 | 高 / 中 / 🟡（保 `score_authorized=False`/internal/多人闸门不变） |
| **C5** | 段重抽从帧 0 解码+推理（无 seek） | `rule_scoring.py:170-193`；`tech_eval.py:245-273` | 远于 `start_i` 的帧只解码不推理，临近 ~15 帧 warm-up 窗口再推理（或并入 C1/B2）。推理 heavy ~55ms/帧 ≫ 解码 ~1-3ms | 中 / 中 / 🟡（warm-up 窗口长度影响时序态，需保足够 warm-up） |
| **C6** | `batch_tech_eval --full+--debug` 重抽 2-3× | `batch_tech_eval.py:139-188` | 收紧分支保证每视频恰好一次推理（overlay 解码不重推理，已确认） | 中 / 低 / ⚪ |
| **C7** | 多线程路径编码串行 + 写死 `mp4v` | `main.py:223-257,175/463/532` | ①`writer.write()` 移到独立编码线程（有序队列）；②改走 `core/video_writer.open_video_writer` 的 avc1→H264→MJPG→mp4v 回退链 | 中 / 中 / ⚪（高分辨率/高 worker 时收益大；回退可能改容器扩展名，调用方接 `actual_path`） |
| **C8** | reader 解码无 overlap/GPU 解码 | `main.py:184-194` | 低优先，**profile 先**：增 `frame_q` 深度防 starve；GPU/硬解仅 decode-bound 时 | 低 / 中 / ⚪ |

---

## D. 预览传输 + 前端 canvas + 打包/启动

### D-常量：纯数字调档（⚪，仅作用于发给前端的预览副本，不碰录制/评分）

| 常量 | 位置 | 当前值 | 建议 |
|---|---|---|---|
| `PREVIEW_JPEG_QUALITY` | `ui_backend.py:69` | `70` | 降到 **55-60**，每帧字节 -20~30% |
| `PREVIEW_MAX_EDGE` | `ui_backend.py:70` | `960` | 降到 **720/640**，像素 -44~55%（编码+payload+canvas 同减） |
| `PREVIEW_FRAME_EVENT_MIN_INTERVAL_S` | `ui_backend.py:71` | `1/30` | 降到 **1/20**，发布/编码量 -33%；建议给离线视频循环（`~1586-1623` 现每帧都编码）也补节流 |
| `PREVIEW_CAPTURE_IDLE_SLEEP_S` | `ui_backend.py:72` | `0.001` | 弱机可升到 3-5ms 省 CPU |
| 编码下采样滤波 `INTER_AREA` | `ui_backend.py:2539` | — | 保持不动（下采样正确滤波，非瓶颈） |
| 单槽缓冲区 | `ui_backend.py:428-521` | — | **别动**——已是正确 latest-wins 背压，换队列会反向劣化 |

> 建议把上面前 4 个做成 env/route 覆盖（如 `VISION_PREVIEW_MAX_FPS`），强机保 30、弱机降档。

### D-打包/启动（最大单点）

| ID | 优化项 | 位置 | 改法 | 收益/成本/风险 |
|---|---|---|---|---|
| **D1** | sidecar 是 ONEFILE | `ui_backend_sidecar.spec:77-95`（已确认无 `COLLECT`、`runtime_tmpdir=None`） | 每次启动把整个 mediapipe 包自解压到 `%TEMP%/_MEI*`。改 **onedir（加 COLLECT）**，同步改 `build-tauri-sidecar.ps1`、`tauri.conf.json` resources、`lib.rs` 路径解析 | 高 / 中 / ⚪。冷启动省数秒。需过 `test_windows_packaging_smoke.py`。`heavy_excludes`（torch/ultralytics/yolo `:46-60`）不动 |
| **D2** | sidecar 懒拉起 | `lib.rs:265-307,625-634` | 现首次操作才付解压+import 代价。改成 Tauri 启动 splash 期 `ping` 预拉起 | 中 / 中 / ⚪。配合 D1 最佳 |
| **D3** | 30s 超时含冷解压 | `lib.rs:309-310` | 真正修法是 D1；保 onefile 则给 `session.start` 更长超时 | 低 / 低 / ⚪ |
| — | UPX | `spec:87` | **保持 `upx=False`**——开了反而增解压 CPU + 杀软误报 + DLL 崩 | — |

### D-前端 canvas / 传输（⚪ 纯展示）

| ID | 优化项 | 位置 | 改法 | 收益/成本 |
|---|---|---|---|---|
| **D4** | 每帧 `getContext('2d')` + 无 OffscreenCanvas/bitmaprenderer | `App.vue:711,723,837-843` | ①context 缓存一次；②换 `bitmaprenderer` context + `ctx.transferFromImageBitmap(bitmap)`（零拷贝 GPU 路径，免 drawImage 栅格化）。rAF 合并已正确，保留 | 中 / 中 |
| **D5** | `slice(8)` 每帧整帧拷贝 | `bridge.ts:117-125`；`App.vue:710` | 改 `new Blob([new Uint8Array(response,8)])` 视图免拷贝；保 frameId 单调守卫（`App.vue:740-748`） | 中 / 中 |
| **D6** | Rust 每帧 `slot.clone()` 深拷贝 | `lib.rs:331-340,362-365` | slot 存 `Arc<Vec<u8>>`，服务端 clone 变引用计数 +1，缩短锁持有 | 中 / 中（JPEG 才几十 KB，绝对值有限） |

---

## 建议执行顺序

1. **先摘最甜的、零数值风险**：A1（预览多核）、A3（关手部）、A4（预览 lite）、C2/C3（批并行）、D1（onedir）、D-常量。这批要么纯编排/打包/展示，要么只动预览默认，不碰金标，性价比最高。
2. **再上安全的离线向量化**：B1（DTW 代价矩阵）、B3（归一化）、B4①（规则表提升）、B5（误差聚合）——全部 🟢 代数等价，跑一遍金标确认即可。
3. **A2（GPU）单独做**：opt-in + 强制回退，严守「正式评分永不走 GPU」。
4. **B2/C1 单次抽帧**：高收益但 🟡，用真实 MediaPipe 验证规则分一致后再合。
5. **B7/B8、C7/C8、D2/D4-D6**：先 `offline_matching_profile.py` / `bench_annotate_fps.py` profile，证明是热点再投入。

> 若意图做出「结果有意改变」的优化（如 B8 加 DTW 带），需经 `tests/fixtures/regen_pose33_v3_golden.py` 重生金标并单独作为评分变更评审。

---

## 一句话背景结论

经两轮架构调研：web 端相对 Tkinter 的性能损耗，**主因是跨进程「JPEG 编码 → IPC → 解码」三角 + 推理 + onefile 冷启动**，这三者都不是「把代码搬进 Rust」能消掉的（Rust 已持有全部可持有的传输层）。因此本清单聚焦真正的杠杆：推理并行/档位、离线 CPU 向量化、批并行、打包与传输瘦身。
