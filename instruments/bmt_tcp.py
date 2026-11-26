"""BMT3000 TCP client (server IP / port)."""

from __future__ import annotations

import logging
import select
import socket
from time import monotonic

logger = logging.getLogger(__name__)

DEFAULT_BMT_TCP_PORT = 51000
CONNECT_TIMEOUT_SEC = 5.0


class BmtTcpClient:
    """Minimal blocking TCP client for BMT3000."""

    def __init__(self) -> None:
        self._socket: socket.socket | None = None
        self._is_connected = False
        self._remote: tuple[str, int] | None = None
        self.roic_clock_frequency: str | None = None

    @property
    def is_connected(self) -> bool:
        return self._is_connected and self._socket is not None

    @property
    def remote_endpoint(self) -> tuple[str, int] | None:
        return self._remote

    def check_connection(self) -> bool:
        """Detect a closed peer without consuming any pending response data."""
        sock = self._socket
        if not self.is_connected or sock is None:
            return False
        try:
            readable, _, exceptional = select.select([sock], [], [sock], 0)
            if exceptional or (readable and not sock.recv(1, socket.MSG_PEEK)):
                self.disconnect()
        except OSError:
            self.disconnect()
        return self.is_connected

    def connect(
        self,
        ip: str,
        port: int = DEFAULT_BMT_TCP_PORT,
        timeout: float = CONNECT_TIMEOUT_SEC,
    ) -> None:
        if self._socket is not None:
            self.disconnect()

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            sock.connect((ip, int(port)))
        except OSError as exc:
            sock.close()
            if isinstance(exc, TimeoutError):
                raise TimeoutError(f"連線逾時 (超過 {timeout:g} 秒)") from None
            raise
        sock.settimeout(None)
        self._socket = sock
        self._is_connected = True
        self._remote = (ip, int(port))
        logger.info("BMT TCP connected to %s:%s", ip, port)

    def disconnect_roic(self) -> None:
        """Stop the external clock before intentionally ending a ROIC session."""
        if self.is_connected:
            try:
                self.send("PI5, StopCLK_EXT\n")
            except (OSError, RuntimeError):
                logger.warning("Unable to stop the ROIC external clock", exc_info=True)
        self.disconnect()

    def generate_roic_clock(self, frequency: str) -> None:
        """Generate the requested clock and wait for its matching acknowledgment."""
        self.roic_clock_frequency = None
        self.send(f"PI5, GenCLK_EXT,{frequency}\n")
        expected = f"GenCLK_EXT,OK,{frequency}".encode("ascii")
        deadline = monotonic() + 5
        pending = b""
        while (remaining := deadline - monotonic()) > 0:
            chunk = self.recv(timeout=remaining)
            if not chunk:
                self.disconnect()
                raise ConnectionError("Server disconnected")
            pending += chunk
            while b"\n" in pending:
                line, _, pending = pending.partition(b"\n")
                if line.startswith(b"GenCLK_EXT,"):
                    if line.removesuffix(b"\r") != expected:
                        raise ValueError("Unexpected external clock reply")
                    self.roic_clock_frequency = frequency
                    return
            if len(pending) > 65536:
                raise ValueError("Server reply is too long")
        raise TimeoutError("External clock reply timed out")

    def disconnect(self) -> None:
        self.roic_clock_frequency = None
        self._is_connected = False
        sock = self._socket
        self._socket = None
        self._remote = None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        logger.info("BMT TCP disconnected")

    def send(self, data: bytes | str) -> None:
        if not self.is_connected or self._socket is None:
            raise RuntimeError("TCP 未連接到 BMT Server")
        payload = data.encode("utf-8") if isinstance(data, str) else data
        self._socket.sendall(payload)

    def recv(self, bufsize: int = 4096, timeout: float | None = 5.0) -> bytes:
        if not self.is_connected or self._socket is None:
            raise RuntimeError("TCP 未連接到 BMT Server")
        sock = self._socket
        previous = sock.gettimeout()
        try:
            sock.settimeout(timeout)
            return sock.recv(bufsize)
        finally:
            try:
                sock.settimeout(previous)
            except OSError:
                pass

    def recv_exact(self, nbytes: int, timeout: float | None = 5.0) -> bytes:
        if nbytes < 0:
            raise ValueError("讀取長度不可為負數。")
        if nbytes == 0:
            return b""
        chunks: list[bytes] = []
        remaining = nbytes
        while remaining > 0:
            chunk = self.recv(min(remaining, 65536), timeout=timeout)
            if not chunk:
                raise ConnectionError(
                    f"伺服器提前關閉連線（已讀 {nbytes - remaining}/{nbytes} bytes）。"
                )
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)
