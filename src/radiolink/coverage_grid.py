from __future__ import annotations

import gc
import hashlib
import importlib.metadata
import json
import math
import multiprocessing
import os
import platform
import sys
import threading
import time
from collections.abc import Iterator
from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor, wait
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from .copernicus import (
    default_cache_directory,
    download_tile,
    sample_elevations,
    tile_code,
)
from .coverage import (
    CONTOUR_LEVELS_DB,
    CoverageCancelled,
    CoverageOutcome,
    CoverageProgress,
    CoverageRequest,
    CoverageStateCallback,
)
from .geodesy import destination_point, destination_points
from .itu_data import (
    P1812_PRODUCT,
    ensure_itu_data,
    load_digital_product_module,
    product_data_directory,
)
from .link_budget import watts_to_dbm

DIRECT_GRID_ENGINE_VERSION = "1"
GRID_PROJECTION = "spherical azimuthal equidistant"
GRID_BLOCK_SIZE = 16
MINIMUM_P1812_DISTANCE_M = 250.0
MAXIMUM_WORKERS = 12
PERFORMANCE_HISTORY_LIMIT = 12
DEFAULT_WORK_UNITS_PER_SECOND_PER_WORKER = 55_000.0
CELL_OVERHEAD_WORK_UNITS = 667.0


@dataclass(frozen=True)
class CoverageEstimate:
    resolution_m: int
    grid_width: int
    grid_height: int
    valid_circle_cells: int
    p1812_cells: int
    short_range_cells: int
    estimated_profile_points: int
    estimated_seconds_low: float
    estimated_seconds_high: float
    estimated_memory_mb: float
    worker_count: int
    terrain_tile_count: int
    uncached_terrain_tile_count: int
    resumable_cells: int = 0

    @property
    def warning_level(self) -> str:
        if self.estimated_seconds_high > 30.0 * 60.0:
            return "red"
        if self.estimated_seconds_high > 10.0 * 60.0:
            return "yellow"
        return "normal"


@dataclass(frozen=True)
class GridBlockSpec:
    block_id: int
    row_start: int
    row_stop: int
    column_start: int
    column_stop: int


@dataclass(frozen=True)
class GridBlockResult:
    block_id: int
    row_start: int
    row_stop: int
    column_start: int
    column_stop: int
    margin_db: np.ndarray
    calculated_cells: int
    profile_points: int
    p1812_cells: int
    short_range_cells: int
    failed_cells: int
    elapsed_seconds: float
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class _WorkerConfiguration:
    latitude_deg: float
    longitude_deg: float
    radius_m: float
    resolution_m: int
    dimension: int
    terrain_step_m: float
    frequency_mhz: float
    time_percentage: float
    polarization_code: int
    transmitter_height_m: float
    transmitter_power_dbm: float
    transmitter_gain_dbi: float
    transmitter_line_loss_db: float
    receiver_height_m: float
    receiver_gain_dbi: float
    receiver_line_loss_db: float
    receiver_threshold_dbm: float


@dataclass(frozen=True)
class _CheckpointPaths:
    directory: Path
    metadata: Path
    grid: Path
    completed: Path
    block_statistics: Path


class _ProgressTracker:
    def __init__(self, callback: CoverageStateCallback | None) -> None:
        self.callback = callback
        self.started = time.monotonic()
        self.last_percent = 0.0

    def emit(
        self,
        overall_percent: float,
        phase: str,
        message: str,
        *,
        completed: int = 0,
        total: int = 0,
        remaining_seconds: float | None = None,
    ) -> None:
        percent = min(100.0, max(self.last_percent, float(overall_percent)))
        self.last_percent = percent
        if self.callback is None:
            return
        self.callback(
            CoverageProgress(
                overall_percent=percent,
                phase=phase,
                message=message,
                completed=completed,
                total=total,
                elapsed_seconds=time.monotonic() - self.started,
                remaining_seconds=remaining_seconds,
            )
        )


_WORKER_CONFIGURATION: _WorkerConfiguration | None = None
_WORKER_P1812: Any | None = None
_WORKER_CANCEL_EVENT: Any | None = None


def default_worker_count() -> int:
    available = os.cpu_count() or 2
    return max(1, min(MAXIMUM_WORKERS, available - 1 if available > 2 else 1))


def coverage_grid_dimension(radius_km: int, resolution_m: int) -> int:
    if radius_km <= 0 or resolution_m <= 0:
        raise ValueError("radius and resolution must be positive")
    return 2 * round(radius_km * 1000.0 / resolution_m) + 1


def coverage_circle_cell_count(radius_km: int, resolution_m: int) -> int:
    """Count cell centres inside the metric circle without allocating a grid."""
    radius_m = radius_km * 1000.0
    half = round(radius_m / resolution_m)
    total = 0
    for north_index in range(-half, half + 1):
        north_m = north_index * resolution_m
        east_limit = math.sqrt(max(0.0, radius_m**2 - north_m**2))
        total += 2 * math.floor(east_limit / resolution_m + 1e-9) + 1
    return total


