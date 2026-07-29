from __future__ import annotations

import csv
import math
import os
import urllib.request
from collections.abc import Callable
from pathlib import Path

import numpy as np

from .geodesy import great_circle_distance_m, great_circle_points
from .terrain import TerrainProfile

COPERNICUS_ROOT = "https://copernicus-dem-30m.s3.amazonaws.com"
DEFAULT_STEP_M = 30.0
ProgressCallback = Callable[[str], None]


def default_cache_directory() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        root = Path(local_app_data)
    else:
        root = Path.home() / ".cache"
    return root / "RadioLinkPlanner" / "Copernicus-GLO-30"


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


def download_tile(
    code: str,
    cache_dir: str | Path | None = None,
    progress: ProgressCallback | None = None,
) -> Path:
    cache = Path(cache_dir or default_cache_directory())
    cache.mkdir(parents=True, exist_ok=True)
    destination = cache / f"{code}.tif"
    if destination.exists() and destination.stat().st_size > 10_000:
        _notify(progress, f"Terreno: usando bloco {code} do cache.")
        return destination

    temporary = destination.with_suffix(".part")
    temporary.unlink(missing_ok=True)
    request = urllib.request.Request(
        tile_url(code),
        headers={"User-Agent": "RadioLinkPlanner/0.2 (+https://github.com/mariopin80)"},
    )
    _notify(progress, f"Terreno: baixando bloco Copernicus {code}…")
    try:
        with (
            urllib.request.urlopen(request, timeout=90) as response,
            temporary.open("wb") as handle,
        ):
            total = int(response.headers.get("Content-Length", "0") or 0)
            downloaded = 0
            next_report = 10
            while chunk := response.read(1024 * 1024):
                handle.write(chunk)
                downloaded += len(chunk)
                if total > 0:
                    percent = int(100 * downloaded / total)
                    if percent >= next_report:
                        _notify(
                            progress,
                            f"Terreno: bloco {code}, {min(percent, 100)}%…",
                        )
                        next_report += 10
        if temporary.stat().st_size <= 10_000:
            raise OSError(f"downloaded Copernicus tile is unexpectedly small: {code}")
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return destination


def extract_profile(
    latitude_a_deg: float,
    longitude_a_deg: float,
    latitude_b_deg: float,
    longitude_b_deg: float,
    output_path: str | Path,
    *,
    step_m: float = DEFAULT_STEP_M,
    cache_dir: str | Path | None = None,
    progress: ProgressCallback | None = None,
) -> TerrainProfile:
    if step_m <= 0.0:
        raise ValueError("terrain step must be positive")
    try:
        import rasterio
    except ImportError as exc:
        raise RuntimeError(
            "O componente geográfico não está disponível nesta instalação."
        ) from exc

    distance_m = great_circle_distance_m(
        latitude_a_deg,
        longitude_a_deg,
        latitude_b_deg,
        longitude_b_deg,
    )
    count = max(2, round(distance_m / step_m) + 1)
    latitudes, longitudes = great_circle_points(
        latitude_a_deg,
        longitude_a_deg,
        latitude_b_deg,
        longitude_b_deg,
        count,
    )
    point_codes = np.asarray(
        [
            tile_code(float(latitude), float(longitude))
            for latitude, longitude in zip(latitudes, longitudes)
        ],
        dtype=object,
    )
    codes = sorted(set(point_codes.tolist()))
    _notify(
        progress,
        f"Terreno: {distance_m / 1000.0:.2f} km, "
        f"{count} amostras e {len(codes)} bloco(s).",
    )

    elevations = np.empty(count, dtype=float)
    for code in codes:
        source = download_tile(code, cache_dir=cache_dir, progress=progress)
        indices = np.flatnonzero(point_codes == code)
        coordinates = [
            (float(longitudes[index]), float(latitudes[index])) for index in indices
        ]
        with rasterio.open(source) as dataset:
            samples = np.asarray(
                [float(value[0]) for value in dataset.sample(coordinates)],
                dtype=float,
            )
            if dataset.nodata is not None:
                samples[np.isclose(samples, float(dataset.nodata))] = np.nan
        elevations[indices] = samples

    elevations = repair_elevation_samples(elevations)
    distances = np.linspace(0.0, distance_m / 1000.0, count)
    destination = Path(output_path).resolve()
    write_profile_csv(
        destination,
        distances,
        latitudes,
        longitudes,
        elevations,
    )
    _notify(progress, f"Terreno: perfil salvo com {count} pontos.")
    return TerrainProfile.from_csv(destination)


def repair_elevation_samples(elevation: np.ndarray) -> np.ndarray:
    result = np.asarray(elevation, dtype=float).copy()
    result[result < -1000.0] = np.nan
    valid = np.isfinite(result)
    if np.count_nonzero(valid) < 2:
        raise ValueError("Copernicus profile has insufficient valid elevations")
    if not np.all(valid):
        valid_indices = np.flatnonzero(valid)
        invalid_indices = np.flatnonzero(~valid)
        result[invalid_indices] = np.interp(
            invalid_indices,
            valid_indices,
            result[valid],
        )

    zero_indices = np.flatnonzero(result == 0.0)
    for index in zero_indices:
        if index == 0 or index == len(result) - 1:
            continue
        left = result[index - 1]
        right = result[index + 1]
        if left > 30.0 and right > 30.0:
            result[index] = 0.5 * (left + right)
    return result


def write_profile_csv(
    output_path: str | Path,
    distances_km: np.ndarray,
    latitudes_deg: np.ndarray,
    longitudes_deg: np.ndarray,
    elevations_m: np.ndarray,
) -> Path:
    destination = Path(output_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="") as handle:
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
        for values in zip(
            distances_km,
            latitudes_deg,
            longitudes_deg,
            elevations_m,
        ):
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
    return destination


def _notify(progress: ProgressCallback | None, message: str) -> None:
    if progress is not None:
        progress(message)
