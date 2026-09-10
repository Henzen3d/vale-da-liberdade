#!/usr/bin/env python3
"""Valida o arquivo Netscape de cookies do YouTube usado pelo pipeline BM.

Uso:
    python3 scripts/yt_cookies_check.py [caminho] [--video-id ID]

Sem argumentos usa credentials/youtube_cookies.txt e testa contra um vídeo do
canal. Sai com 0 = ok, 1 = problema (e diz qual).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

DEFAULT_PATH = PROJECT_ROOT / "credentials" / "youtube_cookies.txt"
DEFAULT_VIDEO = "C2ad_B39L_c"

# Cookies que só existem numa sessão realmente logada.
SESSION_COOKIES = (
    "SID",
    "HSID",
    "SSID",
    "APISID",
    "SAPISID",
    "__Secure-1PSID",
    "__Secure-3PSID",
    "LOGIN_INFO",
)


def read_cookie_names(path: Path) -> tuple[set[str], int, list[str]]:
    """Retorna (nomes de cookie, total de linhas válidas, domínios vistos)."""
    names: set[str] = set()
    domains: list[str] = []
    total = 0
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        dom, _, _, _, _, name, _ = parts[:7]
        total += 1
        names.add(name.strip())
        if dom.strip() not in domains:
            domains.append(dom.strip())
    return names, total, domains


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("path", nargs="?", default=str(DEFAULT_PATH))
    ap.add_argument("--video-id", default=DEFAULT_VIDEO)
    args = ap.parse_args()

    path = Path(args.path).expanduser()
    print(f"arquivo: {path}")

    if not path.is_file():
        print("❌ não existe. Exporte do navegador logado (ver skill web-jornal-production).")
        return 1

    size = path.stat().st_size
    print(f"tamanho: {size} bytes")
    if size < 80:
        print("❌ pequeno demais — export vazio ou truncado.")
        return 1

    head = path.read_text(encoding="utf-8", errors="replace")[:120]
    if "Netscape" not in head and "\t" not in head:
        print("❌ não parece o formato Netscape (cabeçalho ausente).")
        print("   Exporte como 'Netscape' / cookies.txt, não JSON.")
        return 1

    names, total, domains = read_cookie_names(path)
    print(f"linhas válidas: {total} | domínios: {', '.join(domains[:4]) or '-'}")

    missing = [c for c in SESSION_COOKIES if c not in names]
    present = [c for c in SESSION_COOKIES if c in names]
    print(f"cookies de sessão presentes: {len(present)}/{len(SESSION_COOKIES)}")
    if missing:
        print(f"⚠️  ausentes: {', '.join(missing)}")

    if "LOGIN_INFO" not in names or len(present) < 2:
        print("❌ a sessão NÃO está logada. Faça login no YouTube ANTES de exportar.")
        return 1
    print("✅ sessão autenticada detectada no arquivo.")

    print(f"\n▶ teste ao vivo (yt-dlp) no vídeo {args.video_id}...")
    from bm_transcript import _yt_dlp_cmd, ytdlp_is_bot_block  # noqa: PLC0415

    cmd = _yt_dlp_cmd(
        "--cookies", str(path),
        "--skip-download", "--print", "%(id)s|%(title).60s",
        f"https://www.youtube.com/watch?v={args.video_id}",
    )
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=180)
    out = (r.stdout or "").strip()
    err = (r.stderr or "").strip()

    if r.returncode == 0 and out:
        print(f"✅ FUNCIONOU: {out.splitlines()[-1]}")
        print("   Reinicie/copie via cron: nada mais a fazer — o pipeline pega o arquivo sozinho.")
        return 0

    if ytdlp_is_bot_block(err):
        print("❌ ainda bloqueado (Sign in to confirm you're not a bot).")
        print("   Causas prováveis: conta usada não é a logada, cookies velhos,")
        print("   ou export feito do google.com em vez de youtube.com.")
        print(f"   stderr: {err.splitlines()[-1][:200] if err else '-'}")
        return 1

    print(f"❌ yt-dlp falhou (exit {r.returncode}): {(err or out)[-400:]}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
