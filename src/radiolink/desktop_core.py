from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .domain import Project
from .engine import analyze_project
from .itu_data import ensure_itu_data
from .report import write_outputs
from .terrain import TerrainProfile

APP_NAME = "Radio Link Planner"
EXAMPLE_PROJECT = Path("examples") / "morro_jacu_palmira.json"


@dataclass(frozen=True)
class AnalysisRequest:
    project_path: Path
    output_directory: Path
    monte_carlo_runs: int | None = None
    make_plots: bool = True


@dataclass(frozen=True)
class AnalysisOutcome:
    project: Project
    result: dict[str, Any]
    paths: dict[str, Path]


def bundle_root() -> Path:
    """Return the source checkout or PyInstaller extraction directory."""
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root).resolve()
    return Path(__file__).resolve().parents[2]


def bundled_example_path() -> Path:
    return bundle_root() / EXAMPLE_PROJECT


def default_output_directory() -> Path:
    return Path.home() / APP_NAME / "Resultados" / "Morro-do-Jacu-Palmira"


def run_analysis(request: AnalysisRequest) -> AnalysisOutcome:
    project, base_dir = Project.from_json(request.project_path)
    if project.models.p1812 or project.models.p2001:
        ensure_itu_data(
            include_p1812=project.models.p1812,
            include_p2001=project.models.p2001,
            cleanup_source_maps=True,
            progress=None,
        )
    if request.monte_carlo_runs is not None:
        project = project.model_copy(deep=True)
        project.monte_carlo.runs = request.monte_carlo_runs
    profile = TerrainProfile.from_csv(project.resolved_terrain_path(base_dir))
    result, arrays = analyze_project(project, profile)
    paths = write_outputs(
        request.output_directory,
        project,
        profile,
        result,
        arrays,
        make_plots=request.make_plots,
    )
    return AnalysisOutcome(project=project, result=result, paths=paths)


def build_desktop_summary(outcome: AnalysisOutcome) -> str:
    project = outcome.project
    result = outcome.result
    geometry = result["geometry"]
    lines = [
        project.name,
        f"{project.frequency_mhz:.3f} MHz • {project.primary_mode.upper()} • "
        f"{project.polarization.value}",
        "",
        f"Distância: {geometry['profile_distance_km']:.3f} km",
        f"Pior obstrução geométrica: {geometry['worst_obstruction_m']:.1f} m "
        f"a {geometry['worst_obstruction_distance_km']:.1f} km",
        f"Fresnel de 60% obstruída em "
        f"{geometry['fresnel_60_obstructed_percent']:.1f}% do percurso",
        "",
    ]
    classification_labels = {
        "robust": "ROBUSTO",
        "viable": "VIÁVEL",
        "marginal": "MARGINAL",
        "improbable": "IMPROVÁVEL",
        "indeterminate": "INDETERMINADO",
    }
    confidence_labels = {"high": "alta", "medium": "média", "low": "baixa"}
    for direction in result["directions"].values():
        assessment = direction["assessment"]
        classification = classification_labels.get(
            assessment["classification"], assessment["classification"].upper()
        )
        confidence = confidence_labels.get(
            assessment["confidence"], assessment["confidence"]
        )
        lines.extend(
            [
                f"{direction['transmitter']} → {direction['receiver']}",
                f"Parecer: {classification} • confiança {confidence}",
            ]
        )
        budgets = {budget["model_id"]: budget for budget in direction["link_budgets"]}
        simulations = {
            simulation["model_id"]: simulation
            for simulation in direction["monte_carlo"]
        }
        for model in direction["design_models"]:
            model_id = model["model_id"]
            if model["status"] != "ok" or model_id not in budgets:
                lines.append(
                    f"  {model_id.upper()}: {model['status']} (consulte o relatório)"
                )
                continue
            budget = budgets[model_id]
            detail = (
                f"perda {model['loss_db']:.2f} dB • "
                f"margem {budget['fade_margin_db']:+.2f} dB"
            )
            simulation = simulations.get(model_id)
            if simulation:
                primary = next(
                    (
                        item
                        for item in simulation["mode_results"]
                        if item["mode"] == project.primary_mode.upper()
                    ),
                    None,
                )
                if primary:
                    detail += (
                        f" • sucesso {primary['success_probability_percent']:.1f}%"
                    )
            lines.append(f"  {model_id.upper()}: {detail}")
        lines.append("")
    lines.extend(
        [
            f"Relatório: {outcome.paths['report_html']}",
            f"SHA-256 do resultado: {result['result_sha256']}",
        ]
    )
    return "\n".join(lines)


def smoke_test(output_directory: str | Path) -> AnalysisOutcome:
    example = bundled_example_path()
    if not example.is_file():
        raise FileNotFoundError(f"bundled example not found: {example}")
    outcome = run_analysis(
        AnalysisRequest(
            project_path=example,
            output_directory=Path(output_directory),
            monte_carlo_runs=500,
            make_plots=True,
        )
    )
    statuses = {
        model["model_id"]: model["status"]
        for direction in outcome.result["directions"].values()
        for model in direction["design_models"]
    }
    unavailable = {
        model_id: status for model_id, status in statuses.items() if status != "ok"
    }
    if unavailable:
        raise RuntimeError(f"propagation models unavailable: {unavailable}")
    for key in ("result_json", "summary_markdown", "report_html"):
        if not outcome.paths[key].is_file():
            raise FileNotFoundError(f"expected output not found: {key}")
    return outcome
