#!/usr/bin/env python3
"""Monta o MP4 faceless: loop do scroll (ou Ken Burns no PNG) + áudio."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))
COVER = ROOT / "public" / "assets" / "cover.jpg"
INTRO = ROOT / "branding" / "intro.mp4"
OUTRO = ROOT / "branding" / "outro.mp4"
W, H, FPS = 1920, 1080, 30


def run(cmd: list[str], tag: str) -> None:
    print(f"▶ {tag}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "")[-2000:]
        raise SystemExit(f"❌ {tag}\n{err}")


def ffprobe_s(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
    )
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def _index_by_url(captures_index: Path) -> dict[str, dict]:
    if not captures_index.exists():
        return {}
    data = json.loads(captures_index.read_text(encoding="utf-8"))
    return {i["url"]: i for i in data.get("items") or [] if i.get("url")}


def _fallback_visual(by_url: dict[str, dict], url: str, last: Path | None) -> Path:
    rec = by_url.get(url) or {}
    for key in ("path", "shot"):
        p = rec.get(key)
        if p and Path(p).exists() and Path(p).stat().st_size > 1000:
            return Path(p)
    if last and last.exists():
        return last
    if COVER.exists():
        return COVER
    raise SystemExit("❌ sem visual (captura falhou e não há cover.jpg)")


def _render_hold(src: Path, dest: Path, seconds: float) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    vf = (
        f"scale={W}:{H}:force_original_aspect_ratio=increase,"
        f"crop={W}:{H},zoompan=z='min(zoom+0.00035,1.06)':d=1:"
        f"x='iw/2-(iw/zoom/2)':y='0':s={W}x{H}:fps={FPS},format=yuv420p"
    )
    run(
        [
            "ffmpeg", "-y", "-loop", "1", "-i", str(src),
            "-t", f"{seconds:.3f}", "-vf", vf,
            "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            str(dest),
        ],
        f"hold {dest.name}",
    )


def _render_loop(src: Path, dest: Path, seconds: float) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    vf = (
        f"scale={W}:{H}:force_original_aspect_ratio=increase,"
        f"crop={W}:{H},fps={FPS},format=yuv420p"
    )
    run(
        [
            "ffmpeg", "-y", "-stream_loop", "-1", "-i", str(src),
            "-t", f"{seconds:.3f}", "-vf", vf,
            "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            str(dest),
        ],
        f"loop {dest.name}",
    )


def _overlay_l3(part: Path, l3: Path, dest: Path) -> None:
    from faceless_lower_third import overlay_filter

    run(
        [
            "ffmpeg", "-y",
            "-i", str(part),
            "-stream_loop", "-1", "-i", str(l3),
            "-filter_complex", overlay_filter(),
            "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            str(dest),
        ],
        f"l3 {dest.name}",
    )


def _place_on_desktop(site: Path, page_url: str, dest: Path, work: Path, seconds: float) -> None:
    from faceless_desktop import desktop_filter, render_chrome_png, write_wallpaper

    host = page_url or "fonte"
    wall = write_wallpaper(work / "wall.png", host)
    chrome = render_chrome_png(work / "chrome.png", page_url)
    dur = f"{max(seconds, 0.3):.3f}"
    run(
        [
            "ffmpeg", "-y",
            "-i", str(site),
            "-loop", "1", "-t", dur, "-i", str(wall),
            "-loop", "1", "-t", dur, "-i", str(chrome),
            "-filter_complex", desktop_filter(),
            "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-t", dur,
            str(dest),
        ],
        f"desktop {dest.name}",
    )


def compose(timeline_path: Path, out: Path, max_seconds: float | None, lower_third: bool = False, desktop: bool = False) -> Path:
    data = json.loads(timeline_path.read_text(encoding="utf-8"))
    audio = Path(data["audio"])
    if not audio.exists():
        raise SystemExit(f"❌ áudio ausente: {audio}")
    clips = data.get("clips") or []
    if not clips:
        raise SystemExit("❌ timeline sem clips")
    by_url = _index_by_url(timeline_path.parent / "captures" / "index.json")
    limit_ms = int(max_seconds * 1000) if max_seconds else None

    with tempfile.TemporaryDirectory(prefix="faceless_") as td:
        td_path = Path(td)
        parts: list[Path] = []
        last_visual: Path | None = None
        for i, clip in enumerate(clips, 1):
            start, end = int(clip["start_ms"]), int(clip["end_ms"])
            if limit_ms is not None:
                if start >= limit_ms:
                    break
                end = min(end, limit_ms)
            seconds = max((end - start) / 1000.0, 0.2)
            visual = _fallback_visual(by_url, clip.get("url") or "", last_visual)
            last_visual = visual
            raw = td_path / f"p{i:03d}_raw.mp4"
            if visual.suffix.lower() in {".webm", ".mp4", ".mov", ".mkv"}:
                _render_loop(visual, raw, seconds)
            else:
                _render_hold(visual, raw, seconds)
            if desktop:
                framed = td_path / f"p{i:03d}_desk.mp4"
                try:
                    _place_on_desktop(raw, clip.get("url") or "", framed, td_path / f"desk{i:03d}", seconds)
                    raw = framed
                except Exception as e:
                    print(f"  ⚠ desktop falhou ({e}); tela cheia")
            part = td_path / f"p{i:03d}.mp4"
            if lower_third:
                try:
                    from faceless_lower_third import clip_payload, date_from_audio, render_lower_third

                    title = data.get("titulo") or ""
                    payload = clip_payload(
                        clip,
                        title,
                        date=date_from_audio(str(data.get("audio") or "")),
                        kind=data.get("kind") or "bm",
                    )
                    l3 = td_path / f"l3_{i:03d}.webm"
                    render_lower_third(l3, payload)
                    _overlay_l3(raw, l3, part)
                except Exception as e:
                    print(f"  ⚠ lower-third falhou ({e}); segue sem faixa")
                    raw.replace(part)
            else:
                raw.replace(part)
            parts.append(part)
        if not parts:
            raise SystemExit("❌ nenhum clipe renderizado")

        concat_list = td_path / "concat.txt"
        concat_list.write_text("".join(f"file '{p}'\n" for p in parts), encoding="utf-8")
        body = td_path / "body.mp4"
        run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(body)],
            "concat body",
        )

        muxed = td_path / "muxed.mp4"
        mux_cmd = [
            "ffmpeg", "-y", "-i", str(body), "-i", str(audio),
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest", "-movflags", "+faststart",
        ]
        if max_seconds:
            mux_cmd.extend(["-t", f"{max_seconds:.3f}"])
        mux_cmd.append(str(muxed))
        run(mux_cmd, "mux audio")

        chain = []
        if INTRO.exists() and not max_seconds:
            chain.append(INTRO)
        chain.append(muxed)
        if OUTRO.exists() and not max_seconds:
            chain.append(OUTRO)
        out.parent.mkdir(parents=True, exist_ok=True)
        if len(chain) == 1:
            run(["ffmpeg", "-y", "-i", str(chain[0]), "-c", "copy", str(out)], "copy out")
        else:
            scaled = []
            for j, src in enumerate(chain):
                s = td_path / f"s{j}.mp4"
                run(
                    [
                        "ffmpeg", "-y", "-i", str(src),
                        "-vf", f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,fps={FPS},format=yuv420p",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                        str(s),
                    ],
                    f"scale {src.name}",
                )
                scaled.append(s)
            cl = td_path / "final.txt"
            cl.write_text("".join(f"file '{p}'\n" for p in scaled), encoding="utf-8")
            run(
                ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(cl), "-c", "copy", str(out)],
                "concat intro/outro",
            )
    print(f"✅ {out}  {ffprobe_s(out):.1f}s")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Compose faceless 1080p")
    ap.add_argument("--timeline", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-seconds", type=float, default=None)
    ap.add_argument("--no-lower-third", action="store_true")
    ap.add_argument("--desktop", action="store_true", help="matéria dentro de mockup de browser + wallpaper")
    args = ap.parse_args()
    compose(
        Path(args.timeline),
        Path(args.out),
        args.max_seconds,
        lower_third=not args.no_lower_third,
        desktop=args.desktop,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
