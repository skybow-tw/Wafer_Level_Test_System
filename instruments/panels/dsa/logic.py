"""DSA frequency-sweep measurement logic for NI PXI-4461."""

from __future__ import annotations

import csv
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from instruments.panels.dsa.chart import DsaChartController, magnitude_v_to_db
from instruments.pxi4461 import (
    DsaHardwareSettings,
    build_frequency_points,
    measure_tone,
)
from save_params import get_save_params

_BANDWIDTH_DB_DROP = 3.0


def compute_resonance_and_bandwidth(
    frequencies_hz: list[float],
    magnitudes_v: list[float],
) -> tuple[float | None, float | None]:
    """Return peak-magnitude frequency and -3 dB bandwidth.

    Resonance is the frequency of the maximum magnitude. Bandwidth is the
    half-power width (magnitude 3 dB below the peak), interpolated between
    adjacent sweep points. Bandwidth is None if either -3 dB crossing is
    outside the measured range.
    """
    count = min(len(frequencies_hz), len(magnitudes_v))
    if count == 0:
        return None, None
    frequencies = frequencies_hz[:count]
    magnitudes_db = [magnitude_v_to_db(value) for value in magnitudes_v[:count]]
    peak_index = max(range(count), key=magnitudes_db.__getitem__)
    resonance_hz = frequencies[peak_index]
    threshold_db = magnitudes_db[peak_index] - _BANDWIDTH_DB_DROP
    lower_hz = _interpolate_threshold(
        frequencies, magnitudes_db, peak_index, -1, threshold_db
    )
    upper_hz = _interpolate_threshold(
        frequencies, magnitudes_db, peak_index, 1, threshold_db
    )
    if lower_hz is None or upper_hz is None:
        return resonance_hz, None
    return resonance_hz, max(0.0, upper_hz - lower_hz)


def _interpolate_threshold(
    frequencies: list[float],
    magnitudes_db: list[float],
    peak_index: int,
    direction: int,
    threshold_db: float,
) -> float | None:
    count = len(frequencies)
    index = peak_index
    while 0 <= index + direction < count:
        next_index = index + direction
        y0 = magnitudes_db[index]
        y1 = magnitudes_db[next_index]
        crossed = (y0 >= threshold_db >= y1) or (y0 <= threshold_db <= y1)
        if crossed:
            span = y1 - y0
            if abs(span) < 1e-12:
                return frequencies[index]
            ratio = (threshold_db - y0) / span
            f0 = frequencies[index]
            f1 = frequencies[next_index]
            return f0 + ratio * (f1 - f0)
        index = next_index
    return None


def save_dsa_measurement_csv(
    work_dir: Path,
    *,
    frequencies_hz: list[float],
    magnitudes_v: list[float],
    phases_deg: list[float],
    measurement_die_x: int | None,
    measurement_die_y: int | None,
    resonance_hz: float | None,
    bandwidth_hz: float | None,
) -> Path:
    params = get_save_params()
    die_x = measurement_die_x if measurement_die_x is not None else params.x
    die_y = measurement_die_y if measurement_die_y is not None else params.y
    output_path = params.output_path(work_dir, x=die_x, y=die_y, tag="DSA")

    def _hz_cell(value: float | None) -> str | float:
        if value is None:
            return ""
        return value

    with output_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "Frequency(HZ)",
                "Magnitude(dB)",
                "Phase(deg)",
                "Resonance(HZ)",
                "Bandwidth(HZ)",
            ]
        )
        for row_index, (frequency_hz, magnitude_v, phase_deg) in enumerate(
            zip(frequencies_hz, magnitudes_v, phases_deg, strict=True)
        ):
            if row_index == 0:
                writer.writerow(
                    [
                        frequency_hz,
                        magnitude_v_to_db(magnitude_v),
                        phase_deg,
                        _hz_cell(resonance_hz),
                        _hz_cell(bandwidth_hz),
                    ]
                )
            else:
                writer.writerow(
                    [
                        frequency_hz,
                        magnitude_v_to_db(magnitude_v),
                        phase_deg,
                        "",
                        "",
                    ]
                )
    return output_path


