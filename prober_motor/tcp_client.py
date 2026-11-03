"""TCP client for MPI prober command interface."""

from __future__ import annotations

import logging
import socket
import threading
import time

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)

DEFAULT_TCP_PORT = 5555
CONNECT_TIMEOUT_SEC = 5.0
DEFAULT_REPLY_TIMEOUT_SEC = 5.0
CRLF_SUFFIX = "\r\n"


class ProberTcpClient(QObject):
    """Minimal blocking TCP client for sending prober command strings."""

    command_sent = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._socket: socket.socket | None = None
        self._is_connected = False
        self._receive_thread: threading.Thread | None = None
        self._io_lock = threading.Lock()
        self._sync_query = threading.Event()
        self._command_suffix = ""

    @property
    def command_suffix(self) -> str:
        return self._command_suffix

    @command_suffix.setter
    def command_suffix(self, suffix: str) -> None:
        self._command_suffix = suffix

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    def connect(
        self,
        ip: str,
        port: int = DEFAULT_TCP_PORT,
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
        self._receive_thread = threading.Thread(
            target=self._receive_loop, daemon=True
        )
        self._receive_thread.start()
        logger.info("TCP connected to %s:%s", ip, port)

    def disconnect(self) -> None:
        self._is_connected = False
        with self._io_lock:
            sock = self._socket
            self._socket = None
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
        receive_thread = self._receive_thread
        if receive_thread is not None and receive_thread.is_alive():
            receive_thread.join(timeout=1.0)
        self._receive_thread = None
        logger.info("TCP disconnected")

    @staticmethod
    def _normalize_command(data: str) -> str:
        return data.strip().removesuffix("\r\n").removesuffix("\n")

    def _notify_command_sent(self, data: str) -> None:
        command = self._normalize_command(data)
        logger.info("[TCP 發送] %s", command)
        self.command_sent.emit(command)

    def _prepare_payload(self, data: str) -> str:
        suffix = self._command_suffix
        if not suffix or data.endswith(suffix):
            return data
        return f"{data}{suffix}"

    def send(self, data: str) -> None:
        payload = self._prepare_payload(data)
        with self._io_lock:
            if not self._is_connected or self._socket is None:
                raise RuntimeError("TCP 未連接到 Prober Server")
            sock = self._socket
            sock.sendall(payload.encode("utf-8"))
        self._notify_command_sent(payload)

    def send_and_receive(
        self,
        data: str,
        timeout: float = DEFAULT_REPLY_TIMEOUT_SEC,
    ) -> str:
        if not self._is_connected or self._socket is None:
            raise RuntimeError("TCP 未連接到 Prober Server")

        payload = self._prepare_payload(data)
        with self._io_lock:
            if not self._is_connected or self._socket is None:
                raise RuntimeError("TCP 未連接到 Prober Server")
            sock = self._socket
            self._sync_query.set()
            try:
                sock.settimeout(timeout)
                sock.sendall(payload.encode("utf-8"))
                self._notify_command_sent(payload)

                chunks: list[bytes] = []
                while True:
                    try:
                        chunk = sock.recv(1024)
                    except TimeoutError:
                        break
                    if not chunk:
                        break
                    chunks.append(chunk)
                    if b"\n" in chunk or b"\r" in chunk:
                        break

                response = b"".join(chunks).decode("utf-8", errors="ignore").strip()
                if response:
                    logger.info("[TCP 接收] %s", response)
                return response
            finally:
                if self._socket is sock:
                    try:
                        sock.settimeout(None)
                    except OSError:
                        pass
                self._sync_query.clear()

    def _receive_loop(self) -> None:
        try:
            while self._is_connected:
                if self._sync_query.is_set():
                    time.sleep(0.01)
                    continue
                if not self._io_lock.acquire(blocking=False):
                    time.sleep(0.01)
                    continue
                try:
                    if self._sync_query.is_set() or not self._is_connected:
                        continue
                    sock = self._socket
                    if sock is None:
                        continue
                    sock.settimeout(0.2)
                    try:
                        data = sock.recv(1024)
                    except TimeoutError:
                        continue
                    if not data:
                        break
                    logger.info(
                        "[TCP 接收] %s",
                        data.decode("utf-8", errors="ignore").strip(),
                    )
                finally:
                    self._io_lock.release()
        except OSError as exc:
            if self._is_connected:
                logger.warning("TCP receive error: %s", exc)
        finally:
            if self._is_connected:
                self._is_connected = False
                with self._io_lock:
                    sock = self._socket
                    self._socket = None
                    if sock is not None:
                        try:
                            sock.close()
                        except OSError:
                            pass
