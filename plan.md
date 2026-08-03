Plano de Execução — Revisão Técnica & Arquitetural do Web Jornal Vale da Liberdade
Idioma: todos os deliverables em pt-BR (decisão confirmada). Motor de IA não-TTS: Hermes Agent (inline) — Gemini restrito a TTS (decisão confirmada). Cobertura nacional/internacional: feeds RSS curados (decisão confirmada). Formato: documentos + plano de código em fases sequenciais executáveis.

Este plano produz 5 deliverables solicitados (Avaliação Atual, Roadmap Priorizado, Arquitetura-Alvo, Exemplos de Implementação, Recomendações Estratégicas) na forma de documentação markdown atualizada mais um refactor de código faseado. Cada fase é independentemente shippável.

Achados críticos que o plano corrige (resumo da auditoria)
1. Violação do约束 "Gemini = só TTS" — dois usos não-TTS ativos:

scripts/ai_news_filter.py:133 → gemini-2.5-flash (filtro, categorização, ranking 1-5, sumarização)
scripts/generate_script.py:211 → gemini-2.5-flash (roteiro editorial com personas Peter/Ricardo)
2. Pipeline de aquisição com lacunas: content_hashes (dedup semântica) é scaffolding morto; zero clustering/correlação de eventos; zero detecção de breaking-news/trend; campo tier de credibilidade nunca lido; apenas fontes locais (0 nacional/internacional); x_collector.py (1273 linhas, totalmente funcional) completamente desconectado do pipeline.

3. Defeitos reais de áudio/TTS: marcadores [PAUSA]/[PAUSA_CURTA] são removidos do prompt antes do TTS e explicitamente ignorados → zero efeito acústico; regra genérica BR→B-R corrompe códigos de rodovia (BR-470→B-R-470, confirmado em produção); nenhuma normalização de número/data/ano/hora além de um dict estático de ~40 entradas; sem SSML/prosódia/ênfase; loudnorm de passo único (sem EBU R128 de 2 passos); CHUNK_TARGET_WORDS (chunking) é código morto — episódio inteiro numa chamada.

4. Regressão de qualidade em produção: episódio 2026-06-20 saiu pelo caminho boilerplate (_fill_roteiro_from_raw, código morto/mantenido-como-fallback) → 430 palavras, 3 quadros, falha no próprio checklist de validação (sem Educação, sem Esportes, sem viés libertário). O _fill_roteiro_from_raw nunca deveria ter produzido o roteiro final.

5. Inconsistências de doc: .continue-here.md existe fisicamente apesar de AGENT_GUIDE dizer que foi removido; episodio sempre null; campos de metadata hard-coded (fontes_utilizadas, noticias_com_continuidade).

FASE 0 — Correções de segurança & quick wins (High Impact / Low Effort)
Objetivo: eliminar defeitos que já estão degradando o produto hoje, sem arquitetura nova.

0.1 Desativar o caminho boilerplate que regrediu o 2026-06-20
Em scripts/pipeline.py, cmd_process (~L425): o try/except que chama generate_script atualmente cai para manter o template, mas em produção o template foi preenchido por _fill_roteiro_from_raw num fluxo anterior. Remover a chamada a _fill_roteiro_from_raw de qualquer caminho ativo; deixá-lo apenas como função marcada @deprecated com raise NotImplementedError ou delete após confirmação (conforme LESSONS_LEARNED já sugere).
Garantir que cmd_process falhe alto (exit non-zero + log claro) se generate_script falhar, em vez de silenciosamente emitir um roteiro de 430 palavras que reprova a validação.
0.2 Corrigir a corrupção de rodovias no TTS
Em scripts/tts_preprocessor.py, TTS_SUBSTITUTIONS: a regra BR→B-R está convertendo BR-470 em B-R-470. Trocar por regex que preserva códigos de rodovia: BR-\d+ → mantém; só soletrar BR isolado. Adicionar alias explícito para rodovias regionais (BR-470, BR-101, BR-116, SC-470, etc.) se a soletração numérica sair melhor.
0.3 Implementar a dedup que já está scaffoldada
content_hashes em sources/cache.json existe mas é {}. Implementar hash SimHash/MinHash do conteúdo no news_collector.collect_all_news para dedup semântica além da URL (captura a mesma notícia em URLs diferentes entre os 14 portais).
0.4 Tornar os marcadores de pausa acousticamente reais
generate_gemini_tts_multi.py:build_prompt (L92) faz re.sub removendo [PAUSA] e diz "IGNORE". Em vez disso: dividir o texto nos marcadores de pausa, gerar áudio por segmento e inserir silêncio real (1,5s / 0,5s) via ffmpeg na cadeia de pós-processamento. (Isto também resolve o chunking morto — ver Fase 3.)
0.5 Doc: sincronizar AGENT_GUIDE vs realidade
.continue-here.md existe mas AGENT_GUIDE L18 diz "não existe mais". Decisão: deletar .continue-here.md e consolidar handoffs em archive/handoffs/YYYY-MM-DD.md (convenção já estabelecida). Atualizar AGENT_GUIDE.
Entrega Fase 0: episódios deixam de regredir para boilerplate; áudio não corrompe BR-470; dedup semântica funciona; pausas têm efeito real.

