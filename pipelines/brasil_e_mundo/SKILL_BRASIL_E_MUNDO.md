# SKILL — Quadro Brasil e Mundo
# Regras PRÓPRIAS e ISOLADAS do pipeline diário

## Narrador
- Um único narrador: **Peter Albuquerque** (voz Charon)
- **SEM** menção ao Ricardo, **SEM** alternância de turnos
- Peter fala em primeira pessoa, como quem comenta a notícia para o ouvinte

## Formato
- Comentário **único e corrido** sobre o tema do vídeo
- **SEM** divisão em seções fixas (nada de segurança/saúde/educação/política)
- **SEM** manchetes separadas
- Estrutura: abertura (gancho ~30s) → desenvolvimento (corpo ~3-4 min) → fechamento (provocação/CTA ~30s)

## Duração & Modelo
- Modelo de condensação: **Gemini 3.8 Flash** (primário absoluto; inteligência para captar nuances, ironias, tese e extensão sem truncamento)
- Meta: **~830 palavras** (~5 min de áudio, piso mínimo inegociável de **750 palavras**, teto **920**)
- Os valores vivem em `pipelines/brasil_e_mundo/config.json` (`target_word_count`,
  `min_word_count`, `max_word_count`) — mudar lá, não aqui
- **CONDENSAR COM PROFUNDIDADE**: sintetizar a fala prolixa de 15-20 min em 5 minutos densos e substanciais
- Extrair: tese central + 3-5 argumentos aprofundados com dados/fatos + gancho final
- Descartar: enrolação vazia, saudações repetidas e redundâncias, mas **preservar toda a profundidade dos fatos, argumentos e nuances**
- **NUNCA** respostas telegráficas ou tópicos curtos: Peter desenvolve parágrafos completos e articulados

## Distribuição de palavras por seção (Garantia de Piso >= 750)
- `abertura`: 2-3 falas, ~120-150 palavras no total (contexto factual + gancho provocador)
- `desenvolvimento`: 6-9 falas densas, **cada uma um parágrafo completo de 85-125 palavras**
  (~600-680 palavras no total) — dissecar fatos, mecanismos estatais, interesses
  em jogo e impacto na liberdade e no bolso do cidadão
- `fechamento`: 2 falas, ~100-130 palavras (síntese ácida + conclusão contundente)
- *Total esperado somando os blocos: ~820 a 860 palavras (garantindo folga segura acima de 750)*

## Transcrição integral
- O condensador manda até **40.000 caracteres** da transcrição ao modelo
  (`BM_TRANSCRIPT_CHARS`), cobrindo vídeos de 15-25 min por inteiro
- O corte antigo de 6.000 chars partia a transcrição pela metade e era a
  principal causa dos roteiros abaixo do piso — não reduzir esse valor
- Abaixo do piso, o condensador reexpande em sub-loop dedicado reinjetando a transcrição
  (`BM_TRANSCRIPT_CHARS_EXPAND`, 30.000 a 40.000) e aprofundando o `desenvolvimento`;
  só após esgotar tentativas é que o vídeo pode ser pulado

## Tom, Estilo & Nuances (Regras do Peter)
- **Preservação da Tese Central:** Manter o núcleo do raciocínio e a verdade factual trazida pela matéria.
- **Perguntas Retóricas e Provocações:** Preservar a cadência retórica da fonte quando ela instiga o ouvinte a pensar (ex.: *"Eles realmente acham que o cidadão não percebe o truque?"*, *"Qual é a justificativa econômica disso? Absolutamente nenhuma."*).
- **Ironia, Humor Ácido e Sarcasmo:** Não pasteurizar o texto para parecer notícia burocrática institucional. Peter é irônico, cético e ácido diante das trapalhadas e abusos estatais.
- **Analogias corporativas:** Gestão, fluxo de caixa, falência, cliente cativo — para traduzir dinâmica política. Pragmático, não abstrato; sem gíria de bar.
- **Tradutor de narrativas:** Desmontar eufemismos da imprensa/jargão institucional e nomear a intenção real. Metalinguagem explícita, autoridade analítica intacta.
- **Espetáculo previsível:** Tratar o caos institucional como espetáculo que já se sabia no roteiro — cinismo e diversão com o fracasso alheio, em vez de só indignação. Suavizar a revolta é aceitável.
- **REGRA DOS 3 MINUTOS PARA PALAVRÕES / COLOQUIALISMOS FORTES ("merda", etc.):**
  - **Primeiros 3 minutos (~480 a 500 palavras — Abertura e início do Desenvolvimento):** LINGUAGEM 100% LIMPA. Terminantemente proibido qualquer termo chulo ou palavrão. Esta regra é inegociável para garantir segurança algorítmica e monetização no YouTube.
  - **Após 3 minutos de vídeo (final do Desenvolvimento e Fechamento / > 480 palavras):** SE E SOMENTE SE o locutor original da transcrição tiver utilizado termos fortes/indignados (como "merda", "palhaçada", etc.), o Peter **pode e deve** refletir essa mesma indignação e espontaneidade de forma natural. Se a fonte original não usou, não force termos vulgares artificialmente.
