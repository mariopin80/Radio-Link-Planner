from __future__ import annotations

from dataclasses import asdict, dataclass

from .domain import Direction, Project
from .link_budget import LinkBudget
from .modes import threshold_dbm


@dataclass(frozen=True)
class TechnicalAssessment:
    classification: str
    confidence: str
    model_spread_db: float | None
    limiting_factors: tuple[str, ...]
    uncertainties: tuple[str, ...]
    recommendations: tuple[dict, ...]

    def to_dict(self) -> dict:
        result = asdict(self)
        result["limiting_factors"] = list(self.limiting_factors)
        result["uncertainties"] = list(self.uncertainties)
        result["recommendations"] = list(self.recommendations)
        return result


def assess(
    project: Project,
    direction: Direction,
    design_budgets: list[LinkBudget],
    comparison_losses: list[float],
    geometry: dict,
) -> TechnicalAssessment:
    margins = [item.fade_margin_db for item in design_budgets]
    spread = (
        max(comparison_losses) - min(comparison_losses)
        if len(comparison_losses) >= 2
        else None
    )
    if margins and min(margins) >= 10.0:
        classification = "robust"
    elif margins and min(margins) >= 3.0:
        classification = "viable"
    elif margins and max(margins) >= -3.0:
        classification = "marginal"
    elif margins:
        classification = "improbable"
    else:
        classification = "indeterminate"

    confidence = "high"
    if spread is not None and spread > 6.0:
        confidence = "low"
    elif spread is not None and spread > 3.0:
        confidence = "medium"
    if not project.clutter_included:
        confidence = _downgrade(confidence)

    limiting: list[str] = []
    if geometry["worst_obstruction_m"] > 0.0:
        limiting.append("deep_terrain_obstruction")
    if geometry["fresnel_60_obstructed_percent"] > 50.0:
        limiting.append("first_fresnel_zone_obstructed")
    if spread is not None and spread > 6.0:
        limiting.append("strong_model_divergence")
    if margins and min(margins) < 3.0:
        limiting.append("small_or_negative_fade_margin")

    uncertainties = [
        "vegetação e edificações não estão representadas"
        if not project.clutter_included
        else "a qualidade da cobertura do solo varia ao longo do percurso",
        "o ruído local do receptor ainda não foi medido"
        if all(
            terminal.receiver.external_noise_db == 0.0
            for terminal in (project.terminal_a, project.terminal_b)
        )
        else "o ruído externo se baseia na estimativa configurada",
        "erros verticais do DEM não são amostrados no Monte Carlo 0.1",
    ]
    recommendations = _recommendations(project, direction)
    return TechnicalAssessment(
        classification=classification,
        confidence=confidence,
        model_spread_db=spread,
        limiting_factors=tuple(limiting),
        uncertainties=tuple(uncertainties),
        recommendations=tuple(recommendations),
    )


def _recommendations(project: Project, direction: Direction) -> list[dict]:
    transmitter, receiver = direction.terminals(project)
    items: list[dict] = []
    if transmitter.antenna_gain_dbi < 9.0:
        items.append(
            {
                "action": (
                    f"aumentar o ganho da antena de {transmitter.name} para 9 dBi"
                ),
                "estimated_margin_improvement_db": 9.0
                - transmitter.antenna_gain_dbi,
                "basis": "ganho direto no orçamento do enlace",
            }
        )
    if receiver.antenna_gain_dbi < 9.0:
        items.append(
            {
                "action": (
                    f"aumentar o ganho da antena de {receiver.name} para 9 dBi"
                ),
                "estimated_margin_improvement_db": 9.0
                - receiver.antenna_gain_dbi,
                "basis": "ganho direto no orçamento do enlace",
            }
        )
    cable_improvement = max(0.0, transmitter.line_loss_db - 0.5) + max(
        0.0, receiver.line_loss_db - 0.5
    )
    if cable_improvement > 0.0:
        items.append(
            {
                "action": "reduzir cada perda de linha para aproximadamente 0,5 dB",
                "estimated_margin_improvement_db": cable_improvement,
                "basis": "redução direta no orçamento do enlace",
            }
        )
    fm_threshold, _ = threshold_dbm(receiver.receiver, "FM")
    ssb_threshold, _ = threshold_dbm(receiver.receiver, "SSB")
    if project.primary_mode.upper() == "FM" and ssb_threshold < fm_threshold:
        items.append(
            {
                "action": "usar SSB quando isso for operacionalmente aceitável",
                "estimated_margin_improvement_db": fm_threshold - ssb_threshold,
                "basis": "modelo de ruído configurado para o receptor",
            }
        )
    items.sort(
        key=lambda item: item["estimated_margin_improvement_db"], reverse=True
    )
    return items


def _downgrade(value: str) -> str:
    return {"high": "medium", "medium": "low", "low": "low"}[value]
