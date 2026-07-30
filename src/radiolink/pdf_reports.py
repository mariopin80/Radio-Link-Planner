from __future__ import annotations

from pathlib import Path
from typing import Any

from .coverage import CoverageRequest
from .domain import Project
from .report import describe_geometry_clearance

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
                f"Relatório de enlace ponto a ponto • "
                f"{project.frequency_mhz:.3f} MHz • "
                f"{_escape(project.primary_mode.upper())}"
            ),
            styles["subtitle"],
        ),
        report["Spacer"](1, 10),
        _notice(
            report,
            styles,
            (
                "Resultado de planejamento baseado nos parâmetros informados e "
                "nos modelos selecionados. Vegetação, edificações e perdas de "
                "instalação só aparecem quando explicitamente representadas."
            ),
        ),
        report["Spacer"](1, 14),
        report["Paragraph"]("Configuração", styles["heading"]),
        _table(
            report,
            [
                ["Parâmetro", "Terminal A", "Terminal B"],
                [
                    "Local",
                    _escape(project.terminal_a.name),
                    _escape(project.terminal_b.name),
                ],
                [
                    "Coordenadas",
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
                    "Altura da antena",
                    f"{project.terminal_a.antenna_height_m:g} m",
                    f"{project.terminal_b.antenna_height_m:g} m",
                ],
                [
                    "Ganho / perda de linha",
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
                    "Potência TX",
                    f"{project.terminal_a.tx_power_w:g} W",
                    f"{project.terminal_b.tx_power_w:g} W",
                ],
            ],
            widths=(105, 190, 190),
        ),
        report["Spacer"](1, 14),
        report["Paragraph"]("Geometria do percurso", styles["heading"]),
    ]
    geometry = result["geometry"]
    story.extend(
        [
            _table(
                report,
                [
                    ["Distância", f"{geometry['profile_distance_km']:.3f} km"],
                    ["Condição limitante", describe_geometry_clearance(geometry)],
                    [
                        "Fresnel de 60% obstruída",
                        f"{geometry['fresnel_60_obstructed_percent']:.1f}%",
                    ],
                    [
                        "Fator k exibido no perfil",
                        f"{project.environment.effective_earth_k:.3f}",
                    ],
                ],
                widths=(180, 305),
                header_rows=0,
            ),
            report["Spacer"](1, 14),
            report["Paragraph"]("Resultados por direção", styles["heading"]),
        ]
    )
    for direction in result["directions"].values():
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
        story.append(
            report["Paragraph"](
                (
                    f"Classificação: <b>{_escape(str(assessment.get('classification', '—')).upper())}</b> "
                    f"• confiança do diagnóstico: "
                    f"{_escape(str(assessment.get('confidence', '—')))}"
                ),
                styles["body"],
            )
        )
        budgets = {
            item["model_id"]: item
            for item in direction.get("link_budgets", ())
        }
        simulations = {
            item["model_id"]: item
            for item in direction.get("monte_carlo", ())
        }
        rows = [["Modelo", "Perda", "Potência RX", "Margem", "Monte Carlo"]]
        for model in direction.get("design_models", ()):
            model_id = model.get("model_id", "—")
            if model.get("status") != "ok":
                rows.append(
                    [
                        str(model_id).upper(),
                        str(model.get("status", "indisponível")),
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
                    _number(model.get("loss_db"), " dB"),
                    _number(budget.get("received_power_dbm"), " dBm"),
                    _signed_number(budget.get("fade_margin_db"), " dB"),
                    (
                        f"{probability:.1f}%"
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
                    widths=(70, 92, 105, 92, 105),
                ),
                report["Spacer"](1, 12),
            ]
        )

    for title, key in (
        ("Perfil topográfico e zona de Fresnel", "profile_plot"),
        ("Análise de Monte Carlo", "monte_carlo_plot"),
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
    story.extend(
        [
            report["Spacer"](1, 14),
            report["Paragraph"]("Rastreabilidade", styles["heading"]),
            report["Paragraph"](
                (
                    "Identificador do resultado: "
                    f"<font name='Courier'>{_escape(str(result.get('result_sha256', '—')))}</font>"
                ),
                styles["small"],
            ),
            report["Paragraph"](
                (
                    "A interpretação de viabilidade deve considerar uma margem de "
                    "engenharia adequada ao serviço, à disponibilidade pretendida "
                    "e às perdas práticas não modeladas."
                ),
                styles["small"],
            ),
        ]
    )
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
                f"Relatório de cobertura • {request.frequency_mhz:.3f} MHz • "
                f"P.1812 a {request.time_percentage:g}% do tempo"
            ),
            styles["subtitle"],
        ),
        report["Spacer"](1, 10),
        _notice(
            report,
            styles,
            (
                "As porcentagens representam células da grade que superam cada "
                "limiar no cenário modelado. Não são garantia de cobertura em "
                "campo e não incluem automaticamente árvores ou edificações."
            ),
        ),
        report["Spacer"](1, 14),
        report["Paragraph"]("Configuração", styles["heading"]),
        _table(
            report,
            [
                ["Parâmetro", "Valor", "Parâmetro", "Valor"],
                [
                    "Centro",
                    f"{request.latitude_deg:.6f}, {request.longitude_deg:.6f}",
                    "Raio",
                    f"{request.radius_km} km",
                ],
                [
                    "Célula da grade",
                    f"{request.resolution_m} m",
                    "Polarização",
                    request.polarization.capitalize(),
                ],
                [
                    "Potência / ganho TX",
                    (
                        f"{request.transmitter_power_w:g} W / "
                        f"{request.transmitter_gain_dbi:g} dBi"
                    ),
                    "Altura TX",
                    f"{request.transmitter_height_m:g} m",
                ],
                [
                    "Sensibilidade / ganho RX",
                    (
                        f"{request.receiver_threshold_dbm:g} dBm / "
                        f"{request.receiver_gain_dbi:g} dBi"
                    ),
                    "Altura RX",
                    f"{request.receiver_height_m:g} m",
                ],
            ],
            widths=(100, 155, 100, 130),
        ),
        report["Spacer"](1, 14),
        report["Paragraph"]("Síntese da cobertura", styles["heading"]),
        _table(
            report,
            [
                ["Indicador", "Resultado"],
                ["Margem mínima", _signed_number(statistics.get("minimum_margin_db"), " dB")],
                ["Margem máxima", _signed_number(statistics.get("maximum_margin_db"), " dB")],
                ["Área com margem ≥ 0 dB", f"{statistics['covered_percent']:.1f}%"],
                ["Área com margem ≥ +3 dB", f"{statistics['margin_3_db_percent']:.1f}%"],
                ["Área com margem ≥ +6 dB", f"{statistics['margin_6_db_percent']:.1f}%"],
                ["Área com margem ≥ +12 dB", f"{statistics['margin_12_db_percent']:.1f}%"],
                [
                    "Células calculadas",
                    f"{statistics.get('calculated_cells', 0):,}",
                ],
            ],
            widths=(245, 240),
        ),
    ]
    heatmap = paths.get("heatmap")
    if heatmap and heatmap.is_file():
        story.extend(
            [
                report["PageBreak"](),
                report["Paragraph"]("Mapa técnico de margens", styles["heading"]),
                report["Spacer"](1, 8),
                _fit_image(report, heatmap, 500, 650),
            ]
        )
    story.extend(
        [
            report["Spacer"](1, 14),
            report["Paragraph"]("Limitações de interpretação", styles["heading"]),
            report["Paragraph"](
                (
                    "A P.1812 considera o perfil topográfico e os mecanismos de "
                    "propagação previstos na recomendação. Obstáculos menores que "
                    "a resolução do terreno, ruído local, interferência, perdas por "
                    "polarização e variações de instalação devem ser tratados como "
                    "margens adicionais de engenharia."
                ),
                styles["small"],
            ),
        ]
    )
    _build_document(report, destination, story)
    return destination


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
            "A dependência de relatórios PDF (ReportLab) não está instalada."
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
        author="Radio Link Planner",
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
            "Radio Link Planner • processamento local",
        )
        canvas.drawRightString(
            width - 16 * report["mm"],
            8 * report["mm"],
            f"Página {doc.page}",
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
