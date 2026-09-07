# 02 — Saneamento da Raiz e Segurança do Repositório

> **Foco:** Limpeza, segurança de credenciais e eliminação de artefatos pesados da raiz.  
> **Status:** PLANEJADO (Pronto para execução atômica)  
> **Adaptação servidor:** 2026-09-02 — OAuth já em `credentials/`; vários `mv` do rascunho original apontam para paths inexistentes.  
> **Risco:** Quase zero (nenhum script de produção depende de binários ou backups da raiz).  
> **Diretriz de Segurança:** Não republicar client IDs. Arquivar antes de deletar. Pular paths já ausentes.

---

## 1. Diagnóstico dos Problemas na Raiz

A raiz do repositório foi utilizada como "área de rascunho rápido" ao longo de meses de vibe coding, acumulando:

1. **Vazamento Potencial de Credenciais:**
   - **Já resolvido no disco.** Não há `client_secret*.json` na raiz. Canônico: `credentials/client_secret.json` (+ slots). `youtube_uploader.py` já usa `CRED_DIR = ROOT / "credentials"`. `.gitignore` já ignora `credentials/`. **Não listar client IDs neste plano.**
2. **Gigabytes de Binários e Áudios Órfãos (ainda na raiz, já gitignored):**
   - `pt_BR-faber-medium.onnx` e seu `.json`.
   - `kokoro-v1.0.onnx`.
   - `edge.mp3` e `piper.wav`.
3. **Scripts "Gêmeos" Duplicados (Raiz vs `scripts/`):**
   - Na raiz (existem): `run_audio.py`, `run_pipeline_today.py`, `run_process.py`, `run_publish.py`, `process_today.py`, `serve.py`.
4. **Pastas zumbis:**
   - **Existem:** `new-ux.backup-20260806/`, `site/`, `thumbnail-generetor/`, `kokoro_work/`, `test_output/`, `persona_suggestions/`.
   - **Não existem — não `mv`:** `BACKUP-web-jornal-vale-da-liberdade/`, `new-ux/`.
5. **Documentação na raiz:** 22 `.md` (não 30+). `YOUTUBE_PIPELINE_MAP.md` e `plano-equipe-jornalistica.md` já estão no `.gitignore`.

---

## 2. Plano de Ação Cirúrgico

### Etapa 1: Blindagem de Segredos e OAuth

**Já feito.** Confirmar (não mover de novo):

```bash
test -f credentials/client_secret.json && echo SECRET_OK
test ! -e client_secret*.json && echo ROOT_CLEAN
grep -n 'credentials/' .gitignore
```

`youtube_uploader.py` já busca em `credentials/` via `youtube_quota.client_secret_path(slot)`. Só alterar o uploader se um `ls` mostrar secret ainda fora de `credentials/`.

Opcional: garantir `client_secret*.json` no `.gitignore` da raiz (defesa em profundidade). **Não** commitar secrets.

---

### Etapa 2: Expurgar Binários e Áudios Temporários

1. Mover os modelos ONNX legados para quarentena ou descarte (eles não são usados pelo motor oficial que é o Gemini TTS):
   ```bash
   mkdir -p archive/legacy_models/
   mv pt_BR-faber-medium.onnx* archive/legacy_models/
   mv kokoro-v1.0.onnx archive/legacy_models/
   ```
2. Deletar áudios temporários soltos na raiz:
   ```bash
   rm -f edge.mp3 piper.wav
   ```

---

### Etapa 3: Saneamento dos Scripts Duplicados da Raiz

Os wrappers canônicos de produção usam estritamente o diretório `scripts/` (ex: `scripts/pipeline.py`, `scripts/cron-wrapper.sh`, `scripts/bm-hourly-pipeline.sh`).

1. Para os scripts `run_audio.py`, `run_pipeline_today.py`, `run_process.py`, `run_publish.py`, `process_today.py` e `serve.py` na raiz:
   - Comparar com `scripts/` correspondente.
   - Remover as cópias soltas na raiz OU transformá-las em atalhos de 3 linhas que apenas chamam o script oficial em `scripts/`:
     ```python
     # run_pipeline_today.py (shim de conveniência)
     import subprocess, sys
     from pathlib import Path
     target = Path(__file__).resolve().parent / "scripts" / "run_pipeline_today.py"
     sys.exit(subprocess.run([sys.executable, str(target)] + sys.argv[1:]).returncode)
     ```
   - Opcionalmente (mais limpo): remover completamente da raiz para forçar o uso da pasta canônica `scripts/`.

---

### Etapa 4: Quarentena e Remoção de Diretórios Zumbis

Mover **somente pastas que existirem**. `test -d` antes de cada `mv`. Não criar `new-ux/` para depois arquivar.

```bash
mkdir -p archive/quarantine_2026/
for d in new-ux.backup-20260806 site thumbnail-generetor kokoro_work test_output persona_suggestions; do
  if [ -e "$d" ]; then mv "$d" archive/quarantine_2026/; else echo "SKIP absent $d"; fi
done
# NÃO: BACKUP-web-jornal-vale-da-liberdade (ausente)
# NÃO: new-ux (ausente; vale-repo-orientation proíbe recriar)
```

> **Verificação:** Rodar `git status` e conferir se nenhuma dependência de `public/` ou `scripts/` foi afetada.

---

### Etapa 5: Organização da Documentação na Raiz

Preservar na raiz os documentos institucionais canônicos:
- `README.md`, `CANONICAL.md`, `SYSTEM_MAP.md`, `SKILL.md`, `AGENT_GUIDE.md`, `LESSONS_LEARNED.md`, `PRD.md`
- `ARCHITECTURE.md` e `ROADMAP.md` (já com banner histórico apontando para `docs/INDEX.md`)

Só mover o que **existir** e não estiver no `.gitignore`. Relatórios `IMAGEN4_TEST_REPORT.md` / `NIM_TEST_REPORT.md` / `TEST_REPORT.md` já estão no `.gitignore` — não falhar o `mv` se ausentes.

```bash
mkdir -p docs/reports/models/ docs/archive/
for f in IMAGEN4_TEST_REPORT.md NIM_TEST_REPORT.md MODEL_TEST_REPORT.md MODEL_TEST_REPORT.json TEST_REPORT.md free-api.md; do
  [ -f "$f" ] && mv "$f" docs/reports/models/ || echo "SKIP $f"
done
for f in plan.md plan02.md plano-admin-dashboard.md plano-brasil-e-mundo-webjornal.md PLANO_AUDITORIA_WEBJORNAL.md prompt.md TODO-defuddle-integration.md TODO-youtube-integration.md; do
  [ -f "$f" ] && mv "$f" docs/archive/ || echo "SKIP $f"
done
# plano-equipe-jornalistica.md e YOUTUBE_PIPELINE_MAP.md já gitignored — não versionar
```

---

## 3. Resultado Esperado da Raiz

Uma raiz limpa, profissional e auditável:

```
web-jornal-vale-da-liberdade/
├── .env.example
├── .gitignore
├── CANONICAL.md
├── LESSONS_LEARNED.md
├── README.md
├── SYSTEM_MAP.md
├── config/
├── credentials/          (ignorado no git)
├── docs/
├── episodes/
├── output/
├── public/
├── scripts/
├── sources/
└── tests/
```
