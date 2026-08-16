#!/usr/bin/env python3
"""
Publica o catálogo do site estático (public/) a partir de episodes/ + audio/.

- Gera public/data/episodes.json (feed Twitter-style)
- Gera public/feed.xml (RSS 2.0 + iTunes para Spotify/Apple/etc.)
- Gera public/feed.json (JSON Feed)
- Copia áudios finais para public/audio/
- Copia roteiros .md para public/episodes/
- Atualiza cache-bust do service worker

Uso:
  python3 scripts/publish_site.py
  python3 scripts/publish_site.py --date 2026-07-22
  python3 scripts/publish_site.py --limit 30

Env:
  SITE_URL=https://radio.mob.tec.br
  PODCAST_EMAIL=contato@mob.tec.br
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from email.utils import format_datetime, parsedate_to_datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

# Minificacao CSS/JS (opcional, depende de csscompressor/rjsmin)
try:
    from csscompressor import compress as compress_css
    from rjsmin import jsmin as compress_js
    HAS_MINIFIERS = True
except ImportError:
    HAS_MINIFIERS = False
    import warnings
    warnings.warn("csscompressor/rjsmin nao instalados — pulando minificacao")

# Otimizacao de imagens (opcional, depende de Pillow)
try:
    from PIL import Image as PILImage
    HAS_PIL = True
except ImportError:
    PILImage = None  # type: ignore[assignment,misc]
    HAS_PIL = False

ROOT = Path(__file__).resolve().parent.parent
# NEW_UX_PUBLIC removido (2026-08-06): new-ux/ aposentado, public/ agora é a única fonte.
load_dotenv(ROOT / ".env")

EPISODES_DIR = ROOT / "episodes"
AUDIO_DIR = ROOT / "audio"
PUBLIC = ROOT / "public"
PUBLIC_DATA = PUBLIC / "data"
PUBLIC_AUDIO = PUBLIC / "audio"
PUBLIC_EPS = PUBLIC / "episodes"
THUMBNAILS_PUBLIC = PUBLIC / "thumbnails"
THUMBNAILS_DIR = ROOT / "thumbnails"
SW_PATH = PUBLIC / "sw.js"
FEED_PATH = PUBLIC / "feed.xml"
FEED_JSON_PATH = PUBLIC / "feed.json"

PAGE_SIZE = 12

DEFAULT_SITE_URL = "https://news.mob.tec.br"

PODCAST_TITLE = "Vale da Liberdade"
PODCAST_AUTHOR = "Peter Albuquerque & Ricardo Souto"
PODCAST_EMAIL = os.environ.get("PODCAST_EMAIL", "contato@mob.tec.br")
PODCAST_CATEGORY = os.environ.get("PODCAST_CATEGORY", "News")
PODCAST_SUBCATEGORY = os.environ.get("PODCAST_SUBCATEGORY", "Daily News")
PODCAST_LANGUAGE = "pt-BR"
PODCAST_EXPLICIT = "false"
PODCAST_DESCRIPTION = (
    "Web Jornal diário do Vale da Liberdade: Peter Albuquerque e Ricardo Souto "
    "debatem notícias de Blumenau, Alto Vale e Santa Catarina com viés crítico "
    "e libertário — cobertura local, segurança, saúde, política e o mundo."
)

MONTHS_PT = {
    1: "janeiro", 2: "fevereiro", 3: "março", 4: "abril",
    5: "maio", 6: "junho", 7: "julho", 8: "agosto",
    9: "setembro", 10: "outubro", 11: "novembro", 12: "dezembro",
}


def site_url() -> str:
    return (os.environ.get("SITE_URL") or DEFAULT_SITE_URL).strip().rstrip("/")


def r2_public_domain() -> str:
    """Retorna o domínio público do bucket R2, se configurado."""
    return (os.environ.get("R2_PUBLIC_DOMAIN") or "").strip().rstrip("/")


def r2_catalog_url(date_str: str) -> str | None:
    """
    Verifica se existe sidecar R2 para o episódio e retorna a URL pública.
    Retorna None se não houver sidecar ou se o R2 não estiver configurado.
    """
    r2_domain = r2_public_domain()
    if not r2_domain:
        return None

    sidecar_path = EPISODES_DIR / f"{date_str}-r2.json"
    if not sidecar_path.exists():
        return None

    try:
        with open(sidecar_path, 'r', encoding='utf-8') as f:
            meta = json.load(f)
        if meta.get("r2_uploaded") and meta.get("catalog_url"):
            return meta["catalog_url"]
    except Exception:
        pass

    return None


def abs_url(path: str) -> str:
    base = site_url()
    if not path:
        return base + "/"
    if path.startswith("http://") or path.startswith("https://"):
        return path
    path = path.lstrip("./")
    if not path.startswith("/"):
        path = "/" + path
    return base + path


def parse_date(s: str) -> datetime | None:
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        return None


def human_title(date_str: str, episode: int | None = None) -> str:
    dt = parse_date(date_str)
    if not dt:
        return f"Edição {date_str}"
    base = f"{dt.day} de {MONTHS_PT[dt.month]} de {dt.year}"
    if episode:
        return f"Episódio {episode} · {base}"
    return f"Edição de {base}"


def read_optimized_title(date_str: str) -> str | None:
    """Retorna o título otimizado (episodes/{date}-title.txt) se existir.

    O arquivo é gravado por scripts/title_optimizer.py na pipeline. Quando
    presente, substitui o título genérico humano no catálogo/RSS.
    """
    p = EPISODES_DIR / f"{date_str}-title.txt"
    if not p.exists():
        return None
    title = p.read_text(encoding="utf-8").strip().lstrip("•-–— ").strip()
    if not title or "manchetes" in title.lower():
        return None
    return title


def rfc2822_from_date(date_str: str, hour: int = 6, minute: int = 15) -> str:
    dt = parse_date(date_str)
    if not dt:
        dt = datetime.now(timezone.utc)
    else:
        dt = dt.replace(hour=hour, minute=minute, second=0, tzinfo=timezone.utc)
    return format_datetime(dt)


def itunes_duration(minutes: float | None, audio_path: Path | None = None) -> str:
    secs = None
    if audio_path and audio_path.exists():
        try:
            proc = subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=nw=1:nk=1",
                    str(audio_path),
                ],
                capture_output=True, text=True, timeout=30,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                secs = int(float(proc.stdout.strip()))
        except Exception:
            secs = None
    if secs is None and minutes is not None:
        secs = int(float(minutes) * 60)
    if secs is None:
        return "00:10:00"
    h, rem = divmod(max(secs, 0), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def read_manchetes(date: str) -> list[str]:
    p = EPISODES_DIR / f"{date}-manchetes.txt"
    if p.exists():
        lines = []
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip().lstrip("•-–— ").strip()
            if line and "manchetes" not in line.lower():
                lines.append(line)
        if lines:
            return lines[:6]
    md = EPISODES_DIR / f"{date}.md"
    if not md.exists():
        return []
    text = md.read_text(encoding="utf-8")
    items: list[str] = []
    in_block = False
    for line in text.splitlines():
        low = line.lower().strip()
        if "manchetes" in low and (line.strip().startswith("#") or "📋" in line or low.startswith("##")):
            in_block = True
            continue
        if in_block:
            if line.strip().startswith("#") or line.strip().startswith("---") or line.strip().startswith("###"):
                if items:
                    break
                continue
            m = re.match(r"^[\s•\-\*]+(.+)$", line)
            if m:
                item = m.group(1).strip()
                if item and "manchetes" not in item.lower():
                    items.append(item)
            elif line.strip() == "" and items:
                continue
            elif line.strip() and not m and items:
                break
    return items[:6]


def excerpt_from_md(date: str, manchetes: list[str]) -> str:
    if manchetes:
        return " · ".join(manchetes[:2])
    md = EPISODES_DIR / f"{date}.md"
    if not md.exists():
        return "Cobertura diária do Vale da Liberdade."
    text = md.read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("Peter:") or line.startswith("Ricardo:"):
            body = line.split(":", 1)[1].strip()
            if len(body) > 40:
                return body[:180] + ("…" if len(body) > 180 else "")
    return "Cobertura diária do Vale da Liberdade."


def pick_audio(date: str) -> Path | None:
    candidates = [
        AUDIO_DIR / f"{date}.mp3",
        AUDIO_DIR / f"{date}-vale-da-liberdade.mp3",
        AUDIO_DIR / f"{date}-completo.mp3",
    ]
    existing = [p for p in candidates if p.exists() and p.stat().st_size > 200_000]
    if not existing:
        for p in sorted(AUDIO_DIR.glob(f"{date}*.mp3")):
            if re.search(r"-(peter|ricardo|edge)-\d+", p.name):
                continue
            if p.stat().st_size > 200_000:
                existing.append(p)
    if not existing:
        return None
    existing.sort(key=lambda p: p.stat().st_size, reverse=True)
    for preferred in candidates[:2]:
        if preferred in existing and preferred.stat().st_size >= 1_000_000:
            return preferred
    return existing[0]


def ffprobe_duration_min(path: Path) -> float | None:
    try:
        proc = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=nw=1:nk=1",
                str(path),
            ],
            capture_output=True, text=True, timeout=30,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return round(float(proc.stdout.strip()) / 60.0, 1)
    except Exception:
        return None
    return None


def load_metadata(date: str) -> dict:
    p = EPISODES_DIR / f"{date}-metadata.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def discover_dates() -> list[str]:
    dates: set[str] = set()
    for p in EPISODES_DIR.glob("????-??-??.md"):
        dates.add(p.stem)
    for p in EPISODES_DIR.glob("????-??-??-metadata.json"):
        dates.add(p.name[:10])
    for p in AUDIO_DIR.glob("????-??-??*.mp3"):
        m = re.match(r"(\d{4}-\d{2}-\d{2})", p.name)
        if m:
            dates.add(m.group(1))
    return sorted(dates, reverse=True)


def episode_sponsors_static(date: str) -> list[dict]:
    """Fallback estático de patrocinadores (Tipo 1) a partir de ads/schedule.json.

    Usado pelo frontend quando a RPC get_episode_sponsors() está indisponível.
    Retorna [] se não houver anúncio para a data.
    """
    sched = ROOT / "ads" / "schedule.json"
    if not sched.exists():
        return []
    try:
        data = json.loads(sched.read_text(encoding="utf-8"))
    except Exception:
        return []
    ads = data.get("ads", {})
    out = []
    seen = set()
    for h in data.get("history", []):
        if h.get("date") != date or h.get("status") != "done":
            continue
        ad = ads.get(h.get("ad_id"))
        if not ad:
            continue
        slug = ad.get("sponsor_slug") or ad.get("sponsor")
        if slug in seen:
            continue
        seen.add(slug)
        out.append({
            "name": ad.get("sponsor"),
            "website_url": ad.get("website_url"),
            "logo_url": ad.get("logo_url"),
            "placement": "mid-roll",
        })
    return out



def _thumbnail_url(date: str, episode_id: str) -> str | None:
    """Retorna a URL relativa da thumbnail do episódio, ou None se não existir."""
    # episode_id can be:
    #   "YYYY-MM-DD" (daily) → file is ep_YYYY-MM-DD.webp
    #   "bm_XXXX" (especial) → file is bm_XXXX.webp
    date_str = date
    if episode_id.startswith("bm_"):
        thumb_id = episode_id  # bm_XXXX
    else:
        thumb_id = f"ep_{episode_id}"  # daily: ep_YYYY-MM-DD
    for ext in (".webp", ".jpg"):
        thumb = THUMBNAILS_PUBLIC / date_str / f"{thumb_id}{ext}"
        if thumb.exists():
            return f"./thumbnails/{date_str}/{thumb_id}{ext}"
    return None

def build_episode(date: str) -> dict | None:
    meta = load_metadata(date)
    audio = pick_audio(date)
    md = EPISODES_DIR / f"{date}.md"
    if not audio and not md.exists():
        return None

    manchetes = read_manchetes(date)
    words = meta.get("palavras_total")
    if words is None and md.exists():
        words = len(md.read_text(encoding="utf-8").split())

    duration = meta.get("duracao_estimada_min")
    if audio:
        probed = ffprobe_duration_min(audio)
        if probed:
            duration = probed

    episode_num = meta.get("episodio")
    title = (
        read_optimized_title(date)
        or human_title(date, episode_num if isinstance(episode_num, int) else None)
    )

    audio_url = None
    audio_bytes = None
    if audio:
        dest = PUBLIC_AUDIO / f"{date}.mp3"
        PUBLIC_AUDIO.mkdir(parents=True, exist_ok=True)
        try:
            same = audio.resolve() == dest.resolve()
        except OSError:
            same = False
        if not same:
            try:
                # prefer hardlink (no extra disk); fallback copy
                if dest.exists() or dest.is_symlink():
                    dest.unlink()
                try:
                    os.link(audio, dest)
                except OSError:
                    shutil.copy2(audio, dest)
            except Exception:
                # last resort: leave existing dest if any
                if not dest.exists():
                    shutil.copy2(audio, dest)
        try:
            dest.chmod(0o644)
        except OSError:
            pass
        audio_url = f"./audio/{date}.mp3"
        audio_bytes = dest.stat().st_size if dest.exists() else audio.stat().st_size

        # Verificar sidecar R2 e usar URL pública se disponível
        r2_url = r2_catalog_url(date)
        if r2_url:
            audio_url = r2_url

    script_url = None
    if md.exists():
        PUBLIC_EPS.mkdir(parents=True, exist_ok=True)
        shutil.copy2(md, PUBLIC_EPS / f"{date}.md")
        script_url = f"./episodes/{date}.md"

    return {
        "id": date,
        "date": date,
        "episode": episode_num,
        "title": title,
        "excerpt": excerpt_from_md(date, manchetes),
        "manchetes": manchetes,
        "quadros": meta.get("quadros_gerados") or [],
        "duration_min": duration,
        "words": words,
        "audio_url": audio_url,
        "script_url": script_url,
        "audio_bytes": audio_bytes,
        "sources": meta.get("fontes_utilizadas") or [],
        "sponsors": episode_sponsors_static(date),
        "cover_url": _thumbnail_url(date, date),
        "published_at": datetime.now().isoformat(timespec="seconds"),
    }


def bump_sw_cache_version() -> None:
    if not SW_PATH.exists():
        return
    text = SW_PATH.read_text(encoding="utf-8")
    stamp = datetime.now().strftime("%Y%m%d%H%M")
    new = re.sub(r'const CACHE = "[^"]+"', f'const CACHE = "vld-v1-{stamp}"', text, count=1)
    if new != text:
        SW_PATH.write_text(new, encoding="utf-8")
        print(f"  SW cache → vld-v1-{stamp}")


def _ep_payload(ep: dict) -> dict:
    """Payload enxuto para arquivos de página — remove campos *_abs (não usados pela UI)."""
    return {k: v for k, v in ep.items() if k not in ("audio_url_abs", "script_url_abs")}


def write_paginated_catalog(ordered: list[dict], catalog: dict) -> None:
    """Gera episodes-index.json + episodes-{categoria}-page-N.json (PERF-003)."""
    PUBLIC_DATA.mkdir(parents=True, exist_ok=True)

    buckets = {
        "todos": ordered,
        "diario": [e for e in ordered if e.get("type") != "especial"],
        "especial": [e for e in ordered if e.get("type") == "especial"],
    }

    index = {
        "generated_at": catalog.get("generated_at"),
        "page_size": PAGE_SIZE,
        "total_episodes": len(ordered),
        "categories": {},
    }

    for cat, eps in buckets.items():
        total_eps = len(eps)
        total_pages = (total_eps + PAGE_SIZE - 1) // PAGE_SIZE if total_eps else 0
        index["categories"][cat] = {
            "total_episodes": total_eps,
            "total_pages": total_pages,
            "pages": [f"./data/episodes-{cat}-page-{n}.json" for n in range(1, total_pages + 1)],
        }

        for page_num in range(1, total_pages + 1):
            start = (page_num - 1) * PAGE_SIZE
            chunk = eps[start : start + PAGE_SIZE]
            (PUBLIC_DATA / f"episodes-{cat}-page-{page_num}.json").write_text(
                json.dumps(
                    {
                        "generated_at": catalog.get("generated_at"),
                        "category": cat,
                        "page": page_num,
                        "page_size": PAGE_SIZE,
                        "total_pages": total_pages,
                        "episodes": [_ep_payload(e) for e in chunk],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

    # Limpar páginas órfãs de catálogos anteriores (ex.: catálogo encolheu)
    valid_pages = {p.split("/")[-1] for c in index["categories"].values() for p in c["pages"]}
    for orphan in PUBLIC_DATA.glob("episodes-*-page-*.json"):
        if orphan.name not in valid_pages:
            try:
                orphan.unlink()
            except OSError:
                pass

    (PUBLIC_DATA / "episodes-index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    todos = index["categories"]["todos"]
    print(
        f"  📄 Paginação: {todos['total_pages']} páginas ({PAGE_SIZE}/pág) → episodes-index.json"
    )


def write_rss(episodes: list[dict]) -> Path:
    """RSS 2.0 + iTunes — XML limpo (Spotify/Apple/Amazon/Pocket Casts)."""
    base = site_url()
    audio_eps = [e for e in episodes if e.get("audio_url") and e.get("type") != "especial"]
    now = format_datetime(datetime.now(timezone.utc))
    cover = abs_url("/assets/cover.jpg")
    feed_self = abs_url("/feed.xml")

    def esc(s: str) -> str:
        return html.escape(s or "", quote=False)

    items_xml: list[str] = []
    for ep in audio_eps:
        title = ep.get("title") or human_title(ep["date"])
        desc_parts = []
        if ep.get("manchetes"):
            desc_parts.append("Manchetes: " + "; ".join(ep["manchetes"][:5]))
        if ep.get("excerpt"):
            desc_parts.append(ep["excerpt"])
        desc_parts.append(f"Apresentação: {PODCAST_AUTHOR}")
        description = "\n\n".join(desc_parts)
        local_audio = PUBLIC_AUDIO / f"{ep['date']}.mp3"
        length = local_audio.stat().st_size if local_audio.exists() else (ep.get("audio_bytes") or 0)
        dur = itunes_duration(ep.get("duration_min"), local_audio if local_audio.exists() else None)
        ep_num = ""
        if isinstance(ep.get("episode"), int):
            ep_num = f"      <itunes:episode>{ep['episode']}</itunes:episode>\n"
        # Per-episode thumbnail: diário → ep_{date}.webp, especial → bm_{id}.webp
        ep_cover = cover  # fallback genérico
        ep_id = ep.get("id", ep["date"])
        if ep_id.startswith("bm_"):
            thumb_id = ep_id
        elif ep_id.startswith("especial-"):
            thumb_id = "bm_" + ep_id.replace("especial-", "")
        else:
            thumb_id = f"ep_{ep['date']}"
        date_str = ep["date"]
        for ext in (".webp", ".jpg"):
            thumb_path = THUMBNAILS_PUBLIC / date_str / f"{thumb_id}{ext}"
            if thumb_path.exists():
                ep_cover = abs_url(f"/thumbnails/{date_str}/{thumb_id}{ext}")
                break
        items_xml.append(
            f"""    <item>
      <title>{esc(title)}</title>
      <link>{esc(abs_url(f"/?ep={ep_id}"))}</link>
      <guid isPermaLink="false">vld-{esc(ep_id)}</guid>
      <pubDate>{rfc2822_from_date(ep['date'])}</pubDate>
      <description>{esc(description)}</description>
      <enclosure url="{esc(abs_url(ep['audio_url']))}" length="{length}" type="audio/mpeg"/>
      <itunes:title>{esc(title)}</itunes:title>
      <itunes:summary>{esc(description[:4000])}</itunes:summary>
      <itunes:duration>{dur}</itunes:duration>
      <itunes:explicit>{PODCAST_EXPLICIT}</itunes:explicit>
      <itunes:episodeType>full</itunes:episodeType>
{ep_num}      <itunes:image href="{esc(ep_cover)}"/>
    </item>"""
        )

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
  xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
  xmlns:content="http://purl.org/rss/1.0/modules/content/"
  xmlns:atom="http://www.w3.org/2005/Atom"
  xmlns:podcast="https://podcastindex.org/namespace/1.0">
  <channel>
    <title>{esc(PODCAST_TITLE)}</title>
    <link>{esc(base)}/</link>
    <description>{esc(PODCAST_DESCRIPTION)}</description>
    <language>{PODCAST_LANGUAGE}</language>
    <copyright>© {datetime.now().year} {esc(PODCAST_TITLE)}</copyright>
    <lastBuildDate>{now}</lastBuildDate>
    <generator>Vale da Liberdade publish_site.py</generator>
    <docs>https://help.apple.com/itc/podcasts_connect/#/itcb54353390</docs>
    <atom:link href="{esc(feed_self)}" rel="self" type="application/rss+xml"/>
    <itunes:author>{esc(PODCAST_AUTHOR)}</itunes:author>
    <itunes:summary>{esc(PODCAST_DESCRIPTION)}</itunes:summary>
    <itunes:explicit>{PODCAST_EXPLICIT}</itunes:explicit>
    <itunes:type>episodic</itunes:type>
    <itunes:owner>
      <itunes:name>{esc(PODCAST_TITLE)}</itunes:name>
      <itunes:email>{esc(PODCAST_EMAIL)}</itunes:email>
    </itunes:owner>
    <itunes:image href="{esc(cover)}"/>
    <itunes:category text="{esc(PODCAST_CATEGORY)}">
      <itunes:category text="{esc(PODCAST_SUBCATEGORY)}"/>
    </itunes:category>
    <image>
      <url>{esc(cover)}</url>
      <title>{esc(PODCAST_TITLE)}</title>
      <link>{esc(base)}/</link>
    </image>
{chr(10).join(items_xml)}
  </channel>
</rss>
"""
    FEED_PATH.write_text(xml, encoding="utf-8")
    print(f"  📻 RSS: {FEED_PATH} ({len(audio_eps)} itens)")
    print(f"     URL: {abs_url('/feed.xml')}")
    return FEED_PATH

