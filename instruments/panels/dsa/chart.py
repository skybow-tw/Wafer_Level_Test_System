"""Stacked magnitude / phase vs frequency charts for the DSA panel."""

from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis
from PySide6.QtCore import QMargins, QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

from instruments.panels.lcr.chart import (
    CHART_SURFACE_COLOR,
    apply_chart_surface_color,
)

_CHART_PLOT_MARGINS = QMargins(20, 20, 20, 20)
_CHART_LAYOUT_MARGINS = (8, 8, 8, 8)
_CHART_Y_MAJOR_TICK_COUNT = 6
_MAGNITUDE_DB_FLOOR = 1e-12


@dataclass
class _XyChartRefs:
    chart_view: QChartView
    series: QLineSeries
    axis_x: QValueAxis
    axis_y: QValueAxis


def magnitude_v_to_db(magnitude_v: float) -> float:
    return 20.0 * math.log10(max(abs(magnitude_v), _MAGNITUDE_DB_FLOOR))


def _apply_chart_plot_margins(chart: QChart) -> None:
    chart.setMargins(_CHART_PLOT_MARGINS)
    layout = chart.layout()
    if layout is not None:
        left, top, right, bottom = _CHART_LAYOUT_MARGINS
        layout.setContentsMargins(left, top, right, bottom)


def _configure_axis(axis: QValueAxis, *, is_x: bool) -> None:
    axis.setLabelsVisible(True)
    axis.setTitleVisible(True)
    axis.setGridLineVisible(True)
    axis.setMinorGridLineVisible(False)
    if not is_x:
        axis.setTickCount(_CHART_Y_MAJOR_TICK_COUNT)


def _autoscale_axis(
    axis: QValueAxis,
    values: list[float],
    *,
    pad_ratio: float = 0.1,
    floor_zero: bool = False,
    label_format: str,
) -> None:
    if not values:
        return
    vmin = min(values)
    vmax = max(values)
    if math.isclose(vmin, vmax):
        span = max(abs(vmax) * 0.2, 1e-6)
        vmin -= span
        vmax += span
    else:
        span = vmax - vmin
        vmin -= span * pad_ratio
        vmax += span * pad_ratio
    if floor_zero:
        if vmax <= 0:
            vmax = 1.0
    axis.setLabelFormat(label_format)
    axis.setRange(vmin, vmax)
    axis.setTickCount(_CHART_Y_MAJOR_TICK_COUNT)


def _build_xy_chart(
    x_title: str,
    y_title: str,
    color: QColor,
    *,
    x_range: tuple[float, float],
    y_range: tuple[float, float],
    y_format: str,
) -> _XyChartRefs:
    series = QLineSeries()
    series.setPen(QPen(color, 2.0))

    chart = QChart()
    chart.legend().setVisible(False)
    chart.setTitle("")
    _apply_chart_plot_margins(chart)

    axis_x = QValueAxis()
    axis_x.setTitleText(x_title)
    axis_x.setLabelFormat("%.0f")
    axis_x.setRange(*x_range)
    _configure_axis(axis_x, is_x=True)

    axis_y = QValueAxis()
    axis_y.setTitleText(y_title)
    axis_y.setLabelFormat(y_format)
    axis_y.setRange(*y_range)
    axis_y.setLinePen(QPen(color, 1.5))
    axis_y.setLabelsColor(color)
    axis_y.setTitleBrush(color)
    _configure_axis(axis_y, is_x=False)

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
    chart_view.setContentsMargins(0, 0, 0, 0)
    apply_chart_surface_color(chart_view, CHART_SURFACE_COLOR)
    return _XyChartRefs(
        chart_view=chart_view,
        series=series,
        axis_x=axis_x,
        axis_y=axis_y,
    )


class DsaChartController:
    """Owns stacked Magnitude and Phase vs Frequency charts."""

    def __init__(self) -> None:
        mag_color = QColor("#1565C0")
        phase_color = QColor("#D32F2F")
        self._magnitude = _build_xy_chart(
            "Frequency (Hz)",
            "Magnitude(dB)",
            mag_color,
            x_range=(500, 8000),
            y_range=(-60, 0),
            y_format="%.1f",
        )
        self._phase = _build_xy_chart(
            "Frequency (Hz)",
            "Phase (deg)",
            phase_color,
            x_range=(500, 8000),
            y_range=(-180, 180),
            y_format="%.1f",
        )
        host = QWidget()
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self._magnitude.chart_view, stretch=3)
        layout.addWidget(self._phase.chart_view, stretch=2)
        self._host = host

    @property
    def host(self) -> QWidget:
        return self._host

    def clear(self) -> None:
        self._magnitude.series.clear()
        self._phase.series.clear()

    def append_point(
        self, frequency_hz: float, magnitude_v: float, phase_deg: float
    ) -> None:
        self._magnitude.series.append(
            QPointF(frequency_hz, magnitude_v_to_db(magnitude_v))
        )
        self._phase.series.append(QPointF(frequency_hz, phase_deg))
        self._update_axes()

    def set_plot_data(
        self,
        frequencies_hz: list[float],
        magnitudes_v: list[float],
        phases_deg: list[float],
    ) -> None:
        self.clear()
        for frequency, magnitude in zip(frequencies_hz, magnitudes_v, strict=False):
            self._magnitude.series.append(
                QPointF(frequency, magnitude_v_to_db(magnitude))
            )
        for frequency, phase in zip(frequencies_hz, phases_deg, strict=False):
            self._phase.series.append(QPointF(frequency, phase))
        self._update_axes()

    def _update_axes(self) -> None:
        mag_series = self._magnitude.series
        if mag_series.count() == 0:
            return
        xs = [mag_series.at(i).x() for i in range(mag_series.count())]
        mags_db = [mag_series.at(i).y() for i in range(mag_series.count())]
        phases = [
            self._phase.series.at(i).y() for i in range(self._phase.series.count())
        ]
        xmin = min(xs)
        xmax = max(xs)
        if math.isclose(xmin, xmax):
            pad = max(abs(xmax) * 0.05, 1.0)
            x_lower, x_upper = xmin - pad, xmax + pad
        else:
            span = xmax - xmin
            x_lower, x_upper = xmin - span * 0.05, xmax + span * 0.05
        if xmin >= 0:
            x_lower = max(x_lower, 0.0)
        for axis in (self._magnitude.axis_x, self._phase.axis_x):
            axis.setRange(x_lower, x_upper)
            if xmax >= 1000:
                axis.setLabelFormat("%.0f")
            elif xmax >= 10:
                axis.setLabelFormat("%.1f")
            else:
                axis.setLabelFormat("%.2f")
        _autoscale_axis(
            self._magnitude.axis_y,
            mags_db,
            floor_zero=False,
            label_format="%.1f",
        )
        if phases:
            _autoscale_axis(
                self._phase.axis_y,
                phases,
                floor_zero=False,
                label_format="%.1f",
            )
