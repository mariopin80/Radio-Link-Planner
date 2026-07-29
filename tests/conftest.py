from __future__ import annotations

from pathlib import Path

import pytest

from radiolink.domain import Project
from radiolink.terrain import TerrainProfile


ROOT = Path(__file__).resolve().parents[1]
REFERENCE_DIR = ROOT / "tests" / "reference" / "morro_jacu_palmira"


@pytest.fixture(scope="session")
def reference_project() -> Project:
    project, _ = Project.from_json(ROOT / "examples" / "morro_jacu_palmira.json")
    return project


@pytest.fixture(scope="session")
def reference_profile() -> TerrainProfile:
    return TerrainProfile.from_csv(REFERENCE_DIR / "terrain_profile.csv")
