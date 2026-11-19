"""Main application window matching GUI_002 layout."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from excel_loader import WaferMapData, load_wafer_map_xlsx, save_wafer_map_report
from map_data_reader import InspectionTargetList, extract_inspection_targets
from theme_config import THEMES, generate_theme_qss
from datalog import create_session_dir
from datalog_watcher import DatalogWatcher
from save_params_window import SaveParamsPanel
from measure import DieMeasurementResult, measure_Start, MeasurementSession
from lcr_criterion import GOOD_DIE_BIN
from statistics_report import init_statistics_report
from prober_motor import ProberType, create_chuck_motor
from prober_motor.mpi_tp80 import MpiTp80ChuckMotor
from prober_motor.suss import SussChuckMotor
from prober_motor.tcp_client import ProberTcpClient
from instruments.bmt_tcp import BmtTcpClient
from wafer_map_view import WaferMapView

logger = logging.getLogger(__name__)

_MAIN_WINDOW_LEFT_MARGIN_PX = 20


def position_main_window_at_screen_left(
    window: QMainWindow,
    left_margin: int = _MAIN_WINDOW_LEFT_MARGIN_PX,
) -> None:
    app = QApplication.instance()
    if app is None:
        return

    screen = app.primaryScreen()
    if screen is None:
        return

    screen_geometry = screen.geometry()
    available_geometry = screen.availableGeometry()
    window.move(
        screen_geometry.left() + left_margin,
        available_geometry.top(),
    )


class MainWindow(QMainWindow):
    def __init__(
        self,
        work_dir: Path | None = None,
        prober_type: ProberType = ProberType.SIMULATION,
        bm_model: str | None = None,
        instrument_type: str | None = None,
        tcp_client: ProberTcpClient | None = None,
        asic_tcp_client: BmtTcpClient | None = None,
    ):
        super().__init__()
        self._work_dir = work_dir or Path.cwd()
        self._bm_model = bm_model
        self._instrument_type = instrument_type
        self._prober_type = prober_type
        self._chuck_motor = create_chuck_motor(prober_type)
        self._tcp_client = (
            tcp_client if tcp_client is not None else ProberTcpClient(self)
        )
        self._asic_tcp_client = asic_tcp_client
        self._attach_tcp_client_to_motor()
        self._read_initial_contact_height()
        self._datalog_session_dir: Path | None = None
        self._datalog_open_dir: Path | None = None
        self._datalog_watcher = DatalogWatcher(self._work_dir, self)
        self._datalog_watcher.datalog_detected.connect(self._on_datalog_detected)
        self._datalog_watcher.start()
        self._current_theme: str | None = None
        self._inspection_targets: InspectionTargetList | None = None
        self._wafer_map_path: Path | None = None
        self._wafer_map_data: WaferMapData | None = None
        self._measurement_good_count = 0
        self._pending_inspection_count = 0
        self._measurement_session: MeasurementSession | None = None
        self._instrument_windows: dict[str, QMainWindow] = {}
        self._xy_velocity_timer = QTimer(self)
        self._xy_velocity_timer.setInterval(100)
        self._xy_velocity_direction: tuple[str, str, str] | None = None
        self._xy_velocity_timer.timeout.connect(self._on_xy_velocity_timer)
        self._z_velocity_timer = QTimer(self)
        self._z_velocity_timer.setInterval(100)
        self._z_velocity_direction: str | None = None
        self._z_velocity_timer.timeout.connect(self._on_z_velocity_timer)
        self.setWindowTitle("Wafer Level Inspection")
        self.resize(600, 800)
        self._build_menu_bar()
        self._build_ui()
        self._tcp_client.command_sent.connect(self._on_tcp_command_sent)
        self.apply_theme("light")

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._instrument_type is not None:
            self._open_instrument_from_menu(self._instrument_type)

    def _forget_invalid_instrument_windows(self) -> None:
        stale: list[str] = []
        for name, window in self._instrument_windows.items():
            try:
                window.windowTitle()
            except RuntimeError:
                stale.append(name)
        for name in stale:
            self._instrument_windows.pop(name, None)

    def _instrument_stack_index(self, instrument_name: str) -> int:
        names = list(self._instrument_windows.keys())
        if instrument_name in names:
            return names.index(instrument_name)
        return len(names)

    def _open_instrument_from_menu(self, instrument_name: str) -> None:
        self._forget_invalid_instrument_windows()
        existing = self._instrument_windows.get(instrument_name)
        if existing is not None:
            try:
                existing.raise_()
                existing.activateWindow()
                return
            except RuntimeError:
                self._instrument_windows.pop(instrument_name, None)

        from instruments.panels.registry import create_modular_instrument_window

        window = create_modular_instrument_window(
            instrument_name,
            parent=self,
            work_dir=self._work_dir,
            asic_tcp_client=self._asic_tcp_client,
        )
        if window is None:
            QMessageBox.information(
                self,
                "儀器",
                f"尚未支援儀器面板：{instrument_name}",
            )
            return
        stack_index = self._instrument_stack_index(instrument_name)
        window.align_to_main_window(self, stack_index=stack_index)
        window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        window.destroyed.connect(
            lambda _obj=None, name=instrument_name: self._instrument_windows.pop(
                name, None
            )
        )
        self._instrument_windows[instrument_name] = window
        window.show()

    def _measurement_instrument_window(self) -> QMainWindow | None:
        """Instrument panel used by automated wafer measurement (from guided setup)."""
        if self._instrument_type is None:
            return None
        self._forget_invalid_instrument_windows()
        window = self._instrument_windows.get(self._instrument_type)
        if window is not None:
            return window
        self._open_instrument_from_menu(self._instrument_type)
        return self._instrument_windows.get(self._instrument_type)

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QGridLayout(central)
        root.setContentsMargins(4, 4, 4, 4)
        root.setHorizontalSpacing(6)
        root.setVerticalSpacing(6)

        self.tabs = self._build_tabs()

        root.addWidget(self._build_sidebar(), 0, 0)
        root.addWidget(self.tabs, 0, 1)

        root.setColumnStretch(1, 1)
        root.setRowStretch(0, 1)

    def _build_menu_bar(self) -> None:
        menubar = self.menuBar()

        file_menu = menubar.addMenu("檔案(&F)")
        exit_action = QAction("結束(&X)", self)
        exit_action.setShortcut("Alt+F4")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        settings_menu = menubar.addMenu("設定(&S)")

        hardware_menu = settings_menu.addMenu("硬體")
        hardware_menu.addAction(QAction("DAQ", self))
        dsa_action = QAction("DSA", self)
        dsa_action.triggered.connect(
            lambda: self._open_instrument_from_menu("DSA")
        )
        hardware_menu.addAction(dsa_action)

        theme_menu = settings_menu.addMenu("外觀風格")
        for theme_id, theme_config in THEMES.items():
            action = QAction(theme_config["name"], self)
            action.triggered.connect(
                lambda checked, tid=theme_id: self.apply_theme(tid)
            )
            theme_menu.addAction(action)

        instrument_menu = menubar.addMenu("儀器(&I)")
        lcr_action = QAction("LCR meter", self)
        lcr_action.triggered.connect(self._on_open_lcr_meter_from_menu)
        instrument_menu.addAction(lcr_action)

        lcr_bolometer_action = QAction("LCR_Meter_Bolometer", self)
        lcr_bolometer_action.triggered.connect(
            lambda: self._open_instrument_from_menu("LCR_Meter_Bolometer")
        )
        instrument_menu.addAction(lcr_bolometer_action)

        bmt3000_action = QAction("BMT3000", self)
        bmt3000_action.triggered.connect(
            lambda: self._open_instrument_from_menu("BMT3000")
        )
        instrument_menu.addAction(bmt3000_action)

        bmt5000_action = QAction("BMT5000", self)
        bmt5000_action.triggered.connect(
            lambda: self._open_instrument_from_menu("BMT5000")
        )
        instrument_menu.addAction(bmt5000_action)

        ni8452_action = QAction("NI_8452", self)
        ni8452_action.triggered.connect(
            lambda: self._open_instrument_from_menu("NI_8452")
        )
        instrument_menu.addAction(ni8452_action)

    def _on_open_lcr_meter_from_menu(self) -> None:
        self._open_instrument_from_menu("LCR Meter")

    def _sidebar_control_width(self) -> int:
        return 120

    def _build_sidebar(self) -> QWidget:
        panel = QWidget()
        panel.setFixedWidth(self._sidebar_control_width() + 8)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.btn_load_map = QPushButton("Load Map")
        self.btn_set = QPushButton("Set")
        self.btn_start = QPushButton("Start")
        self.btn_pause = QPushButton("Pause")
        self.btn_close = QPushButton("Close")

        for btn in (self.btn_set, self.btn_start, self.btn_pause):
            btn.setEnabled(False)

        self.btn_load_map.clicked.connect(self._on_load_map)
        self.btn_set.clicked.connect(self._on_set)
        self.btn_start.clicked.connect(self._on_start)
        self.btn_pause.clicked.connect(self._on_pause)
        self.btn_close.clicked.connect(self.close)

        button_width = self._sidebar_control_width()
        for btn in (
            self.btn_load_map,
            self.btn_set,
            self.btn_start,
            self.btn_pause,
            self.btn_close,
        ):
            btn.setMinimumHeight(36)
            btn.setFixedWidth(button_width)
            layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignLeft)

        self._mark_primary_button(self.btn_load_map)
        self._mark_start_button(self.btn_start)
        self._mark_close_button(self.btn_close)

        layout.addSpacing(24)

        self._save_params_panel = SaveParamsPanel(
            self._work_dir, compact=True
        )
        self.edit_folder = self._save_params_panel.edit_folder
        self.edit_prefix = self._save_params_panel.edit_prefix
        self.spin_x = self._save_params_panel.spin_x
        self.spin_y = self._save_params_panel.spin_y
        self.edit_suffix = self._save_params_panel.edit_suffix
        self.btn_open_folder = self._save_params_panel.btn_open_folder
        layout.addWidget(self._save_params_panel)
        layout.addStretch()
        return panel

    def _build_tabs(self) -> QTabWidget:
        tabs = QTabWidget()
        tabs.addTab(self._build_wafer_map_tab(), "(1) Wafer Map")
        tabs.addTab(self._build_prober_control_tab(), "(2) Prober控制")
        return tabs

    def _read_only_line_edit(
        self, text: str, min_width: int | None = None
    ) -> QLineEdit:
        field = QLineEdit(text)
        field.setReadOnly(True)
        if min_width is not None:
            field.setMinimumWidth(min_width)
        return field

    def _build_wafer_map_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        map_info_row = QHBoxLayout()
        map_info_row.addWidget(QLabel("Chuck Index X (um):"))
        self.lbl_map_chuck_index_x = self._read_only_line_edit("-")
        self.lbl_map_chuck_index_x.setFixedWidth(80)
        map_info_row.addWidget(self.lbl_map_chuck_index_x)
        map_info_row.addWidget(QLabel("Chuck Index Y (um):"))
        self.lbl_map_chuck_index_y = self._read_only_line_edit("-")
        self.lbl_map_chuck_index_y.setFixedWidth(80)
        map_info_row.addWidget(self.lbl_map_chuck_index_y)
        map_info_row.addStretch()
        layout.addLayout(map_info_row)

        coord_row = QHBoxLayout()
        coord_row.addWidget(QLabel("目前檢測元件座標:"))
        coord_row.addWidget(QLabel("X:"))
        self.lbl_cur_x = self._read_only_line_edit("0")
        self.lbl_cur_x.setFixedWidth(60)
        coord_row.addWidget(self.lbl_cur_x)
        coord_row.addWidget(QLabel("Y:"))
        self.lbl_cur_y = self._read_only_line_edit("0")
        self.lbl_cur_y.setFixedWidth(60)
        coord_row.addWidget(self.lbl_cur_y)
        coord_row.addStretch()
        layout.addLayout(coord_row)

        stats_row1 = QHBoxLayout()
        stats_row1.addWidget(QLabel("元件總數:"))
        self.lbl_total = self._read_only_line_edit("0")
        self.lbl_total.setFixedWidth(60)
        stats_row1.addWidget(self.lbl_total)
        stats_row1.addWidget(QLabel("本次待檢數目:"))
        self.lbl_pending = self._read_only_line_edit("0")
        self.lbl_pending.setFixedWidth(60)
        stats_row1.addWidget(self.lbl_pending)
        stats_row1.addWidget(QLabel("本次已檢數目:"))
        self.lbl_inspected = self._read_only_line_edit("0")
        self.lbl_inspected.setFixedWidth(60)
        stats_row1.addWidget(self.lbl_inspected)
        stats_row1.addWidget(QLabel("全部已檢數目:"))
        self.lbl_all_inspected = self._read_only_line_edit("0")
        self.lbl_all_inspected.setFixedWidth(60)
        stats_row1.addWidget(self.lbl_all_inspected)
        stats_row1.addStretch()
        layout.addLayout(stats_row1)

        stats_row2 = QHBoxLayout()
        stats_row2.addWidget(QLabel("良品數目:"))
        self.lbl_good = self._read_only_line_edit("0")
        self.lbl_good.setFixedWidth(60)
        stats_row2.addWidget(self.lbl_good)
        stats_row2.addWidget(QLabel("良率:"))
        self.lbl_yield = self._read_only_line_edit("0.00%")
        self.lbl_yield.setFixedWidth(60)
        stats_row2.addWidget(self.lbl_yield)
        self.lbl_good.setStyleSheet("color: blue;")
        self.lbl_yield.setStyleSheet("color: blue;")
        stats_row2.addStretch()
        layout.addLayout(stats_row2)

        zoom_row = QHBoxLayout()
        zoom_row.addWidget(QLabel("Zoom Factor (% of Original Size)"))
        self.slider_zoom = QSlider(Qt.Orientation.Horizontal)
        self.slider_zoom.setRange(20, 200)
        self.slider_zoom.setValue(100)
        self.slider_zoom.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.slider_zoom.setTickInterval(20)
        self.slider_zoom.setFixedWidth(300)
        self.lbl_zoom = self._read_only_line_edit("100")
        self.lbl_zoom.setFixedWidth(60)
        self.slider_zoom.valueChanged.connect(self._on_zoom_changed)
        zoom_row.addWidget(self.slider_zoom)
        zoom_row.addWidget(self.lbl_zoom)
        zoom_row.addStretch()
        layout.addLayout(zoom_row)

        map_frame = QGroupBox("Wafer Map")
        map_layout = QVBoxLayout(map_frame)
        self.wafer_view = WaferMapView()
        self.wafer_view.die_clicked.connect(self._on_die_clicked)
        map_layout.addWidget(self.wafer_view)
        layout.addWidget(map_frame, stretch=1)
        return tab

    def _build_prober_control_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.txt_tcp_commands = self._build_tcp_command_log()
        layout.addWidget(self.txt_tcp_commands, 0)

        xy_row = QHBoxLayout()
        xy_row.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        xy_row.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        xy_group = self._build_xy_move_group()
        z_axis_group = self._build_z_axis_control_group()
        self._sync_motor_group_heights(xy_group, z_axis_group)
        xy_row.addWidget(xy_group)
        xy_row.addWidget(z_axis_group)
        xy_row.addStretch()
        layout.addLayout(xy_row, 0)

        home_row = QHBoxLayout()
        home_row.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        home_row.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        home_row.addWidget(self._build_set_home_group())
        self.txt_home_abs_coords = self._build_home_abs_coord_log()
        home_row.addWidget(self.txt_home_abs_coords)
        home_row.addStretch()
        layout.addLayout(home_row, 0)

        instant_group = self._build_instant_move_group()
        quick_move_group = self._build_quick_move_group()
        self._sync_motor_group_heights(instant_group, quick_move_group)

        motor_row = QHBoxLayout()
        motor_row.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        motor_row.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        motor_row.addWidget(instant_group)
        motor_row.addWidget(quick_move_group)
        motor_row.addStretch()
        layout.addLayout(motor_row, 0)

        position_row = QHBoxLayout()
        self.lbl_chuck_x = QLabel("Chuck X: 0.000")
        self.lbl_chuck_y = QLabel("Chuck Y: 0.000")
        self.lbl_chuck_z = QLabel("Chuck Z: 0.000")
        self.lbl_chuck_index = QLabel("Die: (0, 0)")
        for lbl in (
            self.lbl_chuck_x,
            self.lbl_chuck_y,
            self.lbl_chuck_z,
            self.lbl_chuck_index,
        ):
            lbl.setStyleSheet("font-weight:bold;")
            position_row.addWidget(lbl)
        position_row.addStretch()
        layout.addLayout(position_row, 0)
        layout.addStretch(1)

        self._update_chuck_position_display()
        return tab

    def _build_tcp_command_log(self) -> QPlainTextEdit:
        view = QPlainTextEdit()
        view.setReadOnly(True)
        view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        view.document().setDocumentMargin(4)
        line_height = view.fontMetrics().lineSpacing()
        view.setFixedHeight(line_height * 4 + 2 * view.frameWidth() + 8)
        view.setPlaceholderText("尚無 TCP 命令")
        return view

    def _build_home_abs_coord_log(self) -> QPlainTextEdit:
        view = QPlainTextEdit()
        view.setReadOnly(True)
        view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        view.document().setDocumentMargin(4)
        metrics = view.fontMetrics()
        line_height = metrics.lineSpacing()
        view.setFixedHeight(line_height * 3 + 2 * view.frameWidth() + 8)
        view.setFixedWidth(300)
        view.setPlaceholderText("尚無 座標")
        return view

    def _on_tcp_command_sent(self, command: str) -> None:
        self.txt_tcp_commands.appendPlainText(command)
        cursor = self.txt_tcp_commands.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.txt_tcp_commands.setTextCursor(cursor)

    def _compact_motor_group_box(self, group: QGroupBox, layout) -> None:
        layout.setContentsMargins(6, 4, 6, 6)
        layout.setSpacing(4)

    def _sync_motor_group_heights(
        self, reference: QGroupBox, *groups: QGroupBox
    ) -> None:
        height = reference.sizeHint().height()
        for group in (reference, *groups):
            group.setFixedHeight(height)

    def _build_set_home_group(self) -> QGroupBox:
        group = QGroupBox("設定HOME點")
        row = QHBoxLayout(group)
        row.setContentsMargins(6, -4, 6, 4)
        row.setSpacing(8)
        row.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.spin_home_die_index_x = QSpinBox()
        self.spin_home_die_index_y = QSpinBox()
        for spin in (self.spin_home_die_index_x, self.spin_home_die_index_y):
            spin.setRange(0, 999)
        row.addWidget(QLabel("X座標"))
        row.addWidget(self.spin_home_die_index_x)
        row.addWidget(QLabel("Y座標"))
        row.addWidget(self.spin_home_die_index_y)
        self.btn_set_home = QPushButton("Set Home")
        self.btn_set_home.clicked.connect(self._on_set_chuck_home)
        row.addWidget(self.btn_set_home)
        group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        group.adjustSize()
        group.setFixedHeight(group.sizeHint().height())
        return group

    def _build_instant_move_group(self) -> QGroupBox:
        group = QGroupBox("瞬間移動")
        form = QFormLayout(group)
        self._compact_motor_group_box(group, form)
        self.spin_instant_x = QSpinBox()
        self.spin_instant_y = QSpinBox()
        for spin in (self.spin_instant_x, self.spin_instant_y):
            spin.setRange(0, 999)
        form.addRow("X座標", self.spin_instant_x)
        form.addRow("Y座標", self.spin_instant_y)
        self.btn_move_xy = QPushButton("Move")
        self.btn_move_xy.setMinimumHeight(36)
        self.btn_move_xy.clicked.connect(self._on_move_chuck_relative)
        form.addRow(self.btn_move_xy)
        return group

    def _build_quick_move_group(self) -> QGroupBox:
        group = QGroupBox("快速移動")
        layout = QVBoxLayout(group)
        self._compact_motor_group_box(group, layout)
        self.btn_index_home = QPushButton("Home")
        self.btn_chuck_load = QPushButton("Load")
        for btn in (self.btn_index_home, self.btn_chuck_load):
            btn.setMinimumHeight(36)
        self.btn_index_home.clicked.connect(self._on_move_chuck_home)
        self.btn_chuck_load.clicked.connect(self._on_move_chuck_load)
        layout.addWidget(self.btn_index_home)
        layout.addWidget(self.btn_chuck_load)
        layout.addStretch()
        return group

    def _build_z_axis_control_group(self) -> QGroupBox:
        group = QGroupBox("下針抬針")
        layout = QVBoxLayout(group)
        self._compact_motor_group_box(group, layout)
        self.btn_set_contact = QPushButton("Set Contact")
        self.btn_contact = QPushButton("Contact")
        self.btn_seperate = QPushButton("Seperate")
        for btn in (self.btn_set_contact, self.btn_contact, self.btn_seperate):
            btn.setMinimumHeight(36)
        self.btn_set_contact.clicked.connect(self._on_set_chuck_contact)
        self.btn_contact.clicked.connect(self._on_move_chuck_contact)
        self.btn_seperate.clicked.connect(self._on_move_chuck_seperation)
        layout.addWidget(self.btn_set_contact)
        layout.addWidget(self.btn_contact)
        layout.addWidget(self.btn_seperate)
        layout.addStretch()
        return group

    def _build_xy_move_group(self) -> QGroupBox:
        group = QGroupBox("X/Y/Z軸移動")
        root = QVBoxLayout(group)
        self._compact_motor_group_box(group, root)

        mode_group = QGroupBox("模式選擇")
        mode_layout = QHBoxLayout(mode_group)
        mode_layout.setContentsMargins(6, 4, 6, 6)
        mode_layout.setSpacing(12)
        self.radio_xy_index = QRadioButton("Index")
        self.radio_xy_velocity = QRadioButton("Velocity")
        self.radio_xy_jog = QRadioButton("Jog")
        self.radio_xy_index.setChecked(True)
        mode_layout.addWidget(self.radio_xy_index)
        mode_layout.addWidget(self.radio_xy_velocity)
        mode_layout.addWidget(self.radio_xy_jog)
        mode_layout.addStretch()
        root.addWidget(mode_group)

        self.xy_speed_row = QWidget()
        speed_layout = QHBoxLayout(self.xy_speed_row)
        speed_layout.setContentsMargins(0, 0, 0, 0)
        speed_layout.setSpacing(8)
        self.slider_xy_speed = QSlider(Qt.Orientation.Horizontal)
        self.slider_xy_speed.setRange(1, 100)
        self.slider_xy_speed.setValue(20)
        self.slider_xy_speed.setMinimumWidth(120)
        self.lbl_xy_speed_value = QLabel("20")
        self.lbl_xy_speed_value.setMinimumWidth(24)
        self.lbl_xy_speed_value.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.slider_xy_speed.valueChanged.connect(self._on_xy_speed_changed)
        self.lbl_xy_speed_title = QLabel("速度")
        speed_layout.addWidget(self.lbl_xy_speed_title)
        speed_layout.addWidget(self.slider_xy_speed, stretch=1)
        speed_layout.addWidget(self.lbl_xy_speed_value)
        root.addWidget(self.xy_speed_row)

        self.radio_xy_index.toggled.connect(self._update_xy_speed_enabled)
        self.radio_xy_velocity.toggled.connect(self._update_xy_speed_enabled)
        self.radio_xy_jog.toggled.connect(self._update_xy_speed_enabled)
        self._update_xy_speed_enabled()

        grid = QGridLayout()
        grid.setHorizontalSpacing(4)
        grid.setVerticalSpacing(2)

        self.btn_index_up_left = QPushButton("↖")
        self.btn_index_up = QPushButton("Y↑")
        self.btn_index_up_right = QPushButton("↗")
        self.btn_z_up = QPushButton("Z↑")
        self.btn_index_left = QPushButton("X←")
        self.btn_index_right = QPushButton("X→")
        self.btn_index_down_left = QPushButton("↙")
        self.btn_index_down = QPushButton("Y↓")
        self.btn_index_down_right = QPushButton("↘")
        self.btn_z_down = QPushButton("Z↓")
        for btn in (
            self.btn_index_up_left,
            self.btn_index_up,
            self.btn_index_up_right,
            self.btn_z_up,
            self.btn_index_left,
            self.btn_index_right,
            self.btn_index_down_left,
            self.btn_index_down,
            self.btn_index_down_right,
            self.btn_z_down,
        ):
            btn.setMinimumWidth(72)

        self.btn_index_up_left.pressed.connect(
            lambda: self._on_xy_direction_pressed(-1, 1, "-", "+", "0")
        )
        self.btn_index_up.pressed.connect(
            lambda: self._on_xy_direction_pressed(0, 1, "0", "+", "0")
        )
        self.btn_index_up_right.pressed.connect(
            lambda: self._on_xy_direction_pressed(1, 1, "+", "+", "0")
        )
        self.btn_index_down_left.pressed.connect(
            lambda: self._on_xy_direction_pressed(-1, -1, "-", "-", "0")
        )
        self.btn_index_down.pressed.connect(
            lambda: self._on_xy_direction_pressed(0, -1, "0", "-", "0")
        )
        self.btn_index_down_right.pressed.connect(
            lambda: self._on_xy_direction_pressed(1, -1, "+", "-", "0")
        )
        self.btn_index_left.pressed.connect(
            lambda: self._on_xy_direction_pressed(-1, 0, "-", "0", "0")
        )
        self.btn_index_right.pressed.connect(
            lambda: self._on_xy_direction_pressed(1, 0, "+", "0", "0")
        )
        for btn in (
            self.btn_index_up_left,
            self.btn_index_up,
            self.btn_index_up_right,
            self.btn_index_left,
            self.btn_index_right,
            self.btn_index_down_left,
            self.btn_index_down,
            self.btn_index_down_right,
        ):
            btn.released.connect(self._on_xy_direction_released)

        self.btn_z_up.pressed.connect(lambda: self._on_z_direction_pressed("+"))
        self.btn_z_down.pressed.connect(lambda: self._on_z_direction_pressed("-"))
        self.btn_z_up.released.connect(self._on_z_direction_released)
        self.btn_z_down.released.connect(self._on_z_direction_released)

        grid.addWidget(self.btn_index_up_left, 0, 0)
        grid.addWidget(self.btn_index_up, 0, 1)
        grid.addWidget(self.btn_index_up_right, 0, 2)
        grid.addWidget(self.btn_z_up, 0, 3)
        grid.addWidget(self.btn_index_left, 1, 0)
        grid.addWidget(self.btn_index_right, 1, 2)
        grid.addWidget(self.btn_index_down_left, 2, 0)
        grid.addWidget(self.btn_index_down, 2, 1)
        grid.addWidget(self.btn_index_down_right, 2, 2)
        grid.addWidget(self.btn_z_down, 2, 3)
        root.addLayout(grid)
        return group

    def _update_xy_speed_enabled(self) -> None:
        enabled = self.radio_xy_velocity.isChecked()
        self.slider_xy_speed.setEnabled(enabled)
        self.lbl_xy_speed_title.setEnabled(enabled)
        self.lbl_xy_speed_value.setEnabled(enabled)

    def _on_xy_speed_changed(self, value: int) -> None:
        self.lbl_xy_speed_value.setText(str(value))
        if self._xy_velocity_direction is not None:
            self._send_xy_velocity_command()
        if self._z_velocity_direction is not None:
            self._send_z_velocity_command()

    def _is_suss_velocity_mode(self) -> bool:
        return (
            self._prober_type == ProberType.SUSS and self.radio_xy_velocity.isChecked()
        )

    def _is_tp80_jog_mode(self) -> bool:
        return (
            self._prober_type == ProberType.MPI_TP80 and self.radio_xy_jog.isChecked()
        )

    def _is_tp80_velocity_mode(self) -> bool:
        return (
            self._prober_type == ProberType.MPI_TP80
            and self.radio_xy_velocity.isChecked()
        )

    def _on_xy_direction_pressed(
        self,
        num_x_index: int,
        num_y_index: int,
        vx: str,
        vy: str,
        vz: str,
    ) -> None:
        if self._is_tp80_jog_mode() and isinstance(
            self._chuck_motor, MpiTp80ChuckMotor
        ):
            self._run_motor_action(lambda: self._chuck_motor.move_chuck_xy_jog(vx, vy))
            return
        if self._is_tp80_velocity_mode() and isinstance(
            self._chuck_motor, MpiTp80ChuckMotor
        ):
            speed = float(self.slider_xy_speed.value())
            self._run_motor_action(
                lambda: self._chuck_motor.move_chuck_velocity(vx, vy, vz, speed)
            )
            return
        if self._is_suss_velocity_mode():
            self._start_xy_velocity_move(vx, vy, vz)
        elif self.radio_xy_index.isChecked():
            self._on_move_chuck_index_relative(num_x_index, num_y_index)

    def _on_xy_direction_released(self) -> None:
        if self._is_tp80_jog_mode() or self._is_tp80_velocity_mode():
            return
        if self._is_suss_velocity_mode():
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
        if not was_moving:
            return
        try:
            self._chuck_motor.stop_chuck_movement()
        except Exception as exc:
            QMessageBox.critical(self, "馬達控制錯誤", str(exc))

    def _on_xy_velocity_timer(self) -> None:
        self._send_xy_velocity_command()

    def _send_xy_velocity_command(self) -> None:
        if self._xy_velocity_direction is None:
            return
        vx, vy, vz = self._xy_velocity_direction
        speed = float(self.slider_xy_speed.value())
        try:
            self._chuck_motor.move_chuck_velocity(vx, vy, vz, speed)
        except Exception as exc:
            self._xy_velocity_timer.stop()
            self._xy_velocity_direction = None
            QMessageBox.critical(self, "馬達控制錯誤", str(exc))

    def _is_suss_z_velocity_mode(self) -> bool:
        return self._prober_type == ProberType.SUSS

    def _on_z_direction_pressed(self, vz: str) -> None:
        if self._prober_type == ProberType.MPI_TP80 and isinstance(
            self._chuck_motor, MpiTp80ChuckMotor
        ):
            if self._is_tp80_velocity_mode():
                speed = float(self.slider_xy_speed.value())
                self._run_motor_action(
                    lambda: self._chuck_motor.move_chuck_z_velocity(
                        "0", "0", vz, speed
                    )
                )
            else:
                # Index and Jog: fixed 0.001 mm step
                self._run_motor_action(
                    lambda: self._chuck_motor.move_chuck_z_jog(vz)
                )
            return
        self._start_z_velocity_move(vz)

    def _on_z_direction_released(self) -> None:
        if self._prober_type == ProberType.MPI_TP80:
            return
        self._stop_z_velocity_move()

    def _start_z_velocity_move(self, vz: str) -> None:
        self._z_velocity_direction = vz
        self._send_z_velocity_command()
        if not self._z_velocity_timer.isActive():
            self._z_velocity_timer.start()

    def _stop_z_velocity_move(self) -> None:
        was_moving = self._z_velocity_direction is not None
        self._z_velocity_timer.stop()
        self._z_velocity_direction = None
        if not was_moving:
            return
        if not self._is_suss_z_velocity_mode():
            return
        try:
            self._chuck_motor.stop_chuck_movement()
        except Exception as exc:
            QMessageBox.critical(self, "馬達控制錯誤", str(exc))

    def _on_z_velocity_timer(self) -> None:
        self._send_z_velocity_command()

    def _send_z_velocity_command(self) -> None:
        if self._z_velocity_direction is None:
            return
        speed = float(self.slider_xy_speed.value())
        try:
            self._chuck_motor.move_chuck_z_velocity(
                "0", "0", self._z_velocity_direction, speed
            )
        except Exception as exc:
            self._z_velocity_timer.stop()
            self._z_velocity_direction = None
            QMessageBox.critical(self, "馬達控制錯誤", str(exc))

    def _run_motor_action(self, action, *, use_cache: bool = False) -> None:
        try:
            action()
            self._update_chuck_position_display(use_cache=use_cache)
        except Exception as exc:
            QMessageBox.critical(self, "馬達控制錯誤", str(exc))

    def _update_chuck_position_display(self, *, use_cache: bool = False) -> None:
        pos = self._chuck_motor.read_chuck_position(use_cache=use_cache)
        self.lbl_chuck_x.setText(f"Chuck X: {pos.x:.3f}")
        self.lbl_chuck_y.setText(f"Chuck Y: {pos.y:.3f}")
        self.lbl_chuck_z.setText(f"Chuck Z: {pos.z:.3f} ({pos.z_state})")
        self.lbl_chuck_index.setText(
            f"Die: ({pos.now_die_index_x}, {pos.now_die_index_y})"
        )

    def _attach_tcp_client_to_motor(self) -> None:
        if isinstance(self._chuck_motor, (MpiTp80ChuckMotor, SussChuckMotor)):
            self._chuck_motor.set_tcp_client(self._tcp_client)

    def _read_initial_contact_height(self) -> None:
        """Read and record contact height for the selected prober (um / micron meter)."""
        try:
            height_um = self._chuck_motor.read_chuck_contact_pos()
            logger.info(
                "[%s] initial contact height = %.3f um",
                self._chuck_motor.prober_name,
                height_um,
            )
        except Exception as exc:
            logger.warning(
                "[%s] read_chuck_contact_pos failed: %s",
                self._chuck_motor.prober_name,
                exc,
            )

    def _disconnect_tcp(self) -> None:
        if self._tcp_client.is_connected:
            self._tcp_client.disconnect()
        if isinstance(self._chuck_motor, (MpiTp80ChuckMotor, SussChuckMotor)):
            self._chuck_motor.set_tcp_client(self._tcp_client)

    def _close_instrument_windows(self) -> None:
        for window in list(self._instrument_windows.values()):
            window.close()
        self._instrument_windows.clear()

    def closeEvent(self, event) -> None:
        if self._measurement_session is not None:
            self._measurement_session.stop(silent=True)
            self._measurement_session = None
        if self._xy_velocity_timer.isActive():
            self._stop_xy_velocity_move()
        if self._z_velocity_timer.isActive():
            self._stop_z_velocity_move()
        self._close_instrument_windows()
        self._disconnect_tcp()
        if self._asic_tcp_client is not None:
            self._asic_tcp_client.disconnect()
        self._datalog_watcher.stop()
        super().closeEvent(event)

    def _mark_primary_button(self, button: QPushButton) -> None:
        button.setProperty("btnRole", "primary")
        self._repolish_widget(button)

    def _mark_close_button(self, button: QPushButton) -> None:
        button.setProperty("btnRole", "close")
        self._repolish_widget(button)

    def _mark_start_button(self, button: QPushButton) -> None:
        button.setProperty("btnRole", "start")
        self._repolish_widget(button)

    def _repolish_widget(self, widget: QWidget) -> None:
        style = widget.style()
        style.unpolish(widget)
        style.polish(widget)
        widget.update()

    def _refresh_sidebar_button_styles(self) -> None:
        for btn in (
            self.btn_load_map,
            self.btn_set,
            self.btn_start,
            self.btn_pause,
            self.btn_close,
            self.btn_open_folder,
        ):
            self._repolish_widget(btn)

    def apply_theme(self, theme_id: str) -> None:
        if theme_id not in THEMES:
            return
        if theme_id == self._current_theme:
            return

        self._current_theme = theme_id
        theme = THEMES[theme_id]
        app = QApplication.instance()
        if app is None:
            return

        app.setStyleSheet(generate_theme_qss(theme))

        accent = theme["accent"]

        self.lbl_good.setStyleSheet(f"color: {accent};")
        self.lbl_yield.setStyleSheet(f"color: {accent};")
        for lbl in (
            self.lbl_chuck_x,
            self.lbl_chuck_y,
            self.lbl_chuck_z,
            self.lbl_chuck_index,
        ):
            lbl.setStyleSheet("font-weight:bold;")

        self._refresh_sidebar_button_styles()

    def _append_home_abs_coord_log(self, x_um: float, y_um: float) -> None:
        self.txt_home_abs_coords.appendPlainText(f"{x_um:.4f},{y_um:.4f}")
        cursor = self.txt_home_abs_coords.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.txt_home_abs_coords.setTextCursor(cursor)

    def _on_move_chuck_relative(self) -> None:
        now_die_index_x = self.spin_instant_x.value()
        now_die_index_y = self.spin_instant_y.value()

        def action() -> None:
            self._chuck_motor.move_chuck_index_jump(now_die_index_x, now_die_index_y)
            d_x = now_die_index_x - self._chuck_motor.home_die_index_x
            d_y = now_die_index_y - self._chuck_motor.home_die_index_y
            x_um = (
                d_x * self._chuck_motor.Chuck_index_x_um
                + self._chuck_motor.home_abs_coord_x
            )
            y_um = (
                d_y * self._chuck_motor.Chuck_index_y_um
                + self._chuck_motor.home_abs_coord_y
            )
            self._append_home_abs_coord_log(x_um, y_um)

        self._run_motor_action(action)

    def _on_move_chuck_index_relative(self, num_x_index: int, num_y_index: int) -> None:
        self._run_motor_action(
            lambda: self._chuck_motor.move_chuck_index_relative(
                num_x_index, num_y_index
            )
        )

    def _on_move_chuck_contact(self) -> None:
        self._run_motor_action(self._chuck_motor.move_chuck_contact)

    def _on_move_chuck_seperation(self) -> None:
        self._run_motor_action(self._chuck_motor.move_chuck_seperation)

    def _on_set_chuck_contact(self) -> None:
        self._run_motor_action(self._chuck_motor.set_chuck_contact)

    def _on_move_chuck_load(self) -> None:
        self._run_motor_action(self._chuck_motor.move_chuck_load)

    def _on_set_chuck_home(self) -> None:
        home_die_index_x = self.spin_home_die_index_x.value()
        home_die_index_y = self.spin_home_die_index_y.value()

        def action() -> None:
            self._chuck_motor.set_chuck_home(home_die_index_x, home_die_index_y)
            self._append_home_abs_coord_log(
                self._chuck_motor.home_abs_coord_x,
                self._chuck_motor.home_abs_coord_y,
            )

        self._run_motor_action(action, use_cache=True)

    def _on_move_chuck_home(self) -> None:
        self._run_motor_action(self._chuck_motor.move_chuck_home)

    def _on_load_map(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "選擇 Wafer Map Excel 檔案",
            str(self._work_dir),
            "Excel Files (*.xlsx);;All Files (*)",
        )
        if not path:
            return
        try:
            data = load_wafer_map_xlsx(path)
            self._wafer_map_path = Path(path)
            self._wafer_map_data = data
            self.wafer_view.load_map(data)
            self._inspection_targets = extract_inspection_targets(data)
            self._update_map_info(data)
            self._update_statistics(data.die_count)
            self.setWindowTitle(f"Wafer Level Inspection - {Path(path).name}")
            if data.x_index is not None and data.y_index is not None:
                self._chuck_motor.set_chuck_index(data.x_index, data.y_index)
            else:
                QMessageBox.warning(
                    self,
                    "Index 間距未設定",
                    "Excel 第 1 列 C 欄 (X index) 或第 2 列 C 欄 (Y index) 無有效數值，"
                    "無法設定馬達 index 間距。",
                )
            self.btn_set.setEnabled(True)
            self.btn_start.setEnabled(False)
            self._datalog_session_dir = None
            self._datalog_open_dir = None
            self._datalog_watcher.reset_baseline()
        except Exception as exc:
            QMessageBox.critical(self, "載入失敗", f"無法讀取 Excel 檔案:\n{exc}")

    def _on_set(self) -> None:
        if self._inspection_targets is None:
            QMessageBox.warning(self, "Set", "請先載入 Wafer Map。")
            return
        if self._inspection_targets.count == 0:
            QMessageBox.warning(
                self,
                "Set",
                "此 Map 中沒有 bin=10 的待檢 die。",
            )
            return

        self._pending_inspection_count = self._inspection_targets.count
        self.lbl_pending.setText(str(self._pending_inspection_count))
        self.lbl_inspected.setText("0")
        self.btn_set.setEnabled(False)
        self.btn_start.setEnabled(True)

    def _on_start(self) -> None:
        if self._inspection_targets is None or self._pending_inspection_count == 0:
            QMessageBox.warning(self, "Start", "請先完成 Set 以確認待檢清單。")
            return
        instrument_window = self._measurement_instrument_window()
        if instrument_window is None:
            QMessageBox.warning(self, "Start", "未開啟儀器控制視窗。")
            return

        try:
            self._datalog_session_dir = create_session_dir(
                self._work_dir,
                self.edit_folder.toPlainText().replace("\n", "").replace("\r", ""),
            )
        except OSError as exc:
            QMessageBox.critical(self, "建立目錄失敗", f"無法建立 Datalog 目錄:\n{exc}")
            return

        if instrument_window.uses_statistics_report:
            try:
                init_statistics_report(
                    self._datalog_session_dir,
                    instrument_window.get_statistics_report_headers(),
                )
            except OSError as exc:
                QMessageBox.critical(
                    self, "建立統計報告失敗", f"無法建立統計報告:\n{exc}"
                )
                return

        self.btn_start.setEnabled(False)
        self.btn_pause.setEnabled(True)
        self.btn_pause.setText("Pause")
        self._measurement_good_count = 0
        self.lbl_good.setText("0")
        self.lbl_yield.setText("0.00%")
        self.lbl_all_inspected.setText("0")
        self._measurement_session = measure_Start(
            self,
            motor=self._chuck_motor,
            targets=self._inspection_targets,
            session_dir=self._datalog_session_dir,
            instrument_window=instrument_window,
            on_die_started=self._on_measure_die_started,
            on_die_measured=self._on_measure_die_measured,
            on_progress=self._on_measure_progress,
            on_complete=self._on_measure_complete,
        )
        self._measurement_session.paused.connect(self._on_measure_paused)
        self._measurement_session.resumed.connect(self._on_measure_resumed)

    def _on_pause(self) -> None:
        if self._measurement_session is None:
            return
        if self._measurement_session.is_paused:
            self._measurement_session.resume()
            self.btn_pause.setText("Pause")
        else:
            self._measurement_session.pause()
            self.btn_pause.setText("Resume")

    def _on_measure_paused(self) -> None:
        self.btn_pause.setText("Resume")

    def _on_measure_resumed(self) -> None:
        self.btn_pause.setText("Pause")

    def _on_measure_die_started(self, x_idx: int, y_idx: int) -> None:
        self.lbl_cur_x.setText(str(x_idx))
        self.lbl_cur_y.setText(str(y_idx))
        self.spin_x.setValue(x_idx)
        self.spin_y.setValue(y_idx)
        self.wafer_view.select_die(x_idx, y_idx)
        self._update_chuck_position_display()

    def _on_measure_die_measured(self, result: DieMeasurementResult) -> None:
        if self._wafer_map_data is not None:
            self._wafer_map_data.grid[(result.x, result.y)] = result.judgment_bin
        self.wafer_view.set_die_bin(result.x, result.y, result.judgment_bin)
        if result.judgment_bin == GOOD_DIE_BIN:
            self._measurement_good_count += 1
        self._update_measurement_yield()

    def _update_measurement_yield(self) -> None:
        inspected_text = self.lbl_inspected.text()
        try:
            inspected = int(inspected_text)
        except ValueError:
            inspected = 0
        good = self._measurement_good_count
        self.lbl_good.setText(str(good))
        self.lbl_all_inspected.setText(str(inspected))
        if inspected > 0:
            self.lbl_yield.setText(f"{good / inspected * 100:.2f}%")
        else:
            self.lbl_yield.setText("0.00%")

    def _on_measure_progress(self, inspected: int, total: int) -> None:
        pending = max(total - inspected, 0)
        self.lbl_inspected.setText(str(inspected))
        self.lbl_pending.setText(str(pending))

    def _on_measure_complete(self, results) -> None:
        self._measurement_session = None
        self.btn_pause.setEnabled(False)
        self.btn_pause.setText("Pause")
        if results:
            self._save_measurement_report()
        if not results:
            self.btn_start.setEnabled(True)

    def _save_measurement_report(self) -> None:
        if (
            self._wafer_map_path is None
            or self._wafer_map_data is None
            or self._datalog_session_dir is None
        ):
            return
        report_path = self._datalog_session_dir / "01_分布圖.xlsx"
        try:
            save_wafer_map_report(
                self._wafer_map_path,
                self._wafer_map_data,
                report_path,
            )
        except OSError as exc:
            QMessageBox.warning(
                self,
                "分布圖",
                f"無法儲存分布圖:\n{exc}",
            )

    def _on_datalog_detected(self, path: Path) -> None:
        self._datalog_open_dir = path

    def _update_map_info(self, data: WaferMapData) -> None:
        self.lbl_map_chuck_index_x.setText(
            str(data.x_index) if data.x_index is not None else "-"
        )
        self.lbl_map_chuck_index_y.setText(
            str(data.y_index) if data.y_index is not None else "-"
        )

    def _update_statistics(self, die_count: int) -> None:
        self.lbl_total.setText(str(die_count))
        self.lbl_pending.setText("0")
        self.lbl_inspected.setText("0")
        self.lbl_good.setText("0")
        self.lbl_all_inspected.setText("0")
        self.lbl_yield.setText("0.00%")
        self._measurement_good_count = 0
        self._pending_inspection_count = 0

    def _on_die_clicked(self, x_idx: int, y_idx: int, bin_value: int) -> None:
        self.lbl_cur_x.setText(str(x_idx))
        self.lbl_cur_y.setText(str(y_idx))
        self.spin_x.setValue(x_idx)
        self.spin_y.setValue(y_idx)

    def _on_zoom_changed(self, value: int) -> None:
        self.lbl_zoom.setText(str(value))
        self.wafer_view.set_zoom_percent(value)

def run_instrument_app(
    instrument_name: str, work_dir: Path | None = None
) -> int:
    import sys

    from PySide6.QtWidgets import QApplication

    from instruments.panels.registry import create_modular_instrument_window

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    base_dir = work_dir or Path.cwd()
    window = create_modular_instrument_window(
        instrument_name,
        work_dir=base_dir,
    )
    if window is None:
        print(f"尚未支援儀器面板：{instrument_name}", file=sys.stderr)
        return 1
    window.show()
    return app.exec()


def run_lcr_meter_app(work_dir: Path | None = None) -> int:
    return run_instrument_app("LCR Meter", work_dir=work_dir)


def run_app(work_dir: Path | None = None) -> int:
    import sys

    from guided_setup import GuidedSetupResult, GuidedSetupWindow

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    main_window: MainWindow | None = None

    def on_setup_finished(result: GuidedSetupResult) -> None:
        nonlocal main_window
        main_window = MainWindow(
            work_dir=work_dir,
            prober_type=result.prober_type,
            bm_model=result.bm_model.value if result.bm_model is not None else None,
            instrument_type=(
                result.instrument_type.value
                if result.instrument_type is not None
                else None
            ),
            tcp_client=result.tcp_client,
            asic_tcp_client=result.asic_tcp_client,
        )
        position_main_window_at_screen_left(main_window)
        main_window.show()

    wizard = GuidedSetupWindow(work_dir=work_dir)
    wizard.finished.connect(on_setup_finished)
    wizard.show()
    return app.exec()
