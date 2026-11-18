from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import IntEnum

import numpy as np

from .domain import MAX_EFFECTIVE_EARTH_K, MIN_EFFECTIVE_EARTH_K, Project
from .geodesy import EARTH_MEAN_RADIUS_M, great_circle_distance_m, initial_bearing_deg
from .i18n import tr
from .terrain import TerrainProfile


SPEED_OF_LIGHT_M_S = 299_792_458.0
CLEARANCE_TOLERANCE_M = 1e-8


class ClearanceClass(IntEnum):
    NO_PATH = 0
    FRESNEL_CLEAR = 1
    LINE_OF_SIGHT = 2
    OBSTRUCTED = 3


def validate_geometry_criteria(fresnel_percent: float, effective_earth_k: float) -> None:
    if not 0.0 <= fresnel_percent <= 100.0:
        raise ValueError(tr("A desobstrução de Fresnel deve estar entre 0 e 100%."))
    if not MIN_EFFECTIVE_EARTH_K < effective_earth_k <= MAX_EFFECTIVE_EARTH_K:
        raise ValueError(tr("O fator k deve ser maior que 0,1 e menor ou igual a 10."))


@dataclass(frozen=True)
class GeometryResult:
    geodesic_distance_km: float
    profile_distance_km: float
    distance_error_percent: float
    bearing_a_to_b_deg: float
    bearing_b_to_a_deg: float
    wavelength_m: float
    maximum_earth_bulge_m: float
    maximum_fresnel_radius_m: float
    worst_clearance_m: float
    worst_obstruction_m: float
    worst_obstruction_distance_km: float
    terrain_above_direct_ray_percent: float
    fresnel_60_obstructed_percent: float
    horizon_from_a_km: float
    horizon_from_b_km: float
    fresnel_percent: float
    effective_earth_k: float
    fresnel_obstructed_percent: float

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass(frozen=True)
class GeometryArrays:
    distance_m: np.ndarray
    direct_ray_m_asl: np.ndarray
    apparent_terrain_m_asl: np.ndarray
    earth_bulge_m: np.ndarray
    fresnel_radius_m: np.ndarray
    clearance_m: np.ndarray


def profile_geometry(
    distance_m: np.ndarray,
    terrain_m: np.ndarray,
    start_height_m: float,
    end_height_m: float,
    wavelength_m: float,
    effective_radius_m: float,
) -> GeometryArrays:
    total_m = float(distance_m[-1])
    distance_product = distance_m * (total_m - distance_m)
    earth_bulge = distance_product / (2.0 * effective_radius_m)
    direct_ray = start_height_m + (end_height_m - start_height_m) * distance_m / total_m
    apparent_terrain = terrain_m + earth_bulge
    fresnel = np.sqrt(wavelength_m * distance_product / total_m)
    return GeometryArrays(
        distance_m, direct_ray, apparent_terrain, earth_bulge, fresnel,
        direct_ray - apparent_terrain,
    )


def profile_clearance_class(arrays: GeometryArrays, fresnel_percent: float) -> ClearanceClass:
    clearance = arrays.clearance_m[1:-1] + CLEARANCE_TOLERANCE_M
    if np.any(clearance < 0.0):
        return ClearanceClass.OBSTRUCTED
    if np.any(clearance < (fresnel_percent / 100.0) * arrays.fresnel_radius_m[1:-1]):
        return ClearanceClass.LINE_OF_SIGHT
    return ClearanceClass.FRESNEL_CLEAR


