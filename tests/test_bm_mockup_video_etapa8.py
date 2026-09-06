#!/usr/bin/env python3
"""Unit tests Etapa 8 — payload builder + last_videos helper (bm_mockup_video)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from bm_scene_timeline import SceneBeat, SceneBeatV2  # noqa: E402
import bm_mockup_video as bm  # noqa: E402


def test_normalize_legacy_scenebeat_to_v2():
    legacy = SceneBeat(
        t0=0.0,
        t1=10.0,
        url="https://example.com/a",
        veiculo="G1",
        kind="source",
        shot="src-00.png",
    )
    out = bm._normalize_beat_v2(legacy)
    assert out["visual_component"] == "source"
    assert out["kind"] == "source"
    assert out["shot"] == "src-00.png"
    assert isinstance(out.get("visual_payload"), dict)
    assert out["url"] == "https://example.com/a"


def test_normalize_legacy_dict_xpost():
    d = {
        "t0": 1.0,
        "t1": 5.0,
        "url": "https://x.com/1",
        "veiculo": "X",
        "kind": "x-post",
        "x_post": {"handle": "@foo", "text": "oi"},
    }
    out = bm._normalize_beat_v2(d)
    assert out["visual_component"] == "x-post"
    assert out["x_post"]["handle"] == "@foo"


def test_normalize_scenebeat_v2_passthrough():
    v2 = SceneBeatV2(
        t0=2.0,
        t1=8.0,
        semantic_role="declaracao_forte",
        visual_component="quote",
        visual_variant="card_gold",
        visual_payload={"quote_text": "Sem aumento.", "author_name": "Prefeito"},
        url="https://example.com",
        veiculo="G1",
    )
    out = bm._normalize_beat_v2(v2)
    assert out["visual_component"] == "quote"
    assert out["kind"] == "quote"
    assert out["visual_payload"]["author_name"] == "Prefeito"
    assert out["visual_variant"] == "card_gold"


def test_build_mockup_update_payload_quote():
    beat = {
        "visual_component": "quote",
        "visual_variant": "card_gold",
        "visual_payload": {
            "quote_text": "Frase.",
            "author_name": "Autor",
        },
        "url": "https://example.com/n",
        "shot": None,
        "video": None,
    }
    payload = bm._build_mockup_update_payload(beat)
    assert payload["kind"] == "quote"
    assert payload["visual_component"] == "quote"
    assert payload["visual_variant"] == "card_gold"
    assert payload["visual_payload"]["quote_text"] == "Frase."
    assert payload["url"] == "https://example.com/n"
    assert "pageImage" in payload
    assert "pageVideo" in payload


def test_build_mockup_update_payload_broll():
    beat = {
        "visual_component": "broll",
        "kind": "broll",
        "broll_file": "clip a.mp4",
        "url": "https://news.mob.tec.br",
        "visual_payload": {},
        "visual_variant": "",
    }
    payload = bm._build_mockup_update_payload(beat)
    assert payload["kind"] == "broll"
    assert payload["pageVideo"].startswith("/broll/")
    assert "clip" in payload["pageVideo"]


def test_dominant_style():
    assert bm._dominant_style_from_components(["source", "source", "quote"]) == "standard_source"
    assert bm._dominant_style_from_components(["quote", "quote", "source"]) == "quote"
    assert bm._dominant_style_from_components([]) == "standard_source"


def test_append_last_video(tmp_path, monkeypatch):
    target = tmp_path / "last_videos.json"
    monkeypatch.setattr(bm, "LAST_VIDEOS_PATH", target)

    beats = [
        SceneBeat(t0=0, t1=5, url="u", veiculo="G1", kind="source"),
        SceneBeatV2(
            t0=5, t1=10,
            semantic_role="declaracao_forte",
            visual_component="quote",
            visual_variant="card_gold",
            visual_payload={"quote_text": "x"},
        ),
    ]
    bm.append_last_video("vid_a", "2026-09-06", beats)
    data = json.loads(target.read_text(encoding="utf-8"))
    assert "history" in data
    assert data["history"][-1]["video_id"] == "vid_a"
    assert data["history"][-1]["date"] == "2026-09-06"
    assert "source" in data["history"][-1]["components_used"]
    assert "quote" in data["history"][-1]["components_used"]

    # upsert same id
    bm.append_last_video("vid_a", "2026-09-06", beats)
    data2 = json.loads(target.read_text(encoding="utf-8"))
    assert sum(1 for h in data2["history"] if h["video_id"] == "vid_a") == 1

    # append another
    bm.append_last_video("vid_b", "2026-09-05", [beats[0]])
    data3 = json.loads(target.read_text(encoding="utf-8"))
    assert [h["video_id"] for h in data3["history"]] == ["vid_a", "vid_b"]


def test_normalize_legacy_dict_kind_quote_promotes_component():
    """kind=quote em dict legado deve virar visual_component=quote (nao source)."""
    d = {
        "t0": 0.0,
        "t1": 6.0,
        "url": "https://example.com",
        "veiculo": "G1",
        "kind": "quote",
        "quote_text": "ignored-top-level",
    }
    out = bm._normalize_beat_v2(d)
    assert out["visual_component"] == "quote"
    assert out["kind"] == "quote"
    assert out["semantic_role"] == "declaracao_forte"


def test_safe_mockup_update_resilience():
    class DummyPageOk:
        def __init__(self):
            self.called = False
            self.last_payload = None

        def evaluate(self, script, payload):
            self.called = True
            self.last_payload = payload

    dummy = DummyPageOk()
    bm._safe_mockup_update(dummy, {"kind": "quote", "visual_component": "quote"}, label="test_ok")
    assert dummy.called is True
    assert dummy.last_payload["visual_component"] == "quote"

    class DummyPageFail:
        def evaluate(self, script, payload):
            raise RuntimeError("Browser desconectado")

    # Não deve levantar exceção
    bm._safe_mockup_update(DummyPageFail(), {"kind": "quote"}, label="test_fail")


def test_build_mockup_update_payload_document():
    v2_doc = {
        "visual_component": "document",
        "visual_variant": "doc_stf",
        "visual_payload": {
            "doc_type": "sentenca",
            "case_number": "PROC-12345",
            "doc_institution": "STF",
        },
        "url": "https://stf.jus.br",
        "shot": "stf.png",
    }
    payload = bm._build_mockup_update_payload(v2_doc)
    assert payload["kind"] == "document"
    assert payload["visual_component"] == "document"
    assert payload["visual_variant"] == "doc_stf"
    assert payload["visual_payload"]["case_number"] == "PROC-12345"
    assert payload["pageImage"] == "/shots/stf.png"

