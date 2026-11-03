"""NI PXI-4461 dynamic signal analyzer (AO sine sweep + AI lock-in)."""

from __future__ import annotations

import math
from dataclasses import dataclass

PXI4461_PRODUCT_TOKEN = "4461"
PXI4461_MAX_SAMPLE_RATE_HZ = 204_800.0
PXI4461_MIN_FREQ_HZ = 500.0
PXI4461_MAX_FREQ_HZ = 99_000.0
PXI4461_AO_PEAK_MAX_V = 10.0
PXI4461_VPP_MIN = 0.01
PXI4461_VPP_MAX = 2.0 * PXI4461_AO_PEAK_MAX_V
PXI4461_DC_OFFSET_MIN_V = -PXI4461_AO_PEAK_MAX_V
PXI4461_DC_OFFSET_MAX_V = PXI4461_AO_PEAK_MAX_V
PXI4461_POINT_COUNT_MIN = 1
PXI4461_POINT_COUNT_MAX = 1000
PXI4461_VOLTAGE_SPIN_MIN = -42.4
PXI4461_VOLTAGE_SPIN_MAX = 42.4
TERMINAL_CONFIG_LABELS: tuple[str, ...] = (
    "Default",
    "RSE",
    "NRSE",
    "Differential",
    "Pseudodifferential",
)


@dataclass(frozen=True)
class Pxi4461DeviceInfo:
    name: str
    product_type: str

    @property
    def display_label(self) -> str:
        if self.product_type and self.product_type != self.name:
            return f"{self.name} ({self.product_type})"
        return self.name


@dataclass(frozen=True)
class ToneMeasurement:
    frequency_hz: float
    magnitude_v: float
    phase_deg: float
    sample_rate_hz: float
    sample_count: int


@dataclass
class DsaHardwareSettings:
    ao_channel: str = ""
    ao_max_v: float = 5.0
    ao_min_v: float = -5.0
    ao_terminal: str = "Default"
    sample_rate_hz: float = 0.0
    ai_stimulus_channel: str = ""
    ai_stimulus_max_v: float = 5.0
    ai_stimulus_min_v: float = -5.0
    ai_stimulus_terminal: str = "Default"
    ai_response_channel: str = ""
    ai_response_max_v: float = 5.0
    ai_response_min_v: float = -5.0
    ai_response_terminal: str = "Default"

    @property
    def ao_device_name(self) -> str:
        if "/" not in self.ao_channel:
            return self.ao_channel
        return self.ao_channel.split("/", 1)[0]


def _load_nidaqmx():
    try:
        import nidaqmx
    except ImportError as exc:
        raise RuntimeError(
            "未安裝 nidaqmx，請執行: pip install nidaqmx\n"
            "並確認本機已安裝 NI-DAQmx 執行環境。"
        ) from exc
    except Exception as exc:
        raise RuntimeError(
            f"無法載入 NI-DAQmx：{exc}\n請確認本機已安裝 NI-DAQmx 執行環境。"
        ) from exc
    return nidaqmx


def list_pxi4461_devices() -> list[Pxi4461DeviceInfo]:
    """Return connected NI devices whose product type or name includes 4461."""
    nidaqmx = _load_nidaqmx()
    system = nidaqmx.system.System.local()
    devices: list[Pxi4461DeviceInfo] = []
    for device in system.devices:
        name = str(device.name)
        product_type = str(getattr(device, "product_type", "") or "")
        haystack = f"{name} {product_type}".upper()
        if PXI4461_PRODUCT_TOKEN in haystack:
            devices.append(Pxi4461DeviceInfo(name=name, product_type=product_type))
    return devices


def list_dsa_ao_channels() -> list[str]:
    """Return AO physical channels on connected NI PXI-4461 devices."""
    return _list_dsa_physical_channels(kind="ao")


def list_dsa_ai_channels() -> list[str]:
    """Return AI physical channels on connected NI PXI-4461 devices."""
    return _list_dsa_physical_channels(kind="ai")


def _list_dsa_physical_channels(*, kind: str) -> list[str]:
    nidaqmx = _load_nidaqmx()
    system = nidaqmx.system.System.local()
    names: list[str] = []
    for info in list_pxi4461_devices():
        device = system.devices[info.name]
        collection = (
            device.ao_physical_chans if kind == "ao" else device.ai_physical_chans
        )
        names.extend(str(name) for name in collection.channel_names)
    return names


def _terminal_config(nidaqmx, label: str):
    mapping = {
        "Default": nidaqmx.constants.TerminalConfiguration.DEFAULT,
        "RSE": nidaqmx.constants.TerminalConfiguration.RSE,
        "NRSE": nidaqmx.constants.TerminalConfiguration.NRSE,
        "Differential": nidaqmx.constants.TerminalConfiguration.DIFF,
        "Pseudodifferential": nidaqmx.constants.TerminalConfiguration.PSEUDO_DIFF,
    }
    return mapping.get(label, nidaqmx.constants.TerminalConfiguration.DEFAULT)


