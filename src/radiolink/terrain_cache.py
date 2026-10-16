"""Prepared, read-only terrain pixels shared through the OS file cache.

GeoTIFFs are decoded once. Workers map the resulting arrays instead of
allocating a complete copy per process. The mapping LRU bounds open handles;
file-backed pages can be reclaimed by the OS under memory pressure.
"""
from __future__ import annotations

import hashlib
import os
import tempfile
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .copernicus import (
    CopernicusSeaTileError,
    _require_rasterio,
    _sample_raster,
    default_cache_directory,
    download_tile,
    repair_elevation_samples,
)

MAX_OPEN_TERRAIN_MAPS = 12


@dataclass(frozen=True)
class PreparedTerrainTile:
    key: int
    source: Path | None
    pixels: Path | None = None
    transform: tuple[float, ...] = ()
    width: int = 0
    height: int = 0
    nodata: float | None = None


def _tile_key(code: str) -> int:
    lat, _, lon, _ = code.split("_")
    latitude = int(lat[1:]) * (-1 if lat[0] == "S" else 1)
    longitude = int(lon[1:]) * (-1 if lon[0] == "W" else 1)
    return (latitude + 90) * 360 + longitude + 180


def prepare_terrain_tile(code: str, *, cache_dir: Path | None = None) -> PreparedTerrainTile:
    cache = Path(cache_dir or default_cache_directory())
    key = _tile_key(code)
    try:
        source = download_tile(code, cache_dir=cache)
    except CopernicusSeaTileError:
        return PreparedTerrainTile(key=key, source=None)
    rasterio = _require_rasterio()
    with rasterio.open(source) as dataset:
        stat = source.stat()
        identity = f"{source.resolve()}|{stat.st_size}|{stat.st_mtime_ns}|pixels-1"
        signature = hashlib.sha256(identity.encode()).hexdigest()[:20]
        pixels = cache / "prepared" / f"{code}-{signature}.npy"
        temporary: Path | None = None
        try:
            if pixels.is_file():
                existing = np.load(pixels, mmap_mode="r", allow_pickle=False)
                valid = existing.shape == (dataset.height, dataset.width) and existing.dtype == np.dtype(dataset.dtypes[0])
                existing._mmap.close()
                if not valid:
                    raise OSError("invalid prepared terrain array")
            else:
                pixels.parent.mkdir(parents=True, exist_ok=True)
                descriptor, filename = tempfile.mkstemp(dir=pixels.parent, suffix=".tmp")
                os.close(descriptor)
                temporary = Path(filename)
                array = np.lib.format.open_memmap(
                    temporary, mode="w+", dtype=dataset.dtypes[0],
                    shape=(dataset.height, dataset.width),
                )
                try:
                    dataset.read(1, out=array)
                    array.flush()
                finally:
                    array._mmap.close()
                os.replace(temporary, pixels)
        except (OSError, ValueError):
            # Read-only/full cache: preserve the existing block sampler.
            pixels = None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return PreparedTerrainTile(
            key=key, source=source, pixels=pixels,
            transform=tuple(dataset.transform)[:6],
            width=dataset.width, height=dataset.height,
            nodata=float(dataset.nodata) if dataset.nodata is not None else None,
        )


class PreparedTerrainSampler:
    def __init__(self, tiles: tuple[PreparedTerrainTile, ...]) -> None:
        self.tiles = {tile.key: tile for tile in tiles}
        self.arrays: OrderedDict[int, np.memmap] = OrderedDict()

    def close(self) -> None:
        for array in self.arrays.values():
            array._mmap.close()
        self.arrays.clear()

    def sample(self, latitudes: np.ndarray, longitudes: np.ndarray) -> np.ndarray:
        # Coverage already supplies finite, same-size one-dimensional arrays.
        # A great-circle profile visits contiguous runs of one-degree tiles;
        # splitting those runs needs neither sorting nor one mask per tile.
        longitude_floors = (np.floor(longitudes).astype(np.int64) + 180) % 360 - 180
        keys = (np.floor(latitudes).astype(np.int64) + 90) * 360 + longitude_floors + 180
        stops = np.flatnonzero(keys[1:] != keys[:-1]) + 1
        result = np.empty(len(keys), dtype=float)
        start = 0
        for stop in (*stops, len(keys)):
            selected = slice(start, int(stop))
            key = int(keys[start])
            tile = self.tiles.get(key)
            if tile is None:
                raise ValueError(f"terrain tile {key} was not prepared")
            if tile.source is None:
                result[selected] = 0.0
            elif tile.pixels is None:
                values, nodata = _sample_raster(
                    tile.source, longitudes[selected], latitudes[selected], _require_rasterio(),
                )
                if nodata is not None:
                    values[np.isclose(values, nodata)] = np.nan
                result[selected] = values
            else:
                array = self.arrays.pop(key, None)
                if array is None:
                    array = np.load(tile.pixels, mmap_mode="r", allow_pickle=False)
                self.arrays[key] = array
                while len(self.arrays) > MAX_OPEN_TERRAIN_MAPS:
                    _, oldest = self.arrays.popitem(last=False)
                    oldest._mmap.close()
                x, y = longitudes[selected], latitudes[selected]
                # Preserve Rasterio's exact matrix-operation ordering at pixel
                # boundaries, where algebraically equivalent formulas can
                # choose an adjacent pixel after floating-point rounding.
                from affine import Affine
                from rasterio.transform import rowcol
                rows, columns = rowcol(Affine(*tile.transform), x, y)
                rows = np.clip(np.asarray(rows, dtype=np.int64), 0, tile.height-1)
                columns = np.clip(np.asarray(columns, dtype=np.int64), 0, tile.width-1)
                values = array[rows, columns].astype(float)
                if tile.nodata is not None:
                    values[np.isclose(values, tile.nodata)] = np.nan
                result[selected] = values
            start = int(stop)
        return repair_elevation_samples(result)
