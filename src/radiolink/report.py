from __future__ import annotations

from .i18n import tr, choice_label, html_language, map_locale

import html
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from .domain import Project
from .geodesy import great_circle_points
from .geometry import GeometryArrays
from .terrain import TerrainProfile

_MATPLOTLIB_CACHE = Path(tempfile.gettempdir()) / "radio-link-planner-matplotlib"
_MATPLOTLIB_CACHE.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_MATPLOTLIB_CACHE))
os.environ.setdefault("MPLBACKEND", "Agg")
MAPLIBRE_VERSION = "5.24.0"


def describe_geometry_clearance(geometry: dict[str, Any]) -> str:
    """Describe the limiting terrain point without calling a clear path blocked."""
    distance_km = geometry["worst_obstruction_distance_km"]
    obstruction_m = geometry["worst_obstruction_m"]
    if obstruction_m > 0.0:
        return (
            tr('Pior obstrução geométrica: {x0:.1f} m a {x1:.1f} km', x0=obstruction_m, x1=distance_km)
        )
    return (
        tr('Menor folga geométrica: {x0:.1f} m a {x1:.1f} km', x0=geometry['worst_clearance_m'], x1=distance_km)
    )


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
        render_profile_plot(project, profile, result, geometry_arrays, profile_path)
        render_monte_carlo_plot(project, result, monte_carlo_path)
        paths["profile_plot"] = profile_path
        paths["monte_carlo_plot"] = monte_carlo_path
    map_assets = _install_map_assets(destination)
    report_path.write_text(
        build_html_report(
            project,
            profile,
            result,
            make_plots=make_plots,
            map_assets=map_assets,
        ),
        encoding="utf-8",
    )
    paths["interactive_map"] = report_path
    from .pdf_reports import write_link_pdf

    pdf_path = destination / "relatorio_enlace.pdf"
    paths["report_pdf"] = write_link_pdf(
        project=project,
        result=result,
        paths=paths,
        output_path=pdf_path,
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
        label=tr('Terreno / superfície'),
    )
    axis.plot(
        distance_km,
        arrays.apparent_terrain_m_asl,
        color="#d98b39",
        linewidth=1.1,
        label=tr('Terreno aparente (k={x0:.3f})', x0=project.environment.effective_earth_k),
    )
    axis.plot(
        distance_km,
        arrays.direct_ray_m_asl,
        color="#e7333f",
        linewidth=1.6,
        label=tr('Raio direto'),
    )
    axis.plot(
        distance_km,
        arrays.direct_ray_m_asl + 0.6 * arrays.fresnel_radius_m,
        color="#7db6d8",
        linewidth=0.9,
        label=tr('60% da 1ª Fresnel'),
    )
    axis.plot(
        distance_km,
        arrays.direct_ray_m_asl - 0.6 * arrays.fresnel_radius_m,
        color="#7db6d8",
        linewidth=0.9,
    )
    geometry = result["geometry"]
    is_obstructed = geometry["worst_obstruction_m"] > 0.0
    marker_color = "#f6c85f" if is_obstructed else "#3a9d62"
    box_color = "#fff7df" if is_obstructed else "#eaf7ef"
    annotation = (
        tr('Pior bloqueio: {x0:.1f} m', x0=geometry['worst_obstruction_m'])
        if is_obstructed
        else tr('Menor folga: {x0:.1f} m', x0=geometry['worst_clearance_m'])
    )
    axis.axvline(
        geometry["worst_obstruction_distance_km"],
        color=marker_color,
        linestyle="--",
        linewidth=1.0,
    )
    axis.annotate(
        tr("{annotation}\na {distance:.1f} km", annotation=annotation, distance=geometry["worst_obstruction_distance_km"]),
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
            "facecolor": box_color,
            "edgecolor": marker_color,
        },
    )
    axis.set_title(
        f"{project.name} — {project.frequency_mhz:.3f} MHz",
        loc="left",
        fontsize=15,
        fontweight="bold",
    )
    axis.set_xlabel(tr('Distância desde o terminal A (km)'))
    axis.set_ylabel(tr('Altitude / altura aparente (m)'))
    axis.grid(True, alpha=0.18)
    axis.legend(loc="upper right", ncol=2, fontsize=8)
    axis.set_xlim(0.0, profile.total_distance_km)
    lower = min(ground.min(), arrays.direct_ray_m_asl.min()) - 80.0
    upper = (
        max(
            arrays.apparent_terrain_m_asl.max(),
            (arrays.direct_ray_m_asl + 0.6 * arrays.fresnel_radius_m).max(),
        )
        + 80.0
    )
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
                tr('P1812 (condicional em p50)')
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
            label=tr('Limiar {x0}: {x1:.1f} dBm', x0=project.primary_mode.upper(), x1=threshold),
        )
    axis_hist.set_title(tr('Distribuição da potência recebida'), loc="left")
    axis_hist.set_xlabel(tr('Potência no receptor (dBm)'))
    axis_hist.set_ylabel(tr('Densidade relativa'))
    axis_hist.grid(True, alpha=0.18)
    axis_hist.legend(fontsize=8)
    bars = axis_bar.bar(labels, probabilities, color=bar_colors)
    axis_bar.axhline(
        project.target_availability_percent,
        color="#d62728",
        linestyle="--",
        linewidth=1.2,
        label=tr('Meta {x0:.0f}%', x0=project.target_availability_percent),
    )
    axis_bar.set_ylim(0.0, 105.0)
    axis_bar.set_ylabel(tr('Probabilidade estimada (%)'))
    axis_bar.set_title(tr('Funcionamento em {x0}', x0=project.primary_mode.upper()), loc="left")
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
            tr('* P.1812: probabilidade condicional ao p50; não é disponibilidade anual.'),
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
        tr('Versão do motor: {x0}', x0=result['engine_version']),
        "",
        tr('## Geometria'),
        "",
        tr('- Distância: {x0:.3f} km', x0=geometry['profile_distance_km']),
        f"- {describe_geometry_clearance(geometry)}",
        (
            tr('- Raio máximo da primeira Fresnel: {x0:.1f} m', x0=geometry['maximum_fresnel_radius_m'])
        ),
        (
            tr('- Fresnel de 60% obstruída em {x0:.1f}% do percurso', x0=geometry['fresnel_60_obstructed_percent'])
        ),
        "",
    ]
    for direction in result["directions"].values():
        assessment = direction["assessment"]
        classification_label = {
            "robust": tr('robusto'),
            "viable": tr('viável'),
            "marginal": tr('marginal'),
            "improbable": tr('improvável'),
            "indeterminate": tr('indeterminado'),
        }.get(assessment["classification"], assessment["classification"])
        confidence_label = {
            "high": tr('alta'),
            "medium": tr('média'),
            "low": tr('baixa'),
        }.get(assessment["confidence"], assessment["confidence"])
        lines.extend(
            [
                f"## {direction['transmitter']} → {direction['receiver']}",
                "",
                tr('**Parecer: {x0}**  ', x0=classification_label),
                tr('Confiança: {x0}', x0=confidence_label),
                "",
                tr('### Comparação coerente em {x0:.0f}%', x0=direction['comparison_percent']),
                "",
                tr('| Modelo | Perda (dB) |'),
                "|---|---:|",
            ]
        )
        for model in direction["comparison_models"]:
            if model["status"] == "ok":
                lines.append(
                    f"| {model['model_id'].upper()} | {model['loss_db']:.2f} |"
                )
            else:
                lines.append(f"| {model['model_id'].upper()} | {choice_label(model['status'])} |")
        if assessment["model_spread_db"] is not None:
            lines.extend(
                [
                    "",
                    (
                        tr('Dispersão entre modelos: **{x0:.2f} dB**.', x0=assessment['model_spread_db'])
                    ),
                ]
            )
        lines.extend(
            [
                "",
                tr('### Ponto de projeto: {x0:.0f}%', x0=direction['target_availability_percent']),
                "",
                tr('| Modelo | Quantil de projeto | Perda (dB) | Potência (dBm) | Margem (dB) |'),
                "|---|---:|---:|---:|---:|",
            ]
        )
        budgets = {item["model_id"]: item for item in direction["link_budgets"]}
        for model in direction["design_models"]:
            budget = budgets.get(model["model_id"])
            if model["status"] != "ok" or budget is None:
                lines.append(
                    tr('| {x0} | — | indisponível | — | — |', x0=model['model_id'].upper())
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
                    (
                        tr('> A P.1812 é limitada a 1–50% do tempo. Seu valor na tabela é mediano e não representa a meta de {x0:.0f}%.', x0=project.target_availability_percent)
                    ),
                ]
            )
        lines.extend(["", tr('### Recomendações'), ""])
        for item in assessment["recommendations"]:
            lines.append(
                tr('- {x0}: aproximadamente +{x1:.1f} dB ({x2}).', x0=recommendation_action(item), x1=item['estimated_margin_improvement_db'], x2=tr(item['basis']))
            )
        lines.extend(["", tr('### Incertezas declaradas'), ""])
        for item in assessment["uncertainties"]:
            lines.append(f"- {tr(item)}.")
        lines.append("")
    lines.extend(
        [
            tr('## Rastreabilidade'),
            "",
            tr('- SHA-256 do perfil: `{x0}`', x0=result['traceability']['terrain_sha256']),
            tr('- Pontos do perfil: {x0}', x0=result['traceability']['terrain_point_count']),
            (
                tr('- Passo nominal: {x0:.3f} m', x0=result['traceability']['terrain_nominal_step_m'])
            ),
            tr('- SHA-256 do resultado: `{x0}`', x0=result['result_sha256']),
            "",
            (
                tr('Os modelos permanecem separados; a divergência entre eles não é tratada como uma distribuição aleatória.')
            ),
            "",
        ]
    )
    return "\n".join(lines)


