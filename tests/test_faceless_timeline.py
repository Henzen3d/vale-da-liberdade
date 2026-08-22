from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from faceless_timeline import (  # noqa: E402
    build_bm_timeline,
    build_daily_timeline,
    is_usable_url,
    parse_raw_md,
)

RAW = """### QUADRO: SEGURANÇA PÚBLICA
#### • AlertaBlu
  - **URL**: [https://oblumenauense.com.br/alerta/](https://oblumenauense.com.br/alerta/)
### QUADRO: SAÚDE
#### • Hospital
  - **URL**: [https://news.mob.tec.br/ep/x.html](https://news.mob.tec.br/ep/x.html)
"""


def test_parse_and_drop_self():
    stories = [s for s in parse_raw_md(RAW) if is_usable_url(s.url)]
    assert [s.quadro for s in stories] == ["SEGURANÇA PÚBLICA"]
    assert stories[0].url.startswith("https://oblumenauense.com.br")


def test_covers_full_audio():
    roteiro = {
        "introducao": [{"quadro": "INTRODUÇÃO EDITORIAL", "texto": "oi"}],
        "quadros": [
            {"quadro": "SEGURANÇA PÚBLICA", "texto": "alerta blu rotas"},
            {"quadro": "SEGURANÇA PÚBLICA", "texto": "mais sobre o app"},
        ],
        "fechamento": [{"quadro": "FECHAMENTO", "texto": "tchau"}],
    }
    stories = parse_raw_md(RAW)
    clips = build_daily_timeline(roteiro, stories, duration_ms=10_000)
    assert clips[0].start_ms == 0
    assert clips[-1].end_ms == 10_000
    assert any(c.url.startswith("https://oblumenauense") for c in clips)


def test_bm_drops_self_and_covers_duration():
    especial = {
        "abertura": [{"texto": "abre a conversa"}],
        "desenvolvimento": [{"texto": "a Folha publicou o telefonema"}],
        "fechamento": [{"texto": "fecha o caso"}],
        "fonte_referencias": [
            {"veiculo": "Folha", "url": "https://www1.folha.uol.com.br/poder/x.shtml"},
            {"veiculo": "G1", "url": "https://g1.globo.com/politica/noticia.html"},
            {"veiculo": "Vale", "url": "https://news.mob.tec.br/ep/x.html", "self": True},
        ],
    }
    clips = build_bm_timeline(especial, 9_000)
    assert clips[0].start_ms == 0
    assert clips[-1].end_ms == 9_000
    urls = {c.url for c in clips}
    assert "https://news.mob.tec.br/ep/x.html" not in urls
    assert any("folha.uol.com.br" in u for u in urls)
    folha = [c for c in clips if "folha" in c.url]
    assert folha, "texto que cita Folha deve ancorar a URL da Folha"
    assert all(c.end_ms > c.start_ms for c in clips)
    # desenvolvimento vira fatias longas, não um corte por parágrafo
    assert all((c.end_ms - c.start_ms) >= 1500 for c in clips)
