# Validação final — reorganização cirúrgica (Dias 1–5)

> **Quando:** 2026-09-02 13:20 -03 (America/Sao_Paulo)
> **Repo:** `/home/osmar/web-jornal-vale-da-liberdade` @ `e67c8d8` (`main`, 7 commits à frente de `origin/main`)
> **Método:** testes estáticos e de importação. **Não** rodou `pipeline.py full`, **não** passou data ao wrapper, **não** executou `bm-hourly-pipeline.sh`, **não** fez upload.
> **Barra:** Diário 06:00 e Brasil e Mundo a cada 20 min amanhã sem intervenção humana, com log, áudio e vídeo.

---

## Resultado

| # | Subsistema | Status | Evidência |
|---|---|---|---|
| 1 | Gatilho diário | PASS | Job `74472bd658a5` `no_agent=true`, `script=vale-daily-cron-wrapper.sh`, `state=scheduled`, `next_run=2026-09-03T06:00:00-03:00`, `last_status=ok`. Shim `exec` no wrapper canônico. `bash -n` nos dois = 0. `.env` sourced no wrapper; chaves Gemini/R2 SET. |
| 2 | Pipeline diário | PASS | `py_compile` + import file-based (sem `__main__`) de `pipeline.py`, `news_collector.py`, `generate_roteiro_llm.py`, `tts_preprocessor.py`, `generate_gemini_tts_multi.py`, `publish_site.py` no HERMES_PY. `feedparser`, `google.genai`, `boto3` OK. `ffmpeg` = `/usr/bin/ffmpeg` 6.1.1. |
| 3 | Pipeline BM | PASS | `bash -n scripts/bm-hourly-pipeline.sh` OK. `bm_monitor.py` / `bm_pipeline.py` importam no HERMES_PY. `bm_mockup_video.py` / `youtube_uploader.py` importam no PROJECT_PY. Chromium Playwright em `~/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome` existe. |
| 4 | Screenshots | PASS | `screenshots.base` e `screenshots.runner` importam. 34/34 handlers em `scripts/screenshots/sites/` carregam. `try_handler_screenshot` em `bm_mockup_video.py` linha 121. |
| 5 | Thumbnails | PASS | PROJECT_PY: `youtube_thumbnail.generate_youtube_thumbnail` existe; `thumbnail_generator.py` e `episode_image_manifest.py` importam. |
| 6 | Storage & publicação | PASS | `upload_r2.py` importa. R2 vars SET (lens 32/32/64/20). `get_r2_client()` monta `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`. `publish_site.r2_public_domain()` e `r2_catalog_url()` resolvem; `SITE_URL` set. Sem upload. |
| 7 | Crons & jobs | PASS | Nenhum job **ativo** com `last_status=error`. Vitais `74472bd658a5` e `aefe99598bbe` scheduled. Zumbis `253558aea1e6` e `02e26ba9a2e9` paused. Crontab do host: só o coletor `*/5` de `/home/osmar/transito`. |
| 8 | Git & working tree | FIX→PASS | Antes: `?? YOUTUBE_PIPELINE_MAP.md`, `?? archive/backup_pre_cirurgico/`, `?? plano-equipe-jornalistica.md`. Depois do gitignore+commit: só `moss-tts-nano` (gitlink), `M scripts/bm_condensador.py`, `?? scripts/clean_screenshot.py`. Nenhum script de produção com `M`. |
| 9 | Docs & governança | PASS | `CANONICAL.md`, `docs/INDEX.md`, `SYSTEM_MAP.md` existem e estão no git. Banner histórico no topo de `ARCHITECTURE.md`, `ROADMAP.md`, `docs/PIPELINE_SCRIPTS_INVENTORY.md`. |

**Painel: 9/9 verde** (1 correção mínima no gitignore).

---

## 1. Gatilho diário

Job Hermes `web-jornal-vale-da-liberdade-daily` (`74472bd658a5`):

