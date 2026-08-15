#!/usr/bin/env python3
"""Autopilot Brasil & Mundo — renderiza e publica vídeos BM curtos (≤5min) automaticamente.

Fluxo por episódio (somente áudios BM ≤ 5min; o áudio longo de Blumenau/Vale da
Liberdade em audio/YYYY-MM-DD*.mp3 fica FORA deste pipeline):
  1. quadros   → bm_quadros_mapper.py --video-id <ID>
  2. assets    → bm_pipeline.py assets --video-id <ID>
  3. review    → bm_pipeline.py review --video-id <ID> (gate técnico)
  4. composicao→ build_episode_composition.py --legenda-mode destaques
  5. check     → npm run check
  6. render    → hyperframes render 1080p
  7. publish   → youtube_uploader.py upload (unlisted)
  8. registro  → output/brasil_e_mundo/videos_published.json

Karaoke palavra-a-palavra foi rejeitado pelo dono (2026-08-15) — não reintroduzir.
"""
from __future__ import annotations

import argparse
import html as _html
import json
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = ROOT / "scripts"
PY = sys.executable
AUDIO_DIR = ROOT / "output" / "brasil_e_mundo" / "audio"
EPS_DIR = ROOT / "output" / "brasil_e_mundo" / "episodes"
ASSETS_DIR = ROOT / "output" / "brasil_e_mundo" / "assets"
VIDEOS_OUT = ROOT / "output" / "videos"
PROTO = ROOT / "references" / "youtube" / "prototype"
BANCADA = PROTO / "bancada-render"
BASE_PROJECT = BANCADA / "project"
STATE_PATH = ROOT / "output" / "brasil_e_mundo" / "videos_published.json"
MAX_DURATION_S = 305.0
WINDOW_DAYS = 2
MAX_PER_RUN = 1
DESC_TEMPLATE = "Comentário de {data} sobre {veiculo}.\n\nFontes:\n{refs}\n\n#BrasilEMundo #{tags}\n"
FIXED_TAGS = ("Brasil e Mundo", "Vale da Liberdade", "notícias", "comentário")


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
        capture_output=True, text=True,
    )
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def run(cmd, tag: str, timeout: int = 900, cwd=None) -> bool:
    print(f"\n▶ {tag}")
    print("  $ " + " ".join(str(c) for c in cmd))
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=str(cwd) if cwd else None)
    except subprocess.TimeoutExpired:
        print(f"  ❌ {tag}: TIMEOUT ({timeout}s)")
        return False
    out = (r.stdout or "").strip()
    err = (r.stderr or "").strip()
    if out:
        print("  " + out[-300:])
    if r.returncode != 0:
        print(f"  ❌ {tag}: exit {r.returncode}")
        if err:
            print("     " + err[-300:])
        return False
    return True


def candidate_audios(days: int, backfill: bool) -> list[Path]:
    """Áudios BM (raiz de output/brasil_e_mundo/audio), ≤5min, excluindo testes/ruído."""
    audios: list[Path] = []
    cutoff = datetime.now() - timedelta(days=days)
    for p in sorted(AUDIO_DIR.glob("*.mp3")):
        name = p.name
        if name.startswith("teste-") or "_ruido" in name:
            continue
        if not re.match(r"^([A-Za-z0-9_-]{6,})_\d{4}-\d{2}-\d{2}\.mp3$", name):
            continue
        if not backfill and datetime.fromtimestamp(p.stat().st_mtime) < cutoff:
            continue
        if probe_duration_s(p) > MAX_DURATION_S:
            continue
        audios.append(p)
    return audios


def episode_title(video_id: str) -> str:
    ep = EPS_DIR / f"especial-{video_id}.json"
    if ep.exists():
        d = json.loads(ep.read_text(encoding="utf-8"))
        t = (d.get("titulo") or "").strip()
        if t:
            return _unescape_html(t)
    return f"Brasil & Mundo — Comentário ({video_id})"


def _clean_url(u: str) -> str:
    """Remove parâmetros de tracking (utm_*) que deixam a URL gigante."""
    u = (u or "").strip()
    if not u:
        return ""
    try:
        parts = urlsplit(u)
        qs = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not k.lower().startswith("utm_")]
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(qs), parts.fragment))
    except Exception:
        return u


