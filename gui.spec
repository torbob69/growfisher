# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['gui.py'],
    pathex=[],
    binaries=[],
    datas=[('ui/dist', 'ui/dist'), ('venv/Lib/site-packages/rapidocr_onnxruntime', 'rapidocr_onnxruntime'),
           ('runs/detect/runs/detect/growfisher-4/weights/best.onnx', 'runs/detect/runs/detect/growfisher-4/weights')],
    hiddenimports=['pyclipper', 'six', 'shapely', 'shapely.geometry', 'yaml'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # ponytail: torch only arrives via onnxruntime.transformers / ultralytics; inference is pure onnxruntime
    excludes=['torch', 'torchvision', 'torchgen', 'functorch', 'ultralytics', 'onnxruntime.transformers'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Growfisher',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['ui/public/icon.ico'],
)
