#!/usr/bin/env python3
"""
Módulo de deduplicação para vídeos do canal Vale da Liberdade / Brasil & Mundo.
Evita reprocessamento de vídeos com títulos idênticos ou semanticamente duplicados
(ex: 'LULA confisca CELULAR de VORCARO').
"""
from __future__ import annotations

import html
import re
import sys
import unicodedata
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


def normalize_title(text: str) -> str:
    """Normaliza título para comparação estrita (minúsculo, sem acentos, sem pontuação)."""
    text = html.unescape(text or "").lower()
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return " ".join(text.split())


def check_video_duplicate(
    title: str,
    seen_videos: dict,
    queue: list[dict] | None = None,
    current_video_id: str | None = None,
    threshold: float = 0.88,
) -> tuple[bool, str]:
    """Verifica se um vídeo é duplicata por título contra seen_videos.json e queue.json.

    Retorna (is_dup, reason_msg).
    """
    if not title:
        return False, ""

    norm = normalize_title(title)
    if len(norm) < 6:
        return False, ""

    # 1. Comparação exata normalizada na fila
    if queue:
        for q in queue:
            q_vid = q.get("video_id")
            if current_video_id and q_vid == current_video_id:
                continue
            q_title = q.get("title") or ""
            if q_title and normalize_title(q_title) == norm:
                return True, f"já existe na fila ({q_vid}): '{q_title}'"

    # 2. Comparação exata normalizada em seen_videos
    videos_dict = seen_videos.get("videos", {}) if isinstance(seen_videos, dict) else {}
    for s_vid, s_data in videos_dict.items():
        if current_video_id and s_vid == current_video_id:
            continue
        s_title = s_data.get("titulo") or ""
        if s_title and normalize_title(s_title) == norm:
            return True, f"já processado em seen_videos ({s_vid}): '{s_title}'"

    # 3. Comparação aproximada com MinHash para títulos mais longos (>= 15 caracteres)
    if len(norm) >= 15:
        try:
            from minhash_dedup import MinHasher, jaccard_from_signatures

            hasher = MinHasher(n_grams=3, n_hashes=64)
            sig_new = hasher.signature(norm)

            # Checar últimos 100 vídeos processados
            for s_vid, s_data in list(videos_dict.items())[-100:]:
                if current_video_id and s_vid == current_video_id:
                    continue
                s_title = s_data.get("titulo") or ""
                if not s_title:
                    continue
                s_norm = normalize_title(s_title)
                if len(s_norm) < 15:
                    continue
                sig_prev = hasher.signature(s_norm)
                sim = jaccard_from_signatures(sig_new, sig_prev)
                if sim >= threshold:
                    return True, f"quase idêntico a vídeo já processado ({s_vid}, sim={sim:.2f}): '{s_title}'"
        except Exception:
            pass

    return False, ""
