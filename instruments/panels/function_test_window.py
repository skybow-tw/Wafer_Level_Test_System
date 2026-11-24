"""Entry window for the Bolometer ASIC function test workflow."""

from __future__ import annotations

from pathlib import Path
import re
from threading import Thread
from time import monotonic

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLCDNumber,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from instruments.bmt_tcp import BmtTcpClient
from instruments.panels.base import InstrumentPanelBase

_CLOCK_REPLY = re.compile(
    rb"(PCLK_Check|V_SYNC_Check|H_SYNC_Check),\s*(PASS|FAIL),\s*([0-9]+(?:\.[0-9]+)?)\s*Hz"
)


class FunctionTestWindow(InstrumentPanelBase):
    _clock_finished = Signal(str, str, str, str)

    def __init__(
        self,
        parent: QWidget | None = None,
        work_dir: Path | None = None,
        tcp_client: BmtTcpClient | None = None,
    ) -> None:
        super().__init__("Bolometer ROIC Function Tester (RPI5)", parent=parent, work_dir=work_dir)
        self._tcp_client = tcp_client
        self._clock_buffer = b""
        self._clock_rows: dict[str, tuple[QLineEdit, QLabel, QLabel]] = {}
        self._command_buttons: list[QPushButton] = []
        self._clock_finished.connect(self._apply_clock_result)
        self.setFixedSize(850, 560)
        root = QWidget(self)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        button_row = QHBoxLayout()
        button_row.setSpacing(6)
        self.start_button = QPushButton("Full Test")
        self.start_button.setEnabled(False)
        self.start_button.setToolTip("Full test workflow is not connected yet")
        button_row.addWidget(self.start_button)
        for label, command in (
            ("CLK_EXT(1MHz)", "PI5, GenGPCLK,1MHz\n"),
            ("Check PCLK", "PI5, PCLK_Check\n"),
            ("Check V_SYNC", "PI5, V_SYNC_Check\n"),
            ("Check H_SYNC", "PI5, H_SYNC_Check\n"),
            ("Check Analog", "PI5, Read_Analog\n"),
        ):
            button = QPushButton(label)
            button.setEnabled(tcp_client is not None and tcp_client.is_connected)
            button.clicked.connect(
                lambda _checked=False, payload=command: self._send_command(payload)
            )
            button_row.addWidget(button)
            self._command_buttons.append(button)
        layout.addLayout(button_row)

        clock = QGroupBox("Digital_Clock")
        clock.setFixedWidth(700)
        clock_layout = QGridLayout(clock)
        clock_layout.setContentsMargins(16, 12, 16, 10)
        clock_layout.setHorizontalSpacing(10)
        clock_layout.setVerticalSpacing(5)
        clock_layout.setColumnStretch(5, 1)
        for row, (name, check) in enumerate((
            ("PCLK Check", "PCLK_Check"),
            ("V_SYNC Check", "V_SYNC_Check"),
            ("H_SYNC Check", "H_SYNC_Check"),
        )):
            label = QLabel(name)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setFixedHeight(32)
            label.setFixedWidth(180)
            label.setStyleSheet(
                "background: #DCECF7; border: 1px solid #A4C8E2; font-size: 14px;"
            )
            clock_layout.addWidget(label, row, 0)
            display = QLineEdit("--")
            display.setReadOnly(True)
            display.setAlignment(Qt.AlignmentFlag.AlignRight)
            display.setFixedHeight(32)
            display.setStyleSheet("font-size: 18px; background: white;")
            display.setFixedWidth(190)
            clock_layout.addWidget(display, row, 1)
            unit = QLabel("Hz")
            unit.setStyleSheet("font-size: 18px;")
            clock_layout.addWidget(unit, row, 2)
            lamp = QLabel()
            lamp.setFixedSize(24, 24)
            lamp.setStyleSheet(
                "background: #444; border: 2px solid #666; border-radius: 12px;"
            )
            clock_layout.addWidget(lamp, row, 3)
            status_label = QLabel("--")
            status_label.setStyleSheet("font-size: 18px;")
            clock_layout.addWidget(status_label, row, 4)
            self._clock_rows[check] = display, lamp, status_label
        layout.addWidget(clock)

        register_map = QGroupBox("Digital_SPI")
        register_map.setFixedWidth(700)
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

        analog = QGroupBox("Analog Test")
        analog.setFixedWidth(700)
        analog_layout = QGridLayout(analog)
        analog_layout.setColumnStretch(3, 1)
        for row, name in enumerate(("BGR current", "DAC_V1", "DAC_V2", "DAC_V3")):
            analog_layout.addWidget(QLabel(f"{name}:"), row, 0)
            display = QLCDNumber(analog)
            display.setDigitCount(6)
            display.setFixedWidth(100)
            display.setSegmentStyle(QLCDNumber.SegmentStyle.Flat)
            display.display("--")
            analog_layout.addWidget(display, row, 1)
            analog_layout.addWidget(QLabel("V"), row, 2)
        layout.addWidget(analog)
        self.setCentralWidget(root)

    def _send_command(self, command: str) -> None:
        if self._tcp_client is None or not self._tcp_client.is_connected:
            QMessageBox.warning(self, "TCP connection", "Server is not connected.")
            return
        check = command.partition(",")[2].strip()
        if check in self._clock_rows:
            for button in self._command_buttons:
                button.setEnabled(False)
            self._clock_rows[check][2].setText("Testing...")
            Thread(
                target=self._read_clock_result,
                args=(self._tcp_client, command, check),
                daemon=True,
            ).start()
            return
        try:
            self._tcp_client.send(command)
        except (OSError, RuntimeError) as exc:
            QMessageBox.warning(self, "TCP command failed", str(exc))

    def _read_clock_result(self, client: BmtTcpClient, command: str, check: str) -> None:
        try:
            client.send(command)
            deadline = monotonic() + 5
            while (remaining := deadline - monotonic()) > 0:
                while b"\n" in self._clock_buffer:
                    line, _, self._clock_buffer = self._clock_buffer.partition(b"\n")
                    reply = _CLOCK_REPLY.fullmatch(line.strip())
                    if reply is not None and reply[1].decode("ascii") == check:
                        self._clock_finished.emit(
                            check, reply[2].decode("ascii"), reply[3].decode("ascii"), ""
                        )
                        return
                chunk = client.recv(timeout=remaining)
                if not chunk:
                    client.disconnect()
                    raise ConnectionError("Server disconnected.")
                self._clock_buffer += chunk
                if len(self._clock_buffer) > 65536:
                    raise ValueError("Server reply is too long.")
            raise TimeoutError
        except TimeoutError:
            self._clock_finished.emit(check, "", "", "Timeout")
        except (OSError, RuntimeError, ValueError):
            self._clock_buffer = b""
            self._clock_finished.emit(check, "", "", "Error")

    @Slot(str, str, str, str)
    def _apply_clock_result(self, check: str, status: str, frequency: str, error: str) -> None:
        display, lamp, status_label = self._clock_rows[check]
        display.setText(frequency or "--")
        status_label.setText(error or status)
        color = {"PASS": "#2E7D32", "FAIL": "#C62828"}.get(status, "#444")
        lamp.setStyleSheet(
            f"background: {color}; border: 2px solid #666; border-radius: 12px;"
        )
        connected = self._tcp_client is not None and self._tcp_client.is_connected
        for button in self._command_buttons:
            button.setEnabled(connected)

    def start_measurement(
        self,
        die_x: int | None = None,
        die_y: int | None = None,
        *,
        automated: bool = False,
    ) -> bool:
        return False
