from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from bm_scene_timeline import SceneBeat, SceneBeatV2, build_scene_timeline  # noqa: E402


def test_scene_beat_v2_construction():
    beat = SceneBeatV2(
        t0=0.0,
        t1=14.2,
        semantic_role="apresentacao_fato",
        visual_component="source",
        visual_variant="portal_clean",
        visual_payload={"headline": "Obras na BR-470"},
        url="https://example.com/noticia",
        veiculo="G1",
        shot="src-00.png",
    )
    assert beat.t0 == 0.0
    assert beat.t1 == 14.2
    assert beat.duration == 14.2
    assert beat.semantic_role == "apresentacao_fato"
    assert beat.visual_component == "source"
    assert beat.visual_variant == "portal_clean"
    assert beat.visual_payload["headline"] == "Obras na BR-470"
    assert beat.url == "https://example.com/noticia"
    assert beat.veiculo == "G1"
    assert beat.shot == "src-00.png"
    assert beat.video is None
    assert beat.broll_file is None


def test_scene_beat_v2_to_dict_json_serializable():
    beat = SceneBeatV2(
        t0=1.0,
        t1=5.5,
        semantic_role="declaracao_forte",
        visual_component="quote",
        visual_variant="card_gold",
        visual_payload={"quote_text": "Nao havera aumento.", "author_name": "Prefeito"},
        url="https://example.com",
        veiculo="G1",
    )
    data = beat.to_dict()
    assert isinstance(data, dict)
    assert "duration" not in data  # property, not field
    assert data["semantic_role"] == "declaracao_forte"
    assert data["visual_component"] == "quote"
    assert data["visual_payload"]["author_name"] == "Prefeito"
    encoded = json.dumps(data, ensure_ascii=False)
    decoded = json.loads(encoded)
    assert decoded["t0"] == 1.0
    assert decoded["t1"] == 5.5
    assert decoded["visual_variant"] == "card_gold"


def test_to_legacy_beat_maps_known_components():
    v2 = SceneBeatV2(
        t0=2.0,
        t1=10.0,
        semantic_role="repercussao_social",
        visual_component="x-post",
        visual_variant="",
        visual_payload={},
        url="https://x.com/status/1",
        veiculo="X",
        shot="x.png",
        video=None,
        broll_file=None,
    )
    legacy = v2.to_legacy_beat()
    assert isinstance(legacy, SceneBeat)
    assert legacy.t0 == 2.0
    assert legacy.t1 == 10.0
    assert legacy.kind == "x-post"
    assert legacy.url == "https://x.com/status/1"
    assert legacy.veiculo == "X"
    assert legacy.shot == "x.png"


def test_to_legacy_beat_maps_new_components_to_source():
    v2 = SceneBeatV2(
        t0=0.0,
        t1=8.0,
        semantic_role="impacto_economico",
        visual_component="chart",
        visual_variant="stat_counter",
        visual_payload={"metric_value": 10},
    )
    legacy = v2.to_legacy_beat()
    assert legacy.kind == "source"
    assert legacy.url == ""
    assert legacy.veiculo == ""


def test_from_legacy_and_round_trip():
    legacy = SceneBeat(
        t0=3.0,
        t1=12.0,
        url="https://news.example/a",
        veiculo="Folha",
        kind="source",
        shot="a.png",
        video="a.mp4",
        broll_file=None,
        x_post=None,
    )
    v2 = SceneBeatV2.from_legacy(legacy)
    assert v2.semantic_role == "apresentacao_fato"
    assert v2.visual_component == "source"
    assert v2.visual_variant == ""
    assert v2.visual_payload == {}
    assert v2.url == legacy.url
    assert v2.veiculo == legacy.veiculo
    assert v2.shot == legacy.shot
    assert v2.video == legacy.video
    assert abs(v2.duration - 9.0) < 1e-9

    back = v2.to_legacy_beat()
    assert back.t0 == legacy.t0
    assert back.t1 == legacy.t1
    assert back.url == legacy.url
    assert back.veiculo == legacy.veiculo
    assert back.kind == "source"
    assert back.shot == legacy.shot
    assert back.video == legacy.video


def test_from_legacy_infers_broll_and_xpost():
    broll = SceneBeat(t0=0, t1=1.2, url="", veiculo="Transicao", kind="broll", broll_file="clip.mp4")
    v_b = SceneBeatV2.from_legacy(broll)
    assert v_b.semantic_role == "transicao_broll"
    assert v_b.visual_component == "broll"
    assert v_b.broll_file == "clip.mp4"

    xp = SceneBeat(t0=1, t1=5, url="https://x.com/1", veiculo="X", kind="x-post")
    v_x = SceneBeatV2.from_legacy(xp)
    assert v_x.semantic_role == "repercussao_social"
    assert v_x.visual_component == "x-post"


def test_from_legacy_overrides():
    legacy = SceneBeat(t0=0, t1=5, url="u", veiculo="V", kind="source")
    v2 = SceneBeatV2.from_legacy(
        legacy,
        semantic_role="declaracao_forte",
        visual_component="quote",
        visual_variant="card_gold",
        visual_payload={"quote_text": "oi"},
    )
    assert v2.semantic_role == "declaracao_forte"
    assert v2.visual_component == "quote"
    assert v2.visual_variant == "card_gold"
    assert v2.visual_payload["quote_text"] == "oi"


def test_legacy_scenebeat_and_build_scene_timeline_still_work():
    """Garante que SceneBeat legado e build_scene_timeline seguem intactos."""
    episode = {
        "titulo": "Teste",
        "abertura": [{"texto": "Abertura curta do episodio de hoje.", "fonte_url": "https://a.example"}],
        "desenvolvimento": [{"texto": "Desenvolvimento com varias palavras para preencher tempo.", "fonte_url": "https://b.example"}],
        "fechamento": [{"texto": "Fechamento final.", "fonte_url": ""}],
    }
    scenes = [
        {"url": "https://a.example", "veiculo": "A", "shot": None, "video": None},
        {"url": "https://b.example", "veiculo": "B", "shot": None, "video": None},
    ]
    beats = build_scene_timeline(episode, total_duration_s=60.0, scenes=scenes)
    assert isinstance(beats, list)
    assert len(beats) >= 1
    assert all(isinstance(b, SceneBeat) for b in beats)
    assert beats[0].t0 == 0.0
    assert beats[-1].t1 == 60.0
