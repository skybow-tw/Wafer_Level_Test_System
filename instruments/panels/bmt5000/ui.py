"""BMT5000 instrument panel layout."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from bmt_array_view import BmtArrayView, DATA_ARRAY_COLUMN_WIDTH
from instruments.panels.bmt.ui_helpers import (
    build_hex_param_row,
    build_pixel_param_panel,
)
from instruments.panels.common import mark_close_button, mark_start_button
from instruments.panels.widgets.usb_device_combo import UsbDeviceComboBox
from instruments.roic_adc_reader import ROIC_ADCReader

PIXEL_MODE_EASY = "easy"
PIXEL_MODE_STRING = "string"

_CONTENT_WIDTH = 260


@dataclass
class Bmt5000Ui:
    root: QWidget
    group_connection: QGroupBox
    group_register: QGroupBox
    group_pixel: QGroupBox
    cmb_usb_device: UsbDeviceComboBox
    btn_connect: QPushButton
    btn_read_register: QPushButton
    btn_read_pixel: QPushButton
    btn_exit: QPushButton
    cmb_device_id: QComboBox
    cmb_offset: QComboBox
    cmb_length: QComboBox
    pixel_param_panel: QWidget
    cmb_s_h_ibs: QComboBox
    cmb_ctia_ibs: QComboBox
    cmb_buff_ibs: QComboBox
    cmb_int_time: QComboBox
    cmb_period: QComboBox
    cmb_adc_off: QComboBox
    cmb_enable_rr: QComboBox
    radio_easy_mode: QRadioButton
    radio_string_mode: QRadioButton
    pixel_mode_group: QButtonGroup
    pixel_mode_stack: QStackedWidget
    edit_easy_command_preview: QLineEdit
    edit_pixel_command: QLineEdit
    register_map_view: BmtArrayView
    array_view: BmtArrayView
    tabs: QTabWidget


def _action_button(label: str) -> QPushButton:
    button = QPushButton(label)
    button.setMinimumSize(120, 44)
    button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    return button


def _build_connection_group() -> tuple[QGroupBox, UsbDeviceComboBox, QPushButton]:
    group = QGroupBox("連線")
    layout = QVBoxLayout(group)
    layout.setContentsMargins(8, 12, 8, 8)
    layout.setSpacing(6)

    usb_label = QLabel("USB device")
    usb_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
    layout.addWidget(usb_label)

    cmb_usb = UsbDeviceComboBox()
    cmb_usb.setPlaceholderText("按下選單掃描 USB…")
    cmb_usb.setMinimumWidth(_CONTENT_WIDTH)
    cmb_usb.setMaximumWidth(_CONTENT_WIDTH)
    cmb_usb.setSizeAdjustPolicy(
        QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
    )
    cmb_usb.setMinimumContentsLength(28)
    cmb_usb.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    layout.addWidget(cmb_usb)

    btn_connect = _action_button("Connect")
    mark_start_button(btn_connect)
    layout.addWidget(btn_connect, alignment=Qt.AlignmentFlag.AlignLeft)
    return group, cmb_usb, btn_connect


def _build_register_group() -> (
    tuple[QGroupBox, QComboBox, QComboBox, QComboBox, QPushButton]
):
    group = QGroupBox("Read Register")
    layout = QVBoxLayout(group)
    layout.setContentsMargins(8, 12, 8, 8)
    layout.setSpacing(6)

    hex_row, device_id, offset, length = build_hex_param_row(usb_width=_CONTENT_WIDTH)
    hex_row.layout().setContentsMargins(0, 0, 0, 0)
    register_tip = "設定 Device ID / Register / Length 後讀取。"
    device_id.setToolTip(register_tip)
    offset.setToolTip(register_tip)
    length.setToolTip(register_tip)
    layout.addWidget(hex_row)

    btn_read_register = _action_button("Read Register")
    layout.addWidget(btn_read_register, alignment=Qt.AlignmentFlag.AlignLeft)
    return group, device_id, offset, length, btn_read_register


def _build_pixel_group() -> tuple[
    QGroupBox,
    QWidget,
    QComboBox,
    QComboBox,
    QComboBox,
    QComboBox,
    QComboBox,
    QComboBox,
    QComboBox,
    QRadioButton,
    QRadioButton,
    QButtonGroup,
    QStackedWidget,
    QLineEdit,
    QLineEdit,
    QPushButton,
]:
    group = QGroupBox("Read Pixel")
    layout = QVBoxLayout(group)
    layout.setContentsMargins(8, 12, 8, 8)
    layout.setSpacing(6)

    mode_row = QHBoxLayout()
    mode_row.setContentsMargins(0, 0, 0, 0)
    mode_row.setSpacing(12)
    mode_tip = "先選模式，再設定參數或命令字串。"
    radio_easy = QRadioButton("參數模式")
    radio_string = QRadioButton("工程模式")
    radio_easy.setToolTip(mode_tip)
    radio_string.setToolTip(mode_tip)
    radio_easy.setChecked(True)
    mode_group = QButtonGroup(group)
    mode_group.addButton(radio_easy)
    mode_group.addButton(radio_string)
    mode_row.addWidget(radio_easy)
    mode_row.addWidget(radio_string)
    mode_row.addStretch()
    layout.addLayout(mode_row)

    pixel_panel, s_h, ctia, buff, int_time, period, adc_off, enable_rr = (
        build_pixel_param_panel(usb_width=_CONTENT_WIDTH)
    )
    pixel_panel.layout().setContentsMargins(0, 0, 0, 0)

    easy_page = QWidget()
    easy_layout = QVBoxLayout(easy_page)
    easy_layout.setContentsMargins(0, 0, 0, 0)
    easy_layout.setSpacing(4)
    easy_layout.addWidget(pixel_panel)
    preview_label = QLabel("命令字串（根據上方參數組成）")
    preview_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
    easy_layout.addWidget(preview_label)
    edit_preview = QLineEdit()
    edit_preview.setReadOnly(True)
    edit_preview.setPlaceholderText("由上方下拉選單組成")
    easy_layout.addWidget(edit_preview)

    string_page = QWidget()
    string_layout = QVBoxLayout(string_page)
    string_layout.setContentsMargins(0, 0, 0, 0)
    string_layout.setSpacing(4)
    cmd_label = QLabel("命令字串(手動輸入)")
    cmd_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
    string_layout.addWidget(cmd_label)
    edit_command = QLineEdit()
    edit_command.setPlaceholderText("例如 384E0001100A0A0000")
    string_layout.addWidget(edit_command)
    string_layout.addStretch()

    mode_stack = QStackedWidget()
    mode_stack.addWidget(easy_page)  # index 0
    mode_stack.addWidget(string_page)  # index 1
    mode_stack.setCurrentIndex(0)
    layout.addWidget(mode_stack)

    btn_read_pixel = _action_button("Read Pixel")
    layout.addWidget(btn_read_pixel, alignment=Qt.AlignmentFlag.AlignLeft)

    return (
        group,
        pixel_panel,
        s_h,
        ctia,
        buff,
        int_time,
        period,
        adc_off,
        enable_rr,
        radio_easy,
        radio_string,
        mode_group,
        mode_stack,
        edit_preview,
        edit_command,
        btn_read_pixel,
    )


def build_bmt5000_ui() -> Bmt5000Ui:
    central = QWidget()
    outer = QVBoxLayout(central)
    outer.setContentsMargins(8, 8, 8, 8)
    outer.setSpacing(8)

    root = QHBoxLayout()
    root.setSpacing(8)
    root.setContentsMargins(0, 0, 0, 0)

    left_col = QVBoxLayout()
    left_col.setContentsMargins(0, 0, 0, 0)
    left_col.setSpacing(10)

    group_connection, cmb_usb, btn_connect = _build_connection_group()
    (
        group_register,
        device_id,
        offset,
        length,
        btn_read_register,
    ) = _build_register_group()
    (
        group_pixel,
        pixel_panel,
        s_h,
        ctia,
        buff,
        int_time,
        period,
        adc_off,
        enable_rr,
        radio_easy,
        radio_string,
        mode_group,
        mode_stack,
        edit_preview,
        edit_command,
        btn_read_pixel,
    ) = _build_pixel_group()

    # Require USB connection before register / pixel operations.
    group_register.setEnabled(False)
    group_pixel.setEnabled(False)

    btn_exit = _action_button("Exit")
    mark_close_button(btn_exit)

    left_col.addWidget(group_connection)
    left_col.addWidget(group_register)
    left_col.addWidget(group_pixel)
    left_col.addWidget(btn_exit, alignment=Qt.AlignmentFlag.AlignLeft)
    left_col.addStretch()

    left_col_widget = QWidget()
    left_col_widget.setLayout(left_col)
    left_col_widget.setSizePolicy(
        QSizePolicy.Policy.Fixed,
        QSizePolicy.Policy.Preferred,
    )
    left_col_widget.setFixedWidth(max(left_col_widget.sizeHint().width(), 300))

    tabs = QTabWidget()
    register_page = QWidget()
    register_layout = QVBoxLayout(register_page)
    register_layout.setContentsMargins(0, 0, 0, 0)
    register_view = BmtArrayView()
    register_view.load_register_map()
    register_layout.addWidget(register_view, stretch=1)
    tabs.addTab(register_page, "Register Map")

    array_page = QWidget()
    array_layout = QVBoxLayout(array_page)
    array_layout.setContentsMargins(0, 0, 0, 0)
    array_view = BmtArrayView(column_width=DATA_ARRAY_COLUMN_WIDTH)
    array_view.load_array(ROIC_ADCReader.ROW, ROIC_ADCReader.COL)
    array_layout.addWidget(array_view, stretch=1)
    tabs.addTab(array_page, "Data Array")

    page3 = QWidget()
    page3_layout = QVBoxLayout(page3)
    page3_layout.setContentsMargins(8, 8, 8, 8)
    page3_layout.addWidget(QLabel("Page 3"))
    page3_layout.addStretch()
    tabs.addTab(page3, "Page 3")
    tabs.setCurrentIndex(0)

    root.addWidget(left_col_widget, 0)
    root.addWidget(tabs, stretch=1)
    outer.addLayout(root, stretch=1)

    return Bmt5000Ui(
        root=central,
        group_connection=group_connection,
        group_register=group_register,
        group_pixel=group_pixel,
        cmb_usb_device=cmb_usb,
        btn_connect=btn_connect,
        btn_read_register=btn_read_register,
        btn_read_pixel=btn_read_pixel,
        btn_exit=btn_exit,
        cmb_device_id=device_id,
        cmb_offset=offset,
        cmb_length=length,
        pixel_param_panel=pixel_panel,
        cmb_s_h_ibs=s_h,
        cmb_ctia_ibs=ctia,
        cmb_buff_ibs=buff,
        cmb_int_time=int_time,
        cmb_period=period,
        cmb_adc_off=adc_off,
        cmb_enable_rr=enable_rr,
        radio_easy_mode=radio_easy,
        radio_string_mode=radio_string,
        pixel_mode_group=mode_group,
        pixel_mode_stack=mode_stack,
        edit_easy_command_preview=edit_preview,
        edit_pixel_command=edit_command,
        register_map_view=register_view,
        array_view=array_view,
        tabs=tabs,
    )
