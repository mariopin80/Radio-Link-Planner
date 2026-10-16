from __future__ import annotations

import json
from dataclasses import replace

import numpy as np
import pytest

import radiolink.coverage_grid as cg
from test_performance_regressions import request


@pytest.fixture
def isolated_history(tmp_path, monkeypatch):
    history = tmp_path / "coverage-performance.json"
    monkeypatch.setattr(cg, "_performance_history_path", lambda: history)
    monkeypatch.setattr(cg, "_resumable_cell_count", lambda _: 0)
    monkeypatch.setattr(cg, "_propagation_cache_metadata", lambda _: None)
    return history


def test_initial_300_km_quick_estimate_uses_optimized_costs(tmp_path, isolated_history):
    configuration = request(tmp_path, radius_km=300, resolution_preset="quick")
    estimate = cg.estimate_coverage(configuration, worker_count=7)
    assert estimate.valid_circle_cells == 196321
    assert 0 < estimate.estimated_seconds_low < estimate.estimated_seconds_high < 600
    assert estimate.estimation_basis == "default"
    assert estimate.warning_level == "normal"


def test_unmeasured_downloads_do_not_add_invented_minutes(tmp_path, isolated_history, monkeypatch):
    configuration = request(tmp_path, radius_km=300, resolution_preset="quick")
    monkeypatch.setattr(cg, "_valid_cached_tile", lambda _: False)
    missing = cg.estimate_coverage(configuration, worker_count=7)
    monkeypatch.setattr(cg, "_valid_cached_tile", lambda _: True)
    cached = cg.estimate_coverage(configuration, worker_count=7)
    assert missing.uncached_terrain_tile_count > 0
    assert cached.uncached_terrain_tile_count == 0
    assert cached.estimated_seconds_low == missing.estimated_seconds_low
    assert cached.estimated_seconds_high == missing.estimated_seconds_high


def test_042_history_is_recalculated_from_raw_work_and_elapsed_time(tmp_path, isolated_history):
    configuration = request(tmp_path, radius_km=300, resolution_preset="quick")
    before = cg.estimate_coverage(configuration, worker_count=7)
    # This has the exact record format of 0.4.2, including its old stored weight.
    isolated_history.write_text(json.dumps({"schema_version":1,"runs":[{
        "machine_key":cg._machine_key(7),"workers":7,
        "cells":before.valid_circle_cells,"profile_points":before.estimated_profile_points,
        "elapsed_seconds":300.,"work_units_per_second":
        (before.estimated_profile_points+before.valid_circle_cells*667.)/300.,
    }]}))
    calibrated = cg.estimate_coverage(configuration, worker_count=7)
    assert calibrated.estimation_basis == "history"
    assert calibrated.estimated_seconds_low < 300 < calibrated.estimated_seconds_high
    expected = (before.estimated_profile_points+before.valid_circle_cells*cg.CELL_OVERHEAD_WORK_UNITS)/300.
    assert cg._historical_work_rate(7) == pytest.approx(expected)


def test_history_prefers_matching_workers_and_can_scale_other_counts(tmp_path, isolated_history):
    runs = []
    for workers, seconds in ((1,8.),(4,3.)):
        runs.append({"machine_key":cg._machine_key(workers),"workers":workers,
                     "cells":7845,"profile_points":8723468,"elapsed_seconds":seconds})
    isolated_history.write_text(json.dumps({"runs":runs}))
    units = 8723468+7845*cg.CELL_OVERHEAD_WORK_UNITS
    assert cg._historical_work_rate(4) == pytest.approx(units/3.)
    assert cg._historical_work_rate(1) == pytest.approx(units/8.)
    rates = cg._historical_work_rates(7)
    assert len(rates) == 2
    np.testing.assert_allclose(rates,[units/8.*cg._effective_workers(7), units/3./cg._effective_workers(4)*cg._effective_workers(7)])


def test_corrupt_old_and_tiny_timings_cannot_poison_estimates(isolated_history):
    isolated_history.write_text("{interrupted write")
    assert cg._historical_work_rates(4) == []
    samples = [
        {"machine_key":cg._machine_key(4),"workers":4,"cells":10,"profile_points":100,"elapsed_seconds":.01},
        {"machine_key":cg._machine_key(4),"workers":4,"cells":1000,"profile_points":10000,"elapsed_seconds":float('nan')},
        {"machine_key":"unoptimized-engine-v1","workers":4,"cells":1000,"profile_points":10000,"elapsed_seconds":5},
        {}, None,
    ]
    isolated_history.write_text(json.dumps({"runs":samples}))
    assert cg._historical_work_rates(4) == []
    assert cg._historical_work_rate(4) == cg._default_work_rate(4)


def test_remaining_time_accounts_for_profile_lengths_and_resumed_work():
    # Long edge profiles take more work than central cells; count-only ETA
    # treats them alike. The remaining 50 cells here have much shorter paths.
    eta = cg._remaining_compute_seconds(
        total_cells=100,total_profile_points=1_000_000,
        completed_cells=50,completed_profile_points=750_000,
        session_cells=50,session_profile_points=750_000,
        elapsed_seconds=50.,fallback_seconds=999.,
    )
    assert 0 < eta < 50.
    resumed = cg._remaining_compute_seconds(
        total_cells=100,total_profile_points=1_000_000,
        completed_cells=50,completed_profile_points=750_000,
        session_cells=25,session_profile_points=375_000,
        elapsed_seconds=25.,fallback_seconds=999.,
    )
    assert resumed == pytest.approx(eta)
    assert cg._remaining_compute_seconds(
        total_cells=100,total_profile_points=1_000_000,
        completed_cells=100,completed_profile_points=999_000,
        session_cells=100,session_profile_points=999_000,
        elapsed_seconds=70.,fallback_seconds=999.,
    ) == 0.


def test_recorded_runs_remain_reusable_with_the_new_weight(isolated_history):
    cg._record_performance(workers=4,cells=7845,profile_points=8723468,elapsed_seconds=3.)
    assert cg._historical_work_rates(4)
    record = json.loads(isolated_history.read_text())["runs"][0]
    assert record["cell_overhead_work_units"] == cg.CELL_OVERHEAD_WORK_UNITS
