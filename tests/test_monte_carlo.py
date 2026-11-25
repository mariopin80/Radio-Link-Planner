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


def test_plot_uses_reverse_receiver_and_separates_conditional_success(
    reference_project, tmp_path, monkeypatch,
) -> None:
    matplotlib = pytest.importorskip("matplotlib.figure")
    from radiolink.report import render_monte_carlo_plot

    project = reference_project.model_copy(deep=True)
    project.terminal_a.receiver.threshold_overrides_dbm = {"FM": -104.0}
    project.terminal_b.receiver.threshold_overrides_dbm = {"FM": -115.0}
    project.target_availability_percent = 70.0
    curve = QuantileCurve(
        model_id="itm", direction="b_to_a",
        percentiles=np.array([0.1, 50.0, 99.9]),
        loss_db=np.array([100.0, 101.0, 102.0]),
        percentile_meaning="time_percent_loss_not_exceeded",
        complete_annual_distribution=True,
    )
    reverse = {
        "transmitter": project.terminal_b.name, "receiver": project.terminal_a.name,
        "design_models": [{"model_id": "p1812", "percentile": 50.0}],
        "monte_carlo": [
            simulate(project, Direction.B_TO_A, "itm", curve).to_dict(),
            simulate(project, Direction.B_TO_A, "p1812", None, fixed_loss_db=100.0).to_dict(),
        ],
    }
    figures = []
    monkeypatch.setattr(matplotlib.Figure, "savefig", lambda figure, *a, **k: figures.append(figure))
    render_monte_carlo_plot(
        project, {"directions": {"b_to_a": reverse}}, tmp_path / "reverse.png", direction_id="b_to_a",
    )

    figure, = figures
    figure.canvas.draw()
    histogram, annual, conditional = figure.axes
    threshold_line = histogram.lines[-1]
    assert list(threshold_line.get_xdata()) == [-104.0, -104.0]
    assert annual.get_legend().get_texts()[0].get_text() == "Meta 70%"
    assert conditional.get_legend() is None
    assert conditional.get_xticklabels()[0].get_text() == "P1812 (p50)"
    assert "100%*" in [label.get_text() for label in conditional.texts]
    renderer = figure.canvas.get_renderer()
    for axis in (annual, conditional):
        assert all(label.get_window_extent(renderer).y1 < axis.bbox.y1 for label in axis.texts)
