#!/usr/bin/env python3
"""
Orquestrador do Pipeline Brasil e Mundo.

Pipeline completo e independente do jornal diário.
Reutiliza componentes de baixo nível (TTS, upload, publicação)
sem herdar as regras editoriais do noticiário diário.

Uso:
    # Pipeline completo a partir de URL
    python scripts/bm_pipeline.py full --url "https://youtube.com/watch?v=XXXXX"

    # Processar tudo que está na fila
    python scripts/bm_pipeline.py process-queue

    # Etapas individuais
    python scripts/bm_pipeline.py transcript --url "URL"
    python scripts/bm_pipeline.py roteiro --video-id "abc123"
    python scripts/bm_pipeline.py audio --video-id "abc123"

Cron sugerido:
    */60 * * * *   python scripts/bm_monitor.py
    */60 * * * *   python scripts/bm_pipeline.py process-queue
    0 9 * * 1      python scripts/bm_persona_digest.py
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(Path.home() / ".hermes" / ".env", override=False)

PIPELINE_DIR = PROJECT_ROOT / "pipelines" / "brasil_e_mundo"
RAW_DIR      = PROJECT_ROOT / "output" / "brasil_e_mundo" / "raw"
EPS_DIR      = PROJECT_ROOT / "output" / "brasil_e_mundo" / "episodes"
AUDIO_DIR    = PROJECT_ROOT / "output" / "brasil_e_mundo" / "audio"
QUEUE_PATH   = PIPELINE_DIR / "queue.json"
SEEN_PATH    = PIPELINE_DIR / "seen_videos.json"

# Hermes python (servidor Linux) ou python local
HERMES_PY = Path("/home/osmar/.hermes/hermes-agent/venv/bin/python3")
PY = str(HERMES_PY) if HERMES_PY.exists() else sys.executable


def _py(script: str) -> list[str]:
    """Retorna [python, script_path]."""
    return [PY, str(SCRIPT_DIR / script)]


def extract_video_id(url: str) -> str | None:
    patterns = [
        r"(?:youtube\.com/watch\?.*v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})",
        r"^([a-zA-Z0-9_-]{11})$",
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None


def load_queue() -> list[dict]:
    if QUEUE_PATH.exists():
        return json.loads(QUEUE_PATH.read_text(encoding="utf-8")).get("queue", [])
    return []


def save_queue(queue: list[dict]) -> None:
    QUEUE_PATH.write_text(json.dumps({"queue": queue}, ensure_ascii=False, indent=2), encoding="utf-8")


def load_seen() -> dict:
    if SEEN_PATH.exists():
        return json.loads(SEEN_PATH.read_text(encoding="utf-8"))
    return {"videos": {}}


def save_seen(seen: dict) -> None:
    SEEN_PATH.write_text(json.dumps(seen, ensure_ascii=False, indent=2), encoding="utf-8")


def mark_seen(video_id: str, metadata: dict | None = None) -> None:
    seen = load_seen()
    seen.setdefault("videos", {})[video_id] = {
        "processed_at": datetime.now(timezone.utc).isoformat(),
        **(metadata or {}),
    }
    save_seen(seen)


def run_step(cmd: list[str], label: str, env: dict | None = None) -> bool:
    """Roda um subprocesso e retorna True se bem-sucedido."""
    env = {**os.environ, **(env or {})}
    print(f"\n  ▶ {label}")
    result = subprocess.run(cmd, env=env, cwd=str(PROJECT_ROOT), capture_output=True, text=True, encoding="utf-8")
    if result.stdout:
        print(result.stdout[-3000:])
    if result.returncode != 0:
        print(f"  ❌ FALHA ({label}): exit {result.returncode}")
        if result.stderr:
            print(result.stderr[-2000:])
        return False
    return True


# ── Etapas do pipeline ──────────────────────────────────────────────────────

def step_transcript(url: str, video_id: str) -> bool:
    """Fase 2: Extrair transcrição."""
    raw_path = RAW_DIR / f"{video_id}.json"
    if raw_path.exists():
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        if raw.get("transcript") and len(raw["transcript"].split()) > 50:
            print(f"  ℹ️  Transcrição já existe ({raw.get('transcript_words', '?')} palavras)")
            return True
    return run_step(
        _py("bm_transcript.py") + ["--url", url],
        "Extração de transcrição (yt-dlp)",
    )


def step_roteiro(video_id: str, force: bool = False) -> bool:
    """Fase 3: Condensar transcrição em roteiro."""
    json_path = EPS_DIR / f"especial-{video_id}.json"
    if json_path.exists() and not force:
        print(f"  ℹ️  Roteiro já existe: {json_path.name}")
        return True
    # Passar video_id como valor de variável de ambiente para evitar problemas
    # com IDs que começam com '-' (ex: -G7PwtSmQ7Q)
    env = os.environ.copy()
    env["BM_VIDEO_ID"] = video_id
    cmd = _py("bm_condensador.py") + ["--video-id-env"]
    if force:
        cmd.append("--force")
    return run_step(cmd, "Condensação LLM (Peter solo ~5 min)", env=env)


def step_preprocess_tts(video_id: str) -> bool:
    """Fase 4a: Pré-processamento TTS."""
    md_path  = EPS_DIR / f"especial-{video_id}.md"
    tts_path = EPS_DIR / f"especial-{video_id}-tts.txt"

    if not md_path.exists():
        print(f"  ❌ Roteiro MD não encontrado: {md_path}")
        return False

    from tts_preprocessor import preprocess_for_tts
    content = md_path.read_text(encoding="utf-8")
    tts_text = preprocess_for_tts(content)
    tts_path.write_text(tts_text, encoding="utf-8")
    print(f"  ✅ TTS preprocessado: {tts_path} ({len(tts_text.split())} palavras)")
    return True


def step_audio(video_id: str) -> bool:
    """Fase 4b: Gerar áudio TTS single-speaker (Peter/Charon)."""
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    tts_path = EPS_DIR / f"especial-{video_id}-tts.txt"
    if not tts_path.exists():
        print(f"  ❌ TTS não encontrado: {tts_path}")
        return False

    today = datetime.now().strftime("%Y-%m-%d")
    wav_out = AUDIO_DIR / f"{video_id}_{today}-completo.wav"
    mp3_out = AUDIO_DIR / f"{video_id}_{today}.mp3"

    # Verifica se MP3 já existe
    if mp3_out.exists() and mp3_out.stat().st_size > 200_000:
        print(f"  ℹ️  MP3 já existe: {mp3_out}")
        return True

    tts_script = SCRIPT_DIR / "generate_gemini_tts_multi.py"

    # Tentar Gemini TTS (single speaker Peter) — modelo 2.5 para BM (mesma cota RPD,
    # isola o budget do diário que usa 3.1; disponível nas 3 keys do projeto)
    ok = run_step(
        [PY, str(tts_script),
         "--episode", str(tts_path),
         "--out", str(wav_out),
         "--speakers", "Peter",
         "--single-speaker", "Peter",
         "--mode", "halves",
         "--model", "gemini-2.5-flash-preview-tts",
         "--skip-preprocess"],
        "Geração TTS Gemini 2.5 (voz Peter/Charon) — BM",
    )

    # Verificar se MP3 foi gerado pelo pós-processamento do TTS
    if ok and mp3_out.exists():
        size = mp3_out.stat().st_size
        print(f"  ✅ MP3 gerado: {mp3_out} ({size/1e6:.2f} MB)")
        if size < 200_000:
            print(f"  ⚠️  MP3 muito pequeno ({size} bytes) — pode estar incompleto")
        return True

    # Fallback: tentar gerar MP3 com ffmpeg a partir do WAV
    if wav_out.exists():
        print("  🔁 Convertendo WAV → MP3 via ffmpeg...")
        ok2 = run_step(
            ["ffmpeg", "-y", "-i", str(wav_out),
             "-codec:a", "libmp3lame", "-qscale:a", "2",
             "-af", "loudnorm=I=-16:LRA=11:TP=-1.5",
             str(mp3_out)],
            "Conversão WAV→MP3 (ffmpeg)",
        )
        if ok2 and mp3_out.exists():
            print(f"  ✅ MP3: {mp3_out}")
            return True

    print("  ❌ Falha na geração de áudio")
    return False


def resolve_bm_mp3(video_id: str) -> Path | None:
    """Retorna o MP3 mais recente de output/brasil_e_mundo/audio/{video_id}_*.mp3."""
    if not AUDIO_DIR.exists():
        return None
    files = sorted(
        AUDIO_DIR.glob(f"{video_id}_*.mp3"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for p in files:
        if p.stat().st_size > 200_000:
            return p
    return files[0] if files else None


def step_upload_r2_especial(video_id: str) -> bool:
    """Fase 4c: Upload do áudio especial para Cloudflare R2 + sidecar.

    Catálogo usa id especial-{video_id} e chave R2 audio/especial-{video_id}.mp3.
    """
    mp3 = resolve_bm_mp3(video_id)
    if not mp3:
        print(f"  ⚠️  Sem MP3 para upload R2 (video_id={video_id})")
        return False

    especial_id = f"especial-{video_id}"
    r2_script = SCRIPT_DIR / "upload_r2.py"
    if not r2_script.exists():
        print(f"  ❌ upload_r2.py não encontrado: {r2_script}")
        return False

    print(f"  ☁️  Upload R2 especial disparado: {especial_id} ← {mp3.name}")
    ok = run_step(
        [PY, str(r2_script), "--date", especial_id, "--file", str(mp3)],
        f"Upload R2 ({especial_id})",
    )
    if ok:
        domain = (os.environ.get("R2_PUBLIC_DOMAIN") or "https://audio.mob.tec.br").rstrip("/")
        print(f"  ✅ R2 especial OK: {domain}/audio/{especial_id}.mp3")
    else:
        print(f"  ❌ Upload R2 falhou para {especial_id} — publish_site NÃO será executado")
    return ok


def step_publish_site_catalog() -> bool:
    """Reconstroi catálogo/RSS do portal (public/data + feed)."""
    pub_script = SCRIPT_DIR / "publish_site.py"
    if not pub_script.exists():
        print(f"  ❌ publish_site.py não encontrado: {pub_script}")
        return False
    ok = run_step([PY, str(pub_script)], "Publish site catalog")
    if ok:
        print("  ✅ Catálogo/site atualizado (publish_site.py)")
    else:
        print("  ❌ publish_site.py falhou")
    return ok


def step_publish_feed(video_id: str) -> bool:
    """Fase 4c: Atualizar feed RSS do Brasil e Mundo."""
    feed_path = PROJECT_ROOT / "output" / "brasil_e_mundo" / "feed.xml"
    eps_json  = EPS_DIR / f"especial-{video_id}.json"
    today     = datetime.now().strftime("%Y-%m-%d")
    mp3_name  = f"{video_id}_{today}.mp3"
    mp3_path  = AUDIO_DIR / mp3_name

    if not eps_json.exists():
        print(f"  ⚠️  Roteiro JSON não encontrado, pulando feed update")
        return True  # Não bloqueia

    episode_data = json.loads(eps_json.read_text(encoding="utf-8"))
    mp3_size = mp3_path.stat().st_size if mp3_path.exists() else 0

    # Ler feed existente ou criar novo
    site_url = os.environ.get("SITE_URL", "https://news.mob.tec.br")
    audio_url = f"{site_url}/brasil-e-mundo/audio/{mp3_name}"

    # Gerar item RSS
    pub_date = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    tags_str = "".join(f"  <category>{tag}</category>\n" for tag in episode_data.get("tags", []))
    refs = episode_data.get("fonte_referencias") or []
    refs_text = ""
    if refs:
        refs_text = " Referências: " + " | ".join(
            f"{r.get('veiculo', '').strip()}: {r.get('url', '').strip()}".strip(" :")
            for r in refs if r.get("url")
        )
    show_notes = (
        f"Comentário do Peter sobre notícias do Brasil e do Mundo. "
        f"Fonte original: {episode_data.get('fonte_veiculo') or episode_data.get('fonte_canal', 'ANCAPSU')}. "
        f"Vídeo de referência: {episode_data.get('fonte_url', '')}."
        + refs_text
    )

    new_item = f"""  <item>
    <title>{_xml_escape(episode_data.get('titulo', 'Episódio Brasil e Mundo'))}</title>
    <link>{_xml_escape(audio_url)}</link>
    <description>{_xml_escape(show_notes)}</description>
    <pubDate>{pub_date}</pubDate>
    <guid isPermaLink="false">brasil-e-mundo-{video_id}</guid>
    <enclosure url="{_xml_escape(audio_url)}" length="{mp3_size}" type="audio/mpeg"/>
    <itunes:episodeType>bonus</itunes:episodeType>
    <itunes:duration>300</itunes:duration>
{tags_str}  </item>"""

    # Criar ou atualizar feed.xml
    if feed_path.exists():
        content = feed_path.read_text(encoding="utf-8")
        # Inserir antes do </channel>
        if "</channel>" in content:
            content = content.replace("</channel>", new_item + "\n</channel>")
        else:
            content += new_item
    else:
        content = _build_initial_feed(new_item, site_url)

    feed_path.write_text(content, encoding="utf-8")
    print(f"  ✅ Feed RSS atualizado: {feed_path}")
    # publish_site.py roda depois do upload R2 (step_upload_r2_especial + step_publish_site_catalog)
    return True


def _xml_escape(text: str) -> str:
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def _build_initial_feed(first_item: str, site_url: str) -> str:
    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
     xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>Brasil e Mundo — Vale da Liberdade</title>
    <link>{site_url}/brasil-e-mundo</link>
    <description>Comentários do Peter Albuquerque sobre notícias do Brasil e do Mundo com viés libertário e anarcocapitalista.</description>
    <language>pt-BR</language>
    <lastBuildDate>{now}</lastBuildDate>
    <itunes:author>Peter Albuquerque</itunes:author>
    <itunes:category text="News"/>
    <itunes:explicit>false</itunes:explicit>
{first_item}
  </channel>
</rss>"""


