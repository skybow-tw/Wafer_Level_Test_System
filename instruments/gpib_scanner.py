"""GPIB instrument discovery via VISA."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GpibInstrumentInfo:
    resource_name: str
    identification: str

    @property
    def model(self) -> str:
        """Product model from *IDN? (2nd comma-separated field)."""
        if not self.identification:
            return ""
        parts = [part.strip() for part in self.identification.split(",")]
        if len(parts) >= 2:
            return parts[1]
        return ""

    @property
    def display_label(self) -> str:
        if self.model:
            return f"{self.resource_name} ({self.model})"
        return self.resource_name


def list_gpib_instruments() -> list[GpibInstrumentInfo]:
    """Return GPIB instruments currently visible to the VISA resource manager."""
    try:
        import pyvisa
    except ImportError as exc:
        raise RuntimeError(
            "未安裝 pyvisa，請執行: pip install pyvisa"
        ) from exc

    rm = pyvisa.ResourceManager()
    instruments: list[GpibInstrumentInfo] = []

    for resource_name in rm.list_resources("GPIB?*::INSTR"):
        identification = ""
        try:
            instrument = rm.open_resource(resource_name)
            instrument.timeout = 2000
            identification = str(instrument.query("*IDN?")).strip()
            instrument.close()
        except Exception:
            identification = ""
        instruments.append(
            GpibInstrumentInfo(
                resource_name=resource_name,
                identification=identification,
            )
        )

    return instruments
