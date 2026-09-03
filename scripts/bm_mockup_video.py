#!/usr/bin/env python3
"""Gera vídeo BM com mockup-browser + sites reais das matérias e sobe no YouTube.

PIPELINE OFICIAL de vídeo BM desde 2026-08-22 (substitui HyperFrames).
Usado pelo cron hourly (bm-hourly-pipeline.sh) depois do process-queue.
Não misturar com bm_video_autopilot.py (aposentado).

Fluxo:
  1. lê especial-<id>.json + áudio BM
  2. captura screenshots das URLs em fonte_referencias (sem YouTube/self)
  3. grava o mockup-browser em 1920×1080 trocando cenas no ritmo do áudio
  4. muxa o MP3 do episódio
  5. opcional: upload público via youtube_uploader.py
"""
from __future__ import annotations

import argparse
import hashlib
import html as _html
import json
import os
import random
import re
import shlex
import shutil
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = ROOT / "scripts"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
MOCKUP_DIR = ROOT / "references" / "youtube" / "mockup-browser"
MOCKUP_HTML = "mockup-brower.html"  # typo histórico no arquivo
WALLPAPER_DIR = MOCKUP_DIR / "wallpaper"
BROLL_DIR = ROOT / "references" / "youtube" / "broll"
BROLL_INDEX = BROLL_DIR / "_index.json"
AVATAR_LOOP = (
    ROOT / "references" / "youtube" / "Apresentadores"
    / "Peter Albuquerque" / "Peter-Loop-Picsart-BackgroundRemover.mp4"
)
# Layout aprovado 2026-08-22 (v6): crop 1/18 esquerdo, escala 0.6, 1/7 abaixo.
# Spec canônica: docs/BM-VIDEO-LAYOUT.md + docs/bm-video-layout.json — não alterar estes
# números sem atualizar os dois docs.
AVATAR_CROP = "910:720:54:0"
AVATAR_SCALE = "546:432"
AVATAR_OVERLAY = "0:H-h+38"
APP_URL = "https://news.mob.tec.br"

# Screenshot com desvio padrão de luminância abaixo disso é considerada em
# branco/preto (página não renderizou, login-wall) e a cena é descartada.
BLANK_SHOT_STDDEV = float(os.environ.get("BM_BLANK_SHOT_STDDEV", "6.0"))
# Tamanho mínimo do PNG para valer como captura real.
MIN_SHOT_BYTES = int(os.environ.get("BM_MIN_SHOT_BYTES", "20000"))
EPS_DIR = ROOT / "output" / "brasil_e_mundo" / "episodes"
AUDIO_DIR = ROOT / "output" / "brasil_e_mundo" / "audio"
VIDEOS_OUT = ROOT / "output" / "videos"
STATE_PATH = ROOT / "output" / "brasil_e_mundo" / "videos_published.json"
WORK_ROOT = ROOT / "output" / "brasil_e_mundo" / "mockup_video"
CAPTURE_CACHE_DIR = ROOT / "output" / "brasil_e_mundo" / "capture-cache"
THUMB_DIRS = (ROOT / "thumbnails", ROOT / "public" / "thumbnails")

MAX_DURATION_S = 330.0
MAX_PER_RUN = 1
WINDOW_DAYS = 2
MAX_SCENES = 8
MAX_PER_HOST = 2
CACHE_MAX_AGE_HOURS = 36.0
# Invalida prints antigos (HTML sem CSS). Subir quando a captura mudar de novo.
CAPTURE_CACHE_VERSION = "handler-v3"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
FIXED_TAGS = ("Brasil e Mundo", "Vale da Liberdade", "notícias", "comentário")
DESC_TEMPLATE = (
    "{summary}\n\n"
    "Ouça no app: {app}\n\n"
    "{assista}"
    "Fontes:\n{refs}\n\n"
    "#BrasilEMundo #{tags}\n"
)

# Quantos vídeos anteriores recomendar no bloco "Assista também".
ASSISTA_TAMBEM_N = 2


def _unescape(s: str) -> str:
    return _html.unescape(s or "")


def _clean_url(u: str) -> str:
    u = (u or "").strip()
    if not u:
        return ""
    try:
        parts = urlsplit(u)
        qs = [
            (k, v)
            for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if not k.lower().startswith("utm_")
        ]
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(qs), parts.fragment))
    except Exception:
        return u


def domain_of(url: str) -> str:
    try:
        return (urlsplit(url or "").netloc or "").lower().removeprefix("www.")
    except Exception:
        return ""


def try_handler_screenshot(url: str, dest: Path, viewport: dict[str, int] | None = None) -> dict | None:
    """Captura via handler dedicado (ads/paywall). None = sem handler, usar Playwright genérico."""
    try:
        from scripts.screenshots.sites import get_scraper
        from scripts.screenshots.runner import capture as clean_capture
    except Exception:
        return None
    if get_scraper(domain_of(url)) is None:
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
        and dest.exists()
        and dest.stat().st_size > MIN_SHOT_BYTES
        and not _shot_looks_blank(dest)
    )


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


def is_blocked_source_url(url: str) -> bool:
    low = (url or "").lower()
    if not low.startswith("http"):
        return True
    return any(
        token in low
        for token in (
            "youtube.com",
            "youtu.be",
            "ancapsu",
            "news.mob.tec.br/ep/",
            "news.mob.tec.br/episodes/",
        )
    )


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
    return "generic"


_X_STATUS_RE = re.compile(r"(?:x|twitter)\.com/[^/]+/status/(\d+)")

_X_EMBED_WRAP = """<!doctype html><html><head><meta charset="utf-8">
<style>
 html,body{margin:0;height:100%;background:#15202b;
   display:flex;align-items:center;justify-content:center;
   font-family:system-ui,-apple-system,'Segoe UI',sans-serif}
 #box{width:640px;transform:scale(1.3);transform-origin:center center}
 iframe{width:100%;border:0;display:block}
</style></head><body>
<div id="box"><iframe id="tw"
 src="https://platform.twitter.com/embed/Tweet.html?id=__TWEET_ID__&theme=dark&dnt=true&lang=pt"
 scrolling="no" allowtransparency="true"></iframe></div>
<script>
 window.addEventListener('message', function(e){
   try{
     var d = JSON.parse(e.data);
     var p = d && d['twttr.embed'] && d['twttr.embed'].params;
     var h = p && p[0] && p[0].height;
     if(h){ document.getElementById('tw').style.height = h + 'px'; }
   }catch(_){}
 });
 setTimeout(function(){
   var f = document.getElementById('tw');
   if(!f.style.height){ f.style.height = '540px'; }
 }, 3000);
</script></body></html>"""


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


