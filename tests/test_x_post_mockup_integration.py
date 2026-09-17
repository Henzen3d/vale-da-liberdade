"""Testes de regressão: Integração do Card do X e padronização do mockup-browser.html."""
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
MOCKUP_DIR = ROOT / "references" / "youtube" / "mockup-browser"


def test_mockup_browser_files_exist_and_in_sync():
    browser_html = MOCKUP_DIR / "mockup-browser.html"
    brower_html = MOCKUP_DIR / "mockup-brower.html"

    assert browser_html.is_file(), "mockup-browser.html deve existir"
    assert brower_html.is_file(), "mockup-brower.html (compatibilidade) deve existir"

    content_browser = browser_html.read_text(encoding="utf-8")
    content_brower = brower_html.read_text(encoding="utf-8")

    # Verifica elementos essenciais do card do X em ambos
    for content in (content_browser, content_brower):
        assert 'id="xCard"' in content, "Elemento #xCard deve estar presente"
        assert ".bcard-x-post" in content, "Classe CSS .bcard-x-post deve estar presente"
        assert "transitionToX" in content, "Método transitionToX deve estar implementado no VDL_MOCKUP_ENGINE"
        assert '"xCard"' in content, "xCard deve estar registrado em _hideAllCards()"
        assert 'kind === "x-post"' in content, "update() deve rotear kind x-post para transitionToX"
        assert 'id="xMediaBox"' in content, "#xMediaBox deve existir para imagens de tweets"
        assert 'id="xLikeBtn"' in content, "#xLikeBtn deve existir para micro-animação de like"


def test_demo_broadcast_studio_points_to_browser_and_has_x_post():
    studio_html = (MOCKUP_DIR / "demo-broadcast-studio.html").read_text(encoding="utf-8")
    assert 'src="mockup-browser.html"' in studio_html, "iframe do studio deve apontar para mockup-browser.html"
    assert 'data-kind="x-post"' in studio_html, "Botão Modo 8 do switcher deve ter data-kind='x-post'"
    assert '"x-post": {' in studio_html, "Preset do x-post deve estar definido em DEMO_PRESETS"


def test_constants_mockup_html_resolution():
    from scripts.bm_video.constants import MOCKUP_HTML
    assert MOCKUP_HTML == "mockup-browser.html", "Constante oficial MOCKUP_HTML deve priorizar mockup-browser.html"


def test_build_mockup_update_payload_x_post():
    from scripts.bm_video.state import _build_mockup_update_payload

    beat = {
        "visual_component": "x-post",
        "url": "https://x.com/alexandre/status/1830689409823485952",
        "x_post": {
            "author_name": "Alexandre de Moraes",
            "handle": "@alexandre",
            "text": "STF em defesa da Constituição.",
            "media": "/shots/x-media-123.jpg",
        },
    }
    payload = _build_mockup_update_payload(beat)
    assert payload["kind"] == "x-post"
    assert payload["visual_component"] == "x-post"
    assert payload["xPost"]["author_name"] == "Alexandre de Moraes"
    assert payload["xPost"]["media"] == "/shots/x-media-123.jpg"


def test_build_scene_timeline_preserves_x_post_without_shot():
    from scripts.bm_scene_timeline import build_scene_timeline, SceneBeatV2

    episode = {
        "titulo": "Teste X Post",
        "abertura": [{"speaker": "Peter", "texto": "Abertura comentando a repercussão no X.", "fonte_url": "https://x.com/autor/status/123"}],
        "desenvolvimento": [{"speaker": "Peter", "texto": "Desenvolvimento do comentário sobre o tweet.", "fonte_url": "https://x.com/autor/status/123"}],
        "fechamento": [{"speaker": "Peter", "texto": "Fechamento."}],
    }
    scenes = [
        {
            "veiculo": "Post no X",
            "url": "https://x.com/autor/status/123",
            "kind": "x-post",
            "shot": None,
            "video": None,
            "x_post": {
                "author_name": "Autor Teste",
                "handle": "@autor",
                "text": "Texto do tweet",
                "likes": "150",
            },
        }
    ]
    beats = build_scene_timeline(episode, total_duration_s=60.0, scenes=scenes)
    assert len(beats) > 0
    x_beats = [b for b in beats if b.visual_component == "x-post" or b.kind == "x-post"]
    assert len(x_beats) > 0, "Deveria conter beats com componente x-post"
    assert x_beats[0].x_post is not None, "x_post deve ser preservado no SceneBeat"
    assert x_beats[0].x_post["author_name"] == "Autor Teste"

    # Teste em V2
    beats_v2 = build_scene_timeline(episode, total_duration_s=60.0, scenes=scenes, return_v2=True)
    assert len(beats_v2) > 0
    x_beats_v2 = [b for b in beats_v2 if b.visual_component == "x-post"]
    assert len(x_beats_v2) > 0
    assert x_beats_v2[0].x_post is not None, "x_post deve ser preservado no SceneBeatV2"
    legacy = x_beats_v2[0].to_legacy_beat()
    assert legacy.x_post is not None, "to_legacy_beat() deve transferir x_post"

