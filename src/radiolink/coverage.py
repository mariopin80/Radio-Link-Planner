from __future__ import annotations

import json
import math
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .copernicus import sample_elevations
from .domain import (
    Direction,
    ModelSelection,
    Polarization,
    Project,
    ReceiverSpec,
    Terminal,
)
from .geodesy import destination_points
from .itu_data import ensure_itu_data
from .link_budget import watts_to_dbm
from .modes import MODE_PROFILES
from .propagation import P1812Model
from .propagation.base import ModelContext, ModelStatus
from .terrain import TerrainProfile

ProgressCallback = Callable[[str], None]

COVERAGE_RESOLUTION_PRESETS: dict[int, dict[str, int]] = {
    50: {"quick": 200, "recommended": 100, "detailed": 50},
    100: {"quick": 400, "recommended": 200, "detailed": 100},
    200: {"quick": 800, "recommended": 400, "detailed": 200},
    300: {"quick": 1200, "recommended": 600, "detailed": 300},
    400: {"quick": 1600, "recommended": 800, "detailed": 400},
    500: {"quick": 2000, "recommended": 1000, "detailed": 500},
}
COVERAGE_RESOLUTION_M: dict[int, int] = {
    radius: presets["recommended"]
    for radius, presets in COVERAGE_RESOLUTION_PRESETS.items()
}
RESOLUTION_PRESETS = frozenset({"quick", "recommended", "detailed", "custom"})
CONTOUR_LEVELS_DB = (0.0, 3.0, 6.0, 12.0)
DEFAULT_TERRAIN_STEP_M = 30.0


@dataclass(frozen=True)
class CoverageProgress:
    """Structured, monotonic progress for a coverage calculation."""

    overall_percent: float
    phase: str
    message: str
    completed: int = 0
    total: int = 0
    elapsed_seconds: float = 0.0
    remaining_seconds: float | None = None

    def __str__(self) -> str:
        return self.message


CoverageStateCallback = Callable[[CoverageProgress], None]


class CoverageCancelled(RuntimeError):
    """Raised after a direct-grid run has saved a resumable checkpoint."""

    def __init__(
        self,
        *,
        completed_cells: int,
        total_cells: int,
        checkpoint_directory: Path,
    ) -> None:
        self.completed_cells = completed_cells
        self.total_cells = total_cells
        self.checkpoint_directory = checkpoint_directory
        super().__init__(
            "Cálculo cancelado após "
            f"{completed_cells:,} de {total_cells:,} células. "
            "O progresso foi preservado para retomada."
        )


