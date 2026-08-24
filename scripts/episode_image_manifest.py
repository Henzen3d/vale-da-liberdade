#!/usr/bin/env python3
"""Vínculo auditável entre episódio, imagem editorial e thumbnail do YouTube.

A imagem editorial NÃO é descoberta por glob/mtime/latest. O único caminho
válido é o gravado neste manifesto. Placeholder e hash divergente falham.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EPS_DIR = PROJECT_ROOT / "output" / "brasil_e_mundo" / "episodes"
THUMBS_DIR = PROJECT_ROOT / "thumbnails"

CF_MODEL_ID = "@cf/black-forest-labs/flux-1-schnell"
MIN_EDITORIAL_BYTES = 2000


class EditorialImageError(RuntimeError):
    """Imagem editorial ausente, placeholder, de outro episódio ou hash errado."""


class YoutubeThumbnailError(RuntimeError):
    """Thumbnail do YouTube ausente ou não amarrada à editorial do episódio."""


def sha256_file(path: Path | str) -> str:
    p = Path(path)
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def episode_id_for(video_id: str) -> str:
    return f"especial-{video_id}"


def manifest_path(video_id: str) -> Path:
    return EPS_DIR / f"especial-{video_id}.image-manifest.json"


def sidecar_manifest_path(date: str, video_id: str) -> Path:
    return THUMBS_DIR / date / f"bm_{video_id}.manifest.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _lock_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    data = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    with tmp.open("w", encoding="utf-8") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    tmp.replace(path)


def load_manifest(video_id: str) -> dict[str, Any]:
    p = manifest_path(video_id)
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def save_manifest(video_id: str, data: dict[str, Any]) -> Path:
    data = dict(data)
    data["episode_id"] = episode_id_for(video_id)
    data["video_id"] = video_id
    data["updated_at"] = now_iso()
    dest = manifest_path(video_id)
    _lock_write(dest, data)
    date = data.get("date") or ""
    if date:
        try:
            _lock_write(sidecar_manifest_path(str(date), video_id), data)
        except OSError:
            pass
    return dest


def _as_abs(path: Path | str) -> Path:
    p = Path(path)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    return p


def _belongs_to_episode(path: Path, video_id: str) -> bool:
    name = path.name
    return f"bm_{video_id}." in name or name.startswith(f"bm_{video_id}.")


def record_editorial(
    video_id: str,
    date: str,
    editorial_image_path: Path | str,
    model: str,
    is_placeholder: bool,
    generated_at: str | None = None,
) -> dict[str, Any]:
    path = _as_abs(editorial_image_path)
    data = load_manifest(video_id)
    data.update({
        "episode_id": episode_id_for(video_id),
        "video_id": video_id,
        "date": date,
        "editorial_image_path": str(path),
        "editorial_image_hash": sha256_file(path) if path.is_file() and path.stat().st_size else "",
        "editorial_image_generated_at": generated_at or now_iso(),
        "editorial_image_model": model,
        "editorial_is_placeholder": bool(is_placeholder),
        "editorial_image_size": path.stat().st_size if path.is_file() else 0,
    })
    save_manifest(video_id, data)
    return data


def record_youtube_thumbnail(
    video_id: str,
    youtube_thumbnail_path: Path | str,
    editorial_used: Path | str,
    generated_at: str | None = None,
    extra: dict | None = None,
) -> dict[str, Any]:
    out = _as_abs(youtube_thumbnail_path)
    used = _as_abs(editorial_used)
    data = load_manifest(video_id)
    data.update({
        "youtube_thumbnail_path": str(out),
        "youtube_thumbnail_input_hash": sha256_file(used),
        "youtube_thumbnail_output_hash": sha256_file(out) if out.is_file() else "",
        "youtube_thumbnail_generated_at": generated_at or now_iso(),
    })
    if extra:
        data.update(extra)
    save_manifest(video_id, data)
    return data


def validate_image_file(path: Path, *, min_bytes: int = MIN_EDITORIAL_BYTES) -> None:
    if not path.is_file():
        raise EditorialImageError(f"arquivo inexistente: {path}")
    size = path.stat().st_size
    if size < min_bytes:
        raise EditorialImageError(f"arquivo vazio/curto ({size} B): {path}")
    try:
        from PIL import Image
        with Image.open(path) as im:
            im.verify()
    except Exception as exc:  # noqa: BLE001
        raise EditorialImageError(f"imagem corrompida: {path} ({exc})") from exc


def resolve_editorial_image(video_id: str, *, allow_placeholder: bool = False) -> Path:
    """Única resolução permitida da imagem editorial do episódio."""
    data = load_manifest(video_id)
    if not data:
        raise EditorialImageError(
            f"manifesto ausente para {video_id} ({manifest_path(video_id)})"
        )
    raw = data.get("editorial_image_path") or ""
    if not raw:
        raise EditorialImageError(f"manifesto sem editorial_image_path: {video_id}")
    path = _as_abs(raw)
    if data.get("editorial_is_placeholder") and not allow_placeholder:
        raise EditorialImageError(
            f"placeholder recusado como editorial de {video_id}: {path}"
        )
    if not _belongs_to_episode(path, video_id):
        raise EditorialImageError(
            f"arquivo {path.name} não pertence ao episódio {video_id}"
        )
    validate_image_file(path)
    expected = data.get("editorial_image_hash") or ""
    actual = sha256_file(path)
    if expected and actual != expected:
        raise EditorialImageError(
            f"hash editorial divergente para {video_id}: manifesto={expected} arquivo={actual}"
        )
    return path


def resolve_youtube_thumbnail(video_id: str) -> Path:
    data = load_manifest(video_id)
    if not data:
        raise YoutubeThumbnailError(f"manifesto ausente para {video_id}")
    raw = data.get("youtube_thumbnail_path") or ""
    if not raw:
        raise YoutubeThumbnailError(
            f"thumbnail YouTube ainda não gerada para {video_id} (sem fallback para bm_*)"
        )
    path = _as_abs(raw)
    if not path.is_file():
        raise YoutubeThumbnailError(f"thumbnail YouTube inexistente: {path}")
    editorial = resolve_editorial_image(video_id)
    input_hash = data.get("youtube_thumbnail_input_hash") or ""
    editorial_hash = sha256_file(editorial)
    if input_hash and input_hash != editorial_hash:
        raise YoutubeThumbnailError(
            f"thumbnail YouTube de {video_id} foi gerada com editorial {input_hash}, "
            f"mas a editorial atual é {editorial_hash}"
        )
    return path


def describe_editorial(video_id: str, path: Path) -> dict[str, Any]:
    return {
        "episode_id": episode_id_for(video_id),
        "editorial_image": str(path),
        "editorial_image_exists": path.is_file(),
        "editorial_image_size": path.stat().st_size if path.is_file() else 0,
        "editorial_image_hash": sha256_file(path) if path.is_file() else "",
    }
