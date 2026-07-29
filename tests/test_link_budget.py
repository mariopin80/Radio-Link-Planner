from __future__ import annotations

import pytest

from radiolink.domain import Direction
from radiolink.link_budget import calculate_link_budget, watts_to_dbm


def test_radio_mobile_budget(reference_project) -> None:
    budget = calculate_link_budget(
        reference_project,
        Direction.A_TO_B,
        "radio_mobile",
        path_loss_db=169.73,
        percentile=70.0,
    )
    assert watts_to_dbm(45.0) == pytest.approx(46.5321, abs=0.001)
    assert budget.received_power_dbm == pytest.approx(-115.1979, abs=0.001)
    assert budget.fade_margin_db == pytest.approx(5.7821, abs=0.001)