FASE 1 — Migrar IA não-TTS para Hermes Agent (High Impact / High Effort) — o coração do constraint
Objetivo: eliminar todos os usos não-TTS do Gemini. O Hermes Agent (durante cada execução do pipeline) assume filtro, ranking, sumarização e geração de roteiro inline, escrevendo resultados em arquivos estruturados. Gemini permanece apenas em generate_gemini_tts_multi.py.

1.1 Converter ai_news_filter.py em motor determinístico + contrato de agente
Manter o schema Pydantic (NewsItem, NewsAnalysis) — ele é o contrato de dados entre coleta e roteiro.
Remover o bloco Gemini (L19-20 imports, L84 init, L131-141 chamada).
Substituir a função filter_and_categorize_news por duas camadas:
Camada determinística (código): scoring programático que hoje não existe — relevância geográfica por keywords ponderadas, scoring de credibilidade por fonte (usar tier que está morto), detecção de breaking-news por recência/velocidade, clustering por similaridade (ver Fase 2). Produz NewsAnalysis parcial.
Camada editorial (Hermes Agent inline): o pipeline.py cmd_collect, ao final, delega ao Hermes Agent a seleção final + sumarização + key_points ricos. Isto é feito expondo um arquivo de input (episodes/_candidates-{date}.json) que o agente lê, e produzindo raw-{date}.md seguindo o contrato. O fallback_heuristic_filter existente (L175) torna-se o fallback offline (sem agente, sem Gemini) para quando o Hermes não estiver disponível.
Decisão de orquestração: introduzir um subcomando pipeline.py collect --handoff que para após escrever _candidates-{date}.json e registra um handoff pointer em archive/handoffs/ para o Hermes Agent retomar a seleção editorial.
1.2 Converter generate_script.py em template/renderer puro
Remover o bloco Gemini (L17-18 imports, L209 init, L211-219 chamada).
A geração do roteiro (diálogo Peter/Ricardo) passa a ser responsabilidade do Hermes Agent, usando SKILL.md como fonte canônica de regras (personas, quadros, tom, checklist — já está completo em SKILL.md seções 4-9).
Manter parse_raw(), format_script() e o schema RoteiroCompleto — eles são o contrato de formatação. O Hermes Agent produz o RoteiroCompleto (em JSON) e format_script() o renderiza para markdown.
Expor generate_script.render_from_json(path) que lê um roteiro-{date}.json (escrito pelo agente) e emite {date}.md. O pipeline.py cmd_process chama este renderer; se o JSON não existir, falha alto (não cai para boilerplate).
1.3 Atualizar documentação de arquitetura
ARCHITECTURE.md: o fluxo ponta-a-ponta muda — o passo "Gemini filtro" vira "Hermes Agent (determinístico + editorial)", e "Gemini roteiro" vira "Hermes Agent (renderiza JSON→MD)".
PRD.md: requisito funcional 2 e 3 reescritos para refletir Hermes como motor.
SKILL.md: nota de que a skill é executada pelo agente Hermes, não por chamada Gemini.
Entrega Fase 1: zero chamadas Gemini fora de TTS. Contratos de dados preservados. grep -ri "gemini-2.5-flash" scripts/ retorna vazio.

FASE 2 — Pipeline de aquisição robusto (High Impact / High Effort)
Objetivo: endereçar cada lacuna listada no briefing (regional, duplicatas, clustering, breaking-news, viral, credibilidade, relevância, trend, correlação multi-fonte, fake-news).

