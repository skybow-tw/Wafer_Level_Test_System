"""Simulated single-series trend measurement (NI placeholder)."""

from __future__ import annotations

import random

from PySide6.QtCore import QObject, QTimer, Signal

from instruments.panels.simple_trend.chart import SimpleTrendChartController

_MEASUREMENT_POINT_COUNT = 20
_MEASUREMENT_POINT_DELAY_MS = 100


def generate_measurement_y_values(point_count: int = _MEASUREMENT_POINT_COUNT) -> list[float]:
    values: list[float] = []
    y = random.uniform(0, 50)
    values.append(y)
    for remaining in range(point_count - 1, 0, -1):
        max_step = (1000.0 - y) / remaining * 1.5
        y = min(y + random.uniform(0, max(max_step, 1.0)), 1000.0)
        values.append(y)
    return values


class SimpleTrendLogic(QObject):
    """Animated placeholder sweep used until real DSA / NI drivers exist."""

    measurement_finished = Signal(list, list)
    measuring_changed = Signal(bool)

    def __init__(
        self,
        chart: SimpleTrendChartController,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._chart = chart
        self._measuring = False
        self._measure_timer = QTimer(self)
        self._measure_timer.setSingleShot(True)
        self._measure_timer.timeout.connect(self._append_next_point)
        self._measure_x_values: list[float] = []
        self._measure_y_values: list[float] = []
        self._pending_y_values: list[float] = []
        self._measure_point_index = 0

    @property
    def is_measuring(self) -> bool:
        return self._measuring

    def start_measurement(self) -> bool:
        if self._measuring:
            return False
        self._measuring = True
        self.measuring_changed.emit(True)
        self._chart.clear_series()
        self._measure_x_values = []
        self._measure_y_values = []
        self._measure_point_index = 0
        self._pending_y_values = generate_measurement_y_values()
        self._schedule_next_point()
        return True

    def _schedule_next_point(self) -> None:
        self._measure_timer.start(_MEASUREMENT_POINT_DELAY_MS)

    def _append_next_point(self) -> None:
        total_points = len(self._pending_y_values) or _MEASUREMENT_POINT_COUNT
        if self._measure_point_index >= total_points:
            self._finish_measurement()
            return

        x_value = float(self._measure_point_index + 1)
        y_value = self._pending_y_values[self._measure_point_index]
        self._measure_x_values.append(x_value)
        self._measure_y_values.append(y_value)
        self._chart.append_point(x_value, y_value)
        self._measure_point_index += 1

        if self._measure_point_index < total_points:
            self._schedule_next_point()
        else:
            self._finish_measurement()

    def _finish_measurement(self) -> None:
        self._measuring = False
        self.measuring_changed.emit(False)
        self.measurement_finished.emit(
            self._measure_x_values.copy(),
            self._measure_y_values.copy(),
        )
