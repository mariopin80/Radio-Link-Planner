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


def test_unknown_tails_are_not_reported_as_certain_annual_success(reference_project):
    from radiolink.domain import UncertaintySpec
    from radiolink.monte_carlo import describe_simulated_success, percentage_text

    project = reference_project.model_copy(deep=True)
    project.monte_carlo.uncertainty = UncertaintySpec(
        **dict.fromkeys(UncertaintySpec.model_fields, 0.0),
    )
    curve = QuantileCurve(
        model_id="p2001", direction=Direction.A_TO_B.value,
        percentiles=np.array([1.0, 50.0, 99.0]),
        loss_db=np.array([1.0, 2.0, 3.0]),
        percentile_meaning="time_percent_loss_not_exceeded",
        complete_annual_distribution=True,
    )
    simulation = simulate(project, Direction.A_TO_B, "p2001", curve)
    assert simulation.temporal_sampling == "conditional_percentile_interval"
    assert simulation.percentile_interval == (1.0, 99.0)
    fm = next(row for row in simulation.mode_results if row.mode == "FM")
    assert fm.success_probability_percent == 100.0
    assert fm.annual_availability_bounds_percent == (98.0, 100.0)
    assert "98% a 100%" in describe_simulated_success(simulation.to_dict(), "FM", 99.5)
    assert percentage_text(99.99999) == "99.99999"
