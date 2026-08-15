#!/usr/bin/env python3
"""Coletor de assets visuais por quadro (Brasil e Mundo). Restaurado 2026-08-15 a partir
do bytecode + spec — cascata Wikimedia → Pexels/Pixabay → og:image → DashScope.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:
    Image = ImageDraw = ImageFont = None

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
load_dotenv(ROOT / ".env")

EPS_DIR = ROOT / "output" / "brasil_e_mundo" / "episodes"
ASSETS_DIR = ROOT / "output" / "brasil_e_mundo" / "assets"
PROTO_DIR = ROOT / "references" / "youtube" / "prototype"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
WM_UA = "ValeLiberdadeVideoPipeline/1.0 (https://news.mob.tec.br; contato: pipeline@mob.tec.br)"
TIMEOUT = 20
MAX_IMAGE_SIDE = 1920
STOPWORDS = set("""
a o e é de do da dos das em no na nos nas um uma uns umas para por com sem sob
sobre entre até que se não sim mas como mais menos muito bem ao aos à às pelo pela
foi foram ser sendo está estão era eram tem têm já ainda também só depois antes
quando onde porque pois então aqui ali lá mesmo toda todo todos todas contra outra
outros outras outro algo alguém nada tudo cada qualquer
""".split())
OG_IMAGE_RE = re.compile(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', re.I)
OG_IMAGE_RE2 = re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', re.I)
PT_EN = {
    "estreito de ormuz": "strait of hormuz",
    "oriente médio": "middle east",
    "estados unidos": "united states",
    "ácido sulfúrico": "sulfuric acid",
    "segurança alimentar": "food security",
    "livre mercado": "free market",
    "cadeia de suprimentos": "supply chain",
    "enxofre": "sulfur",
    "fertilizante": "fertilizer",
    "petróleo": "oil",
    "guerra": "war",
    "navio": "ship",
    "brasil": "brazil",
    "china": "china",
}
DASHSCOPE_BASE = os.environ.get("DASHSCOPE_BASE_URL", "https://dashscope-intl.aliyuncs.com/api/v1")
MM_ENDPOINT = f"{DASHSCOPE_BASE}/services/aigc/multimodal-generation/generation"
MM_MODEL = "qwen-image-3.0"
MM_SIZE = "1664*928"
_SEEN_SHOT_HASHES: set[str] = set()


def log(msg: str) -> None:
    print(msg, flush=True)


def get(url: str, **kw) -> requests.Response:
    headers = dict(kw.pop("headers", {}) or {})
    headers.setdefault("User-Agent", WM_UA if "wikimedia" in url or "wikipedia" in url else UA)
    return requests.get(url, timeout=TIMEOUT, headers=headers, **kw)


def slugify(s: str, maxlen: int = 40) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", (s or "").lower()).strip("-")
    return s[:maxlen] or "img"


def extract_keywords(text: str, extra: list[str] | None = None, top: int = 6) -> list[str]:
    text = text or ""
    ents = re.findall(r"(?<![.!?]\s)(?<!\A)([A-ZÁÉÍÓÚÂÊÔÃÕ][\wÁÉÍÓÚÂÊÔÃÕáéíóúâêôãõç-]{2,}(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕ][\wÁÉÍÓÚÂÊÔÃÕáéíóúâêôãõç-]{2,})*)", text)
    words = re.findall(r"[A-Za-zÁ-úçÇ]{4,}", text.lower())
    score: dict[str, float] = {}
    for w in words:
        if w in STOPWORDS or w.endswith("mente"):
            continue
        score[w] = score.get(w, 0) + 1 + len(w) * 0.05
    for e in ents:
        score[e] = score.get(e, 0) + 8
    for e in extra or []:
        if e:
            score[e] = score.get(e, 0) + 10
    ordered = sorted(score, key=lambda k: (-score[k], -len(k)))
    return ordered[:top]


def _translate_phrase(s: str) -> str:
    low = (s or "").lower()
    for pt, en in sorted(PT_EN.items(), key=lambda kv: -len(kv[0])):
        if pt in low:
            low = low.replace(pt, en)
    return low


def en_keywords(kws: list[str]) -> list[str]:
    out = []
    for k in kws:
        t = _translate_phrase(k)
        if re.search(r"[àáâãéêíóôõúç]", t):
            continue
        out.append(t)
    return out


def fetch_og_image(url: str) -> str | None:
    try:
        r = get(url)
        if r.status_code >= 400:
            return None
        html = r.text
        m = OG_IMAGE_RE.search(html) or OG_IMAGE_RE2.search(html)
        if not m:
            return None
        img = m.group(1).replace("&amp;", "&")
        if img.startswith("//"):
            img = "https:" + img
        return img
    except Exception:
        return None


def build_og_pool(urls: list[str]) -> list[tuple[str, str]]:
    pool = []
    for u in urls:
        if not u or "youtube.com" in u or "youtu.be" in u:
            continue
        img = fetch_og_image(u)
        if img:
            pool.append((u, img))
    return pool


def wikimedia_search(query: str, limit: int = 5) -> list[dict]:
    try:
        r = get(
            "https://commons.wikimedia.org/w/api.php",
            params={
                "action": "query", "list": "search", "srsearch": f"{query} filetype:bitmap",
                "srnamespace": 6, "srlimit": limit, "format": "json",
            },
        )
        r.raise_for_status()
        return (r.json().get("query") or {}).get("search") or []
    except Exception as e:
        log(f"  ⚠️ wikimedia search: {e}")
        return []


def wikimedia_file_url(title: str, width: int = 1920) -> dict | None:
    try:
        r = get(
            "https://commons.wikimedia.org/w/api.php",
            params={
                "action": "query", "titles": title, "prop": "imageinfo",
                "iiprop": "url|size|extmetadata", "iiurlwidth": width, "format": "json",
            },
        )
        pages = (r.json().get("query") or {}).get("pages") or {}
        for pg in pages.values():
            info = (pg.get("imageinfo") or [{}])[0]
            desc = ((info.get("extmetadata") or {}).get("ImageDescription") or {}).get("value") or ""
            return {
                "url": info.get("thumburl") or info.get("url"),
                "orig": info.get("url"),
                "width": info.get("thumbwidth") or info.get("width"),
                "description": re.sub(r"<[^>]+>", "", desc)[:400],
                "title": title,
            }
    except Exception:
        return None
    return None


def pexels_search(query: str, limit: int = 5) -> list[dict]:
    key = os.environ.get("PEXELS_API_KEY") or ""
    if not key or "***" in key:
        return []
    try:
        r = requests.get(
            "https://api.pexels.com/v1/search",
            params={"query": query, "per_page": max(3, limit), "orientation": "landscape"},
            headers={"Authorization": key},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        return [{"url": p.get("src", {}).get("large2x"), "photographer": p.get("photographer")} for p in r.json().get("photos") or [] if p.get("src")]
    except Exception as e:
        log(f"  ⚠️ pexels: {e}")
        return []


def pixabay_search(query: str, limit: int = 5) -> list[dict]:
    key = os.environ.get("PIXABAY_API_KEY") or ""
    if not key or "***" in key:
        return []
    try:
        r = get(
            "https://pixabay.com/api/",
            params={"key": key, "q": query, "image_type": "photo", "orientation": "horizontal", "per_page": max(3, limit)},
        )
        r.raise_for_status()
        return [{"url": h.get("largeImageURL"), "user": h.get("user")} for h in r.json().get("hits") or []]
    except Exception as e:
        log(f"  ⚠️ pixabay: {e}")
        return []


def dashscope_generate(prompt: str) -> bytes | None:
    key = os.environ.get("DASHSCOPE_API_KEY") or ""
    if not key or "***" in key:
        return None
    body = {
        "model": MM_MODEL,
        "input": {"messages": [{"role": "user", "content": [{"text": prompt}]}]},
        "parameters": {"size": MM_SIZE},
    }
    try:
        r = requests.post(
            MM_ENDPOINT, json=body,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            timeout=90,
        )
        if r.status_code >= 400:
            return None
        data = r.json()
        url = None
        # several shapes
        try:
            url = data["output"]["choices"][0]["message"]["content"][0]["image"]
        except Exception:
            url = None
        if not url:
            return None
        img = get(url)
        return img.content if img.ok else None
    except Exception as e:
        log(f"  ⚠️ dashscope: {e}")
        return None


def download_image(url: str, dest: Path, min_width: int = 640) -> bool:
    if not url or Image is None:
        return False
    try:
        r = get(url)
        r.raise_for_status()
        im = Image.open(io.BytesIO(r.content))
        if im.mode == "P":
            im = im.convert("RGBA")
        w, h = im.size
        if max(w, h) < min_width:
            return False
        if max(w, h) > MAX_IMAGE_SIDE:
            im.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
        dest.parent.mkdir(parents=True, exist_ok=True)
        if im.mode in ("RGBA", "LA") and dest.suffix.lower() == ".png":
            im.save(dest)
        else:
            im.convert("RGB").save(dest.with_suffix(".jpg"), quality=88)
            if dest.suffix.lower() != ".jpg":
                dest = dest.with_suffix(".jpg")
        hsh = hashlib.md5(dest.read_bytes()[:4096]).hexdigest()
        if hsh in _SEEN_SHOT_HASHES:
            dest.unlink(missing_ok=True)
            return False
        _SEEN_SHOT_HASHES.add(hsh)
        return True
    except Exception as e:
        log(f"  ⚠️ download: {e}")
        return False


def relevant(title: str, desc: str, kws: list[str], min_rel: int = 2) -> int:
    blob = f"{title} {desc}".lower()
    hits = sum(1 for k in kws if k.lower() in blob)
    if kws and kws[0].lower() in (title or "").lower():
        hits = max(hits, 2)
    return hits if hits >= min_rel else 0


def _wikimedia_try(kws_en: list[str], dest: Path, min_rel: int) -> dict | None:
    query = " ".join(kws_en[:3])
    if not query:
        return None
    for hit in wikimedia_search(query):
        title = hit.get("title") or ""
        info = wikimedia_file_url(title)
        if not info or not info.get("url"):
            continue
        rel = relevant(title, info.get("description") or "", kws_en, min_rel)
        if rel < min_rel:
            continue
        if download_image(info["url"], dest):
            return {"kind": "wikimedia", "title": title, "image_url": info["url"], "query": query,
                    "description": info.get("description"), "relevance": rel}
    return None


def _stock_try(kws_en: list[str], dest: Path) -> dict | None:
    q = " ".join(kws_en[:3])
    for src in pexels_search(q) + pixabay_search(q):
        url = src.get("url")
        if url and download_image(url, dest):
            return {"kind": "stock", "image_url": url, "query": q}
    return None


def _og_rotated(pool: list[tuple[str, str]], idx: int, dest: Path) -> dict | None:
    if not pool:
        return None
    n = len(pool)
    ordered = [pool[(idx + i) % n] for i in range(n)]
    for pass_land in (True, False):
        for page, img in ordered:
            if download_image(img, dest):
                if pass_land and Image is not None:
                    try:
                        with Image.open(dest.with_suffix(".jpg") if dest.suffix != ".jpg" else dest) as im:
                            w, h = im.size
                        if h > w * 1.1:
                            dest.with_suffix(".jpg").unlink(missing_ok=True)
                            continue
                    except Exception:
                        pass
                host_m = re.match(r"https?://([^/]+)", page)
                host = re.sub(r"^www\.", "", host_m.group(1) if host_m else "")
                return {"kind": "og:image", "fonte_url": page, "image_url": img, "veiculo": host}
    return None


def _dashscope_try(text: str, dest: Path) -> dict | None:
    prompt = (
        "Editorial photograph, 16:9, cinematic lighting, no text, no words, no letters, "
        "no typography, no captions, no signage. Visual metaphor of: "
        + (text or "news commentary")[:280]
    )
    blob = dashscope_generate(prompt)
    if not blob or Image is None:
        return None
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        im = Image.open(io.BytesIO(blob)).convert("RGB")
        im.save(dest.with_suffix(".jpg"), quality=88)
        return {"kind": "dashscope", "model": MM_MODEL}
    except Exception:
        return None


def collect_for_quadro(q: dict, dest_dir: Path, og_pool, idx: int, generate: bool, force: bool, min_width: int) -> dict:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "image.jpg"
    src_path = dest_dir / "image_source.json"
    if dest.exists() and src_path.exists() and not force:
        src = json.loads(src_path.read_text(encoding="utf-8"))
        return {"image_path": str(dest.relative_to(PROTO_DIR.parent.parent.parent) if False else dest), "image_source": src}

    text = q.get("script_text") or ""
    extra = [q.get("fonte_nome") or "", q.get("chapter_label") or ""]
    kws = extract_keywords(text, extra)
    kws_en = en_keywords(kws)
    (dest_dir / "keywords.json").write_text(json.dumps({"pt": kws, "en": kws_en}, ensure_ascii=False, indent=2), encoding="utf-8")

    typ = q.get("type") or ""
    src = None
    if typ == "comentario_materia":
        src = _wikimedia_try(kws_en, dest, min_rel=2) or _stock_try(kws_en, dest) or _og_rotated(og_pool, idx, dest)
    else:
        src = _og_rotated(og_pool, idx, dest) or _stock_try(kws_en, dest) or _wikimedia_try(kws_en, dest, min_rel=1)
    if not src and generate:
        src = _dashscope_try(text, dest)

    img_file = dest if dest.exists() else dest.with_suffix(".jpg")
    out = {
        "id": q.get("id"),
        "type": typ,
        "keywords": kws,
        "image_path": str(img_file) if img_file.exists() else None,
        "image_source": src,
        "screenshot_materia": q.get("screenshot_materia"),
        "fonte_url": q.get("fonte_url"),
        "fonte_nome": q.get("fonte_nome"),
    }
    if src:
        src_path.write_text(json.dumps(src, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def _contact_sheet(results: list[dict], dest: Path) -> None:
    if Image is None or not results:
        return
    cells = []
    for r in results:
        p = r.get("image_path")
        if p and Path(p).exists():
            cells.append(Path(p))
    if not cells:
        return
    tw, th = 320, 180
    cols = 3
    rows = (len(cells) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tw, rows * th), (20, 20, 20))
    for i, p in enumerate(cells):
        try:
            im = Image.open(p).convert("RGB")
            im.thumbnail((tw, th))
            x = (i % cols) * tw + (tw - im.width) // 2
            y = (i // cols) * th + (th - im.height) // 2
            sheet.paste(im, (x, y))
        except Exception:
            continue
    dest.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(dest, quality=85)


def update_quadros(qpath: Path, results: list[dict], video_id: str) -> None:
    data = json.loads(qpath.read_text(encoding="utf-8"))
    by_id = {r.get("id"): r for r in results}
    for q in data.get("quadros") or []:
        r = by_id.get(q.get("id"))
        if not r:
            continue
        if r.get("image_path"):
            rel = Path(r["image_path"])
            try:
                q["image_path"] = str(rel.relative_to(PROTO_DIR))
            except ValueError:
                q["image_path"] = f"assets/{video_id}/{q['id']}/image.jpg"
        if r.get("image_source"):
            q["image_source"] = r["image_source"]
        if r.get("screenshot_materia"):
            q["screenshot_materia"] = r["screenshot_materia"]
    qpath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def build(video_id: str, quadros_path: Path | None, generate: bool, force: bool, min_width: int, skip_screenshots: bool) -> Path:
    qpath = quadros_path or (PROTO_DIR / f"quadros-{video_id}.json")
    if not qpath.exists():
        raise SystemExit(f"❌ {qpath} — rode bm_quadros_mapper.py primeiro")
    data = json.loads(qpath.read_text(encoding="utf-8"))
    urls = []
    fp = data.get("fonte_principal") or {}
    if fp.get("fonte_url"):
        urls.append(fp["fonte_url"])
    for r in data.get("fonte_referencias") or []:
        if r.get("url"):
            urls.append(r["url"])
    for q in data.get("quadros") or []:
        if q.get("fonte_url"):
            urls.append(q["fonte_url"])
    # unique preserve order
    seen = set()
    uniq = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    log(f"og:image pool ← {len(uniq)} urls")
    og_pool = build_og_pool(uniq)
    log(f"  acessíveis: {len(og_pool)}")

    ep_dir = ASSETS_DIR / video_id
    ep_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for i, q in enumerate(data.get("quadros") or []):
        log(f"→ {q.get('id')} {q.get('type')}")
        r = collect_for_quadro(q, ep_dir / q["id"], og_pool, i, generate, force, min_width)
        results.append(r)

    manifest = {"video_id": video_id, "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "quadros": results}
    (ep_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    _contact_sheet(results, ep_dir / "contact_sheet.jpg")
    update_quadros(qpath, results, video_id)
    ok = sum(1 for r in results if r.get("image_path"))
    log(f"✅ assets {video_id}: {ok}/{len(results)} com imagem → {ep_dir}")
    return ep_dir


def main() -> int:
    ap = argparse.ArgumentParser(description="Coletor de assets por quadro BM")
    ap.add_argument("--video-id", required=True)
    ap.add_argument("--quadros", default=None)
    ap.add_argument("--generate", action="store_true")
    ap.add_argument("--with-videos", action="store_true")
    ap.add_argument("--skip-screenshots", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--min-width", type=int, default=640)
    args = ap.parse_args()
    build(
        args.video_id,
        Path(args.quadros) if args.quadros else None,
        args.generate, args.force, args.min_width, args.skip_screenshots,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
