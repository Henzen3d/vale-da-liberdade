# Web Jornal Vale da Liberdade

Podcast/jornal web diário de notícias locais de Blumenau, Alto Vale do Itajaí, Santa Catarina, Brasil e Mundo,
apresentado por dois locutores de personalidades opostas em tensão dialética: Peter (ancap radical)
e Ricardo (conservador racional). O viés editorial libertário é intencional — o produto nasceu
dessa perspectiva e não pretende ser "imparcial" no sentido jornalístico tradicional.

Para quem: ouvintes de Blumenau e região que querem notícias locais com análise opinativa,
crítica a gastos públicos e defesa da liberdade econômica.

## Quick Start

Dependências: `requirements.txt`
Variáveis: copie `.env.example` para `.env` e preencha `GEMINI_API_KEY`.

Comandos principais:
- `python scripts/pipeline.py init --date 2026-06-20` — cria/coleta raw + template de roteiro
- `python scripts/pipeline.py collect --date 2026-06-20` — apenas coleta/atualiza o raw
- `python scripts/pipeline.py process --date 2026-06-20` — renderiza roteiro JSON → MD, gera TTS, manchetes e metadados
- `python scripts/pipeline.py validate --date 2026-06-20` — valida contra checklist
- `python scripts/pipeline.py audio --date 2026-06-20` — gera áudio multi-locutor
- `python scripts/pipeline.py full --date 2026-06-20` — pipeline completo (process + validate + audio + archive)

Fluxo do roteiro:
1. `init` cria `raw-YYYY-MM-DD.md` (coleta automática opcional) + template `YYYY-MM-DD.md`
2. Hermes Agent lê o raw e gera `episodes/roteiro-YYYY-MM-DD.json`
3. `process` renderiza o JSON em roteiro final e gera artefatos TTS

Template de JSON para referência: `episodes/roteiro-template.json`
Prompt canônico: `python scripts/generate_script.py --print-prompt --date YYYY-MM-DD`

## Estrutura de pastas

```
├── archive/
│   ├── handoffs/          # Handoffs históricos (YYYY-MM-DD.md)
│   └── index.md           # Lista de episódios publicados
├── audio/                 # WAV e MP3 dos episódios
├── episodes/              # Roteiros diários + raw + metadados + roteiro-template.json
├── logs/                  # Logs do cron
├── scripts/               # Código fonte
├── sources/               # Config de fontes + cache
├── .env                   # GEMINI_API_KEY (não versionado)
├── .env.example
├── README.md
├── SKILL.md               # ⭐ Fonte canônica do roteiro e personagens
├── prompt.md              # Documento paralelo (ver nota em SKILL.md)
├── ARCHITECTURE.md
├── PRD.md
├── LESSONS_LEARNED.md
├── AGENT_GUIDE.md
└── requirements.txt
```

## Automação via cron

Agendamento: `0 6 * * *` (06:00 UTC)
Comando: `/home/osmar/web-jornal-vale-da-liberdade/scripts/cron-wrapper.sh`
O wrapper chama: `python scripts/pipeline.py full --date <data atual>`

## Pipeline Especial Brasil & Mundo (Vídeos de 5 Minutos)

Vídeos verticais/horizontais opinativos focados em um tema quente do dia, apresentados por Peter Albuquerque (~830 palavras, 5 minutos de áudio).

### Comandos Principais:
- Processar vídeo específico do YouTube (sob demanda):
  ```bash
  python scripts/bm_pipeline.py full --youtube-url "https://www.youtube.com/watch?v=XXXXX"
  ```
- Processar fila pendente do monitor:
  ```bash
  python scripts/bm_pipeline.py process-queue
  ```
- Baixar B-rolls de apoio visual (Pexels/Pixabay):
  ```bash
  python scripts/bm_broll_fetcher.py --query "politica brasilia congresso" --count 2
  ```

### Motor Visual & Retenção do Telespectador:
- **Gancho Inicial (Primeiros 15s):** 3 cortes rápidos de abertura (0-5s, 5-9s, 9-15s) combinando manchete, close de parágrafo e B-roll para prender a atenção e evitar abandono precoce do vídeo.
- **Mínimo de 10 Telas por Episódio:** Timeline dinâmica que impede telas estáticas por mais de 22s.
- **Multi-Shot por Matéria:** Captura dupla em Playwright (Hero da manchete + Detail rolado no parágrafo/gráfico), dobrando as telas reais sem precisar recorrer a links irrelevantes.
- **B-Roll Footage:** Vídeos gratuitos em 1080p (Pexels / Pixabay) e tweets do X inseridos contextualmente.
- **Relevância de Fontes (Qualidade > Quantidade):** Se a descrição do YouTube já contém fontes verificadas (>= 2), elas são suficientes. Fontes externas de RSS passam por filtro estrito de entidades (vetando termos genéricos e matérias com mais de 7 dias).

### Roadmap de Crescimento Orgânico:
- **Fase 1 (Atual):** Monitoramento automático do canal @ancapsu → transcrição → resumo analítico de 5 min → vídeo dinâmico.
- **Fase 2 (Sob Demanda):** Geração por URL avulsa do YouTube (`--youtube-url`).
- **Fase 3 (Agente Hermes Autônomo):** Criação de episódios a partir de comandos em linguagem natural (ex.: *"Faça um roteiro sobre a queda na bolsa de valores hoje"*), buscando fontes diretamente via Tavily/RSS e sintetizando o episódio completo.


## Problemas comuns

- **Roteiro JSON ausente:** `pipeline.py process` agora falha alto (exit 3) se `roteiro-YYYY-MM-DD.json` não existir. Gere o JSON via Hermes Agent antes de rodar `process`.
- **Falha da API Gemini (TTS):** `generate_gemini_tts_multi.py` faz 3 retries com backoff. Se falhar, o pipeline aborta na etapa de áudio.
- **ffmpeg ausente:** A geração de MP3 falha; apenas WAV é produzido.
- **Rate limit do X:** `x_collector.py` é tolerante a falhas; se cookies expirarem ou o X bloquear, o pipeline prossegue sem tweets.

Links para documentos:
- `SKILL.md` — regras de geração do roteiro e personagens
- `ARCHITECTURE.md` — fluxo ponta-a-ponta e schemas
- `PRD.md` — produto, escopo e roadmap
- `LESSONS_LEARNED.md` — incidentes e decisões técnicas
- `AGENT_GUIDE.md` — ordem de leitura para IAs retomando o projeto

## Fluxo de commits

Todo mudança aprovada pelo usuário ou validada autônoma em itens autorizados termina com commit real neste repositório:

```bash
cd /home/osmar/web-jornal-vale-da-liberdade
git add -A
git commit -m "feat: descrição da mudança"
git push
```

Nunca commitar:
- `.env` ou arquivos com chaves/tokens reais
- Arquivos maiores que 50MB (onnx, wav, mp3)
- `node_modules/`, `.venv/`, `venv_win/`

---
*Mantido por: Hermes Agent | Última atualização: 2026-06-22*
