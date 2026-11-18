from dataclasses import replace

import pytest

from radiolink.analysis import assess, describe_agreement, recommendation_lines
from radiolink.domain import Direction
from radiolink.link_budget import calculate_link_budget


@pytest.mark.parametrize(
    "losses, level",
    [
        ({"itm": 120.0, "p1812": 123.0}, "high"),
        ({"itm": 120.0, "p1812": 126.0}, "medium"),
        ({"itm": 113.38, "p1812": 122.17, "p2001": 122.20}, "low"),
        ({"itm": 120.0, "p1812": float("nan")}, "insufficient"),
    ],
)
def test_model_agreement_uses_only_valid_comparison_losses(reference_project, losses, level):
    geometry = {"worst_obstruction_m": 0.0, "fresnel_60_obstructed_percent": 0.0}
    for clutter in (False, True):
        project = reference_project.model_copy(update={"clutter_included": clutter})
        assessment = assess(project, Direction.A_TO_B, [], losses, geometry)
        assert assessment.model_agreement == level
        assert assessment.uncertainties
    text = describe_agreement(assessment.to_dict())
    if level == "low":
        assert "8.82 dB" in text and "0.03 dB" in text
        assert all(model in text for model in ("ITM", "P1812", "P2001"))
    if level == "insufficient":
        assert assessment.model_spread_db is None


@pytest.mark.parametrize(
    "margin, classification",
    [(10.0, "robust"), (3.0, "viable"), (-3.0, "marginal"), (-3.01, "improbable")],
)
def test_recommendations_follow_viability_and_mode_permission(reference_project, margin, classification):
    geometry = {"worst_obstruction_m": 2, "fresnel_60_obstructed_percent": 60}
    budget = calculate_link_budget(reference_project, Direction.A_TO_B, "itm", 130.0, 50.0)
    budget = replace(budget, fade_margin_db=margin)
    for allow_mode_change in (True, False):
        project = reference_project.model_copy(update={"allow_mode_change": allow_mode_change})
        assessment = assess(project, Direction.A_TO_B, [budget], {"itm": 130.0}, geometry)
        assert assessment.classification == classification
        assert assessment.uncertainties
        if classification == "robust":
            assert not assessment.recommendations
            assert "dispensa mudanças" in recommendation_lines(assessment.to_dict())[0]
            continue
        ssb = [item for item in assessment.recommendations if "SSB" in item["action"]]
        assert bool(ssb) is allow_mode_change
        if ssb:
            assert "limiares" in ssb[0]["basis"]
        if classification == "viable":
            assert "reserva operacional" in recommendation_lines(assessment.to_dict())[0]
        else:
            assert "otimização de altura" in assessment.recommendations[0]["action"]
            assert any(item.get("estimated_margin_improvement_db") == 3.0 - margin for item in assessment.recommendations)
