"""Step-by-step guided setup wizard shown before the main application."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from prober_motor import ProberType, create_chuck_motor
from prober_motor.base import ChuckMotorBase
from prober_motor.mpi_tp80 import MpiTp80ChuckMotor
from prober_motor.suss import SussChuckMotor
from prober_motor.tcp_client import ProberTcpClient
from prober_tcp_settings import ProberTcpSettingsStore
from theme_config import THEMES, generate_theme_qss


class DeviceType(Enum):
    IMU = "IMU"
    BOLOMETER = "Bolometer"
    GYRO = "Gyro"
    OTHERS = "Others"


class BmModelType(Enum):
    BM28 = "BM28"
    BM1602 = "BM1602"
    BM6402 = "BM6402"
    BM12801 = "BM12801"


class ImuSubType(Enum):
    COMPONENT = "Element"
    ASIC = "ASIC"


class DutType(Enum):
    ELEMENT = "Element"
    ASIC = "ASIC"


class InstrumentType(Enum):
    LCR_METER = "LCR Meter"
    LCR_METER_BOLOMETER = "LCR_Meter_Bolometer"
    VIRTUAL_LCR = "VirtualLCR"
    DSA = "DSA"
    BMT3000 = "BMT3000"
    BMT5000 = "BMT5000"
    NI_8452_SPI_TEST = "NI 8452 SPI Test"


@dataclass(frozen=True)
class GuidedSetupResult:
    prober_type: ProberType
    device_type: DeviceType
    bm_model: BmModelType | None = None
    imu_subtype: ImuSubType | None = None
    dut_type: DutType | None = None
    instrument_type: InstrumentType | None = None
    tcp_client: ProberTcpClient | None = None


_PROBER_BUTTONS: tuple[tuple[str, ProberType], ...] = (
    ("MPI-TP80", ProberType.MPI_TP80),
    ("SUSS", ProberType.SUSS),
    ("MPI-TS2000", ProberType.MPI_TS2000),
    ("Simulation", ProberType.SIMULATION),
)

_DEVICE_BUTTONS: tuple[tuple[str, DeviceType], ...] = (
    ("IMU", DeviceType.IMU),
    ("Bolometer", DeviceType.BOLOMETER),
    ("Gyro", DeviceType.GYRO),
    ("Others", DeviceType.OTHERS),
)

_BM_BUTTONS: tuple[tuple[str, BmModelType], ...] = (
    ("BM28", BmModelType.BM28),
    ("BM1602", BmModelType.BM1602),
    ("BM6402", BmModelType.BM6402),
    ("BM12801", BmModelType.BM12801),
)

_IMU_BUTTONS: tuple[tuple[str, ImuSubType], ...] = (
    ("Element", ImuSubType.COMPONENT),
    ("ASIC", ImuSubType.ASIC),
)

_DUT_BUTTONS: tuple[tuple[str, DutType], ...] = (
    ("Element", DutType.ELEMENT),
    ("ASIC", DutType.ASIC),
)

_TRADITIONAL_INSTRUMENT_BUTTONS: tuple[tuple[str, InstrumentType], ...] = (
    ("LCR Meter", InstrumentType.LCR_METER),
    ("DSA", InstrumentType.DSA),
)

_OTHERS_INSTRUMENT_BUTTONS: tuple[tuple[str, InstrumentType], ...] = (
    ("LCR Meter", InstrumentType.LCR_METER),
    ("DSA", InstrumentType.DSA),
    ("VirtualLCR", InstrumentType.VIRTUAL_LCR),
)

_BOLOMETER_INSTRUMENT_BUTTONS: tuple[tuple[str, InstrumentType], ...] = (
    ("BMT3000", InstrumentType.BMT3000),
    ("BMT5000", InstrumentType.BMT5000),
    ("LCR Meter", InstrumentType.LCR_METER_BOLOMETER),
)

_ASIC_INSTRUMENT_BUTTONS: tuple[tuple[str, InstrumentType], ...] = (
    ("NI 8452 SPI Test", InstrumentType.NI_8452_SPI_TEST),
)

_DUT_PAGE_INDEX = 4
_INSTRUMENT_PAGE_INDEX = 5

_TCP_PROBER_TYPES = frozenset(
    {ProberType.SUSS, ProberType.MPI_TP80, ProberType.MPI_TS2000}
)

_TCP_TEST_VELOCITY_SPEED = 50


def _connect_error_code(exc: BaseException) -> str:
    if isinstance(exc, TimeoutError):
        return "timeout"
    if isinstance(exc, OSError):
        winerror = getattr(exc, "winerror", None)
        if winerror is not None:
            return str(winerror)
        if exc.errno is not None:
            return str(exc.errno)
    return "unknown"


_GUIDED_SETUP_QSS = """
QPushButton[setupChoice="true"]:checked {
    background-color: #0078D4;
    color: #FFFFFF;
    border: 1px solid #0078D4;
}
QPushButton[setupChoice="true"]:checked:hover {
    background-color: #106EBE;
    color: #FFFFFF;
    border: 1px solid #106EBE;
}
"""


class _TcpConnectBridge(QObject):
    finished = Signal(bool, str)


class GuidedSetupWindow(QMainWindow):
    """Multi-step wizard: prober, device type, then path-specific selection."""

    finished = Signal(GuidedSetupResult)

    def __init__(self, work_dir: Path | None = None) -> None:
        super().__init__()
        self._work_dir = work_dir or Path.cwd()
        self._tcp_settings = ProberTcpSettingsStore(self._work_dir)
        self._completed = False
        self._selected_prober: ProberType | None = None
        self._selected_device: DeviceType | None = None
        self._selected_bm: BmModelType | None = None
        self._selected_imu_subtype: ImuSubType | None = None
        self._selected_dut: DutType | None = None
        self._selected_instrument: InstrumentType | None = None
        self._instrument_back_index = 1
        self._instrument_page: QGroupBox | None = None
        self._tcp_client = ProberTcpClient()
        self._tcp_connect_bridge = _TcpConnectBridge()
        self._tcp_connect_bridge.finished.connect(self._on_tcp_connect_finished)
        self._tcp_connecting = False
        self._tcp_last_error: str | None = None
        self._tcp_connect_error_code: str | None = None
        self._chuck_motor: ChuckMotorBase | None = None
        self._xy_velocity_timer = QTimer(self)
        self._xy_velocity_timer.setInterval(100)
        self._xy_velocity_timer.timeout.connect(self._on_xy_velocity_timer)
        self._xy_velocity_direction: tuple[str, str, str] | None = None
        self.setWindowTitle("Guided Setup")
        self.setFixedSize(640, 520)
        app_font = QApplication.font() if QApplication.instance() else self.font()
        self._choice_font_point_size = max(app_font.pointSize() * 2, 16)
        self._build_ui()
        self.setStyleSheet(generate_theme_qss(THEMES["light"]) + _GUIDED_SETUP_QSS)
        self._update_tcp_panel()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(0)

        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(6)

        self._stack = QStackedWidget()
        self._stack.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self._stack.addWidget(self._build_prober_page())
        self._stack.addWidget(
            self._build_choice_page(
                "Device selection:",
                _DEVICE_BUTTONS,
                self._on_device_selected,
            )
        )
        self._stack.addWidget(
            self._build_choice_page(
                "Bolometer selection:",
                _BM_BUTTONS,
                self._on_bm_selected,
            )
        )
        self._stack.addWidget(
            self._build_choice_page(
                "IMU selection:",
                _IMU_BUTTONS,
                self._on_imu_selected,
            )
        )
        self._stack.addWidget(
            self._build_choice_page(
                "DUT Selection:",
                _DUT_BUTTONS,
                self._on_dut_selected,
            )
        )
        self._instrument_page = self._build_instrument_page()
        self._stack.addWidget(self._instrument_page)
        panel_layout.addWidget(self._stack, stretch=1)

        nav_row = QHBoxLayout()
        nav_row.setContentsMargins(0, 0, 0, 0)
        nav_row.setSpacing(0)
        self.btn_prev = QPushButton("取消")
        self.btn_prev.setMinimumSize(140, 44)
        self.btn_prev.clicked.connect(self._on_prev)
        self.btn_next = QPushButton("下一步")
        self.btn_next.setEnabled(False)
        self.btn_next.setMinimumSize(140, 44)
        self.btn_next.clicked.connect(self._on_next)
        nav_row.addWidget(self.btn_prev, alignment=Qt.AlignmentFlag.AlignLeft)
        nav_row.addStretch()
        nav_row.addWidget(self.btn_next, alignment=Qt.AlignmentFlag.AlignRight)
        panel_layout.addLayout(nav_row)
        self._update_prev_button()

        root.addWidget(panel)

    def _build_prober_page(self) -> QGroupBox:
        group = QGroupBox("Prober Selection:")
        group.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        layout = QGridLayout(group)
        layout.setContentsMargins(10, 14, 10, 10)
        layout.setSpacing(10)
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 1)
        layout.setRowStretch(0, 1)
        layout.setRowStretch(1, 1)
        layout.setRowStretch(2, 0)
        layout.setRowStretch(3, 0)

        button_group = QButtonGroup(group)
        button_group.setExclusive(True)

        for index, (label, prober_type) in enumerate(_PROBER_BUTTONS):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setProperty("setupChoice", "true")
            button.setMinimumHeight(56)
            button.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Expanding,
            )
            self._apply_choice_button_font(button, checked=False)
            button.toggled.connect(
                lambda checked, btn=button: self._apply_choice_button_font(btn, checked)
            )
            button.clicked.connect(
                lambda checked, pt=prober_type: self._on_prober_selected(pt)
                if checked
                else None
            )
            button_group.addButton(button)
            layout.addWidget(button, index // 2, index % 2)

        tcp_row = QHBoxLayout()
        tcp_row.addWidget(QLabel("Server IP:"))
        self.edit_server_ip = QLineEdit("127.0.0.1")
        self.edit_server_ip.setFixedWidth(130)
        tcp_row.addWidget(self.edit_server_ip)
        tcp_row.addWidget(QLabel("Port:"))
        self.edit_server_port = QLineEdit("5555")
        self.edit_server_port.setFixedWidth(60)
        tcp_row.addWidget(self.edit_server_port)
        self.btn_tcp_connect = QPushButton("Connect")
        self.btn_tcp_connect.clicked.connect(self._on_tcp_connect_clicked)
        tcp_row.addWidget(self.btn_tcp_connect)
        self.lbl_tcp_status = QLabel()
        self.lbl_tcp_status.setFixedWidth(120)
        self.lbl_tcp_status.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Preferred,
        )
        tcp_row.addWidget(self.lbl_tcp_status)
        tcp_row.addStretch()

        self._tcp_panel = QWidget()
        self._tcp_panel.setLayout(tcp_row)
        layout.addWidget(self._tcp_panel, 2, 0, 1, 2)

        test_row = QHBoxLayout()
        test_row.addWidget(QLabel("連線測試:"))
        self.btn_test_left = QPushButton("X←")
        self.btn_test_left.setMinimumWidth(72)
        self.btn_test_left.setEnabled(False)
        self.btn_test_left.pressed.connect(
            lambda: self._on_tcp_test_direction_pressed(-1, 0, "-", "0", "0")
        )
        self.btn_test_left.released.connect(self._on_tcp_test_direction_released)
        test_row.addWidget(self.btn_test_left)
        self.btn_test_right = QPushButton("X→")
        self.btn_test_right.setMinimumWidth(72)
        self.btn_test_right.setEnabled(False)
        self.btn_test_right.pressed.connect(
            lambda: self._on_tcp_test_direction_pressed(1, 0, "+", "0", "0")
        )
        self.btn_test_right.released.connect(self._on_tcp_test_direction_released)
        test_row.addWidget(self.btn_test_right)
        test_row.addStretch()

        self._tcp_test_panel = QWidget()
        self._tcp_test_panel.setLayout(test_row)
        layout.addWidget(self._tcp_test_panel, 3, 0, 1, 2)

        return group

    def _build_choice_page(
        self,
        title: str,
        options: tuple[tuple[str, ProberType | DeviceType | BmModelType | ImuSubType | DutType], ...],
        on_selected,
    ) -> QGroupBox:
        group = QGroupBox(title)
        group.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        layout = QGridLayout(group)
        layout.setContentsMargins(10, 14, 10, 10)
        layout.setSpacing(10)
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 1)
        layout.setRowStretch(0, 1)
        layout.setRowStretch(1, 1)

        button_group = QButtonGroup(group)
        button_group.setExclusive(True)

        for index, (label, value) in enumerate(options):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setProperty("setupChoice", "true")
            button.setMinimumHeight(56)
            button.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Expanding,
            )
            self._apply_choice_button_font(button, checked=False)
            button.toggled.connect(
                lambda checked, btn=button: self._apply_choice_button_font(btn, checked)
            )
            button.clicked.connect(
                lambda checked, selected=value: on_selected(selected) if checked else None
            )
            button_group.addButton(button)
            layout.addWidget(button, index // 2, index % 2)

        return group

    def _build_instrument_page(self) -> QGroupBox:
        group = QGroupBox("Instrument selection:")
        group.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        layout = QGridLayout(group)
        layout.setContentsMargins(10, 14, 10, 10)
        layout.setSpacing(10)
        return group

    def _configure_instrument_page(
        self,
        title: str,
        options: tuple[tuple[str, InstrumentType], ...],
        back_index: int,
    ) -> None:
        assert self._instrument_page is not None
        self._instrument_back_index = back_index
        self._selected_instrument = None
        self._instrument_page.setTitle(title)

        layout = self._instrument_page.layout()
        if layout is None:
            layout = QGridLayout(self._instrument_page)
        else:
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()

        layout.setContentsMargins(10, 14, 10, 10)
        layout.setSpacing(10)
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 1)
        layout.setRowStretch(0, 1)
        layout.setRowStretch(1, 1)

        button_group = QButtonGroup(self._instrument_page)
        button_group.setExclusive(True)

        for index, (label, instrument_type) in enumerate(options):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setProperty("setupChoice", "true")
            button.setMinimumHeight(56)
            button.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Expanding,
            )
            self._apply_choice_button_font(button, checked=False)
            button.toggled.connect(
                lambda checked, btn=button: self._apply_choice_button_font(btn, checked)
            )
            button.clicked.connect(
                lambda checked, selected=instrument_type: self._on_instrument_selected(
                    selected
                )
                if checked
                else None
            )
            button_group.addButton(button)
            layout.addWidget(button, index // 2, index % 2)

    def _show_instrument_page(
        self,
        options: tuple[tuple[str, InstrumentType], ...],
        back_index: int,
    ) -> None:
        title_parts = [self._selected_device.value]
        if self._selected_device == DeviceType.BOLOMETER:
            title_parts.extend((self._selected_bm.value, self._selected_dut.value))
        elif self._selected_device == DeviceType.IMU:
            title_parts.append(self._selected_imu_subtype.value)
        title = f"{'_'.join(title_parts)}_Instrument Selection"
        self._configure_instrument_page(title, options, back_index)
        self._stack.setCurrentIndex(_INSTRUMENT_PAGE_INDEX)
        self.btn_next.setText("完成")
        self.btn_next.setEnabled(False)
        self._update_prev_button()

    def _apply_choice_button_font(self, button: QPushButton, checked: bool) -> None:
        font = QFont(button.font())
        font.setPointSize(self._choice_font_point_size)
        font.setBold(checked)
        button.setFont(font)

    def _requires_tcp_prober(self, prober_type: ProberType | None) -> bool:
        return prober_type in _TCP_PROBER_TYPES

    def _can_proceed_step0(self) -> bool:
        if self._selected_prober is None:
            return False
        if self._requires_tcp_prober(self._selected_prober):
            return self._tcp_client.is_connected
        return True

    def _update_prev_button(self) -> None:
        if self._stack.currentIndex() == 0:
            self.btn_prev.setText("取消")
        else:
            self.btn_prev.setText("上一步")

    def _update_step0_next_button(self) -> None:
        if self._stack.currentIndex() == 0:
            if self._selected_prober == ProberType.SIMULATION:
                self.btn_next.setText("完成")
            else:
                self.btn_next.setText("下一步")
            self.btn_next.setEnabled(self._can_proceed_step0())

    def _update_device_type_nav(self) -> None:
        if self._stack.currentIndex() != 1:
            return
        self.btn_next.setText("下一步")
        self.btn_next.setEnabled(self._selected_device is not None)

    def _refresh_tcp_status_label(self) -> None:
        if not self._requires_tcp_prober(self._selected_prober):
            self.lbl_tcp_status.setText("")
            return
        if self._tcp_client.is_connected:
            self.lbl_tcp_status.setText("TCP 已連接")
        elif self._tcp_connecting:
            self.lbl_tcp_status.setText("TCP 連接中...")
        elif self._tcp_connect_error_code is not None:
            self.lbl_tcp_status.setText(f"連線失敗 ({self._tcp_connect_error_code})")
        elif self._tcp_last_error:
            self.lbl_tcp_status.setText(self._tcp_last_error)
        else:
            self.lbl_tcp_status.setText("請連接 Prober Server")

    def _update_tcp_panel(self) -> None:
        tcp_required = self._requires_tcp_prober(self._selected_prober)

        if self._tcp_client.is_connected:
            self.btn_tcp_connect.setText("Disconnect")
        else:
            self.btn_tcp_connect.setText("Connect")

        inputs_enabled = (
            tcp_required
            and not self._tcp_client.is_connected
            and not self._tcp_connecting
        )
        self.edit_server_ip.setEnabled(inputs_enabled)
        self.edit_server_port.setEnabled(inputs_enabled)
        self.btn_tcp_connect.setEnabled(
            tcp_required
            and (self._tcp_client.is_connected or not self._tcp_connecting)
        )
        self._refresh_tcp_status_label()
        self._update_tcp_test_buttons()

    def _disconnect_tcp(self) -> None:
        self._stop_xy_velocity_move()
        if self._tcp_client.is_connected:
            self._tcp_client.disconnect()
        self._tcp_connecting = False

    def _ensure_chuck_motor(self) -> None:
        if self._selected_prober is None:
            self._chuck_motor = None
            return
        self._chuck_motor = create_chuck_motor(self._selected_prober)
        self._attach_tcp_client_to_motor()

    def _attach_tcp_client_to_motor(self) -> None:
        if self._chuck_motor is None:
            return
        if isinstance(self._chuck_motor, (MpiTp80ChuckMotor, SussChuckMotor)):
            self._chuck_motor.set_tcp_client(self._tcp_client)

    def _is_suss_velocity_test_mode(self) -> bool:
        return self._selected_prober == ProberType.SUSS

    def _on_tcp_test_direction_pressed(
        self,
        num_x_index: int,
        num_y_index: int,
        vx: str,
        vy: str,
        vz: str,
    ) -> None:
        if self._chuck_motor is None:
            return
        if self._is_suss_velocity_test_mode():
            self._start_xy_velocity_move(vx, vy, vz)
        else:
            self._run_motor_action(
                lambda: self._chuck_motor.move_chuck_index_relative(
                    num_x_index, num_y_index
                )
            )

    def _on_tcp_test_direction_released(self) -> None:
        if self._is_suss_velocity_test_mode():
            self._stop_xy_velocity_move()

    def _start_xy_velocity_move(self, vx: str, vy: str, vz: str) -> None:
        self._xy_velocity_direction = (vx, vy, vz)
        self._send_xy_velocity_command()
        if not self._xy_velocity_timer.isActive():
            self._xy_velocity_timer.start()

    def _stop_xy_velocity_move(self) -> None:
        was_moving = self._xy_velocity_direction is not None
        self._xy_velocity_timer.stop()
        self._xy_velocity_direction = None
        if not was_moving or self._chuck_motor is None:
            return
        try:
            self._chuck_motor.stop_chuck_movement()
        except Exception as exc:
            QMessageBox.critical(self, "馬達控制錯誤", str(exc))

    def _on_xy_velocity_timer(self) -> None:
        self._send_xy_velocity_command()

    def _send_xy_velocity_command(self) -> None:
        if self._xy_velocity_direction is None or self._chuck_motor is None:
            return
        vx, vy, vz = self._xy_velocity_direction
        try:
            self._chuck_motor.move_chuck_velocity(
                vx, vy, vz, float(_TCP_TEST_VELOCITY_SPEED)
            )
        except Exception as exc:
            self._xy_velocity_timer.stop()
            self._xy_velocity_direction = None
            QMessageBox.critical(self, "馬達控制錯誤", str(exc))

    def _run_motor_action(self, action) -> None:
        try:
            action()
        except Exception as exc:
            QMessageBox.critical(self, "馬達控制錯誤", str(exc))

    def _update_tcp_test_buttons(self) -> None:
        tcp_required = self._requires_tcp_prober(self._selected_prober)
        enabled = (
            tcp_required
            and self._tcp_client.is_connected
            and self._chuck_motor is not None
        )
        # Keep this row in the layout for every prober type.  In simulation
        # mode the disabled panel (and its child widgets) uses the theme's
        # disabled/grey styling, rather than disappearing and shifting layout.
        self._tcp_test_panel.setVisible(True)
        self._tcp_test_panel.setEnabled(tcp_required)
        self.btn_test_left.setEnabled(enabled)
        self.btn_test_right.setEnabled(enabled)

    def _load_tcp_fields_for_prober(self, prober_type: ProberType) -> None:
        if not self._requires_tcp_prober(prober_type):
            return
        endpoint = self._tcp_settings.get_endpoint(prober_type)
        if endpoint is None:
            endpoint = self._tcp_settings.default_endpoint()
        self.edit_server_ip.setText(endpoint.ip)
        self.edit_server_port.setText(str(endpoint.port))

    def _save_tcp_fields_for_prober(self) -> None:
        if self._selected_prober is None or not self._requires_tcp_prober(
            self._selected_prober
        ):
            return
        port = self._parse_server_port()
        if port is None:
            return
        ip = self.edit_server_ip.text().strip()
        if not ip:
            return
        self._tcp_settings.save_endpoint(self._selected_prober, ip, port)

    def _parse_server_port(self) -> int | None:
        port_text = self.edit_server_port.text().strip()
        if not port_text:
            self._tcp_last_error = "請輸入 Port"
            self._refresh_tcp_status_label()
            return None
        try:
            port = int(port_text)
        except ValueError:
            self._tcp_last_error = "Port 必須為整數"
            self._refresh_tcp_status_label()
            return None
        if not 1 <= port <= 65535:
            self._tcp_last_error = "Port 必須介於 1–65535"
            self._refresh_tcp_status_label()
            return None
        return port

    def _on_tcp_connect_clicked(self) -> None:
        if self._tcp_client.is_connected:
            self._disconnect_tcp()
            self._tcp_last_error = None
            self._tcp_connect_error_code = None
            self._update_tcp_panel()
            self._update_step0_next_button()
            return

        ip = self.edit_server_ip.text().strip()
        if not ip:
            self._tcp_last_error = "請輸入 Server IP 位址"
            self._refresh_tcp_status_label()
            return

        port = self._parse_server_port()
        if port is None:
            return

        self._tcp_last_error = None
        self._tcp_connect_error_code = None
        self._tcp_connecting = True
        self._update_tcp_panel()
        self.btn_next.setEnabled(False)

        def connect_worker() -> None:
            try:
                self._tcp_client.connect(ip, port)
            except (OSError, TimeoutError) as exc:
                self._tcp_connect_bridge.finished.emit(False, _connect_error_code(exc))
            else:
                self._tcp_connect_bridge.finished.emit(True, "")

        threading.Thread(target=connect_worker, daemon=True).start()

    def _on_tcp_connect_finished(self, success: bool, error_code: str) -> None:
        self._tcp_connecting = False
        if success:
            self._tcp_last_error = None
            self._tcp_connect_error_code = None
            self._attach_tcp_client_to_motor()
            self._save_tcp_fields_for_prober()
        else:
            self._tcp_connect_error_code = error_code or "unknown"
            self._tcp_last_error = None
        self._update_tcp_panel()
        self._update_step0_next_button()

    def _on_prober_selected(self, prober_type: ProberType) -> None:
        if (
            self._selected_prober is not None
            and self._selected_prober != prober_type
        ):
            self._disconnect_tcp()
            self._tcp_last_error = None
            self._tcp_connect_error_code = None
        self._selected_prober = prober_type
        self._ensure_chuck_motor()
        self._load_tcp_fields_for_prober(prober_type)
        self._update_tcp_panel()
        self._update_step0_next_button()

    def _on_device_selected(self, device_type: DeviceType) -> None:
        self._selected_device = device_type
        self._update_device_type_nav()

    def _on_bm_selected(self, bm_model: BmModelType) -> None:
        self._selected_bm = bm_model
        if self._stack.currentIndex() == 2:
            self.btn_next.setEnabled(True)

    def _on_imu_selected(self, imu_subtype: ImuSubType) -> None:
        self._selected_imu_subtype = imu_subtype
        if self._stack.currentIndex() == 3:
            self.btn_next.setEnabled(True)

    def _on_dut_selected(self, dut_type: DutType) -> None:
        self._selected_dut = dut_type
        if self._stack.currentIndex() == _DUT_PAGE_INDEX:
            self.btn_next.setEnabled(True)

    def _on_instrument_selected(self, instrument_type: InstrumentType) -> None:
        self._selected_instrument = instrument_type
        if self._stack.currentIndex() == _INSTRUMENT_PAGE_INDEX:
            self.btn_next.setEnabled(True)

    def _finish_setup(self) -> None:
        if self._selected_prober is None:
            return
        if (
            self._selected_prober != ProberType.SIMULATION
            and self._selected_device is None
        ):
            return

        self._completed = True
        device_type = (
            self._selected_device
            if self._selected_device is not None
            else DeviceType.OTHERS
        )
        instrument_type = self._selected_instrument
        if self._selected_prober == ProberType.SIMULATION:
            instrument_type = InstrumentType.VIRTUAL_LCR
        tcp_client = (
            self._tcp_client
            if self._requires_tcp_prober(self._selected_prober)
            else None
        )
        self.finished.emit(
            GuidedSetupResult(
                prober_type=self._selected_prober,
                device_type=device_type,
                bm_model=self._selected_bm,
                imu_subtype=self._selected_imu_subtype,
                dut_type=self._selected_dut,
                instrument_type=instrument_type,
                tcp_client=tcp_client,
            )
        )
        self.close()

    def _on_prev(self) -> None:
        current = self._stack.currentIndex()
        if current == 0:
            self.close()
            return
        if current == _INSTRUMENT_PAGE_INDEX:
            self._stack.setCurrentIndex(self._instrument_back_index)
            if self._instrument_back_index == 1:
                self._update_device_type_nav()
            elif self._instrument_back_index == 2:
                self.btn_next.setText("下一步")
                self.btn_next.setEnabled(self._selected_bm is not None)
            elif self._instrument_back_index == 3:
                self.btn_next.setText("下一步")
                self.btn_next.setEnabled(self._selected_imu_subtype is not None)
            elif self._instrument_back_index == _DUT_PAGE_INDEX:
                self.btn_next.setText("下一步")
                self.btn_next.setEnabled(self._selected_dut is not None)
            self._update_prev_button()
            return
        if current == _DUT_PAGE_INDEX:
            self._stack.setCurrentIndex(2)
            self.btn_next.setText("下一步")
            self.btn_next.setEnabled(self._selected_bm is not None)
            self._update_prev_button()
            return
        if current in (2, 3):
            self._stack.setCurrentIndex(1)
            self._update_device_type_nav()
            self._update_prev_button()
            return
        self._stack.setCurrentIndex(0)
        self._update_step0_next_button()
        self._update_prev_button()

    def _on_next(self) -> None:
        current = self._stack.currentIndex()
        if current == 0:
            if not self._can_proceed_step0():
                return
            if self._selected_prober == ProberType.SIMULATION:
                self._finish_setup()
                return
            self._stack.setCurrentIndex(1)
            self._update_device_type_nav()
            self._update_prev_button()
            return

        if current == 1:
            if self._selected_device is None:
                return
            if self._selected_device == DeviceType.BOLOMETER:
                self._stack.setCurrentIndex(2)
                self.btn_next.setText("下一步")
                self.btn_next.setEnabled(self._selected_bm is not None)
                self._update_prev_button()
                return
            if self._selected_device == DeviceType.IMU:
                self._stack.setCurrentIndex(3)
                self.btn_next.setText("下一步")
                self.btn_next.setEnabled(self._selected_imu_subtype is not None)
                self._update_prev_button()
                return
            if self._selected_device == DeviceType.GYRO:
                self._show_instrument_page(
                    _TRADITIONAL_INSTRUMENT_BUTTONS,
                    back_index=1,
                )
                return
            if self._selected_device == DeviceType.OTHERS:
                self._show_instrument_page(
                    _OTHERS_INSTRUMENT_BUTTONS,
                    back_index=1,
                )
            return

        if current == 2:
            if self._selected_bm is None:
                return
            self._stack.setCurrentIndex(_DUT_PAGE_INDEX)
            self.btn_next.setText("下一步")
            self.btn_next.setEnabled(self._selected_dut is not None)
            self._update_prev_button()
            return

        if current == 3:
            if self._selected_imu_subtype is None:
                return
            if self._selected_imu_subtype == ImuSubType.COMPONENT:
                self._show_instrument_page(
                    _TRADITIONAL_INSTRUMENT_BUTTONS,
                    back_index=3,
                )
                return
            self._show_instrument_page(
                _ASIC_INSTRUMENT_BUTTONS,
                back_index=3,
            )
            return

        if current == _DUT_PAGE_INDEX:
            if self._selected_dut is None:
                return
            self._show_instrument_page(
                _BOLOMETER_INSTRUMENT_BUTTONS,
                back_index=_DUT_PAGE_INDEX,
            )
            return

        if current == _INSTRUMENT_PAGE_INDEX:
            if self._selected_instrument is None:
                return
            self._finish_setup()

    def closeEvent(self, event) -> None:
        self._stop_xy_velocity_move()
        if not self._completed:
            self._disconnect_tcp()
            app = QApplication.instance()
            if app is not None:
                app.quit()
        super().closeEvent(event)
