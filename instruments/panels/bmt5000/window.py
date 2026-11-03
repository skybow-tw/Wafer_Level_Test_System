"""BMT5000 instrument control window."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QMessageBox, QWidget

from instruments.panels.base import InstrumentPanelBase
from instruments.panels.bmt.constants import (
    DEFAULT_BMT_PIXEL_INT_TIME,
    DEFAULT_BMT_PIXEL_PERIOD,
)
from instruments.panels.bmt.ui_helpers import combo_bool_value, combo_int_value
from instruments.panels.bmt5000.logic import Bmt5000Logic
from instruments.panels.bmt5000.ui import (
    PIXEL_MODE_EASY,
    PIXEL_MODE_STRING,
    Bmt5000Ui,
    build_bmt5000_ui,
)
from instruments.panels.registry import BMT5000_DISPLAY_NAME
from instruments.panels.widgets.usb_device_combo import USB_DETAIL_ROLE, USB_SN_ROLE
from instruments.usb_raw_scanner import UsbDeviceInfo, list_usb_devices
from theme_config import THEMES, generate_theme_qss


class Bmt5000Window(InstrumentPanelBase):
    def __init__(
        self,
        parent: QWidget | None = None,
        work_dir: Path | None = None,
    ) -> None:
        super().__init__(BMT5000_DISPLAY_NAME, parent=parent, work_dir=work_dir)
        self.setMinimumSize(900, 720)
        self.setMaximumSize(1600, 1200)
        self.resize(960, 780)
        self._logic = Bmt5000Logic()
        self._logic.set_frame_callback(self._on_pixel_frame)
        self._ui: Bmt5000Ui = build_bmt5000_ui()
        self.setCentralWidget(self._ui.root)
        self._usb_devices: list[UsbDeviceInfo] = []
        self._wire_ui()
        self._update_pixel_mode_controls()
        self._update_connect_button()
        self.setStyleSheet(generate_theme_qss(THEMES["light"]))

    def _wire_ui(self) -> None:
        ui = self._ui
        ui.cmb_usb_device.scan_requested.connect(self._scan_usb_devices)
        ui.btn_connect.clicked.connect(self._on_connect_clicked)
        ui.btn_read_register.clicked.connect(self._on_read_register_clicked)
        ui.btn_read_pixel.clicked.connect(self._on_read_pixel_clicked)
        ui.btn_exit.clicked.connect(self.close)
        ui.radio_easy_mode.toggled.connect(self._on_pixel_mode_changed)
        ui.radio_string_mode.toggled.connect(self._on_pixel_mode_changed)
        for combo in (
            ui.cmb_s_h_ibs,
            ui.cmb_ctia_ibs,
            ui.cmb_buff_ibs,
            ui.cmb_int_time,
            ui.cmb_period,
            ui.cmb_adc_off,
            ui.cmb_enable_rr,
        ):
            combo.currentIndexChanged.connect(self._sync_easy_command_preview)

    def _pixel_mode(self) -> str:
        if self._ui.radio_string_mode.isChecked():
            return PIXEL_MODE_STRING
        return PIXEL_MODE_EASY

    def _on_pixel_mode_changed(self, checked: bool) -> None:
        if not checked:
            return
        self._update_pixel_mode_controls()

    def _update_pixel_mode_controls(self) -> None:
        easy = self._pixel_mode() == PIXEL_MODE_EASY
        self._ui.pixel_mode_stack.setCurrentIndex(0 if easy else 1)
        if easy:
            self._sync_easy_command_preview()
        else:
            # Entering string mode: seed from the current easy-composed command.
            self._ui.edit_pixel_command.setText(
                self._ui.edit_easy_command_preview.text()
            )

    def _easy_pixel_params(self) -> dict:
        ui = self._ui
        return {
            "s_h_index": combo_int_value(ui.cmb_s_h_ibs, 0),
            "ctia_index": combo_int_value(ui.cmb_ctia_ibs, 0),
            "buff_index": combo_int_value(ui.cmb_buff_ibs, 0),
            "int_time": combo_int_value(ui.cmb_int_time, DEFAULT_BMT_PIXEL_INT_TIME),
            "period": combo_int_value(ui.cmb_period, DEFAULT_BMT_PIXEL_PERIOD),
            "adc_off": combo_bool_value(ui.cmb_adc_off, False),
            "enable_rr": combo_bool_value(ui.cmb_enable_rr, False),
        }

    def _sync_easy_command_preview(self, *_args) -> None:
        command_hex = self._logic.build_easy_pixel_command(**self._easy_pixel_params())
        self._ui.edit_easy_command_preview.setText(command_hex)

    def set_bmt_array_values(self, values: list[list[object]]) -> None:
        self._ui.array_view.set_values(values)

    def set_bmt_cell_value(
        self,
        x_idx: int,
        y_idx: int,
        value: object | None,
        *,
        color=None,
    ) -> None:
        self._ui.array_view.set_cell_value(
            x_idx, y_idx, value, auto_color=color is None
        )
        if color is not None:
            self._ui.array_view.set_cell_color(x_idx, y_idx, color)

    def set_bmt_register_value(
        self,
        x_idx: int,
        y_idx: int,
        value: object | None,
        *,
        color=None,
    ) -> None:
        self._ui.register_map_view.set_cell_value(
            x_idx, y_idx, value, auto_color=color is None
        )
        if color is not None:
            self._ui.register_map_view.set_cell_color(x_idx, y_idx, color)

    def _scan_usb_devices(self) -> None:
        combo = self._ui.cmb_usb_device
        current_id = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("掃描中…", None)
        combo.blockSignals(False)

        try:
            self._usb_devices = list_usb_devices()
        except Exception as exc:
            self._usb_devices = []
            combo.blockSignals(True)
            combo.clear()
            combo.blockSignals(False)
            QMessageBox.warning(self, "USB 掃描失敗", str(exc))
            return

        combo.blockSignals(True)
        combo.clear()
        if not self._usb_devices:
            combo.addItem("未偵測到 STM32 Virtual ComPort", None)
        else:
            restore_index = 0
            for index, info in enumerate(self._usb_devices):
                combo.addItem(info.name, info.device_id)
                item_index = combo.count() - 1
                combo.setItemData(item_index, info.vid_pid_label, USB_DETAIL_ROLE)
                combo.setItemData(item_index, info.sn_label, USB_SN_ROLE)
                if info.device_id == current_id:
                    restore_index = index
            combo.setCurrentIndex(restore_index)
        combo.blockSignals(False)

    def _selected_usb_device(self) -> UsbDeviceInfo | None:
        device_id = self._ui.cmb_usb_device.currentData()
        if not device_id:
            return None
        for info in self._usb_devices:
            if info.device_id == device_id:
                return info
        return None

    def _update_connect_button(self) -> None:
        connected = self._logic.is_usb_connected()
        self._ui.btn_connect.setText("Disconnect" if connected else "Connect")
        self._ui.cmb_usb_device.setEnabled(not connected)
        self._ui.group_register.setEnabled(connected)
        self._ui.group_pixel.setEnabled(connected)

    def _on_connect_clicked(self) -> None:
        if self._logic.is_usb_connected():
            self._logic.disconnect_usb()
            self._update_connect_button()
            return

        device_info = self._selected_usb_device()
        if device_info is None:
            QMessageBox.information(
                self,
                "Connect",
                "請先從 USB device 選單選擇裝置。",
            )
            return

        try:
            self._logic.connect_usb(device_info)
        except Exception as exc:
            self._update_connect_button()
            QMessageBox.warning(self, "Connect 失敗", str(exc))
            return

        self._update_connect_button()
        QMessageBox.information(
            self,
            "Connect",
            "已連線至裝置：\n" f"{device_info.name}\n" f"{device_info.detail_label}",
        )

    def _on_read_register_clicked(self) -> None:
        ui = self._ui
        try:
            data, offset = self._logic.read_registers(
                did=combo_int_value(ui.cmb_device_id, 0xC0),
                offset=combo_int_value(ui.cmb_offset, 0x00),
                length=combo_int_value(ui.cmb_length, 0x90),
            )
        except ValueError as exc:
            QMessageBox.information(self, "Read Register", str(exc))
            return
        except PermissionError:
            QMessageBox.critical(
                self, "Read Register", "權限不足，無法存取 USB 裝置。"
            )
            return
        except Exception as exc:
            message = str(exc)
            if "timeout" in message.lower() or getattr(exc, "errno", None) == 110:
                QMessageBox.critical(
                    self, "Read Register", "USB 通訊逾時 (Timeout Error)"
                )
            else:
                QMessageBox.critical(
                    self, "Read Register", f"讀取暫存器失敗：\n{exc}"
                )
            return

        self._fill_register_map(data, start=offset)
        ui.tabs.setCurrentIndex(0)

    def _fill_register_map(self, data: bytes, start: int = 0) -> None:
        view = self._ui.register_map_view
        for i in range(len(data)):
            addr = start + i
            if addr >= 256:
                break
            row = addr // 16
            col = addr % 16
            view.set_cell_value(col, row, f"{data[i]:02X}", auto_color=True)

    def _on_read_pixel_clicked(self) -> None:
        ui = self._ui
        try:
            if self._pixel_mode() == PIXEL_MODE_STRING:
                self._logic.read_pixel_frame_from_command(ui.edit_pixel_command.text())
            else:
                self._logic.read_pixel_frame(**self._easy_pixel_params())
        except ValueError as exc:
            QMessageBox.information(self, "Read Pixel", str(exc))
            return
        except PermissionError:
            QMessageBox.critical(self, "Read Pixel", "權限不足，無法存取 USB 裝置。")
            return
        except Exception as exc:
            message = str(exc)
            if "timeout" in message.lower() or getattr(exc, "errno", None) == 110:
                QMessageBox.critical(self, "Read Pixel", "USB 通訊逾時 (Timeout Error)")
            else:
                QMessageBox.critical(self, "Read Pixel", f"讀取 Pixel 失敗：\n{exc}")
            return

        self._show_pixel_frame_on_data_array()
        roic = self._logic.roic_reader
        if roic.stream_error:
            QMessageBox.warning(
                self,
                "Read Pixel",
                "Pixel stream header/end 不正確 "
                f"(Header=0x{roic.PXL_Stream_Header:04X}, "
                f"End=0x{roic.PXL_Stream_End:04X})。\n"
                "已顯示上一筆有效資料。",
            )

    def _on_pixel_frame(self, _data_array: list[int]) -> None:
        self._show_pixel_frame_on_data_array()

    def _show_pixel_frame_on_data_array(self) -> None:
        roic = self._logic.roic_reader
        self.set_bmt_array_values(roic.pixels_as_grid())
        self._ui.tabs.setCurrentIndex(1)

    def closeEvent(self, event) -> None:
        self._logic.disconnect_usb()
        super().closeEvent(event)
