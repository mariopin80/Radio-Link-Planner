from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from .domain import Direction, Project
from .i18n import choice_label, tr
from .link_budget import LinkBudget
from .modes import threshold_dbm


AGREEMENT_CRITERIA = (
    "Concordância entre modelos: alta até 3 dB de dispersão, média acima de 3 até 6 dB "
    "e baixa acima de 6 dB. A dispersão é a diferença entre a maior e a menor perda prevista."
)
LOCAL_NOISE_UNKNOWN = "o ruído local do receptor ainda não foi medido"
VIABILITY_CRITERIA = (
    "Margem de projeto: robusto quando todas são ≥10 dB; viável quando todas são ≥3 dB; "
    "marginal quando ao menos uma é ≥−3 dB; improvável abaixo disso; indeterminado sem margem aplicável."
)


@dataclass(frozen=True)
class TechnicalAssessment:
    classification: str
    model_agreement: str
    model_spread_db: float | None
    model_loss_extremes: tuple[tuple[str, float], ...]
    closest_model_pair: tuple[tuple[str, float], ...]
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
    comparison_losses: dict[str, float],
    geometry: dict,
) -> TechnicalAssessment:
    margins = [item.fade_margin_db for item in design_budgets if math.isfinite(item.fade_margin_db)]
    available = sorted(
        ((model, loss) for model, loss in comparison_losses.items() if math.isfinite(loss)),
        key=lambda item: item[1],
    )
    extremes = (available[0], available[-1]) if len(available) >= 2 else ()
    spread = extremes[1][1] - extremes[0][1] if extremes else None
    closest = ()
    if len(available) >= 3:
        closest = min(zip(available, available[1:]), key=lambda pair: pair[1][1] - pair[0][1])
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

    if spread is None:
        agreement = "insufficient"
    elif spread > 6.0:
        agreement = "low"
    elif spread > 3.0:
        agreement = "medium"
    else:
        agreement = "high"

    limiting: list[str] = []
    if geometry["worst_obstruction_m"] > 0.0:
        limiting.append("deep_terrain_obstruction")
    fresnel_obstructed = geometry.get("fresnel_obstructed_percent")
    if fresnel_obstructed is None:
        fresnel_obstructed = geometry["fresnel_60_obstructed_percent"]
    if fresnel_obstructed > 50.0:
        limiting.append("first_fresnel_zone_obstructed")
    if spread is not None and spread > 6.0:
        limiting.append("strong_model_divergence")
    if margins and min(margins) < 3.0:
        limiting.append("small_or_negative_fade_margin")

    uncertainties = [
        "vegetação e edificações não estão representadas"
        if not project.clutter_included
        else "a qualidade da cobertura do solo varia ao longo do percurso",
        LOCAL_NOISE_UNKNOWN
        if direction.terminals(project)[1].receiver.external_noise_db == 0.0
        else "o ruído externo se baseia na estimativa configurada",
        "erros verticais do DEM não são amostrados no Monte Carlo 0.1",
    ]
    if project.metadata.get("terrain_zone_assumption") == "all_inland_land":
        uncertainties.append(
            "o perfil automático assume zona terrestre interior em todo o "
            "percurso; enlaces costeiros ou sobre água exigem revisão da "
            "classificação mar/terra"
        )
    recommendations = _recommendations(project, direction, classification, margins, limiting)
    return TechnicalAssessment(
        classification=classification,
        model_agreement=agreement,
        model_spread_db=spread,
        model_loss_extremes=extremes,
        closest_model_pair=closest,
        limiting_factors=tuple(limiting),
        uncertainties=tuple(uncertainties),
        recommendations=tuple(recommendations),
    )