def write_feed_json(episodes: list[dict]) -> None:
    items = []
    for ep in episodes:
        if not ep.get("audio_url") or ep.get("type") == "especial":
            continue
        items.append({
            "id": f"vld-{ep.get('id', ep['date'])}",
            "url": abs_url(f"/?ep={ep.get('id', ep['date'])}"),
            "title": ep.get("title"),
            "content_text": ep.get("excerpt") or "",
            "date_published": f"{ep['date']}T06:15:00Z",
            "attachments": [{
                "url": abs_url(ep["audio_url"]),
                "mime_type": "audio/mpeg",
                "size_in_bytes": ep.get("audio_bytes"),
                "duration_in_seconds": int(float(ep.get("duration_min") or 0) * 60) or None,
            }],
            "image": abs_url("/assets/cover.jpg"),
            "tags": ep.get("quadros") or [],
        })
    payload = {
        "version": "https://jsonfeed.org/version/1.1",
        "title": PODCAST_TITLE,
        "home_page_url": site_url() + "/",
        "feed_url": abs_url("/feed.json"),
        "description": PODCAST_DESCRIPTION,
        "icon": abs_url("/icons/icon-512.png"),
        "favicon": abs_url("/icons/favicon-32.png"),
        "language": "pt-BR",
        "authors": [{"name": PODCAST_AUTHOR}],
        "items": items,
    }
    FEED_JSON_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def discover_especial_episodes() -> list[dict]:
    eps = []
    bm_episodes_dir = ROOT / "output" / "brasil_e_mundo" / "episodes"
    bm_audio_dir = ROOT / "output" / "brasil_e_mundo" / "audio"
    bm_feed_src = ROOT / "output" / "brasil_e_mundo" / "feed.xml"
    
    # Copiar o feed próprio se existir
    if bm_feed_src.exists():
        try:
            shutil.copy2(bm_feed_src, PUBLIC / "feed-brasil-e-mundo.xml")
            print("  🎯 RSS Brasil e Mundo publicado")
        except Exception as e:
            print(f"  ⚠️ Falha ao copiar feed especial: {e}")

    if not bm_episodes_dir.exists():
        return eps

    for p in bm_episodes_dir.glob("especial-*.json"):
        video_id = p.name.replace("especial-", "").replace(".json", "")
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue

        # Encontrar áudio em output/brasil_e_mundo/audio/
        audio_files = list(bm_audio_dir.glob(f"{video_id}_*.mp3"))
        # 2026-08-10 (BUG LULINHA): glob volta em ordem alfabética (08-09 antes
        # de 08-10) — o catálogo republicava o áudio ANTIGO/corrompido. Ordenar
        # pela data no nome (YYYY-MM-DD) e escolher a MAIS RECENTE.
        def _audio_date_key(p: Path) -> tuple:
            m = re.search(r"_(\d{4}-\d{2}-\d{2})\.mp3$", p.name)
            return (m.group(1) if m else "0000-00-00", p.stat().st_mtime)
        audio_files.sort(key=_audio_date_key, reverse=True)
        audio_path = None
        # Try to get date from audio filename or mtime
        date_str = None
        if audio_files:
            # Pegar o áudio mais recente ou o primeiro
            audio_path = audio_files[0]
            # Extrair data do nome do arquivo: video_id_YYYY-MM-DD.mp3
            m = re.search(r"_(\d{4}-\d{2}-\d{2})\.mp3$", audio_path.name)
            if m:
                date_str = m.group(1)
            else:
                # Fallback: usar data de modificação do arquivo
                import os as _os
                from datetime import datetime as _datetime, timezone as _timezone
                mtime = _os.path.getmtime(audio_path)
                date_str = _datetime.fromtimestamp(mtime, tz=_timezone.utc).strftime("%Y-%m-%d")
        if not date_str:
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            audio_path = audio_files[0]
            m = re.search(r"_(\d{4}-\d{2}-\d{2})\.mp3$", audio_path.name)
            if m:
                date_str = m.group(1)

        md_file = bm_episodes_dir / f"especial-{video_id}.md"

        # Calcular palavras
        words = 0
        for sec in ("abertura", "desenvolvimento", "fechamento"):
            for item in data.get(sec, []):
                words += len(item.get("texto", "").split())

        # Estimar duração
        duration_min = round(words / 150.0, 1)

        # Obter duração real com ffprobe se disponível
        audio_bytes = 0
        audio_url = None
        if audio_path and audio_path.exists():
            audio_bytes = audio_path.stat().st_size
            probed = ffprobe_duration_min(audio_path)
            if probed:
                duration_min = probed

            # Copiar para public/audio/especial-{video_id}.mp3
            dest = PUBLIC_AUDIO / f"especial-{video_id}.mp3"
            PUBLIC_AUDIO.mkdir(parents=True, exist_ok=True)
            try:
                if dest.exists() or dest.is_symlink():
                    dest.unlink()
                try:
                    os.link(audio_path, dest)
                except OSError:
                    shutil.copy2(audio_path, dest)
                dest.chmod(0o644)
            except Exception as e:
                print(f"  ⚠️ Falha ao copiar áudio {video_id}: {e}")
            audio_url = f"./audio/especial-{video_id}.mp3"

            # Verificar sidecar R2 e usar URL pública se disponível
            r2_url = r2_catalog_url(f"especial-{video_id}")
            if r2_url:
                audio_url = r2_url

        script_url = None
        if md_file.exists():
            # Copiar para public/episodes/especial-{video_id}.md
            PUBLIC_EPS.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(md_file, PUBLIC_EPS / f"especial-{video_id}.md")
            except Exception:
                pass
            script_url = f"./episodes/especial-{video_id}.md"

        # Extrair pubDate do feed XML se existir, senão usar timestamp do arquivo
        pub_date = None
        if bm_feed_src.exists():
            try:
                with open(bm_feed_src, 'r') as f:
                    feed_content = f.read()
                # Procurar o pubDate correspondente a este video_id usando o link do arquivo
                pattern = rf'<link>.*?{video_id}.*?</link>.*?<pubDate>([^<]+)</pubDate>'
                match = re.search(pattern, feed_content, re.DOTALL)
                if match:
                    pub_date = match.group(1)
                    print(f"  ℹ️  pubDate extraído: {pub_date[:25]}")
                else:
                    print(f"  ⚠️  pubDate não encontrado para {video_id}")
            except Exception as e:
                print(f"  ⚠️  Erro ao extrair pubDate: {e}")

        # Se não encontrou no feed, usar timestamp do arquivo de áudio
        if not pub_date and audio_path and audio_path.exists():
            import os as _os
            from datetime import datetime as _datetime, timezone as _timezone
            mtime = _os.path.getmtime(audio_path)
            pub_date = _datetime.fromtimestamp(mtime, tz=_timezone.utc).strftime('%a, %d %b %Y %H:%M:%S +0000')

        refs = data.get("fonte_referencias") or []
        eps.append({
            "id": f"especial-{video_id}",
            "date": date_str,
            "pubDate": pub_date,
            "type": "especial",
            "title": data.get("titulo") or f"Especial {video_id}",
            "excerpt": data.get("abertura", [{}])[0].get("texto", "")[:180] + "...",
            "manchetes": [],
            "quadros": data.get("tags") or [],
            "duration_min": duration_min,
            "words": words,
            "audio_url": audio_url,
            "script_url": script_url,
            "audio_bytes": audio_bytes,
            # Fonte do site = links da seção "Referências:" da descrição do
            # YouTube (inclui os links do nosso próprio site: página do
            # episódio + matéria transcrita).
            "sources": [r.get("veiculo") for r in refs if r.get("veiculo")]
            or ([data.get("fonte_veiculo")] if data.get("fonte_veiculo") else []),
            "referencias": refs,
            "share_url": f"./ep/especial-{video_id}.html",
            "cover_url": _thumbnail_url(date_str, f"bm_{video_id}"),
            "published_at": datetime.now().isoformat(timespec="seconds"),
        })

    return eps


