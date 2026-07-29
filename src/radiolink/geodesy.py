from __future__ import annotations

import math

import numpy as np


EARTH_MEAN_RADIUS_M = 6_371_008.8


def great_circle_distance_m(
    latitude_1_deg: float,
    longitude_1_deg: float,
    latitude_2_deg: float,
    longitude_2_deg: float,
) -> float:
    lat1 = math.radians(latitude_1_deg)
    lat2 = math.radians(latitude_2_deg)
    dlat = lat2 - lat1
    dlon = math.radians(longitude_2_deg - longitude_1_deg)
    a = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2.0) ** 2
    )
    return 2.0 * EARTH_MEAN_RADIUS_M * math.asin(math.sqrt(a))


def initial_bearing_deg(
    latitude_1_deg: float,
    longitude_1_deg: float,
    latitude_2_deg: float,
    longitude_2_deg: float,
) -> float:
    lat1 = math.radians(latitude_1_deg)
    lat2 = math.radians(latitude_2_deg)
    dlon = math.radians(longitude_2_deg - longitude_1_deg)
    y = math.sin(dlon) * math.cos(lat2)
    x = (
        math.cos(lat1) * math.sin(lat2)
        - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    )
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def great_circle_points(
    latitude_1_deg: float,
    longitude_1_deg: float,
    latitude_2_deg: float,
    longitude_2_deg: float,
    count: int,
) -> tuple[np.ndarray, np.ndarray]:
    if count < 2:
        raise ValueError("count must be at least two")

    def unit_vector(lat_deg: float, lon_deg: float) -> np.ndarray:
        lat = math.radians(lat_deg)
        lon = math.radians(lon_deg)
        return np.array(
            [
                math.cos(lat) * math.cos(lon),
                math.cos(lat) * math.sin(lon),
                math.sin(lat),
            ]
        )

    start = unit_vector(latitude_1_deg, longitude_1_deg)
    end = unit_vector(latitude_2_deg, longitude_2_deg)
    omega = math.acos(float(np.clip(np.dot(start, end), -1.0, 1.0)))
    if omega == 0.0:
        return (
            np.full(count, latitude_1_deg),
            np.full(count, longitude_1_deg),
        )
    fractions = np.linspace(0.0, 1.0, count)
    denominator = math.sin(omega)
    vectors = (
        np.sin((1.0 - fractions) * omega)[:, None] / denominator * start
        + np.sin(fractions * omega)[:, None] / denominator * end
    )
    latitudes = np.degrees(
        np.arctan2(vectors[:, 2], np.hypot(vectors[:, 0], vectors[:, 1]))
    )
    longitudes = np.degrees(np.arctan2(vectors[:, 1], vectors[:, 0]))
    return latitudes, longitudes
