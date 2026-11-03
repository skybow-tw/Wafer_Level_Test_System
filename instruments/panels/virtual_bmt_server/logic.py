"""Virtual BMT TCP server: framed messages and Measure responses for BMT3000."""

from __future__ import annotations

import math
import socket
import struct
import threading
from typing import Callable

from instruments.bmt_tcp import DEFAULT_BMT_TCP_PORT
from instruments.panels.bmt3000.logic import (
    CONNECT_ID,
    DEFAULT_COLUMN_COUNT,
    FLOAT64_BYTES,
    MAX_PAYLOAD_BYTES,
    MEASURE_COMMAND,
    SIZE_HEADER_BYTES,
    pack_size_header,
    parse_size_header,
)

DEFAULT_BIND_HOST = "0.0.0.0"
DEFAULT_POINT_COUNT = 51
RECV_TIMEOUT_SEC = 1.0


def generate_virtual_iv_payload(
    point_count: int = DEFAULT_POINT_COUNT,
    columns: int = DEFAULT_COLUMN_COUNT,
) -> bytes:
    """Build big-endian float64 rows: V_in, V_Out, I(mA), R(kΩ).

    Byte order matches BMT3000 ``payload_to_rows`` (``>{n}d``).
    """
    if point_count < 2:
        raise ValueError("point_count 至少為 2。")
    if columns != DEFAULT_COLUMN_COUNT:
        raise ValueError(f"目前僅支援 {DEFAULT_COLUMN_COUNT} 欄虛擬資料。")

    values: list[float] = []
    for index in range(point_count):
        v_in = 5.0 * index / (point_count - 1)
        # Soft diode-like IV so BMT3000 chart has a clear curve.
        i_ma = 0.05 * (math.exp(v_in / 0.85) - 1.0)
        v_out = max(0.0, v_in - 0.02 * i_ma)
        r_kohm = (v_in / i_ma) if i_ma > 1e-9 else 1.0e6
        values.extend((v_in, v_out, i_ma, r_kohm))
    return struct.pack(f">{len(values)}d", *values)


def build_measure_response(
    point_count: int = DEFAULT_POINT_COUNT,
) -> bytes:
    payload = generate_virtual_iv_payload(point_count=point_count)
    return pack_size_header(len(payload)) + payload


def _recv_exact(sock: socket.socket, nbytes: int) -> bytes:
    if nbytes < 0:
        raise ValueError("讀取長度不可為負數。")
    if nbytes == 0:
        return b""
    if nbytes > MAX_PAYLOAD_BYTES:
        raise ValueError(f"請求長度過大（{nbytes} bytes）。")
    chunks: list[bytes] = []
    remaining = nbytes
    while remaining > 0:
        chunk = sock.recv(min(remaining, 65536))
        if not chunk:
            raise ConnectionError(
                f"client 提前關閉連線（已讀 {nbytes - remaining}/{nbytes} bytes）。"
            )
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


