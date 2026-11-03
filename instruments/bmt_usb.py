"""BMT USB connection via pyusb (CDC bulk endpoints)."""

from __future__ import annotations

from dataclasses import dataclass

from instruments.usb_raw_scanner import UsbDeviceInfo

_CDC_DATA_CLASS = 0x0A


@dataclass
class BmtUsbConnection:
    """Open USB handle for a selected STM32 / BMT device."""

    device_info: UsbDeviceInfo
    _device: object
    _interface_number: int
    endpoint_out: object
    endpoint_in: object

    @classmethod
    def open(cls, device_info: UsbDeviceInfo) -> BmtUsbConnection:
        try:
            import usb.core
            import usb.util
        except ImportError as exc:
            raise RuntimeError(
                "未安裝 pyusb，請執行: pip install pyusb"
            ) from exc

        device = _find_matching_device(device_info)
        if device is None:
            raise RuntimeError(
                f"找不到裝置：{device_info.name} ({device_info.detail_label})"
            )

        try:
            device.set_configuration()
        except usb.core.USBError:
            # Already configured is acceptable.
            pass

        configuration = device.get_active_configuration()
        interface = _find_data_interface(configuration)
        if interface is None:
            raise RuntimeError("找不到可用的 USB data interface / endpoint。")

        interface_number = int(interface.bInterfaceNumber)
        try:
            if device.is_kernel_driver_active(interface_number):
                device.detach_kernel_driver(interface_number)
        except (NotImplementedError, usb.core.USBError):
            pass

        usb.util.claim_interface(device, interface_number)

        endpoint_out = usb.util.find_descriptor(
            interface,
            custom_match=lambda ep: (
                usb.util.endpoint_direction(ep.bEndpointAddress)
                == usb.util.ENDPOINT_OUT
            ),
        )
        endpoint_in = usb.util.find_descriptor(
            interface,
            custom_match=lambda ep: (
                usb.util.endpoint_direction(ep.bEndpointAddress)
                == usb.util.ENDPOINT_IN
            ),
        )
        if endpoint_out is None or endpoint_in is None:
            usb.util.release_interface(device, interface_number)
            usb.util.dispose_resources(device)
            raise RuntimeError("找不到 Bulk IN/OUT endpoint。")

        return cls(
            device_info=device_info,
            _device=device,
            _interface_number=interface_number,
            endpoint_out=endpoint_out,
            endpoint_in=endpoint_in,
        )

    @property
    def is_open(self) -> bool:
        return self._device is not None

    def close(self) -> None:
        if self._device is None:
            return
        try:
            import usb.util

            try:
                usb.util.release_interface(self._device, self._interface_number)
            except Exception:
                pass
            try:
                usb.util.dispose_resources(self._device)
            except Exception:
                pass
        finally:
            self._device = None
            self.endpoint_out = None
            self.endpoint_in = None

    def flush_input(
        self,
        *,
        chunk_size: int | None = None,
        timeout_ms: int = 50,
        max_reads: int = 64,
    ) -> int:
        """Discard any unread data waiting on the IN endpoint.

        Keeps reading short chunks until a timeout (empty buffer) or
        ``max_reads`` is reached. Returns the number of bytes discarded.
        """
        if self._device is None or self.endpoint_in is None:
            return 0

        import usb.core

        read_size = chunk_size
        if read_size is None:
            try:
                read_size = int(self.endpoint_in.wMaxPacketSize) or 64
            except Exception:
                read_size = 64

        discarded = 0
        for _ in range(max_reads):
            try:
                data = self.endpoint_in.read(read_size, timeout=timeout_ms)
            except usb.core.USBError as exc:
                errno = getattr(exc, "errno", None)
                message = str(exc).lower()
                # Timeout ⇒ no more pending data.
                if (
                    errno in (-7, 110, 10060)
                    or "timeout" in message
                    or "timed out" in message
                ):
                    break
                # Other USB errors: stop draining rather than failing the caller.
                break
            if not data:
                break
            discarded += len(data)
        return discarded

    def write_read(self, cmd: bytes, length: int, timeout_ms: int = 1000) -> bytes:
        """Write a command to OUT endpoint, then read ``length`` bytes from IN."""
        if self._device is None or self.endpoint_out is None or self.endpoint_in is None:
            raise RuntimeError("USB 裝置尚未連線。")
        if length < 1:
            raise ValueError("length must be >= 1")

        import usb.core

        self.endpoint_out.write(cmd, timeout=timeout_ms)
        response = self.endpoint_in.read(length, timeout=timeout_ms)
        data = bytes(response)
        if len(data) < length:
            raise usb.core.USBError("讀取資料長度不足！")
        return data

    def read_registers(
        self,
        did: int | str = 0xC0,
        reg: int | str = 0x00,
        length: int | str = 0x10,
        *,
        timeout_ms: int = 1000,
        flush_first: bool = True,
    ) -> bytes:
        """Read register bytes using BMT5000 protocol ``F304{DID}00{REG}{LEN}``."""
        did_byte = _as_u8(did, "did")
        reg_byte = _as_u8(reg, "reg")
        len_byte = _as_u8(length, "length")
        if len_byte < 1:
            raise ValueError("length must be >= 1")

        if flush_first:
            self.flush_input()

        # Example: F304C0000010  →  DID=C0, REG=00, LEN=10
        cmd = bytes(
            (
                0xF3,
                0x04,
                did_byte,
                0x00,
                reg_byte,
                len_byte,
            )
        )
        return self.write_read(cmd, len_byte, timeout_ms=timeout_ms)

    def read_register_map(
        self,
        did: int | str = 0xC0,
        *,
        timeout_ms: int = 1000,
    ) -> bytes:
        """Read the full 256-byte register map (16 rows × 16 bytes)."""
        chunks: list[bytes] = []
        for row_base in range(0, 256, 16):
            chunks.append(
                self.read_registers(
                    did=did,
                    reg=row_base,
                    length=0x10,
                    timeout_ms=timeout_ms,
                )
            )
        return b"".join(chunks)


