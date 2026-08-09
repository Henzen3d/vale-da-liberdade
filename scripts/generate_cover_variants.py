#!/usr/bin/env python3
"""
"""Gera variações da capa padrão (WebP + JPEG em 400/800/1200) a partir de
public/assets/cover.jpg.

NÃO roda no publish_site.py — executar **uma única vez** quando a capa mudar.
Quando a feature futura de capa por episódio existir, aí sim o publish passa
a gerar variações automaticamente.

Uso:
  python3 scripts/generate_cover_variants.py
Saída: public/assets/cover-{400,800,1200}.{webp,jpg}
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("pip install pillow", file=sys.stderr)
    raise SystemExit(1)

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "public" / "assets" / "cover.jpg"
OUT_DIRS = [
    ROOT / "public" / "assets",
]
SIZES = [400, 800, 1200]
WEBP_Q = 82
JPEG_Q = 85


def main() -> int:
    if not SRC.exists():
        print(f"fonte ausente: {SRC}", file=sys.stderr)
        return 1

    total_saved_webp = 0
    total_jpg = 0
    with Image.open(SRC) as src:
        src = src.convert("RGB")
        for size in SIZES:
            img = src.copy()
            if max(img.size) > size:
                img.thumbnail((size, size), Image.Resampling.LANCZOS)
            for out_dir in OUT_DIRS:
                out_dir.mkdir(parents=True, exist_ok=True)
                webp_path = out_dir / f"cover-{size}.webp"
                jpg_path = out_dir / f"cover-{size}.jpg"
                img.save(webp_path, "WEBP", quality=WEBP_Q, method=6)
                img.save(jpg_path, "JPEG", quality=JPEG_Q, optimize=True, progressive=True)
                w = webp_path.stat().st_size
                j = jpg_path.stat().st_size
                total_saved_webp += w
                total_jpg += j
                print(f"  {size:>5}px  webp={w/1024:6.1f}KiB  jpg={j/1024:6.1f}KiB  → {out_dir.name}/cover-{size}.{{webp,jpg}}")

    print(f"\ntotal webp gerado: {total_saved_webp/1024:.1f} KiB")
    print(f"total jpg  gerado: {total_jpg/1024:.1f} KiB")
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
