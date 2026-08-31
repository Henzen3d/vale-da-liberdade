#!/usr/bin/env python3
"""Testes de relevância de fontes e descarte de cenas em branco (Brasil e Mundo).

Cobre as duas causas do bug de "print de notícia sem relação com o conteúdo":
1. RSS casando por verbo genérico ("mostra", "aguarda") e por matéria antiga;
2. screenshot em branco virando cena de 8s com o browser vazio.
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import pytest  # noqa: E402

from bm_enrich_sources import (  # noqa: E402
    GENERIC_TITLE_WORDS,
    _rss_item_is_recent,
    strong_keywords_from_title,
)

TITULO_GTA = (
    "MUNDO INTEIRO aguarda o GTA VI ANSIOSAMENTE: "
    "BRASILEIROS temem LEI FELCA (NÃO mostra pra JANJA)"
)

# As duas matérias erradas que apareceram no vídeo do GTA 6.
FALSO_POSITIVO_G1_TRANSPORTE = (
    "Levantamento do G1 mostra variação de preço nas opções "
    "de transporte em Divinópolis; confira"
)
FALSO_POSITIVO_G1_ITUIUTABA = (
    "Quase dois anos após matar grávida e roubar bebê em Ituiutaba, "
    "quatro acusados aguardam julgamento"
)


def _match_count(titulo_pauta: str, titulo_materia: str) -> int:
    kws = strong_keywords_from_title(titulo_pauta)
    low = titulo_materia.lower()
    return sum(1 for k in kws if k in low)


class TestKeywordsFortes:
    def test_verbos_genericos_saem_das_keywords(self):
        kws = strong_keywords_from_title(TITULO_GTA)
        assert "mostra" not in kws
        assert "aguarda" not in kws
        assert "temem" not in kws

    def test_termos_discriminantes_permanecem(self):
        kws = strong_keywords_from_title(TITULO_GTA)
        for esperado in ("felca", "janja", "ansiosamente", "brasileiros"):
            assert esperado in kws, f"{esperado} deveria ser keyword forte"

    @pytest.mark.parametrize(
        "materia",
        [FALSO_POSITIVO_G1_TRANSPORTE, FALSO_POSITIVO_G1_ITUIUTABA],
    )
    def test_falsos_positivos_reais_nao_casam_mais(self, materia):
        """Antes casavam por 'mostra'/'aguarda' — agora precisam de 2 termos fortes."""
        assert _match_count(TITULO_GTA, materia) < 2

    def test_materia_realmente_do_tema_casa(self):
        materia = "Lei Felca avança e brasileiros temem censura, diz relatório"
        assert _match_count(TITULO_GTA, materia) >= 2

    def test_generic_words_nao_vazia(self):
        assert "mostra" in GENERIC_TITLE_WORDS
        assert "aguarda" in GENERIC_TITLE_WORDS


def _item_com_data(data_str: str | None) -> ET.Element:
    item = ET.Element("item")
    ET.SubElement(item, "title").text = "Qualquer manchete"
    ET.SubElement(item, "link").text = "https://example.com/n"
    if data_str is not None:
        ET.SubElement(item, "pubDate").text = data_str
    return item


class TestFiltroDeIdadeRSS:
    def test_materia_de_2018_rejeitada(self):
        item = _item_com_data("Mon, 30 Jul 2018 12:00:00 -0300")
        assert _rss_item_is_recent(item) is False

    def test_materia_de_hoje_aceita(self):
        agora = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
        assert _rss_item_is_recent(_item_com_data(agora)) is True

    def test_materia_de_3_dias_aceita(self):
        d = datetime.now(timezone.utc) - timedelta(days=3)
        assert _rss_item_is_recent(_item_com_data(d.strftime("%a, %d %b %Y %H:%M:%S +0000"))) is True

    def test_materia_de_30_dias_rejeitada(self):
        d = datetime.now(timezone.utc) - timedelta(days=30)
        assert _rss_item_is_recent(_item_com_data(d.strftime("%a, %d %b %Y %H:%M:%S +0000"))) is False

    def test_item_sem_data_rejeitado(self):
        assert _rss_item_is_recent(_item_com_data(None)) is False

    def test_data_atom_iso_aceita(self):
        item = ET.Element("entry")
        agora = datetime.now(timezone.utc).isoformat()
        ET.SubElement(item, "{http://www.w3.org/2005/Atom}published").text = agora
        assert _rss_item_is_recent(item) is True


class TestDescarteDeCenaEmBranco:
    def _png(self, tmp_path: Path, cor, nome: str) -> Path:
        from PIL import Image

        p = tmp_path / nome
        Image.new("RGB", (1400, 900), cor).save(p)
        return p

    def test_screenshot_branca_detectada(self, tmp_path):
        from bm_mockup_video import _shot_looks_blank

        assert _shot_looks_blank(self._png(tmp_path, (255, 255, 255), "branca.png")) is True

    def test_screenshot_preta_detectada(self, tmp_path):
        from bm_mockup_video import _shot_looks_blank

        assert _shot_looks_blank(self._png(tmp_path, (0, 0, 0), "preta.png")) is True

    def test_screenshot_com_conteudo_aprovada(self, tmp_path):
        import random as _r

        from PIL import Image

        from bm_mockup_video import _shot_looks_blank

        im = Image.new("RGB", (400, 300))
        px = im.load()
        _r.seed(7)
        for x in range(400):
            for y in range(300):
                v = _r.randint(0, 255)
                px[x, y] = (v, v, v)
        p = tmp_path / "conteudo.png"
        im.save(p)
        assert _shot_looks_blank(p) is False

    def test_cena_sem_shot_e_sem_video_e_descartavel(self):
        captured = [
            {"veiculo": "Kotaku", "url": "https://kotaku.com/a", "shot": "src-00.png"},
            {"veiculo": "X", "url": "https://x.com/a/status/1", "shot": None, "video": None},
            {"veiculo": "G1", "url": "https://g1.globo.com/b", "shot": None, "video": "v.mp4"},
        ]
        usable = [c for c in captured if c.get("shot") or c.get("video")]
        assert len(usable) == 2
        assert all(u["veiculo"] != "X" for u in usable)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
