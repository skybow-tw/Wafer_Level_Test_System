"""Measurement workflow: motor stepping and instrument reads."""

from __future__ import annotations

import csv
import logging
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import QMessageBox, QWidget

from map_data_reader import InspectionTargetList
from prober_motor.base import ChuckMotorBase
from lcr_criterion import BAD_DIE_BIN, GOOD_DIE_BIN, judge_real_lcr_die, judge_virtual_lcr_die
from instruments.panels.registry import DSA_DISPLAY_NAME
from save_params import get_save_params
from statistics_report import append_statistics_row

if TYPE_CHECKING:
    from instruments.panels.base import InstrumentPanelBase

logger = logging.getLogger(__name__)


class _DieStep(Enum):
    ENSURE_Z_RAISED = auto()
    MOVE_TO_DIE = auto()
    MOVE_CONTACT = auto()
    START_MEASURE = auto()
    MOVE_SEPARATION = auto()


class _MotorWorker(QThread):
    """Run a blocking motor action off the GUI thread."""

    succeeded = Signal()
    failed = Signal(str)

    def __init__(self, action: Callable[[], None], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._action = action

    def run(self) -> None:
        try:
            self._action()
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.succeeded.emit()


@dataclass(frozen=True)
class DieMeasurementResult:
    x: int
    y: int
    x_values: list[float]
    y_values: list[float]
    judgment_bin: int


class MeasurementSession(QObject):
    """Visit each inspection die, move chuck, and run instrument measurement."""

    die_started = Signal(int, int)
    die_measured = Signal(object)
    progress = Signal(int, int)
    paused = Signal()
    resumed = Signal()
    finished = Signal(list)
    failed = Signal(str)

    def __init__(
        self,
        motor: ChuckMotorBase,
        targets: InspectionTargetList,
        instrument_window: InstrumentPanelBase | None = None,
        session_dir: Path | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._motor = motor
        self._targets = list(targets.targets)
        self._instrument_window = instrument_window
        self._session_dir = session_dir
        self._next_index = 0
        self._results: list[DieMeasurementResult] = []
        self._running = False
        self._paused = False
        self._paused_mid_die = False
        self._busy = False
        self._current_die_x = 0
        self._current_die_y = 0
        self._pending_x_values: list[float] = []
        self._pending_y_values: list[float] = []
        self._die_step = _DieStep.ENSURE_Z_RAISED
        self._motor_worker: _MotorWorker | None = None
        self._pending_motor_success: Callable[[], None] | None = None

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return
        if not self._targets:
            self.failed.emit("沒有可量測的 die（bin=10）。")
            return
        if self._instrument_window is None:
            self.failed.emit("未開啟儀器控制視窗。")
            return
        self._running = True
        self._paused = False
        self._paused_mid_die = False
        self._next_index = 0
        self._results = []
        QTimer.singleShot(0, self._process_next)

    def pause(self) -> None:
        if not self._running or self._paused:
            return
        self._paused_mid_die = self._busy
        self._paused = True
        self.paused.emit()

    def resume(self) -> None:
        if not self._running or not self._paused:
            return
        self._paused = False
        self.resumed.emit()
        if self._paused_mid_die:
            self._paused_mid_die = False
            self._busy = True
            QTimer.singleShot(0, self._advance_die_step)
        else:
            QTimer.singleShot(0, self._process_next)

    def stop(self, *, silent: bool = False) -> None:
        if silent:
            try:
                self.failed.disconnect()
            except (RuntimeError, TypeError):
                pass
        self._running = False
        self._paused = False
        self._paused_mid_die = False
        self._busy = False
        self._pending_motor_success = None
        worker = self._motor_worker
        self._motor_worker = None
        if worker is not None and self._is_qthread_running(worker):
            worker.wait(5000)

    @staticmethod
    def _is_qthread_running(worker: _MotorWorker) -> bool:
        try:
            return worker.isRunning()
        except RuntimeError:
            return False

    def _release_motor_worker(self, worker: _MotorWorker) -> None:
        if self._motor_worker is worker:
            self._motor_worker = None
        worker.deleteLater()

    def _process_next(self) -> None:
        if self._paused or not self._running:
            return

        if self._next_index >= len(self._targets):
            self._running = False
            self.finished.emit(self._results)
            return

        die = self._targets[self._next_index]
        self._busy = True
        self._current_die_x = die.x
        self._current_die_y = die.y
        # Safe XY move (e.g. TP80) raises Z itself; skip explicit pre-raise.
        if self._motor.xy_move_ends_at_contact:
            self._die_step = _DieStep.MOVE_TO_DIE
        else:
            self._die_step = _DieStep.ENSURE_Z_RAISED
        self.die_started.emit(die.x, die.y)
        self._advance_die_step()

    def _advance_die_step(self) -> None:
        if not self._running:
            return
        if self._paused and self._die_step != _DieStep.MOVE_SEPARATION:
            return

        die_x = self._current_die_x
        die_y = self._current_die_y

        if self._die_step == _DieStep.ENSURE_Z_RAISED:
            if self._motor.is_z_at("separation") or self._motor.is_z_at("load"):
                logger.info("Die (%d, %d): Z already raised, moving to die", die_x, die_y)
                self._die_step = _DieStep.MOVE_TO_DIE
                self._advance_die_step()
                return
            logger.info("Die (%d, %d): raising Z before XY move", die_x, die_y)
            self._run_motor_action(
                self._motor.move_chuck_seperation_and_wait,
                on_success=self._after_z_raised,
            )
            return

        if self._die_step == _DieStep.MOVE_TO_DIE:
            logger.info("Die (%d, %d): moving chuck to die", die_x, die_y)
            self._run_motor_action(
                lambda: self._motor.move_to_die_and_wait(die_x, die_y),
                on_success=self._after_die_arrived,
            )
            return

        if self._die_step == _DieStep.MOVE_CONTACT:
            logger.info("Die (%d, %d): lowering Z to contact", die_x, die_y)
            self._run_motor_action(
                self._motor.move_chuck_contact_and_wait,
                on_success=self._after_contact,
            )
            return

        if self._die_step == _DieStep.START_MEASURE:
            logger.info("Die (%d, %d): starting instrument measurement", die_x, die_y)
            self._start_instrument_measurement()
            return

        if self._die_step == _DieStep.MOVE_SEPARATION:
            # Safe XY (e.g. TP80 ``move_chuck_xy …,1``) raises Z on the next
            # die move; skip an explicit separation command between dies.
            if self._motor.xy_move_ends_at_contact:
                logger.info(
                    "Die (%d, %d): skip separation (safe XY will raise Z)",
                    die_x,
                    die_y,
                )
                self._after_separation()
                return
            self._run_motor_action(
                self._motor.move_chuck_seperation_and_wait,
                on_success=self._after_separation,
            )

    def _after_z_raised(self) -> None:
        self._die_step = _DieStep.MOVE_TO_DIE
        self._advance_die_step()

    def _after_die_arrived(self) -> None:
        # Safe XY move already ends at contact; skip redundant Z contact command.
        if self._motor.xy_move_ends_at_contact or self._motor.is_z_at("contact"):
            logger.info(
                "Die (%d, %d): XY arrived at contact, starting instrument measurement",
                self._current_die_x,
                self._current_die_y,
            )
            self._die_step = _DieStep.START_MEASURE
        else:
            logger.info(
                "Die (%d, %d): XY arrived, proceeding to contact",
                self._current_die_x,
                self._current_die_y,
            )
            self._die_step = _DieStep.MOVE_CONTACT
        self._advance_die_step()

    def _after_contact(self) -> None:
        logger.info(
            "Die (%d, %d): Z at contact, starting instrument measurement",
            self._current_die_x,
            self._current_die_y,
        )
        self._die_step = _DieStep.START_MEASURE
        self._advance_die_step()

    def _start_instrument_measurement(self) -> None:
        instrument = self._instrument_window
        if instrument is None:
            self._fail("未開啟儀器控制視窗。")
            return

        def _on_finished_once(
            x_values: list[float], y_values: list[float]
        ) -> None:
            instrument.measurement_finished.disconnect(_on_finished_once)
            instrument.measurement_failed.disconnect(_on_failed_once)
            self._on_instrument_measurement_finished(x_values, y_values)

        def _on_failed_once(message: str) -> None:
            instrument.measurement_finished.disconnect(_on_finished_once)
            instrument.measurement_failed.disconnect(_on_failed_once)
            self._fail(message)

        instrument.measurement_finished.connect(
            _on_finished_once,
            Qt.ConnectionType.QueuedConnection,
        )
        instrument.measurement_failed.connect(
            _on_failed_once,
            Qt.ConnectionType.QueuedConnection,
        )
        started = instrument.start_measurement(
            die_x=self._current_die_x,
            die_y=self._current_die_y,
            automated=True,
        )
        if not started:
            instrument.measurement_finished.disconnect(_on_finished_once)
            instrument.measurement_failed.disconnect(_on_failed_once)
            if instrument.is_measuring:
                self._fail("儀器正在量測中，無法開始新的量測。")
            else:
                self._fail(
                    "無法啟動儀器量測，請確認儀器已連線並完成 Configure。"
                )

    def _on_instrument_measurement_finished(
        self,
        x_values: list[float],
        y_values: list[float],
    ) -> None:
        if not self._running:
            return

        die_x = self._current_die_x
        die_y = self._current_die_y
        self._pending_x_values = x_values
        self._pending_y_values = y_values

        try:
            if self._session_dir is not None:
                output_path = self._session_dir / self._die_measurement_filename(
                    die_x, die_y
                )
                instrument = self._instrument_window
                if instrument is not None and instrument.uses_register_measurement:
                    instrument.save_register_measurement(self._session_dir, die_x, die_y)
                elif not output_path.exists():
                    write_die_measurement_csv(
                        self._session_dir,
                        die_x,
                        die_y,
                        x_values,
                        y_values,
                        tag=self._save_filename_tag(),
                    )
                if instrument is not None and instrument.uses_statistics_report:
                    append_statistics_row(
                        self._session_dir,
                        die_x,
                        die_y,
                        instrument.get_statistics_report_values(),
                    )
        except Exception as exc:
            self._fail(str(exc))
            return

        self._die_step = _DieStep.MOVE_SEPARATION
        self._advance_die_step()

    def _after_separation(self) -> None:
        die_x = self._current_die_x
        die_y = self._current_die_y
        x_values = self._pending_x_values
        y_values = self._pending_y_values

        try:
            judgment_bin = self._judge_current_die(x_values, y_values)
            result = DieMeasurementResult(
                die_x,
                die_y,
                x_values,
                y_values,
                judgment_bin,
            )
            self._results.append(result)
            logger.info(
                "Measured die (%d, %d): %d points, judgment bin=%d",
                die_x,
                die_y,
                len(x_values),
                judgment_bin,
            )
            self.die_measured.emit(result)
            self.progress.emit(self._next_index + 1, len(self._targets))
            self._next_index += 1
        except Exception as exc:
            self._fail(str(exc))
            return
        finally:
            self._busy = False

        if self._paused:
            self.paused.emit()
            return

        QTimer.singleShot(0, self._process_next)

    def _run_motor_action(
        self,
        action: Callable[[], None],
        on_success: Callable[[], None],
    ) -> None:
        if self._motor_worker is not None and self._is_qthread_running(
            self._motor_worker
        ):
            self._fail("馬達動作進行中，無法重複下達命令。")
            return

        self._pending_motor_success = on_success
        worker = _MotorWorker(action, parent=self)
        worker.succeeded.connect(
            self._on_motor_worker_succeeded,
            Qt.ConnectionType.QueuedConnection,
        )
        worker.failed.connect(
            self._on_motor_worker_failed,
            Qt.ConnectionType.QueuedConnection,
        )
        worker.finished.connect(
            lambda finished_worker=worker: self._release_motor_worker(
                finished_worker
            )
        )
        self._motor_worker = worker
        worker.start()

    def _on_motor_worker_succeeded(self) -> None:
        self._motor_worker = None
        callback = self._pending_motor_success
        self._pending_motor_success = None
        if callback is None or not self._running:
            return
        if self._paused:
            return
        callback()

    def _on_motor_worker_failed(self, message: str) -> None:
        self._motor_worker = None
        self._pending_motor_success = None
        self._fail(message)

    def _judge_current_die(
        self,
        x_values: list[float],
        y_values: list[float],
    ) -> int:
        instrument = self._instrument_window
        if instrument is None:
            return GOOD_DIE_BIN
        if instrument.uses_register_measurement:
            return GOOD_DIE_BIN if instrument.register_measurement_passed() else BAD_DIE_BIN
        if instrument.is_virtual_lcr:
            return judge_virtual_lcr_die(x_values, y_values)
        return judge_real_lcr_die(x_values, y_values)

    def _save_filename_tag(self) -> str:
        instrument = self._instrument_window
        if instrument is None:
            return ""
        name = getattr(instrument, "_instrument_name", "")
        if name == DSA_DISPLAY_NAME:
            return "DSA"
        return ""

    def _die_measurement_filename(self, die_x: int, die_y: int) -> str:
        if (
            self._instrument_window is not None
            and self._instrument_window.uses_register_measurement
        ):
            return f"X{die_x}_Y{die_y}_ROIC.csv"
        return die_measurement_filename(
            die_x, die_y, tag=self._save_filename_tag()
        )

    def _fail(self, message: str) -> None:
        self._running = False
        self._paused = False
        self._paused_mid_die = False
        self._busy = False
        self.failed.emit(message)


def die_measurement_filename(die_x: int, die_y: int, *, tag: str = "") -> str:
    return get_save_params().filename(x=die_x, y=die_y, tag=tag)


def write_die_measurement_csv(
    session_dir: Path,
    die_x: int,
    die_y: int,
    x_values: list[float],
    y_values: list[float],
    *,
    tag: str = "",
) -> Path:
    output_path = session_dir / die_measurement_filename(die_x, die_y, tag=tag)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["X", "Y"])
        for x_value, y_value in zip(x_values, y_values, strict=False):
            writer.writerow([x_value, y_value])
    return output_path


def write_measurement_csv(
    session_dir: Path,
    results: list[DieMeasurementResult],
    *,
    tag: str = "",
) -> Path:
    output_path = session_dir / "measurement_results.csv"
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Die_X", "Die_Y", "Data_File", "Point_Count", "Judgment_Bin"])
        for item in results:
            writer.writerow(
                [
                    item.x,
                    item.y,
                    die_measurement_filename(item.x, item.y, tag=tag),
                    len(item.x_values),
                    item.judgment_bin,
                ]
            )
    return output_path


def measure_Start(
    parent: QWidget,
    motor: ChuckMotorBase,
    targets: InspectionTargetList,
    session_dir: Path | None = None,
    instrument_window: InstrumentPanelBase | None = None,
    on_die_started: Callable[[int, int], None] | None = None,
    on_die_measured: Callable[[DieMeasurementResult], None] | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    on_complete: Callable[[list[DieMeasurementResult]], None] | None = None,
) -> MeasurementSession:
    """Run sequential die measurement and return the active session."""
    session = MeasurementSession(
        motor=motor,
        targets=targets,
        instrument_window=instrument_window,
        session_dir=session_dir,
        parent=parent,
    )

    def _handle_finished(results: list[DieMeasurementResult]) -> None:
        if (
            session_dir is not None
            and results
            and (instrument_window is None or not instrument_window.uses_register_measurement)
        ):
            write_measurement_csv(
                session_dir, results, tag=session._save_filename_tag(),
            )
        if on_complete is not None:
            on_complete(results)
        QMessageBox.information(parent, "量測", "量測完成!")

    def _handle_failed(message: str) -> None:
        QMessageBox.critical(parent, "量測錯誤", message)
        if on_complete is not None:
            on_complete([])

    session.finished.connect(_handle_finished)
    session.failed.connect(_handle_failed)
    if on_die_started is not None:
        session.die_started.connect(on_die_started)
    if on_die_measured is not None:
        session.die_measured.connect(on_die_measured)
    if on_progress is not None:
        session.progress.connect(on_progress)

    session.start()
    return session
