from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np

from .domain import Project
from .geometry import CLEARANCE_TOLERANCE_M, calculate_geometry, validate_geometry_criteria
from .i18n import choice_label, tr
from .terrain import TerrainProfile

MIN_HEIGHT_STEP_M = 0.01

HEIGHT_OPTIMIZATION_CRITERION = (
    "Menor aumento total nas alturas; em caso de empate, menor aumento em A."
)
HEIGHT_OPTIMIZATION_LIMIT = (
    "A desobstrução geométrica é um critério de projeto. "
    "A margem e a disponibilidade dependem dos resultados de propagação e das condições reais."
)


@dataclass(frozen=True)
class HeightBounds:
    minimum_m: float
    maximum_m: float

    def starting_height(self, current_m: float) -> float:
        if not 0.0 < self.minimum_m <= self.maximum_m <= 3000.0:
            raise ValueError(tr("As alturas mínima e máxima devem ser positivas, ordenadas e de até 3.000 m."))
        return max(current_m, self.minimum_m)


@dataclass(frozen=True)
class CriticalClearance:
    distance_km: float
    clearance_m: float
    required_m: float

    @property
    def excess_m(self) -> float:
        return self.clearance_m - self.required_m


@dataclass(frozen=True)
class HeightSolution:
    original_a_m: float
    original_b_m: float
    proposed_a_m: float
    proposed_b_m: float
    fresnel_percent: float
    effective_earth_k: float
    step_m: float
    before: CriticalClearance
    after: CriticalClearance


def optimize_antenna_heights(
    project: Project,
    profile: TerrainProfile,
    *,
    bounds_a: HeightBounds | None,
    bounds_b: HeightBounds | None,
    step_m: float,
    fresnel_percent: float,
    effective_earth_k: float,
) -> HeightSolution | None:
    """Minimize total added height on the two discrete grids without rerunning models."""
    if bounds_a is None and bounds_b is None:
        raise ValueError(tr("Selecione pelo menos uma antena para elevar."))
    if not math.isfinite(step_m) or step_m < MIN_HEIGHT_STEP_M:
        raise ValueError(tr("O passo deve ser de pelo menos 0,01 m."))
    validate_geometry_criteria(fresnel_percent, effective_earth_k)
    if len(profile.distance_km) < 3:
        raise ValueError(tr("O perfil deve ter pelo menos um ponto entre as duas estações."))
    current_a = project.terminal_a.antenna_height_m
    current_b = project.terminal_b.antenna_height_m
    minimum_a = bounds_a.starting_height(current_a) if bounds_a else current_a
    minimum_b = bounds_b.starting_height(current_b) if bounds_b else current_b
    maximum_a = bounds_a.maximum_m if bounds_a else current_a
    maximum_b = bounds_b.maximum_m if bounds_b else current_b
    if minimum_a > maximum_a or minimum_b > maximum_b:
        return None
    count_a = math.floor((maximum_a - minimum_a) / step_m + 1e-10)
    count_b = math.floor((maximum_b - minimum_b) / step_m + 1e-10)
    before = project_at_heights(project, current_a, current_b, effective_earth_k)
    _, arrays = calculate_geometry(before, profile)
    fraction = arrays.distance_m[1:-1] / arrays.distance_m[-1]
    clearance = arrays.clearance_m[1:-1]
    required = arrays.fresnel_radius_m[1:-1] * fresnel_percent / 100.0
    minimum_clearance = (
        clearance + (1.0 - fraction) * (minimum_a - current_a)
        + fraction * (minimum_b - current_b)
    )
    deficit = required - minimum_clearance - CLEARANCE_TOLERANCE_M
    coefficient = 1.0 - 2.0 * fraction
    near_a, near_b = coefficient > 0.0, coefficient < 0.0
    midpoint = ~(near_a | near_b)

    def steps_at_a(total_steps: int) -> int | None:
        # With B = total - A, every sample sets a lower or upper bound on A.
        residual = deficit / step_m - fraction * total_steps
        if np.any(residual[midpoint] > 0.0):
            return None
        lower = max(
            0, total_steps - count_b,
            math.ceil(float(np.max(residual[near_a] / coefficient[near_a], initial=-1.0))),
        )
        upper = min(
            total_steps, count_a,
            math.floor(float(np.min(residual[near_b] / coefficient[near_b], initial=count_a))),
        )
        return lower if lower <= upper else None

    low, high = 0, count_a + count_b
    if steps_at_a(high) is None:
        return None
    while low < high:
        middle = (low + high) // 2
        if steps_at_a(middle) is None:
            low = middle + 1
        else:
            high = middle
    increments_a = steps_at_a(low)
    assert increments_a is not None
    proposed_a = min(maximum_a, minimum_a + increments_a * step_m)
    proposed_b = min(maximum_b, minimum_b + (low - increments_a) * step_m)
    after_clearance = (
        clearance + (1.0 - fraction) * (proposed_a - current_a)
        + fraction * (proposed_b - current_b)
    )

    def critical(values: np.ndarray) -> CriticalClearance:
        index = int(np.argmin(values - required))
        return CriticalClearance(
            float(profile.distance_km[index + 1]), float(values[index]), float(required[index])
        )

    return HeightSolution(
        current_a, current_b, proposed_a, proposed_b, fresnel_percent,
        effective_earth_k, step_m, critical(clearance), critical(after_clearance),
    )


