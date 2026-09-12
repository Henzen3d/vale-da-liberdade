"""Estado, episódio, cenas e metadados do vídeo BM (sem Playwright)."""
from __future__ import annotations

import hashlib
import html as _html
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from bm_video.constants import *  # noqa: F403
from bm_video.render import probe_duration_s

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


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"videos": {}}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


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


def highlight_from_script(text: str, limit: int = 48) -> str:
    """Ponto alto do roteiro para capítulo YouTube — não o nome do veículo."""
    s = _unescape(text or "").strip()
    s = re.sub(r"^\s*peter:\s*", "", s, flags=re.I)
    if not s or _CTA_RE.search(s):
        return ""
    sent = s
    for sep in (". ", "! ", "? ", "; "):
        i = s.find(sep)
        if 18 <= i <= 160:
            sent = s[:i].strip()
            break
    sent = _OUTLET_PREFIX_RE.sub("", sent).strip()
    sent = re.sub(
        r"^(?:traz(?: os bastidores)?|mostra|aponta|relata|informa)(?: que)?\s+",
        "",
        sent,
        flags=re.I,
    )
    sent = re.sub(r"\s+", " ", sent).strip(" ,;:—-")
    if len(sent) > limit:
        cut = sent[:limit]
        for sep in (", ", " e ", " que ", " para ", " sobre "):
            j = cut.rfind(sep)
            if j >= 18:
                cut = cut[:j]
                break
        else:
            cut = cut.rsplit(" ", 1)[0]
        sent = cut.strip(" ,;:—-")
    if not sent:
        return ""
    return sent[0].upper() + sent[1:]


def _chapter_labels_from_episode(episode: dict, n: int) -> list[str]:
    """N rótulos a partir do desenvolvimento (abertura só se faltar texto)."""
    if n <= 0 or not episode:
        return []
    labels: list[str] = []
    seen: set[str] = set()
    for key in ("desenvolvimento", "abertura"):
        for item in episode.get(key) or []:
            raw = item.get("texto") if isinstance(item, dict) else item
            h = highlight_from_script(raw or "")
            keyn = h.casefold()
            if not h or keyn in seen:
                continue
            seen.add(keyn)
            labels.append(h)
            if len(labels) >= n:
                return labels
    return labels


def _inject_assista(desc: str, assista: str) -> str:
    if not assista:
        return desc
    if "Fontes:" in desc:
        return desc.replace("Fontes:", assista + "Fontes:", 1)
    return desc.rstrip() + "\n\n" + assista


def _bm_seo_description(
    video_id: str,
    episode: dict,
    title: str,
    refs_ok: list[str],
    tags: list[str],
) -> str:
    """Corpo SEO da skill descricoes-vale-liberdade — nunca o início cru do roteiro."""
    try:
        from description_optimizer import (
            clean_youtube_description,
            deterministic_description,
            generate_description_via_llm,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"  ⚠️  description_optimizer indisponível: {exc}")
        return ""
    ctx = {
        "video_id": video_id,
        "title": title,
        "resumo": episode_summary(episode, limit=1200) or title,
        "is_bm": True,
    }
    raw_body = None
    llm_tags: list[str] = []
    try:
        llm_res = generate_description_via_llm(ctx)
        if llm_res:
            raw_body, llm_tags = llm_res
    except Exception as exc:  # noqa: BLE001
        print(f"  ⚠️  LLM da descrição falhou: {exc}")
    if not raw_body:
        raw_body = deterministic_description(ctx)
    hashtags = llm_tags or [f"#{t}" for t in tags if t][:3]
    return clean_youtube_description(
        raw_body,
        sources=refs_ok,
        hashtags=hashtags,
        is_bm=True,
    )


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


def build_chapters(
    scenes: list[dict],
    dur: float,
    timeline_beats: list[Any] | None = None,
    episode: dict | None = None,
) -> list[tuple[float, str]]:
    """Timestamps das cenas; rótulos = pontos altos do roteiro, não o veículo do print."""
    entries: list[tuple[float, str]] = []
    if timeline_beats:
        for beat in timeline_beats:
            b_dict = beat.to_dict() if hasattr(beat, "to_dict") else dict(beat)
            if b_dict.get("kind") == "broll":
                continue
            t0 = float(b_dict.get("t0", 0.0))
            label = (b_dict.get("veiculo") or "Fonte").strip()
            if label and label.lower() not in {"transição", "introdução"}:
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

    highlight_slots = sum(1 for ts, label in entries if label != "Conclusão")
    highlights = _chapter_labels_from_episode(episode or {}, highlight_slots)
    if highlights:
        hi = 0
        rewritten: list[tuple[float, str]] = []
        for ts, label in entries:
            if label == "Conclusão":
                rewritten.append((ts, label))
                continue
            rewritten.append((ts, highlights[hi] if hi < len(highlights) else label))
            hi += 1
        entries = rewritten

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