def _recommendations(
    project: Project, direction: Direction, classification: str,
    margins: list[float], limiting: list[str],
) -> list[dict]:
    if classification in {"robust", "indeterminate"}:
        return []
    transmitter, receiver = direction.terminals(project)
    items: list[dict] = []
    cable_improvement = max(0.0, transmitter.line_loss_db - 0.5) + max(
        0.0, receiver.line_loss_db - 0.5
    )
    if cable_improvement > 0.0:
        items.append(
            {
                "action": "reduzir para 0,5 dB as perdas de linha que excedem esse valor",
                "estimated_margin_improvement_db": cable_improvement,
                "basis": "estimativa se os cabos e conectores atingirem a perda indicada",
            }
        )
    fm_threshold, _ = threshold_dbm(receiver.receiver, "FM")
    ssb_threshold, _ = threshold_dbm(receiver.receiver, "SSB")
    if (
        project.allow_mode_change and project.primary_mode.upper() == "FM"
        and ssb_threshold < fm_threshold
    ):
        items.append(
            {
                "action": "usar SSB quando isso for operacionalmente aceitável",
                "estimated_margin_improvement_db": fm_threshold - ssb_threshold,
                "basis": "diferença entre os limiares do receptor; a potência recebida é a mesma",
            }
        )
    if classification in {"marginal", "improbable"}:
        additional_margin = 3.0 - min(margins)
        items.append({
            "action": "avaliar ganho líquido combinado de antenas para atingir 3 dB de margem",
            "estimated_margin_improvement_db": additional_margin,
            "basis": "ganho adicional necessário no pior modelo; validar as antenas e o apontamento",
        })
        if {"deep_terrain_obstruction", "first_fresnel_zone_obstructed"}.intersection(limiting):
            items.insert(0, {
                "action": "avaliar a elevação das antenas com a ferramenta de otimização de altura",
                "basis": "obstrução do percurso; simular novamente para estimar a variação da margem",
            })
    return items


def describe_agreement(assessment: dict) -> str:
    if assessment.get("model_spread_db") is None or not assessment.get("model_loss_extremes"):
        return tr("Concordância entre modelos: dados insuficientes (são necessárias duas perdas válidas).")
    (lowest_model, lowest_loss), (highest_model, highest_loss) = assessment["model_loss_extremes"]
    description = tr(
        "Concordância entre modelos: {level} • dispersão {spread:.2f} dB "
        "({low_model} {low_loss:.2f} dB ↔ {high_model} {high_loss:.2f} dB).",
        level=choice_label(assessment["model_agreement"]), spread=assessment["model_spread_db"],
        low_model=lowest_model.upper(), low_loss=lowest_loss,
        high_model=highest_model.upper(), high_loss=highest_loss,
    )
    if assessment["model_agreement"] == "low" and assessment.get("closest_model_pair"):
        (first, first_loss), (second, second_loss) = assessment["closest_model_pair"]
        description += " " + tr(
            "{first} e {second} estão a {difference:.2f} dB entre si.",
            first=first.upper(), second=second.upper(), difference=second_loss - first_loss,
        )
    return description


def describe_assessment_basis(assessment: dict) -> str:
    models = assessment.get("design_model_ids")
    if models is None:
        return ""
    if not models:
        return tr("Nenhum modelo calculou a margem na meta de projeto.")
    return tr("Modelos que sustentam o parecer na meta: {models}.",
              models=", ".join(model.upper() for model in models))


def model_diagnostic_lines(direction: dict) -> list[str]:
    diagnostics = (
        f"{model['model_id'].upper()} · {tr(warning)}"
        for key in ("design_models", "comparison_models")
        for model in direction.get(key, ())
        for warning in model.get("warnings", ())
    )
    return list(dict.fromkeys(diagnostics))


def recommendation_lines(assessment: dict) -> list[str]:
    classification = assessment["classification"]
    if classification == "robust":
        lines = [tr("Os modelos indicam margem suficiente nas condições simuladas.")]
        if LOCAL_NOISE_UNKNOWN in assessment.get("uncertainties", ()):
            lines.append(tr("Verifique o ruído e a interferência no receptor antes de decidir sobre o equipamento."))
        return lines
    if classification == "indeterminate":
        return [tr("Confirme os dados e obtenha uma margem de projeto para orientar as recomendações.")]
    items = assessment["recommendations"]
    lines = []
    if classification == "viable":
        lines.append(
            tr("Opções para aumentar a reserva operacional.") if items else
            tr("Os resultados indicam reserva operacional; mantenha a configuração nas condições analisadas.")
        )
    for item in items:
        action = tr(item["action"])
        basis = tr(item["basis"])
        gain = item.get("estimated_margin_improvement_db")
        if gain is None:
            lines.append(f"{action} ({basis}).")
        else:
            lines.append(f"{action} (+{gain:.1f} dB, {basis}).")
    return lines
