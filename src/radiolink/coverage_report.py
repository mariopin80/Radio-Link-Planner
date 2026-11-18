from __future__ import annotations

from .i18n import tr, html_language, map_locale

import html
import json
import math
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

from .coverage import (
    CONTOUR_LEVELS_DB,
    CoverageRequest,
    ProgressCallback,
    RadialCoverage,
)
from .geodesy import destination_point
from .legal_notices import (
    COPERNICUS_GLO30_DERIVED_CREDIT,
    COPERNICUS_GLO30_NO_LIABILITY,
    COPERNICUS_LICENSE_URL,
    OSM_HTML_ATTRIBUTION,
)
from .report import _install_map_assets

_MATPLOTLIB_CACHE = Path(tempfile.gettempdir()) / "radio-link-planner-matplotlib"
_MATPLOTLIB_CACHE.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_MATPLOTLIB_CACHE))
os.environ.setdefault("MPLBACKEND", "Agg")

# IARU VHF/UHF convention: S9 = -93 dBm, 6 dB per S-unit.
S_CONTOUR_LEVELS_DBM = (
    ("S1", -141.0),
    ("S3", -129.0),
    ("S5", -117.0),
    ("S7", -105.0),
    ("S9+", -93.0),
)


def write_coverage_outputs(
    *,
    request: CoverageRequest,
    grid: np.ndarray,
    grid_metadata: dict[str, Any],
    output_directory: Path,
    progress: ProgressCallback | None = None,
    radials: tuple[RadialCoverage, ...] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> tuple[dict[str, Path], dict[str, Any]]:
    output_directory.mkdir(parents=True, exist_ok=True)
    overlay_path = output_directory / "coverage_overlay.png"
    s_overlay_path = output_directory / "coverage_overlay_s.png"
    heatmap_path = output_directory / "coverage_heatmap.png"
    contours_path = output_directory / "coverage_contours.geojson"
    s_contours_path = output_directory / "coverage_contours_s.geojson"
    report_path = output_directory / "coverage_report.html"

    _check_cancelled(cancel_check)
    _notify(progress, tr('Cobertura: renderizando escala de cores…'))
    sampled, axis_km = _sample_grid_for_rendering(
        grid,
        request.radius_km,
        request.resolution_m,
    )
    _check_cancelled(cancel_check)
    _notify(progress, tr('Cobertura: grade preparada para renderização.'))
    overlay_tiles = _render_overlay(
        request,
        sampled,
        axis_km,
        overlay_path,
    )
    s_overlay_tiles = _render_overlay(
        request,
        sampled,
        axis_km,
        s_overlay_path,
        scale="s",
    )
    _check_cancelled(cancel_check)
    _notify(progress, tr('Cobertura: heatmap interativo renderizado.'))
    contour_geojson = _render_heatmap_and_contours(
        request,
        sampled,
        axis_km,
        heatmap_path,
    )
    s_contour_geojson = _render_s_contours(request, sampled, axis_km)
    _check_cancelled(cancel_check)
    _notify(progress, tr('Cobertura: contornos científicos gerados.'))
    contours_path.write_text(
        json.dumps(contour_geojson, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    s_contours_path.write_text(
        json.dumps(s_contour_geojson, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    map_assets = _install_map_assets(output_directory)
    _check_cancelled(cancel_check)
    statistics = _coverage_statistics(grid)
    report_path.write_text(
        _build_coverage_report(
            request=request,
            statistics=statistics,
            grid_metadata=grid_metadata,
            contour_geojson=contour_geojson,
            overlay_tiles=overlay_tiles,
            s_contour_geojson=s_contour_geojson,
            s_overlay_tiles=s_overlay_tiles,
            map_assets=map_assets,
            radials=radials,
        ),
        encoding="utf-8",
    )
    paths = {
        "report_html": report_path,
        "heatmap": heatmap_path,
        "map_overlay": overlay_path,
        "s_map_overlay": s_overlay_path,
        "contours": contours_path,
        "s_contours": s_contours_path,
    }
    from .pdf_reports import write_coverage_pdf

    paths["report_pdf"] = write_coverage_pdf(
        request=request,
        statistics={**grid_metadata, **statistics},
        paths=paths,
        output_path=output_directory / "relatorio_cobertura.pdf",
    )
    _check_cancelled(cancel_check)
    _notify(progress, tr('Cobertura: mapa e relatório finalizados.'))
    return paths, statistics


def _sample_grid_for_rendering(
    grid: np.ndarray,
    radius_km: int,
    resolution_m: int,
) -> tuple[np.ndarray, np.ndarray]:
    maximum_render_dimension = 1800
    stride = max(1, math.ceil(max(grid.shape) / maximum_render_dimension))
    sampled = np.asarray(grid[::stride, ::stride], dtype=np.float32)
    radius = radius_km * 1000.0
    full_axis = (
        np.arange(grid.shape[1], dtype=float) - (grid.shape[1] - 1) / 2.0
    ) * resolution_m
    return sampled, full_axis[::stride] / 1000.0


def _coverage_colormap():
    from matplotlib.colors import LinearSegmentedColormap

    return LinearSegmentedColormap.from_list(
        "radio_link_margin",
        [
            (0.00, "#65121b"),
            (0.20, "#c62828"),
            (0.36, "#ef6c00"),
            (0.44, "#ffd54f"),
            (0.58, "#9ccc65"),
            (0.76, "#2e7d32"),
            (1.00, "#0b5969"),
        ],
    )


def _render_overlay(
    request: CoverageRequest,
    grid: np.ndarray,
    axis_km: np.ndarray,
    path: Path,
    *,
    scale: str = "margin",
) -> list[dict[str, Any]]:
    import matplotlib.pyplot as plt
    from matplotlib.colors import Normalize

    colormap = _coverage_colormap()
    if scale == "margin":
        render_values = grid
        minimum, maximum = -12.0, 18.0
    elif scale == "s":
        render_values = grid + request.receiver_threshold_dbm
        minimum, maximum = -141.0, -93.0
    else:
        raise ValueError(f"unsupported coverage scale: {scale}")
    normalization = Normalize(vmin=minimum, vmax=maximum, clip=True)
    rgba = colormap(normalization(np.nan_to_num(render_values, nan=minimum)))
    rgba[..., 3] = np.where(np.isfinite(grid), 0.78, 0.0)
    plt.imsave(path, rgba, origin="upper")
    tile_count = 1 if request.radius_km <= 100 else (
        2 if request.radius_km <= 300 else 4
    )
    boundaries = np.linspace(0, len(axis_km) - 1, tile_count + 1, dtype=int)
    north_axis_km = axis_km[::-1]
    tiles: list[dict[str, Any]] = []
    for row in range(tile_count):
        for column in range(tile_count):
            row_start = int(boundaries[row])
            row_stop = int(boundaries[row + 1])
            column_start = int(boundaries[column])
            column_stop = int(boundaries[column + 1])
            suffix = "_s" if scale == "s" else ""
            filename = f"coverage_overlay{suffix}_r{row}_c{column}.png"
            tile_path = path.parent / filename
            plt.imsave(
                tile_path,
                rgba[
                    row_start : row_stop + 1,
                    column_start : column_stop + 1,
                ],
                origin="upper",
            )
            local_corners = (
                (axis_km[column_start], north_axis_km[row_start]),
                (axis_km[column_stop], north_axis_km[row_start]),
                (axis_km[column_stop], north_axis_km[row_stop]),
                (axis_km[column_start], north_axis_km[row_stop]),
            )
            tiles.append(
                {
                    "url": filename,
                    "coordinates": [
                        _local_point_to_lon_lat(request, east, north)
                        for east, north in local_corners
                    ],
                }
            )
    return tiles


def _render_heatmap_and_contours(
    request: CoverageRequest,
    grid: np.ndarray,
    axis_km: np.ndarray,
    output_path: Path,
) -> dict[str, Any]:
    import matplotlib.pyplot as plt
    from matplotlib.colors import Normalize

    x_grid, y_grid = np.meshgrid(axis_km, axis_km[::-1])
    colormap = _coverage_colormap()
    normalization = Normalize(vmin=-12.0, vmax=18.0, clip=True)
    figure, axis = plt.subplots(figsize=(10.8, 9.2), dpi=150)
    image = axis.imshow(
        grid,
        extent=(axis_km[0], axis_km[-1], axis_km[0], axis_km[-1]),
        origin="upper",
        cmap=colormap,
        norm=normalization,
        interpolation="bilinear",
    )
    contours = axis.contour(
        x_grid,
        y_grid,
        grid,
        levels=CONTOUR_LEVELS_DB,
        colors=("#7a0012", "#8a5a00", "#1d551f", "#08384f"),
        linewidths=(0.65, 0.5, 0.5, 0.6),
        alpha=0.5,
    )
    axis.clabel(contours, fmt=lambda value: f"{value:+.0f} dB", fontsize=7)
    axis.scatter(
        [0.0],
        [0.0],
        marker="^",
        s=90,
        color="#111111",
        edgecolor="#ffffff",
        linewidth=1.1,
        zorder=10,
        label=tr('Transmissor'),
    )
    axis.set_title(
        f"{request.name} — {request.frequency_mhz:.3f} MHz",
        loc="left",
        fontsize=15,
        fontweight="bold",
    )
    axis.set_xlabel(tr('Deslocamento leste–oeste (km)'))
    axis.set_ylabel(tr('Deslocamento norte–sul (km)'))
    axis.set_aspect("equal")
    axis.grid(True, color="#ffffff", alpha=0.15)
    colorbar = figure.colorbar(image, ax=axis, shrink=0.86, pad=0.025)
    colorbar.set_label(tr('Margem do enlace (dB)'))
    axis.legend(loc="lower right")
    figure.tight_layout()
    figure.savefig(output_path, bbox_inches="tight")

    features: list[dict[str, Any]] = []
    for level, segments in zip(contours.levels, contours.allsegs):
        for segment in segments:
            if len(segment) < 2:
                continue
            coordinates = _local_km_to_lon_lat(
                request.latitude_deg,
                request.longitude_deg,
                segment,
            )
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "level_db": float(level),
                        "label": f"{level:+.0f} dB",
                    },
                    "geometry": {
                        "type": "LineString",
                        "coordinates": coordinates,
                    },
                }
            )
    plt.close(figure)
    return {
        "type": "FeatureCollection",
        "features": features,
    }


def _render_s_contours(
    request: CoverageRequest,
    grid: np.ndarray,
    axis_km: np.ndarray,
) -> dict[str, Any]:
    """Return S-meter contours from received power, not link margin."""
    import matplotlib.pyplot as plt

    power_dbm = np.asarray(grid, dtype=float) + request.receiver_threshold_dbm
    finite_values = power_dbm[np.isfinite(power_dbm)]
    if not finite_values.size:
        return {"type": "FeatureCollection", "features": []}

    lowest, highest = float(np.min(finite_values)), float(np.max(finite_values))
    selected = [
        (label, level)
        for label, level in S_CONTOUR_LEVELS_DBM
        if lowest < level < highest
    ]
    if not selected:
        return {"type": "FeatureCollection", "features": []}

    x_grid, y_grid = np.meshgrid(axis_km, axis_km[::-1])
    figure, axis = plt.subplots()
    contours = axis.contour(
        x_grid, y_grid, np.ma.masked_invalid(power_dbm),
        levels=[level for _, level in selected],
    )
    features: list[dict[str, Any]] = []
    for (label, level), segments in zip(selected, contours.allsegs):
        for segment in segments:
            if len(segment) < 2:
                continue
            features.append({
                "type": "Feature",
                "properties": {"level_dbm": level, "label": label},
                "geometry": {
                    "type": "LineString",
                    "coordinates": _local_km_to_lon_lat(
                        request.latitude_deg, request.longitude_deg, segment,
                    ),
                },
            })
    plt.close(figure)
    return {"type": "FeatureCollection", "features": features}


def _local_km_to_lon_lat(
    latitude_deg: float,
    longitude_deg: float,
    points_km: np.ndarray,
) -> list[list[float]]:
    east_m = points_km[:, 0] * 1000.0
    north_m = points_km[:, 1] * 1000.0
    distances = np.hypot(east_m, north_m)
    bearings = (np.degrees(np.arctan2(east_m, north_m)) + 360.0) % 360.0
    coordinates: list[list[float]] = []
    for bearing, distance in zip(bearings, distances):
        latitude, longitude = destination_point(
            latitude_deg,
            longitude_deg,
            float(bearing),
            float(distance),
        )
        coordinates.append([longitude, latitude])
    return coordinates


def _coverage_statistics(grid: np.ndarray) -> dict[str, Any]:
    finite_count = 0
    threshold_counts = {level: 0 for level in CONTOUR_LEVELS_DB}
    minimum = float("inf")
    maximum = float("-inf")
    chunk_rows = 256
    for start in range(0, grid.shape[0], chunk_rows):
        values = np.asarray(grid[start : start + chunk_rows])
        finite = values[np.isfinite(values)]
        if not len(finite):
            continue
        finite_count += len(finite)
        minimum = min(minimum, float(np.min(finite)))
        maximum = max(maximum, float(np.max(finite)))
        for level in threshold_counts:
            threshold_counts[level] += int(np.count_nonzero(finite >= level))
    if finite_count == 0:
        raise ValueError("coverage grid contains no finite cells")
    return {
        "minimum_margin_db": minimum,
        "maximum_margin_db": maximum,
        "covered_percent": 100.0 * threshold_counts[0.0] / finite_count,
        "margin_3_db_percent": 100.0 * threshold_counts[3.0] / finite_count,
        "margin_6_db_percent": 100.0 * threshold_counts[6.0] / finite_count,
        "margin_12_db_percent": 100.0 * threshold_counts[12.0] / finite_count,
    }


def _build_coverage_report(
    *,
    request: CoverageRequest,
    statistics: dict[str, Any],
    grid_metadata: dict[str, Any],
    contour_geojson: dict[str, Any],
    overlay_tiles: list[dict[str, Any]],
    map_assets: tuple[str, str],
    radials: tuple[RadialCoverage, ...] | None = None,
    s_contour_geojson: dict[str, Any] | None = None,
    s_overlay_tiles: list[dict[str, Any]] | None = None,
) -> str:
    map_css, map_js = map_assets
    bounds = _coverage_bounds(request)
    embedded_contours = json.dumps(
        contour_geojson,
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\\/")
    embedded_overlay_tiles = json.dumps(
        overlay_tiles,
        separators=(",", ":"),
    )
    embedded_s_contours = json.dumps(
        s_contour_geojson or {"type": "FeatureCollection", "features": []},
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\\/")
    embedded_s_overlay_tiles = json.dumps(
        s_overlay_tiles or [], separators=(",", ":"),
    )
    raster_cells = grid_metadata["valid_circle_cells"]
    failed_cells = int(grid_metadata.get("failed_cells", 0))
    resume_count = int(grid_metadata.get("resume_count", 0))
    compute_duration = _format_duration(
        float(grid_metadata.get("compute_seconds", 0.0))
    )
    if radials is None:
        eyebrow = tr('Radio Link Planner · grade métrica direta')
        traceability_rows = f"""
        <tr><th>{html.escape(tr('Modelo'))}</th><td>ITU-R P.1812-8</td></tr>
        <tr><th>{html.escape(tr('Implementação'))}</th>
          <td>{html.escape(str(grid_metadata["model_version"]))}</td></tr>
        <tr><th>{html.escape(tr('Método'))}</th><td>{html.escape(tr('Grade métrica direta (AEQD)'))}</td></tr>
        <tr><th>{html.escape(tr('Resolução das células'))}</th>
          <td>{html.escape(tr('{x0} m', x0=request.resolution_m))}</td></tr>
        <tr><th>{html.escape(tr('Amostragem do terreno nos perfis'))}</th>
          <td>{html.escape(tr('{x0:g} m', x0=request.terrain_step_m))}</td></tr>
        <tr><th>{html.escape(tr('Células dentro do círculo'))}</th><td>{raster_cells:,}</td></tr>
        <tr><th>{html.escape(tr('Células concluídas'))}</th>
          <td>{grid_metadata.get("calculated_cells", raster_cells):,}</td></tr>
        <tr><th>{html.escape(tr('Células P.1812 calculadas'))}</th>
          <td>{grid_metadata["p1812_cells"]:,}</td></tr>
        <tr><th>{html.escape(tr('Células de curta distância (espaço livre)'))}</th>
          <td>{grid_metadata["short_range_free_space_cells"]:,}</td></tr>
        <tr><th>{html.escape(tr('Células com falha'))}</th><td>{failed_cells:,}</td></tr>
        <tr><th>{html.escape(tr('Células interpoladas pelo motor'))}</th><td>0</td></tr>
        <tr><th>{html.escape(tr('Células com perda reaproveitada'))}</th>
          <td>{grid_metadata.get("reused_propagation_cells", 0):,}</td></tr>
        <tr><th>{html.escape(tr('Chamadas P.1812 nesta execução'))}</th>
          <td>{grid_metadata.get("p1812_calls_this_run", grid_metadata["p1812_cells"]):,}</td></tr>
        <tr><th>{html.escape(tr('Pontos de terreno processados'))}</th>
          <td>{grid_metadata["terrain_profile_points"]:,}</td></tr>
        <tr><th>{html.escape(tr('Processos de cálculo'))}</th>
          <td>{grid_metadata["worker_count"]}</td></tr>
        <tr><th>{html.escape(tr('Tempo acumulado da grade'))}</th>
          <td>{html.escape(compute_duration)}</td></tr>
        <tr><th>{html.escape(tr('Retomadas de checkpoint'))}</th><td>{resume_count}</td></tr>
        <tr><th>{html.escape(tr('Relevo'))}</th><td>Copernicus GLO-30</td></tr>"""
        method_notes = f"""
      <p class="note">{html.escape(tr("Cada centro de célula a partir de 250 m recebeu uma execução independente da P.1812 com seu próprio perfil de terreno. Não há interpolação de perda entre radiais ou entre células. A imagem pode ser reamostrada apenas para exibição no navegador."))}</p>
      <p class="note">{html.escape(tr("A P.1812-8 declara escopo a partir de 0,25 km. Dentro dessa distância, o programa utiliza perda em espaço livre, identificada separadamente nos metadados."))}</p>"""
    else:
        eyebrow = tr('Radio Link Planner · comparação radial legada')
        evaluated = sum(item.evaluated_point_count for item in radials)
        traceability_rows = f"""
        <tr><th>Modelo</th><td>ITU-R P.1812-8</td></tr>
        <tr><th>Método</th><td>Radiais adaptativos legados</td></tr>
        <tr><th>Resolução visual</th><td>{request.resolution_m} m</td></tr>
        <tr><th>Perfis radiais calculados</th><td>{len(radials)}</td></tr>
        <tr><th>Pontos avaliados fisicamente</th><td>{evaluated:,}</td></tr>
        <tr><th>Células do raster interpolado</th><td>{raster_cells:,}</td></tr>
        <tr><th>Relevo</th><td>Copernicus GLO-30</td></tr>"""
        method_notes = f"""
      <p class="note">{html.escape(tr("Resultado legado mantido somente para comparações controladas. O raster foi interpolado entre perfis radiais e não representa uma execução independente da P.1812 em cada célula."))}</p>"""
    return f"""<!doctype html>
<html lang="{html_language()}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="referrer" content="strict-origin-when-cross-origin">
  <title>{html.escape(tr('{x0} — Radio Link Planner', x0=request.name))}</title>
  <link rel="stylesheet" href="{html.escape(map_css, quote=True)}">
  <style>
    :root {{ --ink:#17191d; --muted:#60646c; --line:#d7dae0;
             --accent:#c91f37; --paper:#fff; --wash:#f4f5f7; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; color:var(--ink); background:var(--wash);
            font:15px/1.5 Inter,Segoe UI,Arial,sans-serif; }}
    header {{ background:#15171b; color:white; padding:28px 6vw 24px;
              border-bottom:5px solid var(--accent); }}
    header h1 {{ margin:5px 0 2px; font-size:30px; }}
    header .eyebrow {{ color:#c7cbd2; text-transform:uppercase;
                       letter-spacing:.08em; font-size:12px; }}
    main {{ max-width:1280px; margin:24px auto; padding:0 22px 60px; }}
    .card {{ background:var(--paper); border:1px solid var(--line);
             border-radius:10px; padding:18px; margin:18px 0;
             box-shadow:0 4px 18px rgba(0,0,0,.045); }}
    #coverage-map {{ height:650px; border-radius:7px; background:#dfe4e8; }}
    .legend {{ position:absolute; z-index:2; left:14px; bottom:28px;
               background:rgba(255,255,255,.94); padding:10px 12px;
               border-radius:6px; box-shadow:0 2px 10px rgba(0,0,0,.2);
               width:235px; font-size:12px; }}
    .legend-gradient {{ height:13px; border-radius:3px; margin:5px 0 3px;
      background:linear-gradient(90deg,#65121b,#c62828,#ef6c00,#ffd54f,
                                 #9ccc65,#2e7d32,#0b5969); }}
    .legend-ticks {{ display:flex; justify-content:space-between; color:#34383e; }}
    .map-wrap {{ position:relative; }}
    .map-actions {{ display:flex; flex-wrap:wrap; align-items:center;
                    justify-content:space-between; gap:12px; margin-bottom:12px; }}
    .map-actions label {{ font-weight:600; }}
    .map-actions select {{ margin-left:8px; padding:7px 10px; border:1px solid var(--line);
                           border-radius:6px; background:white; }}
    .map-actions button {{ background:var(--accent); color:white; border:0;
                           padding:9px 15px; border-radius:6px; font-weight:600;
                           cursor:pointer; }}
    .map-actions button:disabled {{ opacity:0.5; cursor:wait; }}
    .export-status {{ color:var(--muted); font-size:12px; min-height:18px; }}
    .stats {{ display:grid; grid-template-columns:repeat(4,minmax(130px,1fr));
              gap:12px; }}
    .stat {{ background:#f2f3f5; border-radius:7px; padding:13px; }}
    .stat strong {{ display:block; font-size:22px; }}
    .note {{ color:var(--muted); font-size:13px; }}
    table {{ border-collapse:collapse; width:100%; }}
    th,td {{ border-bottom:1px solid var(--line); padding:9px;
             text-align:left; }}
    th:last-child,td:last-child {{ text-align:right; }}
    @media(max-width:760px) {{
      #coverage-map {{ height:520px; }}
      .stats {{ grid-template-columns:repeat(2,1fr); }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="eyebrow">{eyebrow}</div>
    <h1>{html.escape(request.name)}</h1>
    <div>{html.escape(tr('{x0:.3f} MHz · P.1812 a {x1:.0f}% do tempo · raio {x2} km', x0=request.frequency_mhz, x1=request.time_percentage, x2=request.radius_km))}</div>
  </header>
  <main>
    <section class="card map-wrap">
      <div class="map-actions">
        <label for="coverage-scale">{html.escape(tr('Visualização'))}
          <select id="coverage-scale">
            <option value="margin">{html.escape(tr('Margem (dB)'))}</option>
            <option value="s">{html.escape(tr('Escala S'))}</option>
          </select>
        </label>
        <button type="button" id="export-map-pdf" disabled>{html.escape(tr('Exportar PDF com este mapa'))}</button>
      </div>
      <div class="export-status" id="export-status" role="status" aria-live="polite"></div>
      <p class="note">{html.escape(tr('Escala S estimada para VHF/UHF: S9 = −93 dBm e 6 dB por unidade S. O indicador real do receptor pode ser diferente.'))}</p>
      <div id="coverage-map" aria-label="{html.escape(tr('Mapa de cobertura'), quote=True)}"></div>
      <div class="legend" id="coverage-legend">
        <strong id="legend-title">{html.escape(tr('Margem do enlace'))}</strong>
        <div class="legend-gradient"></div>
        <div class="legend-ticks" id="legend-ticks"><span>−12</span><span>0</span>
          <span>+6</span><span>+12</span><span>{html.escape(tr('+18 dB'))}</span></div>
        <div style="margin-top:7px" id="legend-contours">{html.escape(tr('Contornos: 0, +3, +6 e +12 dB'))}</div>
      </div>
    </section>
    <section class="card">
      <div class="stats">
        <div class="stat"><span>{html.escape(tr('Área com margem ≥ 0 dB'))}</span>
          <strong>{html.escape(tr('{x0:.1f}%', x0=statistics['covered_percent']))}</strong></div>
        <div class="stat"><span>{html.escape(tr('Margem ≥ +3 dB'))}</span>
          <strong>{html.escape(tr('{x0:.1f}%', x0=statistics['margin_3_db_percent']))}</strong></div>
        <div class="stat"><span>{html.escape(tr('Margem ≥ +6 dB'))}</span>
          <strong>{html.escape(tr('{x0:.1f}%', x0=statistics['margin_6_db_percent']))}</strong></div>
        <div class="stat"><span>{html.escape(tr('Margem ≥ +12 dB'))}</span>
          <strong>{html.escape(tr('{x0:.1f}%', x0=statistics['margin_12_db_percent']))}</strong></div>
      </div>
    </section>
    <section class="card">
      <h2>{html.escape(tr('Rastreabilidade do cálculo'))}</h2>
      <table>
        {traceability_rows}
      </table>
      {method_notes}
      <p class="note">{html.escape(tr('Vegetação, edificações e ruído local ainda não estão representados nesta versão; áreas urbanas e florestais devem ser interpretadas com essa limitação.'))}</p>
      <p class="note">{html.escape(COPERNICUS_GLO30_DERIVED_CREDIT)}</p>
      <p class="note">{html.escape(COPERNICUS_GLO30_NO_LIABILITY)}
        <a href="{html.escape(COPERNICUS_LICENSE_URL, quote=True)}">Copernicus DEM licence</a></p>
    </section>
    <section class="card">
      <img src="coverage_heatmap.png" alt="{html.escape(tr('Mapa técnico de cobertura'), quote=True)}"
           style="width:100%;height:auto;display:block">
    </section>
  </main>
  <script src="{html.escape(map_js, quote=True)}"></script>
  <script>
    const overlayTiles = {embedded_overlay_tiles};
    const sOverlayTiles = {embedded_s_overlay_tiles};
    const coverageBounds = {json.dumps(bounds)};
    const contourData = {embedded_contours};
    const sContourData = {embedded_s_contours};
    const stationCoordinates = [{request.longitude_deg}, {request.latitude_deg}];
    const scaleSelect = document.getElementById("coverage-scale");
    const exportButton = document.getElementById("export-map-pdf");
    const exportStatus = document.getElementById("export-status");
    const legendLabels = {{
      margin: {{title:{json.dumps(tr('Margem do enlace'))},
                ticks:["−12", "0", "+6", "+12", "+18 dB"],
                contours:{json.dumps(tr('Contornos: 0, +3, +6 e +12 dB'))}}},
      s: {{title:{json.dumps(tr('Potência recebida estimada (escala S)'))},
          ticks:["S1", "S3", "S5", "S7", "S9+"],
          contours:{json.dumps(tr('Contornos: S1, S3, S5, S7 e S9+'))}}}
    }};
    const palette = ["#65121b", "#c62828", "#ef6c00", "#ffd54f",
                     "#9ccc65", "#2e7d32", "#0b5969"];
    const map = new maplibregl.Map({{
      locale: {json.dumps(map_locale(), ensure_ascii=False)},
      container: "coverage-map",
      canvasContextAttributes: {{preserveDrawingBuffer:true}},
      style: {{
        version: 8,
        sources: {{
          osm: {{
            type: "raster",
            tiles: ["https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png"],
            tileSize: 256,
            attribution: {json.dumps(OSM_HTML_ATTRIBUTION, ensure_ascii=False)}
          }}
        }},
        layers: [{{ id:"osm", type:"raster", source:"osm" }}]
      }}
    }});
    map.fitBounds(coverageBounds, {{padding:45,duration:0}});
    map.addControl(new maplibregl.NavigationControl(), "top-right");
    function addOverlayGroup(tiles, mode) {{
      tiles.forEach((tile,index) => {{
        const sourceId = "coverage-" + mode + "-" + index;
        map.addSource(sourceId, {{
          type:"image", url:tile.url, coordinates:tile.coordinates
        }});
        map.addLayer({{
          id:"coverage-image-" + mode + "-" + index,
          type:"raster", source:sourceId,
          layout:{{visibility:mode === "margin" ? "visible" : "none"}},
          paint:{{"raster-opacity":0.78,"raster-resampling":"linear"}}
        }});
      }});
    }}
    function addContourGroup(data, mode) {{
      const sourceId = "contours-" + mode;
      map.addSource(sourceId, {{type:"geojson", data:data}});
      const matchExpression = mode === "margin"
        ? ["match",["get","level_db"],
           0,"#7a0012",3,"#8a5a00",6,"#1d551f",12,"#08384f","#111"]
        : ["match",["get","level_dbm"],
           -141,"#7a0012",-129,"#8a5a00",-117,"#1d551f",
           -105,"#08384f",-93,"#062e3d","#111"];
      map.addLayer({{
        id:"contour-lines-" + mode, type:"line", source:sourceId,
        layout:{{visibility:mode === "margin" ? "visible" : "none"}},
        paint:{{"line-color":matchExpression,"line-width":1.0,"line-opacity":0.75}}
      }});
      map.addLayer({{
        id:"contour-labels-" + mode, type:"symbol", source:sourceId,
        layout:{{
          visibility:mode === "margin" ? "visible" : "none",
          "symbol-placement":"line",
          "text-field":["get","label"],
          "text-size":11,
          "symbol-spacing":350,
          "text-allow-overlap":false
        }},
        paint:{{
          "text-color":"#111", "text-halo-color":"#fff",
          "text-halo-width":1.2, "text-opacity":0.9
        }}
      }});
    }}
    function updateScale() {{
      for (const mode of ["margin", "s"]) {{
        const visibility = mode === scaleSelect.value ? "visible" : "none";
        const tiles = mode === "margin" ? overlayTiles : sOverlayTiles;
        tiles.forEach((_,index) => {{
          map.setLayoutProperty("coverage-image-" + mode + "-" + index,
                                "visibility", visibility);
        }});
        for (const layer of ["contour-lines-", "contour-labels-"]) {{
          map.setLayoutProperty(layer + mode, "visibility", visibility);
        }}
      }}
      const label = legendLabels[scaleSelect.value];
      document.getElementById("legend-title").textContent = label.title;
      document.getElementById("legend-ticks").replaceChildren(
        ...label.ticks.map(text => {{
          const item = document.createElement("span");
          item.textContent = text;
          return item;
        }})
      );
      document.getElementById("legend-contours").textContent = label.contours;
    }}
    let layersReady = false;
    map.on("load", () => {{
      addOverlayGroup(overlayTiles, "margin");
      addOverlayGroup(sOverlayTiles, "s");
      addContourGroup(contourData, "margin");
      addContourGroup(sContourData, "s");
      new maplibregl.Marker({{color:"#c91f37"}})
        .setLngLat(stationCoordinates)
        .setPopup(new maplibregl.Popup().setText({json.dumps(tr("Transmissor"))}))
        .addTo(map);
      layersReady = true;
      exportButton.disabled = location.protocol !== "http:";
    }});
    scaleSelect.addEventListener("change", () => {{
      if (layersReady) updateScale();
    }});

    function captureVisibleMap() {{
      const sourceCanvas = map.getCanvas();
      const canvas = document.createElement("canvas");
      canvas.width = sourceCanvas.width;
      canvas.height = sourceCanvas.height;
      const ctx = canvas.getContext("2d");
      const cssWidth = sourceCanvas.clientWidth;
      const cssHeight = sourceCanvas.clientHeight;
      ctx.setTransform(canvas.width/cssWidth, 0, 0,
                       canvas.height/cssHeight, 0, 0);
      ctx.drawImage(sourceCanvas, 0, 0, cssWidth, cssHeight);

      // MapLibre's station marker, legend and attribution are HTML elements.
      // Compose them over the same rendered map canvas for the exported PDF.
      const station = map.project(stationCoordinates);
      ctx.save();
      ctx.translate(station.x, station.y);
      ctx.fillStyle = "#c91f37";
      ctx.strokeStyle = "#ffffff";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(0, 1);
      ctx.lineTo(-10, -16);
      ctx.arc(0, -18, 10, Math.PI, 0, false);
      ctx.lineTo(10, -16);
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
      ctx.fillStyle = "#fff";
      ctx.beginPath(); ctx.arc(0, -18, 3, 0, Math.PI*2); ctx.fill();
      ctx.restore();

      const label = legendLabels[scaleSelect.value];
      const legendWidth = Math.min(300, cssWidth-24);
      const legendHeight = 91;
      const legendX = 14;
      const legendY = cssHeight-legendHeight-28;
      ctx.fillStyle = "rgba(255,255,255,0.94)";
      ctx.fillRect(legendX,legendY,legendWidth,legendHeight);
      ctx.fillStyle = "#17191d";
      ctx.font = "bold 12px Arial, sans-serif";
      ctx.fillText(label.title,legendX+10,legendY+17,legendWidth-20);
      const gradient = ctx.createLinearGradient(legendX+10,0,legendX+legendWidth-10,0);
      palette.forEach((color,index) => gradient.addColorStop(index/(palette.length-1),color));
      ctx.fillStyle = gradient;
      ctx.fillRect(legendX+10,legendY+25,legendWidth-20,13);
      ctx.fillStyle = "#34383e";
      ctx.font = "11px Arial, sans-serif";
      label.ticks.forEach((text,index) => {{
        const tickX = legendX+10+(legendWidth-20)*index/(label.ticks.length-1);
        ctx.textAlign = index === 0 ? "left" :
                        index === label.ticks.length-1 ? "right" : "center";
        ctx.fillText(text,tickX,legendY+52);
      }});
      ctx.textAlign = "left";
      ctx.fillText(label.contours,legendX+10,legendY+73,legendWidth-20);

      const copyright = "© OpenStreetMap contributors — openstreetmap.org/copyright";
      ctx.font = "11px Arial, sans-serif";
      const creditWidth = ctx.measureText(copyright).width+12;
      ctx.fillStyle = "rgba(255,255,255,0.88)";
      ctx.fillRect(cssWidth-creditWidth,cssHeight-19,creditWidth,19);
      ctx.fillStyle = "#17191d";
      ctx.fillText(copyright,cssWidth-creditWidth+6,cssHeight-6);
      return canvas;
    }}

    exportButton.addEventListener("click", async () => {{
      exportButton.disabled = true;
      exportStatus.textContent = {json.dumps(tr('Aguardando o mapa carregar…'))};
      try {{
        if (!map.loaded() || !map.areTilesLoaded()) {{
          await new Promise(resolve => map.once("idle",resolve));
        }}
        const screenshot = captureVisibleMap();
        const blob = await new Promise((resolve,reject) =>
          screenshot.toBlob(value => value ? resolve(value)
            : reject(new Error("PNG indisponível")), "image/png")
        );
        exportStatus.textContent = {json.dumps(tr('Gerando o PDF com mapa geográfico…'))};
        const response = await fetch("_export_coverage_pdf", {{
          method:"POST", headers:{{"Content-Type":"image/png"}}, body:blob
        }});
        if (!response.ok) throw new Error("HTTP " + response.status);
        const pdf = await response.blob();
        const url = URL.createObjectURL(pdf);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = "relatorio_cobertura_com_mapa.pdf";
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        setTimeout(() => URL.revokeObjectURL(url), 60000);
        exportStatus.textContent = {json.dumps(tr('PDF com mapa geográfico salvo e baixado.'))};
      }} catch (error) {{
        exportStatus.textContent = {json.dumps(tr('Não foi possível exportar o mapa: '))} + error.message;
      }} finally {{
        exportButton.disabled = false;
      }}
    }});
  </script>
</body>
</html>
"""


def _format_duration(seconds: float) -> str:
    value = max(0, round(seconds))
    hours, remainder = divmod(value, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours} h {minutes:02d} min {secs:02d} s"
    if minutes:
        return f"{minutes} min {secs:02d} s"
    return f"{secs} s"


def _local_point_to_lon_lat(
    request: CoverageRequest,
    east_km: float,
    north_km: float,
) -> list[float]:
    distance_m = math.hypot(east_km, north_km) * 1000.0
    bearing = (
        math.degrees(math.atan2(east_km, north_km)) + 360.0
    ) % 360.0
    latitude, longitude = destination_point(
        request.latitude_deg,
        request.longitude_deg,
        bearing,
        distance_m,
    )
    return [longitude, latitude]


def _coverage_bounds(request: CoverageRequest) -> list[list[float]]:
    radius = request.radius_km * 1000.0
    north_latitude, _ = destination_point(
        request.latitude_deg, request.longitude_deg, 0.0, radius
    )
    _, east_longitude = destination_point(
        request.latitude_deg, request.longitude_deg, 90.0, radius
    )
    south_latitude, _ = destination_point(
        request.latitude_deg, request.longitude_deg, 180.0, radius
    )
    _, west_longitude = destination_point(
        request.latitude_deg, request.longitude_deg, 270.0, radius
    )
    return [
        [west_longitude, south_latitude],
        [east_longitude, north_latitude],
    ]


def _notify(progress: ProgressCallback | None, message: str) -> None:
    if progress is not None:
        progress(message)


def _check_cancelled(cancel_check: Callable[[], bool] | None) -> None:
    if cancel_check is not None and cancel_check():
        raise InterruptedError("coverage report rendering cancelled")

