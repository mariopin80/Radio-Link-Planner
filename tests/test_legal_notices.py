from __future__ import annotations

from radiolink.legal_notices import (
    COPERNICUS_GLO30_DERIVED_CREDIT,
    COPERNICUS_GLO30_NO_LIABILITY,
    OSM_COPYRIGHT_URL,
    uses_copernicus_glo30,
)
from radiolink.map_picker import build_picker_html


def test_copernicus_attribution_applies_only_to_identified_terrain() -> None:
    assert uses_copernicus_glo30("Copernicus GLO-30, downloaded locally")
    assert uses_copernicus_glo30("COPERNICUS GLO-30")
    assert not uses_copernicus_glo30("user-supplied")
    assert not uses_copernicus_glo30(None)


def test_link_markdown_includes_required_copernicus_notice(
    reference_project,
    reference_profile,
) -> None:
    from radiolink.engine import analyze_project
    from radiolink.report import build_markdown_summary

    project = reference_project.model_copy(deep=True)
    project.models.itm = project.models.p1812 = project.models.p2001 = False
    project.terrain_source = "Copernicus GLO-30"
    result, _ = analyze_project(project, reference_profile)
    summary = build_markdown_summary(project, result)
    assert COPERNICUS_GLO30_DERIVED_CREDIT in summary
    assert COPERNICUS_GLO30_NO_LIABILITY in summary

    project.terrain_source = "user-supplied"
    assert COPERNICUS_GLO30_DERIVED_CREDIT not in build_markdown_summary(project, result)


def test_map_picker_attribution_contains_copyright_link() -> None:
    html = build_picker_html(
        title="Escolher transmissor",
        initial_latitude=-23.0,
        initial_longitude=-47.0,
        local_assets=False,
    )
    assert OSM_COPYRIGHT_URL in html
    assert "© OpenStreetMap contributors" in html


def test_pdf_notice_contains_exact_copernicus_credit() -> None:
    from radiolink.pdf_reports import _copernicus_pdf_notice, _reportlab, _styles

    report = _reportlab()
    items = _copernicus_pdf_notice(report, _styles(report))
    paragraphs = [item for item in items if hasattr(item, "text")]
    all_text = " ".join(item.text for item in paragraphs)
    assert COPERNICUS_GLO30_DERIVED_CREDIT in all_text
    assert COPERNICUS_GLO30_NO_LIABILITY in all_text


def test_generated_link_pdf_exposes_copernicus_attribution(
    tmp_path,
    reference_project,
    reference_profile,
) -> None:
    from pypdf import PdfReader

    from radiolink.engine import analyze_project
    from radiolink.pdf_reports import write_link_pdf

    project = reference_project.model_copy(deep=True)
    project.models.itm = project.models.p1812 = project.models.p2001 = False
    project.terrain_source = "Copernicus GLO-30"
    result, _ = analyze_project(project, reference_profile)
    output = write_link_pdf(
        project=project,
        result=result,
        paths={},
        output_path=tmp_path / "link.pdf",
    )
    extracted = "\n".join(page.extract_text() for page in PdfReader(output).pages)
    assert "Copernicus WorldDEM-30" in extracted
    assert "Airbus Defence and Space" in extracted
    assert "The organisations in charge" in extracted
