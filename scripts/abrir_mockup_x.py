#!/usr/bin/env python3
"""Abre a demonstração interativa dos Mockups do X no navegador local."""
from __future__ import annotations

import sys
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
MOCKUP_DIR = ROOT / "references" / "youtube" / "mockup-browser"


class _MultiDirHandler(SimpleHTTPRequestHandler):
    directories = [MOCKUP_DIR, ROOT]

    def translate_path(self, path: str) -> str:
        rel = path.split("?", 1)[0].lstrip("/")
        for base in self.directories:
            cand = (base / rel).resolve()
            try:
                cand.relative_to(base.resolve())
            except ValueError:
                continue
            if cand.is_file():
                return str(cand)
            if cand.is_dir():
                for idx in ("demo-mockup-x-showcase.html", "index.html"):
                    target = cand / idx
                    if target.exists():
                        return str(target)
        return str((self.directories[0] / rel).resolve())

    def log_message(self, format, *args):
        return


def main():
    port = 8769
    httpd = None
    for p in range(port, port + 20):
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", p), _MultiDirHandler)
            port = p
            break
        except OSError:
            continue

    if not httpd:
        print("❌ Não foi possível encontrar uma porta livre para o servidor local.")
        sys.exit(1)

    url = f"http://127.0.0.1:{port}/demo-mockup-x-showcase.html"
    print("\n" + "=" * 68)
    print("🎬 VALE DA LIBERDADE • AVALIADOR DE MOCKUPS DO X (3 MODELOS)")
    print("=" * 68)
    print(f"🔗 Servidor ativo em: {url}")
    print("🚀 Abrindo no seu navegador padrão...")
    print("⌨️  Pressione Ctrl+C para encerrar o servidor quando terminar.\n")

    webbrowser.open(url)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Servidor encerrado com sucesso.")
        httpd.server_close()


if __name__ == "__main__":
    main()