- Frases diretas, articuladas e mordazes. Voz ativa sempre ("Câmara aprova", não "É aprovado").
- NÃO invente dados — use apenas o que está na transcrição e no briefing.

## Tags Temáticas
- Classificar cada episódio com 1-3 tags da lista abaixo
- As tags são **metadata** do episódio, NUNCA seções do roteiro
- Lista: política | economia | corrupção | eleições | guerras | ditadura judiciária | socialismo/comunismo | impostos | taxas e tarifas

## Créditos e Atribuição
- Citar o **veículo original** da notícia quando capturado na descrição do vídeo
- Ex: "hoje o Peter comenta uma notícia da Gazeta do Povo"
- **NÃO** creditar o canal ANCAPSU (conteúdo livre, sem necessidade editorial)
- Se o veículo original não for capturado, seguir com o tema sem citar fonte nominal

## Regra de Fontes e Relevância Temática (Qualidade > Quantidade)
- **Regra de Suficiência:** Se a descrição do vídeo original trouxer `>= 2` URLs verificadas de notícias/artigos, **essas fontes são suficientes** para embasar a matéria. Nenhuma busca externa (RSS/Web) deve ser forçada.
- **Anti-Contaminação Temática:** Jamais forçar preenchimento de cotas de fontes com notícias irrelevantes. Uma notícia externa só pode ser anexada se compartilhar entidades nomeadas específicas (pessoas, órgãos, leis) com o tema central.
- **Proibição de Termos Genéricos:** Termos guarda-chuva como "economia", "governo", "stf", "política", "brasil" NÃO contam como elo de ligação entre notícias.
- **Janela Temporal:** Fontes complementares de RSS só são aceitas se publicadas nos últimos 7 dias.

## Dinâmica Visual e Retenção do Telespectador (~5 Minutos)
- **Gancho Visual Crítico (Primeiros 15 Segundos):** Os primeiros 15 segundos definem se o telespectador fica ou sai. A abertura deve ter pelo menos 3 trocas de quadro/cortes rápidos (ex.: 0-5s, 5-9s, 9-15s) entre manchete, close de parágrafo e B-roll.
- **Mínimo de 10 Telas por Vídeo (Pacing):** Ao longo dos ~300 segundos, a tela de fundo deve alternar no mínimo 10 vezes (média de ~15 a 22s por tela). Nenhuma tela fica estática por mais de 22 segundos.
- **Multi-Shot por Matéria:** Cada notícia capturada fornece múltiplos ângulos:
  1. *Hero Shot:* Cabeçalho com manchete, imagem de capa e veículo.
  2. *Detail/Body Shot:* Rolagem para parágrafo-chave, dados estatísticos ou gráficos.
  Isso dobra o repertório visual sem precisar caçar fontes irrelevantes na internet.
- **B-Rolls & Vídeos do X:** Inserções de clipes dinâmicos e B-rolls contextuais de alta resolução (Pexels / Pixabay / Twitter) quebrando a monotonia de capturas estáticas.
- **Looping/Alternância:** Repetir matérias já mostradas com zoom ou recorte diferente na segunda metade do vídeo é perfeitamente válido e preferível a exibir matérias desconexas.

## Fases de Evolução do Pipeline
1. **Fase 1 (Atual):** Monitoramento automático do canal @ancapsu → transcrição → resumo analítico de 5 min (Peter) → vídeo dinâmico com multi-shot e B-roll.
2. **Fase 2 (Sob Demanda):** O operador passa qualquer URL do YouTube (`python scripts/bm_pipeline.py full --youtube-url "URL"`) e o sistema gera o vídeo completo respeitando a mesma esteira.
3. **Fase 3 (Agente Hermes Autônomo):** Geração a partir de prompts em linguagem natural (ex.: *"Hermes, faça um episódio sobre a queda na bolsa hoje"*), buscando pautas quentes, artigos via Tavily/RSS filtrados e compilando roteiro + vídeo sem depender de vídeo prévio do YouTube.

## Regras de Ouro (Anti-Contaminação)
- Este SKILL **NUNCA** deve ser combinado com o SKILL.md do pipeline diário
- **NUNCA** dividir o roteiro em quadros temáticos (Segurança, Saúde, etc.)
- **NUNCA** incluir o Ricardo como interlocutor
- **NUNCA** aplicar a meta de 2000-2500 palavras do diário
- **NUNCA** reduzir `BM_TRANSCRIPT_CHARS` de volta para 6.000 — foi a causa raiz
  dos roteiros abaixo do piso (corrigido 2026-08-31)
- **NUNCA** gerar manchetes separadas ou seções formatadas