class VirtualBmtTcpServer:
    """Multi-client TCP server compatible with BMT3000 framed Measure protocol."""

    def __init__(
        self,
        *,
        on_status: Callable[[bool], None] | None = None,
        on_client_count: Callable[[int], None] | None = None,
        on_log: Callable[[str], None] | None = None,
        point_count: int = DEFAULT_POINT_COUNT,
    ) -> None:
        self._on_status = on_status
        self._on_client_count = on_client_count
        self._on_log = on_log
        self._point_count = point_count

        self._lock = threading.Lock()
        self._server_sock: socket.socket | None = None
        self._accept_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._clients: dict[socket.socket, tuple[str, int]] = {}
        self._client_threads: list[threading.Thread] = []
        self._running = False
        self._bound_port: int | None = None

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def bound_port(self) -> int | None:
        return self._bound_port

    @property
    def client_count(self) -> int:
        with self._lock:
            return len(self._clients)

    def _emit_log(self, message: str) -> None:
        if self._on_log is not None:
            self._on_log(message)

    def _emit_status(self) -> None:
        if self._on_status is not None:
            self._on_status(self._running)

    def _emit_client_count(self) -> None:
        if self._on_client_count is not None:
            self._on_client_count(self.client_count)

    def start(
        self,
        port: int = DEFAULT_BMT_TCP_PORT,
        host: str = DEFAULT_BIND_HOST,
    ) -> None:
        if self._running:
            raise RuntimeError("Server 已在執行中。")
        if not (1 <= int(port) <= 65535):
            raise ValueError("Port 必須介於 1–65535。")

        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server.bind((host, int(port)))
            server.listen(16)
            server.settimeout(RECV_TIMEOUT_SEC)
        except OSError:
            server.close()
            raise

        self._stop_event.clear()
        self._server_sock = server
        self._bound_port = int(port)
        self._running = True
        self._emit_status()
        self._emit_client_count()
        self._emit_log(f"Server 已啟動，監聽 {host}:{port}")

        self._accept_thread = threading.Thread(
            target=self._accept_loop,
            name="VirtualBmtAccept",
            daemon=True,
        )
        self._accept_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        server = self._server_sock
        self._server_sock = None

        if server is not None:
            try:
                server.close()
            except OSError:
                pass

        with self._lock:
            clients = list(self._clients.keys())
            self._clients.clear()

        for client in clients:
            try:
                client.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                client.close()
            except OSError:
                pass

        accept_thread = self._accept_thread
        self._accept_thread = None
        if accept_thread is not None and accept_thread.is_alive():
            accept_thread.join(timeout=2.0)

        with self._lock:
            threads = list(self._client_threads)
            self._client_threads.clear()
        for thread in threads:
            if thread.is_alive():
                thread.join(timeout=1.0)

        was_running = self._running
        self._running = False
        self._bound_port = None
        self._emit_status()
        self._emit_client_count()
        if was_running:
            self._emit_log("Server 已停止")

    def _accept_loop(self) -> None:
        while not self._stop_event.is_set():
            server = self._server_sock
            if server is None:
                break
            try:
                client, address = server.accept()
            except socket.timeout:
                continue
            except OSError:
                if self._stop_event.is_set():
                    break
                self._emit_log("Accept 失敗，Server 將停止。")
                break

            client.settimeout(RECV_TIMEOUT_SEC)
            with self._lock:
                self._clients[client] = address
            self._emit_client_count()
            self._emit_log(f"Client 連線：{address[0]}:{address[1]}")

            thread = threading.Thread(
                target=self._client_loop,
                args=(client, address),
                name=f"VirtualBmtClient-{address[0]}:{address[1]}",
                daemon=True,
            )
            with self._lock:
                self._client_threads.append(thread)
            thread.start()

        self._running = False
        self._emit_status()

    def _unregister_client(self, client: socket.socket, address: tuple[str, int]) -> None:
        with self._lock:
            removed = self._clients.pop(client, None) is not None
        try:
            client.close()
        except OSError:
            pass
        if removed:
            self._emit_client_count()
            self._emit_log(f"Client 斷線：{address[0]}:{address[1]}")

    def _client_loop(self, client: socket.socket, address: tuple[str, int]) -> None:
        try:
            while not self._stop_event.is_set():
                try:
                    header = _recv_exact(client, SIZE_HEADER_BYTES)
                except socket.timeout:
                    continue
                except (ConnectionError, OSError):
                    break

                try:
                    size_data = parse_size_header(header)
                    payload = _recv_exact(client, size_data)
                except (ValueError, ConnectionError, OSError) as exc:
                    self._emit_log(
                        f"讀取 frame 失敗 ({address[0]}:{address[1]}): {exc}"
                    )
                    break

                self._handle_payload(client, address, payload)
        finally:
            self._unregister_client(client, address)

    def _handle_payload(
        self,
        client: socket.socket,
        address: tuple[str, int],
        payload: bytes,
    ) -> None:
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError:
            text = f"<binary {len(payload)} bytes>"

        peer = f"{address[0]}:{address[1]}"
        if text == CONNECT_ID:
            self._emit_log(f"[{peer}] Connect ID: {text}")
            return

        if text == MEASURE_COMMAND:
            response = build_measure_response(point_count=self._point_count)
            float_count = (len(response) - SIZE_HEADER_BYTES) // FLOAT64_BYTES
            row_count = float_count // DEFAULT_COLUMN_COUNT
            try:
                client.sendall(response)
            except OSError as exc:
                self._emit_log(f"[{peer}] Measure 回傳失敗: {exc}")
                return
            self._emit_log(
                f"[{peer}] Measure '{MEASURE_COMMAND}' → "
                f"{row_count} 列虛擬 IV 資料 ({len(response)} bytes)"
            )
            return

        self._emit_log(f"[{peer}] 收到未處理命令: {text!r}")
