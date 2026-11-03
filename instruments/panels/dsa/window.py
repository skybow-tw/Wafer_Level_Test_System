"""DSA instrument control window."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QMessageBox, QTableWidgetItem, QWidget

from instruments.panels.base import InstrumentPanelBase
from instruments.panels.common import resolve_work_dir
from instruments.panels.dsa.chart import DsaChartController, magnitude_v_to_db
from instruments.panels.dsa.hardware_dialog import DsaHardwareDialog
from instruments.panels.dsa.logic import DsaLogic, compute_resonance_and_bandwidth
from instruments.panels.dsa.settings_store import (
    DsaSignalSettings,
    default_settings_path,
    load_dsa_settings,
    load_dsa_signal_settings,
    save_dsa_settings,
    save_dsa_signal_settings,
)
from instruments.panels.dsa.ui import DsaUi, build_dsa_ui
from instruments.panels.registry import DSA_DISPLAY_NAME
from save_params import get_save_params
from theme_config import THEMES, generate_theme_qss


class DsaWindow(InstrumentPanelBase):
    def __init__(
        self,
        parent: QWidget | None = None,
        work_dir: Path | None = None,
    ) -> None:
        super().__init__(DSA_DISPLAY_NAME, parent=parent, work_dir=work_dir)
        self.setMinimumSize(1180, 720)
        self.resize(1280, 780)
        work = resolve_work_dir(self, work_dir)
        self._chart = DsaChartController()
        self._logic = DsaLogic(self._chart, work, parent=self)
        self._ui: DsaUi = build_dsa_ui(self._chart.host)
        self.setCentralWidget(self._ui.root)
        self._settings_path = default_settings_path()
        self._statistics_values: tuple[float | None, float | None] = (None, None)
        self._build_menu()
        self._wire_ui()
        self._logic.measurement_finished.connect(self._on_measurement_finished)
        self._logic.measurement_failed.connect(self._on_measurement_failed)
        self._logic.measuring_changed.connect(self._on_measuring_changed)
        self._logic.pause_changed.connect(self._on_pause_changed)
        self._logic.point_measured.connect(self._on_point_measured)
        self._load_saved_hardware_settings()
        self._apply_saved_signal_settings()
        self.setStyleSheet(generate_theme_qss(THEMES["light"]))

    def _build_menu(self) -> None:
        settings_menu = self.menuBar().addMenu("設定")
        channel_action = settings_menu.addAction("PXI DSA 儀器卡")
        channel_action.triggered.connect(self._open_hardware_settings)
        self._settings_menu = settings_menu

    def _wire_ui(self) -> None:
        ui = self._ui
        ui.btn_measure.clicked.connect(self._on_measure_clicked)
        ui.btn_pause.clicked.connect(self._on_pause_clicked)
        ui.btn_exit.clicked.connect(self.close)

    @property
    def is_measuring(self) -> bool:
        return self._logic.is_measuring

    @property
    def uses_statistics_report(self) -> bool:
        return True

    def get_statistics_report_headers(self) -> tuple[str, ...]:
        return ("X", "Y", "Resonance_Hz", "Bandwidth_Hz")

    def get_statistics_report_values(self) -> tuple[float | int | None, ...]:
        return self._statistics_values

    def start_measurement(
        self,
        die_x: int | None = None,
        die_y: int | None = None,
        *,
        automated: bool = False,
    ) -> bool:
        ui = self._ui
        params = get_save_params()
        if die_x is None:
            die_x = params.x
        if die_y is None:
            die_y = params.y
        try:
            started = self._logic.start_measurement(
                start_hz=ui.spin_freq_start.value(),
                stop_hz=ui.spin_freq_stop.value(),
                point_count=ui.spin_point_count.value(),
                vpp=ui.spin_vpp.value(),
                dc_offset=ui.spin_dc_offset.value(),
                die_x=die_x,
                die_y=die_y,
                save_to_file=ui.chk_save_to_file.isChecked(),
            )
        except ValueError as exc:
            if not automated:
                QMessageBox.warning(self, "掃頻設定錯誤", str(exc))
            return False
        except RuntimeError as exc:
            if not automated:
                QMessageBox.information(self, "DSA", str(exc))
            return False
        if started:
            self._save_signal_settings()
        return started

    def _on_measure_clicked(self) -> None:
        self.start_measurement()

    def _on_pause_clicked(self) -> None:
        self._logic.toggle_pause()

    def _on_measuring_changed(self, measuring: bool) -> None:
        ui = self._ui
        if measuring:
            self._reset_results_panel()
        ui.btn_measure.setEnabled(not measuring)
        ui.btn_pause.setEnabled(measuring)
        ui.chk_save_to_file.setEnabled(not measuring)
        ui.spin_freq_start.setEnabled(not measuring)
        ui.spin_freq_stop.setEnabled(not measuring)
        ui.spin_point_count.setEnabled(not measuring)
        ui.spin_vpp.setEnabled(not measuring)
        ui.spin_dc_offset.setEnabled(not measuring)
        self._settings_menu.setEnabled(not measuring)
        if not measuring:
            ui.btn_pause.setText("Pause")

    def _on_pause_changed(self, paused: bool) -> None:
        self._ui.btn_pause.setText("Resume" if paused else "Pause")

    def _on_measurement_failed(self, message: str) -> None:
        # Forward failures to an active automated measurement session.  The
        # base signal is otherwise unused for a standalone DSA panel.
        self.measurement_failed.emit(message)
        QMessageBox.warning(self, "DSA 量測失敗", message)

    def _on_point_measured(
        self, frequency_hz: float, magnitude_v: float, phase_deg: float
    ) -> None:
        table = self._ui.table_sweep
        row = table.rowCount()
        table.insertRow(row)
        values = (
            f"{frequency_hz:.2f}",
            f"{magnitude_v_to_db(magnitude_v):.2f}",
            f"{phase_deg:.2f}",
        )
        for column, text in enumerate(values):
            item = QTableWidgetItem(text)
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            table.setItem(row, column, item)
        table.scrollToBottom()

    def _on_measurement_finished(
        self, x_values: list[float], y_values: list[float]
    ) -> None:
        resonance_hz, bandwidth_hz = compute_resonance_and_bandwidth(
            x_values, y_values
        )
        self._statistics_values = (resonance_hz, bandwidth_hz)
        self._ui.label_resonance.setText(_format_hz(resonance_hz))
        self._ui.label_bandwidth.setText(_format_hz(bandwidth_hz))
        self.measurement_finished.emit(x_values, y_values)

    def _reset_results_panel(self) -> None:
        self._ui.table_sweep.setRowCount(0)
        self._ui.label_resonance.setText("—")
        self._ui.label_bandwidth.setText("—")

    def _open_hardware_settings(self) -> None:
        dialog = DsaHardwareDialog(self._logic.hardware_settings, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        settings = dialog.selected_settings()
        self._logic.set_hardware_settings(settings)
        try:
            save_dsa_settings(settings, self._settings_path)
        except Exception as exc:
            QMessageBox.warning(self, "DSA", f"儲存設定檔失敗：\n{exc}")

    def _load_saved_hardware_settings(self) -> None:
        try:
            settings = load_dsa_settings(self._settings_path)
        except Exception as exc:
            QMessageBox.warning(self, "DSA", f"載入設定檔失敗，改用預設值：\n{exc}")
            return
        self._logic.set_hardware_settings(settings)

    def _collect_signal_settings(self) -> DsaSignalSettings:
        ui = self._ui
        return DsaSignalSettings(
            freq_start_hz=ui.spin_freq_start.value(),
            freq_stop_hz=ui.spin_freq_stop.value(),
            point_count=ui.spin_point_count.value(),
            vpp=ui.spin_vpp.value(),
            dc_offset_v=ui.spin_dc_offset.value(),
            save_to_file=ui.chk_save_to_file.isChecked(),
        )

    def _save_signal_settings(self) -> None:
        try:
            save_dsa_signal_settings(
                self._collect_signal_settings(), self._settings_path
            )
        except Exception:
            # Non-fatal: next open falls back to previous file or UI defaults.
            pass

    def _apply_saved_signal_settings(self) -> None:
        try:
            settings = load_dsa_signal_settings(self._settings_path)
        except Exception as exc:
            QMessageBox.warning(
                self, "DSA", f"載入 Signal Settings 失敗，改用預設值：\n{exc}"
            )
            return
        ui = self._ui
        ui.spin_freq_start.setValue(settings.freq_start_hz)
        ui.spin_freq_stop.setValue(settings.freq_stop_hz)
        ui.spin_point_count.setValue(settings.point_count)
        ui.spin_vpp.setValue(settings.vpp)
        ui.spin_dc_offset.setValue(settings.dc_offset_v)
        ui.chk_save_to_file.setChecked(settings.save_to_file)

    def closeEvent(self, event) -> None:  # noqa: ANN001
        self._logic.stop_measurement()
        self._save_signal_settings()
        super().closeEvent(event)


def _format_hz(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.2f}"
