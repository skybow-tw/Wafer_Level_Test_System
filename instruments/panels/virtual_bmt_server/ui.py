"""Virtual BMT TCP server panel layout."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from instruments.bmt_tcp import DEFAULT_BMT_TCP_PORT
from instruments.panels.common import mark_close_button, mark_start_button
from instruments.panels.virtual_bmt_server.logic import DEFAULT_BIND_HOST


@dataclass
class VirtualBmtServerUi:
    root: QWidget
    edit_host: QLineEdit
    spin_port: QSpinBox
    lbl_server_status: QLabel
    lbl_client_count: QLabel
    btn_start: QPushButton
    btn_stop: QPushButton
    btn_clear_log: QPushButton
    btn_exit: QPushButton
    log_view: QPlainTextEdit


def build_virtual_bmt_server_ui() -> VirtualBmtServerUi:
    root = QWidget()
    root.setObjectName("virtualBmtServerRoot")
    layout = QVBoxLayout(root)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(12)

    title = QLabel("Virtual BMT TCP Server")
    title.setObjectName("virtualBmtServerTitle")
    title.setStyleSheet("font-size: 18px; font-weight: 600;")
    layout.addWidget(title)

    subtitle = QLabel(
        "模擬 BMT Server：多 client、4-byte 長度標頭協議，"
        "Measure(Q) 回傳虛擬 IV 資料供 BMT3000 畫圖。"
    )
    subtitle.setWordWrap(True)
    subtitle.setStyleSheet("color: #555555;")
    layout.addWidget(subtitle)

    bind_box = QGroupBox("監聽設定")
    bind_form = QFormLayout(bind_box)
    bind_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

    edit_host = QLineEdit(DEFAULT_BIND_HOST)
    edit_host.setPlaceholderText("0.0.0.0 或 127.0.0.1")
    edit_host.setClearButtonEnabled(True)

    spin_port = QSpinBox()
    spin_port.setRange(1, 65535)
    spin_port.setValue(DEFAULT_BMT_TCP_PORT)
    spin_port.setKeyboardTracking(False)

    bind_form.addRow("Host", edit_host)
    bind_form.addRow("Port", spin_port)
    layout.addWidget(bind_box)

    status_box = QGroupBox("狀態")
    status_layout = QFormLayout(status_box)
    status_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

    lbl_server_status = QLabel("關閉")
    lbl_server_status.setObjectName("virtualBmtServerStatus")
    lbl_server_status.setStyleSheet("font-weight: 600; color: #B71C1C;")

    lbl_client_count = QLabel("0")
    lbl_client_count.setObjectName("virtualBmtClientCount")
    lbl_client_count.setStyleSheet("font-weight: 600;")

    status_layout.addRow("Server", lbl_server_status)
    status_layout.addRow("連線 Client 數", lbl_client_count)
    layout.addWidget(status_box)

    button_row = QHBoxLayout()
    button_row.setSpacing(8)

    btn_start = QPushButton("Start Server")
    mark_start_button(btn_start)
    btn_start.setMinimumWidth(120)

    btn_stop = QPushButton("Stop Server")
    btn_stop.setEnabled(False)
    btn_stop.setMinimumWidth(120)

    btn_clear_log = QPushButton("清除 Log")
    btn_exit = QPushButton("Exit")
    mark_close_button(btn_exit)

    button_row.addWidget(btn_start)
    button_row.addWidget(btn_stop)
    button_row.addWidget(btn_clear_log)
    button_row.addStretch(1)
    button_row.addWidget(btn_exit)
    layout.addLayout(button_row)

    log_box = QGroupBox("事件 Log")
    log_layout = QVBoxLayout(log_box)
    log_view = QPlainTextEdit()
    log_view.setReadOnly(True)
    log_view.setMaximumBlockCount(2000)
    log_view.setPlaceholderText("Server 事件會顯示在這裡…")
    log_view.setMinimumHeight(280)
    log_layout.addWidget(log_view)
    layout.addWidget(log_box, stretch=1)

    return VirtualBmtServerUi(
        root=root,
        edit_host=edit_host,
        spin_port=spin_port,
        lbl_server_status=lbl_server_status,
        lbl_client_count=lbl_client_count,
        btn_start=btn_start,
        btn_stop=btn_stop,
        btn_clear_log=btn_clear_log,
        btn_exit=btn_exit,
        log_view=log_view,
    )
