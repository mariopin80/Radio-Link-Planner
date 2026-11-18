from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .i18n import tr


COVERAGE_ANTENNA_DEFAULTS = {
    "tx_pattern": "omni",
    "tx_hpbw": "60",
    "tx_front_to_back": "15",
    "tx_azimuth": "0",
}


@dataclass(frozen=True)
class DirectionalAntenna:
    hpbw_deg: float
    front_to_back_db: float
    azimuth_deg: float

    def __post_init__(self) -> None:
        if not 0.0 < self.hpbw_deg / 2.0 < 180.0:
            raise ValueError(tr("A abertura a −3 dB deve ser maior que 0° e menor que 360°."))
        if not 3.0 <= self.front_to_back_db <= 60.0:
            raise ValueError(tr("A relação frente/costas deve estar entre 3 e 60 dB."))
        if not 0.0 <= self.azimuth_deg <= 360.0:
            raise ValueError(tr("O azimute deve estar entre 0° e 360°."))
        object.__setattr__(self, "azimuth_deg", self.azimuth_deg % 360.0)

    def attenuation_db(self, bearing_deg: float | np.ndarray) -> float | np.ndarray:
        """Two monotonic cosine segments through 0 dB, −3 dB and the rear gain."""
        half_width = self.hpbw_deg / 2.0
        angle = np.abs((bearing_deg - self.azimuth_deg + 180.0) % 360.0 - 180.0)
        inside = np.clip(angle / half_width, 0.0, 1.0)
        outside = np.clip((angle - half_width) / (180.0 - half_width), 0.0, 1.0)
        return (
            3.0 * np.sin(math.pi / 2.0 * inside) ** 2
            + (self.front_to_back_db - 3.0) * np.sin(math.pi / 2.0 * outside) ** 2
        )


def antenna_report_rows(
    peak_gain_dbi: float, pattern: DirectionalAntenna | None
) -> list[tuple[str, str]]:
    rows = [(tr("Antena transmissora"), tr("Direcional" if pattern else "Omnidirecional"))]
    gain_label = tr("Ganho máximo da antena") if pattern else tr("Ganho da antena (dBi)")
    rows.append((gain_label, f"{peak_gain_dbi:g} dBi"))
    if pattern:
        rows.extend([
            (tr("Abertura a −3 dB"), f"{pattern.hpbw_deg:g}°"),
            (tr("Relação frente/costas"), f"{pattern.front_to_back_db:g} dB"),
            (tr("Azimute de apontamento"), f"{pattern.azimuth_deg:g}°"),
        ])
    return rows


ANTENNA_APPROXIMATION_NOTE = (
    "O diagrama horizontal é uma aproximação com dois trechos de cosseno. "
    "Ganho, abertura e frente/costas não determinam o diagrama real. "
    "A célula do transmissor usa o ganho máximo."
)