@dataclass(frozen=True)
class CoverageRequest:
    name: str
    latitude_deg: float
    longitude_deg: float
    frequency_mhz: float
    polarization: str
    mode: str
    radius_km: int
    transmitter_height_m: float
    transmitter_gain_dbi: float
    transmitter_line_loss_db: float
    transmitter_power_w: float
    receiver_height_m: float
    receiver_gain_dbi: float
    receiver_line_loss_db: float
    receiver_threshold_dbm: float
    output_directory: Path
    time_percentage: float = 50.0
    resolution_preset: str = "recommended"
    custom_resolution_m: int | None = None
    terrain_step_m: float = DEFAULT_TERRAIN_STEP_M

    @property
    def resolution_m(self) -> int:
        return coverage_resolution_m(
            self.radius_km,
            preset=self.resolution_preset,
            custom_resolution_m=self.custom_resolution_m,
        )

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("Informe um nome para a cobertura.")
        if not -80.0 <= self.latitude_deg <= 80.0:
            raise ValueError(
                "A latitude deve estar entre -80 e 80° para a P.1812."
            )
        if not -180.0 <= self.longitude_deg <= 180.0:
            raise ValueError("A longitude deve estar entre -180 e 180°.")
        if not 30.0 <= self.frequency_mhz <= 3000.0:
            raise ValueError(
                "A frequência deve estar entre 30 e 3000 MHz nesta versão VHF/UHF."
            )
        if self.polarization.lower() not in {"vertical", "horizontal"}:
            raise ValueError("Escolha uma polarização válida.")
        if self.mode.upper() not in MODE_PROFILES:
            raise ValueError("Escolha um modo de recepção válido.")
        if self.radius_km not in COVERAGE_RESOLUTION_PRESETS:
            raise ValueError("Escolha um dos raios de cobertura disponíveis.")
        if self.resolution_preset not in RESOLUTION_PRESETS:
            raise ValueError("Escolha uma resolução de cobertura válida.")
        if self.resolution_preset == "custom":
            if self.custom_resolution_m is None:
                raise ValueError("Informe a resolução personalizada.")
            if not 25 <= int(self.custom_resolution_m) <= 10_000:
                raise ValueError(
                    "A resolução personalizada deve estar entre 25 e 10.000 m."
                )
        if not 10.0 <= self.terrain_step_m <= 100.0:
            raise ValueError(
                "A amostragem do perfil deve estar entre 10 e 100 m."
            )
        if not 1.0 <= self.time_percentage <= 50.0:
            raise ValueError("A P.1812 aceita percentuais de tempo entre 1 e 50%.")
        heights = {
            "altura da antena transmissora": self.transmitter_height_m,
            "altura da antena receptora": self.receiver_height_m,
        }
        for label, value in heights.items():
            if value < 1.0 or value > 3000.0:
                raise ValueError(
                    f"A {label} deve estar entre 1 e 3.000 m "
                    "para a P.1812."
                )
        if self.transmitter_power_w <= 0.0:
            raise ValueError("A potência transmissora deve ser positiva.")
        for label, value in {
            "perda da linha transmissora": self.transmitter_line_loss_db,
            "perda da linha receptora": self.receiver_line_loss_db,
        }.items():
            if value < 0.0:
                raise ValueError(f"A {label} não pode ser negativa.")
        if not -200.0 <= self.receiver_threshold_dbm <= 0.0:
            raise ValueError("A sensibilidade deve estar entre -200 e 0 dBm.")


@dataclass(frozen=True)
class RadialCoverage:
    bearing_deg: float
    distance_m: np.ndarray
    latitude_deg: np.ndarray
    longitude_deg: np.ndarray
    elevation_m: np.ndarray
    margin_db: np.ndarray
    evaluated_point_count: int

    @property
    def coverage_reach_m(self) -> float:
        valid = np.flatnonzero(np.isfinite(self.margin_db) & (self.margin_db >= 0.0))
        return float(self.distance_m[valid[-1]]) if len(valid) else 0.0


@dataclass(frozen=True)
class CoverageOutcome:
    request: CoverageRequest
    radials: tuple[RadialCoverage, ...]
    paths: dict[str, Path]
    statistics: dict[str, Any]


def coverage_resolution_m(
    radius_km: int,
    *,
    preset: str = "recommended",
    custom_resolution_m: int | None = None,
) -> int:
    try:
        radius = int(radius_km)
        if preset == "custom":
            if custom_resolution_m is None:
                raise ValueError("custom resolution is required")
            resolution = int(custom_resolution_m)
            if not 25 <= resolution <= 10_000:
                raise ValueError("custom resolution outside supported range")
            return resolution
        return COVERAGE_RESOLUTION_PRESETS[radius][preset]
    except (KeyError, ValueError) as exc:
        raise ValueError(
            f"unsupported coverage resolution: radius={radius_km}, "
            f"preset={preset}"
        ) from exc


def run_coverage_analysis(
    request: CoverageRequest,
    progress: CoverageStateCallback | None = None,
    *,
    cancel_event: threading.Event | None = None,
    worker_count: int | None = None,
) -> CoverageOutcome:
    """Calculate direct P.1812 coverage at every metric-grid cell."""
    from .coverage_grid import run_direct_grid_coverage

    return run_direct_grid_coverage(
        request,
        progress=progress,
        cancel_event=cancel_event,
        worker_count=worker_count,
    )


