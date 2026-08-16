# LESSONS_LEARNED — Web Jornal Vale da Liberdade

Formato: entrada por incidente/decisão com contexto, causa, solução e como evitar.

---

## [2026-06-20] Notícia repetida no roteiro final quando preenchido pelo raw

- **Contexto:** Episódio 2026-06-20 gerado via `pipeline.py process` auto-preenchendo o roteiro a partir do raw.
- **O que aconteceu:** A mesma notícia aparece duas vezes no mesmo quadro, com redação levemente diferente. Exemplo no quadro Segurança Pública: a fala de Ricardo apresenta o incêndio na BR-470, e logo depois a fala de Peter repete o mesmo fato com outro texto.
- **Causa raiz:** `_fill_roteiro_from_raw()` em `pipeline.py` extrai o título e o resumo do raw e insere como fala de Ricardo (apresentação) + Peter (título + pontos-chave), mas o raw já vinha com um resumo longo que cobria toda a notícia. Resultado: duas versões da mesma história na sequência.
- **Solução aplicada:** `pipeline.py cmd_process` foi alterado para chamar `generate_script.py` quando o roteiro ainda for template. Isso gera roteiro com diálogos ricos e sem duplicação.
- **Como evitar/repetir no futuro:** Se o `generate_script.py` falhar, o `cmd_process` agora cai para manter o template, evitando sobrescrever com `_fill_roteiro_from_raw`. Manter essa ordem de prioridade.

---

## [2026-06-20] Integração de `generate_script.py` ao pipeline principal

- **Contexto:** `generate_script.py` existia como script standalone, mas nunca foi chamado pelo pipeline padrão.
- **O que aconteceu:** O pipeline usava `_fill_roteiro_from_raw` como fallback, produzindo roteiro enxuto sem diálogos ricos ou tensão dialética entre Peter e Ricardo.
- **Causa raiz:** Ausência de import e chamada de `generate_script`/`format_script` em `pipeline.py` e ausência de tratamento de exceção no `cmd_process`.
- **Solução aplicada:** Adicionado import de `generate_script` em `pipeline.py` e substituída a chamada a `_fill_roteiro_from_raw` por bloco `try/except` que usa `generate_script(date)` + `format_script(date, roteiro_obj)`.
- **Como evitar/repetir no futuro:** Se for necessário reverter, basta restaurar o bloco anterior. O `_fill_roteiro_from_raw` permanece no código como fallback documentado.

---

## [2026-06-20] Integração resiliente do `x_collector.py` no pipeline principal

- **Contexto:** O script `x_collector.py` existia no repositório, mas necessita de cookies de sessão válidos para emular navegação autenticada no X (Twitter).
- **O que aconteceu:** Foi realizada a conexão dos tweets obtidos pelo `x_collector.py` com o pipeline de coleta diária (`pipeline.py`). Como sessões do X são voláteis e podem expirar ou falhar por rate limiting, havia o risco de travar o fluxo inteiro de coleta de notícias.
- **Causa raiz:** Processamento linear e síncrono da coleta onde qualquer erro no Playwright/Twitter interromperia o pipeline diário.
- **Solução aplicada:** O módulo do X foi reativado no `pipeline.py`, mas envelopado de forma totalmente tolerante a falhas (resiliente) com blocos `try/except` robustos no import e na execução. Se os cookies expirarem ou o scraper falhar, o pipeline exibe apenas um aviso no console e prossegue normalmente com a coleta de RSS.
- **Como evitar/repetir no futuro:** Sempre projetar integrações com scrapers ou APIs de terceiros voláteis sob um modelo de degradação suave ("graceful degradation"), garantindo que falhas nestes sub-módulos não impeçam o processamento dos dados principais.

---

## [2026-06-20] Scripts legados (`daily-collect.sh`, `cron-daily.sh`) causam confusão

- **Contexto:** O usuário perguntou se `daily-collect.sh` ainda está em uso.
- **O que aconteceu:** O `crontab -l` executa `scripts/cron-wrapper.sh` que chama `pipeline.py full`. O `daily-collect.sh` é um shell antigo que cria template raw vazio + roteiro template, sem coleta real. O `cron-daily.sh` referencia `daily-pipeline.sh` que não existe.
- **Solução aplicada:** Marcar ambos como deprecated em `ARCHITECTURE.md` sem deletar (conforme regra do prompt).
- **Com evitar/repetir no futuro:** Adicionar aviso de deprecation no próprio arquivo ou remover após confirmação com Osmar.