# ============================================================
# MODELO 3 (Cinematic Prime 3D Glass) — Modo 8 renovado
# ============================================================

# Elementos estruturais do novo layout que devem existir no mockup
_MODELO3_DOM_MARKERS = [
    'id="xStageRoot"',           # camada raiz (diagonais + speaker + ambient)
    'class="diagonal-sublayer"',  # camada 1 do painel diagonal duplo
    'class="diagonal-main-shape"',  # camada 2 (painel branco)
    'id="xSpeakerBox"',           # bloco do speaker (quadrante sup. esquerdo)
    'id="xSpeakerAvatarImg"',     # foto do speaker
    'id="xSpeakerVerifiedBadge"',  # selo oficial de verificado
    'id="xSpeakerName"',
    'id="xSpeakerHandle"',
    'x-speaker-vip-badge',
    'x-ambient-light',
]


@pytest.mark.parametrize("marker", _MODELO3_DOM_MARKERS)
def test_modelo3_dom_markers_present(marker):
    """Cada elemento do layout Modelo 3 deve existir no mockup e no alias."""
    for name in ("mockup-browser.html", "mockup-brower.html"):
        content = (MOCKUP_DIR / name).read_text(encoding="utf-8")
        assert marker in content, f"[[REDACTED] deve existir em {name}"


def test_modelo3_css_geometry():
    """Geometria calibrada: card top:44 (centralizado entre topo Y:0 e LT Y:880), height 720px, mídia 350px, avatar 300px."""
    content = (MOCKUP_DIR / "mockup-browser.html").read_text(encoding="utf-8")
    css = content[content.index(".bcard-x-post {"):content.index(".x-header {")]
    assert "top: 44px;" in css, "card centralizado entre Y:0 e Lower Third Y:880 (top:44px)"
    assert "height: 720px;" in css, "card com altura fixa travada em 720px"
    assert "right: 44px;" in css, "card alinhado à direita (right:44px)"
    assert "rotateY(-1.8deg)" in css, "perspectiva 3D do card"
    assert "width: 1250px;" in css, "card ampliado 1250px"
    assert "z-index: 32;" in css, "card deve ficar à frente das diagonais"

    css_media = content[content.index(".x-media-box {"):content.index(".x-media-img {")]
    assert "height: 350px;" in css_media, "mídia do tweet calibrada com 350px"

    css_body = content[content.index(".x-body {"):content.index(".x-body strong {")]
    assert "font-size: 38px;" in css_body, "texto editorial base em 38px"
    assert ".bcard-x-post.is-text-only .x-body" in content, "regra para posts sem imagem"

    css_speaker = content[content.index(".x-speaker-avatar {"):content.index(".x-speaker-avatar img {")]
    assert "width: 300px;" in css_speaker, "avatar do speaker 300px"
    assert "height: 300px;" in css_speaker


@pytest.mark.parametrize("name", ["mockup-browser.html", "mockup-brower.html"])
def test_transition_to_x_populates_speaker(name):
    """transitionToX deve ler speaker_* do payload e popular o DOM do speaker."""
    content = (MOCKUP_DIR / name).read_text(encoding="utf-8")
    js = content[content.index("transitionToX(payload = {}) {"):]
    js = js[:js.index("_isValePlaceholderUrl")]
    for key in ("speaker_name", "speaker_handle", "speaker_avatar", "speaker_verified"):
        assert f"xp.{key}" in js, f"transitionToX deve ler {key} do payload"
    for el in ("xSpeakerName", "xSpeakerHandle", "xSpeakerAvatarImg",
               "xSpeakerVerifiedBadge", "xSpeakerAvatarFallback"):
        assert f'getElementById("{el}")' in js, f"transitionToX deve popular #{el}"
    # Ken Burns na mídia
    assert "mediaImg" in js and "scale: 1.05" in js, "Ken Burns suave na mídia"
    # Fallback: sem speaker secundário, usa o autor do tweet
    assert "|| author" in js, "speaker_name deve cair para o autor do tweet"


def test_build_payload_speaker_fallback_to_tweet_author():
    """Sem speaker secundário, o xPost enrichido usa o autor do tweet."""
    from scripts.bm_video.state import _build_mockup_update_payload

    beat = {
        "visual_component": "x-post",
        "url": "https://x.com/alexandre/status/1",
        "x_post": {
            "author_name": "Alexandre de Moraes",
            "handle": "@alexandre",
            "text": "Texto do tweet.",
            "avatar": "/shots/x-av-1.jpg",
            "verified": True,
        },
    }
    payload = _build_mockup_update_payload(beat)
    xp = payload["xPost"]
    assert xp["speaker_name"] == "Alexandre de Moraes"
    assert xp["speaker_handle"] == "@alexandre"
    assert xp["speaker_avatar"] == "/shots/x-av-1.jpg"
    assert xp["speaker_verified"] is True


