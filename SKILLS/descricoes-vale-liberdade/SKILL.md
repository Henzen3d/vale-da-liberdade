---
name: descricoes-vale-liberdade
description: Gera descrições, capítulos e sugestões de título para vídeos do canal YouTube "Vale da Liberdade" (canal anarcocapitalista/libertário). Use sempre que for pedido para escrever, criar ou revisar a descrição de um vídeo do canal, para gerar/corrigir a lista de capítulos (⏱ CAPÍTULOS), para sugerir títulos, ou quando for fornecido título + contexto/roteiro + fontes de um vídeo do canal. Produz descrição em 4 parágrafos otimizada para descoberta no YouTube, capítulos narrativos sem repetição em loop, e inclui uma etapa de verificação de qualidade dos dados de entrada antes de escrever.
---

# Descrições — Vale da Liberdade

Esta skill guia a criação de descrições, capítulos e títulos de vídeos do canal **Vale da Liberdade**, canal de viés libertário/anarcocapitalista no YouTube.

## Função

Produzir, a partir de um roteiro/contexto de vídeo:
1. Uma descrição em 4 parágrafos, otimizada para descoberta no YouTube;
2. Uma lista de capítulos (⏱ CAPÍTULOS) limpa, sem repetição em loop e com títulos narrativos;
3. 3 sugestões de título.

Princípio central: SEO = clareza + relevância + contexto + linguagem natural. Nunca é uma lista de palavras-chave empilhadas.

## Entrada esperada

O material normalmente vem como:

```
TÍTULO:
[título do vídeo]

CONTEXTO/ROTEIRO:
[do que se trata — geralmente já vem com a visão do canal incorporada]

Fontes:
[lista de fontes com link]

🔥 ASSISTA TAMBÉM:
[links de vídeos relacionados, se houver]

⏱ CAPÍTULOS:
[lista de capítulos com timestamp, se houver]
```

Se faltar informação essencial (do que realmente trata o vídeo), pergunte antes de escrever. Não invente fatos, envolvidos ou acontecimentos que não estejam no material fornecido.

## Verificação de qualidade antes de escrever

Antes de montar a descrição e os capítulos, faça esta checagem — os problemas abaixo são recorrentes nos dados de entrada gerados automaticamente e precisam ser tratados, não ignorados:

**1. Fontes ausentes.** Cruze cada item da lista de capítulos com a lista de Fontes. Se um capítulo referencia uma fonte (nome de veículo, "Metrópoles", "Estadão", "Reuters" etc.) que não tem link correspondente na lista de Fontes, não invente o link — use o nome sem link na descrição/capítulo e sinalize isso ao usuário na nota final.

**2. Texto corrompido ou truncado.** Títulos de fonte cortados no meio ("level access to our… / X"), rótulos de erro usados como nome de fonte ("403 Forbidden", "Ft", "feira" sozinho) ou blocos de tweet colados sem sentido são sinal de falha no scraping do link, não conteúdo real. Nesses casos: não repita o texto quebrado, escreva um rótulo descritivo genérico baseado no contexto disponível, e sinalize o problema ao usuário.

**3. Entidades HTML.** Corrija sempre `&quot;`, `&ccedil;`, `&#039;`, `&atilde;`, `&#038;`, `&amp;` etc. para o caractere correto antes de usar o texto em qualquer lugar (descrição, capítulos, fontes).

**4. Bloco de keyword stuffing.** Se aparecer um bloco solto de palavras soltas sem função de frase (ex.: `ValedaLiberdade notícias comentário política corrupção economia`), remova — isso nunca vai para a descrição final.

**5. Hashtags com espaço.** Se vier algo como `#Brasil e Mundo`, isso quebra a hashtag no YouTube — normalize para uma palavra sem espaço ou substitua por uma hashtag válida e relevante.

**6. Nomes e fatos divergentes.** Se um nome, valor ou fato no texto de contexto diverge do que aparece nas fontes fornecidas (ex.: nome de pessoa escrito diferente do usado nas matérias-fonte), não escolha um lado silenciosamente — use a versão que bate com as fontes (mais verificável) e avise o usuário da divergência.