2.1 Scoring de credibilidade de fonte (usar tier que está morto)
Em news_collector.py e no novo scoring determinístico da Fase 1.1: cada artigo herda tier da fonte; source_stats (já coleta success_count, avg_items_per_fetch) alimenta um credibility_score = f(tier, success_rate, frescura). Fontes tier-1 (ND+, O Blumenauense, etc.) pesam mais.
2.2 Clustering de eventos / correlação multi-fonte
Implementar clustering por similaridade de título+resumo (TF-IDF cosine ou MinHash — MinHash já é leve e compatível com a dedup SimHash da Fase 0.3). Mesma notícia em 2+ fontes → um cluster com a versão mais completa + lista de fontes correlatas. Isto também é o input para "multi-source correlation" e reduz duplicação percebida pelo ouvinte.
2.3 Detecção de breaking-news e trend
Breaking-news: flag quando um cluster aparece em ≥3 fontes tier-1 numa janela de ≤6h, ou contém termos de urgência (urgente, agora, ao vivo, modalidade). Promove ao topo do roteiro.
Trend/velocity: contar menções por tema nas últimas 24h vs. média móvel de 7 dias; score de burst.
2.4 Detecção de viral (X/Twitter)
Conectar o x_collector.py (hoje desconectado). O .continue-here.md mostra que ele está pronto: consume_x_tweets_for_pipeline() (L1004) já existe, só falta um caller. Adicionar chamada em pipeline.py cmd_collect que mescla tweets consolidados nos candidatos. Usar métricas de engajamento (likes/retweets/views, já parseadas em _parse_metric) como sinal de viralidade.
2.5 Ranking de relevância local programático
Substituir o quality_score puramente-LLM por uma fórmula: relevance = w1*geo_match + w2*credibility + w3*recency_decay + w4*burst + w5*engagement_x. Geo_match por dicionário ponderado de entidades (Blumenau=1.0, Rio do Sul/Indaial/Pomerode=0.8, SC=0.5, nacional-com-impacto=0.3). O Hermes Agent faz o ajuste editorial final por cima.
2.6 Redução de risco de fake-news
Cross-validation: notícia só entra se confirmada por ≥1 fonte tier-1 OU ≥2 fontes tier-2 (usa o clustering da 2.2). Flag de single-source para revisão editorial do agente. Rejeição de padrões de clickbait (regex de títulos sensacionalistas).
Entrega Fase 2: cobertura regional mais densa, sem duplicação, com breaking-news detectado, viral capturado, credibilidade ponderada, e redução estrutural de fake-news.

FASE 3 — Estratégia editorial nacional/internacional (High Impact / Medium Effort)
Objetivo: ≥1 notícia nacional de alto impacto + ≥1 internacional por edição, sem ofuscar a cobertura local. (Decisão: feeds RSS curados.)

3.1 Adicionar feeds nacionais e internacionais ao sources/sources.json
Nacional (tier-1, alta credibilidade): G1, Folha de S.Paulo, Estadão, Valor Econômico, CNN Brasil, BBC Brasil, Agência Brasil.
Internacional: Reuters (World/Brazil), AP News, BBC World.
Cada fonte recebe scope: "nacional" | "internacional" (novo campo) além de tier.
3.2 Metodologia de ranking automatizada para seleção nacional/internacional
Score de impacto = f(reach_potencial, relevância_econômica_para_SC, recência, alinhamento_com_lente_libertária).
Cotas: o roteiro força exatamente 1 nacional + 1 internacional (não mais, para não ofuscar o local), selecionados pelo score de impacto.
Filtro de impacto local: notícia nacional só entra se tiver implications para SC/Vale do Itajaí (ex: política tributária federal, ICMS, infraestrutura rodoviária) ou for de altíssimo alcance (presidencial, crise nacional). Internacional só se de altíssimo alcance (geopolítica, economia global, desastres).
3.3 Nova estrutura de quadros no SKILL.md e generate_script.py
Adicionar dois quadros à sequência fixa (após quadros locais, antes de Rapidinhas):
### QUADRO: BRASIL (≥1 nacional)
### QUADRO: MUNDO (≥1 internacional)
Atualizar categories_map em pipeline.py, QUADROS em generate_script.py, validação em tts_preprocessor.validate_episode.
Entrega Fase 3: cada edição tem contexto nacional e internacional conciso, preparando a plataforma para expansão geográfica.

FASE 4 — Roteiro ideal para audiência brasileira (Medium Impact / Low Effort)
Objetivo: estrutura de bulletin otimizada para retenção e fluxo natural. O Hermes Agent segue esta estrutura ao gerar o roteiro (Fase 1.2).

