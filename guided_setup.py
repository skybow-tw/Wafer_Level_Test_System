"""Step-by-step guided setup wizard shown before the main application."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal, QSize, QRectF
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
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
    QToolButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from bolometer_asic_tcp_settings import BolometerAsicTcpSettingsStore, ROIC_CLOCK_OPTIONS
from instruments.bmt_tcp import BmtTcpClient
from instruments.panels.widgets.ni_device_combo import NiDeviceComboBox
from instruments.pxi4461 import list_roic_daq_devices
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
    FUNCTION_TEST_SPI_DAC = "Function Test(SPI、DAC)"


@dataclass(frozen=True)
class GuidedSetupResult:
    prober_type: ProberType
    device_type: DeviceType
    bm_model: BmModelType | None = None
    imu_subtype: ImuSubType | None = None
    dut_type: DutType | None = None
    instrument_type: InstrumentType | None = None
    tcp_client: ProberTcpClient | None = None
    asic_tcp_client: BmtTcpClient | None = None


_PROBER_BUTTONS: tuple[tuple[str, ProberType], ...] = (
    ("MPI-TP80", ProberType.MPI_TP80),
    ("SUSS", ProberType.SUSS),
    ("MPI-TS2000", ProberType.MPI_TS2000),
    ("Simulation", ProberType.SIMULATION),
)

_DEVICE_BUTTONS: tuple[tuple[str, DeviceType], ...] = (
    ("IMU", DeviceType.IMU),
    ("Bolometer", DeviceType.BOLOMETER),
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
_BOLOMETER_ASIC_PAGE_INDEX = 6

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
QAbstractButton[illustratedChoice="true"] {
    background-color: #FFFFFF;
    border: 2px solid #D7E3EE;
    border-radius: 12px;
    padding: 12px;
}
QAbstractButton[illustratedChoice="true"]:hover {
    background-color: #F0F7FD;
    border-color: #69A8DA;
}
QAbstractButton[illustratedChoice="true"]:checked {
    background-color: #0078D4;
    color: #FFFFFF;
    border-color: #0078D4;
}
QAbstractButton[illustratedChoice="true"]:checked:hover {
    background-color: #106EBE;
    border-color: #106EBE;
}
"""


def _prober_icon(pixmap: QPixmap) -> QIcon:
    """Keep hover from recoloring the icon; checked color is drawn separately."""
    icon = QIcon()
    for mode in (QIcon.Mode.Normal, QIcon.Mode.Active, QIcon.Mode.Selected):
        for state in (QIcon.State.Off, QIcon.State.On):
            icon.addPixmap(pixmap, mode, state)
    return icon


def _tp80_icon(selected: bool = False) -> QIcon:
    """Draw the TP80 enclosure, probe assembly, and control panel."""
    pixmap = QPixmap(96, 96)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = QColor("#FFFFFF" if selected else "#1676B8")
    painter.setPen(QPen(color, 2, Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.MiterJoin))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(7, 6, 82, 84, 6, 6)
    painter.drawRect(15, 15, 66, 51)
    painter.drawLine(7, 73, 89, 73)
    painter.drawRoundedRect(43, 23, 10, 22, 3, 3)
    painter.drawRect(22, 43, 13, 9)
    painter.drawRect(61, 43, 13, 9)
    painter.drawLine(35, 47, 40, 47)
    painter.drawLine(56, 47, 61, 47)
    painter.drawLine(40, 47, 45, 54)
    painter.drawLine(56, 47, 51, 54)
    painter.drawRect(36, 57, 24, 4)
    painter.drawRect(17, 79, 25, 5)
    painter.drawEllipse(72, 78, 7, 7)
    painter.end()
    return _prober_icon(pixmap)


