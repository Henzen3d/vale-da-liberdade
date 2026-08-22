from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from faceless_compose import compose  # noqa: E402


def test_compose_two_pngs(tmp_path):
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    Image.new("RGB", (64, 64), (200, 40, 40)).save(a)
    Image.new("RGB", (64, 64), (40, 40, 200)).save(b)
    silence = tmp_path / "silence.wav"
    subprocess.check_call(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "2", str(silence)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    timeline = tmp_path / "timeline.json"
    captures = tmp_path / "captures"
    captures.mkdir()
    (captures / "index.json").write_text(
        '{"items":[{"url":"https://a.example/","ok":true,"path":"%s","kind":"shot"},'
        '{"url":"https://b.example/","ok":true,"path":"%s","kind":"shot"}]}' % (a, b),
        encoding="utf-8",
    )
    timeline.write_text(
        '{"audio":"%s","clips":['
        '{"start_ms":0,"end_ms":1000,"url":"https://a.example/","veiculo":"A","quadro":"q","action":"hold"},'
        '{"start_ms":1000,"end_ms":2000,"url":"https://b.example/","veiculo":"B","quadro":"q","action":"hold"}'
        "]}" % silence,
        encoding="utf-8",
    )
    out = tmp_path / "out.mp4"
    compose(timeline, out, max_seconds=2)
    assert out.exists() and out.stat().st_size > 1000
    probe = subprocess.check_output(
        ["ffprobe", "-v", "quiet", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(out)],
        text=True,
    ).strip()
    assert probe.startswith("1920,1080")
    dur = float(
        subprocess.check_output(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)],
            text=True,
        ).strip()
    )
    assert 1.6 <= dur <= 2.5
