# Requirements Document

## Introduction

当前 `apps/app_ui.py` 的 Tkinter 桌面界面将控件分散在「输入 / 选项 / 运行 / 状态」四个卡片中，主要操作（摄像头选择、模型选择、开始、动作比对）混杂在次要选项之间，主次不分、布局凌乱。本特性对主窗口左侧控制区进行重新设计，使五项核心操作清晰、突出、易达：**摄像头选择、模型选择、开始、录制/暂停（新增）、动作比对**。其中「录制/暂停」是新增能力，允许用户在实时识别运行期间按需开始或暂停录制结果视频，而不必在启动前预先勾选导出选项。

本特性聚焦于桌面 UI 的布局与交互重组，以及录制控制状态机；不改变底层视觉推理逻辑（`core/vision_pipeline.py`）、模板匹配与技术评估算法。次要选项（离线线程数、手部检测、视频文件选择、直拳检测入口等）应保留但可置于次级/折叠区域。

## Glossary

- **Main_Window**: `apps/app_ui.py` 中 `App` 类管理的主窗口，包含左侧控制区与右侧预览区。
- **Control_Panel**: 主窗口左侧承载所有操作控件的区域。
- **Primary_Controls**: 五项核心控件的集合：摄像头选择、模型选择、开始、录制/暂停、动作比对。
- **Camera_Selector**: 用于列举并选择可用摄像头的下拉控件。
- **Model_Selector**: 用于选择人体姿态模型变体（lite/full/heavy）的下拉控件。
- **Start_Control**: 启动实时识别或离线处理的按钮（即「开始」）。
- **Record_Toggle**: 新增的「录制/暂停」按钮，用于在会话运行期间控制结果视频录制。
- **Compare_Control**: 打开动作比对窗口的按钮（即「动作比对」）。
- **Recording_State**: 录制功能的状态，取值为 `空闲`（idle）、`录制中`（recording）、`已暂停`（paused）。
- **Session**: 一次实时识别或离线视频处理的运行过程，从点击「开始」到结束或停止。
- **Result_Video**: 由录制功能写入磁盘的、带识别标注的输出视频文件。
- **Secondary_Options**: 非核心选项，包括离线线程数、启用手部检测、选择视频文件、直拳检测入口等。
- **Status_Area**: 显示运行状态、识别结果与进度的区域。

## Requirements

### Requirement 1: 突出展示核心控件

**User Story:** 作为用户，我希望五项核心操作在界面中清晰、集中地展示，以便快速找到并使用它们，而不被次要选项干扰。

#### Acceptance Criteria

1. THE Main_Window SHALL 在 Control_Panel 中展示 Primary_Controls，且 Primary_Controls 恰好包含 Camera_Selector、Model_Selector、Start_Control、Record_Toggle 与 Compare_Control 这五项控件，不多不少。
2. THE Control_Panel SHALL 将 Primary_Controls 与 Secondary_Options 划分为两个互不重叠的可见分组区域，区域之间存在明确的可见分隔（分隔线或独立分组容器），使两组控件不混排于同一连续区域内。
3. THE Control_Panel SHALL 按自上而下的垂直顺序排列 Primary_Controls，顺序依次为 Camera_Selector、Model_Selector、Start_Control、Record_Toggle、Compare_Control，且相邻控件之间不插入任何 Secondary_Options。
4. THE Control_Panel SHALL 将全部 Secondary_Options 置于 Primary_Controls 区域之后的次级区域，使任一 Secondary_Option 在垂直布局中均位于 Compare_Control 之后。
5. WHEN 用户将 Main_Window 调整至不小于其最小允许尺寸（宽 800 像素、高 600 像素）的任意尺寸，THE Control_Panel SHALL 保持全部五项 Primary_Controls 完整可见且不被裁剪。
6. IF Main_Window 被调整至小于最小允许尺寸（宽 800 像素或高 600 像素），THEN THE Control_Panel SHALL 提供滚动机制，使全部五项 Primary_Controls 仍可通过滚动完整访问且不被永久裁剪。

