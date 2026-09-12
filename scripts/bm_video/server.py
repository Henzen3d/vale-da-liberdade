"""HTTP local do mockup-browser (ThreadingHTTPServer)."""
from __future__ import annotations

import socket
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class _Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, directories=None, **k):
        self._directories = directories or []
        super().__init__(*a, **k)

    def translate_path(self, path: str) -> str:
        rel = path.split("?", 1)[0].lstrip("/")
        for base in self._directories:
            cand = (base / rel).resolve()
            try:
                cand.relative_to(base.resolve())
            except ValueError:
                continue
            if cand.is_file():
                return str(cand)
            if cand.is_dir():
                index = cand / "index.html"
                if index.exists():
                    return str(index)
        return str((self._directories[0] / "missing").resolve())

    def log_message(self, format, *args):
        return


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_server(directories: list[Path]) -> tuple[ThreadingHTTPServer, int]:
    port = _free_port()

    def factory(*a, **k):
        return _Handler(*a, directories=directories, **k)

    httpd = ThreadingHTTPServer(("127.0.0.1", port), factory)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd, port