| Campo | Valor |
|---|---|
| `no_agent` | `true` |
| `script` | `vale-daily-cron-wrapper.sh` (resolve em `~/.hermes/scripts/`) |
| `schedule` | `0 6 * * *` |
| `workdir` | `/home/osmar/web-jornal-vale-da-liberdade` |
| `enabled` / `state` | true / scheduled |
| `last_status` | ok (2026-09-02 06:07 -03) |
| `next_run_at` | 2026-09-03T06:00:00-03:00 |

Shim (`~/.hermes/scripts/vale-daily-cron-wrapper.sh`, 775):

```
exec /home/osmar/web-jornal-vale-da-liberdade/scripts/cron-wrapper.sh "$@"
```

Wrapper real (`scripts/cron-wrapper.sh`, 775): `set -a; source "$PROJECT_DIR/.env"; set +a`; log em `logs/daily-$(date +%F).log`; Python = HERMES_PY `pipeline.py full --date`.

Comandos: `bash -n` shim e wrapper → `SHIM_SYNTAX_OK` / `WRAPPER_SYNTAX_OK`. `.env` presente; `GEMINI_API_KEY` e as quatro vars R2 = SET (valores não impressos).

---

## 2. Pipeline diário (sem executar)

Interpretador: `/home/osmar/.hermes/hermes-agent/venv/bin/python3`.

- `python3 -m py_compile` nos 6 scripts → `PY_COMPILE_OK`
- Import via `spec_from_file_location` (não dispara CLI): todos `IMPORT_OK`
- Deps no venv Hermes: `feedparser`, `google.genai`, `boto3`
- `ffmpeg` no PATH do sistema (não no venv): `/usr/bin/ffmpeg` 6.1.1

---

## 3. Pipeline BM (sem executar)

`scripts/bm-hourly-pipeline.sh` (Dia 5): cabeçalho canônico HERMES_PY vs PROJECT_PY; `bash -n` → `BM_SH_SYNTAX_OK`.

| Módulo | Runtime | Resultado |
|---|---|---|
| `bm_monitor.py` | HERMES_PY | IMPORT_OK |
| `bm_pipeline.py` | HERMES_PY | IMPORT_OK |
| `bm_mockup_video.py` | PROJECT_PY | IMPORT_OK |
| `youtube_uploader.py` | PROJECT_PY | IMPORT_OK |
| Playwright Chromium | PROJECT_PY | `CHROMIUM_EXISTS=True` |

Job `aefe99598bbe` (`web-jornal-brasil-mundo-hourly`): `no_agent=true`, `script=bm-hourly-pipeline.sh`, `*/20 * * * *`, scheduled, `last_status=ok`.

---

## 4. Screenshots

PROJECT_PY: `screenshots.base`, `screenshots.runner` OK. `HANDLER_FILES=34`, `HANDLERS_LOADED=34`, `HANDLERS_FAILED=[]`. `try_handler_screenshot` presente (lineno 121) e chamado no mockup (lineno 1105).

---

## 5. Thumbnails

PROJECT_PY:

- `IMPORT_OK youtube_thumbnail` + `GENERATE_YOUTUBE_THUMBNAIL=OK`
- `IMPORT_OK thumbnail_generator`
- `IMPORT_OK episode_image_manifest`

---

## 6. Storage & publicação

`.env` (nomes apenas): `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME` SET.

`upload_r2.get_r2_client()` → cliente boto3, endpoint `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`. Sem `list`/`put`.

`publish_site.r2_public_domain()` resolvido (True); `site_url()` resolvido; helpers `r2_catalog_url` presentes.

---

## 7. Crons & jobs

Jobs Hermes com `last_status=error`:

| ID | Nome | Ativo? |
|---|---|---|
| `253558aea1e6` | webjornal-scout-weekly | **não** — `enabled=false`, `state=paused` |
| `02e26ba9a2e9` | youtube-pipeline-lembrete | **não** — `enabled=false`, `state=paused` |

