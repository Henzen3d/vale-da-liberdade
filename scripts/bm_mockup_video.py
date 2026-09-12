#!/usr/bin/env python3
"""Gera vídeo BM com mockup-browser + sites reais das matérias e sobe no YouTube.

PIPELINE OFICIAL de vídeo BM desde 2026-08-22 (substitui HyperFrames).
Usado pelo cron hourly (bm-hourly-pipeline.sh) depois do process-queue.
Não misturar com bm_video_autopilot.py (aposentado).

Fachada (plano 08): implementação em scripts/bm_video/.
CLI e flags inalterados (--pending, --upload, --privacy, --max, --days).
find_episode_thumbnail usa resolve_youtube_thumbnail (não cai em bm_*.jpg).
"""
from __future__ import annotations

import sys as _sys

from bm_video import capture as _capture
from bm_video import cli as _cli
from bm_video import constants as _constants
from bm_video import render as _render
from bm_video import server as _server
from bm_video import state as _state
from bm_video import youtube as _youtube
from bm_video.cli import main

_this = _sys.modules[__name__]
_submods = (_constants, _state, _server, _capture, _render, _youtube, _cli)
for _mod in _submods:
    for _k, _v in vars(_mod).items():
        if _k.startswith("__"):
            continue
        setattr(_this, _k, _v)


class _FacadeModule(_this.__class__):
    def __setattr__(self, name: str, value: object) -> None:
        super().__setattr__(name, value)
        if not name.startswith("__"):
            for mod in _submods:
                if hasattr(mod, name):
                    setattr(mod, name, value)


_this.__class__ = _FacadeModule

if __name__ == "__main__":
    raise SystemExit(main())
