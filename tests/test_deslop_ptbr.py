import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from deslop_ptbr import HOUSE_SKIP, PROMPT_BLOCK, audit_text, warnings_for_markdown  # noqa: E402
from generate_script import build_script_prompt  # noqa: E402
from validate_naturalidade import validate_naturalidade  # noqa: E402
from bm_condensador import build_prompt, load_config  # noqa: E402


class TestDeslopPtbr(unittest.TestCase):
    def test_flags_gerundismo_sac(self):
        hits = audit_text("Vou estar enviando o dossiê para validação ainda hoje.")
        ids = {h["regra_id"] for h in hits}
        self.assertIn("W1", ids)

    def test_skips_house_rhetorical_and_olha_so(self):
        text = (
            "Olha só: setenta metros de fiação. "
            "Você já se perguntou por que a fiscalização some?\n"
            "A verdade é que o talude não foi olhado."
        )
        hits = audit_text(text)
        ids = {h["regra_id"] for h in hits}
        self.assertTrue(ids.isdisjoint(HOUSE_SKIP))

    def test_warnings_never_critical(self):
        lines = warnings_for_markdown(
            "No cenário atual, vamos estar enviando o recado, destarte."
        )
        self.assertTrue(lines)
        self.assertTrue(all(l.startswith("⚠️") for l in lines))
        self.assertFalse(any(l.startswith("❌") for l in lines))

    def test_daily_prompt_has_deslop_and_keeps_7_1(self):
        prompt = build_script_prompt("2026-09-17", {"quadros": {}})
        self.assertIn("DESLOP PT-BR", prompt)
        self.assertIn("7.1", prompt)
        self.assertIn("pergunta retórica", prompt.lower())

    def test_bm_prompt_has_deslop_and_keeps_rhetoric(self):
        fake_raw = {
            "title": "Decisão polêmica em Brasília",
            "channel": "ANCAPSU",
            "url": "https://youtube.com/watch?v=12345678901",
            "transcript": "Transcrição simulada de teste sobre taxas e impostos.",
            "source_names": ["Gazeta do Povo"],
        }
        prompt = build_prompt(fake_raw, load_config(), "")
        self.assertIn("DESLOP PT-BR", prompt)
        self.assertIn("perguntas retóricas", prompt)
        self.assertIn("ironia", prompt)

    def test_naturalidade_episode_no_new_critical_from_deslop(self):
        path = PROJECT_ROOT / "episodes" / "2026-09-17.md"
        if not path.is_file():
            self.skipTest("episódio do dia ausente")
        text = path.read_text(encoding="utf-8")
        issues = validate_naturalidade(text)
        deslop_crit = [i for i in issues if i.startswith("❌") and "Deslop" in i]
        self.assertEqual(deslop_crit, [])


if __name__ == "__main__":
    unittest.main()