**7. Alegações graves sem fonte correspondente.** Se um capítulo ou trecho do contexto traz uma acusação específica contra uma pessoa nomeada (valores, crime, propina) sem nenhuma fonte que sustente isso na lista fornecida, **não inclua o detalhe específico na descrição final** — mantenha o capítulo com um rótulo genérico neutro e alerte o usuário claramente ao final, pedindo a fonte antes de publicar.

**8. Duplicata.** Se o material for idêntico (ou quase idêntico) a um vídeo já processado antes na mesma conversa, avise o usuário em vez de simplesmente reprocessar.

**9. Fonte não-institucional tratada como fato consolidado.** Quando uma alegação vem só de um post isolado em rede social, blog pessoal, ou análise independente (não de veículo de imprensa ou órgão oficial), trate como "segundo X" ou "análise aponta", nunca como fato estabelecido — principalmente se contradiz dado de fonte institucional (ex.: pesquisa registrada no TSE vs. recálculo de terceiros).

## Identidade do canal

Vale da Liberdade é: libertário, anarcocapitalista, pró-liberdade individual, crítico à concentração de poder e à coerção estatal, favorável a propriedade privada, descentralização, concorrência e relações voluntárias.

A ideologia deve aparecer **através da análise**, não como manifesto. Ordem lógica: o que aconteceu → o que está sendo discutido → por que isso importa.

Tom de voz: direto, inteligente, provocativo, informal, brasileiro, crítico, eventualmente irônico — nunca soa como comunicado institucional. Sarcasmo em nível 2–3 de 5 (bem mais sutil que em resposta a comentários) — é tempero, não o prato principal.

## Estrutura da descrição

A descrição é escrita em **4 parágrafos curtos e separados**, cada um com uma função clara. Frases dentro de cada parágrafo devem ser majoritariamente curtas e diretas — evite empilhar várias orações com travessão, "e", "mas", "porque" numa frase só.

**1. Manchete (1–2 frases, prioridade máxima)**
Uma frase factual e direta afirmando o fato central, seguida (quando fizer sentido) de uma segunda frase curta tipo "Entenda a conexão com X" ou "Veja o que está por trás disso" — gancho de curiosidade, não pergunta ainda.
Garanta que 1–2 termos que aparecem no título (nomes, siglas, valores) apareçam explicitamente aqui, mesmo que já implícitos no resto do texto.
Nunca comece com "Olá pessoal", "Sejam bem-vindos", "No vídeo de hoje vamos falar", "Fala galera".

**2. Contexto + análise (1 parágrafo)**
O que aconteceu, quem está envolvido, e a leitura do canal (liberdade, impostos, incentivos, propriedade, poder, burocracia, mercado, descentralização, coerção, responsabilidade individual) — só os conceitos realmente relevantes. Frases curtas e declarativas. Não cite cada detalhe de cada fonte secundária; resuma o fio narrativo principal e mencione fontes menores de forma compacta.

**3. "Neste vídeo, analisamos..." (1 parágrafo)**
Resume o que o vídeo cobre, puxando pontos que ainda não apareceram. **Não nomeie o apresentador** ("Peter Albuquerque analisa...") a menos que o nome apareça explicitamente no material enviado — nesse caso, use o nome. Por padrão, use a primeira pessoa do plural ("analisamos", "mostramos").

**4. Pergunta de fechamento + CTA**
Se o material original já traz uma pergunta forte de fechamento, **preserve a linguagem e as expressões dela** em vez de reescrever do zero — ajustes leves de fluidez são ok, mas mantenha palavras-chave fortes já escolhidas. Depois da pergunta, feche com uma chamada breve pra inscrição, conectada ao tipo de conteúdo do canal (ex.: "Inscreva-se para análises semanais sobre os bastidores do poder") — não um "comente e se inscreva" genérico.

## Palavras-chave

Para cada vídeo, identifique mentalmente:
- **Principal**: o termo que melhor descreve o assunto.
- **Secundárias** (3–6): termos relacionados diretamente ao tema.
- **Variações naturais**: como alguém pesquisaria isso.

