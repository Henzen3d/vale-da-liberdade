#!/usr/bin/env python3
"""Reconstrói as <description> do feed RSS Brasil e Mundo com as referências.

Cada item é identificado pelo <guid>brasil-e-mundo-{video_id}</guid>; a
description é remontada no mesmo formato do step_publish_feed (bm_pipeline):
"Fonte original: X. Vídeo de referência: Y. Referências: veiculo: url | ..."

Itens cujo especial-{id}.json não existir mantêm a description atual.

Uso:
    python scripts/bm_feed_rebuild.py
    # depois: publish_site.py para copiar output/.../feed.xml → public/
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
FEED = ROOT / "output" / "brasil_e_mundo" / "feed.xml"
EPS = ROOT / "output" / "brasil_e_mundo" / "episodes"


def _xml_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def show_notes(data: dict) -> str:
    refs = data.get("fonte_referencias") or []
    notes = (
        f"Comentário do Peter sobre notícias do Brasil e do Mundo. "
        f"Fonte original: {data.get('fonte_veiculo') or data.get('fonte_canal', 'ANCAPSU')}. "
        f"Vídeo de referência: {data.get('fonte_url', '')}."
    )
    if refs:
        notes += " Referências: " + " | ".join(
            f"{r.get('veiculo', '').strip()}: {r.get('url', '').strip()}".strip(" :")
            for r in refs
            if r.get("url")
        )
    return notes


def main() -> int:
    if not FEED.exists():
        print(f"❌ Feed não encontrado: {FEED}")
        return 1
    feed = FEED.read_text(encoding="utf-8")

    def _repl(m: re.Match) -> str:
        item = m.group(0)
        g = re.search(r"<guid[^>]*>brasil-e-mundo-([^<]+)</guid>", item)
        if not g:
            return item
        jp = EPS / f"especial-{g.group(1)}.json"
        if not jp.exists():
            return item
        try:
            data = json.loads(jp.read_text(encoding="utf-8"))
        except Exception:
            return item
        desc = _xml_escape(show_notes(data))
        return re.sub(
            r"<description>.*?</description>",
            f"<description>{desc}</description>",
            item,
            count=1,
            flags=re.S,
        )

    new_feed = re.sub(r"<item>.*?</item>", _repl, feed, flags=re.S)
    FEED.write_text(new_feed, encoding="utf-8")
    total = len(re.findall(r"<item>", new_feed))
    com_refs = len(re.findall(r"Referências:", new_feed))
    print(f"✅ Feed atualizado: {total} itens · {com_refs} com Referências")
    print("➡️  Rode publish_site.py para copiar para public/feed-brasil-e-mundo.xml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
