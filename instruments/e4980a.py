"""Agilent / Keysight E4980A precision LCR meter driver."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pyvisa


# Display label -> SCPI :FUNCtion:IMPedance:TYPE value
E4980A_IMPEDANCE_FUNCTIONS: dict[str, str] = {
    "Cp-D": "CPD",
    "Cp-Q": "CPQ",
    "Cp-G": "CPG",
    "Cp-Rp": "CPRP",
    "Cp-Z": "CPZ",
    "Cs-D": "CSD",
    "Cs-Q": "CSQ",
    "Cs-Rs": "CSRS",
    "Cs-Z": "CSZ",
    "Lp-D": "LPD",
    "Lp-G": "LPG",
    "Lp-Rp": "LPRP",
    "Lp-Z": "LPZ",
    "Ls-D": "LSD",
    "Ls-G": "LSG",
    "Ls-Q": "LSQ",
    "Ls-Rs": "LSRS",
    "Ls-Z": "LSZ",
    "R-X": "RX",
    "Z-θ": "ZTR",
    "Z-D": "ZTD",
    "Y-θ": "YTR",
    "Y-D": "YTD",
    "G-B": "GBL",
}

E4980A_VOLTAGE_MIN_V = 0.005
E4980A_VOLTAGE_MAX_V = 2.0
E4980A_FREQ_MIN_HZ = 20.0
E4980A_FREQ_MAX_HZ = 2_000_000.0
E4980A_DC_OFFSET_MIN_V = -40.0
E4980A_DC_OFFSET_MAX_V = 40.0
E4980A_CABLE_LENGTHS_M = (0, 1, 2, 4)

_IMPEDANCE_PARAM_UNITS: dict[str, str] = {
    "Cp": "F",
    "Cs": "F",
    "Lp": "H",
    "Ls": "H",
    "R": "ohm",
    "Z": "ohm",
    "Y": "S",
    "G": "S",
    "D": "",
    "Q": "",
    "Rp": "ohm",
    "Rs": "ohm",
    "X": "ohm",
    "B": "S",
    "θ": "deg",
}


_IMPEDANCE_PARAM_DISPLAY: dict[str, str] = {
    "θ": "theta",
}


def impedance_function_csv_headers(function_label: str) -> tuple[str, str]:
    """Return CSV / axis column headers for primary and secondary parameters."""
    if function_label in ("Cp-Rp", "Cs-Rs"):
        return "電容(fF)", "電阻 (Ω)"
    if "-" not in function_label:
        raise ValueError(f"不支援的量測功能: {function_label}")
    primary, secondary = function_label.split("-", 1)

    def _header(param: str) -> str:
        display = _IMPEDANCE_PARAM_DISPLAY.get(param, param)
        unit = _IMPEDANCE_PARAM_UNITS.get(param, "")
        return f"{display}({unit})" if unit else display

    return _header(primary), _header(secondary)


def impedance_function_bias_csv_header(function_label: str) -> str:
    """Return the DC-bias / X-axis column header used in die CSV files."""
    if function_label in ("Cp-Rp", "Cs-Rs"):
        return "DC偏壓(V)"
    return "DC_Offset_V"


def impedance_function_saves_capacitance_as_ff(function_label: str) -> bool:
    """True when Capacitance is written to CSV in fF (×10^15 from F)."""
    return function_label in ("Cp-Rp", "Cs-Rs")


class AgilentE4980A:
    """Minimal SCPI driver for common E4980A settings."""

    def __init__(self, resource_name: str) -> None:
        self._resource_name = resource_name
        self._instrument: pyvisa.resources.MessageBasedResource | None = None

    @property
    def resource_name(self) -> str:
        return self._resource_name

    @property
    def is_connected(self) -> bool:
        return self._instrument is not None

    def connect(self) -> str:
        import pyvisa

        if self._instrument is not None:
            self.disconnect()

        rm = pyvisa.ResourceManager()
        self._instrument = rm.open_resource(self._resource_name)
        # Allow time for :INITiate + *OPC? under MED/LONG aperture.
        self._instrument.timeout = 30_000
        return str(self._instrument.query("*IDN?")).strip()

    def disconnect(self) -> None:
        if self._instrument is not None:
            self._instrument.close()
            self._instrument = None

    def set_impedance_function(self, function_label: str) -> None:
        scpi_type = E4980A_IMPEDANCE_FUNCTIONS.get(function_label)
        if scpi_type is None:
            raise ValueError(f"不支援的量測功能: {function_label}")
        self._write(f":FUNCtion:IMPedance:TYPE {scpi_type}")

    def set_voltage_level(self, volts: float) -> None:
        if not E4980A_VOLTAGE_MIN_V <= volts <= E4980A_VOLTAGE_MAX_V:
            raise ValueError(
                f"信號振福需介於 {E4980A_VOLTAGE_MIN_V} V 與 {E4980A_VOLTAGE_MAX_V} V"
            )
        self._write(f":VOLTage:LEVel {volts}")

    def set_frequency(self, hz: float) -> None:
        if not E4980A_FREQ_MIN_HZ <= hz <= E4980A_FREQ_MAX_HZ:
            raise ValueError(
                f"頻率需介於 {E4980A_FREQ_MIN_HZ} Hz 與 {E4980A_FREQ_MAX_HZ} Hz"
            )
        self._write(f":FREQuency {hz}")

    def set_dc_offset(self, volts: float) -> None:
        if not E4980A_DC_OFFSET_MIN_V <= volts <= E4980A_DC_OFFSET_MAX_V:
            raise ValueError(
                f"DC offset 需介於 {E4980A_DC_OFFSET_MIN_V} V 與 {E4980A_DC_OFFSET_MAX_V} V"
            )
        self._write(f":BIAS:VOLTage {volts}")
        if volts == 0:
            self._write(":BIAS:STATe OFF")
        else:
            self._write(":BIAS:STATe ON")

    def apply_settings(
        self,
        function_label: str,
        voltage_v: float,
        frequency_hz: float,
        dc_offset_v: float | None = None,
    ) -> None:
        self.set_impedance_function(function_label)
        self.set_voltage_level(voltage_v)
        self.set_frequency(frequency_hz)
        if dc_offset_v is not None:
            self.set_dc_offset(dc_offset_v)

    def set_cable_length(self, length_m: int) -> None:
        if length_m not in E4980A_CABLE_LENGTHS_M:
            allowed = ", ".join(str(value) for value in E4980A_CABLE_LENGTHS_M)
            raise ValueError(f"電纜長度需為 {allowed} m")
        self._write(f":CORRection:LENGth {length_m}")

    def execute_open_correction(self) -> None:
        """Execute OPEN correction and enable OPEN correction state."""
        self._write(":CORRection:OPEN")
        self._query("*OPC?")
        self._write(":CORRection:OPEN:STATe ON")

    def execute_short_correction(self) -> None:
        """Execute SHORT correction and enable SHORT correction state."""
        self._write(":CORRection:SHORt")
        self._query("*OPC?")
        self._write(":CORRection:SHORt:STATe ON")

    def initiate_measurement(self) -> None:
        """Start a new measurement cycle and wait until it completes."""
        self._write(":INITiate")
        self._query("*OPC?")

    def measure_impedance_values(self) -> tuple[float, float]:
        """Trigger a fresh measurement with :INITiate, then read :FETCh?.

        E4980A :FETCh? returns ``<primary>,<secondary>[,status]``.
        Only the first two numeric fields are used as the XY pair values.
        """
        self.initiate_measurement()
        response = self.fetch_raw()
        return self.parse_fetch_impedance_pair(response)

    @staticmethod
    def parse_fetch_impedance_pair(response: str) -> tuple[float, float]:
        """Parse :FETCh? text into (primary, secondary)."""
        parts = [part.strip() for part in response.split(",") if part.strip() != ""]
        if len(parts) < 2:
            raise RuntimeError(f"無法解析量測結果（少於 2 個欄位）: {response}")
        try:
            primary = float(parts[0])
            secondary = float(parts[1])
        except ValueError as exc:
            raise RuntimeError(f"無法解析量測結果: {response}") from exc
        return primary, secondary

    def fetch_raw(self) -> str:
        """Send :FETCh? and return the raw instrument response."""
        return self._query(":FETCh?")

    def query_trigger_source(self) -> str:
        """Send :TRIG:SOUR? and return Continuous/Hold/Bus source."""
        return self._query(":TRIGger:SOURce?")

    def measure_primary_value(self) -> float:
        return self.measure_impedance_values()[0]

    def _query(self, command: str) -> str:
        if self._instrument is None:
            raise RuntimeError("尚未連線至 E4980A")
        return str(self._instrument.query(command)).strip()

    def _write(self, command: str) -> None:
        if self._instrument is None:
            raise RuntimeError("尚未連線至 E4980A")
        self._instrument.write(command)
