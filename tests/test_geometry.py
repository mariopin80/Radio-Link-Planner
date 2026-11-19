from __future__ import annotations

import pytest
import numpy as np

from radiolink.geometry import calculate_geometry
from radiolink.terrain import matches_terminal_coordinates


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


def test_terrain_reuse_requires_matching_terminal_coordinates(reference_project, reference_profile):
    a, b = reference_project.terminal_a, reference_project.terminal_b
    original = (a.latitude_deg, a.longitude_deg, b.latitude_deg, b.longitude_deg)
    assert matches_terminal_coordinates(reference_profile, *original)

    # Actual v0.6.0 regression: the 180.19 km example was reused for a 95 km link.
    assert not matches_terminal_coordinates(
        reference_profile, -23.27873714, -47.67702601, -23.45842360, -46.76704776,
    )
    assert not matches_terminal_coordinates(reference_profile.reverse(), *original)
    changed_distances = reference_profile.distance_km * 1.01
    assert not matches_terminal_coordinates(
        reference_profile._replace(distance_km=changed_distances), *original,
    )


def test_selected_fresnel_compares_only_interior_samples(reference_project, reference_profile):
    project = reference_project.model_copy(deep=True)
    default, _ = calculate_geometry(project, reference_profile)
    project.environment.effective_earth_k = 1.0
    project.environment.fresnel_percent = 0.0
    direct, arrays = calculate_geometry(project, reference_profile)
    assert direct.maximum_earth_bulge_m > default.maximum_earth_bulge_m
    assert direct.fresnel_obstructed_percent == pytest.approx(
        100.0 * np.mean(arrays.clearance_m[1:-1] < 0.0)
    )
    project.environment.fresnel_percent = 80.0
    fresnel, _ = calculate_geometry(project, reference_profile)
    assert fresnel.fresnel_percent == 80.0
    assert fresnel.fresnel_obstructed_percent > direct.fresnel_obstructed_percent
