from __future__ import annotations

from .i18n import tr, html_language, map_locale

import html
import importlib.util
import json
import multiprocessing
import secrets
import threading
import webbrowser
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .desktop_core import bundle_root
from .report import MAPLIBRE_VERSION

CoordinateCallback = Callable[[float, float], None]


def _run_embedded_picker(title: str, url: str) -> None:
    """Run the map in a separate native WebView window."""
    import webview

    webview.create_window(
        title,
        url,
        width=1120,
        height=760,
        min_size=(800, 520),
        background_color="#11151a",
    )
    webview.start(debug=False)


def open_coordinate_picker(
    *,
    title: str,
    initial_latitude: float | None,
    initial_longitude: float | None,
    on_selected: CoordinateCallback,
) -> ThreadingHTTPServer:
    """Open a localhost MapLibre picker in an app window when available."""
    assets = bundle_root() / "map-assets"
    token = secrets.token_urlsafe(18)
    picker_process: multiprocessing.Process | None = None

    def stop_server() -> None:
        server.shutdown()
        server.server_close()
        if picker_process is not None and picker_process.is_alive():
            timer = threading.Timer(1.0, picker_process.terminate)
            timer.daemon = True
            timer.start()

    class PickerHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            parsed = urlparse(self.path)
            if parsed.path == "/":
                if parse_qs(parsed.query).get("token") != [token]:
                    self._send(403, "text/plain", b"Forbidden")
                    return
                body = build_picker_html(
                    title=title,
                    initial_latitude=initial_latitude,
                    initial_longitude=initial_longitude,
                    local_assets=assets.is_dir(),
                    selection_token=token,
                ).encode("utf-8")
                self._send(200, "text/html; charset=utf-8", body)
                return
            if parsed.path == "/maplibre-gl.js":
                self._send_asset(assets / "maplibre-gl.js", "text/javascript")
                return
            if parsed.path == "/maplibre-gl.css":
                self._send_asset(assets / "maplibre-gl.css", "text/css")
                return
            if parsed.path == "/select":
                try:
                    query = parse_qs(parsed.query)
                    if query.get("token") != [token]:
                        raise ValueError("invalid token")
                    latitude = float(query["lat"][0])
                    longitude = float(query["lon"][0])
                    if not -90.0 <= latitude <= 90.0:
                        raise ValueError('invalid latitude')
                    if not -180.0 <= longitude <= 180.0:
                        raise ValueError('invalid longitude')
                except (KeyError, IndexError, ValueError):
                    self._send(
                        400,
                        "text/plain; charset=utf-8",
                        tr('Coordenadas inválidas.').encode("utf-8"),
                    )
                    return
                self._send(
                    200,
                    "text/html; charset=utf-8",
                    (
                        "<!doctype html><meta charset='utf-8'>"
                        f"<title>{html.escape(tr('Local selecionado'))}</title>"
                        "<body style='font:18px Segoe UI;padding:40px'>"
                        f"<h2>{html.escape(tr('Local selecionado'))}</h2>"
                        f"<p>{html.escape(tr('As coordenadas foram enviadas ao Radio Link Planner. Esta janela será fechada automaticamente.'))}</p>"
                        "<script>setTimeout(() => window.close(), 350);</script>"
                        "</body>"
                    ).encode("utf-8"),
                )
                on_selected(latitude, longitude)
                threading.Thread(
                    target=stop_server,
                    daemon=True,
                ).start()
                return
            self._send(
                404,
                "text/plain; charset=utf-8",
                b"Not found",
            )

        def log_message(self, format: str, *args: object) -> None:
            return

        def _send_asset(self, path: Path, content_type: str) -> None:
            if not path.is_file():
                self._send(404, "text/plain", b"Not found")
                return
            self._send(200, content_type, path.read_bytes())

        def _send(self, status: int, content_type: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), PickerHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    timeout = threading.Timer(600.0, stop_server)
    timeout.daemon = True
    timeout.start()
    host, port = server.server_address
    url = f"http://{host}:{port}/?token={token}"
    display_mode = "browser"
    if importlib.util.find_spec("webview") is not None:
        try:
            picker_process = multiprocessing.get_context("spawn").Process(
                target=_run_embedded_picker,
                args=(title, url),
                daemon=True,
            )
            picker_process.start()
            display_mode = "embedded"
        except (OSError, RuntimeError):
            picker_process = None
    if display_mode == "browser":
        webbrowser.open(url)
    setattr(server, "display_mode", display_mode)
    setattr(server, "picker_process", picker_process)
    return server


