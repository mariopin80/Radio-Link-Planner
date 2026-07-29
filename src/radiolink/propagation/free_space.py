from __future__ import annotations

import math


def free_space_loss_db(distance_km: float, frequency_mhz: float) -> float:
    if distance_km <= 0.0:
        raise ValueError("distance must be positive")
    if frequency_mhz <= 0.0:
        raise ValueError("frequency must be positive")
    return 32.447783 + 20.0 * math.log10(distance_km) + 20.0 * math.log10(
        frequency_mhz
    )