---

## [2026-06-20] `episodio` sempre null nos metadados

- **Contexto:** Todos os `*-metadata.json` analisados têm `"episodio": null`.
- **O que aconteceu:** A numeração sequencial de episódios nunca foi implementada.
- **Solução aplicada:** Criada a função helper `get_episode_number` no `pipeline.py` que lê o arquivo `archive/index.md`, analisa e ordena as datas e deduz o número do episódio atual (posição de inserção na série histórica). Esse valor é agora passado dinamicamente para o `generate_metadata()`.
- **Como evitar/repetir no futuro:** Utilizar índices de arquivos estáticos como fonte confiável de dados para cálculos sequenciais no pipeline offline.

---

## [2026-06-20] Handoffs eram sobrescritos a cada sessão (`.continue-here.md`)

- **Contexto:** O prompt menciona `.continue-here.md` que era sobrescrito perdendo histórico.
- **O que aconteceu:** O arquivo não existe mais no repositório atual — provavelmente já foi removido ou nunca foi commitado.
- **Solução aplicada:** Criar convenção `archive/handoffs/YYYY-MM-DD.md` em `AGENT_GUIDE.md`.
- **Como evitar/repetir no futuro:** A partir de agora, todo handoff de sessão será salvo como arquivo datado em `archive/handoffs/`.

---

## [2026-06-20] Marcadores [PAUSA] e [PAUSA_CURTA] são removidos do prompt TTS — zero efeito acústico

- **Contexto:** `tts_preprocessor.py` insere `[PAUSA]` (entre quadros) e `[PAUSA_CURTA]` (após falas longas). `SKILL.md` seção 8.3 documenta durações de 1,5s e 0,5s.
- **O que aconteceu:** `generate_gemini_tts_multi.py:build_prompt()` (L92) faz `re.sub(r"\[PAUSA(?:_CURTA)?\]", "", episode_text)` e o prompt diz "IGNORE completamente qualquer marcação como [PAUSA] ou [PAUSA_CURTA]: elas não devem ser lidas." Os marcadores sobrevivem apenas no artefato `-tts.txt`, mas **nunca produzem silêncio real** no áudio.
- **Causa raiz:** O modelo TTS recebe todo o texto como uma string contínua, sem capacidade de interpretar marcadores de pausa. O pipeline nunca insere silêncio no nível do áudio (ffmpeg).
- **Solução aplicada:** Registrado como item do ROADMAP Fase 0.4. A correção envolve: (1) dividir o texto nos marcadores de pausa, (2) sintetizar cada segmento separadamente, (3) concatenar com silêncio real via ffmpeg. Isto também resolve o chunking morto (`CHUNK_TARGET_WORDS=300` nunca referenciado).
- **Como evitar/repetir no futuro:** Qualquer marcador de prosódia no roteiro deve ter uma implementação acústica correspondente — ou implementar ou remover da documentação.

---

## [2026-06-20] Regra genérica BR→B-R corrompe códigos de rodovia em produção

- **Contexto:** `tts_preprocessor.py:64` define `"BR": "B-R"`, aplicado via `\bBR\b` em L137-140. O mesmo para `"SC": "S-C"`.
- **O que aconteceu:** `BR-470` (rodovia mais referenciada na cobertura regional) era convertido em `B-R-470` no áudio final. Confirmado em `episodes/2026-06-20-tts.txt` linhas 6-7 e 16-17: "B-R-470", "B-R-101".
- **Causa raiz:** O regex `\bBR\b` casa `BR` antes de `-470` porque `-` é um word boundary. A substituição não distinguia códigos de rodovia (`BR-\d+`) da sigla isolada.
- **Solução aplicada:** Fase 0.2 — `_apply_substitutions` agora protege rodovias com placeholders temporários (`\x00RODOVIA{idx}\x00`) antes de substituir siglas, e as restaura depois. Suporta `BR-###`, `SC-###`, `RR-###`, etc.
- **Como evitar/repetir no futuro:** Sempre que adicionar uma sigla ao `TTS_SUBSTITUTIONS`, verificar se ela forma prefixo de termos compostos relevantes (rodovias, códigos, nomes locais).

---

## [2026-06-20] Violação do constraint "Gemini = apenas TTS" — dois usos não-TTS ativos

