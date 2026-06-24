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

---
*Mantido por: Hermes Agent | Última atualização: 2026-06-22*