Vitais scheduled: `74472bd658a5` (diário 06:00), `aefe99598bbe` (BM */20). Autopilot legado `e5d6df754c19` continua paused.

Crontab do host (`crontab -l`):

```
*/5 * * * * cd /home/osmar/transito && python3 collector.py >> /home/osmar/transito/collector.log 2>&1
```

Nenhuma linha Vale em `/etc/cron.d` ou `/etc/crontab`.

---

## 8. Git & working tree

`git status -s` **antes** da correção:

```
 ? moss-tts-nano
 M scripts/bm_condensador.py
?? YOUTUBE_PIPELINE_MAP.md
?? archive/backup_pre_cirurgico/
?? plano-equipe-jornalistica.md
?? scripts/clean_screenshot.py
```

Gap: três paths untracked fora da allowlist. Nenhum script de produção com `M` (só `bm_condensador.py`, já previsto).

`git status -s` **depois**:

```
 ? moss-tts-nano
 M scripts/bm_condensador.py
?? scripts/clean_screenshot.py
```

`.env`, `credentials/`, `sources/cache.json` continuam ignorados (não aparecem).

---

## 9. Docs & governança

| Arquivo | Disco | `git ls-files` | Banner histórico |
|---|---|---|---|
| `CANONICAL.md` | sim | TRACKED | n/a (fonte viva) |
| `docs/INDEX.md` | sim | TRACKED | n/a (fonte viva) |
| `SYSTEM_MAP.md` | sim | TRACKED | n/a (mapa Dia 3) |
| `ARCHITECTURE.md` | sim | TRACKED | sim (L3–L4) |
| `ROADMAP.md` | sim | TRACKED | sim (L3–L4) |
| `docs/PIPELINE_SCRIPTS_INVENTORY.md` | sim | TRACKED | sim (L3–L4) |

Texto do banner: `DOCUMENTO HISTÓRICO / ARQUIVO` apontando para `CANONICAL.md` e `docs/INDEX.md`.

---

## Correções aplicadas

1. **`.gitignore`** — passou a ignorar `archive/backup_pre_cirurgico/`, `YOUTUBE_PIPELINE_MAP.md` (rascunho, `docs/INDEX.md` já o classifica como não-spec) e `plano-equipe-jornalistica.md`.
2. **Commit** `e67c8d8` — `chore(git): ignora snapshot cirurgico e rascunhos locais nao-spec` (1 arquivo, +5 linhas). Sem mudança de runtime.

Nenhum `.py` / `.sh` de produção foi alterado nesta validação.

---

## Pronto para amanhã (06:00 BRT)?

**Sim, no que esta validação cobre.** Os dois produtos estão armados:

- Diário: 2026-09-03 06:00 -03, `no_agent` → shim → `cron-wrapper.sh` → HERMES_PY `pipeline.py full`, log em `logs/daily-2026-09-03.log`.
- Brasil e Mundo: `*/20`, `no_agent` → `bm-hourly-pipeline.sh` (áudio no HERMES_PY, vídeo/upload no PROJECT_PY).

Prova viva (única que confirma áudio gerado + vídeo publicado) continua sendo o próprio ciclo: após 06:05, existir `logs/daily-2026-09-03.log` com `Daily build started` / `finished`; BM segue pelos logs `logs/bm-monitor.log` e o stdout do job `aefe99598bbe`.

Residual (não bloqueia o cron local): `main` está 7 commits à frente de `origin/main`. Produção lê o disco, não o remoto.

---

## O que esta validação não fez (de propósito)

- Não executou `pipeline.py full` nem `cron-wrapper.sh` com data.
- Não executou `bm-hourly-pipeline.sh` (processa fila e pode upload público).
- Não listou/enviou objetos no R2.
- Não regenerou catálogo via `publish_site.py`.
