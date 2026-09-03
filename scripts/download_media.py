#!/usr/bin/env python3
"""Baixador de mídia (Instagram Reels/Posts, X/Twitter, YouTube).

Permite que o Hermes ou o operador baixe vídeos e clipes diretamente via CLI
ou importe como módulo Python, usando o yt-dlp disponível no ambiente.

Uso:
  python -m scripts.download_media --url "https://www.instagram.com/reel/DczgElQso4z/"
  python -m scripts.download_media --url "https://x.com/username/status/12345" --output "output/videos/"
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


def find_ytdlp() -> str:
    """Localiza o executável yt-dlp no ambiente atual, PATH ou diretórios padrões."""
    # 1. No mesmo diretório do Python em execução (venv)
    venv_bin = Path(sys.executable).parent
    for name in ("yt-dlp.exe", "yt-dlp"):
        cand = venv_bin / name
        if cand.exists():
            return str(cand)

    # 2. No PATH do sistema
    cand = shutil.which("yt-dlp")
    if cand:
        return cand

    # 3. Locais comuns no Linux/Servidor
    for p in ("/home/osmar/.local/bin/yt-dlp", "/usr/local/bin/yt-dlp", "/usr/bin/yt-dlp"):
        if Path(p).exists():
            return p

    return "yt-dlp"


def download_media(url: str, output_dir: Path | str = "output/videos", filename_template: str | None = None) -> dict:
    """Baixa mídia de URL pública compatível com yt-dlp (Instagram, X, YouTube, etc.).

    Args:
        url: Link do vídeo ou post.
        output_dir: Diretório de destino.
        filename_template: Template de saída do yt-dlp (opcional).

    Returns:
        dict com status, caminho do arquivo baixado e metadados.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    template = filename_template or "%(extractor)s_%(id)s_%(title).50B.%(ext)s"
    output_path_tpl = str(out_dir / template)

    ytdlp = find_ytdlp()
    cmd = [
        ytdlp,
        "-f", "bv*[height<=1080]+ba/b[height<=1080]/b",
        "--merge-output-format", "mp4",
        "--no-playlist",
        "--no-warnings",
        "--print-json",
        "-o", output_path_tpl,
        url,
    ]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except Exception as exc:
        return {"ok": False, "error": str(exc), "url": url}

    if proc.returncode != 0:
        return {
            "ok": False,
            "error": proc.stderr.strip() or "Falha ao baixar mídia",
            "url": url,
        }

    meta = {}
    downloaded_file = None
    # yt-dlp com --print-json imprime metadados no stdout
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                meta = json.loads(line)
                downloaded_file = meta.get("_filename")
                break
            except Exception:
                pass

    if not downloaded_file:
        # Se não capturou via JSON, pega o arquivo mais recente criado no output_dir
        candidates = list(out_dir.glob("*.*"))
        if candidates:
            candidates.sort(key=lambda f: f.stat().st_mtime, reverse=True)
            downloaded_file = str(candidates[0])

    return {
        "ok": True,
        "url": url,
        "file": downloaded_file,
        "title": meta.get("title"),
        "uploader": meta.get("uploader"),
        "duration": meta.get("duration"),
    }


def main():
    parser = argparse.ArgumentParser(description="Baixador de vídeos do Instagram, X e YouTube via yt-dlp")
    parser.add_argument("--url", required=True, help="URL da mídia (Instagram, X, etc.)")
    parser.add_argument("--output", default="output/videos", help="Diretório de saída (padrão: output/videos)")
    parser.add_argument("--json", action="store_true", help="Saída em formato JSON")
    args = parser.parse_args()

    result = download_media(args.url, output_dir=args.output)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result.get("ok"):
            print(f"✅ Vídeo baixado com sucesso: {result.get('file')}")
            if result.get("title"):
                print(f"   Título: {result.get('title')}")
        else:
            print(f"❌ Erro ao baixar vídeo: {result.get('error')}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
