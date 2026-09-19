# 离线桌面 EXE

本次交付旧版 Tk 桌面及学生练习功能，适用 Windows 10/11 64 位。

## 给使用者

1. 解压交付包，双击 `散打动作练习.exe`。不需要安装 Python、配置开发环境或下载模型。
2. 单文件首次打开需要解压运行库，请等待窗口出现。
3. 插入摄像头，选择输入设备，点击“学生练习…”，填写学号和动作，再按“开始 → 结束 → 动作评判”操作。
4. 若没有画面，检查 Windows 相机权限，并关闭正在占用摄像头的软件。

内置 MediaPipe Lite、Full、Heavy 三个人体模型，以及手部模型。录像转码工具也已内置，使用 CPU 即可运行，不需要独立显卡或本地视觉大模型。

程序数据位于 `%LOCALAPPDATA%\VisionSanda`：`models` 为模型，`templates` 为模板，`outputs` 为默认录制/历史目录，`desktop.log` 为运行日志。可在程序中修改录制保存位置。升级时替换 EXE 即可，不要删除数据目录。

学生练习的问题说明仍是关键点规则检查，候选问题需要教师确认；打包不等于完成动作准确率与甲方摄像头现场验收。

## 维护者构建

在仓库根目录，使用已安装 `requirements.txt` 的 Python 环境：

```powershell
python -m pip install pyinstaller==6.22.3 imageio-ffmpeg==0.6.0
python -m PyInstaller app_ui_onefile.spec --noconfirm
```

构建前 `models` 必须有 `pose_landmarker_lite.task`、`pose_landmarker_full.task`、`pose_landmarker_heavy.task`、`hand_landmarker.task`。缺文件时构建失败，不生成缺模型的交付包。本机环境在 `D:\DevTools\venvs\vision`。

产物为 `dist/vision_ui.exe`。最终交付目录中可重命名为 `散打动作练习.exe`，不影响运行。仅附带仓库两个公开的在线直拳模板，不包含开发电脑的学生历史、录制视频、用户偏好或私人模板。

## 离线检查

```powershell
Start-Process -FilePath .\dist\vision_ui.exe -ArgumentList '--offline-self-check', 'D:\offline-check.json' -Wait
```

该入口在独立临时用户目录下运行，屏蔽 Python 网络连接和下载，检查四个模型的 CPU 加载与推理、视频写入/MP4 转码/读取、学生练习页面、MediaPipe 问题说明、个人历史与报告导出。退出后删除临时数据，保留指定的 JSON 结果和同名日志；`ok=true` 才表示通过。

发布检查还需要把 EXE 拷到仓库之外的中文/空格路径，清空 `PYTHONPATH`、`PYTHONHOME`、`VIRTUAL_ENV`，将 `PATH` 限制为 Windows 系统目录后运行。此检查不能代替甲方实际摄像头、硬件性能和系统安全策略验收。
