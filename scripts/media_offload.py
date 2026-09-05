#!/usr/bin/env python3
"""Offload de mídia Vale: SSD → /mnt/hd_extra depois de R2 / YouTube.

SSD fica para encode, TTS e cache. Artefatos já publicados vão para o HD.

Regras:
  - Host (audio/, output/videos/, output/brasil_e_mundo/audio/): copia +
    substitui por symlink (pipeline/ffmpeg continuam achando o path).
  - public/audio/: NÃO vira symlink (nginx no Docker só monta public/).
    Apaga só se o catálogo já aponta para audio.mob.tec.br.
  - Se o HD não estiver montado/gravável: no-op com aviso.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

DEFAULT_ARCHIVE = Path("/mnt/hd_extra/vale-media")


def archive_root() -> Path:
    return Path(os.environ.get("VALE_MEDIA_ARCHIVE") or DEFAULT_ARCHIVE)


def archive_ready(root: Path | None = None) -> bool:
    root = root or archive_root()
    parent = root.parent
    try:
        if not parent.exists():
            return False
        if not os.access(parent, os.W_OK):
            return False
        root.mkdir(parents=True, exist_ok=True)
        return True
    except OSError:
        return False


def _same_file(a: Path, b: Path) -> bool:
    try:
        return a.exists() and b.exists() and a.stat().st_ino == b.stat().st_ino and a.stat().st_dev == b.stat().st_dev
    except OSError:
        return False


def copy_verified(src: Path, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size == src.stat().st_size:
        return True
    tmp = dest.with_suffix(dest.suffix + ".partial")
    try:
        shutil.copy2(src, tmp)
        if tmp.stat().st_size != src.stat().st_size:
            tmp.unlink(missing_ok=True)
            return False
        tmp.replace(dest)
        return dest.stat().st_size == src.stat().st_size
    except OSError:
        tmp.unlink(missing_ok=True)
        return False


def replace_with_symlink(src: Path, dest: Path) -> None:
    """src vira symlink relativo-absoluto para dest (já copiado)."""
    if src.is_symlink():
        src.unlink()
    elif src.exists():
        src.unlink()
    src.symlink_to(dest)


def offload_host_file(src: Path, dest: Path) -> str:
    """Copia para o HD e deixa symlink no path original. Idempotente."""
    if not src.exists():
        return "missing"
    if src.is_symlink():
        target = src.resolve()
        if target == dest.resolve() and dest.exists():
            return "already"
        if not dest.exists() and target.exists() and target != src:
            if not copy_verified(target, dest):
                return "copy-fail"
            src.unlink()
            src.symlink_to(dest)
            return "ok"
        return "already"
    if _same_file(src, dest):
        return "already"
    if not copy_verified(src, dest):
        return "copy-fail"
    replace_with_symlink(src, dest)
    return "ok"


def catalog_uses_r2(episode_id: str) -> bool:
    sidecar = PROJECT_ROOT / "episodes" / f"{episode_id}-r2.json"
    if sidecar.exists():
        try:
            meta = json.loads(sidecar.read_text(encoding="utf-8"))
            if meta.get("r2_uploaded"):
                url = (meta.get("catalog_url") or meta.get("r2_url") or "")
                if "audio.mob.tec.br" in url:
                    return True
        except (OSError, json.JSONDecodeError):
            pass
    catalog = PROJECT_ROOT / "public" / "data" / "episodes.json"
    if not catalog.exists():
        return False
    try:
        data = json.loads(catalog.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    eps = data.get("episodes") or data.get("items") or (data if isinstance(data, list) else [])
    for e in eps:
        eid = str(e.get("id") or e.get("date") or e.get("slug") or "")
        if eid != episode_id and not eid.endswith(episode_id):
            continue
        url = e.get("audio_url") or e.get("audio") or ""
        return "audio.mob.tec.br" in url
    return False


def after_r2(episode_id: str, root: Path | None = None) -> dict:
    """Offload dos MP3 de um episódio já no R2."""
    root = root or archive_root()
    result = {"id": episode_id, "ok": [], "skip": [], "error": []}
    if not archive_ready(root):
        result["error"].append("archive-unavailable")
        print(f"  ⚠️  offload R2: HD extra indisponível ({root})")
        return result

    audio_dest_dir = root / "audio"
    host_candidates: list[Path] = [
        PROJECT_ROOT / "audio" / f"{episode_id}.mp3",
        PROJECT_ROOT / "audio" / f"{episode_id}-vale-da-liberdade.mp3",
        PROJECT_ROOT / "audio" / f"{episode_id}-completo.mp3",
    ]
    if episode_id.startswith("especial-"):
        vid = episode_id.removeprefix("especial-")
        bm_audio = PROJECT_ROOT / "output" / "brasil_e_mundo" / "audio"
        host_candidates.extend(sorted(bm_audio.glob(f"{vid}_*.mp3")))

    for src in host_candidates:
        if not src.exists() and not src.is_symlink():
            continue
        dest = audio_dest_dir / src.name
        status = offload_host_file(src, dest)
        result["ok" if status in ("ok", "already") else "error"].append(f"{src.name}:{status}")
        print(f"  📦 offload audio {src.name} → {dest} ({status})")

    public_mp3 = PROJECT_ROOT / "public" / "audio" / f"{episode_id}.mp3"
    if public_mp3.exists() or public_mp3.is_symlink():
        if catalog_uses_r2(episode_id):
            if public_mp3.is_symlink():
                public_mp3.unlink()
                result["ok"].append(f"public:{episode_id}.mp3:unlinked-symlink")
            else:
                dest = audio_dest_dir / public_mp3.name
                if copy_verified(public_mp3, dest):
                    public_mp3.unlink()
                    result["ok"].append(f"public:{episode_id}.mp3:archived")
                    print(f"  📦 public/audio/{episode_id}.mp3 arquivado (catálogo R2)")
                else:
                    result["error"].append(f"public:{episode_id}.mp3:copy-fail")
        else:
            result["skip"].append(f"public:{episode_id}.mp3:local-catalog")
            print(f"  ⏭️  public/audio/{episode_id}.mp3 permanece (catálogo ainda local)")
    return result


def after_youtube(video_id: str, root: Path | None = None) -> dict:
    """Offload do mp4 publicado e da pasta de trabalho do mockup."""
    root = root or archive_root()
    result = {"id": video_id, "ok": [], "skip": [], "error": []}
    if not archive_ready(root):
        result["error"].append("archive-unavailable")
        print(f"  ⚠️  offload YT: HD extra indisponível ({root})")
        return result

    videos_dir = PROJECT_ROOT / "output" / "videos"
    dest_dir = root / "videos"
    for src in sorted(videos_dir.glob(f"especial-{video_id}*.mp4")):
        dest = dest_dir / src.name
        status = offload_host_file(src, dest)
        bucket = "ok" if status in ("ok", "already") else "error"
        result[bucket].append(f"{src.name}:{status}")
        print(f"  📦 offload vídeo {src.name} → {dest} ({status})")

    work = PROJECT_ROOT / "output" / "brasil_e_mundo" / "mockup_video" / video_id
    if work.exists() and work.is_dir() and not work.is_symlink():
        dest_work = root / "mockup" / video_id
        try:
            if dest_work.exists():
                shutil.rmtree(dest_work)
            shutil.copytree(work, dest_work, symlinks=True)
            shutil.rmtree(work)
            result["ok"].append(f"mockup:{video_id}:moved")
            print(f"  📦 offload mockup {video_id}/ → {dest_work}")
        except OSError as exc:
            result["error"].append(f"mockup:{exc}")
            print(f"  ⚠️  offload mockup falhou: {exc}")
    return result


def backfill(*, dry_run: bool = False) -> dict:
    """Arquiva mp4 já no YouTube e mp3 já no R2."""
    summary = {"videos": 0, "audio": 0, "errors": 0}
    if not archive_ready():
        print(f"❌ HD extra indisponível: {archive_root()}")
        summary["errors"] += 1
        return summary

    state_path = PROJECT_ROOT / "output" / "brasil_e_mundo" / "videos_published.json"
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        videos = state.get("videos") or {}
        for vid, meta in videos.items():
            if not (meta or {}).get("yt_id"):
                continue
            if dry_run:
                print(f"  [dry-run] youtube {vid}")
                summary["videos"] += 1
                continue
            r = after_youtube(vid)
            if r["ok"]:
                summary["videos"] += 1
            if r["error"]:
                summary["errors"] += 1

    epi_dir = PROJECT_ROOT / "episodes"
    if epi_dir.exists():
        for sidecar in sorted(epi_dir.glob("*-r2.json")):
            try:
                meta = json.loads(sidecar.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not meta.get("r2_uploaded"):
                continue
            eid = meta.get("date") or sidecar.name.removesuffix("-r2.json")
            if dry_run:
                print(f"  [dry-run] r2 {eid}")
                summary["audio"] += 1
                continue
            r = after_r2(eid)
            if r["ok"]:
                summary["audio"] += 1
            if r["error"]:
                summary["errors"] += 1
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description="Offload de mídia Vale para /mnt/hd_extra")
    ap.add_argument("--after-r2", metavar="ID", help="Offload de um episódio já no R2")
    ap.add_argument("--after-youtube", metavar="VIDEO_ID", help="Offload de um mp4 já no YouTube")
    ap.add_argument("--backfill", action="store_true", help="Arquiva o que já foi publicado")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if args.after_r2:
        after_r2(args.after_r2)
        return 0
    if args.after_youtube:
        after_youtube(args.after_youtube)
        return 0
    if args.backfill:
        s = backfill(dry_run=args.dry_run)
        print(f"✅ backfill vídeos={s['videos']} áudios={s['audio']} erros={s['errors']}")
        return 0 if s["errors"] == 0 else 1
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
