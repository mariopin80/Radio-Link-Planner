from __future__ import annotations

import mimetypes
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

DEFAULT_REPORT_SERVER_TIMEOUT_SECONDS = 60 * 60


def start_report_server(
    report_path: str | Path,
    *,
    timeout_seconds: float = DEFAULT_REPORT_SERVER_TIMEOUT_SECONDS,
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

        def log_message(self, format: str, *args: object) -> None:
            return

        def _send_error(self, status: int, body: bytes) -> None:
            self._send(status, "text/plain; charset=utf-8", body)

        def _send(self, status: int, content_type: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "private, max-age=60")
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
) -> ThreadingHTTPServer:
    """Open a generated report through localhost instead of ``file://``."""
    server, report_url = start_report_server(
        report_path,
        timeout_seconds=timeout_seconds,
    )
    webbrowser.open(report_url)
    return server
