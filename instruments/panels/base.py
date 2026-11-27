"""Shared base class for instrument control windows."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QMainWindow, QWidget

from instruments.panels.common import resolve_work_dir
from statistics_report import LcrDieSummary


class InstrumentPanelBase(QMainWindow):
    """Contract used by the main window and measurement workflow."""

    measurement_finished = Signal(list, list)
    measurement_failed = Signal(str)

    def __init__(
        self,
        instrument_name: str,
        parent: QWidget | None = None,
        work_dir: Path | None = None,
    ) -> None:
        super().__init__(parent)
        self._instrument_name = instrument_name
        self._work_dir = work_dir
        self._save_params_window = None
        self.setWindowTitle(instrument_name)
        self._setup_save_params_window(work_dir)

    def _setup_save_params_window(self, work_dir: Path | None) -> None:
        if self.parent() is not None:
            return
        from save_params_window import SaveParamsWindow

        work = resolve_work_dir(self, work_dir)
        self._save_params_window = SaveParamsWindow(work, parent=self)

    def showEvent(self, event) -> None:  # noqa: ANN001
        super().showEvent(event)
        window = self._save_params_window
        if window is not None:
            window.align_to_host(self)
            window.show()

    @property
    def is_measuring(self) -> bool:
        return False

    @property
    def is_virtual_lcr(self) -> bool:
        return False

    @property
    def uses_lcr_measurement(self) -> bool:
        return False

    @property
    def uses_statistics_report(self) -> bool:
        """Whether automated measurement writes one statistics row per die."""
        return False

    @property
    def uses_register_measurement(self) -> bool:
        return False

    def get_statistics_report_headers(self) -> tuple[str, ...]:
        raise NotImplementedError

    def get_statistics_report_values(self) -> tuple[float | int | str | None, ...]:
        raise NotImplementedError

    def save_register_measurement(self, session_dir: Path, die_x: int, die_y: int) -> Path:
        raise NotImplementedError

    def register_measurement_passed(self) -> bool:
        raise NotImplementedError

    def get_lcr_die_summary(self) -> LcrDieSummary:
        raise NotImplementedError

    def start_measurement(
        self,
        die_x: int | None = None,
        die_y: int | None = None,
        *,
        automated: bool = False,
    ) -> bool:
        del die_x, die_y, automated
        return False

    def align_to_main_window(
        self, main_window: QMainWindow, *, stack_index: int = 0
    ) -> None:
        main_geo = main_window.frameGeometry()
        offset = 28 * max(0, stack_index)
        self.move(main_geo.right() + offset, main_geo.top() + offset)
