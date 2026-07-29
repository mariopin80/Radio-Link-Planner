from __future__ import annotations

import html
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from .domain import Project
from .geometry import GeometryArrays
from .terrain import TerrainProfile


_MATPLOTLIB_CACHE = Path(tempfile.gettempdir()) / "radio-link-planner-matplotlib"
_MATPLOTLIB_CACHE.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_MATPLOTLIB_CACHE))
os.environ.setdefault("MPLBACKEND", "Agg")


def write_outputs(
    output_dir: str | Path,
    project: Project,
    profile: TerrainProfile,
    result: dict[str, Any],
    geometry_arrays: GeometryArrays,
    make_plots: bool = True,
) -> dict[str, Path]:
    destination = Path(output_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    result_path = destination / "result.json"
    summary_path = destination / "summary.md"
    report_path = destination / "report.html"
    result_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    summary = build_markdown_summary(project, result)
    summary_path.write_text(summary, encoding="utf-8")
    paths = {
        "result_json": result_path,
        "summary_markdown": summary_path,
        "report_html": report_path,
    }
    if make_plots:
        profile_path = destination / "profile.png"
        monte_carlo_path = destination / "monte_carlo.png"
        render_profile_plot(
            project, profile, result, geometry_arrays, profile_path
        )
        render_monte_carlo_plot(project, result, monte_carlo_path)
        paths["profile_plot"] = profile_path
        paths["monte_carlo_plot"] = monte_carlo_path
    report_path.write_text(
        build_html_report(project, result, make_plots=make_plots),
        encoding="utf-8",
    )
    return paths


def render_profile_plot(
    project: Project,
    profile: TerrainProfile,
    result: dict[str, Any],
    arrays: GeometryArrays,
    output_path: str | Path,
) -> None:
    import matplotlib.pyplot as plt

    distance_km = arrays.distance_m / 1000.0
    ground = profile.elevation_m + profile.clutter_height_m
    fig, axis = plt.subplots(figsize=(14, 6.8), dpi=150)
    axis.fill_between(
        distance_km,
        0.0,
        ground,
        color="#4e5158",
        alpha=0.95,
        label="Terreno / superfície",
    )
    axis.plot(
        distance_km,
        arrays.apparent_terrain_m_asl,
        color="#d98b39",
        linewidth=1.1,
        label=f"Terreno aparente (k={project.environment.effective_earth_k:.3f})",
    )
    axis.plot(
        distance_km,
        arrays.direct_ray_m_asl,
        color="#e7333f",
        linewidth=1.6,
        label="Raio direto",
    )
    axis.plot(
        distance_km,
        arrays.direct_ray_m_asl + 0.6 * arrays.fresnel_radius_m,
        color="#7db6d8",
        linewidth=0.9,
        label="60% da 1ª Fresnel",
    )
    axis.plot(
        distance_km,
        arrays.direct_ray_m_asl - 0.6 * arrays.fresnel_radius_m,
        color="#7db6d8",
        linewidth=0.9,
    )
    geometry = result["geometry"]
    axis.axvline(
        geometry["worst_obstruction_distance_km"],
        color="#f6c85f",
        linestyle="--",
        linewidth=1.0,
    )
    axis.annotate(
        (
            f"Pior bloqueio: {geometry['worst_obstruction_m']:.1f} m\n"
            f"a {geometry['worst_obstruction_distance_km']:.1f} km"
        ),
        xy=(
            geometry["worst_obstruction_distance_km"],
            np.interp(
                geometry["worst_obstruction_distance_km"],
                distance_km,
                arrays.apparent_terrain_m_asl,
            ),
        ),
        xytext=(18, -54),
        textcoords="offset points",
        va="top",
        fontsize=9,
        color="#111111",
        bbox={
            "boxstyle": "round,pad=0.35",
            "facecolor": "#fff7df",
            "edgecolor": "#f6c85f",
        },
    )
    axis.set_title(
        f"{project.name} — {project.frequency_mhz:.3f} MHz",
        loc="left",
        fontsize=15,
        fontweight="bold",
    )
    axis.set_xlabel("Distância desde o terminal A (km)")
    axis.set_ylabel("Altitude / altura aparente (m)")
    axis.grid(True, alpha=0.18)
    axis.legend(loc="upper right", ncol=2, fontsize=8)
    axis.set_xlim(0.0, profile.total_distance_km)
    lower = min(ground.min(), arrays.direct_ray_m_asl.min()) - 80.0
    upper = max(
        arrays.apparent_terrain_m_asl.max(),
        (arrays.direct_ray_m_asl + 0.6 * arrays.fresnel_radius_m).max(),
    ) + 80.0
    axis.set_ylim(lower, upper)
    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)


