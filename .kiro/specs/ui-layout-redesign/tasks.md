  # Implementation Plan: UI 布局重组与录制/暂停运行时控制

## Overview

（概述）

实施分两条主线，按可测试性排序：先落地与 Tkinter 解耦的纯状态机 `RecordingController`（`core/recording_controller.py`）及其 7 条属性测试，再将其接入 `apps/app_ui.py` 的工作线程与 UI 控件，最后完成左侧控制区的布局重组（可滚动 Canvas + Primary_Controls / Secondary_Options 分组）。

实现语言：**Python**（设计文档已明确使用 Python，与现有仓库一致），属性测试使用仓库已有的 **Hypothesis**，测试文件置于 `tests/`。

验证基线（参考 AGENTS.md）：
```powershell
.\.venv\Scripts\python.exe -m py_compile .\apps\main.py .\apps\app_ui.py .\core\recording_controller.py
.\.venv\Scripts\python.exe -m pytest tests/test_recording_controller.py -q
```

## Tasks

- [x] 1. 搭建 `RecordingController` 模块骨架与数据模型
  - [x] 1.1 创建模块、类型别名与数据模型
    - 创建 `core/recording_controller.py`
    - 定义 `RecordingState = Literal["idle", "recording", "paused"]` 与 `WriterFactory` 类型别名
    - 定义 `@dataclass(frozen=True) RecordingSnapshot(state, result_path, frames_written, last_error)`
    - 声明 `RecordingController.__init__(writer_factory, path_provider)`，初始化内部字段：`_state="idle"`、`_lock=threading.Lock()`、`_writer=None`、`_result_path=None`、`_session_active=False`、`_fps`、`_size`、`_frames_written=0`、`_last_error=None`
    - 提供默认 `path_provider`（`outputs_dir()/record_<timestamp>.mp4`）与默认 `writer_factory`（绑定 `core.video_writer.open_video_writer`）
    - _Requirements: 5.1, 5.8_

- [x] 2. 实现 `RecordingController` 状态机核心逻辑
  - [x] 2.1 实现 `begin_session` / `state` / `snapshot`
    - `begin_session(fps, size)`：在锁内登记 `_fps`、`_size`，置 `_session_active=True`，重置 `_frames_written=0`、`_last_error=None`、`_result_path=None`，状态保持 `idle`，不创建 writer（懒创建）
    - `state` 属性与 `snapshot()` 在锁内返回当前状态/不可变快照
    - _Requirements: 4.1, 5.1, 5.10_

  - [x] 2.2 实现 `request_toggle` 状态转换
    - 在锁内实现循环切换：`idle→recording`、`recording→paused`、`paused→recording`
    - 会话未运行（`_session_active=False`）时为 no-op 并保持 `idle`
    - `idle→recording` 仅置状态并记下"需懒创建"语义，不在此处创建 writer
    - 返回切换后的状态
    - _Requirements: 5.2, 5.3, 5.4, 5.5, 5.6, 5.7_

  - [x] 2.3 实现 `write_frame` 写盘与懒创建
    - 在锁内：仅当状态为 `recording` 时写盘；`paused`/`idle` 直接跳过且不丢弃已写帧
    - 首次写盘时经 `_writer_factory` 懒创建 writer，记录 `_result_path`（取工厂返回的 `actual_path`）
    - 写盘成功后 `_frames_written += 1`
    - 创建或写入抛异常时进入错误处理：释放任何半开资源、`_writer=None`、置 `_last_error`、状态复位 `idle`（异常不外泄到 worker 主循环）
    - _Requirements: 5.3, 5.5, 5.7, 5.11_

  - [x] 2.4 实现 `close_session`
    - 在锁内：无论 `recording` 还是 `paused`，释放 writer（调用 `release()` 后置 `_writer=None`）、置 `_session_active=False`、状态复位 `idle`
    - 返回本会话实际写入路径（曾录制过则为 `_result_path`，否则 `None`）
    - _Requirements: 4.4, 5.8_