def build_html_report(
    project: Project,
    profile: TerrainProfile,
    result: dict[str, Any],
    make_plots: bool,
    map_assets: tuple[str, str] | None = None,
) -> str:
    summary_html = _markdown_summary_to_simple_html(
        build_markdown_summary(project, result)
    )
    if map_assets is None:
        map_assets = (
            (f"https://unpkg.com/maplibre-gl@{MAPLIBRE_VERSION}/dist/maplibre-gl.css"),
            (f"https://unpkg.com/maplibre-gl@{MAPLIBRE_VERSION}/dist/maplibre-gl.js"),
        )
    map_css, map_js = map_assets
    route_json = _route_json(project, profile)
    images = ""
    if make_plots:
        images = (
            '<section class="visual"><img src="profile.png" '
            f'alt="{html.escape(tr("Perfil técnico do enlace"))}"></section>'
            '<section class="visual"><img src="monte_carlo.png" '
            f'alt="{html.escape(tr("Resultado de Monte Carlo"))}"></section>'
        )
    return f"""<!doctype html>
<html lang="{html_language()}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="referrer" content="strict-origin-when-cross-origin">
  <title>{html.escape(tr('{x0} — Radio Link Planner', x0=html.escape(project.name)))}</title>
  <link rel="stylesheet" href="{html.escape(map_css, quote=True)}">
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
    .map-card {{ background:var(--paper); border:1px solid var(--line);
                 border-radius:10px; padding:14px; margin:18px 0;
                 box-shadow:0 4px 18px rgba(0,0,0,.045); }}
    #route-map {{ width:100%; height:470px; border-radius:7px;
                  background:#dfe4e8; }}
    .map-note {{ color:var(--muted); font-size:12px; margin:9px 3px 0; }}
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
    <div class="version">{html.escape(tr('Radio Link Planner {x0}', x0=html.escape(result['engine_version'])))}</div>
    <h1>{html.escape(project.name)}</h1>
    <div>{html.escape(tr('{x0:.3f} MHz · análise local e rastreável', x0=project.frequency_mhz))}</div>
  </header>
  <main>
    <section class="map-card">
      <div id="route-map" aria-label="{html.escape(tr('Mapa interativo do enlace'), quote=True)}"></div>
      <div class="map-note">{html.escape(tr('Mapa interativo MapLibre. A camada OpenStreetMap requer internet; o cálculo científico usa o perfil Copernicus salvo localmente e não depende do mapa.'))}</div>
    </section>
    {images}
    <article>{summary_html}</article>
    <div class="footer">{html.escape(tr('Gerado em {x0}', x0=html.escape(result['generated_at_utc'])))}</div>
  </main>
  <script src="{html.escape(map_js, quote=True)}"></script>
  <script>
    const routeData = {route_json};
    const map = new maplibregl.Map({{
      locale: {json.dumps(map_locale(), ensure_ascii=False)},
      container: "route-map",
      style: {{
        version: 8,
        sources: {{
          osm: {{
            type: "raster",
            tiles: ["https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png"],
            tileSize: 256,
            attribution: "© OpenStreetMap contributors"
          }}
        }},
        layers: [{{ id: "osm", type: "raster", source: "osm" }}]
      }},
      attributionControl: true
    }});
    map.addControl(new maplibregl.NavigationControl(), "top-right");
    map.on("load", () => {{
      map.addSource("route", {{
        type: "geojson",
        data: {{
          type: "Feature",
          properties: {{}},
          geometry: {{ type: "LineString", coordinates: routeData.coordinates }}
        }}
      }});
      map.addLayer({{
        id: "route-halo",
        type: "line",
        source: "route",
        paint: {{ "line-color": "#ffffff", "line-width": 7, "line-opacity": 0.9 }}
      }});
      map.addLayer({{
        id: "route-line",
        type: "line",
        source: "route",
        paint: {{ "line-color": "#c91f37", "line-width": 4 }}
      }});
      new maplibregl.Marker({{ color: "#2264a7" }})
        .setLngLat(routeData.coordinates[0])
        .setPopup(new maplibregl.Popup().setText(routeData.terminalA))
        .addTo(map);
      new maplibregl.Marker({{ color: "#c91f37" }})
        .setLngLat(routeData.coordinates[routeData.coordinates.length - 1])
        .setPopup(new maplibregl.Popup().setText(routeData.terminalB))
        .addTo(map);
      const bounds = new maplibregl.LngLatBounds(
        routeData.coordinates[0],
        routeData.coordinates[0]
      );
      routeData.coordinates.forEach((point) => bounds.extend(point));
      map.fitBounds(bounds, {{ padding: 70, maxZoom: 13, duration: 0 }});
    }});
  </script>
</body>
</html>
"""


