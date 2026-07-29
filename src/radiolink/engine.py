from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .analysis import assess
from .domain import Direction, Project
from .geometry import calculate_geometry
from .link_budget import calculate_link_budget
from .modes import all_mode_thresholds
from .monte_carlo import simulate
from .propagation import ItmModel, P1812Model, P2001Model
from .propagation.base import ModelContext, ModelStatus
from .propagation.free_space import free_space_loss_db
from .terrain import TerrainProfile
from .version import __version__


def analyze_project(
    project: Project,
    profile: TerrainProfile,
) -> tuple[dict[str, Any], Any]:
    geometry, geometry_arrays = calculate_geometry(project, profile)
    geometry_dict = geometry.to_dict()
    models = _enabled_models(project)
    result: dict[str, Any] = {
        "schema_version": "0.1",
        "engine_version": __version__,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "project": project.model_dump(mode="json"),
        "traceability": {
            "terrain_sha256": profile.fingerprint(),
            "terrain_reference": project.terrain_profile,
            "terrain_point_count": len(profile.distance_km),
            "terrain_nominal_step_m": profile.nominal_step_m,
        },
        "geometry": geometry_dict,
        "free_space_loss_db": free_space_loss_db(
            profile.total_distance_km, project.frequency_mhz
        ),
        "directions": {},
    }

    for direction in Direction:
        context = ModelContext(project=project, profile=profile, direction=direction)
        _, receiver = direction.terminals(project)
        comparison_evaluations = []
        design_evaluations = []
        curves: dict[str, Any] = {}
        budgets = []
        monte_carlo = []

        for model in models:
            comparison = model.evaluate(
                context, project.models.comparison_percent
            )
            comparison_evaluations.append(comparison)
            if model.model_id in {"itm", "p2001"}:
                design = model.evaluate(
                    context, project.target_availability_percent
                )
            elif project.target_availability_percent <= 50.0:
                design = model.evaluate(
                    context, project.target_availability_percent
                )
            else:
                design = comparison
            design_evaluations.append(design)

            curve = model.quantile_curve(
                context, project.models.curve_percentiles
            )
            if curve is not None:
                curves[model.model_id] = curve.to_dict()

            if design.status is ModelStatus.OK and design.loss_db is not None:
                budget = calculate_link_budget(
                    project,
                    direction,
                    model.model_id,
                    design.loss_db,
                    design.percentile,
                )
                budgets.append(budget)
                mc_curve = (
                    curve
                    if curve is not None
                    and curve.complete_annual_distribution
                    else None
                )
                monte_carlo.append(
                    simulate(
                        project=project,
                        direction=direction,
                        model_id=model.model_id,
                        curve=mc_curve,
                        fixed_loss_db=(
                            None if mc_curve is not None else design.loss_db
                        ),
                    )
                )

        comparison_losses = [
            float(item.loss_db)
            for item in comparison_evaluations
            if item.status is ModelStatus.OK and item.loss_db is not None
        ]
        design_budgets_for_assessment = [
            item
            for item in budgets
            if item.model_id in {"itm", "p2001"}
            or project.target_availability_percent <= 50.0
        ]
        assessment = assess(
            project,
            direction,
            design_budgets_for_assessment,
            comparison_losses,
            geometry_dict,
        )
        result["directions"][direction.value] = {
            "transmitter": direction.terminals(project)[0].name,
            "receiver": direction.terminals(project)[1].name,
            "mode_thresholds": all_mode_thresholds(receiver.receiver),
            "comparison_percent": project.models.comparison_percent,
            "comparison_models": [
                item.to_dict() for item in comparison_evaluations
            ],
            "target_availability_percent": project.target_availability_percent,
            "design_models": [item.to_dict() for item in design_evaluations],
            "quantile_curves": curves,
            "link_budgets": [item.to_dict() for item in budgets],
            "monte_carlo": [item.to_dict() for item in monte_carlo],
            "assessment": assessment.to_dict(),
        }
    result["result_sha256"] = _result_hash(result)
    return result, geometry_arrays


def load_and_analyze(
    project_path: str | Path,
) -> tuple[Project, TerrainProfile, dict[str, Any], Any]:
    project, base_dir = Project.from_json(project_path)
    terrain_path = project.resolved_terrain_path(base_dir)
    profile = TerrainProfile.from_csv(terrain_path)
    result, arrays = analyze_project(project, profile)
    return project, profile, result, arrays


def _enabled_models(project: Project):
    models = []
    if project.models.itm:
        models.append(ItmModel())
    if project.models.p1812:
        models.append(P1812Model())
    if project.models.p2001:
        models.append(P2001Model())
    return models


def _result_hash(result: dict[str, Any]) -> str:
    stable = json.loads(json.dumps(result, ensure_ascii=False))
    stable.pop("generated_at_utc", None)
    stable.get("traceability", {}).pop("terrain_reference", None)
    stable.get("project", {}).pop("terrain_profile", None)
    encoded = json.dumps(
        stable, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
