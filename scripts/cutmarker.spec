# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

block_cipher = None
# SPECPATH is the directory containing this .spec file (scripts/)
root = Path(SPECPATH).resolve().parent

a = Analysis(
    [str(root / "cutmarker" / "__main__.py")],
    pathex=[str(root)],
    binaries=[
        (str(root / "cutmarker" / "resources" / "bin" / "ffmpeg.exe"), "ffmpeg"),
        (str(root / "cutmarker" / "resources" / "bin" / "ffprobe.exe"), "ffmpeg"),
    ] if (root / "cutmarker" / "resources" / "bin" / "ffmpeg.exe").is_file() else [],
    datas=[
        (str(root / "cutmarker" / "resources"), "cutmarker/resources"),
    ],
    hiddenimports=[
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "cv2",
        "numpy",
        "scenedetect",
        "scenedetect.detectors",
        "imageio_ffmpeg",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

icon_path = (root / "assets" / "cutmarker.ico").resolve()
if not icon_path.is_file():
    icon_path = (root / "cutmarker" / "resources" / "cutmarker.ico").resolve()
if not icon_path.is_file():
    raise SystemExit(f"CutMarker icon not found: {icon_path}")
print(f"Using icon: {icon_path} ({icon_path.stat().st_size} bytes)")

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CutMarker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon_path),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="CutMarker",
)