- **Contexto:** A arquitetura declara que Gemini deve ser usado exclusivamente para Text-to-Speech. Todas as demais responsabilidades (filtro, ranking, sumarização, geração de roteiro) são do Hermes Agent.
- **O que aconteceu:** `ai_news_filter.py:133` chama `gemini-2.5-flash` para filtrar, categorizar em 6 quadros, atribuir quality_score 1-5 e escrever resumos/key_points. `generate_script.py:211` chama `gemini-2.5-flash` para gerar o roteiro editorial completo com personas Peter/Ricardo. Apenas `generate_gemini_tts_multi.py` usa Gemini para TTS (`gemini-3.1-flash-tts-preview` com `response_modalities=["AUDIO"]`).
- **Causa raiz:** Ambos os scripts foram implementados antes do constraint ser formalizado. O `GEMINI_API_KEY` é a única variável de API configurada, tornando Gemini o caminho natural para qualquer tarefa de IA.
- **Solução aplicada:** Registrado como ROADMAP Fase 1 (migração completa). O `ai_news_filter.py` será split em camada determinística + Hermes Agent inline. O `generate_script.py` perderá o bloco Gemini e virará renderer JSON→MD. Meta: `grep gemini-2.5-flash scripts/` retorna vazio.
- **Como evitar/repetir no futuro:** Adicionar validação no pipeline: se qualquer módulo exceto `generate_gemini_tts_multi.py` importar `google.genai`, emitir warning. Documentar o constraint em `ARCHITECTURE.md`.

---

## [2026-06-20] `x_collector.py` (1.273 linhas) completamente desconectado do pipeline

- **Contexto:** O coletor de X/Twitter foi desenvolvido (sessão de 2026-06-16) com login, busca por termos, monitoramento de perfis, métricas de engajamento e proteção contra rate-limit. A função `consume_x_tweets_for_pipeline()` (L1004) está pronta para converter tweets em artigos.
- **O que aconteceu:** Nenhum módulo do pipeline importa ou chama o `x_collector`. Os tweets coletados (em `sources/x_tweets_cache.json`) nunca chegam ao `ai_news_filter` ou ao `raw-{date}.md`.
- **Causa raiz:** A integração foi interrompida pelo rate-limit do X durante testes (registrado no handoff de 2026-06-16) e nunca retomada. O `.continue-here.md` que documentava o próximo passo foi movido para `archive/handoffs/2026-06-16-x-collector.md`.
- **Solução aplicada:** Registrado como ROADMAP Fase 2.4. A conexão é simples: `cmd_collect` chamar `consume_x_tweets_for_pipeline()` e mesclar os resultados com os artigos de sites antes do filtro.
- **Como evitar/repetir no futuro:** Todo script criado deve ter um "integration test" mínimo que verifica se é importável e chamável a partir do pipeline principal.

---

## [2026-06-20] `content_hashes` scaffoldado mas nunca populado — dedup semântica inexistente

- **Contexto:** `cache.json` tem a chave `content_hashes: {}` (sempre vazia). A dedup é puramente por URL exata em `news_collector.py:442-454`.
- **O que aconteceu:** A mesma notícia publicada em 2 portais com URLs diferentes entra duas vezes no pipeline. Exemplo real: o incêndio na BR-470 coberto por Mesorregional e Informe Blumenau aparece como 2 itens separados.
- **Causa raiz:** O `content_hashes` foi inicializado com `get("content_hashes", {})` em `load_cache` mas nenhuma função o popula. A dedup por URL é suficiente para RSS (onde cada portal emite um URL único por notícia) mas falha quando a mesma notícia é republicada ou quando portais diferentes cobrem o mesmo evento com títulos diferentes.
- **Solução aplicada:** Registrado como ROADMAP Fase 0.3 (implementação de hash semântico SimHash/MinHash sobre título+resumo) e Fase 2.2 (clustering por similaridade).
- **Como evitar/repetir no futuro:** Ao scaffoldar um campo no schema, implementar ao menos um placeholder funcional e adicionar teste.

---

## [2026-06-20] `.continue-here.md` existia contradizendo AGENT_GUIDE.md

- **Contexto:** `AGENT_GUIDE.md:18` diz "Não sobrescreva `.continue-here.md` (não existe mais no repositório)".
- **O que aconteceu:** O arquivo `.continue-here.md` existia na raiz do projeto, contendo o handoff da sessão de integração do X/Twitter (2026-06-16).
- **Solução aplicada:** Movido para `archive/handoffs/2026-06-16-x-collector.md` seguindo a convenção estabelecida no AGENT_GUIDE.
- **Como evitar/repetir no futuro:** Antes de afirmar que algo "não existe mais", verificar com `ls` ou `git status`.

