"""LCR chart view and simulated sweep plotting (virtual LCR)."""

from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis
from PySide6.QtCore import QMargins, QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy

from instruments.e4980a import (
    impedance_function_bias_csv_header,
    impedance_function_csv_headers,
    impedance_function_saves_capacitance_as_ff,
)
from instruments.panels.lcr.measurement import FF_TO_F, LCR_CAP_MAX_F, LCR_CAP_MIN_F

_LCR_X_AXIS_GRID_V = 0.1
_LCR_X_AXIS_MAJOR_TICK_V = 1.0
_CHART_PLOT_MARGINS = QMargins(20, 20, 20, 20)
_CHART_LAYOUT_MARGINS = (8, 8, 8, 8)
_CHART_Y_MAJOR_TICK_COUNT = 6
CHART_SURFACE_COLOR = QColor("#F0F0F0")
_CHART_SURFACE_BORDER = QColor("#BDBDBD")


def apply_chart_surface_color(chart_view: QChartView, color: QColor) -> None:
    """Apply a panel surface color to the chart and its view."""
    chart = chart_view.chart()
    if chart is None:
        return
    LcrChartController._apply_chart_surface_style(chart, chart_view, color)


@dataclass
class LcrChartRefs:
    chart_view: QChartView
    primary_series: QLineSeries
    secondary_series: QLineSeries
    axis_x: QValueAxis
    axis_y_primary: QValueAxis
    axis_y_secondary: QValueAxis


