"""Reusable simple-trend instrument window (Configure / Start / Exit)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QWidget

from instruments.panels.base import InstrumentPanelBase
from instruments.panels.simple_trend.chart import SimpleTrendChartController
from instruments.panels.simple_trend.logic import SimpleTrendLogic
from instruments.panels.simple_trend.ui import SimpleTrendUi, build_simple_trend_ui
from theme_config import THEMES, generate_theme_qss


class SimpleTrendWindow(InstrumentPanelBase):
    """Placeholder panel used by NI 8452 until a real driver is added."""

    def __init__(
        self,
        instrument_name: str,
        parent: QWidget | None = None,
        work_dir: Path | None = None,
    ) -> None:
        super().__init__(instrument_name, parent=parent, work_dir=work_dir)
        self.setFixedSize(640, 480)
        self._chart = SimpleTrendChartController()
        self._logic = SimpleTrendLogic(self._chart, parent=self)
        self._ui: SimpleTrendUi = build_simple_trend_ui(self._chart.chart_view)
        self.setCentralWidget(self._ui.root)
        self._wire_ui()
        self._logic.measurement_finished.connect(self.measurement_finished)
        self._logic.measuring_changed.connect(self._on_measuring_changed)
        self.setStyleSheet(generate_theme_qss(THEMES["light"]))

    def _wire_ui(self) -> None:
        # Configure is a placeholder (same as legacy ICW for non-LCR instruments).
        self._ui.btn_configure.clicked.connect(lambda: None)
        self._ui.btn_start.clicked.connect(self._on_start_clicked)
        self._ui.btn_exit.clicked.connect(self.close)

    @property
    def is_measuring(self) -> bool:
        return self._logic.is_measuring

    def start_measurement(
        self,
        die_x: int | None = None,
        die_y: int | None = None,
        *,
        automated: bool = False,
    ) -> bool:
        del die_x, die_y, automated
        return self._logic.start_measurement()

    def set_plot_data(self, x_values: list[float], y_values: list[float]) -> None:
        self._chart.set_plot_data(x_values, y_values)

    def _on_start_clicked(self) -> None:
        self.start_measurement()

    def _on_measuring_changed(self, measuring: bool) -> None:
        self._ui.btn_start.setEnabled(not measuring)
