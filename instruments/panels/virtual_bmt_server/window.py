"""Virtual BMT TCP server control window."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QMainWindow, QMessageBox, QWidget

from instruments.panels.virtual_bmt_server.logic import VirtualBmtTcpServer
from instruments.panels.virtual_bmt_server.ui import (
    VirtualBmtServerUi,
    build_virtual_bmt_server_ui,
)
from theme_config import THEMES, generate_theme_qss


class _ServerUiBridge(QObject):
    status_changed = Signal(bool)
    client_count_changed = Signal(int)
    log_message = Signal(str)


class VirtualBmtServerWindow(QMainWindow):
    def __init__(
        self,
        parent: QWidget | None = None,
        work_dir: Path | None = None,
    ) -> None:
        del work_dir
        super().__init__(parent)
        self.setWindowTitle("Virtual BMT TCP Server")
        self.setMinimumSize(560, 640)
        self.resize(640, 720)

        self._ui: VirtualBmtServerUi = build_virtual_bmt_server_ui()
        self.setCentralWidget(self._ui.root)

        self._bridge = _ServerUiBridge(self)
        self._bridge.status_changed.connect(self._on_status_changed)
        self._bridge.client_count_changed.connect(self._on_client_count_changed)
        self._bridge.log_message.connect(self._append_log)

        self._server = VirtualBmtTcpServer(
            on_status=self._bridge.status_changed.emit,
            on_client_count=self._bridge.client_count_changed.emit,
            on_log=self._bridge.log_message.emit,
        )

        self._wire_ui()
        self._refresh_controls(running=False)
        self.setStyleSheet(generate_theme_qss(THEMES["light"]))

    def _wire_ui(self) -> None:
        ui = self._ui
        ui.btn_start.clicked.connect(self._on_start_clicked)
        ui.btn_stop.clicked.connect(self._on_stop_clicked)
        ui.btn_clear_log.clicked.connect(ui.log_view.clear)
        ui.btn_exit.clicked.connect(self.close)

    def _refresh_controls(self, *, running: bool) -> None:
        ui = self._ui
        ui.btn_start.setEnabled(not running)
        ui.btn_stop.setEnabled(running)
        ui.edit_host.setEnabled(not running)
        ui.spin_port.setEnabled(not running)
        if running:
            port = self._server.bound_port
            port_text = f":{port}" if port is not None else ""
            ui.lbl_server_status.setText(f"開啟中{port_text}")
            ui.lbl_server_status.setStyleSheet(
                "font-weight: 600; color: #2E7D32;"
            )
        else:
            ui.lbl_server_status.setText("關閉")
            ui.lbl_server_status.setStyleSheet(
                "font-weight: 600; color: #B71C1C;"
            )

    def _on_status_changed(self, running: bool) -> None:
        self._refresh_controls(running=running)

    def _on_client_count_changed(self, count: int) -> None:
        self._ui.lbl_client_count.setText(str(count))

    def _append_log(self, message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self._ui.log_view.appendPlainText(f"[{stamp}] {message}")

    def _on_start_clicked(self) -> None:
        if self._server.is_running:
            return
        host = self._ui.edit_host.text().strip() or "0.0.0.0"
        port = int(self._ui.spin_port.value())
        try:
            self._server.start(port=port, host=host)
        except OSError as exc:
            QMessageBox.warning(
                self,
                "Start Server 失敗",
                f"無法綁定 {host}:{port}\n{exc}",
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Start Server", str(exc))
        except RuntimeError as exc:
            QMessageBox.information(self, "Start Server", str(exc))

    def _on_stop_clicked(self) -> None:
        self._server.stop()

    def closeEvent(self, event) -> None:  # noqa: ANN001
        self._server.stop()
        super().closeEvent(event)
