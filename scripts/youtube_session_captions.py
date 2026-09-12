#!/usr/bin/env python3
"""Legendas YouTube via cookies de sessão, sem yt-dlp.

O YouTube responde "Sign in to confirm you're not a bot" no yt-dlp mesmo
quando a página autenticada já lista captionTracks. Este módulo:

1. Lê cookies Netscape **ou** JSON de extensão (Cookie-Editor / Bazar).
2. Prefere o arquivo com LOGIN_INFO / PSIDs (sessão real).
3. GET /watch?v=ID com Cookie header congelado (não deixa o Set-Cookie
   do YouTube apagar LOGIN_INFO no jar).
4. Lê ytInitialPlayerResponse (título, descrição, captionTracks).
5. GET timedtext (json3 → xml). Se o corpo vier vazio (POT/exp=xpe),
   tenta de novo sem o parâmetro exp.

Não grava de volta no arquivo de cookies — o yt-dlp faz isso e transforma
uma sessão logada em jar de visitante.
"""
from __future__ import annotations

import html as htmllib
import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from xml.etree import ElementTree as ET

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

AUTH_COOKIE_NAMES = frozenset(
    {
        "LOGIN_INFO",
        "SID",
        "HSID",
        "SSID",
        "APISID",
        "SAPISID",
        "__Secure-1PSID",
        "__Secure-1PAPISID",
        "__Secure-3PSID",
        "__Secure-3PAPISID",
        "__Secure-1PSIDTS",
        "__Secure-3PSIDTS",
        "__Secure-1PSIDCC",
        "__Secure-3PSIDCC",
    }
)

_DEFAULT_CANDIDATES = (
    PROJECT_ROOT / "credentials" / "www.youtube.com_cookies.txt",
    PROJECT_ROOT / "credentials" / "youtube_cookies_heron.txt",
    PROJECT_ROOT / "credentials" / "youtube_cookies_bazar.txt",
    PROJECT_ROOT / "credentials" / "youtube_cookies.txt",
    Path.home() / ".config" / "yt-dlp" / "cookies.txt",
)

WATCH_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

_PT_LANGS = ("pt", "pt-BR", "pt-PT")


def parse_cookie_file(path: Path) -> list[dict[str, Any]]:
    """Aceita Netscape cookies.txt **ou** JSON de extensão Chrome."""
    raw = path.read_text(encoding="utf-8", errors="replace").lstrip("\ufeff")
    stripped = raw.lstrip()
    if stripped.startswith("[") or stripped.startswith("{"):
        return _parse_json_cookies(stripped)
    return _parse_netscape(raw)


def _parse_json_cookies(raw: str) -> list[dict[str, Any]]:
    data = json.loads(raw)
    if isinstance(data, dict):
        data = data.get("cookies") or data.get("data") or []
    if not isinstance(data, list):
        return []
    out: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        value = item.get("value")
        if not name or value is None:
            continue
        domain = str(item.get("domain") or ".youtube.com")
        path = str(item.get("path") or "/")
        exp = item.get("expirationDate") or item.get("expiry") or item.get("expires") or 0
        try:
            exp_i = int(float(exp))
        except (TypeError, ValueError):
            exp_i = 0
        out.append(
            {
                "name": name,
                "value": str(value),
                "domain": domain,
                "path": path,
                "secure": bool(item.get("secure", True)),
                "httpOnly": bool(item.get("httpOnly") or item.get("http_only")),
                "expirationDate": exp_i,
            }
        )
    return out