def step_persona_watch(video_id: str) -> None:
    """Fase 5: Análise de estilo (não-bloqueante)."""
    try:
        run_step(
            _py("bm_persona_watch.py") + ["--video-id", video_id],
            "Análise de estilo (persona watch)",
        )
    except Exception as exc:
        print(f"  ⚠️  Persona watch falhou (não-bloqueante): {exc}")


# ── Comandos CLI ─────────────────────────────────────────────────────────────

def cmd_full(url: str, skip_audio: bool = False, force: bool = False) -> None:
    """Pipeline completo: URL → transcrição → roteiro → TTS → feed → persona."""
    video_id = extract_video_id(url)
    if not video_id:
        print(f"❌ Não foi possível extrair video_id de: {url}")
        sys.exit(1)

    print(f"\n🚀 Pipeline Brasil e Mundo — {video_id}")
    print("=" * 55)

    # 1. Transcrição
    print("\n📥 Etapa 1/5 — Extração de transcrição")
    if not step_transcript(url, video_id):
        print("❌ FALHA na extração. Abortando.")
        sys.exit(2)

    # 2. Roteiro LLM
    print("\n🧠 Etapa 2/5 — Condensação LLM")
    if not step_roteiro(video_id, force=force):
        print("❌ FALHA na condensação. Abortando.")
        sys.exit(2)

    # 3. Pré-processamento TTS
    print("\n📝 Etapa 3/5 — Pré-processamento TTS")
    if not step_preprocess_tts(video_id):
        print("❌ FALHA no pré-processamento. Abortando.")
        sys.exit(2)

    # 4. Áudio
    if skip_audio:
        print("\n🎙️  Etapa 4/5 — Áudio IGNORADO (--skip-audio)")
    else:
        print("\n🎙️  Etapa 4/5 — Geração de áudio (Peter solo)")
        if not step_audio(video_id):
            print("❌ FALHA na geração de áudio. Abortando.")
            sys.exit(2)

    # 4.5. Thumbnail automática (não-bloqueante)
    print("\n🖼️  Etapa 4.5/6 — Thumbnail automática")
    try:
        from thumbnail_generator import generate_thumbnail_safe
        # tenta ler título/resumo/data do JSON do especial
        eps_json_pre = EPS_DIR / f"especial-{video_id}.json"
        h, s = video_id, video_id
        # FONTE DE VERDADE da data = nome do arquivo de áudio {video_id}_{YYYY-MM-DD}.mp3
        # (mesma fonte que publish_site.discover_especial_episodes usa p/ o catálogo).
        # NUNCA usar datetime.now() como fallback primário — o JSON do especial
        # não tem campo de data e datetime.now() grava a thumbnail na pasta do dia
        # de PROCESSAMENTO, não do dia de PUBLICAÇÃO (bug: thumbnail "sumia").
        date_str = None
        try:
            mp3s = sorted(AUDIO_DIR.glob(f"{video_id}_*.mp3"))
            if mp3s:
                m = re.search(r"_(\d{4}-\d{2}-\d{2})\.mp3$", mp3s[0].name)
                if m:
                    date_str = m.group(1)
        except Exception:
            pass
        if not date_str:
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if eps_json_pre.exists():
            try:
                _d = json.loads(eps_json_pre.read_text(encoding="utf-8"))
                h = _d.get("titulo") or _d.get("title") or h
                s = _d.get("resumo") or _d.get("summary") or h
                # Derive date from pubDate/published_at/published (se existir no JSON)
                pub = _d.get("pubDate") or _d.get("published_at") or _d.get("published") or ""
                if pub and not date_str:
                    if re.match(r"^\d{8}$", str(pub)):
                        # Format "20260807" (YYYYMMDD) — from YouTube 'published' field
                        date_str = f"{pub[:4]}-{pub[4:6]}-{pub[6:8]}"
                    else:
                        # Parse RFC 2822 date: "Thu, 06 Aug 2026 01:14:10 +0000"
                        from email.utils import parsedate_to_datetime
                        dt = parsedate_to_datetime(str(pub))
                        date_str = dt.strftime("%Y-%m-%d")
            except Exception:
                pass
        thumb = generate_thumbnail_safe(
            date=date_str,
            episode_id=f"bm_{video_id}",
            headline=str(h),
            summary=str(s)[:600],
        )
        if thumb.get("path"):
            print(
                f"  ✅ thumbnail: {thumb.get('path')} "
                f"(model={thumb.get('image_model_used')} placeholder={thumb.get('is_placeholder')})"
            )
        else:
            print(f"  ⚠️  thumbnail sem path (não bloqueia): {thumb.get('error', thumb)}")
    except Exception as e:
        print(f"⚠️  thumbnail falhou (não bloqueia): {e}")

    # 5. Feed + Persona
    print("\n📡 Etapa 5/7 — Feed RSS + Persona watch")
    step_publish_feed(video_id)
    step_persona_watch(video_id)

    # 6. Upload R2 do especial + catálogo do portal
    # Ordem importa: sidecar R2 precisa existir antes do publish_site escolher a URL.
    print("\n☁️  Etapa 6/7 — Upload R2 especial + publish_site")
    if skip_audio and not resolve_bm_mp3(video_id):
        print("  ℹ️  Sem áudio e --skip-audio — pulando R2/publish")
    else:
        if step_upload_r2_especial(video_id):
            step_publish_site_catalog()
        else:
            print("  ⚠️  Upload R2 falhou — publish_site NÃO executado (evita URL local no catálogo)")

    # Marcar como processado só se o MP3 existir (evita seen fantasma sem áudio)
    mp3 = resolve_bm_mp3(video_id)
    if mp3:
        eps_json = EPS_DIR / f"especial-{video_id}.json"
        meta = {}
        if eps_json.exists():
            data = json.loads(eps_json.read_text(encoding="utf-8"))
            meta = {"titulo": data.get("titulo", ""), "tags": data.get("tags", [])}
        mark_seen(video_id, meta)
    else:
        print("  ⚠️  Sem MP3 — seen_videos NÃO atualizado")

    print(f"\n✅ Pipeline concluído: {video_id}")
    print(f"   Roteiro: {EPS_DIR / f'especial-{video_id}.md'}")
    print(f"   Áudio:   {AUDIO_DIR}")
    print(f"   Feed:    {PROJECT_ROOT / 'output' / 'brasil_e_mundo' / 'feed.xml'}")
    mp3 = resolve_bm_mp3(video_id)
    if mp3:
        print(f"   MP3:     {mp3}")
        print(f"   R2 id:   especial-{video_id}")


