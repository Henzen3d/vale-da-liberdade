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
    kind: str  # "source" | "broll" | "x-post"
    shot: str | None = None
    video: str | None = None
    broll_file: str | None = None
    x_post: dict | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


MIN_SCENE_DURATION_S = 8.0
MAX_SCENE_DURATION_S = 22.0
DEFAULT_BROLL_DUR_S = 1.2
TARGET_MIN_BEATS_5MIN = 10


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

    - Distribui o tempo total do áudio proporcionalmente à contagem de palavras de cada fala.
    - Se a fala tiver `fonte_url`, sincroniza com a cena correspondente.
    - Garante piso de pelo menos 8s por cena de fonte externa.
    - Insere transições de b-roll (0.8–1.5s) em mudanças de matéria se houver clipes disponíveis.
    - Garante ritmo dinâmico com pelo menos 10 telas/beats em episódios de 5 minutos (~300s).
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
            "kind": scene_item.get("kind") or "source",
            "shot": scene_item.get("shot"),
            "video": scene_item.get("video"),
            "broll_file": None,
            "x_post": scene_item.get("x_post"),
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
        x_post = rb.get("x_post")
        t0 = rb["t0"]
        t1 = rb["t1"]

        # Agrupar beats consecutivos idênticos
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
            x_post=x_post,
        ))
        i += 1

    # 5. Gancho dos Primeiros 15 Segundos (Visual Hook)
    # Se o vídeo for longo (>= 120s) e a abertura for estática (> 15s), insere cortes dinâmicos
    if total_dur >= 120.0 and len(final_beats) > 1 and len(scene_queue) > 1:
        if final_beats[0].t1 >= 14.0 and final_beats[0].kind == "source":
            old_first = final_beats[0]
            cut1 = 5.0
            cut2 = 9.0
            alt_scene = scene_queue[1 % len(scene_queue)]
            b0_a = SceneBeat(
                t0=0.0,
                t1=cut1,
                url=old_first.url,
                veiculo=old_first.veiculo,
                kind="source",
                shot=old_first.shot,
                video=old_first.video,
                x_post=old_first.x_post,
            )
            b0_b = SceneBeat(
                t0=cut1,
                t1=cut2,
                url=alt_scene.get("url") or old_first.url,
                veiculo=alt_scene.get("veiculo") or old_first.veiculo,
                kind=alt_scene.get("kind") or "source",
                shot=alt_scene.get("shot") or old_first.shot,
                video=alt_scene.get("video") or old_first.video,
                x_post=alt_scene.get("x_post") or old_first.x_post,
            )
            b0_c = SceneBeat(
                t0=cut2,
                t1=old_first.t1,
                url=old_first.url,
                veiculo=old_first.veiculo,
                kind="source",
                shot=old_first.shot,
                video=old_first.video,
                x_post=old_first.x_post,
            )
            final_beats[0:1] = [b0_a, b0_b, b0_c]

    # 6. Dinamismo: quebra beats longos (> 22s) alternando entre as cenas disponíveis
    expanded_beats: list[SceneBeat] = []
    cycle_ptr = 1
    for beat in final_beats:
        dur = beat.t1 - beat.t0
        if dur > MAX_SCENE_DURATION_S and len(scene_queue) > 1 and beat.kind == "source":
            num_sub = int(dur // 15.0) + 1
            step = dur / num_sub
            sub_t0 = beat.t0
            for s_idx in range(num_sub):
                sub_t1 = round(beat.t0 + (s_idx + 1) * step, 2)
                if s_idx == num_sub - 1:
                    sub_t1 = beat.t1
                alt_scene = scene_queue[cycle_ptr % len(scene_queue)]
                cycle_ptr += 1
                expanded_beats.append(SceneBeat(
                    t0=round(sub_t0, 2),
                    t1=round(sub_t1, 2),
                    url=alt_scene.get("url") or beat.url,
                    veiculo=alt_scene.get("veiculo") or beat.veiculo,
                    kind=alt_scene.get("kind") or "source",
                    shot=alt_scene.get("shot") or beat.shot,
                    video=alt_scene.get("video") or beat.video,
                    broll_file=None,
                    x_post=alt_scene.get("x_post") or beat.x_post,
                ))
                sub_t0 = sub_t1
        else:
            expanded_beats.append(beat)

    # 7. Garantia de Piso de Telas: assegura pelo menos 10 beats em vídeos de ~5min (>= 180s)
    if total_dur >= 180.0 and len(expanded_beats) < TARGET_MIN_BEATS_5MIN and len(scene_queue) > 1:
        while len(expanded_beats) < TARGET_MIN_BEATS_5MIN:
            longest_idx = max(range(len(expanded_beats)), key=lambda idx: (expanded_beats[idx].t1 - expanded_beats[idx].t0))
            b_target = expanded_beats[longest_idx]
            b_dur = b_target.t1 - b_target.t0
            if b_dur < 12.0:
                break
            half = round(b_target.t0 + b_dur / 2.0, 2)
            alt_scene = scene_queue[cycle_ptr % len(scene_queue)]
            cycle_ptr += 1
            b1 = SceneBeat(
                t0=b_target.t0,
                t1=half,
                url=b_target.url,
                veiculo=b_target.veiculo,
                kind=b_target.kind,
                shot=b_target.shot,
                video=b_target.video,
                broll_file=b_target.broll_file,
                x_post=b_target.x_post,
            )
            b2 = SceneBeat(
                t0=half,
                t1=b_target.t1,
                url=alt_scene.get("url") or b_target.url,
                veiculo=alt_scene.get("veiculo") or b_target.veiculo,
                kind=alt_scene.get("kind") or "source",
                shot=alt_scene.get("shot") or b_target.shot,
                video=alt_scene.get("video") or b_target.video,
                broll_file=None,
                x_post=alt_scene.get("x_post") or b_target.x_post,
            )
            expanded_beats[longest_idx:longest_idx + 1] = [b1, b2]

    final_beats = expanded_beats

    # 8. Ajustar continuidade estrita dos timestamps
    for j in range(len(final_beats) - 1):
        if final_beats[j].t1 != final_beats[j + 1].t0:
            final_beats[j + 1].t0 = final_beats[j].t1

    if final_beats:
        final_beats[0].t0 = 0.0
        final_beats[-1].t1 = round(total_dur, 2)

    return final_beats