def calculate_geometry(
    project: Project, profile: TerrainProfile
) -> tuple[GeometryResult, GeometryArrays]:
    terminal_a = project.terminal_a
    terminal_b = project.terminal_b
    geodesic_m = great_circle_distance_m(
        terminal_a.latitude_deg,
        terminal_a.longitude_deg,
        terminal_b.latitude_deg,
        terminal_b.longitude_deg,
    )
    profile_m = profile.distance_km * 1000.0
    total_m = float(profile_m[-1])
    distance_error_percent = 100.0 * (total_m - geodesic_m) / geodesic_m
    if abs(distance_error_percent) > 0.5:
        raise ValueError(
            "terrain profile distance differs from terminal geodesic distance "
            f"by {distance_error_percent:.3f}%"
        )

    effective_radius_m = (
        EARTH_MEAN_RADIUS_M * project.environment.effective_earth_k
    )
    start_asl = float(profile.elevation_m[0] + terminal_a.antenna_height_m)
    end_asl = float(profile.elevation_m[-1] + terminal_b.antenna_height_m)
    terrain_m = profile.elevation_m + profile.clutter_height_m
    wavelength = SPEED_OF_LIGHT_M_S / (project.frequency_mhz * 1e6)
    arrays = profile_geometry(
        profile_m, terrain_m, start_asl, end_asl, wavelength, effective_radius_m,
    )
    clearance = arrays.clearance_m
    fresnel = arrays.fresnel_radius_m
    worst_index = 1 + int(np.argmin(clearance[1:-1]))
    fresnel_percent = project.environment.fresnel_percent
    required_clearance = (fresnel_percent / 100.0) * fresnel[1:-1]

    horizon_a_index = _horizon_index(
        distance_m=profile_m,
        terrain_m=terrain_m,
        terminal_height_asl_m=start_asl,
        effective_radius_m=effective_radius_m,
    )
    reverse_distance = total_m - profile_m[::-1]
    horizon_b_reverse_index = _horizon_index(
        distance_m=reverse_distance,
        terrain_m=terrain_m[::-1],
        terminal_height_asl_m=end_asl,
        effective_radius_m=effective_radius_m,
    )
    horizon_b_distance_from_b_m = reverse_distance[horizon_b_reverse_index]

    result = GeometryResult(
        geodesic_distance_km=geodesic_m / 1000.0,
        profile_distance_km=total_m / 1000.0,
        distance_error_percent=distance_error_percent,
        bearing_a_to_b_deg=initial_bearing_deg(
            terminal_a.latitude_deg,
            terminal_a.longitude_deg,
            terminal_b.latitude_deg,
            terminal_b.longitude_deg,
        ),
        bearing_b_to_a_deg=initial_bearing_deg(
            terminal_b.latitude_deg,
            terminal_b.longitude_deg,
            terminal_a.latitude_deg,
            terminal_a.longitude_deg,
        ),
        wavelength_m=wavelength,
        maximum_earth_bulge_m=float(np.max(arrays.earth_bulge_m)),
        maximum_fresnel_radius_m=float(np.max(fresnel)),
        worst_clearance_m=float(clearance[worst_index]),
        worst_obstruction_m=float(max(0.0, -clearance[worst_index])),
        worst_obstruction_distance_km=float(profile.distance_km[worst_index]),
        terrain_above_direct_ray_percent=float(100.0 * np.mean(clearance < 0.0)),
        fresnel_60_obstructed_percent=float(
            100.0 * np.mean(clearance < 0.6 * fresnel)
        ),
        horizon_from_a_km=float(profile.distance_km[horizon_a_index]),
        horizon_from_b_km=float(horizon_b_distance_from_b_m / 1000.0),
        fresnel_percent=fresnel_percent,
        effective_earth_k=project.environment.effective_earth_k,
        fresnel_obstructed_percent=float(
            100.0 * np.mean(clearance[1:-1] + CLEARANCE_TOLERANCE_M < required_clearance)
        ),
    )
    return result, arrays


def _horizon_index(
    distance_m: np.ndarray,
    terrain_m: np.ndarray,
    terminal_height_asl_m: float,
    effective_radius_m: float,
) -> int:
    interior_distance = distance_m[1:]
    curvature = interior_distance**2 / (2.0 * effective_radius_m)
    elevation_angle = (
        terrain_m[1:] + curvature - terminal_height_asl_m
    ) / interior_distance
    return int(np.argmax(elevation_angle) + 1)
