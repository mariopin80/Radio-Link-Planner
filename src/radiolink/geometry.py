from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from .domain import Project
from .geodesy import EARTH_MEAN_RADIUS_M, great_circle_distance_m, initial_bearing_deg
from .terrain import TerrainProfile


SPEED_OF_LIGHT_M_S = 299_792_458.0


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
    earth_bulge = profile_m * (total_m - profile_m) / (2.0 * effective_radius_m)
    start_asl = float(profile.elevation_m[0] + terminal_a.antenna_height_m)
    end_asl = float(profile.elevation_m[-1] + terminal_b.antenna_height_m)
    direct_ray = start_asl + (end_asl - start_asl) * profile_m / total_m
    apparent_terrain = (
        profile.elevation_m + profile.clutter_height_m + earth_bulge
    )
    clearance = direct_ray - apparent_terrain

    wavelength = SPEED_OF_LIGHT_M_S / (project.frequency_mhz * 1e6)
    fresnel = np.sqrt(
        wavelength * profile_m * (total_m - profile_m) / total_m
    )
    interior = np.arange(1, len(profile.distance_km) - 1)
    worst_index = int(interior[np.argmin(clearance[interior])])

    horizon_a_index = _horizon_index(
        distance_m=profile_m,
        terrain_m=profile.elevation_m + profile.clutter_height_m,
        terminal_height_asl_m=start_asl,
        effective_radius_m=effective_radius_m,
    )
    reverse_distance = total_m - profile_m[::-1]
    horizon_b_reverse_index = _horizon_index(
        distance_m=reverse_distance,
        terrain_m=(
            profile.elevation_m[::-1] + profile.clutter_height_m[::-1]
        ),
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
        maximum_earth_bulge_m=float(np.max(earth_bulge)),
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
    )
    arrays = GeometryArrays(
        distance_m=profile_m,
        direct_ray_m_asl=direct_ray,
        apparent_terrain_m_asl=apparent_terrain,
        earth_bulge_m=earth_bulge,
        fresnel_radius_m=fresnel,
        clearance_m=clearance,
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
