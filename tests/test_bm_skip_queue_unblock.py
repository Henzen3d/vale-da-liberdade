#!/usr/bin/env python3
"""Testes de desbloqueio da fila BM quando há vídeos com _skip_video_reason."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import pytest

from bm_video import cli


def test_process_one_auto_blocks_skipped_video(tmp_path: Path):
    fake_state_file = tmp_path / "videos_published.json"
    fake_state_file.write_text(json.dumps({"videos": {}, "blocked": {}}), encoding="utf-8")

    episode_data = {
        "video_id": "test123",
        "_skip_video_reason": "duração insuficiente: 712 palavras < 750",
    }

    with patch("bm_video.cli.load_episode", return_value=episode_data), \
         patch("bm_video.cli.load_state", return_value=json.loads(fake_state_file.read_text(encoding="utf-8"))), \
         patch("bm_video.cli.save_state") as mock_save:
        res = cli.process_one("test123", upload=False, privacy="unlisted", dry_run=True, force=False)
        assert res.get("skipped") is True
        assert "712 palavras" in res.get("reason", "")
        assert mock_save.called
        saved_state = mock_save.call_args[0][0]
        assert "test123" in saved_state["blocked"]
        assert "712 palavras" in saved_state["blocked"]["test123"]["motivo"]


def test_main_does_not_consume_max_quota_on_skipped_video():
    with patch("bm_video.cli.pending_ids", return_value=["vid_skipped", "vid_ready"]), \
         patch("bm_video.cli.process_one") as mock_process:
        
        # Primeiro vídeo é pulado, segundo vídeo tem sucesso
        mock_process.side_effect = [
            {"video_id": "vid_skipped", "skipped": True, "reason": "duração insuficiente"},
            {"video_id": "vid_ready", "skipped": False, "title": "Vídeo Sucesso"},
        ]

        test_args = ["bm_video.py", "--pending", "--max", "1", "--dry-run"]
        with patch("sys.argv", test_args):
            exit_code = cli.main()
            assert exit_code == 0
            assert mock_process.call_count == 2
            # Garante que ambos foram chamados porque o primeiro foi pulado e não gastou a cota
            assert mock_process.call_args_list[0][0][0] == "vid_skipped"
            assert mock_process.call_args_list[1][0][0] == "vid_ready"
