"""FFmpeg, VA-API lock, intro/outro e muxing do vídeo BM."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path

from bm_video.constants import *  # noqa: F403

def probe_duration_s(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
    )
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def vaapi_encode_lock():
    """HD 630: 2 h264_vaapi em paralelo geram NAL inválido (Gilmar Jjy1_umSvXA)."""

    class _Lock:
        def __enter__(self):
            self.f = open(VAAPI_LOCK_PATH, "w")
            fcntl.flock(self.f.fileno(), fcntl.LOCK_EX)
            return self

        def __exit__(self, *_exc):
            try:
                fcntl.flock(self.f.fileno(), fcntl.LOCK_UN)
            finally:
                self.f.close()

    return _Lock()


def mp4_is_playable(path: Path) -> bool:
    """False se o container mente (duration ok) mas o H264 não decodifica."""
    if not path or not path.is_file() or path.stat().st_size < 50_000:
        return False
    if probe_duration_s(path) < 5.0:
        return False
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-t", "3", "-f", "null", "-"],
        capture_output=True,
        text=True,
        timeout=90,
    )
    err = (r.stderr or "")
    if r.returncode != 0:
        return False
    bad = ("invalid nal", "error splitting", "nothing was written", "pps_id")
    return not any(b in err.lower() for b in bad)


def _run_ffmpeg(cmd: list) -> subprocess.CompletedProcess:
    """Roda ffmpeg; se a sessão ainda não tem grupo render, usa sg se disponível."""
    env = os.environ.copy()
    env.setdefault("LIBVA_DRIVER_NAME", "iHD")
    if os.access(RENDER_NODE, os.R_OK | os.W_OK):
        return subprocess.run(cmd, capture_output=True, text=True, env=env)
    if shutil.which("sg") and os.path.exists(RENDER_NODE):
        inner = " ".join(shlex.quote(c) for c in cmd)
        return subprocess.run(
            ["sg", "render", "-c", inner],
            capture_output=True,
            text=True,
            env=env,
        )
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


def mux_video(raw: Path, audio: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    # HD 630: h264_qsv (libvpl) falha com MFX -9 neste ffmpeg.
    # Encode real é VA-API (iHD EncSliceLP) + fallback CPU.
    cmd_hw = [
        "ffmpeg", "-y",
        "-vaapi_device", RENDER_NODE,
        "-i", str(raw),
        "-i", str(audio),
        "-vf", "format=nv12,hwupload",
        "-c:v", "h264_vaapi", "-qp", "20",
        "-c:a", "aac", "-b:a", "192k", "-ac", "2",
        "-shortest",
        "-movflags", "+faststart",
        str(dest),
    ]
    with vaapi_encode_lock():
        r = _run_ffmpeg(cmd_hw)
    if r.returncode == 0 and dest.exists() and dest.stat().st_size > 0 and mp4_is_playable(dest):
        print("  ⚡ muxing acelerado por hardware Intel VA-API (h264_vaapi)")
        return dest

    print(f"  ℹ️  h264_vaapi indisponível; fallback libx264: {(r.stderr or '')[-180:].strip()}")
    cmd_cpu = [
        "ffmpeg", "-y",
        "-i", str(raw),
        "-i", str(audio),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-ac", "2",
        "-shortest", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(dest),
    ]
    r = subprocess.run(cmd_cpu, capture_output=True, text=True)
    if r.returncode != 0 or not dest.exists():
        raise RuntimeError(r.stderr[-800:] if r.stderr else "ffmpeg falhou")
    return dest


def compose_presenter(base_mp4: Path, episode: dict, audio: Path, work: Path) -> Path:
    """Sobre o mockup: avatar aprovado + lower third na frente. Falha não derruba o mp4 base."""
    if not AVATAR_LOOP.is_file():
        print("  ⚠️  avatar loop ausente — segue sem apresentador")
        return base_mp4
    dest = base_mp4.with_name(base_mp4.stem + "-onair.mp4")
    l3_path = work / "lower-third.webm"
    try:
        from faceless_lower_third import clip_payload, date_from_audio, render_lower_third

        title = _unescape(episode.get("titulo") or "Brasil e Mundo")
        subhead = one_line_subhead(episode)
        vid = work.name if work.name else None
        headlines = ticker_headlines(episode, vid)
        payload = clip_payload(
            {
                "veiculo": episode.get("fonte_veiculo") or "Brasil e Mundo",
                "url": APP_URL,
                "line": title,
            },
            episode_title=title,
            date=date_from_audio(str(audio)) or episode_date(audio),
            kind="bm",
            subtitle=subhead,
            ticker=headlines,
        )
        render_lower_third(l3_path, payload, seconds=12.0)
    except Exception as exc:
        print(f"  ⚠️  lower-third falhou ({exc}); overlay só do avatar")
        l3_path = None

    vf_avatar = (
        f"[1:v]crop={AVATAR_CROP},format=rgba,"
        f"colorkey=0x007E00:0.10:0.03,lut=a='if(lt(val\\,230)\\,0\\,255)',"
        f"scale={AVATAR_SCALE}:flags=lanczos,"
        f"tpad=start_duration={AVATAR_START_DELAY_S}:start_mode=clone[av];"
        f"[0:v][av]overlay={AVATAR_OVERLAY}:format=auto:shortest=1"
    )
    inputs = ["-i", str(base_mp4), "-stream_loop", "-1", "-i", str(AVATAR_LOOP)]
    if l3_path and l3_path.is_file():
        inputs += ["-stream_loop", "-1", "-i", str(l3_path)]
        filter_complex = (
            vf_avatar + "[base];"
            "[2:v]format=yuva444p,colorkey=0x00FF00:0.10:0.22,"
            "despill=type=green:mix=0.45:expand=0[l3];"
            "[base][l3]overlay=0:0:shortest=1,format=yuv420p[v]"
        )
    else:
        filter_complex = vf_avatar + ",format=yuv420p[v]"

    hw_fc = filter_complex.replace("format=yuv420p[v]", "format=nv12,hwupload[v]")
    cmd_hw = [
        "ffmpeg", "-y",
        "-vaapi_device", RENDER_NODE,
        *inputs,
        "-filter_complex", hw_fc,
        "-map", "[v]", "-map", "0:a",
        "-c:v", "h264_vaapi", "-qp", "20",
        "-c:a", "copy",
        "-movflags", "+faststart",
        str(dest),
    ]
    with vaapi_encode_lock():
        r = _run_ffmpeg(cmd_hw)
    if r.returncode == 0 and dest.exists() and dest.stat().st_size > 0 and mp4_is_playable(dest):
        print(f"  ⚡ apresentador acelerado por hardware Intel VA-API ({dest.stat().st_size // 1024} KB)")
        return dest
    if dest.exists():
        dest.unlink(missing_ok=True)
        print("  ⚠️  VA-API onair ilegível — fallback libx264")

    cmd_cpu = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "0:a",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
        "-c:a", "copy",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(dest),
    ]
    r = subprocess.run(cmd_cpu, capture_output=True, text=True)
    if r.returncode != 0 or not dest.exists() or not mp4_is_playable(dest):
        print(f"  ⚠️  compose apresentador falhou; usa mockup puro: {(r.stderr or '')[-300:]}")
        return base_mp4
    print(f"  ✅ apresentador {dest.name} ({dest.stat().st_size // 1024} KB)")
    return dest


def find_intro_audio() -> Path | None:
    """Localiza o arquivo de áudio da música de abertura (intro)."""
    candidates = [
        INTRO_AUDIO_DIR / "Top-Intro.mp3",
        INTRO_AUDIO_DIR / "intro_tema.wav",
        INTRO_AUDIO_DIR / "intro_tema.mp3",
    ]
    for c in candidates:
        if c.is_file() and c.stat().st_size > 1000:
            return c
    if INTRO_AUDIO_DIR.is_dir():
        for p in sorted(INTRO_AUDIO_DIR.iterdir()):
            if p.is_file() and p.suffix.lower() in {".mp3", ".wav", ".m4a", ".aac"} and "readme" not in p.name.lower():
                return p
    return None


def prepare_audio_with_intro(audio: Path, work_dir: Path) -> Path:
    """Aplica a vinheta musical no início do áudio com ducking elegante.

    0.0s–1.5s: trilha em volume cheio (1.0), sem voz.
    1.5s: locução entra (adelay 1500ms) e música cai para 0.18.
    1.5s–8.0s: hold em 0.18.
    8.0s–15.0s: fade linear 0.18 → 0.00.
    """
    intro = find_intro_audio()
    if not intro:
        return audio

    out_audio = work_dir / f"{audio.stem}-with-intro-{INTRO_MIX_TAG}.mp3"
    if out_audio.is_file() and out_audio.stat().st_size > 50_000:
        return out_audio

    print(f"  🎵 Mixando trilha de abertura ({intro.name}) com auto-ducking...")
    fade_span = INTRO_FADE_END_S - INTRO_DUCK_UNTIL_S
    delay_ms = int(INTRO_VOICE_DELAY_S * 1000)
    vol_expr = (
        f"if(lt(t,{INTRO_VOICE_DELAY_S}),1,"
        f"if(lt(t,{INTRO_DUCK_UNTIL_S}),{INTRO_DUCK_VOL},"
        f"if(lt(t,{INTRO_FADE_END_S}),{INTRO_DUCK_VOL}*({INTRO_FADE_END_S}-t)/{fade_span},0)))"
    )
    fc = (
        f"[0:a]aformat=channel_layouts=stereo:sample_rates=48000,"
        f"apad=whole_dur={INTRO_FADE_END_S},atrim=0:{INTRO_FADE_END_S},"
        f"volume='{vol_expr}':eval=frame[bgm];"
        f"[1:a]aformat=channel_layouts=stereo:sample_rates=48000,adelay={delay_ms}|{delay_ms}[voz];"
        "[bgm][voz]amix=inputs=2:duration=longest:normalize=0[a]"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", str(intro),
        "-i", str(audio),
        "-filter_complex", fc,
        "-map", "[a]",
        "-c:a", "libmp3lame", "-b:a", "192k",
        str(out_audio),
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if r.returncode == 0 and out_audio.is_file() and out_audio.stat().st_size > 50_000:
            print(f"  ✅ Trilha de abertura integrada ao episódio ({out_audio.name})")
            return out_audio
        print(f"  ⚠️  Falha ao mixar intro musical: {(r.stderr or '')[-200:]}; usando áudio original")
    except Exception as exc:
        print(f"  ⚠️  Exceção ao mixar intro musical: {exc}; usando áudio original")

    return audio


def find_music_outro() -> Path | None:
    """Localiza a trilha musical de encerramento em branding/audio/outro/."""
    candidates = [
        AUDIO_OUTRO_DIR / "final-mix-25s.wav",
        AUDIO_OUTRO_DIR / "outro_tema.wav",
        AUDIO_OUTRO_DIR / "outro_tema.mp3",
        AUDIO_OUTRO_DIR / "final.mp3",
    ]
    for c in candidates:
        if c.is_file() and c.stat().st_size > 1000:
            return c
    if AUDIO_OUTRO_DIR.is_dir():
        for p in sorted(AUDIO_OUTRO_DIR.iterdir()):
            if p.is_file() and p.suffix.lower() in {".wav", ".mp3", ".m4a", ".aac"} and "readme" not in p.name.lower():
                return p
    return None


def resolve_outro_take(video_id: str | None = None) -> Path | None:
    """Sorteia um take bruto de gravação do apresentador (gravacoes/*.mp4)."""
    if GRAVACOES_DIR.is_dir():
        takes = sorted(
            p for p in GRAVACOES_DIR.glob("*.mp4")
            if p.is_file() and p.stat().st_size > 500_000 and not p.name.startswith(".")
        )
        if takes:
            if video_id:
                idx = int(hashlib.md5(video_id.encode("utf-8")).hexdigest(), 16) % len(takes)
                return takes[idx]
            return takes[0]
    return None


def compose_outro_for_episode(video_id: str, take: Path, wallpaper: Path | None, work: Path) -> Path | None:
    """Monta o encerramento dinâmico usando o MESMO wallpaper do episódio e ducking suave.

    Durante a fala: trilha em OUTRO_DUCK_VOL.
    Depois da voz: swell linear OUTRO_SWELL_S até OUTRO_PEAK_VOL, hold, fade OUTRO_FADEOUT_S.
    Duração total = take + OUTRO_TAIL_S (último frame do Peter congelado).
    """
    if not take or not take.is_file():
        return None

    dest = work / f"outro_{video_id}_{OUTRO_MIX_TAG}.mp4"
    if dest.is_file() and dest.stat().st_size > 50_000:
        return dest

    dur = probe_duration_s(take)
    if dur <= 0.0:
        return None

    music = find_music_outro()
    wp = wallpaper if (wallpaper and wallpaper.is_file()) else pick_wallpaper(video_id)
    if not wp or not wp.is_file():
        return None

    total = dur + OUTRO_TAIL_S
    swell_start = dur
    swell_end = dur + OUTRO_SWELL_S
    fade_start = max(swell_end, total - OUTRO_FADEOUT_S)
    fade_dur = max(0.2, total - fade_start)
    peak_span = OUTRO_PEAK_VOL - OUTRO_DUCK_VOL

    vf_pres = (
        "[1:v]scale=854:480:force_original_aspect_ratio=decrease,"
        "pad=854:480:(ow-iw)/2:(oh-ih)/2:color=black,"
        "drawbox=x=0:y=0:w=iw:h=ih:color=white@0.8:t=3,"
        f"tpad=stop_mode=clone:stop_duration={OUTRO_TAIL_S:.2f}[pres]"
    )
    vf_bg = (
        "[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,"
        "drawbox=x=1200:y=100:w=608:h=342:color=black@0.4:t=fill,"
        "drawbox=x=1200:y=100:w=608:h=342:color=white@0.2:t=2,"
        "drawbox=x=1200:y=520:w=608:h=342:color=black@0.4:t=fill,"
        "drawbox=x=1200:y=520:w=608:h=342:color=white@0.2:t=2,"
        "drawbox=x=420:y=640:w=180:h=180:color=black@0.4:t=fill,"
        "drawbox=x=420:y=640:w=180:h=180:color=white@0.2:t=2[bg]"
    )
    vf_overlay = "[bg][pres]overlay=80:100:shortest=1[v]"

    inputs = ["-loop", "1", "-i", str(wp), "-i", str(take)]
    if music and music.is_file():
        inputs += ["-stream_loop", "-1", "-i", str(music)]
        vol_expr = (
            f"if(lt(t,{swell_start:.2f}),{OUTRO_DUCK_VOL},"
            f"if(lt(t,{swell_end:.2f}),{OUTRO_DUCK_VOL}+{peak_span:.2f}*(t-{swell_start:.2f})/{OUTRO_SWELL_S:.2f},"
            f"if(lt(t,{fade_start:.2f}),{OUTRO_PEAK_VOL},"
            f"{OUTRO_PEAK_VOL}*({total:.2f}-t)/{fade_dur:.2f})))"
        )
        af_bgm = (
            f"[2:a]atrim=0:{total:.2f},asetpts=PTS-STARTPTS,"
            f"volume='{vol_expr}':eval=frame[bgm]"
        )
        af_voz = f"[1:a]volume=1.0,apad=pad_dur={OUTRO_TAIL_S:.2f}[voz]"
        af_mix = "[voz][bgm]amix=inputs=2:duration=first:normalize=0[a]"
        filter_complex = f"{vf_pres};{vf_bg};{vf_overlay};{af_bgm};{af_voz};{af_mix}"
        map_args = ["-map", "[v]", "-map", "[a]"]
    else:
        filter_complex = f"{vf_pres};{vf_bg};{vf_overlay}"
        map_args = ["-map", "[v]", "-map", "1:a"]

    print(f"  🎬 Compondo encerramento contextual ({take.name} + wallpaper {wp.name}, {total:.1f}s)...")
    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        *map_args,
        "-t", f"{total:.2f}",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(dest),
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if r.returncode == 0 and dest.is_file() and dest.stat().st_size > 50_000:
            print(f"  ✅ Encerramento contextual composto: {dest.name} ({dest.stat().st_size // 1024} KB)")
            return dest
        print(f"  ⚠️  Falha ao compor encerramento dinâmico: {(r.stderr or '')[-300:]}")
    except Exception as exc:
        print(f"  ⚠️  Exceção ao compor encerramento dinâmico: {exc}")

    return None


def resolve_outro_video(video_id: str | None = None, wallpaper: Path | None = None, work: Path | None = None) -> Path | None:
    """Resolve o vídeo de encerramento: compõe dinamicamente com o wallpaper do episódio ou usa fallback."""
    # 1. Tentar composição dinâmica contextual com o wallpaper do episódio
    if video_id and work:
        take = resolve_outro_take(video_id)
        if take:
            composed = compose_outro_for_episode(video_id, take, wallpaper, work)
            if composed:
                return composed

    # 2. Fallback para vídeos pré-renderizados em prontos/
    if OUTRO_PRONTOS_DIR.is_dir():
        prontos = sorted(
            p for p in OUTRO_PRONTOS_DIR.glob("*.mp4")
            if p.is_file() and p.stat().st_size > 100_000
        )
        if prontos:
            if video_id:
                idx = int(hashlib.md5(video_id.encode("utf-8")).hexdigest(), 16) % len(prontos)
                return prontos[idx]
            return prontos[0]

    # 3. Fallback canônico
    if OUTRO_CANONICAL.is_file() and OUTRO_CANONICAL.stat().st_size > 100_000:
        return OUTRO_CANONICAL

    return None


def _normalize_clip_for_concat(src: Path, dest: Path) -> bool:
    """Reencode 1920×1080 / 25fps / yuv420p / stereo 48k — concat demuxer exige isso."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-i", str(src),
        "-vf",
        "scale=1920:1080:force_original_aspect_ratio=decrease,"
        "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,"
        "fps=25,format=yuv420p,setsar=1",
        "-af", "aformat=sample_rates=48000:channel_layouts=stereo,aresample=async=1",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(dest),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    return r.returncode == 0 and dest.is_file() and dest.stat().st_size > 50_000


def _concat_demux(clip_a: Path, clip_b: Path, dest: Path, work: Path) -> bool:
    """Concatena dois clips já normalizados via concat demuxer (sem filtergraph)."""
    lst = work / f"concat_{dest.stem}.txt"
    lst.write_text(
        f"file '{clip_a.resolve()}'\nfile '{clip_b.resolve()}'\n",
        encoding="utf-8",
    )
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(lst),
        "-c", "copy",
        "-movflags", "+faststart",
        str(dest),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    return r.returncode == 0 and dest.is_file() and dest.stat().st_size > 50_000


def append_outro_video(base_mp4: Path, outro_mp4: Path, work: Path) -> Path:
    """Concatena o encerramento. Falha = RuntimeError (não sobe sem outro)."""
    if not outro_mp4 or not outro_mp4.is_file():
        raise RuntimeError("encerramento obrigatório: arquivo de outro ausente")

    dest = base_mp4.with_name(base_mp4.stem + "-outro.mp4")
    print(f"  🎬 Concatenando encerramento: {outro_mp4.name}...")

    fc = (
        "[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
        "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=25,format=yuv420p,setsar=1[v0];"
        "[1:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
        "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=25,format=yuv420p,setsar=1[v1];"
        "[0:a]aformat=sample_rates=48000:channel_layouts=stereo,aresample=async=1[a0];"
        "[1:a]aformat=sample_rates=48000:channel_layouts=stereo,aresample=async=1[a1];"
        "[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", str(base_mp4),
        "-i", str(outro_mp4),
        "-filter_complex", fc,
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(dest),
    ]
    last_err = ""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if r.returncode == 0 and dest.is_file() and dest.stat().st_size > base_mp4.stat().st_size:
            print(f"  ✅ Encerramento anexado: {dest.name} ({dest.stat().st_size // 1024} KB)")
            return dest
        last_err = (r.stderr or "")[-400:]
        print(f"  ⚠️  concat filter falhou: {last_err}")
    except Exception as exc:
        last_err = str(exc)
        print(f"  ⚠️  concat filter exceção: {exc}")

    # Retry: reencode ambos + concat demuxer (evita Invalid argument no filtergraph).
    print("  🔁 retry concat_demux após normalizar os dois clips...")
    na = work / f"{base_mp4.stem}-norm.mp4"
    nb = work / f"{outro_mp4.stem}-norm.mp4"
    if _normalize_clip_for_concat(base_mp4, na) and _normalize_clip_for_concat(outro_mp4, nb):
        if _concat_demux(na, nb, dest, work) and dest.stat().st_size > base_mp4.stat().st_size:
            print(f"  ✅ Encerramento anexado (concat_demux): {dest.name} ({dest.stat().st_size // 1024} KB)")
            return dest

    # Último recurso: outro canônico (já 1080p) no lugar do clip quebrado.
    if OUTRO_CANONICAL.is_file() and outro_mp4.resolve() != OUTRO_CANONICAL.resolve():
        print(f"  🔁 retry com outro canônico {OUTRO_CANONICAL.name}")
        return append_outro_video(base_mp4, OUTRO_CANONICAL, work)

    raise RuntimeError(
        f"encerramento obrigatório: concat falhou para {base_mp4.name} + {outro_mp4.name}: {last_err}"
    )
