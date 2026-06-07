# Implementation Plan: 摄像头下拉选择（camera-dropdown-selection）

## Overview

实现分两条主线推进：先落地不依赖 Tkinter 的纯逻辑模块 `apps/camera_enum.py`（含 `CameraEntry`、`make_label`、`probe_camera`、`enumerate_cameras` 与可独立测试的 `InputSourceState`），并就 4 条 Correctness Properties 编写 Hypothesis 属性测试与 `probe_camera` 示例测试；随后改造 `apps/app_ui.py` 的 `App` 输入区，将自由文本框替换为 readonly 下拉、加入刷新控件与输入源指示标签，接入后台枚举与三态互斥状态模型，并保持 `_worker_loop` 的 `source.isdigit()` 兼容分支不变。每个任务均可追溯到需求与设计，测试任务标注属性编号与需求条款，最后做编译验收并写入 `change.md`。

## Tasks

- [ ] 1. 搭建枚举器模块与纯逻辑
  - [ ] 1.1 创建模块骨架、常量与 `CameraEntry`、`make_label`
    - 新建 `apps/camera_enum.py`
    - 定义常量 `DEFAULT_SCAN_LIMIT = 5`、`SCAN_LIMIT_MIN = 1`、`SCAN_LIMIT_MAX = 32`、`PROBE_TIMEOUT_S = 2.0`
    - 定义 `@dataclass(frozen=True) class CameraEntry`（字段 `label: str`、`index: int`）
    - 实现 `make_label(index: int) -> str`，返回非空显示文本（如 `"摄像头 {index}"`），保证编号与文本一一对应（单射）
    - _Requirements: 1.7, 2.2_

  - [ ]* 1.2 编写 `make_label` 一一对应属性测试
    - 在 `tests/test_camera_enum.py` 中实现
    - **Property 3: 显示文本与编号一一对应且非空**
    - 标签注释：`# Feature: camera-dropdown-selection, Property 3: ...`
    - 使用 `st.lists(st.integers(min_value=0, max_value=1000), unique=True)`，断言每个 `make_label(i)` 非空且 `{make_label(i) for i in idxs}` 大小等于 `len(idxs)`
    - 使用 Hypothesis（≥100 次迭代，必要时 `@settings(max_examples=100)`）
    - **Validates: Requirements 2.2**

  - [ ] 1.3 实现 `enumerate_cameras` 协调逻辑（注入式 probe）
    - 实现 `enumerate_cameras(scan_limit=DEFAULT_SCAN_LIMIT, probe=probe_camera) -> list[CameraEntry]`
    - 将 `scan_limit` 钳制到 `[SCAN_LIMIT_MIN, SCAN_LIMIT_MAX]`（即 `max(1, min(n, 32))`）
    - 从 0 起按编号递增探测至有效上限（含上限），对 `probe(i)` 为真的编号生成 `CameraEntry(make_label(i), i)`
    - 保证返回列表按 `index` 升序、每个可用编号至多出现一次、不可用编号不出现；空时返回空列表
    - _Requirements: 1.1, 1.4, 1.7, 1.8_

  - [ ]* 1.4 编写枚举结果交集属性测试
    - 在 `tests/test_camera_enum.py` 中实现
    - **Property 1: 枚举结果等于可用编号与扫描范围的交集（升序、去重）**
    - 标签注释：`# Feature: camera-dropdown-selection, Property 1: ...`
    - `st.sets(st.integers(min_value=0, max_value=40))` 生成可用集合 A，`st.integers()` 生成 scan_limit，注入 `probe = lambda i: i in A`
    - 断言 `[e.index for e in enumerate_cameras(n, probe)] == sorted(i for i in A if 0 <= i <= clamp(n,1,32))`
    - Hypothesis ≥100 次迭代
    - **Validates: Requirements 1.1, 1.4, 1.8**

  - [ ]* 1.5 编写扫描上限钳制属性测试
    - 在 `tests/test_camera_enum.py` 中实现
    - **Property 2: 扫描上限被钳制到 [1, 32]**
    - 标签注释：`# Feature: camera-dropdown-selection, Property 2: ...`
    - `st.integers()` 生成任意 n（含负数/超大值），用记录被探测编号的 spy `probe` 断言被探测最大编号 == `clamp(n,1,32)`、最小为 0
    - Hypothesis ≥100 次迭代
    - **Validates: Requirements 1.7**

