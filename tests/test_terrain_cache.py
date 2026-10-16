from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

from radiolink.copernicus import sample_elevations, CopernicusSeaTileError
import radiolink.terrain_cache as tc


def make_tiles(tmp_path: Path, monkeypatch):
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin
    tiles = {}
    for index, (code, left) in enumerate((("S24_00_W048_00", -48.), ("S24_00_W047_00", -47.))):
        path = tmp_path / f"{code}.tif"
        heights = np.arange(100, dtype=np.float32).reshape(10, 10) + 100 + index*100
        heights[5,5] = -9999.
        heights[3,3] = 0.
        with rasterio.open(path, "w", driver="GTiff", height=10, width=10,
                           count=1, dtype="float32", nodata=-9999.,
                           crs="EPSG:4326", transform=from_origin(left, -23., .1, .1)) as dataset:
            dataset.write(heights, 1)
        tiles[code] = path

    def download(code, **_):
        if code in tiles:
            return tiles[code]
        raise CopernicusSeaTileError(code)
    monkeypatch.setattr(tc, "download_tile", download)
    monkeypatch.setattr("radiolink.copernicus.download_tile", download)
    return tiles


def test_prepared_pixels_match_original_across_tiles_edges_nodata_and_sea(tmp_path, monkeypatch):
    make_tiles(tmp_path, monkeypatch)
    descriptors = tuple(tc.prepare_terrain_tile(code, cache_dir=tmp_path) for code in (
        "S24_00_W048_00", "S24_00_W047_00", "S24_00_W046_00", "S23_00_W048_00",
    ))
    sampler = tc.PreparedTerrainSampler(descriptors)
    # Re-enter tiles and hit exact pixel boundaries, nodata, isolated zero,
    # tile boundaries, the northern/eastern clipping edges, and missing sea.
    lat = np.asarray([-23.2,-23.35,-23.55,-23.55,-23.35,-23.4,-23.,-23.8,-23.5,-23.2])
    lon = np.asarray([-47.9,-47.65,-47.45,-46.45,-46.65,-47.,-48.,-46.1,-45.5,-47.9])
    try:
        np.testing.assert_array_equal(sampler.sample(lat, lon), sample_elevations(lat, lon, cache_dir=tmp_path))
        assert all(isinstance(array, np.memmap) for array in sampler.arrays.values())
        assert all(not array.flags.writeable for array in sampler.arrays.values())
    finally:
        sampler.close()


def test_prepared_map_lru_and_corrupt_array_fallback(tmp_path, monkeypatch):
    make_tiles(tmp_path, monkeypatch)
    codes = ("S24_00_W048_00", "S24_00_W047_00")
    tiles = tuple(tc.prepare_terrain_tile(code, cache_dir=tmp_path) for code in codes)
    monkeypatch.setattr(tc, "MAX_OPEN_TERRAIN_MAPS", 1)
    sampler = tc.PreparedTerrainSampler(tiles)
    lat, lon = np.asarray([-23.1,-23.2,-23.1]), np.asarray([-47.9,-46.9,-47.9])
    try:
        np.testing.assert_array_equal(sampler.sample(lat, lon), sample_elevations(lat, lon, cache_dir=tmp_path))
        assert len(sampler.arrays) == 1
    finally:
        sampler.close()
    tiles[0].pixels.write_bytes(b"interrupted/corrupted cache")
    fallback = tc.prepare_terrain_tile(codes[0], cache_dir=tmp_path)
    assert fallback.pixels is None
    sampler = tc.PreparedTerrainSampler((fallback, tiles[1]))
    try:
        np.testing.assert_array_equal(sampler.sample(lat, lon), sample_elevations(lat, lon, cache_dir=tmp_path))
    finally:
        sampler.close()


def test_source_replacement_invalidates_prepared_pixels(tmp_path, monkeypatch):
    sources = make_tiles(tmp_path, monkeypatch)
    first = tc.prepare_terrain_tile("S24_00_W048_00", cache_dir=tmp_path)
    source = sources["S24_00_W048_00"]
    stat = source.stat()
    os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns+1_000_000_000))
    second = tc.prepare_terrain_tile("S24_00_W048_00", cache_dir=tmp_path)
    assert first.pixels != second.pixels
    assert second.pixels.is_file()
