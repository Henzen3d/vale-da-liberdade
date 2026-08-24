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
import re
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
MOCKUP_DIR = ROOT / "references" / "youtube" / "mockup-browser"
MOCKUP_HTML = "mockup-brower.html"  # typo histórico no arquivo
WALLPAPER_DIR = MOCKUP_DIR / "wallpaper"
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
EPS_DIR = ROOT / "output" / "brasil_e_mundo" / "episodes"
AUDIO_DIR = ROOT / "output" / "brasil_e_mundo" / "audio"
VIDEOS_OUT = ROOT / "output" / "videos"
STATE_PATH = ROOT / "output" / "brasil_e_mundo" / "videos_published.json"
WORK_ROOT = ROOT / "output" / "brasil_e_mundo" / "mockup_video"
THUMB_DIRS = (ROOT / "thumbnails", ROOT / "public" / "thumbnails")

MAX_DURATION_S = 480.0
MAX_PER_RUN = 1
WINDOW_DAYS = 2
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
FIXED_TAGS = ("Brasil e Mundo", "Vale da Liberdade", "notícias", "comentário")
DESC_TEMPLATE = (
    "{summary}\n\n"
    "Ouça no app: {app}\n\n"
    "Fontes:\n{refs}\n\n"
    "#BrasilEMundo #{tags}\n"
)


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
            # nytimes.com: IP do VPS marcado no PerimeterX — print sai como
            # página de challenge (testado 2026-08-24). Usar fonte alternativa
            # (AP News, Guardian, BBC, El País) para captura visual.
            "nytimes.com",
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


def source_scenes(episode: dict, max_sources: int = 4) -> list[dict]:
    scenes: list[dict] = []
    seen: set[str] = set()
    for ref in episode.get("fonte_referencias") or []:
        if ref.get("self"):
            continue
        url = _clean_url(ref.get("url") or "")
        if not url or is_blocked_source_url(url) or url in seen:
            continue
        seen.add(url)
        veiculo = (ref.get("veiculo") or "").strip() or urlsplit(url).netloc
        scenes.append({"veiculo": veiculo, "url": url, "titulo": veiculo})
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


def one_line_subhead(episode: dict, limit: int = 78) -> str:
    """Linha fina: submanchete de uma linha, nunca o nome da fonte."""
    title = _unescape((episode.get("titulo") or "").strip())
    for key in ("submanchete", "linha_fina", "resumo"):
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


def build_chapters(scenes: list[dict], dur: float) -> list[tuple[float, str]]:
    """Timestamps aproximados das cenas do mockup (mesma matemática do record_mockup)."""
    n = max(len(scenes), 1)
    per = max(8.0, dur / n)
    entries: list[tuple[float, str]] = [(0.0, "Introdução")]
    t = 0.8
    for s in scenes:
        entries.append((t, (s.get("veiculo") or "Fonte").strip()))
        t += per
    concl = max(t, dur - min(20.0, dur * 0.15))
    entries.append((concl, "Conclusão"))
    # normaliza: crescente, >=10s entre capítulos, dentro da duração
    out: list[tuple[float, str]] = []
    for ts, label in sorted(entries):
        ts = min(ts, max(dur - 1.0, 0.0))
        if out and ts - out[-1][0] < 10.0:
            continue
        out.append((round(ts), label))
    return out


def chapters_block(scenes: list[dict], dur: float) -> str:
    ch = build_chapters(scenes, dur)
    if len(ch) < 3:
        return ""
    lines = ["", "⏱ CAPÍTULOS:", "0:00 Introdução"]
    for ts, label in ch[1:-1]:
        lines.append(f"{ts // 60:.0f}:{ts % 60:02d} {label}")
    last_ts, last_label = ch[-1]
    lines.append(f"{last_ts // 60:.0f}:{last_ts % 60:02d} {last_label}")
    return "\n".join(lines)


def build_metadata(video_id: str, episode: dict, audio: Path, scenes: list[dict] | None = None) -> tuple[str, str, list[str]]:
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
    desc = DESC_TEMPLATE.format(
        summary=summary,
        app=APP_URL,
        refs="\n".join(refs_ok) if refs_ok else "—",
        tags=" ".join(t.replace(" ", "") for t in tags if t),
    )
    if scenes:
        desc += chapters_block(scenes, probe_duration_s(audio) or 0.0)
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


