"""Shared BMT panel UI builders."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from instruments.panels.bmt.constants import (
    DEFAULT_BMT_PIXEL_INT_TIME,
    DEFAULT_BMT_PIXEL_PERIOD,
)

# Display labels only; combo itemData remains index 0..4 → ROIC byte map.
_BMT_PIXEL_S_H_IBS_LABELS = ("0.5uA", "1uA", "2uA", "4uA", "7uA")
_BMT_PIXEL_CTIA_IBS_LABELS = ("0.5uA", "1uA", "2uA", "4uA", "7uA")
_BMT_PIXEL_BUFF_IBS_LABELS = ("0.5uA", "1uA", "2uA", "4uA", "7uA")
_BMT_PIXEL_BOOL_LABELS = (("Off", False), ("On", True))


def build_hex_combo(
    max_value: int,
    default: int,
    width: int,
    *,
    step: int = 1,
) -> QComboBox:
    combo = QComboBox()
    for value in range(0, max_value + 1, step):
        combo.addItem(f"0x{value:02X}", value)
    default_index = combo.findData(default)
    combo.setCurrentIndex(0 if default_index < 0 else default_index)
    combo.setFixedWidth(width)
    combo.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    return combo


def build_index_combo(
    labels: tuple[str, ...], *, width: int, default_index: int = 0
) -> QComboBox:
    combo = QComboBox()
    for index, text in enumerate(labels):
        combo.addItem(text, index)
    combo.setCurrentIndex(max(0, min(default_index, len(labels) - 1)))
    combo.setFixedWidth(width)
    combo.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    return combo


def build_bool_combo(*, width: int, default: bool = False) -> QComboBox:
    combo = QComboBox()
    for text, value in _BMT_PIXEL_BOOL_LABELS:
        combo.addItem(text, value)
    index = combo.findData(default)
    combo.setCurrentIndex(0 if index < 0 else index)
    combo.setFixedWidth(width)
    combo.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    return combo


def build_decimal_combo(max_value: int, default: int, width: int) -> QComboBox:
    combo = QComboBox()
    for value in range(max_value + 1):
        combo.addItem(str(value), value)
    index = combo.findData(default)
    combo.setCurrentIndex(0 if index < 0 else index)
    combo.setFixedWidth(width)
    combo.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    return combo


def labeled_combo_col(title: str, combo: QComboBox) -> QVBoxLayout:
    col = QVBoxLayout()
    col.setContentsMargins(0, 0, 0, 0)
    col.setSpacing(2)
    label = QLabel(title)
    label.setAlignment(Qt.AlignmentFlag.AlignLeft)
    col.addWidget(label)
    col.addWidget(combo)
    return col


def build_hex_param_row(usb_width: int) -> tuple[QWidget, QComboBox, QComboBox, QComboBox]:
    spacing = 4
    field_width = (usb_width - spacing * 2) // 3

    row_widget = QWidget()
    row_widget.setFixedWidth(usb_width)
    row = QHBoxLayout(row_widget)
    row.setContentsMargins(0, 4, 0, 0)
    row.setSpacing(spacing)

    device_id = build_hex_combo(0xFF, 0xC0, field_width)
    offset = build_hex_combo(0xF0, 0x00, field_width, step=0x10)
    length = build_hex_combo(0xFF, 0x90, field_width)

    for title, control in (
        ("Device ID", device_id),
        ("Register", offset),
        ("Length", length),
    ):
        row.addLayout(labeled_combo_col(title, control))

    return row_widget, device_id, offset, length


def build_pixel_param_panel(
    usb_width: int,
) -> tuple[
    QWidget,
    QComboBox,
    QComboBox,
    QComboBox,
    QComboBox,
    QComboBox,
    QComboBox,
    QComboBox,
]:
    spacing = 4
    field_width = (usb_width - spacing * 2) // 3

    panel = QWidget()
    panel.setFixedWidth(usb_width)
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(0, 4, 0, 0)
    layout.setSpacing(4)

    s_h = build_index_combo(_BMT_PIXEL_S_H_IBS_LABELS, width=field_width)
    ctia = build_index_combo(_BMT_PIXEL_CTIA_IBS_LABELS, width=field_width)
    buff = build_index_combo(_BMT_PIXEL_BUFF_IBS_LABELS, width=field_width)

    row1 = QHBoxLayout()
    row1.setContentsMargins(0, 0, 0, 0)
    row1.setSpacing(spacing)
    for title, control in (
        ("S_H_IBS", s_h),
        ("CTIA_IBS", ctia),
        ("BUFF_IBS", buff),
    ):
        row1.addLayout(labeled_combo_col(title, control))
    layout.addLayout(row1)

    int_time = build_hex_combo(0xFF, DEFAULT_BMT_PIXEL_INT_TIME, field_width)
    period = build_decimal_combo(0xFF, DEFAULT_BMT_PIXEL_PERIOD, field_width)

    row2 = QHBoxLayout()
    row2.setContentsMargins(0, 0, 0, 0)
    row2.setSpacing(spacing)
    for title, control in (
        ("Int Time", int_time),
        ("Period (ms)", period),
    ):
        row2.addLayout(labeled_combo_col(title, control))
    row2.addStretch()
    layout.addLayout(row2)

    adc_off = build_bool_combo(width=field_width, default=False)
    enable_rr = build_bool_combo(width=field_width, default=False)

    row3 = QHBoxLayout()
    row3.setContentsMargins(0, 0, 0, 0)
    row3.setSpacing(spacing)
    for title, control in (
        ("ADC Off", adc_off),
        ("Enable RR", enable_rr),
    ):
        row3.addLayout(labeled_combo_col(title, control))
    row3.addStretch()
    layout.addLayout(row3)

    return panel, s_h, ctia, buff, int_time, period, adc_off, enable_rr


def combo_int_value(combo: QComboBox | None, default: int) -> int:
    if combo is None:
        return default
    value = combo.currentData()
    return default if value is None else int(value)


def combo_bool_value(combo: QComboBox | None, default: bool = False) -> bool:
    if combo is None:
        return default
    value = combo.currentData()
    return default if value is None else bool(value)
