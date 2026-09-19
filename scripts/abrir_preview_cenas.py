#!/usr/bin/env python3
"""Preview interativo de cenas do Broadcast — navega beats no browser.

Carrega um episódio real (JSON + screenshots) e abre uma UI no navegador
que permite navegar cena por cena, vendo exatamente o que o vídeo exibiria.
"""
from __future__ import annotations

import json
import os
import re
import sys
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
MOCKUP_DIR = ROOT / "references" / "youtube" / "mockup-browser"
EPS_DIR = ROOT / "output" / "brasil_e_mundo" / "episodes"
WORK_ROOT = ROOT / "output" / "brasil_e_mundo" / "mockup_video"
AUDIO_DIR = ROOT / "output" / "brasil_e_mundo" / "audio"
BROLL_DIR = ROOT / "references" / "youtube" / "broll"

# Ensure scripts dir is on path for imports
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _list_recent_episodes(limit: int = 15) -> list[dict]:
    """Lista os episódios mais recentes com metadados básicos."""
    episodes = []
    for f in sorted(EPS_DIR.glob("especial-*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        if f.name.endswith(".image-manifest.json"):
            continue
        vid = f.stem.removeprefix("especial-")
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        title = data.get("titulo", "Sem título")
        work = WORK_ROOT / vid
        has_shots = (work / "shots").is_dir() and any((work / "shots").glob("src-*.png"))
        episodes.append({
            "video_id": vid,
            "title": title,
            "has_shots": has_shots,
            "path": str(f),
            "mtime": f.stat().st_mtime,
        })
        if len(episodes) >= limit:
            break
    return episodes


def _select_episode(video_id: str | None) -> str:
    """Seleciona episódio interativamente ou usa o fornecido."""
    if video_id:
        ep_path = EPS_DIR / f"especial-{video_id}.json"
        if ep_path.exists():
            return video_id
        print(f"❌ Episódio '{video_id}' não encontrado em {EPS_DIR}")
        sys.exit(1)

    episodes = _list_recent_episodes()
    if not episodes:
        print("❌ Nenhum episódio encontrado.")
        sys.exit(1)

    print("\n" + "=" * 64)
    print("📋 EPISÓDIOS RECENTES")
    print("=" * 64)
    for i, ep in enumerate(episodes):
        shots_tag = "📸" if ep["has_shots"] else "  "
        print(f"  {i + 1:2d}. {shots_tag} [{ep['video_id'][:11]}] {ep['title'][:50]}")
    print("=" * 64)
    print("  📸 = tem screenshots capturados")
    print()

    while True:
        try:
            choice = input("Escolha o número do episódio (ou 'q' para sair): ").strip()
        except (EOFError, KeyboardInterrupt):
            sys.exit(0)
        if choice.lower() == "q":
            sys.exit(0)
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(episodes):
                return episodes[idx]["video_id"]
        except ValueError:
            pass
        print("  ⚠️  Opção inválida.")


def _build_preview_data(video_id: str) -> dict:
    """Constrói o payload JSON completo para o preview de cenas."""
    ep_path = EPS_DIR / f"especial-{video_id}.json"
    episode = json.loads(ep_path.read_text(encoding="utf-8"))
    episode["video_id"] = video_id
    work = WORK_ROOT / video_id
    shot_dir = work / "shots"

    title = episode.get("titulo", "Sem título")
    veiculo = episode.get("fonte_veiculo", "")

    # Tentar resolver a data do áudio
    ymd = ""
    audio_files = sorted(AUDIO_DIR.glob(f"{video_id}_*.mp3"), reverse=True)
    if audio_files:
        m = re.search(r"(\d{4}-\d{2}-\d{2})", audio_files[0].name)
        ymd = m.group(1) if m else ""

    # Tentar carregar timeline beats existente
    try:
        from bm_scene_timeline import build_scene_timeline
        from bm_video.state import (
            _normalize_beat_v2,
            _build_mockup_update_payload,
            source_scenes,
            one_line_subhead,
            ticker_headlines,
            _omnibox_url,
        )
    except ImportError as exc:
        print(f"⚠️  Falha ao importar módulos: {exc}")
        sys.exit(1)

    scenes = source_scenes(episode)
    # Carregar metadados de shots salvos se existirem
    shots_meta = {}
    meta_path = shot_dir / "_shots_meta.json"
    if meta_path.exists():
        try:
            shots_meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Attach shots, shot_long e highlight_box se existirem
    for i, scene in enumerate(scenes):
        shot_file = shot_dir / f"src-{i:02d}.png"
        if shot_file.exists():
            scene["shot"] = shot_file.name
        shot_long_file = shot_dir / f"src-{i:02d}-long.png"
        if shot_long_file.exists():
            scene["shot_long"] = shot_long_file.name
        else:
            detail_file = shot_dir / f"src-{i:02d}-detail.png"
            if detail_file.exists() and shot_file.exists():
                from bm_video.capture import stitch_screenshots
                stitched = stitch_screenshots(shot_file, detail_file, shot_long_file)
                if stitched:
                    scene["shot_long"] = shot_long_file.name

        meta_info = shots_meta.get(str(i)) or shots_meta.get(scene.get("url", "")) or {}
        if meta_info.get("highlight_box"):
            scene["highlight_box"] = meta_info["highlight_box"]
        elif not scene.get("highlight_box"):
            # Padrão contextual: área do lead/subtítulo da matéria jornalística
            scene["highlight_box"] = {"found": True, "x": 65, "y": 320, "w": 1050, "h": 72}

    # Calcular duration estimate (2.5 palavras/segundo)
    total_words = 0
    for key in ("abertura", "desenvolvimento", "fechamento"):
        for item in episode.get(key) or []:
            text = item.get("texto") if isinstance(item, dict) else item
            total_words += len((text or "").split())
    dur = max(30.0, total_words / 2.5)

    # Build timeline
    broll_index = BROLL_DIR / "_index.json"
    timeline_beats = build_scene_timeline(episode, dur, scenes, broll_index)
    try:
        from bm_video.capture import stage_person_photo_assets
        stage_person_photo_assets(timeline_beats, work)
    except Exception:
        pass

    subhead = one_line_subhead(episode)
    ticker_items = ticker_headlines(episode, video_id)

    # Build payloads for each beat
    beats_data = []
    for idx, beat in enumerate(timeline_beats):
        b = _normalize_beat_v2(beat)
        payload = _build_mockup_update_payload(b)
        beats_data.append({
            "index": idx,
            "t0": round(float(b.get("t0", 0)), 2),
            "t1": round(float(b.get("t1", 0)), 2),
            "duration": round(float(b.get("t1", 0)) - float(b.get("t0", 0)), 2),
            "kind": b.get("visual_component") or b.get("kind") or "source",
            "veiculo": b.get("veiculo", ""),
            "url": b.get("url", ""),
            "semantic_role": b.get("semantic_role", ""),
            "visual_variant": b.get("visual_variant", ""),
            "has_shot": bool(b.get("shot")),
            "has_video": bool(b.get("video")),
            "payload": payload,
        })

    # Wallpaper
    from bm_video.state import pick_wallpaper
    wallpaper = pick_wallpaper(video_id)

    # Init payload (same as record_mockup)
    first_beat = timeline_beats[0] if timeline_beats else None
    fb_v2 = _normalize_beat_v2(first_beat) if first_beat else {}
    first_shot = fb_v2.get("shot") or (scenes[0].get("shot") if scenes else None)
    first_shot_long = fb_v2.get("shot_long") or (scenes[0].get("shot_long") if scenes else None)
    first_hl = fb_v2.get("highlight_box") or (scenes[0].get("highlight_box") if scenes else {})
    first_url = _omnibox_url(fb_v2.get("url") or (scenes[0].get("url") if scenes else ""))
    first_kind = fb_v2.get("visual_component") or fb_v2.get("kind") or "source"

    init_payload = {
        "categoria": "BRASIL E MUNDO",
        "titulo": title,
        "resumo": subhead,
        "autor": "Peter Albuquerque",
        "data": ymd,
        "dataExtenso": ymd,
        "url": first_url,
        "eyebrow": f"VALE DA LIBERDADE • {veiculo.upper()}" if veiculo else "VALE DA LIBERDADE",
        "lowerTitle": title,
        "lowerSubtitle": subhead,
        "liveText": "B&M",
        "brandSub": "B&M",
        "tag": "VALE DA LIBERDADE",
        "ticker": ticker_items,
        "pageImage": f"/shots/{first_shot}" if first_shot else "",
        "shotLong": f"/shots/{first_shot_long}" if first_shot_long else (f"/shots/{first_shot}" if first_shot else ""),
        "highlightBox": first_hl or {},
        "kind": first_kind,
        "visual_component": first_kind,
        "visual_variant": fb_v2.get("visual_variant") or "",
        "visual_payload": fb_v2.get("visual_payload") or {},
    }
    if wallpaper:
        init_payload["wallpaper"] = f"/wallpaper/{quote(wallpaper.name)}"

    x_post = fb_v2.get("x_post")
    if x_post:
        init_payload["xPost"] = x_post

    return {
        "video_id": video_id,
        "title": title,
        "date": ymd,
        "total_beats": len(beats_data),
        "estimated_duration": round(dur, 1),
        "init_payload": init_payload,
        "beats": beats_data,
    }


class _PreviewHandler(SimpleHTTPRequestHandler):
    """Handler that serves from mockup-browser dir, work dir, and preview data."""
    preview_data: dict = {}
    work_dir: Path = Path(".")

    def translate_path(self, path: str) -> str:
        rel = path.split("?", 1)[0].lstrip("/")

        # Serve preview data as JSON
        if rel == "_preview_data.json":
            return "__JSON_ENDPOINT__"

        # Try work dir first (shots/)
        cand = (self.work_dir / rel).resolve()
        if cand.is_file():
            return str(cand)

        # Try broll dir
        if rel.startswith("broll/"):
            broll_cand = (BROLL_DIR.parent / rel.removeprefix("broll/")).resolve()
            if broll_cand.is_file():
                return str(broll_cand)
            broll_cand2 = (BROLL_DIR / rel.removeprefix("broll/")).resolve()
            if broll_cand2.is_file():
                return str(broll_cand2)

        # Then mockup-browser dir
        cand = (MOCKUP_DIR / rel).resolve()
        if cand.is_file():
            return str(cand)
        if cand.is_dir():
            for idx in ("preview-cenas.html", "index.html"):
                target = cand / idx
                if target.exists():
                    return str(target)

        return str((MOCKUP_DIR / rel).resolve())

    def do_GET(self):
        rel = self.path.split("?", 1)[0].lstrip("/")
        if rel == "_preview_data.json":
            data = json.dumps(self.preview_data, ensure_ascii=False)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data.encode("utf-8"))))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data.encode("utf-8"))
            return
        super().do_GET()

    def log_message(self, format, *args):
        return  # Silencia logs


