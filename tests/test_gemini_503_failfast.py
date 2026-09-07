#!/usr/bin/env python3
"""Teste de validação: Erro 503 Server Overload não varre o anel de chaves no GeminiMultiClient."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import gemini_client as gc


class TestGemini503FailFast(unittest.TestCase):
    def test_server_overload_detection(self):
        msg = "503 UNAVAILABLE. {'error': {'code': 503, 'message': 'This model is currently experiencing high demand.'}}"
        self.assertTrue(gc._is_server_overload(msg))
        self.assertFalse(gc._is_daily_quota_error(msg))

    def test_multiclient_raises_503_without_rotating_all_keys(self):
        """Em caso de 503, MultiClient deve levantar erro imediatamente sem tentar as outras chaves."""
        keys = ["TEST_KEY_1", "TEST_KEY_2", "TEST_KEY_3"]
        multi = gc.GeminiMultiClient(keys)

        mock_err = RuntimeError("503 UNAVAILABLE: This model is currently experiencing high demand.")
        call_count = 0

        def fake_generate(model, contents, **kwargs):
            nonlocal call_count
            call_count += 1
            raise mock_err

        for c in multi._clients:
            c.generate_content = MagicMock(side_effect=fake_generate)

        with self.assertRaises(RuntimeError) as ctx:
            multi.generate_content("gemini-3.5-flash-lite", "teste")

        self.assertIn("503", str(ctx.exception))
        # Deve ter tentado apenas 1 chave (call_count == 1), e NÃO as 3 chaves!
        self.assertEqual(call_count, 1)

    def test_multiclient_rotates_on_429_rpd(self):
        """Em caso de RPD esgotado, MultiClient DEVE rotacionar para a próxima chave."""
        keys = ["TEST_KEY_1", "TEST_KEY_2"]
        multi = gc.GeminiMultiClient(keys)

        call_count = 0
        def fake_generate(model, contents, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Limite diário atingido (RPD de 500) para o modelo gemini-3.5-flash-lite.")
            mock_resp = MagicMock()
            mock_resp.text = "Sucesso na chave 2"
            return mock_resp

        for c in multi._clients:
            c.generate_content = MagicMock(side_effect=fake_generate)

        resp = multi.generate_content("gemini-3.5-flash-lite", "teste")
        self.assertEqual(resp.text, "Sucesso na chave 2")
        self.assertEqual(call_count, 2)


if __name__ == "__main__":
    unittest.main()
