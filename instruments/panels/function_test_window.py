"""Entry window for the Bolometer ASIC function test workflow."""

from __future__ import annotations

from collections import deque
from pathlib import Path
import re
from threading import Thread
from time import monotonic

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QColor, QFontMetrics
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLCDNumber,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from instruments.bmt_tcp import BmtTcpClient
from instruments.panels.base import InstrumentPanelBase
from instruments.pxi4461 import read_roic_voltages

_CLOCK_REPLY = re.compile(
    rb"(PCLK_Check|V_SYNC_Check|H_SYNC_Check),\s*(PASS|FAIL),\s*([0-9]+(?:\.[0-9]+)?)\s*Hz"
)
_EXT_CLOCK_PREFIX = "GenCLK_EXT,"
_TRANSPARENT_LABEL = "background-color: transparent;"
_ENABLE_OUTPUT_CHECK = "En_V_Out"
_REGISTER_READS = {
    "Read_Digital": ("Reg_Dig",),
    "Read_Analog": ("Reg_Dig", "Reg_Ana"),
}


class FunctionTestWindow(InstrumentPanelBase):
    _read_finished = Signal(str, str, str, str)
    _register_received = Signal(str, str, str, bool)
    _voltages_finished = Signal(object, str)

    def __init__(
        self,
        parent: QWidget | None = None,
        work_dir: Path | None = None,
        tcp_client: BmtTcpClient | None = None,
    ) -> None:
        super().__init__("Bolometer ROIC Function Tester (RPI5)", parent=parent, work_dir=work_dir)
        self._tcp_client = tcp_client
        self._reply_buffer = b""
        self._ext_clock_ready = False
        self._clock_rows: dict[str, tuple[QLineEdit, QLabel, QLabel]] = {}
        self._full_test_pending: deque[str] = deque()
        self._full_test_running = False
        self._command_buttons: list[QPushButton] = []
        self._clock_check_buttons: list[QPushButton] = []
        self._read_finished.connect(self._apply_read_result)
        self._register_received.connect(self._append_register)
        self._register_has_failure = False
        self._voltages_finished.connect(self._apply_voltages)
        root = QWidget(self)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        command_group = QGroupBox("Command")
        sidebar = QVBoxLayout(command_group)
        sidebar.setSpacing(8)
        sections = QVBoxLayout()
        sections.setSpacing(10)
        layout.addWidget(command_group, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addLayout(sections, stretch=1)
        self.ext_clock_selection = QComboBox()
        self.ext_clock_selection.addItems(("1MHz", "5MHz", "10MHz"))
        selection_label = QLabel("EXT_CLK Selection:")
        selection_label.setBuddy(self.ext_clock_selection)
        sidebar.addWidget(selection_label)
        sidebar.addWidget(self.ext_clock_selection)
        self.ext_clock_button = QPushButton("Generate")
        self.ext_clock_button.setFixedSize(130, 30)
        self.ext_clock_button.setProperty("btnRole", "primary")
        self.ext_clock_button.clicked.connect(self._generate_ext_clock)
        self._command_buttons.append(self.ext_clock_button)
        sidebar.addWidget(self.ext_clock_button)
        self.start_button = QPushButton("Full Test")
        self.start_button.setProperty("btnRole", "primary")
        self.ext_clock_button.setStyleSheet(
            "QPushButton:disabled { background-color: #0078D4; "
            "color: #DCECF7; border: 1px solid #0078D4; }"
        )
        self.start_button.setFixedSize(130, 30)
        font = self.start_button.font()
        font.setBold(True)
        self.start_button.setFont(font)
        self.start_button.setStyleSheet("QPushButton { font-weight: bold; }")
        self.start_button.setEnabled(False)
        self.start_button.setToolTip("Runs the clock checks, then reads both register maps.")
        self.start_button.clicked.connect(self._start_full_test)
        sidebar.addWidget(self.start_button)
        sidebar.addSpacing(3 * self.start_button.height() - sidebar.spacing())

        clock = QGroupBox("Digital Output Clock Check")
        clock_layout = QGridLayout(clock)
        clock_layout.setContentsMargins(16, 12, 16, 10)
        clock_layout.setHorizontalSpacing(10)
        clock_layout.setVerticalSpacing(5)
        clock_layout.setColumnStretch(5, 1)
        for row, (name, check) in enumerate((
            ("Check PCLK", "PCLK_Check"),
            ("Check V_SYNC", "V_SYNC_Check"),
            ("Check H_SYNC", "H_SYNC_Check"),
        )):
            button = self._make_command_button(name, f"PI5, {check}\n")
            self._clock_check_buttons.append(button)
            clock_layout.addWidget(button, row, 0)
            display = QLineEdit("--")
            display.setReadOnly(True)
            display.setAlignment(Qt.AlignmentFlag.AlignRight)
            display.setFixedHeight(32)
            display.setStyleSheet("font-size: 18px; background: white;")
            display.setFixedWidth(100)
            clock_layout.addWidget(display, row, 1)
            unit = QLabel("Hz")
            unit.setStyleSheet(f"{_TRANSPARENT_LABEL} font-size: 18px;")
            clock_layout.addWidget(unit, row, 2)
            lamp = QLabel()
            lamp.setFixedSize(24, 24)
            self._set_indicator(lamp, None)
            clock_layout.addWidget(lamp, row, 3)
            status_label = QLabel("PASS")
            status_label.setStyleSheet(f"{_TRANSPARENT_LABEL} font-size: 18px;")
            clock_layout.addWidget(status_label, row, 4)
            self._clock_rows[check] = display, lamp, status_label
        sections.addWidget(clock, alignment=Qt.AlignmentFlag.AlignLeft)

        register_map = QGroupBox("Digital_SPI Function Test_Register Map Read/Write")
        register_layout = QVBoxLayout(register_map)
        register_layout.setContentsMargins(10, 4, 10, 8)
        register_layout.setSpacing(4)
        register_buttons = QHBoxLayout()
        self._register_read_buttons = {}
        self._register_indicators: dict[str, tuple[QLabel, QLabel]] = {}
        for label, check in (("Read Digital", "Read_Digital"), ("Read Analog", "Read_Analog")):
            button = self._make_command_button(label, f"PI5, {check}\n")
            self._register_read_buttons[check] = button
            register_buttons.addWidget(button)
            lamp = QLabel()
            lamp.setFixedSize(24, 24)
            status = QLabel("PASS")
            status.setStyleSheet(f"{_TRANSPARENT_LABEL} font-size: 18px;")
            status.ensurePolished()
            status.setFixedWidth(status.fontMetrics().horizontalAdvance("PASS") + 8)
            register_buttons.addWidget(lamp)
            register_buttons.addWidget(status)
            self._register_indicators[check] = (lamp, status)
            self._set_indicator(lamp, None)
        register_buttons.addStretch()
        register_layout.addLayout(register_buttons)
        self.register_table = QTableWidget(0, 3, register_map)
        self.register_table.setHorizontalHeaderLabels(("Address", "Default Value", "Read Value"))
        self.register_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Fixed
        )
        for column in range(3):
            self.register_table.setColumnWidth(column, 150)
        self.register_table.verticalHeader().setVisible(False)
        self.register_table.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOn
        )
        self.register_table.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.register_table.ensurePolished()
        self.register_table.setFixedWidth(
            self.register_table.horizontalHeader().length()
            + self.register_table.verticalScrollBar().sizeHint().width()
            + 2 * self.register_table.frameWidth()
        )
        self.register_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.register_table.setFixedHeight(
            self.register_table.horizontalHeader().sizeHint().height()
            + 3 * self.register_table.verticalHeader().defaultSectionSize()
            + 2 * self.register_table.frameWidth()
        )
        register_layout.addWidget(self.register_table)
        sections.addWidget(register_map, alignment=Qt.AlignmentFlag.AlignLeft)

        analog = QGroupBox("Analog_Output Test")
        analog_layout = QGridLayout(analog)
        analog_layout.setColumnStretch(5, 1)
        output_row = QHBoxLayout()
        self.enable_output_button = self._make_command_button(
            "Enable Output", f"PI5, {_ENABLE_OUTPUT_CHECK}\n"
        )
        output_row.addWidget(self.enable_output_button)
        self.output_lamp = QLabel()
        self.output_lamp.setFixedSize(24, 24)
        self._set_indicator(self.output_lamp, None)
        output_row.addWidget(self.output_lamp)
        output_status = QLabel("ON")
        output_status.setStyleSheet(f"{_TRANSPARENT_LABEL} font-size: 18px;")
        output_row.addWidget(output_status)
        self.check_voltage_button = QPushButton("Check Voltage")
        self.check_voltage_button.setFixedSize(130, 30)
        self.check_voltage_button.clicked.connect(self._check_voltage)
        output_row.addWidget(self.check_voltage_button)
        output_row.addStretch()
        analog_layout.addLayout(output_row, 0, 0, 1, 6)
        self._voltage_displays: list[QLCDNumber] = []
        dac_row = QHBoxLayout()
        for name in ("BGR current", "DAC_V1", "DAC_V2", "DAC_V3"):
            display = QLCDNumber(analog)
            display.setDigitCount(6)
            display.setFixedWidth(100 if name == "BGR current" else 90)
            display.setSegmentStyle(QLCDNumber.SegmentStyle.Flat)
            display.display("--")
            self._voltage_displays.append(display)
            unit = QLabel("V")
            unit.setStyleSheet(_TRANSPARENT_LABEL)
            if name == "BGR current":
                analog_layout.addWidget(QLabel(f"{name}:"), 1, 0)
                analog_layout.addWidget(display, 1, 1)
                analog_layout.addWidget(unit, 1, 2)
                self.bgr_resistance = QSpinBox()
                self.bgr_resistance.setRange(1, 1_000_000)
                self.bgr_resistance.setAccessibleName("BGR resistance")
                analog_layout.addWidget(self.bgr_resistance, 1, 3)
                ohm_unit = QLabel("Ω")
                ohm_unit.setStyleSheet(_TRANSPARENT_LABEL)
                analog_layout.addWidget(ohm_unit, 1, 4)
            else:
                if dac_row.count():
                    dac_row.addSpacing(24)
                dac_row.addWidget(QLabel(f"{name}:"))
                dac_row.addWidget(display)
                dac_row.addWidget(unit)
        dac_row.addStretch()
        analog_layout.addLayout(dac_row, 2, 0, 1, 6)
        sections.addWidget(analog, alignment=Qt.AlignmentFlag.AlignLeft)
        sections.addStretch()
        self.exit_button = QPushButton("Exit")
        self.exit_button.setFixedSize(130, 30)
        self.exit_button.clicked.connect(self._exit_tester)
        sidebar.addWidget(self.exit_button)
        self.setCentralWidget(root)
        self.ensurePolished()
        self.setFixedSize(max(850, layout.sizeHint().width()), 590)
        self.ext_clock_selection.currentTextChanged.connect(self._invalidate_ext_clock)
        self._update_command_buttons()

    def _exit_tester(self) -> None:
        client = self._tcp_client
        error = ""
        if client is not None and client.is_connected:
            try:
                client.send("PI5, StopCLK_EXT\n")
            except (OSError, RuntimeError) as exc:
                error = str(exc)
            finally:
                client.disconnect()
        if error:
            QMessageBox.warning(self, "Stop external clock failed", error)
        self.close()

    def _generate_ext_clock(self) -> None:
        frequency = self.ext_clock_selection.currentText()
        self._send_command(f"PI5, {_EXT_CLOCK_PREFIX}{frequency}\n")

    @staticmethod
    def _set_indicator(lamp: QLabel, passed: bool | None) -> None:
        color = {True: "#2E7D32", False: "#C62828", None: "#000000"}[passed]
        lamp.setStyleSheet(
            f"background: {color}; border: 2px solid #666; border-radius: 12px;"
        )

    def _check_voltage(self) -> None:
        self.check_voltage_button.setEnabled(False)
        for display in self._voltage_displays:
            display.display("--")
        Thread(target=self._read_voltages, daemon=True).start()

    def _read_voltages(self) -> None:
        try:
            values = read_roic_voltages()
            if len(values) != 4:
                raise RuntimeError("Expected four voltage readings from NI DAQ.")
        except Exception as exc:
            self._voltages_finished.emit([], str(exc))
        else:
            self._voltages_finished.emit(values, "")

    @Slot(object, str)
    def _apply_voltages(self, values: list[float], error: str) -> None:
        self.check_voltage_button.setEnabled(True)
        if error:
            QMessageBox.warning(self, "NI DAQ read failed", error)
            return
        for display, value in zip(self._voltage_displays, values):
            display.display(f"{value:.3f}")

    def _invalidate_ext_clock(self) -> None:
        self._ext_clock_ready = False
        self.ext_clock_button.setToolTip("Generate the selected frequency.")
        self._update_command_buttons()

    def _update_command_buttons(self) -> None:
        connected = self._tcp_client is not None and self._tcp_client.is_connected
        clock_enabled = connected and self._ext_clock_ready
        self.start_button.setEnabled(clock_enabled and not self._full_test_running)
        for button in self._command_buttons:
            button.setEnabled(
                clock_enabled if button in self._clock_check_buttons else connected
            )

    def _start_full_test(self) -> None:
        if not self.start_button.isEnabled():
            return
        self._full_test_running = True
        for check in _REGISTER_READS:
            self._set_indicator(self._register_indicators[check][0], None)
        self._full_test_pending.extend((*self._clock_rows, *_REGISTER_READS))
        self._run_next_full_test_step()

    def _run_next_full_test_step(self) -> None:
        check = self._full_test_pending.popleft()
        self.start_button.setToolTip(f"Full Test in progress: {check}")
        self._send_command(f"PI5, {check}\n")

    def _make_command_button(self, label: str, command: str) -> QPushButton:
        button = QPushButton(label)
        button.setFixedSize(130, 30)
        button.setEnabled(self._tcp_client is not None and self._tcp_client.is_connected)
        button.clicked.connect(lambda: self._send_command(command))
        self._command_buttons.append(button)
        return button

    def _send_command(self, command: str) -> None:
        if self._tcp_client is None or not self._tcp_client.is_connected:
            QMessageBox.warning(self, "TCP connection", "Server is not connected.")
            return
        check = command.partition(",")[2].strip()
        generates_clock = check.startswith(_EXT_CLOCK_PREFIX)
        if generates_clock or check in self._clock_rows or check in _REGISTER_READS or check == _ENABLE_OUTPUT_CHECK:
            for button in self._command_buttons:
                button.setEnabled(False)
            self.start_button.setEnabled(False)
            self.exit_button.setEnabled(False)
            self.ext_clock_selection.setEnabled(False)
            if generates_clock:
                self._ext_clock_ready = False
                self.ext_clock_button.setToolTip("Waiting for Server reply...")
            elif check in _REGISTER_READS:
                self.register_table.setRowCount(0)
                self._register_has_failure = False
                self._set_indicator(self._register_indicators[check][0], None)
                self._register_read_buttons[check].setToolTip("Reading register map...")
            elif check == _ENABLE_OUTPUT_CHECK:
                self._set_indicator(self.output_lamp, None)
                self.enable_output_button.setToolTip("Waiting for Analog_On...")
            else:
                _, lamp, label = self._clock_rows[check]
                self._set_indicator(lamp, None)
                label.setToolTip("Testing...")
            Thread(
                target=self._read_result,
                args=(self._tcp_client, command, check),
                daemon=True,
            ).start()
            return
        try:
            self._tcp_client.send(command)
        except (OSError, RuntimeError) as exc:
            QMessageBox.warning(self, "TCP command failed", str(exc))

    def _read_result(self, client: BmtTcpClient, command: str, check: str) -> None:
        frequency = check.removeprefix(_EXT_CLOCK_PREFIX) if check.startswith(_EXT_CLOCK_PREFIX) else ""
        register_prefixes = _REGISTER_READS.get(check)
        try:
            client.send(command)
            deadline = monotonic() + 5
            while (remaining := deadline - monotonic()) > 0:
                while b"\n" in self._reply_buffer:
                    line, _, self._reply_buffer = self._reply_buffer.partition(b"\n")
                    if check == _ENABLE_OUTPUT_CHECK and line.strip() == b"Analog_On":
                        self._read_finished.emit(check, "", "", "")
                        return
                    if register_prefixes is not None:
                        if line.strip() == b"Reg_Tx_OK":
                            self._read_finished.emit(check, "", "", "")
                            return
                        fields = [field.strip() for field in line.decode("ascii", errors="replace").split(",")]
                        if len(fields) == 5 and fields[0] in register_prefixes:
                            _, address, default, actual, status = fields
                            if status.casefold() in ("ok", "fail"):
                                self._register_received.emit(address, default, actual, status.casefold() == "fail")
                                deadline = monotonic() + 5
                        continue
                    if frequency and line.startswith(_EXT_CLOCK_PREFIX.encode("ascii")):
                        expected = f"{_EXT_CLOCK_PREFIX}OK,{frequency}".encode("ascii")
                        error = "" if line.removesuffix(b"\r") == expected else "Unexpected reply"
                        self._read_finished.emit(check, "", frequency, error)
                        return
                    reply = _CLOCK_REPLY.fullmatch(line.strip())
                    if reply is not None and reply[1].decode("ascii") == check:
                        self._read_finished.emit(
                            check, reply[2].decode("ascii"), reply[3].decode("ascii"), ""
                        )
                        return
                chunk = client.recv(timeout=max(0.0, deadline - monotonic()))
                if not chunk:
                    client.disconnect()
                    raise ConnectionError("Server disconnected.")
                self._reply_buffer += chunk
                if len(self._reply_buffer) > 65536:
                    raise ValueError("Server reply is too long.")
            raise TimeoutError
        except TimeoutError:
            self._reply_buffer = b""
            self._read_finished.emit(check, "", "", "Timeout")
        except (OSError, RuntimeError, ValueError):
            self._reply_buffer = b""
            self._read_finished.emit(check, "", "", "Error")

    @Slot(str, str, str, bool)
    def _append_register(self, address: str, default: str, actual: str, failed: bool) -> None:
        self._register_has_failure |= failed
        row = self.register_table.rowCount()
        self.register_table.insertRow(row)
        for column, value in enumerate((address, default, actual)):
            item = QTableWidgetItem(value)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if failed and column == 2:
                item.setBackground(QColor("#F44336"))
            self.register_table.setItem(row, column, item)

    @Slot(str, str, str, str)
    def _apply_read_result(self, check: str, status: str, frequency: str, error: str) -> None:
        if check in self._clock_rows:
            display, lamp, status_label = self._clock_rows[check]
            text = frequency or "--"
            font = display.font()
            font.setPixelSize(18)
            available_width = display.width() - 10
            while font.pixelSize() > 8 and QFontMetrics(font).horizontalAdvance(text) > available_width:
                font.setPixelSize(font.pixelSize() - 1)
            display.setStyleSheet(f"font-size: {font.pixelSize()}px; background: white;")
            display.setText(text)
            status_label.setToolTip(error or status)
            self._set_indicator(lamp, not error and status == "PASS")
        elif check in _REGISTER_READS:
            self._set_indicator(
                self._register_indicators[check][0], not error and not self._register_has_failure
            )
            result = "Register check failed" if self._register_has_failure else "Register map complete"
            self._register_read_buttons[check].setToolTip(error or result)
        elif check == _ENABLE_OUTPUT_CHECK:
            self._set_indicator(self.output_lamp, not error)
            self.enable_output_button.setToolTip(error or "Server confirmed analog output is on")
        else:
            self._ext_clock_ready = not error and frequency == self.ext_clock_selection.currentText()
            self.ext_clock_button.setToolTip(error or f"Server confirmed {frequency}")
        if self._full_test_running:
            connected = self._tcp_client is not None and self._tcp_client.is_connected
            if not error and connected and self._full_test_pending:
                self._run_next_full_test_step()
                return
            self._full_test_running = False
            self._full_test_pending.clear()
            if error or not connected:
                self.start_button.setToolTip(
                    f"Full Test stopped at {check}: {error or 'Server disconnected'}"
                )
            else:
                self.start_button.setToolTip("Full Test sequence complete.")
        self.ext_clock_selection.setEnabled(True)
        self.exit_button.setEnabled(True)
        self._update_command_buttons()

    def start_measurement(
        self,
        die_x: int | None = None,
        die_y: int | None = None,
        *,
        automated: bool = False,
    ) -> bool:
        return False