def chapters_block(
    scenes: list[dict],
    dur: float,
    timeline_beats: list[Any] | None = None,
    episode: dict | None = None,
) -> str:
    ch = build_chapters(scenes, dur, timeline_beats=timeline_beats, episode=episode)
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
    desc = _bm_seo_description(video_id, episode, title, refs_ok, tags)
    if not desc:
        desc = DESC_TEMPLATE.format(
            summary=summary,
            app=APP_URL,
            assista=assista,
            refs="\n".join(refs_ok) if refs_ok else "—",
            tags=" ".join(t.replace(" ", "") for t in tags if t),
        )
    else:
        desc = _inject_assista(desc, assista)
    if scenes or timeline_beats:
        desc += chapters_block(
            scenes or [],
            probe_duration_s(audio) or 0.0,
            timeline_beats=timeline_beats,
            episode=episode,
        )
    seen: set[str] = set()
    uniq: list[str] = []
    for t in tags:
        t = _unescape(str(t)).strip()
        if t and t.lower() not in seen:
            seen.add(t.lower())
            uniq.append(t)
    return title, desc, uniq


def _normalize_beat_v2(beat: Any) -> dict:
    """Normaliza SceneBeat / SceneBeatV2 / dict para dict V2 no recorder."""
    from bm_scene_timeline import SceneBeat, SceneBeatV2

    _v2_kinds = frozenset({"source", "x-post", "quote", "document", "timeline", "chart", "comparison", "broll"})
    _role_map = {
        "quote": "declaracao_forte",
        "document": "evidencia_documental",
        "timeline": "contexto_cronologico",
        "chart": "impacto_economico",
        "comparison": "confronto_posicoes",
    }

    if beat is None:
        return {
            "t0": 0.0, "t1": 0.0,
            "semantic_role": "apresentacao_fato",
            "visual_component": "source",
            "visual_variant": "",
            "visual_payload": {},
            "url": "", "veiculo": "",
            "shot": None, "video": None, "broll_file": None,
            "kind": "source",
        }

    if isinstance(beat, SceneBeatV2):
        out = beat.to_dict()
        out["kind"] = out.get("visual_component") or "source"
        return out

    if isinstance(beat, SceneBeat):
        x_post = beat.x_post
        kind_raw = (beat.kind or "source").strip() or "source"
        # SceneBeat now carries visual_component directly
        vis_comp = getattr(beat, "visual_component", None) or kind_raw
        if vis_comp not in _v2_kinds:
            vis_comp = "source"
        overrides: dict = {}
        if vis_comp not in {"source", "broll", "x-post"}:
            overrides["visual_component"] = vis_comp
            overrides["semantic_role"] = _role_map.get(vis_comp, "apresentacao_fato")
            if getattr(beat, "visual_payload", None):
                overrides["visual_payload"] = dict(beat.visual_payload)
            if getattr(beat, "visual_variant", None):
                overrides["visual_variant"] = beat.visual_variant
        out = SceneBeatV2.from_legacy(beat, **overrides).to_dict()
        out["kind"] = vis_comp if vis_comp in _v2_kinds else (out.get("visual_component") or "source")
        out["visual_component"] = out.get("visual_component") or out["kind"]
        if x_post:
            out["x_post"] = x_post
        return out

    if hasattr(beat, "to_dict") and hasattr(beat, "visual_component"):
        out = dict(beat.to_dict())
        out.setdefault("visual_payload", {})
        out.setdefault("visual_variant", "")
        out["kind"] = out.get("visual_component") or out.get("kind") or "source"
        return out

    d = dict(beat) if not isinstance(beat, dict) else dict(beat)
    if d.get("visual_component") is not None or d.get("visual_payload") is not None:
        out = {
            "t0": float(d.get("t0", 0.0) or 0.0),
            "t1": float(d.get("t1", 0.0) or 0.0),
            "semantic_role": d.get("semantic_role") or "apresentacao_fato",
            "visual_component": d.get("visual_component") or d.get("kind") or "source",
            "visual_variant": d.get("visual_variant") or "",
            "visual_payload": dict(d.get("visual_payload") or {}),
            "url": d.get("url") or "",
            "veiculo": d.get("veiculo") or "",
            "shot": d.get("shot"),
            "video": d.get("video"),
            "broll_file": d.get("broll_file"),
        }
        out["kind"] = out["visual_component"] or d.get("kind") or "source"
        x_post = d.get("x_post") or d.get("xPost")
        if x_post:
            out["x_post"] = x_post
        return out

    from bm_scene_timeline import SceneBeat as _SB
    kind_raw = (d.get("kind") or "source").strip() or "source"
    legacy = _SB(
        t0=float(d.get("t0", 0.0) or 0.0),
        t1=float(d.get("t1", 0.0) or 0.0),
        url=d.get("url") or "",
        veiculo=d.get("veiculo") or "",
        kind=kind_raw if kind_raw in {"source", "broll", "x-post"} else "source",
        shot=d.get("shot"),
        video=d.get("video"),
        broll_file=d.get("broll_file"),
        x_post=d.get("x_post") or d.get("xPost"),
    )
    overrides2: dict = {}
    if kind_raw in _v2_kinds and kind_raw not in {"source", "broll", "x-post"}:
        overrides2["visual_component"] = kind_raw
        overrides2["semantic_role"] = _role_map.get(kind_raw, "apresentacao_fato")
        if d.get("visual_payload"):
            overrides2["visual_payload"] = dict(d.get("visual_payload") or {})
        if d.get("visual_variant"):
            overrides2["visual_variant"] = d.get("visual_variant") or ""
    out2 = SceneBeatV2.from_legacy(legacy, **overrides2).to_dict()
    out2["kind"] = kind_raw if kind_raw in _v2_kinds else (out2.get("visual_component") or "source")
    out2["visual_component"] = out2.get("visual_component") or out2["kind"]
    if legacy.x_post:
        out2["x_post"] = legacy.x_post
    return out2