def _route_json(project: Project, profile: TerrainProfile) -> str:
    maximum_points = 3000
    latitudes = profile.latitude_deg
    longitudes = profile.longitude_deg
    if not np.all(np.isfinite(latitudes)) or not np.all(np.isfinite(longitudes)):
        latitudes, longitudes = great_circle_points(
            project.terminal_a.latitude_deg,
            project.terminal_a.longitude_deg,
            project.terminal_b.latitude_deg,
            project.terminal_b.longitude_deg,
            len(profile.distance_km),
        )
    if len(longitudes) > maximum_points:
        indices = np.linspace(
            0,
            len(longitudes) - 1,
            maximum_points,
            dtype=int,
        )
    else:
        indices = np.arange(len(longitudes))
    coordinates = [
        [float(longitudes[index]), float(latitudes[index])] for index in indices
    ]
    data = {
        "terminalA": project.terminal_a.name,
        "terminalB": project.terminal_b.name,
        "coordinates": coordinates,
    }
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace(
        "</", "<\\/"
    )


def _install_map_assets(destination: Path) -> tuple[str, str]:
    frozen_root = getattr(sys, "_MEIPASS", None)
    source_root = (
        Path(frozen_root).resolve()
        if frozen_root
        else Path(__file__).resolve().parents[2]
    )
    source = source_root / "map-assets"
    javascript = source / "maplibre-gl.js"
    stylesheet = source / "maplibre-gl.css"
    if javascript.is_file() and stylesheet.is_file():
        target = destination / "report-assets"
        target.mkdir(parents=True, exist_ok=True)
        shutil.copy2(javascript, target / javascript.name)
        shutil.copy2(stylesheet, target / stylesheet.name)
        license_path = source / "LICENSE.txt"
        if license_path.is_file():
            shutil.copy2(license_path, target / license_path.name)
        return (
            "report-assets/maplibre-gl.css",
            "report-assets/maplibre-gl.js",
        )
    return (
        (f"https://unpkg.com/maplibre-gl@{MAPLIBRE_VERSION}/dist/maplibre-gl.css"),
        (f"https://unpkg.com/maplibre-gl@{MAPLIBRE_VERSION}/dist/maplibre-gl.js"),
    )


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



def recommendation_action(item: dict[str, Any]) -> str:
    action = item["action"]
    prefix = "aumentar o ganho da antena de "
    suffix = " para 9 dBi"
    if action.startswith(prefix) and action.endswith(suffix):
        return tr("aumentar o ganho da antena de {terminal} para 9 dBi", terminal=action[len(prefix):-len(suffix)])
    return tr(action)
