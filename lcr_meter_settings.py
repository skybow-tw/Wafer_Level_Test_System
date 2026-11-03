"""Persist LCR meter UI defaults between sessions."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_SETTINGS_FILE_NAME = "lcr_meter_settings.json"


@dataclass(frozen=True)
class LcrMeterSettings:
    function: str
    frequency_hz: float
    voltage_v: float
    dc_offset_start_v: float
    dc_offset_stop_v: float
    dc_offset_step_v: float
    vp_detect_method: str
    vp_threshold_ff: float


class LcrMeterSettingsStore:
    """Load/save last configured LCR meter parameters."""

    def __init__(
        self, work_dir: Path | None = None, file_name: str = _SETTINGS_FILE_NAME
    ) -> None:
        self._path = (work_dir or Path.cwd()) / file_name

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> LcrMeterSettings | None:
        if not self._path.is_file():
            return None
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Unable to read %s: %s", self._path, exc)
            return None
        if not isinstance(raw, dict):
            return None
        try:
            return LcrMeterSettings(
                function=str(raw["function"]),
                frequency_hz=float(raw["frequency_hz"]),
                voltage_v=float(raw["voltage_v"]),
                dc_offset_start_v=float(raw["dc_offset_start_v"]),
                dc_offset_stop_v=float(raw["dc_offset_stop_v"]),
                dc_offset_step_v=float(raw["dc_offset_step_v"]),
                vp_detect_method=str(raw["vp_detect_method"]),
                vp_threshold_ff=float(raw["vp_threshold_ff"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Invalid LCR settings in %s: %s", self._path, exc)
            return None

    def save(self, settings: LcrMeterSettings) -> None:
        payload = {
            "function": settings.function,
            "frequency_hz": settings.frequency_hz,
            "voltage_v": settings.voltage_v,
            "dc_offset_start_v": settings.dc_offset_start_v,
            "dc_offset_stop_v": settings.dc_offset_stop_v,
            "dc_offset_step_v": settings.dc_offset_step_v,
            "vp_detect_method": settings.vp_detect_method,
            "vp_threshold_ff": settings.vp_threshold_ff,
        }
        try:
            self._path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("Unable to save %s: %s", self._path, exc)
