"""BMT3000 instrument control window."""

from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QMessageBox, QTableWidgetItem, QWidget

from instruments.panels.base import InstrumentPanelBase
from instruments.panels.bmt3000.logic import Bmt3000Logic
from instruments.panels.bmt3000.ui import Bmt3000Ui, build_bmt3000_ui
from instruments.panels.registry import BMT3000_DISPLAY_NAME
from theme_config import THEMES, generate_theme_qss


class _BmtTcpConnectBridge(QObject):
    finished = Signal(bool, str)


class _BmtMeasureBridge(QObject):
    finished = Signal(bool, object, str)


class Bmt3000Window(InstrumentPanelBase):
    def __init__(
        self,
        parent: QWidget | None = None,
        work_dir: Path | None = None,
    ) -> None:
        super().__init__(BMT3000_DISPLAY_NAME, parent=parent, work_dir=work_dir)
        self.setMinimumSize(900, 760)
        self.setMaximumSize(1600, 1200)
        self.resize(900, 760)
        self._logic = Bmt3000Logic()
        self._ui: Bmt3000Ui = build_bmt3000_ui()
        self.setCentralWidget(self._ui.root)
        self._tcp_connect_bridge = _BmtTcpConnectBridge(self)
        self._tcp_connect_bridge.finished.connect(self._on_tcp_connect_finished)
        self._measure_bridge = _BmtMeasureBridge(self)
        self._measure_bridge.finished.connect(self._on_measure_finished)
        self._automated_measurement = False
        self._statistics_values: tuple[float | int | None, ...] = ()
        self._wire_ui()
        self._update_connect_button()
        self.setStyleSheet(generate_theme_qss(THEMES["light"]))

    def _wire_ui(self) -> None:
        ui = self._ui
        ui.btn_connect.clicked.connect(self._on_connect_clicked)
        ui.btn_measure.clicked.connect(self._on_measure_clicked)
        ui.btn_read_pixel.clicked.connect(self._on_read_pixel_clicked)
        ui.btn_exit.clicked.connect(self.close)

    def _set_read_buttons_enabled(self, enabled: bool) -> None:
        self._ui.btn_measure.setEnabled(enabled)
        self._ui.btn_read_pixel.setEnabled(enabled)

    def _update_connect_button(self) -> None:
        ui = self._ui
        logic = self._logic
        measuring = logic.measuring
        if logic.is_connected():
            ui.btn_connect.setText("Disconnect")
            ui.btn_connect.setEnabled(not measuring)
        elif logic.connecting:
            ui.btn_connect.setText("Connecting…")
            ui.btn_connect.setEnabled(False)
        else:
            ui.btn_connect.setText("Connect")
            ui.btn_connect.setEnabled(True)

        if measuring:
            ui.lbl_tcp_status.setText("量測中…")
        elif logic.is_connected():
            endpoint = logic.remote_endpoint()
            if endpoint is not None:
                ui.lbl_tcp_status.setText(f"已連線 {endpoint[0]}:{endpoint[1]}")
            else:
                ui.lbl_tcp_status.setText("已連線")
        elif logic.connecting:
            ui.lbl_tcp_status.setText("連線中…")
        else:
            ui.lbl_tcp_status.setText("未連線")

        editable = not logic.is_connected() and not logic.connecting
        ui.edit_server_ip.setEnabled(editable)
        ui.edit_server_port.setEnabled(editable)
        self._set_read_buttons_enabled(logic.is_connected() and not measuring)

    def _on_connect_clicked(self) -> None:
        if self._logic.measuring:
            return
        if self._logic.is_connected():
            self._logic.disconnect()
            self._update_connect_button()
            return
        if self._logic.connecting:
            return

        try:
            ip, port = self._logic.parse_endpoint(
                self._ui.edit_server_ip.text(),
                self._ui.edit_server_port.text(),
            )
        except ValueError as exc:
            message = str(exc)
            if "整數" in message or "1–65535" in message:
                QMessageBox.warning(self, "Connect", message)
            else:
                QMessageBox.information(self, "Connect", message)
            return

        self._logic.connecting = True
        self._update_connect_button()

        def connect_worker() -> None:
            try:
                self._logic.connect(ip, port)
            except Exception as exc:
                self._tcp_connect_bridge.finished.emit(False, str(exc))
            else:
                self._tcp_connect_bridge.finished.emit(True, "")

        threading.Thread(target=connect_worker, daemon=True).start()

    def _on_tcp_connect_finished(self, success: bool, error_message: str) -> None:
        self._logic.connecting = False
        if success:
            endpoint = self._logic.remote_endpoint()
            detail = (
                f"{endpoint[0]}:{endpoint[1]}"
                if endpoint is not None
                else "server"
            )
            QMessageBox.information(
                self,
                "Connect",
                f"已連線至 BMT Server：\n{detail}",
            )
        else:
            self._logic.disconnect()
            QMessageBox.warning(
                self,
                "Connect 失敗",
                error_message or "無法連線到指定的 Server。",
            )
        self._update_connect_button()

    def _on_measure_clicked(self) -> None:
        self._start_measurement(automated=False)

    @property
    def is_measuring(self) -> bool:
        return self._logic.measuring

    @property
    def uses_statistics_report(self) -> bool:
        return True

    def get_statistics_report_headers(self) -> tuple[str, ...]:
        return (
            "X", "Y", "Point_Count", "Vin_Min_V", "Vin_Max_V",
            "Vout_Min_V", "Vout_Max_V", "I_Min_mA", "I_Max_mA",
            "R_Min_kOhm", "R_Max_kOhm",
        )

    def get_statistics_report_values(self) -> tuple[float | int | None, ...]:
        return self._statistics_values

    def start_measurement(
        self,
        die_x: int | None = None,
        die_y: int | None = None,
        *,
        automated: bool = False,
    ) -> bool:
        del die_x, die_y
        return self._start_measurement(automated=automated)

    def _start_measurement(self, *, automated: bool) -> bool:
        if not self._logic.is_connected() or self._logic.measuring:
            return False

        self._automated_measurement = automated
        self._logic.measuring = True
        self._update_connect_button()

        def measure_worker() -> None:
            try:
                rows = self._logic.measure()
            except Exception as exc:
                self._measure_bridge.finished.emit(False, [], str(exc))
            else:
                self._measure_bridge.finished.emit(True, rows, "")

        threading.Thread(target=measure_worker, daemon=True).start()
        return True

    def _on_measure_finished(
        self,
        success: bool,
        rows: object,
        error_message: str,
    ) -> None:
        self._logic.measuring = False
        self._update_connect_button()
        if not success:
            if self._automated_measurement:
                self.measurement_failed.emit(error_message or "BMT3000 Measure 失敗")
                return
            QMessageBox.warning(
                self,
                "Measure 失敗",
                error_message or "量測失敗。",
            )
            return
        table_rows = rows if isinstance(rows, list) else []
        self._show_iv_results(table_rows)
        self._statistics_values = self._summarize_iv_rows(table_rows)
        self.measurement_finished.emit(
            [float(row[0]) for row in table_rows if len(row) >= 3],
            [float(row[2]) for row in table_rows if len(row) >= 3],
        )

    @staticmethod
    def _summarize_iv_rows(rows: list) -> tuple[float | int | None, ...]:
        columns = [[], [], [], []]
        for row in rows:
            if not isinstance(row, (list, tuple)) or len(row) < 4:
                continue
            try:
                for index in range(4):
                    columns[index].append(float(row[index]))
            except (TypeError, ValueError):
                continue
        if not columns[0]:
            return (0, None, None, None, None, None, None, None, None)
        return (
            len(columns[0]),
            min(columns[0]), max(columns[0]),
            min(columns[1]), max(columns[1]),
            min(columns[2]), max(columns[2]),
            min(columns[3]), max(columns[3]),
        )

    def _show_iv_results(self, rows: list) -> None:
        self._fill_iv_table(rows)
        self._fill_iv_chart(rows)

    def _fill_iv_table(self, rows: list) -> None:
        table = self._ui.iv_table
        table.setRowCount(len(rows))
        column_count = table.columnCount()
        for row_index, row in enumerate(rows):
            values = row if isinstance(row, (list, tuple)) else []
            for column in range(column_count):
                text = ""
                if column < len(values):
                    try:
                        text = f"{float(values[column]):.6g}"
                    except (TypeError, ValueError):
                        text = str(values[column])
                item = QTableWidgetItem(text)
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
                table.setItem(row_index, column, item)

    def _fill_iv_chart(self, rows: list) -> None:
        series = self._ui.iv_series
        series.clear()
        xs: list[float] = []
        ys: list[float] = []
        for row in rows:
            values = row if isinstance(row, (list, tuple)) else []
            if len(values) < 3:
                continue
            try:
                x_value = float(values[0])
                y_value = float(values[2])
            except (TypeError, ValueError):
                continue
            series.append(x_value, y_value)
            xs.append(x_value)
            ys.append(y_value)
        if not xs:
            self._ui.iv_axis_x.setRange(0, 5)
            self._ui.iv_axis_y.setRange(0, 1)
            return
        xmin, xmax = min(xs), max(xs)
        ymin, ymax = min(ys), max(ys)
        if xmin == xmax:
            xmin, xmax = xmin - 0.5, xmax + 0.5
        else:
            pad = (xmax - xmin) * 0.05
            xmin -= pad
            xmax += pad
        if ymin == ymax:
            span = max(abs(ymax) * 0.1, 0.1)
            ymin, ymax = ymin - span, ymax + span
        else:
            pad = (ymax - ymin) * 0.1
            ymin -= pad
            ymax += pad
        if min(ys) >= 0:
            ymin = max(ymin, 0.0)
        self._ui.iv_axis_x.setRange(xmin, xmax)
        self._ui.iv_axis_y.setRange(ymin, ymax)

    def _on_read_pixel_clicked(self) -> None:
        QMessageBox.information(
            self,
            "Calculate",
            "BMT3000 目前尚未支援 Calculate。",
        )

    def closeEvent(self, event) -> None:
        self._logic.disconnect()
        super().closeEvent(event)