def build_frequency_points(
    start_hz: float, stop_hz: float, point_count: int
) -> list[float]:
    if point_count < PXI4461_POINT_COUNT_MIN:
        raise ValueError(f"步數必須至少為 {PXI4461_POINT_COUNT_MIN}。")
    if point_count > PXI4461_POINT_COUNT_MAX:
        raise ValueError(f"步數不可超過 {PXI4461_POINT_COUNT_MAX}。")
    if start_hz < PXI4461_MIN_FREQ_HZ or stop_hz < PXI4461_MIN_FREQ_HZ:
        raise ValueError(f"頻率必須大於或等於 {PXI4461_MIN_FREQ_HZ:g} Hz。")
    if start_hz > PXI4461_MAX_FREQ_HZ or stop_hz > PXI4461_MAX_FREQ_HZ:
        raise ValueError(f"頻率不可超過 {PXI4461_MAX_FREQ_HZ:g} Hz。")
    if point_count == 1 or math.isclose(start_hz, stop_hz):
        return [float(start_hz)]
    span = stop_hz - start_hz
    return [start_hz + span * index / (point_count - 1) for index in range(point_count)]


def _plan_acquisition(
    frequency_hz: float, sample_rate_hz: float = 0.0
) -> tuple[float, int]:
    samples_per_cycle = 32.0
    if sample_rate_hz > 0:
        sample_rate = min(PXI4461_MAX_SAMPLE_RATE_HZ, float(sample_rate_hz))
    else:
        desired_rate = min(
            PXI4461_MAX_SAMPLE_RATE_HZ,
            max(frequency_hz * samples_per_cycle, 1_000.0),
        )
        sample_rate = min(
            PXI4461_MAX_SAMPLE_RATE_HZ, max(desired_rate, frequency_hz * 8.0)
        )
    min_duration_s = 0.05
    min_cycles = 16
    duration_s = max(min_duration_s, min_cycles / frequency_hz)
    duration_s = min(duration_s, 0.4)
    n_samples = max(256, int(round(sample_rate * duration_s)))
    return sample_rate, n_samples


def _generate_sine(
    frequency_hz: float,
    vpp: float,
    sample_rate: float,
    n_samples: int,
    dc_offset: float = 0.0,
) -> list[float]:
    peak = vpp / 2.0
    two_pi_f = 2.0 * math.pi * frequency_hz
    inv_rate = 1.0 / sample_rate
    return [
        peak * math.sin(two_pi_f * index * inv_rate) + dc_offset
        for index in range(n_samples)
    ]