def write_share_pages(episodes: list) -> None:
    """Gera páginas estáticas /ep/<id>.html com meta OG corretos por episódio +
    redirecionamento para o player. Servem de 'bridge' de preview: o WhatsApp/
    Telegram NÃO executam JS e leem só os <meta> estáticos do HTML; como o site é
    nginx estático, o ?ep= sempre devolve o index.html genérico. Essas páginas
    dão meta por episódio e redirecionam para o deep link do player."""
    from urllib.parse import quote
    share_dir = PUBLIC / "ep"
    share_dir.mkdir(parents=True, exist_ok=True)
    base = site_url()
    generic_img = abs_url("/assets/cover-1200.webp")
    def slug(eid: str) -> str:
        return re.sub(r"[^A-Za-z0-9_.-]+", "-", str(eid)) or "ep"
    seen = set()
    for ep in episodes:
        eid = str(ep.get("id") or "")
        if not eid:
            continue
        fname = slug(eid)
        seen.add(fname)
        title = ep.get("title") or f"Episódio {ep.get('date') or ''}"
        excerpt = ep.get("excerpt") or ""
        if not excerpt and isinstance(ep.get("manchetes"), list) and ep["manchetes"]:
            excerpt = ep["manchetes"][0]
        desc = (excerpt or "").strip()[:160] or f"Ouça o episódio de {ep.get('date') or ''} do Vale da Liberdade."
        img = ep.get("cover_url_abs") or generic_img
        og_url = f"{base}/ep/{quote(eid)}.html"
        target = f"{base}/?ep={quote(eid)}"
        js_target = target.replace("\\", "\\\\").replace('"', '\\"')
        page = (
            "<!DOCTYPE html>\n"
            '<html lang="pt-BR">\n<head>\n'
            '<meta charset="UTF-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f"<title>{html.escape(title)} — Vale da Liberdade</title>\n"
            f'<meta name="description" content="{html.escape(desc, quote=True)}">\n'
            '<meta property="og:type" content="article">\n'
            '<meta property="og:site_name" content="Vale da Liberdade">\n'
            f'<meta property="og:title" content="{html.escape(title, quote=True)}">\n'
            f'<meta property="og:description" content="{html.escape(desc, quote=True)}">\n'
            f'<meta property="og:image" content="{html.escape(img, quote=True)}">\n'
            '<meta property="og:image:width" content="1280">\n'
            '<meta property="og:image:height" content="720">\n'
            f'<meta property="og:url" content="{html.escape(og_url, quote=True)}">\n'
            '<meta name="twitter:card" content="summary_large_image">\n'
            f'<meta name="twitter:title" content="{html.escape(title, quote=True)}">\n'
            f'<meta name="twitter:description" content="{html.escape(desc, quote=True)}">\n'
            f'<meta name="twitter:image" content="{html.escape(img, quote=True)}">\n'
            f'<link rel="canonical" href="{html.escape(og_url, quote=True)}">\n'
            f'<meta http-equiv="refresh" content="0; url={html.escape(target, quote=True)}">\n'
            "</head>\n<body>\n"
            f'<script>location.replace("{js_target}");</script>\n'
            f'<p>Ouvir <a href="{html.escape(target, quote=True)}">{html.escape(title)}</a> no Vale da Liberdade.</p>\n'
            "</body>\n</html>\n"
        )
        (share_dir / f"{fname}.html").write_text(page, encoding="utf-8")
    # Remove páginas órfãs (episódios que saíram do catálogo)
    for f in share_dir.glob("*.html"):
        if f.stem not in seen:
            try:
                f.unlink()
            except OSError:
                pass
    print(f"  🔗 Páginas de compartilhamento OG: {len(seen)} em /ep/")