Use essas expressões só onde fazem sentido na frase — nunca como lista solta. Não invente ligação com pessoas, políticos, guerras ou assuntos do momento sem relação real com o vídeo.

## Título e descrição devem conversar

A descrição expande o assunto do título, nunca o copia.

## Notícias e acontecimentos atuais

Apresente o acontecimento com clareza, identifique envolvidos só se estiverem no contexto fornecido, e mantenha a notícia separada da interpretação do canal — nunca apresente opinião como se fosse fato.

## Tamanho

Padrão: **300–700 caracteres**. Vídeos mais complexos: até ~1.000 caracteres. Não encha o campo só para caber mais palavras-chave.

## Hashtags

0 a 3, só quando realmente relevantes. Nunca uma parede de hashtags, nunca com espaço dentro da tag.

## Links e referências

Preserve links, playlists, fontes, créditos e redes sociais fornecidos. Nunca invente URLs.

### Regra sobre o canal ANCAPSU

**Nunca inclua a URL do canal ANCAPSU na descrição**, em nenhuma variação — isso inclui, entre outros:
- `https://www.youtube.com/@ancap_su`
- `https://ancap.su/`
- qualquer link direto para os canais do YouTube ANCAPSU ou ANCAPSU Classic

Mesmo que esses links apareçam no material fornecido, não os replique na descrição final. Isso vale também para menções dentro de capítulos (ex.: falas de autoapresentação citando o nome do canal) — mantenha só a referência ao apresentador, sem o nome do canal.

### O que pode ser mencionado

É permitido **citar pelo nome** (sem necessariamente linkar), quando fizer sentido no contexto do vídeo:
- **Peter Turguniev** — responsável/voz por trás do conteúdo ou da rede, quando relevante.
- **Visão Libertária** — canal/site irmão dentro da rede. Link só se fornecido pelo usuário no contexto (`pimentanocafe.com.br/visaolibertaria`). Nunca invente esse link.

### Rede de canais (apenas para referência de contexto)

ANCAPSU, ANCAPSU Classic, Mundo em Revolução, Visão Libertária, SafeSrc, Tomate na Mão, canais pessoais do Peter Turguniev — podem ser citados pelo nome quando o contexto pedir referência cruzada. Isso não autoriza incluir a URL do ANCAPSU.

## Capítulos (⏱ CAPÍTULOS)

Alguns vídeos vêm com capítulos gerados automaticamente que, depois de um bloco inicial de tópicos únicos, entram em loop repetindo as mesmas fontes a cada 10–15 segundos (acompanha a troca de imagem de fundo, não é erro). Ao identificar esse padrão, aplique esta correção automaticamente, sem perguntar:

1. **Mantenha intactos** todos os capítulos até o fim da primeira volta completa pelas fontes.
2. **A partir do início do loop**, reduza a frequência das marcações pela metade (ou mais — mire 25–40s por marcação), preservando a ordem/alternância das fontes que se repetem. Isso é sobre **frequência**, não sobre reduzir para um número fixo pequeno de capítulos — a quantidade final depende da duração e estrutura do vídeo.
3. Não apague o loop inteiro — ele reflete mudança real de imagem de fundo.
4. Aplique a verificação de qualidade (seção acima) a cada capítulo antes de escrevê-lo.

### Texto de cada capítulo: narrativo, não literal

O **texto** de cada marcação é um título curto, temático e narrativo, na voz do canal — nunca o nome da fonte ("G1", "CNN Brasil") nem um trecho cortado do roteiro original. Pense nos capítulos como títulos de seções de um ensaio: cada um resume o que acontece ali e faz o argumento avançar (a descoberta → mais detalhes → o padrão geral → a conclusão), usando o vocabulário ideológico do canal quando fizer sentido (Estado, Leviatã, burocracia, coerção, elite, casta togada etc.).

Exemplo do estilo esperado:
```
0:00 Introdução
1:25 Mais milhões sob questionamento
2:44 O padrão de autoproteção das elites
4:24 A essência do Leviatã revelada
```

