# 05 — Compilação de Regex (module-level)

**Impacto**: Baixo no wall-clock do pipeline (rebaixado). Seguro para madrugada.
**Ganho**: ms–centenas de ms no `preprocess_for_tts`, não “30% do episódio”. O cache `re._MAXCACHE` (512) já cobre os literais. O único hot-path real é o **lexicon** (N `re.compile` por chamada).
**Scripts**: `tts_preprocessor.py` (1099), `news_collector.py`, `ai_news_filter.py`
**Já compilados** (não mexer): `bm_mockup_video.py` (`_X_STATUS_RE`, …), `gemini_client.py` (`_RETRY_IN_RE`, …)

---

## O que fazer

Fase A: module-level `re.compile` nos literais de `tts_preprocessor.py` (datas, horas, rodovias, markdown).

Fase B: precompilar o lexicon **uma vez** (`_compile_lexicon()` no load). Este é o ganho.

Fase C: `news_collector` / `ai_news_filter` — só se o pattern está em loop por artigo. `re.sub(r"\s+", ...)` não justifica PR sozinho.

Não afirmar byte-identical do MP3: o preprocessor muda **texto**. Aceite = mesmo texto TTS em episódio de referência (`test_turguniev_scrub.py` + diff do `-tts.txt`).

Rodar testes no **HERMES_PY**.

---

## Checklist

- [ ] `HERMES_PY -m unittest scripts.test_turguniev_scrub`
- [ ] `import tts_preprocessor` no HERMES_PY sem erro
- [ ] `-tts.txt` de um episódio de arquivo idêntico após preprocess
- [ ] Sem mudança de `CHUNK_TARGET_WORDS` / vozes
