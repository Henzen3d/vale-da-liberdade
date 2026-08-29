#!/usr/bin/env python3
"""
YouTube Thumbnail Generator — Vale da Liberdade

Renderiza gerador-thumbnail-vale-liberdade.html (modo card-media) via Playwright
para produzir a thumbnail final do YouTube de um episódio BM.

A imagem editorial NÃO é descoberta por heurística. O caminho vem do manifesto
`especial-{id}.image-manifest.json` gravado pelo gerador Cloudflare.

Uso:
    python3 scripts/youtube_thumbnail.py --video-id ZzVHeO4h6fE
    python3 scripts/youtube_thumbnail.py --video-id ZzVHeO4h6fE --date 2026-08-23
    python3 scripts/youtube_thumbnail.py --last          # último especial COM manifesto

Saída: thumbnails/{data}/yt_bm_{video_id}.png (+ .jpg)
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

import random
import episode_image_manifest as eim

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GERADOR_DIR = PROJECT_ROOT / "references" / "youtube" / "gerador-thumbnail"
PRESENTER_DIR = GERADOR_DIR / "Apresentador"
THUMBS_DIR = PROJECT_ROOT / "thumbnails"
EPS_DIR = PROJECT_ROOT / "output" / "brasil_e_mundo" / "episodes"
STATE_FILE = PROJECT_ROOT / "output" / "youtube_thumbnail_state.json"
HTML_NAME = "gerador-thumbnail-vale-liberdade.html"

MAX_TITLE_CHARS = 58  # card headline: espaço limitado
DEFAULT_FONT = "anton"
LAYOUT_MODES = ("card-media", "card")
LAYOUT_WEIGHTS = (80, 20)
PLANT_CHOICES = ("none", "succulent", "eucalyptus")
PLANT_WEIGHTS = (60, 25, 15)

# Config padrão (layout Card + Imagem 16:9, lado direito, Anton impacto)
BASE_CONFIG = {
    "mode": "card-media",
    "side": "right",
    "cardTheme": "white",
    "fontFamily": "anton",
    "highlightColor": "yellow",
    "kicker": "ANÁLISE EXCLUSIVA",
    "logoText": "VALE DA LIBERDADE",
    "presenterName": "Peter Albuquerque",
    "presenterHandle": "@peteralbuquerque",
    "topicOverlayBadge": "EM FOCO",
    "plant": "none",
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


def fetch_news_lead_image(video_id: str, date: str) -> Path | None:
    """Tenta baixar a imagem principal (og:image) do site da matéria jornalística."""
    episode = load_episode(video_id)
    if not episode:
        return None
    
    refs = episode.get("fonte_referencias") or []
    urls = []
    for ref in refs:
        u = ref.get("url") if isinstance(ref, dict) else str(ref)
        if u and not any(ign in u.lower() for ign in ["youtube.com", "youtu.be", "mob.tec.br", "antonioveronese"]):
            urls.append(u)
    
    main_url = episode.get("fonte_url") or ""
    if main_url and not any(ign in main_url.lower() for ign in ["youtube.com", "youtu.be", "mob.tec.br"]):
        urls.insert(0, main_url)
    
    if not urls:
        return None

    import urllib.request
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    og_re = re.compile(r'<meta[^>]+property=[\'"]og:image[\'"][^>]+content=[\'"]([^\'"]+)[\'"]', re.I)
    og_re2 = re.compile(r'<meta[^>]+content=[\'"]([^\'"]+)[\'"][^>]+property=[\'"]og:image[\'"]', re.I)

    dest = THUMBS_DIR / date / f"news_lead_{video_id}.jpg"
    if dest.exists() and dest.stat().st_size > 15000:
        return dest

    for page_url in urls[:3]:
        try:
            req = urllib.request.Request(page_url, headers=headers)
            with urllib.request.urlopen(req, timeout=5) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
                m = og_re.search(html) or og_re2.search(html)
                if not m:
                    continue
                img_url = m.group(1).replace("&amp;", "&")
                if img_url.startswith("//"):
                    img_url = "https:" + img_url
                
                dest.parent.mkdir(parents=True, exist_ok=True)
                img_req = urllib.request.Request(img_url, headers=headers)
                with urllib.request.urlopen(img_req, timeout=8) as img_resp:
                    content = img_resp.read()
                    if len(content) > 15000:
                        dest.write_bytes(content)
                        print(f"   📸 Imagem de destaque da notícia obtida ({len(content)//1024} KB): {page_url}")
                        return dest
        except Exception:
            continue
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
# Apresentadores (Seleção Aleatória sem repetição imediata)
# --------------------------------------------------------------------------- #
def list_presenters() -> list[Path]:
    files = []
    for ext in ("*.jpeg", "*.jpg", "*.png", "*.webp"):
        files.extend(PRESENTER_DIR.glob(ext))
    peters = [f for f in files if f.name.lower().startswith("peter")]
    return sorted(set(peters or files), key=lambda p: p.name.lower())


def pick_layout(
    mode: str | None = None,
    plant: str | None = None,
    font: str | None = None,
) -> tuple[str, str, str]:
    """Sorteio ponderado; argumentos manuais vencem o sorteio."""
    chosen_mode = mode or random.choices(list(LAYOUT_MODES), weights=list(LAYOUT_WEIGHTS))[0]
    chosen_plant = plant or random.choices(list(PLANT_CHOICES), weights=list(PLANT_WEIGHTS))[0]
    chosen_font = font or DEFAULT_FONT
    return chosen_mode, chosen_plant, chosen_font


def next_presenter() -> Path:
    """Seleção aleatória entre as fotos de Peter sem repetir imediatamente a anterior."""
    files = list_presenters()
    if not files:
        raise SystemExit(f"Nenhuma imagem de apresentador em {PRESENTER_DIR}")
    
    prev_name = ""
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text())
            prev_name = state.get("presenter", "")
        except Exception:
            pass
    
    candidates = [f for f in files if f.name != prev_name] or files
    chosen = random.choice(candidates)
    
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps({"presenter": chosen.name}, ensure_ascii=False, indent=2))
    return chosen


def presenter_from_name(name: str) -> Path | None:
    if not name:
        return None
    cand = PRESENTER_DIR / name
    return cand if cand.is_file() else None


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
        raw = ""
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
            pos = t.lower().rfind(h.lower())
            h = t[pos : pos + len(h)]
            print(f"   ✍️  manchete (Gemini): {t!r} hl={h!r}")
            return t, h
        raise RuntimeError(f"resposta inválida: {raw[:120]}")
    except Exception as exc:
        print(f"   ⚠️  Gemini falhou ({exc}); usando truncamento heurístico")
        t = fallback_title
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


def _render_to(cfg: dict, out_png: Path) -> None:
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


def generate_youtube_thumbnail(
    video_id: str,
    date: str | None = None,
    *,
    force: bool = False,
    dry_run: bool = False,
    title: str | None = None,
    highlight: str | None = None,
    mode: str | None = None,
    plant: str | None = None,
    font: str | None = None,
) -> dict:
    """Gera (ou reusa) a thumbnail YouTube: og:image da matéria, fallback IA."""
    man = eim.load_manifest(video_id) or {}
    date = str(date or man.get("date") or "")
    if not date:
        raise eim.YoutubeThumbnailError(f"sem data para thumbnail de {video_id}")

    news_lead = fetch_news_lead_image(video_id, date)
    if news_lead and news_lead.is_file():
        topic = news_lead
    else:
        topic = eim.resolve_editorial_image(video_id)

    info = eim.describe_editorial(video_id, topic)
    print(f"📺 {video_id} ({date})")
    print(
        f"   episode_id: {info['episode_id']}\n"
        f"   editorial_image: {info['editorial_image']}\n"
        f"   editorial_image_exists: {info['editorial_image_exists']}\n"
        f"   editorial_image_size: {info['editorial_image_size']}\n"
        f"   editorial_image_hash: {info['editorial_image_hash']}"
    )

    out_png = THUMBS_DIR / date / f"yt_bm_{video_id}.png"
    existing = man.get("youtube_thumbnail_path")
    existing_p = Path(existing) if existing else out_png
    if (
        not force
        and existing_p.is_file()
        and man.get("youtube_thumbnail_input_hash") == info["editorial_image_hash"]
    ):
        print(f"   ⏭️  thumbnail já amarrada a este hash — reusando {existing_p}")
        return {
            "ok": True,
            "skipped": True,
            "video_id": video_id,
            "date": date,
            "editorial_image_path": str(topic),
            "editorial_image_hash": info["editorial_image_hash"],
            "youtube_thumbnail_path": str(existing_p),
            "youtube_thumbnail_input_hash": man.get("youtube_thumbnail_input_hash"),
        }

    presenter_name = man.get("youtube_presenter") or ""
    presenter = presenter_from_name(presenter_name) if presenter_name else None
    if presenter is None:
        presenter = next_presenter()
    print(f"   apresentador: {presenter.name}")

    title = (title or man.get("youtube_title") or "").strip()
    highlight = (highlight or man.get("youtube_highlight") or "").strip()
    if not title or not highlight:
        episode = load_episode(video_id)
        title_full, context = episode_text(episode, video_id)
        auto_t, auto_h = generate_headline(title_full, context)
        title = title or auto_t
        highlight = highlight or auto_h

    chosen_mode, chosen_plant, chosen_font = pick_layout(mode=mode, plant=plant, font=font)

    cfg = dict(BASE_CONFIG)
    cfg.update({
        "mode": chosen_mode,
        "plant": chosen_plant,
        "fontFamily": chosen_font,
        "title": title,
        "highlight": highlight,
        "presenterImage": presenter,
        "topicImage": topic,
    })

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "video_id": video_id,
            "config": {k: (str(v) if isinstance(v, Path) else v) for k, v in cfg.items()},
        }

    out_png.parent.mkdir(parents=True, exist_ok=True)
    _render_to(cfg, out_png)
    out_jpg = out_png.with_suffix(".jpg")
    try:
        from PIL import Image
        img = Image.open(out_png).convert("RGB")
        img.save(out_jpg, quality=92)
        final = out_jpg
        print(f"✅ {out_jpg.relative_to(PROJECT_ROOT) if PROJECT_ROOT in out_jpg.parents else out_jpg}")
    except Exception:
        final = out_png
        print(f"✅ {out_png}")

    rec = eim.record_youtube_thumbnail(
        video_id,
        final,
        editorial_used=topic,
        extra={
            "youtube_presenter": presenter.name,
            "youtube_title": title,
            "youtube_highlight": highlight,
            "youtube_mode": chosen_mode,
            "youtube_plant": chosen_plant,
            "youtube_font": chosen_font,
            "youtube_topic_image_path": str(topic),
            "date": date,
        },
    )
    print(
        f"   thumbnail_input_hash: {rec['youtube_thumbnail_input_hash']}\n"
        f"   thumbnail_output: {final}\n"
        f"   mode={chosen_mode} plant={chosen_plant} font={chosen_font}"
    )
    return {
        "ok": True,
        "skipped": False,
        "video_id": video_id,
        "date": date,
        "editorial_image_path": str(topic),
        "editorial_image_hash": info.get("editorial_image_hash", ""),
        "youtube_thumbnail_path": str(final),
        "youtube_thumbnail_input_hash": rec["youtube_thumbnail_input_hash"],
        "mode": chosen_mode,
        "plant": chosen_plant,
        "font": chosen_font,
    }


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description="Gera thumbnail YouTube (gerador HTML)")
    ap.add_argument("--video-id", help="ID do vídeo BM (especial-{id})")
    ap.add_argument("--date", help="Data YYYY-MM-DD (lida do manifesto se ausente)")
    ap.add_argument("--last", action="store_true", help="Usa o especial mais recente COM manifesto")
    ap.add_argument("--force", action="store_true", help="Regenera mesmo se o hash já bater")
    ap.add_argument("--dry-run", action="store_true", help="Só mostra config, não renderiza")
    ap.add_argument("--title", help="Manchete da thumbnail (senão Gemini/heurística)")
    ap.add_argument("--highlight", help="Trecho em amarelo (substring da manchete)")
    ap.add_argument("--mode", choices=["card-media", "card"], help="Força layout (senão 80/20)")
    ap.add_argument("--plant", choices=["none", "succulent", "eucalyptus"], help="Força planta (senão 60/25/15)")
    ap.add_argument("--font", choices=["anton", "inter", "plus"], help="Força fonte (padrão anton)")
    args = ap.parse_args()

    video_id = args.video_id
    if args.last or not video_id:
        specials = sorted(EPS_DIR.glob("especial-*.image-manifest.json"), key=lambda p: p.stat().st_mtime)
        if not specials:
            print("Nenhum manifesto de imagem encontrado")
            return 1
        video_id = specials[-1].name.replace("especial-", "").replace(".image-manifest.json", "")
        print(f"▶ Último especial com manifesto: {video_id}")

    try:
        result = generate_youtube_thumbnail(
            video_id,
            date=args.date,
            force=args.force,
            dry_run=args.dry_run,
            title=args.title,
            highlight=args.highlight,
            mode=args.mode,
            plant=args.plant,
            font=args.font,
        )
    except (eim.EditorialImageError, eim.YoutubeThumbnailError) as exc:
        print(f"❌ {exc}")
        return 1
    if args.dry_run:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
