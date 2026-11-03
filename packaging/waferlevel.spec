# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: dist/WaferLevel.exe (full wafer-level GUI)."""

from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_submodules,
    copy_metadata,
)

ROOT = Path(SPECPATH).resolve().parent

hiddenimports = [
    *collect_submodules("instruments"),
    *collect_submodules("prober_motor"),
    *collect_submodules("nidaqmx"),
    *collect_submodules("nitypes"),
    *collect_submodules("pyvisa"),
    "PySide6.QtCharts",
    "usb.core",
    "usb.util",
    "usb.backend.libusb1",
    "usb.backend.libusb0",
    "openpyxl",
    "numpy",
    "deprecation",
]

datas = [
    (
        str(ROOT / "instruments" / "panels" / "dsa" / "Settings_DSA.toml"),
        "instruments/panels/dsa",
    ),
]
datas += collect_data_files("nidaqmx")
datas += copy_metadata("nidaqmx")
datas += copy_metadata("nitypes")

a = Analysis(
    [str(ROOT / "main.py")],
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
        "PySide6.Qt3DAnimation",
        "PySide6.Qt3DCore",
        "PySide6.Qt3DExtras",
        "PySide6.Qt3DInput",
        "PySide6.Qt3DLogic",
        "PySide6.Qt3DRender",
        "matplotlib",
        "pandas",
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
    name="WaferLevel",
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
