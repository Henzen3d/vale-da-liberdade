#!/usr/bin/env python3
"""
Extrator de transcrição YouTube via yt-dlp — Pipeline Brasil e Mundo.

Extrai legendas (automáticas ou manuais) de vídeos do YouTube usando yt-dlp.
Faz fallback para download de áudio + STT local (Whisper) se não houver legenda.
Salva transcrição limpa + metadata em output/brasil_e_mundo/raw/{video_id}.json.

Uso:
    python scripts/bm_transcript.py --url "https://youtube.com/watch?v=XXXXX"
    python scripts/bm_transcript.py --video-id "XXXXX"
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
import urllib.error
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
OUTPUT_DIR = PROJECT_ROOT / "output" / "brasil_e_mundo" / "raw"

# Garante que o binário `yt-dlp` seja encontrável mesmo sob o PATH mínimo do cron.
# yt-dlp costuma residir em ~/.local/bin (instalação pip --user). Sem isto, o
# subprocess lança [Errno 2] No such file or directory: 'yt-dlp' e toda a fila BM
# falha em "Extração de transcrição (yt-dlp)".
_LOCAL_BIN = str(Path.home() / ".local" / "bin")
if _LOCAL_BIN not in os.environ.get("PATH", ""):
    os.environ["PATH"] = _LOCAL_BIN + os.pathsep + os.environ.get("PATH", "")


def extract_video_id(url: str) -> str | None:
    """Extrai video_id de vários formatos de URL do YouTube."""
    patterns = [
        r"(?:youtube\.com/watch\?.*v=|youtu\.be/|youtube\.com/embed/|youtube\.com/v/)"
        r"([a-zA-Z0-9_-]{11})",
        r"^([a-zA-Z0-9_-]{11})$",
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None


def get_video_metadata(url: str) -> dict:
    """Usa yt-dlp --dump-json para obter metadata do vídeo."""
    try:
        result = subprocess.run(
            ["yt-dlp", "--dump-json", "--no-download", url],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
        )
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout.strip())
            return {
                "title": data.get("title", ""),
                "channel": data.get("channel", data.get("uploader", "")),
                "duration_s": data.get("duration", 0),
                "published": data.get("upload_date", ""),
                "description": data.get("description", ""),
                "view_count": data.get("view_count", 0),
                "like_count": data.get("like_count", 0),
            }
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError) as e:
        print(f"⚠️  Falha ao obter metadata: {e}")
    return {}


def extract_source_urls(description: str) -> list[str]:
    """Extrai URLs de fontes da descrição do vídeo."""
    if not description:
        return []
    # Capturar URLs, excluindo links do próprio YouTube/redes sociais
    url_pattern = r"https?://[^\s<>\"')\]]+(?<![.,;:!?)])"
    urls = re.findall(url_pattern, description)
    exclude_domains = {
        "youtube.com", "youtu.be", "twitter.com", "x.com",
        "instagram.com", "facebook.com", "t.me", "telegram.me",
        "bit.ly", "tinyurl.com", "goo.gl", "amzn.to",
        "rumble.com", "odysee.com",
    }
    filtered = []
    for url in urls:
        domain = re.search(r"https?://(?:www\.)?([^/]+)", url)
        if domain and not any(ex in domain.group(1) for ex in exclude_domains):
            filtered.append(url)
    return filtered[:10]  # Limitar a 10 fontes


def fetch_source_name(url: str) -> str:
    """Best-effort: tenta capturar o nome do veículo via <title> da página."""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (WebjornalBot/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read(8192).decode("utf-8", errors="ignore")
            match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I)
            if match:
                title = match.group(1).strip()
                # Tentar extrair nome do veículo do título
                # Ex: "Notícia tal - Gazeta do Povo" → "Gazeta do Povo"
                parts = re.split(r"\s*[|—–-]\s*", title)
                if len(parts) >= 2:
                    return parts[-1].strip()[:60]
                return title[:60]
    except Exception:
        pass
    return ""


def download_subtitles(url: str, work_dir: Path) -> str | None:
    """Baixa legendas via yt-dlp. Retorna caminho do arquivo .srt ou None."""
    # Tentar legendas em português (manual → automática)
    for lang in ["pt", "pt-BR", "pt-PT"]:
        for sub_type in ["--write-sub", "--write-auto-sub"]:
            cmd = [
                "yt-dlp",
                sub_type,
                "--sub-lang", lang,
                "--skip-download",
                "--convert-subs", "srt",
                "-o", str(work_dir / "%(id)s.%(ext)s"),
                url,
            ]
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, encoding="utf-8", timeout=120
                )
                # Procurar arquivo .srt gerado
                for f in work_dir.iterdir():
                    if f.suffix == ".srt" and f.stat().st_size > 100:
                        return str(f)
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue

    # Fallback: qualquer idioma disponível
    cmd = [
        "yt-dlp",
        "--write-auto-sub",
        "--skip-download",
        "--convert-subs", "srt",
        "-o", str(work_dir / "%(id)s.%(ext)s"),
        url,
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=120)
        for f in work_dir.iterdir():
            if f.suffix == ".srt" and f.stat().st_size > 100:
                return str(f)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return None


def parse_srt(srt_path: str) -> str:
    """Converte .srt em texto limpo (remove timestamps e numeração)."""
    text = Path(srt_path).read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    clean = []
    prev_line = ""

    for line in lines:
        line = line.strip()
        # Pular numeração de sequência
        if re.match(r"^\d+$", line):
            continue
        # Pular timestamps (00:00:01,234 --> 00:00:04,567)
        if re.match(r"\d{2}:\d{2}:\d{2}[,.]", line):
            continue
        # Pular linhas vazias
        if not line:
            continue
        # Remover tags HTML de formatação de legenda
        line = re.sub(r"<[^>]+>", "", line)
        # Deduplicar linhas consecutivas (legendas automáticas repetem)
        if line != prev_line:
            clean.append(line)
            prev_line = line

    return " ".join(clean)


def download_audio_for_stt(url: str, work_dir: Path) -> str | None:
    """Baixa apenas o áudio para STT fallback."""
    out_template = str(work_dir / "audio.%(ext)s")
    cmd = [
        "yt-dlp",
        "-x",
        "--audio-format", "mp3",
        "--audio-quality", "5",  # qualidade média (suficiente para STT)
        "-o", out_template,
        url,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=300)
        if result.returncode == 0:
            for f in work_dir.iterdir():
                if f.suffix in (".mp3", ".m4a", ".wav", ".opus"):
                    return str(f)
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"⚠️  Falha ao baixar áudio: {e}")
    return None


def transcribe_audio_whisper(audio_path: str) -> str | None:
    """Transcreve áudio via Whisper (faster-whisper ou whisper.cpp)."""
    # Tentar faster-whisper (Python)
    try:
        from faster_whisper import WhisperModel
        print("   🎙️ Transcrevendo com faster-whisper (modelo small)...")
        model = WhisperModel("small", device="cpu", compute_type="int8")
        segments, _info = model.transcribe(audio_path, language="pt")
        texts = [seg.text for seg in segments]
        return " ".join(texts)
    except ImportError:
        pass

    # Tentar whisper CLI
    try:
        result = subprocess.run(
            ["whisper", audio_path, "--language", "pt", "--output_format", "txt"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=600,
        )
        txt_path = Path(audio_path).with_suffix(".txt")
        if txt_path.exists():
            return txt_path.read_text(encoding="utf-8").strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    print("   ⚠️  Nenhum backend STT disponível (faster-whisper / whisper)")
    return None


def extract_transcript(url: str, video_id: str) -> dict | None:
    """
    Pipeline completo de extração:
    1. Metadata via yt-dlp --dump-json
    2. Legendas via yt-dlp (pt → auto → qualquer)
    3. Fallback: áudio + Whisper STT
    4. Extração de fontes da descrição
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{video_id}.json"

    # Verificar se já extraído
    if out_path.exists():
        existing = json.loads(out_path.read_text(encoding="utf-8"))
        if existing.get("transcript") and len(existing["transcript"]) > 100:
            print(f"   ℹ️  Transcrição já existe: {out_path}")
            return existing

    print(f"📝 Extraindo transcrição de {video_id}...")

    # 1. Metadata
    print("   📊 Obtendo metadata...")
    meta = get_video_metadata(url)
    if not meta:
        meta = {"title": "", "channel": "", "duration_s": 0, "description": ""}

    # 2. Legendas
    transcript_text = None
    with tempfile.TemporaryDirectory(prefix="bm_transcript_") as tmpdir:
        work_dir = Path(tmpdir)
        print("   📄 Baixando legendas...")
        srt_path = download_subtitles(url, work_dir)

        if srt_path:
            transcript_text = parse_srt(srt_path)
            print(f"   ✅ Legenda extraída ({len(transcript_text.split())} palavras)")
        else:
            # 3. Fallback STT
            print("   ⚠️  Sem legendas disponíveis, tentando fallback STT...")
            audio_path = download_audio_for_stt(url, work_dir)
            if audio_path:
                transcript_text = transcribe_audio_whisper(audio_path)
                if transcript_text:
                    print(
                        f"   ✅ STT concluído ({len(transcript_text.split())} palavras)"
                    )

    if not transcript_text or len(transcript_text.split()) < 20:
        print(f"   ❌ Falha: transcrição vazia ou muito curta")
        return None

    # 4. Fontes da descrição
    source_urls = extract_source_urls(meta.get("description", ""))
    source_names = []
    for src_url in source_urls[:5]:  # Limitar a 5 para não travar
        name = fetch_source_name(src_url)
        if name:
            source_names.append(name)
            print(f"   📰 Fonte: {name}")

    # Montar resultado
    result = {
        "video_id": video_id,
        "title": meta.get("title", ""),
        "channel": meta.get("channel", ""),
        "url": url,
        "duration_s": meta.get("duration_s", 0),
        "published": meta.get("published", ""),
        "description": meta.get("description", "")[:2000],
        "transcript": transcript_text,
        "transcript_words": len(transcript_text.split()),
        "source_urls": source_urls,
        "source_names": list(set(source_names)),
        "extracted_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(),
    }

    # Salvar
    out_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"   💾 Salvo: {out_path}")

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Extrator de transcrição YouTube — Brasil e Mundo"
    )
    parser.add_argument("--url", help="URL do vídeo do YouTube")
    parser.add_argument("--video-id", help="ID do vídeo (alternativa à URL)")
    args = parser.parse_args()

    if args.url:
        video_id = extract_video_id(args.url)
        url = args.url
    elif args.video_id:
        video_id = args.video_id
        url = f"https://www.youtube.com/watch?v={video_id}"
    else:
        print("ERRO: forneça --url ou --video-id")
        sys.exit(1)

    if not video_id:
        print(f"❌ Não foi possível extrair video_id de: {args.url}")
        sys.exit(1)

    result = extract_transcript(url, video_id)
    if result:
        print(f"\n✅ Transcrição extraída: {result['transcript_words']} palavras")
        print(f"   Título: {result['title']}")
        print(f"   Canal: {result['channel']}")
        if result["source_names"]:
            print(f"   Fontes: {', '.join(result['source_names'])}")
    else:
        print("❌ Falha na extração da transcrição")
        sys.exit(1)


if __name__ == "__main__":
    main()
