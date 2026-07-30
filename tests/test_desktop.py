from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pytest

from radiolink.desktop_core import (
    AnalysisOutcome,
    FormAnalysisRequest,
    build_desktop_summary,
    bundled_example_path,
    run_form_analysis,
)
from radiolink.domain import Project
from radiolink.itu_data import (
    P1812_PRODUCT,
    DigitalProduct,
    install_digital_product,
    load_digital_product_module,
)
from radiolink.report import describe_geometry_clearance


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


def test_clear_path_is_described_by_its_minimum_clearance() -> None:
    description = describe_geometry_clearance(
        {
            "worst_clearance_m": 12.34,
            "worst_obstruction_m": 0.0,
            "worst_obstruction_distance_km": 4.01,
        }
    )

    assert description == "Menor folga geométrica: 12.3 m a 4.0 km"


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


def test_itu_product_defaults_to_local_app_data(
    tmp_path: Path,
    monkeypatch,
) -> None:
    archive = tmp_path / "p1812.zip"
    with ZipFile(archive, "w") as bundle:
        bundle.writestr("DN50.TXT", "1 2\n3 4\n")
        bundle.writestr("N050.TXT", "5 6\n7 8\n")
    local_app_data = tmp_path / "LocalAppData"
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))

    output = install_digital_product(
        P1812_PRODUCT,
        archive_path=archive,
        cleanup_source_maps=True,
        progress=None,
    )

    assert output == (
        local_app_data
        / "RadioLinkPlanner"
        / "ITU-R"
        / "Py1812"
        / "P1812.npz"
    )
    assert output.is_file()


def test_itu_product_install_can_be_cancelled(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "p1812.zip"
    with ZipFile(archive, "w") as bundle:
        bundle.writestr("DN50.TXT", "1 2\n3 4\n")
        bundle.writestr("N050.TXT", "5 6\n7 8\n")
    package_dir = tmp_path / "Py1812"
    checks = 0

    def cancel_after_preflight() -> bool:
        nonlocal checks
        checks += 1
        return checks > 1

    with pytest.raises(InterruptedError, match="cancelled"):
        install_digital_product(
            P1812_PRODUCT,
            package_dir=package_dir,
            archive_path=archive,
            cleanup_source_maps=True,
            progress=None,
            cancel_check=cancel_after_preflight,
        )

    assert not (package_dir / "P1812.npz").exists()


def test_reference_module_reads_product_from_user_data(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_name = "FakeITUModel"
    install_root = tmp_path / "Program Files"
    package = install_root / package_name
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "Reference.py").write_text(
        "\n".join(
            (
                "from importlib.resources import files",
                "import numpy as np",
                (
                    f'with np.load(files("{package_name}").joinpath("Fake.npz")) '
                    "as product:"
                ),
                '    VALUE = int(product["value"][0])',
            )
        ),
        encoding="utf-8",
    )
    user_data = tmp_path / "LocalAppData" / package_name
    user_data.mkdir(parents=True)
    np.savez(user_data / "Fake.npz", value=np.asarray([42]))
    product = DigitalProduct(
        recommendation="P.test",
        distribution_name=package_name,
        package_name=package_name,
        output_filename="Fake.npz",
        components_url="https://example.invalid/fake.zip",
        expected_files=frozenset(),
    )
    monkeypatch.syspath_prepend(str(install_root))

    try:
        module = load_digital_product_module(
            product,
            "Reference",
            data_dir=user_data,
        )
        assert module.VALUE == 42
    finally:
        sys.modules.pop(f"{package_name}.Reference", None)
        sys.modules.pop(package_name, None)


def test_form_analysis_bundles_loaded_terrain_and_project(
    reference_project: Project,
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = (
        Path(__file__).resolve().parent
        / "reference"
        / "morro_jacu_palmira"
        / "terrain_profile.csv"
    )

    def fake_analyze(
        project: Project,
        profile,
        output_directory: Path,
        *,
        make_plots: bool,
        progress,
    ) -> AnalysisOutcome:
        report = Path(output_directory) / "report.html"
        report.write_text("<html></html>", encoding="utf-8")
        return AnalysisOutcome(
            project=project,
            result={"result_sha256": "test"},
            paths={"report_html": report},
        )

    monkeypatch.setattr("radiolink.desktop_core._ensure_model_data", lambda *_: None)
    monkeypatch.setattr("radiolink.desktop_core._analyze", fake_analyze)
    outcome = run_form_analysis(
        FormAnalysisRequest(
            project=reference_project,
            output_directory=tmp_path / "result",
            monte_carlo_runs=500,
            make_plots=False,
            existing_terrain_path=source,
        )
    )

    assert outcome.paths["project_json"].is_file()
    assert outcome.paths["terrain_profile"].is_file()
    saved, base_dir = Project.from_json(outcome.paths["project_json"])
    assert saved.monte_carlo.runs == 500
    assert saved.resolved_terrain_path(base_dir) == outcome.paths["terrain_profile"]


@pytest.mark.reference
def test_form_pipeline_executes_all_models_and_writes_map(
    reference_project: Project,
    tmp_path: Path,
) -> None:
    if (
        importlib.util.find_spec("Py1812") is None
        or importlib.util.find_spec("Py2001") is None
    ):
        pytest.skip("optional P.1812/P.2001 implementations are not installed")
    source = (
        Path(__file__).resolve().parent
        / "reference"
        / "morro_jacu_palmira"
        / "terrain_profile.csv"
    )
    outcome = run_form_analysis(
        FormAnalysisRequest(
            project=reference_project,
            output_directory=tmp_path / "full-result",
            monte_carlo_runs=100,
            make_plots=False,
            existing_terrain_path=source,
        )
    )

    statuses = {
        model["model_id"]: model["status"]
        for direction in outcome.result["directions"].values()
        for model in direction["design_models"]
    }
    assert statuses == {"itm": "ok", "p1812": "ok", "p2001": "ok"}
    report = outcome.paths["report_html"].read_text(encoding="utf-8")
    assert 'id="route-map"' in report
    assert "maplibregl.Map" in report
    assert outcome.paths["project_json"].is_file()
    assert outcome.paths["terrain_profile"].is_file()