def render_monte_carlo_plot(
    project: Project, result: dict[str, Any], output_path: str | Path
) -> None:
    import matplotlib.pyplot as plt

    direction = result["directions"]["a_to_b"]
    simulations = direction["monte_carlo"]
    fig, (axis_hist, axis_bar) = plt.subplots(
        1, 2, figsize=(14, 5.5), dpi=150, gridspec_kw={"width_ratios": [1.55, 1]}
    )
    colors = {"itm": "#4464ad", "p1812": "#e07a2d", "p2001": "#7f3c8d"}
    for simulation in simulations:
        edges = np.asarray(simulation["histogram_edges_dbm"], dtype=float)
        counts = np.asarray(simulation["histogram_counts"], dtype=float)
        centers = (edges[:-1] + edges[1:]) / 2.0
        area = np.trapezoid(counts, centers)
        density = counts / area if area > 0.0 else counts
        axis_hist.plot(
            centers,
            density,
            linewidth=1.8,
            color=colors.get(simulation["model_id"]),
            label=(
                "P1812 (condicional em p50)"
                if simulation["temporal_sampling"] == "conditional_fixed_quantile"
                else simulation["model_id"].upper()
            ),
        )
    threshold = None
    labels: list[str] = []
    probabilities: list[float] = []
    bar_colors: list[str] = []
    for simulation in simulations:
        primary = next(
            item
            for item in simulation["mode_results"]
            if item["mode"] == project.primary_mode.upper()
        )
        threshold = primary["threshold_dbm"]
        labels.append(
            "P1812\n(p50 cond.)"
            if simulation["temporal_sampling"] == "conditional_fixed_quantile"
            else simulation["model_id"].upper()
        )
        probabilities.append(primary["success_probability_percent"])
        bar_colors.append(colors.get(simulation["model_id"], "#555555"))
    if threshold is not None:
        axis_hist.axvline(
            threshold,
            color="#d62728",
            linestyle="--",
            linewidth=1.2,
            label=f"Limiar {project.primary_mode.upper()}: {threshold:.1f} dBm",
        )
    axis_hist.set_title("Distribuição da potência recebida", loc="left")
    axis_hist.set_xlabel("Potência no receptor (dBm)")
    axis_hist.set_ylabel("Densidade relativa")
    axis_hist.grid(True, alpha=0.18)
    axis_hist.legend(fontsize=8)
    bars = axis_bar.bar(labels, probabilities, color=bar_colors)
    axis_bar.axhline(
        project.target_availability_percent,
        color="#d62728",
        linestyle="--",
        linewidth=1.2,
        label=f"Meta {project.target_availability_percent:.0f}%",
    )
    axis_bar.set_ylim(0.0, 105.0)
    axis_bar.set_ylabel("Probabilidade estimada (%)")
    axis_bar.set_title(
        f"Funcionamento em {project.primary_mode.upper()}", loc="left"
    )
    axis_bar.grid(True, axis="y", alpha=0.18)
    axis_bar.legend(fontsize=8)
    for bar, value, simulation in zip(bars, probabilities, simulations):
        suffix = (
            "*"
            if simulation["temporal_sampling"] == "conditional_fixed_quantile"
            else ""
        )
        axis_bar.text(
            bar.get_x() + bar.get_width() / 2.0,
            value + 2.0,
            f"{value:.1f}%{suffix}",
            ha="center",
            va="bottom",
            fontsize=9,
        )
    has_conditional_result = any(
        item["temporal_sampling"] == "conditional_fixed_quantile"
        for item in simulations
    )
    if has_conditional_result:
        fig.text(
            0.55,
            0.018,
            "* P.1812: probabilidade condicional ao p50; não é disponibilidade anual.",
            fontsize=7.5,
            color="#555555",
            ha="left",
        )
    fig.suptitle(
        f"Monte Carlo — {result['directions']['a_to_b']['transmitter']} → "
        f"{result['directions']['a_to_b']['receiver']}",
        fontsize=14,
        fontweight="bold",
        x=0.04,
        ha="left",
    )
    fig.tight_layout(rect=(0.0, 0.055 if has_conditional_result else 0.0, 1.0, 0.95))
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)


