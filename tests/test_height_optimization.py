from dataclasses import replace
import os
import sys
import time

import numpy as np
import pytest
from pypdf import PdfReader

from radiolink.domain import Project
from radiolink.engine import analyze_project
from radiolink.geodesy import destination_points
from radiolink.geometry import calculate_geometry
from radiolink.height_optimization import HeightBounds, apply_height_solution, optimize_antenna_heights
from radiolink.propagation.base import ModelEvaluation, ModelStatus
from radiolink.report import write_outputs
from radiolink.terrain import TerrainProfile


@pytest.fixture
def terrain_case(reference_project):
    distances = np.linspace(0.0, 10_000.0, 5)
    latitudes, longitudes = destination_points(0, 0, 0, distances)
    project = reference_project.model_copy(deep=True)
    project.terminal_a.latitude_deg = project.terminal_a.longitude_deg = 0
    project.terminal_b.latitude_deg = float(latitudes[-1])
    project.terminal_b.longitude_deg = float(longitudes[-1])
    project.terminal_a.antenna_height_m = project.terminal_b.antenna_height_m = 10.0
    project.monte_carlo.runs = 100
    profile = TerrainProfile(distances / 1000, np.full(5, 100.0), latitudes, longitudes,
                             np.full(5, 4), np.zeros(5))
    _, arrays = calculate_geometry(project, profile)
    elevations = profile.elevation_m.copy()
    elevations[1:-1] += arrays.clearance_m[1:-1] - 0.6 * arrays.fresnel_radius_m[1:-1] + (6, 5, -1)
    return project, replace(profile, elevation_m=elevations)


@pytest.mark.parametrize(
    "bounds_a,bounds_b,heights",
    [
        (HeightBounds(1, 35), HeightBounds(1, 35), (17, 13)),
        (HeightBounds(1, 35), None, (20, 10)),
        (None, HeightBounds(1, 35), (10, 34)),
        (HeightBounds(1, 14), HeightBounds(1, 14), None),
        (HeightBounds(18, 35), HeightBounds(1, 35), (18, 12)),
    ],
)
def test_optimization_on_known_obstacles(terrain_case, bounds_a, bounds_b, heights):
    project, profile = terrain_case
    solution = optimize_antenna_heights(
        project, profile, bounds_a=bounds_a, bounds_b=bounds_b, step_m=1,
        fresnel_percent=60, effective_earth_k=project.environment.effective_earth_k,
    )
    assert project.terminal_a.antenna_height_m == project.terminal_b.antenna_height_m == 10.0
    if heights is None:
        assert solution is None
        return
    assert (solution.proposed_a_m, solution.proposed_b_m) == heights
    assert solution.before.distance_km == 2.5
    applied = apply_height_solution(project, profile, solution)
    _, arrays = calculate_geometry(applied, profile)
    assert np.min(arrays.clearance_m[1:-1] - 0.6 * arrays.fresnel_radius_m[1:-1]) >= -1e-8


def test_applied_optimization_recalculates_loss_and_reports_both_profiles(terrain_case, tmp_path, monkeypatch):
    project, profile = terrain_case
    solution = optimize_antenna_heights(
        project, profile, bounds_a=HeightBounds(1, 50), bounds_b=None,
        step_m=2, fresnel_percent=60, effective_earth_k=1.2,
    )
    assert solution is not None
    applied = Project.model_validate_json(apply_height_solution(project, profile, solution).model_dump_json())

    class HeightDependentModel:
        model_id = "itm"

        def evaluate(self, context, percentile):
            height = context.project.terminal_a.antenna_height_m
            return ModelEvaluation("itm", "Test", "1", ModelStatus.OK, context.direction.value,
                                   loss_db=160.0 - height, percentile=percentile)

        def quantile_curve(self, context, percentiles):
            return None

    monkeypatch.setattr("radiolink.engine._enabled_models", lambda project: [HeightDependentModel()])
    result, arrays = analyze_project(applied, profile)
    comparison = result["height_optimization"]["model_comparison"]["a_to_b"][0]
    assert comparison["before"]["loss_db"] == 150.0
    assert comparison["after"]["loss_db"] == 160.0 - solution.proposed_a_m
    assert comparison["after"]["margin_db"] > comparison["before"]["margin_db"]
    paths = write_outputs(tmp_path, applied, profile, result, arrays, make_plots=False)
    assert paths["profile_plot"].is_file()
    summary = paths["summary_markdown"].read_text(encoding="utf-8")
    html = paths["report_html"].read_text(encoding="utf-8")
    pdf = "\n".join(page.extract_text() for page in PdfReader(paths["report_pdf"]).pages)
    for report in (summary, html, pdf):
        assert "Otimização da altura das antenas" in report
        assert "150.00" in report and "1.2" in report
    applied.terminal_a.antenna_height_m += 1
    assert "height_optimization" not in analyze_project(applied, profile)[0]


@pytest.mark.skipif(sys.platform != "win32" and not os.environ.get("DISPLAY"), reason="requires a display")
def test_preview_simulation_and_explicit_application(terrain_case, monkeypatch):
    import tkinter as tk
    from tkinter import ttk

    from radiolink.height_dialog import open_height_dialog
    from radiolink.i18n import tr

    project, profile = terrain_case
    simulated = {"status": "ok", "percentile": 50.0, "loss_db": 120.0, "margin_db": 10.0}
    monkeypatch.setattr("radiolink.height_dialog.compare_height_designs", lambda *args: {
        direction: [{"model_id": "itm", "before": simulated, "after": simulated}]
        for direction in ("a_to_b", "b_to_a")
    })

    def children(widget):
        for child in widget.winfo_children():
            yield child
            yield from children(child)

    root = tk.Tk()
    applied = []
    try:
        dialog = open_height_dialog(root, project, profile, applied.append)
        buttons = {
            button.cget("text"): button for button in children(dialog) if isinstance(button, ttk.Button)
        }
        apply_button = buttons[tr("Aplicar alturas")]
        assert apply_button.instate(["disabled"])
        buttons[tr("Calcular alturas")].invoke()
        assert any(
            isinstance(label, ttk.Label) and label.cget("image")
            for label in children(dialog)
        )
        assert not applied and project.terminal_a.antenna_height_m == 10.0
        buttons[tr("Simular antes e depois")].invoke()
        tables = [table for table in children(dialog) if isinstance(table, ttk.Treeview)]
        deadline = time.monotonic() + 5
        while not all(table.get_children() for table in tables) and time.monotonic() < deadline:
            root.update()
            time.sleep(0.02)
        assert all(len(table.get_children()) == 1 for table in tables)
        assert not applied
        apply_button.invoke()
        assert (applied[0].proposed_a_m, applied[0].proposed_b_m) == (17.0, 13.0)
    finally:
        root.destroy()