def _as_u8(value: int | str, name: str) -> int:
    if isinstance(value, str):
        text = value.strip().lower()
        if text.startswith("0x"):
            text = text[2:]
        try:
            parsed = int(text, 16)
        except ValueError as exc:
            raise ValueError(f"{name} 必須為 16 進位字串或整數") from exc
    else:
        parsed = int(value)
    if not (0 <= parsed <= 0xFF):
        raise ValueError(f"{name} 必須介於 0–255")
    return parsed


def _safe_serial(device) -> str | None:
    try:
        serial = device.serial_number
    except Exception:
        return None
    if serial is None:
        return None
    text = str(serial).strip()
    return text or None


def _find_matching_device(device_info: UsbDeviceInfo):
    import usb.core

    vid = int(device_info.vid, 16)
    pid = int(device_info.pid, 16)
    candidates = list(usb.core.find(find_all=True, idVendor=vid, idProduct=pid))
    if not candidates:
        return None

    if device_info.serial:
        for device in candidates:
            if _safe_serial(device) == device_info.serial:
                return device

    for device in candidates:
        if (
            int(device.bus) == device_info.bus
            and int(device.address) == device_info.address
        ):
            return device

    # Fall back only when a single matching VID/PID device is present.
    if len(candidates) == 1:
        return candidates[0]
    return None


def _find_data_interface(configuration):
    # Prefer CDC Data interface; otherwise first interface with IN+OUT endpoints.
    cdc_data = None
    fallback = None
    for interface in configuration:
        has_out = False
        has_in = False
        for endpoint in interface:
            direction = endpoint.bEndpointAddress & 0x80
            if direction == 0x00:
                has_out = True
            else:
                has_in = True
        if not (has_in and has_out):
            continue
        if int(interface.bInterfaceClass) == _CDC_DATA_CLASS:
            cdc_data = interface
            break
        if fallback is None:
            fallback = interface
    return cdc_data or fallback
