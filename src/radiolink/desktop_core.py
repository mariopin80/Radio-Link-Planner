from __future__ import annotations

import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .copernicus import DEFAULT_STEP_M, extract_profile
from .domain import Project
from .engine import analyze_project
from .itu_data import ensure_itu_data
from .project_editor import write_project_json
from .report import describe_geometry_clearance, write_outputs
from .terrain import TerrainProfile

APP_NAME = "Radio Link Planner"
EXAMPLE_PROJECT = Path("examples") / "morro_jacu_palmira.json"
ProgressCallback = Callable[[str], None]


@dataclass(frozen=True)
class AnalysisRequest:
    project_path: Path
    output_directory: Path
    monte_carlo_runs: int | None = None
    make_plots: bool = True


@dataclass(frozen=True)
class FormAnalysisRequest:
    project: Project
    output_directory: Path
    monte_carlo_runs: int | None = None
    make_plots: bool = True
    existing_terrain_path: Path | None = None
    terrain_step_m: float = DEFAULT_STEP_M


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


def run_analysis(
    request: AnalysisRequest,
    progress: ProgressCallback | None = None,
) -> AnalysisOutcome:
    project, base_dir = Project.from_json(request.project_path)
    if request.monte_carlo_runs is not None:
        project = project.model_copy(deep=True)
        project.monte_carlo.runs = request.monte_carlo_runs
    profile = TerrainProfile.from_csv(project.resolved_terrain_path(base_dir))
    _ensure_model_data(project, progress)
    return _analyze(
        project,
        profile,
        request.output_directory,
        make_plots=request.make_plots,
        progress=progress,
    )


def run_form_analysis(
    request: FormAnalysisRequest,
    progress: ProgressCallback | None = None,
) -> AnalysisOutcome:
    destination = request.output_directory.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    terrain_path = destination / "terrain_profile.csv"
    project = request.project.model_copy(deep=True)
    if request.monte_carlo_runs is not None:
        project.monte_carlo.runs = request.monte_carlo_runs

    if request.existing_terrain_path is not None:
        source = request.existing_terrain_path.resolve()
        if not source.is_file():
            raise FileNotFoundError(f"Perfil de terreno não encontrado: {source}")
        if source != terrain_path:
            shutil.copyfile(source, terrain_path)
        _notify(progress, "Terreno: usando o perfil do projeto carregado.")
        profile = TerrainProfile.from_csv(terrain_path)
        project.terrain_resolution_m = profile.nominal_step_m
    else:
        profile = extract_profile(
            project.terminal_a.latitude_deg,
            project.terminal_a.longitude_deg,
            project.terminal_b.latitude_deg,
            project.terminal_b.longitude_deg,
            terrain_path,
            step_m=request.terrain_step_m,
            progress=progress,
        )
        project.terrain_source = (
            "Copernicus GLO-30, obtido automaticamente pelo Radio Link Planner"
        )
        project.terrain_resolution_m = request.terrain_step_m
        project.clutter_included = False
        project.metadata["terrain_zone_assumption"] = "all_inland_land"

    project.terrain_profile = "terrain_profile.csv"
    project = Project.model_validate(project.model_dump(mode="json"))
    project_path = write_project_json(project, destination / "project.json")
    _ensure_model_data(project, progress)
    outcome = _analyze(
        project,
        profile,
        destination,
        make_plots=request.make_plots,
        progress=progress,
    )
    paths = dict(outcome.paths)
    paths["project_json"] = project_path
    paths["terrain_profile"] = terrain_path
    return AnalysisOutcome(project=project, result=outcome.result, paths=paths)


