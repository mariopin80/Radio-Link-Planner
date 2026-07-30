from __future__ import annotations

import importlib.util
import threading
from pathlib import Path

import numpy as np
import pytest

from radiolink.coverage import (
    COVERAGE_RESOLUTION_M,
    COVERAGE_RESOLUTION_PRESETS,
    CoverageCancelled,
    CoverageRequest,
    RadialCoverage,
    angular_refinement_candidates,
    coverage_resolution_m,
    interpolate_radials_to_grid,
    run_coverage_analysis,
)
from radiolink.coverage_grid import (
    GridBlockResult,
    coverage_circle_cell_count,
    coverage_grid_dimension,
    estimate_coverage,
    smoke_test_direct_grid_worker,
)
import radiolink.coverage_grid as coverage_grid
from radiolink.coverage_report import _build_coverage_report
from radiolink.geodesy import destination_point, great_circle_distance_m
from radiolink.map_picker import build_picker_html
from radiolink.report_server import start_report_server


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
        50: 100,
        100: 200,
        200: 400,
        300: 600,
        400: 800,
        500: 1000,
    }
    assert COVERAGE_RESOLUTION_PRESETS[300] == {
        "quick": 1200,
        "recommended": 600,
        "detailed": 300,
    }
    assert coverage_resolution_m(200) == 400
    assert coverage_resolution_m(200, preset="quick") == 800
    assert (
        coverage_resolution_m(
            200,
            preset="custom",
            custom_resolution_m=500,
        )
        == 500
    )
    with pytest.raises(ValueError, match="unsupported"):
        coverage_resolution_m(250)


def test_direct_grid_count_stays_near_one_million_cells() -> None:
    expected = coverage_circle_cell_count(300, 600)
    assert 785_000 < expected < 786_000
    assert coverage_grid_dimension(300, 600) == 1001


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


def test_local_report_server_serves_relative_map_assets(
    tmp_path: Path,
) -> None:
    import urllib.parse
    import urllib.request

    report = tmp_path / "coverage report.html"
    asset = tmp_path / "coverage_overlay_r0_c0.png"
    report.write_text(
        '<html><img src="coverage_overlay_r0_c0.png"></html>',
        encoding="utf-8",
    )
    asset.write_bytes(b"overlay")

    server, report_url = start_report_server(report, timeout_seconds=30.0)
    try:
        assert report_url.startswith("http://127.0.0.1:")
        with urllib.request.urlopen(report_url, timeout=5.0) as response:
            assert response.read().startswith(b"<html>")
            assert (
                response.headers["Referrer-Policy"]
                == "strict-origin-when-cross-origin"
            )
        asset_url = urllib.parse.urljoin(
            report_url,
            "coverage_overlay_r0_c0.png",
        )
        with urllib.request.urlopen(asset_url, timeout=5.0) as response:
            assert response.read() == b"overlay"
    finally:
        server.shutdown()
        server.server_close()


def test_coverage_report_fits_bounds_before_loading_overlay(
    tmp_path: Path,
) -> None:
    report = _build_coverage_report(
        request=_request(tmp_path),
        statistics={
            "minimum_margin_db": -1.0,
            "maximum_margin_db": 15.0,
            "covered_percent": 90.0,
            "margin_3_db_percent": 80.0,
            "margin_6_db_percent": 70.0,
            "margin_12_db_percent": 50.0,
        },
        grid_metadata={
            "valid_circle_cells": 100,
            "calculated_cells": 100,
            "model_version": "test",
            "p1812_cells": 99,
            "short_range_free_space_cells": 1,
            "failed_cells": 0,
            "terrain_profile_points": 1000,
            "worker_count": 2,
            "compute_seconds": 125.0,
            "resume_count": 1,
        },
        contour_geojson={"type": "FeatureCollection", "features": []},
        overlay_tiles=[],
        map_assets=(
            "report-assets/maplibre-gl.css",
            "report-assets/maplibre-gl.js",
        ),
    )

    assert (
        '<meta name="referrer" content="strict-origin-when-cross-origin">'
        in report
    )
    assert report.index("map.fitBounds(coverageBounds") < report.index(
        'map.on("load"'
    )
    assert "2 min 05 s" in report
    assert "<th>Retomadas de checkpoint</th><td>1</td>" in report