4.1 Estrutura-alvo do bulletin (atualizar SKILL.md seção 4 e episodes/TEMPLATE.md)
Abertura (cold open): gancho de impacto (não "bem-vindo"), 1 fala Peter + 1 Ricardo, ≤30s.
Manchetes: 5-6 bullets, narradas por um locutor, ritmo rápido.
Breaking-news (condicional): se detectado na Fase 2.3, vem antes dos quadros fixos.
Quadros locais (Segurança → Saúde → Educação → Política → Esportes).
Brasil (1 notícia, concisa).
Mundo (1 notícia, concisa).
Rapidinhas da Loucura Estatal (opcional, alívio cômico).
Fechamento: provocação Peter + reflexão/CTA Ricardo.
4.2 Regras de retenção e fluidez
Transições variadas: o SKILL.md já tem um banco de transições por quadro (seção 4.x). Reforçar regra anti-repetição: nenhuma transição repetida entre episódios consecutivos (manter histórico em archive/transitions-used.json).
Adaptação de duração: se palavras > 2500, pedir ao agente para enxugar quadros menos relevantes; se < 2000, expandir análise no quadro de maior impacto. Loop de self-check no renderer.
Priorização: quadros com breaking-news ou score de relevância mais alto vêm primeiro dentro dos locais.
Entrega Fase 4: bulletin com retenção otimizada, transições não-repetitivas, duração controlada.

FASE 5 — Qualidade de áudio/TTS avançada (High Impact / Medium Effort)
Objetivo: naturalidade, pronúncia correta de nomes locais, prosódia, normalização robusta.

5.1 Normalização robusta (substituir dict estático por motor de normalização)
Números por extenso: usar num2words (pt-BR) — 104→"cento e quatro", 2025→"dois mil e vinte e cinco".
Datas: 20/06/2026→"vinte de junho de dois mil e vinte e seis"; anos isolados por extenso.
Horas: 21h40→"vinte e uma horas e quarenta".
Moeda: R$ 70 milhões→"setenta milhões de reais" (corrigir a gramática quebrada de hoje: "reais 70 milhões").
Porcentagem: 104%→"cento e quatro por cento" (número por extenso + sufixo).
Acrônimos: manter o dict, mas com contexto (rodovias preservadas — ver Fase 0.2).
5.2 Pronúncia de nomes locais (lexicon)
Criar sources/pronunciation_lexicon.json com aliases para toponímia regional: Blumenau, Rua XV de Novembro, BR-470, Vale do Itajaí, Pomerode, Indaial, Rio do Sul, Gaspar, Alesc, Furb. Como Gemini TTS preview tem suporte limitado a SSML, usar rewriting (substituição fonética por texto mais legível) onde a pronúncia errar.
5.3 Prosódia e ênfase
Investigar o suporte atual do gemini-3.1-flash-tts-preview a SSML/<prosody>/<emphasis>. Se suportado, marcar números-chave e nomes próprios. Se não, reforçar as dicas de persona no prompt (SPEAKER_PERSONAS) com instruções de ritmo/ênfase por quadro.
5.4 Pós-processamento de áudio profissional
Loudnorm de 2 passos (EBU R128): primeiro pass mede (loudnorm=print_format=json), segundo pass aplica linear. Resolve o problema do passo único atual.
Resampling: 24kHz é baixo para podcast — subir para 44.1kHz ou 48kHz (-ar 44100).
Manter highpass/compressor/EQ atuais (são razoáveis).
5.5 Implementar chunking (que estava morto)
CHUNK_TARGET_WORDS = 300 existe mas não é usado. Implementar divisão real do roteiro em chunks por locutor/quadro, gerar áudio por chunk, concatenar com crossfades curtos. Isto (a) reduz timeouts da API, (b) permite retomar apenas chunks falhados, (c) integra com as pausas reais da Fase 0.4.
Entrega Fase 5: áudio com pronúncia correta de nomes locais, números naturais, prosódia controlada, loudness profissional (EBU R128), resiliência a timeouts.

FASE 6 — Escalabilidade multi-cidade/estado/país (High Impact / High Effort)
Objetivo: arquitetura pronta para expansão geográfica futura.

