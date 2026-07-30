from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from radiolink.coverage import (
    COVERAGE_RESOLUTION_M,
    CoverageRequest,
    RadialCoverage,
    angular_refinement_candidates,
    coverage_resolution_m,
    interpolate_radials_to_grid,
    run_coverage_analysis,
)
from radiolink.geodesy import destination_point, great_circle_distance_m
from radiolink.map_picker import build_picker_html


def _request(tmp_path: Path, **updates) -> CoverageRequest:
    values = {
        "name": "Cobertura de teste",
        "latitude_deg": -23.0,
        "longitude_deg": -47.0,
        "frequency_mhz": 146.0,
        "polarization": "vertical",
        "mode": "FM",
        "radius_km": 50,
        "transmitter_height_m": 30.0,
        "transmitter_gain_dbi": 6.0,
        "transmitter_line_loss_db": 1.0,
        "transmitter_power_w": 50.0,
        "receiver_height_m": 2.0,
        "receiver_gain_dbi": 2.0,
        "receiver_line_loss_db": 1.0,
        "receiver_threshold_dbm": -120.0,
        "output_directory": tmp_path,
        "time_percentage": 50.0,
    }
    values.update(updates)
    return CoverageRequest(**values)


def _radial(
    bearing: float,
    margin: list[float],
    elevation: list[float] | None = None,
) -> RadialCoverage:
    count = len(margin)
    distance = np.linspace(0.0, 1000.0, count)
    return RadialCoverage(
        bearing_deg=bearing,
        distance_m=distance,
        latitude_deg=np.zeros(count),
        longitude_deg=np.zeros(count),
        elevation_m=np.asarray(elevation or [0.0] * count),
        margin_db=np.asarray(margin, dtype=float),
        evaluated_point_count=count,
    )


def test_radius_resolution_policy_matches_product_scope() -> None:
    assert COVERAGE_RESOLUTION_M == {
        50: 50,
        100: 100,
        200: 100,
        300: 200,
        400: 200,
        500: 200,
    }
    assert coverage_resolution_m(200) == 100
    with pytest.raises(ValueError, match="unsupported"):
        coverage_resolution_m(250)


def test_coverage_request_rejects_invalid_time_percentage(tmp_path: Path) -> None:
    request = _request(tmp_path, time_percentage=70.0)
    with pytest.raises(ValueError, match="entre 1 e 50"):
        request.validate()


def test_destination_point_preserves_requested_distance() -> None:
    latitude, longitude = destination_point(-23.0, -47.0, 90.0, 50_000.0)
    distance = great_circle_distance_m(-23.0, -47.0, latitude, longitude)
    assert distance == pytest.approx(50_000.0, abs=0.01)


def test_angular_refinement_detects_a_coverage_boundary_jump() -> None:
    left = _radial(0.0, [12.0, 8.0, 4.0])
    right = _radial(10.0, [12.0, -4.0, -8.0])
    candidates = angular_refinement_candidates(
        (left, right),
        minimum_step_deg=0.625,
    )
    bearings = {item[0] for item in candidates}
    assert 5.0 in bearings
    assert 185.0 in bearings


def test_polar_interpolation_builds_a_circular_raster(tmp_path: Path) -> None:
    radials = tuple(
        _radial(bearing, [0.0, 10.0]) for bearing in (0.0, 90.0, 180.0, 270.0)
    )
    grid, metadata = interpolate_radials_to_grid(
        radials,
        radius_km=1,
        resolution_m=1000,
        output_path=tmp_path / "grid.npy",
    )
    assert grid.shape == (3, 3)
    assert grid[1, 1] == pytest.approx(0.0)
    assert grid[0, 1] == pytest.approx(10.0)
    assert np.isnan(grid[0, 0])
    assert metadata["resolution_m"] == 1000


def test_map_picker_exposes_click_confirmation() -> None:
    page = build_picker_html(
        title="Escolher transmissor",
        initial_latitude=-23.0,
        initial_longitude=-47.0,
        local_assets=False,
    )
    assert "Usar este local" in page
    assert 'map.on("click"' in page
    assert "© OpenStreetMap contributors" in page


def test_coverage_pipeline_records_calculated_and_interpolated_counts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    request = _request(tmp_path / "result")
    distances = np.linspace(0.0, 50_000.0, 1001)
    margin = np.linspace(18.0, -8.0, 1001)

    def fake_radial(request, bearing, base_project, model, progress):
        return RadialCoverage(
            bearing_deg=bearing,
            distance_m=distances,
            latitude_deg=np.zeros(1001),
            longitude_deg=np.zeros(1001),
            elevation_m=np.zeros(1001),
            margin_db=margin,
            evaluated_point_count=21,
        )

    def fake_report(**kwargs):
        report = kwargs["output_directory"] / "coverage_report.html"
        heatmap = kwargs["output_directory"] / "coverage_heatmap.png"
        report.write_text("<html></html>", encoding="utf-8")
        heatmap.write_bytes(b"test")
        return (
            {
                "report_html": report,
                "heatmap": heatmap,
                "map_overlay": heatmap,
                "contours": kwargs["output_directory"] / "contours.geojson",
            },
            {
                "minimum_margin_db": -8.0,
                "maximum_margin_db": 18.0,
                "covered_percent": 50.0,
                "margin_3_db_percent": 40.0,
                "margin_6_db_percent": 30.0,
                "margin_12_db_percent": 20.0,
            },
        )

    monkeypatch.setattr("radiolink.coverage.ensure_itu_data", lambda **_: None)
    monkeypatch.setattr("radiolink.coverage._calculate_radial", fake_radial)
    monkeypatch.setattr(
        "radiolink.coverage_report.write_coverage_outputs",
        fake_report,
    )
    outcome = run_coverage_analysis(request)

    assert outcome.statistics["radial_count"] == 36
    assert outcome.statistics["physically_evaluated_points"] == 36 * 21
    assert 3_140_000 < outcome.statistics["visual_grid_cells"] < 3_145_000
    assert outcome.paths["margin_grid"].is_file()
    assert outcome.paths["metadata"].is_file()
