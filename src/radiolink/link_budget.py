from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from .domain import Direction, Project
from .modes import threshold_dbm


def watts_to_dbm(power_w: float) -> float:
    if power_w <= 0.0:
        raise ValueError("power must be positive")
    return 10.0 * math.log10(power_w * 1000.0)


@dataclass(frozen=True)
class LinkBudget:
    direction: str
    model_id: str
    percentile: float | None
    tx_power_dbm: float
    tx_antenna_gain_dbi: float
    tx_line_loss_db: float
    path_loss_db: float
    rx_antenna_gain_dbi: float
    rx_line_loss_db: float
    received_power_dbm: float
    mode: str
    receiver_threshold_dbm: float
    fade_margin_db: float

    def to_dict(self) -> dict:
        return asdict(self)


def calculate_link_budget(
    project: Project,
    direction: Direction,
    model_id: str,
    path_loss_db: float,
    percentile: float | None,
    mode_id: str | None = None,
) -> LinkBudget:
    transmitter, receiver = direction.terminals(project)
    mode = (mode_id or project.primary_mode).upper()
    threshold, _ = threshold_dbm(receiver.receiver, mode)
    tx_power_dbm = watts_to_dbm(transmitter.tx_power_w)
    received = (
        tx_power_dbm
        + transmitter.antenna_gain_dbi
        - transmitter.line_loss_db
        - path_loss_db
        + receiver.antenna_gain_dbi
        - receiver.line_loss_db
    )
    return LinkBudget(
        direction=direction.value,
        model_id=model_id,
        percentile=percentile,
        tx_power_dbm=tx_power_dbm,
        tx_antenna_gain_dbi=transmitter.antenna_gain_dbi,
        tx_line_loss_db=transmitter.line_loss_db,
        path_loss_db=path_loss_db,
        rx_antenna_gain_dbi=receiver.antenna_gain_dbi,
        rx_line_loss_db=receiver.line_loss_db,
        received_power_dbm=received,
        mode=mode,
        receiver_threshold_dbm=threshold,
        fade_margin_db=received - threshold,
    )