def analyze_tone(
    samples: list[float], sample_rate: float, frequency_hz: float
) -> tuple[float, float]:
    """Return peak magnitude (V) and phase (deg) of the tone vs generated sine."""
    n = len(samples)
    if n < 8:
        raise ValueError("擷取點數不足，無法分析。")
    samples_per_cycle = max(1, int(round(sample_rate / frequency_hz)))
    skip = min(n // 4, samples_per_cycle)
    if skip >= n - 8:
        skip = 0
    two_pi_f = 2.0 * math.pi * frequency_hz
    inv_rate = 1.0 / sample_rate
    i_acc = 0.0
    q_acc = 0.0
    for index in range(skip, n):
        t = index * inv_rate
        value = float(samples[index])
        i_acc += value * math.sin(two_pi_f * t)
        q_acc += value * math.cos(two_pi_f * t)
    scale = 2.0 / (n - skip)
    in_phase = i_acc * scale
    quadrature = q_acc * scale
    magnitude = math.hypot(in_phase, quadrature)
    phase_deg = math.degrees(math.atan2(quadrature, in_phase))
    return magnitude, phase_deg


def _channel_samples(read_data, channel_count: int, channel_index: int) -> list[float]:
    if channel_count <= 1:
        if isinstance(read_data, (list, tuple)) and read_data and isinstance(
            read_data[0], (list, tuple)
        ):
            return [float(value) for value in read_data[0]]
        return [float(value) for value in read_data]
    channel_row = read_data[channel_index]
    return [float(value) for value in channel_row]


def _wrap_phase_deg(phase_deg: float) -> float:
    wrapped = (phase_deg + 180.0) % 360.0 - 180.0
    if wrapped <= -180.0:
        return 180.0
    return wrapped


def measure_tone(
    settings: DsaHardwareSettings,
    frequency_hz: float,
    vpp: float,
    dc_offset: float = 0.0,
) -> ToneMeasurement:
    """Output a sine on AO and lock-in stimulus / response AI at ``frequency_hz``."""
    if not settings.ao_channel:
        raise ValueError("請先在設定中選擇 AO excitation channel。")
    if not settings.ai_response_channel:
        raise ValueError("請先在設定中選擇 AI response channel。")
    if vpp < PXI4461_VPP_MIN or vpp > PXI4461_VPP_MAX:
        raise ValueError(
            f"信號 Vpp 必須介於 {PXI4461_VPP_MIN:g} 與 {PXI4461_VPP_MAX:g} V。"
        )
    if dc_offset < PXI4461_DC_OFFSET_MIN_V or dc_offset > PXI4461_DC_OFFSET_MAX_V:
        raise ValueError(
            f"DC Offset 必須介於 {PXI4461_DC_OFFSET_MIN_V:g} 與 "
            f"{PXI4461_DC_OFFSET_MAX_V:g} V。"
        )
    peak = vpp / 2.0
    ao_limit = min(abs(settings.ao_max_v), abs(settings.ao_min_v), PXI4461_AO_PEAK_MAX_V)
    if peak + abs(dc_offset) > ao_limit + 1e-12:
        raise ValueError(f"Vpp/2 加上 |DC Offset| 不可超過 {ao_limit:g} V。")

    nidaqmx = _load_nidaqmx()
    acquisition_type = nidaqmx.constants.AcquisitionType
    device_name = settings.ao_device_name
    desired_rate, n_samples = _plan_acquisition(
        frequency_hz, settings.sample_rate_hz
    )
    timeout_s = max(5.0, n_samples / max(desired_rate, 1.0) + 2.0)

    stimulus_channel = settings.ai_stimulus_channel
    response_channel = settings.ai_response_channel
    capture_stimulus = bool(
        stimulus_channel and stimulus_channel != response_channel
    )
    ai_channels = [response_channel]
    if capture_stimulus:
        ai_channels.insert(0, stimulus_channel)

    with nidaqmx.Task() as ao_task, nidaqmx.Task() as ai_task:
        ao_chan = ao_task.ao_channels.add_ao_voltage_chan(
            settings.ao_channel,
            min_val=settings.ao_min_v,
            max_val=settings.ao_max_v,
        )
        try:
            ao_chan.ao_term_cfg = _terminal_config(nidaqmx, settings.ao_terminal)
        except Exception:
            pass

        if capture_stimulus:
            ai_task.ai_channels.add_ai_voltage_chan(
                stimulus_channel,
                terminal_config=_terminal_config(
                    nidaqmx, settings.ai_stimulus_terminal
                ),
                min_val=settings.ai_stimulus_min_v,
                max_val=settings.ai_stimulus_max_v,
            )
        ai_task.ai_channels.add_ai_voltage_chan(
            response_channel,
            terminal_config=_terminal_config(
                nidaqmx, settings.ai_response_terminal
            ),
            min_val=settings.ai_response_min_v,
            max_val=settings.ai_response_max_v,
        )
        ao_task.timing.cfg_samp_clk_timing(
            rate=desired_rate,
            sample_mode=acquisition_type.FINITE,
            samps_per_chan=n_samples,
        )
        sample_rate = float(ao_task.timing.samp_clk_rate)
        ai_task.timing.cfg_samp_clk_timing(
            rate=sample_rate,
            source=f"/{device_name}/ao/SampleClock",
            sample_mode=acquisition_type.FINITE,
            samps_per_chan=n_samples,
        )
        waveform = _generate_sine(
            frequency_hz, vpp, sample_rate, n_samples, dc_offset
        )
        ao_task.write(waveform, auto_start=False)
        ai_task.start()
        ao_task.start()
        read_data = ai_task.read(
            number_of_samples_per_channel=n_samples,
            timeout=timeout_s,
        )
        ao_task.wait_until_done(timeout=timeout_s)

    channel_count = len(ai_channels)
    if capture_stimulus:
        stimulus_samples = _channel_samples(read_data, channel_count, 0)
        response_samples = _channel_samples(read_data, channel_count, 1)
        stim_mag, stim_phase = analyze_tone(
            stimulus_samples, sample_rate, frequency_hz
        )
        resp_mag, resp_phase = analyze_tone(
            response_samples, sample_rate, frequency_hz
        )
        magnitude = resp_mag / stim_mag if stim_mag > 1e-12 else resp_mag
        phase_deg = _wrap_phase_deg(resp_phase - stim_phase)
        sample_count = len(response_samples)
    else:
        response_samples = _channel_samples(read_data, 1, 0)
        magnitude, phase_deg = analyze_tone(
            response_samples, sample_rate, frequency_hz
        )
        sample_count = len(response_samples)

    return ToneMeasurement(
        frequency_hz=frequency_hz,
        magnitude_v=magnitude,
        phase_deg=phase_deg,
        sample_rate_hz=sample_rate,
        sample_count=sample_count,
    )
