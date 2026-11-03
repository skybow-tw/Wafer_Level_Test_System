"""NI device combo that scans when the dropdown opens."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox


class NiDeviceComboBox(QComboBox):
    """Combo box that scans NI-DAQmx devices when the dropdown is opened."""

    scan_requested = Signal()

    def showPopup(self) -> None:
        self.scan_requested.emit()
        super().showPopup()
