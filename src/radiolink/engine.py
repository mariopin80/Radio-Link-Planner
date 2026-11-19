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
from .height_optimization import height_optimization_for, project_at_heights
from .link_budget import calculate_link_budget
from .modes import all_mode_thresholds
from .monte_carlo import simulate
from .propagation import ItmModel, P1812Model, P2001Model
from .propagation.base import ModelContext, ModelEvaluation, ModelStatus, PropagationModel
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
    optimization = height_optimization_for(project, profile)
    baseline = None
    if optimization:
        baseline = project_at_heights(
            project, optimization["original_a_m"], optimization["original_b_m"],
            optimization["effective_earth_k"],
        )
    result: dict[str, Any] = {
        "schema_version": "0.2",
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
            design = _evaluate_design(model, context, comparison)
            design_evaluations.append(design)

            percentiles = project.models.curve_percentiles
            if model.model_id in {"itm", "p2001"}:
                percentiles = sorted(set(percentiles).union(
                    (0.1, 0.5, 99.5, 99.9, project.target_availability_percent)
                ))
            curve = model.quantile_curve(context, percentiles)
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
                        fixed_percentile=design.percentile,
                    )
                )

        comparison_losses = {
            item.model_id: float(item.loss_db)
            for item in comparison_evaluations
            if item.status is ModelStatus.OK and item.loss_db is not None
        }
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
            "assessment": {
                **assessment.to_dict(),
                "design_model_ids": [item.model_id for item in design_budgets_for_assessment],
            },
        }
    if baseline is not None:
        result["height_optimization"] = {
            **optimization,
            "model_comparison": compare_height_designs(baseline, project, profile, result),
        }
    result["result_sha256"] = _result_hash(result)
    return result, geometry_arrays


def _evaluate_design(
    model: PropagationModel, context: ModelContext, comparison: ModelEvaluation | None = None
) -> ModelEvaluation:
    project = context.project
    if model.model_id == "p1812" and project.target_availability_percent > 50.0:
        return comparison if comparison is not None else model.evaluate(
            context, project.models.comparison_percent
        )
    return model.evaluate(context, project.target_availability_percent)


def compare_height_designs(
    before: Project, after: Project, profile: TerrainProfile,
    after_result: dict[str, Any] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Evaluate both height configurations at the report's design percentiles."""
    comparisons = {}
    models = _enabled_models(after)
    for direction in Direction:
        before_context = ModelContext(before, profile, direction)
        after_context = ModelContext(after, profile, direction)
        existing = after_result["directions"][direction.value] if after_result else None
        rows = []
        for model in models:
            before_design = _evaluate_design(model, before_context)
            before_values = _design_summary(before, direction, before_design)
            if existing is None:
                after_design = _evaluate_design(model, after_context)
                after_values = _design_summary(after, direction, after_design)
            else:
                design = next(item for item in existing["design_models"] if item["model_id"] == model.model_id)
                budget = next((item for item in existing["link_budgets"] if item["model_id"] == model.model_id), {})
                after_values = {
                    "status": design["status"], "percentile": design["percentile"],
                    "loss_db": design["loss_db"], "margin_db": budget.get("fade_margin_db"),
                }
            rows.append({"model_id": model.model_id, "before": before_values, "after": after_values})
        comparisons[direction.value] = rows
    return comparisons


def _design_summary(project: Project, direction: Direction, design: ModelEvaluation) -> dict[str, Any]:
    margin = None
    if design.status is ModelStatus.OK and design.loss_db is not None:
        budget = calculate_link_budget(project, direction, design.model_id, design.loss_db, design.percentile)
        margin = budget.fade_margin_db
    return {
        "status": design.status.value, "percentile": design.percentile,
        "loss_db": design.loss_db, "margin_db": margin,
    }


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
