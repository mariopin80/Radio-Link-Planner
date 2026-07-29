from __future__ import annotations

import pytest

from radiolink.geometry import calculate_geometry


def test_reference_geometry(reference_project, reference_profile) -> None:
    result, arrays = calculate_geometry(reference_project, reference_profile)
    assert result.profile_distance_km == pytest.approx(180.191525, abs=1e-6)
    assert result.maximum_earth_bulge_m == pytest.approx(477.7842, abs=0.01)
    assert result.maximum_fresnel_radius_m == pytest.approx(304.1383, abs=0.01)
    assert result.worst_obstruction_m == pytest.approx(558.7807, abs=0.02)
    assert result.worst_obstruction_distance_km == pytest.approx(
        40.8926, abs=0.001
    )
    assert result.terrain_above_direct_ray_percent == pytest.approx(
        81.6547, abs=0.01
    )
    assert result.fresnel_60_obstructed_percent == pytest.approx(
        90.1781, abs=0.01
    )
    assert len(arrays.distance_m) == 6007


def test_reverse_profile_is_reciprocal(reference_profile) -> None:
    reverse = reference_profile.reverse()
    assert reverse.total_distance_km == pytest.approx(
        reference_profile.total_distance_km
    )
    assert reverse.elevation_m[0] == reference_profile.elevation_m[-1]
    assert reverse.elevation_m[-1] == reference_profile.elevation_m[0]
