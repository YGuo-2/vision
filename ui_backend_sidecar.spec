# -*- mode: python ; coding: utf-8 -*-
r"""PyInstaller sidecar for the Vue/Tauri desktop UI bridge.

Build command from the repository root:
    .\.venv\Scripts\python.exe -m PyInstaller ui_backend_sidecar.spec --noconfirm --clean

The output is ``dist/vision-ui-backend.exe``. The Tauri packaging helper copies
that file into ``frontend/src-tauri/resources/`` so it is bundled next to the
Windows Tauri executable resources. The executable keeps stdin/stdout open for
the JSON bridge protocol.
"""

from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = []

# MediaPipe carries binarypb/modules data that must be available in frozen mode.
for pkg in ("mediapipe",):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

hiddenimports += [
    "apps.ui_backend",
    "apps.camera_enum",
    "core.action_compare",
    "core.body_core_compare",
    "core.feature_layout",
    "core.model_manager",
    "core.parallel_pose_engine",
    "core.paths",
    "core.pose_features",
    "core.recording_controller",
    "core.rule_scoring",
    "core.video_writer",
    "core.vision_pipeline",
    "analysis.tech_eval",
    "pygrabber",
    "pygrabber.dshow_graph",
    "cv2",
]

heavy_excludes = [
    "torch",
    "torchvision",
    "torchaudio",
    "ultralytics",
    "onnx",
    "onnxruntime",
    "onnxslim",
    "tensorrt",
    "core.yolo_adapter",
    "analysis.spike_yolo_baseline",
    "hypothesis",
    "pytest",
    "tkinter",
]

a = Analysis(
    ["apps/ui_backend.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=["packaging/pyinstaller/pyi_rth_video_writer_alias.py"],
    excludes=heavy_excludes + ["nvidia"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="vision-ui-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
