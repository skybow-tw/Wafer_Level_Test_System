"""Modular instrument control panels (GUI + logic per instrument)."""

from instruments.panels.base import InstrumentPanelBase
from instruments.panels.registry import (
    INSTRUMENT_DISPLAY_NAMES,
    create_modular_instrument_window,
)

__all__ = [
    "InstrumentPanelBase",
    "INSTRUMENT_DISPLAY_NAMES",
    "create_modular_instrument_window",
]
