from __future__ import annotations

import ctypes
import hashlib
import os
import platform
from pathlib import Path

import numpy as np

from ..domain import Direction, Polarization
from .base import (
    ModelContext,
    ModelEvaluation,
    ModelStatus,
    QuantileCurve,
)


ITM_COMMIT = "183ad95bd813a8be11009df396e1c631356864b2"


class _IntermediateValues(ctypes.Structure):
    _fields_ = [
        ("theta_hzn", ctypes.c_double * 2),
        ("d_hzn__meter", ctypes.c_double * 2),
        ("h_e__meter", ctypes.c_double * 2),
        ("N_s", ctypes.c_double),
        ("delta_h__meter", ctypes.c_double),
        ("A_ref__db", ctypes.c_double),
        ("A_fs__db", ctypes.c_double),
        ("d__km", ctypes.c_double),
        ("mode", ctypes.c_int),
    ]


class ItmModel:
    model_id = "itm"
    model_name = "NTIA ITS Irregular Terrain Model"
    model_version = f"1.3 ({ITM_COMMIT[:12]})"

    def __init__(self, library_path: str | Path | None = None) -> None:
        self.library_path = self._resolve_library(library_path)
        self.library_sha256 = (
            _sha256_file(self.library_path) if self.library_path else None
        )
        self._library: ctypes.CDLL | None = None
        self._function = None

    @staticmethod
    def _resolve_library(path: str | Path | None) -> Path | None:
        if path is not None:
            candidate = Path(path).expanduser().resolve()
            return candidate if candidate.exists() else None
        environment_path = os.environ.get("RADIO_LINK_ITM_LIBRARY")
        if environment_path:
            candidate = Path(environment_path).expanduser().resolve()
            if candidate.exists():
                return candidate
        suffix = {
            "Windows": "itm.dll",
            "Darwin": "libitm.dylib",
        }.get(platform.system(), "libitm.so")
        project_root = Path(__file__).resolve().parents[3]
        candidates = [
            project_root / "vendor" / "ntia-itm" / "build" / suffix,
            project_root / ".local" / "models" / suffix,
        ]
        return next((item for item in candidates if item.exists()), None)

    def _load(self):
        if self.library_path is None:
            raise FileNotFoundError(
                "ITM native library not found; run scripts/build_itm.py"
            )
        if self._function is not None:
            return self._function
        self._library = ctypes.CDLL(str(self.library_path))
        function = self._library.ITM_P2P_CR_Ex
        function.argtypes = [
            ctypes.c_double,
            ctypes.c_double,
            ctypes.POINTER(ctypes.c_double),
            ctypes.c_int,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.c_int,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.c_int,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_long),
            ctypes.POINTER(_IntermediateValues),
        ]
        function.restype = ctypes.c_int
        self._function = function
        return function

    def evaluate(
        self, context: ModelContext, percentile: float
    ) -> ModelEvaluation:
        if not 0.0 < percentile < 100.0:
            return self._failure(
                context,
                ModelStatus.OUTSIDE_SCOPE,
                f"ITM reliability must be between 0 and 100, got {percentile}",
            )
        if not 20.0 <= context.project.frequency_mhz <= 20_000.0:
            return self._failure(
                context,
                ModelStatus.OUTSIDE_SCOPE,
                "ITM supports 20 MHz to 20 GHz",
            )
        try:
            function = self._load()
            profile = context.directional_profile.resample_uniform()
            transmitter, receiver = context.transmitter_receiver
            elevations = np.asarray(profile.elevation_m, dtype=np.float64)
            pfl_values = np.concatenate(
                (
                    [len(elevations) - 1, profile.nominal_step_m],
                    elevations,
                )
            ).astype(np.float64)
            pfl = (ctypes.c_double * len(pfl_values))(*pfl_values)
            loss = ctypes.c_double()
            warning_bits = ctypes.c_long()
            intermediate = _IntermediateValues()
            polarization = (
                1
                if context.project.polarization is Polarization.VERTICAL
                else 0
            )
            error = function(
                transmitter.antenna_height_m,
                receiver.antenna_height_m,
                pfl,
                context.project.environment.itm_climate,
                context.project.environment.surface_refractivity_n,
                context.project.frequency_mhz,
                polarization,
                context.project.environment.ground_permittivity,
                context.project.environment.ground_conductivity_s_m,
                context.project.environment.itm_variability_mode,
                50.0,
                percentile,
                ctypes.byref(loss),
                ctypes.byref(warning_bits),
                ctypes.byref(intermediate),
            )
            if error != 0:
                return self._failure(
                    context,
                    ModelStatus.ERROR,
                    f"ITM returned error code {error}",
                )
            mechanism = {
                1: "line_of_sight",
                2: "diffraction",
                3: "troposcatter",
            }.get(intermediate.mode, "unknown")
            warnings = (
                (f"ITM warning bitmask: {warning_bits.value}",)
                if warning_bits.value
                else ()
            )
            return ModelEvaluation(
                model_id=self.model_id,
                model_name=self.model_name,
                model_version=self.model_version,
                status=ModelStatus.OK,
                direction=context.direction.value,
                loss_db=float(loss.value),
                percentile=float(percentile),
                percentile_meaning="reliability_percent",
                mechanism=mechanism,
                warnings=warnings,
                details={
                    "confidence_percent": 50.0,
                    "warning_bitmask": int(warning_bits.value),
                    "free_space_loss_db": float(intermediate.A_fs__db),
                    "reference_attenuation_db": float(intermediate.A_ref__db),
                    "terrain_irregularity_m": float(
                        intermediate.delta_h__meter
                    ),
                    "horizon_distance_tx_km": float(
                        intermediate.d_hzn__meter[0] / 1000.0
                    ),
                    "horizon_distance_rx_km": float(
                        intermediate.d_hzn__meter[1] / 1000.0
                    ),
                    "surface_refractivity_n": float(intermediate.N_s),
                    "native_library_filename": self.library_path.name,
                    "native_library_sha256": self.library_sha256,
                },
            )
        except FileNotFoundError as exc:
            return self._failure(context, ModelStatus.UNAVAILABLE, str(exc))
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
        return QuantileCurve(
            model_id=self.model_id,
            direction=context.direction.value,
            percentiles=np.asarray(percentiles, dtype=float),
            loss_db=np.asarray([item.loss_db for item in evaluations], dtype=float),
            percentile_meaning="reliability_percent",
            complete_annual_distribution=True,
            warnings=tuple(
                warning
                for item in evaluations
                for warning in item.warnings
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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
