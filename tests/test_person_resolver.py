import unittest
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from person_resolver import resolve_person_for_text, get_figure_image_path, PERSON_CATALOG

class PersonResolverTests(unittest.TestCase):
    def test_detect_trump(self):
        text = "O presidente Donald Trump anunciou novas medidas econômicas."
        res = resolve_person_for_text(text, auto_download=False)
        self.assertIsNotNone(res)
        self.assertEqual(res["slug"], "donald-trump")
        self.assertEqual(res["name"], "Donald Trump")
        self.assertEqual(res["tag"], "PERSONAGEM EM FOCO")
        self.assertTrue(Path(res["photo_src"]).is_file())

    def test_detect_moraes(self):
        text = "A decisão monocrática de Alexandre de Moraes causou forte reação."
        res = resolve_person_for_text(text, auto_download=False)
        self.assertIsNotNone(res)
        self.assertEqual(res["slug"], "alexandre-de-moraes")
        self.assertEqual(res["name"], "Alexandre de Moraes")
        self.assertTrue(Path(res["photo_src"]).is_file())

    def test_detect_lula(self):
        text = "O presidente Lula discursou nesta manhã sobre a meta fiscal."
        res = resolve_person_for_text(text, auto_download=False)
        self.assertIsNotNone(res)
        self.assertEqual(res["slug"], "lula")
        self.assertTrue(Path(res["photo_src"]).is_file())

    def test_detect_haddad(self):
        text = "Fernando Haddad apresentou o novo pacote de ajuste tributário."
        res = resolve_person_for_text(text, auto_download=False)
        self.assertIsNotNone(res)
        self.assertEqual(res["slug"], "fernando-haddad")
        self.assertTrue(Path(res["photo_src"]).is_file())

    def test_detect_milei(self):
        text = "Javier Milei celebrou o superávit fiscal consecutivo na Argentina."
        res = resolve_person_for_text(text, auto_download=False)
        self.assertIsNotNone(res)
        self.assertEqual(res["slug"], "javier-milei")
        self.assertTrue(Path(res["photo_src"]).is_file())

    def test_detect_musk(self):
        text = "Elon Musk criticou duramente as exigências de censura na plataforma."
        res = resolve_person_for_text(text, auto_download=False)
        self.assertIsNotNone(res)
        self.assertEqual(res["slug"], "elon-musk")
        self.assertTrue(Path(res["photo_src"]).is_file())

    def test_detect_powell(self):
        text = "Jerome Powell indicou que os juros americanos permanecerão altos."
        res = resolve_person_for_text(text, auto_download=False)
        self.assertIsNotNone(res)
        self.assertEqual(res["slug"], "jerome-powell")
        self.assertTrue(Path(res["photo_src"]).is_file())

    def test_unrelated_text_returns_none(self):
        text = "A colisão frontal na rodovia BR-470 interditou o trânsito nesta tarde."
        res = resolve_person_for_text(text, auto_download=False)
        self.assertIsNone(res)

if __name__ == "__main__":
    unittest.main()
