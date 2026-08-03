# PRD — Web Jornal Vale da Liberdade

## Missão e proposta de valor

Entregar um podcast/web jornal diário de notícias locais, nacionais e internacionais (Blumenau, Alto Vale, SC, Brasil e Mundo) com curadoria automatizada e análise opinativa em tensão dialética entre dois apresentadores de personalidades opostas. O diferencial não é a apuração primária — é a combinação de curadoria por IA + viés
editorial consistente (lente libertária) + personalidades carregadas.

## Público-alvo

- Ouvintes de Blumenau e Vale do Itajaí (SC)
- Interessados em política local, gastos públicos, transparência, liberdade econômica
- Faixa etária estimada: 25-55 anos
- Distribuição atual: site estático (`public/`), distribuição planejada via Nginx + Cloudflare Tunnel

## Personas dos apresentadores

Ver `SKILL.md` seções 5 e 6 para as fichas completas. Resumo:

- **Peter Albuquerque (45)** — ex-advogado tributário, ancap radical, irônico, provoca,
  questiona toda ação estatal, usa linguagem acadêmica + popular.
- **Ricardo Souto (46)** — economista, ponderado, traz dados e contraponto pragmático,
  equilibra Peter sem abandonar o viés de liberdade.

## Escopo

**É:**
- Curadoria automatizada de notícias via RSS/scraping + filtro IA
- Geração de roteiro em diálogo entre Peter e Ricardo
- Síntese de voz multi-locutor (Gemini TTS) com pós-processamento ffmpeg
- Publicação diária em `.mp3` + índice em `archive/index.md`

**Não é:**
- Apuração jornalística primária
- Substituição de fontes oficiais
- Conteúdo informativo neutro/busca de "equilíbrio" jornalístico tradicional

## Requisitos funcionais

1. **Coleta automatizada** — RSS + scraping de 14 fontes locais, deduplicação por URL cache
2. **Filtro e categorização IA** — Gemini classifica em 6 quadros + nota de qualidade
3. **Geração de roteiro** — diálogo Peter/Ricardo por quadro, estrutura fixa
4. **Pré-processamento TTS** — expansão de siglas, remoção de markdown, inserção de pausas
5. **Geração de áudio multi-locutor** — Gemini TTS com vozes Charon/Schedar
6. **Pós-processamento** — highpass, compressor, equalizer, loudnorm via ffmpeg
7. **Validação** — checklist automatizado (manchetes, quadros obrigatórios, saudações, duração)
8. **Publicação** — atualização de `archive/index.md`

## Requisitos não-funcionais

- **Custo por episódio:** Gemini API (filtro + roteiro + TTS). `⚠️ A confirmar com Osmar`
  o custo exato por episódio em dólares.
- **Tolerância a falhas:** retry com backoff exponencial (3 tentativas) na API Gemini;
  fallback heurístico no filtro; auto-preenchimento do roteiro a partir do raw quando o
  `generate_script.py` não é chamado.
- **Duração-alvo:** 15 minutos (~2.000–2.500 palavras)
- **Cron:** executa diariamente às 06:00 UTC via `cron-wrapper.sh`

## Métricas de sucesso

- Episódios publicados / semana (atual: meta 7/7)
- Checklist de `SKILL.md` passando (todos os quadros obrigatórios, sem saudações, duração ok)
- Taxa de sucesso de coleta por fonte (rastreada em `cache.json` source_stats)
- Retenção/plays — `⚠️ A confirmar com Osmar` se há analytics configurado

## Roadmap

1. ~~Coleta automatizada~~ — concluído, 30+ fontes operando (locais + nacionais + internacionais)
2. ~~Filtro IA + Categorização~~ — concluído com scoring de credibilidade e relevância
3. ~~Geração de roteiro~~ — concluído via `generate_script.py` + `pipeline.py init`
4. ~~TTS multi-locutor~~ — concluído com chunking, pausas reais e EBU R128 2-pass
5. ~~Corrigir duplicação de notícia~~ — resolvido; `_fill_roteiro_from_raw` desativado, roteiro via JSON
6. ~~Integrar `x_collector.py`~~ — concluído, integração resiliente no pipeline
7. ~~Rate limiting Gemini~~ — concluído (`GeminiClient` com RPM/RPD/TPM + backoff exponencial)
8. ~~Portal web dinâmico com player, transcrição, Auth Supabase e R2~~ — concluído (Fase 7 do ROADMAP)
9. Distribuição em plataformas de podcast (feed RSS automático) — planejado (Fase 8 do ROADMAP)

10. Engine TTS híbrida local (Kokoro/Piper, custo zero) — planejado (Fase 9 do ROADMAP)
11. Chat interativo com personas Peter/Ricardo no portal — planejado (Fase 10 do ROADMAP)
12. Sonoplastia, vinhetas e inserção de anúncios (Monetização) — planejado (Fase 11 do ROADMAP)

> Ver `ROADMAP.md` para planos detalhados de execução de cada fase.

---
*Mantido por: Hermes Agent | Última atualização: 2026-06-24*