def cmd_process_queue(skip_audio: bool = False) -> None:
    """Processa todos os vídeos com status 'pending' na fila."""
    queue = load_queue()
    pending = [item for item in queue if item.get("status") == "pending"]

    if not pending:
        print("ℹ️  Nenhum vídeo pendente na fila")
        return

    print(f"📋 {len(pending)} vídeo(s) pendente(s) na fila")

    for item in pending:
        video_id = item["video_id"]
        url      = item["url"]
        title    = item.get("title", video_id)

        # Marcar como processing
        for q in queue:
            if q["video_id"] == video_id:
                q["status"] = "processing"
                break
        save_queue(queue)

        print(f"\n{'='*55}")
        print(f"🎬 Processando: {title[:60]}")

        try:
            cmd_full(url, skip_audio=skip_audio)
            for q in queue:
                if q["video_id"] == video_id:
                    q["status"] = "done"
                    q["processed_at"] = datetime.now(timezone.utc).isoformat()
                    break
        except SystemExit:
            for q in queue:
                if q["video_id"] == video_id:
                    q["status"] = "error"
                    break
            print(f"  ❌ Falha ao processar {video_id}")

        save_queue(queue)

    # Limpar done da fila (manter apenas pending/error)
    queue = [q for q in queue if q.get("status") not in ("done",)]
    save_queue(queue)

    done = len(pending) - len([q for q in pending if q.get("status") == "error"])
    print(f"\n✅ {done}/{len(pending)} vídeo(s) processado(s) com sucesso")


