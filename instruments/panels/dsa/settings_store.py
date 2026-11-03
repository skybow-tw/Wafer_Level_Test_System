"""Read/write DSA hardware and signal settings from a TOML file."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
import tomllib

from instruments.pxi4461 import (
    PXI4461_DC_OFFSET_MAX_V,
    PXI4461_DC_OFFSET_MIN_V,
    PXI4461_MAX_FREQ_HZ,
    PXI4461_MIN_FREQ_HZ,
    PXI4461_POINT_COUNT_MAX,
    PXI4461_POINT_COUNT_MIN,
    PXI4461_VPP_MAX,
    PXI4461_VPP_MIN,
    DsaHardwareSettings,
)


@dataclass
class DsaSignalSettings:
    """Last-used Signal Settings panel values."""

    freq_start_hz: int = 500
    freq_stop_hz: int = 8_000
    point_count: int = 101
    vpp: float = 1.0
    dc_offset_v: float = 0.0
    save_to_file: bool = True


def default_settings_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "Settings_DSA.toml"
    return Path(__file__).with_name("Settings_DSA.toml")


def _bundled_settings_path() -> Path:
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        bundled = Path(meipass) / "instruments" / "panels" / "dsa" / "Settings_DSA.toml"
        if bundled.is_file():
            return bundled
    return Path(__file__).with_name("Settings_DSA.toml")


def _resolve_settings_path(path: Path | None = None) -> Path:
    settings_path = path or default_settings_path()
    if settings_path.exists():
        return settings_path
    bundled = _bundled_settings_path()
    if bundled.exists() and bundled != settings_path:
        return bundled
    return settings_path


def _read_toml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    return data if isinstance(data, dict) else {}


def load_dsa_settings(path: Path | None = None) -> DsaHardwareSettings:
    settings_path = _resolve_settings_path(path)
    settings = DsaHardwareSettings()
    if not settings_path.exists():
        return settings

    data = _read_toml(settings_path)
    ao = data.get("ao_source", {})
    stim = data.get("ai_stimulus", {})
    resp = data.get("ai_response", {})
    sampling = data.get("sampling", {})

    settings.ao_channel = _as_str(ao.get("channel"), settings.ao_channel)
    settings.ao_max_v = _as_float(ao.get("max_v"), settings.ao_max_v)
    settings.ao_min_v = _as_float(ao.get("min_v"), settings.ao_min_v)
    settings.ao_terminal = _as_str(ao.get("terminal"), settings.ao_terminal)
    settings.ai_stimulus_channel = _as_str(
        stim.get("channel"), settings.ai_stimulus_channel
    )
    settings.ai_stimulus_max_v = _as_float(stim.get("max_v"), settings.ai_stimulus_max_v)
    settings.ai_stimulus_min_v = _as_float(stim.get("min_v"), settings.ai_stimulus_min_v)
    settings.ai_stimulus_terminal = _as_str(
        stim.get("terminal"), settings.ai_stimulus_terminal
    )
    settings.ai_response_channel = _as_str(
        resp.get("channel"), settings.ai_response_channel
    )
    settings.ai_response_max_v = _as_float(resp.get("max_v"), settings.ai_response_max_v)
    settings.ai_response_min_v = _as_float(resp.get("min_v"), settings.ai_response_min_v)
    settings.ai_response_terminal = _as_str(
        resp.get("terminal"), settings.ai_response_terminal
    )
    settings.sample_rate_hz = _as_float(
        sampling.get("frequency_hz"), settings.sample_rate_hz
    )
    return settings


def load_dsa_signal_settings(path: Path | None = None) -> DsaSignalSettings:
    settings_path = _resolve_settings_path(path)
    settings = DsaSignalSettings()
    if not settings_path.exists():
        return settings

    data = _read_toml(settings_path)
    signal = data.get("signal", {})
    if not isinstance(signal, dict):
        return settings

    start_hz = _as_int(signal.get("freq_start_hz"), settings.freq_start_hz)
    stop_hz = _as_int(signal.get("freq_stop_hz"), settings.freq_stop_hz)
    point_count = _as_int(signal.get("point_count"), settings.point_count)
    vpp = _as_float(signal.get("vpp"), settings.vpp)
    dc_offset = _as_float(signal.get("dc_offset_v"), settings.dc_offset_v)
    save_to_file = _as_bool(signal.get("save_to_file"), settings.save_to_file)

    return DsaSignalSettings(
        freq_start_hz=_clamp_int(
            start_hz, int(PXI4461_MIN_FREQ_HZ), int(PXI4461_MAX_FREQ_HZ)
        ),
        freq_stop_hz=_clamp_int(
            stop_hz, int(PXI4461_MIN_FREQ_HZ), int(PXI4461_MAX_FREQ_HZ)
        ),
        point_count=_clamp_int(
            point_count, PXI4461_POINT_COUNT_MIN, PXI4461_POINT_COUNT_MAX
        ),
        vpp=_clamp_float(vpp, PXI4461_VPP_MIN, PXI4461_VPP_MAX),
        dc_offset_v=_clamp_float(
            dc_offset, PXI4461_DC_OFFSET_MIN_V, PXI4461_DC_OFFSET_MAX_V
        ),
        save_to_file=save_to_file,
    )


def save_dsa_settings(
    settings: DsaHardwareSettings, path: Path | None = None
) -> None:
    settings_path = path or default_settings_path()
    signal = load_dsa_signal_settings(settings_path)
    settings_path.write_text(
        _format_toml(settings, signal), encoding="utf-8"
    )


def save_dsa_signal_settings(
    signal: DsaSignalSettings, path: Path | None = None
) -> None:
    settings_path = path or default_settings_path()
    hardware = load_dsa_settings(settings_path)
    settings_path.write_text(
        _format_toml(hardware, signal), encoding="utf-8"
    )


def _format_toml(
    settings: DsaHardwareSettings, signal: DsaSignalSettings | None = None
) -> str:
    signal = signal or DsaSignalSettings()
    return (
        "# DSA hardware and signal settings\n\n"
        "[sampling]\n"
        f"frequency_hz = {_format_float(settings.sample_rate_hz)}\n\n"
        "[ao_source]\n"
        f"channel = {_format_string(settings.ao_channel)}\n"
        f"max_v = {_format_float(settings.ao_max_v)}\n"
        f"min_v = {_format_float(settings.ao_min_v)}\n"
        f"terminal = {_format_string(settings.ao_terminal)}\n\n"
        "[ai_stimulus]\n"
        f"channel = {_format_string(settings.ai_stimulus_channel)}\n"
        f"max_v = {_format_float(settings.ai_stimulus_max_v)}\n"
        f"min_v = {_format_float(settings.ai_stimulus_min_v)}\n"
        f"terminal = {_format_string(settings.ai_stimulus_terminal)}\n\n"
        "[ai_response]\n"
        f"channel = {_format_string(settings.ai_response_channel)}\n"
        f"max_v = {_format_float(settings.ai_response_max_v)}\n"
        f"min_v = {_format_float(settings.ai_response_min_v)}\n"
        f"terminal = {_format_string(settings.ai_response_terminal)}\n\n"
        "[signal]\n"
        f"freq_start_hz = {int(signal.freq_start_hz)}\n"
        f"freq_stop_hz = {int(signal.freq_stop_hz)}\n"
        f"point_count = {int(signal.point_count)}\n"
        f"vpp = {_format_float(signal.vpp)}\n"
        f"dc_offset_v = {_format_float(signal.dc_offset_v)}\n"
        f"save_to_file = {'true' if signal.save_to_file else 'false'}\n"
    )


def _format_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _format_float(value: float) -> str:
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    if text in {"", "-"}:
        return "0.0"
    return text


def _as_str(value: object | None, fallback: str) -> str:
    if value is None:
        return fallback
    return str(value)


def _as_float(value: object | None, fallback: float) -> float:
    if value is None or value == "":
        return fallback
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _as_int(value: object | None, fallback: int) -> int:
    if value is None or value == "":
        return fallback
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return fallback


def _as_bool(value: object | None, fallback: bool) -> bool:
    if value is None:
        return fallback
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return fallback


def _clamp_int(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def _clamp_float(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
