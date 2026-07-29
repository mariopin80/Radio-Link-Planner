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


class P2001Model:
    model_id = "p2001"
    model_name = "ITU-R P.2001-6"

    @property
    def model_version(self) -> str:
        try:
            return version("Py2001")
        except PackageNotFoundError:
            return "not installed"

    def evaluate(
        self, context: ModelContext, percentile: float
    ) -> ModelEvaluation:
        if not 0.0 < percentile < 100.0:
            return self._failure(
                context,
                ModelStatus.OUTSIDE_SCOPE,
                "P.2001-6 time percentage must be between 0 and 100%",
            )
        if not 30.0 <= context.project.frequency_mhz <= 50_000.0:
            return self._failure(
                context,
                ModelStatus.OUTSIDE_SCOPE,
                "P.2001-6 supports 30 MHz to 50 GHz",
            )
        try:
            from Py2001 import P2001

            profile = context.directional_profile
            transmitter, receiver = context.transmitter_receiver
            vertical = (
                1
                if context.project.polarization is Polarization.VERTICAL
                else 0
            )
            loss = P2001.bt_loss(
                profile.distance_km,
                profile.elevation_m,
                profile.zone_code.astype(int),
                context.project.frequency_mhz / 1000.0,
                percentile,
                receiver.longitude_deg,
                receiver.latitude_deg,
                transmitter.longitude_deg,
                transmitter.latitude_deg,
                receiver.antenna_height_m,
                transmitter.antenna_height_m,
                receiver.antenna_gain_dbi,
                transmitter.antenna_gain_dbi,
                vertical,
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
                mechanism="wide_range_combined",
                details={
                    "note": (
                        "terminal antenna gains are also inputs to the "
                        "troposcatter aperture-coupling term"
                    )
                },
            )
        except (ImportError, FileNotFoundError) as exc:
            return self._failure(
                context,
                ModelStatus.UNAVAILABLE,
                f"P.2001 implementation/data unavailable: {exc}",
            )
        except Exception as exc:
            return self._failure(
                context, ModelStatus.ERROR, f"{type(exc).__name__}: {exc}"
            )

    def quantile_curve(
        self, context: ModelContext, percentiles: list[float]
    ) -> QuantileCurve | None:
        evaluations = [self.evaluate(context, value) for value in percentiles]
        if not all(item.status is ModelStatus.OK for item in evaluations):
            return None
        losses = np.asarray([item.loss_db for item in evaluations], dtype=float)
        monotonic = np.maximum.accumulate(losses)
        warnings: tuple[str, ...] = ()
        if not np.allclose(losses, monotonic, atol=1e-8):
            warnings = (
                "non-monotonic numeric values were monotonized for sampling",
            )
        return QuantileCurve(
            model_id=self.model_id,
            direction=context.direction.value,
            percentiles=np.asarray(percentiles, dtype=float),
            loss_db=monotonic,
            percentile_meaning="time_percent_loss_not_exceeded",
            complete_annual_distribution=True,
            warnings=warnings,
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
