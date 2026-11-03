"""BMT3000 TCP connection and Measure operations."""

from __future__ import annotations

import struct

from instruments.bmt_tcp import BmtTcpClient

CONNECT_ID = "Name,MPI"
MEASURE_COMMAND = "Q"
SIZE_HEADER_BYTES = 4
FLOAT64_BYTES = 8
DEFAULT_COLUMN_COUNT = 4
MAX_PAYLOAD_BYTES = 32 * 1024 * 1024
MEASURE_TIMEOUT_SEC = 5.0


def pack_size_header(size: int) -> bytes:
    """Encode payload length as a 4-byte big-endian integer."""
    if size < 0:
        raise ValueError("payload 長度不可為負數。")
    return struct.pack(">I", size)


def frame_payload(data: bytes | str) -> bytes:
    """Prefix a string/bytes payload with its 4-byte length."""
    payload = data.encode("utf-8") if isinstance(data, str) else data
    return pack_size_header(len(payload)) + payload


def parse_size_header(header: bytes) -> int:
    """Decode the 4-byte big-endian payload length prefix."""
    if len(header) != SIZE_HEADER_BYTES:
        raise ValueError(
            f"長度標頭必須為 {SIZE_HEADER_BYTES} bytes，實際為 {len(header)}。"
        )
    size_data = struct.unpack(">I", header)[0]
    if size_data > MAX_PAYLOAD_BYTES:
        raise ValueError(
            f"Size_Data 過大（{size_data} bytes，上限 {MAX_PAYLOAD_BYTES}）。"
        )
    return size_data


def payload_to_rows(
    payload: bytes,
    columns: int = DEFAULT_COLUMN_COUNT,
) -> list[list[float]]:
    """Convert big-endian float64 bytes into an M×N table (N defaults to 4)."""
    if columns < 1:
        raise ValueError("欄數 N 必須大於 0。")
    if len(payload) % FLOAT64_BYTES != 0:
        raise ValueError(
            f"資料長度 {len(payload)} bytes 無法轉成 float64 陣列（需為 8 的倍數）。"
        )
    value_count = len(payload) // FLOAT64_BYTES
    values = struct.unpack(f">{value_count}d", payload) if value_count else ()
    if value_count % columns != 0:
        raise ValueError(
            f"1D 陣列長度 {value_count} 無法整除欄數 N={columns}。"
        )
    row_count = value_count // columns
    return [
        list(values[index * columns : (index + 1) * columns])
        for index in range(row_count)
    ]


class Bmt3000Logic:
    """Hardware interaction for BMT3000 (TCP server)."""

    def __init__(self) -> None:
        self._tcp = BmtTcpClient()
        self._connecting = False
        self._measuring = False

    @property
    def tcp(self) -> BmtTcpClient:
        return self._tcp

    @property
    def connecting(self) -> bool:
        return self._connecting

    @connecting.setter
    def connecting(self, value: bool) -> None:
        self._connecting = value

    @property
    def measuring(self) -> bool:
        return self._measuring

    @measuring.setter
    def measuring(self, value: bool) -> None:
        self._measuring = value

    def is_connected(self) -> bool:
        return self._tcp.is_connected

    def remote_endpoint(self) -> tuple[str, int] | None:
        return self._tcp.remote_endpoint

    def parse_endpoint(self, ip_text: str, port_text: str) -> tuple[str, int]:
        ip = ip_text.strip()
        if not ip:
            raise ValueError("請輸入 Server IP 位址。")
        port_raw = port_text.strip()
        if not port_raw:
            raise ValueError("請輸入 Port。")
        try:
            port = int(port_raw)
        except ValueError as exc:
            raise ValueError("Port 必須為整數。") from exc
        if not (1 <= port <= 65535):
            raise ValueError("Port 必須介於 1–65535。")
        return ip, port

    def connect(self, ip: str, port: int) -> None:
        self._tcp.connect(ip, port)
        try:
            self._tcp.send(frame_payload(CONNECT_ID))
        except Exception:
            self.disconnect()
            raise

    def disconnect(self) -> None:
        self._connecting = False
        self._measuring = False
        try:
            self._tcp.disconnect()
        except Exception:
            pass

    def measure(
        self,
        columns: int = DEFAULT_COLUMN_COUNT,
        timeout: float = MEASURE_TIMEOUT_SEC,
    ) -> list[list[float]]:
        if not self.is_connected():
            raise RuntimeError("TCP 未連接到 BMT Server")
        self._tcp.send(frame_payload(MEASURE_COMMAND))
        header = self._tcp.recv_exact(SIZE_HEADER_BYTES, timeout=timeout)
        size_data = parse_size_header(header)
        payload = self._tcp.recv_exact(size_data, timeout=timeout)
        return payload_to_rows(payload, columns=columns)