def _meter_icon(instrument: InstrumentType, selected: bool = False) -> QIcon:
    """Draw the E4980A or DSA front panel from the reference photos."""
    pixmap = QPixmap(96, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor("#FFFFFF" if selected else "#1676B8"), 2))
    painter.setBrush(Qt.BrushStyle.NoBrush)

    if instrument == InstrumentType.DSA:
        painter.drawRoundedRect(4, 8, 88, 48, 3, 3)
        painter.drawRect(10, 14, 46, 35)
        trace = ((15, 43), (24, 42), (29, 36), (34, 20),
                 (39, 36), (44, 42), (51, 43))
        for (x1, y1), (x2, y2) in zip(trace, trace[1:]):
            painter.drawLine(x1, y1, x2, y2)
        painter.drawEllipse(62, 17, 9, 9)
        for x in (77, 83):
            for y in (19, 26, 33):
                painter.drawLine(x, y, x + 3, y)
        for x in (63, 80):
            painter.drawEllipse(x, 44, 5, 5)
    else:
        painter.drawRoundedRect(4, 17, 88, 30, 5, 5)
        painter.drawRect(11, 23, 28, 18)
        painter.drawLine(16, 29, 32, 29)
        painter.drawLine(16, 35, 28, 35)
        for x in (45, 51, 57):
            for y in (25, 31):
                painter.drawLine(x, y, x + 2, y)
        for x in (64, 71, 78, 85):
            painter.drawEllipse(x, 35, 4, 4)

    painter.end()
    return _prober_icon(pixmap)


def _simulation_icon(selected: bool = False) -> QIcon:
    """Draw a monitor displaying a simulated signal."""
    pixmap = QPixmap(96, 96)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor("#FFFFFF" if selected else "#1676B8"), 3))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(12, 19, 72, 48, 5, 5)
    painter.drawLine(48, 67, 48, 77)
    painter.drawLine(34, 77, 62, 77)
    points = ((23, 44), (34, 44), (42, 33), (53, 54), (61, 44), (73, 44))
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        painter.drawLine(x1, y1, x2, y2)
    painter.end()
    return _prober_icon(pixmap)


def _ts2000_icon(selected: bool = False) -> QIcon:
    """Draw the TS2000 probe column, monitor, and cabinet."""
    pixmap = QPixmap(96, 96)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor("#FFFFFF" if selected else "#1676B8"), 2))
    painter.setBrush(Qt.BrushStyle.NoBrush)

    painter.drawRoundedRect(28, 7, 9, 34, 2, 2)
    painter.drawLine(32, 41, 32, 45)
    painter.drawEllipse(20, 44, 24, 7)
    painter.drawLine(15, 34, 28, 34)
    painter.drawLine(15, 34, 15, 46)
    painter.drawLine(37, 34, 49, 34)
    painter.drawLine(49, 34, 49, 46)

    painter.drawRoundedRect(55, 13, 33, 21, 2, 2)
    painter.drawEllipse(66, 18, 11, 11)
    painter.drawLine(72, 34, 72, 45)
    painter.drawLine(65, 45, 79, 45)

    painter.drawRoundedRect(7, 53, 82, 34, 3, 3)
    painter.drawLine(7, 64, 89, 64)
    painter.drawLine(57, 53, 57, 87)
    painter.drawRect(14, 56, 35, 5)
    painter.drawEllipse(74, 69, 6, 6)
    painter.drawLine(15, 87, 15, 91)
    painter.drawLine(81, 87, 81, 91)
    painter.end()
    return _prober_icon(pixmap)


def _suss_icon(selected: bool = False) -> QIcon:
    """Draw the PA200 microscope, probe stage, and front guard."""
    pixmap = QPixmap(96, 96)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = QColor("#FFFFFF" if selected else "#1676B8")
    painter.setPen(QPen(color, 2, Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.MiterJoin))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    # Vertical camera and objective with the angled support behind them.
    painter.drawRect(43, 7, 12, 10)
    painter.drawRect(45, 17, 8, 25)
    painter.drawRoundedRect(43, 42, 12, 12, 2, 2)
    painter.drawLine(45, 48, 53, 48)
    painter.drawLine(45, 25, 38, 25)
    painter.drawLine(38, 25, 29, 38)
    painter.drawLine(29, 38, 29, 44)
    painter.drawEllipse(56, 24, 6, 6)

    # Opposing probe arms aimed at the round wafer stage.
    painter.drawRect(14, 46, 15, 8)
    painter.drawRect(67, 46, 15, 8)
    painter.drawLine(29, 50, 38, 56)
    painter.drawLine(67, 50, 58, 56)
    painter.drawEllipse(31, 56, 34, 8)

    # Wide cabinet, front guard, and handle.
    painter.drawRoundedRect(6, 64, 84, 24, 4, 4)
    painter.drawRect(30, 67, 36, 12)
    painter.drawRoundedRect(40, 81, 16, 4, 2, 2)
    painter.drawEllipse(75, 73, 6, 6)
    painter.end()
    return _prober_icon(pixmap)


