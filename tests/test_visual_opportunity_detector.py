# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from bm_scene_timeline import detect_visual_opportunities  # noqa: E402


def test_quote_detection_chosen_component():
    text = 'O prefeito garantiu: "Não haverá aumento no IPTU neste ano."'
    result = detect_visual_opportunities(text, "", "")
    assert result["chosen_component"] == "quote"
    assert result["paragraph_text"] == text
    assert isinstance(result["detected_opportunities"], list)
    assert len(result["detected_opportunities"]) >= 1

    quote_ops = [
        o for o in result["detected_opportunities"]
        if o.get("recommended_component") == "quote"
    ]
    assert quote_ops, "expected a quote opportunity"
    op = quote_ops[0]
    assert op["score"] >= 0.75
    assert op["recommended_variant"] == "card_gold"
    extracted = op.get("extracted_data") or {}
    assert "quote" in (extracted.get("quote_text") or "").lower() or "aumento" in (extracted.get("quote_text") or "").lower()
    assert "IPTU" in (extracted.get("quote_text") or "") or "aumento" in (extracted.get("quote_text") or "")


def test_generic_text_falls_back_to_source():
    text = "A equipe visitou a região nesta manhã e conversou com moradores sobre o trânsito local."
    result = detect_visual_opportunities(text, "", "")
    assert result["chosen_component"] == "source"
    comps = [o["recommended_component"] for o in result["detected_opportunities"]]
    assert "source" in comps
    # Sem sinais fortes, não deve escolher quote/document/chart
    assert result["chosen_component"] != "quote"


def test_visual_opportunity_shape_keys():
    text = 'O governador afirmou: "Vamos acelerar as obras da rodovia até dezembro."'
    result = detect_visual_opportunities(text, "https://g1.globo.com/x", "G1", block_index=2)
    assert "paragraph_text" in result
    assert "detected_opportunities" in result
    assert "chosen_component" in result
    assert result["block_index"] == 2
    for op in result["detected_opportunities"]:
        assert "opportunity_type" in op
        assert "score" in op
        assert "recommended_component" in op
        assert "recommended_variant" in op