### Requirement 2: 摄像头选择

**User Story:** 作为用户，我希望能从可用摄像头列表中选择输入源，以便对指定摄像头进行实时识别。

#### Acceptance Criteria

1. WHEN Main_Window 在启动后 3 秒内完成初始化，THE Camera_Selector SHALL 在列表中展示所有已枚举到的可用摄像头，每个条目以唯一设备索引（0 至 15）与设备名称标识。
2. WHEN 用户从 Camera_Selector 选择一个摄像头，THE Main_Window SHALL 将该摄像头设为当前输入源，并将输入源提示文本更新为所选摄像头的设备索引与设备名称。
3. WHEN 用户触发摄像头刷新，THE Camera_Selector SHALL 在 3 秒内重新枚举可用摄像头并以最新枚举结果替换列表内容。
4. IF 在枚举或刷新后未检测到任何可用摄像头，THEN THE Camera_Selector SHALL 显示「未检测到摄像头」提示，并保持当前输入源为空。
5. WHILE Session 处于运行状态，THE Camera_Selector SHALL 处于禁用状态且不响应用户的选择与刷新操作。
6. IF 用户选择的摄像头无法打开或被其他进程占用，THEN THE Main_Window SHALL 保持原有输入源不变，并显示提示信息指明该摄像头不可用。

### Requirement 3: 模型选择

**User Story:** 作为用户，我希望选择人体姿态模型变体，以便在精度与速度之间权衡。

#### Acceptance Criteria

1. THE Model_Selector SHALL 提供 `lite`、`full`、`heavy` 三个互斥可选值，且同一时刻仅有一个值处于选中状态。
2. WHEN Main_Window 首次初始化且用户尚未做出选择，THE Model_Selector SHALL 默认选中 `full`。
3. WHEN 用户从 Model_Selector 选择一个模型变体，THE Main_Window SHALL 将该变体用于此次选择之后启动的新 Session。
4. WHILE 存在正在运行的 Session，THE Main_Window SHALL 不将新选择的模型变体应用于该正在运行的 Session。
5. WHILE Session 处于运行状态，THE Model_Selector SHALL 处于禁用状态且不接受更改。
6. WHEN Session 结束，THE Model_Selector SHALL 恢复为可用状态并保留最后一次选中的值。

### Requirement 4: 开始与停止识别

**User Story:** 作为用户，我希望通过「开始」启动识别会话，以便查看实时或离线处理的标注预览。

#### Acceptance Criteria

1. WHEN 用户点击 Start_Control 且已选择有效输入源，THE Main_Window SHALL 在 2 秒内启动 Session、将 Recording_State 维持为 `空闲`，并在右侧预览区展示含姿态骨架叠加的标注画面。
2. IF 用户点击 Start_Control 时未选择有效输入源（既未选择摄像头，也无可读取的视频文件），THEN THE Main_Window SHALL 显示「请先选择摄像头或视频」错误提示、不启动 Session，并将 Recording_State 维持为 `空闲`。
3. WHILE Session 处于运行状态，THE Start_Control SHALL 显示「停止」标签，且点击行为切换为停止当前 Session。
4. WHEN 用户在 Session 运行期间触发停止，THE Main_Window SHALL 在 1 秒内结束 Session 并将 Recording_State 复位为 `空闲`。
5. WHILE Session 未运行，THE Status_Area SHALL 显示状态文本「就绪」。

### Requirement 5: 录制/暂停（新增）

**User Story:** 作为用户，我希望在识别会话运行期间随时开始或暂停录制结果视频，以便只保存我关心的片段，而无需在启动前预先决定。

#### Acceptance Criteria

