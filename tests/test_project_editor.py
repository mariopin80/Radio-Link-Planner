from __future__ import annotations

from dataclasses import replace
import json

import pytest

from radiolink.domain import Project
from radiolink.project_editor import (
    editor_values_from_project,
    project_from_editor_values,
    project_slug,
    write_project_json,
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


def test_link_geometry_loads_legacy_k_and_saves_new_criteria(reference_project, tmp_path):
    payload = reference_project.model_dump(mode="json")
    payload["environment"].pop("fresnel_percent")
    payload["environment"]["effective_earth_k"] = 1.12
    path = tmp_path / "legacy.rlp"
    path.write_text(json.dumps(payload), encoding="utf-8")
    loaded, _ = Project.from_json(path)
    values = editor_values_from_project(loaded)
    assert values.effective_earth_k == 1.12
    assert values.fresnel_percent == 60.0
    changed = replace(values, effective_earth_k=1.0, fresnel_percent=0.0)
    saved = project_from_editor_values(changed, template=loaded)
    path = write_project_json(saved, tmp_path / "updated.rlp")
    restored, _ = Project.from_json(path)
    assert restored.environment.effective_earth_k == 1.0
    assert restored.environment.fresnel_percent == 0.0
    with pytest.raises(ValueError, match="0,1"):
        project_from_editor_values(replace(changed, effective_earth_k=0.1), template=loaded)


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
        "tx_pattern": "directional",
        "tx_hpbw": "72",
        "tx_front_to_back": "18.5",
        "tx_azimuth": "359",
        "tx_line_loss": "1",
        "tx_power": "50",
        "rx_height": "2",
        "rx_gain": "2",
        "rx_line_loss": "1",
        "rx_sensitivity": "-120",
        "output": str(tmp_path / "output"),
        "include_clearance": "1",
        "fresnel_percent": "78",
        "effective_earth_k": "1.2",
    }

    project_path = write_coverage_project(values, tmp_path / "boituva.rlp")

    assert read_coverage_project(project_path) == values