def _device_icon(device: DeviceType, selected: bool = False) -> QIcon:
    """Draw compact, resolution-independent pictograms for the device cards."""
    pixmap = QPixmap(72, 72)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor("#FFFFFF" if selected else "#1676B8"), 4,
                        Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                        Qt.PenJoinStyle.RoundJoin))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    if device == DeviceType.IMU:
        painter.setPen(QPen(QColor("#FFFFFF" if selected else "#1676B8"), 3,
                            Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                            Qt.PenJoinStyle.RoundJoin))
        # Three motion axes with rotation rings, matching the IMU reference.
        painter.drawLine(36, 43, 36, 5)
        painter.drawLine(26, 15, 36, 5)
        painter.drawLine(36, 5, 46, 15)
        painter.drawEllipse(QRectF(24, 23, 24, 10))
        painter.drawLine(36, 43, 7, 65)
        painter.drawLine(7, 65, 9, 51)
        painter.drawLine(7, 65, 21, 62)
        painter.drawLine(36, 43, 65, 65)
        painter.drawLine(65, 65, 63, 51)
        painter.drawLine(65, 65, 51, 62)
        for x, angle in ((22, -32), (50, 32)):
            painter.save()
            painter.translate(x, 51)
            painter.rotate(angle)
            painter.drawEllipse(QRectF(-5, -11, 10, 22))
            painter.restore()
    elif device == DeviceType.BOLOMETER:
        color = QColor("#FFFFFF" if selected else "#1676B8")
        painter.setPen(QPen(color, 3))
        painter.drawRect(8, 8, 56, 56)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        for row in range(3):
            for column in range(3):
                painter.drawRect(17 + column * 14, 17 + row * 14, 10, 10)
    else:
        for x, y in ((15, 15), (41, 15), (15, 41), (41, 41)):
            painter.drawRoundedRect(x, y, 16, 16, 4, 4)
    painter.end()
    return QIcon(pixmap)


def _bolometer_icon(model: BmModelType, selected: bool = False) -> QIcon:
    """Draw the framed sensor grid for the selected model."""
    rows, columns = {
        BmModelType.BM28: (2, 8),
        BmModelType.BM1602: (3, 4),
        BmModelType.BM6402: (12, 16),
        BmModelType.BM12801: (24, 32),
    }[model]
    square, pitch = 5, 7
    width = 30 + max(rows, columns) * pitch
    height = 30 + rows * pitch
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = QColor("#FFFFFF" if selected else "#1676B8")
    painter.setPen(QPen(color, 3))
    painter.drawRect(8, 8, width - 16, height - 16)
    left = (width - ((columns - 1) * pitch + square)) // 2
    top = (height - ((rows - 1) * pitch + square)) // 2
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    for row in range(rows):
        for column in range(columns):
            painter.drawRect(left + column * pitch, top + row * pitch, square, square)
    painter.end()
    return QIcon(pixmap)


