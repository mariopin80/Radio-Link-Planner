from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

COVERAGE_PROJECT_TYPE = "radio-link-planner-coverage"
COVERAGE_PROJECT_SCHEMA = "1.0"
COVERAGE_PROJECT_KEYS = frozenset(
    {
        "name",
        "latitude",
        "longitude",
        "frequency",
        "polarization",
        "mode",
        "radius",
        "resolution_preset",
        "custom_resolution",
        "time_percentage",
        "tx_height",
        "tx_gain",
        "tx_line_loss",
        "tx_power",
        "rx_height",
        "rx_gain",
        "rx_line_loss",
        "rx_sensitivity",
        "output",
    }
)


def write_coverage_project(
    values: Mapping[str, str],
    path: str | Path,
) -> Path:
    """Write a versioned coverage-project file without calculating coverage."""
    missing = COVERAGE_PROJECT_KEYS.difference(values)
    if missing:
        raise ValueError(
            "Projeto de cobertura incompleto: "
            + ", ".join(sorted(missing))
        )
    destination = Path(path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "project_type": COVERAGE_PROJECT_TYPE,
        "schema_version": COVERAGE_PROJECT_SCHEMA,
        "values": {
            key: str(values[key])
            for key in sorted(COVERAGE_PROJECT_KEYS)
        },
    }
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return destination


def read_coverage_project(path: str | Path) -> dict[str, str]:
    """Read and validate a coverage-project file."""
    source = Path(path).resolve()
    payload = json.loads(source.read_text(encoding="utf-8"))
    if payload.get("project_type") != COVERAGE_PROJECT_TYPE:
        raise ValueError("O arquivo não é um projeto de cobertura.")
    if payload.get("schema_version") != COVERAGE_PROJECT_SCHEMA:
        raise ValueError(
            "Versão de projeto de cobertura não suportada: "
            f"{payload.get('schema_version')!r}."
        )
    values = payload.get("values")
    if not isinstance(values, dict):
        raise ValueError("O projeto de cobertura não contém parâmetros válidos.")
    missing = COVERAGE_PROJECT_KEYS.difference(values)
    if missing:
        raise ValueError(
            "Projeto de cobertura incompleto: "
            + ", ".join(sorted(missing))
        )
    return {
        key: str(values[key])
        for key in COVERAGE_PROJECT_KEYS
    }
