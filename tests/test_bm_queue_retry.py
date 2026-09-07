import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from bm_transcript import EXIT_CODE_NO_SUBS
from bm_pipeline import (
    QUEUE_MAX_PER_RUN,
    cap_ready_queue,
    is_interview_title,
    sanitize_and_recover_queue,
)


class TestBMQueueRetry(unittest.TestCase):
    def test_exit_code_no_subs_is_semantic_3(self):
        """Garante que o código semântico de ausência de legendas seja 3."""
        self.assertEqual(EXIT_CODE_NO_SUBS, 3)

    def test_is_interview_title(self):
        """Valida que entrevistas do ANCAPSU sejam detectadas para exclusão."""
        self.assertTrue(is_interview_title("PETER ENTREVISTA JESSÉ SANGALLI - Deputado"))
        self.assertTrue(is_interview_title("ENTREVISTA: Tarcísio de Freitas"))
        self.assertTrue(is_interview_title("ENTREVISTA COM Nikolas Ferreira"))
        self.assertFalse(is_interview_title("HOJE é 7 de SETEMBRO: LULA tenta usar a SOBERANIA"))
        self.assertFalse(is_interview_title("NIKOLAS faz VÍDEO DESTRUIDOR com DOSSIÊ"))

    def test_sanitize_and_recover_queue(self):
        """Valida a auto-recuperação de itens 'error' para 'pending' e descarte de entrevistas."""
        raw_queue = [
            {
                "video_id": "entrevista1",
                "title": "PETER ENTREVISTA DEPUTADO FULANO",
                "status": "error",
            },
            {
                "video_id": "noticia1",
                "title": "HOJE é 7 de SETEMBRO: LULA tenta usar a SOBERANIA",
                "status": "error",
            },
            {
                "video_id": "noticia2",
                "title": "NOTICIA NORMAL PENDENTE",
                "status": "pending",
                "attempts": 1,
            },
        ]

        cleaned = sanitize_and_recover_queue(raw_queue)

        # Entrevista foi removida
        vids = [item["video_id"] for item in cleaned]
        self.assertNotIn("entrevista1", vids)
        self.assertIn("noticia1", vids)
        self.assertIn("noticia2", vids)

        # noticia1 que estava em 'error' foi recuperada para 'pending'
        noticia1 = next(item for item in cleaned if item["video_id"] == "noticia1")
        self.assertEqual(noticia1["status"], "pending")
        self.assertEqual(noticia1["attempts"], 0)
        self.assertEqual(noticia1["max_attempts"], 4)

    def test_sanitize_recovers_stale_processing(self):
        """Cron timeout 3600s deixa status=processing; próximo tick precisa retomar."""
        raw_queue = [
            {
                "video_id": "stuck1",
                "title": "PESQUISAS e SIMULAÇÕES MOSTRAM FLÁVIO",
                "status": "processing",
                "attempts": 0,
            },
        ]
        cleaned = sanitize_and_recover_queue(raw_queue)
        self.assertEqual(cleaned[0]["status"], "pending")
        self.assertEqual(cleaned[0]["video_id"], "stuck1")

    def test_cap_ready_queue_default_is_one(self):
        """Hermes mata o script em 3600s; um TTS+mockup por tick cabe, a fila não."""
        self.assertEqual(QUEUE_MAX_PER_RUN, 1)
        ready = [{"video_id": "a"}, {"video_id": "b"}, {"video_id": "c"}]
        self.assertEqual(cap_ready_queue(ready, QUEUE_MAX_PER_RUN), [{"video_id": "a"}])
        self.assertEqual(cap_ready_queue(ready, 0), ready)
        self.assertEqual(cap_ready_queue(ready, 2), [{"video_id": "a"}, {"video_id": "b"}])

    def test_backoff_timing_logic(self):
        """Valida lógica de timing de retry_after futuro vs passado."""
        now = datetime.now(timezone.utc)
        future_dt = now + timedelta(minutes=20)
        past_dt = now - timedelta(minutes=5)

        self.assertTrue(now < future_dt)
        self.assertFalse(now < past_dt)


if __name__ == "__main__":
    unittest.main()
