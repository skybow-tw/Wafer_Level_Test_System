"""Shared simple X/Y trend chart used by placeholder instruments (NI 8452)."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis
from PySide6.QtCore import QMargins, QPointF, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QSizePolicy

_MEASUREMENT_POINT_COUNT = 20
_CHART_PLOT_MARGINS = QMargins(56, 48, 56, 40)
_CHART_LAYOUT_MARGINS = (18, 18, 18, 18)
_CHART_Y_MAJOR_TICK_COUNT = 6


@dataclass
class SimpleTrendChartRefs:
    chart_view: QChartView
    series: QLineSeries
    axis_x: QValueAxis
    axis_y: QValueAxis


class SimpleTrendChartController:
    """Owns a single-series Measurement chart (X / Y)."""

    def __init__(self) -> None:
        self._refs = self._build_chart()

    @property
    def chart_view(self) -> QChartView:
        return self._refs.chart_view

    def clear_series(self) -> None:
        self._refs.series.clear()

    def append_point(self, x: float, y: float) -> None:
        self._refs.series.append(QPointF(x, y))
        self._update_axes_from_series()

    def set_plot_data(self, x_values: list[float], y_values: list[float]) -> None:
        self._refs.series.clear()
        for x_value, y_value in zip(x_values, y_values, strict=False):
            self._refs.series.append(QPointF(x_value, y_value))
        self._update_axes_from_series()

    def _build_chart(self) -> SimpleTrendChartRefs:
        series = QLineSeries()
        series.setName("Primary")

        chart = QChart()
        chart.legend().setVisible(False)
        chart.setBackgroundVisible(True)
        chart.setTitle("Measurement")
        self._apply_chart_plot_margins(chart)

        axis_x = QValueAxis()
        axis_x.setTitleText("X")
        axis_x.setTitleVisible(True)
        axis_x.setLabelsVisible(True)
        axis_x.setLabelFormat("%.0f")
        axis_x.setRange(0, _MEASUREMENT_POINT_COUNT + 1)
        self._configure_major_axis_grid(axis_x, is_x=True)

        axis_y = QValueAxis()
        axis_y.setTitleText("Y")
        axis_y.setTitleVisible(True)
        axis_y.setLabelsVisible(True)
        axis_y.setLabelFormat("%.1f")
        axis_y.setRange(0, 1000)
        self._configure_major_axis_grid(axis_y, is_x=False)

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
        return SimpleTrendChartRefs(
            chart_view=chart_view,
            series=series,
            axis_x=axis_x,
            axis_y=axis_y,
        )

    def _update_axes_from_series(self) -> None:
        series = self._refs.series
        if series.count() == 0:
            return
        xs = [series.at(i).x() for i in range(series.count())]
        ys = [series.at(i).y() for i in range(series.count())]
        self._refs.axis_x.setRange(min(xs) - 0.5, max(xs) + 0.5)
        ymax = max(ys)
        self._refs.axis_y.setRange(0, max(ymax * 1.1, 1.0))

    @staticmethod
    def _apply_chart_plot_margins(chart: QChart) -> None:
        chart.setMargins(_CHART_PLOT_MARGINS)
        layout = chart.layout()
        if layout is not None:
            left, top, right, bottom = _CHART_LAYOUT_MARGINS
            layout.setContentsMargins(left, top, right, bottom)

    @staticmethod
    def _configure_major_axis_grid(axis: QValueAxis, *, is_x: bool) -> None:
        axis.setLabelsVisible(True)
        axis.setTitleVisible(True)
        axis.setGridLineVisible(True)
        axis.setMinorGridLineVisible(False)
        if not is_x:
            axis.setTickCount(_CHART_Y_MAJOR_TICK_COUNT)
