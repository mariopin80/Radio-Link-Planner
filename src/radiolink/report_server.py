from __future__ import annotations

import mimetypes
import io
import secrets
import threading
import webbrowser
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

from PIL import Image, UnidentifiedImageError

DEFAULT_REPORT_SERVER_TIMEOUT_SECONDS = 60 * 60
MAX_SCREENSHOT_BYTES = 20 * 1024 * 1024


def start_report_server(
    report_path: str | Path,
    *,
    timeout_seconds: float = DEFAULT_REPORT_SERVER_TIMEOUT_SECONDS,
    on_export_coverage_pdf: Callable[[bytes], Path] | None = None,
) -> tuple[ThreadingHTTPServer, str]:
    """Serve one report directory on localhost and return its private URL."""
    report = Path(report_path).expanduser().resolve()
    if not report.is_file():
        raise FileNotFoundError(f"relatório não encontrado: {report}")
    if timeout_seconds <= 0:
        raise ValueError("report server timeout must be positive")

    root = report.parent
    token = secrets.token_urlsafe(24)
    prefix = f"/{token}/"
    export_lock = threading.Lock()

    class ReportHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            parsed = urlparse(self.path)
            if not parsed.path.startswith(prefix):
                self._send_error(403, b"Forbidden")
                return
            relative_text = unquote(parsed.path[len(prefix) :])
            candidate = (root / relative_text).resolve()
            try:
                candidate.relative_to(root)
            except ValueError:
                self._send_error(403, b"Forbidden")
                return
            if not candidate.is_file():
                self._send_error(404, b"Not found")
                return
            content_type = (
                mimetypes.guess_type(candidate.name)[0]
                or "application/octet-stream"
            )
            self._send(200, content_type, candidate.read_bytes())

        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            if (
                urlparse(self.path).path != prefix + "_export_coverage_pdf"
                or on_export_coverage_pdf is None
            ):
                self._send_error(404, b"Not found")
                return
            host, port = self.server.server_address
            expected_origin = f"http://{host}:{port}"
            if (
                self.headers.get("Origin") != expected_origin
                or self.headers.get("Host") != f"{host}:{port}"
            ):
                self._send_error(403, b"Forbidden")
                return
            if self.headers.get("Content-Type", "").split(";", 1)[0].lower() != "image/png":
                self._send_error(415, b"Only PNG images are accepted")
                return
            try:
                content_length = int(self.headers.get("Content-Length", ""))
            except (TypeError, ValueError):
                self._send_error(411, b"Content-Length required")
                return
            if not 0 < content_length <= MAX_SCREENSHOT_BYTES:
                self._send_error(413, b"Screenshot is too large or empty")
                return

            screenshot = self.rfile.read(content_length)
            try:
                with Image.open(io.BytesIO(screenshot)) as picture:
                    width, height = picture.size
                    if picture.format != "PNG" or not (
                        320 <= width <= 8000 and 240 <= height <= 8000
                    ):
                        raise ValueError("invalid screenshot dimensions")
                    picture.verify()
            except (UnidentifiedImageError, OSError, ValueError):
                self._send_error(422, b"Invalid PNG screenshot")
                return

            try:
                with export_lock:
                    pdf_path = on_export_coverage_pdf(screenshot)
                    pdf_bytes = Path(pdf_path).read_bytes()
            except (OSError, ValueError):
                self._send_error(500, b"Could not create coverage PDF")
                return
            if not pdf_bytes.startswith(b"%PDF-"):
                self._send_error(500, b"Invalid generated PDF")
                return
            self._send(
                200, "application/pdf", pdf_bytes,
                attachment="relatorio_cobertura_com_mapa.pdf",
            )

        def log_message(self, format: str, *args: object) -> None:
            return

        def _send_error(self, status: int, body: bytes) -> None:
            self._send(status, "text/plain; charset=utf-8", body)

        def _send(
            self, status: int, content_type: str, body: bytes,
            *, attachment: str | None = None,
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store" if attachment else "private, max-age=60")
            if attachment:
                self.send_header("Content-Disposition", f'attachment; filename="{attachment}"')
            self.send_header(
                "Referrer-Policy",
                "strict-origin-when-cross-origin",
            )
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), ReportHandler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def stop_server() -> None:
        server.shutdown()
        server.server_close()

    timeout = threading.Timer(timeout_seconds, stop_server)
    timeout.daemon = True
    timeout.start()
    host, port = server.server_address
    report_url = (
        f"http://{host}:{port}{prefix}"
        f"{quote(report.name, safe='')}"
    )
    return server, report_url


def open_report_in_browser(
    report_path: str | Path,
    *,
    timeout_seconds: float = DEFAULT_REPORT_SERVER_TIMEOUT_SECONDS,
    on_export_coverage_pdf: Callable[[bytes], Path] | None = None,
) -> ThreadingHTTPServer:
    """Open a generated report through localhost instead of ``file://``."""
    server, report_url = start_report_server(
        report_path,
        timeout_seconds=timeout_seconds,
        on_export_coverage_pdf=on_export_coverage_pdf,
    )
    webbrowser.open(report_url)
    return server
