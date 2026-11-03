"""NI 8452 instrument control window."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QWidget

from instruments.panels.registry import NI_8452_DISPLAY_NAME
from instruments.panels.simple_trend.window import SimpleTrendWindow


class Ni8452Window(SimpleTrendWindow):
    def __init__(
        self,
        parent: QWidget | None = None,
        work_dir: Path | None = None,
        *,
        display_name: str | None = None,
    ) -> None:
        super().__init__(
            display_name or NI_8452_DISPLAY_NAME,
            parent=parent,
            work_dir=work_dir,
        )