---

## [2026-06-22] Fontes nacionais v1.1 nunca foram executadas em rodada real

- **Contexto:** Ao rodar `news_collector.py --test-sources` (Passo 0 da expansão v1.2), descobriu-se que as 8 fontes nacionais/internacionais adicionadas na v1.1 nunca apareceram em `cache.json:source_stats`. O último `last_run` era 2026-06-20 com apenas 14 fontes locais.
- **O que aconteceu:** Reuters (`feeds.reuters.com`) e AP News (`rsshub.app`) estão com feeds mortos — nunca funcionaram desde que foram cadastrados. G1 Brasil retornou 0 itens (feed pode ter mudado de URL). As demais (G1 SC, Agência Brasil, CNN, BBC Brasil, BBC World) funcionam normalmente.
- **Causa raiz:** As fontes foram adicionadas ao `sources.json` v1.1 mas o pipeline nunca rodou uma coleta completa com a versão atualizada. Não havia validação prévia ao cadastrar.
- **Solução aplicada:** (a) Reuters e AP desabilitados (`enabled: false`) com `_note` para revalidação futura. (b) G1 Brasil mantido habilitado com nota sobre possível URL alternativa (`/dynamo/brasil/rss2.xml`). (c) Criado `scripts/validate_feeds.py` como gate obrigatório para qualquer nova fonte.
- **Como evitar/repetir no futuro:** Todo cadastro de fonte no `sources.json` deve ser precedido de validação via `validate_feeds.py`. Fontes que falhem em 3 rodadas de URLs alternativas devem ser marcadas `enabled: false` imediatamente, não após meses de inatividade.

---

## [2026-06-22] Validação em 3 rodadas recuperou feeds "mortos" via URLs alternativas

- **Contexto:** Dos 20 feeds candidatos importados do `noticias-brasil.opml`, a rodada 1 aprovou apenas 13/20. Os 7 restantes falharam com HTTP 404, conexão recusada ou feed vazio.
- **O que aconteceu:** Ao testar URLs alternativas (sem barra final, variantes `/feed` vs `/rss/`, Arc outboundfeeds, query params), mais 3 feeds foram recuperados na rodada 2 (Correio Braziliense via `/feed`, Valor geral via `/rss/valor`, CNN Política via `/feed` sem barra) e 2 na rodada 3 (Estadão via `/arc/outboundfeeds/feeds/rss/sections/politica/`, CNN Política via `?cat=politica`). Total: 18/20 recuperados.
- **Causa raiz:** Portais brasileiros frequentemente mudam endpoints RSS sem redirecionamento. O `news_urls.md` listava URLs "confirmadas" mas várias estavam desatualizadas ou usavam formatos antigos.
- **Solução aplicada:** O `validate_feeds.py` suporta rodadas com arquivos JSON distintos (`--input`). 4 feeds resistiram a todas as 3 rodadas e foram descartados: Brasil 247 (HTTP 200 mas feedparser não encontra entries em nenhuma URL), Terra histórico (`rss.terra.com.br` conexão recusada — domínio morto), Alexandre Garcia (404 — site inativo), Valor Política (`/politica/rss.xml` 404).
- **Como evitar/repetir no futuro:** Quando cadastrar feed RSS, testar pelo menos 2 variantes de URL. Manter lista de "URLs já testadas e falharam" para evitar retestar as mesmas. Revalidar mensalmente.

---

## [2026-06-22] CNN Política `?cat=politica` retorna feed geral, não filtrado por editoria

- **Contexto:** A URL `cnnbrasil.com.br/feed/?cat=politica` foi aprovada na rodada 3 com 60 itens, mas a primeira notícia é sobre Copa do Mundo (esportes), não política.
- **O que aconteceu:** O parâmetro `?cat=politica` não é reconhecido pelo WordPress da CNN Brasil como filtro de categoria — retorna o feed geral completo. O resultado é idêntico ao feed `/feed/` já cadastrado como `cnn_brasil`.
- **Causa raiz:** A CNN Brasil não expõe feeds por categoria via query parameter. O endpoint correto seria `/politica/feed/` (testado na rodada 2, retornou 404).
- **Solução aplicada:** Feed mantido no `sources.json` v1.2 com `_note` alertando sobre sobreposição. A dedup por URL evitará duplicação pura, mas notícias da CNN aparecerão com peso dobrado no pipeline. Recomendação: monitorar volume e considerar `enabled: false` se gerar muito ruído.
- **Como evitar/repetir no futuro:** Ao validar feeds segmentados por editoria, verificar se o primeiro item retornado é realmente da editoria esperada.