def run_radial_coverage_analysis_legacy(
    request: CoverageRequest,
    progress: ProgressCallback | None = None,
) -> CoverageOutcome:
    """Retain the v0.3 radial engine only for controlled comparisons."""
    request.validate()
    destination = request.output_directory.expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    _notify(progress, "Cobertura: preparando os dados digitais da P.1812…")
    ensure_itu_data(
        include_p1812=True,
        include_p2001=False,
        cleanup_source_maps=True,
        progress=progress,
    )

    model = P1812Model()
    base_project = _base_project(request)
    radials: dict[float, RadialCoverage] = {}
    initial_bearings = np.arange(0.0, 360.0, 10.0)
    _notify(
        progress,
        "Cobertura: primeira passagem com 36 perfis radiais de 10°…",
    )
    for index, bearing in enumerate(initial_bearings, start=1):
        radial = _calculate_radial(
            request,
            float(bearing),
            base_project,
            model,
            progress,
        )
        radials[_bearing_key(bearing)] = radial
        _notify(
            progress,
            f"Cobertura: radial inicial {index}/{len(initial_bearings)} "
            f"({bearing:.1f}°).",
        )

    minimum_step, maximum_radials = _angular_limits(request.radius_km)
    pass_index = 0
    while len(radials) < maximum_radials:
        pass_index += 1
        candidates = angular_refinement_candidates(
            tuple(radials.values()),
            minimum_step_deg=minimum_step,
        )
        candidates = [
            item
            for item in candidates
            if _bearing_key(item[0]) not in radials
        ]
        if not candidates:
            break
        available = maximum_radials - len(radials)
        candidates = candidates[:available]
        _notify(
            progress,
            f"Cobertura: refinamento angular {pass_index}, "
            f"{len(candidates)} novos perfis…",
        )
        for index, (bearing, _) in enumerate(candidates, start=1):
            radial = _calculate_radial(
                request,
                bearing,
                base_project,
                model,
                progress,
            )
            radials[_bearing_key(bearing)] = radial
            if index % 8 == 0 or index == len(candidates):
                _notify(
                    progress,
                    f"Cobertura: refinamento {index}/{len(candidates)} "
                    f"({len(radials)} radiais no total).",
                )

    ordered = tuple(sorted(radials.values(), key=lambda item: item.bearing_deg))
    _notify(progress, "Cobertura: interpolando o raster final…")
    grid_path = destination / "coverage_margin_db.npy"
    grid, grid_metadata = interpolate_radials_to_grid(
        ordered,
        radius_km=request.radius_km,
        resolution_m=request.resolution_m,
        output_path=grid_path,
        progress=progress,
    )

    radial_path = destination / "coverage_radials.npz"
    _write_radials(radial_path, ordered)
    project_path = destination / "coverage_project.json"
    project_path.write_text(
        json.dumps(_request_dict(request), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    from .coverage_report import write_coverage_outputs

    report_paths, report_statistics = write_coverage_outputs(
        request=request,
        radials=ordered,
        grid=grid,
        grid_metadata=grid_metadata,
        output_directory=destination,
        progress=progress,
    )
    paths = {
        "project_json": project_path,
        "radials": radial_path,
        "margin_grid": grid_path,
        **report_paths,
    }
    evaluated = sum(item.evaluated_point_count for item in ordered)
    visual_cells = int(grid_metadata["valid_circle_cells"])
    statistics = {
        **grid_metadata,
        **report_statistics,
        "time_percentage": request.time_percentage,
        "radial_count": len(ordered),
        "physically_evaluated_points": evaluated,
        "visual_grid_cells": visual_cells,
        "interpolation_ratio": (
            visual_cells / evaluated if evaluated else float("inf")
        ),
    }
    metadata_path = destination / "coverage_metadata.json"
    metadata_path.write_text(
        json.dumps(statistics, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    paths["metadata"] = metadata_path
    _notify(progress, "Cobertura concluída: mapa de calor e contornos gerados.")
    return CoverageOutcome(
        request=request,
        radials=ordered,
        paths=paths,
        statistics=statistics,
    )


def _calculate_radial(
    request: CoverageRequest,
    bearing_deg: float,
    base_project: Project,
    model: P1812Model,
    progress: ProgressCallback | None,
) -> RadialCoverage:
    radius_m = request.radius_km * 1000.0
    count = round(radius_m / request.resolution_m) + 1
    distances = np.linspace(0.0, radius_m, count)
    latitudes, longitudes = destination_points(
        request.latitude_deg,
        request.longitude_deg,
        bearing_deg,
        distances,
    )
    _notify(progress, f"Terreno: amostrando radial {bearing_deg:.3f}°…")
    elevations = sample_elevations(
        latitudes,
        longitudes,
        progress=progress,
    )
    full_profile = TerrainProfile(
        distance_km=distances / 1000.0,
        elevation_m=elevations,
        latitude_deg=latitudes,
        longitude_deg=longitudes,
        zone_code=np.full(count, 4, dtype=int),
        clutter_height_m=np.zeros(count, dtype=float),
    )
    margins, evaluated_count = _adaptive_margin_profile(
        request,
        full_profile,
        base_project,
        model,
    )
    return RadialCoverage(
        bearing_deg=_bearing_key(bearing_deg),
        distance_m=distances,
        latitude_deg=latitudes,
        longitude_deg=longitudes,
        elevation_m=elevations,
        margin_db=margins,
        evaluated_point_count=evaluated_count,
    )


def _adaptive_margin_profile(
    request: CoverageRequest,
    profile: TerrainProfile,
    base_project: Project,
    model: P1812Model,
) -> tuple[np.ndarray, int]:
    count = len(profile.distance_km)
    start_index = min(
        count - 1,
        max(1, math.ceil(1000.0 / max(profile.nominal_step_m, 1.0))),
    )
    cache: dict[int, float] = {}
    maximum_evaluations = min(700, count)
    minimum_interval_m = max(4.0 * profile.nominal_step_m, 500.0)
    maximum_interval_m = 20_000.0

    def evaluate(index: int) -> float:
        if index in cache:
            return cache[index]
        partial = _profile_prefix(profile, index)
        receiver = base_project.terminal_b.model_copy(
            update={
                "latitude_deg": float(profile.latitude_deg[index]),
                "longitude_deg": float(profile.longitude_deg[index]),
            }
        )
        project = base_project.model_copy(update={"terminal_b": receiver})
        evaluation = model.evaluate(
            ModelContext(
                project=project,
                profile=partial,
                direction=Direction.A_TO_B,
            ),
            request.time_percentage,
        )
        if evaluation.status is not ModelStatus.OK or evaluation.loss_db is None:
            value = float("nan")
        else:
            value = _margin_from_loss(request, float(evaluation.loss_db))
        cache[index] = value
        return value

    evaluate(start_index)
    evaluate(count - 1)
    pending: list[tuple[int, int]] = [(start_index, count - 1)]
    while pending and len(cache) < maximum_evaluations:
        left, right = pending.pop()
        if right - left <= 1:
            continue
        middle = (left + right) // 2
        left_margin = evaluate(left)
        right_margin = evaluate(right)
        middle_margin = evaluate(middle)
        span_m = float(
            (profile.distance_km[right] - profile.distance_km[left]) * 1000.0
        )
        if span_m <= minimum_interval_m:
            continue
        terrain = profile.elevation_m[left : right + 1]
        terrain_line = np.linspace(terrain[0], terrain[-1], len(terrain))
        terrain_departure_m = float(np.max(np.abs(terrain - terrain_line)))
        values = np.asarray([left_margin, middle_margin, right_margin], dtype=float)
        finite = np.all(np.isfinite(values))
        nonlinear_db = (
            abs(middle_margin - 0.5 * (left_margin + right_margin))
            if finite
            else float("inf")
        )
        crosses_boundary = (
            finite and float(np.min(values)) <= 0.0 <= float(np.max(values))
        )
        near_important_contour = finite and any(
            float(np.min(np.abs(values - level))) <= 2.0
            for level in CONTOUR_LEVELS_DB
        )
        needs_refinement = (
            span_m > maximum_interval_m
            or terrain_departure_m > 35.0
            or nonlinear_db > 1.5
            or crosses_boundary
            or near_important_contour
        )
        if needs_refinement:
            pending.append((middle, right))
            pending.append((left, middle))

    valid = sorted(index for index, value in cache.items() if np.isfinite(value))
    if len(valid) < 2:
        raise RuntimeError(
            "A P.1812 não produziu pontos suficientes neste perfil radial."
        )
    target = np.arange(count)
    margins = np.interp(
        target,
        np.asarray(valid, dtype=float),
        np.asarray([cache[index] for index in valid], dtype=float),
    )
    margins[:start_index] = margins[start_index]
    return margins, len(cache)


def angular_refinement_candidates(
    radials: tuple[RadialCoverage, ...],
    *,
    minimum_step_deg: float,
) -> list[tuple[float, float]]:
    """Return midpoint bearings ranked by terrain/margin discontinuity."""
    if len(radials) < 2:
        return []
    ordered = sorted(radials, key=lambda item: item.bearing_deg)
    candidates: list[tuple[float, float]] = []
    for index, left in enumerate(ordered):
        right = ordered[(index + 1) % len(ordered)]
        span = (right.bearing_deg - left.bearing_deg) % 360.0
        if span <= minimum_step_deg + 1e-9:
            continue
        score = _radial_discontinuity_score(left, right)
        if score < 1.0:
            continue
        midpoint = (left.bearing_deg + span / 2.0) % 360.0
        candidates.append((_bearing_key(midpoint), score))
    candidates.sort(key=lambda item: item[1], reverse=True)
    return candidates


def _radial_discontinuity_score(
    left: RadialCoverage,
    right: RadialCoverage,
) -> float:
    if len(left.margin_db) != len(right.margin_db):
        raise ValueError("radials must share the same distance grid")
    start = max(1, round(1000.0 / max(left.distance_m[1], 1.0)))
    margin_left = left.margin_db[start:]
    margin_right = right.margin_db[start:]
    difference = np.abs(margin_left - margin_right)
    margin_p90 = float(np.nanpercentile(difference, 90.0))
    sign_disagreement = float(
        np.mean((margin_left >= 0.0) != (margin_right >= 0.0))
    )
    reach_difference = abs(left.coverage_reach_m - right.coverage_reach_m)
    radius_m = float(left.distance_m[-1])
    angular_span_rad = math.radians(
        (right.bearing_deg - left.bearing_deg) % 360.0
    )
    lateral_separation = np.maximum(
        500.0,
        2.0
        * left.distance_m[start:]
        * math.sin(min(angular_span_rad, 2.0 * math.pi - angular_span_rad) / 2.0),
    )
    terrain_gradient = float(
        np.nanpercentile(
            np.abs(left.elevation_m[start:] - right.elevation_m[start:])
            / lateral_separation,
            90.0,
        )
    )
    return max(
        margin_p90 / 6.0,
        sign_disagreement / 0.08,
        reach_difference / max(3000.0, radius_m * 0.03),
        terrain_gradient / 0.12,
    )


def interpolate_radials_to_grid(
    radials: tuple[RadialCoverage, ...],
    *,
    radius_km: int,
    resolution_m: int,
    output_path: str | Path,
    progress: ProgressCallback | None = None,
) -> tuple[np.memmap, dict[str, Any]]:
    """Bilinearly interpolate polar radials into a local square raster."""
    if len(radials) < 2:
        raise ValueError("at least two radials are required")
    ordered = sorted(radials, key=lambda item: item.bearing_deg)
    expected_count = round(radius_km * 1000.0 / resolution_m) + 1
    if any(len(item.margin_db) != expected_count for item in ordered):
        raise ValueError("radial distance grids do not match the requested raster")

    bearings = np.asarray([item.bearing_deg for item in ordered], dtype=float)
    margin = np.vstack([item.margin_db for item in ordered]).astype(np.float32)
    wrapped_bearings = np.concatenate([bearings, [bearings[0] + 360.0]])
    wrapped_margin = np.vstack([margin, margin[0]])
    radius_m = radius_km * 1000.0
    dimension = 2 * round(radius_m / resolution_m) + 1
    destination = Path(output_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    grid = np.lib.format.open_memmap(
        destination,
        mode="w+",
        dtype=np.float32,
        shape=(dimension, dimension),
    )
    coordinates = (
        np.arange(dimension, dtype=np.float64) - (dimension - 1) / 2.0
    ) * resolution_m
    distance_grid = ordered[0].distance_m
    chunk_rows = 128
    valid_circle_cells = 0
    for row_start in range(0, dimension, chunk_rows):
        row_stop = min(dimension, row_start + chunk_rows)
        north = coordinates[::-1][row_start:row_stop, None]
        east = coordinates[None, :]
        distances = np.hypot(east, north)
        bearings_grid = (np.degrees(np.arctan2(east, north)) + 360.0) % 360.0

        angular_right = np.searchsorted(
            wrapped_bearings,
            bearings_grid,
            side="right",
        )
        angular_right = np.clip(angular_right, 1, len(wrapped_bearings) - 1)
        angular_left = angular_right - 1
        bearing_left = wrapped_bearings[angular_left]
        bearing_right = wrapped_bearings[angular_right]
        angular_fraction = (bearings_grid - bearing_left) / (
            bearing_right - bearing_left
        )

        radial_right = np.searchsorted(distance_grid, distances, side="right")
        radial_right = np.clip(radial_right, 1, len(distance_grid) - 1)
        radial_left = radial_right - 1
        distance_left = distance_grid[radial_left]
        distance_right = distance_grid[radial_right]
        radial_fraction = (distances - distance_left) / (
            distance_right - distance_left
        )

        lower_left = wrapped_margin[angular_left, radial_left]
        lower_right = wrapped_margin[angular_right, radial_left]
        upper_left = wrapped_margin[angular_left, radial_right]
        upper_right = wrapped_margin[angular_right, radial_right]
        at_left_angle = lower_left + radial_fraction * (upper_left - lower_left)
        at_right_angle = lower_right + radial_fraction * (
            upper_right - lower_right
        )
        values = at_left_angle + angular_fraction * (
            at_right_angle - at_left_angle
        )
        inside_circle = distances <= radius_m
        valid_circle_cells += int(np.count_nonzero(inside_circle))
        values[~inside_circle] = np.nan
        grid[row_start:row_stop] = values.astype(np.float32)
        if row_start % (chunk_rows * 8) == 0:
            percent = 100.0 * row_stop / dimension
            _notify(progress, f"Cobertura: raster interpolado {percent:.0f}%…")
    grid.flush()
    return grid, {
        "radius_km": radius_km,
        "resolution_m": resolution_m,
        "grid_width": dimension,
        "grid_height": dimension,
        "square_grid_cells": dimension * dimension,
        "valid_circle_cells": valid_circle_cells,
        "model": "ITU-R P.1812-8",
    }


def _base_project(request: CoverageRequest) -> Project:
    receiver_spec = ReceiverSpec(
        noise_figure_db=6.0,
        external_noise_db=0.0,
        threshold_overrides_dbm={
            request.mode.upper(): request.receiver_threshold_dbm,
        },
    )
    transmitter = Terminal(
        name="Transmissor",
        latitude_deg=request.latitude_deg,
        longitude_deg=request.longitude_deg,
        antenna_height_m=request.transmitter_height_m,
        antenna_gain_dbi=request.transmitter_gain_dbi,
        line_loss_db=request.transmitter_line_loss_db,
        tx_power_w=request.transmitter_power_w,
    )
    receiver_latitudes, receiver_longitudes = destination_points(
        request.latitude_deg,
        request.longitude_deg,
        0.0,
        np.asarray([1000.0]),
    )
    receiver = Terminal(
        name="Receptor móvel",
        latitude_deg=float(receiver_latitudes[0]),
        longitude_deg=float(receiver_longitudes[0]),
        antenna_height_m=request.receiver_height_m,
        antenna_gain_dbi=request.receiver_gain_dbi,
        line_loss_db=request.receiver_line_loss_db,
        tx_power_w=1.0,
        receiver=receiver_spec,
    )
    return Project(
        schema_version="0.3",
        name=request.name,
        frequency_mhz=request.frequency_mhz,
        polarization=Polarization(request.polarization.lower()),
        primary_mode=request.mode.upper(),
        target_availability_percent=request.time_percentage,
        terminal_a=transmitter,
        terminal_b=receiver,
        terrain_profile="adaptive-radial-coverage",
        terrain_source="Copernicus GLO-30 automático",
        terrain_resolution_m=float(request.resolution_m),
        clutter_included=False,
        models=ModelSelection(itm=False, p1812=True, p2001=False),
        metadata={
            "coverage_method": "adaptive_radial",
            "coverage_interpolated": True,
            "terrain_zone_assumption": "all_inland_land",
        },
    )


def _profile_prefix(profile: TerrainProfile, endpoint_index: int) -> TerrainProfile:
    stop = endpoint_index + 1
    return TerrainProfile(
        distance_km=profile.distance_km[:stop],
        elevation_m=profile.elevation_m[:stop],
        latitude_deg=profile.latitude_deg[:stop],
        longitude_deg=profile.longitude_deg[:stop],
        zone_code=profile.zone_code[:stop],
        clutter_height_m=profile.clutter_height_m[:stop],
    )


def _margin_from_loss(request: CoverageRequest, loss_db: float) -> float:
    received_power_dbm = (
        watts_to_dbm(request.transmitter_power_w)
        + request.transmitter_gain_dbi
        - request.transmitter_line_loss_db
        - loss_db
        + request.receiver_gain_dbi
        - request.receiver_line_loss_db
    )
    return received_power_dbm - request.receiver_threshold_dbm


def _angular_limits(radius_km: int) -> tuple[float, int]:
    if radius_km <= 200:
        return 0.625, 576
    return 1.25, 288


def _write_radials(path: Path, radials: tuple[RadialCoverage, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        bearings_deg=np.asarray([item.bearing_deg for item in radials]),
        distance_m=radials[0].distance_m,
        elevation_m=np.vstack([item.elevation_m for item in radials]),
        margin_db=np.vstack([item.margin_db for item in radials]),
        evaluated_point_count=np.asarray(
            [item.evaluated_point_count for item in radials],
            dtype=int,
        ),
    )


def _request_dict(request: CoverageRequest) -> dict[str, Any]:
    data = asdict(request)
    data["output_directory"] = str(request.output_directory)
    data["resolution_m"] = request.resolution_m
    data["model"] = "ITU-R P.1812-8"
    data["contour_levels_db"] = list(CONTOUR_LEVELS_DB)
    return data


def _bearing_key(value: float) -> float:
    return round(float(value) % 360.0, 6)


def _notify(progress: ProgressCallback | None, message: str) -> None:
    if progress is not None:
        progress(message)