6.1 Arquitetura multi-agente
Editor Regional Agent (um por cidade/região): coleta, filtra, pontua localmente. Hoje = Blumenau; futuro = Florianópolis, Joinville, Curitiba, etc.
Editor Nacional/Internacional Agent: compartilhado, alimenta todos os boletins regionais.
Orquestrador Hermes (chief editor): mescla contribuições, decide lineup final, gera roteiro.
TTS Worker: isolado, só Gemini TTS.
6.2 Segmentação geográfica de conteúdo
sources/sources.json ganha region por fonte. config/regions/{region}.yaml define fontes, termos de busca X, lexicon de pronúncia, peso de entidades geo. Hoje: config/regions/blumenau-vale-itajai.yaml.
6.3 Agregação de feeds regionais
Template de configuração replicável: novo cidade = novo YAML + novas fontes + novo lexicon. Zero mudança de código.
6.4 Personalização (futuro)
Perfis de ouvinte (interesses por quadro), feed personalizado, recomendação por similaridade de episódios. Esboçar schema listeners/ e endpoint futuro.
6.5 Observabilidade & métricas
Métricas técnicas: taxa de sucesso por fonte (já em cache.json), latência por etapa, custo TTS por episódio, taxa de retry, cobertura de quadros.
Métricas editoriais: diversidade de fontes, score médio de relevância, % de episódios com breaking-news, taxa de continuidade editorial.
Métricas de qualidade de áudio: LUFS médio, true-peak, duração vs. alvo.
Painel: gerar reports/daily-{date}.json consolidado a cada execução.
6.6 Confiabilidade & fault-tolerance
Retries com backoff (já existe no TTS; estender para coleta). Dead-letter de fontes falhando cronicamente (auto-desabilitar após N falhas consecutivas, alertar). Checkpointing por etapa (se audio falha, não refazer collect+process). Idempotência por data.
Entrega Fase 6: plataforma pronta para adicionar cidades/estados com config-only, com observabilidade e tolerância a falhas.

Deliverables (documentos a criar/atualizar)
#	Documento	Conteúdo	Ação
D1	REVIEW.md (novo)	Avaliação da arquitetura atual: forças, fraquezas, gargalos, riscos	criar
D2	ROADMAP.md (novo)	Roadmap priorizado (matriz Impacto×Esforço das Fases 0-6)	criar
D3	ARCHITECTURE.md	Atualizar: Hermes como motor não-TTS, x_collector conectado, novos quadros nacional/internacional	atualizar
D4	PRD.md	Atualizar: requisitos funcionais 2-3, estratégia editorial nacional/internacional, roadmap	atualizar
D5	SKILL.md	Atualizar: nota de execução pelo Hermes Agent, novos quadros Brasil/Mundo, estrutura de bulletin ideal, lexicon de pronúncia	atualizar
D6	TARGET_ARCHITECTURE.md (novo)	Descrição da arquitetura-alvo (multi-agente, segmentação geo)	criar
D7	LESSONS_LEARNED.md	Adicionar entradas: regressão 2026-06-20, pausas ignoradas, corrupção BR-470, x_collector conectado	atualizar
D8	IMPLEMENTATION_EXAMPLES.md (novo)	Exemplos práticos: contrato JSON do roteiro, fórmula de relevance score, prompt de seleção editorial, cadeia ffmpeg 2-pass	criar
Cada fase de código (0-6) é executável de forma independente e verificável (grep confirma ausência de Gemini não-TTS; validação passa; episódio de teste atinge duração-alvo).

Ordem de execução recomendada (dependências)

text
Fase 0 (quick wins)        ← independente, fazer primeiro
   ↓
Fase 1 (migrar Gemini→Hermes) ← pré-requisito para tudo
   ↓
Fase 2 (pipeline robusto)  ← usa contrato da Fase 1
   ↓ (paralelo)
Fase 3 (nacional/internacional)  ←  Fase 4 (roteiro ideal)
   ↓
Fase 5 (áudio avançado)
   ↓
Fase 6 (escalabilidade)
Fase 0 + Fase 1 entregam ~70% do valor (eliminam a violação de constraint e a regressão de qualidade). Fases 2-5 são incrementos de qualidade. Fase 6 é preparação para futuro.

Confirmações pendentes marcadas como ⚠️ A confirmar com Osmar (serão endereçadas)
Numeração sequencial de episodio (sempre null) — implementar auto-incremento na Fase 1.
Custo por episódio em USD — adicionar telemetria na Fase 6.5.
Analytics de plays/retenção — escopo de painel na Fase 6.5.
Deploy do public/ automatizado ou manual — documentar.
x_collector.py recriar vs. legado — conectar (decisão: é código vivo, pronto).
Plano pronto para aprovação. Após confirmação, executo Fase 0 primeiro (menor risco, valor imediato), depois apresento resultado antes de prosseguir à Fase 1.