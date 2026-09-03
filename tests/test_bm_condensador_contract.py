import unittest
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from bm_condensador import (
    GEMINI_MODELS,
    load_config,
    build_prompt,
    count_words_in_roteiro,
    enforce_profanity_3min_rule,
)


class TestBMCondensadorContract(unittest.TestCase):
    def test_gemini_models_primary(self):
        """Garante que gemini-3.8-flash seja o modelo primário absoluto."""
        self.assertGreater(len(GEMINI_MODELS), 0)
        self.assertEqual(GEMINI_MODELS[0], "gemini-3.8-flash")
        self.assertIn("gemini-3.6-flash", GEMINI_MODELS)
        self.assertIn("gemini-3.5-flash-lite", GEMINI_MODELS)

    def test_config_word_limits(self):
        """Garante que a configuração padrão e carregada respeite o piso de 750 palavras."""
        cfg = load_config()
        self.assertGreaterEqual(cfg.get("min_word_count", 0), 750)
        self.assertGreaterEqual(cfg.get("target_word_count", 0), 820)
        self.assertGreaterEqual(cfg.get("max_word_count", 0), 900)

    def test_prompt_guidelines_and_rules(self):
        """Valida que o prompt injeta as regras de retórica, humor, ironia e os 3 minutos."""
        fake_raw = {
            "title": "Decisão polêmica em Brasília",
            "channel": "ANCAPSU",
            "url": "https://youtube.com/watch?v=12345678901",
            "transcript": "Transcrição simulada de teste sobre taxas e impostos.",
            "source_names": ["Gazeta do Povo"],
        }
        cfg = load_config()
        prompt = build_prompt(fake_raw, cfg, "")

        # Piso de 750 palavras
        self.assertIn("750 palavras", prompt)
        self.assertIn("PISO MÍNIMO ABSOLUTO", prompt)

        # Retórica, ironia e humor
        self.assertIn("perguntas retóricas", prompt)
        self.assertIn("ironia", prompt)
        self.assertIn("humor ácido", prompt)

        # Regra dos 3 minutos para termos fortes
        self.assertIn("3 MINUTOS", prompt)
        self.assertIn("merda", prompt)
        self.assertIn("LINGUAGEM 100% LIMPA", prompt)

    def test_profanity_3min_rule_enforcement(self):
        """Testa o guardrail de monetização dos 3 minutos (~480 palavras)."""
        # Montar um roteiro simulado onde 'merda' aparece antes e depois de 480 palavras
        words_chunk_100 = " ".join(["palavra"] * 100)
        
        data = {
            "abertura": [
                {"speaker": "Peter", "texto": f"Abertura inicial com uma merda dita aqui. {words_chunk_100}"}
            ],
            "desenvolvimento": [
                # 102 + 101 = 203 palavras acumuladas (< 480)
                {"speaker": "Peter", "texto": f"Outra merda acontecendo no governo. {words_chunk_100}"},
                # 203 + 100 = 303 palavras (< 480)
                {"speaker": "Peter", "texto": f"{words_chunk_100}"},
                # 303 + 100 = 403 palavras (< 480)
                {"speaker": "Peter", "texto": f"{words_chunk_100}"},
                # 403 + 100 = 503 palavras (ultrapassou 480 palavras! Agora está > 3 minutos)
                {"speaker": "Peter", "texto": f"{words_chunk_100}"},
                # Fala após 500 palavras: 'merda' DEVE ser preservada!
                {"speaker": "Peter", "texto": f"Isso aqui é uma merda completa que o burocrata fez. {words_chunk_100}"}
            ],
            "fechamento": [
                {"speaker": "Peter", "texto": "Fechamento contundente. Que merda de estado."}
            ]
        }

        sanitized = enforce_profanity_3min_rule(data, safe_words_threshold=480)

        # Na abertura (< 480 palavras), 'merda' foi convertida para 'porcaria'
        self.assertNotIn("merda", sanitized["abertura"][0]["texto"].lower())
        self.assertIn("porcaria", sanitized["abertura"][0]["texto"].lower())

        # No início do desenvolvimento (< 480 palavras), também convertida
        self.assertNotIn("merda", sanitized["desenvolvimento"][0]["texto"].lower())
        self.assertIn("porcaria", sanitized["desenvolvimento"][0]["texto"].lower())

        # Na fala do desenvolvimento após 480 palavras (> 3 minutos), 'merda' DEVE ser mantida!
        self.assertIn("merda", sanitized["desenvolvimento"][4]["texto"].lower())

        # No fechamento (> 3 minutos), 'merda' também deve ser mantida!
        self.assertIn("merda", sanitized["fechamento"][0]["texto"].lower())


if __name__ == "__main__":
    unittest.main()
