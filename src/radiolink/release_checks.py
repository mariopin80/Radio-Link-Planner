"""Checks run on the real packaged executable before a validation release."""
from __future__ import annotations

import dataclasses
import json
import shutil
from pathlib import Path
from unittest.mock import patch

import numpy as np

from .i18n import LANGUAGES, get_language, set_language


def check_localized_reports(output: Path) -> dict:
    from rasterio.transform import from_origin
    import rasterio

    from .coverage import CoverageRequest, run_coverage_analysis
    from .coverage_grid import coverage_terrain_tile_codes
    from .desktop_core import AnalysisRequest, bundled_example_path, run_analysis

    request = CoverageRequest(
        name="Coverage validation", latitude_deg=-23, longitude_deg=-47,
        frequency_mhz=146, polarization="vertical", mode="FM", radius_km=50,
        transmitter_height_m=30, transmitter_gain_dbi=6, transmitter_line_loss_db=1,
        transmitter_power_w=1, receiver_height_m=2, receiver_gain_dbi=2,
        receiver_line_loss_db=1, receiver_threshold_dbm=-120,
        output_directory=output / "pt/coverage", resolution_preset="custom",
        custom_resolution_m=10_000,
    )
    tiles = {}
    terrain = output / "test-terrain"
    terrain.mkdir(parents=True, exist_ok=True)
    for code in coverage_terrain_tile_codes(request):
        from .copernicus import tile_code
        # The small, deterministic fixture covers the four real grid tile codes.
        for latitude in (-24, -23):
            for longitude in (-48, -47):
                if code != tile_code(latitude + 0.5, longitude + 0.5):
                    continue
                path = terrain / f"{code}.tif"
                y, x = np.mgrid[:120, :120]
                elevations = (650 + 180 * np.sin(x / 18) * np.cos(y / 15)).astype("float32")
                with rasterio.open(path, "w", driver="GTiff", count=1, width=120, height=120,
                                   dtype="float32", crs="EPSG:4326",
                                   transform=from_origin(longitude, latitude + 1, 1 / 120, 1 / 120)) as dataset:
                    dataset.write(elevations, 1)
                tiles[code] = path
    original = get_language()
    baseline_result = None
    baseline_grid = None
    matrix = {}
    first_coverage = None
    try:
        for language in LANGUAGES:
            set_language(language)
            link = run_analysis(AnalysisRequest(
                bundled_example_path(), output / language / "link", monte_carlo_runs=500,
            ))
            stable_result = {key: value for key, value in link.result.items() if key not in {"generated_at_utc", "result_sha256"}}
            if baseline_result is None:
                baseline_result = stable_result
            else:
                assert stable_result == baseline_result, "language altered the scientific result"
            for direction in link.result["directions"].values():
                assert all(model["status"] == "ok" for model in direction["design_models"])
            current = dataclasses.replace(request, output_directory=output / language / "coverage")
            if first_coverage:
                current.output_directory.mkdir(parents=True, exist_ok=True)
                for filename in ("coverage_loss_db.npy", "coverage_propagation.json"):
                    shutil.copyfile(first_coverage.paths["report_html"].parent / filename, current.output_directory / filename)
            with patch("radiolink.coverage_grid.download_tile", side_effect=lambda code, **_: tiles[code]):
                coverage = run_coverage_analysis(current, worker_count=2)
            grid = np.load(coverage.paths["margin_grid"])
            if baseline_grid is None:
                baseline_grid = grid
                first_coverage = coverage
            else:
                np.testing.assert_array_equal(grid, baseline_grid)
                assert coverage.statistics["p1812_calls_this_run"] == 0
            for outcome in (link, coverage):
                report = outcome.paths["report_html"].read_text(encoding="utf-8")
                tag = "pt-BR" if language == "pt" else language
                assert f'<html lang="{tag}">' in report
                assert outcome.paths["report_pdf"].read_bytes().startswith(b"%PDF-")
                assert "&gt;" not in report.split("<style>", 1)[1].split("</style>", 1)[0]
            matrix[language] = {
                "link_models": [model["model_id"] for model in link.result["directions"]["a_to_b"]["design_models"]],
                "coverage_cells": int(np.isfinite(grid).sum()),
                "report_html": str(link.paths["report_html"]),
                "report_pdf": str(link.paths["report_pdf"]),
                "coverage_pdf": str(coverage.paths["report_pdf"]),
            }
    finally:
        set_language(original)
    (output / "validation.json").write_text(json.dumps(matrix, indent=2) + "\n", encoding="utf-8")
    return matrix


def check_interface(root, output: Path) -> None:
    from .coverage import CoverageProgress
    from .desktop import RadioLinkPlannerApp
    from .i18n import choice_label, tr

    original = get_language()
    app = RadioLinkPlannerApp(root, load_preferences=False)
    try:
        for language in LANGUAGES:
            app._change_language(language, persist=False)
            root.update_idletasks()
            assert len(app.language_buttons) == 5
            app._open_mode("link")
            assert app._collect_editor_values().polarization == "vertical"
            assert app.notebook.tab(app.about_tab, "text") == tr("Sobre")
            app._show_start_screen()
            app._open_mode("coverage")
            app.coverage_vars["resolution_preset"].set(choice_label("custom"))
            app.coverage_vars["custom_resolution"].set("1000")
            request = app._collect_coverage_request(for_estimate=True)
            assert request.resolution_preset == "custom"
            app.events.put(("coverage_progress", CoverageProgress(
                42, "cells", tr("{x0:.0f}% — Calculando células: {x1:,} de {x2:,}", x0=42, x1=400, x2=1000),
                400, 1000, 60, 90,
            )))
            app._poll_events()
            assert app.coverage_progress_var.get().count("1 min 30 s") == 1
            assert "1 min 30 s" not in app.status_var.get()
            app._show_start_screen()
    finally:
        set_language(original)
