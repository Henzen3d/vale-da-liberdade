#!/usr/bin/env python3
"""Testes unitários da sincronização de playlist dinâmica (sem rede/API real)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from youtube_playlist_sync import (
    load_playlist_config,
    resolve_dynamic_playlist_id,
    sync_dynamic_playlist,
)


class DynamicPlaylistTests(unittest.TestCase):
    def setUp(self):
        self.mock_yt = MagicMock()

    def test_load_playlist_config(self):
        cfg = load_playlist_config()
        self.assertIsInstance(cfg, dict)
        self.assertTrue(cfg.get("enabled", True))
        self.assertEqual(cfg.get("max_items", 10), 10)

    def test_resolve_by_configured_id(self):
        mock_list = MagicMock()
        mock_list.execute.return_value = {"items": [{"id": "PL123456789012345"}]}
        self.mock_yt.playlists().list.return_value = mock_list

        pid = resolve_dynamic_playlist_id(self.mock_yt, configured_id="PL123456789012345")
        self.assertEqual(pid, "PL123456789012345")

    def test_resolve_by_title_on_channel(self):
        mock_list_mine = MagicMock()
        mock_list_mine.execute.return_value = {
            "items": [
                {"id": "PL_OUTRA", "snippet": {"title": "Outra Playlist"}},
                {"id": "PL_FOUND", "snippet": {"title": "Últimas Notícias — Vale da Liberdade"}},
            ]
        }
        self.mock_yt.playlists().list.return_value = mock_list_mine

        pid = resolve_dynamic_playlist_id(self.mock_yt, configured_id=None, title="Últimas Notícias — Vale da Liberdade")
        self.assertEqual(pid, "PL_FOUND")

    def test_sync_insert_empty_playlist(self):
        # Playlist vazia
        mock_list = MagicMock()
        mock_list.execute.return_value = {"items": []}
        self.mock_yt.playlistItems().list.return_value = mock_list

        # Insert
        mock_insert = MagicMock()
        mock_insert.execute.return_value = {"id": "item_new_1", "snippet": {"resourceId": {"videoId": "vid123"}}}
        self.mock_yt.playlistItems().insert.return_value = mock_insert

        with patch("youtube_playlist_sync.resolve_dynamic_playlist_id", return_value="PL_RESOLVED"):
            res = sync_dynamic_playlist(self.mock_yt, "vid123", playlist_id="PL_RESOLVED", max_items=10)

        self.assertTrue(res["added"])
        self.assertEqual(res["position"], 0)
        self.assertEqual(res["removed"], [])
        self.assertEqual(res["total_items"], 1)
        self.mock_yt.playlistItems().insert.assert_called_once()
        self.mock_yt.playlistItems().delete.assert_not_called()

    def test_sync_idempotent_already_at_top(self):
        # Vídeo já está no topo (index 0)
        mock_list = MagicMock()
        mock_list.execute.return_value = {
            "items": [
                {"id": "item_top", "snippet": {"resourceId": {"videoId": "vid_current"}}},
                {"id": "item_2", "snippet": {"resourceId": {"videoId": "vid_old"}}},
            ]
        }
        self.mock_yt.playlistItems().list.return_value = mock_list

        with patch("youtube_playlist_sync.resolve_dynamic_playlist_id", return_value="PL_RESOLVED"):
            res = sync_dynamic_playlist(self.mock_yt, "vid_current", playlist_id="PL_RESOLVED", max_items=10)

        self.assertFalse(res["added"])
        self.assertTrue(res["already_top"])
        self.mock_yt.playlistItems().insert.assert_not_called()
        self.mock_yt.playlistItems().delete.assert_not_called()

    def test_sync_reinsert_moving_to_top_removes_old_position(self):
        # Vídeo está na posição 2 (não no topo)
        mock_list = MagicMock()
        mock_list.execute.return_value = {
            "items": [
                {"id": "item_1", "snippet": {"resourceId": {"videoId": "other_1"}}},
                {"id": "item_2", "snippet": {"resourceId": {"videoId": "vid_repeat"}}},
                {"id": "item_3", "snippet": {"resourceId": {"videoId": "other_2"}}},
            ]
        }
        self.mock_yt.playlistItems().list.return_value = mock_list

        mock_insert = MagicMock()
        mock_insert.execute.return_value = {"id": "item_new_top", "snippet": {"resourceId": {"videoId": "vid_repeat"}}}
        self.mock_yt.playlistItems().insert.return_value = mock_insert

        mock_delete = MagicMock()
        mock_delete.execute.return_value = {}
        self.mock_yt.playlistItems().delete.return_value = mock_delete

        with patch("youtube_playlist_sync.resolve_dynamic_playlist_id", return_value="PL_RESOLVED"):
            res = sync_dynamic_playlist(self.mock_yt, "vid_repeat", playlist_id="PL_RESOLVED", max_items=10)

        self.assertTrue(res["added"])
        self.assertEqual(res["position"], 0)
        self.assertIn("item_2", res["removed"])
        self.assertEqual(res["total_items"], 3)
        self.mock_yt.playlistItems().delete.assert_called_with(id="item_2")

    def test_sync_overflow_trimming(self):
        # Playlist já tem 3 itens e limite é 3. Inserir o 4º deve deletar o item mais antigo (item_3).
        existing_items = [
            {"id": f"item_{i}", "snippet": {"resourceId": {"videoId": f"old_vid_{i}"}}}
            for i in range(1, 4)
        ]
        mock_list = MagicMock()
        mock_list.execute.return_value = {"items": existing_items}
        self.mock_yt.playlistItems().list.return_value = mock_list

        mock_insert = MagicMock()
        mock_insert.execute.return_value = {"id": "item_new", "snippet": {"resourceId": {"videoId": "vid_fresh"}}}
        self.mock_yt.playlistItems().insert.return_value = mock_insert

        mock_delete = MagicMock()
        mock_delete.execute.return_value = {}
        self.mock_yt.playlistItems().delete.return_value = mock_delete

        with patch("youtube_playlist_sync.resolve_dynamic_playlist_id", return_value="PL_RESOLVED"):
            res = sync_dynamic_playlist(self.mock_yt, "vid_fresh", playlist_id="PL_RESOLVED", max_items=3)

        self.assertTrue(res["added"])
        self.assertIn("item_3", res["removed"])
        self.assertEqual(res["total_items"], 3)
        self.mock_yt.playlistItems().delete.assert_called_with(id="item_3")


if __name__ == "__main__":
    unittest.main()