def extract_x_video(url: str, work: Path, video_id: str, idx: int) -> str | None:
    """Baixa o vídeo de um post do X (sem áudio é suficiente: mockup é mudo).
    Retorna caminho relativo ao server root ('/shots/...') ou None."""
    dest = work / "shots" / f"xvid-{video_id}-{idx:02d}.mp4"
    if dest.exists() and dest.stat().st_size > 50000:
        return f"/shots/{dest.name}"
    cmd = [
        "/home/osmar/.local/bin/yt-dlp", "-f", "bv*[height<=720]/b[height<=720]/b",
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


_PAYWALL_HINTS_JS = """() => {
  const t = (document.body ? document.body.innerText : '').toLowerCase();
  const hits = [];
  const pats = [
    ['paywall', /continue lendo|assine para continuar|subscribe to (continue|read)|conteúdo exclusivo para assinantes|acesso restrito a assinantes|faça sua assinatura|já é assinante/],
    ['adblock', /desative o adblock|disable your ad ?blocker|whitelist this site|permita os anúncios/],
    ['consent-wall', /escolha seu plano|select your plan|we value your privacy|nós valorizamos sua privacidade/],
    ['ad-interstitial', /publicidade|advertisement/i.test(document.querySelector('[id*="interstitial"], [class*="interstitial"]')?.innerText || '') && !!(document.querySelector('[id*="interstitial"], [class*="interstitial"]')?.offsetParent)],
  ];
  for (const [name, re] of pats) {
    try { if (re.test(t)) hits.push(name); } catch(e) {}
  }
  // paywall estrutural: conteúdo principal menor que o overlay
  try {
    const pay = document.querySelector('[class*="paywall"], [id*="paywall"], [class*="subscription-wall"]');
    if (pay && pay.offsetParent) hits.push('paywall-element');
  } catch(e) {}
  return hits;
}"""


# JS extra: rola além de ads/intersticiais e tenta posicionar em texto da matéria.
_SCROLL_PAST_ADVERTS_JS = """({maxScrolls}) => {
  let scrolled = 0;
  for (let i = 0; i < maxScrolls; i++) {
    const t = (document.body ? document.body.innerText : '').toLowerCase();
    const blocked =
      t.includes('assine para continuar') || t.includes('subscribe to continue') ||
      t.includes('conteúdo exclusivo para assinantes') || t.includes('desative o adblock') ||
      t.includes('disable your ad blocker');
    if (!blocked) break;
    window.scrollBy(0, window.innerHeight * 0.9);
    scrolled += Math.round(window.innerHeight * 0.9);
  }
  return Promise.resolve({scrolled});
}"""


# Cliques comuns de cookie / login-wall (ordem: específico → genérico).
_DISMISS_BUTTONS = (
    "button:has-text('Agora não')",
    "button:has-text('Agora Nao')",
    "div[role='button']:has-text('Agora não')",
    "div[role='button']:has-text('Not now')",
    "button:has-text('Not now')",
    "button:has-text('Not Now')",
    "div[role='button']:has-text('Not Now')",
    "button:has-text('Decline optional cookies')",
    "button:has-text('Recusar cookies opcionais')",
    "button:has-text('Only allow essential cookies')",
    "button:has-text('Aceitar')",
    "button:has-text('Aceito')",
    "button:has-text('Accept all')",
    "button:has-text('Accept')",
    "#onetrust-accept-btn-handler",
    "[aria-label='Close']",
    "[aria-label='Fechar']",
    "[aria-label='Dismiss']",
)

_PREPARE_JS = """({kind}) => {
  const hide = (el) => {
    if (!el) return;
    el.style.setProperty('display', 'none', 'important');
    el.style.setProperty('visibility', 'hidden', 'important');
    el.style.setProperty('pointer-events', 'none', 'important');
  };

  // Placeholders vazios (hero cinza da BBC / branco do G1 quando a imagem não carrega).
  document.querySelectorAll(
    'figure, picture, [data-testid="image"], [data-component="image-block"], .content-media, .content-featured-image, [class*="media-container"]'
  ).forEach(el => {
    const img = el.querySelector('img');
    const r = el.getBoundingClientRect();
    const emptyImg = !img || !img.naturalWidth;
    if (r.height > 80 && emptyImg) hide(el);
  });

  if (kind === 'instagram') {
    document.querySelectorAll('[role="dialog"], [role="presentation"]').forEach(el => {
      const t = (el.innerText || '').toLowerCase();
      if (t.includes('entrar') || t.includes('log in') || t.includes('sign up') || t.includes('inscreva')) {
        hide(el);
      }
    });
  }

  document.documentElement.style.overflow = 'auto';
  if (document.body) document.body.style.overflow = 'auto';

  const h1s = Array.from(document.querySelectorAll('h1')).sort(
    (a, b) => ((b.innerText || '').trim().length) - ((a.innerText || '').trim().length)
  );
  const h1 = h1s[0] || document.querySelector('[role="main"] h1, article h1');

  if (h1) {
    const ty = h1.getBoundingClientRect().top;
    document.querySelectorAll('div, figure, section, aside').forEach(el => {
      if (el.contains(h1) || h1.contains(el)) return;
      const r = el.getBoundingClientRect();
      if (r.height < 100 || r.width < 240) return;
      if (r.bottom <= 8 || r.top >= ty - 4) return;
      const txt = (el.innerText || '').trim();
      if (txt.length > 40) return;
      const img = el.querySelector('img');
      if (img && img.naturalWidth > 10) return;
      hide(el);
    });
  }

  let sticky = 0;
  document.querySelectorAll('header, nav, [class*="header"]').forEach(el => {
    const st = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    if ((st.position === 'fixed' || st.position === 'sticky') && r.top < 90 && r.height < 160) {
      sticky = Math.max(sticky, r.bottom);
    }
  });

  if (h1) {
    const y = h1.getBoundingClientRect().top + window.scrollY - sticky - 8;
    window.scrollTo(0, Math.max(0, y));
    return {scrolledTo: 'h1', y: Math.max(0, y), sticky, kind};
  }
  if (kind === 'bbc' || kind === 'g1') {
    const fallback = kind === 'g1' ? 360 : 280;
    window.scrollBy(0, fallback);
    return {scrolledTo: kind + '-fallback', y: fallback};
  }
  return {scrolledTo: 'none', y: 0};
}"""


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


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"videos": {}}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def probe_duration_s(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
    )
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def load_episode(video_id: str) -> dict:
    path = EPS_DIR / f"especial-{video_id}.json"
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_audio(video_id: str) -> Path | None:
    files = sorted(AUDIO_DIR.glob(f"{video_id}_*.mp3"), reverse=True)
    return files[0] if files else None


def episode_date(audio: Path) -> str:
    m = re.search(r"(\d{4}-\d{2}-\d{2})", audio.name)
    return m.group(1) if m else datetime.now().strftime("%Y-%m-%d")