def main():
    video_id = sys.argv[1] if len(sys.argv) > 1 else None
    video_id = _select_episode(video_id)

    print(f"\n🔍 Carregando episódio: {video_id}...")
    try:
        preview_data = _build_preview_data(video_id)
    except Exception as exc:
        print(f"❌ Erro ao construir dados do preview: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    work_dir = WORK_ROOT / video_id
    _PreviewHandler.preview_data = preview_data
    _PreviewHandler.work_dir = work_dir

    port = 8780
    httpd = None
    for p in range(port, port + 20):
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", p), _PreviewHandler)
            port = p
            break
        except OSError:
            continue

    if not httpd:
        print("❌ Não foi possível encontrar uma porta livre.")
        sys.exit(1)

    url = f"http://127.0.0.1:{port}/preview-cenas.html"
    print("\n" + "=" * 64)
    print("🎬 VALE DA LIBERDADE • PREVIEW DE CENAS")
    print("=" * 64)
    print(f"📺 Episódio: {preview_data['title']}")
    print(f"🎞️  Cenas: {preview_data['total_beats']} beats")
    print(f"⏱️  Duração estimada: {preview_data['estimated_duration']:.0f}s")
    print(f"🔗 Servidor ativo em: {url}")
    print("🚀 Abrindo no navegador...")
    print("⌨️  Pressione Ctrl+C para encerrar.\n")

    webbrowser.open(url)

    httpd.daemon_threads = True
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Preview encerrado.")
    finally:
        try:
            httpd.shutdown()
            httpd.server_close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