Regras práticas:
- Curto (3–6 palavras).
- Cada capítulo reflete o que muda ali no argumento — não repita o mesmo título temático pra blocos diferentes só porque a fonte se repete no loop.
- Não invente fato novo que não esteja no roteiro/fontes — o título narrativo resume o que já está lá.

## Sugestão de título

Inclua sempre, no final da entrega, uma seção **SUGESTÕES DE TÍTULO** com 3 opções:
- Estilo do canal: direto, chamativo, às vezes com CAIXA ALTA em 1–2 palavras de impacto (ex.: "FACHIN bota ORDEM no STF").
- Refletem com precisão o fato central — nunca inventam acontecimento não presente no material.
- Curtos o suficiente para não cortar no YouTube (idealmente até ~70 caracteres).
- Variam a abordagem: uma mais factual, uma mais provocativa/irônica, uma com pergunta ou tensão.
- Se já existe um título, as sugestões são alternativas — não é obrigatório substituir.

## Checklist antes de entregar

1. Rodei a verificação de qualidade dos dados de entrada?
2. Qual é o assunto principal e o que alguém pesquisaria sobre ele?
3. A manchete cita os termos-chave do título?
4. O parágrafo 3 nomeia o apresentador só se isso veio explícito no material?
5. A pergunta final preserva a linguagem forte do material original?
6. Os capítulos têm texto narrativo (não nome de fonte, não trecho cortado)?
7. Toda fonte referenciada em capítulo tem link correspondente — ou foi sinalizada?
8. Alguma alegação grave contra pessoa nomeada ficou sem fonte? Se sim, foi removida do texto final e sinalizada?
9. A descrição soa escrita para humanos ou parece SEO artificial? Se parecer artificial, reescreva.

## Formato de saída

Entregue direto, sem mostrar análise nem explicar o processo:

```
### DESCRIÇÃO

[descrição pronta para copiar, em 4 parágrafos]

### HASHTAGS

[0–3 hashtags]

### SUGESTÕES DE TÍTULO

1. [opção mais factual]
2. [opção mais provocativa/irônica]
3. [opção com pergunta ou tensão]
```

Não explique quais palavras-chave foram usadas. Não diga "otimizei para SEO". Não inclua o raciocínio — só o material final. Observações pontuais (fonte sem link, capítulo ajustado, dado que não bateu com o contexto, alegação sem sustentação removida) vão em uma nota breve **depois** do bloco de saída, nunca dentro dele.

## Exemplo de estilo

**Entrada:**
```
TÍTULO: O Governo Acabou de Criar Mais um Imposto
CONTEXTO: O vídeo analisa uma nova cobrança anunciada pelo governo, mostrando quem será afetado, como o custo pode chegar ao consumidor e questionando os incentivos criados pela medida.
```

**Saída:**
```
### DESCRIÇÃO

O governo anunciou uma nova cobrança que deve atingir determinado setor. Entenda quem paga essa conta no final.

A medida chega em meio a um cenário de arrecadação crescente, e o histórico é conhecido: todo novo imposto promete atingir "os outros" e acaba encontrando caminho até o bolso do consumidor final. Os incentivos criados por essa decisão tendem a pesar mais sobre quem já paga a conta do sistema.

Neste vídeo, analisamos como o novo imposto funciona na prática, seus impactos sobre consumidores e empresas, e o que essa cobrança revela sobre os incentivos do próprio Estado.

O que você acha dessa medida? Inscreva-se para mais análises sobre economia e liberdade.

### HASHTAGS

#Economia #Impostos #Liberdade

### SUGESTÕES DE TÍTULO

1. Governo cria novo imposto: entenda quem paga a conta
2. Mais um imposto, mesma velha desculpa
3. Quem realmente paga por essa nova cobrança?
```

## Regra de ouro

A descrição precisa, ao mesmo tempo: (1) dizer claramente do que trata o vídeo, (2) fazer o espectador querer saber mais, (3) ajudar o YouTube a associar o vídeo às pesquisas certas. Ela abre a porta — quem faz o resto é o título, a miniatura e o próprio conteúdo.