def deploy_noticias_pages() -> None:
    """Deploy do espelho /noticias para Cloudflare Pages (vale-liberdade-noticias).

    Roda dentro do publish para o espelho CDN acompanhar o local. Falhas nunca
    bloqueiam o publish (o local é a fonte canônica)."""
    import glob
    import shutil
    import subprocess
    wrangler = shutil.which("wrangler")
    if not wrangler:
        nvm = sorted(glob.glob(str(Path.home() / ".nvm/versions/node/*/bin/wrangler")))
        if nvm:
            wrangler = nvm[-1]
    if not wrangler:
        print("  ⚠️ wrangler não encontrado — espelho Pages não atualizado")
        return
    try:
        r = subprocess.run(
            [wrangler, "pages", "deploy", str(PUBLIC / "noticias"),
             "--project-name", "vale-liberdade-noticias",
             "--branch", "main", "--commit-dirty=true"],
            capture_output=True, text=True, timeout=300,
        )
        if r.returncode == 0:
            print("  ✅ Espelho Cloudflare Pages atualizado (/noticias)")
        else:
            print(f"  ⚠️ Deploy Pages falhou: {(r.stderr or r.stdout)[-300:]}")
    except Exception as e:
        print(f"  ⚠️ Deploy Pages falhou: {e}")


