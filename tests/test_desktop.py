from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

import numpy as np

from radiolink.desktop_core import (
    AnalysisOutcome,
    build_desktop_summary,
    bundled_example_path,
)
from radiolink.domain import Project
from radiolink.itu_data import P1812_PRODUCT, install_digital_product


def test_bundled_example_exists() -> None:
    assert bundled_example_path().is_file()


def test_desktop_summary_exposes_decision_and_report(
    reference_project: Project, tmp_path: Path
) -> None:
    report = tmp_path / "report.html"
    outcome = AnalysisOutcome(
        project=reference_project,
        result={
            "geometry": {
                "profile_distance_km": 180.191,
                "worst_obstruction_m": 558.8,
                "worst_obstruction_distance_km": 40.9,
                "fresnel_60_obstructed_percent": 90.2,
            },
            "directions": {
                "a_to_b": {
                    "transmitter": "Morro do Jacu",
                    "receiver": "Palmira",
                    "assessment": {
                        "classification": "marginal",
                        "confidence": "low",
                    },
                    "design_models": [
                        {
                            "model_id": "itm",
                            "status": "ok",
                            "loss_db": 168.36,
                        }
                    ],
                    "link_budgets": [{"model_id": "itm", "fade_margin_db": 7.15}],
                    "monte_carlo": [
                        {
                            "model_id": "itm",
                            "mode_results": [
                                {
                                    "mode": "FM",
                                    "success_probability_percent": 67.2,
                                }
                            ],
                        }
                    ],
                }
            },
            "result_sha256": "abc123",
        },
        paths={"report_html": report},
    )
    summary = build_desktop_summary(outcome)
    assert "Parecer: MARGINAL" in summary
    assert "ITM: perda 168.36 dB" in summary
    assert "sucesso 67.2%" in summary
    assert str(report) in summary


def test_itu_product_is_built_from_user_download_and_sources_are_cleaned(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "p1812.zip"
    with ZipFile(archive, "w") as bundle:
        bundle.writestr("DN50.TXT", "1 2\n3 4\n")
        bundle.writestr("N050.TXT", "5 6\n7 8\n")
    package_dir = tmp_path / "Py1812"
    output = install_digital_product(
        P1812_PRODUCT,
        package_dir=package_dir,
        archive_path=archive,
        cleanup_source_maps=True,
        progress=None,
    )
    with np.load(output) as product:
        assert product["DN50"].tolist() == [[1.0, 2.0], [3.0, 4.0]]
        assert product["N050"].tolist() == [[5.0, 6.0], [7.0, 8.0]]
    assert not (package_dir / "maps" / "DN50.TXT").exists()
    assert not (package_dir / "maps" / "N050.TXT").exists()