def _unescape_html(s: str) -> str:
    """&#039; → ' ; &amp; → & ; &quot; → \" (títulos vindos de RSS/HTML)."""
    return _html.unescape(s or "")


def build_metadata(video_id: str) -> tuple[str, str, list[str]]:
    """Retorna (título, descrição, tags) para o upload YouTube.

    NUNCA citar @ancapsu nem o link do vídeo original como fonte.
    """
    title = episode_title(video_id)
    ep = EPS_DIR / f"especial-{video_id}.json"
    tags = list(FIXED_TAGS)
    veiculo = ""
    refs_ok: list[str] = []
    if ep.exists():
        d = json.loads(ep.read_text(encoding="utf-8"))
        veiculo = d.get("fonte_veiculo") or ""
        tags.extend(d.get("tags") or [])
        for r in d.get("fonte_referencias") or []:
            ru = _clean_url(r.get("url") or "")
            rv = (r.get("veiculo") or "").strip()
            if not ru:
                continue
            low = ru.lower()
            if "youtube.com" in low or "youtu.be" in low or "ancapsu" in low:
                continue
            refs_ok.append(f"{rv}: {ru}" if rv else ru)
    data = "hoje"
    audios = sorted(AUDIO_DIR.glob(f"{video_id}_*.mp3"))
    if audios:
        mm = re.search(r"(\d{4})-(\d{2})-(\d{2})", audios[0].name)
        if mm:
            y, mo, d = mm.group(1), mm.group(2), mm.group(3)
            data = f"{d}/{mo}/{y}"
    desc = DESC_TEMPLATE.format(
        data=data,
        veiculo=veiculo or "a pauta do dia",
        refs="\n".join(refs_ok) if refs_ok else "—",
        tags=" ".join(t.replace(" ", "") for t in tags if t),
    )
    seen: set[str] = set()
    uniq: list[str] = []
    for t in tags:
        t = _unescape_html(str(t)).strip()
        if t and t.lower() not in seen:
            seen.add(t.lower())
            uniq.append(t)
    return title, desc, uniq


def ensure_project_files(project_dir: Path) -> None:
    """Copia package.json/meta.json do projeto base se ausentes (necessário p/ check/render)."""
    project_dir.mkdir(parents=True, exist_ok=True)
    for f in ("package.json", "meta.json"):
        src = BASE_PROJECT / f
        dst = project_dir / f
        if src.exists() and not dst.exists():
            shutil.copy(src, dst)
            print(f"  ℹ️  {f} copiado para {project_dir.name}")


def render_episode(video_id: str, project_dir: Path) -> Path | None:
    """Render 1080p (composição nativa 1920×1080) → output/videos/especial-<ID>-*.mp4"""
    VIDEOS_OUT.mkdir(parents=True, exist_ok=True)
    mp4 = VIDEOS_OUT / f"especial-{video_id}-bm.mp4"
    cmd = [
        "npx", "--yes", "hyperframes@0.7.105", "render",
        "--quality", "high", "--output", str(mp4),
    ]
    ok = run(cmd, "Render HyperFrames (1080p)", timeout=3600, cwd=project_dir)
    if not ok or not mp4.exists():
        print(f"  ❌ MP4 não gerado: {mp4}")
        return None
    return mp4


def extract_thumbnail(mp4: Path, video_id: str) -> Path | None:
    thumb = Path("/tmp") / f"thumb-{video_id}.jpg"
    r = subprocess.run(
        ["ffmpeg", "-y", "-ss", "8", "-i", str(mp4), "-frames:v", "1",
         "-vf", "scale=1280:720", "-q:v", "3", str(thumb)],
        capture_output=True, text=True,
    )
    if r.returncode != 0 or not thumb.exists():
        print("  ❌ thumbnail: ffmpeg falhou")
        return None
    if thumb.stat().st_size > 2 * 1024 * 1024:
        subprocess.run(["ffmpeg", "-y", "-i", str(thumb), "-q:v", "5", str(thumb)], capture_output=True)
    print(f"  🖼️  thumbnail: {thumb.name} ({thumb.stat().st_size // 1024} KB)")
    return thumb