def build_picker_html(
    *,
    title: str,
    initial_latitude: float | None,
    initial_longitude: float | None,
    local_assets: bool,
    selection_token: str = "test-token",
) -> str:
    latitude = initial_latitude if initial_latitude is not None else -15.0
    longitude = initial_longitude if initial_longitude is not None else -52.0
    zoom = 11 if initial_latitude is not None and initial_longitude is not None else 4
    if local_assets:
        map_css = "/maplibre-gl.css"
        map_js = "/maplibre-gl.js"
    else:
        map_css = (
            f"https://unpkg.com/maplibre-gl@{MAPLIBRE_VERSION}/"
            "dist/maplibre-gl.css"
        )
        map_js = (
            f"https://unpkg.com/maplibre-gl@{MAPLIBRE_VERSION}/"
            "dist/maplibre-gl.js"
        )
    return f"""<!doctype html>
<html lang="{html_language()}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{html.escape(title)}</title>
  <link rel="stylesheet" href="{map_css}">
  <style>
    html,body,#map {{ height:100%; margin:0; }}
    body {{ font-family:Segoe UI,Arial,sans-serif; }}
    .panel {{ position:absolute; z-index:3; left:18px; top:18px;
              width:min(390px,calc(100% - 36px)); background:#fff;
              padding:15px 17px; border-radius:9px;
              box-shadow:0 5px 22px rgba(0,0,0,.28); }}
    h1 {{ font-size:18px; margin:0 0 5px; }}
    p {{ color:#59616a; font-size:13px; margin:4px 0 11px; }}
    .coordinates {{ font:14px Consolas,monospace; background:#f1f3f5;
                    padding:8px; border-radius:5px; margin-bottom:10px; }}
    button {{ border:0; border-radius:5px; background:#c91f37; color:#fff;
              font-weight:600; padding:10px 14px; cursor:pointer; }}
    button:disabled {{ background:#8b8f95; cursor:not-allowed; }}
  </style>
</head>
<body>
  <div id="map"></div>
  <section class="panel">
    <h1>{html.escape(title)}</h1>
    <p>{html.escape(tr('Clique no mapa para posicionar o marcador e confirme o local.'))}</p>
    <div class="coordinates" id="coordinates">{html.escape(tr('Nenhum ponto selecionado'))}</div>
    <button id="confirm" disabled>{html.escape(tr('Usar este local'))}</button>
  </section>
  <script src="{map_js}"></script>
  <script>
    const map = new maplibregl.Map({{
      locale: {json.dumps(map_locale(), ensure_ascii=False)},
      container:"map",
      center:{json.dumps([longitude, latitude])},
      zoom:{zoom},
      style:{{
        version:8,
        sources:{{
          osm:{{
            type:"raster",
            tiles:["https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png"],
            tileSize:256,
            attribution:"© OpenStreetMap contributors"
          }}
        }},
        layers:[{{id:"osm",type:"raster",source:"osm"}}]
      }}
    }});
    map.addControl(new maplibregl.NavigationControl(),"top-right");
    let marker = null;
    let selected = null;
    map.on("click", event => {{
      selected = event.lngLat;
      if (!marker) marker = new maplibregl.Marker({{color:"#c91f37"}})
        .setLngLat(selected).addTo(map);
      else marker.setLngLat(selected);
      document.getElementById("coordinates").textContent =
        selected.lat.toFixed(8) + ", " + selected.lng.toFixed(8);
      document.getElementById("confirm").disabled = false;
    }});
    document.getElementById("confirm").addEventListener("click", () => {{
      if (!selected) return;
      window.location.href = "/select?lat=" +
        encodeURIComponent(selected.lat) + "&lon=" +
        encodeURIComponent(selected.lng) + "&token=" +
        encodeURIComponent({json.dumps(selection_token)});
    }});
  </script>
</body>
</html>
"""

