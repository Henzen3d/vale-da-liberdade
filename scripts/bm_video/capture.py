"""Captura Playwright, handlers, X/Instagram/UOL e gravação do mockup."""
from __future__ import annotations

import hashlib
import html as _html
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from bm_video.constants import *  # noqa: F403
from bm_video.render import probe_duration_s
from bm_video.server import start_server
from bm_video.state import (
    _build_mockup_update_payload,
    _clean_url,
    _normalize_beat_v2,
    _omnibox_url,
    _safe_mockup_update,
    _unescape,
    domain_of,
    episode_date,
    episode_summary,
    highlight_from_script,
    is_blocked_source_url,
    one_line_subhead,
    ticker_headlines,
)

def _import_screenshot_capture():
    """`python3 scripts/bm_mockup_video.py` põe scripts/ em path[0]; sem o
    ROOT do repo `from scripts.screenshots` quebra e o print cai no
    Playwright cru (paywall Folha em xauvz73KEpA / 99MaNTs-qZg).
    """
    root = str(ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    try:
        from scripts.screenshots.runner import capture as clean_capture
    except Exception as exc:  # noqa: BLE001
        print(f"  ⚠️  screenshots.runner indisponível: {type(exc).__name__}: {exc}")
        return None
    return clean_capture


def try_handler_screenshot(url: str, dest: Path, viewport: dict[str, int] | None = None) -> dict | None:
    """Captura via runner: handler dedicado ou BaseScraper (CSS/SPA).

    None só se o módulo de screenshots falhar ao importar. Sem handler
    exclusivo NÃO cai no Playwright cru — isso imprimia SPA (Polymarket)
    antes do CSS (6lZdp_xTADA).
    """
    clean_capture = _import_screenshot_capture()
    if clean_capture is None:
        return None
    return clean_capture(
        url,
        dest=dest,
        viewport=viewport,
        timeout_ms=45_000,
    )


def _open_sync_playwright():
    """Seam for tests. Never call from inside an already-open sync_playwright()."""
    from playwright.sync_api import sync_playwright

    return sync_playwright()


def _handler_shot_ok(result: dict | None, dest: Path) -> bool:
    return bool(
        result
        and result.get("ok")
        and result.get("http_status") not in (403, 500, 502, 503, 520, 521)
        and dest.exists()
        and dest.stat().st_size > MIN_SHOT_BYTES
        and not _shot_looks_blank(dest)
    )


BROKEN_HANDLERS_FILE = ROOT / "output" / "broken_handlers.json"


def record_broken_handler(
    url: str,
    handler_name: str,
    error_reason: str,
    http_status: int | None = None,
    log_file: Path | None = None,
) -> None:
    """Registra falha de captura/handler no arquivo de auditoria para triagem e reparo."""
    if log_file is None:
        log_file = BROKEN_HANDLERS_FILE
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        entries: list[dict[str, Any]] = []
        if log_file.is_file():
            try:
                entries = json.loads(log_file.read_text(encoding="utf-8"))
                if not isinstance(entries, list):
                    entries = []
            except Exception:
                entries = []

        now_iso = datetime.now().astimezone().isoformat()
        domain = ""
        try:
            domain = (urlsplit(url).hostname or "").removeprefix("www.")
        except Exception:
            pass

        new_entry = {
            "timestamp": now_iso,
            "url": url,
            "domain": domain,
            "handler": handler_name,
            "error": str(error_reason),
            "status": http_status,
        }
        entries.append(new_entry)
        if len(entries) > 500:
            entries = entries[-500:]
        log_file.write_text(
            json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except Exception as exc:
        print(f"  ⚠️  Falha ao registrar broken handler: {exc}")


def _get_download_article_image():
    """Import dinâmico de download_article_image para evitar import cíclico."""
    try:
        from person_resolver import download_article_image
        return download_article_image
    except Exception:
        try:
            from scripts.person_resolver import download_article_image
            return download_article_image
        except Exception:
            return None


def cache_path_for_url(url: str) -> Path:
    raw = f"{CAPTURE_CACHE_VERSION}|{(url or '').strip()}"
    url_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return CAPTURE_CACHE_DIR / f"{url_hash}.png"


def get_cached_screenshot(url: str) -> Path | None:
    path = cache_path_for_url(url)
    if not path.exists() or path.stat().st_size <= 8000:
        return None
    age_seconds = time.time() - path.stat().st_mtime
    if age_seconds > (CACHE_MAX_AGE_HOURS * 3600):
        return None
    return path


def save_cached_screenshot(url: str, src_path: Path) -> Path | None:
    if not src_path.exists() or src_path.stat().st_size <= 8000:
        return None
    CAPTURE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    dest = cache_path_for_url(url)
    try:
        shutil.copy2(src_path, dest)
        return dest
    except Exception:
        return None


def stitch_screenshots(top_path: Path, bottom_path: Path, out_path: Path, crop_sticky_px: int = 75) -> Path | None:
    """Combina dois screenshots verticalmente eliminando a barra de navegação duplicada."""
    try:
        from PIL import Image
        if not top_path.exists() or not bottom_path.exists():
            return None
        top_im = Image.open(top_path).convert("RGB")
        bot_im = Image.open(bottom_path).convert("RGB")
        crop_y = min(crop_sticky_px, bot_im.height // 4)
        bot_cropped = bot_im.crop((0, crop_y, bot_im.width, bot_im.height))
        stitched = Image.new("RGB", (top_im.width, top_im.height + bot_cropped.height))
        stitched.paste(top_im, (0, 0))
        stitched.paste(bot_cropped, (0, top_im.height))
        stitched.save(out_path, format="PNG", optimize=True)
        return out_path
    except Exception as exc:
        print(f"  ⚠️  Falha ao concatenar screenshots: {exc}")
        return None


def stage_person_photo_assets(beats: list, work: Path) -> None:
    """Copia foto editorial para work/shots para o HTTP do mockup servir /shots/."""
    shot_dir = work / "shots"
    shot_dir.mkdir(parents=True, exist_ok=True)
    for beat in beats or []:
        payload = None
        if isinstance(beat, dict):
            kind = beat.get("visual_component") or beat.get("kind")
            payload = beat.get("visual_payload")
        else:
            kind = getattr(beat, "visual_component", None) or getattr(beat, "kind", None)
            payload = getattr(beat, "visual_payload", None)
        if kind != "person-photo" or not isinstance(payload, dict):
            continue
        src = Path(str(payload.get("photo_src") or ""))
        if not src.is_file():
            payload["photo"] = ""
            continue
        dest = shot_dir / f"editorial-{src.name}"
        try:
            if not dest.exists() or dest.stat().st_size != src.stat().st_size:
                shutil.copy2(src, dest)
            payload["photo"] = f"/shots/{dest.name}"
        except Exception as exc:
            print(f"  ⚠️  Falha ao copiar foto editorial: {exc}")
            payload["photo"] = ""


def is_uol_flash_url(url: str | None) -> bool:
    """UOL Flash (feed de clipes). Matéria uol.com.br/noticias NÃO entra."""
    if not url:
        return False
    parts = urlsplit(url)
    host = (parts.netloc or "").lower()
    path = (parts.path or "").lower().rstrip("/")
    if "uol.com.br" not in host:
        return False
    return path == "/flash" or path.startswith("/flash/")


def host_kind(url: str) -> str:
    host = (urlsplit(url or "").netloc or "").lower()
    if "instagram.com" in host:
        return "instagram"
    if "bbc." in host or host.endswith("bbc.co.uk") or host.endswith("bbc.com"):
        return "bbc"
    if host.startswith("g1.") or host.endswith("g1.globo.com") or host == "g1.globo.com":
        return "g1"
    if "x.com" in host or "twitter.com" in host:
        return "x"
    if is_uol_flash_url(url):
        return "uol-flash"
    return "generic"


def x_tweet_id(url: str | None) -> str | None:
    """Extrai o ID numérico de um status do X/Twitter."""
    m = _X_STATUS_RE.search(url or "")
    return m.group(1) if m else None


def capture_x_embed(page, url: str, dest: Path) -> bool:
    """Captura um post do X via embed oficial (platform.twitter.com).

    O HTML do x.com devolve 403 para headless, mas o widget de embed é
    público e não exige login. Renderiza o card em fundo escuro e tira
    screenshot do viewport. Retorna True se a captura passou os filtros.
    """
    tid = x_tweet_id(url)
    if not tid:
        return False
    try:
        page.set_content(_X_EMBED_WRAP.replace("__TWEET_ID__", tid), wait_until="load")
        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        page.wait_for_timeout(3500)
        page.screenshot(path=str(dest), full_page=False)
    except Exception as exc:  # noqa: BLE001
        print(f"  ⚠️  x-embed falhou ({tid}): {exc}")
        dest.unlink(missing_ok=True)
        return False
    if not dest.exists() or dest.stat().st_size <= MIN_SHOT_BYTES or _shot_looks_blank(dest):
        print(f"  🚫 x-embed vazio/indisponível ({tid}) — cena descartada")
        dest.unlink(missing_ok=True)
        return False
    return True


def fetch_x_post_data(page, url: str, shot_dir: Path) -> dict | None:
    """Extrai dados estruturados de um tweet (autor, handle, avatar, texto, mídia, métricas).

    Usa oEmbed oficial para obter texto íntegro e autor sem truncamento, e
    o widget oficial do X para extrair imagem de mídia, avatar e contadores.
    Baixa imagens para o shot_dir local para exibição offline sem engasgo de rede.
    """
    import html
    import urllib.request

    m = re.search(r"(?:x|twitter)\.com/([^/]+)/status/(\d+)", url or "")
    if not m:
        return None
    url_handle = m.group(1)
    tid = m.group(2)

    author_name = url_handle
    handle = f"@{url_handle}"
    text = ""
    media_url = ""
    avatar_url = ""
    timestamp = ""
    replies = "12"
    reposts = "45"
    likes = "120"

    # 1. Tentar Syndication API oficial do X (rápida, direta e sem bloqueios)
    try:
        syn_url = f"https://cdn.syndication.twimg.com/tweet-result?id={tid}&lang=pt&token=4"
        req = urllib.request.Request(syn_url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=6) as r:
            syn_data = json.loads(r.read().decode("utf-8"))
            if syn_data.get("user"):
                u = syn_data["user"]
                if u.get("name"):
                    author_name = u["name"]
                if u.get("screen_name"):
                    handle = f"@{u['screen_name'].lstrip('@')}"
                if u.get("profile_image_url_https"):
                    avatar_url = u["profile_image_url_https"].replace("_normal.", "_400x400.")
            if syn_data.get("mediaDetails"):
                m0 = syn_data["mediaDetails"][0]
                if m0.get("media_url_https"):
                    media_url = m0["media_url_https"]
            elif syn_data.get("photos"):
                p0 = syn_data["photos"][0]
                if p0.get("url"):
                    media_url = p0["url"]
            if syn_data.get("text"):
                text = html.unescape(syn_data["text"]).strip()
            if syn_data.get("favorite_count"):
                fc = syn_data["favorite_count"]
                likes = f"{fc/1000:.1f}K" if fc >= 10000 else (f"{fc/1000:.1f}K" if fc >= 1000 else str(fc))
            if syn_data.get("conversation_count"):
                replies = str(syn_data["conversation_count"])
    except Exception as exc:
        print(f"  ⚠️  x-syndication ({tid}): {exc}")

    # 2. Obter texto limpo e autor via oEmbed oficial (se ainda não tiver texto)
    try:
        oembed_url = f"https://publish.twitter.com/oembed?url=https://x.com/{url_handle}/status/{tid}"
        req = urllib.request.Request(oembed_url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=6) as r:
            oembed_data = json.loads(r.read().decode("utf-8"))
            if oembed_data.get("author_name") and (not author_name or author_name == url_handle):
                author_name = oembed_data["author_name"]
            raw_html = oembed_data.get("html", "")
            p_match = re.search(r"<p[^>]*>(.*?)</p>", raw_html, re.DOTALL)
            if p_match:
                p_text = re.sub(r"<a[^>]*>(.*?)</a>", r"\1", p_match.group(1))
                p_text = re.sub(r"<br\s*/?>", "\n", p_text)
                clean_p = html.unescape(p_text).strip()
                if not text or len(clean_p) > len(text):
                    text = clean_p
    except Exception as exc:
        print(f"  ⚠️  x-oembed ({tid}): {exc}")

    # 3. Fallback: widget público via Playwright se ainda faltar avatar ou mídia
    if not avatar_url or not media_url:
        embed_url = f"https://platform.twitter.com/embed/Tweet.html?id={tid}&theme=light&lang=pt"
        try:
            page.goto(embed_url, wait_until="load", timeout=12000)
            page.wait_for_timeout(1500)
            extracted = page.evaluate("""() => {
                const bodyText = document.body.innerText || "";
                const lines = bodyText.split('\\n').map(s => s.trim()).filter(Boolean);
                
                const imgs = Array.from(document.querySelectorAll('img')).map(i => i.src);
                const av = imgs.find(s => s.includes('profile_images')) || "";
                const media = imgs.filter(s => s.includes('/media/')).map(s => s.replace(/name=[a-z0-9_]+/i, 'name=large'));

                let likesCount = "120";
                const likesMatch = bodyText.match(/([0-9.,]+(?:\\s*mil|K|M)?)\\s*(?:curtidas|likes)/i) ||
                                   bodyText.match(/([0-9.,]+(?:\\s*mil|K|M)?)\\s*\\n\\s*Responder/i);
                if (likesMatch) likesCount = likesMatch[1];

                const timeEl = document.querySelector('time');
                const timeStr = timeEl ? timeEl.innerText.trim() : "";

                return {
                    lines,
                    avatar: av,
                    mediaImgs: media,
                    timeStr,
                    likes: likesCount
                };
            }""")

            if not text and extracted.get("lines"):
                lines = extracted["lines"]
                if len(lines) > 2:
                    text = html.unescape(lines[2]).strip()

            if not avatar_url and extracted.get("avatar"):
                avatar_url = extracted["avatar"].replace("_normal.", "_400x400.")
            media_urls = extracted.get("mediaImgs") or []
            if not media_url and media_urls:
                media_url = media_urls[0]
            if not timestamp and extracted.get("timeStr"):
                timestamp = extracted["timeStr"]
            if extracted.get("likes") and likes == "120":
                likes = extracted["likes"]
        except Exception as exc:
            print(f"  ⚠️  x-embed dom ({tid}): {exc}")

    # 4. Higienização do texto: desescapa HTML e SEMPRE remove links finais de fotos (pic.twitter.com, pic.x.com, t.co)
    if text:
        text = html.unescape(text)
        text = re.sub(r"(?:https?://)?(?:pic\.(?:twitter|x)\.com/\S+|t\.co/\S+)\s*$", "", text, flags=re.IGNORECASE).strip()

    # 3. Baixar imagens localmente no shot_dir para funcionar 100% offline
    avatar_rel = ""
    if avatar_url:
        try:
            av_dest = shot_dir / f"x-av-{tid}.jpg"
            if not av_dest.exists():
                req = urllib.request.Request(avatar_url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=6) as r:
                    av_dest.write_bytes(r.read())
            avatar_rel = f"/shots/{av_dest.name}"
        except Exception:
            avatar_rel = avatar_url

    media_rel = ""
    if media_url:
        try:
            m_dest = shot_dir / f"x-media-{tid}.jpg"
            if not m_dest.exists():
                req = urllib.request.Request(media_url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=8) as r:
                    m_dest.write_bytes(r.read())
            media_rel = f"/shots/{m_dest.name}"
        except Exception:
            media_rel = media_url

    post_data = {
        "author_name": author_name,
        "handle": handle,
        "avatar": avatar_rel,
        "media": media_rel,
        "text": text,
        "timestamp": timestamp or "Recente",
        "replies": replies,
        "reposts": reposts,
        "likes": likes,
        "verified": True,
    }

    try:
        from .translation import enrich_x_post_translation
        post_data = enrich_x_post_translation(post_data)
    except Exception as exc:
        print(f"  ⚠️  falha ao verificar/traduzir x_post: {exc}")

    return post_data


def _find_ytdlp() -> str:
    """Localiza o binário do yt-dlp no ambiente atual, PATH ou diretórios padrões de instalação."""
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


def extract_x_video(url: str, work: Path, video_id: str, idx: int) -> str | None:
    """Baixa o vídeo de um post do X (sem áudio é suficiente: mockup é mudo).
    Retorna caminho relativo ao server root ('/shots/...') ou None."""
    dest = work / "shots" / f"xvid-{video_id}-{idx:02d}.mp4"
    if dest.exists() and dest.stat().st_size > 50000:
        return f"/shots/{dest.name}"
    cmd = [
        _find_ytdlp(), "-f", "bv*[height<=720]/b[height<=720]/b",
        "--no-playlist", "--no-warnings", "--quiet",
        "-o", str(dest), url,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    # yt-dlp pode adicionar extensão própria
    if not dest.exists():
        cands = list((work / "shots").glob(f"xvid-{video_id}-{idx:02d}.*"))
        if cands:
            return f"/shots/{cands[0].name}"
    if r.returncode != 0 or not dest.exists() or dest.stat().st_size < 50000:
        print(f"  ⚠️  x-video: sem vídeo embutido em {url}: {(r.stderr or '')[-160:]}")
        return None
    print(f"  🎞️  x-video: {dest.name} ({dest.stat().st_size // 1024} KB)")
    return f"/shots/{dest.name}"


def instagram_shortcode(url: str | None) -> str | None:
    """Extrai o shortcode (ID do post ou reel) de uma URL do Instagram."""
    m = _INSTAGRAM_POST_RE.search(url or "")
    return m.group(1) if m else None


def extract_instagram_video(url: str, work: Path, video_id: str, idx: int) -> str | None:
    """Baixa o vídeo de um post/reel do Instagram via yt-dlp.
    Retorna caminho relativo ao server root ('/shots/...') ou None se não for vídeo ou falhar."""
    dest = work / "shots" / f"igvid-{video_id}-{idx:02d}.mp4"
    if dest.exists() and dest.stat().st_size > 50000:
        return f"/shots/{dest.name}"
    cmd = [
        _find_ytdlp(), "-f", "bv*[height<=720]/b[height<=720]/b",
        "--no-playlist", "--no-warnings", "--quiet",
        "-o", str(dest), url,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except Exception as exc:
        print(f"  ⚠️  instagram-video: erro ao executar yt-dlp: {exc}")
        return None

    if not dest.exists():
        cands = list((work / "shots").glob(f"igvid-{video_id}-{idx:02d}.*"))
        if cands:
            return f"/shots/{cands[0].name}"
    if r.returncode != 0 or not dest.exists() or dest.stat().st_size < 50000:
        print(f"  ⚠️  instagram-video: sem vídeo ou falha em {url}: {(r.stderr or '')[-160:]}")
        return None
    print(f"  📸🎞️  instagram-video: {dest.name} ({dest.stat().st_size // 1024} KB)")
    return f"/shots/{dest.name}"


def extract_uol_flash_video(url: str, work: Path, video_id: str, idx: int) -> str | None:
    """Baixa o clipe de uol.com.br/flash via yt-dlp (teste: loUBwNIVsfk).

    Matéria comum do UOL continua print. Sem vídeo ou falha → None (print fallback).
    """
    dest = work / "shots" / f"uolvid-{video_id}-{idx:02d}.mp4"
    if dest.exists() and dest.stat().st_size > 50000:
        return f"/shots/{dest.name}"
    cmd = [
        _find_ytdlp(), "-f", "bv*[height<=720]/b[height<=720]/b",
        "--no-playlist", "--no-warnings", "--quiet",
        "-o", str(dest), url,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except Exception as exc:
        print(f"  ⚠️  uol-flash-video: erro ao executar yt-dlp: {exc}")
        return None

    if not dest.exists():
        cands = list((work / "shots").glob(f"uolvid-{video_id}-{idx:02d}.*"))
        if cands:
            return f"/shots/{cands[0].name}"
    if r.returncode != 0 or not dest.exists() or dest.stat().st_size < 50000:
        print(f"  ⚠️  uol-flash-video: sem vídeo ou falha em {url}: {(r.stderr or '')[-160:]}")
        return None
    print(f"  🎞️  uol-flash-video: {dest.name} ({dest.stat().st_size // 1024} KB)")
    return f"/shots/{dest.name}"


def capture_instagram_embed(page, url: str, dest: Path) -> bool:
    """Captura post/reel do Instagram via embed público oficial (/embed/).

    Evita o login-wall do Instagram renderizando a versão pública de embed.
    Retorna True se a captura passou os filtros.
    """
    code = instagram_shortcode(url)
    if not code:
        return False
    embed_url = f"https://www.instagram.com/p/{code}/embed/"
    try:
        page.goto(embed_url, wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(2500)
        dest.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(dest), full_page=False)
        if not dest.exists() or dest.stat().st_size <= MIN_SHOT_BYTES or _shot_looks_blank(dest):
            dest.unlink(missing_ok=True)
            return False
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"  ⚠️  instagram-embed falhou ({code}): {exc}")
        dest.unlink(missing_ok=True)
        return False


def _click_first_visible(page, selectors: tuple[str, ...]) -> str | None:
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible(timeout=600):
                loc.click(timeout=800)
                page.wait_for_timeout(350)
                return sel
        except Exception:
            continue
    return None


def prepare_capture(page, url: str) -> dict:
    """Fecha banner/login e posiciona o viewport no conteúdo da matéria."""
    kind = host_kind(url)
    clicked = []
    for _ in range(3):
        hit = _click_first_visible(page, _DISMISS_BUTTONS)
        if not hit:
            break
        clicked.append(hit)
    try:
        info = page.evaluate(_PREPARE_JS, {"kind": kind})
    except Exception as exc:
        info = {"scrolledTo": "error", "error": str(exc)}
    page.wait_for_timeout(400)
    info = dict(info or {})
    info["kind"] = kind
    info["clicked"] = clicked
    return info


def instagram_is_login_wall(page) -> bool:
    """True só se o modal de cadastro/login ainda estiver aberto no meio da tela."""
    try:
        dialog = page.locator("[role='dialog']").first
        if not dialog.count() or not dialog.is_visible(timeout=400):
            return False
        t = (dialog.inner_text() or "").lower()
        return any(k in t for k in ("cadastre-se", "sign up", "entrar", "log in"))
    except Exception:
        return False


def _shot_looks_blank(path: Path) -> bool:
    """True se a screenshot for praticamente uniforme (página vazia/erro).

    Capturas de login-wall ou de página que não renderizou saem como um
    retângulo liso (branco ou preto). Elas viravam cena de 8s+ com o browser
    mostrando nada. Usa desvio padrão da luminância como sinal.
    """
    try:
        from PIL import Image, ImageStat
    except Exception:  # noqa: BLE001
        return False
    try:
        with Image.open(path) as im:
            stat = ImageStat.Stat(im.convert("L"))
            return (stat.stddev[0] if stat.stddev else 0.0) < BLANK_SHOT_STDDEV
    except Exception:  # noqa: BLE001
        return False


def page_looks_blocked(page, status: int | None = None) -> str | None:
    """Devolve o marcador de bloqueio encontrado, ou None se a página é real.

    Uma tela Akamai "Access Denied" rende PNG de ~28 KB com texto preto sobre
    branco: passa em MIN_SHOT_BYTES e em _shot_looks_blank, e antes disso virava
    cena de vídeo. Detectar pelo TEXTO é o único sinal confiável.
    """
    if status is not None and status in (401, 403, 429, 451):
        return f"http-{status}"
    try:
        body = (page.inner_text("body") or "")[:3000].lower()
    except Exception:  # noqa: BLE001
        return None
    if len(body.strip()) > 1500:
        # Página com corpo longo é matéria real; interstitials são curtos.
        return None
    for marker in _BLOCK_TEXT_MARKERS:
        if marker in body:
            return marker
    return None


def wait_for_styled_capture(page, timeout_ms: int = 20000) -> None:
    """Espera CSS + fontes + imagens do viewport antes do screenshot.

    `load` sozinho não basta: portais injetam CSS/hero via JS e o PNG sai
    como texto cru sem formatação.
    """
    try:
        page.wait_for_function(_WAIT_STYLED_JS, timeout=timeout_ms)
    except Exception:
        pass
    try:
        page.evaluate("() => (document.fonts && document.fonts.ready) || true")
    except Exception:
        pass
    try:
        page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        pass
    page.wait_for_timeout(600)


def _assemble_captured_scenes(scenes: list[dict], by_index: dict[int, dict]) -> list[dict]:
    out: list[dict] = []
    for i, scene in enumerate(scenes):
        if i in by_index:
            base = by_index[i]
            out.append(base)
            # Multi-Shot: se capturou também detalhe do texto/corpo, insere como corte alternado
            if base.get("shot_detail"):
                detail_scene = dict(base)
                detail_scene["shot"] = base["shot_detail"]
                detail_scene["veiculo"] = f"{base.get('veiculo', '')} (detalhe)"
                detail_scene["role"] = "supporting"
                out.append(detail_scene)
            continue
        item = dict(scene)
        item.setdefault("shot", None)
        out.append(item)
    return out


def capture_sources(scenes: list[dict], shot_dir: Path) -> list[dict]:
    shot_dir.mkdir(parents=True, exist_ok=True)
    by_index: dict[int, dict] = {}

    # 1. Checar cache em disco primeiro
    to_fetch: list[tuple[int, dict, Path]] = []
    for i, scene in enumerate(scenes):
        dest = shot_dir / f"src-{i:02d}.png"
        url = scene.get("url") or ""
        cached = get_cached_screenshot(url)
        if cached:
            try:
                shutil.copy2(cached, dest)
                if dest.stat().st_size < MIN_SHOT_BYTES or _shot_looks_blank(dest):
                    print(f"  🚫 [cache] {scene['veiculo']}: captura em branco — invalidando cache")
                    try:
                        cached.unlink()
                    except Exception:  # noqa: BLE001
                        pass
                    dest.unlink(missing_ok=True)
                    to_fetch.append((i, scene, dest))
                    continue
                item = dict(scene)
                item["shot"] = dest.name
                item["video"] = None
                by_index[i] = item
                print(f"  ⚡ [cache] {scene['veiculo']}: {dest.name} ({dest.stat().st_size // 1024} KB)")
                continue
            except Exception:
                pass
        to_fetch.append((i, scene, dest))

    # 2. Handlers em Playwright próprio — ANTES do sync_playwright genérico.
    #    Aninhar os dois abre um loop asyncio e o Sync API dos handlers
    #    quebra (vhm4xPVjxFk: prints sem CSS no fallback).
    remaining: list[tuple[int, dict, Path]] = []
    last_domain = ""
    for i, scene, dest in to_fetch:
        url = scene.get("url") or ""
        if host_kind(url) in ("x", "instagram", "uol-flash"):
            remaining.append((i, scene, dest))
            continue
        current_domain = domain_of(url)
        if last_domain:
            if current_domain and current_domain == last_domain:
                delay = random.uniform(8.0, 15.0)
            else:
                delay = random.uniform(3.5, 8.0)
            print(f"  ⏳ Delay educado anti-bot: {delay:.1f}s...")
            time.sleep(delay)
        last_domain = current_domain
        handler_result = try_handler_screenshot(
            url, dest, viewport={"width": 1400, "height": 900}
        )
        if handler_result is not None:
            handler_name = handler_result.get("handler") or "?"
            if _handler_shot_ok(handler_result, dest):
                save_cached_screenshot(url, dest)
                item = dict(scene)
                item["shot"] = dest.name
                item["video"] = None
                meta = handler_result.get("meta") or {}
                if meta.get("shot_long"):
                    item["shot_long"] = meta["shot_long"]
                if meta.get("highlight_box"):
                    item["highlight_box"] = meta["highlight_box"]
                by_index[i] = item
                print(
                    f"  📸 {scene['veiculo']}: {dest.name} "
                    f"({dest.stat().st_size // 1024} KB, handler={handler_name})"
                )
                continue
            err_reason = handler_result.get("error") or f"http_{handler_result.get('http_status')}" or "shot_unusable"
            record_broken_handler(
                url=url,
                handler_name=handler_name,
                error_reason=err_reason,
                http_status=handler_result.get("http_status"),
            )
            print(
                f"  ↪️  {scene['veiculo']}: handler={handler_name} falhou "
                f"({err_reason}) "
                f"— fallback genérico"
            )
            dest.unlink(missing_ok=True)
        remaining.append((i, scene, dest))

    to_fetch = remaining
    if not to_fetch:
        return _assemble_captured_scenes(scenes, by_index) or scenes

    # 3. Fallback genérico (X/Instagram e handlers que falharam)
    with _open_sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True, args=["--disable-blink-features=AutomationControlled"]
        )
        ctx = browser.new_context(
            viewport={"width": 1400, "height": 900},
            user_agent=UA,
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            extra_http_headers={
                "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,"
                    "image/avif,image/webp,image/apng,*/*;q=0.8"
                ),
                "Upgrade-Insecure-Requests": "1",
            },
        )
        last_domain = ""

        for i, scene, dest in to_fetch:
            page = ctx.new_page()
            try:
                try:
                    from playwright_stealth import Stealth

                    Stealth().apply_stealth_sync(page)
                except Exception:  # noqa: BLE001
                    pass
                url = scene.get("url") or ""
                current_domain = domain_of(url)

                # Delay educado com jitter entre requisições
                if last_domain:
                    if current_domain and current_domain == last_domain:
                        delay = random.uniform(8.0, 15.0)
                    else:
                        delay = random.uniform(3.5, 8.0)
                    print(f"  ⏳ Delay educado anti-bot: {delay:.1f}s...")
                    time.sleep(delay)
                last_domain = current_domain

                # X com vídeo embutido: baixa o clipe em vez de screenshot estático
                if host_kind(url) == "x":
                    vid_rel = extract_x_video(url, shot_dir.parent, shot_dir.parent.name, i)
                    if vid_rel:
                        item = dict(scene)
                        item["shot"] = None
                        item["video"] = vid_rel
                        by_index[i] = item
                        continue
                    # sem vídeo: tenta mockup estruturado do X (clean animado)
                    x_post = fetch_x_post_data(page, url, shot_dir)
                    if x_post:
                        # tira screenshot fallback também caso precise de fallback estático
                        capture_x_embed(page, url, dest)
                        item = dict(scene)
                        item["kind"] = "x-post"
                        item["shot"] = dest.name if dest.exists() else None
                        item["video"] = None
                        item["x_post"] = x_post
                        by_index[i] = item
                        print(f"  🐦 {scene['veiculo']}: mockup do X ({x_post.get('handle')}, mídia={'sim' if x_post.get('media') else 'não'})")
                        continue
                    # fallback tradicional de screenshot embed
                    if capture_x_embed(page, url, dest):
                        save_cached_screenshot(url, dest)
                        item = dict(scene)
                        item["shot"] = dest.name
                        item["video"] = None
                        by_index[i] = item
                        print(f"  🐦 {scene['veiculo']}: {dest.name} ({dest.stat().st_size // 1024} KB, embed)")
                        continue
                    item = dict(scene)
                    item["shot"] = None
                    by_index[i] = item
                    continue

                # UOL Flash: clipe no feed (loUBwNIVsfk saiu print do player).
                if host_kind(url) == "uol-flash":
                    vid_rel = extract_uol_flash_video(url, shot_dir.parent, shot_dir.parent.name, i)
                    if vid_rel:
                        item = dict(scene)
                        item["shot"] = None
                        item["video"] = vid_rel
                        by_index[i] = item
                        print(f"  🎞️  {scene['veiculo']}: vídeo baixado ({vid_rel})")
                        continue
                    # Sem MP4: cai no print genérico abaixo.

                # Instagram com vídeo/reel embutido: baixa o clipe com yt-dlp
                if host_kind(url) == "instagram":
                    vid_rel = extract_instagram_video(url, shot_dir.parent, shot_dir.parent.name, i)
                    if vid_rel:
                        item = dict(scene)
                        item["shot"] = None
                        item["video"] = vid_rel
                        by_index[i] = item
                        print(f"  📸🎞️ {scene['veiculo']}: vídeo baixado ({vid_rel})")
                        continue
                    # Sem vídeo ou falhou: tenta embed público oficial para evitar login-wall
                    if capture_instagram_embed(page, url, dest):
                        save_cached_screenshot(url, dest)
                        item = dict(scene)
                        item["shot"] = dest.name
                        item["video"] = None
                        by_index[i] = item
                        print(f"  📸 {scene['veiculo']}: {dest.name} ({dest.stat().st_size // 1024} KB, embed)")
                        continue
                    item = dict(scene)
                    item["shot"] = None
                    by_index[i] = item
                    continue
                resp = page.goto(url, wait_until="load", timeout=45000)
                wait_for_styled_capture(page)
                blocked = page_looks_blocked(page, resp.status if resp else None)
                if blocked:
                    print(f"  🚫 {scene['veiculo']}: bloqueio antibot ({blocked}) — tentando resgate via imagem da matéria (og:image)")
                    record_broken_handler(
                        url=url,
                        handler_name="generic",
                        error_reason=f"blocked:{blocked}",
                        http_status=resp.status if resp else None,
                    )
                    downloader = _get_download_article_image()
                    if downloader and downloader(url, dest):
                        save_cached_screenshot(url, dest)
                        item = dict(scene)
                        item["shot"] = dest.name
                        item["video"] = None
                        by_index[i] = item
                        print(f"  🖼️  {scene['veiculo']}: resgatado com imagem editorial da matéria ({dest.stat().st_size // 1024} KB)")
                        continue
                    item = dict(scene)
                    item["shot"] = None
                    by_index[i] = item
                    continue
                prep = prepare_capture(page, url)
                print(f"  🔧 {scene['veiculo']}: kind={prep.get('kind')} scroll={prep.get('scrolledTo')} click={prep.get('clicked')}")
                wait_for_styled_capture(page, timeout_ms=12000)
                # Injeta limpeza genérica de modais, overlays e banners no fallback
                try:
                    from scripts.screenshots.base import CLEANUP_CSS
                    page.add_style_tag(content=CLEANUP_CSS)
                except Exception:
                    pass
                if prep.get("kind") == "instagram" and instagram_is_login_wall(page):
                    print(f"  ⚠️  Instagram ainda em login-wall — cena sem screenshot")
                    item = dict(scene)
                    item["shot"] = None
                    by_index[i] = item
                    continue
                # paywall / adblock / interstitial: rola além do bloqueio
                try:
                    hints = page.evaluate(_PAYWALL_HINTS_JS)
                    if hints:
                        print(f"  🚧 {scene['veiculo']}: bloqueios={hints} — rolando além")
                        res = page.evaluate(_SCROLL_PAST_ADVERTS_JS, {"maxScrolls": 4})
                        page.wait_for_timeout(500)
                        if res.get("scrolled"):
                            prep["scrolledTo"] = f"past-adverts(+{res['scrolled']}px)"
                except Exception:
                    pass

                try:
                    from scripts.screenshots.base import _EXTRACT_HIGHLIGHT_BOX_JS
                    highlight_box = page.evaluate(_EXTRACT_HIGHLIGHT_BOX_JS)
                except Exception:
                    highlight_box = {"found": False, "x": 80, "y": 320, "w": 1000, "h": 70}

                page.screenshot(path=str(dest), full_page=False)
                if dest.exists() and dest.stat().st_size > MIN_SHOT_BYTES and not _shot_looks_blank(dest):
                    save_cached_screenshot(url, dest)
                    item = dict(scene)
                    item["shot"] = dest.name
                    item["highlight_box"] = highlight_box

                    # Versão longa (1800px) para simulação de rolagem real
                    dest_long = shot_dir / f"src-{i:02d}-long.png"
                    try:
                        page.set_viewport_size({"width": 1400, "height": 1800})
                        page.wait_for_timeout(350)
                        page.screenshot(path=str(dest_long), full_page=False)
                        if dest_long.exists() and dest_long.stat().st_size > MIN_SHOT_BYTES and not _shot_looks_blank(dest_long):
                            item["shot_long"] = dest_long.name
                            print(f"  📜 {scene['veiculo']} (longo): {dest_long.name} ({dest_long.stat().st_size // 1024} KB)")
                    except Exception:
                        pass

                    # Multi-Shot: captura detalhe intermediário (scroll no corpo da matéria)
                    dest_detail = shot_dir / f"src-{i:02d}-detail.png"
                    try:
                        page.set_viewport_size({"width": 1400, "height": 900})
                        page.evaluate("window.scrollBy(0, window.innerHeight * 0.75);")
                        page.wait_for_timeout(350)
                        page.screenshot(path=str(dest_detail), full_page=False)
                        if dest_detail.exists() and dest_detail.stat().st_size > MIN_SHOT_BYTES and not _shot_looks_blank(dest_detail):
                            item["shot_detail"] = dest_detail.name
                            print(f"  📸 {scene['veiculo']} (detalhe): {dest_detail.name} ({dest_detail.stat().st_size // 1024} KB)")
                            # Se dest_long falhou ou não existe, costura dest + dest_detail
                            if not item.get("shot_long"):
                                stitched = stitch_screenshots(dest, dest_detail, dest_long)
                                if stitched:
                                    item["shot_long"] = dest_long.name
                    except Exception:
                        pass

                    by_index[i] = item
                    print(f"  📸 {scene['veiculo']}: {dest.name} ({dest.stat().st_size // 1024} KB)")
                    continue
                print(f"  🚫 {scene['veiculo']}: screenshot em branco/pequena — tentando resgate via imagem da matéria (og:image)")
                record_broken_handler(
                    url=url,
                    handler_name="generic",
                    error_reason="blank_or_small_screenshot",
                    http_status=resp.status if resp else None,
                )
                dest.unlink(missing_ok=True)
                downloader = _get_download_article_image()
                if downloader and downloader(url, dest):
                    save_cached_screenshot(url, dest)
                    item = dict(scene)
                    item["shot"] = dest.name
                    item["video"] = None
                    by_index[i] = item
                    print(f"  🖼️  {scene['veiculo']}: resgatado com imagem editorial da matéria ({dest.stat().st_size // 1024} KB)")
                    continue
            except Exception as exc:
                print(f"  ⚠️  captura falhou / skip:blocked {url}: {exc}")
                record_broken_handler(
                    url=url,
                    handler_name="generic",
                    error_reason=str(exc),
                )
                downloader = _get_download_article_image()
                if downloader and downloader(url, dest):
                    save_cached_screenshot(url, dest)
                    item = dict(scene)
                    item["shot"] = dest.name
                    item["video"] = None
                    by_index[i] = item
                    print(f"  🖼️  {scene['veiculo']}: resgatado com imagem editorial da matéria ({dest.stat().st_size // 1024} KB)")
                    continue
            finally:
                try:
                    page.close()
                except Exception:
                    pass
            item = dict(scene)
            item["shot"] = None
            by_index[i] = item
        ctx.close()
        browser.close()
    assembled = _assemble_captured_scenes(scenes, by_index) or scenes
    try:
        shots_meta = {}
        for idx_k, itm in enumerate(assembled):
            shots_meta[str(idx_k)] = {
                "shot": itm.get("shot"),
                "shot_long": itm.get("shot_long"),
                "highlight_box": itm.get("highlight_box"),
                "url": itm.get("url"),
            }
        (shot_dir / "_shots_meta.json").write_text(json.dumps(shots_meta, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    return assembled


def record_mockup(
    video_id: str,
    episode: dict,
    audio: Path,
    scenes: list[dict],
    work: Path,
    wallpaper: Path | None = None,
    timeline_beats: list[Any] | None = None,
) -> Path:
    from playwright.sync_api import sync_playwright
    from bm_scene_timeline import build_scene_timeline

    rec_dir = work / "rec"
    rec_dir.mkdir(parents=True, exist_ok=True)
    server_dirs = [MOCKUP_DIR, work]
    if BROLL_DIR.is_dir():
        server_dirs.append(BROLL_DIR)
    httpd, port = start_server(server_dirs)
    try:
        dur = min(probe_duration_s(audio) or 60.0, MAX_DURATION_S)
        title = _unescape(episode.get("titulo") or "Brasil e Mundo")
        veiculo = episode.get("fonte_veiculo") or "Brasil e Mundo"
        ymd = episode_date(audio)
        subhead = one_line_subhead(episode)
        ticker_items = ticker_headlines(episode, video_id)
        if not scenes:
            scenes = [{"veiculo": veiculo, "url": "https://news.mob.tec.br", "shot": None}]

        if video_id:
            episode.setdefault("video_id", video_id)
        if not timeline_beats:
            timeline_beats = build_scene_timeline(episode, dur, scenes, BROLL_INDEX)
        stage_person_photo_assets(timeline_beats, work)
        try:
            from bm_video.shot_judge import evaluate_timeline_shots
            evaluate_timeline_shots(
                timeline_beats, scenes, work, episode, enable_semantic_veto=True
            )
        except Exception as _qa_exc:
            print(f"  ⚠️  Auditoria de shots (shot.qa.json) ignorada: {_qa_exc}")

        url = f"http://127.0.0.1:{port}/{MOCKUP_HTML}"
        raw_webm: Path | None = None
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                record_video_dir=str(rec_dir),
                record_video_size={"width": 1920, "height": 1080},
                device_scale_factor=1,
                locale="pt-BR",
            )
            page = ctx.new_page()

            first_beat = timeline_beats[0] if timeline_beats else None
            fb_v2 = _normalize_beat_v2(first_beat) if first_beat else {}
            first_shot = fb_v2.get("shot") or (scenes[0].get("shot") if scenes else None)
            first_vid = fb_v2.get("video") or (scenes[0].get("video") if scenes else None)
            first_url = _omnibox_url(
                fb_v2.get("url") or (scenes[0].get("url") if scenes else "")
            )
            first_kind = fb_v2.get("visual_component") or fb_v2.get("kind") or (scenes[0].get("kind") if scenes else "source")
            first_xpost = fb_v2.get("x_post") or (scenes[0].get("x_post") if scenes else None)

            init_payload = {
                "categoria": "BRASIL E MUNDO", "titulo": title, "resumo": subhead,
                "autor": "Peter Albuquerque", "data": ymd, "dataExtenso": ymd,
                "url": first_url,
                "eyebrow": f"VALE DA LIBERDADE • {veiculo.upper()}",
                "lowerTitle": title, "lowerSubtitle": subhead,
                "liveText": "B&M", "brandSub": "B&M", "tag": "VALE DA LIBERDADE",
                "ticker": ticker_items,
                "pageImage": f"/shots/{first_shot}" if first_shot else "",
                "shotLong": f"/shots/{fb_v2.get('shot_long')}" if fb_v2.get('shot_long') else (f"/shots/{first_shot}" if first_shot else ""),
                "highlightBox": fb_v2.get("highlight_box") or {},
                "pageVideo": first_vid or "",
                "wallpaper": f"/wallpaper/{quote(wallpaper.name)}" if wallpaper else "",
                "kind": first_kind,
                "visual_component": first_kind,
                "visual_variant": fb_v2.get("visual_variant") or "",
                "visual_payload": fb_v2.get("visual_payload") or {},
            }
            if first_xpost:
                init_payload["xPost"] = first_xpost
            # Injeta payload no runtime antes da renderização do HTML para
            # evitar qualquer flash de placeholder de exemplo no frame zero.
            # Playwright Python: add_init_script aceita UM único string —
            # serializa o payload embutido no corpo do script (fb4958f bug).
            import json as _json
            page.add_init_script(
                "window.__VDL_INITIAL_DATA__ = "
                + _json.dumps(init_payload, ensure_ascii=False)
                + ";"
            )
            # Query string no HTML estoura 404 no http.server (xauvz73KEpA).
            # Estado vai via add_init_script + VDL_MOCKUP.update.
            # pageVideo+CDN: nunca networkidle (FNTK1AJegxI).
            resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)
            status = getattr(resp, "status", None)
            if status is None or int(status) >= 400:
                raise RuntimeError(f"mockup {MOCKUP_HTML} HTTP {status} em {url}")
            page.wait_for_function("() => !!window.VDL_MOCKUP", timeout=10000)
            _safe_mockup_update(page, init_payload, label="init")
            # LT do HTML some na gravação. Overlay oficial (1576px, left 300)
            # entra no compose_presenter NA FRENTE do Peter. Sem isso o avatar
            # cobre o LT do mockup (L6BdCfuMVpQ).
            page.evaluate(
                """() => {
                  const el = document.querySelector('.lower-third-overlay');
                  if (el) el.style.setProperty('display', 'none', 'important');
                }"""
            )
            page.wait_for_function(
                """() => {
                  const w = document.getElementById('sceneWallpaper');
                  const s = document.getElementById('pageShot');
                  const ok = el => !el || el.hidden || el.complete !== false;
                  return ok(w) && ok(s);
                }""", timeout=10000,
            )
            page.wait_for_timeout(400)
            # Pré-carrega todas as imagens de shots no cache do Chromium antes de iniciar a gravação,
            # garantindo que as trocas de cena durante o vídeo sejam instantâneas sem latência HTTP.
            all_shot_urls = []
            for b_raw in (timeline_beats or []):
                b_item = _normalize_beat_v2(b_raw)
                s = b_item.get("shot")
                sl = b_item.get("shot_long")
                if s:
                    all_shot_urls.append(f"/shots/{s}")
                if sl:
                    all_shot_urls.append(f"/shots/{sl}")
            for sc in (scenes or []):
                s = sc.get("shot")
                sl = sc.get("shot_long")
                if s:
                    all_shot_urls.append(f"/shots/{s}")
                if sl:
                    all_shot_urls.append(f"/shots/{sl}")
            all_shot_urls = list(dict.fromkeys(all_shot_urls))
            if all_shot_urls:
                page.evaluate(
                    """async (urls) => {
                      await Promise.all(urls.map(u => new Promise(resolve => {
                        const img = new Image();
                        img.onload = async () => {
                          if (img.decode) {
                            try { await img.decode(); } catch(e) {}
                          }
                          resolve(true);
                        };
                        img.onerror = () => resolve(false);
                        img.src = u;
                      })));
                    }""",
                    all_shot_urls,
                )
            if timeline_beats:
                _safe_mockup_update(page, _build_mockup_update_payload(fb_v2), label="beat0_init")
            started = time.monotonic()

            for idx, beat in enumerate(timeline_beats):
                elapsed = time.monotonic() - started
                if elapsed >= dur:
                    break
                b = _normalize_beat_v2(beat)
                if idx > 0:
                    payload = _build_mockup_update_payload(b)
                    _safe_mockup_update(page, payload, label=f"beat{idx}")

                beat_dur = float(b.get("t1", 0.0)) - float(b.get("t0", 0.0))
                remain = dur - (time.monotonic() - started)
                wait_time = max(0.1, min(beat_dur, remain))
                page.wait_for_timeout(int(wait_time * 1000))

            raw_webm = Path(page.video.path())
            ctx.close()
            browser.close()
    finally:
        httpd.shutdown()

    if not raw_webm or not raw_webm.exists():
        raise RuntimeError("gravação do mockup não gerou webm")
    return raw_webm