def _analyze(
    project: Project,
    profile: TerrainProfile,
    output_directory: str | Path,
    *,
    make_plots: bool,
    progress: ProgressCallback | None,
) -> AnalysisOutcome:
    _notify(progress, "Modelos: calculando ITM, P.1812 e P.2001…")
    result, arrays = analyze_project(project, profile)
    _notify(progress, "Relatório: gerando resultados, mapa e gráficos…")
    paths = write_outputs(
        output_directory,
        project,
        profile,
        result,
        arrays,
        make_plots=make_plots,
    )
    _notify(progress, "Análise concluída.")
    return AnalysisOutcome(project=project, result=result, paths=paths)


def _ensure_model_data(
    project: Project,
    progress: ProgressCallback | None,
) -> None:
    if project.models.p1812 or project.models.p2001:
        ensure_itu_data(
            include_p1812=project.models.p1812,
            include_p2001=project.models.p2001,
            cleanup_source_maps=True,
            progress=progress,
        )


def _notify(progress: ProgressCallback | None, message: str) -> None:
    if progress is not None:
        progress(message)


def build_desktop_summary(outcome: AnalysisOutcome) -> str:
    project = outcome.project
    result = outcome.result
    geometry = result["geometry"]
    lines = [
        project.name,
        (
            f"{project.frequency_mhz:.3f} MHz • "
            f"{project.primary_mode.upper()} • {project.polarization.value}"
        ),
        "",
        f"Distância: {geometry['profile_distance_km']:.3f} km",
        describe_geometry_clearance(geometry),
        (
            "Fresnel de 60% obstruída em "
            f"{geometry['fresnel_60_obstructed_percent']:.1f}% do percurso"
        ),
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
    _smoke_test_geographic_component()
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
    from .coverage_grid import smoke_test_direct_grid_worker

    smoke_test_direct_grid_worker()
    for key in ("result_json", "summary_markdown", "report_html", "report_pdf"):
        if not outcome.paths[key].is_file():
            raise FileNotFoundError(f"expected output not found: {key}")
    if getattr(sys, "frozen", False):
        report_assets = outcome.paths["report_html"].parent / "report-assets"
        for filename in ("maplibre-gl.js", "maplibre-gl.css"):
            if not (report_assets / filename).is_file():
                raise FileNotFoundError(f"packaged map asset not found: {filename}")
        for filename in ("home-link.png", "home-coverage.png"):
            image_path = bundle_root() / "assets" / filename
            encoded_path = image_path.with_suffix(f"{image_path.suffix}.b64")
            if not image_path.is_file() and not encoded_path.is_file():
                raise FileNotFoundError(f"packaged home asset not found: {filename}")
        import webview  # noqa: F401 - packaged component smoke test
    _smoke_test_local_report_server(outcome.paths["report_html"])
    return outcome


def _smoke_test_geographic_component() -> None:
    import numpy as np
    from rasterio.io import MemoryFile
    from rasterio.transform import from_origin

    values = np.asarray([[10.0, 20.0], [30.0, 40.0]], dtype=np.float32)
    with MemoryFile() as memory:
        with memory.open(
            driver="GTiff",
            height=2,
            width=2,
            count=1,
            dtype="float32",
            crs="EPSG:4326",
            transform=from_origin(-46.0, -23.0, 0.01, 0.01),
        ) as dataset:
            dataset.write(values, 1)
        with memory.open() as dataset:
            sample = next(dataset.sample([(-45.995, -23.005)]))[0]
    if not np.isfinite(sample):
        raise RuntimeError("packaged rasterio component returned an invalid sample")


def _smoke_test_local_report_server(report_path: Path) -> None:
    import urllib.request

    from .report_server import start_report_server

    server, report_url = start_report_server(report_path, timeout_seconds=30.0)
    try:
        with urllib.request.urlopen(report_url, timeout=10.0) as response:
            body = response.read()
            referrer_policy = response.headers.get("Referrer-Policy")
        if b"maplibregl.Map" not in body:
            raise RuntimeError("local report server returned an invalid report")
        if referrer_policy != "strict-origin-when-cross-origin":
            raise RuntimeError("local report server omitted its referrer policy")
    finally:
        server.shutdown()
        server.server_close()