## [2026-06-22] Integração `generate_script.py` validada com teste ponta-a-ponta

- **Contexto:** Após refatoração, `generate_script.py` virou renderer JSON → MD e `pipeline.py` passou a exigir `roteiro-{date}.json`.
- **O que aconteceu:** Rodei `process --date 2026-06-20` com mock `roteiro-template.json`; pipeline destravou, gerou TTS/manchetes/metadados e áudio MP3 sem erros.
- **Causa raiz:** N/A — teste controle confirma que o fluxo funciona quando o JSON do Hermes está presente.
- **Solução aplicada:** Mock criado e movido para `episodes/roteiro-template.json` para reuso em testes futuros.
- **Como evitar/repetir no futuro:** Todo teste ponta-a-ponta pode clonar `roteiro-template.json` para `roteiro-YYYY-MM-DD.json` e rodar `process` + `audio`.

## [2026-06-22] Coleta e validação de feeds estabilizadas

- **Contexto:** Usuário reportou que, após alterações recentes, erros de `IncompleteRead` da Globo, timeouts de DNS e bloqueios da Veja/Metrópoles foram eliminados.
- **O que aconteceu:** `news_collector.py` agora faz pré-busca HTTP (`requests.get`), retentativas automáticas, controle de concorrência com `max_workers=5` e jitter aleatório.
- **Solução aplicada:** Código já está aplicado no repositório; não há ação adicional necessária.
- **Como evitar/repetir no futuro:** Se novas fontes entrarem, manter padrão: HTTP primeiro, RSS como fallback, WordPress API terceiro, Playwright último recurso.

---

## [2026-06-22] Integração Fase 2.4 do `x_collector.py` ativa no pipeline principal

- **Contexto:** Fase 2.4 do roadmap previa a conexão do `x_collector.py` ao pipeline de coleta diária.
- **O que aconteceu:** A integração foi concluída em `pipeline.py` (`cmd_init`/`cmd_collect`), com chamada a `consume_x_tweets_for_pipeline()` envolvida em `try/except` tolerante a falhas. Em teste, quando não havia tweets válidos no cache, o log registrou `"Nenhum tweet do X no cache para consumir"` e o pipeline seguiu normalmente.
- **Causa raiz:** N/A — confirmação que o fluxo funciona mesmo com resposta vazia ou com falhas transitórias do scraper.
- **Solução aplicada:** Integração ativa e resiliente; falhas no módulo do X não interrompem a coleta de RSS.
- **Como evitar/repetir no futuro:** Sempre validar integrações com testes que cubram pelo menos três cenários: sucesso, resposta vazia e falha/exception.

---

## [2026-06-22] Atualização do scoring de credibilidade e relevância em `scripts/ai_news_filter.py`

- **Contexto:** Ajustes nos pesos e critérios de ranqueamento das notícias antes do filtro de validação.
- **O que aconteceu:** Foi alterada a fórmula de relevância com pesos em `RELEVANCE_WEIGHTS`, incluindo `x_engagement_score()` para artigos vindos do X/Twitter. Além disso, `credibility_score` passou a usar taxa de sucesso como dimensão principal (peso ~70%) quando o `source_id` tiver pelo menos 2 fetches de sucesso registrados.
- **Causa raiz:** Necessidade de diferenciar fontes com histórico de coleta consistente de fontes novas ou com alta taxa de falha recente.
- **Solução aplicada:** Código atualizado em `scripts/ai_news_filter.py` refletindo as novas regras de score. Nenhuma ação adicional necessária.
- **Como evitar/repetir no futuro:** Toda alteração em pesos de ranqueamento deve ser registrada aqui, com referência ao diff e ao surgimento de efeitos colaterais em rankings ou filtros.

---

## [2026-06-23] MinHash com n-gramas de palavras falha em títulos curtos — camada híbrida com keyword overlap resolve

