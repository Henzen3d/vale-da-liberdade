# 10 — Paralelismo no Pipeline Full (`pipeline.py`)

**Impacto**: Médio, com contenção Gemini/RAM
**Ganho realista**: Ads ∥ thumbnail (~minutos se thumb lenta). Title ∥ description **não** nesta onda.
**Script**: `pipeline.py` (1147 linhas)
**Cron**: diário 06:00 HERMES_PY. Não sobrepor com refatoração TTS (02) na mesma noite.

---

## Alinhamento

Etapas reais de `cmd_full` (código vivo): init → roteiro JSON → **2.5 title** → **2.6 description** → process → validate → audio → **5.5 ads** → **5.6 thumb** → archive → publish.

- Title e description usam **o mesmo** `GeminiMultiClient` / `gemini_usage.json`. Dois subprocessos HERMES_PY em paralelo = duas reservas no mesmo JSON. Só é seguro **depois** do plano 06 (`fcntl.flock`). Até lá, **sequencial**.
- Ads (`ads_insert.py`) e thumbnail (`generate_thumbnail_safe` **in-process**, não subprocess) — independentes de arquivo. Thumb usa CF/Pollinations (rede) + às vezes Gemini p/ prompt. Ads usa ffmpeg no MP3. RAM: ffmpeg + possível decode. Teto: não lançar thumb se RSS do processo + ffmpeg > folga (host 7,6 GiB, swap sujo). Preferir ThreadPool **só** se thumb continuar subprocess; hoje thumb é import in-process — um thread GIL não acelera CF HTTP se `requests` bloquear… na verdade HTTP em thread **ajuda**. Ok `max_workers=2` para ads subprocess + thumb, **depois** do áudio existir (ads precisa do MP3).
- Archive vs publish: publish lê catálogo/áudios; archive escreve `archive/index.md`. **Não** paralelizar 6 e 7.
- `_run_subprocess_step`: DRY ok, ganho zero de tempo. Pode ir junto.
- `PipelineOptions` dataclass: cosmética; não misturar com 07 (`PipelineContext`).
- Logs: `ThreadPool` + `print` mistura stdout. Prefixo `[title]` / `[desc]` ou sequencial.
- Title/desc são não-bloqueantes hoje (exit ≠ 0 não derruba o full). Manter.

Ganho “25 min → 18 min” assume title+desc+ads+thumb como 7 min sequenciais. Title+desc são Gemini flash (segundos–1 min). O miolo continua TTS.

---

## Ordem

1. DRY `_run_subprocess_step` (inofensivo)
2. Ads ∥ thumb (medir RAM)
3. Title ∥ desc **só** com flock do plano 06 comprovado

---

## Checklist

- [ ] Artefatos iguais (`-title.txt`, `-description.txt`, MP3 com ads, thumbnail)
- [ ] Sem dois writers Gemini sem flock
- [ ] Publish depois do archive
- [ ] Diário 06:00 seguinte verde