def capture_sources(scenes: list[dict], shot_dir: Path) -> list[dict]:
    from playwright.sync_api import sync_playwright

    shot_dir.mkdir(parents=True, exist_ok=True)
    out: list[dict] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            viewport={"width": 1400, "height": 900},
            user_agent=UA,
            locale="pt-BR",
        )
        page = ctx.new_page()
        for i, scene in enumerate(scenes):
            dest = shot_dir / f"src-{i:02d}.png"
            try:
                # X com vídeo embutido: baixa o clipe em vez de screenshot estático
                if host_kind(scene["url"]) == "x":
                    vid_rel = extract_x_video(scene["url"], shot_dir.parent, shot_dir.parent.name, i)
                    if vid_rel:
                        item = dict(scene)
                        item["shot"] = None
                        item["video"] = vid_rel
                        out.append(item)
                        continue
                page.goto(scene["url"], wait_until="domcontentloaded", timeout=35000)
                page.wait_for_timeout(1800)
                prep = prepare_capture(page, scene["url"])
                print(f"  🔧 {scene['veiculo']}: kind={prep.get('kind')} scroll={prep.get('scrolledTo')} click={prep.get('clicked')}")
                if prep.get("kind") == "instagram" and instagram_is_login_wall(page):
                    print(f"  ⚠️  Instagram ainda em login-wall — cena sem screenshot")
                    item = dict(scene)
                    item["shot"] = None
                    out.append(item)
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
                if dest.exists() and dest.stat().st_size > 8000:
                    item = dict(scene)
                    item["shot"] = dest.name
                    out.append(item)
                    print(f"  📸 {scene['veiculo']}: {dest.name} ({dest.stat().st_size // 1024} KB)")
                    continue
            except Exception as exc:
                print(f"  ⚠️  captura falhou {scene['url']}: {exc}")
            item = dict(scene)
            item["shot"] = None
            out.append(item)
        ctx.close()
        browser.close()
    return out or scenes


def record_mockup(video_id: str, episode: dict, audio: Path, scenes: list[dict], work: Path, wallpaper: Path | None = None) -> Path:
    from playwright.sync_api import sync_playwright

    rec_dir = work / "rec"
    rec_dir.mkdir(parents=True, exist_ok=True)
    httpd, port = start_server([MOCKUP_DIR, work])
    try:
        dur = min(probe_duration_s(audio) or 60.0, MAX_DURATION_S)
        title = _unescape(episode.get("titulo") or "Brasil e Mundo")
        veiculo = episode.get("fonte_veiculo") or "Brasil e Mundo"
        ymd = episode_date(audio)
        subhead = one_line_subhead(episode)
        ticker_items = ticker_headlines(episode, video_id)
        if not scenes:
            scenes = [{"veiculo": veiculo, "url": "https://news.mob.tec.br", "shot": None}]
        per = max(8.0, dur / max(len(scenes), 1))

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
            # Payload inicial vai na URL (loadFromURL): evita os dados demo do
            # HTML aparecerem nos primeiros frames antes do primeiro update().
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

            first_scene = scenes[0] if scenes else {}
            init_payload = {
                "categoria": "BRASIL E MUNDO", "titulo": title, "resumo": subhead,
                "autor": "Peter Albuquerque", "data": ymd, "dataExtenso": ymd,
                "url": first_scene.get("url") or "https://news.mob.tec.br",
                "eyebrow": f"VALE DA LIBERDADE • {veiculo.upper()}",
                "lowerTitle": title, "lowerSubtitle": subhead,
                "liveText": "B&M", "brandSub": "B&M", "tag": "VALE DA LIBERDADE",
                "ticker": ticker_items,
                "pageImage": f"/shots/{first_scene['shot']}" if first_scene.get("shot") else "",
                "pageVideo": first_scene.get("video") or "",
                "wallpaper": f"/wallpaper/{quote(wallpaper.name)}" if wallpaper else "",
            }
            page.goto(f"{url}?{_qs_payload(init_payload)}", wait_until="networkidle", timeout=45000)
            # garante que wallpaper e primeira página decodificaram antes de gravar
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
            idx = 1  # cena 0 já foi aplicada via URL
            first = False
            while time.monotonic() - started < dur:
                scene = scenes[idx % len(scenes)]
                page_image = f"/shots/{scene['shot']}" if scene.get("shot") else ""
                page_video = scene.get("video") or ""
                if first:
                    payload = {
                        "categoria": "BRASIL E MUNDO",
                        "titulo": title,
                        "resumo": subhead,
                        "autor": "Peter Albuquerque",
                        "data": ymd,
                        "dataExtenso": ymd,
                        "url": scene["url"],
                        "eyebrow": f"VALE DA LIBERDADE • {veiculo.upper()}",
                        "lowerTitle": title,
                        "lowerSubtitle": subhead,
                        "liveText": "B&M",
                        "brandSub": "B&M",
                        "tag": "VALE DA LIBERDADE",
                        "ticker": ticker_items,
                        "pageImage": page_image,
                        "pageVideo": page_video,
                        "wallpaper": f"/wallpaper/{quote(wallpaper.name)}" if wallpaper else "",
                    }
                    page.evaluate("data => window.VDL_MOCKUP && window.VDL_MOCKUP.update(data)", payload)
                    first = False
                else:
                    page.evaluate(
                        """({url, pageImage, pageVideo}) => {
                          if (!window.VDL_MOCKUP) return;
                          window.VDL_MOCKUP.update({url, pageImage, pageVideo});
                        }""",
                        {"url": scene["url"], "pageImage": page_image, "pageVideo": page_video},
                    )
                remain = dur - (time.monotonic() - started)
                page.wait_for_timeout(int(min(per, remain) * 1000))
                idx += 1
            raw_webm = Path(page.video.path())
            ctx.close()
            browser.close()
    finally:
        httpd.shutdown()

    if not raw_webm or not raw_webm.exists():
        raise RuntimeError("gravação do mockup não gerou webm")
    return raw_webm


