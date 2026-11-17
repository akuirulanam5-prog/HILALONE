# -*- mode: python ; coding: utf-8 -*-
"""Konfigurasi PyInstaller (mode ONE-DIR) untuk HILALONE Windows Desktop."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

PROJECT_ROOT = Path(SPECPATH).resolve()
SRC_DIR = PROJECT_ROOT / "src"
ENTRY_SCRIPT = SRC_DIR / "hilalone" / "main.py"
ICON_PATH = PROJECT_ROOT / "assets" / "branding" / "hilalone_app_icon.ico"
VERSION_FILE = PROJECT_ROOT / "file_version_info.txt"

# Aset resmi HILALONE (Standard Dark, Night Vision Red, App Icon, beserta cadangan)
branding_files = [
    (str(p), "assets/branding")
    for p in sorted((PROJECT_ROOT / "assets" / "branding").glob("*"))
    if p.is_file()
]

# Data wajib untuk Astropy IERS agar tidak gagal saat startup terbundel
astropy_iers_datas = collect_data_files("astropy_iers_data")

datas = branding_files + astropy_iers_datas

# Hidden imports spesifik yang terdeteksi dari audit pemanggilan dinamis
hiddenimports = [
    "astropy_iers_data",
    "erfa",
    "PIL.Image",
    "PIL.PngImagePlugin",
    "PIL.JpegImagePlugin",
    "PIL.TiffImagePlugin",
    "tifffile",
    "rawpy",
    "av",
    "scipy.interpolate",
    "scipy.ndimage",
    "skimage.exposure",
]

# Kecualikan paket dev & submodul PySide6 berat yang tidak digunakan HILALONE
excludes = [
    "pytest",
    "_pytest",
    "astropy.visualization.wcsaxes",
    "matplotlib",
    "tkinter",
    "_tkinter",
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DExtras",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DRender",
    "PySide6.QtBluetooth",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtDesigner",
    "PySide6.QtGraphs",
    "PySide6.QtGraphsWidgets",
    "PySide6.QtHelp",
    "PySide6.QtLocation",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtNfc",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtPositioning",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.QtQuickControls2",
    "PySide6.QtQuickWidgets",
    "PySide6.QtRemoteObjects",
    "PySide6.QtScxml",
    "PySide6.QtSensors",
    "PySide6.QtSerialBus",
    "PySide6.QtSerialPort",
    "PySide6.QtSpatialAudio",
    "PySide6.QtSql",
    "PySide6.QtTest",
    "PySide6.QtTextToSpeech",
    "PySide6.QtWebChannel",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebSockets",
]

a = Analysis(
    [str(ENTRY_SCRIPT)],
    pathex=[str(SRC_DIR)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[str(PROJECT_ROOT / "hooks")],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="HILALONE",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON_PATH),
    version=str(VERSION_FILE),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="HILALONE",
)
