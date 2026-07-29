from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

import numpy as np

from ..domain import Polarization
from .base import (
    ModelContext,
    ModelEvaluation,
    ModelStatus,
    QuantileCurve,
)


class P1812Model:
    model_id = "p1812"
    model_name = "ITU-R P.1812-8"

    @property
    def model_version(self) -> str:
        try:
            return version("Py1812")
        except PackageNotFoundError:
            return "not installed"

    def evaluate(
        self, context: ModelContext, percentile: float
    ) -> ModelEvaluation:
        if not 1.0 <= percentile <= 50.0:
            return self._failure(
                context,
                ModelStatus.OUTSIDE_SCOPE,
                "P.1812-8 time percentage is limited to 1–50%",
            )
        if not 30.0 <= context.project.frequency_mhz <= 6000.0:
            return self._failure(
                context,
                ModelStatus.OUTSIDE_SCOPE,
                "P.1812-8 supports 30 MHz to 6 GHz",
            )
        try:
            from Py1812 import P1812

            profile = context.directional_profile
            transmitter, receiver = context.transmitter_receiver
            polarization = (
                2
                if context.project.polarization is Polarization.VERTICAL
                else 1
            )
            loss, field_strength = P1812.bt_loss(
                context.project.frequency_mhz / 1000.0,
                percentile,
                profile.distance_km,
                profile.elevation_m,
                profile.clutter_height_m,
                profile.zone_code.astype(int),
                transmitter.antenna_height_m,
                receiver.antenna_height_m,
                polarization,
                transmitter.latitude_deg,
                receiver.latitude_deg,
                transmitter.longitude_deg,
                receiver.longitude_deg,
            )
            return ModelEvaluation(
                model_id=self.model_id,
                model_name=self.model_name,
                model_version=self.model_version,
                status=ModelStatus.OK,
                direction=context.direction.value,
                loss_db=float(loss),
                percentile=float(percentile),
                percentile_meaning="time_percent_loss_not_exceeded",
                mechanism="combined_path_specific",
                details={"field_strength_dbuv_m": float(field_strength)},
            )
        except (ImportError, FileNotFoundError) as exc:
            return self._failure(
                context,
                ModelStatus.UNAVAILABLE,
                f"P.1812 implementation/data unavailable: {exc}",
            )
        except Exception as exc:
            return self._failure(
                context, ModelStatus.ERROR, f"{type(exc).__name__}: {exc}"
            )

    def quantile_curve(
        self, context: ModelContext, percentiles: list[float]
    ) -> QuantileCurve | None:
        supported = [item for item in percentiles if 1.0 <= item <= 50.0]
        if len(supported) < 3:
            return None
        evaluations = [self.evaluate(context, value) for value in supported]
        if not all(item.status is ModelStatus.OK for item in evaluations):
            return None
        return QuantileCurve(
            model_id=self.model_id,
            direction=context.direction.value,
            percentiles=np.asarray(supported, dtype=float),
            loss_db=np.asarray([item.loss_db for item in evaluations], dtype=float),
            percentile_meaning="time_percent_loss_not_exceeded",
            complete_annual_distribution=False,
            warnings=(
                "P.1812 curve ends at 50%; annual availability is not inferred",
            ),
        )

    def _failure(
        self, context: ModelContext, status: ModelStatus, warning: str
    ) -> ModelEvaluation:
        return ModelEvaluation(
            model_id=self.model_id,
            model_name=self.model_name,
            model_version=self.model_version,
            status=status,
            direction=context.direction.value,
            warnings=(warning,),
        )