def source_scenes(episode: dict, max_sources: int = MAX_SCENES) -> list[dict]:
    # 1. Identificar URLs citadas diretamente no roteiro (quoted_in / fala com fonte_url)
    quoted_urls: set[str] = set()
    for section in ("abertura", "desenvolvimento", "fechamento"):
        for item in episode.get(section) or []:
            fu = _clean_url(item.get("fonte_url") or "")
            if fu:
                quoted_urls.add(fu)

    # 2. Filtrar e classificar referências
    candidates: list[dict] = []
    seen: set[str] = set()

    for ref in episode.get("fonte_referencias") or []:
        if ref.get("self"):
            continue
        url = _clean_url(ref.get("url") or "")
        if not url or is_blocked_source_url(url) or url in seen:
            continue
        seen.add(url)
        veiculo = (ref.get("veiculo") or "").strip() or urlsplit(url).netloc
        role = ref.get("role", "supporting")
        is_quoted = (url in quoted_urls) or bool(ref.get("quoted_in"))

        # Peso para ordenação: quoted (0) -> primary (1) -> supporting (2) -> visual (3)
        if is_quoted:
            priority = 0
        elif role == "primary":
            priority = 1
        elif role == "supporting":
            priority = 2
        else:
            priority = 3

        candidates.append({
            "veiculo": veiculo,
            "url": url,
            "titulo": veiculo,
            "priority": priority,
            "role": role,
        })

    # Ordenar por prioridade
    candidates.sort(key=lambda x: x["priority"])

    # 3. Aplicar teto de 2 URLs por host e limite global de cenas
    scenes: list[dict] = []
    host_counts: dict[str, int] = {}

    for cand in candidates:
        dom = domain_of(cand["url"])
        if host_counts.get(dom, 0) >= MAX_PER_HOST:
            continue
        host_counts[dom] = host_counts.get(dom, 0) + 1
        scenes.append({
            "veiculo": cand["veiculo"],
            "url": cand["url"],
            "titulo": cand["titulo"],
        })
        if len(scenes) >= max_sources:
            break

    return scenes


def list_wallpapers() -> list[Path]:
    if not WALLPAPER_DIR.is_dir():
        return []
    out: list[Path] = []
    for p in sorted(WALLPAPER_DIR.iterdir(), key=lambda x: x.name.lower()):
        if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
            out.append(p)
    return out


def pick_wallpaper(video_id: str) -> Path | None:
    files = list_wallpapers()
    if not files:
        return None
    idx = int(hashlib.md5((video_id or "").encode("utf-8")).hexdigest(), 16) % len(files)
    return files[idx]


def episode_summary(episode: dict, limit: int = 380) -> str:
    chunks: list[str] = []
    for key in ("abertura", "desenvolvimento"):
        for block in episode.get(key) or []:
            t = _unescape((block.get("texto") or "").strip())
            if t:
                chunks.append(t)
            if sum(len(c) for c in chunks) > limit:
                break
        if chunks:
            break
    text = " ".join(chunks).strip()
    if not text:
        title = _unescape((episode.get("titulo") or "").strip())
        return f"Comentário de Peter Albuquerque sobre {title}." if title else ""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    for sep in (". ", "! ", "? "):
        i = cut.rfind(sep)
        if i > 120:
            return cut[: i + 1].strip()
    return cut.rsplit(" ", 1)[0].rstrip(",;") + "…"


