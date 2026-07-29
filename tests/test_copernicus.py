from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from radiolink.copernicus import (
    extract_profile,
    repair_elevation_samples,
    tile_code,
    tile_url,
    write_profile_csv,
)
from radiolink.report import _route_json
from radiolink.terrain import TerrainProfile


def test_copernicus_tile_naming_and_url() -> None:
    code = tile_code(-23.0557, -45.9313)
    assert code == "S24_00_W046_00"
    assert (
        tile_url(code) == "https://copernicus-dem-30m.s3.amazonaws.com/"
        "Copernicus_DSM_COG_10_S24_00_W046_00_DEM/"
        "Copernicus_DSM_COG_10_S24_00_W046_00_DEM.tif"
    )


def test_repair_elevation_samples_interpolates_nodata_and_isolated_zero() -> None:
    repaired = repair_elevation_samples(np.asarray([100.0, np.nan, 120.0, 0.0, 140.0]))
    assert repaired.tolist() == [100.0, 110.0, 120.0, 130.0, 140.0]


def test_generated_profile_is_readable_and_routes_to_both_terminals(
    tmp_path: Path,
) -> None:
    profile_path = write_profile_csv(
        tmp_path / "terrain_profile.csv",
        np.asarray([0.0, 1.0, 2.0]),
        np.asarray([-23.0, -23.1, -23.2]),
        np.asarray([-46.0, -46.1, -46.2]),
        np.asarray([700.0, 710.0, 720.0]),
    )
    profile = TerrainProfile.from_csv(profile_path)
    assert profile.total_distance_km == 2.0

    from radiolink.domain import Project

    project, _ = Project.from_json(
        Path(__file__).resolve().parents[1] / "examples" / "morro_jacu_palmira.json"
    )
    route = json.loads(_route_json(project, profile))
    assert route["coordinates"][0] == [-46.0, -23.0]
    assert route["coordinates"][-1] == [-46.2, -23.2]


def test_extract_profile_samples_a_cached_geotiff(
    tmp_path: Path,
    monkeypatch,
) -> None:
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin

    tile = tmp_path / "tile.tif"
    with rasterio.open(
        tile,
        "w",
        driver="GTiff",
        height=2,
        width=2,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(-47.0, -23.0, 0.5, 0.5),
    ) as dataset:
        dataset.write(
            np.asarray([[100.0, 200.0], [300.0, 400.0]], dtype=np.float32),
            1,
        )

    monkeypatch.setattr(
        "radiolink.copernicus.download_tile",
        lambda *_args, **_kwargs: tile,
    )
    output = tmp_path / "profile.csv"
    profile = extract_profile(
        -23.10,
        -46.90,
        -23.20,
        -46.80,
        output,
        step_m=500.0,
    )

    assert output.is_file()
    assert profile.total_distance_km > 10.0
    assert len(profile.distance_km) > 20
    assert np.all(np.isfinite(profile.elevation_m))
