from __future__ import annotations

import html
import json
import math
import os
import tempfile
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
from .report import _install_map_assets

_MATPLOTLIB_CACHE = Path(tempfile.gettempdir()) / "radio-link-planner-matplotlib"
_MATPLOTLIB_CACHE.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_MATPLOTLIB_CACHE))
os.environ.setdefault("MPLBACKEND", "Agg")


def write_coverage_outputs(
    *,
    request: CoverageRequest,
    radials: tuple[RadialCoverage, ...],
    grid: np.ndarray,
    grid_metadata: dict[str, Any],
    output_directory: Path,
    progress: ProgressCallback | None = None,
) -> tuple[dict[str, Path], dict[str, Any]]:
    output_directory.mkdir(parents=True, exist_ok=True)
    overlay_path = output_directory / "coverage_overlay.png"
    heatmap_path = output_directory / "coverage_heatmap.png"
    contours_path = output_directory / "coverage_contours.geojson"
    report_path = output_directory / "coverage_report.html"

    _notify(progress, "Cobertura: renderizando escala de cores…")
    sampled, axis_km = _sample_grid_for_rendering(
        grid,
        request.radius_km,
        request.resolution_m,
    )
    overlay_tiles = _render_overlay(
        request,
        sampled,
        axis_km,
        overlay_path,
    )
    contour_geojson = _render_heatmap_and_contours(
        request,
        sampled,
        axis_km,
        heatmap_path,
    )
    contours_path.write_text(
        json.dumps(contour_geojson, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    map_assets = _install_map_assets(output_directory)
    statistics = _coverage_statistics(grid)
    report_path.write_text(
        _build_coverage_report(
            request=request,
            radials=radials,
            statistics=statistics,
            grid_metadata=grid_metadata,
            contour_geojson=contour_geojson,
            overlay_tiles=overlay_tiles,
            map_assets=map_assets,
        ),
        encoding="utf-8",
    )
    return (
        {
            "report_html": report_path,
            "heatmap": heatmap_path,
            "map_overlay": overlay_path,
            "contours": contours_path,
        },
        statistics,
    )


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
) -> list[dict[str, Any]]:
    import matplotlib.pyplot as plt
    from matplotlib.colors import Normalize

    colormap = _coverage_colormap()
    normalization = Normalize(vmin=-12.0, vmax=18.0, clip=True)
    rgba = colormap(normalization(np.nan_to_num(grid, nan=-12.0)))
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
            filename = f"coverage_overlay_r{row}_c{column}.png"
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
        linewidths=(1.5, 1.25, 1.25, 1.4),
    )
    axis.clabel(contours, fmt=lambda value: f"{value:+.0f} dB", fontsize=8)
    axis.scatter(
        [0.0],
        [0.0],
        marker="^",
        s=90,
        color="#111111",
        edgecolor="#ffffff",
        linewidth=1.1,
        zorder=10,
        label="Transmissor",
    )
    axis.set_title(
        f"{request.name} — {request.frequency_mhz:.3f} MHz",
        loc="left",
        fontsize=15,
        fontweight="bold",
    )
    axis.set_xlabel("Deslocamento leste–oeste (km)")
    axis.set_ylabel("Deslocamento norte–sul (km)")
    axis.set_aspect("equal")
    axis.grid(True, color="#ffffff", alpha=0.15)
    colorbar = figure.colorbar(image, ax=axis, shrink=0.86, pad=0.025)
    colorbar.set_label("Margem do enlace (dB)")
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
    radials: tuple[RadialCoverage, ...],
    statistics: dict[str, Any],
    grid_metadata: dict[str, Any],
    contour_geojson: dict[str, Any],
    overlay_tiles: list[dict[str, Any]],
    map_assets: tuple[str, str],
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
    evaluated = sum(item.evaluated_point_count for item in radials)
    raster_cells = grid_metadata["valid_circle_cells"]
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="referrer" content="strict-origin-when-cross-origin">
  <title>{html.escape(request.name)} — Radio Link Planner</title>
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
    <div class="eyebrow">Radio Link Planner · cobertura adaptativa</div>
    <h1>{html.escape(request.name)}</h1>
    <div>{request.frequency_mhz:.3f} MHz · P.1812 a
         {request.time_percentage:.0f}% do tempo · raio {request.radius_km} km</div>
  </header>
  <main>
    <section class="card map-wrap">
      <div id="coverage-map" aria-label="Mapa de cobertura"></div>
      <div class="legend">
        <strong>Margem do enlace</strong>
        <div class="legend-gradient"></div>
        <div class="legend-ticks"><span>−12</span><span>0</span>
          <span>+6</span><span>+12</span><span>+18 dB</span></div>
        <div style="margin-top:7px">Contornos: 0, +3, +6 e +12 dB</div>
      </div>
    </section>
    <section class="card">
      <div class="stats">
        <div class="stat"><span>Área com margem ≥ 0 dB</span>
          <strong>{statistics["covered_percent"]:.1f}%</strong></div>
        <div class="stat"><span>Margem ≥ +3 dB</span>
          <strong>{statistics["margin_3_db_percent"]:.1f}%</strong></div>
        <div class="stat"><span>Margem ≥ +6 dB</span>
          <strong>{statistics["margin_6_db_percent"]:.1f}%</strong></div>
        <div class="stat"><span>Margem ≥ +12 dB</span>
          <strong>{statistics["margin_12_db_percent"]:.1f}%</strong></div>
      </div>
    </section>
    <section class="card">
      <h2>Rastreabilidade do cálculo</h2>
      <table>
        <tr><th>Modelo</th><td>ITU-R P.1812-8</td></tr>
        <tr><th>Resolução visual</th><td>{request.resolution_m} m</td></tr>
        <tr><th>Perfis radiais calculados</th><td>{len(radials)}</td></tr>
        <tr><th>Pontos avaliados fisicamente</th><td>{evaluated:,}</td></tr>
        <tr><th>Células do raster final</th><td>{raster_cells:,}</td></tr>
        <tr><th>Relevo</th><td>Copernicus GLO-30</td></tr>
      </table>
      <p class="note">O raster é interpolado entre perfis radiais adaptativos.
      A resolução visual não significa que uma execução independente da P.1812
      tenha sido feita em cada célula. O refinamento aumenta onde o relevo,
      a margem ou a borda de cobertura variam rapidamente.</p>
      <p class="note">Vegetação, edificações e ruído local ainda não estão
      representados nesta versão; áreas urbanas e florestais devem ser
      interpretadas com essa limitação.</p>
    </section>
    <section class="card">
      <img src="coverage_heatmap.png" alt="Mapa técnico de cobertura"
           style="width:100%;height:auto;display:block">
    </section>
  </main>
  <script src="{html.escape(map_js, quote=True)}"></script>
  <script>
    const overlayTiles = {embedded_overlay_tiles};
    const coverageBounds = {json.dumps(bounds)};
    const contourData = {embedded_contours};
    const map = new maplibregl.Map({{
      container: "coverage-map",
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
        layers: [{{ id:"osm", type:"raster", source:"osm" }}]
      }}
    }});
    map.fitBounds(coverageBounds, {{padding:45,duration:0}});
    map.addControl(new maplibregl.NavigationControl(), "top-right");
    map.on("load", () => {{
      overlayTiles.forEach((tile,index) => {{
        const sourceId = "coverage-" + index;
        map.addSource(sourceId, {{
          type:"image", url:tile.url, coordinates:tile.coordinates
        }});
        map.addLayer({{
          id:"coverage-image-" + index, type:"raster", source:sourceId,
          paint:{{"raster-opacity":0.78,"raster-resampling":"linear"}}
        }});
      }});
      map.addSource("contours", {{type:"geojson", data:contourData}});
      map.addLayer({{
        id:"contour-lines", type:"line", source:"contours",
        paint:{{
          "line-color":[
            "match",["get","level_db"],
            0,"#7a0012",3,"#8a5a00",6,"#1d551f",12,"#08384f","#111"
          ],
          "line-width":2.0,
          "line-opacity":0.95
        }}
      }});
      map.addLayer({{
        id:"contour-labels", type:"symbol", source:"contours",
        layout:{{
          "symbol-placement":"line",
          "text-field":["get","label"],
          "text-size":11,
          "text-allow-overlap":false
        }},
        paint:{{
          "text-color":"#111",
          "text-halo-color":"#fff",
          "text-halo-width":1.4
        }}
      }});
      new maplibregl.Marker({{color:"#c91f37"}})
        .setLngLat([{request.longitude_deg},{request.latitude_deg}])
        .setPopup(new maplibregl.Popup().setText("Transmissor"))
        .addTo(map);
    }});
  </script>
</body>
</html>
"""


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