def main():
    parser = argparse.ArgumentParser(
        description="Pipeline Brasil e Mundo — Orquestrador",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Comandos:
  full            Pipeline completo a partir de URL
  process-queue   Processa todos os vídeos pendentes na fila
  transcript      Apenas extrai a transcrição
  roteiro         Apenas gera o roteiro (precisa de transcrição)
  audio           Apenas gera o áudio (precisa de roteiro)
  assets          Coleta imagens por quadro (bm_assets_collector)
  review          Gate de qualidade dos assets (bm_assets_review)
  composicao      Gera HTML HyperFrames (destaques, sem karaoke)
        """,
    )
    parser.add_argument("command", choices=["full", "process-queue", "transcript", "roteiro", "audio", "assets", "review", "composicao"])
    parser.add_argument("--url", help="URL do vídeo do YouTube (para: full, transcript)")
    parser.add_argument("--video-id", help="ID do vídeo")
    parser.add_argument("--skip-audio", action="store_true", help="Pular geração de áudio")
    parser.add_argument("--force", action="store_true", help="Forçar regeneração de arquivos existentes")
    parser.add_argument("--generate", action="store_true", help="assets: permite DashScope")
    parser.add_argument("--json", action="store_true", help="review: saída JSON")
    parser.add_argument("--approve", action="store_true", help="review: aprovar")
    parser.add_argument("--force-approve", action="store_true", help="review: aprovar com ressalvas")
    parser.add_argument("--project-dir", default=None, help="composicao: diretório do projeto HyperFrames")
    args = parser.parse_args()

    if args.command == "full":
        if not args.url:
            print("❌ --url é obrigatório para o comando 'full'")
            sys.exit(1)
        cmd_full(args.url, skip_audio=args.skip_audio, force=args.force)

    elif args.command == "process-queue":
        cmd_process_queue(skip_audio=args.skip_audio)

    elif args.command == "transcript":
        if not args.url:
            print("❌ --url é obrigatório para 'transcript'")
            sys.exit(1)
        video_id = extract_video_id(args.url)
        if not step_transcript(args.url, video_id):
            sys.exit(2)

    elif args.command == "roteiro":
        if not args.video_id:
            print("❌ --video-id é obrigatório para 'roteiro'")
            sys.exit(1)
        if not step_roteiro(args.video_id, force=args.force):
            sys.exit(2)

    elif args.command == "audio":
        if not args.video_id:
            print("❌ --video-id é obrigatório para 'audio'")
            sys.exit(1)
        if not step_preprocess_tts(args.video_id):
            sys.exit(2)
        if not step_audio(args.video_id):
            sys.exit(2)
        # Após gerar o MP3 do especial: upload R2 + catálogo
        print("\n☁️  Upload R2 especial + publish_site (pós-áudio)")
        if step_upload_r2_especial(args.video_id):
            step_publish_site_catalog()
        else:
            print("  ⚠️  Upload R2 falhou — publish_site NÃO executado")
            sys.exit(3)

    elif args.command == "assets":
        if not args.video_id:
            print("❌ --video-id é obrigatório para 'assets'")
            sys.exit(1)
        cmd = _py("bm_assets_collector.py") + ["--video-id", args.video_id]
        if args.force:
            cmd.append("--force")
        if args.generate:
            cmd.append("--generate")
        if not run_step(cmd, "Coleta de assets por quadro"):
            sys.exit(2)

    elif args.command == "review":
        if not args.video_id:
            print("❌ --video-id é obrigatório para 'review'")
            sys.exit(1)
        cmd = _py("bm_assets_review.py") + ["--video-id", args.video_id]
        if args.json:
            cmd.append("--json")
        if args.approve:
            cmd.append("--approve")
        if args.force_approve:
            cmd.append("--force-approve")
        if not run_step(cmd, "Review de assets"):
            sys.exit(2)

    elif args.command == "composicao":
        if not args.video_id:
            print("❌ --video-id é obrigatório para 'composicao'")
            sys.exit(1)
        gen = PROJECT_ROOT / "references" / "youtube" / "prototype" / "bancada-render" / "build_episode_composition.py"
        cmd = [PY, str(gen), "--video-id", args.video_id, "--legenda-mode", "destaques"]
        if args.project_dir:
            cmd += ["--project-dir", args.project_dir]
        if not run_step(cmd, "Composição HyperFrames"):
            sys.exit(2)


if __name__ == "__main__":
    main()