def _dut_icon(dut: DutType, selected: bool = False) -> QIcon:
    pixmap = QPixmap(72, 72)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = QColor("#FFFFFF" if selected else "#1676B8")
    painter.setPen(QPen(color, 3, Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    if dut == DutType.ELEMENT:
        painter.drawRoundedRect(12, 25, 48, 30, 3, 3)
        painter.drawLine(18, 32, 27, 32)
        painter.drawLine(45, 32, 54, 32)
        painter.drawEllipse(29, 28, 14, 14)
        painter.drawLine(36, 42, 36, 48)
        painter.drawLine(19, 18, 53, 18)
        painter.drawLine(23, 18, 23, 25)
        painter.drawLine(49, 18, 49, 25)
    else:
        painter.drawRoundedRect(17, 17, 38, 38, 4, 4)
        painter.drawRoundedRect(26, 26, 20, 20, 2, 2)
        for point in (26, 36, 46):
            painter.drawLine(point, 10, point, 17)
            painter.drawLine(point, 55, point, 62)
            painter.drawLine(10, point, 17, point)
            painter.drawLine(55, point, 62, point)
    painter.end()
    return QIcon(pixmap)


def _function_test_icon(selected: bool = False) -> QIcon:
    """Draw the Function Test square wave."""
    pixmap = QPixmap(72, 72)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = QColor("#FFFFFF" if selected else "#1676B8")
    painter.setPen(QPen(color, 4, Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    painter.drawLine(7, 51, 16, 51)
    painter.drawLine(16, 51, 16, 22)
    painter.drawLine(16, 22, 32, 22)
    painter.drawLine(32, 22, 32, 51)
    painter.drawLine(32, 51, 48, 51)
    painter.drawLine(48, 51, 48, 22)
    painter.drawLine(48, 22, 64, 22)
    painter.end()
    return QIcon(pixmap)


class _TcpConnectBridge(QObject):
    finished = Signal(bool, str)


class _RoicClockBridge(QObject):
    finished = Signal(str, str)


class GuidedSetupWindow(QMainWindow):
    """Multi-step wizard: prober, device type, then path-specific selection."""

    finished = Signal(GuidedSetupResult)

    def __init__(self, work_dir: Path | None = None) -> None:
        super().__init__()
        self._work_dir = work_dir or Path.cwd()
        self._tcp_settings = ProberTcpSettingsStore(self._work_dir)
        self._asic_tcp_settings = BolometerAsicTcpSettingsStore(self._work_dir)
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
        self._asic_tcp_client = BmtTcpClient()
        self._asic_generating_clock = False
        self._asic_clock_bridge = _RoicClockBridge(self)
        self._asic_clock_bridge.finished.connect(self._on_asic_clock_finished)
        self._asic_connecting = False
        self._asic_connect_bridge = _TcpConnectBridge()
        self._asic_connect_bridge.finished.connect(self._on_asic_tcp_connect_finished)
        self._asic_connection_timer = QTimer(self)
        self._asic_connection_timer.setInterval(200)
        self._asic_connection_timer.timeout.connect(self._check_asic_tcp_connection)
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
        self._stack.currentChanged.connect(self._resize_for_setup_page)
        self.setStyleSheet(generate_theme_qss(THEMES["light"]) + _GUIDED_SETUP_QSS)
        self._update_tcp_panel()
        self._update_asic_tcp_panel()

    def _resize_for_setup_page(self, index: int) -> None:
        # The BM12801 grid needs room for its full icon and label.
        if index == 2:
            self.setFixedSize(640, 600)
        else:
            self.setFixedSize(640, 520)

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
        self._stack.addWidget(self._build_bolometer_asic_page())
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
            icon_factory = {
                ProberType.MPI_TP80: _tp80_icon,
                ProberType.SUSS: _suss_icon,
                ProberType.MPI_TS2000: _ts2000_icon,
                ProberType.SIMULATION: _simulation_icon,
            }.get(prober_type)
            if icon_factory is not None:
                button.setProperty("illustratedChoice", "true")
                button.setIcon(icon_factory())
                button.setIconSize(QSize(96, 96))
                button.toggled.connect(
                    lambda checked, btn=button, factory=icon_factory: btn.setIcon(
                        factory(checked)
                    )
                )
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
        self.btn_test_z_up = QPushButton("Z↑ 1mm")
        self.btn_test_z_down = QPushButton("Z↓ 1mm")
        self.btn_test_z_up.clicked.connect(lambda: self._run_tp80_z_test(1.0))
        self.btn_test_z_down.clicked.connect(lambda: self._run_tp80_z_test(-1.0))
        test_row.addWidget(self.btn_test_z_up)
        test_row.addWidget(self.btn_test_z_down)
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
            if isinstance(value, BmModelType):
                button = QToolButton()
                button.setText(label)
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            else:
                button = QPushButton(label)
            button.setCheckable(True)
            button.setProperty("setupChoice", "true")
            if isinstance(value, DeviceType) or value == DutType.ELEMENT:
                device = value if isinstance(value, DeviceType) else DeviceType.BOLOMETER
                button.setProperty("illustratedChoice", "true")
                button.setIcon(_device_icon(device))
                button.setIconSize(QSize(64, 64))
                button.toggled.connect(
                    lambda checked, btn=button, device=device: btn.setIcon(
                        _device_icon(device, checked)
                    )
                )
            elif isinstance(value, BmModelType):
                button.setProperty("illustratedChoice", "true")
                button.setIcon(_bolometer_icon(value))
                icon_size = button.icon().availableSizes()[0]
                button.setIconSize(icon_size * (64 / 72))
                button.toggled.connect(
                    lambda checked, btn=button, model=value: btn.setIcon(
                        _bolometer_icon(model, checked)
                    )
                )
            elif isinstance(value, (DutType, ImuSubType)):
                dut = (
                    DutType.ELEMENT
                    if value == ImuSubType.COMPONENT
                    else DutType.ASIC
                )
                button.setProperty("illustratedChoice", "true")
                button.setIcon(_dut_icon(dut))
                button.setIconSize(QSize(64, 64))
                button.toggled.connect(
                    lambda checked, btn=button, dut=dut: btn.setIcon(
                        _dut_icon(dut, checked)
                    )
                )
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

    def _build_bolometer_asic_page(self) -> QGroupBox:
        group = QGroupBox()
        layout = QVBoxLayout(group)
        layout.setContentsMargins(10, 14, 10, 10)
        layout.setSpacing(10)
        choice_grid = QGridLayout()
        choice_grid.setSpacing(10)
        choice_grid.setColumnStretch(0, 1)
        choice_grid.setColumnStretch(1, 1)
        choice_grid.setRowStretch(0, 1)
        choice_grid.setRowStretch(1, 1)

        self.btn_function_test = QPushButton("RPI5 Tester")
        self.btn_function_test.setCheckable(True)
        self.btn_function_test.setProperty("setupChoice", "true")
        self.btn_function_test.setProperty("illustratedChoice", "true")
        self.btn_function_test.setIcon(_function_test_icon())
        self.btn_function_test.setIconSize(QSize(68, 68))
        self.btn_function_test.toggled.connect(
            lambda checked: self.btn_function_test.setIcon(
                _function_test_icon(checked)
            )
        )
        self.btn_function_test.setMinimumHeight(56)
        self.btn_function_test.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._apply_choice_button_font(self.btn_function_test, checked=False)
        self.btn_function_test.toggled.connect(
            lambda checked: self._apply_choice_button_font(
                self.btn_function_test, checked
            )
        )
        self.btn_function_test.clicked.connect(self._on_asic_instrument_selected)
        choice_grid.addWidget(self.btn_function_test, 0, 0)
        arm_tester = QPushButton("ARM Tester")
        arm_tester.setMinimumHeight(56)
        arm_tester.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._apply_choice_button_font(arm_tester, checked=False)
        arm_tester.setEnabled(False)
        arm_tester.setToolTip("ARM Tester is not available yet.")
        choice_grid.addWidget(arm_tester, 0, 1)
        layout.addLayout(choice_grid, stretch=1)

        tcp_row = QHBoxLayout()
        server_label = QLabel("Server IP:")
        server_label.setStyleSheet("background-color: transparent;")
        tcp_row.addWidget(server_label)
        endpoint = self._asic_tcp_settings.get_endpoint()
        self.edit_asic_server_ip = QLineEdit(endpoint.ip)
        self.edit_asic_server_ip.setFixedWidth(130)
        tcp_row.addWidget(self.edit_asic_server_ip)
        port_label = QLabel("Port:")
        port_label.setStyleSheet("background-color: transparent;")
        tcp_row.addWidget(port_label)
        self.edit_asic_server_port = QLineEdit(str(endpoint.port))
        self.edit_asic_server_port.setFixedWidth(60)
        tcp_row.addWidget(self.edit_asic_server_port)
        self.btn_asic_tcp_connect = QPushButton("Connect")
        self.btn_asic_tcp_connect.clicked.connect(self._on_asic_tcp_connect_clicked)
        tcp_row.addWidget(self.btn_asic_tcp_connect)
        self.lbl_asic_tcp_status = QLabel("請連接 Server")
        self.lbl_asic_tcp_status.setStyleSheet("background-color: transparent;")
        self.lbl_asic_tcp_status.setFixedWidth(120)
        tcp_row.addWidget(self.lbl_asic_tcp_status)
        tcp_row.addStretch()
        layout.addLayout(tcp_row)

        clock_row = QHBoxLayout()
        clock_label = QLabel("EXT_CLK Selection:")
        clock_label.setStyleSheet("background-color: transparent;")
        self.roic_clock_combo = QComboBox()
        self.roic_clock_combo.addItems(ROIC_CLOCK_OPTIONS)
        clock_label.setBuddy(self.roic_clock_combo)
        self.btn_roic_generate = QPushButton("Generate")
        self.btn_roic_generate.setProperty("btnRole", "primary")
        self.btn_roic_generate.clicked.connect(self._generate_roic_clock)
        self.roic_clock_combo.currentTextChanged.connect(self._on_roic_clock_selection_changed)
        self.roic_clock_status = QLabel()
        self.roic_clock_status.setStyleSheet("background-color: transparent;")
        for widget in (clock_label, self.roic_clock_combo, self.btn_roic_generate, self.roic_clock_status):
            clock_row.addWidget(widget)
        clock_row.addStretch()
        layout.addLayout(clock_row)

        daq_row = QHBoxLayout()
        daq_label = QLabel("DAQ Selection:")
        daq_label.setStyleSheet("background-color: transparent;")
        self.roic_daq_combo = NiDeviceComboBox()
        self.roic_daq_combo.setMinimumWidth(180)
        self.roic_daq_combo.setPlaceholderText("Select NI DAQ")
        daq_label.setBuddy(self.roic_daq_combo)
        self.btn_roic_daq_ok = QPushButton("OK")
        self.btn_roic_daq_ok.setEnabled(False)
        saved_device = self._asic_tcp_settings.get_daq_device()
        if saved_device:
            self.roic_daq_combo.addItem(saved_device, saved_device)
        self.roic_daq_combo.scan_requested.connect(self._scan_roic_daq_devices)
        self.roic_daq_combo.currentIndexChanged.connect(self._update_asic_tcp_panel)
        self.btn_roic_daq_ok.clicked.connect(self._save_roic_daq_device)
        daq_row.addWidget(daq_label)
        daq_row.addWidget(self.roic_daq_combo)
        daq_row.addWidget(self.btn_roic_daq_ok)
        self.roic_daq_status = QLabel()
        self.roic_daq_status.setStyleSheet("background-color: transparent;")
        daq_row.addWidget(self.roic_daq_status)
        daq_row.addStretch()
        layout.addLayout(daq_row)
        return group

    def _scan_roic_daq_devices(self) -> None:
        combo = self.roic_daq_combo
        previous = combo.currentData() or self._asic_tcp_settings.get_daq_device()
        combo.clear()
        try:
            devices = list_roic_daq_devices()
        except Exception as exc:
            self.roic_daq_status.setText("DAQ scan failed")
            self.roic_daq_status.setToolTip(str(exc))
            return
        for name, simulated in devices:
            combo.addItem(f"{name} (Simulated)" if simulated else name, name)
        combo.setCurrentIndex(combo.findData(previous) if previous else -1)
        self.roic_daq_status.setText("" if devices else "No compatible DAQ")
        self.roic_daq_status.setToolTip("")

    def _save_roic_daq_device(self) -> None:
        device = self.roic_daq_combo.currentData()
        if not device:
            return
        try:
            self._asic_tcp_settings.save_daq_device(device)
        except OSError as exc:
            self.roic_daq_status.setText("Save failed")
            self.roic_daq_status.setToolTip(str(exc))
        else:
            self.roic_daq_status.setText("Saved")
            self.roic_daq_status.setToolTip(device)

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
            if instrument_type in (
                InstrumentType.LCR_METER,
                InstrumentType.LCR_METER_BOLOMETER,
                InstrumentType.DSA,
            ):
                button.setProperty("illustratedChoice", "true")
                button.setIconSize(QSize(84, 56))
                button.setIcon(_meter_icon(instrument_type))
                button.toggled.connect(
                    lambda checked, btn=button, kind=instrument_type: btn.setIcon(
                        _meter_icon(kind, checked)
                    )
                )
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
        self._configure_instrument_page(
            self._instrument_title(), options, back_index
        )
        self._stack.setCurrentIndex(_INSTRUMENT_PAGE_INDEX)
        self.btn_next.setText("完成")
        self.btn_next.setEnabled(False)
        self._update_prev_button()

    def _instrument_title(self) -> str:
        title_parts = [self._selected_device.value]
        if self._selected_device == DeviceType.BOLOMETER:
            title_parts.extend((self._selected_bm.value, self._selected_dut.value))
        elif self._selected_device == DeviceType.IMU:
            title_parts.append(self._selected_imu_subtype.value)
        return f"{'_'.join(title_parts)}_Instrument Selection"

    def _show_bolometer_asic_page(self) -> None:
        self._selected_instrument = (
            InstrumentType.FUNCTION_TEST_SPI_DAC
            if self.btn_function_test.isChecked()
            else None
        )
        self._stack.widget(_BOLOMETER_ASIC_PAGE_INDEX).setTitle(
            "ROIC_Tester_Selection"
        )
        self._stack.setCurrentIndex(_BOLOMETER_ASIC_PAGE_INDEX)
        self.btn_next.setText("完成")
        if not self._asic_tcp_client.is_connected and not self._asic_connecting:
            endpoint = self._asic_tcp_settings.get_endpoint()
            self.edit_asic_server_ip.setText(endpoint.ip)
            self.edit_asic_server_port.setText(str(endpoint.port))
        was_blocked = self.roic_clock_combo.blockSignals(True)
        self.roic_clock_combo.setCurrentText(self._asic_tcp_settings.get_clock_frequency())
        self.roic_clock_combo.blockSignals(was_blocked)
        self.roic_daq_combo.setCurrentIndex(-1)
        self._scan_roic_daq_devices()
        self._update_asic_tcp_panel()
        self._update_prev_button()

    def _update_asic_next_button(self) -> None:
        if self._stack.currentIndex() == _BOLOMETER_ASIC_PAGE_INDEX:
            self.btn_next.setEnabled(
                self.btn_function_test.isChecked()
                and self._asic_tcp_client.is_connected
                and not self._asic_connecting
                and not self._asic_generating_clock
                and self._asic_tcp_client.roic_clock_frequency == self.roic_clock_combo.currentText()
            )

    def _update_asic_tcp_panel(self) -> None:
        connected = self._asic_tcp_client.is_connected
        selected = self.btn_function_test.isChecked()
        self.edit_asic_server_ip.setEnabled(
            selected and not connected and not self._asic_connecting
        )
        self.edit_asic_server_port.setEnabled(
            selected and not connected and not self._asic_connecting
        )
        self.btn_function_test.setEnabled(not self._asic_generating_clock and not self._asic_connecting)
        self.btn_asic_tcp_connect.setEnabled(
            selected and not self._asic_connecting and not self._asic_generating_clock
        )
        self.btn_asic_tcp_connect.setText("Disconnect" if connected else "Connect")
        self.roic_clock_combo.setEnabled(selected and not self._asic_generating_clock)
        self.btn_roic_generate.setEnabled(
            selected and connected and not self._asic_connecting and not self._asic_generating_clock
        )
        self.roic_daq_combo.setEnabled(selected)
        self.btn_roic_daq_ok.setEnabled(selected and self.roic_daq_combo.currentIndex() >= 0)
        if not connected:
            self.roic_clock_status.clear()
        self._update_asic_next_button()

    def _on_roic_clock_selection_changed(self, frequency: str) -> None:
        try:
            self._asic_tcp_settings.save_clock_frequency(frequency)
        except OSError as exc:
            self.roic_clock_status.setText("Save failed")
            self.roic_clock_status.setToolTip(str(exc))
        self._update_asic_tcp_panel()

    def _generate_roic_clock(self) -> None:
        client = self._asic_tcp_client
        if self._asic_generating_clock:
            return
        if not client.is_connected:
            self.roic_clock_status.setText("Connect to Server first")
            return
        frequency = self.roic_clock_combo.currentText()
        client.roic_clock_frequency = None
        self._asic_generating_clock = True
        self.roic_clock_status.setText("Waiting...")
        self._update_asic_tcp_panel()

        def worker() -> None:
            try:
                client.generate_roic_clock(frequency)
            except (OSError, RuntimeError, ValueError) as exc:
                self._asic_clock_bridge.finished.emit(frequency, str(exc) or "Timeout")
            else:
                self._asic_clock_bridge.finished.emit(frequency, "")

        threading.Thread(target=worker, daemon=True).start()

    def _on_asic_clock_finished(self, frequency: str, error: str) -> None:
        self._asic_generating_clock = False
        self._update_asic_tcp_panel()
        self.roic_clock_status.setText(error or f"{frequency} OK")

    def _on_asic_instrument_selected(self, checked: bool) -> None:
        if not checked and self._asic_tcp_client.is_connected:
            self._asic_connection_timer.stop()
            self._asic_tcp_client.disconnect_roic()
            self.lbl_asic_tcp_status.setText("請連接 Server")
        self._selected_instrument = (
            InstrumentType.FUNCTION_TEST_SPI_DAC if checked else None
        )
        self._update_asic_tcp_panel()

    def _on_asic_tcp_connect_clicked(self) -> None:
        if self._asic_tcp_client.is_connected:
            self._asic_connection_timer.stop()
            self._asic_tcp_client.disconnect_roic()
            self.lbl_asic_tcp_status.setText("請連接 Server")
            self._update_asic_tcp_panel()
            return
        ip = self.edit_asic_server_ip.text().strip()
        if not ip:
            self.lbl_asic_tcp_status.setText("請輸入 Server IP")
            return
        try:
            port = int(self.edit_asic_server_port.text().strip())
        except ValueError:
            self.lbl_asic_tcp_status.setText("Port 必須為整數")
            return
        if not 1 <= port <= 65535:
            self.lbl_asic_tcp_status.setText("Port 必須介於 1–65535")
            return
        self._asic_connecting = True
        self.lbl_asic_tcp_status.setText("TCP 連接中...")
        self._update_asic_tcp_panel()

        def connect_worker() -> None:
            try:
                self._asic_tcp_client.connect(ip, port)
            except (OSError, TimeoutError) as exc:
                self._asic_connect_bridge.finished.emit(
                    False, _connect_error_code(exc)
                )
            else:
                self._asic_connect_bridge.finished.emit(True, "")

        threading.Thread(target=connect_worker, daemon=True).start()

    def _on_asic_tcp_connect_finished(self, success: bool, error_code: str) -> None:
        self._asic_connecting = False
        if success:
            self._asic_tcp_settings.save_endpoint(
                self.edit_asic_server_ip.text(),
                int(self.edit_asic_server_port.text()),
            )
            self._asic_connection_timer.start()
        self.lbl_asic_tcp_status.setText(
            "TCP 已連接" if success else f"連線失敗 ({error_code or 'unknown'})"
        )
        self._update_asic_tcp_panel()

    def _check_asic_tcp_connection(self) -> None:
        if self._asic_generating_clock:
            return
        if self._asic_tcp_client.check_connection():
            return
        self._asic_connection_timer.stop()
        self.lbl_asic_tcp_status.setText("請連接 Server")
        self._update_asic_tcp_panel()

    def _apply_choice_button_font(self, button: QPushButton | QToolButton, checked: bool) -> None:
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
        elif isinstance(self._chuck_motor, MpiTp80ChuckMotor):
            self._run_motor_action(
                lambda: self._chuck_motor.move_chuck_relative_um(
                    num_x_index * 1000, num_y_index * 1000
                )
            )
        else:
            self._run_motor_action(
                lambda: self._chuck_motor.move_chuck_index_relative(
                    num_x_index, num_y_index
                )
            )

    def _run_tp80_z_test(self, distance_mm: float) -> None:
        motor = self._chuck_motor
        if isinstance(motor, MpiTp80ChuckMotor):
            self._run_motor_action(lambda: motor.move_chuck_z_relative_mm(distance_mm))

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
        suffix = " 1mm" if self._selected_prober == ProberType.MPI_TP80 else ""
        self.btn_test_left.setText(f"X←{suffix}")
        self.btn_test_right.setText(f"X→{suffix}")
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
        is_tp80 = self._selected_prober == ProberType.MPI_TP80
        for button in (self.btn_test_z_up, self.btn_test_z_down):
            button.setVisible(is_tp80)
            button.setEnabled(enabled and is_tp80)

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
                asic_tcp_client=(
                    self._asic_tcp_client
                    if self._selected_device == DeviceType.BOLOMETER
                    and self._selected_dut == DutType.ASIC
                    else None
                ),
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
        if current == _BOLOMETER_ASIC_PAGE_INDEX:
            self._stack.setCurrentIndex(_DUT_PAGE_INDEX)
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
            if self._selected_dut == DutType.ELEMENT:
                self._show_instrument_page(
                    _BOLOMETER_INSTRUMENT_BUTTONS,
                    back_index=_DUT_PAGE_INDEX,
                )
            else:
                self._show_bolometer_asic_page()
            return

        if current == _INSTRUMENT_PAGE_INDEX:
            if self._selected_instrument is None:
                return
            self._finish_setup()
            return

        if current == _BOLOMETER_ASIC_PAGE_INDEX:
            if not self.btn_next.isEnabled():
                return
            self._finish_setup()

    def closeEvent(self, event) -> None:
        self._stop_xy_velocity_move()
        self._asic_connection_timer.stop()
        if not self._completed:
            self._disconnect_tcp()
            self._asic_tcp_client.disconnect_roic()
            app = QApplication.instance()
            if app is not None:
                app.quit()
        super().closeEvent(event)
