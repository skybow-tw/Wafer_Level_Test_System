"""Watch 00_Datalog for new folders and measurement files."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QObject, QTimer, Signal

from datalog import DATALOG_ROOT_NAME

_MEASUREMENT_FILE_SUFFIXES = {".csv", ".xls", ".xlsx"}
_DEBOUNCE_MS = 100


class DatalogWatcher(QObject):
    """Emit when a new datalog folder or measurement file appears."""

    datalog_detected = Signal(object)  # Path — directory to open in file explorer

    def __init__(self, work_dir: Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._root = work_dir / DATALOG_ROOT_NAME
        self._known: set[str] = set()
        self._watcher = QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(self._on_directory_changed)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(_DEBOUNCE_MS)
        self._debounce.timeout.connect(self._check_for_changes)

    def start(self) -> None:
        self._root.mkdir(exist_ok=True)
        self._known = self._snapshot()
        self._register_watches()

    def stop(self) -> None:
        self._debounce.stop()
        for path in self._watcher.directories():
            self._watcher.removePath(path)

    def reset_baseline(self) -> None:
        """Treat the current tree as baseline; only later additions trigger."""
        self._known = self._snapshot()
        self._register_watches()

    def _snapshot(self) -> set[str]:
        if not self._root.is_dir():
            return set()
        return {self._key(path) for path in self._root.rglob("*")}

    @staticmethod
    def _key(path: Path) -> str:
        return str(path.resolve())

    def _register_watches(self) -> None:
        if not self._root.is_dir():
            return

        watched = set(self._watcher.directories())
        dirs_to_watch = {str(self._root.resolve())}
        for path in self._root.rglob("*"):
            if path.is_dir():
                dirs_to_watch.add(str(path.resolve()))

        for directory in dirs_to_watch - watched:
            self._watcher.addPath(directory)

    def _on_directory_changed(self, _path: str) -> None:
        # OS may fire several signals for one write; debounce into a single scan.
        self._debounce.start()

    def _check_for_changes(self) -> None:
        if not self._root.is_dir():
            self._root.mkdir(exist_ok=True)
            self._register_watches()
            return

        self._register_watches()
        current = self._snapshot()
        new_keys = current - self._known
        if not new_keys:
            return

        self._known = current
        open_dir = self._pick_open_dir(new_keys)
        if open_dir is not None:
            self.datalog_detected.emit(open_dir)

    def _pick_open_dir(self, new_keys: set[str]) -> Path | None:
        new_paths = [Path(key) for key in new_keys]

        measurement_files = [
            path
            for path in new_paths
            if path.is_file() and path.suffix.lower() in _MEASUREMENT_FILE_SUFFIXES
        ]
        if measurement_files:
            newest = max(measurement_files, key=lambda path: path.stat().st_mtime)
            return newest.parent

        new_dirs = [path for path in new_paths if path.is_dir()]
        if new_dirs:
            newest = max(new_dirs, key=lambda path: path.stat().st_mtime)
            return newest

        other_files = [path for path in new_paths if path.is_file()]
        if other_files:
            newest = max(other_files, key=lambda path: path.stat().st_mtime)
            return newest.parent

        return None
