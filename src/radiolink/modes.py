from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from .domain import ReceiverSpec


THERMAL_NOISE_DENSITY_DBM_HZ = -174.0


@dataclass(frozen=True)
class ModeProfile:
    mode_id: str
    label: str
    bandwidth_hz: float
    required_snr_db: float
    notes: str


MODE_PROFILES: dict[str, ModeProfile] = {
    "FM": ModeProfile(
        mode_id="FM",
        label="FM estreito / 12 dB SINAD",
        bandwidth_hz=12_500.0,
        required_snr_db=12.0,
        notes="preset editável; prefira o limiar medido do rádio",
    ),
    "SSB": ModeProfile(
        mode_id="SSB",
        label="SSB voz",
        bandwidth_hz=2_400.0,
        required_snr_db=6.0,
        notes="nível aproximado para inteligibilidade",
    ),
    "CW": ModeProfile(
        mode_id="CW",
        label="CW 500 Hz",
        bandwidth_hz=500.0,
        required_snr_db=-3.0,
        notes="operador e filtro influenciam fortemente",
    ),
    "APRS": ModeProfile(
        mode_id="APRS",
        label="APRS 1200 AFSK",
        bandwidth_hz=12_000.0,
        required_snr_db=9.0,
        notes="preset inicial; modem e desvio de áudio importam",
    ),
    "LORA_SF7": ModeProfile(
        mode_id="LORA_SF7",
        label="LoRa 125 kHz SF7",
        bandwidth_hz=125_000.0,
        required_snr_db=-7.5,
        notes="depende do chipset e da taxa de código",
    ),
    "LORA_SF12": ModeProfile(
        mode_id="LORA_SF12",
        label="LoRa 125 kHz SF12",
        bandwidth_hz=125_000.0,
        required_snr_db=-20.0,
        notes="depende do chipset, taxa de código e tempo no ar",
    ),
}


def threshold_dbm(receiver: ReceiverSpec, mode_id: str) -> tuple[float, dict]:
    normalized = mode_id.upper()
    if normalized in receiver.threshold_overrides_dbm:
        value = float(receiver.threshold_overrides_dbm[normalized])
        return value, {
            "mode_id": normalized,
            "threshold_dbm": value,
            "source": "receiver_override",
        }
    if normalized not in MODE_PROFILES:
        raise KeyError(f"unknown mode profile: {mode_id}")
    mode = MODE_PROFILES[normalized]
    value = (
        THERMAL_NOISE_DENSITY_DBM_HZ
        + 10.0 * math.log10(mode.bandwidth_hz)
        + receiver.noise_figure_db
        + receiver.external_noise_db
        + mode.required_snr_db
    )
    details = asdict(mode)
    details.update(
        {
            "threshold_dbm": value,
            "source": "thermal_noise_budget",
            "noise_figure_db": receiver.noise_figure_db,
            "external_noise_db": receiver.external_noise_db,
        }
    )
    return value, details


def all_mode_thresholds(receiver: ReceiverSpec) -> dict[str, dict]:
    return {
        mode_id: threshold_dbm(receiver, mode_id)[1]
        for mode_id in MODE_PROFILES
    }
