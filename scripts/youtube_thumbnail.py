#!/usr/bin/env python3
"""
YouTube Thumbnail Generator — Vale da Liberdade

Renderiza gerador-thumbnail-vale-liberdade.html (modo card-media) via Playwright
para produzir a thumbnail final do YouTube de um episódio BM.

Uso:
    python3 scripts/youtube_thumbnail.py --video-id ZzVHeO4h6fE
    python3 scripts/youtube_thumbnail.py --video-id ZzVHeO4h6fE --date 2026-08-23
    python3 scripts/youtube_thumbnail.py --last          # último especial gerado

Comportamento:
- Título curto: gerado pelo Gemini (simplificação do título/vídeo, ≤ 60 chars)
  com highlight; fallback = truncamento heurístico do título do vídeo.
- Apresentador: ciclo sequencial sobre Apresentador/peter*.{jpeg,jpg,png},
  começando em peter01; contador persistente (novas imagens entram no ciclo).
- Tema: thumbnails/{data}/bm_{video_id}.jpg (ou ep_{data}.jpg p/ diário).
- Saída: thumbnails/{data}/yt_{episode_id}.png (+ .jpg)

Requer: playwright (venv do projeto), google-genai global (opcional, só título).
"""
from __future__ import annotations

import argparse
import functools
import json
import os
import re
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GERADOR_DIR = PROJECT_ROOT / "references" / "youtube" / "gerador-thumbnail"
PRESENTER_DIR = GERADOR_DIR / "Apresentador"
THUMBS_DIR = PROJECT_ROOT / "thumbnails"
EPS_DIR = PROJECT_ROOT / "output" / "brasil_e_mundo" / "episodes"
STATE_FILE = PROJECT_ROOT / "output" / "youtube_thumbnail_state.json"
HTML_NAME = "gerador-thumbnail-vale-liberdade.html"

MAX_TITLE_CHARS = 58  # card headline: espaço limitado

# Config padrão enviada pelo Osmar (layout Card + Imagem 16:9, lado direito)
BASE_CONFIG = {
    "mode": "card-media",
    "side": "right",
    "cardTheme": "white",
    "fontFamily": "inter",
    "highlightColor": "yellow",
    "kicker": "ANÁLISE EXCLUSIVA",
    "logoText": "VALE DA LIBERDADE",
    "presenterName": "Peter Albuquerque",
    "presenterHandle": "@peteralbuquerque",
    "topicOverlayBadge": "EM FOCO",
    "plant": "succulent",
    "plantX": 18,
    "plantY": -126,
    "plantScale": 1.25,
    "plantBlur": 6,
    "cardWidth": 720,
    "cardTilt": -2,
    "glowOpacity": 45,
}


# --------------------------------------------------------------------------- #
# Episódio
# --------------------------------------------------------------------------- #
def load_episode(video_id: str) -> dict | None:
    p = EPS_DIR / f"especial-{video_id}.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return None


def find_episode_date(video_id: str) -> str | None:
    """Procura thumbnails/{data}/bm_{id}.* para inferir a data do episódio."""
    if not THUMBS_DIR.is_dir():
        return None
    hits = sorted(THUMBS_DIR.glob(f"*/bm_{video_id}.jpg"))
    return hits[-1].parent.name if hits else None


def episode_topic_image(video_id: str, date: str | None) -> Path | None:
    candidates = []
    if date:
        candidates.append(THUMBS_DIR / date / f"bm_{video_id}.jpg")
        candidates.append(THUMBS_DIR / date / f"ep_{date}.jpg")
    # fallback: varre todas as datas
    for d in sorted(THUMBS_DIR.glob(f"*/bm_{video_id}.jpg"), reverse=True):
        candidates.append(d)
    for c in candidates:
        if c.exists():
            return c
    return None


def episode_text(episode: dict | None, video_id: str) -> tuple[str, str]:
    """Retorna (titulo, contexto) para geração da manchete curta."""
    if not episode:
        return "", ""
    titulo = episode.get("titulo") or ""
    ctx_parts = []
    for key in ("abertura", "desenvolvimento"):
        for block in episode.get(key) or []:
            t = (block.get("texto") or "").strip()
            if t:
                ctx_parts.append(t)
            if sum(len(c) for c in ctx_parts) > 900:
                break
    return titulo, "\n".join(ctx_parts)[:1200]


# --------------------------------------------------------------------------- #
# Ciclo do apresentador
# --------------------------------------------------------------------------- #
def list_presenters() -> list[Path]:
    files = []
    for ext in ("*.jpeg", "*.jpg", "*.png", "*.webp"):
        files.extend(PRESENTER_DIR.glob(ext))
    return sorted(set(files), key=lambda p: p.name.lower())


