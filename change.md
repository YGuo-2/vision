## 2026-07-09: [chore] change.md 归档与重建

### 问题描述

`change.md` 累积至 586 行（覆盖 2026-06-14 ~ 2026-07-09），按任务完成规范需归档并重建空文件。

### 修改内容

- `git mv change.md "change（2026.6~2026.7）.md"`，重建空 `change.md`，本条为首条记录。
- 同步更新 `CLAUDE.md` 归档清单：新增 `change（2026.6~2026.7）.md`。
- 历史归档：`change（start~2026.5）.md`、`change（2026.5~2026.6）.md`、`change（2026.6~2026.7）.md`。

### 验证方法

- `ls change*.md` → 三份归档 + 空 `change.md`。
- `git mv` 保留文件历史（非删除重建）。

## 2026-07-09: [apps/core] 接通 Tkinter 实时直拳识别、预览平滑与录制 H.264 转码

### 问题描述

`core/online_matcher.py`、`templates/online/` 左右手直拳模板与 `core/preview_smoother.py` 均已就绪且单测全绿，但 `apps/app_ui.py` 未接线：Tkinter 实时预览无法显示在线识别结果，预览骨架未平滑，录制回退的 MJPG AVI 也未转 H.264。

### 修改内容

- `apps/app_ui.py`：
  - 新增默认开启的「实时动作识别」开关 + `match_var` 命中/分数显示，以及 `_build_online_matcher`/`_feed_online_matcher`/`_post_match` 三个接入边界；模板缺失/不兼容安全降级为无 matcher，关窗/停止竞态不刷新已销毁 UI。
  - 开关值经 Tk 主线程收进 `UiState.online_match_enabled`，worker 不跨线程读 `BooleanVar`；matcher 仅接单摄实时流，双摄/离线不接。
  - 单线程摄像头按 `infer(raw) → matcher(raw) → smoother → draw` 执行；文件 VIDEO 路径保留原 `annotate()`，帧序号/时间戳语义不变。
  - 并行摄像头启用 `ParallelPoseEngine(defer_draw=True)`，在有序出口喂 raw matcher、平滑并绘制，用采集 monotonic 时间戳保留满队列丢帧的真实间隔（顺带消除原「时序平滑关闭」抖动）。
  - 绘制均以 raw landmarks 做动作分类、smoothed landmarks 画骨架，smoother 不回流识别/评分序列。
  - 新增 `_transcode_async`，接入手动结束录制与单线程/双摄/并行视频/并行摄像头四个会话收敛点；录制文件名加微秒防同秒重录与后台转码争用。
- `core/vision_pipeline.py`：`draw_pose_frame` / `MediaPipePipeline.draw` 新增可选 `action_pose_landmarks`（默认沿用绘制 landmarks，旧行为不变），平滑预览显式传 raw 做分类。
- `core/video_writer.py`：新增 `transcode_to_h264`，仅把 AVI 用 `libx264/medium/CRF20/yuv420p` 转 MP4；成功且目标非空才删 AVI，ffmpeg 缺失/失败保留原录像。
- `core/parallel_pose_engine.py`：`ParallelPoseEngine` 新增 `defer_draw`，`InferResult` 携带 raw `pose_landmarks`/`hands`/`frame` 供重排出口单线程平滑+绘制。
- 新增 `tests/test_online_matcher.py`、`tests/test_app_ui_online_matcher.py`、`tests/test_preview_smoother.py`、`tests/test_preview_draw_contract.py`、`tests/test_video_writer_transcode.py`。

### 验证方法

- 定向 + 安全网 **68 passed**：在线 matcher、Tkinter 接入、预览平滑/绘制边界、转码、`pose33_v3` golden、`valid_mask`、双摄、手部开关全绿。
- 全量 `pytest tests -q` → **403 passed / 10 failed**：10 个失败均为开工前既有红（5 个桌面 `ui_backend` session 属未提交在制品、3 个文档同步、1 个 `test_browse_video` 旧命名），本轮零新增回归。
- `py_compile apps/app_ui.py core/vision_pipeline.py core/video_writer.py core/parallel_pose_engine.py` → OK。
- 待场地人员按实际机位人工确认左右手命中、平滑观感、录制全链路，并现场标定 `MatcherConfig` 阈值。
