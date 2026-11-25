"""Persist the local NI DAQ selection for the ROIC tester."""

from pathlib import Path


class RoicDaqSettingsStore:
    def __init__(self, work_dir: Path | None = None) -> None:
        self._path = (work_dir or Path.cwd()) / "roic_daq_device.txt"

    def get_device(self) -> str | None:
        try:
            return self._path.read_text(encoding="utf-8").strip() or None
        except (OSError, UnicodeError):
            return None

    def save_device(self, name: str) -> None:
        self._path.write_text(name + "\n", encoding="utf-8")
