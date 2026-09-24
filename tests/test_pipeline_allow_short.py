#!/usr/bin/env python3
"""Testes para o comportamento de allow_short_audio em cmd_validate e pipeline."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

for mod in ["news_collector", "ai_news_filter", "generate_script", "dotenv"]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import pytest
import pipeline


def test_cmd_validate_blocks_short_script_without_flag(tmp_path: Path):
    fake_episodes_dir = tmp_path / "episodes"
    fake_episodes_dir.mkdir(parents=True)
    fake_md = fake_episodes_dir / "2026-09-24.md"
    fake_md.write_text("texto qualquer curto", encoding="utf-8")

    fake_issues = [
        "❌ Roteiro curto demais para áudio (500 palavras) — mínimo 1500",
    ]

    with patch("pipeline.EPISODES_DIR", fake_episodes_dir), \
         patch("pipeline.validate_episode", return_value=fake_issues):
        ok, errors, warnings = pipeline.cmd_validate("2026-09-24", allow_short=False)
        assert ok is False
        assert len(errors) == 1
        assert "curto demais" in errors[0]


def test_cmd_validate_allows_short_script_with_flag(tmp_path: Path):
    fake_episodes_dir = tmp_path / "episodes"
    fake_episodes_dir.mkdir(parents=True)
    fake_md = fake_episodes_dir / "2026-09-24.md"
    fake_md.write_text("texto qualquer curto", encoding="utf-8")

    fake_issues = [
        "❌ Roteiro curto demais para áudio (1150 palavras) — mínimo 1500 (~8 min); meta 2000-2500 (~15 min)",
    ]

    with patch("pipeline.EPISODES_DIR", fake_episodes_dir), \
         patch("pipeline.validate_episode", return_value=fake_issues):
        ok, errors, warnings = pipeline.cmd_validate("2026-09-24", allow_short=True)
        assert ok is True
        assert len(errors) == 0
        assert len(warnings) == 1
        assert "[ALLOW-SHORT-AUDIO]" in warnings[0]


def test_cmd_validate_still_blocks_real_critical_errors_with_flag(tmp_path: Path):
    fake_episodes_dir = tmp_path / "episodes"
    fake_episodes_dir.mkdir(parents=True)
    fake_md = fake_episodes_dir / "2026-09-24.md"
    fake_md.write_text("texto curto", encoding="utf-8")

    fake_issues = [
        "❌ Roteiro curto demais para áudio (1150 palavras)",
        "❌ Bloco de manchetes ausente",
    ]

    with patch("pipeline.EPISODES_DIR", fake_episodes_dir), \
         patch("pipeline.validate_episode", return_value=fake_issues):
        ok, errors, warnings = pipeline.cmd_validate("2026-09-24", allow_short=True)
        assert ok is False
        assert len(errors) == 1
        assert "Bloco de manchetes ausente" in errors[0]