- **Contexto:** Fase 2.2 previa MinHash leve para dedup semântica em `news_collector.py`.
- **O que aconteceu:** Com n-gramas de palavra e threshold 0.62 em uma lista aleatória, títulos quase idênticos não compartilhavam nenhum n-grama completo e a similaridade MinHash ficava em 0.0 para pares que claramente se referem ao mesmo evento.
- **Causa raiz:** Títulos curtos variam muito com 1-2 palavras trocadas. A janela dos 50 mais recentes também estava sujeita à ordem assíncrona de entrada, então matches reais se perdiam.
- **Solução aplicada:** Dupla camada: (1) MinHash com shingles de caractere (3-grams) para quase-duplicatas, e (2) similaridade por palavras-chave compartilhadas (Jaccard sobre tokens após remover stopwords PT e termos com <=2 letras). Nova camada usa threshold 0.70 e janela de 50 títulos recentes.
- **Como evitar/repetir no futuro:** Para dedup de notícias curtas, n-gramas de caractere + camada lexical é mais confiável que n-gramas de palavra puros. Medir recall em pares sintéticos antes de decidir remover a camada lexical.

---

## [2026-08-08] Duplo autoplay no `ended` — player.js avança direto e derrota o interstitial (race)

- **Contexto:** transição automática entre episódios; afeta todos os ouvintes, principalmente na tab Brasil e Mundo.
- **O que acontece:** no `ended`, o próximo episódio começa a tocar imediatamente E o interstitial de anúncio é mostrado ~0,3–1s depois (áudio do episódio por trás do ad). `playEpisode` é chamado 2× por transição → `incrementView` 2× (double view).
- **Causa raiz:** `player.js` L2 tem listener nativo `ended` que chama `window.playEpisode(nextEp.id)` DIRETO; `app.js` L188 também escuta `playerevent` type `ended` e chama `handleAutoPlayNext()` (busca ad → pause → showInterstitial). Dois caminhos concorrentes; o direto do player.js vence o timing. Encontrado na auditoria agy Fase 3 (Claude Opus 4.6).
- **Solução:** Aplicada 2026-08-08 (aprovada por Osmar) — removido o autoplay direto do `ended` handler do `player.js` (ficou só o `WakeLock.release`); `handleAutoPlayNext()` passou a ser o ÚNICO caminho de autoplay. Também eliminou o double-view (`incrementView` 2× por transição).
- **Como evitar no futuro:** regra: navegação/autoplay de episódio SEMPRE passa por UMA função central (`handleAutoPlayNext`), nunca por dois caminhos paralelos; verificar `grep -n "playEpisode" player.js` em qualquer mudança de autoplay.

## [2026-08-08] XSS em thumbnails via `ep.cover_url_abs` interpolada sem escape (app.js)

- **Contexto:** renderRow (feed) e renderContinueRail (rail "Continuar ouvindo") montavam `<img src="${rowThumb}" ...>` com URL vinda do JSON/Supabase sem `escapeHtml()`.
- **O que acontece:** URL malformada com aspas (dado externo) quebrava a marcação e permitia injeção de atributos/HTML.
- **Causa raiz:** `public/assets/js/app.js:103` e `:145` (minificado) — interpolação direta de `rowThumb`/`rowThumbJpg`/`railThumb`/`railThumbJpg`.
- **Solução:** Aplicada automaticamente — `escapeHtml()` nas 4 interpolações (auditoria 2A ∩ 2E concordaram; validado por node --check).
- **Como evitar no futuro:** Toda interpolação de dado externo em template string de innerHTML usa `escapeHtml()`; auditorias futuras devem grep `src="\${` em app.js.

## [2026-08-08] XSS via pseudo-protocolo `javascript:` em URLs de patrocinadores e CTA de anúncio

- **Contexto:** `renderSponsorsHtml()` (app.js:327) e CTA da sidebar (app.js:329) aceitavam qualquer URL como `href`/`ctaEl.href`.
- **O que acontece:** `href="javascript:..."` executaria script no clique (dado controlável pelo admin no Supabase; defesa em profundidade).
- **Causa raiz:** falta de validação de protocolo `^https?:\/\/` nas URLs de ad/sponsor.
- **Solução:** Aplicada automaticamente — validação de protocolo com fallback `'#'`/`hidden=true`.
- **Como evitar no futuro:** qualquer URL vinda de Supabase exige validação de protocolo antes de entrar em href/src; grep `click_url`/`website_url` em mudanças de ad.

## [2026-08-08] offline.html referencia `./styles.css` que não existe — página offline sem estilo

- **Contexto:** PWA offline; usuários sem conexão veem a página de fallback.
- **O que acontece:** `public/offline.html` L8 carrega `./styles.css` (não existe no projeto — só `assets/css/*.css`); a página offline renderiza sem estilo (texto puro).
- **Causa raiz:** `public/offline.html:8` — href de stylesheet apontando para arquivo removido/movido.
- **Solução:** Pendente aprovação — corrigir href para os CSS reais (`./assets/css/tokens.css` + `base.css` + `components.css`) ou um bundle offline dedicado.
- **Como evitar no futuro:** validar todos os hrefs de `offline.html`/`index.html` contra `ls public/` após reestruturações de CSS; a auditoria 2C não viu, o Hermes achou na verificação manual de existência de arquivo.

