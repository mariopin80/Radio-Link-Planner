from __future__ import annotations

from .i18n import tr

import json
from collections.abc import Mapping
from pathlib import Path

from .antenna import COVERAGE_ANTENNA_DEFAULTS

COVERAGE_PROJECT_TYPE = "radio-link-planner-coverage"
COVERAGE_PROJECT_SCHEMA = "1.3"
COVERAGE_THRESHOLD_OVERRIDES = "rx_thresholds_dbm"
COVERAGE_PROJECT_KEYS = frozenset(
    {
        "name",
        'latitude',
        'longitude',
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
            tr('Projeto de cobertura incompleto: ')
            + ", ".join(sorted(missing))
        )
    destination = Path(path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    saved_values = {key: str(values[key]) for key in sorted(COVERAGE_PROJECT_KEYS)}
    saved_values.update({
        key: str(values.get(key, default))
        for key, default in COVERAGE_ANTENNA_DEFAULTS.items()
    })
    if COVERAGE_THRESHOLD_OVERRIDES in values:
        saved_values[COVERAGE_THRESHOLD_OVERRIDES] = values[COVERAGE_THRESHOLD_OVERRIDES]
    payload = {
        "project_type": COVERAGE_PROJECT_TYPE,
        "schema_version": COVERAGE_PROJECT_SCHEMA,
        "values": saved_values,
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
        raise ValueError(tr('O arquivo não é um projeto de cobertura.'))
    schema = payload.get("schema_version")
    if schema not in {"1.0", "1.1", "1.2", COVERAGE_PROJECT_SCHEMA}:
        raise ValueError(
            tr('Versão de projeto de cobertura não suportada: {x0!r}.', x0=payload.get('schema_version'))
        )
    values = payload.get("values")
    if not isinstance(values, dict):
        raise ValueError(tr('O projeto de cobertura não contém parâmetros válidos.'))
    missing = COVERAGE_PROJECT_KEYS.difference(values)
    if missing:
        raise ValueError(
            tr('Projeto de cobertura incompleto: ')
            + ", ".join(sorted(missing))
        )
    loaded = {
        key: str(values[key])
        for key in COVERAGE_PROJECT_KEYS
    }
    if schema in {"1.2", COVERAGE_PROJECT_SCHEMA}:
        loaded.update({
            key: str(values.get(key, default))
            for key, default in COVERAGE_ANTENNA_DEFAULTS.items()
        })
    if schema == COVERAGE_PROJECT_SCHEMA and COVERAGE_THRESHOLD_OVERRIDES in values:
        loaded[COVERAGE_THRESHOLD_OVERRIDES] = str(values[COVERAGE_THRESHOLD_OVERRIDES])
    return loaded

