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
  5. opcional: upload unlisted via youtube_uploader.py
"""
from __future__ import annotations

import argparse
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
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = ROOT / "scripts"
MOCKUP_DIR = ROOT / "references" / "youtube" / "mockup-browser"
MOCKUP_HTML = "mockup-brower.html"  # typo histórico no arquivo
EPS_DIR = ROOT / "output" / "brasil_e_mundo" / "episodes"
AUDIO_DIR = ROOT / "output" / "brasil_e_mundo" / "audio"
VIDEOS_OUT = ROOT / "output" / "videos"
STATE_PATH = ROOT / "output" / "brasil_e_mundo" / "videos_published.json"
WORK_ROOT = ROOT / "output" / "brasil_e_mundo" / "mockup_video"

MAX_DURATION_S = 480.0
MAX_PER_RUN = 1
WINDOW_DAYS = 2
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
FIXED_TAGS = ("Brasil e Mundo", "Vale da Liberdade", "notícias", "comentário")
DESC_TEMPLATE = "Comentário de {data} sobre {veiculo}.\n\nFontes:\n{refs}\n\n#BrasilEMundo #{tags}\n"


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
    return "generic"


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


def build_metadata(video_id: str, episode: dict, audio: Path) -> tuple[str, str, list[str]]:
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
    y, mo, d = ymd.split("-")
    desc = DESC_TEMPLATE.format(
        data=f"{d}/{mo}/{y}",
        veiculo=veiculo or "a pauta do dia",
        refs="\n".join(refs_ok) if refs_ok else "—",
        tags=" ".join(t.replace(" ", "") for t in tags if t),
    )
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


def record_mockup(video_id: str, episode: dict, audio: Path, scenes: list[dict], work: Path) -> Path:
    from playwright.sync_api import sync_playwright

    rec_dir = work / "rec"
    rec_dir.mkdir(parents=True, exist_ok=True)
    httpd, port = start_server([MOCKUP_DIR, work])
    try:
        dur = min(probe_duration_s(audio) or 60.0, MAX_DURATION_S)
        title = _unescape(episode.get("titulo") or "Brasil e Mundo")
        veiculo = episode.get("fonte_veiculo") or "Brasil e Mundo"
        ymd = episode_date(audio)
        ticker_items = [title.upper()]
        for s in scenes:
            ticker_items.append(f"{s['veiculo'].upper()} — {s['url']}")
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
            page.goto(url, wait_until="networkidle", timeout=45000)
            page.wait_for_timeout(800)
            started = time.monotonic()
            idx = 0
            while time.monotonic() - started < dur:
                scene = scenes[idx % len(scenes)]
                page_image = f"/shots/{scene['shot']}" if scene.get("shot") else ""
                payload = {
                    "categoria": "BRASIL E MUNDO",
                    "titulo": title,
                    "resumo": f"Fonte: {scene['veiculo']}",
                    "autor": "Peter Albuquerque",
                    "data": ymd,
                    "dataExtenso": ymd,
                    "url": scene["url"],
                    "eyebrow": f"VALE DA LIBERDADE • {veiculo.upper()}",
                    "lowerTitle": title,
                    "lowerSubtitle": scene["veiculo"],
                    "liveText": "B&M",
                    "brandSub": "B&M",
                    "tag": "VALE DA LIBERDADE",
                    "ticker": ticker_items,
                    "pageImage": page_image,
                }
                page.evaluate("data => window.VDL_MOCKUP && window.VDL_MOCKUP.update(data)", payload)
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

    title, desc, tags = build_metadata(video_id, episode, audio)
    scenes = source_scenes(episode)
    print(f"🎬 {video_id} · {dur:.0f}s · {title}")
    print(f"   fontes: {len(scenes)} · upload={upload} privacy={privacy}")
    if dry_run:
        return {"video_id": video_id, "title": title, "scenes": scenes, "dry_run": True}

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
    raw = record_mockup(video_id, episode, audio, captured or scenes, work)
    mp4 = VIDEOS_OUT / f"especial-{video_id}-mockup.mp4"
    mux_video(raw, audio, mp4)
    print(f"  ✅ mp4 {mp4} ({mp4.stat().st_size // 1024} KB)")

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
        state = load_state()
        state.setdefault("videos", {})[video_id] = {
            "yt_id": yt_id,
            "url": result["url"],
            "mp4": str(mp4),
            "data": episode_date(audio),
            "published_at": datetime.now().isoformat(),
            "engine": "mockup-browser",
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
    ap.add_argument("--privacy", default="unlisted", choices=["unlisted", "private", "public"])
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
