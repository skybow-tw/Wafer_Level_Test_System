"""Virtual LCR (simulated) instrument control window."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QMessageBox, QWidget

from instruments.panels.base import InstrumentPanelBase
from instruments.panels.common import resolve_work_dir
from instruments.panels.lcr.chart import LcrChartController
from instruments.panels.registry import VIRTUAL_LCR_INSTRUMENT_NAME
from instruments.panels.virtual_lcr.logic import VirtualLcrMeasurementLogic
from instruments.panels.virtual_lcr.ui import build_virtual_lcr_ui
from save_params import get_save_params
from statistics_report import LcrDieSummary, virtual_lcr_default_summary
from theme_config import THEMES, generate_theme_qss


class VirtualLcrWindow(InstrumentPanelBase):
    def __init__(
        self,
        parent: QWidget | None = None,
        work_dir: Path | None = None,
    ) -> None:
        super().__init__(VIRTUAL_LCR_INSTRUMENT_NAME, parent=parent, work_dir=work_dir)
        self.setFixedSize(640, 480)
        work = resolve_work_dir(self, work_dir)
        self._chart = LcrChartController(VIRTUAL_LCR_INSTRUMENT_NAME)
        self._logic = VirtualLcrMeasurementLogic(self._chart, work, parent=self)
        ui = build_virtual_lcr_ui(self._chart.chart_view)
        self.setCentralWidget(ui.root)
        ui.btn_simulation.clicked.connect(self._on_simulation)
        ui.btn_exit.clicked.connect(self.close)
        self._btn_simulation = ui.btn_simulation
        self._logic.measurement_finished.connect(self.measurement_finished)
        self._logic.measurement_failed.connect(self._on_measurement_failed)
        self._logic.measuring_changed.connect(self._on_measuring_changed)
        self.setStyleSheet(generate_theme_qss(THEMES["light"]))

    @property
    def is_measuring(self) -> bool:
        return self._logic.is_measuring

    @property
    def is_virtual_lcr(self) -> bool:
        return True

    @property
    def uses_lcr_measurement(self) -> bool:
        return True

    @property
    def uses_statistics_report(self) -> bool:
        return True

    def get_statistics_report_headers(self) -> tuple[str, ...]:
        return ("X", "Y", "Co", "Vp", "deltaC")

    def get_statistics_report_values(self) -> tuple[float | int | None, ...]:
        summary = self.get_lcr_die_summary()
        return (summary.co, summary.vp, summary.delta_c)

    def get_lcr_die_summary(self) -> LcrDieSummary:
        return virtual_lcr_default_summary()

    def start_measurement(
        self,
        die_x: int | None = None,
        die_y: int | None = None,
        *,
        automated: bool = False,
    ) -> bool:
        del automated
        params = get_save_params()
        if die_x is None:
            die_x = params.x
        if die_y is None:
            die_y = params.y
        return self._logic.start_measurement(die_x=die_x, die_y=die_y)

    def _on_simulation(self) -> None:
        self.start_measurement()

    def _on_measuring_changed(self, measuring: bool) -> None:
        self._btn_simulation.setEnabled(not measuring)

    def _on_measurement_failed(self, message: str) -> None:
        QMessageBox.warning(self, "LCR 存檔失敗", message)