def mux_video(raw: Path, audio: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-i", str(raw),
        "-i", str(audio),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-ac", "2",
        "-shortest", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(dest),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
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

    cmd = [
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
    r = subprocess.run(cmd, capture_output=True, text=True)
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


def publish_youtube(mp4: Path, title: str, desc: str, tags: list[str], privacy: str) -> str:
    up = [
        sys.executable,
        str(SCRIPT_DIR / "youtube_uploader.py"),
        "upload",
        "--file", str(mp4),
        "--title", title[:100],
        "--description", desc,
        "--tags", ", ".join(tags),
        "--privacy", privacy,
    ]
    r = subprocess.run(up, capture_output=True, text=True, timeout=1800)
    out = (r.stdout or "") + (r.stderr or "")
    if r.returncode != 0:
        raise RuntimeError(out[-800:])
    m = re.search(r"ID:\s*([A-Za-z0-9_-]{6,})", out)
    if not m:
        raise RuntimeError(f"upload sem ID:\n{out[-400:]}")
    return m.group(1)


def process_one(video_id: str, upload: bool, privacy: str, dry_run: bool) -> dict:
    episode = load_episode(video_id)
    audio = resolve_audio(video_id)
    if not audio:
        raise FileNotFoundError(f"áudio BM não encontrado para {video_id}")
    dur = probe_duration_s(audio)
    if dur > MAX_DURATION_S:
        raise RuntimeError(f"{video_id}: áudio {dur:.0f}s > {MAX_DURATION_S:.0f}s — pulado")

    scenes = source_scenes(episode)
    title, desc, tags = build_metadata(video_id, episode, audio, scenes=scenes)
    wallpaper = pick_wallpaper(video_id)
    print(f"🎬 {video_id} · {dur:.0f}s · {title}")
    print(f"   fontes: {len(scenes)} · upload={upload} privacy={privacy}")
    if wallpaper:
        print(f"   wallpaper: {wallpaper.name}")
    if dry_run:
        return {
            "video_id": video_id,
            "title": title,
            "scenes": scenes,
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
    raw = record_mockup(video_id, episode, audio, captured or scenes, work, wallpaper=wallpaper)
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
        yt_id = publish_youtube(mp4, title, desc, tags, privacy)
        result["yt_id"] = yt_id
        result["url"] = f"https://youtu.be/{yt_id}"
        thumb = find_episode_thumbnail(video_id, episode_date(audio))
        if thumb:
            set_youtube_thumbnail(yt_id, thumb)
        else:
            print("  ⚠️  sem thumbnail bm_* do episódio")
        state = load_state()
        state.setdefault("videos", {})[video_id] = {
            "yt_id": yt_id,
            "url": result["url"],
            "mp4": str(mp4),
            "data": episode_date(audio),
            "published_at": datetime.now().isoformat(),
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
            process_one(vid, upload=args.upload, privacy=args.privacy, dry_run=args.dry_run)
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
