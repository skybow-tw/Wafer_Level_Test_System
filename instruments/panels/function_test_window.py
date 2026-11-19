"""Entry window for the Bolometer ASIC function test workflow."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QLabel,
    QLCDNumber,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from instruments.panels.base import InstrumentPanelBase


class FunctionTestWindow(InstrumentPanelBase):
    def __init__(
        self,
        parent: QWidget | None = None,
        work_dir: Path | None = None,
    ) -> None:
        super().__init__("Function Test(SPI、DAC)", parent=parent, work_dir=work_dir)
        self.setFixedSize(640, 480)
        root = QWidget(self)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self.start_button = QPushButton("Start Test")
        self.start_button.setEnabled(False)
        self.start_button.setToolTip("Test control is not connected yet")
        layout.addWidget(self.start_button)

        clock = QGroupBox("Clock")
        clock_layout = QGridLayout(clock)
        clock_layout.setColumnStretch(1, 1)
        for row, (name, value, unit) in enumerate((
            ("PCLK", 10, "MHz"),
            ("V_SYNC", 30, "Hz"),
            ("H_SYNC", 16500, "Hz"),
        )):
            clock_layout.addWidget(QLabel(f"{name}:"), row, 0)
            display = QLCDNumber(clock)
            display.setDigitCount(6)
            display.setSegmentStyle(QLCDNumber.SegmentStyle.Flat)
            display.display(value)
            clock_layout.addWidget(display, row, 1)
            clock_layout.addWidget(QLabel(unit), row, 2)
        layout.addWidget(clock)

        register_map = QGroupBox("Reg. Map")
        register_layout = QVBoxLayout(register_map)
        register_layout.setContentsMargins(10, 10, 10, 10)
        self.register_table = QTableWidget(20, 3, register_map)
        self.register_table.setHorizontalHeaderLabels(("Address", "Register", "Value"))
        self.register_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.register_table.verticalHeader().setVisible(False)
        self.register_table.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOn
        )
        self.register_table.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.register_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.register_table.setFixedHeight(
            self.register_table.horizontalHeader().height()
            + 3 * self.register_table.verticalHeader().defaultSectionSize()
            + 2 * self.register_table.frameWidth()
        )
        register_layout.addWidget(self.register_table)
        layout.addWidget(register_map)

        analog = QGroupBox("Analog")
        analog_layout = QGridLayout(analog)
        analog_layout.setColumnStretch(1, 1)
        for row, name in enumerate(("BGR current", "DAC_V1", "DAC_V2", "DAC_V3")):
            analog_layout.addWidget(QLabel(f"{name}:"), row, 0)
            display = QLCDNumber(analog)
            display.setDigitCount(6)
            display.setSegmentStyle(QLCDNumber.SegmentStyle.Flat)
            display.display("--")
            analog_layout.addWidget(display, row, 1)
            analog_layout.addWidget(QLabel("V"), row, 2)
        layout.addWidget(analog)
        self.setCentralWidget(root)

    def start_measurement(
        self,
        die_x: int | None = None,
        die_y: int | None = None,
        *,
        automated: bool = False,
    ) -> bool:
        return False
