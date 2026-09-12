# 02 — TTS: Gemini 3.1 & Fallback Edge-TTS (Linux Hermes)

**Impacto**: Crítico
**Ganho realista**:
- Gemini: pouco wall-clock extra se já espera 20 s/RPM; paralelo **por chave** só via `GeminiMultiClient` existente. Furar RPM queima RPD (incidente das 6 chaves).
- Edge: 1 processo Python em vez de N spawns — este é o ganho real (minutos → ~1–2 min com Semaphore 3, **não** 25–40 s com 8 sockets).
**Scripts**:
- `scripts/generate_gemini_tts_multi.py` (**1713** linhas, não 1504)
- `scripts/tts_fallback_edge.sh` (CRLF hoje) → opcional `tts_fallback_edge.py`
- `scripts/ricardo_voice_fx.py` (425 linhas)
- `scripts/pipeline.py` (`cmd_audio`)
**Interpretador**: **HERMES_PY** (3.11). Não PROJECT_PY.
**Não executar** entre 05:45 e o fim do diário 06:00.

---

## 1. Contexto real

- Cron diário: HERMES_PY `pipeline.py full` → `cmd_audio` → Gemini 3.1 → Edge se falhar.
- Cadeia real: Gemini multi → Edge (`tts_fallback_edge.sh`). ElevenLabs **nunca** teve conta. MOSS desligado.
- `uvloop` **existe** no HERMES_PY — `try: import uvloop; uvloop.install()` ok.
- `edge_tts` existe no HERMES_PY (7.2.7).
- **`librosa`, `pyworld`, `scipy` NÃO existem no HERMES_PY.** O FX do Ricardo (`ricardo_voice_fx.py`) importa isso. Hoje o shell chama `$HERMES_PY ricardo_voice_fx.py` — o FX **já falha** neste host e cai no raw (script trata falha). Plano 02 **não** instala librosa/pyworld na madrugada (pesado, numpy/scipy, risco de OOM). Batch in-process do FX só depois de decidir instalar no HERMES_PY **ou** aplicar FX com ffmpeg-only.
- `CHUNK_TARGET_WORDS = 300` no código (memória antiga “200” não está no arquivo).
- Vozes Gemini no código: Peter=Charon, Ricardo=**Kore**. Não “alinhar” para Schedar neste plano (é avaliação de locutor; fora de escopo de performance).
- **Vozes do `tts_fallback_edge.py` (decisão 2026-09-10):** duas vozes Edge distintas, iguais ao `pipeline.py` / mapa em `generate_gemini_tts_multi.py`:
  - Peter = `pt-BR-AntonioNeural`
  - Ricardo = `pt-BR-FranciscaNeural`
  FX librosa/pyworld **não** roda no HERMES_PY nesta onda — Antonio+FX deixaria os dois com a mesma voz. Não usar Fabio. Azure Humberto/Brenda é outra stack (não misturar). Se um dia o FX voltar no Hermes, aí sim reavaliar voz única + formant.
- FFmpeg cadeia **v2** (loudnorm depois do EQ, −16 LUFS). Concat **não** pode virar um `-af highpass,loudnorm` único que regrida para v1. Reusar `_ffmpeg_chain` / `VALE_TTS_FFMPEG_CHAIN` já em `generate_gemini_tts_multi.py`.
- 6 chaves no `.env` (`GEMINI_API_KEY` + `_3`…`_7`; sem `_2` neste arquivo). TTS: **3 RPM / 10 RPD** por chave. Reserva **antes** da API; 429 RPM faz rollback, não marca RPD.
- `tts_fallback_edge.sh` está **CRLF**. Mesmo bug do `cron-wrapper.sh` (shebang `\r`). Converter para LF **antes** de qualquer teste de fallback.

---

## 2. Gargalos que ainda valem

### A. Gemini (`generate_gemini_tts_multi.py`)
Loop por chunk. `asyncio` só aparece no fallback Edge interno (~L1097), não no caminho Gemini principal. Throughput legal = min(chaves_vivas, floor(RPM)). Com 6 chaves TTS: teto teórico 18 req/min, mas `GeminiMultiClient` já faz RR + timer 20 s **por chave**. `gather` de 8 chunks na **mesma** chave = 429 em < 60 s.

**Permitido:** producer-consumer com 1 in-flight por chave, usando o cliente existente (reserva/rollback). **Proibido:** `Semaphore(2) por chave` + `generate_tts_async` inventado — o cliente é síncrono.

### B. Edge (`tts_fallback_edge.sh`)
N spawns `python -m edge_tts` + N spawns FX. Este é o plano que vale a pena.

---

## 3. Edge — solução alinhada

Novo `scripts/tts_fallback_edge.py` no HERMES_PY. O `.sh` vira wrapper LF:

```bash
#!/usr/bin/env bash
exec "${HERMES_PY:-/home/osmar/.hermes/hermes-agent/venv/bin/python3}" \
  "$(dirname "$0")/tts_fallback_edge.py" "$@"
```

Regras:

1. `asyncio` + `edge_tts.Communicate`; **Semaphore(3)** neste host (não 8). Microsoft Edge TTS também rate-limita.
2. Voz por locutor no `Communicate(text, voice)`: Antonio vs Francisca. **Não** aplicar FX nesta onda. Se `import librosa` falhar (vai falhar no HERMES_PY), logar uma vez e seguir. Não importar `ricardo_voice_fx` no hot path.
3. `/dev/shm/valeliberdade-edge-{DATE}/` só se livre > 512 MiB **e** swap used < 2,5 GiB; senão `audio/tmp/{DATE}/`. `finally: rmtree`.
4. Concat via a cadeia FFmpeg **v2** já versionada (não inventar filtro).
5. CLI: `tts_fallback_edge.py [DATE]` e `--date` para o pipeline.

Não prometer 25–45 s. Meta: episódio típico **< 2,5 min** com Semaphore 3, sem FX pesado.

---

## 4. Gemini — solução alinhada

Não adicionar `generate_tts_async` paralelo sem passar por `_enforce_rate_limit`.

- Manter 1 worker por chave viva, fila de chunks, `run_in_executor` se quiser I/O, mas a reserva continua no cliente.
- Buffers WAV em `/dev/shm` com os mesmos tetos do Edge.
- Retry: já existe `max_retries=2` + janela RPM. Não empilhar backoff de 2 s em 429 de taxa.
- Não mudar `CHUNK_TARGET_WORDS` neste plano.

---

## 5. `cmd_audio`

Ordem permanece: Gemini → Edge. Trocar o subprocess do `.sh` pelo `.py` **depois** do `.py` passar no mesmo episódio de referência (diff de duração ±10%, LUFS −16). Manter o `.sh` como wrapper.

Não reativar ElevenLabs.

---

## 6. Checklist

| Item | Aceite |
|------|--------|
| Áudio | Cadeia FFmpeg v2, −16 LUFS, Peter/Ricardo inteligíveis |
| Edge | 1 processo; Semaphore ≤ 3; tmp limpo |
| Gemini | 0 chamadas sem reserva; 429 RPM não marca RPD |
| RAM | Pico < 1,5 GiB no processo TTS (sem librosa) |
| Cron | Diário 06:00 seguinte ok |
| CRLF | `.sh` em LF antes do primeiro teste |
