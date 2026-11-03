"""Real LCR Meter (E4980A) measurement logic."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from instruments.e4980a import (
    AgilentE4980A,
    E4980A_VOLTAGE_MAX_V,
    E4980A_VOLTAGE_MIN_V,
)
from instruments.gpib_scanner import GpibInstrumentInfo, list_gpib_instruments
from instruments.panels.lcr.chart import LcrChartController
from instruments.panels.lcr.measurement import (
    FF_TO_F,
    build_dc_offset_sweep_points,
    generate_lcr_simulation_values,
    save_lcr_measurement_csv,
)
from instruments.panels.lcr_meter.constants import (
    VP_DETECT_METHOD_2_POINT_SLOPE,
    VP_DETECT_METHOD_AVERAGE,
    VP_SLOPE_DELTA_CAP_THRESHOLD_FF,
)
from lcr_meter_settings import LcrMeterSettingsStore
from statistics_report import LcrDieSummary

_MEASUREMENT_POINT_COUNT = 20
_MEASUREMENT_POINT_DELAY_MS = 100


class LcrMeterLogic(QObject):
    """Runs E4980A DC-offset sweeps and optional simulation."""

    measurement_finished = Signal(list, list)
    measurement_failed = Signal(str)
    measuring_changed = Signal(bool)
    hardware_warning = Signal(str, str)  # title, message

    def __init__(
        self,
        chart: LcrChartController,
        work_dir: Path,
        parent: QObject | None = None,
        amplitude_mode: bool = False,
    ) -> None:
        super().__init__(parent)
        self._chart = chart
        self._work_dir = work_dir
        self._amplitude_mode = amplitude_mode
        self._e4980a: AgilentE4980A | None = None
        self._gpib_instruments: list[GpibInstrumentInfo] = []
        self._measuring = False
        self._measure_timer = QTimer(self)
        self._measure_timer.setSingleShot(True)
        self._measure_timer.timeout.connect(self._append_next_simulation_point)
        self._dc_offset_points: list[float] = []
        self._dc_offset_point_index = 0
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
        self._lcr_r0_value: float | None = None
        self._lcr_delta_c: float | None = None
        self._vp_early_stop_triggered = False
        self._vp_detect_method = VP_DETECT_METHOD_2_POINT_SLOPE
        self._vp_threshold_ff = VP_SLOPE_DELTA_CAP_THRESHOLD_FF
        self._simulation_mode = False
        self._save_to_file = True

    @property
    def is_measuring(self) -> bool:
        return self._measuring

    @property
    def e4980a(self) -> AgilentE4980A | None:
        return self._e4980a

    @property
    def gpib_instruments(self) -> list[GpibInstrumentInfo]:
        return self._gpib_instruments

    def settings_store(self) -> LcrMeterSettingsStore:
        file_name = (
            "lcr_meter_bolometer_settings.json"
            if self._amplitude_mode
            else "lcr_meter_settings.json"
        )
        return LcrMeterSettingsStore(self._work_dir, file_name=file_name)

    def list_gpib(self) -> list[GpibInstrumentInfo]:
        self._gpib_instruments = list_gpib_instruments()
        return self._gpib_instruments

    def disconnect_instrument(self) -> None:
        if self._e4980a is not None:
            self._e4980a.disconnect()
            self._e4980a = None

    def connect_gpib(self, resource_name: str) -> None:
        if self._e4980a is not None and self._e4980a.resource_name == resource_name:
            return
        self.disconnect_instrument()
        driver = AgilentE4980A(resource_name)
        driver.connect()
        self._e4980a = driver

    def configure(
        self, function_label: str, voltage_v: float, frequency_hz: float
    ) -> None:
        if self._e4980a is None:
            raise RuntimeError("請先從 GPIB 儀器選單選擇並連線儀器。")
        if self._amplitude_mode:
            self._e4980a.set_impedance_function(function_label)
            self._e4980a.set_frequency(frequency_hz)
            self._e4980a.set_dc_offset(0.0)
        else:
            self._e4980a.apply_settings(function_label, voltage_v, frequency_hz)
        self._chart.function_label = function_label

    def set_cable_length(self, length_m: int) -> None:
        if self._e4980a is None:
            raise RuntimeError("請先從 GPIB 儀器選單選擇並連線儀器。")
        self._e4980a.set_cable_length(length_m)

    def execute_open_correction(self) -> None:
        if self._e4980a is None:
            raise RuntimeError("請先從 GPIB 儀器選單選擇並連線儀器。")
        self._e4980a.execute_open_correction()

    def execute_short_correction(self) -> None:
        if self._e4980a is None:
            raise RuntimeError("請先從 GPIB 儀器選單選擇並連線儀器。")
        self._e4980a.execute_short_correction()

    def set_vp_detect_params(self, method: str, threshold_ff: float) -> None:
        self._vp_detect_method = method
        self._vp_threshold_ff = threshold_ff

    def get_lcr_die_summary(self) -> LcrDieSummary:
        return LcrDieSummary(
            co=self._lcr_c0_value,
            vp=0.0 if self._lcr_vp_offset_v is None else self._lcr_vp_offset_v,
            delta_c=self._lcr_delta_c,
        )

    def get_result_readouts(
        self,
    ) -> tuple[float | None, float | None, float | None, float | None]:
        return (
            self._lcr_c0_value,
            self._lcr_vp_offset_v,
            self._lcr_r0_value,
            self._lcr_delta_c,
        )

    def start_measurement(
        self,
        *,
        die_x: int | None,
        die_y: int | None,
        start_v: float,
        stop_v: float,
        step_v: float,
        function_label: str,
        vp_method: str,
        vp_threshold_ff: float,
        save_to_file: bool = True,
        automated: bool = False,
    ) -> bool:
        if self._measuring:
            return False
        if self._e4980a is None:
            if not automated:
                raise RuntimeError("請先從 GPIB 儀器選單選擇並連線儀器。")
            return False
        if self._amplitude_mode:
            if not (
                E4980A_VOLTAGE_MIN_V <= start_v <= E4980A_VOLTAGE_MAX_V
                and E4980A_VOLTAGE_MIN_V <= stop_v <= E4980A_VOLTAGE_MAX_V
            ):
                raise ValueError("Amplitude must be between 0.005 V and 2.0 V")
            if step_v <= 0:
                raise ValueError("Amplitude step must be greater than zero")
        self._dc_offset_points = build_dc_offset_sweep_points(start_v, stop_v, step_v)
        self._measurement_die_x = die_x
        self._measurement_die_y = die_y
        self._vp_detect_method = vp_method
        self._vp_threshold_ff = vp_threshold_ff
        self._save_to_file = save_to_file
        self._simulation_mode = False
        self._chart.function_label = function_label
        self._begin_common()
        self._dc_offset_point_index = 0
        QTimer.singleShot(0, self._measure_next_dc_offset_point)
        return True

    def run_simulation(
        self,
        *,
        die_x: int | None,
        die_y: int | None,
        start_v: float,
        stop_v: float,
        step_v: float,
        function_label: str,
    ) -> bool:
        if self._measuring:
            return False
        self._dc_offset_points = build_dc_offset_sweep_points(start_v, stop_v, step_v)
        self._measurement_die_x = die_x
        self._measurement_die_y = die_y
        self._simulation_mode = True
        self._chart.function_label = function_label
        self._begin_common()
        point_count = len(self._dc_offset_points) or _MEASUREMENT_POINT_COUNT
        self._pending_y_values, self._pending_secondary_values = (
            generate_lcr_simulation_values(point_count)
        )
        self._schedule_next_simulation_point()
        return True

    def _begin_common(self) -> None:
        self._measuring = True
        self.measuring_changed.emit(True)
        self._chart.clear_series()
        self._measure_x_values = []
        self._measure_y_values = []
        self._measure_secondary_values = []
        self._measure_point_index = 0
        self._vp_early_stop_triggered = False
        self._lcr_c0_value = None
        self._lcr_vp_offset_v = None
        self._lcr_r0_value = None
        self._lcr_delta_c = None

    def _measure_next_dc_offset_point(self) -> None:
        if self._dc_offset_point_index >= len(self._dc_offset_points):
            self._finish_measurement()
            return

        if self._e4980a is None:
            self._finish_measurement()
            self.hardware_warning.emit("E4980A 量測失敗", "儀器連線已中斷。")
            return

        sweep_v = self._dc_offset_points[self._dc_offset_point_index]
        try:
            if self._amplitude_mode:
                self._e4980a.set_voltage_level(sweep_v)
            else:
                self._e4980a.set_dc_offset(sweep_v)
            primary_value, secondary_value = self._e4980a.measure_impedance_values()
        except Exception as exc:
            self._finish_measurement()
            self.hardware_warning.emit("E4980A 量測失敗", str(exc))
            return

        self._measure_x_values.append(sweep_v)
        self._measure_y_values.append(primary_value)
        self._measure_secondary_values.append(secondary_value)
        self._chart.append_point(sweep_v, primary_value, secondary_value)

        if self._dc_offset_point_index == 0:
            self._lcr_c0_value = primary_value
            self._lcr_r0_value = secondary_value

        if self._should_stop_by_vp_detect():
            self._vp_early_stop_triggered = True
            self._lcr_vp_offset_v = sweep_v
            if self._lcr_c0_value is not None:
                self._lcr_delta_c = primary_value - self._lcr_c0_value
            self._finish_measurement()
            return

        self._dc_offset_point_index += 1
        QTimer.singleShot(0, self._measure_next_dc_offset_point)

    def _vp_threshold_f(self) -> float:
        return self._vp_threshold_ff * FF_TO_F

    def _should_stop_by_vp_detect(self) -> bool:
        if self._simulation_mode:
            return False
        if self._chart.function_label != "Cp-Rp":
            return False
        if self._vp_detect_method == VP_DETECT_METHOD_2_POINT_SLOPE:
            return self._should_stop_by_vp_2point_slope()
        if self._vp_detect_method == VP_DETECT_METHOD_AVERAGE:
            return self._should_stop_by_vp_average()
        return False

    def _should_stop_by_vp_2point_slope(self) -> bool:
        if len(self._measure_y_values) < 2:
            return False
        delta_cap = abs(self._measure_y_values[-1] - self._measure_y_values[-2])
        return delta_cap > self._vp_threshold_f()

    def _should_stop_by_vp_average(self) -> bool:
        if len(self._measure_y_values) < 2:
            return False
        latest = self._measure_y_values[-1]
        average = sum(self._measure_y_values) / len(self._measure_y_values)
        if latest <= average:
            return False
        return (latest - average) > self._vp_threshold_f()

    def _schedule_next_simulation_point(self) -> None:
        self._measure_timer.start(_MEASUREMENT_POINT_DELAY_MS)

    def _append_next_simulation_point(self) -> None:
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
            self._lcr_r0_value = secondary_value
        self._chart.append_point(x_value, y_value, secondary_value)
        self._measure_point_index += 1

        if self._measure_point_index < total_points:
            self._schedule_next_simulation_point()
        else:
            self._finish_measurement()

    def _apply_default_vp_if_undetected(self) -> None:
        if self._simulation_mode:
            return
        if self._lcr_vp_offset_v is None:
            self._lcr_vp_offset_v = 0.0

    def _reset_lcr_sweep_output(self) -> None:
        if self._simulation_mode or self._e4980a is None:
            return
        if self._amplitude_mode:
            try:
                self._e4980a.set_voltage_level(E4980A_VOLTAGE_MIN_V)
            except Exception as exc:
                self.hardware_warning.emit(
                    "E4980A amplitude reset failed",
                    f"Could not reset amplitude to {E4980A_VOLTAGE_MIN_V} V: {exc}",
                )
            return
        try:
            self._e4980a.set_dc_offset(0.0)
        except Exception as exc:
            self.hardware_warning.emit(
                "E4980A DC offset 重設失敗",
                f"量測已結束，但無法將 DC offset 重設為 0 V：\n{exc}",
            )

    def _finish_measurement(self) -> None:
        self._measuring = False
        self.measuring_changed.emit(False)
        self._apply_default_vp_if_undetected()
        self._reset_lcr_sweep_output()
        if self._measure_x_values and self._save_to_file:
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
                    x_axis_header="Amplitude(V)" if self._amplitude_mode else None,
                )
            except Exception as exc:
                self.measurement_failed.emit(str(exc))
        self._measurement_die_x = None
        self._measurement_die_y = None
        self.measurement_finished.emit(
            self._measure_x_values.copy(),
            self._measure_y_values.copy(),
        )
