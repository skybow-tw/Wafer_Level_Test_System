"""Virtual LCR simulated measurement logic (no hardware)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from instruments.panels.lcr.chart import LcrChartController
from instruments.panels.lcr.measurement import (
    build_dc_offset_sweep_points,
    generate_lcr_simulation_values,
    save_lcr_measurement_csv,
)

_MEASUREMENT_POINT_COUNT = 20
_MEASUREMENT_POINT_DELAY_MS = 100
_DEFAULT_VIRTUAL_DC_OFFSET_START_V = 0.0
_DEFAULT_VIRTUAL_DC_OFFSET_STOP_V = 20.0
_DEFAULT_VIRTUAL_DC_OFFSET_STEP_V = 1.0


def default_virtual_dc_offset_points() -> list[float]:
    return build_dc_offset_sweep_points(
        _DEFAULT_VIRTUAL_DC_OFFSET_START_V,
        _DEFAULT_VIRTUAL_DC_OFFSET_STOP_V,
        _DEFAULT_VIRTUAL_DC_OFFSET_STEP_V,
    )


class VirtualLcrMeasurementLogic(QObject):
    """Runs animated virtual LCR sweeps and updates the chart controller."""

    measurement_finished = Signal(list, list)
    measurement_failed = Signal(str)
    measuring_changed = Signal(bool)

    def __init__(
        self,
        chart: LcrChartController,
        work_dir: Path,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._chart = chart
        self._work_dir = work_dir
        self._measuring = False
        self._measure_timer = QTimer(self)
        self._measure_timer.setSingleShot(True)
        self._measure_timer.timeout.connect(self._append_next_point)
        self._dc_offset_points: list[float] = []
        self._measure_x_values: list[float] = []
        self._measure_y_values: list[float] = []
        self._measure_secondary_values: list[float] = []
        self._pending_y_values: list[float] = []
        self._pending_secondary_values: list[float] = []
        self._measure_point_index = 0
        self._measurement_die_x: int | None = None
        self._measurement_die_y: int | None = None
        self._lcr_c0_value: float | None = None
        self._lcr_vp_offset_v: float | None = None
        self._lcr_delta_c: float | None = None

    @property
    def is_measuring(self) -> bool:
        return self._measuring

    def start_measurement(
        self,
        die_x: int | None = None,
        die_y: int | None = None,
    ) -> bool:
        if self._measuring:
            return False
        self._measurement_die_x = die_x
        self._measurement_die_y = die_y
        self._measuring = True
        self.measuring_changed.emit(True)
        self._chart.clear_series()
        self._measure_x_values = []
        self._measure_y_values = []
        self._measure_secondary_values = []
        self._measure_point_index = 0
        self._lcr_c0_value = None
        self._lcr_vp_offset_v = None
        self._lcr_delta_c = None
        self._dc_offset_points = default_virtual_dc_offset_points()
        self._chart.function_label = "Cp-D"
        point_count = len(self._dc_offset_points) or _MEASUREMENT_POINT_COUNT
        self._pending_y_values, self._pending_secondary_values = (
            generate_lcr_simulation_values(point_count)
        )
        self._schedule_next_point()
        return True

    def _schedule_next_point(self) -> None:
        self._measure_timer.start(_MEASUREMENT_POINT_DELAY_MS)

    def _append_next_point(self) -> None:
        total_points = len(self._pending_y_values) or _MEASUREMENT_POINT_COUNT
        if self._measure_point_index >= total_points:
            self._finish_measurement()
            return

        if self._dc_offset_points:
            x_value = self._dc_offset_points[self._measure_point_index]
        else:
            x_value = float(self._measure_point_index + 1)
        y_value = self._pending_y_values[self._measure_point_index]
        secondary_value = self._pending_secondary_values[self._measure_point_index]
        self._measure_x_values.append(x_value)
        self._measure_y_values.append(y_value)
        self._measure_secondary_values.append(secondary_value)
        if self._measure_point_index == 0:
            self._lcr_c0_value = y_value
        self._chart.append_point(x_value, y_value, secondary_value)
        self._measure_point_index += 1

        if self._measure_point_index < total_points:
            self._schedule_next_point()
        else:
            self._finish_measurement()

    def _finish_measurement(self) -> None:
        self._measuring = False
        self.measuring_changed.emit(False)
        if self._measure_x_values:
            try:
                save_lcr_measurement_csv(
                    self._work_dir,
                    function_label=self._chart.function_label,
                    measure_x_values=self._measure_x_values,
                    measure_y_values=self._measure_y_values,
                    measure_secondary_values=self._measure_secondary_values,
                    measurement_die_x=self._measurement_die_x,
                    measurement_die_y=self._measurement_die_y,
                    lcr_c0_value=self._lcr_c0_value,
                    lcr_vp_offset_v=self._lcr_vp_offset_v,
                    lcr_delta_c=self._lcr_delta_c,
                )
            except Exception as exc:
                self.measurement_failed.emit(str(exc))
        self._measurement_die_x = None
        self._measurement_die_y = None
        self.measurement_finished.emit(
            self._measure_x_values.copy(),
            self._measure_y_values.copy(),
        )