def publish_youtube(mp4: Path, video_id: str) -> str | None:
    """Upload unlisted + thumbnail. Retorna yt_id."""
    title, desc, tags = build_metadata(video_id)
    up = [
        PY, str(SCRIPT_DIR / "youtube_uploader.py"), "upload",
        "--file", str(mp4), "--title", title, "--description", desc,
        "--tags", ", ".join(tags), "--privacy", "unlisted",
    ]
    print(f"\n📤 Upload YouTube (unlisted): {title}")
    r = subprocess.run(up, capture_output=True, text=True, timeout=1800)
    out = (r.stdout or "") + (r.stderr or "")
    if r.returncode != 0:
        print(f"  ❌ upload falhou: {out[-500:]}")
        return None
    m = re.search(r"ID:\s*([A-Za-z0-9_-]{6,})", out)
    if not m:
        print(f"  ❌ não consegui extrair ID do upload:\n{out[-400:]}")
        return None
    yt_id = m.group(1)
    print(f"  ✅ publicado: https://youtu.be/{yt_id}")
    thumb = extract_thumbnail(mp4, video_id)
    if thumb:
        subprocess.run(
            [PY, str(SCRIPT_DIR / "youtube_uploader.py"), "thumbnail",
             "--video-id", yt_id, "--image", str(thumb)],
            capture_output=True, text=True, timeout=300,
        )
        print("  🖼️  thumbnail definida")
    return yt_id


