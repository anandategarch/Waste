# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — Waste Anomaly Detection
# Build:  pyinstaller waste_anomaly.spec  (atau jalankan BUILD_EXE.bat di Windows)
#
# Catatan:
# - python-calamine OPSIONAL — kalau tidak terinstall saat build, exclude aman
#   (loader otomatis fallback ke openpyxl).
# - config.json + assets ikon di-bundle sebagai data.
# - matplotlib backend TkAgg di-hook otomatis PyInstaller.

import sys
from pathlib import Path

block_cipher = None
ROOT = Path(SPECPATH)

datas = [
    (str(ROOT / "waste_anomaly" / "config.json"), "waste_anomaly"),
    (str(ROOT / "assets"), "assets"),
]

hiddenimports = [
    "matplotlib.backends.backend_tkagg",
]

# calamine opsional — jangan gagalkan build kalau tidak ada
try:
    import python_calamine  # noqa: F401
    hiddenimports.append("python_calamine")
except ImportError:
    pass

a = Analysis(
    ["ui_app.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
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

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="WasteAnomalyDetection",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX sering memicu false-positive antivirus — matikan
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # GUI app — tanpa jendela console hitam
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "assets" / "app_icon.ico"),  # Windows; diabaikan di macOS/Linux
)