def publish(limit: int = 200, only_date: str | None = None) -> dict:
    PUBLIC_DATA.mkdir(parents=True, exist_ok=True)
    PUBLIC_AUDIO.mkdir(parents=True, exist_ok=True)
    PUBLIC_EPS.mkdir(parents=True, exist_ok=True)

    catalog_path = PUBLIC_DATA / "episodes.json"
    existing_by_id: dict[str, dict] = {}
    if catalog_path.exists():
        try:
            prev = json.loads(catalog_path.read_text(encoding="utf-8"))
            for ep in prev.get("episodes") or []:
                if ep.get("id"):
                    existing_by_id[ep["id"]] = ep
        except Exception:
            pass

    dates = [only_date] if only_date else discover_dates()[:limit]
    for d in dates:
        if not d:
            continue
        ep = build_episode(d)
        if ep and (ep.get("audio_url") or ep.get("script_url")):
            existing_by_id[ep["id"]] = ep
            flag = "🎧" if ep.get("audio_url") else "📝"
            print(f"  {flag} {d} · {ep.get('title')}")

    # Sempre incluir especiais (independente de --date)
    especial_eps = discover_especial_episodes()
    for ep in especial_eps:
        existing_by_id[ep["id"]] = ep
        flag = "🎯" if ep.get("audio_url") else "📝"
        print(f"  {flag} {ep['id']} · {ep.get('title')}")

    episodes = list(existing_by_id.values())
    episodes.sort(key=lambda e: e.get("date") or "", reverse=True)
    if not only_date:
        episodes = episodes[:limit]

    # Ordenar: diários primeiro (por data, desc), depois especiais (por pubDate, desc).
    # FIX 2026-08-16: RFC-2822 ("Wed, 12 Aug 2026 ...") NÃO ordena como string
    # (vira ordem alfabética por dia da semana). Normalizar p/ datetime ISO.
    def sort_key(ep):
        if str(ep.get("id", "")).startswith("especial"):
            pub = ep.get("pubDate")
            if pub:
                try:
                    return (0, parsedate_to_datetime(pub).isoformat())
                except Exception:
                    return (0, pub)
            return (0, "")
        d = ep.get("date") or ""
        return (1, d + "T00:00:00" if d else "0000-01-01T00:00:00")

    ordered = sorted(episodes, key=sort_key, reverse=True)

    for ep in ordered:
        if ep.get("audio_url"):
            ep["audio_url_abs"] = abs_url(ep["audio_url"])
        if ep.get("script_url"):
            ep["script_url_abs"] = abs_url(ep["script_url"])
        if ep.get("share_url"):
            ep["share_url_abs"] = abs_url(ep["share_url"])
        if ep.get("cover_url"):
            ep["cover_url_abs"] = abs_url(ep["cover_url"])

    base = site_url()
    today = datetime.now().strftime("%Y-%m-%d")
    catalog = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "site": PODCAST_TITLE,
        "site_url": base,
        "feed_url": abs_url("/feed.xml"),
        "feed_json_url": abs_url("/feed.json"),
        "today": ordered[0]["date"] if ordered else today,
        "count": len(ordered),
        "episodes": ordered,
    }

    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    write_rss(ordered)
    write_feed_json(ordered)
    write_paginated_catalog(ordered, catalog)
    write_share_pages(ordered)
    # Páginas de notícia /noticias (BBC-style) — regenera a cada publish para
    # artigos novos subirem automaticamente em news.mob.tec.br/noticias
    try:
        from gen_noticias import main as _gen_noticias_main
        _gen_noticias_main()
    except Exception as e:
        print(f"  ⚠️ Falha ao regenerar /noticias: {e}")
    deploy_noticias_pages()
    bump_sw_cache_version()

    (PUBLIC / "robots.txt").write_text(
        "User-agent: *\n"
        "Allow: /\n"
        f"Sitemap: {abs_url('/feed.xml')}\n",
        encoding="utf-8",
    )

    # (removido) Sincronizar shell UX — new-ux/ aposentado em 2026-08-06
    # sync_ux_assets()

    # Sincronizar thumbnails (origem → public)
    sync_thumbnails()

    # Injetar variáveis de ambiente no index.html (substituir placeholders)
    inject_env_vars()

    # Minificar CSS/JS se possivel
    if HAS_MINIFIERS:
        css_assets = list(PUBLIC.glob("assets/css/*.css"))
        js_assets = list(PUBLIC.glob("assets/js/*.js"))
        for css_path in css_assets:
            try:
                src = css_path.read_text(encoding="utf-8")
                dst = compress_css(src)
                if len(dst) < len(src):
                    css_path.write_text(dst, encoding="utf-8")
                    saved = len(src) - len(dst)
                    print(f"  ✅ CSS minificado: {css_path.name} ({saved} bytes)")
            except Exception as e:
                print(f"  ⚠️ Falha ao minificar CSS {css_path.name}: {e}")
        for js_path in js_assets:
            try:
                src = js_path.read_text(encoding="utf-8")
                dst = compress_js(src)
                if len(dst) < len(src):
                    js_path.write_text(dst, encoding="utf-8")
                    saved = len(src) - len(dst)
                    print(f"  ✅ JS minificado: {js_path.name} ({saved} bytes)")
            except Exception as e:
                print(f"  ⚠️ Falha ao minificar JS {js_path.name}: {e}")

    # WebP da capa (LCP) — JPG 1400x1400 permanece para RSS/iTunes
    optimize_cover_images()

    print(f"\n✅ Catálogo: {catalog_path} ({len(ordered)} episódios)")
    print(f"   Site URL: {base}")
    print(f"   RSS:      {abs_url('/feed.xml')}")
    print(f"   JSON:     {abs_url('/feed.json')}")
    return catalog


