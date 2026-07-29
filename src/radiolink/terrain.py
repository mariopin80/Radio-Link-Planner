from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class TerrainProfile:
    distance_km: np.ndarray
    elevation_m: np.ndarray
    latitude_deg: np.ndarray
    longitude_deg: np.ndarray
    zone_code: np.ndarray
    clutter_height_m: np.ndarray
    source_path: Path | None = None

    def __post_init__(self) -> None:
        lengths = {
            len(self.distance_km),
            len(self.elevation_m),
            len(self.latitude_deg),
            len(self.longitude_deg),
            len(self.zone_code),
            len(self.clutter_height_m),
        }
        if len(lengths) != 1 or not lengths or next(iter(lengths)) < 2:
            raise ValueError("terrain arrays must have the same length >= 2")
        if not np.all(np.isfinite(self.distance_km)):
            raise ValueError("profile distance contains non-finite values")
        if not np.all(np.isfinite(self.elevation_m)):
            raise ValueError("profile elevation contains non-finite values")
        if abs(float(self.distance_km[0])) > 1e-6:
            raise ValueError("profile distance must begin at zero")
        if np.any(np.diff(self.distance_km) <= 0.0):
            raise ValueError("profile distances must be strictly increasing")

    @property
    def total_distance_km(self) -> float:
        return float(self.distance_km[-1])

    @property
    def nominal_step_m(self) -> float:
        return float(self.total_distance_km * 1000.0 / (len(self.distance_km) - 1))

    @property
    def is_equally_spaced(self) -> bool:
        steps = np.diff(self.distance_km)
        return bool(np.allclose(steps, steps.mean(), rtol=1e-5, atol=1e-8))

    @classmethod
    def from_csv(cls, path: str | Path) -> TerrainProfile:
        source = Path(path).resolve()
        rows: list[dict[str, str]] = []
        with source.open("r", encoding="utf-8", newline="") as handle:
            rows.extend(csv.DictReader(handle))
        if len(rows) < 2:
            raise ValueError(f"terrain profile has fewer than two rows: {source}")

        def column(name: str, default: float = 0.0) -> np.ndarray:
            return np.asarray(
                [float(row.get(name, default) or default) for row in rows],
                dtype=float,
            )

        profile = cls(
            distance_km=column("distance_km"),
            elevation_m=column("elevation_m"),
            latitude_deg=column("latitude_deg", np.nan),
            longitude_deg=column("longitude_deg", np.nan),
            zone_code=column("zone_code", 4).astype(int),
            clutter_height_m=column("clutter_height_m", 0.0),
            source_path=source,
        )
        return profile.repair_isolated_nodata()

    def repair_isolated_nodata(self) -> TerrainProfile:
        elevation = self.elevation_m.copy()
        invalid = ~np.isfinite(elevation)
        if np.any(invalid):
            valid_indices = np.flatnonzero(~invalid)
            if len(valid_indices) < 2:
                raise ValueError("terrain profile has insufficient valid elevations")
            elevation[invalid] = np.interp(
                np.flatnonzero(invalid), valid_indices, elevation[~invalid]
            )
        return self._replace(elevation_m=elevation)

    def resample_uniform(self, count: int | None = None) -> TerrainProfile:
        if count is None:
            count = len(self.distance_km)
        if count < 2:
            raise ValueError("resampled profile must contain at least two points")
        target = np.linspace(0.0, self.total_distance_km, count)
        nearest = np.searchsorted(self.distance_km, target, side="left")
        nearest = np.clip(nearest, 0, len(self.distance_km) - 1)
        return TerrainProfile(
            distance_km=target,
            elevation_m=np.interp(target, self.distance_km, self.elevation_m),
            latitude_deg=np.interp(target, self.distance_km, self.latitude_deg),
            longitude_deg=np.interp(target, self.distance_km, self.longitude_deg),
            zone_code=self.zone_code[nearest],
            clutter_height_m=np.interp(
                target, self.distance_km, self.clutter_height_m
            ),
            source_path=self.source_path,
        )

    def reverse(self) -> TerrainProfile:
        total = self.total_distance_km
        return TerrainProfile(
            distance_km=total - self.distance_km[::-1],
            elevation_m=self.elevation_m[::-1].copy(),
            latitude_deg=self.latitude_deg[::-1].copy(),
            longitude_deg=self.longitude_deg[::-1].copy(),
            zone_code=self.zone_code[::-1].copy(),
            clutter_height_m=self.clutter_height_m[::-1].copy(),
            source_path=self.source_path,
        )

    def fingerprint(self) -> str:
        digest = hashlib.sha256()
        for array in (
            self.distance_km,
            self.elevation_m,
            self.zone_code,
            self.clutter_height_m,
        ):
            digest.update(np.ascontiguousarray(array).tobytes())
        return digest.hexdigest()

    def _replace(self, **updates: np.ndarray) -> TerrainProfile:
        values = {
            "distance_km": self.distance_km,
            "elevation_m": self.elevation_m,
            "latitude_deg": self.latitude_deg,
            "longitude_deg": self.longitude_deg,
            "zone_code": self.zone_code,
            "clutter_height_m": self.clutter_height_m,
            "source_path": self.source_path,
        }
        values.update(updates)
        return TerrainProfile(**values)