- [x] 3. 为 `RecordingController` 编写属性测试（Hypothesis）
  - [x] 3.1 编写测试夹具：假 writer 与引用模型
    - 在 `tests/test_recording_controller.py` 中实现 FakeWriter（记录 `write`/`release` 调用次数，可配置第 N 次 `write` 抛错）与 fake writer_factory（可配置创建时抛错）
    - 实现用于 model-based 断言的简单引用模型（reference model）
    - 推荐使用 Hypothesis `RuleBasedStateMachine` 或自定义动作序列生成器；每条测试 `max_examples>=100`
    - _Requirements: 5.11_

  - [x] 3.2 Property 1：状态转换合法性
    - **Property 1: 状态转换合法性**
    - **Validates: Requirements 4.1, 5.1**
    - 注释标注：`# Feature: ui-layout-redesign, Property 1: 状态转换合法性`

  - [x] 3.3 Property 2：仅录制中写盘
    - **Property 2: 仅录制中写盘**
    - **Validates: Requirements 5.3, 5.5**
    - 注释标注：`# Feature: ui-layout-redesign, Property 2: 仅录制中写盘`

  - [x] 3.4 Property 3：单会话单文件
    - **Property 3: 单会话单文件**
    - **Validates: Requirements 5.7**
    - 注释标注：`# Feature: ui-layout-redesign, Property 3: 单会话单文件`

  - [x] 3.5 Property 4：结束必复位
    - **Property 4: 结束必复位**
    - **Validates: Requirements 4.4, 5.8**
    - 注释标注：`# Feature: ui-layout-redesign, Property 4: 结束必复位`

  - [x] 3.6 Property 5：writer 与路径生命周期
    - **Property 5: writer 与路径生命周期**
    - **Validates: Requirements 5.9, 5.10**
    - 注释标注：`# Feature: ui-layout-redesign, Property 5: writer 与路径生命周期`

  - [x] 3.7 Property 6：错误条件复位
    - **Property 6: 错误条件复位**
    - **Validates: Requirements 5.11**
    - 注释标注：`# Feature: ui-layout-redesign, Property 6: 错误条件复位`

- [x] 4. 检查点 - 确保 `RecordingController` 单元/属性测试通过
  - 确保所有测试通过，如有疑问请询问用户。

- [x] 5. 实现离线线程数规范化与其属性测试
  - [x] 5.1 实现/抽取线程数钳制函数
    - 在 `apps/app_ui.py`（或 `core` 合适位置）实现 `clamp_workers(n) -> int`，将输入钳制到 `[1, os.cpu_count()]`
    - 在 Secondary_Options 的离线线程数 Spinbox 读取处复用该函数
    - _Requirements: 7.2_

  - [x] 5.2 Property 7：离线线程数钳制
    - **Property 7: 离线线程数钳制**
    - **Validates: Requirements 7.2**
    - 注释标注：`# Feature: ui-layout-redesign, Property 7: 离线线程数钳制`（置于 `tests/test_recording_controller.py` 或新建 `tests/test_clamp_workers.py`）

- [x] 6. 将 `RecordingController` 接入 `App` 并改造工作线程
  - [x] 6.1 在 `App` 构造期创建 controller 实例
    - 在 `App.__init__` 中创建 `self._rec = RecordingController(writer_factory=open_video_writer, path_provider=默认时间戳路径)`
    - 移除/解除 `UiState.save_output` / `out_path` 对运行时录制流程的控制作用（worker 不再据此建 writer）
    - _Requirements: 5.1_

  - [x] 6.2 改造 `_worker_loop`
    - 进入循环前调用 `self._rec.begin_session(fps=fps_for_ts, size=(w, h))`
    - 移除内联 `cv2.VideoWriter_fourcc("mp4v")` 与 `state.out_path` 建 writer 逻辑
    - 每帧由内联 `writer.write(annotated)` 改为 `self._rec.write_frame(annotated)`
    - 在 `finally` 中调用 `self._rec.close_session()`（覆盖正常结束、停止、异常）
    - _Requirements: 5.3, 5.5, 5.7, 5.8_

  - [x] 6.3 改造 `_worker_loop_parallel_video`
    - 同步去除内联 writer 逻辑，写盘点改为 `self._rec.write_frame(annotated)`
    - 进入循环前 `begin_session`，结束时 `close_session`
    - _Requirements: 5.3, 5.5, 5.7, 5.8_

- [x] 7. 实现录制相关 UI 回调与状态刷新
  - [x] 7.1 实现 `_on_record_toggle`
    - 调用 `self._rec.request_toggle()`，据返回状态刷新 `Record_Toggle` 文本：`idle→开始录制`、`recording→暂停录制`、`paused→继续录制`
    - _Requirements: 5.2, 5.3, 5.4, 5.5, 5.6, 5.7_

  - [x] 7.2 实现 `_refresh_recording_status` 并由 `_tick` 周期调用
    - 读取 `self._rec.snapshot()`：`recording`/`paused` 时在 Status_Area 显示状态文本与 Result_Video 完整路径；`idle` 时清除录制文本与路径
    - 检测到 `last_error` 非空时弹出错误提示并使 UI 复位（按钮文本回到「开始录制」）
    - _Requirements: 5.9, 5.10, 5.11_

  - [x] 7.3 实现 `_set_running_controls(running)` 与会话起止联动
    - 集中管理运行态控件 enable/disable：运行中禁用 Camera_Selector、Model_Selector，启用 Record_Toggle 并置文本「开始录制」；Compare_Control 始终 enabled
    - 会话未运行时禁用 Record_Toggle 并保持 Recording_State 为 idle；Start_Control 文本在「开始」「停止」间切换；Status_Area 未运行显示「就绪」
    - _Requirements: 2.5, 3.5, 3.6, 4.3, 4.5, 5.1, 5.2, 6.4, 6.5_

  - [x] 7.4 编写按钮文本映射与控件联动单元测试
    - 测试三态按钮文本映射、运行态 enable/disable 联动
    - _Requirements: 4.3, 5.2, 5.4, 5.6, 6.4, 6.5_