1. WHILE Session 未运行，THE Record_Toggle SHALL 处于禁用状态，且 Recording_State 保持为 `空闲`。
2. WHEN Session 启动，THE Main_Window SHALL 启用 Record_Toggle 并将其文本设为「开始录制」。
3. WHEN 用户在 Recording_State 为 `空闲` 时点击 Record_Toggle，THE Main_Window SHALL 在 100 毫秒内将 Recording_State 置为 `录制中`，并开始将与右侧预览区一致的带标注帧写入 Result_Video。
4. WHILE Recording_State 为 `录制中`，THE Record_Toggle SHALL 显示「暂停录制」文本。
5. WHEN 用户在 Recording_State 为 `录制中` 时点击 Record_Toggle，THE Main_Window SHALL 将 Recording_State 置为 `已暂停`、停止向 Result_Video 写入新帧，并保留已写入的帧不丢弃。
6. WHILE Recording_State 为 `已暂停`，THE Record_Toggle SHALL 显示「继续录制」文本。
7. WHEN 用户在 Recording_State 为 `已暂停` 时点击 Record_Toggle，THE Main_Window SHALL 将 Recording_State 置回 `录制中`，并继续向同一个 Result_Video 追加帧，不新建文件且不覆盖已写入内容。
8. WHEN Session 结束或被停止，THE Main_Window SHALL 无论当前 Recording_State 为 `录制中` 或 `已暂停`，均关闭 Result_Video 文件、释放写入资源并将 Recording_State 复位为 `空闲`。
9. WHILE Recording_State 为 `录制中` 或 `已暂停`，THE Status_Area SHALL 显示当前录制状态文本与 Result_Video 的完整保存路径。
10. WHILE Recording_State 为 `空闲`，THE Status_Area SHALL 不显示录制状态文本与保存路径。
11. IF Result_Video 文件无法创建或在写入过程中失败，THEN THE Main_Window SHALL 关闭并释放已打开的写入资源、显示包含失败原因的错误提示，并将 Recording_State 复位为 `空闲`。

### Requirement 6: 动作比对入口

**User Story:** 作为用户，我希望通过「动作比对」打开模板匹配窗口，以便比较视频与模板的相似度。

#### Acceptance Criteria

1. WHEN 用户点击 Compare_Control 且动作比对窗口尚未打开，THE Main_Window SHALL 在 1 秒内创建并显示动作比对窗口。
2. IF 动作比对窗口已打开，THEN THE Main_Window SHALL 将已存在的窗口前置聚焦而非新建窗口，且任意时刻动作比对窗口实例数量不超过 1 个。
3. IF 用户点击 Compare_Control 后动作比对窗口创建失败，THEN THE Main_Window SHALL 显示指示创建失败原因的错误提示，并保持 Main_Window 当前状态不变。
4. WHILE Session 处于运行状态，THE Compare_Control SHALL 保持可点击（enabled）。
5. WHILE Session 处于未运行状态，THE Compare_Control SHALL 保持可点击（enabled）。

### Requirement 7: 保留次要选项

**User Story:** 作为用户，我希望现有的次要功能在重新设计后仍然可用，以便不丢失既有能力。

#### Acceptance Criteria

1. THE Control_Panel SHALL 在 Secondary_Options 区域显示视频文件选择控件，且该控件可点击并能打开文件选择对话框。
2. THE Control_Panel SHALL 在 Secondary_Options 区域显示离线线程数设置控件，且接受 1 至当前主机 CPU 逻辑核心数范围内的整数值。
3. THE Control_Panel SHALL 在 Secondary_Options 区域显示启用手部检测开关，该开关可在「开启」与「关闭」两种状态间切换并保持所选状态。
4. THE Control_Panel SHALL 在 Secondary_Options 区域显示直拳检测入口，且该入口可点击并进入直拳检测功能。
5. IF 用户选择的视频文件不存在或格式不受支持，THEN THE Control_Panel SHALL 拒绝该文件、保留先前的选择状态并显示指示文件无效的错误提示。
6. WHEN 处理运行中，THE Status_Area SHALL 显示当前运行状态。
7. WHEN 识别结果产生，THE Status_Area SHALL 显示识别结果。
8. WHILE 处理进行中，THE Status_Area SHALL 显示处理进度。
