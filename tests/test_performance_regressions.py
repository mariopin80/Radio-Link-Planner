from __future__ import annotations

import importlib.resources
import importlib.util
import math
import threading
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from radiolink.coverage import CoverageRequest, CoverageCancelled
import radiolink.coverage_grid as cg
from radiolink.geodesy import destination_points
from radiolink.itu_data import P1812_PRODUCT, product_data_directory
from radiolink.propagation.p1812_fast import optimize_p1812


def request(directory: Path, **changes) -> CoverageRequest:
    values = dict(
        name="Performance regression", latitude_deg=-23.5, longitude_deg=-47.5,
        frequency_mhz=146.0, polarization="vertical", mode="FM", radius_km=50,
        transmitter_height_m=30.0, transmitter_gain_dbi=6.0,
        transmitter_line_loss_db=1.0, transmitter_power_w=50.0,
        receiver_height_m=2.0, receiver_gain_dbi=2.0,
        receiver_line_loss_db=1.0, receiver_threshold_dbm=-120.0,
        output_directory=directory, resolution_preset="custom", custom_resolution_m=5000,
    )
    return CoverageRequest(**(values | changes))


@pytest.mark.reference
def test_vectorization_preserves_upstream_losses_for_varied_profiles(monkeypatch):
    Py1812 = pytest.importorskip("Py1812")
    data = product_data_directory(P1812_PRODUCT)
    if not (data / "P1812.npz").is_file():
        pytest.skip("official P.1812 digital maps are not installed")
    spec = importlib.util.spec_from_file_location(
        "pristine_p1812", Path(Py1812.__file__).with_name("P1812.py"),
    )
    original = importlib.util.module_from_spec(spec)
    with monkeypatch.context() as patch:
        patch.setattr(importlib.resources, "files", lambda *_: data)
        spec.loader.exec_module(original)
    cases = []
    rng = np.random.default_rng(724193)
    for index in range(72):
        distance_km = (0.25, 1.0, 10.0, 50.0, 200.0, 500.0)[index % 6]
        count = math.ceil(distance_km * 1000 / 30) + 1
        d = np.linspace(0.0, distance_km, count)
        kind = (index // 6) % 3
        if kind == 0:
            h = np.zeros(count)
        elif kind == 1:
            h = 650 + 130*np.sin(d/4.0) + 80*np.cos(d/13.0) + rng.uniform(0, 5, count)
        else:
            h = 100 + 600*np.exp(-((d-distance_km/2)/max(.03, distance_km/20))**2)
        zone = np.full(count, 4, dtype=int)
        if index % 4 == 1:
            zone[:] = 1
        elif index % 4 == 2:
            zone[count//3:count*2//3] = 1
            zone[:count//3] = 3
        clutter = np.zeros(count)
        if index % 5 == 0:
            clutter[count//4:count//2] = 10.0
        args = (
            (.03, .146, .435, 1.296, 3.0)[index % 5], (1., 10., 50.)[index % 3],
            d, h, clutter, zone, (2., 30., 100.)[index % 3],
            (1.5, 10.)[index % 2], 1 + index % 2, -23.5, -23., -47.5, -47.,
        )
        cases.append((args, original.bt_loss(*args)))
    optimize_p1812(original)
    for args, expected in cases:
        np.testing.assert_array_equal(original.bt_loss(*args), expected)
    # Idempotence is needed when link and coverage modules share a process.
    first = original.dl_bull
    assert optimize_p1812(original).dl_bull is first


def install_fake_engine(monkeypatch):
    calls = []

    class FakeP1812:
        def bt_loss(self, f, p, d, h, clutter, zone, ht, hr, *_):
            calls.append(float(d[-1]))
            return 100.0 + 5*f + 0.03*float(d[-1]) + ht/100 + hr/100, 0.0

    def initialize(configuration, cancel):
        monkeypatch.setattr(cg, "_WORKER_CONFIGURATION", configuration)
        monkeypatch.setattr(cg, "_WORKER_CANCEL_EVENT", cancel)
        monkeypatch.setattr(cg, "_WORKER_P1812", FakeP1812())
        monkeypatch.setattr(cg, "_WORKER_TERRAIN", None)

    def report(**kwargs):
        directory = kwargs["output_directory"]
        path = directory / "coverage_report.html"
        path.write_text("<html>regression test</html>")
        return {"report_html": path}, {}

    monkeypatch.setattr(cg, "_initialize_grid_worker", initialize)
    monkeypatch.setattr(cg, "sample_elevations", lambda lat, lon, **_: np.zeros(len(lat)))
    monkeypatch.setattr(cg, "ensure_itu_data", lambda **_: None)
    monkeypatch.setattr(cg, "coverage_terrain_tile_codes", lambda _: ())
    monkeypatch.setattr(cg, "_record_performance", lambda **_: None)
    monkeypatch.setattr("radiolink.coverage_report.write_coverage_outputs", report)
    return calls


def test_budget_changes_reuse_loss_and_match_a_full_rerun(tmp_path, monkeypatch):
    calls = install_fake_engine(monkeypatch)
    first = request(tmp_path / "reuse")
    outcome = cg.run_direct_grid_coverage(first, worker_count=1)
    assert len(calls) == outcome.statistics["p1812_cells"]
    assert np.load(outcome.paths["loss_grid"]).dtype == np.float64
    changed = replace(
        first, name="New radio settings", transmitter_power_w=100.,
        transmitter_gain_dbi=8., transmitter_line_loss_db=0.5,
        receiver_gain_dbi=4., receiver_line_loss_db=0.2, receiver_threshold_dbm=-125.,
    )
    assert cg.estimate_coverage(changed, worker_count=1).reusable_propagation_cells > 0
    calls.clear()
    reused = cg.run_direct_grid_coverage(changed, worker_count=1)
    assert not calls
    assert reused.statistics["propagation_cache_reused"] is True
    assert reused.statistics["p1812_calls_this_run"] == 0
    reused_grid = np.load(reused.paths["margin_grid"])
    direct = cg.run_direct_grid_coverage(replace(changed, output_directory=tmp_path/"direct"), worker_count=1)
    np.testing.assert_array_equal(reused_grid, np.load(direct.paths["margin_grid"]))
    assert len(calls) == direct.statistics["p1812_cells"]
    calls.clear()
    new_frequency = cg.run_direct_grid_coverage(replace(changed, frequency_mhz=435.), worker_count=1)
    assert calls and not new_frequency.statistics["propagation_cache_reused"]


@pytest.mark.parametrize("changes", [
    {"frequency_mhz":435.}, {"transmitter_height_m":31.}, {"receiver_height_m":3.},
    {"time_percentage":10.}, {"polarization":"horizontal"}, {"radius_km":100},
    {"custom_resolution_m":10000}, {"latitude_deg":-23.4}, {"longitude_deg":-47.4},
    {"terrain_step_m":50.},
])
def test_physical_changes_invalidate_the_loss_cache(tmp_path, changes):
    original = request(tmp_path)
    assert cg.propagation_fingerprint(original) != cg.propagation_fingerprint(replace(original, **changes))


def test_corrupted_loss_cache_is_recomputed(tmp_path, monkeypatch):
    calls = install_fake_engine(monkeypatch)
    original = request(tmp_path)
    outcome = cg.run_direct_grid_coverage(original, worker_count=1)
    with outcome.paths["loss_grid"].open("r+b") as handle:
        handle.seek(-8, 2)
        handle.write(b"12345678")
    calls.clear()
    outcome = cg.run_direct_grid_coverage(original, worker_count=1)
    assert calls and not outcome.statistics["propagation_cache_reused"]


def test_loss_checkpoint_resumes_and_releases_file_handles(tmp_path, monkeypatch):
    calls = install_fake_engine(monkeypatch)
    original = request(tmp_path)
    cancel = threading.Event()
    def stop(state):
        if state.phase == "cells" and state.completed:
            cancel.set()
    with pytest.raises(CoverageCancelled) as error:
        cg.run_direct_grid_coverage(original, worker_count=1, progress=stop, cancel_event=cancel)
    completed = error.value.completed_cells
    assert 0 < completed < cg.coverage_circle_cell_count(50, 5000)
    calls.clear()
    result = cg.run_direct_grid_coverage(original, worker_count=1)
    assert result.statistics["resumed"]
    assert len(calls) < result.statistics["p1812_cells"]
    assert not list(tmp_path.glob(".coverage-checkpoint-*"))
    assert np.count_nonzero(np.isfinite(np.load(result.paths["loss_grid"]))) == result.statistics["calculated_cells"]