def inject_env_vars() -> None:
    """Substitui placeholders {{VAR}} no index.html com valores do .env"""
    index_path = PUBLIC / "index.html"
    if not index_path.exists():
        print("  ⚠️  index.html não encontrado — pulando injeção de env vars")
        return
    
    content = index_path.read_text(encoding="utf-8")
    
    # Substituir placeholders com valores do .env
    replacements = {
        "{{SUPABASE_URL}}": os.environ.get("SUPABASE_URL", ""),
        "{{SUPABASE_ANON_KEY}}": os.environ.get("SUPABASE_ANON_KEY", ""),
    }
    
    changed = False
    for placeholder, value in replacements.items():
        if placeholder in content:
            content = content.replace(placeholder, value)
            changed = True
            print(f"  🔐 Injetado: {placeholder} → {value[:20]}...")
    
    if changed:
        index_path.write_text(content, encoding="utf-8")
        print("  ✅ Env vars injetadas no index.html")
    else:
        print("  ℹ️  Nenhum placeholder encontrado no index.html")


def sync_thumbnails() -> None:
    """Copia thumbnails de thumbnails/ → public/thumbnails/."""
    if not THUMBNAILS_DIR.is_dir():
        return
    THUMBNAILS_PUBLIC.mkdir(parents=True, exist_ok=True)
    count = 0
    for date_dir in THUMBNAILS_DIR.iterdir():
        if not date_dir.is_dir():
            continue
        pub_dir = THUMBNAILS_PUBLIC / date_dir.name
        pub_dir.mkdir(parents=True, exist_ok=True)
        for f in date_dir.iterdir():
            if f.is_file() and f.suffix in ('.webp', '.jpg'):
                dest = pub_dir / f.name
                if not dest.exists() or dest.stat().st_mtime < f.stat().st_mtime:
                    shutil.copy2(f, dest)
                    count += 1
    if count:
        print(f"  🖼️  Thumbnails sync: {count} arquivo(s) copiado(s)")