- [x] 8. 检查点 - 确保录制接入后测试通过且可编译
  - 运行 `py_compile apps/main.py apps/app_ui.py core/recording_controller.py`
  - 确保所有测试通过，如有疑问请询问用户。

- [x] 9. 重构 `App._build_ui()` 为可滚动控制区与主次分组
  - [x] 9.1 构建可滚动 Canvas 容器
    - 左侧改为 `Canvas` + 垂直 `Scrollbar` + 内嵌 `inner` Frame；`inner` 通过 `<Configure>` 更新 `scrollregion`；绑定鼠标滚轮
    - 设置 `self.root.minsize(800, 600)`，保留初始 `geometry`
    - _Requirements: 1.5, 1.6_

  - [x] 9.2 构建 Primary_Controls 分组（固定顺序）
    - 在 `inner` 内自上而下放置：Camera_Selector → Model_Selector → Start_Control → Record_Toggle → Compare_Control，恰好五项、不插入任何 Secondary_Option
    - _Requirements: 1.1, 1.3_

  - [x] 9.3 添加可见分隔并构建 Secondary_Options 分组
    - 在两组之间插入 `ttk.Separator(orient="horizontal")`
    - 在 Compare_Control 之后放置 Secondary_Options：选择视频、离线线程数 Spinbox、手部检测 Checkbutton、直拳检测按钮
    - 保留 Status_Area（状态文本/识别结果/进度条）于控制区底部
    - _Requirements: 1.2, 1.4, 7.1, 7.2, 7.3, 7.4, 7.6, 7.7, 7.8_

  - [x] 9.4 编写布局结构断言单元测试
    - 断言 Primary_Controls 五项与顺序、Separator 存在、Secondary_Options 位于其后
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 10. 串联错误处理与输入校验
  - [x] 10.1 无输入源/无效视频/比对窗口失败的错误提示
    - 点击开始无有效输入源时弹「请先选择摄像头或视频」、不启动会话、Recording_State 保持 idle
    - 无效视频文件拒绝并保留先前选择、弹文件无效提示
    - 比对窗口创建失败 try/except 弹框、主窗口状态不变
    - _Requirements: 4.2, 6.3, 7.5_

  - [x] 10.2 编写错误处理场景单元测试
    - 覆盖无输入源、无效视频、比对窗口创建失败
    - _Requirements: 4.2, 6.3, 7.5_

- [x] 11. 最终检查点 - 全量验证
  - 运行 `py_compile apps/main.py apps/app_ui.py core/recording_controller.py`
  - 运行 Hypothesis 属性测试与单元测试，确保全部通过
  - 按任务完成规范将修改总结写入 `change.md`
  - 确保所有测试通过，如有疑问请询问用户。

## Notes

- 标记 `*` 的子任务为可选（测试类），可为加速 MVP 跳过；核心实现任务不得标记可选。
- 每个任务引用具体需求子条款以保证可追溯。
- 属性测试仅适用于纯状态机 `RecordingController` 与线程数钳制函数；UI 渲染/几何（1.5、1.6）采用冒烟测试人工验证，未纳入自动化属性测试。
- 任务顺序保证可测试的 `RecordingController` 单元及其属性测试先于 Tkinter 接线完成，便于尽早发现状态机缺陷。
- 摄像头枚举（需求 2.1–2.4、2.6）由既有 `apps/camera_enum.py` 覆盖，本计划不重复实现。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4"] },
    { "id": 3, "tasks": ["3.1", "5.1"] },
    { "id": 4, "tasks": ["3.2", "3.3", "3.4", "3.5", "3.6", "3.7", "5.2"] },
    { "id": 5, "tasks": ["6.1"] },
    { "id": 6, "tasks": ["6.2", "6.3", "7.1", "7.2", "7.3"] },
    { "id": 7, "tasks": ["7.4", "9.1"] },
    { "id": 8, "tasks": ["9.2", "9.3"] },
    { "id": 9, "tasks": ["9.4", "10.1"] },
    { "id": 10, "tasks": ["10.2"] }
  ]
}
```