def next_presenter() -> Path:
    """Ciclo persistente: peter01, peter02, ... volta ao início."""
    files = list_presenters()
    if not files:
        raise SystemExit(f"Nenhuma imagem de apresentador em {PRESENTER_DIR}")
    idx = 0
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text())
            prev_name = state.get("presenter", "")
            prev_idx = next((i for i, f in enumerate(files) if f.name == prev_name), None)
            if prev_idx is not None:
                idx = (prev_idx + 1) % len(files)
        except Exception:
            idx = 0
    chosen = files[idx]
    STATE_FILE.write_text(json.dumps({"presenter": chosen.name}, ensure_ascii=False, indent=2))
    return chosen


# --------------------------------------------------------------------------- #
# Manchete curta via Gemini
# --------------------------------------------------------------------------- #
def generate_headline(title: str, context: str) -> tuple[str, str]:
    """Retorna (title, highlight). Highlight deve ser substring final do title."""
    fallback_title = heuristic_short_title(title)
    try:
        from google import genai  # type: ignore
        from dotenv import load_dotenv  # type: ignore

        load_dotenv(PROJECT_ROOT / ".env")
        keys = [os.environ.get(f"GEMINI_API_KEY{_suffix}", "").strip()
                for _suffix in ("", "_2", "_3", "_4", "_5", "_6", "_7")]
        keys = [k for k in keys if k]
        if not keys:
            raise RuntimeError("sem GEMINI_API_KEY")
        prompt = f"""Você cria manchetes curtas para thumbnail de YouTube de um canal de notícias/análise libertário brasileiro chamado Vale da Liberdade.

Título completo do vídeo: "{title}"

Contexto da notícia:
{context}

Escreva uma frase curta e impactante para a thumbnail (máximo {MAX_TITLE_CHARS} caracteres), em português, capturando o gancho principal da notícia. Pode simplificar/reescrever o título. Tom direto, provocativo, jornalístico. Sem aspas, sem hashtag, sem emoji.
Além disso, escolha um trecho FINAL da frase para destacar em amarelo (2-4 palavras, substring exata do final da frase).

Responda SOMENTE com JSON válido:
{{"title": "...", "highlight": "..."}}"""
        data = None
        last_err = None
        for key in keys:
            client = genai.Client(api_key=key)
            for model in ("gemini-flash-latest", "gemini-flash-lite-latest"):
                try:
                    resp = client.models.generate_content(model=model, contents=prompt)
                    raw = (resp.text or "").strip()
                    m = re.search(r"\{.*\}", raw, re.S)
                    data = json.loads(m.group(0))
                    break
                except Exception as exc:
                    last_err = exc
                    continue
            if data:
                break
        if not data:
            raise RuntimeError(f"todas as chaves falharam: {last_err}")
        t = data.get("title", "").strip()
        h = data.get("highlight", "").strip()
        if t and h and h.lower() in t.lower() and len(t) <= MAX_TITLE_CHARS + 10:
            # garantir substring exata respeitando caixa
            pos = t.lower().rfind(h.lower())
            h = t[pos : pos + len(h)]
            print(f"   ✍️  manchete (Gemini): {t!r} hl={h!r}")
            return t, h
        raise RuntimeError(f"resposta inválida: {raw[:120]}")
    except Exception as exc:
        print(f"   ⚠️  Gemini falhou ({exc}); usando truncamento heurístico")
        t = fallback_title
        # highlight = últimas 2-3 palavras
        words = t.rsplit(" ", 3)
        h = words[-1] if len(words) > 1 else t
        return t, h


def heuristic_short_title(title: str) -> str:
    t = re.sub(r"\s+", " ", title).strip()
    if len(t) <= MAX_TITLE_CHARS:
        return t
    cut = t[:MAX_TITLE_CHARS]
    if ":" in cut:
        return cut.split(":")[0].strip()[:MAX_TITLE_CHARS]
    # corta no último espaço antes do limite
    return cut[: cut.rfind(" ")].rstrip(":,!-").strip()


