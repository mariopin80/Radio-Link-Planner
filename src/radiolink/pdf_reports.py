from __future__ import annotations

from .i18n import tr, choice_label

from pathlib import Path
from typing import Any

from .analysis import (
    AGREEMENT_CRITERIA, VIABILITY_CRITERIA, describe_agreement, describe_assessment_basis,
    model_diagnostic_lines, recommendation_lines,
)
from .monte_carlo import describe_simulated_success, percentage_text
from .antenna import ANTENNA_APPROXIMATION_NOTE, antenna_report_rows
from .coverage import CoverageRequest
from .domain import Project
from .height_optimization import height_comparison_table, height_summary_lines
from .legal_notices import (
    COPERNICUS_GLO30_DERIVED_CREDIT,
    COPERNICUS_GLO30_NO_LIABILITY,
    COPERNICUS_LICENSE_URL,
    OSM_COPYRIGHT_URL,
    uses_copernicus_glo30,
)
from .report import describe_fresnel_clearance, describe_geometry_clearance
from .propagation.p1812 import P1812_TIME_HELP
from .version import APP_NAME

_RED = "#c62835"
_DARK = "#20252b"
_GRAY = "#5e6872"
_LIGHT = "#eef0f2"


def write_link_pdf(
    *,
    project: Project,
    result: dict[str, Any],
    paths: dict[str, Path],
    output_path: str | Path,
) -> Path:
    """Create a portable, printable point-to-point analysis report."""
    destination = Path(output_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    report = _reportlab()
    styles = _styles(report)
    story: list[Any] = [
        report["Paragraph"]("RADIO LINK PLANNER", styles["eyebrow"]),
        report["Paragraph"](_escape(project.name), styles["title"]),
        report["Paragraph"](
            (
                tr('Relatório de enlace ponto a ponto • {x0:.3f} MHz • {x1}', x0=project.frequency_mhz, x1=_escape(project.primary_mode.upper()))
            ),
            styles["subtitle"],
        ),
        report["Spacer"](1, 10),
        _notice(
            report,
            styles,
            (
                tr('Resultado de planejamento baseado nos parâmetros informados e nos modelos selecionados. Vegetação, edificações e perdas de instalação só aparecem quando explicitamente representadas.')
            ),
        ),
        report["Spacer"](1, 14),
        report["Paragraph"](tr('Configuração'), styles["heading"]),
        _table(
            report,
            [
                [tr('Parâmetro'), tr('Terminal A'), tr('Terminal B')],
                [
                    tr('Local'),
                    _escape(project.terminal_a.name),
                    _escape(project.terminal_b.name),
                ],
                [
                    tr('Coordenadas'),
                    (
                        f"{project.terminal_a.latitude_deg:.6f}, "
                        f"{project.terminal_a.longitude_deg:.6f}"
                    ),
                    (
                        f"{project.terminal_b.latitude_deg:.6f}, "
                        f"{project.terminal_b.longitude_deg:.6f}"
                    ),
                ],
                [
                    tr('Altura da antena'),
                    f"{project.terminal_a.antenna_height_m:g} m",
                    f"{project.terminal_b.antenna_height_m:g} m",
                ],
                [
                    tr('Ganho / perda de linha'),
                    (
                        f"{project.terminal_a.antenna_gain_dbi:g} dBi / "
                        f"{project.terminal_a.line_loss_db:g} dB"
                    ),
                    (
                        f"{project.terminal_b.antenna_gain_dbi:g} dBi / "
                        f"{project.terminal_b.line_loss_db:g} dB"
                    ),
                ],
                [
                    tr('Potência TX'),
                    f"{project.terminal_a.tx_power_w:g} W",
                    f"{project.terminal_b.tx_power_w:g} W",
                ],
                [tr("Polarização"), choice_label(project.polarization.value), choice_label(project.polarization.value)],
            ],
            widths=(105, 190, 190),
        ),
        report["Spacer"](1, 14),
        report["Paragraph"](tr('Geometria do percurso'), styles["heading"]),
    ]
    geometry = result["geometry"]
    story.extend(
        [
            _table(
                report,
                [
                    [tr('Distância'), f"{geometry['profile_distance_km']:.3f} km"],
                    [tr('Condição limitante'), describe_geometry_clearance(geometry)],
                    [
                        tr('Fresnel livre (%)'),
                        describe_fresnel_clearance(geometry),
                    ],
                    [
                        tr('Fator k exibido no perfil'),
                        f"{project.environment.effective_earth_k:.6g}",
                    ],
                ],
                widths=(180, 305),
                header_rows=0,
            ),
            report["Spacer"](1, 14),
            report["Paragraph"](tr('Resultados por direção'), styles["heading"]),
        ]
    )
    optimization = result.get("height_optimization")
    for direction_id, direction in result["directions"].items():
        story.append(
            report["Paragraph"](
                (
                    f"{_escape(direction['transmitter'])} → "
                    f"{_escape(direction['receiver'])}"
                ),
                styles["subheading"],
            )
        )
        assessment = direction.get("assessment", {})
        story.extend([
            report["Paragraph"](_escape(tr("Viabilidade: {classification}", classification=choice_label(assessment["classification"]))), styles["body"]),
            report["Paragraph"](_escape(describe_agreement(assessment)), styles["body"]),
        ])
        if basis := describe_assessment_basis(assessment):
            story.append(report["Paragraph"](_escape(basis), styles["body"]))
        comparison_rows = [[tr("Modelo"), tr("Perda"), tr("Tempo (%)")]]
        for model in direction.get("comparison_models", ()):
            comparison_rows.append([
                model["model_id"].upper(),
                _number(model["loss_db"], " dB") if model["status"] == "ok" else choice_label(model["status"]),
                f"{direction['comparison_percent']:g}",
            ])
        if len(comparison_rows) > 1:
            story.append(_table(report, comparison_rows, widths=(120, 150, 105)))
            story.append(report["Spacer"](1, 7))
        budgets = {
            item["model_id"]: item
            for item in direction.get("link_budgets", ())
        }
        simulations = {
            item["model_id"]: item
            for item in direction.get("monte_carlo", ())
        }
        rows = [[tr('Modelo'), tr('Tempo (%)'), tr('Perda'), tr('Potência RX'), tr('Margem'), "Monte Carlo"]]
        for model in direction.get("design_models", ()):
            model_id = model.get("model_id", "—")
            if model.get("status") != "ok":
                rows.append(
                    [
                        str(model_id).upper(),
                        "—",
                        choice_label(str(model.get("status", "unavailable"))),
                        "—",
                        "—",
                        "—",
                    ]
                )
                continue
            budget = budgets.get(model_id, {})
            probability = _primary_probability(
                simulations.get(model_id),
                project.primary_mode,
            )
            rows.append(
                [
                    str(model_id).upper(),
                    percentage_text(model["percentile"]) + "%",
                    _number(model.get("loss_db"), " dB"),
                    _number(budget.get("received_power_dbm"), " dBm"),
                    _signed_number(budget.get("fade_margin_db"), " dB"),
                    (
                        f"{percentage_text(probability)}%"
                        if probability is not None
                        else "—"
                    ),
                ]
            )
        story.extend(
            [
                _table(
                    report,
                    rows,
                    widths=(62, 74, 80, 94, 78, 97),
                ),
                report["Spacer"](1, 12),
            ]
        )
        for model_id, simulation in simulations.items():
            if description := describe_simulated_success(
                simulation, project.primary_mode, project.target_availability_percent,
            ):
                story.append(report["Paragraph"](_escape(f"{model_id.upper()} · {description}"), styles["small"]))
        for diagnostic in model_diagnostic_lines(direction):
            story.append(report["Paragraph"](_escape(diagnostic), styles["small"]))
        for label, details in (
            (tr("Recomendações pertinentes"), recommendation_lines(assessment)),
            (tr("Incertezas declaradas"), [tr(item) for item in assessment["uncertainties"]]),
        ):
            story.append(report["Paragraph"](label, styles["subheading"]))
            story.extend(report["Paragraph"](_escape(line), styles["body"]) for line in details)
        if optimization:
            story.extend([
                report["Paragraph"](tr("Propagação antes e depois da elevação"), styles["subheading"]),
                _table(report, height_comparison_table(optimization["model_comparison"][direction_id]),
                       widths=(75, 65, 170, 175)),
            ])

    if optimization:
        story.append(report["Paragraph"](tr("Otimização da altura das antenas"), styles["heading"]))
        story.extend(report["Paragraph"](_escape(line), styles["body"]) for line in height_summary_lines(optimization))

    for title, key in (
        (tr('Mapa geográfico do enlace'), "geographic_map"),
        (tr('Perfil topográfico e zona de Fresnel'), "profile_plot"),
        (tr('Análise de Monte Carlo'), "monte_carlo_plot"),
    ):
        image_path = paths.get(key)
        if image_path and image_path.is_file():
            story.extend(
                [
                    report["PageBreak"](),
                    report["Paragraph"](title, styles["heading"]),
                    report["Spacer"](1, 8),
                    _fit_image(report, image_path, 500, 650),
                ]
            )
            if key == "geographic_map":
                story.extend(_geographic_map_credit(report, styles))
    story.extend(
        [
            report["Spacer"](1, 14),
            report["Paragraph"](tr('Rastreabilidade'), styles["heading"]),
            report["Paragraph"](_escape(tr(VIABILITY_CRITERIA)), styles["small"]),
            report["Paragraph"](_escape(tr(AGREEMENT_CRITERIA)), styles["small"]),
            report["Paragraph"](
                _escape(tr("Meta de disponibilidade do enlace: {target:g}%.", target=project.target_availability_percent)),
                styles["small"],
            ),
            report["Paragraph"](
                (
                    tr("Identificador do resultado: <font name='Courier'>{x0}</font>", x0=_escape(str(result.get('result_sha256', '—'))))
                ),
                styles["small"],
            ),
            report["Paragraph"](
                (
                    tr('A interpretação de viabilidade deve considerar uma margem de engenharia adequada ao serviço, à disponibilidade pretendida e às perdas práticas não modeladas.')
                ),
                styles["small"],
            ),
        ]
    )
    if project.models.p1812:
        story.append(report["Paragraph"](_escape(tr(P1812_TIME_HELP)), styles["small"]))
        if project.target_availability_percent > 50.0:
            story.append(report["Paragraph"](_escape(tr(
                "A tabela usa {percent:g}% para P.1812. A viabilidade na meta de {target:g}% usa ITM e P.2001 disponíveis.",
                percent=project.models.comparison_percent, target=project.target_availability_percent,
            )), styles["small"]))
    if uses_copernicus_glo30(project.terrain_source):
        story.extend(_copernicus_pdf_notice(report, styles))
    _build_document(report, destination, story)
    return destination


def write_coverage_pdf(
    *,
    request: CoverageRequest,
    statistics: dict[str, Any],
    paths: dict[str, Path],
    output_path: str | Path,
) -> Path:
    """Create a portable, printable coverage-analysis report."""
    destination = Path(output_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    report = _reportlab()
    styles = _styles(report)
    story: list[Any] = [
        report["Paragraph"]("RADIO LINK PLANNER", styles["eyebrow"]),
        report["Paragraph"](_escape(request.name), styles["title"]),
        report["Paragraph"](
            (
                tr('Relatório de cobertura • {x0:.3f} MHz • P.1812 a {x1:g}% do tempo', x0=request.frequency_mhz, x1=request.time_percentage)
            ),
            styles["subtitle"],
        ),
        report["Spacer"](1, 10),
        _notice(
            report,
            styles,
            (
                tr('As porcentagens representam células da grade que superam cada limiar no cenário modelado. Não são garantia de cobertura em campo e não incluem automaticamente árvores ou edificações.')
            ),
        ),
        report["Spacer"](1, 14),
        report["Paragraph"](tr('Configuração'), styles["heading"]),
        _table(
            report,
            [
                [tr('Parâmetro'), tr('Valor'), tr('Parâmetro'), tr('Valor')],
                [
                    tr("Centro"),
                    f"{request.latitude_deg:.6f}, {request.longitude_deg:.6f}",
                    tr('Raio'),
                    f"{request.radius_km} km",
                ],
                [
                    tr('Célula da grade'),
                    f"{request.resolution_m} m",
                    tr('Polarização'),
                    choice_label(request.polarization),
                ],
                [
                    tr('Potência / ganho TX'),
                    (
                        f"{request.transmitter_power_w:g} W / "
                        f"{request.transmitter_gain_dbi:g} dBi"
                    ),
                    tr('Altura TX'),
                    f"{request.transmitter_height_m:g} m",
                ],
                [
                    tr('Sensibilidade / ganho RX'),
                    (
                        f"{request.receiver_threshold_dbm:g} dBm / "
                        f"{request.receiver_gain_dbi:g} dBi"
                    ),
                    tr('Altura RX'),
                    f"{request.receiver_height_m:g} m",
                ],
                [
                    tr("Perda no cabo transmissor"), f"{request.transmitter_line_loss_db:g} dB",
                    tr("Perda no cabo receptor"), f"{request.receiver_line_loss_db:g} dB",
                ],
            ],
            widths=(100, 155, 100, 130),
        ),
        report["Spacer"](1, 6),
        _table(report, antenna_report_rows(request.transmitter_gain_dbi, request.transmitter_pattern),
               widths=(245, 240), header_rows=0),
        report["Paragraph"](_escape(tr(P1812_TIME_HELP)), styles["small"]),
        report["Spacer"](1, 14),
        report["Paragraph"](tr('Síntese da cobertura'), styles["heading"]),
        _table(
            report,
            [
                [tr("Indicador"), tr('Resultado')],
                [tr('Margem mínima'), _signed_number(statistics.get("minimum_margin_db"), " dB")],
                [tr('Margem máxima'), _signed_number(statistics.get("maximum_margin_db"), " dB")],
                [tr('Área com margem ≥ 0 dB'), f"{statistics['covered_percent']:.1f}%"],
                [tr('Área com margem ≥ +3 dB'), f"{statistics['margin_3_db_percent']:.1f}%"],
                [tr('Área com margem ≥ +6 dB'), f"{statistics['margin_6_db_percent']:.1f}%"],
                [tr('Área com margem ≥ +12 dB'), f"{statistics['margin_12_db_percent']:.1f}%"],
                [
                    tr('Células calculadas'),
                    f"{statistics.get('calculated_cells', 0):,}",
                ],
            ],
            widths=(245, 240),
        ),
    ]
    if request.transmitter_pattern:
        story.append(report["Paragraph"](_escape(tr(ANTENNA_APPROXIMATION_NOTE)), styles["small"]))
    display_resolution = statistics.get("display_resolution_m", request.resolution_m)
    if display_resolution != request.resolution_m:
        story.append(report["Paragraph"](_escape(tr(
            "Imagem do mapa: {display} m. Contornos e consulta de células: grade original de {native} m.",
            display=display_resolution, native=request.resolution_m,
        )), styles["small"]))
    geographic_map = paths.get("geographic_map")
    heatmap = paths.get("heatmap")
    selected_map = (
        geographic_map if geographic_map and geographic_map.is_file() else heatmap
    )
    if selected_map and selected_map.is_file():
        story.extend(
            [
                report["PageBreak"](),
                report["Paragraph"](
                    tr('Mapa de cobertura com referências geográficas')
                    if selected_map == geographic_map
                    else tr('Mapa técnico de margens'),
                    styles["heading"],
                ),
                report["Spacer"](1, 8),
                _fit_image(report, selected_map, 500, 650),
            ]
        )
        if selected_map == geographic_map:
            story.extend(_geographic_map_credit(report, styles))
    story.extend(
        [
            report["Spacer"](1, 14),
            report["Paragraph"](tr('Limitações de interpretação'), styles["heading"]),
            report["Paragraph"](
                (
                    tr('A P.1812 considera o perfil topográfico e os mecanismos de propagação previstos na recomendação. Obstáculos menores que a resolução do terreno, ruído local, interferência, perdas por polarização e variações de instalação devem ser tratados como margens adicionais de engenharia.')
                ),
                styles["small"],
            ),
        ]
    )
    story.extend(_copernicus_pdf_notice(report, styles))
    _build_document(report, destination, story)
    return destination


def _geographic_map_credit(report: dict[str, Any], styles: dict[str, Any]) -> list[Any]:
    url = _escape(OSM_COPYRIGHT_URL)
    return [
        report["Spacer"](1, 8),
        report["Paragraph"](
            tr('Captura do mapa interativo no enquadramento e na escala escolhidos pelo usuário.'),
            styles["small"],
        ),
        report["Paragraph"](f'© OpenStreetMap contributors — <a href="{url}">{url}</a>', styles["small"]),
    ]


def _copernicus_pdf_notice(report: dict[str, Any], styles: dict[str, Any]) -> list[Any]:
    return [
        report["Spacer"](1, 10),
        report["Paragraph"](tr('Fonte e licença do relevo'), styles["heading"]),
        report["Paragraph"](_escape(COPERNICUS_GLO30_DERIVED_CREDIT), styles["small"]),
        report["Paragraph"](_escape(COPERNICUS_GLO30_NO_LIABILITY), styles["small"]),
        report["Paragraph"](_escape(COPERNICUS_LICENSE_URL), styles["small"]),
    ]


def _reportlab() -> dict[str, Any]:
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            Image,
            PageBreak,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError as exc:
        raise RuntimeError(
            tr('A dependência de relatórios PDF (ReportLab) não está instalada.')
        ) from exc
    return locals()


def _styles(report: dict[str, Any]) -> dict[str, Any]:
    base = report["getSampleStyleSheet"]()
    paragraph_style = report["ParagraphStyle"]
    return {
        "eyebrow": paragraph_style(
            "Eyebrow",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            textColor=report["colors"].HexColor(_RED),
            spaceAfter=5,
            tracking=1.5,
        ),
        "title": paragraph_style(
            "Title",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=26,
            textColor=report["colors"].HexColor(_DARK),
            alignment=report["TA_LEFT"],
            spaceAfter=4,
        ),
        "subtitle": paragraph_style(
            "Subtitle",
            parent=base["Normal"],
            fontSize=10,
            leading=14,
            textColor=report["colors"].HexColor(_GRAY),
        ),
        "heading": paragraph_style(
            "Heading",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=13,
            textColor=report["colors"].HexColor(_DARK),
            spaceBefore=4,
            spaceAfter=7,
        ),
        "subheading": paragraph_style(
            "Subheading",
            parent=base["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=10,
            textColor=report["colors"].HexColor(_RED),
            spaceBefore=4,
            spaceAfter=4,
        ),
        "body": paragraph_style(
            "Body",
            parent=base["BodyText"],
            fontSize=8.5,
            leading=12,
            textColor=report["colors"].HexColor(_DARK),
            spaceAfter=6,
        ),
        "small": paragraph_style(
            "Small",
            parent=base["BodyText"],
            fontSize=7.5,
            leading=10.5,
            textColor=report["colors"].HexColor(_GRAY),
            spaceAfter=5,
        ),
        "notice": paragraph_style(
            "Notice",
            parent=base["BodyText"],
            fontSize=8,
            leading=11,
            textColor=report["colors"].HexColor(_DARK),
            borderColor=report["colors"].HexColor("#d6dade"),
            borderWidth=0.7,
            borderPadding=8,
            backColor=report["colors"].HexColor("#f7f8f9"),
        ),
    }


def _notice(
    report: dict[str, Any],
    styles: dict[str, Any],
    text: str,
) -> Any:
    return report["Paragraph"](text, styles["notice"])


def _table(
    report: dict[str, Any],
    rows: list[list[Any]],
    *,
    widths: tuple[float, ...],
    header_rows: int = 1,
) -> Any:
    # Paragraphs wrap translated headings and long terminal names within cells.
    # Plain strings can overlap the next column, especially in German.
    rows = [
        [
            report["Paragraph"](
                str(value),
                report["ParagraphStyle"](
                    "TableHeader" if row_index < header_rows else "TableCell",
                    fontName="Helvetica-Bold" if row_index < header_rows else "Helvetica",
                    fontSize=7.5,
                    leading=10,
                    textColor=report["colors"].white if row_index < header_rows else report["colors"].HexColor(_DARK),
                ),
            )
            for value in row
        ]
        for row_index, row in enumerate(rows)
    ]
    table = report["Table"](
        rows,
        colWidths=list(widths),
        repeatRows=header_rows,
        hAlign="LEFT",
    )
    commands: list[tuple[Any, ...]] = [
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("LEADING", (0, 0), (-1, -1), 10),
        ("TEXTCOLOR", (0, 0), (-1, -1), report["colors"].HexColor(_DARK)),
        ("GRID", (0, 0), (-1, -1), 0.35, report["colors"].HexColor("#ccd1d5")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, header_rows), (-1, -1), [
            report["colors"].white,
            report["colors"].HexColor("#f7f8f9"),
        ]),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    if header_rows:
        commands.extend(
            [
                ("BACKGROUND", (0, 0), (-1, header_rows - 1), report["colors"].HexColor(_DARK)),
                ("TEXTCOLOR", (0, 0), (-1, header_rows - 1), report["colors"].white),
                ("FONTNAME", (0, 0), (-1, header_rows - 1), "Helvetica-Bold"),
            ]
        )
    table.setStyle(report["TableStyle"](commands))
    return table


def _fit_image(
    report: dict[str, Any],
    path: Path,
    max_width: float,
    max_height: float,
) -> Any:
    image = report["Image"](str(path))
    scale = min(max_width / image.imageWidth, max_height / image.imageHeight)
    image.drawWidth = image.imageWidth * scale
    image.drawHeight = image.imageHeight * scale
    image.hAlign = "CENTER"
    return image


def _build_document(
    report: dict[str, Any],
    destination: Path,
    story: list[Any],
) -> None:
    document = report["SimpleDocTemplate"](
        str(destination),
        pagesize=report["A4"],
        rightMargin=16 * report["mm"],
        leftMargin=16 * report["mm"],
        topMargin=16 * report["mm"],
        bottomMargin=17 * report["mm"],
        title=destination.stem,
        author=APP_NAME,
    )

    def footer(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        width, _ = report["A4"]
        canvas.setStrokeColor(report["colors"].HexColor("#d6dade"))
        canvas.setLineWidth(0.5)
        canvas.line(
            16 * report["mm"],
            12 * report["mm"],
            width - 16 * report["mm"],
            12 * report["mm"],
        )
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(report["colors"].HexColor(_GRAY))
        canvas.drawString(
            16 * report["mm"],
            8 * report["mm"],
            tr('{app_name} • processamento local', app_name=APP_NAME),
        )
        canvas.drawRightString(
            width - 16 * report["mm"],
            8 * report["mm"],
            tr('Página {x0}', x0=doc.page),
        )
        canvas.restoreState()

    document.build(story, onFirstPage=footer, onLaterPages=footer)


def _primary_probability(
    simulation: dict[str, Any] | None,
    primary_mode: str,
) -> float | None:
    if not simulation:
        return None
    for item in simulation.get("mode_results", ()):
        if str(item.get("mode", "")).upper() == primary_mode.upper():
            value = item.get("success_probability_percent")
            return float(value) if value is not None else None
    return None


def _number(value: Any, suffix: str = "") -> str:
    if value is None:
        return "—"
    return f"{float(value):.2f}{suffix}"


def _signed_number(value: Any, suffix: str = "") -> str:
    if value is None:
        return "—"
    return f"{float(value):+.2f}{suffix}"


def _escape(value: str) -> str:
    import html

    return html.escape(value)

