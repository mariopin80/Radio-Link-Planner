#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import math
import urllib.request
from pathlib import Path

import numpy as np

from radiolink.geodesy import great_circle_distance_m, great_circle_points


COPERNICUS_ROOT = "https://copernicus-dem-30m.s3.amazonaws.com"


def tile_code(latitude_deg: float, longitude_deg: float) -> str:
    latitude_floor = math.floor(latitude_deg)
    longitude_floor = math.floor(longitude_deg)
    latitude = (
        f"N{latitude_floor:02d}"
        if latitude_floor >= 0
        else f"S{abs(latitude_floor):02d}"
    )
    longitude = (
        f"E{longitude_floor:03d}"
        if longitude_floor >= 0
        else f"W{abs(longitude_floor):03d}"
    )
    return f"{latitude}_00_{longitude}_00"


def tile_url(code: str) -> str:
    directory = f"Copernicus_DSM_COG_10_{code}_DEM"
    return f"{COPERNICUS_ROOT}/{directory}/{directory}.tif"


def download_tile(code: str, cache_dir: Path) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    destination = cache_dir / f"{code}.tif"
    if destination.exists() and destination.stat().st_size > 10_000:
        return destination
    temporary = destination.with_suffix(".part")
    urllib.request.urlretrieve(tile_url(code), temporary)
    temporary.replace(destination)
    return destination


def repair_isolated_zero_samples(elevation: np.ndarray) -> np.ndarray:
    result = elevation.copy()
    zero_indices = np.flatnonzero(result == 0.0)
    for index in zero_indices:
        if index == 0 or index == len(result) - 1:
            continue
        left = result[index - 1]
        right = result[index + 1]
        if left > 30.0 and right > 30.0:
            result[index] = 0.5 * (left + right)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Extract a great-circle profile from Copernicus GLO-30"
    )
    parser.add_argument("lat_a", type=float)
    parser.add_argument("lon_a", type=float)
    parser.add_argument("lat_b", type=float)
    parser.add_argument("lon_b", type=float)
    parser.add_argument("--step-m", type=float, default=30.0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--cache",
        type=Path,
        default=Path.home() / ".cache" / "radio-link-planner" / "copernicus",
    )
    args = parser.parse_args(argv)

    try:
        import rasterio
    except ImportError:
        parser.error('rasterio is required; install with pip install -e ".[geo]"')

    distance_m = great_circle_distance_m(
        args.lat_a, args.lon_a, args.lat_b, args.lon_b
    )
    count = max(2, round(distance_m / args.step_m) + 1)
    latitudes, longitudes = great_circle_points(
        args.lat_a, args.lon_a, args.lat_b, args.lon_b, count
    )
    codes = sorted(
        {
            tile_code(float(latitude), float(longitude))
            for latitude, longitude in zip(latitudes, longitudes)
        }
    )
    datasets = {
        code: rasterio.open(download_tile(code, args.cache)) for code in codes
    }
    elevation = np.empty(count, dtype=float)
    for index, (latitude, longitude) in enumerate(zip(latitudes, longitudes)):
        code = tile_code(float(latitude), float(longitude))
        elevation[index] = next(
            datasets[code].sample([(float(longitude), float(latitude))])
        )[0]
    for dataset in datasets.values():
        dataset.close()
    elevation = repair_isolated_zero_samples(elevation)
    distances = np.linspace(0.0, distance_m / 1000.0, count)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "distance_km",
                "latitude_deg",
                "longitude_deg",
                "elevation_m",
                "zone_code",
                "clutter_height_m",
            ]
        )
        for values in zip(distances, latitudes, longitudes, elevation):
            writer.writerow(
                [
                    f"{values[0]:.6f}",
                    f"{values[1]:.8f}",
                    f"{values[2]:.8f}",
                    f"{values[3]:.3f}",
                    4,
                    "0.000",
                ]
            )
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