def _clip_line(text: str, limit: int) -> str:
    s = re.sub(r"\s+", " ", (text or "")).strip()
    if len(s) <= limit:
        return s
    return s[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def one_line_subhead(episode: dict, limit: int = 98) -> str:
    """Linha fina: submanchete de uma linha, nunca o nome da fonte nem a fala de abertura do roteiro."""
    title = _unescape((episode.get("titulo") or "").strip())
    for key in ("subtitulo", "submanchete", "linha_fina", "subhead", "resumo"):
        v = _unescape(str(episode.get(key) or "")).strip()
        if v and v.casefold() != title.casefold():
            return _clip_line(v, limit)
    blob = episode_summary(episode, limit=240)
    sent = blob
    for sep in (". ", "? ", "! "):
        i = blob.find(sep)
        if 24 <= i <= 140:
            sent = blob[:i].strip()
            break
    if title and title.casefold() in sent.casefold()[: max(len(title), 12) + 8]:
        rest = blob[len(sent):].lstrip(".!? ").strip()
        if rest:
            sent = rest.split(". ")[0].split("? ")[0].strip()
    # Remove vícios de fala de abertura caso caia no texto do roteiro
    sent = re.sub(r"^(fala\s+pessoal|ol[áa]\s+a\s+todos|ol[áa]|bem-vindos|hoje\s+vamos\s+falar|neste\s+v[íi]deo|peter:\s*)[,.\s-]*", "", sent, flags=re.IGNORECASE).strip()
    if sent:
        sent = sent[0].upper() + sent[1:]
    return _clip_line(sent or title, limit)


def recent_headlines(exclude_id: str | None = None, limit: int = 6) -> list[str]:
    """Títulos dos especiais BM mais recentes (para o ticker)."""
    out: list[str] = []
    seen: set[str] = set()
    files = sorted(
        EPS_DIR.glob("especial-*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in files:
        vid = path.stem.removeprefix("especial-")
        if exclude_id and vid == exclude_id:
            continue
        try:
            ep = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        t = _unescape((ep.get("titulo") or "").strip())
        if not t:
            continue
        key = t.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(t.upper())
        if len(out) >= limit:
            break
    return out


def ticker_headlines(episode: dict, video_id: str | None = None) -> list[str]:
    current = _unescape((episode.get("titulo") or "").strip()).upper()
    items: list[str] = []
    seen: set[str] = set()
    for t in ([current] if current else []) + recent_headlines(exclude_id=video_id, limit=6):
        key = t.casefold()
        if not t or key in seen:
            continue
        seen.add(key)
        items.append(t)
        if len(items) >= 7:
            break
    return items or ["VALE DA LIBERDADE"]


def find_episode_thumbnail(video_id: str, ymd: str) -> Path | None:
    """Só a thumbnail YouTube amarrada no manifesto. Sem fallback para bm_*."""
    import episode_image_manifest as eim
    from youtube_thumbnail import generate_youtube_thumbnail
    try:
        return eim.resolve_youtube_thumbnail(video_id)
    except eim.YoutubeThumbnailError:
        pass
    except eim.EditorialImageError as exc:
        print(f"  ❌ editorial inválida — não envio thumbnail ao YouTube: {exc}")
        return None
    # editorial ok, mockup ainda não existe: tenta gerar agora (mesmo caminho da 4.6)
    try:
        result = generate_youtube_thumbnail(video_id, date=ymd)
        return Path(result["youtube_thumbnail_path"])
    except Exception as exc:  # noqa: BLE001
        print(f"  ❌ sem thumbnail YouTube válida para {video_id}: {exc}")
        return None


def build_chapters(scenes: list[dict], dur: float, timeline_beats: list[Any] | None = None) -> list[tuple[float, str]]:
    """Timestamps das cenas do mockup baseados na timeline calculada."""
    entries: list[tuple[float, str]] = []
    if timeline_beats:
        for beat in timeline_beats:
            b_dict = beat.to_dict() if hasattr(beat, "to_dict") else dict(beat)
            if b_dict.get("kind") == "broll":
                continue
            t0 = float(b_dict.get("t0", 0.0))
            label = (b_dict.get("veiculo") or "Fonte").strip()
            if label and label.lower() not in {"transição", "introdução"}:
                # Se for a primeira cena, posiciona com folga após introdução
                ts = t0 if t0 >= 10.0 else max(10.0, round(dur * 0.08))
                entries.append((ts, label))
        concl = max(entries[-1][0] + 10.0 if entries else 0.0, dur - min(20.0, dur * 0.15))
        entries.append((concl, "Conclusão"))
    else:
        n = max(len(scenes), 1)
        per = max(8.0, dur / n)
        t = 0.8
        for s in scenes:
            entries.append((t, (s.get("veiculo") or "Fonte").strip()))
            t += per
        concl = max(t, dur - min(20.0, dur * 0.15))
        entries.append((concl, "Conclusão"))

    # normaliza: Introdução sempre em 0:00, timestamps crescentes, >=10s entre capítulos
    out: list[tuple[float, str]] = [(0, "Introdução")]
    for ts, label in sorted(entries, key=lambda x: x[0]):
        if label == "Introdução" or ts < 8.0:
            continue
        ts = min(ts, max(dur - 1.0, 0.0))
        if out and ts - out[-1][0] < 10.0:
            continue
        out.append((round(ts), label))
    return out


def chapters_block(scenes: list[dict], dur: float, timeline_beats: list[Any] | None = None) -> str:
    ch = build_chapters(scenes, dur, timeline_beats=timeline_beats)
    if len(ch) < 3:
        return ""
    lines = ["", "⏱ CAPÍTULOS:", "0:00 Introdução"]
    for ts, label in ch[1:-1]:
        lines.append(f"{ts // 60:.0f}:{ts % 60:02d} {label}")
    last_ts, last_label = ch[-1]
    lines.append(f"{last_ts // 60:.0f}:{last_ts % 60:02d} {last_label}")
    return "\n".join(lines)


def _playlist_link(title: str, desc: str) -> tuple[str, str] | None:
    """Playlist temática oficial escolhida por choose_playlists (nome, url) ou None."""
    try:
        sys.path.insert(0, str(SCRIPT_DIR))
        from youtube_channel_policy import PLAYLIST_IDS, choose_playlists
    except Exception:  # noqa: BLE001
        return None
    decision = choose_playlists(title, desc)
    if not decision.names:
        return None
    name = decision.names[0]
    pid = PLAYLIST_IDS.get(name)
    if not pid:
        return None
    return name, f"https://www.youtube.com/playlist?list={pid}"


def build_assista_tambem(video_id: str, title: str, desc_for_playlist: str) -> str:
    """Bloco 'Assista também' com os últimos vídeos publicados + playlist temática.

    Fonte: videos_published.json (state local). Títulos vêm do próprio state
    ('title', gravado no save_state) com fallback para o JSON do episódio.
    Nenhuma chamada de API — dados 100% locais.
    """
    lines: list[str] = []
    try:
        videos = load_state().get("videos", {})
    except Exception:  # noqa: BLE001
        videos = {}
    # Ordena por published_at desc, exclui o vídeo atual e entradas sem yt_id.
    cands = [
        (vid, meta)
        for vid, meta in videos.items()
        if vid != video_id and meta.get("yt_id")
    ]
    cands.sort(key=lambda kv: kv[1].get("published_at") or "", reverse=True)
    for vid, meta in cands[:ASSISTA_TAMBEM_N]:
        rec_title = (meta.get("title") or "").strip()
        if not rec_title:
            try:
                rec_title = _unescape((load_episode(vid).get("titulo") or "").strip())
            except Exception:  # noqa: BLE001
                rec_title = ""
        rec_title = rec_title or "Comentário anterior"
        yt = meta.get("yt_id")
        lines.append(f"▶️ {rec_title}: https://youtu.be/{yt}")
    pl = _playlist_link(title, desc_for_playlist)
    if pl:
        lines.append(f"▶️ Playlist {pl[0]}: {pl[1]}")
    if not lines:
        return ""
    return "🔥 ASSISTA TAMBÉM:\n" + "\n".join(lines) + "\n\n"


def build_metadata(
    video_id: str,
    episode: dict,
    audio: Path,
    scenes: list[dict] | None = None,
    timeline_beats: list[Any] | None = None,
) -> tuple[str, str, list[str]]:
    title = _unescape((episode.get("titulo") or "").strip()) or f"Brasil & Mundo — Comentário ({video_id})"
    tags = list(FIXED_TAGS)
    tags.extend(episode.get("tags") or [])
    veiculo = episode.get("fonte_veiculo") or ""
    refs_ok: list[str] = []
    for r in episode.get("fonte_referencias") or []:
        ru = _clean_url(r.get("url") or "")
        rv = (r.get("veiculo") or "").strip()
        if not ru or is_blocked_source_url(ru) or r.get("self"):
            continue
        refs_ok.append(f"{rv}: {ru}" if rv else ru)
    ymd = episode_date(audio)
    summary = episode_summary(episode)
    if not summary:
        y, mo, d = ymd.split("-")
        summary = f"Comentário de {d}/{mo}/{y} sobre {veiculo or 'a pauta do dia'}."
    assista = build_assista_tambem(video_id, title, summary)
    desc = DESC_TEMPLATE.format(
        summary=summary,
        app=APP_URL,
        assista=assista,
        refs="\n".join(refs_ok) if refs_ok else "—",
        tags=" ".join(t.replace(" ", "") for t in tags if t),
    )
    if scenes or timeline_beats:
        desc += chapters_block(scenes or [], probe_duration_s(audio) or 0.0, timeline_beats=timeline_beats)
    seen: set[str] = set()
    uniq: list[str] = []
    for t in tags:
        t = _unescape(str(t)).strip()
        if t and t.lower() not in seen:
            seen.add(t.lower())
            uniq.append(t)
    return title, desc, uniq


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


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


def start_server(directories: list[Path]) -> tuple[ThreadingHTTPServer, int]:
    port = _free_port()

    def factory(*a, **k):
        return _Handler(*a, directories=directories, **k)

    httpd = ThreadingHTTPServer(("127.0.0.1", port), factory)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd, port


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


_BLOCK_TEXT_MARKERS = (
    "access denied",
    "you don't have permission to access",
    "voce nao tem permissao",
    "acesso restrito",
    "errors.edgesuite.net",
    "request blocked",
    "attention required",
    "just a moment",
    "are you a robot",
    "perimeterx",
    "http error 403",
    "403 forbidden",
    "temporarily offline",
)


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


_WAIT_STYLED_JS = """() => {
  if (document.readyState !== 'complete') return false;
  const sheets = document.styleSheets;
  if (!sheets || sheets.length === 0) return false;
  let cssOk = false;
  for (const s of sheets) {
    try {
      if (s.cssRules && s.cssRules.length > 0) { cssOk = true; break; }
    } catch (e) {
      cssOk = true; // CSS cross-origin já aplicado no layout
      break;
    }
  }
  if (!cssOk) return false;
  const imgs = [...document.images].filter((im) => {
    const r = im.getBoundingClientRect();
    return r.width >= 60 && r.height >= 40 && r.bottom > 0 && r.top < innerHeight + 200;
  });
  if (imgs.length === 0) return true;
  const loaded = imgs.filter((im) => im.complete && im.naturalWidth > 0);
  return loaded.length >= Math.min(imgs.length, 2) || loaded.length >= 1;
}"""


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
            out.append(by_index[i])
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
        if host_kind(url) in ("x", "instagram"):
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
                by_index[i] = item
                print(
                    f"  📸 {scene['veiculo']}: {dest.name} "
                    f"({dest.stat().st_size // 1024} KB, handler={handler_name})"
                )
                continue
            print(
                f"  ↪️  {scene['veiculo']}: handler={handler_name} falhou "
                f"({handler_result.get('error') or handler_result.get('http_status')}) "
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
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
            },
        )
        page = ctx.new_page()
        try:
            from playwright_stealth import Stealth

            Stealth().apply_stealth_sync(page)
        except Exception:  # noqa: BLE001
            pass
        last_domain = ""

        for i, scene, dest in to_fetch:
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

            try:
                # X com vídeo embutido: baixa o clipe em vez de screenshot estático
                if host_kind(url) == "x":
                    vid_rel = extract_x_video(url, shot_dir.parent, shot_dir.parent.name, i)
                    if vid_rel:
                        item = dict(scene)
                        item["shot"] = None
                        item["video"] = vid_rel
                        by_index[i] = item
                        continue
                    # sem vídeo: x.com dá 403 em headless, então usa o embed público
                    if capture_x_embed(page, url, dest):
                        save_cached_screenshot(url, dest)
                        item = dict(scene)
                        item["shot"] = dest.name
                        by_index[i] = item
                        print(f"  🐦 {scene['veiculo']}: {dest.name} ({dest.stat().st_size // 1024} KB, embed)")
                        continue
                    item = dict(scene)
                    item["shot"] = None
                    by_index[i] = item
                    continue
                resp = page.goto(url, wait_until="load", timeout=45000)
                wait_for_styled_capture(page)
                blocked = page_looks_blocked(page, resp.status if resp else None)
                if blocked:
                    print(f"  🚫 {scene['veiculo']}: bloqueio antibot ({blocked}) — cena descartada")
                    item = dict(scene)
                    item["shot"] = None
                    by_index[i] = item
                    continue
                prep = prepare_capture(page, url)
                print(f"  🔧 {scene['veiculo']}: kind={prep.get('kind')} scroll={prep.get('scrolledTo')} click={prep.get('clicked')}")
                wait_for_styled_capture(page, timeout_ms=12000)
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
                page.screenshot(path=str(dest), full_page=False)
                if dest.exists() and dest.stat().st_size > MIN_SHOT_BYTES and not _shot_looks_blank(dest):
                    save_cached_screenshot(url, dest)
                    item = dict(scene)
                    item["shot"] = dest.name
                    by_index[i] = item
                    print(f"  📸 {scene['veiculo']}: {dest.name} ({dest.stat().st_size // 1024} KB)")
                    continue
                print(f"  🚫 {scene['veiculo']}: screenshot em branco/pequena — cena descartada")
                dest.unlink(missing_ok=True)
            except Exception as exc:
                print(f"  ⚠️  captura falhou / skip:blocked {url}: {exc}")
            item = dict(scene)
            item["shot"] = None
            by_index[i] = item
        ctx.close()
        browser.close()
    return _assemble_captured_scenes(scenes, by_index) or scenes


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

        if not timeline_beats:
            timeline_beats = build_scene_timeline(episode, dur, scenes, BROLL_INDEX)

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

            def _qs_payload(payload: dict) -> str:
                from urllib.parse import quote as _q
                ticker = "|".join(payload.get("ticker") or [])
                pairs = {
                    "categoria": payload["categoria"], "titulo": payload["titulo"],
                    "resumo": payload["resumo"], "autor": payload["autor"],
                    "data": payload["data"], "dataExtenso": payload["dataExtenso"],
                    "url": payload["url"], "eyebrow": payload["eyebrow"],
                    "lowerTitle": payload["lowerTitle"], "lowerSubtitle": payload["lowerSubtitle"],
                    "live": payload["liveText"], "brandSub": payload["brandSub"],
                    "tag": payload["tag"], "ticker": ticker,
                }
                if payload.get("pageImage"):
                    pairs["pageImage"] = payload["pageImage"]
                if payload.get("pageVideo"):
                    pairs["pageVideo"] = payload["pageVideo"]
                if payload.get("wallpaper"):
                    pairs["wallpaper"] = payload["wallpaper"]
                return "&".join(f"{k}={_q(str(v))}" for k, v in pairs.items())

            first_beat = timeline_beats[0] if timeline_beats else None
            fb_dict = first_beat.to_dict() if hasattr(first_beat, "to_dict") else (dict(first_beat) if first_beat else {})
            first_shot = fb_dict.get("shot") or (scenes[0].get("shot") if scenes else None)
            first_vid = fb_dict.get("video") or (scenes[0].get("video") if scenes else None)
            first_url = fb_dict.get("url") or (scenes[0].get("url") if scenes else "https://news.mob.tec.br")

            init_payload = {
                "categoria": "BRASIL E MUNDO", "titulo": title, "resumo": subhead,
                "autor": "Peter Albuquerque", "data": ymd, "dataExtenso": ymd,
                "url": first_url or "https://news.mob.tec.br",
                "eyebrow": f"VALE DA LIBERDADE • {veiculo.upper()}",
                "lowerTitle": title, "lowerSubtitle": subhead,
                "liveText": "B&M", "brandSub": "B&M", "tag": "VALE DA LIBERDADE",
                "ticker": ticker_items,
                "pageImage": f"/shots/{first_shot}" if first_shot else "",
                "pageVideo": first_vid or "",
                "wallpaper": f"/wallpaper/{quote(wallpaper.name)}" if wallpaper else "",
            }
            page.goto(f"{url}?{_qs_payload(init_payload)}", wait_until="networkidle", timeout=45000)
            page.wait_for_function(
                """() => {
                  const w = document.getElementById('sceneWallpaper');
                  const s = document.getElementById('pageShot');
                  const ok = el => !el || el.hidden || el.complete !== false;
                  return ok(w) && ok(s);
                }""", timeout=10000,
            )
            page.wait_for_timeout(400)
            started = time.monotonic()

            for idx, beat in enumerate(timeline_beats):
                elapsed = time.monotonic() - started
                if elapsed >= dur:
                    break
                b = beat.to_dict() if hasattr(beat, "to_dict") else dict(beat)
                if idx > 0:
                    page_image = f"/shots/{b['shot']}" if b.get("shot") else ""
                    page_video = b.get("video") or ""
                    if b.get("kind") == "broll" and b.get("broll_file"):
                        page_video = f"/broll/{quote(b['broll_file'])}"
                    page.evaluate(
                        """({url, pageImage, pageVideo}) => {
                          if (!window.VDL_MOCKUP) return;
                          window.VDL_MOCKUP.update({url, pageImage, pageVideo});
                        }""",
                        {"url": b.get("url") or "https://news.mob.tec.br", "pageImage": page_image, "pageVideo": page_video},
                    )

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


RENDER_NODE = "/dev/dri/renderD128"


def _run_ffmpeg(cmd: list[str]) -> subprocess.CompletedProcess:
    """Roda ffmpeg; se a sessão ainda não tem grupo render, usa sg."""
    env = os.environ.copy()
    env.setdefault("LIBVA_DRIVER_NAME", "iHD")
    if os.access(RENDER_NODE, os.R_OK | os.W_OK):
        return subprocess.run(cmd, capture_output=True, text=True, env=env)
    inner = " ".join(shlex.quote(c) for c in cmd)
    return subprocess.run(
        ["sg", "render", "-c", inner],
        capture_output=True,
        text=True,
        env=env,
    )


def mux_video(raw: Path, audio: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    # HD 630: h264_qsv (libvpl) falha com MFX -9 neste ffmpeg.
    # Encode real é VA-API (iHD EncSliceLP) + fallback CPU.
    cmd_hw = [
        "ffmpeg", "-y",
        "-vaapi_device", RENDER_NODE,
        "-i", str(raw),
        "-i", str(audio),
        "-vf", "format=nv12,hwupload",
        "-c:v", "h264_vaapi", "-qp", "20",
        "-c:a", "aac", "-b:a", "192k", "-ac", "2",
        "-shortest",
        "-movflags", "+faststart",
        str(dest),
    ]
    r = _run_ffmpeg(cmd_hw)
    if r.returncode == 0 and dest.exists() and dest.stat().st_size > 0:
        print("  ⚡ muxing acelerado por hardware Intel VA-API (h264_vaapi)")
        return dest

    print(f"  ℹ️  h264_vaapi indisponível; fallback libx264: {(r.stderr or '')[-180:].strip()}")
    cmd_cpu = [
        "ffmpeg", "-y",
        "-i", str(raw),
        "-i", str(audio),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-ac", "2",
        "-shortest", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(dest),
    ]
    r = subprocess.run(cmd_cpu, capture_output=True, text=True)
    if r.returncode != 0 or not dest.exists():
        raise RuntimeError(r.stderr[-800:] if r.stderr else "ffmpeg falhou")
    return dest


def compose_presenter(base_mp4: Path, episode: dict, audio: Path, work: Path) -> Path:
    """Sobre o mockup: avatar aprovado + lower third na frente. Falha não derruba o mp4 base."""
    if not AVATAR_LOOP.is_file():
        print("  ⚠️  avatar loop ausente — segue sem apresentador")
        return base_mp4
    dest = base_mp4.with_name(base_mp4.stem + "-onair.mp4")
    l3_path = work / "lower-third.webm"
    try:
        from faceless_lower_third import clip_payload, date_from_audio, render_lower_third

        title = _unescape(episode.get("titulo") or "Brasil e Mundo")
        subhead = one_line_subhead(episode)
        vid = work.name if work.name else None
        headlines = ticker_headlines(episode, vid)
        payload = clip_payload(
            {
                "veiculo": episode.get("fonte_veiculo") or "Brasil e Mundo",
                "url": APP_URL,
                "line": title,
            },
            episode_title=title,
            date=date_from_audio(str(audio)) or episode_date(audio),
            kind="bm",
            subtitle=subhead,
            ticker=headlines,
        )
        render_lower_third(l3_path, payload, seconds=12.0)
    except Exception as exc:
        print(f"  ⚠️  lower-third falhou ({exc}); overlay só do avatar")
        l3_path = None

    vf_avatar = (
        f"[1:v]crop={AVATAR_CROP},format=rgba,"
        f"colorkey=0x007E00:0.10:0.03,lut=a='if(lt(val\\,230)\\,0\\,255)',"
        f"scale={AVATAR_SCALE}:flags=lanczos[av];"
        f"[0:v][av]overlay={AVATAR_OVERLAY}:format=auto:shortest=1"
    )
    inputs = ["-i", str(base_mp4), "-stream_loop", "-1", "-i", str(AVATAR_LOOP)]
    if l3_path and l3_path.is_file():
        inputs += ["-stream_loop", "-1", "-i", str(l3_path)]
        filter_complex = (
            vf_avatar + "[base];"
            "[2:v]format=yuva444p,colorkey=0x00FF00:0.10:0.22,"
            "despill=type=green:mix=0.45:expand=0[l3];"
            "[base][l3]overlay=0:0:shortest=1,format=yuv420p[v]"
        )
    else:
        filter_complex = vf_avatar + ",format=yuv420p[v]"

    hw_fc = filter_complex.replace("format=yuv420p[v]", "format=nv12,hwupload[v]")
    cmd_hw = [
        "ffmpeg", "-y",
        "-vaapi_device", RENDER_NODE,
        *inputs,
        "-filter_complex", hw_fc,
        "-map", "[v]", "-map", "0:a",
        "-c:v", "h264_vaapi", "-qp", "20",
        "-c:a", "copy",
        "-movflags", "+faststart",
        str(dest),
    ]
    r = _run_ffmpeg(cmd_hw)
    if r.returncode == 0 and dest.exists() and dest.stat().st_size > 0:
        print(f"  ⚡ apresentador acelerado por hardware Intel VA-API ({dest.stat().st_size // 1024} KB)")
        return dest

    cmd_cpu = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "0:a",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
        "-c:a", "copy",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(dest),
    ]
    r = subprocess.run(cmd_cpu, capture_output=True, text=True)
    if r.returncode != 0 or not dest.exists():
        print(f"  ⚠️  compose apresentador falhou; usa mockup puro: {(r.stderr or '')[-300:]}")
        return base_mp4
    print(f"  ✅ apresentador {dest.name} ({dest.stat().st_size // 1024} KB)")
    return dest


def set_youtube_thumbnail(yt_id: str, image: Path) -> bool:
    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "youtube_uploader.py"),
        "thumbnail",
        "--video-id", yt_id,
        "--image", str(image),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        print(f"  ⚠️  thumbnail: {(r.stderr or r.stdout or '')[-240:]}")
        return False
    print(f"  ✅ thumbnail {image.name}")
    return True


def publish_youtube(
    mp4: Path,
    title: str,
    desc: str,
    tags: list[str],
    privacy: str,
    *,
    publish_at: str | None = None,
    localizations_file: Path | None = None,
) -> str:
    up = [
        sys.executable,
        str(SCRIPT_DIR / "youtube_uploader.py"),
        "upload",
        "--file", str(mp4),
        "--title", title[:100],
        "--description", desc,
        "--tags", ", ".join(tags),
        "--privacy", privacy,
        "--default-lang", "pt-BR",
    ]
    if publish_at:
        up.extend(["--publish-at", publish_at])
    if localizations_file and localizations_file.exists():
        up.extend(["--localizations-file", str(localizations_file)])
    r = subprocess.run(up, capture_output=True, text=True, timeout=1800)
    out = (r.stdout or "") + (r.stderr or "")
    if r.returncode != 0:
        raise RuntimeError(out[-800:])
    m = re.search(r"ID:\s*([A-Za-z0-9_-]{6,})", out)
    if not m:
        raise RuntimeError(f"upload sem ID:\n{out[-400:]}")
    return m.group(1)


def _previous_published(video_id: str) -> dict | None:
    """Vídeo publicado imediatamente anterior (por published_at desc), com yt_id e título."""
    try:
        videos = load_state().get("videos", {})
    except Exception:  # noqa: BLE001
        return None
    cands = [
        (vid, meta)
        for vid, meta in videos.items()
        if vid != video_id and meta.get("yt_id")
    ]
    if not cands:
        return None
    cands.sort(key=lambda kv: kv[1].get("published_at") or "", reverse=True)
    vid, meta = cands[0]
    title = (meta.get("title") or "").strip()
    if not title:
        try:
            title = _unescape((load_episode(vid).get("titulo") or "").strip())
        except Exception:  # noqa: BLE001
            title = ""
    return {"yt_id": meta["yt_id"], "title": title or "nosso especial anterior"}


def post_channel_cross_comment(yt_id: str, prev: dict) -> bool:
    """Posta o primeiro comentário do canal com gancho para o vídeo anterior.

    Não-bloqueante por design (chamador ignora retorno). A API v3 NÃO fixa
    comentários — só o Studio faz o pin; avisamos no log.
    """
    text = (
        f"👉 Gostou da análise? Veja também nosso especial: "
        f"https://youtu.be/{prev['yt_id']} — {prev['title']}"
    )
    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "youtube_uploader.py"),
        "comment",
        "--video-id", yt_id,
        "--text", text,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except Exception as exc:  # noqa: BLE001
        print(f"  ⚠️  comentário do canal falhou: {exc}")
        return False
    if r.returncode != 0:
        print(f"  ⚠️  comentário do canal: {(r.stderr or r.stdout or '')[-240:]}")
        return False
    print("  ✅ comentário do canal postado (fixar/destacar é manual no Studio)")
    return True


