"""USB device discovery via pyusb (Name / VID / PID)."""

from __future__ import annotations

from dataclasses import dataclass

_TARGET_PRODUCT_NAME = "STM32 Virtual ComPort"


@dataclass(frozen=True)
class UsbDeviceInfo:
    name: str
    vid: str
    pid: str
    bus: int
    address: int
    serial: str | None = None

    @property
    def device_id(self) -> str:
        """Stable-enough selection key for the current session."""
        if self.serial:
            return f"{self.vid}:{self.pid}:SN={self.serial}"
        return f"{self.vid}:{self.pid}:BUS={self.bus}:ADDR={self.address}"

    # Backward-compatible alias used by older UI code.
    @property
    def pnp_device_id(self) -> str:
        return self.device_id

    @property
    def vid_pid_label(self) -> str:
        return f"VID={self.vid}  PID={self.pid}"

    @property
    def sn_label(self) -> str:
        if self.serial:
            return f"SN={self.serial}"
        return f"Bus={self.bus}  Addr={self.address}"

    @property
    def detail_label(self) -> str:
        return f"{self.vid_pid_label}  {self.sn_label}"

    @property
    def display_label(self) -> str:
        return f"{self.name}\n{self.vid_pid_label}\n{self.sn_label}"


UsbRawDeviceInfo = UsbDeviceInfo


def _safe_product_name(device) -> str | None:
    try:
        product = device.product
    except Exception:
        return None
    if product is None:
        return None
    return str(product).strip()


def _safe_serial_number(device) -> str | None:
    try:
        serial = device.serial_number
    except Exception:
        return None
    if serial is None:
        return None
    text = str(serial).strip()
    return text or None


def list_usb_devices() -> list[UsbDeviceInfo]:
    """Return STM32 Virtual ComPort devices found by pyusb."""
    try:
        import usb.core
    except ImportError as exc:
        raise RuntimeError(
            "未安裝 pyusb，請執行: pip install pyusb"
        ) from exc

    devices: list[UsbDeviceInfo] = []
    for device in usb.core.find(find_all=True):
        name = _safe_product_name(device)
        if name != _TARGET_PRODUCT_NAME:
            continue

        devices.append(
            UsbDeviceInfo(
                name=name,
                vid=f"{int(device.idVendor):04X}",
                pid=f"{int(device.idProduct):04X}",
                bus=int(device.bus),
                address=int(device.address),
                serial=_safe_serial_number(device),
            )
        )

    devices.sort(
        key=lambda item: (
            item.name.lower(),
            item.vid,
            item.pid,
            item.serial or "",
            item.bus,
            item.address,
        )
    )
    return devices


def list_usb_raw_devices() -> list[UsbDeviceInfo]:
    """Alias kept for compatibility with existing call sites."""
    return list_usb_devices()
