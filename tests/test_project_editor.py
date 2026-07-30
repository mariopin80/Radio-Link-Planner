from __future__ import annotations

from dataclasses import replace

import pytest

from radiolink.domain import Project
from radiolink.project_editor import (
    editor_values_from_project,
    project_from_editor_values,
    project_slug,
)
from radiolink.project_files import (
    read_coverage_project,
    write_coverage_project,
)


def test_editor_round_trip_preserves_exposed_link_parameters(
    reference_project: Project,
) -> None:
    values = editor_values_from_project(reference_project)
    rebuilt = project_from_editor_values(values, template=reference_project)

    assert rebuilt.schema_version == "0.2"
    assert rebuilt.name == reference_project.name
    assert rebuilt.frequency_mhz == reference_project.frequency_mhz
    assert rebuilt.primary_mode == reference_project.primary_mode
    assert rebuilt.polarization == reference_project.polarization
    assert rebuilt.terminal_a.latitude_deg == reference_project.terminal_a.latitude_deg
    assert rebuilt.terminal_b.tx_power_w == reference_project.terminal_b.tx_power_w
    assert (
        rebuilt.terminal_b.receiver.threshold_overrides_dbm["FM"]
        == reference_project.terminal_b.receiver.threshold_overrides_dbm["FM"]
    )
    assert rebuilt.environment == reference_project.environment
    assert rebuilt.models == reference_project.models


def test_editor_rejects_link_outside_desktop_distance_scope(
    reference_project: Project,
) -> None:
    values = editor_values_from_project(reference_project)
    too_short = replace(
        values,
        terminal_b=replace(
            values.terminal_b,
            latitude_deg=values.terminal_a.latitude_deg + 0.001,
            longitude_deg=values.terminal_a.longitude_deg,
        ),
    )
    with pytest.raises(ValueError, match="entre 3 e 1000 km"):
        project_from_editor_values(too_short)


def test_project_slug_is_portable() -> None:
    assert project_slug("Morro do Jacu – Palmira") == "morro-do-jacu-palmira"


def test_coverage_project_round_trip_preserves_form_values(tmp_path) -> None:
    values = {
        "name": "Cobertura Boituva",
        "latitude": "-23.283",
        "longitude": "-47.672",
        "frequency": "146.000",
        "polarization": "Vertical",
        "mode": "FM",
        "radius": "100",
        "resolution_preset": "Recomendada",
        "custom_resolution": "500",
        "time_percentage": "50",
        "tx_height": "30",
        "tx_gain": "6",
        "tx_line_loss": "1",
        "tx_power": "50",
        "rx_height": "2",
        "rx_gain": "2",
        "rx_line_loss": "1",
        "rx_sensitivity": "-120",
        "output": str(tmp_path / "output"),
    }

    project_path = write_coverage_project(values, tmp_path / "boituva.rlp")

    assert read_coverage_project(project_path) == values
