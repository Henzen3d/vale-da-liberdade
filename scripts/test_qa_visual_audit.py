#!/usr/bin/env python3
"""Testes leves do QA visual (Etapa 9)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(ROOT))

from qa_visual_audit import validate_pre_render  # noqa: E402


def test_pre_render_healthy_plan():
    plan = {
        "video_id": "yt_bm_test",
        "total_duration_s": 30.0,
        "beats": [
            {
                "t0": 0.0,
                "t1": 14.0,
                "semantic_role": "apresentacao_fato",
                "visual_component": "source",
                "visual_variant": "portal_clean",
                "visual_payload": {"headline": "ok"},
                "url": "https://example.com",
                "veiculo": "G1",
            },
            {
                "t0": 14.0,
                "t1": 30.0,
                "semantic_role": "declaracao_forte",
                "visual_component": "quote",
                "visual_variant": "card_gold",
                "visual_payload": {
                    "author_name": "Fulano",
                    "author_role": "Prefeito",
                    "quote_text": "Não haverá aumento de IPTU neste ano fiscal.",
                    "source_name": "Coletiva",
                    "date": "05/09/2026",
                },
            },
        ],
    }
    out = validate_pre_render(plan, audio_duration_s=30.0, demote_invalid=True)
    assert out["ok"] is True
    assert out["elapsed_ms"] < 1000
    assert out["status"] == "APPROVED"
    assert out["beats"][1]["visual_component"] == "quote"


def test_pre_render_demotes_short_quote():
    plan = {
        "video_id": "yt_bm_bad_quote",
        "total_duration_s": 20.0,
        "beats": [
            {
                "t0": 0.0,
                "t1": 12.0,
                "semantic_role": "declaracao_forte",
                "visual_component": "quote",
                "visual_variant": "card_gold",
                "visual_payload": {"quote_text": "curto", "author_name": "X"},
            },
            {
                "t0": 12.0,
                "t1": 20.0,
                "semantic_role": "apresentacao_fato",
                "visual_component": "source",
                "visual_variant": "",
                "visual_payload": {},
            },
        ],
    }
    out = validate_pre_render(plan, audio_duration_s=20.0)
    assert out["ok"] is True
    assert out["demotions"], "esperava demote"
    assert out["beats"][0]["visual_component"] == "source"


def test_pre_render_chart_nan_demotes():
    plan = {
        "beats": [
            {
                "t0": 0.0,
                "t1": 10.0,
                "visual_component": "chart",
                "visual_payload": {"metric_value": "NaN", "metric_label": "X"},
            },
            {
                "t0": 10.0,
                "t1": 20.0,
                "visual_component": "source",
                "visual_payload": {},
            },
        ]
    }
    out = validate_pre_render(plan, audio_duration_s=20.0)
    assert out["beats"][0]["visual_component"] == "source"
    assert any(d["from"] == "chart" for d in out["demotions"])


if __name__ == "__main__":
    test_pre_render_healthy_plan()
    test_pre_render_demotes_short_quote()
    test_pre_render_chart_nan_demotes()
    print("OK test_qa_visual_audit")