def process_one(video_id: str, dry_run: bool = False) -> bool:
    state = load_state()
    if video_id in state.get("videos", {}):
        print(f"⏭️  {video_id} já publicado ({state['videos'][video_id].get('url')})")
        return True
    if video_id in (state.get("blocked") or {}):
        print(f"🔒 {video_id} bloqueado — use --unblock {video_id} após corrigir assets")
        return False

    audio = sorted(AUDIO_DIR.glob(f"{video_id}_*.mp3"), reverse=True)
    if not audio:
        print(f"❌ {video_id}: áudio não encontrado")
        return False
    dur = probe_duration_s(audio[0])
    if dur > MAX_DURATION_S:
        print(f"⏭️  {video_id}: {dur/60:.1f}min > 5min — fora do escopo (áudio longo)")
        return False

    print("\n" + "=" * 60)
    print(f"\n🎬 {video_id} · {dur/60:.1f}min · {episode_title(video_id)}")
    if dry_run:
        print("  [dry-run] quadros → assets → review → composicao → check → render → publish")
        return True

    qpath = PROTO / f"quadros-{video_id}.json"
    if not qpath.exists():
        if not run(
            [PY, str(SCRIPT_DIR / "bm_quadros_mapper.py"), "--video-id", video_id, "--audio", str(audio[0])],
            "Quadros (mapper)", timeout=300,
        ):
            return False

    if not run([PY, str(SCRIPT_DIR / "bm_pipeline.py"), "assets", "--video-id", video_id],
               "Assets (screenshots)", timeout=1800):
        return False

    rv = subprocess.run(
        [PY, str(SCRIPT_DIR / "bm_pipeline.py"), "review", "--video-id", video_id, "--json"],
        capture_output=True, text=True, timeout=120,
    )
    review_ok = False
    resumo = {}
    try:
        j = json.loads((rv.stdout or "").strip().splitlines()[-1] if (rv.stdout or "").strip() else "{}")
        status = j.get("status") or ""
        resumo = j.get("resumo") or {}
        review_ok = status in ("approved", "approved_forced", "approved_with_caveats", "pending") and not (
            (resumo.get("sem_imagem") or 0) > 0
        )
        # Autopilot só publica com pending (sem issues) ou approved*
        if status == "changes_requested" or (resumo.get("sem_imagem") or 0) > 0:
            review_ok = False
        if status == "pending" and (resumo.get("revisar") or 0) == 0 and (resumo.get("sem_imagem") or 0) == 0:
            review_ok = True
        if not review_ok:
            print(f"  ⛔ review NÃO aprovou: {status} {resumo}")
    except (json.JSONDecodeError, IndexError):
        print("  ⚠️  review: saída JSON não parseável — tratando como reprovado")
        review_ok = False

    if not review_ok:
        print(f"  ⛔ {video_id}: assets reprovados no gate — NÃO vai publicar. Revisar manualmente.")
        state.setdefault("blocked", {})[video_id] = {
            "reason": "assets reprovados no review",
            "at": datetime.now().isoformat(),
        }
        save_state(state)
        print(f"  🔒 {video_id} registrado como BLOQUEADO — cron vai pular (use --unblock <ID> após corrigir assets)")
        return False

    project_dir = BANCADA / f"project-{video_id}"
    ensure_project_files(project_dir)
    if not run(
        [PY, str(BANCADA / "build_episode_composition.py"),
         "--video-id", video_id, "--project-dir", str(project_dir),
         "--legenda-mode", "destaques"],
        "Composição HyperFrames (vale-newsroom, 1080p, destaques)",
        timeout=300,
    ):
        return False

    if not run(["npm", "run", "check"], "npm run check", timeout=180, cwd=project_dir):
        print(f"  ❌ {video_id}: check falhou ou projeto incompleto — NÃO vai publicar")
        return False
    if not (project_dir / "index.html").exists():
        print(f"  ❌ {video_id}: check falhou ou projeto incompleto — NÃO vai publicar")
        return False

    mp4 = render_episode(video_id, project_dir)
    if not mp4:
        return False

    yt_id = publish_youtube(mp4, video_id)
    if not yt_id:
        print(f"  ⚠️  {video_id}: render OK, mas upload falhou — MP4 em {mp4}")
        return False

    state.setdefault("videos", {})[video_id] = {
        "yt_id": yt_id,
        "url": f"https://youtu.be/{yt_id}",
        "mp4": str(mp4),
        "data": datetime.now().strftime("%Y-%m-%d"),
        "published_at": datetime.now().isoformat(),
    }
    save_state(state)
    print(f"\n✅ {video_id} publicado → https://youtu.be/{yt_id}")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="Autopilot BM: render 1080p + publicar curtos (≤5min)")
    ap.add_argument("--video-id", default=None, help="Processa UM episódio específico")
    ap.add_argument("--days", type=int, default=WINDOW_DAYS, help="Janela de áudios (default: 2 dias)")
    ap.add_argument("--max", type=int, default=MAX_PER_RUN, help="Máx de episódios por execução (default: 1)")
    ap.add_argument("--backfill", action="store_true", help="Processa TODO o backlog (perigoso: muitos renders)")
    ap.add_argument("--dry-run", action="store_true", help="Só lista o que faria")
    ap.add_argument("--unblock", default=None, help="Remove o bloqueio de um ID (após corrigir os assets)")
    args = ap.parse_args()

    if args.unblock:
        state = load_state()
        blocked = state.get("blocked") or {}
        if args.unblock in blocked:
            del blocked[args.unblock]
            state["blocked"] = blocked
            save_state(state)
            print(f"✅ --unblock {args.unblock}: bloqueio removido")
        else:
            print(f"ℹ️ --unblock {args.unblock}: não estava bloqueado")
        return 0

    if args.video_id:
        ok = process_one(args.video_id, dry_run=args.dry_run)
        return 0 if ok else 1

    candidates = candidate_audios(args.days, args.backfill)
    pending = []
    state = load_state()
    seen = set((state.get("videos") or {}).keys()) | set((state.get("blocked") or {}).keys())
    for a in candidates:
        m = re.match(r"^([A-Za-z0-9_-]{6,})_", a.name)
        if not m:
            continue
        vid = m.group(1)
        if vid not in seen and vid not in pending:
            pending.append(vid)

    if not pending:
        print("✅ Nenhum episódio BM pendente na janela.")
        return 0
    print(f"📋 {len(pending)} pendente(s): {', '.join(pending[:12])}")

    n_ok = 0
    for vid in pending:
        try:
            if process_one(vid, dry_run=args.dry_run):
                n_ok += 1
        except Exception as e:
            print(f"  ❌ {vid}: erro inesperado: {e}")
        if n_ok >= args.max:
            break
    print(f"\n🏁 Execução concluída: {n_ok} publicado(s).")
    return 0 if n_ok > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
