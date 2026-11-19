from __future__ import annotations

from .i18n import tr

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from .domain import Environment, Polarization, Project, ReceiverSpec, Terminal
from .geodesy import great_circle_distance_m
from .modes import MODE_PROFILES, threshold_dbm
from .version import APP_NAME, __version__

MIN_DESKTOP_FREQUENCY_MHZ = 30.0
MAX_DESKTOP_FREQUENCY_MHZ = 3000.0
MIN_DESKTOP_DISTANCE_KM = 3.0
MAX_DESKTOP_DISTANCE_KM = 1000.0


@dataclass(frozen=True)
class TerminalEditorValues:
    name: str
    latitude_deg: float
    longitude_deg: float
    antenna_height_m: float
    antenna_gain_dbi: float
    line_loss_db: float
    tx_power_w: float
    receiver_threshold_dbm: float
    receiver: ReceiverSpec | None = None


@dataclass(frozen=True)
class ProjectEditorValues:
    name: str
    frequency_mhz: float
    polarization: str
    primary_mode: str
    target_availability_percent: float
    terminal_a: TerminalEditorValues
    terminal_b: TerminalEditorValues
    allow_mode_change: bool = False

    @property
    def distance_km(self) -> float:
        return (
            great_circle_distance_m(
                self.terminal_a.latitude_deg,
                self.terminal_a.longitude_deg,
                self.terminal_b.latitude_deg,
                self.terminal_b.longitude_deg,
            )
            / 1000.0
        )


def editor_values_from_project(project: Project) -> ProjectEditorValues:
    mode = project.primary_mode.upper()

    def terminal_values(terminal: Terminal) -> TerminalEditorValues:
        receiver_threshold, _ = threshold_dbm(terminal.receiver, mode)
        return TerminalEditorValues(
            name=terminal.name,
            latitude_deg=terminal.latitude_deg,
            longitude_deg=terminal.longitude_deg,
            antenna_height_m=terminal.antenna_height_m,
            antenna_gain_dbi=terminal.antenna_gain_dbi,
            line_loss_db=terminal.line_loss_db,
            tx_power_w=terminal.tx_power_w,
            receiver_threshold_dbm=receiver_threshold,
            receiver=terminal.receiver.model_copy(deep=True),
        )

    return ProjectEditorValues(
        name=project.name,
        frequency_mhz=project.frequency_mhz,
        polarization=project.polarization.value,
        primary_mode=mode,
        target_availability_percent=project.target_availability_percent,
        terminal_a=terminal_values(project.terminal_a),
        terminal_b=terminal_values(project.terminal_b),
        allow_mode_change=project.allow_mode_change,
    )


def project_from_editor_values(
    values: ProjectEditorValues,
    *,
    template: Project | None = None,
    terrain_profile: str = "terrain_profile.csv",
) -> Project:
    _validate_desktop_scope(values)
    mode = values.primary_mode.upper()
    if mode not in MODE_PROFILES:
        raise ValueError(tr('Modo desconhecido: {x0}', x0=values.primary_mode))
    environment = template.with_standard_geometry().environment if template is not None else Environment()

    def terminal(data: TerminalEditorValues, previous: Terminal | None = None) -> Terminal:
        receiver = data.receiver or (previous.receiver if previous is not None else ReceiverSpec())
        existing_threshold, _ = threshold_dbm(receiver, mode)
        if data.receiver_threshold_dbm != existing_threshold:
            receiver = receiver.model_copy(update={
                "threshold_overrides_dbm": {
                    **receiver.threshold_overrides_dbm, mode: data.receiver_threshold_dbm,
                },
            })
        return Terminal(
            name=data.name.strip(),
            latitude_deg=data.latitude_deg,
            longitude_deg=data.longitude_deg,
            antenna_height_m=data.antenna_height_m,
            antenna_gain_dbi=data.antenna_gain_dbi,
            line_loss_db=data.line_loss_db,
            tx_power_w=data.tx_power_w,
            receiver=receiver,
        )

    if template is None:
        project = Project(
            schema_version="0.2",
            name=values.name.strip(),
            frequency_mhz=values.frequency_mhz,
            polarization=Polarization(values.polarization.lower()),
            primary_mode=mode,
            target_availability_percent=values.target_availability_percent,
            terminal_a=terminal(values.terminal_a),
            terminal_b=terminal(values.terminal_b),
            terrain_profile=terrain_profile,
            terrain_source='Copernicus GLO-30 automático',
            terrain_resolution_m=30.0,
            clutter_included=False,
            allow_mode_change=values.allow_mode_change,
            environment=environment,
            metadata={
                "created_with": f"{APP_NAME} desktop {__version__}",
                "terrain_zone_assumption": "all_inland_land",
            },
        )
    else:
        project = template.model_copy(deep=True)
        project.schema_version = "0.2"
        project.name = values.name.strip()
        project.frequency_mhz = values.frequency_mhz
        project.polarization = Polarization(values.polarization.lower())
        project.primary_mode = mode
        project.target_availability_percent = values.target_availability_percent
        project.allow_mode_change = values.allow_mode_change
        project.environment = environment
        project.terminal_a = terminal(values.terminal_a, template.terminal_a)
        project.terminal_b = terminal(values.terminal_b, template.terminal_b)
        project.terrain_profile = terrain_profile
    return Project.model_validate(project.model_dump(mode="json"))


def write_project_json(project: Project, path: str | Path) -> Path:
    destination = Path(path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(project.model_dump(mode="json"), ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    return destination


def project_slug(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name).strip("-")
    return slug or 'novo-enlace'


def _validate_desktop_scope(values: ProjectEditorValues) -> None:
    if not values.name.strip():
        raise ValueError(tr('Informe um nome para o enlace.'))
    if not (
        MIN_DESKTOP_FREQUENCY_MHZ <= values.frequency_mhz <= MAX_DESKTOP_FREQUENCY_MHZ
    ):
        raise ValueError(
            tr('A frequência deve estar entre 30 e 3000 MHz nesta versão VHF/UHF.')
        )
    if not (MIN_DESKTOP_DISTANCE_KM <= values.distance_km <= MAX_DESKTOP_DISTANCE_KM):
        raise ValueError(
            tr('A distância deve estar entre 3 e 1000 km nesta versão científica.')
        )

