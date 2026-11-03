"""DSA instrument panel layout (PXI-4461 frequency sweep)."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from instruments.panels.common import mark_close_button, mark_start_button
from instruments.pxi4461 import (
    PXI4461_DC_OFFSET_MAX_V,
    PXI4461_DC_OFFSET_MIN_V,
    PXI4461_MAX_FREQ_HZ,
    PXI4461_MIN_FREQ_HZ,
    PXI4461_POINT_COUNT_MAX,
    PXI4461_POINT_COUNT_MIN,
    PXI4461_VPP_MAX,
    PXI4461_VPP_MIN,
)

_SETTING_CONTROL_WIDTH = 120
_INNER_GROUP_WIDTH = _SETTING_CONTROL_WIDTH + 8
_SIGNAL_GROUP_WIDTH = _INNER_GROUP_WIDTH + 16
_KEY_PANEL_WIDTH = 320
_SWEEP_TABLE_HEADERS = ("Frequency(HZ)", "Magnitude(dB)", "Phase(deg)")


@dataclass
class DsaUi:
    root: QWidget
    spin_freq_start: QSpinBox
    spin_freq_stop: QSpinBox
    spin_point_count: QSpinBox
    spin_vpp: QDoubleSpinBox
    spin_dc_offset: QDoubleSpinBox
    chk_save_to_file: QCheckBox
    btn_measure: QPushButton
    btn_pause: QPushButton
    btn_exit: QPushButton
    chart_host: QWidget
    label_resonance: QLabel
    label_bandwidth: QLabel
    table_sweep: QTableWidget


def _action_button(label: str) -> QPushButton:
    button = QPushButton(label)
    button.setMinimumSize(120, 44)
    button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    return button


def _setting_row(label_text: str, control: QWidget) -> QVBoxLayout:
    row = QVBoxLayout()
    row.setSpacing(2)
    label = QLabel(label_text)
    label.setAlignment(Qt.AlignmentFlag.AlignLeft)
    control.setFixedWidth(_SETTING_CONTROL_WIDTH)
    row.addWidget(label)
    row.addWidget(control)
    return row


def _compact_group_box(group: QGroupBox, *, width: int = _INNER_GROUP_WIDTH) -> None:
    group.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
    group.setFixedWidth(width)


def _build_frequency_range_group() -> tuple[QGroupBox, QSpinBox, QSpinBox, QSpinBox]:
    group = QGroupBox("Frequency Range")
    layout = QVBoxLayout(group)
    layout.setContentsMargins(8, 12, 8, 8)
    layout.setSpacing(6)

    spin_freq_start = QSpinBox()
    spin_freq_start.setRange(int(PXI4461_MIN_FREQ_HZ), int(PXI4461_MAX_FREQ_HZ))
    spin_freq_start.setSingleStep(100)
    spin_freq_start.setValue(500)

    spin_freq_stop = QSpinBox()
    spin_freq_stop.setRange(int(PXI4461_MIN_FREQ_HZ), int(PXI4461_MAX_FREQ_HZ))
    spin_freq_stop.setSingleStep(100)
    spin_freq_stop.setValue(8_000)

    spin_point_count = QSpinBox()
    spin_point_count.setRange(PXI4461_POINT_COUNT_MIN, PXI4461_POINT_COUNT_MAX)
    spin_point_count.setSingleStep(1)
    spin_point_count.setValue(101)

    layout.addLayout(_setting_row("Start(500~99kHz)", spin_freq_start))
    layout.addLayout(_setting_row("Stop(500~99kHz)", spin_freq_stop))
    layout.addLayout(_setting_row("# of steps(1~1000)", spin_point_count))
    _compact_group_box(group)
    return group, spin_freq_start, spin_freq_stop, spin_point_count


def _build_sinewave_group() -> tuple[QGroupBox, QDoubleSpinBox, QDoubleSpinBox]:
    group = QGroupBox("Sinewave")
    layout = QVBoxLayout(group)
    layout.setContentsMargins(8, 12, 8, 8)
    layout.setSpacing(6)

    spin_vpp = QDoubleSpinBox()
    spin_vpp.setRange(PXI4461_VPP_MIN, PXI4461_VPP_MAX)
    spin_vpp.setDecimals(3)
    spin_vpp.setSingleStep(0.1)
    spin_vpp.setValue(1.0)

    spin_dc_offset = QDoubleSpinBox()
    spin_dc_offset.setRange(PXI4461_DC_OFFSET_MIN_V, PXI4461_DC_OFFSET_MAX_V)
    spin_dc_offset.setDecimals(3)
    spin_dc_offset.setSingleStep(0.1)
    spin_dc_offset.setValue(0.0)

    layout.addLayout(_setting_row("Vpp(V)", spin_vpp))
    layout.addLayout(_setting_row("DC Offset(V)", spin_dc_offset))
    _compact_group_box(group)
    return group, spin_vpp, spin_dc_offset


def _value_label() -> QLabel:
    label = QLabel("—")
    label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    label.setMinimumWidth(90)
    return label


def _build_key_value_group() -> tuple[QGroupBox, QLabel, QLabel]:
    group = QGroupBox("Key value")
    form = QFormLayout(group)
    form.setContentsMargins(10, 12, 10, 10)
    form.setSpacing(8)
    form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    label_resonance = _value_label()
    label_bandwidth = _value_label()
    form.addRow("共振頻率(HZ)", label_resonance)
    form.addRow("頻寬(HZ)", label_bandwidth)
    group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
    return group, label_resonance, label_bandwidth


def _build_sweep_table() -> QTableWidget:
    table = QTableWidget(0, len(_SWEEP_TABLE_HEADERS))
    table.setHorizontalHeaderLabels(list(_SWEEP_TABLE_HEADERS))
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(24)
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
    table.setAlternatingRowColors(True)
    table.setMinimumWidth(_KEY_PANEL_WIDTH)
    return table


def _build_results_panel() -> tuple[QWidget, QLabel, QLabel, QTableWidget]:
    panel = QWidget()
    panel.setFixedWidth(_KEY_PANEL_WIDTH)
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    key_group, label_resonance, label_bandwidth = _build_key_value_group()
    table = _build_sweep_table()
    layout.addWidget(key_group)
    layout.addWidget(table, stretch=1)
    return panel, label_resonance, label_bandwidth, table


def build_dsa_ui(chart_host: QWidget) -> DsaUi:
    central = QWidget()
    outer = QVBoxLayout(central)
    outer.setContentsMargins(8, 8, 8, 8)
    outer.setSpacing(8)

    root = QHBoxLayout()
    root.setSpacing(12)
    root.setContentsMargins(0, 0, 0, 0)

    left_col = QVBoxLayout()
    left_col.setContentsMargins(0, 0, 0, 0)
    left_col.setSpacing(10)

    signal_group = QGroupBox("Signal Settings")
    signal_group.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
    signal_group.setFixedWidth(_SIGNAL_GROUP_WIDTH)
    signal_layout = QVBoxLayout(signal_group)
    signal_layout.setContentsMargins(8, 12, 8, 8)
    signal_layout.setSpacing(8)

    freq_group, spin_freq_start, spin_freq_stop, spin_point_count = (
        _build_frequency_range_group()
    )
    sine_group, spin_vpp, spin_dc_offset = _build_sinewave_group()
    signal_layout.addWidget(freq_group)
    signal_layout.addWidget(sine_group)

    chk_save_to_file = QCheckBox("Save to file")
    chk_save_to_file.setChecked(True)
    btn_measure = _action_button("Measure")
    mark_start_button(btn_measure)
    btn_pause = _action_button("Pause")
    btn_pause.setEnabled(False)
    btn_exit = _action_button("Exit")
    mark_close_button(btn_exit)

    left_col.addWidget(signal_group)
    left_col.addWidget(chk_save_to_file, alignment=Qt.AlignmentFlag.AlignLeft)
    left_col.addWidget(btn_measure, alignment=Qt.AlignmentFlag.AlignLeft)
    left_col.addWidget(btn_pause, alignment=Qt.AlignmentFlag.AlignLeft)
    left_col.addWidget(btn_exit, alignment=Qt.AlignmentFlag.AlignLeft)
    left_col.addStretch()

    left_col_widget = QWidget()
    left_col_widget.setLayout(left_col)
    left_col_widget.setSizePolicy(
        QSizePolicy.Policy.Fixed,
        QSizePolicy.Policy.Preferred,
    )
    left_col_widget.setFixedWidth(max(left_col_widget.sizeHint().width(), 120))

    results_panel, label_resonance, label_bandwidth, table_sweep = (
        _build_results_panel()
    )
    charts_row = QWidget()
    charts_layout = QHBoxLayout(charts_row)
    charts_layout.setContentsMargins(0, 0, 0, 0)
    charts_layout.setSpacing(8)
    charts_layout.addWidget(chart_host, stretch=1)
    charts_layout.addWidget(results_panel, stretch=0)

    root.addWidget(left_col_widget, 0)
    root.addWidget(charts_row, stretch=1)
    outer.addLayout(root, stretch=1)

    return DsaUi(
        root=central,
        spin_freq_start=spin_freq_start,
        spin_freq_stop=spin_freq_stop,
        spin_point_count=spin_point_count,
        spin_vpp=spin_vpp,
        spin_dc_offset=spin_dc_offset,
        chk_save_to_file=chk_save_to_file,
        btn_measure=btn_measure,
        btn_pause=btn_pause,
        btn_exit=btn_exit,
        chart_host=chart_host,
        label_resonance=label_resonance,
        label_bandwidth=label_bandwidth,
        table_sweep=table_sweep,
    )
