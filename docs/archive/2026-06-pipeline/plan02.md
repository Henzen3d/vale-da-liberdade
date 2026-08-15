<!-- [ARQUIVADO em 14/08/2026 — documento histórico, não reflete o estado atual do projeto. Ver CANONICAL.md e README.md para estado vigente.] -->
Plano de Execução — Revisão Técnica & Arquitetural (Web Jornal Vale da Liberdade)
Idioma: pt-BR | IA não-TTS: Hermes Agent inline | Gemini: só TTS | Nacional/Intl: feeds RSS curados | Formato: docs + código faseado.

Achados críticos (da auditoria de código feita)
Violação do constraint "Gemini=só TTS" — 2 usos não-TTS em gemini-2.5-flash:
scripts/ai_news_filter.py:133 (filtro, ranking 1-5, sumarização, categorização)
scripts/generate_script.py:211 (roteiro editorial com personas Peter/Ricardo)
TTS (generate_gemini_tts_multi.py, modelo gemini-3.1-flash-tts-preview) está correto.
Pipeline de aquisição com lacunas: content_hashes (dedup semântica) é scaffolding morto; zero clustering/correlação; zero breaking-news/trend; campo tier de credibilidade nunca lido; só fontes locais (0 nacional/internacional); x_collector.py (1273 linhas, funcional) desconectado.
Defeitos de áudio: [PAUSA] é removido do prompt e ignorado → zero efeito acústico; regra BR→B-R corrompe rodovias (BR-470→B-R-470, confirmado em produção); sem normalização de número/data/moeda além de dict de ~40 entradas; sem SSML/prosódia; loudnorm de passo único; CHUNK_TARGET_WORDS é código morto.
Regressão de produção: episódio 2026-06-20 saiu pelo caminho boilerplate _fill_roteiro_from_raw → 430 palavras, 3 quadros, reprovou o próprio checklist.
Doc inconsistente: .continue-here.md existe mas AGENT_GUIDE diz que foi removido; episodio sempre null; metadata hard-coded.
FASE 0 — Quick wins (High Impact / Low Effort)
0.1 Desativar _fill_roteiro_from_raw de caminhos ativos em pipeline.py cmd_process; falhar alto se generate_script falhar (em vez de emitir boilerplate que reprova).
0.2 Corrigir BR→B-R em tts_preprocessor.py: regex BR-\d+ preservado; soletrar só BR isolado.
0.3 Implementar dedup semântica (SimHash/MinHash) no content_hashes que já existe vazio.
0.4 Pausas reais: dividir texto nos marcadores e inserir silêncio via ffmpeg (resolve chunking morto).
0.5 Deletar .continue-here.md, consolidar handoffs em archive/handoffs/.
FASE 1 — Migrar IA não-TTS para Hermes Agent (coração do constraint)
1.1 ai_news_filter.py: remover Gemini; manter schemas Pydantic (NewsItem/NewsAnalysis) como contrato; split em camada determinística (scoring programático: geo, credibilidade via tier, recência, burst) + camada editorial (Hermes inline escreve raw-{date}.md a partir de _candidates-{date}.json). fallback_heuristic_filter vira fallback offline.
1.2 generate_script.py: remover Gemini; parse_raw()/format_script()/schema RoteiroCompleto viram renderer de roteiro-{date}.json→{date}.md. Hermes gera o JSON seguindo SKILL.md. cmd_process falha alto se faltar JSON.
1.3 Atualizar ARCHITECTURE.md, PRD.md, SKILL.md. Meta: grep gemini-2.5-flash scripts/ → vazio.
FASE 2 — Pipeline de aquisição robusto (High Impact / High Effort)
2.1 Credibilidade: usar tier + source_stats → credibility_score ponderado.
2.2 Clustering TF-IDF/MinHash: mesma notícia em 2+ fontes = 1 cluster (versão mais completa + fontes correlatas). Base da correlação multi-fonte.
2.3 Breaking-news: cluster em ≥3 fontes tier-1 em ≤6h ou termos de urgência → topo do roteiro. Trend: burst vs. média móvel 7d.
2.4 Conectar x_collector.py: consume_x_tweets_for_pipeline() já existe, só falta caller em cmd_collect; engajamento (likes/RT/views) = sinal viral.
2.5 Ranking programático: relevance = w1·geo + w2·credibilidade + w3·recência + w4·burst + w5·engajamento_x. Geo por dicionário ponderado (Blumenau=1.0, Alto Vale=0.8, SC=0.5).
2.6 Anti-fake: cross-validation (≥1 tier-1 OU ≥2 tier-2); flag single-source; regex anti-clickbait.
FASE 3 — Nacional/Internacional (High Impact / Medium Effort)
3.1 Adicionar feeds: nacional (G1, Folha, Estadão, Valor, CNN Brasil, BBC Brasil, Agência Brasil) + internacional (Reuters, AP, BBC World). Novo campo scope.
3.2 Ranking de impacto = f(reach, relevância econômica p/ SC, recência, alinhamento libertário). Cotas fixas: 1 nacional + 1 internacional. Filtro de impacto local.
3.3 Novos quadros BRASIL e MUNDO na sequência fixa. Atualizar categories_map, QUADROS, validação, TEMPLATE.md.
FASE 4 — Roteiro ideal (Medium Impact / Low Effort)
4.1 Estrutura: cold open (gancho, ≤30s) → manchetes → breaking-news (cond.) → quadros locais → Brasil → Mundo → Rapidinhas → fechamento.
4.2 Anti-repetição de transições (histórico em archive/transitions-used.json); adaptação de duração (loop self-check 2000-2500 palavras); priorização por score.
FASE 5 — Áudio/TTS avançado (High Impact / Medium Effort)
5.1 Normalização via num2words pt-BR: números, datas, anos, horas, moeda (R$ 70 mi→"setenta milhões de reais"), %.
5.2 sources/pronunciation_lexicon.json para toponímia (Blumenau, Rua XV, BR-470, Vale do Itajaí, Alesc, Furb).
5.3 Prosódia: investigar SSML/<prosody>/<emphasis> no modelo TTS; se indisponível, reforçar SPEAKER_PERSONAS.
5.4 Loudnorm 2-pass EBU R128; resample 24kHz→44.1kHz.
5.5 Implementar chunking (CHUNK_TARGET_WORDS=300) real: gerar por chunk, concatenar com crossfade, retomar só chunks falhados.
FASE 6 — Escalabilidade (High Impact / High Effort)
6.1 Multi-agente: Editor Regional (por cidade) + Editor Nacional/Intl (compartilhado) + Orquestrador Hermes (chief editor) + TTS Worker isolado.
6.2 Segmentação geo: config/regions/{region}.yaml (fontes, termos X, lexicon, pesos). Hoje: blumenau-vale-itajai.yaml.
6.3 Agregação replicável: nova cidade = novo YAML, zero código.
6.4 Esboço de personalização futura (listeners/, recomendação por similaridade).
6.5 Observabilidade: reports/daily-{date}.json — métricas técnicas (sucesso/fonte, latência, custo TTS, retry), editoriais (diversidade de fontes, relevância média, % breaking-news, continuidade), áudio (LUFS, true-peak, duração).
6.6 Fault-tolerance: dead-letter de fontes crônicas, checkpointing por etapa, idempotência por data.
Documentos (deliverables)
Doc	Ação	Conteúdo
REVIEW.md	criar	Avaliação atual: forças, fraquezas, gargalos, riscos
ROADMAP.md	criar	Matriz Impacto×Esforço das Fases 0-6
TARGET_ARCHITECTURE.md	criar	Arquitetura-alvo multi-agente + segmentação geo
IMPLEMENTATION_EXAMPLES.md	criar	JSON do roteiro, fórmula relevance, prompt editorial, cadeia ffmpeg 2-pass
ARCHITECTURE.md	atualizar	Hermes como motor não-TTS, x_collector conectado, quadros BR/Mundo
PRD.md	atualizar	Requisitos 2-3, estratégia nacional/internacional, roadmap
SKILL.md	atualizar	Execução pelo Hermes, quadros Brasil/Mundo, bulletin ideal, lexicon
LESSONS_LEARNED.md	atualizar	Regressão 2026-06-20, pausas ignoradas, BR-470, x_collector
Ordem de execução

text
Fase 0 (quick wins)  →  Fase 1 (Gemini→Hermes, pré-req)  →  Fase 2 (pipeline robusto)
                                                          ↘  Fase 3 (nacional/intl) ‖ Fase 4 (roteiro)
                                                          →  Fase 5 (áudio)  →  Fase 6 (escala)
Fase 0 + Fase 1 ≈ 70% do valor. Após aprovação, executo Fase 0 primeiro e reporto antes de seguir à Fase 1.

Confirmações ⚠️ Osmar endereçadas no plano
episodio null → auto-incremento na Fase 1 | Custo/ep em USD → telemetria Fase 6.5 | Analytics plays → painel Fase 6.5 | Deploy public/ → documentar | x_collector.py → conectar (é código vivo pronto).