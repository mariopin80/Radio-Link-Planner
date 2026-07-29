from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass

import numpy as np

from .domain import Direction, Project
from .link_budget import watts_to_dbm
from .modes import MODE_PROFILES, threshold_dbm
from .propagation.base import QuantileCurve


@dataclass(frozen=True)
class MonteCarloModeResult:
    mode: str
    threshold_dbm: float
    success_probability_percent: float
    margin_p05_db: float
    margin_p50_db: float
    margin_p95_db: float


@dataclass(frozen=True)
class MonteCarloResult:
    model_id: str
    direction: str
    runs: int
    seed: int
    temporal_sampling: str
    received_power_p05_dbm: float
    received_power_p50_dbm: float
    received_power_p95_dbm: float
    mode_results: tuple[MonteCarloModeResult, ...]
    sensitivity: tuple[dict, ...]
    histogram_edges_dbm: tuple[float, ...]
    histogram_counts: tuple[int, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict:
        result = asdict(self)
        result["mode_results"] = [asdict(item) for item in self.mode_results]
        result["sensitivity"] = list(self.sensitivity)
        result["histogram_edges_dbm"] = list(self.histogram_edges_dbm)
        result["histogram_counts"] = list(self.histogram_counts)
        result["warnings"] = list(self.warnings)
        return result


def simulate(
    project: Project,
    direction: Direction,
    model_id: str,
    curve: QuantileCurve | None,
    fixed_loss_db: float | None = None,
) -> MonteCarloResult:
    if curve is None and fixed_loss_db is None:
        raise ValueError("curve or fixed loss must be provided")
    transmitter, receiver = direction.terminals(project)
    spec = project.monte_carlo
    uncertainty = spec.uncertainty
    seed = _derived_seed(spec.seed, model_id, direction.value)
    rng = np.random.default_rng(seed)
    runs = spec.runs

    if curve is not None and curve.complete_annual_distribution:
        time_percentile = rng.uniform(
            float(curve.percentiles[0]),
            float(curve.percentiles[-1]),
            runs,
        )
        path_loss = np.interp(
            time_percentile, curve.percentiles, curve.loss_db
        )
        temporal_sampling = "model_temporal_quantile_curve"
        warnings = tuple(curve.warnings)
    else:
        baseline = (
            fixed_loss_db
            if fixed_loss_db is not None
            else float(np.interp(50.0, curve.percentiles, curve.loss_db))
        )
        path_loss = np.full(runs, baseline, dtype=float)
        temporal_sampling = "conditional_fixed_quantile"
        warnings = (
            "result is conditional on one propagation quantile, not annual availability",
        )
        if curve is not None:
            warnings += tuple(curve.warnings)

    tx_power_error = rng.normal(0.0, uncertainty.tx_power_sd_db, runs)
    tx_gain_error = rng.normal(0.0, uncertainty.antenna_gain_sd_db, runs)
    rx_gain_error = rng.normal(0.0, uncertainty.antenna_gain_sd_db, runs)
    tx_line_error = rng.normal(0.0, uncertainty.line_loss_sd_db, runs)
    rx_line_error = rng.normal(0.0, uncertainty.line_loss_sd_db, runs)
    pointing_loss = np.abs(
        rng.normal(0.0, uncertainty.pointing_loss_sd_db, runs)
    )
    polarization_loss = np.abs(
        rng.normal(0.0, uncertainty.polarization_loss_sd_db, runs)
    )

    tx_line = np.maximum(0.0, transmitter.line_loss_db + tx_line_error)
    rx_line = np.maximum(0.0, receiver.line_loss_db + rx_line_error)
    received_power = (
        watts_to_dbm(transmitter.tx_power_w)
        + tx_power_error
        + transmitter.antenna_gain_dbi
        + tx_gain_error
        - tx_line
        - path_loss
        + receiver.antenna_gain_dbi
        + rx_gain_error
        - rx_line
        - pointing_loss
        - polarization_loss
    )

    threshold_error = rng.normal(
        0.0, uncertainty.receiver_threshold_sd_db, runs
    )
    mode_results: list[MonteCarloModeResult] = []
    primary_margin: np.ndarray | None = None
    for mode_id in MODE_PROFILES:
        nominal_threshold, _ = threshold_dbm(receiver.receiver, mode_id)
        margin = received_power - (nominal_threshold + threshold_error)
        if mode_id == project.primary_mode.upper():
            primary_margin = margin
        p05, p50, p95 = np.percentile(margin, [5.0, 50.0, 95.0])
        mode_results.append(
            MonteCarloModeResult(
                mode=mode_id,
                threshold_dbm=float(nominal_threshold),
                success_probability_percent=float(100.0 * np.mean(margin >= 0.0)),
                margin_p05_db=float(p05),
                margin_p50_db=float(p50),
                margin_p95_db=float(p95),
            )
        )
    if primary_margin is None:
        nominal_threshold, _ = threshold_dbm(
            receiver.receiver, project.primary_mode
        )
        primary_margin = received_power - (nominal_threshold + threshold_error)

    factors = {
        "propagation_loss": -path_loss,
        "tx_power": tx_power_error,
        "tx_antenna_gain": tx_gain_error,
        "rx_antenna_gain": rx_gain_error,
        "tx_line_loss": -tx_line,
        "rx_line_loss": -rx_line,
        "pointing_loss": -pointing_loss,
        "polarization_loss": -polarization_loss,
        "receiver_threshold": -threshold_error,
    }
    sensitivity: list[dict] = []
    margin_std = float(np.std(primary_margin))
    for name, values in factors.items():
        factor_std = float(np.std(values))
        correlation = (
            float(np.corrcoef(values, primary_margin)[0, 1])
            if factor_std > 0.0 and margin_std > 0.0
            else 0.0
        )
        sensitivity.append(
            {
                "factor": name,
                "correlation_with_margin": correlation,
                "absolute_correlation": abs(correlation),
            }
        )
    sensitivity.sort(key=lambda item: item["absolute_correlation"], reverse=True)
    counts, edges = np.histogram(received_power, bins=50)
    rp05, rp50, rp95 = np.percentile(
        received_power, [5.0, 50.0, 95.0]
    )
    return MonteCarloResult(
        model_id=model_id,
        direction=direction.value,
        runs=runs,
        seed=seed,
        temporal_sampling=temporal_sampling,
        received_power_p05_dbm=float(rp05),
        received_power_p50_dbm=float(rp50),
        received_power_p95_dbm=float(rp95),
        mode_results=tuple(mode_results),
        sensitivity=tuple(sensitivity[:8]),
        histogram_edges_dbm=tuple(float(value) for value in edges),
        histogram_counts=tuple(int(value) for value in counts),
        warnings=warnings,
    )


def _derived_seed(base_seed: int, model_id: str, direction: str) -> int:
    payload = f"{base_seed}:{model_id}:{direction}".encode("utf-8")
    digest = hashlib.sha256(payload).digest()
    return int.from_bytes(digest[:8], "big") & (2**63 - 1)
