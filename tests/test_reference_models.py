from __future__ import annotations

import pytest

from radiolink.domain import Direction
from radiolink.propagation import ItmModel, P1812Model, P2001Model
from radiolink.propagation.base import ModelContext, ModelStatus


@pytest.mark.reference
def test_itm_reference(reference_project, reference_profile) -> None:
    context = ModelContext(
        project=reference_project,
        profile=reference_profile,
        direction=Direction.A_TO_B,
    )
    result = ItmModel().evaluate(context, 70.0)
    if result.status is ModelStatus.UNAVAILABLE:
        pytest.skip(result.warnings[0])
    assert result.status is ModelStatus.OK
    assert result.loss_db == pytest.approx(168.36556, abs=0.02)
    assert result.mechanism == "diffraction"


@pytest.mark.reference
def test_p1812_reference(reference_project, reference_profile) -> None:
    context = ModelContext(
        project=reference_project,
        profile=reference_profile,
        direction=Direction.A_TO_B,
    )
    result = P1812Model().evaluate(context, 50.0)
    if result.status is ModelStatus.UNAVAILABLE:
        pytest.skip(result.warnings[0])
    assert result.status is ModelStatus.OK
    assert result.loss_db == pytest.approx(171.23501, abs=0.03)


@pytest.mark.reference
@pytest.mark.parametrize(
    ("percentile", "expected"),
    [(50.0, 175.49383), (70.0, 177.33593)],
)
def test_p2001_reference(
    reference_project, reference_profile, percentile, expected
) -> None:
    context = ModelContext(
        project=reference_project,
        profile=reference_profile,
        direction=Direction.A_TO_B,
    )
    result = P2001Model().evaluate(context, percentile)
    if result.status is ModelStatus.UNAVAILABLE:
        pytest.skip(result.warnings[0])
    assert result.status is ModelStatus.OK
    assert result.loss_db == pytest.approx(expected, abs=0.04)