def test_coverage_pipeline_records_direct_cells_without_interpolation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    request = _request(
        tmp_path / "result",
        resolution_preset="custom",
        custom_resolution_m=10_000,
    )

    def fake_block(spec):
        dimension = coverage_grid_dimension(50, 10_000)
        centre = (dimension - 1) / 2.0
        values = np.full(
            (
                spec.row_stop - spec.row_start,
                spec.column_stop - spec.column_start,
            ),
            np.nan,
            dtype=np.float32,
        )
        calculated = 0
        for local_row, row in enumerate(range(spec.row_start, spec.row_stop)):
            north = (centre - row) * 10_000
            for local_column, column in enumerate(
                range(spec.column_start, spec.column_stop)
            ):
                east = (column - centre) * 10_000
                if np.hypot(east, north) <= 50_000:
                    values[local_row, local_column] = 12.0
                    calculated += 1
        return GridBlockResult(
            block_id=spec.block_id,
            row_start=spec.row_start,
            row_stop=spec.row_stop,
            column_start=spec.column_start,
            column_stop=spec.column_stop,
            margin_db=values,
            calculated_cells=calculated,
            profile_points=calculated * 10,
            p1812_cells=max(0, calculated - 1),
            short_range_cells=min(1, calculated),
            failed_cells=0,
            elapsed_seconds=0.01,
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

    monkeypatch.setattr(
        "radiolink.coverage_grid.ensure_itu_data",
        lambda **_: None,
    )
    monkeypatch.setattr(
        "radiolink.coverage_grid.coverage_terrain_tile_codes",
        lambda _: (),
    )
    monkeypatch.setattr(
        "radiolink.coverage_grid._initialize_grid_worker",
        lambda *_: None,
    )
    monkeypatch.setattr(
        "radiolink.coverage_grid._evaluate_grid_block",
        fake_block,
    )
    monkeypatch.setattr(
        "radiolink.coverage_report.write_coverage_outputs",
        fake_report,
    )
    monkeypatch.setattr(coverage_grid, "_record_performance", lambda **_: None)
    progress_states = []
    outcome = run_coverage_analysis(
        request,
        progress=progress_states.append,
        worker_count=1,
    )

    expected = coverage_circle_cell_count(50, 10_000)
    assert outcome.statistics["calculated_cells"] == expected
    assert outcome.statistics["propagation_interpolated_cells"] == 0
    assert (
        outcome.statistics["p1812_cells"]
        + outcome.statistics["short_range_free_space_cells"]
        == expected
    )
    assert outcome.paths["margin_grid"].is_file()
    assert outcome.paths["metadata"].is_file()
    percentages = [state.overall_percent for state in progress_states]
    assert percentages == sorted(percentages)
    assert percentages[0] == 0.0
    assert percentages[-1] == 100.0
    assert {"prepare", "cells", "render", "complete"} <= {
        state.phase for state in progress_states
    }


def test_estimate_warns_for_a_detailed_large_radius(tmp_path: Path) -> None:
    request = _request(
        tmp_path,
        radius_km=500,
        resolution_preset="detailed",
    )
    estimate = estimate_coverage(request, worker_count=4)
    assert estimate.resolution_m == 500
    assert estimate.valid_circle_cells > 3_000_000
    assert estimate.warning_level == "red"


def test_grid_worker_executes_one_p1812_call_per_eligible_cell(
    tmp_path: Path,
    monkeypatch,
) -> None:
    request = _request(
        tmp_path,
        resolution_preset="custom",
        custom_resolution_m=10_000,
    )
    dimension = coverage_grid_dimension(50, 10_000)

    class FakeP1812:
        def __init__(self) -> None:
            self.calls = 0

        def bt_loss(self, *_args):
            self.calls += 1
            return 120.0, 0.0

    model = FakeP1812()
    monkeypatch.setattr(
        coverage_grid,
        "sample_elevations",
        lambda latitudes, _longitudes, progress=None: np.zeros(
            len(latitudes),
            dtype=float,
        ),
    )
    coverage_grid._WORKER_CONFIGURATION = coverage_grid._worker_configuration(
        request,
        dimension,
    )
    coverage_grid._WORKER_P1812 = model
    coverage_grid._WORKER_CANCEL_EVENT = threading.Event()
    spec = next(
        coverage_grid._iter_grid_blocks(
            request.radius_km,
            request.resolution_m,
            coverage_grid.GRID_BLOCK_SIZE,
        )
    )
    result = coverage_grid._evaluate_grid_block(spec)

    expected = coverage_circle_cell_count(50, 10_000)
    assert result.calculated_cells == expected
    assert result.short_range_cells == 1
    assert result.p1812_cells == expected - 1
    assert model.calls == expected - 1
    assert result.failed_cells == 0


def test_cancelled_grid_is_resumed_from_saved_blocks(
    tmp_path: Path,
    monkeypatch,
) -> None:
    request = _request(
        tmp_path / "resumable",
        resolution_preset="custom",
        custom_resolution_m=5_000,
    )
    dimension = coverage_grid_dimension(50, 5_000)
    centre = (dimension - 1) / 2.0

    def fake_block(spec):
        values = np.full(
            (
                spec.row_stop - spec.row_start,
                spec.column_stop - spec.column_start,
            ),
            np.nan,
            dtype=np.float32,
        )
        calculated = 0
        for local_row, row in enumerate(range(spec.row_start, spec.row_stop)):
            north = (centre - row) * 5_000
            for local_column, column in enumerate(
                range(spec.column_start, spec.column_stop)
            ):
                east = (column - centre) * 5_000
                if np.hypot(east, north) <= 50_000:
                    values[local_row, local_column] = 6.0
                    calculated += 1
        return GridBlockResult(
            block_id=spec.block_id,
            row_start=spec.row_start,
            row_stop=spec.row_stop,
            column_start=spec.column_start,
            column_stop=spec.column_stop,
            margin_db=values,
            calculated_cells=calculated,
            profile_points=calculated * 4,
            p1812_cells=calculated,
            short_range_cells=0,
            failed_cells=0,
            elapsed_seconds=0.01,
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
                "minimum_margin_db": 6.0,
                "maximum_margin_db": 6.0,
                "covered_percent": 100.0,
                "margin_3_db_percent": 100.0,
                "margin_6_db_percent": 100.0,
                "margin_12_db_percent": 0.0,
            },
        )

    monkeypatch.setattr(coverage_grid, "ensure_itu_data", lambda **_: None)
    monkeypatch.setattr(
        coverage_grid,
        "coverage_terrain_tile_codes",
        lambda _: (),
    )
    monkeypatch.setattr(
        coverage_grid,
        "_initialize_grid_worker",
        lambda *_: None,
    )
    monkeypatch.setattr(coverage_grid, "_evaluate_grid_block", fake_block)
    monkeypatch.setattr(
        "radiolink.coverage_report.write_coverage_outputs",
        fake_report,
    )
    monkeypatch.setattr(coverage_grid, "_record_performance", lambda **_: None)

    cancel = threading.Event()

    def cancel_after_first_block(state) -> None:
        if state.phase == "cells" and state.completed > 0:
            cancel.set()

    with pytest.raises(CoverageCancelled) as cancelled:
        run_coverage_analysis(
            request,
            progress=cancel_after_first_block,
            cancel_event=cancel,
            worker_count=1,
        )
    assert cancelled.value.completed_cells > 0
    assert estimate_coverage(request, worker_count=1).resumable_cells > 0

    outcome = run_coverage_analysis(request, worker_count=1)
    assert outcome.statistics["resumed"] is True
    assert outcome.statistics["resume_count"] == 1
    assert outcome.statistics["calculated_cells"] == coverage_circle_cell_count(
        50,
        5_000,
    )