def _omnibox_url(url: str | None) -> str:
    """URL da barra do mockup. Nunca o portal Vale — isso é o template branco."""
    u = (url or "").strip()
    if not u:
        return ""
    low = u.lower()
    if "news.mob.tec.br" in low or "valedaliberdade.com.br" in low:
        return ""
    return u


def _build_mockup_update_payload(beat_v2: dict) -> dict:
    """Payload para window.VDL_MOCKUP.update — campos V2 + legado."""
    from urllib.parse import quote as _q
    kind = beat_v2.get("visual_component") or beat_v2.get("kind") or "source"
    page_image = f"/shots/{beat_v2['shot']}" if beat_v2.get("shot") else ""
    page_video = beat_v2.get("video") or ""
    if kind == "broll" and beat_v2.get("broll_file"):
        page_video = f"/broll/{_q(beat_v2['broll_file'])}"
    payload: dict = {
        "pageImage": page_image,
        "pageVideo": page_video,
        "kind": kind,
        "visual_component": kind,
        "visual_variant": beat_v2.get("visual_variant") or "",
        "visual_payload": dict(beat_v2.get("visual_payload") or {}),
    }
    url = _omnibox_url(beat_v2.get("url"))
    if url:
        payload["url"] = url
    x_post = beat_v2.get("x_post") or beat_v2.get("xPost")
    if x_post:
        payload["xPost"] = x_post
    return payload


def _safe_mockup_update(page: Any, payload: dict, *, label: str = "") -> None:
    """Chama VDL_MOCKUP.update sem abortar a gravação em caso de erro."""
    try:
        page.evaluate(
            """(data) => {
              if (!window.VDL_MOCKUP) return;
              try {
                window.VDL_MOCKUP.update(data);
              } catch (err) {
                console.warn('VDL_MOCKUP.update failed', err);
              }
            }""",
            payload,
        )
    except Exception as exc:  # noqa: BLE001
        tag = f" ({label})" if label else ""
        print(f"  ⚠️  mockup update{tag} falhou — segue tela default: {exc}")


def _components_used_from_beats(beats: list | None) -> list:
    comps: list = []
    for beat in beats or []:
        b = _normalize_beat_v2(beat)
        comps.append(b.get("visual_component") or b.get("kind") or "source")
    return comps


def _dominant_style_from_components(components: list) -> str:
    if not components:
        return "standard_source"
    counts: dict = {}
    for c in components:
        counts[c] = counts.get(c, 0) + 1
    top = max(counts.items(), key=lambda kv: kv[1])[0]
    return "standard_source" if top == "source" else top


def append_last_video(
    video_id: str,
    date: str,
    timeline_beats: list | None = None,
    *,
    dominant_style: str | None = None,
    components_used: list | None = None,
    max_history: int = 30,
) -> None:
    """Append/update anti-fadiga em last_videos.json."""
    comps = list(components_used) if components_used is not None else _components_used_from_beats(timeline_beats)
    style = dominant_style or _dominant_style_from_components(comps)
    entry = {
        "video_id": video_id,
        "date": date,
        "dominant_style": style,
        "components_used": comps,
    }
    try:
        LAST_VIDEOS_PATH.parent.mkdir(parents=True, exist_ok=True)
        if LAST_VIDEOS_PATH.exists():
            data = json.loads(LAST_VIDEOS_PATH.read_text(encoding="utf-8"))
        else:
            data = {"history": []}
        if not isinstance(data, dict):
            data = {"history": []}
        history = data.get("history")
        if not isinstance(history, list):
            history = []
        history = [h for h in history if not (isinstance(h, dict) and h.get("video_id") == video_id)]
        history.append(entry)
        if max_history > 0 and len(history) > max_history:
            history = history[-max_history:]
        data["history"] = history
        LAST_VIDEOS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        print(f"  ⚠️  append_last_video falhou: {exc}")
