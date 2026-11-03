"""Real LCR Meter (E4980A) instrument control window."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QMessageBox, QWidget

from instruments.e4980a import (
    E4980A_FREQ_MAX_HZ,
    E4980A_FREQ_MIN_HZ,
    E4980A_IMPEDANCE_FUNCTIONS,
    E4980A_VOLTAGE_MAX_V,
    E4980A_VOLTAGE_MIN_V,
)
from instruments.panels.base import InstrumentPanelBase
from instruments.panels.common import resolve_work_dir
from instruments.panels.lcr.chart import LcrChartController
from instruments.panels.lcr_meter.constants import VP_DETECT_METHOD_2_POINT_SLOPE
from instruments.panels.lcr_meter.logic import LcrMeterLogic
from instruments.panels.lcr_meter.ui import LcrMeterUi, build_lcr_meter_ui
from instruments.panels.registry import (
    LCR_METER_BOLOMETER_DISPLAY_NAME,
    LCR_METER_DISPLAY_NAME,
)
from lcr_meter_settings import LcrMeterSettings
from save_params import get_save_params
from statistics_report import LcrDieSummary
from theme_config import THEMES, generate_theme_qss


class LcrMeterWindow(InstrumentPanelBase):
    def __init__(
        self,
        parent: QWidget | None = None,
        work_dir: Path | None = None,
        amplitude_mode: bool = False,
    ) -> None:
        self._amplitude_mode = amplitude_mode
        display_name = (
            LCR_METER_BOLOMETER_DISPLAY_NAME
            if amplitude_mode
            else LCR_METER_DISPLAY_NAME
        )
        super().__init__(display_name, parent=parent, work_dir=work_dir)
        self.setStyleSheet(generate_theme_qss(THEMES["light"]))
        self.setMinimumSize(800, 600)
        self.resize(900, 640)
        work = resolve_work_dir(self, work_dir)
        self._chart = LcrChartController(
            display_name, x_axis_title="Amplitude(V)" if amplitude_mode else None
        )
        self._chart.function_label = "Cp-Rp"
        self._logic = LcrMeterLogic(
            self._chart, work, parent=self, amplitude_mode=amplitude_mode
        )
        self._ui: LcrMeterUi = build_lcr_meter_ui(
            self._chart.chart_view, amplitude_mode=amplitude_mode
        )
        self.setCentralWidget(self._ui.root)
        self._wire_ui()
        self._logic.measurement_finished.connect(self.measurement_finished)
        self._logic.measurement_finished.connect(self._update_result_readouts)
        self._logic.measurement_failed.connect(self._on_measurement_failed)
        self._logic.measuring_changed.connect(self._on_measuring_changed)
        self._logic.hardware_warning.connect(self._on_hardware_warning)
        self._apply_saved_lcr_settings()

    def _wire_ui(self) -> None:
        ui = self._ui
        ui.cmb_gpib.scan_requested.connect(self._scan_gpib_instruments)
        ui.cmb_gpib.currentIndexChanged.connect(self._on_gpib_selection_changed)
        ui.cmb_cable_length.currentIndexChanged.connect(
            self._on_cable_length_changed
        )
        ui.btn_open_correction.clicked.connect(self._on_open_correction_clicked)
        ui.btn_short_correction.clicked.connect(self._on_short_correction_clicked)
        ui.btn_start.clicked.connect(self._on_start_clicked)
        ui.btn_exit.clicked.connect(self.close)

    @property
    def is_measuring(self) -> bool:
        return self._logic.is_measuring

    @property
    def is_virtual_lcr(self) -> bool:
        return False

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
        return self._logic.get_lcr_die_summary()

    def start_measurement(
        self,
        die_x: int | None = None,
        die_y: int | None = None,
        *,
        automated: bool = False,
    ) -> bool:
        ui = self._ui
        if not self._apply_instrument_configuration(automated=automated):
            return False
        params = get_save_params()
        if die_x is None:
            die_x = params.x
        if die_y is None:
            die_y = params.y
        try:
            return self._logic.start_measurement(
                die_x=die_x,
                die_y=die_y,
                start_v=ui.spin_dc_offset_start.value(),
                stop_v=ui.spin_dc_offset_stop.value(),
                step_v=ui.spin_dc_offset_step.value(),
                function_label=ui.cmb_function.currentText(),
                vp_method=ui.cmb_vp_detect_method.currentText(),
                vp_threshold_ff=ui.spin_vp_threshold_f.value(),
                save_to_file=ui.chk_save_to_file.isChecked(),
                automated=automated,
            )
        except ValueError as exc:
            if not automated:
                QMessageBox.warning(self, "DC Offset 設定錯誤", str(exc))
            return False
        except RuntimeError as exc:
            if not automated:
                QMessageBox.information(self, "E4980A", str(exc))
            return False

    def _apply_instrument_configuration(self, *, automated: bool = False) -> bool:
        ui = self._ui
        function_label = ui.cmb_function.currentText()
        voltage_v = ui.spin_voltage.value()
        frequency_hz = ui.spin_frequency.value()
        try:
            self._logic.configure(function_label, voltage_v, frequency_hz)
        except RuntimeError as exc:
            if not automated:
                QMessageBox.information(self, "E4980A", str(exc))
            return False
        except Exception as exc:
            if not automated:
                QMessageBox.warning(self, "E4980A 設定失敗", str(exc))
            return False

        self._save_lcr_settings_defaults()
        return True

    def _on_start_clicked(self) -> None:
        self.start_measurement()

    def _on_measuring_changed(self, measuring: bool) -> None:
        self._ui.btn_start.setEnabled(not measuring)
        if measuring:
            self._clear_result_readouts()

    def _format_result_value(self, value: float | None) -> str:
        if value is None:
            return "—"
        return f"{value:.6g}"

    def _clear_result_readouts(self) -> None:
        for label in (
            self._ui.label_c0,
            self._ui.label_vp,
            self._ui.label_r0,
            self._ui.label_delta_c,
        ):
            label.setText("—")

    def _update_result_readouts(self, *_args) -> None:
        c0, vp, r0, delta_c = self._logic.get_result_readouts()
        self._ui.label_c0.setText(self._format_result_value(c0))
        self._ui.label_vp.setText(self._format_result_value(vp))
        self._ui.label_r0.setText(self._format_result_value(r0))
        self._ui.label_delta_c.setText(self._format_result_value(delta_c))

    def _on_measurement_failed(self, message: str) -> None:
        QMessageBox.warning(self, "LCR 存檔失敗", message)

    def _on_hardware_warning(self, title: str, message: str) -> None:
        QMessageBox.warning(self, title, message)

    def _scan_gpib_instruments(self) -> None:
        combo = self._ui.cmb_gpib
        current_resource = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("掃描中…", None)
        combo.blockSignals(False)

        try:
            instruments = self._logic.list_gpib()
        except Exception as exc:
            combo.blockSignals(True)
            combo.clear()
            combo.blockSignals(False)
            QMessageBox.warning(self, "GPIB 掃描失敗", str(exc))
            return

        combo.blockSignals(True)
        combo.clear()
        if not instruments:
            combo.addItem("未偵測到 GPIB 儀器", None)
        else:
            restore_index = 0
            for index, info in enumerate(instruments):
                combo.addItem(info.display_label, info.resource_name)
                if info.resource_name == current_resource:
                    restore_index = index
            combo.setCurrentIndex(restore_index)
        combo.blockSignals(False)
        self._on_gpib_selection_changed(combo.currentIndex())

    def _on_gpib_selection_changed(self, index: int) -> None:
        if index < 0:
            return
        resource_name = self._ui.cmb_gpib.itemData(index)
        if not resource_name:
            self._logic.disconnect_instrument()
            return
        try:
            self._logic.connect_gpib(str(resource_name))
            self._apply_cable_length_setting(show_not_connected=False)
        except Exception as exc:
            QMessageBox.warning(self, "GPIB 連線失敗", str(exc))

    def _apply_cable_length_setting(self, *, show_not_connected: bool = True) -> None:
        index = self._ui.cmb_cable_length.currentIndex()
        if index < 0:
            return
        length_m = self._ui.cmb_cable_length.itemData(index)
        if length_m is None:
            return
        try:
            self._logic.set_cable_length(int(length_m))
        except RuntimeError as exc:
            if show_not_connected:
                QMessageBox.information(self, "E4980A", str(exc))
        except Exception as exc:
            QMessageBox.warning(self, "E4980A 電纜長度設定失敗", str(exc))

    def _on_cable_length_changed(self, index: int) -> None:
        if index < 0:
            return
        self._apply_cable_length_setting()

    def _on_open_correction_clicked(self) -> None:
        try:
            self._logic.execute_open_correction()
        except RuntimeError as exc:
            QMessageBox.information(self, "E4980A", str(exc))
            return
        except Exception as exc:
            QMessageBox.warning(self, "E4980A OPEN 校正失敗", str(exc))
            return
        QMessageBox.information(
            self,
            "E4980A",
            "已執行 OPEN 校正並啟用 OPEN correction。",
        )

    def _on_short_correction_clicked(self) -> None:
        try:
            self._logic.execute_short_correction()
        except RuntimeError as exc:
            QMessageBox.information(self, "E4980A", str(exc))
            return
        except Exception as exc:
            QMessageBox.warning(self, "E4980A SHORT 校正失敗", str(exc))
            return
        QMessageBox.information(
            self,
            "E4980A",
            "已執行 SHORT 校正並啟用 SHORT correction。",
        )

    def _collect_lcr_settings_defaults(self) -> LcrMeterSettings:
        ui = self._ui
        return LcrMeterSettings(
            function=ui.cmb_function.currentText(),
            frequency_hz=ui.spin_frequency.value(),
            voltage_v=ui.spin_voltage.value(),
            dc_offset_start_v=ui.spin_dc_offset_start.value(),
            dc_offset_stop_v=ui.spin_dc_offset_stop.value(),
            dc_offset_step_v=ui.spin_dc_offset_step.value(),
            vp_detect_method=ui.cmb_vp_detect_method.currentText(),
            vp_threshold_ff=ui.spin_vp_threshold_f.value(),
        )

    def _save_lcr_settings_defaults(self) -> None:
        self._logic.settings_store().save(self._collect_lcr_settings_defaults())

    def _apply_saved_lcr_settings(self) -> None:
        settings = self._logic.settings_store().load()
        if settings is None:
            return
        ui = self._ui
        if settings.function in E4980A_IMPEDANCE_FUNCTIONS:
            ui.cmb_function.setCurrentText(settings.function)
            self._chart.function_label = settings.function

        ui.spin_frequency.setValue(
            min(max(settings.frequency_hz, E4980A_FREQ_MIN_HZ), E4980A_FREQ_MAX_HZ)
        )
        ui.spin_voltage.setValue(
            min(max(settings.voltage_v, E4980A_VOLTAGE_MIN_V), E4980A_VOLTAGE_MAX_V)
        )
        ui.spin_dc_offset_start.setValue(
            min(
                max(settings.dc_offset_start_v, ui.spin_dc_offset_start.minimum()),
                ui.spin_dc_offset_start.maximum(),
            )
        )
        ui.spin_dc_offset_stop.setValue(
            min(
                max(settings.dc_offset_stop_v, ui.spin_dc_offset_stop.minimum()),
                ui.spin_dc_offset_stop.maximum(),
            )
        )
        ui.spin_dc_offset_step.setValue(
            min(
                max(settings.dc_offset_step_v, ui.spin_dc_offset_step.minimum()),
                ui.spin_dc_offset_step.maximum(),
            )
        )

        index = ui.cmb_vp_detect_method.findText(settings.vp_detect_method)
        if index >= 0:
            ui.cmb_vp_detect_method.setCurrentIndex(index)
        else:
            ui.cmb_vp_detect_method.setCurrentText(VP_DETECT_METHOD_2_POINT_SLOPE)
        ui.spin_vp_threshold_f.setValue(max(settings.vp_threshold_ff, 0.0))

    def closeEvent(self, event) -> None:
        self._logic.disconnect_instrument()
        super().closeEvent(event)


class LcrMeterBolometerWindow(LcrMeterWindow):
    """E4980A panel that sweeps AC signal amplitude for Bolometer devices."""

    def __init__(
        self, parent: QWidget | None = None, work_dir: Path | None = None
    ) -> None:
        super().__init__(parent=parent, work_dir=work_dir, amplitude_mode=True)
