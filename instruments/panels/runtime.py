"""Standalone Qt entry for modular instrument panels."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

from PySide6.QtWidgets import QApplication, QMainWindow

from theme_config import THEMES, generate_theme_qss


def run_standalone_panel_app(
    window_factory: Callable[[Path], QMainWindow],
    work_dir: Path | None = None,
) -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(generate_theme_qss(THEMES["light"]))
    if work_dir is not None:
        base_dir = work_dir
    elif getattr(sys, "frozen", False):
        base_dir = Path(sys.executable).resolve().parent
    else:
        base_dir = Path(__file__).resolve().parents[2]
    window = window_factory(base_dir)
    window.show()
    return app.exec()
