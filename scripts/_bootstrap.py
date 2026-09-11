#!/usr/bin/env python3
"""Bootstrap opt-in para scripts/ do Vale. Sem Pydantic Settings.

    from _bootstrap import PROJECT_ROOT, SCRIPT_DIR
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env", override=False)
    load_dotenv(Path.home() / ".hermes" / ".env", override=False)
except Exception:
    pass
