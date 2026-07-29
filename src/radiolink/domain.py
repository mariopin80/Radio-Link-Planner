from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Polarization(str, Enum):
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"


class ReceiverSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    noise_figure_db: float = Field(default=6.0, ge=0.0, le=30.0)
    external_noise_db: float = Field(default=0.0, ge=0.0, le=60.0)
    threshold_overrides_dbm: dict[str, float] = Field(default_factory=dict)

    @field_validator("threshold_overrides_dbm")
    @classmethod
    def validate_thresholds(cls, value: dict[str, float]) -> dict[str, float]:
        for mode, threshold in value.items():
            if not mode.strip():
                raise ValueError("mode name cannot be empty")
            if not -200.0 <= threshold <= 0.0:
                raise ValueError(f"invalid threshold for {mode}: {threshold}")
        return value


class Terminal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    latitude_deg: float = Field(ge=-90.0, le=90.0)
    longitude_deg: float = Field(ge=-180.0, le=180.0)
    antenna_height_m: float = Field(gt=0.0, le=3000.0)
    antenna_gain_dbi: float = Field(ge=-20.0, le=60.0)
    line_loss_db: float = Field(ge=0.0, le=100.0)
    tx_power_w: float = Field(gt=0.0, le=1_000_000.0)
    receiver: ReceiverSpec = Field(default_factory=ReceiverSpec)


class Environment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    effective_earth_k: float = Field(default=4.0 / 3.0, gt=0.1, le=10.0)
    itm_climate: int = Field(default=2, ge=1, le=7)
    surface_refractivity_n: float = Field(default=301.0, ge=250.0, le=400.0)
    ground_permittivity: float = Field(default=15.0, gt=1.0, le=100.0)
    ground_conductivity_s_m: float = Field(default=0.005, gt=0.0, le=10.0)
    itm_variability_mode: int = Field(default=1, ge=0, le=33)


class ModelSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    itm: bool = True
    p1812: bool = True
    p2001: bool = True
    comparison_percent: float = Field(default=50.0, ge=1.0, le=50.0)
    curve_percentiles: list[float] = Field(
        default_factory=lambda: [
            1.0,
            5.0,
            10.0,
            20.0,
            30.0,
            40.0,
            50.0,
            60.0,
            70.0,
            80.0,
            90.0,
            95.0,
            99.0,
        ]
    )

    @field_validator("curve_percentiles")
    @classmethod
    def validate_percentiles(cls, value: list[float]) -> list[float]:
        cleaned = sorted(set(float(item) for item in value))
        if len(cleaned) < 3:
            raise ValueError("at least three temporal percentiles are required")
        if cleaned[0] <= 0.0 or cleaned[-1] >= 100.0:
            raise ValueError("curve percentiles must be strictly between 0 and 100")
        return cleaned


class UncertaintySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tx_power_sd_db: float = Field(default=0.5, ge=0.0, le=20.0)
    antenna_gain_sd_db: float = Field(default=1.0, ge=0.0, le=20.0)
    line_loss_sd_db: float = Field(default=0.25, ge=0.0, le=20.0)
    receiver_threshold_sd_db: float = Field(default=1.0, ge=0.0, le=20.0)
    pointing_loss_sd_db: float = Field(default=0.5, ge=0.0, le=20.0)
    polarization_loss_sd_db: float = Field(default=0.5, ge=0.0, le=30.0)


class MonteCarloSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runs: int = Field(default=20_000, ge=100, le=2_000_000)
    seed: int = Field(default=20260728, ge=0, le=2**63 - 1)
    uncertainty: UncertaintySpec = Field(default_factory=UncertaintySpec)


class Project(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "0.1"
    name: str = Field(min_length=1)
    frequency_mhz: float = Field(ge=20.0, le=50_000.0)
    polarization: Polarization = Polarization.VERTICAL
    primary_mode: str = "FM"
    target_availability_percent: float = Field(default=70.0, gt=0.0, lt=100.0)
    terminal_a: Terminal
    terminal_b: Terminal
    terrain_profile: str
    terrain_source: str = "user-supplied"
    terrain_resolution_m: float | None = Field(default=None, gt=0.0)
    clutter_included: bool = False
    environment: Environment = Field(default_factory=Environment)
    models: ModelSelection = Field(default_factory=ModelSelection)
    monte_carlo: MonteCarloSpec = Field(default_factory=MonteCarloSpec)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_terminals(self) -> Project:
        if (
            self.terminal_a.latitude_deg == self.terminal_b.latitude_deg
            and self.terminal_a.longitude_deg == self.terminal_b.longitude_deg
        ):
            raise ValueError("terminals must have different coordinates")
        if not any((self.models.itm, self.models.p1812, self.models.p2001)):
            raise ValueError("at least one propagation model must be enabled")
        return self

    @classmethod
    def from_json(cls, path: str | Path) -> tuple[Project, Path]:
        source = Path(path).resolve()
        data = json.loads(source.read_text(encoding="utf-8"))
        project = cls.model_validate(data)
        return project, source.parent

    def resolved_terrain_path(self, base_dir: str | Path) -> Path:
        path = Path(self.terrain_profile)
        if not path.is_absolute():
            path = Path(base_dir) / path
        return path.resolve()


class Direction(str, Enum):
    A_TO_B = "a_to_b"
    B_TO_A = "b_to_a"

    def terminals(self, project: Project) -> tuple[Terminal, Terminal]:
        if self is Direction.A_TO_B:
            return project.terminal_a, project.terminal_b
        return project.terminal_b, project.terminal_a
