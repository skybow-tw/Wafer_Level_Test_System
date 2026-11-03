"""BMT5000 USB / register / pixel operations."""

from __future__ import annotations

from instruments.bmt_usb import BmtUsbConnection
from instruments.roic_adc_reader import ROIC_ADCReader
from instruments.usb_raw_scanner import UsbDeviceInfo


class Bmt5000Logic:
    """Hardware interaction for BMT5000 (USB + ROIC reader)."""

    def __init__(self) -> None:
        self._usb: BmtUsbConnection | None = None
        self._frame_callback = None
        self._roic = ROIC_ADCReader(on_frame=self._on_frame)

    def set_frame_callback(self, callback) -> None:
        self._frame_callback = callback

    def _on_frame(self, data_array: list[int]) -> None:
        if self._frame_callback is not None:
            self._frame_callback(data_array)

    @property
    def roic_reader(self) -> ROIC_ADCReader:
        return self._roic

    @property
    def usb_connection(self) -> BmtUsbConnection | None:
        return self._usb

    def is_usb_connected(self) -> bool:
        return self._usb is not None and self._usb.is_open

    def connect_usb(self, device_info: UsbDeviceInfo) -> None:
        self.disconnect_usb()
        self._usb = BmtUsbConnection.open(device_info)
        self._roic.set_connection(self._usb)

    def disconnect_usb(self) -> None:
        if self._usb is not None:
            try:
                self._usb.close()
            except OSError:
                pass
        self._usb = None
        self._roic.set_connection(None)

    def read_registers(
        self,
        *,
        did: int,
        offset: int,
        length: int,
    ) -> tuple[bytes, int]:
        if self._usb is None or not self._usb.is_open:
            raise RuntimeError("USB not connected")
        if length < 1:
            raise ValueError("Length 必須大於 0。")
        data = self._usb.read_registers(did=did, reg=offset, length=length)
        return data, offset

    def build_easy_pixel_command(
        self,
        *,
        s_h_index: int,
        ctia_index: int,
        buff_index: int,
        int_time: int,
        period: int,
        adc_off: bool,
        enable_rr: bool,
    ) -> str:
        return self._roic.build_adc_command_hex(
            s_h_index=s_h_index,
            ctia_index=ctia_index,
            buff_index=buff_index,
            int_time_text=f"{int_time:02X}",
            period_text=str(period),
            adc_off_checked=adc_off,
            enable_rr_checked=enable_rr,
        )

    def read_pixel_frame(
        self,
        *,
        s_h_index: int,
        ctia_index: int,
        buff_index: int,
        int_time: int,
        period: int,
        adc_off: bool,
        enable_rr: bool,
    ) -> None:
        if self._usb is None or not self._usb.is_open:
            raise RuntimeError("USB not connected")
        self._roic.set_connection(self._usb)
        command_hex = self.build_easy_pixel_command(
            s_h_index=s_h_index,
            ctia_index=ctia_index,
            buff_index=buff_index,
            int_time=int_time,
            period=period,
            adc_off=adc_off,
            enable_rr=enable_rr,
        )
        self._roic.read_adc_one_frame_from_command(command_hex)

    def read_pixel_frame_from_command(self, command_hex: str) -> None:
        if self._usb is None or not self._usb.is_open:
            raise RuntimeError("USB not connected")
        self._roic.set_connection(self._usb)
        self._roic.read_adc_one_frame_from_command(command_hex)