def project_at_heights(
    project: Project, height_a_m: float, height_b_m: float, effective_earth_k: float,
    *, fresnel_percent: float | None = None,
) -> Project:
    geometry = {"effective_earth_k": effective_earth_k}
    if fresnel_percent is not None:
        geometry["fresnel_percent"] = fresnel_percent
    return project.model_copy(update={
        "terminal_a": project.terminal_a.model_copy(update={"antenna_height_m": height_a_m}),
        "terminal_b": project.terminal_b.model_copy(update={"antenna_height_m": height_b_m}),
        "environment": project.environment.model_copy(update=geometry),
    })


def apply_height_solution(
    project: Project, profile: TerrainProfile, solution: HeightSolution
) -> Project:
    updated = project_at_heights(
        project, solution.proposed_a_m, solution.proposed_b_m, solution.effective_earth_k,
        fresnel_percent=solution.fresnel_percent,
    )
    return updated.model_copy(update={
        "metadata": {**project.metadata, "height_optimization": {
            **asdict(solution),
            "terrain_sha256": profile.fingerprint(),
            "frequency_mhz": project.frequency_mhz,
            "coordinates": _coordinates(project),
        }},
    })


def height_optimization_for(project: Project, profile: TerrainProfile) -> dict | None:
    """Use saved provenance only when the applied geometry still matches."""
    record = project.metadata.get("height_optimization")
    if not isinstance(record, dict):
        return None
    if (
        record.get("frequency_mhz") != project.frequency_mhz
        or record.get("coordinates") != _coordinates(project)
        or record.get("effective_earth_k") != project.environment.effective_earth_k
        or record.get("proposed_a_m") != project.terminal_a.antenna_height_m
        or record.get("proposed_b_m") != project.terminal_b.antenna_height_m
        or record.get("terrain_sha256") != profile.fingerprint()
    ):
        return None
    try:
        for key in ("before", "after"):
            critical = CriticalClearance(**record[key])
            if not all(math.isfinite(value) for value in asdict(critical).values()):
                return None
        if not (
            0.0 < record["original_a_m"] <= record["proposed_a_m"]
            and 0.0 < record["original_b_m"] <= record["proposed_b_m"]
            and 0.0 <= record["fresnel_percent"] <= 100.0
            and MIN_HEIGHT_STEP_M <= record["step_m"] < math.inf
        ):
            return None
    except (KeyError, TypeError, ValueError):
        return None
    return record


def height_summary_lines(record: dict) -> list[str]:
    lines = [
        tr("Critério geométrico de {percent:g}% da primeira zona de Fresnel, k={k:.4g}, passo de {step:g} m.",
           percent=record["fresnel_percent"], k=record["effective_earth_k"], step=record["step_m"]),
    ]
    for terminal in ("a", "b"):
        original, proposed = record[f"original_{terminal}_m"], record[f"proposed_{terminal}_m"]
        lines.append(tr(
            "Terminal {terminal}: {before:g} → {after:g} m ({increment:+g} m).",
            terminal=terminal.upper(), before=original, after=proposed, increment=proposed - original,
        ))
    for key, label in (("before", tr("Antes")), ("after", tr("Depois"))):
        critical = CriticalClearance(**record[key])
        lines.append(tr(
            "{label} — ponto crítico a {distance:.3f} km de A: folga {clearance:+.2f} m; "
            "requisito {required:.2f} m; saldo {excess:+.2f} m.",
            label=label, distance=critical.distance_km, clearance=critical.clearance_m,
            required=critical.required_m, excess=critical.excess_m,
        ))
    lines.extend([tr(HEIGHT_OPTIMIZATION_CRITERION), tr(HEIGHT_OPTIMIZATION_LIMIT)])
    return lines


def height_comparison_table(comparison: list[dict]) -> list[list[str]]:
    def pair(row: dict, field: str) -> str:
        labels = []
        for key in ("before", "after"):
            model = row[key]
            value = model[field]
            labels.append(
                f"{value:.2f}" if value is not None else choice_label(model["status"])
            )
        return " → ".join(labels)

    rows = [[tr("Modelo"), tr("Tempo (%)"), tr("Perda antes → depois (dB)"), tr("Margem antes → depois (dB)")]]
    for row in comparison:
        percentile = row["after"]["percentile"]
        rows.append([
            row["model_id"].upper(), "—" if percentile is None else f"{percentile:g}",
            pair(row, "loss_db"), pair(row, "margin_db"),
        ])
    return rows


def _coordinates(project: Project) -> list[float]:
    a, b = project.terminal_a, project.terminal_b
    return [a.latitude_deg, a.longitude_deg, b.latitude_deg, b.longitude_deg]
