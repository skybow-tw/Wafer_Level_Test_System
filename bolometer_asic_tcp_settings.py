"""Persist the last successful Bolometer ASIC server endpoint."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path


logger = logging.getLogger(__name__)

SETTINGS_FILE_NAME = "bolometer_asic_tcp_settings.json"
DEFAULT_IP = "192.168.50.186"
DEFAULT_PORT = 5000


@dataclass(frozen=True)
class BolometerAsicTcpEndpoint:
    ip: str
    port: int


class BolometerAsicTcpSettingsStore:
    def __init__(self, work_dir: Path | None = None) -> None:
        self._path = (work_dir or Path.cwd()) / SETTINGS_FILE_NAME

    def get_endpoint(self) -> BolometerAsicTcpEndpoint:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return BolometerAsicTcpEndpoint(DEFAULT_IP, DEFAULT_PORT)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Unable to read %s: %s", self._path, exc)
            return BolometerAsicTcpEndpoint(DEFAULT_IP, DEFAULT_PORT)

        if isinstance(raw, dict):
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

    def save_endpoint(self, ip: str, port: int) -> None:
        ip = ip.strip()
        if not ip or not 1 <= port <= 65535:
            return
        try:
            self._path.write_text(
                json.dumps({"ip": ip, "port": port}, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("Unable to save %s: %s", self._path, exc)