def sync_ux_assets() -> None:
    """DESABILITADO (2026-08-06): new-ux/ aposentado. public/ agora é a única fonte.

    Mantido como stub para não quebrar chamadas antigas.
    """
    return


def optimize_cover_images() -> None:
    """Gera cover.webp a partir de cover.jpg (LCP). Mantém JPG para podcasts."""
    if not HAS_PIL or PILImage is None:
        print("  ⚠️  Pillow não instalada — pulando otimização de imagem")
        return

    cover_jpg = PUBLIC / "assets" / "cover.jpg"
    if not cover_jpg.exists():
        print("  ⚠️  cover.jpg não encontrado — pulando WebP")
        return

    try:
        webp_path = PUBLIC / "assets" / "cover.webp"
        with PILImage.open(cover_jpg) as img:
            rgb = img.convert("RGB")
            # LCP hero ~ display menor que 1400; redimensiona se > 800 mantendo aspect
            max_edge = 800
            if max(rgb.size) > max_edge:
                rgb.thumbnail((max_edge, max_edge), PILImage.Resampling.LANCZOS)
            rgb.save(webp_path, "WEBP", quality=82, method=6)

        jpg_kb = cover_jpg.stat().st_size / 1024
        webp_kb = webp_path.stat().st_size / 1024
        saved = jpg_kb - webp_kb
        print(
            f"  🖼️  Cover WebP: {webp_path.name} "
            f"({webp_kb:.1f} KiB, era {jpg_kb:.1f} KiB JPEG, −{saved:.1f} KiB)"
        )
    except Exception as e:
        print(f"  ⚠️  Falha ao gerar cover.webp: {e}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Publica catálogo + RSS do Web Jornal")
    parser.add_argument("--date", help="Publica/atualiza só esta data YYYY-MM-DD")
    parser.add_argument("--limit", type=int, default=200, help="Máx. episódios no feed")
    args = parser.parse_args()
    print("📡 publish_site — Vale da Liberdade")
    print(f"   SITE_URL={site_url()}")
    publish(limit=args.limit, only_date=args.date)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
