"""GPIB instrument combo that scans when the dropdown opens."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox


class GpibInstrumentComboBox(QComboBox):
    """Combo box that scans GPIB instruments when the dropdown is opened."""

    scan_requested = Signal()

    def showPopup(self) -> None:
        self.scan_requested.emit()
        super().showPopup()