## [2026-08-08] Service Worker devolve `offline.html` para qualquer fetch falho (não só navegação)

- **Contexto:** SW genérico cache-first; recursos quebrados (imagens, etc.).
- **O que acontece:** `sw.js:102` cai em `caches.match("./offline.html")` para QUALQUER requisição que falhe — o browser recebe um documento HTML onde esperava imagem/asset (comportamento bizarro de parsing).
- **Causa raiz:** fallback offline incondicional no catch do fetch handler.
- **Solução:** Pendente aprovação — guard `if (req.mode === "navigate")` antes de servir offline.html; demais recursos retornam erro.
- **Como evitar no futuro:** revisar o catch do SW sempre que tocar em estratégia de cache; navegação ≠ sub-recurso.

## [2026-08-08] Memory leak no interstitial: `fakeInterval` de imagem continuava rodando após fechar o anúncio

- **Contexto:** ad_manager.js; anúncios de imagem sem áudio (fake timer de 10s).
- **O que acontece:** ao pular/fechar o anúncio antes dos 10s, o `fakeInterval` (200ms) continuava ativo até completar o ciclo (timer + callback) — até 10s de CPU por anúncio fechado.
- **Causa raiz:** `fakeInterval` declarado no escopo do bloco `else` (imagem), inacessível ao `cleanupAndClose()`.
- **Solução:** Aplicada automaticamente — variável movida para o escopo pai e `clearInterval(fakeInterval)` adicionado ao cleanup (auditoria 2D).
- **Como evitar no futuro:** todo `setInterval` criado em módulo de mídia precisa de cleanup no mesmo escopo da função que o cria; regra: timers locais → escopo do ciclo de vida do componente.

## [2026-08-08] Preview de compartilhamento errado no WhatsApp — crawler não executa JS (OG estático por episódio)

- **Contexto:** ao compartilhar links de episódio no WhatsApp/Telegram, o card mostrava a imagem/título/descrição genéricos do canal, não os do episódio.
- **O que acontece:** WhatsApp/Telegram montam o preview lendo SOMENTE os `<meta og:*>` estáticos do HTML; eles não executam JavaScript. As tags dinâmicas por episódio eram injetadas pelo `updateFullPlayerMetadata()` (app.js) só depois do JS rodar — tarde demais para o crawler.
- **Causa raiz:** site 100% nginx estático; `?ep=` sempre devolve `index.html` com og genérico da home.
- **Solução:** Aplicada — geradas páginas estáticas `/ep/<id>.html` por episódio (título, resumo, thumbnail absoluta via `cover_url_abs` + `og:image`/twitter + canonical) que redirecionam para `?ep=<id>`. O `episodeUrl()` no app.js passou a gerar `/ep/<id>.html`, então compartilhar/copiar usam o preview correto. Geração integrada ao `publish_site.py` (`write_share_pages`), então cada publish re-sincroniza (e remove páginas órfãs).
- **Como evitar no futuro:** NUNCA depender de JS para meta de compartilhamento em site estático. Toda vez que um episódio for publicado/preview de share for necessário, ele precisa de um HTML estático alcançável com os `<meta>` certos (ou SSR/edge). Limitação conhecida: links `?ep=` antigos continuam com preview genérico — só os novos `/ep/` têm preview correto (corrigir os antigos exige nginx SSI/edge/SSR, documentado como futura Opção B).

## [2026-08-08] Página /noticias: filtro "não funcionava" (hidden anulado por display:grid) + scroll infinito (mês colapsável)

