"""Entry window for the Bolometer ASIC function test workflow."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from instruments.panels.base import InstrumentPanelBase


class FunctionTestWindow(InstrumentPanelBase):
    def __init__(
        self,
        parent: QWidget | None = None,
        work_dir: Path | None = None,
    ) -> None:
        super().__init__("Function Test(SPI、DAC)", parent=parent, work_dir=work_dir)
        self.setFixedSize(640, 480)
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.addWidget(QLabel("Function Test(SPI、DAC)"))
        self.setCentralWidget(root)

    def start_measurement(
        self,
        die_x: int | None = None,
        die_y: int | None = None,
        *,
        automated: bool = False,
    ) -> bool:
        return False
