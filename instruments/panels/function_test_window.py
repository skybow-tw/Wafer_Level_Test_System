"""Entry window for the Bolometer ASIC function test workflow."""

from __future__ import annotations

from collections import deque
from datetime import datetime
from pathlib import Path
import re
from threading import Thread
from time import monotonic

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QColor, QFontMetrics
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
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from bolometer_asic_tcp_settings import BolometerAsicTcpSettingsStore
from instruments.bmt_tcp import BmtTcpClient
from instruments.panels.base import InstrumentPanelBase
from instruments.pxi4461 import read_roic_voltages

_CLOCK_REPLY = re.compile(
    rb"(PCLK_Check|V_SYNC_Check|H_SYNC_Check),\s*(PASS|FAIL),\s*([0-9]+(?:\.[0-9]+)?)\s*Hz"
)
_TRANSPARENT_LABEL = "background-color: transparent;"
_ENABLE_OUTPUT_CHECK = "En_V_Out"
_REGISTER_READS = {
    "Read_Digital": ("Reg_Dig",),
    "Read_Analog": ("Reg_Dig", "Reg_Ana"),
}


class FunctionTestWindow(InstrumentPanelBase):
    _read_finished = Signal(str, str, str, str)
    _register_received = Signal(str, str, str, str, bool)
    _voltages_finished = Signal(object, str)
    _standalone_finished = Signal(str, str, str, str)

    def __init__(
        self,
        parent: QWidget | None = None,
        work_dir: Path | None = None,
        tcp_client: BmtTcpClient | None = None,
    ) -> None:
        super().__init__("Bolometer ROIC Function Tester (RPI5)", parent=parent, work_dir=work_dir)
        self._tcp_client = tcp_client
        self._roic_settings = BolometerAsicTcpSettingsStore(work_dir)
        self._standalone = False
        self._standalone_starting = False
        self._standalone_close_requested = False
        self._standalone_daq_device: str | None = None
        self._standalone_finished.connect(self._apply_standalone_result)
        self._reply_buffer = b""
        self._clock_rows: dict[str, tuple[QLineEdit, QLabel, QLabel]] = {}
        self._pending_checks: deque[str] = deque()
        self._active_sequence: QPushButton | None = None
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

        sidebar = QVBoxLayout()
        sidebar.setSpacing(8)
        sections = QVBoxLayout()
        sections.setSpacing(10)
        layout.addLayout(sidebar)
        layout.addLayout(sections, stretch=1)
        self.start_button = QPushButton("Full Test")
        self.start_button.setProperty("btnRole", "primary")
        self.start_button.setFixedSize(130, 30)
        font = self.start_button.font()
        font.setBold(True)
        self.start_button.setFont(font)
        self.start_button.setStyleSheet("QPushButton { font-weight: bold; }")
        self.start_button.setEnabled(False)
        self.start_button.setToolTip("Runs the clock checks, then reads both register maps.")
        self.start_button.clicked.connect(self._start_full_test)
        sidebar.addWidget(self.start_button)
        self.clock_sequence_button = QPushButton("Clock Check")
        self.register_sequence_button = QPushButton("Read Reg. Map")
        self.analog_sequence_button = QPushButton("Analog Test")
        self._sequence_buttons = (
            self.start_button, self.clock_sequence_button,
            self.register_sequence_button, self.analog_sequence_button,
        )
        for button in self._sequence_buttons[1:]:
            button.setFixedSize(130, 30)
            sidebar.addWidget(button)
        self.clock_sequence_button.clicked.connect(
            lambda: self._start_sequence(self.clock_sequence_button, tuple(self._clock_rows))
        )
        self.register_sequence_button.clicked.connect(
            lambda: self._start_sequence(self.register_sequence_button, tuple(_REGISTER_READS))
        )
        self.analog_sequence_button.clicked.connect(
            lambda: self._start_sequence(self.analog_sequence_button, (_ENABLE_OUTPUT_CHECK,))
        )
        self.exit_button = QPushButton("Exit")
        self.exit_button.setProperty("btnRole", "close")
        self.exit_button.setFixedSize(130, 30)
        self.exit_button.clicked.connect(self._exit_tester)
        sidebar.addWidget(self.exit_button)
        sidebar.addStretch()

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
            unit.setStyleSheet(f"{_TRANSPARENT_LABEL} font-size: 9pt;")
            clock_layout.addWidget(unit, row, 2)
            lamp = QLabel()
            lamp.setFixedSize(24, 24)
            self._set_indicator(lamp, None)
            clock_layout.addWidget(lamp, row, 3)
            status_label = QLabel("PASS")
            status_label.setStyleSheet(f"{_TRANSPARENT_LABEL} font-size: 9pt;")
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
            status.setStyleSheet(f"{_TRANSPARENT_LABEL} font-size: 9pt;")
            status.ensurePolished()
            status.setFixedWidth(status.fontMetrics().horizontalAdvance("PASS") + 8)
            register_buttons.addWidget(lamp)
            register_buttons.addWidget(status)
            self._register_indicators[check] = (lamp, status)
            self._set_indicator(lamp, None)
        register_buttons.addStretch()
        register_layout.addLayout(register_buttons)
        register_tables = QHBoxLayout()
        self._register_tables: dict[str, QTableWidget] = {}
        for check in _REGISTER_READS:
            table = self._make_register_table(register_map)
            self._register_tables[check] = table
            register_tables.addWidget(table)
        register_tables.addStretch()
        register_layout.addLayout(register_tables)
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
        output_status.setStyleSheet(f"{_TRANSPARENT_LABEL} font-size: 9pt;")
        output_row.addWidget(output_status)
        self.check_voltage_button = QPushButton("Check Voltage")
        self.check_voltage_button.setFixedSize(130, 30)
        self.check_voltage_button.clicked.connect(self._check_voltage)
        output_row.addStretch()
        analog_layout.addLayout(output_row, 0, 0, 1, 6)
        analog_layout.addWidget(
            self.check_voltage_button, 1, 0, 1, 6, Qt.AlignmentFlag.AlignLeft
        )
        self._voltage_displays: list[QLCDNumber] = []
        for row, name in enumerate(("BGR current", "DAC_V1", "DAC_V2", "DAC_V3"), 2):
            display = QLCDNumber(analog)
            display.setDigitCount(6)
            display.setFixedWidth(100 if name == "BGR current" else 90)
            display.setSegmentStyle(QLCDNumber.SegmentStyle.Flat)
            display.display("--")
            self._voltage_displays.append(display)
            unit = QLabel("V")
            unit.setStyleSheet(_TRANSPARENT_LABEL)
            name_label = QLabel(f"{name}:")
            name_label.setStyleSheet(_TRANSPARENT_LABEL)
            analog_layout.addWidget(name_label, row, 0)
            analog_layout.addWidget(display, row, 1, Qt.AlignmentFlag.AlignLeft)
            analog_layout.addWidget(unit, row, 2)
            if name == "BGR current":
                self.bgr_resistance = QSpinBox()
                self.bgr_resistance.setRange(1, 1_000_000)
                self.bgr_resistance.setAccessibleName("BGR resistance")
                analog_layout.addWidget(self.bgr_resistance, 2, 3)
                ohm_unit = QLabel("Ω")
                ohm_unit.setStyleSheet(_TRANSPARENT_LABEL)
                analog_layout.addWidget(ohm_unit, 2, 4)
        sections.addWidget(analog, alignment=Qt.AlignmentFlag.AlignLeft)
        sections.addStretch()
        self.setCentralWidget(root)
        self.ensurePolished()
        self.setFixedSize(
            max(850, layout.sizeHint().width()), max(590, layout.minimumSize().height())
        )
        self._update_command_buttons()

    @staticmethod
    def _make_register_table(parent: QWidget) -> QTableWidget:
        table = QTableWidget(0, 3, parent)
        table.setHorizontalHeaderLabels(("Addr.", "Default", "Read"))
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        table.verticalHeader().setVisible(False)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.ensurePolished()
        header.ensurePolished()
        for column in range(table.columnCount()):
            table.setColumnWidth(column, 90)
        frame = 2 * table.frameWidth()
        table.setFixedSize(
            header.length() + table.verticalScrollBar().sizeHint().width() + frame,
            header.sizeHint().height() + 3 * table.verticalHeader().defaultSectionSize() + frame,
        )
        return table

    def start_standalone(self) -> None:
        """Connect and configure the tester using the last local settings."""
        if self._standalone:
            return
        self._standalone = True
        self._standalone_starting = True
        client = BmtTcpClient()
        self._tcp_client = client
        self.check_voltage_button.setEnabled(False)
        self._standalone_status = QLabel("連線中…")
        self._standalone_status.setStyleSheet(_TRANSPARENT_LABEL)
        self._standalone_status.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.statusBar().addWidget(self._standalone_status, 1)
        content_height = self.centralWidget().layout().minimumSize().height()
        self.setFixedHeight(max(self.height(), content_height + self.statusBar().sizeHint().height()))
        Thread(target=self._configure_standalone, args=(client,), daemon=True).start()

    def _configure_standalone(self, client: BmtTcpClient) -> None:
        endpoint = self._roic_settings.get_endpoint()
        try:
            client.connect(endpoint.ip, endpoint.port)
        except (OSError, RuntimeError, ValueError):
            self._standalone_finished.emit("", "", "", "")
            return

        connected_at = datetime.now().astimezone()
        server = f"{endpoint.ip}:{endpoint.port}｜連線時間 {connected_at:%Y-%m-%d %H:%M:%S}"
        if self._standalone_close_requested:
            self._standalone_finished.emit(server, "", "", "")
            return
        device = self._roic_settings.get_daq_device() or ""
        frequency = self._roic_settings.get_clock_frequency()
        try:
            client.generate_roic_clock(frequency)
        except (OSError, RuntimeError, ValueError) as exc:
            self._standalone_finished.emit(server, device, frequency, str(exc) or "Timeout")
        else:
            self._standalone_finished.emit(server, device, frequency, "")

    @Slot(str, str, str, str)
    def _apply_standalone_result(
        self, server: str, device: str, frequency: str, error: str
    ) -> None:
        self._standalone_starting = False
        if self._standalone_close_requested:
            self.close()
            return
        self._standalone_daq_device = device or None
        self.check_voltage_button.setEnabled(True)
        self._update_command_buttons()
        if not server:
            self._standalone_status.setText("連線失敗")
            return
        result = "失敗" if error else "成功"
        self._standalone_status.setText(
            f"Server：{server}　｜　"
            f"DAQ：{device or '未選擇（自動偵測）'}　｜　"
            f"CLK_EXT：{frequency}（{result}）"
        )
        self.setFixedWidth(max(self.width(), self._standalone_status.sizeHint().width() + 20))
        self._standalone_status.setToolTip(error)

    def _exit_tester(self) -> None:
        if not self._standalone and self._tcp_client is not None:
            self._tcp_client.disconnect_roic()
        self.close()

    def closeEvent(self, event) -> None:
        if self._standalone_starting:
            self._standalone_close_requested = True
            event.ignore()
            return
        if self._standalone and self._tcp_client is not None:
            self._tcp_client.disconnect_roic()
        super().closeEvent(event)

    @staticmethod
    def _set_indicator(lamp: QLabel, passed: bool | None) -> None:
        color = {True: "#2E7D32", False: "#C62828", None: "#000000"}[passed]
        lamp.setStyleSheet(
            f"background: {color}; border: 2px solid #666; border-radius: 12px;"
        )

    def _check_voltage(self) -> None:
        self.check_voltage_button.setEnabled(False)
        self.analog_sequence_button.setEnabled(False)
        for display in self._voltage_displays:
            display.display("--")
        Thread(target=self._read_voltages, daemon=True).start()

    def _read_voltages(self) -> None:
        try:
            device = (
                self._standalone_daq_device if self._standalone
                else self._roic_settings.get_daq_device()
            )
            values = read_roic_voltages(device)
            if len(values) != 4:
                raise RuntimeError("Expected four voltage readings from NI DAQ.")
        except Exception as exc:
            self._voltages_finished.emit([], str(exc))
        else:
            self._voltages_finished.emit(values, "")

    @Slot(object, str)
    def _apply_voltages(self, values: list[float], error: str) -> None:
        self.check_voltage_button.setEnabled(True)
        if self._active_sequence is self.analog_sequence_button:
            self._finish_sequence("Check Voltage", error)
        elif self.exit_button.isEnabled():
            self._update_command_buttons()
        if error:
            QMessageBox.warning(self, "NI DAQ read failed", error)
            return
        for display, value in zip(self._voltage_displays, values):
            display.display(f"{value:.3f}")

    def _update_command_buttons(self) -> None:
        connected = self._tcp_client is not None and self._tcp_client.is_connected
        clock_enabled = connected and bool(self._tcp_client.roic_clock_frequency)
        self.start_button.setEnabled(clock_enabled)
        self.clock_sequence_button.setEnabled(clock_enabled)
        self.register_sequence_button.setEnabled(connected)
        self.analog_sequence_button.setEnabled(connected and self.check_voltage_button.isEnabled())
        self.exit_button.setEnabled(True)
        for button in self._command_buttons:
            if button in self._clock_check_buttons:
                button.setEnabled(clock_enabled)
            else:
                button.setEnabled(connected)

    def _start_full_test(self) -> None:
        self._start_sequence(self.start_button, (*self._clock_rows, *_REGISTER_READS))

    def _start_sequence(self, button: QPushButton, checks: tuple[str, ...]) -> None:
        if not button.isEnabled() or self._active_sequence is not None:
            return
        self._active_sequence = button
        if button is self.analog_sequence_button:
            self.check_voltage_button.setEnabled(False)
        for check in _REGISTER_READS:
            if check in checks:
                self._set_indicator(self._register_indicators[check][0], None)
        self._pending_checks.extend(checks)
        self._run_next_sequence_step()

    def _run_next_sequence_step(self) -> None:
        check = self._pending_checks.popleft()
        self._active_sequence.setToolTip(f"In progress: {check}")
        self._send_command(f"PI5, {check}\n")

    def _finish_sequence(self, check: str, error: str) -> None:
        button = self._active_sequence
        self._active_sequence = None
        self._pending_checks.clear()
        if button is self.analog_sequence_button:
            self.check_voltage_button.setEnabled(True)
        if button is not None:
            button.setToolTip(f"Stopped at {check}: {error}" if error else "Sequence complete.")
        self._update_command_buttons()

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
        if check in self._clock_rows or check in _REGISTER_READS or check == _ENABLE_OUTPUT_CHECK:
            for button in self._command_buttons:
                button.setEnabled(False)
            for button in self._sequence_buttons:
                button.setEnabled(False)
            self.exit_button.setEnabled(False)
            if check in _REGISTER_READS:
                self._register_tables[check].setRowCount(0)
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
                                self._register_received.emit(check, address, default, actual, status.casefold() == "fail")
                                deadline = monotonic() + 5
                        continue
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

    @Slot(str, str, str, str, bool)
    def _append_register(
        self, check: str, address: str, default: str, actual: str, failed: bool
    ) -> None:
        self._register_has_failure |= failed
        table = self._register_tables[check]
        row = table.rowCount()
        table.insertRow(row)
        for column, value in enumerate((address, default, actual)):
            item = QTableWidgetItem(value)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if failed and column == 2:
                item.setBackground(QColor("#F44336"))
            table.setItem(row, column, item)

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
        if self._active_sequence is not None:
            connected = self._tcp_client is not None and self._tcp_client.is_connected
            if not error and connected and self._pending_checks:
                self._run_next_sequence_step()
                return
            if not error and connected and self._active_sequence is self.analog_sequence_button:
                self._active_sequence.setToolTip("In progress: Check Voltage")
                self._check_voltage()
                return
            self._finish_sequence(check, error or ("" if connected else "Server disconnected"))
            return
        self._update_command_buttons()

    def start_measurement(
        self,
        die_x: int | None = None,
        die_y: int | None = None,
        *,
        automated: bool = False,
    ) -> bool:
        return False