- **Contexto:** home do portal /noticias gerada por `gen_noticias.py`; dono reportou que os filtros de editoria não escondiam nada e que a lista única de 124 artigos era má UX.
- **O que acontece:** (1) clicar em "Diário"/"Brasil e Mundo" não escondia os itens; (2) página única infinita sem separação temporal.
- **Causa raiz:** (1) o script de filtro setava `it.hidden=true`, mas o CSS `.grade-item{display:grid}` ANULA a regra UA `[hidden]{display:none}` (mesmo pitfall do app, mas aqui sem a regra `[hidden]{display:none!important}` no CSS inline). Meu teste CDP inicial checava o ATRIBUTO `hidden`, não o `display` computado — o dono estava certo e o teste estava errado. (2) não havia agrupamento.
- **Solução:** aplicada — `[hidden]{display:none!important}` no CSS; grade agrupada em `<section class="grade-mes">` por mês (mês atual expandido; anteriores colapsados com 6 itens + botão "Ver todos de Mês"); filtro combinado com colapsagem (seções sem itens visíveis ganham `.mes-vazio` e escondem o header); anúncios entre seções; `alt` descritivo nas imagens (hero via template — o `hero_html` inline era código morto). **PITFALL de geração: `"\n".join(grade_items)` em cima de um `grade_items` que JÁ era string** → separa caractere por caractere (HTML inteiro com newline a cada char, sem erro de sintaxe!). Ao mudar a estrutura de uma lista para string unida, REMOVER o join do return (o .format recebe a string pronta).
- **Como evitar no futuro:** (a) em testes de filtro, medir `getComputedStyle(el).display`, nunca só o atributo `hidden`; (b) regra `[hidden]{display:none!important}` em qualquer folha que use `display:*` em elementos ocultáveis; (c) ao refatorar geradores, conferir joins duplos (join de string = separa chars).

---

*Mantido por: Hermes Agent | Última atualização: 2026-08-08*

---

## [2026-08-16] Cron diário abortou em 6s sem gerar log — scripts perderam bit de execução

- **Contexto:** Em 16/08 o `logs/daily-2026-08-16.log` não existia às 06:05 e nenhum processo do pipeline rodava, apesar do crontab `0 6 * * *` disparar o `scripts/cron-wrapper.sh` (session do cron fechou em 06:00:07). No dia 15/08 o build só começou às 06:43 (mesma falha silenciosa na 06:00).
- **O que aconteceu:** O wrapper era invocado diretamente pelo cron (`/home/osmar/.../cron-wrapper.sh`), que exige o bit de execução. O arquivo estava `-rw-rw-r--` (mode 100644 no git) → `Permission denied` (exit 126) → cron descarta a saída (sem MTA) → dia vazio, sem log.
- **Causa raiz:** A recuperação/convergência de branches de 15/08 (checkout de arquivos) restaurou `scripts/cron-wrapper.sh`, `cron-daily.sh`, `cron-wrapper-v2.sh`, `daily-collect.sh` e `delivery_health_check.sh` sem o bit `+x` (modo 644 no índice git).
- **Solução aplicada:** `chmod +x` nos 5 scripts + `git update-index --chmod=+x` + commit `cc0c60f` (push). Build do dia rodou manualmente em seguida.
- **Como evitar/repetir no futuro:** Ao restaurar/checkout de arquivos, conferir `git ls-files -s scripts/*.sh` (esperado `100755` para entrypoints de cron). Diagnóstico rápido de "cron não rodou": `journalctl -u cron --since 'HH:55'` → procurar `CMD (...cron-wrapper.sh)` + `Permission denied`.

---

## [2026-08-16] Catálogo ordenava especiais por dia da semana (sort de string RFC-2822)

- **Contexto:** Ao publicar o episódio de 16/08, `public/data/episodes.json` mostrava no topo especiais de 12/08 (quarta-feira) — o card de destaque do site exibia um episódio de 4 dias atrás, e o diário do dia estava na posição ~148.
- **O que aconteceu:** `sort_key` em `publish_site.py` retornava `pubDate` (RFC-2822, ex. `"Wed, 12 Aug 2026 23:12:14 +0000"`) como string e o Python comparava lexicograficamente → ordem alfabética por dia da semana (`Wed > Tue > Thu > Sun > Sat > Mon > Fri`), não cronológica.
- **Causa raiz:** Comentário do código dizia "RFC 2822, comparável diretamente" — incorreto: só é comparável como string se o formato for ISO-8601.
- **Solução aplicada:** `sort_key` agora normaliza com `email.utils.parsedate_to_datetime(pub).isoformat()` e ordena por tupla `(1, data)` para diários (primeiro) e `(0, pubDate)` para especiais (depois), ambos desc — conforme SKILL do web-jornal ("diários primeiro, depois especiais, mais recente primeiro"). Rebuild do catálogo/feed feito; `2026-08-16` agora é o card de destaque.
- **Como evitar/repetir no futuro:** Nunca comparar RFC-2822 como string; normalizar para datetime/ISO antes de ordenar. Teste rápido: primeiro item do catálogo deve ser o episódio mais recente.
