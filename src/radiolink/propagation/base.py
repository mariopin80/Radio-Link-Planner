from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Protocol

import numpy as np

from ..domain import Direction, Project
from ..terrain import TerrainProfile


class ModelStatus(str, Enum):
    OK = "ok"
    UNAVAILABLE = "unavailable"
    OUTSIDE_SCOPE = "outside_scope"
    ERROR = "error"


@dataclass(frozen=True)
class ModelEvaluation:
    model_id: str
    model_name: str
    model_version: str
    status: ModelStatus
    direction: str
    loss_db: float | None = None
    percentile: float | None = None
    percentile_meaning: str | None = None
    mechanism: str | None = None
    warnings: tuple[str, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["status"] = self.status.value
        return result


@dataclass(frozen=True)
class QuantileCurve:
    model_id: str
    direction: str
    percentiles: np.ndarray
    loss_db: np.ndarray
    percentile_meaning: str
    complete_annual_distribution: bool
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "direction": self.direction,
            "percentiles": self.percentiles.tolist(),
            "loss_db": self.loss_db.tolist(),
            "percentile_meaning": self.percentile_meaning,
            "complete_annual_distribution": self.complete_annual_distribution,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class ModelContext:
    project: Project
    profile: TerrainProfile
    direction: Direction

    @property
    def directional_profile(self) -> TerrainProfile:
        if self.direction is Direction.A_TO_B:
            return self.profile
        return self.profile.reverse()

    @property
    def transmitter_receiver(self):
        return self.direction.terminals(self.project)


class PropagationModel(Protocol):
    model_id: str

    def evaluate(
        self, context: ModelContext, percentile: float
    ) -> ModelEvaluation: ...

    def quantile_curve(
        self, context: ModelContext, percentiles: list[float]
    ) -> QuantileCurve | None: ...
