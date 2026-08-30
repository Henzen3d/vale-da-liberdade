#!/usr/bin/env python3
"""
Timeline de Cenas — Pipeline Brasil e Mundo.

Calcula a distribuição temporal das cenas de fontes e transições de b-roll
sincronizadas com o áudio do episódio (baseado na contagem de palavras das falas).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class SceneBeat:
    t0: float
    t1: float
    url: str
    veiculo: str
    kind: str  # "source" | "broll"
    shot: str | None = None
    video: str | None = None
    broll_file: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


MIN_SCENE_DURATION_S = 8.0
DEFAULT_BROLL_DUR_S = 1.0


def count_words(text: str) -> int:
    return len((text or "").split())


def load_broll_clips(broll_index_path: Path | None = None) -> list[dict]:
    if not broll_index_path or not broll_index_path.is_file():
        return []
    try:
        data = json.loads(broll_index_path.read_text(encoding="utf-8"))
        return data.get("clips", [])
    except Exception:
        return []


def build_scene_timeline(
    episode: dict,
    total_duration_s: float,
    scenes: list[dict],
    broll_index_path: Path | None = None,
) -> list[SceneBeat]:
    """Gera lista de SceneBeat sincronizados com o áudio falado.

    - Distrui o tempo total do áudio proporcionalmente à contagem de palavras de cada fala.
    - Se a fala tiver `fonte_url`, sincroniza com a cena correspondente.
    - Garante piso de pelo menos 8s por cena de fonte externa.
    - Insere transições de b-roll (0.8–1.5s) em mudanças de matéria se houver clipes disponíveis.
    """
    total_dur = max(total_duration_s, 10.0)
    if not scenes:
        scenes = [{"veiculo": "Vale da Liberdade", "url": "https://news.mob.tec.br", "shot": None, "video": None}]

    # 1. Coletar falas em ordem sequencial com seus blocos e fonte_url
    blocks: list[dict] = []
    for section_name in ("abertura", "desenvolvimento", "fechamento"):
        for item in episode.get(section_name) or []:
            txt = (item.get("texto") or "").strip()
            if not txt:
                continue
            blocks.append({
                "section": section_name,
                "texto": txt,
                "words": max(1, count_words(txt)),
                "fonte_url": item.get("fonte_url") or "",
            })

    if not blocks:
        blocks = [{
            "section": "desenvolvimento",
            "texto": episode.get("titulo") or "Comentário",
            "words": 100,
            "fonte_url": "",
        }]

    total_words = sum(b["words"] for b in blocks)
    available_broll = load_broll_clips(broll_index_path)

    # 2. Mapeamento de cenas por URL
    scene_by_url = {s["url"]: s for s in scenes if s.get("url")}
    scene_queue = list(scenes)
    scene_ptr = 0

    # 3. Construção dos beats preliminares
    raw_beats: list[dict] = []
    current_t = 0.0

    for idx, b in enumerate(blocks):
        dur_block = (b["words"] / total_words) * total_dur
        target_url = b.get("fonte_url")
        scene_item = None

        if target_url and target_url in scene_by_url:
            scene_item = scene_by_url[target_url]
        else:
            # Avança na fila de cenas disponíveis
            scene_item = scene_queue[scene_ptr % len(scene_queue)]

        t_end = min(total_dur, current_t + dur_block)

        # Inserção de b-roll na transição entre matérias/blocos se biblioteca contiver clips
        if available_broll and raw_beats and raw_beats[-1]["url"] != scene_item.get("url"):
            # Só insere se houver folga de tempo
            if total_dur - current_t > 15.0:
                clip = available_broll[len(raw_beats) % len(available_broll)]
                clip_dur = float(clip.get("dur_s", DEFAULT_BROLL_DUR_S))
                broll_end = min(total_dur - 5.0, current_t + clip_dur)
                raw_beats.append({
                    "t0": round(current_t, 2),
                    "t1": round(broll_end, 2),
                    "url": "",
                    "veiculo": "Transição",
                    "kind": "broll",
                    "shot": None,
                    "video": None,
                    "broll_file": clip.get("file"),
                })
                current_t = broll_end
                t_end = min(total_dur, current_t + dur_block)

        raw_beats.append({
            "t0": round(current_t, 2),
            "t1": round(t_end, 2),
            "url": scene_item.get("url") or "",
            "veiculo": scene_item.get("veiculo") or "Fonte",
            "kind": "source",
            "shot": scene_item.get("shot"),
            "video": scene_item.get("video"),
            "broll_file": None,
        })
        scene_ptr += 1
        current_t = t_end

    # 4. Agregação e aplicação de piso mínimo de 8.0s por cena de fonte
    final_beats: list[SceneBeat] = []
    i = 0
    while i < len(raw_beats):
        rb = raw_beats[i]
        kind = rb["kind"]
        url = rb["url"]
        veic = rb["veiculo"]
        shot = rb["shot"]
        video = rb["video"]
        broll_file = rb["broll_file"]
        t0 = rb["t0"]
        t1 = rb["t1"]

        # Agrupar beats consecutivos da mesma cena
        while i + 1 < len(raw_beats) and raw_beats[i + 1]["kind"] == kind and raw_beats[i + 1]["url"] == url:
            t1 = raw_beats[i + 1]["t1"]
            i += 1

        # Garantir piso mínimo de 8s para source se não for o último beat
        if kind == "source" and (t1 - t0) < MIN_SCENE_DURATION_S and i + 1 < len(raw_beats):
            t1 = min(total_dur, t0 + MIN_SCENE_DURATION_S)

        final_beats.append(SceneBeat(
            t0=round(t0, 2),
            t1=round(t1, 2),
            url=url,
            veiculo=veic,
            kind=kind,
            shot=shot,
            video=video,
            broll_file=broll_file,
        ))
        i += 1

    # 5. Ajustar continuidade dos timestamps
    for j in range(len(final_beats) - 1):
        if final_beats[j].t1 != final_beats[j + 1].t0:
            final_beats[j + 1].t0 = final_beats[j].t1

    if final_beats:
        final_beats[0].t0 = 0.0
        final_beats[-1].t1 = round(total_dur, 2)

    return final_beats