- [ ] 2. 实现真实摄像头探测与输入源状态模型
  - [ ] 2.1 实现 `probe_camera` 真实 OpenCV 探测
    - 在 `apps/camera_enum.py` 中实现 `probe_camera(index: int, timeout_s: float = PROBE_TIMEOUT_S) -> bool`
    - 使用 `cv2.VideoCapture(index, cv2.CAP_DSHOW)` 打开摄像头
    - 在子线程内执行打开 + `read()`，主线程 `join(timeout_s)`；超时判不可用并继续
    - 判定可用：`isOpened()` 为真且 `read()` 返回 `ok is True 且 frame is not None 且 frame.size > 0`
    - `try/except` 捕获探测异常视为不可用；`finally` 中调用 `cap.release()` 释放资源
    - _Requirements: 1.2, 1.3, 1.5, 1.6_

  - [ ]* 2.2 编写 `probe_camera` 示例测试
    - 在 `tests/test_camera_enum.py` 中实现，mock `cv2.VideoCapture`，不接触真实硬件
    - 覆盖样例：未打开（`isOpened()` False）→ 不可用；打开+空帧（`frame=None` 或 `frame.size==0`）→ 不可用；打开+非空帧 → 可用
    - 覆盖超时：注入阻塞读帧，断言超时判不可用且不阻塞后续
    - 覆盖资源释放：断言每次探测后 `release()` 被调用
    - _Requirements: 1.3, 1.5, 1.6_

  - [ ] 2.3 抽取输入源状态模型 `InputSourceState`
    - 在 `apps/camera_enum.py` 中实现纯结构 `InputSourceState`（持有 `kind: str`、`value: str`，初始 `kind="none"`、`value=""`）
    - `select_camera(index: int)`：设 `kind="camera"`、`value=str(index)`，清除任何视频残留
    - `select_video(path: str)`：设 `kind="video"`、`value=path`，清除摄像头选中语义
    - 不变式：`kind=="camera"` ⇒ `value.isdigit()`；`kind=="video"` ⇒ `not value.isdigit()`；`kind=="none"` ⇒ `value==""`；任一时刻至多一个生效源
    - _Requirements: 3.3, 3.4_

  - [ ]* 2.4 编写输入源切换不变式属性测试
    - 在 `tests/test_input_source_state.py` 中实现
    - **Property 4: 输入源切换保持「至多一个生效源」不变式**
    - 标签注释：`# Feature: camera-dropdown-selection, Property 4: ...`
    - `st.lists` 生成由「选择摄像头(index)」与「选择有效视频(path)」组成的随机操作序列，逐步应用并在每步后断言不变式（camera ⇒ value.isdigit()；video ⇒ not value.isdigit()；互斥）
    - Hypothesis ≥100 次迭代
    - **Validates: Requirements 3.3, 3.4**

  - [ ]* 2.5 编写输入源状态机示例测试
    - 在 `tests/test_input_source_state.py` 中实现
    - 覆盖：初始 `none`；camera→video 切换后无摄像头残留；video→camera 切换后无视频路径残留
    - _Requirements: 3.3, 3.4_

- [ ] 3. Checkpoint - 确保枚举器与状态模型测试通过
  - 运行 `.\.venv\Scripts\python.exe -m pytest tests/test_camera_enum.py tests/test_input_source_state.py`
  - 如未安装 Hypothesis：`.\.venv\Scripts\python.exe -m pip install hypothesis --proxy http://127.0.0.1:7890`
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. 改造 App 输入区并接入枚举与状态
  - [ ] 4.1 改造 `_build_ui` 控件与 `__init__` 实例状态
    - 修改 `apps/app_ui.py` 的 `_build_ui`：移除原摄像头编号 `ttk.Entry`（`self.source_entry`），界面不再保留该自由文本框
    - 新增 `ttk.Combobox(state="readonly", textvariable=self.camera_choice_var)`，绑定 `<<ComboboxSelected>>` → `_on_camera_selected`
    - 保留“选择视频…”按钮（command=`_browse_video`）；新增“刷新”按钮（command=`_refresh_cameras`）；新增当前输入源指示标签（textvariable=`self.source_hint_var`）
    - 在 `__init__` 新增：`self.camera_choice_var = StringVar(value="")`、`self.source_hint_var = StringVar(value="当前输入源：未选择")`、`self.source_kind = "none"`、`self._camera_entries: list[CameraEntry] = []`、`self._enum_busy = threading.Event()`；保留 `self.source_var` 复用为最终输入标识
    - _Requirements: 2.1, 2.4, 3.1, 3.5, 5.1_

  - [ ] 4.2 实现 `_start_enumeration()` 与 `_set_refresh_enabled()`
    - `_start_enumeration`：置 `_enum_busy`，禁用刷新与下拉（下拉显示“正在检测摄像头…”），起后台 `threading.Thread` 跑 `enumerate_cameras`，结果/异常经 `root.after(0, ...)` 交给 `_apply_camera_entries`
    - `_set_refresh_enabled`：仅当「非枚举中且采集未运行」时启用刷新控件
    - 在 `__init__`/`_build_ui` 完成后触发一次启动枚举
    - _Requirements: 1.1, 5.2, 5.3_

  - [ ] 4.3 实现 `_apply_camera_entries(entries, ok)` 回填
    - 主线程回调：`ok=True` 且非空 → 更新 `_camera_entries`、重建下拉 `values`、保留/设定选中项并经 `InputSourceState` 更新输入源；启动场景选首项并记录 `source_var=str(index)`
    - 空列表 → 禁用下拉、显示“未检测到可用摄像头”、`source_kind="none"`、不记录输入源
    - `ok=False` → 保留刷新前 `_camera_entries` 与下拉项不变，状态栏提示“刷新摄像头失败”
    - 清 `_enum_busy`，调用 `_set_refresh_enabled()` 按采集态恢复刷新
    - _Requirements: 1.8, 2.2, 2.5, 2.6, 5.4, 5.5, 5.6_