def _parse_netscape(raw: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line in raw.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        domain, _flag, path, secure, exp, name, value = parts[:7]
        try:
            exp_i = int(float(exp)) if exp else 0
        except ValueError:
            exp_i = 0
        out.append(
            {
                "name": name.strip(),
                "value": value,
                "domain": domain.strip() or ".youtube.com",
                "path": path.strip() or "/",
                "secure": str(secure).upper() == "TRUE",
                "httpOnly": False,
                "expirationDate": exp_i,
            }
        )
    return out


def _is_youtube_domain(domain: str) -> bool:
    d = (domain or "").lower().lstrip(".")
    return d == "youtube.com" or d.endswith(".youtube.com") or d in {
        "youtu.be",
        "youtube-nocookie.com",
        "googlevideo.com",
        "ytimg.com",
        "ggpht.com",
    } or d.endswith(".google.com") or d == "google.com"


def score_cookie_records(records: list[dict[str, Any]]) -> int:
    """Sessão logada vale mais que jar de visitante (VISITOR_* / PREF).

    Jar só-YouTube ganha de dump de navegador inteiro com o mesmo LOGIN_INFO:
    o dump mistura SID de outros sites e o merge pisa na sessão boa.
    """
    names = {r.get("name") for r in records}
    score = 0
    if "LOGIN_INFO" in names:
        score += 10
    score += 2 * len(names & AUTH_COOKIE_NAMES)
    if names & {"VISITOR_INFO1_LIVE", "YSC", "PREF"}:
        score += 1
    domains = {(r.get("domain") or "") for r in records if r.get("domain")}
    if domains and all(_is_youtube_domain(d) for d in domains):
        score += 5
    return score


def _candidate_paths(candidates: list[Path] | None = None) -> list[Path]:
    env = os.environ.get("YTDLP_COOKIES") or os.environ.get("YOUTUBE_COOKIES") or ""
    paths: list[Path] = []
    if env:
        paths.append(Path(env))
    paths.extend(candidates or list(_DEFAULT_CANDIDATES))
    out: list[Path] = []
    seen: set[Path] = set()
    for p in paths:
        if not p or str(p) in {".", ""}:
            continue
        try:
            resolved = p.expanduser().resolve()
        except OSError:
            continue
        if resolved in seen or not resolved.is_file() or resolved.stat().st_size < 80:
            continue
        seen.add(resolved)
        out.append(resolved)
    return out


def pick_cookie_file(candidates: list[Path] | None = None) -> Path | None:
    """Escolhe o jar com maior score; empate vai para o arquivo mais novo."""
    best: tuple[int, float, Path] | None = None
    for resolved in _candidate_paths(candidates):
        try:
            recs = parse_cookie_file(resolved)
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        sc = score_cookie_records(recs)
        try:
            mtime = resolved.stat().st_mtime
        except OSError:
            mtime = 0.0
        if best is None or (sc, mtime) > (best[0], best[1]):
            best = (sc, mtime, resolved)
    return best[2] if best else None


def _youtube_only_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """SID/LOGIN_INFO de fandom/ads no dump de navegador não podem ir no header."""
    out: list[dict[str, Any]] = []
    for rec in records:
        domain = rec.get("domain") or ".youtube.com"
        if _is_youtube_domain(domain):
            out.append(rec)
    return out


def load_merged_cookie_records(candidates: list[Path] | None = None) -> list[dict[str, Any]]:
    """Une todos os arquivos: LOGIN_INFO/PSIDs de um + VISITOR/PREF do outro."""
    ranked: list[tuple[int, list[dict[str, Any]]]] = []
    for resolved in _candidate_paths(candidates):
        try:
            recs = _youtube_only_records(parse_cookie_file(resolved))
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        if recs:
            ranked.append((score_cookie_records(recs), recs))
    ranked.sort(key=lambda x: x[0])
    by_name: dict[str, dict[str, Any]] = {}
    for _sc, recs in ranked:
        for rec in recs:
            name = rec.get("name") or ""
            if name:
                by_name[name] = rec
    return list(by_name.values())


def cookie_header_from_records(records: list[dict[str, Any]]) -> str:
    """Header Cookie estático — o YouTube não consegue apagar LOGIN_INFO no jar."""
    parts: list[str] = []
    seen: set[str] = set()
    for rec in records:
        name = rec.get("name") or ""
        if not name or name in seen:
            continue
        seen.add(name)
        parts.append(f"{name}={rec.get('value', '')}")
    return "; ".join(parts)


def netscape_from_records(records: list[dict[str, Any]]) -> str:
    """Converte JSON/records para Netscape. Não escreve no arquivo de origem."""
    now = int(time.time())
    lines = ["# Netscape HTTP Cookie File", "# converted; do not feed back into yt-dlp --cookies dump", ""]
    for rec in records:
        domain = rec.get("domain") or ".youtube.com"
        flag = "TRUE" if domain.startswith(".") else "FALSE"
        path = rec.get("path") or "/"
        secure = "TRUE" if rec.get("secure") else "FALSE"
        exp = rec.get("expirationDate") or 0
        try:
            exp_i = int(exp)
        except (TypeError, ValueError):
            exp_i = 0
        if exp_i <= 0:
            exp_i = now + 30 * 24 * 3600
        name = rec.get("name") or ""
        value = rec.get("value") or ""
        if not name:
            continue
        lines.append(f"{domain}\t{flag}\t{path}\t{secure}\t{exp_i}\t{name}\t{value}")
    return "\n".join(lines) + "\n"


def extract_yt_json_object(html: str, var_name: str) -> dict[str, Any] | None:
    marker = f"var {var_name} ="
    i = html.find(marker)
    if i < 0:
        marker = f"{var_name} ="
        i = html.find(marker)
        if i < 0:
            return None
    i = html.find("{", i)
    if i < 0:
        return None
    depth = 0
    for j, ch in enumerate(html[i:], i):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(html[i : j + 1])
                except json.JSONDecodeError:
                    return None
                return obj if isinstance(obj, dict) else None
    return None


def select_caption_track(player: dict[str, Any]) -> dict[str, Any] | None:
    caps = (
        ((player.get("captions") or {}).get("playerCaptionsTracklistRenderer") or {}).get(
            "captionTracks"
        )
        or []
    )
    if not caps:
        return None

    def score(track: dict[str, Any]) -> tuple[int, int, int]:
        lang = (track.get("languageCode") or "").lower()
        kind = track.get("kind") or ""
        pt = 2 if lang in {x.lower() for x in _PT_LANGS} else (1 if lang.startswith("pt") else 0)
        manual = 1 if kind != "asr" else 0
        return (pt, manual, 1)

    return max(caps, key=score)


def strip_timedtext_exp(url: str) -> str:
    """exp=xpe no timedtext costuma exigir PO Token e devolve 200 vazio."""
    parsed = urlparse(url)
    query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k != "exp"]
    return urlunparse(parsed._replace(query=urlencode(query)))


