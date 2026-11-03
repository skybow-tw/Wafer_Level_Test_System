"""BMT3000 instrument panel layout."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis
from PySide6.QtCore import QMargins, Qt
from PySide6.QtGui import QPainter, QPen, QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from instruments.bmt_tcp import DEFAULT_BMT_TCP_PORT
from instruments.panels.common import mark_close_button, mark_start_button

_DEFAULT_BMT_TCP_IP = "127.0.0.1"
_IV_TABLE_ROWS = 10
_IV_TABLE_HEADERS = ("V_in", "V_Out", "I(mA)", "R(k歐姆)")
_CHART_PLOT_MARGINS = QMargins(56, 48, 56, 40)
_CHART_LAYOUT_MARGINS = (18, 18, 18, 18)
_CHART_Y_MAJOR_TICK_COUNT = 6


@dataclass
class Bmt3000Ui:
    root: QWidget
    edit_server_ip: QLineEdit
    edit_server_port: QLineEdit
    lbl_tcp_status: QLabel
    btn_connect: QPushButton
    btn_measure: QPushButton
    btn_read_pixel: QPushButton
    btn_exit: QPushButton
    iv_chart_view: QChartView
    iv_series: QLineSeries
    iv_axis_x: QValueAxis
    iv_axis_y: QValueAxis
    iv_table: QTableWidget
    tabs: QTabWidget


def _build_iv_chart() -> tuple[QChartView, QLineSeries, QValueAxis, QValueAxis]:
    series = QLineSeries()
    series.setName("IV")
    series.setPen(QPen(QColor("#1565C0"), 2.5))

    chart = QChart()
    chart.legend().setVisible(False)
    chart.setBackgroundVisible(True)
    chart.setTitle("IV curve")
    chart.setMargins(_CHART_PLOT_MARGINS)
    layout = chart.layout()
    if layout is not None:
        left, top, right, bottom = _CHART_LAYOUT_MARGINS
        layout.setContentsMargins(left, top, right, bottom)

    axis_x = QValueAxis()
    axis_x.setTitleText("電壓 (V)")
    axis_x.setTitleVisible(True)
    axis_x.setLabelsVisible(True)
    axis_x.setLabelFormat("%.2f")
    axis_x.setRange(0, 5)
    axis_x.setGridLineVisible(True)
    axis_x.setMinorGridLineVisible(False)

    axis_y = QValueAxis()
    axis_y.setTitleText("電流 (mA)")
    axis_y.setTitleVisible(True)
    axis_y.setLabelsVisible(True)
    axis_y.setLabelFormat("%.2f")
    axis_y.setRange(0, 1)
    axis_y.setTickCount(_CHART_Y_MAJOR_TICK_COUNT)
    axis_y.setGridLineVisible(True)
    axis_y.setMinorGridLineVisible(False)

    chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
    chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
    chart.addSeries(series)
    series.attachAxis(axis_x)
    series.attachAxis(axis_y)

    chart_view = QChartView(chart)
    chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
    chart_view.setSizePolicy(
        QSizePolicy.Policy.Expanding,
        QSizePolicy.Policy.Expanding,
    )
    chart_view.setMinimumHeight(280)
    return chart_view, series, axis_x, axis_y


def _build_iv_table() -> QTableWidget:
    table = QTableWidget(_IV_TABLE_ROWS, len(_IV_TABLE_HEADERS))
    table.setHorizontalHeaderLabels(list(_IV_TABLE_HEADERS))
    table.verticalHeader().setVisible(True)
    table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
    table.verticalHeader().setDefaultSectionSize(28)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.setAlternatingRowColors(True)
    table.setStyleSheet(
        "QTableWidget {"
        " background-color: #FFFFFF;"
        " alternate-background-color: #EAF1F7;"
        "}"
    )
    table.setMinimumHeight(320)
    return table


def build_bmt3000_ui() -> Bmt3000Ui:
    central = QWidget()
    outer = QVBoxLayout(central)
    outer.setContentsMargins(8, 8, 8, 8)
    outer.setSpacing(8)

    root = QHBoxLayout()
    root.setSpacing(2)
    root.setContentsMargins(0, 0, 0, 0)

    button_col = QVBoxLayout()
    button_col.setContentsMargins(0, 0, 0, 0)
    button_col.setSpacing(8)

    tcp_panel = QVBoxLayout()
    tcp_panel.setContentsMargins(0, 0, 0, 0)
    tcp_panel.setSpacing(2)

    ip_label = QLabel("Server IP")
    ip_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
    tcp_panel.addWidget(ip_label)

    edit_server_ip = QLineEdit(_DEFAULT_BMT_TCP_IP)
    edit_server_ip.setFixedWidth(160)
    tcp_panel.addWidget(edit_server_ip)

    port_label = QLabel("Port")
    port_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
    tcp_panel.addWidget(port_label)

    edit_server_port = QLineEdit(str(DEFAULT_BMT_TCP_PORT))
    edit_server_port.setFixedWidth(80)
    tcp_panel.addWidget(edit_server_port)

    lbl_tcp_status = QLabel("未連線")
    lbl_tcp_status.setAlignment(Qt.AlignmentFlag.AlignLeft)
    tcp_panel.addWidget(lbl_tcp_status)
    button_col.addLayout(tcp_panel)

    btn_connect: QPushButton | None = None
    btn_measure: QPushButton | None = None
    btn_read_pixel: QPushButton | None = None
    btn_exit: QPushButton | None = None

    for label in ("Connect", "Measure", "Calculate", "Exit"):
        button = QPushButton(label)
        button.setMinimumSize(120, 44)
        button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        if label == "Connect":
            btn_connect = button
            mark_start_button(button)
        elif label == "Measure":
            btn_measure = button
            button.setEnabled(False)
        elif label == "Calculate":
            btn_read_pixel = button
            button.setEnabled(False)
        else:
            btn_exit = button
            mark_close_button(button)
        button_col.addWidget(button)

    assert btn_connect is not None
    assert btn_measure is not None
    assert btn_read_pixel is not None
    assert btn_exit is not None

    button_col.addStretch()
    left_col_widget = QWidget()
    left_col_widget.setLayout(button_col)
    left_col_widget.setSizePolicy(
        QSizePolicy.Policy.Fixed,
        QSizePolicy.Policy.Preferred,
    )
    left_col_widget.setFixedWidth(left_col_widget.sizeHint().width())

    tabs = QTabWidget()
    iv_page = QWidget()
    iv_layout = QVBoxLayout(iv_page)
    iv_layout.setContentsMargins(4, 4, 4, 4)
    iv_layout.setSpacing(8)

    iv_chart_view, iv_series, iv_axis_x, iv_axis_y = _build_iv_chart()
    iv_table = _build_iv_table()
    iv_layout.addWidget(iv_chart_view, stretch=1)
    iv_layout.addWidget(iv_table, stretch=0)

    tabs.addTab(iv_page, "IV Curve")
    tabs.setCurrentIndex(0)

    root.addWidget(left_col_widget, 0)
    root.addWidget(tabs, stretch=1)
    outer.addLayout(root, stretch=1)

    return Bmt3000Ui(
        root=central,
        edit_server_ip=edit_server_ip,
        edit_server_port=edit_server_port,
        lbl_tcp_status=lbl_tcp_status,
        btn_connect=btn_connect,
        btn_measure=btn_measure,
        btn_read_pixel=btn_read_pixel,
        btn_exit=btn_exit,
        iv_chart_view=iv_chart_view,
        iv_series=iv_series,
        iv_axis_x=iv_axis_x,
        iv_axis_y=iv_axis_y,
        iv_table=iv_table,
        tabs=tabs,
    )