- [ ] 5. 实现输入源选择与采集接入
  - [ ] 5.1 实现 `_on_camera_selected(event)`
    - 由选中 label 反查对应 `CameraEntry.index`，经状态模型设 `source_kind="camera"`、`source_var=str(index)`，清除视频路径，更新 `source_hint_var` 为“当前输入源：摄像头 {index}”
    - 持续显示该条目文本为下拉当前选中项直至下次选择
    - _Requirements: 2.3, 3.3_

  - [ ] 5.2 改造 `_browse_video()`
    - 弹出 `filedialog`；取消（空串）→ 直接 return，状态与指示不变
    - 选中 → 用 `Path.exists()` + 临时 `cv2.VideoCapture(path)`/`isOpened()` 校验可打开；成功 → `source_kind="video"`、`source_var=path`、清空下拉选中、更新指示为“当前输入源：视频文件 {路径}”
    - 失败 → `messagebox.showerror`（含路径），保持先前输入源与指示不变
    - _Requirements: 3.2, 3.3, 3.4, 3.6, 3.7, 4.5_

  - [ ] 5.3 实现 `_refresh_cameras()`
    - 若采集运行中（`self._worker` 存活）或枚举进行中（`_enum_busy` 已置）则直接忽略；否则调用 `_start_enumeration()`
    - _Requirements: 5.1, 5.3, 5.7_

  - [ ] 5.4 改造 `_collect_state()` 与采集启停门控
    - `_collect_state`：`source_kind=="none"` 时抛 `ValueError("未选择输入源…")`；否则用 `source_var` 构造 `UiState`
    - 在 `_start`/`_stop` 中调用 `_set_refresh_enabled()`，确保采集运行中禁用刷新、停止后恢复
    - 确认 `_worker_loop` 维持 `source = state.source`、`is_file = not source.isdigit()` 兼容分支（数字 → `cv2.VideoCapture(int(source), cv2.CAP_DSHOW)`；否则路径打开），打开失败提示含 `source` 标识
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 5.7_

  - [ ]* 5.5 编写刷新门控示例测试
    - 在 `tests/test_input_source_state.py` 中补充（以可注入方式覆盖门控逻辑）
    - 覆盖：`source_kind=="none"` 时收集状态抛错（4.3）；对 `(enum_busy, capture_running)` 四组合断言刷新启用态（5.3, 5.7）
    - _Requirements: 4.3, 5.3, 5.7_

- [ ] 6. 兼容性验收（编译检查）
  - [ ] 6.1 运行 py_compile 编译检查
    - 运行 `.\.venv\Scripts\python.exe -m py_compile .\apps\app_ui.py .\apps\camera_enum.py`
    - 修复任何编译错误
    - _Requirements: 2.1, 4.1, 4.2_

- [ ] 7. Checkpoint - 最终校验并归档修改总结
  - 运行全部新增测试与 `py_compile` 编译检查，确保通过
  - 按 AGENTS.md 任务完成规范，将本次修改总结写入 `change.md`（含修改日期、问题描述、修改内容、验证方法）
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- 标记 `*` 的子任务为可选测试任务，可为加快 MVP 跳过；核心实现任务不标记 `*`。
- 枚举器测试通过注入 `probe`/操作序列，不接触真实摄像头硬件，保证确定性。
- 属性测试使用 Hypothesis（≥100 次迭代），每条属性单独成一个测试，并带 `# Feature: camera-dropdown-selection, Property N: ...` 标签注释。
- 真实硬件枚举、`cv2.CAP_DSHOW` 后端、采集端到端打开依赖真实 OpenCV，由示例测试 + 手动验证覆盖，不纳入属性测试。
- 每个任务引用具体需求条款以保证可追溯性；checkpoint 用于增量验证。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "2.1", "2.3"] },
    { "id": 2, "tasks": ["1.4", "1.5", "2.2", "2.4", "2.5"] },
    { "id": 3, "tasks": ["4.1"] },
    { "id": 4, "tasks": ["4.2", "4.3"] },
    { "id": 5, "tasks": ["5.1", "5.2", "5.3", "5.4"] },
    { "id": 6, "tasks": ["5.5", "6.1"] }
  ]
}
```
