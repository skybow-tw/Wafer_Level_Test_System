"""Virtual LCR instrument panel layout."""

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
class VirtualLcrUi:
    root: QWidget
    btn_simulation: QPushButton
    btn_exit: QPushButton
    chart_host: QWidget


def build_virtual_lcr_ui(chart_view: QWidget) -> VirtualLcrUi:
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

    sim_button = QPushButton("Simulation")
    sim_button.setMinimumSize(120, 44)
    sim_button.setSizePolicy(
        QSizePolicy.Policy.Fixed,
        QSizePolicy.Policy.Fixed,
    )
    button_col.addWidget(sim_button)

    exit_button = QPushButton("Exit")
    exit_button.setMinimumSize(120, 44)
    exit_button.setSizePolicy(
        QSizePolicy.Policy.Fixed,
        QSizePolicy.Policy.Fixed,
    )
    mark_close_button(exit_button)
    button_col.addWidget(exit_button)
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

    return VirtualLcrUi(
        root=central,
        btn_simulation=sim_button,
        btn_exit=exit_button,
        chart_host=chart_view,
    )