class LcrChartController:
    """Owns LCR chart axes/series updates for Cp-D style plots."""

    def __init__(self, instrument_title: str, *, x_axis_title: str | None = None) -> None:
        self._instrument_title = instrument_title
        self._x_axis_title = x_axis_title
        self._lcr_function_label = "Cp-D"
        self._refs = self._build_chart(instrument_title)

    @property
    def refs(self) -> LcrChartRefs:
        return self._refs

    @property
    def function_label(self) -> str:
        return self._lcr_function_label

    @function_label.setter
    def function_label(self, value: str) -> None:
        self._lcr_function_label = value
        self.update_axis_titles()

    @property
    def chart_view(self) -> QChartView:
        return self._refs.chart_view

    def clear_series(self) -> None:
        self._refs.primary_series.clear()
        self._refs.secondary_series.clear()

    def append_point(
        self, x: float, y: float, y_secondary: float | None = None
    ) -> None:
        plot_y = y
        if impedance_function_saves_capacitance_as_ff(self._lcr_function_label):
            plot_y = y / FF_TO_F
        self._refs.primary_series.append(QPointF(x, plot_y))
        if y_secondary is not None:
            self._refs.secondary_series.append(QPointF(x, y_secondary))
        self._update_axes_from_series()

    def update_axis_titles(self) -> None:
        chart = self._refs.chart_view.chart()
        if chart is not None:
            chart.setTitle(self._lcr_function_label or self._instrument_title)
            self._apply_chart_plot_margins(chart)
        axis_x = self._refs.axis_x
        axis_x.setTitleText(
            self._x_axis_title
            or (
                impedance_function_bias_csv_header(self._lcr_function_label)
                if self._lcr_function_label in ("Cp-Rp", "Cs-Rs")
                else "DC offset(V)"
            )
        )
        primary_header, secondary_header = impedance_function_csv_headers(
            self._lcr_function_label
        )
        primary_color = QColor("#1565C0")
        secondary_color = QColor("#D32F2F")
        y_primary = self._refs.axis_y_primary
        y_primary.setTitleText(primary_header)
        y_primary.setTitleBrush(primary_color)
        y_primary.setLabelsColor(primary_color)
        y_primary.setLinePen(QPen(primary_color, 1.5))
        y_secondary = self._refs.axis_y_secondary
        y_secondary.setTitleText(secondary_header)
        y_secondary.setTitleBrush(secondary_color)
        y_secondary.setLabelsColor(secondary_color)
        y_secondary.setLinePen(QPen(secondary_color, 1.5))
        self._refs.primary_series.setName(primary_header)
        self._refs.primary_series.setPen(QPen(primary_color, 2.5))
        self._refs.secondary_series.setName(secondary_header)
        self._refs.secondary_series.setPen(QPen(secondary_color, 2.5))
        self._bind_series_axes()

    def _build_chart(self, instrument_title: str) -> LcrChartRefs:
        primary_color = QColor("#1565C0")
        secondary_color = QColor("#D32F2F")

        primary_series = QLineSeries()
        primary_series.setPen(QPen(primary_color, 2.5))
        secondary_series = QLineSeries()
        secondary_series.setPen(QPen(secondary_color, 2.5))

        chart = QChart()
        chart.legend().setVisible(False)
        chart.setTitle(instrument_title)
        self._apply_chart_plot_margins(chart)

        axis_x = QValueAxis()
        axis_x.setTitleText("DC offset(V)")
        self._configure_lcr_x_axis_grid(axis_x, 0.0, 1.0)

        axis_y = QValueAxis()
        axis_y.setLabelFormat("%.2e")
        axis_y.setRange(LCR_CAP_MIN_F, LCR_CAP_MAX_F)
        axis_y.setLinePen(QPen(primary_color, 1.5))
        axis_y.setLabelsColor(primary_color)
        axis_y.setTitleBrush(primary_color)
        self._configure_major_axis_grid(axis_y, is_x=False)

        axis_y_secondary = QValueAxis()
        axis_y_secondary.setLabelFormat("%.3f")
        axis_y_secondary.setRange(0, 1)
        axis_y_secondary.setLinePen(QPen(secondary_color, 1.5))
        axis_y_secondary.setLabelsColor(secondary_color)
        axis_y_secondary.setTitleBrush(secondary_color)
        self._configure_major_axis_grid(
            axis_y_secondary, is_x=False, show_grid=False
        )

        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        chart.addAxis(axis_y_secondary, Qt.AlignmentFlag.AlignRight)
        chart.addSeries(primary_series)
        chart.addSeries(secondary_series)
        self._bind_series_axes_impl(
            primary_series, secondary_series, axis_x, axis_y, axis_y_secondary
        )

        chart_view = QChartView(chart)
        chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        chart_view.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        chart_view.setMinimumSize(360, 400)
        chart_view.setContentsMargins(0, 0, 0, 0)
        self._apply_chart_surface_style(chart, chart_view)

        refs = LcrChartRefs(
            chart_view=chart_view,
            primary_series=primary_series,
            secondary_series=secondary_series,
            axis_x=axis_x,
            axis_y_primary=axis_y,
            axis_y_secondary=axis_y_secondary,
        )
        self._refs = refs
        self.update_axis_titles()
        return refs

    def _bind_series_axes(self) -> None:
        self._bind_series_axes_impl(
            self._refs.primary_series,
            self._refs.secondary_series,
            self._refs.axis_x,
            self._refs.axis_y_primary,
            self._refs.axis_y_secondary,
        )

    @staticmethod
    def _bind_series_axes_impl(
        primary_series: QLineSeries,
        secondary_series: QLineSeries,
        axis_x: QValueAxis,
        axis_y_primary: QValueAxis,
        axis_y_secondary: QValueAxis,
    ) -> None:
        for series in (primary_series, secondary_series):
            for axis in list(series.attachedAxes()):
                series.detachAxis(axis)
        primary_series.attachAxis(axis_x)
        primary_series.attachAxis(axis_y_primary)
        secondary_series.attachAxis(axis_x)
        secondary_series.attachAxis(axis_y_secondary)

    @staticmethod
    def _apply_chart_plot_margins(chart: QChart) -> None:
        chart.setMargins(_CHART_PLOT_MARGINS)
        layout = chart.layout()
        if layout is not None:
            left, top, right, bottom = _CHART_LAYOUT_MARGINS
            layout.setContentsMargins(left, top, right, bottom)

    @staticmethod
    def _apply_chart_surface_style(
        chart: QChart,
        chart_view: QChartView,
        color: QColor | None = None,
    ) -> None:
        surface_color = color or CHART_SURFACE_COLOR
        surface = QBrush(surface_color)
        chart.setBackgroundVisible(True)
        chart.setBackgroundBrush(surface)
        chart.setBackgroundPen(QPen(_CHART_SURFACE_BORDER, 1))
        chart.setBackgroundRoundness(0)
        chart.setPlotAreaBackgroundVisible(True)
        chart.setPlotAreaBackgroundBrush(surface)

        chart_view.setAutoFillBackground(True)
        palette = chart_view.palette()
        palette.setColor(chart_view.backgroundRole(), surface_color)
        chart_view.setPalette(palette)

    @staticmethod
    def _configure_major_axis_grid(
        axis: QValueAxis,
        *,
        is_x: bool,
        show_grid: bool = True,
    ) -> None:
        axis.setLabelsVisible(True)
        axis.setTitleVisible(True)
        axis.setGridLineVisible(show_grid)
        axis.setMinorGridLineVisible(False)
        if not is_x:
            axis.setTickCount(_CHART_Y_MAJOR_TICK_COUNT)

    def _configure_lcr_x_axis_grid(
        self, axis: QValueAxis, lower: float, upper: float
    ) -> None:
        lower, upper = self._snap_lcr_x_axis_range(lower, upper)
        axis.setRange(lower, upper)
        axis.setLabelFormat("%.2f" if self._x_axis_title else "%.0f")
        axis.setTickType(QValueAxis.TickType.TicksDynamic)
        axis.setTickAnchor(0.0)
        axis.setTickInterval(
            _LCR_X_AXIS_GRID_V if self._x_axis_title else _LCR_X_AXIS_MAJOR_TICK_V
        )
        axis.setMinorTickCount(0)
        axis.setLabelsVisible(True)
        axis.setTitleVisible(True)
        axis.setGridLineVisible(True)
        axis.setMinorGridLineVisible(False)

    @staticmethod
    def _snap_lcr_x_axis_range(lower: float, upper: float) -> tuple[float, float]:
        grid = _LCR_X_AXIS_GRID_V
        snapped_lower = math.floor(lower / grid - 1e-9) * grid
        snapped_upper = math.ceil(upper / grid + 1e-9) * grid
        if snapped_upper <= snapped_lower:
            snapped_upper = snapped_lower + grid
        return round(snapped_lower, 1), round(snapped_upper, 1)

    def _update_axes_from_series(self) -> None:
        primary_series = self._refs.primary_series
        if primary_series.count() == 0:
            return
        xs = [primary_series.at(i).x() for i in range(primary_series.count())]
        primary_ys = [
            primary_series.at(i).y() for i in range(primary_series.count())
        ]
        self._update_lcr_x_axis(xs)
        self._autoscale_lcr_y_axis(self._refs.axis_y_primary, primary_ys)
        secondary_series = self._refs.secondary_series
        if secondary_series.count() > 0:
            secondary_ys = [
                secondary_series.at(i).y()
                for i in range(secondary_series.count())
            ]
            self._autoscale_value_axis(self._refs.axis_y_secondary, secondary_ys)
            self._configure_major_axis_grid(
                self._refs.axis_y_secondary, is_x=False, show_grid=False
            )

    def _update_lcr_x_axis(self, xs: list[float]) -> None:
        if not xs:
            return
        xmin = min(xs)
        xmax = max(xs)
        if xmin == xmax:
            pad = max(abs(xmax) * 0.05, _LCR_X_AXIS_GRID_V)
            lower = xmin - pad
            upper = xmax + pad
        else:
            span = xmax - xmin
            lower = xmin - span * 0.05
            upper = xmax + span * 0.05
        if lower >= xmin:
            lower = xmin - _LCR_X_AXIS_GRID_V
        if upper <= xmax:
            upper = xmax + _LCR_X_AXIS_GRID_V
        if xmin >= 0:
            lower = max(lower, 0.0)
        self._configure_lcr_x_axis_grid(self._refs.axis_x, lower, upper)

    @staticmethod
    def _autoscale_value_axis(
        axis: QValueAxis,
        ys: list[float],
        *,
        floor_min: float | None = None,
    ) -> None:
        ymin = min(ys)
        ymax = max(ys)
        if ymin == ymax:
            center = ymax if ymax != 0 else (floor_min or 1.0)
            half_span = max(abs(center) * 0.5, abs(center) * 0.1, 1e-12)
            ymin = center - half_span
            ymax = center + half_span
        else:
            span = ymax - ymin
            ymin -= span * 0.1
            ymax += span * 0.1
        if floor_min is not None:
            ymin = max(ymin, floor_min)
        peak = max(abs(ymin), abs(ymax))
        if peak < 0.01 or peak >= 10000:
            axis.setLabelFormat("%.2e")
        else:
            axis.setLabelFormat("%.3f")
        axis.setRange(ymin, ymax)
        axis.setLabelsVisible(True)
        axis.setTickCount(_CHART_Y_MAJOR_TICK_COUNT)
        axis.setGridLineVisible(True)
        axis.setMinorGridLineVisible(False)

    def _autoscale_lcr_y_axis(self, axis: QValueAxis, ys: list[float]) -> None:
        self._autoscale_value_axis(axis, ys)
        axis.setLabelFormat("%.2e")
