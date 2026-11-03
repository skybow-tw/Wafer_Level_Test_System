# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: dist/BMT5000.exe (BMT5000 only, minimal Qt deps)."""

from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent

hiddenimports = [
    "bmt_array_view",
    "theme_config",
    "PySide6.QtCharts",
    "usb.core",
    "usb.util",
    "usb.backend.libusb1",
    "usb.backend.libusb0",
    "instruments.panels.bmt5000.window",
    "instruments.panels.bmt5000.logic",
    "instruments.panels.bmt5000.ui",
    "instruments.panels.bmt.ui_helpers",
    "instruments.panels.widgets.usb_device_combo",
    "instruments.panels.common",
    "instruments.panels.base",
    "instruments.bmt_usb",
    "instruments.roic_adc_reader",
    "instruments.usb_raw_scanner",
]

a = Analysis(
    [str(ROOT / "packaging" / "bmt5000_entry.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PySide6.QtWebEngine",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.Qt3D",
        "matplotlib",
        "numpy",
        "pandas",
    ],
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
    name="BMT5000",
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
)