def test_failed_direct_cell_does_not_complete_its_block(
    tmp_path: Path,
    monkeypatch,
) -> None:
    request = _request(
        tmp_path / "failed-cell",
        resolution_preset="custom",
        custom_resolution_m=10_000,
    )

    def failed_block(spec):
        shape = (
            spec.row_stop - spec.row_start,
            spec.column_stop - spec.column_start,
        )
        return GridBlockResult(
            block_id=spec.block_id,
            row_start=spec.row_start,
            row_stop=spec.row_stop,
            column_start=spec.column_start,
            column_stop=spec.column_stop,
            margin_db=np.full(shape, np.nan, dtype=np.float32),
            calculated_cells=1,
            profile_points=0,
            p1812_cells=0,
            short_range_cells=0,
            failed_cells=1,
            elapsed_seconds=0.01,
            errors=("ValueError: synthetic failure",),
        )

    monkeypatch.setattr(coverage_grid, "ensure_itu_data", lambda **_: None)
    monkeypatch.setattr(
        coverage_grid,
        "coverage_terrain_tile_codes",
        lambda _: (),
    )
    monkeypatch.setattr(
        coverage_grid,
        "_initialize_grid_worker",
        lambda *_: None,
    )
    monkeypatch.setattr(coverage_grid, "_evaluate_grid_block", failed_block)

    with pytest.raises(RuntimeError, match="não foi marcado como concluído"):
        run_coverage_analysis(request, worker_count=1)

    assert estimate_coverage(request, worker_count=1).resumable_cells == 0


