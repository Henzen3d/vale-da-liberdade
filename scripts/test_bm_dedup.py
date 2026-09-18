import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bm_dedup import normalize_title, check_video_duplicate


class TestBmDedup(unittest.TestCase):
    def test_normalize_title(self):
        self.assertEqual(
            normalize_title("LULA confisca CELULAR de VORCARO!"),
            "lula confisca celular de vorcaro",
        )
        self.assertEqual(
            normalize_title("Atenção: Novo Imposto &quot;Invisível&quot;"),
            "atencao novo imposto invisivel",
        )

    def test_exact_title_match_in_seen(self):
        seen = {
            "videos": {
                "abc12345678": {
                    "titulo": "LULA confisca CELULAR de VORCARO",
                }
            }
        }
        is_dup, reason = check_video_duplicate(
            "Lula confisca celular de Vorcaro",
            seen_videos=seen,
            current_video_id="xyz98765432",
        )
        self.assertTrue(is_dup)
        self.assertIn("já processado em seen_videos", reason)

    def test_exact_title_match_in_queue(self):
        seen = {"videos": {}}
        queue = [
            {
                "video_id": "q1234567890",
                "title": "STF decide sobre marco temporal",
            }
        ]
        is_dup, reason = check_video_duplicate(
            "stf decide sobre marco temporal",
            seen_videos=seen,
            queue=queue,
            current_video_id="other_video",
        )
        self.assertTrue(is_dup)
        self.assertIn("já existe na fila", reason)

    def test_self_video_id_ignored(self):
        seen = {
            "videos": {
                "same_id_123": {
                    "titulo": "Mesmo vídeo sendo revalidado",
                }
            }
        }
        is_dup, _ = check_video_duplicate(
            "Mesmo vídeo sendo revalidado",
            seen_videos=seen,
            current_video_id="same_id_123",
        )
        self.assertFalse(is_dup)

    def test_distinct_title_not_duplicate(self):
        seen = {
            "videos": {
                "v1": {"titulo": "Governo aumenta imposto sobre combustíveis"},
            }
        }
        is_dup, _ = check_video_duplicate(
            "Banco Central eleva taxa básica de juros",
            seen_videos=seen,
            current_video_id="v2",
        )
        self.assertFalse(is_dup)


if __name__ == "__main__":
    unittest.main()