def test_build_payload_speaker_secondary_preserved():
    """Speaker secundário explícito não é sobrescrito pelo autor do tweet."""
    from scripts.bm_video.state import _build_mockup_update_payload

    beat = {
        "visual_component": "x-post",
        "url": "https://x.com/alexandre/status/1",
        "x_post": {
            "author_name": "Alexandre de Moraes",
            "handle": "@alexandre",
            "text": "Texto.",
            "speaker_name": "Tim Kaine",
            "speaker_handle": "@timkaine",
            "speaker_avatar": "/shots/speaker.jpg",
            "speaker_verified": False,
        },
    }
    payload = _build_mockup_update_payload(beat)
    xp = payload["xPost"]
    assert xp["speaker_name"] == "Tim Kaine"
    assert xp["speaker_handle"] == "@timkaine"
    assert xp["speaker_avatar"] == "/shots/speaker.jpg"
    assert xp["speaker_verified"] is False


def test_build_payload_speaker_missing_author_defaults():
    """x_post vazio/parcial não quebra o enrich de speaker."""
    from scripts.bm_video.state import _build_mockup_update_payload

    payload = _build_mockup_update_payload({"visual_component": "x-post", "x_post": {}})
    xp = payload["xPost"]
    assert xp["speaker_name"] == "Autoridade"
    assert xp["speaker_verified"] is True


def test_translation_is_portuguese_detection():
    """Detecta corretamente se o texto é português ou língua estrangeira."""
    from scripts.bm_video.translation import is_portuguese

    assert is_portuguese("O STF reafirma o compromisso com a constituição brasileira.") is True
    assert is_portuguese("Decisão histórica do plenário nesta tarde em Brasília.") is True
    assert is_portuguese("Breaking: The Senate passes the new economic bill with 65 votes.") is False
    assert is_portuguese("Donald Trump announces new tariffs on foreign steel imports today.") is False
    assert is_portuguese("El presidente anunció nuevas medidas contra la inflación hoy.") is False


def test_translation_enrich_x_post_translates_foreign():
    """enrich_x_post_translation traduz tweet estrangeiro e preserva original."""
    from scripts.bm_video.translation import enrich_x_post_translation

    post_en = {
        "author_name": "Donald Trump",
        "handle": "@realDonaldTrump",
        "text": "Donald Trump announced new tariffs on steel and aluminum imports today.",
    }
    enriched = enrich_x_post_translation(post_en)
    assert enriched["is_translated"] is True
    assert enriched["original_text"] == "Donald Trump announced new tariffs on steel and aluminum imports today."
    assert "tarifas" in enriched["text"].lower() or "aço" in enriched["text"].lower()

    # Post em português não é alterado
    post_pt = {
        "author_name": "Lula",
        "handle": "@LulaOficial",
        "text": "O Brasil voltou a crescer com responsabilidade e justiça social.",
    }
    enriched_pt = enrich_x_post_translation(post_pt)
    assert enriched_pt["is_translated"] is False
    assert enriched_pt["text"] == "O Brasil voltou a crescer com responsabilidade e justiça social."


def test_transition_to_x_adaptive_typography_in_html():
    """transitionToX no HTML deve conter lógica para ampliar a fonte quando não houver imagem."""
    content = (MOCKUP_DIR / "mockup-browser.html").read_text(encoding="utf-8")
    assert "is-text-only" in content, "mockup deve alternar classe is-text-only"
    assert "bodyTextEl.style.fontSize" in content, "mockup deve definir fontSize dinamicamente"
    assert "56px" in content, "mockup deve ter escala ampliada para posts curtos"


def test_transition_to_x_html_unescape_and_link_cleaning():
    """HTML do mockup deve conter métodos _unescapeHtml e _cleanTweetText."""
    for filename in ("mockup-browser.html", "mockup-brower.html"):
        content = (MOCKUP_DIR / filename).read_text(encoding="utf-8")
        assert "_unescapeHtml(str)" in content, f"{filename} deve ter _unescapeHtml"
        assert "_cleanTweetText(str)" in content, f"{filename} deve ter _cleanTweetText"
        assert "pic." in content, f"{filename} deve limpar trailing pic.twitter.com"


def test_enrich_x_post_speaker_unescapes_entities_and_strips_photo_links():
    """_enrich_x_post_speaker deve desescapar &quot; e remover links de foto finais."""
    from scripts.bm_video.state import _enrich_x_post_speaker

    raw_post = {
        "author_name": "Paulo &quot;Figueiredo&quot;",
        "handle": "@pfigueiredo08",
        "text": "Preocupado com a &quot;narrativa da esquerda&quot;. pic.twitter.com/S3qahrylxi",
    }
    enriched = _enrich_x_post_speaker(raw_post)
    assert enriched["author_name"] == 'Paulo "Figueiredo"'
    assert enriched["speaker_name"] == 'Paulo "Figueiredo"'
    assert '&quot;' not in enriched["text"]
    assert '"narrativa da esquerda"' in enriched["text"]
    assert 'pic.twitter.com' not in enriched["text"]


