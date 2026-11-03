"""ROIC ADC one-frame pixel reader for BMT5000 (V02 layout)."""

from __future__ import annotations

import struct
from collections.abc import Callable
from typing import Protocol


class _UsbReadable(Protocol):
    def write_read(self, cmd: bytes, length: int, timeout_ms: int = 1000) -> bytes: ...


class ROIC_ADCReader:
    """Read a single ADC frame from BMT5000 ROIC (V02 byte order)."""

    COL = 130
    ROW = 168
    # USB bulk reads for a full frame need more headroom than register peek.
    READ_TIMEOUT_MS = 5000

    def __init__(
        self,
        connection: _UsbReadable | None = None,
        *,
        on_frame: Callable[[list[int]], None] | None = None,
    ) -> None:
        self._connection = connection
        self._on_frame = on_frame

        self.col = self.COL
        self.row = self.ROW
        self.length = 2 * self.col * self.row + 4

        self.S_H_IBS_str = bytearray(1)
        self.CTIA_BUFF_IBS_Str = bytearray(1)

        pixel_count = self.col * self.row
        self.Pixel_CNT = [0] * pixel_count
        self.Pixel_CNT_Old = [0] * pixel_count
        self.PXL_Table = [0] * pixel_count
        self.PIXEL_Textval = [""] * (1 + pixel_count)

        self.PXL_Stream_Header = 0
        self.PXL_Stream_End = 0
        self.Frame_Number = 0
        self.stream_error = 0

    def set_connection(self, connection: _UsbReadable | None) -> None:
        self._connection = connection

    def set_on_frame(self, on_frame: Callable[[list[int]], None] | None) -> None:
        self._on_frame = on_frame

    def xibs_index_to_bin(
        self, s_h_index: int, ctia_index: int, buff_index: int
    ) -> None:
        """Map UI dropdown indices to S_H / CTIA / BUFF IBS byte values."""
        if s_h_index == 0:
            self.S_H_IBS_str[0] = 0x01
        elif s_h_index == 1:
            self.S_H_IBS_str[0] = 0x02
        elif s_h_index == 2:
            self.S_H_IBS_str[0] = 0x04
        elif s_h_index == 3:
            self.S_H_IBS_str[0] = 0x08
        else:
            self.S_H_IBS_str[0] = 0x0E

        if ctia_index == 0:
            self.CTIA_BUFF_IBS_Str[0] = 0x10
        elif ctia_index == 1:
            self.CTIA_BUFF_IBS_Str[0] = 0x20
        elif ctia_index == 2:
            self.CTIA_BUFF_IBS_Str[0] = 0x40
        elif ctia_index == 3:
            self.CTIA_BUFF_IBS_Str[0] = 0x80
        else:
            self.CTIA_BUFF_IBS_Str[0] = 0xE0

        if buff_index == 0:
            self.CTIA_BUFF_IBS_Str[0] |= 0x01
        elif buff_index == 1:
            self.CTIA_BUFF_IBS_Str[0] |= 0x02
        elif buff_index == 2:
            self.CTIA_BUFF_IBS_Str[0] |= 0x04
        elif buff_index == 3:
            self.CTIA_BUFF_IBS_Str[0] |= 0x08
        else:
            self.CTIA_BUFF_IBS_Str[0] |= 0x0E

    def build_adc_command_hex(
        self,
        s_h_index: int,
        ctia_index: int,
        buff_index: int,
        int_time_text: str,
        period_text: str,
        adc_off_checked: bool,
        enable_rr_checked: bool,
    ) -> str:
        """Compose the ADC read command hex string (easy mode)."""
        self.xibs_index_to_bin(s_h_index, ctia_index, buff_index)
        period_time = int(period_text)
        adc_off = 1 if adc_off_checked else 0
        enable_rr_mode = 1 if enable_rr_checked else 0
        return (
            "384E00"
            + self.S_H_IBS_str.hex().upper()
            + self.CTIA_BUFF_IBS_Str.hex().upper()
            + f"{int_time_text}{period_time:02X}{adc_off:02X}{enable_rr_mode:02X}"
        )

    def read_adc_one_frame(
        self,
        s_h_index: int,
        ctia_index: int,
        buff_index: int,
        int_time_text: str,
        period_text: str,
        adc_off_checked: bool,
        enable_rr_checked: bool,
    ) -> list[int]:
        """Read one ADC frame using easy-mode dropdown parameters."""
        cmd_hex = self.build_adc_command_hex(
            s_h_index,
            ctia_index,
            buff_index,
            int_time_text,
            period_text,
            adc_off_checked,
            enable_rr_checked,
        )
        return self.read_adc_one_frame_from_command(cmd_hex)

    def read_adc_one_frame_from_command(self, command_hex: str) -> list[int]:
        """Read one ADC frame using a raw hex command string."""
        cleaned = "".join(command_hex.split())
        if not cleaned:
            raise ValueError("命令字串不可為空。")
        try:
            cmd_byte_read = bytes.fromhex(cleaned)
        except ValueError as exc:
            raise ValueError("命令字串必須為有效的十六進位字串。") from exc

        index_buf = 0
        stream_error = 0
        self.Frame_Number = 0

        rbuf = self.read_from_device(cmd_byte_read, self.length)

        self.PXL_Stream_Header = struct.unpack("<H", rbuf[0:2])[0]
        end_idx = 2 * ((self.col * self.row) + 1)
        self.PXL_Stream_End = struct.unpack("<H", rbuf[end_idx : end_idx + 2])[0]
        self.PIXEL_Textval[0] = str(self.PXL_Stream_Header)

        stream_error = (
            1
            if (self.PXL_Stream_Header != 0x5A5A or self.PXL_Stream_End != 0x8D8D)
            else 0
        )
        self.stream_error = stream_error

        for i in range(self.col):
            for j in range(self.row):
                idx = i * self.row + j
                if stream_error == 0:
                    byte_offset = 2 + idx * 2
                    pixel_val = struct.unpack(
                        "<h", rbuf[byte_offset : byte_offset + 2]
                    )[0]
                    self.Pixel_CNT[idx] = pixel_val
                    self.Pixel_CNT_Old[idx] = pixel_val

                    if index_buf < (self.col * self.row):
                        self.PIXEL_Textval[1 + idx] = str(pixel_val)
                        self.PXL_Table[idx] = pixel_val
                else:
                    if index_buf < (self.row * self.col):
                        self.PIXEL_Textval[1 + idx] = str(self.Pixel_CNT_Old[idx])
                        self.PXL_Table[idx] = self.Pixel_CNT_Old[idx]

                index_buf += 1

        int_array = list(self.Pixel_CNT[: self.col * self.row])
        self.draw_image_in_picture_box(int_array)
        return int_array

    def pixels_as_grid(self) -> list[list[int]]:
        """Return row-major grid (ROW × COL) from V02 column-major ``Pixel_CNT``."""
        grid: list[list[int]] = []
        for j in range(self.row):
            row_vals: list[int] = []
            for i in range(self.col):
                row_vals.append(int(self.Pixel_CNT[i * self.row + j]))
            grid.append(row_vals)
        return grid

    def read_from_device(self, cmd: bytes, length: int) -> bytes:
        if self._connection is None:
            raise RuntimeError("USB 裝置尚未連線。")
        return self._connection.write_read(
            cmd, length, timeout_ms=self.READ_TIMEOUT_MS
        )

    def draw_image_in_picture_box(self, data_array: list[int]) -> None:
        if self._on_frame is not None:
            self._on_frame(list(data_array))
