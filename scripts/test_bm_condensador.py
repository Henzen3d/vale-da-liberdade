# Testes do gate de duracao do condensador BM.
# Regride o episodio 82KsKJygHWA (21/09/2026): roteiro de 441 palavras foi
# publicado porque _trim_to_max aceitou um corte que desceu abaixo do piso
# minimo (750), abortando o gate de duracao.
import json
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bm_condensador import _trim_to_max, count_words_in_roteiro


def _roteiro(n_palavras: int) -> dict:
    """Monta um roteiro cuja contagem de palavras fica proxima de n_palavras."""
    frase = "O STF acumulou lambancas em um so dia provando que o monopolio da justica funciona como um balcao de interesses blindado contra qualquer fiscalizacao externa. "
    frase_n = len(frase.split())
    desenvolvimento = []
    total = 0
    alvo = max(n_palavras - 120, 0)  # abertura+fechamento somam ~120
    while total < alvo:
        desenvolvimento.append({"speaker": "Peter", "texto": frase})
        total += frase_n
    return {
        "abertura": [
            {"speaker": "Peter", "texto": frase},
            {"speaker": "Peter", "texto": frase},
        ],
        "desenvolvimento": desenvolvimento,
        "fechamento": [
            {"speaker": "Peter", "texto": frase},
            {"speaker": "Peter", "texto": "Eu sou Peter Albuquerque para o Web Jornal Vale da Liberdade. Ate a proxima."},
        ],
    }


class TrimToMaxTestCase(unittest.TestCase):

    def test_corte_abaixo_do_piso_e_rejeitado(self):
        # Caso real: LLM devolveu >920 palavras, o corte encolheu para 441.
        # Antes do fix, 441 era aceito (441 < words) e o gate de duracao
        # virava apenas um aviso, publicando um audio de ~2.5 min.
        data = _roteiro(1200)
        words = count_words_in_roteiro(data)
        self.assertGreater(words, 920)

        cortado = _roteiro(441)
        cortado_words = count_words_in_roteiro(cortado)
        self.assertLess(cortado_words, 750)

        with patch("bm_condensador._call_llm", return_value=json.dumps(cortado)):
            out, out_words = _trim_to_max(data, words, 830, 920, 750)

        # Nao aceita o corte: mantem o original acima do piso.
        self.assertEqual(out, data)
        self.assertEqual(out_words, words)

    def test_corte_dentro_do_intervalo_e_aceito(self):
        data = _roteiro(1200)
        words = count_words_in_roteiro(data)

        cortado = _roteiro(800)
        cortado_words = count_words_in_roteiro(cortado)
        self.assertGreaterEqual(cortado_words, 750)
        self.assertLess(cortado_words, words)

        with patch("bm_condensador._call_llm", return_value=json.dumps(cortado)):
            out, out_words = _trim_to_max(data, words, 830, 920, 750)

        self.assertEqual(out, cortado)
        self.assertEqual(out_words, cortado_words)

    def test_corte_igual_ao_original_mantem_o_original(self):
        data = _roteiro(900)
        words = count_words_in_roteiro(data)
        with patch("bm_condensador._call_llm", return_value=json.dumps(data)):
            out, out_words = _trim_to_max(data, words, 830, 920, 750)
        self.assertEqual(out, data)
        self.assertEqual(out_words, words)

    def test_falha_do_llm_mantem_o_original(self):
        data = _roteiro(1200)
        words = count_words_in_roteiro(data)

        def _boom(_prompt):
            raise RuntimeError("503 UNAVAILABLE")

        with patch("bm_condensador._call_llm", side_effect=_boom):
            out, out_words = _trim_to_max(data, words, 830, 920, 750)
        self.assertEqual(out, data)
        self.assertEqual(out_words, words)


if __name__ == "__main__":
    unittest.main()
