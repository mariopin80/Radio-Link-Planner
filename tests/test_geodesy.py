from __future__ import annotations

import pytest

from radiolink.geodesy import great_circle_distance_m, initial_bearing_deg


def test_reference_distance_and_bearing() -> None:
    distance_m = great_circle_distance_m(
        -23.05570436,
        -45.93130177,
        -23.27871226,
        -47.67718038,
    )
    assert distance_m / 1000.0 == pytest.approx(180.191525, abs=0.0001)
    assert initial_bearing_deg(
        -23.05570436,
        -45.93130177,
        -23.27871226,
        -47.67718038,
    ) == pytest.approx(261.75, abs=0.02)