def test_completed_grid_is_copied_from_checkpoint_not_replaced(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "checkpoint-grid.npy"
    destination = tmp_path / "coverage_margin_db.npy"
    source.write_bytes(b"direct-grid-result")

    def replacement_must_not_be_used(*_args, **_kwargs) -> None:
        raise AssertionError("A grade final não deve mover o checkpoint")

    monkeypatch.setattr(coverage_grid.os, "replace", replacement_must_not_be_used)
    coverage_grid._copy_completed_grid(source, destination)

    assert destination.read_bytes() == b"direct-grid-result"
    assert source.is_file()


@pytest.mark.reference
def test_direct_grid_cell_matches_point_to_point_p1812(
    tmp_path: Path,
) -> None:
    if importlib.util.find_spec("Py1812") is None:
        pytest.skip("optional P.1812 implementation is not installed")
    from radiolink.coverage import _base_project
    from radiolink.geodesy import destination_points
    from radiolink.propagation.base import (
        Direction,
        ModelContext,
        ModelStatus,
    )
    from radiolink.propagation.p1812 import P1812Model
    from radiolink.terrain import TerrainProfile

    request = _request(
        tmp_path,
        resolution_preset="custom",
        custom_resolution_m=10_000,
    )
    configuration = coverage_grid._worker_configuration(
        request,
        coverage_grid_dimension(request.radius_km, request.resolution_m),
    )
    try:
        coverage_grid._initialize_grid_worker(
            configuration,
            threading.Event(),
        )
    except FileNotFoundError as exc:
        pytest.skip(f"P.1812 digital product unavailable: {exc}")

    distance_m = 10_000.0
    count = int(np.ceil(distance_m / request.terrain_step_m)) + 1
    distances_m = np.linspace(0.0, distance_m, count)
    latitudes, longitudes = destination_points(
        request.latitude_deg,
        request.longitude_deg,
        45.0,
        distances_m,
    )
    elevations = np.linspace(650.0, 700.0, count)
    direct_margin = coverage_grid._p1812_margin_for_profile(
        configuration,
        distances_m,
        latitudes,
        longitudes,
        elevations,
    )

    project = _base_project(request)
    receiver = project.terminal_b.model_copy(
        update={
            "latitude_deg": float(latitudes[-1]),
            "longitude_deg": float(longitudes[-1]),
        }
    )
    project = project.model_copy(update={"terminal_b": receiver})
    profile = TerrainProfile(
        distance_km=distances_m / 1000.0,
        elevation_m=elevations,
        latitude_deg=latitudes,
        longitude_deg=longitudes,
        zone_code=np.full(count, 4, dtype=int),
        clutter_height_m=np.zeros(count, dtype=float),
    )
    evaluation = P1812Model().evaluate(
        ModelContext(
            project=project,
            profile=profile,
            direction=Direction.A_TO_B,
        ),
        request.time_percentage,
    )
    assert evaluation.status is ModelStatus.OK
    expected_margin = coverage_grid._margin_from_loss(
        configuration,
        float(evaluation.loss_db),
    )
    assert direct_margin == pytest.approx(expected_margin, abs=1e-9)


@pytest.mark.reference
def test_spawned_direct_grid_worker_runs_p1812() -> None:
    if importlib.util.find_spec("Py1812") is None:
        pytest.skip("optional P.1812 implementation is not installed")
    try:
        margin = smoke_test_direct_grid_worker()
    except FileNotFoundError as exc:
        pytest.skip(f"P.1812 digital product unavailable: {exc}")
    assert np.isfinite(margin)
