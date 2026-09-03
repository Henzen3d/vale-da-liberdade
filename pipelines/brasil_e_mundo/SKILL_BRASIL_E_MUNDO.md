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

## Regras de Ouro (Anti-Contaminação)
- Este SKILL **NUNCA** deve ser combinado com o SKILL.md do pipeline diário
- **NUNCA** dividir o roteiro em quadros temáticos (Segurança, Saúde, etc.)
- **NUNCA** incluir o Ricardo como interlocutor
- **NUNCA** aplicar a meta de 2000-2500 palavras do diário
- **NUNCA** reduzir `BM_TRANSCRIPT_CHARS` de volta para 6.000 — foi a causa raiz
  dos roteiros abaixo do piso (corrigido 2026-08-31)
- **NUNCA** gerar manchetes separadas ou seções formatadas
