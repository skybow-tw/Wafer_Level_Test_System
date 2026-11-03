# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: dist/LCRMeter.exe (LCR Meter / E4980A only)."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, copy_metadata

ROOT = Path(SPECPATH).resolve().parent

hiddenimports = [
    *collect_submodules("pyvisa"),
    "theme_config",
    "lcr_meter_settings",
    "statistics_report",
    "excel_loader",
    "openpyxl",
    "PySide6.QtCharts",
    "instruments.e4980a",
    "instruments.gpib_scanner",
    "instruments.panels.lcr_meter.window",
    "instruments.panels.lcr_meter.logic",
    "instruments.panels.lcr_meter.ui",
    "instruments.panels.lcr_chart",
    "instruments.panels.virtual_lcr.logic",
    "instruments.panels.widgets.gpib_instrument_combo",
    "instruments.panels.common",
    "instruments.panels.base",
    "instruments.panels.runtime",
    "instruments.panels.registry",
]

datas = []
datas += copy_metadata("pyvisa")

a = Analysis(
    [str(ROOT / "packaging" / "lcr_meter_entry.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
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
        "nidaqmx",
        "nitypes",
        "usb",
        "pyusb",
        "tkinter",
        "IPython",
        "pytest",
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
    name="LCRMeter",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
