"""Real LCR Meter instrument panel layout."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from instruments.e4980a import (
    E4980A_CABLE_LENGTHS_M,
    E4980A_DC_OFFSET_MAX_V,
    E4980A_DC_OFFSET_MIN_V,
    E4980A_FREQ_MAX_HZ,
    E4980A_FREQ_MIN_HZ,
    E4980A_IMPEDANCE_FUNCTIONS,
    E4980A_VOLTAGE_MAX_V,
    E4980A_VOLTAGE_MIN_V,
)
from instruments.panels.common import mark_close_button, mark_start_button
from instruments.panels.lcr_meter.constants import (
    VP_DETECT_METHOD_2_POINT_SLOPE,
    VP_DETECT_METHOD_AVERAGE,
    VP_SLOPE_DELTA_CAP_THRESHOLD_FF,
)
from instruments.panels.widgets.gpib_instrument_combo import GpibInstrumentComboBox

_GPIB_WIDTH = 200
_COMPACT_CONTROL_WIDTH = 60
_FUNCTION_WIDTH = _COMPACT_CONTROL_WIDTH + 5
_SPIN_WIDTH = 120
_SPIN_MIN_HEIGHT = 26
_BUTTON_MIN_WIDTH = 120
_BUTTON_MIN_HEIGHT = 44
_CHART_ASPECT_W = 16
_CHART_ASPECT_H = 9
_KEY_VALUE_FONT_PT = 18
_KEY_VALUE_WIDTH = 160


@dataclass
class LcrMeterUi:
    root: QWidget
    cmb_gpib: GpibInstrumentComboBox
    cmb_cable_length: QComboBox
    btn_open_correction: QPushButton
    btn_short_correction: QPushButton
    cmb_function: QComboBox
    spin_frequency: QDoubleSpinBox
    spin_voltage: QDoubleSpinBox
    spin_dc_offset_start: QDoubleSpinBox
    spin_dc_offset_stop: QDoubleSpinBox
    spin_dc_offset_step: QDoubleSpinBox
    btn_start: QPushButton
    chk_save_to_file: QCheckBox
    btn_exit: QPushButton
    cmb_vp_detect_method: QComboBox
    spin_vp_threshold_f: QDoubleSpinBox
    chart_host: QWidget
    label_c0: QLabel
    label_vp: QLabel
    label_r0: QLabel
    label_delta_c: QLabel


def _configure_spin(spin: QDoubleSpinBox, *, width: int) -> None:
    spin.setFixedWidth(width)
    spin.setMinimumHeight(_SPIN_MIN_HEIGHT)
    spin.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)


def _correction_button(label: str) -> QPushButton:
    button = QPushButton(label)
    button.setMinimumSize(_COMPACT_CONTROL_WIDTH, _SPIN_MIN_HEIGHT)
    button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    return button


def _action_button(label: str) -> QPushButton:
    button = QPushButton(label)
    button.setMinimumSize(_BUTTON_MIN_WIDTH, _BUTTON_MIN_HEIGHT)
    button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    return button


class _AspectRatioHost(QWidget):
    """Sizes a child to the largest box that fits this host at a fixed ratio."""

    def __init__(self, child: QWidget, ratio_w: int, ratio_h: int) -> None:
        super().__init__()
        self._child = child
        self._ratio_w = ratio_w
        self._ratio_h = ratio_h
        child.setParent(self)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Maximum,
        )

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return max(width * self._ratio_h // self._ratio_w, 1)

    def sizeHint(self) -> QSize:
        width = max(self.width(), self._child.minimumWidth(), 1)
        return QSize(width, self.heightForWidth(width))

    def resizeEvent(self, event) -> None:  # noqa: ANN001
        super().resizeEvent(event)
        box_w = max(self.width(), 1)
        box_h = max(self.height(), 1)
        target_h = box_w * self._ratio_h // self._ratio_w
        if target_h > box_h:
            target_h = box_h
            target_w = box_h * self._ratio_w // self._ratio_h
        else:
            target_w = box_w
        self._child.setGeometry(0, 0, target_w, target_h)


def _key_value_font() -> QFont:
    font = QFont()
    font.setPointSize(_KEY_VALUE_FONT_PT)
    return font


def _result_value_label() -> QLabel:
    label = QLabel("—")
    label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    label.setFont(_key_value_font())
    label.setMinimumHeight(_SPIN_MIN_HEIGHT)
    label.setFixedWidth(_KEY_VALUE_WIDTH)
    label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    return label


def _key_value_setting_row(title: str, value: QLabel) -> QVBoxLayout:
    row = QVBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(2)
    heading = QLabel(title)
    heading.setAlignment(Qt.AlignmentFlag.AlignLeft)
    heading.setFont(_key_value_font())
    heading.setFixedWidth(_KEY_VALUE_WIDTH)
    heading.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    row.addWidget(heading)
    row.addWidget(value)
    return row


def _build_results_group() -> tuple[QGroupBox, QLabel, QLabel, QLabel, QLabel]:
    group = QGroupBox("Key Value")
    group.setFont(_key_value_font())
    layout = QVBoxLayout(group)
    layout.setContentsMargins(8, 12, 8, 8)
    layout.setSpacing(8)

    label_c0 = _result_value_label()
    label_vp = _result_value_label()
    label_r0 = _result_value_label()
    label_delta_c = _result_value_label()

    row_top = QHBoxLayout()
    row_top.setContentsMargins(0, 0, 0, 0)
    row_top.setSpacing(8)
    row_top.addLayout(_key_value_setting_row("C0 (fF)", label_c0))
    row_top.addLayout(_key_value_setting_row("Vp (V)", label_vp))

    row_bottom = QHBoxLayout()
    row_bottom.setContentsMargins(0, 0, 0, 0)
    row_bottom.setSpacing(8)
    row_bottom.addLayout(_key_value_setting_row("R0 (Ω)", label_r0))
    row_bottom.addLayout(_key_value_setting_row("deltaC (fF)", label_delta_c))

    layout.addLayout(row_top)
    layout.addLayout(row_bottom)
    group.setSizePolicy(
        QSizePolicy.Policy.Fixed,
        QSizePolicy.Policy.Minimum,
    )
    layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
    return group, label_c0, label_vp, label_r0, label_delta_c


def _lcr_setting_row(
    label_text: str,
    control: QWidget,
    control_width: int = _SPIN_WIDTH,
    *,
    tooltip: str | None = None,
) -> QVBoxLayout:
    row = QVBoxLayout()
    row.setSpacing(2)
    label = QLabel(label_text)
    label.setAlignment(Qt.AlignmentFlag.AlignLeft)
    row.addWidget(label)
    control.setFixedWidth(control_width)
    if tooltip:
        label.setToolTip(tooltip)
        control.setToolTip(tooltip)
    row.addWidget(control)
    return row


def _build_vp_detect_method_widget() -> tuple[QWidget, QComboBox, QDoubleSpinBox]:
    widget = QWidget()
    widget.setSizePolicy(
        QSizePolicy.Policy.Maximum,
        QSizePolicy.Policy.Fixed,
    )
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)
    layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

    method_col = QVBoxLayout()
    method_col.setContentsMargins(0, 0, 0, 0)
    method_col.setSpacing(1)
    label = QLabel("Vp Detect Method")
    label.setAlignment(Qt.AlignmentFlag.AlignLeft)
    method_col.addWidget(label)

    combo = QComboBox()
    combo.addItems([VP_DETECT_METHOD_2_POINT_SLOPE, VP_DETECT_METHOD_AVERAGE])
    combo.setCurrentText(VP_DETECT_METHOD_2_POINT_SLOPE)
    combo.setFixedWidth(120)
    method_col.addWidget(combo, alignment=Qt.AlignmentFlag.AlignLeft)
    layout.addLayout(method_col)

    threshold_col = QVBoxLayout()
    threshold_col.setContentsMargins(0, 0, 0, 0)
    threshold_col.setSpacing(1)
    threshold_label = QLabel("Vp門檻值(fF)")
    threshold_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
    threshold_col.addWidget(threshold_label)

    threshold_spin = QDoubleSpinBox()
    threshold_spin.setDecimals(1)
    threshold_spin.setRange(0.0, 1_000_000.0)
    threshold_spin.setSingleStep(1.0)
    threshold_spin.setValue(VP_SLOPE_DELTA_CAP_THRESHOLD_FF)
    threshold_spin.setFixedWidth(90)
    threshold_spin.setMinimumHeight(_SPIN_MIN_HEIGHT)
    threshold_col.addWidget(threshold_spin, alignment=Qt.AlignmentFlag.AlignLeft)
    layout.addLayout(threshold_col)
    return widget, combo, threshold_spin


def _build_open_short_correction_group() -> tuple[QGroupBox, QComboBox, QPushButton, QPushButton]:
    group = QGroupBox("Open-Short Correction")
    layout = QHBoxLayout(group)
    layout.setContentsMargins(8, 12, 8, 8)
    layout.setSpacing(8)

    cmb_cable_length = QComboBox()
    for length_m in E4980A_CABLE_LENGTHS_M:
        cmb_cable_length.addItem(f"{length_m} m", length_m)
    cmb_cable_length.setFixedWidth(_COMPACT_CONTROL_WIDTH)
    cmb_cable_length.setMinimumHeight(_SPIN_MIN_HEIGHT)

    btn_open_correction = _correction_button("Open")
    btn_short_correction = _correction_button("Short")

    layout.addLayout(
        _lcr_setting_row("Cable Length", cmb_cable_length, _COMPACT_CONTROL_WIDTH)
    )
    layout.addLayout(
        _lcr_setting_row("Open", btn_open_correction, _COMPACT_CONTROL_WIDTH)
    )
    layout.addLayout(
        _lcr_setting_row("Short", btn_short_correction, _COMPACT_CONTROL_WIDTH)
    )

    group.setSizePolicy(
        QSizePolicy.Policy.Fixed,
        QSizePolicy.Policy.Minimum,
    )
    layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
    return group, cmb_cable_length, btn_open_correction, btn_short_correction


def _build_lcr_settings_panel(*, amplitude_mode: bool = False) -> tuple[
    QVBoxLayout,
    GpibInstrumentComboBox,
    QComboBox,
    QPushButton,
    QPushButton,
    QComboBox,
    QDoubleSpinBox,
    QDoubleSpinBox,
    QDoubleSpinBox,
    QDoubleSpinBox,
    QDoubleSpinBox,
]:
    panel = QVBoxLayout()
    panel.setContentsMargins(0, 0, 0, 0)
    panel.setSpacing(6)
    panel.setAlignment(Qt.AlignmentFlag.AlignLeft)

    cmb_gpib = GpibInstrumentComboBox()
    cmb_gpib.setPlaceholderText("按下選單掃描儀器…")
    cmb_gpib.setFixedWidth(_GPIB_WIDTH)
    cmb_gpib.setMinimumHeight(_SPIN_MIN_HEIGHT)
    panel.addLayout(_lcr_setting_row("GPIB 儀器", cmb_gpib, _GPIB_WIDTH))

    (
        correction_group,
        cmb_cable_length,
        btn_open_correction,
        btn_short_correction,
    ) = _build_open_short_correction_group()
    panel.addWidget(correction_group, alignment=Qt.AlignmentFlag.AlignLeft)

    cmb_function = QComboBox()
    cmb_function.addItems(list(E4980A_IMPEDANCE_FUNCTIONS))
    cmb_function.setCurrentText("Cp-Rp")

    spin_frequency = QDoubleSpinBox()
    spin_frequency.setRange(E4980A_FREQ_MIN_HZ, E4980A_FREQ_MAX_HZ)
    spin_frequency.setDecimals(0)
    spin_frequency.setSingleStep(100.0)
    spin_frequency.setValue(1_000.0)

    spin_voltage = QDoubleSpinBox()
    spin_voltage.setRange(E4980A_VOLTAGE_MIN_V, E4980A_VOLTAGE_MAX_V)
    spin_voltage.setDecimals(3)
    spin_voltage.setSingleStep(0.01)
    spin_voltage.setValue(1.0)

    cmb_function.setFixedWidth(_FUNCTION_WIDTH)
    cmb_function.setMinimumHeight(_SPIN_MIN_HEIGHT)
    _configure_spin(spin_frequency, width=_COMPACT_CONTROL_WIDTH)
    _configure_spin(spin_voltage, width=_COMPACT_CONTROL_WIDTH)

    function_row = QWidget()
    function_layout = QHBoxLayout(function_row)
    function_layout.setContentsMargins(0, 0, 0, 0)
    function_layout.setSpacing(8)
    function_layout.addLayout(
        _lcr_setting_row("Function", cmb_function, _FUNCTION_WIDTH)
    )
    function_layout.addLayout(
        _lcr_setting_row("Frequency(Hz)", spin_frequency, _COMPACT_CONTROL_WIDTH)
    )
    if not amplitude_mode:
        function_layout.addLayout(
            _lcr_setting_row(
                "Level(V)",
                spin_voltage,
                _COMPACT_CONTROL_WIDTH,
                tooltip="Level=Vrms=0.707Vpp",
            )
        )
    function_row.setSizePolicy(
        QSizePolicy.Policy.Fixed,
        QSizePolicy.Policy.Preferred,
    )
    panel.addWidget(function_row, alignment=Qt.AlignmentFlag.AlignLeft)

    spin_dc_offset_start = QDoubleSpinBox()
    spin_dc_offset_start.setRange(
        E4980A_VOLTAGE_MIN_V if amplitude_mode else E4980A_DC_OFFSET_MIN_V,
        E4980A_VOLTAGE_MAX_V if amplitude_mode else E4980A_DC_OFFSET_MAX_V,
    )
    spin_dc_offset_start.setDecimals(2)
    spin_dc_offset_start.setSingleStep(0.01)
    spin_dc_offset_start.setValue(E4980A_VOLTAGE_MIN_V if amplitude_mode else 0.0)
    spin_dc_offset_stop = QDoubleSpinBox()
    spin_dc_offset_stop.setRange(
        E4980A_VOLTAGE_MIN_V if amplitude_mode else E4980A_DC_OFFSET_MIN_V,
        E4980A_VOLTAGE_MAX_V if amplitude_mode else E4980A_DC_OFFSET_MAX_V,
    )
    spin_dc_offset_stop.setDecimals(2)
    spin_dc_offset_stop.setSingleStep(0.01)
    spin_dc_offset_stop.setValue(E4980A_VOLTAGE_MAX_V if amplitude_mode else 20.0)
    spin_dc_offset_step = QDoubleSpinBox()
    spin_dc_offset_step.setRange(
        0.001 if amplitude_mode else 0.01,
        2.0 if amplitude_mode else 100.0,
    )
    spin_dc_offset_step.setDecimals(3 if amplitude_mode else 2)
    spin_dc_offset_step.setSingleStep(0.001 if amplitude_mode else 0.01)
    spin_dc_offset_step.setValue(0.01 if amplitude_mode else 1.0)
    if amplitude_mode:
        spin_dc_offset_start.setDecimals(3)
        spin_dc_offset_stop.setDecimals(3)

    _configure_spin(spin_dc_offset_start, width=_COMPACT_CONTROL_WIDTH)
    _configure_spin(spin_dc_offset_stop, width=_COMPACT_CONTROL_WIDTH)
    _configure_spin(spin_dc_offset_step, width=_COMPACT_CONTROL_WIDTH)

    dc_offset_group = QGroupBox("Amplitude" if amplitude_mode else "DC offset")
    dc_offset_layout = QHBoxLayout(dc_offset_group)
    dc_offset_layout.setContentsMargins(8, 12, 8, 8)
    dc_offset_layout.setSpacing(8)
    dc_offset_layout.addLayout(
        _lcr_setting_row("Start (V)", spin_dc_offset_start, _COMPACT_CONTROL_WIDTH)
    )
    dc_offset_layout.addLayout(
        _lcr_setting_row("Stop (V)", spin_dc_offset_stop, _COMPACT_CONTROL_WIDTH)
    )
    dc_offset_layout.addLayout(
        _lcr_setting_row("Step(V)", spin_dc_offset_step, _COMPACT_CONTROL_WIDTH)
    )
    dc_offset_group.setSizePolicy(
        QSizePolicy.Policy.Fixed,
        QSizePolicy.Policy.Minimum,
    )
    dc_offset_layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
    panel.addWidget(dc_offset_group, alignment=Qt.AlignmentFlag.AlignLeft)

    return (
        panel,
        cmb_gpib,
        cmb_cable_length,
        btn_open_correction,
        btn_short_correction,
        cmb_function,
        spin_frequency,
        spin_voltage,
        spin_dc_offset_start,
        spin_dc_offset_stop,
        spin_dc_offset_step,
    )


def build_lcr_meter_ui(chart_view: QWidget, *, amplitude_mode: bool = False) -> LcrMeterUi:
    central = QWidget()
    outer = QVBoxLayout(central)
    outer.setContentsMargins(8, 8, 8, 8)
    outer.setSpacing(8)

    root = QHBoxLayout()
    root.setSpacing(8)
    root.setContentsMargins(0, 0, 0, 0)

    button_col = QVBoxLayout()
    button_col.setContentsMargins(0, 0, 0, 0)
    button_col.setSpacing(8)

    (
        settings_panel,
        cmb_gpib,
        cmb_cable_length,
        btn_open_correction,
        btn_short_correction,
        cmb_function,
        spin_frequency,
        spin_voltage,
        spin_dc_offset_start,
        spin_dc_offset_stop,
        spin_dc_offset_step,
    ) = _build_lcr_settings_panel(amplitude_mode=amplitude_mode)
    button_col.addLayout(settings_panel)

    vp_widget, cmb_vp_detect_method, spin_vp_threshold_f = (
        _build_vp_detect_method_widget()
    )
    button_col.addWidget(vp_widget, alignment=Qt.AlignmentFlag.AlignLeft)

    chk_save_to_file = QCheckBox("Save to file")
    chk_save_to_file.setChecked(True)
    button_col.addWidget(chk_save_to_file, alignment=Qt.AlignmentFlag.AlignLeft)

    btn_start = _action_button("Measure")
    mark_start_button(btn_start)
    button_col.addWidget(btn_start)

    btn_exit = _action_button("Exit")
    mark_close_button(btn_exit)
    button_col.addWidget(btn_exit)
    button_col.addStretch()

    left_col_widget = QWidget()
    left_col_widget.setLayout(button_col)
    left_col_widget.setSizePolicy(
        QSizePolicy.Policy.Fixed,
        QSizePolicy.Policy.Minimum,
    )
    left_col_widget.setFixedWidth(left_col_widget.sizeHint().width())

    root.addWidget(left_col_widget, 0)

    chart_view.setContentsMargins(0, 0, 0, 0)
    min_chart_w = 16 * 24
    chart_view.setMinimumSize(
        min_chart_w, min_chart_w * _CHART_ASPECT_H // _CHART_ASPECT_W
    )
    chart_host = _AspectRatioHost(chart_view, _CHART_ASPECT_W, _CHART_ASPECT_H)
    results_group, label_c0, label_vp, label_r0, label_delta_c = _build_results_group()

    right_col = QWidget()
    right_layout = QVBoxLayout(right_col)
    right_layout.setContentsMargins(0, 0, 0, 0)
    right_layout.setSpacing(0)
    right_layout.addWidget(chart_host, stretch=0)
    right_layout.addWidget(
        results_group, stretch=0, alignment=Qt.AlignmentFlag.AlignLeft
    )
    right_layout.addStretch(1)
    root.addWidget(right_col, stretch=1)
    outer.addLayout(root, stretch=1)

    return LcrMeterUi(
        root=central,
        cmb_gpib=cmb_gpib,
        cmb_cable_length=cmb_cable_length,
        btn_open_correction=btn_open_correction,
        btn_short_correction=btn_short_correction,
        cmb_function=cmb_function,
        spin_frequency=spin_frequency,
        spin_voltage=spin_voltage,
        spin_dc_offset_start=spin_dc_offset_start,
        spin_dc_offset_stop=spin_dc_offset_stop,
        spin_dc_offset_step=spin_dc_offset_step,
        btn_start=btn_start,
        chk_save_to_file=chk_save_to_file,
        btn_exit=btn_exit,
        cmb_vp_detect_method=cmb_vp_detect_method,
        spin_vp_threshold_f=spin_vp_threshold_f,
        chart_host=chart_view,
        label_c0=label_c0,
        label_vp=label_vp,
        label_r0=label_r0,
        label_delta_c=label_delta_c,
    )
