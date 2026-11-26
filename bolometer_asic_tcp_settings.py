"""Persist the ROIC tester endpoint, DAQ device and external clock selection."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path


logger = logging.getLogger(__name__)

SETTINGS_FILE_NAME = "bolometer_asic_tcp_settings.json"
DEFAULT_IP = "192.168.50.186"
DEFAULT_PORT = 5000
ROIC_CLOCK_OPTIONS = ("1MHz", "5MHz", "10MHz")


@dataclass(frozen=True)
class BolometerAsicTcpEndpoint:
    ip: str
    port: int


class BolometerAsicTcpSettingsStore:
    def __init__(self, work_dir: Path | None = None) -> None:
        self._path = (work_dir or Path.cwd()) / SETTINGS_FILE_NAME

    def _read_settings(self) -> dict:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            logger.warning("Unable to read %s: %s", self._path, exc)
            return {}
        return raw if isinstance(raw, dict) else {}

    def get_endpoint(self) -> BolometerAsicTcpEndpoint:
        raw = self._read_settings()
        if "ip" in raw or "port" in raw:
            ip = raw.get("ip")
            port = raw.get("port")
            if (
                isinstance(ip, str)
                and ip.strip()
                and isinstance(port, int)
                and not isinstance(port, bool)
                and 1 <= port <= 65535
            ):
                return BolometerAsicTcpEndpoint(ip.strip(), port)
            logger.warning("Invalid Bolometer ASIC server settings in %s", self._path)
        return BolometerAsicTcpEndpoint(DEFAULT_IP, DEFAULT_PORT)

    def get_clock_frequency(self) -> str:
        frequency = self._read_settings().get("clock_frequency")
        return frequency if frequency in ROIC_CLOCK_OPTIONS else ROIC_CLOCK_OPTIONS[0]

    def save_clock_frequency(self, frequency: str) -> None:
        if frequency in ROIC_CLOCK_OPTIONS:
            self._save_settings(clock_frequency=frequency)

    def get_daq_device(self) -> str | None:
        name = self._read_settings().get("daq_device")
        if isinstance(name, str) and name.strip():
            return name.strip()
        try:
            return self._path.with_name("roic_daq_device.txt").read_text(encoding="utf-8").strip() or None
        except (OSError, UnicodeError):
            return None

    def save_daq_device(self, name: str) -> None:
        self._save_settings(daq_device=name)

    def _save_settings(self, **updates: str | int) -> None:
        settings = self._read_settings()
        settings.update(updates)
        self._path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")

    def save_endpoint(self, ip: str, port: int) -> None:
        ip = ip.strip()
        if not ip or not 1 <= port <= 65535:
            return
        try:
            self._save_settings(ip=ip, port=port)
        except OSError as exc:
            logger.warning("Unable to save %s: %s", self._path, exc)
