from __future__ import annotations

import numpy as np
import pytest

from radiolink.domain import Direction
from radiolink.monte_carlo import simulate
from radiolink.propagation.base import QuantileCurve


def test_monte_carlo_is_reproducible(reference_project) -> None:
    project = reference_project.model_copy(deep=True)
    project.monte_carlo.runs = 5000
    curve = QuantileCurve(
        model_id="test",
        direction=Direction.A_TO_B.value,
        percentiles=np.array([1.0, 50.0, 99.0]),
        loss_db=np.array([160.0, 170.0, 180.0]),
        percentile_meaning="test",
        complete_annual_distribution=True,
    )
    first = simulate(project, Direction.A_TO_B, "test", curve)
    second = simulate(project, Direction.A_TO_B, "test", curve)
    assert first.to_dict() == second.to_dict()
    fm = next(item for item in first.mode_results if item.mode == "FM")
    ssb = next(item for item in first.mode_results if item.mode == "SSB")
    assert ssb.success_probability_percent > fm.success_probability_percent
    assert first.received_power_p05_dbm < first.received_power_p50_dbm
    assert first.received_power_p50_dbm < first.received_power_p95_dbm


def test_fixed_quantile_is_labeled_conditional(reference_project) -> None:
    project = reference_project.model_copy(deep=True)
    project.monte_carlo.runs = 1000
    result = simulate(
        project,
        Direction.A_TO_B,
        "fixed",
        curve=None,
        fixed_loss_db=170.0,
    )
    assert result.temporal_sampling == "conditional_fixed_quantile"
    assert result.warnings
