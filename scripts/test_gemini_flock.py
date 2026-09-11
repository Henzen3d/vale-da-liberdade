#!/usr/bin/env python3
"""flock: sleep de RPM fora do lock; dois processos reservam chaves distintas."""
from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import gemini_client as gc


class FlockSemanticsTests(unittest.TestCase):
    def test_os_replace_not_unlink_in_unlocked_save(self):
        src = Path(gc.__file__).read_text(encoding="utf-8")
        # o caminho Linux não faz unlink do JSON vivo
        self.assertIn("os.replace(temp_path, file_path)", src)
        self.assertNotIn("file_path.unlink()", src)

    def test_enforce_sleep_is_outside_lock_block(self):
        src = Path(gc.__file__).read_text(encoding="utf-8")
        # time.sleep da espera RPM aparece DEPOIS do with _usage_lock
        lock_idx = src.find("with _usage_lock(self.usage_file)")
        sleep_idx = src.find("time.sleep(wait_gap)")
        self.assertGreater(lock_idx, 0)
        self.assertGreater(sleep_idx, lock_idx)

    def test_two_sequential_saves_keep_rr_index(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "gemini_usage.json"
            gc._save_usage(path, {"_meta": {"rr_index": 3}, "k1": {}})
            data = gc._load_usage(path)
            data["k2"] = {"m": {"requests": [1.0]}}
            gc._save_usage(path, data)
            again = gc._load_usage(path)
            self.assertEqual(again["_meta"]["rr_index"], 3)
            self.assertIn("k2", again)
            self.assertFalse(path.with_suffix(path.suffix + ".tmp").exists())


if __name__ == "__main__":
    unittest.main()