# --------------------------------------------------------------------------- #
# Render Playwright
# --------------------------------------------------------------------------- #
def build_url(port: int, cfg: dict) -> str:
    from urllib.parse import quote

    def rel(path: Path) -> str:
        return "/" + str(path.resolve().relative_to(PROJECT_ROOT)).replace(os.sep, "/")

    params = {
        "mode": cfg["mode"],
        "side": cfg["side"],
        "cardTheme": cfg["cardTheme"],
        "font": cfg["fontFamily"],
        "title": cfg["title"],
        "highlight": cfg["highlight"],
        "hlColor": cfg["highlightColor"],
        "kicker": cfg["kicker"],
        "logo": cfg["logoText"],
        "presenter": rel(cfg["presenterImage"]),
        "topic": rel(cfg["topicImage"]),
        "plant": cfg["plant"],
        "plantX": cfg["plantX"],
        "plantY": cfg["plantY"],
        "plantScale": cfg["plantScale"],
        "plantBlur": cfg["plantBlur"],
        "width": cfg["cardWidth"],
        "tilt": cfg["cardTilt"],
    }
    qs = "&".join(f"{k}={quote(str(v))}" for k, v in params.items())
    rel_dir = GERADOR_DIR.resolve().relative_to(PROJECT_ROOT).as_posix()
    return f"http://127.0.0.1:{port}/{rel_dir}/{HTML_NAME}?{qs}"


def render(url: str, out_png: Path) -> None:
    from playwright.sync_api import sync_playwright

    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(PROJECT_ROOT))
    import logging

    logging.getLogger("httpserver").setLevel(logging.ERROR)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1400, "height": 900})
            page.goto(url, wait_until="networkidle", timeout=60000)
            page.wait_for_function("window.__THUMB_READY__ === true", timeout=30000)
            page.wait_for_timeout(600)
            stage = page.locator(".stage").first
            stage.screenshot(path=str(out_png))
            browser.close()
    finally:
        httpd.shutdown()


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description="Gera thumbnail YouTube (gerador HTML)")
    ap.add_argument("--video-id", help="ID do vídeo BM (especial-{id})")
    ap.add_argument("--date", help="Data YYYY-MM-DD (inferida das thumbnails se ausente)")
    ap.add_argument("--last", action="store_true", help="Usa o especial mais recente")
    ap.add_argument("--dry-run", action="store_true", help="Só mostra config, não renderiza")
    args = ap.parse_args()

    video_id = args.video_id
    if args.last or not video_id:
        specials = sorted(EPS_DIR.glob("especial-*.json"), key=lambda p: p.stat().st_mtime)
        if not specials:
            print("Nenhum especial encontrado"); return 1
        video_id = specials[-1].stem.replace("especial-", "")
        print(f"▶ Último especial: {video_id}")

    date = args.date or find_episode_date(video_id)
    episode = load_episode(video_id)
    topic = episode_topic_image(video_id, date)
    if not topic:
        print(f"❌ Thumbnail de tema não encontrada para {video_id} (data={date})"); return 1
    if not date:
        date = topic.parent.name

    title_full, context = episode_text(episode, video_id)
    print(f"📺 {video_id} ({date})")
    print(f"   tema: {topic.relative_to(PROJECT_ROOT)}")

    presenter = next_presenter()
    print(f"   apresentador: {presenter.name}")

    title, highlight = generate_headline(title_full, context)

    cfg = dict(BASE_CONFIG)
    cfg.update({"title": title, "highlight": highlight,
                "presenterImage": presenter, "topicImage": topic})

    if args.dry_run:
        print(json.dumps({k: (str(v) if isinstance(v, Path) else v) for k, v in cfg.items()},
                         ensure_ascii=False, indent=2))
        return 0

    out_png = THUMBS_DIR / date / f"yt_bm_{video_id}.png"
    out_png.parent.mkdir(parents=True, exist_ok=True)
    url = build_url(0, cfg)  # porta resolvida dentro de render(); rebuild abaixo
    # render() inicia o próprio servidor; construir URL com porta correta:
    http_port_holder = {}

    def _render_with_port():
        from playwright.sync_api import sync_playwright
        handler = functools.partial(SimpleHTTPRequestHandler, directory=str(PROJECT_ROOT))
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        port = httpd.server_address[1]
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            final_url = build_url(port, cfg)
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1400, "height": 900})
                page.goto(final_url, wait_until="networkidle", timeout=60000)
                page.wait_for_function("window.__THUMB_READY__ === true", timeout=30000)
                page.wait_for_timeout(600)
                page.locator(".stage").first.screenshot(path=str(out_png))
                browser.close()
        finally:
            httpd.shutdown()

    _render_with_port()

    # variante JPG
    try:
        from PIL import Image
        img = Image.open(out_png).convert("RGB")
        out_jpg = out_png.with_suffix(".jpg")
        img.save(out_jpg, quality=92)
        print(f"✅ {out_jpg.relative_to(PROJECT_ROOT)}")
    except Exception:
        print(f"✅ {out_png.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
