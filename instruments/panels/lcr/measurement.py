"""Shared LCR sweep helpers, simulation values, and CSV export.

Used by both Virtual LCR and the real LCR Meter panels.
"""

from __future__ import annotations

import csv
import random
from pathlib import Path

from instruments.e4980a import (
    impedance_function_bias_csv_header,
    impedance_function_csv_headers,
    impedance_function_saves_capacitance_as_ff,
)
from save_params import get_save_params

LCR_CAP_MIN_F = 1e-12
LCR_CAP_MAX_F = 1e-6
FF_TO_F = 1e-15


def build_dc_offset_sweep_points(
    start_v: float, stop_v: float, step_v: float
) -> list[float]:
    if step_v <= 0:
        raise ValueError("DC Offset 增量必須大於 0。")

    direction = 1.0 if stop_v >= start_v else -1.0
    signed_step = abs(step_v) * direction
    values: list[float] = []
    current = start_v
    guard = 0
    while current <= stop_v + 1e-12 if direction > 0 else current >= stop_v - 1e-12:
        values.append(round(current, 6))
        current += signed_step
        guard += 1
        if guard > 100000:
            raise ValueError("DC Offset 點數過多，請調整起訖或增量。")

    if not values:
        values.append(round(start_v, 6))
    if abs(values[-1] - stop_v) > 1e-9:
        values.append(round(stop_v, 6))
    return values


def generate_lcr_simulation_values(
    point_count: int,
) -> tuple[list[float], list[float]]:
    primary_values: list[float] = []
    secondary_values: list[float] = []
    primary = random.uniform(LCR_CAP_MIN_F * 10, LCR_CAP_MAX_F * 0.01)
    secondary = random.uniform(0.001, 0.05)
    primary_values.append(primary)
    secondary_values.append(secondary)
    for remaining in range(point_count - 1, 0, -1):
        max_step = (LCR_CAP_MAX_F - primary) / remaining * 1.5
        primary = min(
            primary + random.uniform(0, max(max_step, LCR_CAP_MIN_F)),
            LCR_CAP_MAX_F,
        )
        secondary = min(secondary + random.uniform(-0.005, 0.01), 1.0)
        secondary = max(secondary, 0.0)
        primary_values.append(primary)
        secondary_values.append(secondary)
    return primary_values, secondary_values


def save_lcr_measurement_csv(
    work_dir: Path,
    *,
    function_label: str,
    measure_x_values: list[float],
    measure_y_values: list[float],
    measure_secondary_values: list[float],
    measurement_die_x: int | None,
    measurement_die_y: int | None,
    lcr_c0_value: float | None,
    lcr_vp_offset_v: float | None,
    lcr_delta_c: float | None,
    x_axis_header: str | None = None,
) -> Path:
    params = get_save_params()
    die_x = measurement_die_x if measurement_die_x is not None else params.x
    die_y = measurement_die_y if measurement_die_y is not None else params.y
    output_path = params.output_path(work_dir, x=die_x, y=die_y)
    bias_header = x_axis_header or impedance_function_bias_csv_header(function_label)
    primary_header, secondary_header = impedance_function_csv_headers(function_label)
    save_c_as_ff = impedance_function_saves_capacitance_as_ff(function_label)

    def _cap_for_csv(value: float) -> float:
        return value / FF_TO_F if save_c_as_ff else value

    def _cap_summary_cell(value: float | None) -> str | float:
        if value is None:
            return ""
        return _cap_for_csv(value)

    def _format_vp_cell(value: float | None) -> str:
        return f"{0.0 if value is None else value:.2f}"

    with output_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                bias_header,
                primary_header,
                secondary_header,
                "C0",
                "Vp",
                "deltaC",
            ]
        )
        for row_index, (x_value, primary_value, secondary_value) in enumerate(
            zip(
                measure_x_values,
                measure_y_values,
                measure_secondary_values,
                strict=True,
            )
        ):
            csv_primary = _cap_for_csv(primary_value)
            if row_index == 0:
                writer.writerow(
                    [
                        x_value,
                        csv_primary,
                        secondary_value,
                        _cap_summary_cell(lcr_c0_value),
                        _format_vp_cell(lcr_vp_offset_v),
                        _cap_summary_cell(lcr_delta_c),
                    ]
                )
            else:
                writer.writerow([x_value, csv_primary, secondary_value, "", "", ""])
    return output_path
