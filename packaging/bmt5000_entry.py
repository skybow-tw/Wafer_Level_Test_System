"""Entry point for the BMT5000 production-line executable (PyInstaller)."""

from __future__ import annotations

import sys
from pathlib import Path


def _work_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    if not getattr(sys, "frozen", False):
        root_str = str(root)
        if root_str not in sys.path:
            sys.path.insert(0, root_str)

    from PySide6.QtWidgets import QApplication

    from instruments.panels.bmt5000.window import Bmt5000Window

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = Bmt5000Window(work_dir=_work_dir())
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
