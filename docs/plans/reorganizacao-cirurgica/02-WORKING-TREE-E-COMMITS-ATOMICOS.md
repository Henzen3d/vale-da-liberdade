# Plano 02 — Higienização do Working Tree e Commits Atômicos

> **Fase:** Dia 2  
> **Prioridade:** ALTA (Evita incidentes por desvio entre código em disco e repositório Git)  
> **Escopo:** Git / Verificação de testes unitários / Higienização de branches  
> **Regra:** Não commitar tudo em um único "commit monstro". Dividir em pacotes atômicos e testados.

---

## 1. Contexto e Diagnóstico

### O Problema Atual
Diversos scripts fundamentais para o funcionamento do Diário e do Brasil e Mundo possuem alterações locais não commitadas no servidor/workspace:
- **Diário & Fontes:** `scripts/news_collector.py`, `scripts/pipeline.py`, `scripts/http_fetch.py`, `scripts/validate_feeds.py`, `sources/sources.json`.
- **Captura & Recuperação:** `scripts/recover_page.py`, `scripts/clean_screenshot.py`, `scripts/test_blocked_page_recovery.py`.
- **Brasil e Mundo:** `scripts/bm_enrich_sources.py`, `scripts/bm_transcript.py`.
- **R2, manifesto, legendas, capas (também `M`):** `scripts/upload_r2.py`, `scripts/batch_upload_r2.py`, `scripts/episode_image_manifest.py`, `scripts/youtube_captions.py`, `scripts/test_youtube_captions.py`, `scripts/test_youtube_thumbnail_identity.py`.

### O Risco
Este cenário é idêntico ao incidente de 15/08: qualquer `git pull`, `git checkout` ou sincronização automática pode sobrescrever correções vitais ou deixar o ambiente de produção em estado inconsistente.

---

## 2. Estratégia de Separação em Pacotes Atômicos

A higienização deve ser dividida em **commits atômicos temáticos só do que `git status` mostrar sujo**. Auditoria local (cruzada com `git status`):

- M: `news_collector.py`, `pipeline.py`, `http_fetch.py`, `validate_feeds.py`, `sources/sources.json`, `bm_enrich_sources.py`, `bm_transcript.py`, `upload_r2.py`, `batch_upload_r2.py`, `episode_image_manifest.py`, `youtube_captions.py`, `test_youtube_captions.py`, `test_youtube_thumbnail_identity.py`, `public/sw.js`, `LESSONS_LEARNED.md`
- ??: `recover_page.py`, `clean_screenshot.py`, `test_blocked_page_recovery.py`, `tests/test_schemas_and_metadata.py`, `SYSTEM_MAP.md`, `YOUTUBE_PIPELINE_MAP.md`, `docs/plans/reorganizacao-cirurgica/`
- **Não commitar:** `moss-tts-nano/`, `.env`, `credentials/`, `sources/cache.json`

```
[Working Tree Sujo]
       │
       ├──► Pacote A: Blocked Page Recovery & HTTP Fetch
       ├──► Pacote B: News Collector, Feeds & Pipeline Core
       ├──► Pacote C: Brasil e Mundo (Enrich & Transcripts)
       ├──► Pacote D: Upload R2 & Manifesto de Imagens
       ├──► Pacote E: Legendas e Identidade de Capas YouTube
       └──► Pacote F: sw.js (commit separado ou stash)
```

---

## 3. Passo a Passo de Execução Cirúrgica

### Pacote A: Recuperação de Páginas Bloqueadas (`blocked-page-recovery`)
1. **Arquivos envolvidos:**
   - `scripts/recover_page.py`
   - `scripts/http_fetch.py`
   - `scripts/test_blocked_page_recovery.py`
2. **Teste pré-commit** (caminho de arquivo, sem depender de `scripts/` ser pacote):
   ```bash
   cd /home/osmar/web-jornal-vale-da-liberdade
   .venv/bin/python -m unittest scripts/test_blocked_page_recovery.py
   ```
   `tests/test_schemas_and_metadata.py` **existe no disco** como untracked (`??`); ainda não está no git. Não é gate deste pacote — versionar só se o Dia 2/3 incluir testes de schema, senão deixa para um commit de testes depois.
3. **Commit:**
   ```bash
   git add scripts/recover_page.py scripts/http_fetch.py scripts/test_blocked_page_recovery.py
   git commit -m "feat(fetch): adiciona modulo de recuperacao de paginas bloqueadas e fallback http"
   ```

---

### Pacote B: Coletor de Notícias, Fontes e Pipeline Diário
1. **Arquivos envolvidos (só se `git status` mostrar `M`):**
   - `scripts/news_collector.py`
   - `scripts/pipeline.py`
   - `scripts/validate_feeds.py`
   - `sources/sources.json`