class DsaLogic(QObject):
    """Runs an AO sine sweep and plots AI magnitude / phase."""

    measurement_finished = Signal(list, list)
    measurement_failed = Signal(str)
    measuring_changed = Signal(bool)
    pause_changed = Signal(bool)
    point_measured = Signal(float, float, float)

    def __init__(
        self,
        chart: DsaChartController,
        work_dir: Path,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._chart = chart
        self._work_dir = work_dir
        self._hardware = DsaHardwareSettings()
        self._measuring = False
        self._paused = False
        self._measure_timer = QTimer(self)
        self._measure_timer.setSingleShot(True)
        self._measure_timer.timeout.connect(self._measure_next_point)
        self._vpp = 1.0
        self._dc_offset = 0.0
        self._frequencies: list[float] = []
        self._point_index = 0
        self._x_values: list[float] = []
        self._y_values: list[float] = []
        self._phase_values: list[float] = []
        self._measurement_die_x: int | None = None
        self._measurement_die_y: int | None = None
        self._save_to_file = True

    @property
    def is_measuring(self) -> bool:
        return self._measuring

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def hardware_settings(self) -> DsaHardwareSettings:
        return replace(self._hardware)

    def set_hardware_settings(self, settings: DsaHardwareSettings) -> None:
        self._hardware = replace(settings)

    def start_measurement(
        self,
        *,
        start_hz: float,
        stop_hz: float,
        point_count: int,
        vpp: float,
        dc_offset: float = 0.0,
        die_x: int | None = None,
        die_y: int | None = None,
        save_to_file: bool = True,
    ) -> bool:
        if self._measuring:
            return False
        if not self._hardware.ao_channel or not self._hardware.ai_response_channel:
            raise RuntimeError("請先從「設定」選擇 AO 與 AI 通道。")
        self._frequencies = build_frequency_points(start_hz, stop_hz, point_count)
        self._vpp = vpp
        self._dc_offset = dc_offset
        self._measurement_die_x = die_x
        self._measurement_die_y = die_y
        self._save_to_file = save_to_file
        self._point_index = 0
        self._x_values = []
        self._y_values = []
        self._phase_values = []
        self._paused = False
        self._chart.clear()
        self._measuring = True
        self.measuring_changed.emit(True)
        self.pause_changed.emit(False)
        self._measure_timer.start(0)
        return True

    def pause_measurement(self) -> None:
        if not self._measuring or self._paused:
            return
        self._paused = True
        self._measure_timer.stop()
        self.pause_changed.emit(True)

    def resume_measurement(self) -> None:
        if not self._measuring or not self._paused:
            return
        self._paused = False
        self.pause_changed.emit(False)
        self._measure_timer.start(0)

    def toggle_pause(self) -> None:
        if self._paused:
            self.resume_measurement()
        else:
            self.pause_measurement()

    def stop_measurement(self) -> None:
        if not self._measuring:
            return
        self._measure_timer.stop()
        self._paused = False
        self._measuring = False
        self.pause_changed.emit(False)
        self.measuring_changed.emit(False)

    def _measure_next_point(self) -> None:
        if not self._measuring or self._paused:
            return
        if self._point_index >= len(self._frequencies):
            self._finish_measurement()
            return

        frequency_hz = self._frequencies[self._point_index]
        try:
            result = measure_tone(
                self._hardware,
                frequency_hz,
                self._vpp,
                self._dc_offset,
            )
        except Exception as exc:
            self.stop_measurement()
            self.measurement_failed.emit(str(exc))
            return

        self._x_values.append(result.frequency_hz)
        self._y_values.append(result.magnitude_v)
        self._phase_values.append(result.phase_deg)
        self._chart.append_point(
            result.frequency_hz, result.magnitude_v, result.phase_deg
        )
        self.point_measured.emit(
            result.frequency_hz, result.magnitude_v, result.phase_deg
        )
        self._point_index += 1
        if self._point_index < len(self._frequencies):
            if not self._paused:
                self._measure_timer.start(0)
        else:
            self._finish_measurement()

    def _finish_measurement(self) -> None:
        self._paused = False
        self._measuring = False
        self.pause_changed.emit(False)
        self.measuring_changed.emit(False)
        if self._x_values and self._save_to_file:
            resonance_hz, bandwidth_hz = compute_resonance_and_bandwidth(
                self._x_values, self._y_values
            )
            try:
                save_dsa_measurement_csv(
                    self._work_dir,
                    frequencies_hz=self._x_values,
                    magnitudes_v=self._y_values,
                    phases_deg=self._phase_values,
                    measurement_die_x=self._measurement_die_x,
                    measurement_die_y=self._measurement_die_y,
                    resonance_hz=resonance_hz,
                    bandwidth_hz=bandwidth_hz,
                )
            except Exception as exc:
                self.measurement_failed.emit(str(exc))
        self._measurement_die_x = None
        self._measurement_die_y = None
        self.measurement_finished.emit(
            self._x_values.copy(),
            self._y_values.copy(),
        )
