"""Map instrument display names to modular panel window classes."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget

    from instruments.bmt_tcp import BmtTcpClient
    from instruments.panels.base import InstrumentPanelBase

VIRTUAL_LCR_INSTRUMENT_NAME = "VirtualLCR"
LCR_METER_DISPLAY_NAME = "LCR Meter"
LCR_METER_BOLOMETER_DISPLAY_NAME = "LCR_Meter_Bolometer"
BMT3000_DISPLAY_NAME = "BMT3000"
BMT5000_DISPLAY_NAME = "BMT5000"
DSA_DISPLAY_NAME = "DSA"
NI_8452_DISPLAY_NAME = "NI_8452"
# Guided-setup label (same panel as NI_8452 menu entry).
NI_8452_SPI_TEST_DISPLAY_NAME = "NI 8452 SPI Test"
FUNCTION_TEST_SPI_DAC_DISPLAY_NAME = "Function Test(SPI、DAC)"

INSTRUMENT_DISPLAY_NAMES: frozenset[str] = frozenset(
    {
        VIRTUAL_LCR_INSTRUMENT_NAME,
        LCR_METER_DISPLAY_NAME,
        LCR_METER_BOLOMETER_DISPLAY_NAME,
        BMT3000_DISPLAY_NAME,
        BMT5000_DISPLAY_NAME,
        DSA_DISPLAY_NAME,
        NI_8452_DISPLAY_NAME,
        NI_8452_SPI_TEST_DISPLAY_NAME,
        FUNCTION_TEST_SPI_DAC_DISPLAY_NAME,
    }
)


def create_modular_instrument_window(
    instrument_name: str,
    parent: QWidget | None = None,
    work_dir: Path | None = None,
    asic_tcp_client: BmtTcpClient | None = None,
) -> InstrumentPanelBase | None:
    if instrument_name == FUNCTION_TEST_SPI_DAC_DISPLAY_NAME:
        from instruments.panels.function_test_window import FunctionTestWindow

        return FunctionTestWindow(
            parent=parent, work_dir=work_dir, tcp_client=asic_tcp_client
        )
    if instrument_name == VIRTUAL_LCR_INSTRUMENT_NAME:
        from instruments.panels.virtual_lcr.window import VirtualLcrWindow

        return VirtualLcrWindow(parent=parent, work_dir=work_dir)
    if instrument_name == LCR_METER_DISPLAY_NAME:
        from instruments.panels.lcr_meter.window import LcrMeterWindow

        return LcrMeterWindow(parent=parent, work_dir=work_dir)
    if instrument_name == LCR_METER_BOLOMETER_DISPLAY_NAME:
        from instruments.panels.lcr_meter.window import LcrMeterBolometerWindow

        return LcrMeterBolometerWindow(parent=parent, work_dir=work_dir)
    if instrument_name == BMT3000_DISPLAY_NAME:
        from instruments.panels.bmt3000.window import Bmt3000Window

        return Bmt3000Window(parent=parent, work_dir=work_dir)
    if instrument_name == BMT5000_DISPLAY_NAME:
        from instruments.panels.bmt5000.window import Bmt5000Window

        return Bmt5000Window(parent=parent, work_dir=work_dir)
    if instrument_name == DSA_DISPLAY_NAME:
        from instruments.panels.dsa.window import DsaWindow

        return DsaWindow(parent=parent, work_dir=work_dir)
    if instrument_name in {NI_8452_DISPLAY_NAME, NI_8452_SPI_TEST_DISPLAY_NAME}:
        from instruments.panels.ni8452.window import Ni8452Window

        return Ni8452Window(
            parent=parent,
            work_dir=work_dir,
            display_name=instrument_name,
        )
    return None
