"""Orquestração e CLI canônico do mockup BM."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

from bm_video.capture import capture_sources, record_mockup
from bm_video.constants import *  # noqa: F403
from bm_video.render import (
    append_outro_video,
    compose_presenter,
    find_portal_transition_times,
    mix_portal_transition_sfx,
    mp4_is_playable,
    mux_video,
    prepare_audio_with_intro,
    probe_duration_s,
    resolve_outro_take,
    resolve_outro_video,
)
from bm_video.state import (
    append_last_video,
    build_metadata,
    episode_date,
    find_episode_thumbnail,
    load_episode,
    load_state,
    pick_wallpaper,
    resolve_audio,
    save_state,
    source_scenes,
)
from bm_video.youtube import (
    _previous_published,
    post_channel_cross_comment,
    publish_youtube,
    set_youtube_thumbnail,
    sync_dynamic_playlist_action,
)


def _scene_host(url: str) -> str:
    from urllib.parse import urlsplit
    try:
        host = (urlsplit(url or "").hostname or "").lower()
    except Exception:
        return ""
    return host[4:] if host.startswith("www.") else host


def _is_x_scene(url: str) -> bool:
    return _scene_host(url) in {"x.com", "twitter.com", "mobile.x.com", "mobile.twitter.com"}


def _is_youtube_scene(url: str) -> bool:
    host = _scene_host(url)
    return host in {"youtube.com", "youtu.be", "m.youtube.com", "music.youtube.com"} or host.endswith(".youtube.com")


def _scene_has_pixels(scene: dict) -> bool:
    return bool(scene.get("shot") or scene.get("video") or scene.get("x_post"))


def select_usable_scenes(
    captured: list[dict],
    episode: dict,
    shot_dir: Path | None = None,
    rescue=None,
) -> list[dict]:
    """Mantém a matéria primária não-X mesmo se o screenshot falhar.

    Tenta o resgate og:image já existente. Post do X continua na lista só
    para a fala que o citar. Nunca substitui a matéria morta pelo X vizinho.
    """
    explicit: set[str] = set()
    for section in ("abertura", "desenvolvimento", "fechamento"):
        for item in episode.get(section) or []:
            url = (item.get("fonte_url") or "").strip()
            if url and not _is_youtube_scene(url):
                explicit.add(url)

    primary = None
    for scene in captured:
        url = scene.get("url") or ""
        if url and not _is_x_scene(url) and not _is_youtube_scene(url):
            primary = scene
            break

    protected: list[dict] = []
    if primary is not None:
        protected.append(primary)
    for scene in captured:
        if scene is primary:
            continue
        url = scene.get("url") or ""
        if url in explicit and not _is_x_scene(url):
            protected.append(scene)

    if shot_dir is not None:
        shot_dir.mkdir(parents=True, exist_ok=True)
        if rescue is None:
            from person_resolver import download_article_image
            rescue = download_article_image
        for index, scene in enumerate(protected):
            if _scene_has_pixels(scene):
                continue
            url = scene.get("url") or ""
            if not url.startswith("http"):
                continue
            dest = shot_dir / f"rescued-primary-{index:02d}.jpg"
            try:
                ok = bool(rescue(url, dest))
            except Exception:
                ok = False
            if ok and dest.is_file() and dest.stat().st_size >= 8192:
                scene["shot"] = dest.name

    usable: list[dict] = []
    seen: set[int] = set()
    for scene in captured:
        keep = scene in protected or _scene_has_pixels(scene)
        if _is_x_scene(scene.get("url") or "") and not scene.get("x_post") and not scene.get("shot") and not scene.get("video"):
            keep = False
        if keep and id(scene) not in seen:
            usable.append(scene)
            seen.add(id(scene))
    if not usable:
        usable = [{
            "veiculo": episode.get("fonte_veiculo") or "Vale da Liberdade",
            "url": APP_URL,
            "titulo": episode.get("titulo") or "",
            "shot": None,
            "video": None,
        }]
    return usable


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

    work = WORK_ROOT / video_id
    work.mkdir(parents=True, exist_ok=True)
    audio = prepare_audio_with_intro(audio, work)

    dur = probe_duration_s(audio)
    if dur > MAX_DURATION_S:
        raise RuntimeError(f"{video_id}: áudio {dur:.0f}s > {MAX_DURATION_S:.0f}s — pulado")
    if dur > SOFT_DURATION_S:
        print(f"  ⚠️  {video_id}: áudio {dur:.0f}s > {SOFT_DURATION_S:.0f}s (alvo 5m30s); gerando mesmo assim")

    scenes = source_scenes(episode, max_sources=MAX_SCENES)
    wallpaper = pick_wallpaper(video_id)

    from bm_scene_timeline import build_scene_timeline
    if video_id:
        episode.setdefault("video_id", video_id)
    timeline_beats = build_scene_timeline(episode, dur, scenes, BROLL_INDEX)

    title, desc, tags = build_metadata(video_id, episode, audio, scenes=scenes, timeline_beats=timeline_beats)
    print(f"🎬 {video_id} · {dur:.0f}s · {title}")
    print(f"   fontes: {len(scenes)} (beats: {len(timeline_beats)}) · upload={upload} privacy={privacy}")
    if wallpaper:
        print(f"   wallpaper: {wallpaper.name}")
    take = resolve_outro_take(video_id)
    if take and wallpaper:
        print(f"   outro:     {take.name} (contextual wallpaper: {wallpaper.name})")
    elif resolve_outro_video(video_id):
        print(f"   outro:     {resolve_outro_video(video_id).name}")
    if dry_run:
        return {
            "video_id": video_id,
            "title": title,
            "scenes": scenes,
            "beats": [b.to_dict() for b in timeline_beats],
            "wallpaper": wallpaper.name if wallpaper else None,
            "outro": f"{take.name} (wallpaper: {wallpaper.name})" if (take and wallpaper) else (resolve_outro_video(video_id).name if resolve_outro_video(video_id) else None),
            "thumb": str(find_episode_thumbnail(video_id, episode_date(audio)) or ""),
            "desc": desc,
            "dry_run": True,
        }

    shots = work / "shots"
    if work.exists():
        # recicla só o rec; screenshots podem ser reaproveitadas
        rec = work / "rec"
        if rec.exists():
            for p in rec.glob("*"):
                p.unlink()
    shots.mkdir(parents=True, exist_ok=True)
    captured = capture_sources(scenes, shots) if scenes else []

    # Matéria primária não-X não sai da lista só porque o screenshot falhou.
    # O resgate og:image roda aqui. X vizinho não ocupa o lugar.
    usable = select_usable_scenes(captured, episode, shots)
    dropped = [c for c in captured if c not in usable]
    if dropped:
        for c in dropped:
            print(f"  🚫 cena descartada (captura falhou): {c.get('veiculo')} · {c.get('url')}")

    # Recalcula timeline só com as cenas que têm imagem/vídeo de verdade
    if video_id:
        episode.setdefault("video_id", video_id)
    timeline_beats = build_scene_timeline(episode, dur, usable, BROLL_INDEX)

    # FASE 4 (opcional) — sincronia fina por word-timestamps do Whisper.
    # Só ativa via BM_WHISPER_ALIGN=1; precisa do mp3 final do episódio.
    if os.environ.get("BM_WHISPER_ALIGN") == "1":
        from bm_whisper_align import align_beats_to_audio

        block_texts = [
            (b.get("texto") or b.get("text") or "")
            for b in (
                (episode.get("abertura") or [])
                + (episode.get("desenvolvimento") or [])
                + (episode.get("fechamento") or [])
            )
        ]
        timeline_beats = align_beats_to_audio(
            timeline_beats, Path(audio), block_texts, cache_dir=work
        )
    trans_times = find_portal_transition_times(timeline_beats)
    if trans_times:
        audio = mix_portal_transition_sfx(audio, trans_times, work)
    raw = record_mockup(video_id, episode, audio, usable, work, wallpaper=wallpaper, timeline_beats=timeline_beats)
    mp4 = VIDEOS_OUT / f"especial-{video_id}-mockup.mp4"
    mux_video(raw, audio, mp4)
    print(f"  ✅ mp4 {mp4} ({mp4.stat().st_size // 1024} KB)")
    mp4 = compose_presenter(mp4, episode, audio, work)
    if not mp4_is_playable(mp4):
        raise RuntimeError(f"{video_id}: MP4 ilegível após overlay — recusando upload")
    outro_video = resolve_outro_video(video_id, wallpaper=wallpaper, work=work)
    if not outro_video:
        raise RuntimeError(f"{video_id}: encerramento obrigatório — nenhum clip de outro resolvido")
    mp4 = append_outro_video(mp4, outro_video, work)

    try:
        from bm_video.video_judge import audit_rendered_video
        qa_rep = audit_rendered_video(mp4, work, timeline_beats=timeline_beats, expected_duration_s=dur)
        status_sym = "✅" if qa_rep.get("overall_status") == "APPROVED" else ("⚠️" if qa_rep.get("overall_status") == "WARNING" else "❌")
        print(f"  {status_sym} Video QA: {qa_rep.get('overall_status')} ({qa_rep.get('sampled_frames_count', 0)} frames auditados)")
    except Exception as exc:  # noqa: BLE001
        print(f"  ⚠️  Video QA falhou: {exc}")



    try:
        append_last_video(video_id, episode_date(audio), timeline_beats, wallpaper=wallpaper.name if wallpaper else None)
    except Exception as exc:  # noqa: BLE001
        print(f"  ⚠️  last_videos append falhou: {exc}")

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
        try:
            append_last_video(video_id, episode_date(audio), timeline_beats)
        except Exception as exc:  # noqa: BLE001
            print(f"  ⚠️  last_videos append falhou: {exc}")
        print(f"  ✅ YouTube {result['url']}")
        try:
            from media_offload import after_youtube

            after_youtube(video_id)
        except Exception as exc:  # noqa: BLE001
            print(f"  ⚠️  offload HD após YouTube falhou: {exc}")
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
        dur_s = probe_duration_s(audio)
        if dur_s > MAX_DURATION_S:
            print(f"  ⏭️  {vid}: áudio {dur_s:.0f}s > {MAX_DURATION_S:.0f}s — fora da fila do mockup")
            continue
        if dur_s > SOFT_DURATION_S:
            print(f"  ⚠️  {vid}: áudio {dur_s:.0f}s > {SOFT_DURATION_S:.0f}s (alvo 5m30s); segue mesmo assim")
        pending.append(vid)
    return pending


def _argv_video_id_allows_leading_hyphen(argv: list[str]) -> list[str]:
    """YouTube ids like -Z1IlCPZVoc look like flags to argparse.

    `--video-id -Z1IlCPZVoc` → expected one argument. Rewrite to `--video-id=-Z1IlCPZVoc`.
    """
    out: list[str] = []
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok == "--video-id" and i + 1 < len(argv):
            nxt = argv[i + 1]
            if nxt.startswith("-") and not nxt.startswith("--"):
                out.append(f"--video-id={nxt}")
                i += 2
                continue
        out.append(tok)
        i += 1
    return out


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
    args = ap.parse_args(_argv_video_id_allows_leading_hyphen(sys.argv[1:]))

    ids = [args.video_id] if args.video_id else (pending_ids(args.days, args.backfill) if args.pending else [])
    if not ids:
        print("✅ Nenhum episódio BM pendente para vídeo mockup.")
        return 0
    print(f"📋 {len(ids)} candidato(s): {', '.join(ids[:8])}")
    n_ok = 0
    n_tried = 0
    last_err = None
    for vid in ids:
        n_tried += 1
        try:
            process_one(vid, upload=args.upload, privacy=args.privacy, dry_run=args.dry_run, force=args.force)
            n_ok += 1
        except Exception as exc:
            last_err = exc
            print(f"  ❌ {vid}: {exc}")
        if n_tried >= args.max:
            break
    if n_ok == 0 and last_err:
        return 1
    return 0