def parse_caption_payload(payload: str, kind: str) -> str:
    if not payload or not payload.strip():
        return ""
    if kind == "json3":
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return ""
        parts: list[str] = []
        prev = ""
        for event in data.get("events") or []:
            chunk = "".join(seg.get("utf8", "") for seg in (event.get("segs") or []))
            chunk = chunk.replace("\n", " ").strip()
            if chunk and chunk != prev:
                parts.append(chunk)
                prev = chunk
        return " ".join(parts)
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        return ""
    parts = []
    prev = ""
    for node in root.iter("text"):
        text = htmllib.unescape("".join(node.itertext())).replace("\n", " ").strip()
        if text and text != prev:
            parts.append(text)
            prev = text
    return " ".join(parts)


def _session_from_header(cookie_header: str) -> requests.Session:
    sess = requests.Session()
    sess.headers.update(
        {
            "User-Agent": WATCH_UA,
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Cookie": cookie_header,
        }
    )
    sess.cookies.clear()
    return sess


def fetch_watch_html(video_id: str, cookie_header: str, timeout: float = 30.0) -> str:
    sess = _session_from_header(cookie_header)
    url = f"https://www.youtube.com/watch?v={video_id}"
    resp = sess.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def fetch_timedtext(base_url: str, cookie_header: str, timeout: float = 30.0) -> str:
    sess = _session_from_header(cookie_header)
    sess.headers["Accept"] = "*/*"
    headers = {
        "Referer": "https://www.youtube.com/",
        "Origin": "https://www.youtube.com",
        "Cookie": cookie_header,
    }
    candidates = [base_url, strip_timedtext_exp(base_url)]
    seen: set[str] = set()
    for url in candidates:
        if not url or url in seen:
            continue
        seen.add(url)
        for extra in ({"fmt": "json3"}, {}):
            try:
                resp = sess.get(url, params=extra or None, headers=headers, timeout=timeout)
            except requests.RequestException:
                continue
            if resp.status_code != 200 or not resp.content:
                continue
            kind = "json3" if extra.get("fmt") == "json3" or "json3" in (resp.text[:40].lower()) else "xml"
            text = parse_caption_payload(resp.text, kind)
            if len(text.split()) >= 20:
                return text
            if extra.get("fmt") == "json3" and not text:
                text = parse_caption_payload(resp.text, "xml")
                if len(text.split()) >= 20:
                    return text
    return ""


def extract_via_session_cookies(
    video_id: str,
    cookie_path: Path | None = None,
    timeout: float = 30.0,
) -> dict[str, Any] | None:
    """Retorna dict com title/description/transcript ou None."""
    path = cookie_path or pick_cookie_file()
    records: list[dict[str, Any]] = []
    if path is not None:
        try:
            records = _youtube_only_records(parse_cookie_file(path))
        except (OSError, json.JSONDecodeError, ValueError):
            records = []
    # Não mesclar jars: LOGIN_INFO/SID de arquivos velhos + dump de navegador
    # geram header híbrido e o watch page volta LOGIN_REQUIRED.
    if not records:
        return None
    header = cookie_header_from_records(records)
    if not header:
        return None
    last: dict[str, Any] | None = None
    delays = (0.0, 1.5, 4.0)
    for i, wait in enumerate(delays):
        if wait:
            time.sleep(wait)
        try:
            html = fetch_watch_html(video_id, header, timeout=timeout)
        except requests.RequestException:
            continue
        player = extract_yt_json_object(html, "ytInitialPlayerResponse") or {}
        details = player.get("videoDetails") or {}
        title = details.get("title") or ""
        description = details.get("shortDescription") or ""
        channel = details.get("author") or ""
        try:
            duration_s = int(details.get("lengthSeconds") or 0)
        except (TypeError, ValueError):
            duration_s = 0
        play = player.get("playabilityStatus") or {}
        track = select_caption_track(player)
        if play.get("status") == "LOGIN_REQUIRED" and not title:
            last = {
                "ok": False,
                "reason": "bot_or_login",
                "cookie_path": str(path) if path else "",
                "playability": play.get("reason") or play.get("status"),
            }
            continue
        transcript = ""
        if track and track.get("baseUrl"):
            transcript = fetch_timedtext(track["baseUrl"], header, timeout=timeout)
        if transcript and len(transcript.split()) >= 20:
            return {
                "ok": True,
                "cookie_path": str(path) if path else "",
                "title": title,
                "description": description,
                "channel": channel,
                "duration_s": duration_s,
                "transcript": transcript,
                "language": (track or {}).get("languageCode") or "",
                "kind": (track or {}).get("kind") or "",
            }
        last = {
            "ok": False,
            "reason": "no_captions" if not track else "empty_timedtext",
            "cookie_path": str(path) if path else "",
            "title": title,
            "description": description,
            "channel": channel,
            "duration_s": duration_s,
            "has_track": bool(track),
        }
    return last