def estimate_coverage(
    request: CoverageRequest,
    *,
    worker_count: int | None = None,
) -> CoverageEstimate:
    request.validate()
    workers = _validated_worker_count(worker_count)
    resolution = request.resolution_m
    dimension = coverage_grid_dimension(request.radius_km, resolution)
    valid_cells = coverage_circle_cell_count(request.radius_km, resolution)
    short_range_radius_cells = MINIMUM_P1812_DISTANCE_M / resolution
    short_range_cells = min(
        valid_cells,
        max(1, round(math.pi * short_range_radius_cells**2)),
    )
    p1812_cells = max(0, valid_cells - short_range_cells)
    average_distance_m = 2.0 * request.radius_km * 1000.0 / 3.0
    average_profile_points = max(
        2.0,
        average_distance_m / request.terrain_step_m + 1.0,
    )
    profile_points = round(p1812_cells * average_profile_points)
    work_units = profile_points + valid_cells * CELL_OVERHEAD_WORK_UNITS
    work_rate = _historical_work_rate(workers)
    compute_seconds = work_units / max(work_rate, 1.0)

    codes = coverage_terrain_tile_codes(request)
    cache = default_cache_directory()
    uncached = sum(
        1
        for code in codes
        if not _valid_cached_tile(cache / f"{code}.tif")
    )
    download_low = uncached * 12.0
    download_high = uncached * 60.0
    fixed_seconds = 20.0
    square_cells = dimension * dimension
    maximum_profile_points = (
        request.radius_km * 1000.0 / request.terrain_step_m + 1.0
    )
    grid_and_render_bytes = square_cells * 4.0 * 8.0
    worker_profile_bytes = workers * maximum_profile_points * 8.0 * 7.0
    fixed_runtime_bytes = (250.0 + workers * 120.0) * 1024.0**2
    memory_mb = (
        grid_and_render_bytes + worker_profile_bytes + fixed_runtime_bytes
    ) / 1024.0**2

    resumable = _resumable_cell_count(request)
    fraction_remaining = max(0.0, 1.0 - resumable / valid_cells)
    low = (
        fixed_seconds
        + download_low
        + 0.70 * compute_seconds * fraction_remaining
    )
    high = (
        fixed_seconds
        + download_high
        + 1.45 * compute_seconds * fraction_remaining
    )

    return CoverageEstimate(
        resolution_m=resolution,
        grid_width=dimension,
        grid_height=dimension,
        valid_circle_cells=valid_cells,
        p1812_cells=p1812_cells,
        short_range_cells=short_range_cells,
        estimated_profile_points=profile_points,
        estimated_seconds_low=low,
        estimated_seconds_high=high,
        estimated_memory_mb=memory_mb,
        worker_count=workers,
        terrain_tile_count=len(codes),
        uncached_terrain_tile_count=uncached,
        resumable_cells=resumable,
    )


def format_duration(seconds: float | None) -> str:
    if seconds is None or not math.isfinite(seconds):
        return "calculando…"
    value = max(0, round(seconds))
    hours, remainder = divmod(value, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours} h {minutes:02d} min"
    if minutes:
        return f"{minutes} min {secs:02d} s"
    return f"{secs} s"


def available_memory_bytes() -> int | None:
    if os.name == "nt":
        try:
            import ctypes

            class MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("length", ctypes.c_ulong),
                    ("memory_load", ctypes.c_ulong),
                    ("total_physical", ctypes.c_ulonglong),
                    ("available_physical", ctypes.c_ulonglong),
                    ("total_page_file", ctypes.c_ulonglong),
                    ("available_page_file", ctypes.c_ulonglong),
                    ("total_virtual", ctypes.c_ulonglong),
                    ("available_virtual", ctypes.c_ulonglong),
                    ("available_extended_virtual", ctypes.c_ulonglong),
                ]

            status = MemoryStatus()
            status.length = ctypes.sizeof(status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.available_physical)
        except Exception:
            return None
    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        available_pages = os.sysconf("SC_AVPHYS_PAGES")
        return int(page_size * available_pages)
    except (AttributeError, OSError, ValueError):
        return None


def coverage_request_fingerprint(request: CoverageRequest) -> str:
    payload = _request_payload(request, include_output_directory=False)
    payload["engine_version"] = DIRECT_GRID_ENGINE_VERSION
    payload["model_implementation_version"] = _p1812_version()
    encoded = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def coverage_terrain_tile_codes(request: CoverageRequest) -> tuple[str, ...]:
    """Return the GLO-30 tiles in the circle's conservative bounding box."""
    radius_m = request.radius_km * 1000.0
    bearings = np.arange(0.0, 360.0, 5.0)
    latitudes = [request.latitude_deg]
    longitude_deltas = [0.0]
    for bearing in bearings:
        latitude, longitude = destination_point(
            request.latitude_deg,
            request.longitude_deg,
            float(bearing),
            radius_m,
        )
        latitudes.append(latitude)
        longitude_deltas.append(
            ((longitude - request.longitude_deg + 180.0) % 360.0) - 180.0
        )
    latitude_start = math.floor(min(latitudes))
    latitude_stop = math.floor(max(latitudes))
    longitude_start = math.floor(
        request.longitude_deg + min(longitude_deltas)
    )
    longitude_stop = math.floor(
        request.longitude_deg + max(longitude_deltas)
    )
    codes: set[str] = set()
    for latitude_floor in range(latitude_start, latitude_stop + 1):
        for longitude_floor in range(longitude_start, longitude_stop + 1):
            normalized_longitude = (
                (longitude_floor + 0.5 + 180.0) % 360.0
            ) - 180.0
            codes.add(tile_code(latitude_floor + 0.5, normalized_longitude))
    return tuple(sorted(codes))