def build_markdown_summary(project: Project, result: dict[str, Any]) -> str:
    geometry = result["geometry"]
    lines = [
        f"# {project.name}",
        "",
        f"Versão do motor: {result['engine_version']}",
        "",
        "## Geometria",
        "",
        f"- Distância: {geometry['profile_distance_km']:.3f} km",
        f"- Pior bloqueio geométrico: {geometry['worst_obstruction_m']:.1f} m "
        f"a {geometry['worst_obstruction_distance_km']:.1f} km",
        f"- Raio máximo da primeira Fresnel: "
        f"{geometry['maximum_fresnel_radius_m']:.1f} m",
        f"- Fresnel de 60% obstruída em "
        f"{geometry['fresnel_60_obstructed_percent']:.1f}% do percurso",
        "",
    ]
    for direction_id, direction in result["directions"].items():
        assessment = direction["assessment"]
        classification_label = {
            "robust": "robusto",
            "viable": "viável",
            "marginal": "marginal",
            "improbable": "improvável",
            "indeterminate": "indeterminado",
        }.get(assessment["classification"], assessment["classification"])
        confidence_label = {
            "high": "alta",
            "medium": "média",
            "low": "baixa",
        }.get(assessment["confidence"], assessment["confidence"])
        lines.extend(
            [
                f"## {direction['transmitter']} → {direction['receiver']}",
                "",
                f"**Parecer: {classification_label}**  ",
                f"Confiança: {confidence_label}",
                "",
                f"### Comparação coerente em {direction['comparison_percent']:.0f}%",
                "",
                "| Modelo | Perda (dB) |",
                "|---|---:|",
            ]
        )
        for model in direction["comparison_models"]:
            if model["status"] == "ok":
                lines.append(
                    f"| {model['model_id'].upper()} | {model['loss_db']:.2f} |"
                )
            else:
                lines.append(
                    f"| {model['model_id'].upper()} | {model['status']} |"
                )
        if assessment["model_spread_db"] is not None:
            lines.extend(
                [
                    "",
                    f"Dispersão entre modelos: "
                    f"**{assessment['model_spread_db']:.2f} dB**.",
                ]
            )
        lines.extend(
            [
                "",
                f"### Ponto de projeto: {direction['target_availability_percent']:.0f}%",
                "",
                "| Modelo | Quantil de projeto | Perda (dB) | Potência (dBm) | Margem (dB) |",
                "|---|---:|---:|---:|---:|",
            ]
        )
        budgets = {
            item["model_id"]: item for item in direction["link_budgets"]
        }
        for model in direction["design_models"]:
            budget = budgets.get(model["model_id"])
            if model["status"] != "ok" or budget is None:
                lines.append(
                    f"| {model['model_id'].upper()} | — | indisponível | — | — |"
                )
                continue
            lines.append(
                f"| {model['model_id'].upper()} | "
                f"{model['percentile']:.1f}% | "
                f"{model['loss_db']:.2f} | "
                f"{budget['received_power_dbm']:.2f} | "
                f"{budget['fade_margin_db']:.2f} |"
            )
        if project.target_availability_percent > 50.0:
            lines.extend(
                [
                    "",
                    "> A P.1812 é limitada a 1–50% do tempo. Seu valor na "
                    "tabela é mediano e não representa a meta de "
                    f"{project.target_availability_percent:.0f}%.",
                ]
            )
        lines.extend(["", "### Recomendações", ""])
        for item in assessment["recommendations"]:
            lines.append(
                f"- {item['action']}: aproximadamente "
                f"+{item['estimated_margin_improvement_db']:.1f} dB "
                f"({item['basis']})."
            )
        lines.extend(["", "### Incertezas declaradas", ""])
        for item in assessment["uncertainties"]:
            lines.append(f"- {item}.")
        lines.append("")
    lines.extend(
        [
            "## Rastreabilidade",
            "",
            f"- SHA-256 do perfil: `{result['traceability']['terrain_sha256']}`",
            f"- Pontos do perfil: {result['traceability']['terrain_point_count']}",
            f"- Passo nominal: "
            f"{result['traceability']['terrain_nominal_step_m']:.3f} m",
            f"- SHA-256 do resultado: `{result['result_sha256']}`",
            "",
            "Os modelos permanecem separados; a divergência entre eles não é "
            "tratada como uma distribuição aleatória.",
            "",
        ]
    )
    return "\n".join(lines)


