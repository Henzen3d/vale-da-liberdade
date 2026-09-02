# Plano 03 — Mapa de Vida dos Componentes (VIVO / MORTO / NÃO TOCAR)

> **Fase:** Dia 3  
> **Prioridade:** MÉDIA-ALTA (Cria clareza operacional e impede trabalho em código zumbi)  
> **Escopo:** Documentação de Governança e Mapeamento de Arquivos  
> **Regra:** **Nenhum arquivo físico deve ser deletado** nesta fase. O isolamento é feito estritamente no papel e na documentação canônica.

---

## 1. Contexto e Diagnóstico

O repositório acumulou 103+ scripts `.py`, 3 gerações de renderização de vídeo e 3 estruturas de geração de thumbnail. A coexistência desses arquivos confunde novos agentes e desenvolvedores, gerando tentativas de "otimizar" scripts que não estão em produção.

---

## 2. Matriz Canônica de Componentes

### 🟢 Módulos VIVOS (Produção Ativa — NÃO MEXER SEM TESTE RIGOROSO)

| Subsistema | Fluxo Canônico em Produção | Arquivos Principais |
|---|---|---|
| **Diário (06:00)** | Coleta ➔ Roteiro ➔ TTS Multi ➔ Publicação | [scripts/pipeline.py](file:///j:/Arquivos%20Osmar/Hermes/web-jornal-vale-da-liberdade/scripts/pipeline.py)<br>[scripts/news_collector.py](file:///j:/Arquivos%20Osmar/Hermes/web-jornal-vale-da-liberdade/scripts/news_collector.py)<br>[scripts/generate_roteiro_llm.py](file:///j:/Arquivos%20Osmar/Hermes/web-jornal-vale-da-liberdade/scripts/generate_roteiro_llm.py)<br>[scripts/generate_script.py](file:///j:/Arquivos%20Osmar/Hermes/web-jornal-vale-da-liberdade/scripts/generate_script.py)<br>[scripts/tts_preprocessor.py](file:///j:/Arquivos%20Osmar/Hermes/web-jornal-vale-da-liberdade/scripts/tts_preprocessor.py)<br>[scripts/generate_gemini_tts_multi.py](file:///j:/Arquivos%20Osmar/Hermes/web-jornal-vale-da-liberdade/scripts/generate_gemini_tts_multi.py)<br>[scripts/publish_site.py](file:///j:/Arquivos%20Osmar/Hermes/web-jornal-vale-da-liberdade/scripts/publish_site.py)<br>[scripts/upload_r2.py](file:///j:/Arquivos%20Osmar/Hermes/web-jornal-vale-da-liberdade/scripts/upload_r2.py) |
| **Brasil & Mundo (BM)** | Monitor RSS ➔ Fila ➔ Mockup Vídeo ➔ Upload YT | [scripts/bm_monitor.py](file:///j:/Arquivos%20Osmar/Hermes/web-jornal-vale-da-liberdade/scripts/bm_monitor.py)<br>[scripts/bm_pipeline.py](file:///j:/Arquivos%20Osmar/Hermes/web-jornal-vale-da-liberdade/scripts/bm_pipeline.py)<br>[scripts/bm_condensador.py](file:///j:/Arquivos%20Osmar/Hermes/web-jornal-vale-da-liberdade/scripts/bm_condensador.py)<br>[scripts/bm_enrich_sources.py](file:///j:/Arquivos%20Osmar/Hermes/web-jornal-vale-da-liberdade/scripts/bm_enrich_sources.py)<br>[scripts/bm_mockup_video.py](file:///j:/Arquivos%20Osmar/Hermes/web-jornal-vale-da-liberdade/scripts/bm_mockup_video.py)<br>[scripts/youtube_uploader.py](file:///j:/Arquivos%20Osmar/Hermes/web-jornal-vale-da-liberdade/scripts/youtube_uploader.py) |
|| **Screenshots Jornalísticos** | Motor modular + handlers por domínio | `scripts/screenshots/base.py`<br>`scripts/screenshots/runner.py`<br>`scripts/screenshots/sites/`<br>`try_handler_screenshot` em `bm_mockup_video.py` (não existe `scripts/screenshots/core/`) |
|| **Thumbnails Canônicos** | Diário: `thumbnail_generator.py`. **Ambos VIVOS, papéis distintos:** `youtube_thumbnail.py` = produção (importado por `bm_mockup_video.find_episode_thumbnail` → `generate_youtube_thumbnail`). `hermes_youtube_thumbnail.py` = CLI manual/auxiliar (não é o import do mockup). | `scripts/thumbnail_generator.py`<br>`scripts/youtube_thumbnail.py` (VIVO produção)<br>`scripts/hermes_youtube_thumbnail.py` (VIVO CLI) |
| **Gatilhos Oficiais** | Wrappers de execução | [scripts/cron-wrapper.sh](file:///j:/Arquivos%20Osmar/Hermes/web-jornal-vale-da-liberdade/scripts/cron-wrapper.sh)<br>[scripts/bm-hourly-pipeline.sh](file:///j:/Arquivos%20Osmar/Hermes/web-jornal-vale-da-liberdade/scripts/bm-hourly-pipeline.sh) |

---

### 🔴 Módulos MORTOS / PARALELOS / LEGADOS (NÃO LIGAR, NÃO OTIMIZAR)

Estes arquivos **não são chamados pelos cron-wrappers oficiais** e devem ser tratados como legado:

| Componente | Motivo / Diagnóstico | Ação no Plano |
|---|---|---|
| `scripts/bm_video_autopilot.py` | Substituído pelo fluxo canônico do `bm-hourly-pipeline.sh` + `bm_mockup_video.py` | Manter job pausado, marcar cabeçalho como legado |
| `scripts/faceless_*.py` | Prova de conceito de 22/08 (autopilot não ativado) | Marcar como legado em `archive/legacy_scripts/` |
| `scripts/youtube_video_generator.py` | Renderizador de vídeo de geração anterior | Marcar como legado |
| `references/youtube/prototype/` | Protótipo HyperFrames bancada-render | Manter apenas como referência de design |
| `scripts/clean_screenshot.py` | Versão órfã monolítica (substituída por `scripts/screenshots/`) | Isolar |
|| `thumbnail-generetor/` | Pasta aninhada com typo e código legado | Isolar no papel |
|| `scripts/cron-wrapper-v2.sh`, `cron-daily.sh`, `daily-collect.sh` | Wrappers antigos; o diário oficial após Plano 01 é `cron-wrapper.sh` via Hermes | Marcar como obsoletos |
| `~/.hermes/skills/web-jornal-production` vs `.../content/web-jornal-production` | Skill duplicada | Declarar `content/web-jornal-production` como única |

---

## 3. Fontes Canônicas da Verdade (Governança de Docs)

Para evitar que a documentação minta ou desvie do código real, fica estabelecida a seguinte hierarquia de documentação:

1. **DOCUMENTAÇÃO OFICIAL (FONTE DA VERDADE):**
   - `CANONICAL.md`
   - `docs/INDEX.md`
   - `docs/BM-VIDEO-LAYOUT.md` (só layout visual do mockup — **não** é o lugar de venv/cron)
   - `~/.hermes/skills/content/web-jornal-production/SKILL.md`

2. **DOCUMENTAÇÃO HISTÓRICA / ARQUIVO (NÃO USAR COMO SPEC):**
   - `docs/PIPELINE_SCRIPTS_INVENTORY.md` (Inventário de agosto com crontab antigo).
   - `ARCHITECTURE.md` e `ROADMAP.md` na raiz (versões conceituais de junho).
   - `SYSTEM_MAP.md` e `YOUTUBE_PIPELINE_MAP.md` (úteis, mas exigem marcação de status).

---

## 4. Passo a Passo de Execução Cirúrgica

1. **Inserir banner de aviso em documentos históricos:**
   Adicionar no topo de `docs/PIPELINE_SCRIPTS_INVENTORY.md`, `ARCHITECTURE.md` e `ROADMAP.md`:
   ```markdown
   > ⚠️ **DOCUMENTO HISTÓRICO / ARQUIVO**: Este documento reflete o estado em Junho/Agosto de 2026.
   > Para especificações ativas e regras de produção, consulte `CANONICAL.md` e `docs/INDEX.md`.
   ```
2. **Atualizar `docs/INDEX.md` e `SYSTEM_MAP.md`** com as tabelas de VIVO / MORTO acima.
3. **Commit da Documentação de Governança:**
   ```bash
   git add docs/ CANONICAL.md SYSTEM_MAP.md LESSONS_LEARNED.md
   git commit -m "docs: estabelece mapa canonico de subsistemas vivos e marca legados"
   ```