def run_direct_grid_coverage(
    request: CoverageRequest,
    *,
    progress: CoverageStateCallback | None = None,
    cancel_event: threading.Event | None = None,
    worker_count: int | None = None,
) -> CoverageOutcome:
    request.validate()
    _validate_coverage_extent(request)
    workers = _validated_worker_count(worker_count)
    external_cancel = cancel_event or threading.Event()
    tracker = _ProgressTracker(progress)
    destination = request.output_directory.expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    estimate = estimate_coverage(request, worker_count=workers)
    fingerprint = coverage_request_fingerprint(request)
    blocks = tuple(
        _iter_grid_blocks(
            request.radius_km,
            request.resolution_m,
            GRID_BLOCK_SIZE,
        )
    )
    checkpoint = _checkpoint_paths(request, fingerprint)
    grid, completed, block_statistics, resumed = _open_checkpoint(
        request,
        fingerprint,
        blocks,
        checkpoint,
    )
    completed_cells = int(np.sum(block_statistics[completed, 0]))
    if resumed:
        try:
            existing_metadata = json.loads(
                checkpoint.metadata.read_text(encoding="utf-8")
            )
            resume_count = int(existing_metadata.get("resumed_runs", 0)) + 1
            previous_compute_seconds = float(
                existing_metadata.get("accumulated_compute_seconds", 0.0)
            )
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            resume_count = 1
            previous_compute_seconds = 0.0
    else:
        resume_count = 0
        previous_compute_seconds = 0.0
    _update_checkpoint_metadata(
        request,
        fingerprint,
        blocks,
        checkpoint,
        completed_cells=completed_cells,
        resumed_runs=resume_count,
        accumulated_compute_seconds=previous_compute_seconds,
    )

    tracker.emit(
        0.0,
        "prepare",
        "0% — Preparando os dados científicos da P.1812…",
    )
    if external_cancel.is_set():
        _raise_cancelled(completed_cells, estimate.valid_circle_cells, checkpoint)
    try:
        ensure_itu_data(
            include_p1812=True,
            include_p2001=False,
            cleanup_source_maps=True,
            progress=lambda message: tracker.emit(
                2.0,
                "prepare",
                f"2% — P.1812: {message}",
            ),
            cancel_check=external_cancel.is_set,
        )
    except InterruptedError:
        _raise_cancelled(
            completed_cells,
            estimate.valid_circle_cells,
            checkpoint,
        )

    terrain_codes = coverage_terrain_tile_codes(request)
    cache = default_cache_directory()
    for index, code in enumerate(terrain_codes, start=1):
        if external_cancel.is_set():
            _raise_cancelled(
                completed_cells,
                estimate.valid_circle_cells,
                checkpoint,
            )
        base_percent = 2.0 + 6.0 * (index - 1) / max(len(terrain_codes), 1)
        try:
            download_tile(
                code,
                cache_dir=cache,
                progress=lambda message, value=base_percent: tracker.emit(
                    value,
                    "terrain",
                    f"{value:.0f}% — {message}",
                ),
                cancel_check=external_cancel.is_set,
            )
        except InterruptedError:
            _raise_cancelled(
                completed_cells,
                estimate.valid_circle_cells,
                checkpoint,
            )
        tile_percent = 2.0 + 6.0 * index / max(len(terrain_codes), 1)
        tracker.emit(
            tile_percent,
            "terrain",
            f"{tile_percent:.0f}% — Terreno: bloco {index}/"
            f"{len(terrain_codes)} pronto.",
            completed=index,
            total=len(terrain_codes),
        )

    pending = [spec for spec in blocks if not bool(completed[spec.block_id])]
    if resumed and completed_cells:
        tracker.emit(
            10.0 + 80.0 * completed_cells / estimate.valid_circle_cells,
            "cells",
            "Retomando cobertura: "
            f"{completed_cells:,} de {estimate.valid_circle_cells:,} "
            "células já estavam concluídas.",
            completed=completed_cells,
            total=estimate.valid_circle_cells,
            remaining_seconds=estimate.estimated_seconds_high,
        )
    else:
        tracker.emit(
            10.0,
            "cells",
            "10% — Grade direta preparada; iniciando as células P.1812.",
            completed=0,
            total=estimate.valid_circle_cells,
            remaining_seconds=estimate.estimated_seconds_high,
        )

    compute_started = time.monotonic()
    session_start_cells = completed_cells
    session_profile_points = 0
    configuration = _worker_configuration(request, estimate.grid_width)
    # Keep neighbouring endpoints close in the queue so each worker can reuse
    # opened GeoTIFF datasets and their internal raster blocks.
    ordered_pending = pending

    def accept_result(result: GridBlockResult) -> None:
        nonlocal completed_cells, session_profile_points
        if external_cancel.is_set():
            return
        if result.failed_cells:
            details = "; ".join(result.errors) or "erro numérico não especificado"
            raise RuntimeError(
                "A P.1812 não produziu resultado para "
                f"{result.failed_cells} célula(s) do bloco "
                f"{result.block_id}. O bloco não foi marcado como concluído "
                f"e poderá ser reprocessado. Detalhes: {details}"
            )
        grid[
            result.row_start : result.row_stop,
            result.column_start : result.column_stop,
        ] = result.margin_db
        grid.flush()
        block_statistics[result.block_id] = (
            result.calculated_cells,
            result.profile_points,
            result.p1812_cells,
            result.short_range_cells,
            result.failed_cells,
            round(result.elapsed_seconds * 1000.0),
        )
        block_statistics.flush()
        completed[result.block_id] = True
        completed.flush()
        completed_cells += result.calculated_cells
        session_profile_points += result.profile_points
        _update_checkpoint_metadata(
            request,
            fingerprint,
            blocks,
            checkpoint,
            completed_cells=completed_cells,
            resumed_runs=resume_count,
            accumulated_compute_seconds=(
                previous_compute_seconds
                + max(0.0, time.monotonic() - compute_started)
            ),
        )
        session_cells = completed_cells - session_start_cells
        elapsed = max(0.001, time.monotonic() - compute_started)
        observed_rate = session_cells / elapsed if session_cells else 0.0
        remaining = (
            (estimate.valid_circle_cells - completed_cells) / observed_rate
            if observed_rate > 0.0
            else estimate.estimated_seconds_high
        )
        overall = 10.0 + 80.0 * min(
            1.0,
            completed_cells / estimate.valid_circle_cells,
        )
        tracker.emit(
            overall,
            "cells",
            f"{overall:.0f}% — Calculando células: "
            f"{completed_cells:,} de {estimate.valid_circle_cells:,} • "
            f"restante {format_duration(remaining)}",
            completed=completed_cells,
            total=estimate.valid_circle_cells,
            remaining_seconds=remaining,
        )
    if workers == 1:
        local_cancel = external_cancel
        _initialize_grid_worker(configuration, local_cancel)
        for spec in ordered_pending:
            if external_cancel.is_set():
                break
            accept_result(_evaluate_grid_block(spec))
    elif ordered_pending:
        _run_parallel_blocks(
            ordered_pending,
            configuration,
            workers,
            external_cancel,
            accept_result,
        )

    if external_cancel.is_set():
        _record_performance(
            workers=workers,
            cells=completed_cells - session_start_cells,
            profile_points=session_profile_points,
            elapsed_seconds=max(
                time.monotonic() - compute_started,
                0.001,
            ),
        )
        _raise_cancelled(
            completed_cells,
            estimate.valid_circle_cells,
            checkpoint,
        )
    if completed_cells != estimate.valid_circle_cells:
        raise RuntimeError(
            "A grade terminou incompleta: "
            f"{completed_cells:,} de {estimate.valid_circle_cells:,} células."
        )

    session_compute_seconds = time.monotonic() - compute_started
    compute_seconds = previous_compute_seconds + session_compute_seconds
    all_profile_points = int(np.sum(block_statistics[completed, 1]))
    p1812_cells = int(np.sum(block_statistics[completed, 2]))
    short_range_cells = int(np.sum(block_statistics[completed, 3]))
    failed_cells = int(np.sum(block_statistics[completed, 4]))
    worker_compute_seconds = float(
        np.sum(block_statistics[completed, 5])
    ) / 1000.0
    _record_performance(
        workers=workers,
        cells=completed_cells - session_start_cells,
        profile_points=session_profile_points,
        elapsed_seconds=max(session_compute_seconds, 0.001),
    )
    grid_metadata = {
        "engine": "direct_metric_grid",
        "engine_version": DIRECT_GRID_ENGINE_VERSION,
        "model": "ITU-R P.1812-8",
        "model_version": _p1812_version(),
        "projection": GRID_PROJECTION,
        "radius_km": request.radius_km,
        "resolution_m": request.resolution_m,
        "terrain_profile_step_m": request.terrain_step_m,
        "grid_width": estimate.grid_width,
        "grid_height": estimate.grid_height,
        "square_grid_cells": estimate.grid_width * estimate.grid_height,
        "valid_circle_cells": estimate.valid_circle_cells,
        "calculated_cells": completed_cells,
        "p1812_cells": p1812_cells,
        "short_range_free_space_cells": short_range_cells,
        "failed_cells": failed_cells,
        "terrain_profile_points": all_profile_points,
        "propagation_interpolated_cells": 0,
        "worker_count": workers,
        "block_size": GRID_BLOCK_SIZE,
        "compute_seconds": compute_seconds,
        "session_compute_seconds": session_compute_seconds,
        "worker_compute_seconds": worker_compute_seconds,
        "resumed": resumed,
        "resume_count": resume_count,
        "terrain_source": "Copernicus GLO-30",
        "terrain_zone_assumption": "all_inland_land",
        "clutter_included": False,
    }

    tracker.emit(
        91.0,
        "render",
        "91% — Montando o raster calculado e os produtos cartográficos…",
        completed=completed_cells,
        total=estimate.valid_circle_cells,
    )
    if external_cancel.is_set():
        _raise_cancelled(completed_cells, estimate.valid_circle_cells, checkpoint)

    from .coverage_report import write_coverage_outputs

    render_messages = 0

    def render_progress(message: str) -> None:
        nonlocal render_messages
        render_messages += 1
        percent = min(98.5, 91.0 + render_messages * 1.5)
        tracker.emit(percent, "render", f"{percent:.0f}% — {message}")

    try:
        report_paths, report_statistics = write_coverage_outputs(
            request=request,
            grid=grid,
            grid_metadata=grid_metadata,
            output_directory=destination,
            progress=render_progress,
            cancel_check=external_cancel.is_set,
        )
    except InterruptedError:
        _raise_cancelled(
            completed_cells,
            estimate.valid_circle_cells,
            checkpoint,
        )
    if external_cancel.is_set():
        _raise_cancelled(completed_cells, estimate.valid_circle_cells, checkpoint)

    project_path = destination / "coverage_project.json"
    project_path.write_text(
        json.dumps(
            {
                **_request_payload(request, include_output_directory=True),
                "model": "ITU-R P.1812-8",
                "engine": "direct_metric_grid",
                "contour_levels_db": list(CONTOUR_LEVELS_DB),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    statistics = {
        **grid_metadata,
        **report_statistics,
        "time_percentage": request.time_percentage,
        "total_elapsed_seconds": time.monotonic() - tracker.started,
        "request_fingerprint": fingerprint,
        "completed_at_utc": datetime.now(UTC).isoformat(),
    }
    metadata_path = destination / "coverage_metadata.json"
    metadata_path.write_text(
        json.dumps(statistics, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    _close_memmap(grid)
    _close_memmap(completed)
    _close_memmap(block_statistics)
    # Windows does not allow replacing an open memory-mapped file. Dropping
    # the arrays releases NumPy's final references before moving the checkpoint.
    del grid, completed, block_statistics
    gc.collect()
    final_grid_path = destination / "coverage_margin_db.npy"
    os.replace(checkpoint.grid, final_grid_path)
    _remove_completed_checkpoint(checkpoint)
    tracker.emit(
        100.0,
        "complete",
        "100% — Cobertura concluída: grade direta, heatmap e contornos gerados.",
        completed=completed_cells,
        total=estimate.valid_circle_cells,
        remaining_seconds=0.0,
    )
    paths = {
        "project_json": project_path,
        "margin_grid": final_grid_path,
        "metadata": metadata_path,
        **report_paths,
    }
    return CoverageOutcome(
        request=request,
        radials=(),
        paths=paths,
        statistics=statistics,
    )


def _run_parallel_blocks(
    blocks: list[GridBlockSpec],
    configuration: _WorkerConfiguration,
    workers: int,
    external_cancel: threading.Event,
    accept_result,
) -> None:
    context = multiprocessing.get_context("spawn")
    process_cancel = context.Event()
    executor = ProcessPoolExecutor(
        max_workers=workers,
        mp_context=context,
        initializer=_initialize_grid_worker,
        initargs=(configuration, process_cancel),
    )
    iterator = iter(blocks)
    futures: dict[Future[GridBlockResult], GridBlockSpec] = {}

    def submit_next() -> bool:
        try:
            spec = next(iterator)
        except StopIteration:
            return False
        futures[executor.submit(_evaluate_grid_block, spec)] = spec
        return True

    try:
        for _ in range(min(len(blocks), workers * 2)):
            submit_next()
        while futures:
            if external_cancel.is_set():
                process_cancel.set()
            done, _ = wait(
                futures,
                timeout=0.2,
                return_when=FIRST_COMPLETED,
            )
            for future in done:
                futures.pop(future)
                result = future.result()
                if not external_cancel.is_set():
                    accept_result(result)
                    if not external_cancel.is_set():
                        submit_next()
            if external_cancel.is_set() and not done:
                continue
    finally:
        process_cancel.set()
        for future in futures:
            future.cancel()
        executor.shutdown(wait=True, cancel_futures=True)


def _initialize_grid_worker(
    configuration: _WorkerConfiguration,
    cancel_event: Any,
) -> None:
    global _WORKER_CONFIGURATION, _WORKER_P1812, _WORKER_CANCEL_EVENT
    _WORKER_CONFIGURATION = configuration
    _WORKER_CANCEL_EVENT = cancel_event
    _WORKER_P1812 = load_digital_product_module(P1812_PRODUCT, "P1812")


def _evaluate_grid_block(spec: GridBlockSpec) -> GridBlockResult:
    if _WORKER_CONFIGURATION is None or _WORKER_P1812 is None:
        raise RuntimeError("coverage worker was not initialized")
    configuration = _WORKER_CONFIGURATION
    started = time.monotonic()
    rows = spec.row_stop - spec.row_start
    columns = spec.column_stop - spec.column_start
    values = np.full((rows, columns), np.nan, dtype=np.float32)
    calculated = 0
    profile_points = 0
    p1812_cells = 0
    short_range_cells = 0
    failures = 0
    errors: list[str] = []
    centre = (configuration.dimension - 1) / 2.0

    for local_row, row in enumerate(range(spec.row_start, spec.row_stop)):
        north_m = (centre - row) * configuration.resolution_m
        for local_column, column in enumerate(
            range(spec.column_start, spec.column_stop)
        ):
            if _WORKER_CANCEL_EVENT is not None and _WORKER_CANCEL_EVENT.is_set():
                return GridBlockResult(
                    block_id=spec.block_id,
                    row_start=spec.row_start,
                    row_stop=spec.row_stop,
                    column_start=spec.column_start,
                    column_stop=spec.column_stop,
                    margin_db=values,
                    calculated_cells=calculated,
                    profile_points=profile_points,
                    p1812_cells=p1812_cells,
                    short_range_cells=short_range_cells,
                    failed_cells=failures,
                    elapsed_seconds=time.monotonic() - started,
                    errors=tuple(errors),
                )
            east_m = (column - centre) * configuration.resolution_m
            distance_m = math.hypot(east_m, north_m)
            if distance_m > configuration.radius_m + 1e-6:
                continue
            calculated += 1
            try:
                if distance_m < MINIMUM_P1812_DISTANCE_M:
                    effective_distance = max(
                        1.0,
                        distance_m,
                        configuration.resolution_m / 2.0,
                    )
                    values[local_row, local_column] = _free_space_margin(
                        configuration,
                        effective_distance,
                    )
                    short_range_cells += 1
                    continue
                bearing_deg = (
                    math.degrees(math.atan2(east_m, north_m)) + 360.0
                ) % 360.0
                margin, count = _p1812_cell_margin(
                    configuration,
                    bearing_deg,
                    distance_m,
                )
                values[local_row, local_column] = margin
                profile_points += count
                p1812_cells += 1
            except Exception as exc:
                failures += 1
                if len(errors) < 3:
                    errors.append(f"{type(exc).__name__}: {exc}")

    return GridBlockResult(
        block_id=spec.block_id,
        row_start=spec.row_start,
        row_stop=spec.row_stop,
        column_start=spec.column_start,
        column_stop=spec.column_stop,
        margin_db=values,
        calculated_cells=calculated,
        profile_points=profile_points,
        p1812_cells=p1812_cells,
        short_range_cells=short_range_cells,
        failed_cells=failures,
        elapsed_seconds=time.monotonic() - started,
        errors=tuple(errors),
    )


def _p1812_cell_margin(
    configuration: _WorkerConfiguration,
    bearing_deg: float,
    distance_m: float,
) -> tuple[float, int]:
    count = max(2, math.ceil(distance_m / configuration.terrain_step_m) + 1)
    distances_m = np.linspace(0.0, distance_m, count)
    latitudes, longitudes = destination_points(
        configuration.latitude_deg,
        configuration.longitude_deg,
        bearing_deg,
        distances_m,
    )
    elevations = sample_elevations(latitudes, longitudes, progress=None)
    margin = _p1812_margin_for_profile(
        configuration,
        distances_m,
        latitudes,
        longitudes,
        elevations,
    )
    return margin, count


def _p1812_margin_for_profile(
    configuration: _WorkerConfiguration,
    distances_m: np.ndarray,
    latitudes: np.ndarray,
    longitudes: np.ndarray,
    elevations: np.ndarray,
) -> float:
    count = len(distances_m)
    loss, _ = _WORKER_P1812.bt_loss(
        configuration.frequency_mhz / 1000.0,
        configuration.time_percentage,
        distances_m / 1000.0,
        elevations,
        np.zeros(count, dtype=float),
        np.full(count, 4, dtype=int),
        configuration.transmitter_height_m,
        configuration.receiver_height_m,
        configuration.polarization_code,
        configuration.latitude_deg,
        float(latitudes[-1]),
        configuration.longitude_deg,
        float(longitudes[-1]),
    )
    margin = _margin_from_loss(configuration, float(loss))
    if not math.isfinite(margin):
        raise ValueError("P.1812 returned a non-finite margin")
    return margin


def smoke_test_direct_grid_worker() -> float:
    """Exercise a spawned/forked P.1812 coverage worker without network terrain."""
    product_path = (
        product_data_directory(P1812_PRODUCT)
        / P1812_PRODUCT.output_filename
    )
    if not product_path.is_file():
        raise FileNotFoundError(
            f"dados {P1812_PRODUCT.recommendation} não encontrados em "
            f"{product_path}"
        )
    request = CoverageRequest(
        name="Direct-grid smoke test",
        latitude_deg=-23.0,
        longitude_deg=-47.0,
        frequency_mhz=146.0,
        polarization="vertical",
        mode="FM",
        radius_km=50,
        transmitter_height_m=10.0,
        transmitter_gain_dbi=3.0,
        transmitter_line_loss_db=1.0,
        transmitter_power_w=1.0,
        receiver_height_m=2.0,
        receiver_gain_dbi=2.0,
        receiver_line_loss_db=1.0,
        receiver_threshold_dbm=-120.0,
        output_directory=Path.cwd(),
        resolution_preset="custom",
        custom_resolution_m=10_000,
    )
    configuration = _worker_configuration(
        request,
        coverage_grid_dimension(request.radius_km, request.resolution_m),
    )
    context = multiprocessing.get_context("spawn")
    process_cancel = context.Event()
    with ProcessPoolExecutor(
        max_workers=1,
        mp_context=context,
        initializer=_initialize_grid_worker,
        initargs=(configuration, process_cancel),
    ) as executor:
        margin = executor.submit(_evaluate_synthetic_worker_profile).result(
            timeout=90.0
        )
    if not math.isfinite(margin):
        raise RuntimeError("direct-grid P.1812 worker returned a non-finite margin")
    return margin


def _evaluate_synthetic_worker_profile() -> float:
    if _WORKER_CONFIGURATION is None or _WORKER_P1812 is None:
        raise RuntimeError("coverage worker was not initialized")
    if getattr(sys, "frozen", False):
        import rasterio  # noqa: F401 - verify child-process packaging

    configuration = _WORKER_CONFIGURATION
    distance_m = 10_000.0
    count = math.ceil(distance_m / configuration.terrain_step_m) + 1
    distances_m = np.linspace(0.0, distance_m, count)
    latitudes, longitudes = destination_points(
        configuration.latitude_deg,
        configuration.longitude_deg,
        45.0,
        distances_m,
    )
    elevations = np.linspace(650.0, 700.0, count)
    return _p1812_margin_for_profile(
        configuration,
        distances_m,
        latitudes,
        longitudes,
        elevations,
    )


def _free_space_margin(
    configuration: _WorkerConfiguration,
    distance_m: float,
) -> float:
    distance_km = max(distance_m / 1000.0, 1e-6)
    loss_db = (
        32.447783
        + 20.0 * math.log10(configuration.frequency_mhz)
        + 20.0 * math.log10(distance_km)
    )
    return _margin_from_loss(configuration, loss_db)


def _margin_from_loss(
    configuration: _WorkerConfiguration,
    loss_db: float,
) -> float:
    received_power_dbm = (
        configuration.transmitter_power_dbm
        + configuration.transmitter_gain_dbi
        - configuration.transmitter_line_loss_db
        - loss_db
        + configuration.receiver_gain_dbi
        - configuration.receiver_line_loss_db
    )
    return received_power_dbm - configuration.receiver_threshold_dbm


def _worker_configuration(
    request: CoverageRequest,
    dimension: int,
) -> _WorkerConfiguration:
    return _WorkerConfiguration(
        latitude_deg=request.latitude_deg,
        longitude_deg=request.longitude_deg,
        radius_m=request.radius_km * 1000.0,
        resolution_m=request.resolution_m,
        dimension=dimension,
        terrain_step_m=request.terrain_step_m,
        frequency_mhz=request.frequency_mhz,
        time_percentage=request.time_percentage,
        polarization_code=2 if request.polarization.lower() == "vertical" else 1,
        transmitter_height_m=request.transmitter_height_m,
        transmitter_power_dbm=watts_to_dbm(request.transmitter_power_w),
        transmitter_gain_dbi=request.transmitter_gain_dbi,
        transmitter_line_loss_db=request.transmitter_line_loss_db,
        receiver_height_m=request.receiver_height_m,
        receiver_gain_dbi=request.receiver_gain_dbi,
        receiver_line_loss_db=request.receiver_line_loss_db,
        receiver_threshold_dbm=request.receiver_threshold_dbm,
    )


def _iter_grid_blocks(
    radius_km: int,
    resolution_m: int,
    block_size: int,
) -> Iterator[GridBlockSpec]:
    dimension = coverage_grid_dimension(radius_km, resolution_m)
    radius_m = radius_km * 1000.0
    centre = (dimension - 1) / 2.0
    block_id = 0
    for row_start in range(0, dimension, block_size):
        row_stop = min(dimension, row_start + block_size)
        for column_start in range(0, dimension, block_size):
            column_stop = min(dimension, column_start + block_size)
            if not _block_intersects_circle(
                row_start,
                row_stop,
                column_start,
                column_stop,
                centre,
                resolution_m,
                radius_m,
            ):
                continue
            yield GridBlockSpec(
                block_id=block_id,
                row_start=row_start,
                row_stop=row_stop,
                column_start=column_start,
                column_stop=column_stop,
            )
            block_id += 1


def _block_intersects_circle(
    row_start: int,
    row_stop: int,
    column_start: int,
    column_stop: int,
    centre: float,
    resolution_m: int,
    radius_m: float,
) -> bool:
    north_values = (
        (centre - (row_start + row_stop - 1) / 2.0) * resolution_m,
        (centre - row_start) * resolution_m,
        (centre - (row_stop - 1)) * resolution_m,
    )
    east_values = (
        ((column_start + column_stop - 1) / 2.0 - centre) * resolution_m,
        (column_start - centre) * resolution_m,
        ((column_stop - 1) - centre) * resolution_m,
    )

    def nearest_zero(values: tuple[float, ...]) -> float:
        low = min(values[1], values[2])
        high = max(values[1], values[2])
        if low <= 0.0 <= high:
            return 0.0
        return min(abs(low), abs(high))

    nearest_north = nearest_zero(north_values)
    nearest_east = nearest_zero(east_values)
    return math.hypot(nearest_east, nearest_north) <= radius_m + 1e-6


def _checkpoint_paths(
    request: CoverageRequest,
    fingerprint: str,
) -> _CheckpointPaths:
    directory = (
        request.output_directory.expanduser().resolve()
        / f".coverage-checkpoint-{fingerprint[:12]}"
    )
    return _CheckpointPaths(
        directory=directory,
        metadata=directory / "checkpoint.json",
        grid=directory / "coverage_margin_db.npy",
        completed=directory / "completed_blocks.npy",
        block_statistics=directory / "block_statistics.npy",
    )


def _open_checkpoint(
    request: CoverageRequest,
    fingerprint: str,
    blocks: tuple[GridBlockSpec, ...],
    paths: _CheckpointPaths,
) -> tuple[np.memmap, np.memmap, np.memmap, bool]:
    dimension = coverage_grid_dimension(request.radius_km, request.resolution_m)
    resumed = paths.metadata.is_file()
    paths.directory.mkdir(parents=True, exist_ok=True)
    if resumed:
        metadata = json.loads(paths.metadata.read_text(encoding="utf-8"))
        if metadata.get("request_fingerprint") != fingerprint:
            raise RuntimeError("O checkpoint não corresponde a esta cobertura.")
        try:
            grid = np.load(paths.grid, mmap_mode="r+")
            completed = np.load(paths.completed, mmap_mode="r+")
            statistics = np.load(paths.block_statistics, mmap_mode="r+")
        except Exception as exc:
            raise RuntimeError(
                f"O checkpoint de cobertura está danificado: {paths.directory}"
            ) from exc
        if grid.shape != (dimension, dimension):
            raise RuntimeError("A grade do checkpoint possui dimensões inválidas.")
        if completed.shape != (len(blocks),):
            raise RuntimeError("O estado de blocos do checkpoint é inválido.")
        if statistics.shape != (len(blocks), 6):
            raise RuntimeError("As estatísticas do checkpoint são inválidas.")
        return grid, completed, statistics, True

    grid = np.lib.format.open_memmap(
        paths.grid,
        mode="w+",
        dtype=np.float32,
        shape=(dimension, dimension),
    )
    for row_start in range(0, dimension, 256):
        grid[row_start : row_start + 256] = np.nan
    grid.flush()
    completed = np.lib.format.open_memmap(
        paths.completed,
        mode="w+",
        dtype=np.bool_,
        shape=(len(blocks),),
    )
    completed[:] = False
    completed.flush()
    statistics = np.lib.format.open_memmap(
        paths.block_statistics,
        mode="w+",
        dtype=np.int64,
        shape=(len(blocks), 6),
    )
    statistics[:] = 0
    statistics.flush()
    _update_checkpoint_metadata(
        request,
        fingerprint,
        blocks,
        paths,
        completed_cells=0,
        resumed_runs=0,
        accumulated_compute_seconds=0.0,
    )
    return grid, completed, statistics, False


def _update_checkpoint_metadata(
    request: CoverageRequest,
    fingerprint: str,
    blocks: tuple[GridBlockSpec, ...],
    paths: _CheckpointPaths,
    *,
    completed_cells: int,
    resumed_runs: int,
    accumulated_compute_seconds: float,
) -> None:
    payload = {
        "schema_version": 1,
        "engine": "direct_metric_grid",
        "engine_version": DIRECT_GRID_ENGINE_VERSION,
        "request_fingerprint": fingerprint,
        "request": _request_payload(request, include_output_directory=False),
        "grid_dimension": coverage_grid_dimension(
            request.radius_km,
            request.resolution_m,
        ),
        "block_size": GRID_BLOCK_SIZE,
        "block_count": len(blocks),
        "completed_cells": completed_cells,
        "resumed_runs": resumed_runs,
        "accumulated_compute_seconds": accumulated_compute_seconds,
        "updated_at_utc": datetime.now(UTC).isoformat(),
    }
    temporary = paths.metadata.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, paths.metadata)


def _remove_completed_checkpoint(paths: _CheckpointPaths) -> None:
    for path in (
        paths.metadata,
        paths.completed,
        paths.block_statistics,
    ):
        path.unlink(missing_ok=True)
    try:
        paths.directory.rmdir()
    except OSError:
        pass


def _resumable_cell_count(request: CoverageRequest) -> int:
    fingerprint = coverage_request_fingerprint(request)
    paths = _checkpoint_paths(request, fingerprint)
    if not (
        paths.metadata.is_file()
        and paths.completed.is_file()
        and paths.block_statistics.is_file()
    ):
        return 0
    completed: np.memmap | None = None
    statistics: np.memmap | None = None
    try:
        completed = np.load(paths.completed, mmap_mode="r")
        statistics = np.load(paths.block_statistics, mmap_mode="r")
        return int(np.sum(statistics[completed, 0]))
    except Exception:
        return 0
    finally:
        if completed is not None:
            _close_memmap(completed)
        if statistics is not None:
            _close_memmap(statistics)


def _close_memmap(array: np.memmap) -> None:
    array.flush()
    mapped = getattr(array, "_mmap", None)
    if mapped is not None:
        mapped.close()


def _raise_cancelled(
    completed_cells: int,
    total_cells: int,
    paths: _CheckpointPaths,
) -> None:
    raise CoverageCancelled(
        completed_cells=completed_cells,
        total_cells=total_cells,
        checkpoint_directory=paths.directory,
    )


def _request_payload(
    request: CoverageRequest,
    *,
    include_output_directory: bool,
) -> dict[str, Any]:
    data = asdict(request)
    if include_output_directory:
        data["output_directory"] = str(request.output_directory)
    else:
        data.pop("output_directory", None)
    data["resolution_m"] = request.resolution_m
    return data


def _validate_coverage_extent(request: CoverageRequest) -> None:
    radius_m = request.radius_km * 1000.0
    north, _ = destination_point(
        request.latitude_deg,
        request.longitude_deg,
        0.0,
        radius_m,
    )
    south, _ = destination_point(
        request.latitude_deg,
        request.longitude_deg,
        180.0,
        radius_m,
    )
    if north > 80.0 or south < -80.0:
        raise ValueError(
            "Parte da cobertura ultrapassa ±80° de latitude, limite da "
            "implementação P.1812 utilizada."
        )


def _validated_worker_count(worker_count: int | None) -> int:
    workers = default_worker_count() if worker_count is None else int(worker_count)
    if workers < 1:
        raise ValueError("worker count must be positive")
    return min(workers, MAXIMUM_WORKERS)


def _p1812_version() -> str:
    try:
        return importlib.metadata.version("Py1812")
    except importlib.metadata.PackageNotFoundError:
        return "not installed"


def _valid_cached_tile(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 10_000
    except OSError:
        return False


def _performance_history_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        root = Path(local_app_data)
    else:
        xdg_data_home = os.environ.get("XDG_DATA_HOME")
        root = (
            Path(xdg_data_home)
            if xdg_data_home
            else Path.home() / ".local" / "share"
        )
    return root / "RadioLinkPlanner" / "coverage-performance.json"


def _machine_key(workers: int) -> str:
    return "|".join(
        (
            platform.system(),
            platform.machine(),
            str(os.cpu_count() or 0),
            str(workers),
        )
    )


def _historical_work_rate(workers: int) -> float:
    default = (
        DEFAULT_WORK_UNITS_PER_SECOND_PER_WORKER
        * max(1.0, workers * 0.75)
    )
    path = _performance_history_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        values = [
            float(item["work_units_per_second"])
            for item in payload.get("runs", [])
            if item.get("machine_key") == _machine_key(workers)
            and float(item.get("work_units_per_second", 0.0)) > 0.0
        ]
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return default
    if not values:
        return default
    return float(np.median(np.asarray(values[-5:], dtype=float)))


def _record_performance(
    *,
    workers: int,
    cells: int,
    profile_points: int,
    elapsed_seconds: float,
) -> None:
    if cells <= 0 or elapsed_seconds <= 0.0:
        return
    path = _performance_history_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        payload = {"schema_version": 1, "runs": []}
    runs = list(payload.get("runs", []))
    work_units = profile_points + cells * CELL_OVERHEAD_WORK_UNITS
    runs.append(
        {
            "machine_key": _machine_key(workers),
            "workers": workers,
            "cells": cells,
            "profile_points": profile_points,
            "elapsed_seconds": elapsed_seconds,
            "work_units_per_second": work_units / elapsed_seconds,
            "recorded_at_utc": datetime.now(UTC).isoformat(),
        }
    )
    payload["runs"] = runs[-PERFORMANCE_HISTORY_LIMIT:]
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    except OSError:
        return
