"""Upload YouTube v3 e registro em videos_published.json."""
from __future__ import annotations

import json
from pathlib import Path

from bm_video.constants import *  # noqa: F403
from bm_video.state import load_state

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