def build_html_report(
    project: Project, result: dict[str, Any], make_plots: bool
) -> str:
    summary_html = _markdown_summary_to_simple_html(
        build_markdown_summary(project, result)
    )
    images = ""
    if make_plots:
        images = (
            '<section class="visual"><img src="profile.png" '
            'alt="Perfil técnico do enlace"></section>'
            '<section class="visual"><img src="monte_carlo.png" '
            'alt="Resultado de Monte Carlo"></section>'
        )
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(project.name)} — Radio Link Planner</title>
  <style>
    :root {{ --ink:#17191d; --muted:#60646c; --line:#d7dae0;
             --accent:#c91f37; --paper:#ffffff; --wash:#f4f5f7; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; color:var(--ink); background:var(--wash);
            font:15px/1.55 Inter,Segoe UI,Arial,sans-serif; }}
    header {{ background:#15171b; color:white; padding:30px 6vw 26px;
              border-bottom:5px solid var(--accent); }}
    header .version {{ color:#c7cbd2; letter-spacing:.08em;
                       text-transform:uppercase; font-size:12px; }}
    header h1 {{ margin:5px 0 2px; font-size:30px; }}
    main {{ max-width:1200px; margin:26px auto; padding:0 22px 60px; }}
    article, .visual {{ background:var(--paper); border:1px solid var(--line);
                        border-radius:10px; padding:24px 30px; margin:18px 0;
                        box-shadow:0 4px 18px rgba(0,0,0,.045); }}
    .visual {{ padding:10px; }}
    .visual img {{ display:block; width:100%; height:auto; }}
    h1,h2,h3 {{ line-height:1.2; }}
    h2 {{ margin-top:30px; border-bottom:1px solid var(--line);
          padding-bottom:8px; }}
    table {{ border-collapse:collapse; width:100%; margin:14px 0 22px; }}
    th,td {{ border-bottom:1px solid var(--line); padding:9px 8px;
             text-align:right; }}
    th:first-child,td:first-child {{ text-align:left; }}
    th {{ background:#f0f1f3; }}
    code {{ overflow-wrap:anywhere; }}
    .footer {{ color:var(--muted); font-size:12px; margin-top:30px; }}
  </style>
</head>
<body>
  <header>
    <div class="version">Radio Link Planner {html.escape(result['engine_version'])}</div>
    <h1>{html.escape(project.name)}</h1>
    <div>{project.frequency_mhz:.3f} MHz · análise local e rastreável</div>
  </header>
  <main>
    {images}
    <article>{summary_html}</article>
    <div class="footer">Gerado em {html.escape(result['generated_at_utc'])}</div>
  </main>
</body>
</html>
"""


def _markdown_summary_to_simple_html(markdown: str) -> str:
    lines = markdown.splitlines()
    output: list[str] = []
    in_list = False
    in_table = False
    table_rows: list[list[str]] = []

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            output.append("</ul>")
            in_list = False

    def close_table() -> None:
        nonlocal in_table, table_rows
        if not in_table:
            return
        output.append("<table>")
        for index, row in enumerate(table_rows):
            tag = "th" if index == 0 else "td"
            output.append(
                "<tr>"
                + "".join(f"<{tag}>{html.escape(cell)}</{tag}>" for cell in row)
                + "</tr>"
            )
        output.append("</table>")
        in_table = False
        table_rows = []

    for raw in lines:
        line = raw.strip()
        if line.startswith("|") and line.endswith("|"):
            close_list()
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if all(set(cell) <= {"-", ":"} for cell in cells):
                continue
            in_table = True
            table_rows.append(cells)
            continue
        close_table()
        if line.startswith("- "):
            if not in_list:
                output.append("<ul>")
                in_list = True
            output.append(f"<li>{html.escape(line[2:])}</li>")
            continue
        close_list()
        if line.startswith("# "):
            output.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("## "):
            output.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("### "):
            output.append(f"<h3>{html.escape(line[4:])}</h3>")
        elif line:
            escaped = html.escape(line).replace("**", "")
            output.append(f"<p>{escaped}</p>")
    close_list()
    close_table()
    return "\n".join(output)