2. **Teste pré-commit:**
   ```bash
   cd /home/osmar/web-jornal-vale-da-liberdade
   .venv/bin/python -m py_compile scripts/news_collector.py scripts/pipeline.py scripts/validate_feeds.py
   ```
   `validate_feeds.py` bate na rede — **não** é gate obrigatório do commit. `public/sw.js` → Pacote F. `LESSONS_LEARNED.md` → commit de docs do **Dia 3**, não neste pacote.
3. **Commit:**
   ```bash
   git add scripts/news_collector.py scripts/pipeline.py scripts/validate_feeds.py sources/sources.json
   git commit -m "fix(collector): aprimora validacao de feeds e resiliencia da coleta diaria"
   ```

---

### Pacote C: Brasil e Mundo (Enriquecimento e Transcrições)
1. **Arquivos envolvidos:**
   - `scripts/bm_enrich_sources.py`
   - `scripts/bm_transcript.py`
   - `scripts/test_bm_enrich_sources.py` (já versionado; só incluir se o diff do enrich exigir)
2. **Teste pré-commit:**
   ```bash
   cd /home/osmar/web-jornal-vale-da-liberdade
   .venv/bin/python -m unittest scripts/test_bm_enrich_sources.py
   ```
3. **Commit:**
   ```bash
   git add scripts/bm_enrich_sources.py scripts/bm_transcript.py scripts/test_bm_enrich_sources.py
   git commit -m "feat(bm): atualiza pipeline de transcricao e enriquecimento de fontes BM"
   ```

---

### Pacote D: Upload R2 & Manifesto de Imagens
1. **Arquivos envolvidos (`M` confirmado):**
   - `scripts/upload_r2.py`
   - `scripts/batch_upload_r2.py`
   - `scripts/episode_image_manifest.py` (importado por `bm_mockup_video.py`)
2. **Teste pré-commit:**
   ```bash
   cd /home/osmar/web-jornal-vale-da-liberdade
   .venv/bin/python -m py_compile scripts/upload_r2.py scripts/batch_upload_r2.py scripts/episode_image_manifest.py
   ```
3. **Commit:**
   ```bash
   git add scripts/upload_r2.py scripts/batch_upload_r2.py scripts/episode_image_manifest.py
   git commit -m "fix(media): atualiza upload R2 e manifesto de imagens BM"
   ```

---

### Pacote E: Legendas e Identidade de Capas YouTube
1. **Arquivos envolvidos (`M` confirmado):**
   - `scripts/youtube_captions.py`
   - `scripts/test_youtube_captions.py`
   - `scripts/test_youtube_thumbnail_identity.py`
2. **Teste pré-commit** (caminho de arquivo):
   ```bash
   cd /home/osmar/web-jornal-vale-da-liberdade
   .venv/bin/python -m unittest scripts/test_youtube_captions.py scripts/test_youtube_thumbnail_identity.py
   ```
3. **Commit:**
   ```bash
   git add scripts/youtube_captions.py scripts/test_youtube_captions.py scripts/test_youtube_thumbnail_identity.py
   git commit -m "fix(youtube): atualiza legendas e testes de identidade de capa"
   ```

---

### Pacote F: `public/sw.js` — commit separado ou stash
- **Não** misturar com collector, R2 ou YouTube.
- Opção 1: commit atômico só do service worker, se a mudança for intencional e revisada.
- Opção 2: `git stash push -m "sw.js dia2" -- public/sw.js` e tratar depois (player/PWA, não pipeline).
- `LESSONS_LEARNED.md` **não** entra no Dia 2: vai no commit de docs do **Dia 3** (`git add LESSONS_LEARNED.md` junto de INDEX/SYSTEM_MAP).

---

### Órfãos — **não mover arquivo no Dia 2**
- `scripts/clean_screenshot.py`: órfão (canônico = `scripts/screenshots/`). Isolar **no papel** no Plano 03. Não `mv` para `archive/` ainda.
- `SYSTEM_MAP.md` / `YOUTUBE_PIPELINE_MAP.md`: untracked; entram no Plano 03 (docs).

---

## 4. Teste de Validação / Prova de Sucesso

Ao final da execução do Dia 2, o comando:
```bash
git status -s scripts/ sources/ public/
```
Deve retornar limpo em `scripts/` e `sources/` **exceto** o que o Plano 03 for documentar (`clean_screenshot.py` untracked pode permanecer até o mapa). `public/sw.js` ou foi commitado no Pacote F ou está no stash. `LESSONS_LEARNED.md` ainda pode aparecer `M` até o Dia 3.