def sync_dynamic_playlist_action(yt_id: str) -> bool:
    """Sincroniza o vídeo na playlist dinâmica rotativa ('Últimas Notícias').

    Não-bloqueante por design (chamador ignora retorno).
    """
    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "youtube_uploader.py"),
        "sync-dynamic-playlist",
        "--video-id", yt_id,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except Exception as exc:  # noqa: BLE001
        print(f"  ⚠️  playlist dinâmica falhou: {exc}")
        return False
    if r.returncode != 0:
        print(f"  ⚠️  playlist dinâmica: {(r.stderr or r.stdout or '')[-240:]}")
        return False
    print(f"  ✅ playlist dinâmica sincronizada para {yt_id}")
    return True


def process_one(video_id: str, upload: bool, privacy: str, dry_run: bool, force: bool = False) -> dict:
    episode = load_episode(video_id)
    if episode.get("_skip_video_reason") and not force:
        print(f"  ⏭️  Vídeo pulado: {episode['_skip_video_reason']}")
        return {"video_id": video_id, "skipped": True, "reason": episode["_skip_video_reason"]}
    if episode.get("_skip_video_reason") and force:
        print(f"  ⚠️  Forçando geração (skip original: {episode['_skip_video_reason']})")

    audio = resolve_audio(video_id)
    if not audio:
        raise FileNotFoundError(f"áudio BM não encontrado para {video_id}")
    dur = probe_duration_s(audio)
    if dur > MAX_DURATION_S:
        raise RuntimeError(f"{video_id}: áudio {dur:.0f}s > {MAX_DURATION_S:.0f}s — pulado")

    scenes = source_scenes(episode, max_sources=MAX_SCENES)
    wallpaper = pick_wallpaper(video_id)

    from bm_scene_timeline import build_scene_timeline
    timeline_beats = build_scene_timeline(episode, dur, scenes, BROLL_INDEX)

    title, desc, tags = build_metadata(video_id, episode, audio, scenes=scenes, timeline_beats=timeline_beats)
    print(f"🎬 {video_id} · {dur:.0f}s · {title}")
    print(f"   fontes: {len(scenes)} (beats: {len(timeline_beats)}) · upload={upload} privacy={privacy}")
    if wallpaper:
        print(f"   wallpaper: {wallpaper.name}")
    if dry_run:
        return {
            "video_id": video_id,
            "title": title,
            "scenes": scenes,
            "beats": [b.to_dict() for b in timeline_beats],
            "wallpaper": wallpaper.name if wallpaper else None,
            "thumb": str(find_episode_thumbnail(video_id, episode_date(audio)) or ""),
            "desc": desc,
            "dry_run": True,
        }

    work = WORK_ROOT / video_id
    shots = work / "shots"
    if work.exists():
        # recicla só o rec; screenshots podem ser reaproveitadas
        rec = work / "rec"
        if rec.exists():
            for p in rec.glob("*"):
                p.unlink()
    shots.mkdir(parents=True, exist_ok=True)
    captured = capture_sources(scenes, shots) if scenes else []

    # Descarta cenas mortas: captura falhou (sem screenshot E sem vídeo).
    # Sem esse filtro elas continuavam ocupando 8s+ da timeline exibindo o
    # browser vazio — era o "frame preto/escuro travado" reportado.
    usable = [c for c in captured if c.get("shot") or c.get("video")]
    dropped = len(captured) - len(usable)
    if dropped:
        for c in captured:
            if not (c.get("shot") or c.get("video")):
                print(f"  🚫 cena descartada (captura falhou): {c.get('veiculo')} · {c.get('url')}")
    if not usable:
        usable = [{
            "veiculo": episode.get("fonte_veiculo") or "Vale da Liberdade",
            "url": APP_URL,
            "titulo": episode.get("titulo") or "",
            "shot": None,
            "video": None,
        }]

    # Recalcula timeline só com as cenas que têm imagem/vídeo de verdade
    timeline_beats = build_scene_timeline(episode, dur, usable, BROLL_INDEX)
    raw = record_mockup(video_id, episode, audio, usable, work, wallpaper=wallpaper, timeline_beats=timeline_beats)
    mp4 = VIDEOS_OUT / f"especial-{video_id}-mockup.mp4"
    mux_video(raw, audio, mp4)
    print(f"  ✅ mp4 {mp4} ({mp4.stat().st_size // 1024} KB)")
    mp4 = compose_presenter(mp4, episode, audio, work)

    result = {
        "video_id": video_id,
        "title": title,
        "mp4": str(mp4),
        "scenes": len(captured or scenes),
    }
    if upload:
        # 1. Gera localizações EN/ES antecipadamente para embutir no insert (custo de cota ZERO)
        localizations_file: Path | None = None
        loc_embedded = False
        try:
            from youtube_captions import translate_title_desc_multi
            locs = translate_title_desc_multi(title, desc)
            if locs:
                loc_path = work / "localizations.json"
                loc_path.write_text(json.dumps(locs, ensure_ascii=False, indent=2), encoding="utf-8")
                localizations_file = loc_path
                loc_embedded = True
                print(f"  🌐 localizações EN/ES prontas para embutir no insert")
        except Exception as exc:  # noqa: BLE001
            print(f"  ⚠️  geração de localizações pré-insert falhou: {exc}")

        # 2. Agendamento inteligente no próximo slot se privacy == public (desativado: envio imediato)
        publish_at: str | None = None
        if privacy == "public":
            try:
                from youtube_channel_policy import next_publication_slot
                publish_at = next_publication_slot()
                if publish_at:
                    print(f"  📅 agendado para o próximo slot: {publish_at}")
                else:
                    print(f"  🚀 publicação imediata (status={privacy})")
            except Exception as exc:  # noqa: BLE001
                print(f"  ⚠️  cálculo de slot falhou: {exc}")

        yt_id = publish_youtube(
            mp4,
            title,
            desc,
            tags,
            privacy,
            publish_at=publish_at,
            localizations_file=localizations_file,
        )
        result["yt_id"] = yt_id
        result["url"] = f"https://youtu.be/{yt_id}"
        if publish_at:
            result["publish_at"] = publish_at
        thumb = find_episode_thumbnail(video_id, episode_date(audio))
        if thumb:
            set_youtube_thumbnail(yt_id, thumb)
        else:
            print("  ⚠️  sem thumbnail YouTube do episódio")
        try:
            from youtube_captions import attach_captions_and_en
            attach_captions_and_en(
                video_id,
                yt_id,
                audio,
                title,
                desc,
                localizations_embedded=loc_embedded,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  ⚠️  legendas/EN falharam (vídeo já no ar): {exc}")

        # Sincronização da playlist dinâmica "Últimas Notícias"
        # Não-bloqueante: falha aqui não derruba o pipeline nem o vídeo já publicado.
        try:
            sync_dynamic_playlist_action(yt_id)
        except Exception as exc:  # noqa: BLE001
            print(f"  ⚠️  playlist dinâmica falhou (vídeo já no ar): {exc}")

        # Comentário do canal com gancho para o vídeo anterior (tráfego cruzado).
        # Não-bloqueante: falha aqui não derruba o pipeline nem o vídeo já publicado.
        prev = _previous_published(video_id)
        if prev:
            post_channel_cross_comment(yt_id, prev)
        state = load_state()
        state.setdefault("videos", {})[video_id] = {
            "yt_id": yt_id,
            "url": result["url"],
            "title": title,
            "mp4": str(mp4),
            "data": episode_date(audio),
            "published_at": datetime.now().isoformat(),
            "publish_at": publish_at,
            "engine": "mockup-browser",
            "wallpaper": wallpaper.name if wallpaper else None,
        }
        save_state(state)
        print(f"  ✅ YouTube {result['url']}")
    return result


def pending_ids(days: int, backfill: bool) -> list[str]:
    state = load_state()
    seen = set((state.get("videos") or {}).keys()) | set((state.get("blocked") or {}).keys())
    cutoff = datetime.now() - timedelta(days=days)
    pending: list[str] = []
    for audio in sorted(AUDIO_DIR.glob("*.mp3"), key=lambda p: p.stat().st_mtime, reverse=True):
        if audio.name.startswith("teste-") or "_ruido" in audio.name:
            continue
        m = re.match(r"^([A-Za-z0-9_-]{6,})_(\d{4}-\d{2}-\d{2})\.mp3$", audio.name)
        if not m:
            continue
        vid = m.group(1)
        if vid in seen or vid in pending:
            continue
        if not backfill and datetime.fromtimestamp(audio.stat().st_mtime) < cutoff:
            continue
        if not (EPS_DIR / f"especial-{vid}.json").exists():
            continue
        if probe_duration_s(audio) > MAX_DURATION_S:
            continue
        pending.append(vid)
    return pending


def main() -> int:
    ap = argparse.ArgumentParser(description="Vídeo BM com mockup-browser + upload YouTube")
    ap.add_argument("--video-id", default=None)
    ap.add_argument("--pending", action="store_true", help="Processa pendentes da janela")
    ap.add_argument("--days", type=int, default=WINDOW_DAYS)
    ap.add_argument("--max", type=int, default=MAX_PER_RUN)
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--upload", action="store_true")
    ap.add_argument("--privacy", default="public", choices=["unlisted", "private", "public"])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="Gera vídeo mesmo se _skip_video_reason")
    args = ap.parse_args()

    ids = [args.video_id] if args.video_id else (pending_ids(args.days, args.backfill) if args.pending else [])
    if not ids:
        print("✅ Nenhum episódio BM pendente para vídeo mockup.")
        return 0
    print(f"📋 {len(ids)} candidato(s): {', '.join(ids[:8])}")
    n_ok = 0
    last_err = None
    for vid in ids:
        try:
            process_one(vid, upload=args.upload, privacy=args.privacy, dry_run=args.dry_run, force=args.force)
            n_ok += 1
        except Exception as exc:
            last_err = exc
            print(f"  ❌ {vid}: {exc}")
        if n_ok >= args.max:
            break
    if n_ok == 0 and last_err:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
