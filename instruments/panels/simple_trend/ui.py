"""Shared Configure / Start / Exit layout for simple trend instruments."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from instruments.panels.common import mark_close_button


@dataclass
class SimpleTrendUi:
    root: QWidget
    btn_configure: QPushButton
    btn_start: QPushButton
    btn_exit: QPushButton
    chart_host: QWidget


def build_simple_trend_ui(chart_view: QWidget) -> SimpleTrendUi:
    central = QWidget()
    outer = QVBoxLayout(central)
    outer.setContentsMargins(8, 8, 8, 8)
    outer.setSpacing(8)

    root = QHBoxLayout()
    root.setSpacing(12)
    root.setContentsMargins(0, 0, 0, 0)

    button_col = QVBoxLayout()
    button_col.setContentsMargins(0, 0, 0, 0)
    button_col.setSpacing(8)

    btn_configure = QPushButton("Configure")
    btn_configure.setMinimumSize(120, 44)
    btn_configure.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    button_col.addWidget(btn_configure)

    btn_start = QPushButton("Start")
    btn_start.setMinimumSize(120, 44)
    btn_start.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    button_col.addWidget(btn_start)

    btn_exit = QPushButton("Exit")
    btn_exit.setMinimumSize(120, 44)
    btn_exit.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    mark_close_button(btn_exit)
    button_col.addWidget(btn_exit)
    button_col.addStretch()

    left_col_widget = QWidget()
    left_col_widget.setLayout(button_col)
    left_col_widget.setSizePolicy(
        QSizePolicy.Policy.Fixed,
        QSizePolicy.Policy.Preferred,
    )
    left_col_widget.setFixedWidth(left_col_widget.sizeHint().width())

    root.addWidget(left_col_widget, 0)
    root.addWidget(chart_view, stretch=1)
    outer.addLayout(root, stretch=1)

    return SimpleTrendUi(
        root=central,
        btn_configure=btn_configure,
        btn_start=btn_start,
        btn_exit=btn_exit,
        chart_host=chart_view,
    )
