"""Persist TCP server IP/port per prober type for guided setup."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from prober_motor import ProberType
from prober_motor.tcp_client import DEFAULT_TCP_PORT

logger = logging.getLogger(__name__)

_SETTINGS_FILE_NAME = "prober_tcp_settings.json"
_DEFAULT_IP = "127.0.0.1"
_TCP_PROBER_TYPES = frozenset(
    {ProberType.SUSS, ProberType.MPI_TP80, ProberType.MPI_TS2000}
)


@dataclass(frozen=True)
class ProberTcpEndpoint:
    ip: str
    port: int


class ProberTcpSettingsStore:
    """Load/save last successful TCP endpoints keyed by prober type."""

    def __init__(self, work_dir: Path | None = None) -> None:
        self._path = (work_dir or Path.cwd()) / _SETTINGS_FILE_NAME

    def get_endpoint(self, prober_type: ProberType) -> ProberTcpEndpoint | None:
        if prober_type not in _TCP_PROBER_TYPES:
            return None
        data = self._read_all()
        entry = data.get(prober_type.value)
        if not isinstance(entry, dict):
            return None
        ip = str(entry.get("ip", "")).strip()
        port = entry.get("port")
        if not ip or not isinstance(port, int) or not 1 <= port <= 65535:
            return None
        return ProberTcpEndpoint(ip=ip, port=port)

    def save_endpoint(
        self, prober_type: ProberType, ip: str, port: int
    ) -> None:
        if prober_type not in _TCP_PROBER_TYPES:
            return
        ip = ip.strip()
        if not ip or not 1 <= port <= 65535:
            return

        data = self._read_all()
        data[prober_type.value] = {"ip": ip, "port": port}
        try:
            self._path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("Unable to save %s: %s", self._path, exc)

    def default_endpoint(self) -> ProberTcpEndpoint:
        return ProberTcpEndpoint(ip=_DEFAULT_IP, port=DEFAULT_TCP_PORT)

    def _read_all(self) -> dict[str, dict[str, object]]:
        if not self._path.is_file():
            return {}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Unable to read %s: %s", self._path, exc)
            return {}
        if not isinstance(raw, dict):
            return {}
        return raw
