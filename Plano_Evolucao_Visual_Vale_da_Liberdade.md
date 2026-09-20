# Plano de Evolução Visual --- Webjornal Vale da Liberdade

## 1. Objetivo

Transformar o pipeline atual do **Vale da Liberdade** em um sistema de
produção visual mais sofisticado, variado e inteligente, sem reconstruir
o que já funciona.

O objetivo não é substituir o pipeline Python nem fazer a IA renderizar
tudo. A proposta é adicionar uma camada de **Direção de Criação
Visual**, capaz de analisar cada pauta e decidir qual linguagem visual é
mais adequada.

### Princípio central

> O apresentador não precisa ser o vídeo inteiro. Ele deve ser a âncora
> de uma narrativa visual.

O sistema atual já possui uma base funcional:

-   apresentador/avatar;
-   identidade visual;
-   screenshots das fontes;
-   manchetes;
-   lower thirds;
-   ticker;
-   mudanças de background;
-   montagem automática;
-   publicação recorrente.

A evolução proposta é passar de:

**notícia → roteiro → avatar + site ao fundo**

para:

**notícia → análise editorial → conceito visual → plano de cenas →
geração dos elementos → montagem → avaliação visual → publicação**

------------------------------------------------------------------------

# 2. Papel da IA de Direção Visual

A IA não deve simplesmente receber a instrução:

> "Melhore este vídeo."

Ela deve atuar como um **diretor de criação visual**.

Suas responsabilidades:

1.  analisar a pauta;
2.  entender a natureza da notícia;
3.  analisar as fontes e materiais disponíveis;
4.  conhecer a identidade visual do canal;
5.  analisar vídeos anteriores;
6.  detectar repetição visual;
7.  escolher uma linguagem visual adequada;
8.  propor novas soluções;
9.  transformar a ideia em um plano de cenas;
10. indicar quais componentes existentes podem ser reutilizados;
11. sugerir novos componentes quando necessário;
12. avaliar o resultado renderizado;
13. sugerir correções.

------------------------------------------------------------------------

# 3. Arquitetura conceitual

``` text
                    ┌───────────────────┐
                    │   FONTES / PAUTA  │
                    └─────────┬─────────┘
                              │
                              ▼
                    ┌───────────────────┐
                    │   EDITOR IA       │
                    │ contexto + roteiro│
                    └─────────┬─────────┘
                              │
                              ▼
                    ┌───────────────────┐
                    │ VISUAL DIRECTOR   │
                    │ conceito visual   │
                    └─────────┬─────────┘
                              │
                              ▼
                  ┌────────────────────────┐
                  │ SCENE PLAN / JSON      │
                  │ sequência + componentes│
                  └────────────┬───────────┘
                               │
                               ▼
              ┌─────────────────────────────────┐
              │         PIPELINE PYTHON         │
              │                                 │
              │ avatar / áudio / imagens /      │
              │ HTML / gráficos / FFmpeg        │
              └────────────────┬────────────────┘
                               │
                               ▼
                       ┌──────────────┐
                       │ VÍDEO FINAL  │
                       └──────┬───────┘
                              │
                              ▼
                    ┌───────────────────┐
                    │ VISUAL QA IA      │
                    │ análise de frames │
                    └─────────┬─────────┘
                              │
                       ┌──────┴──────┐
                       │             │
                       ▼             ▼
                    APROVADO      CORRIGIR
```

------------------------------------------------------------------------

# 4. Primeiro passo --- não alterar o pipeline

Antes de implementar grandes mudanças:

-   preservar o pipeline atual;
-   criar uma camada paralela de experimentação;
-   registrar cada conceito visual;
-   testar os novos componentes isoladamente;
-   comparar o resultado com o vídeo atual.

A primeira versão do sistema deve ser **assistida**, não totalmente
autônoma.

Fluxo inicial:

``` text
Pauta
  ↓
IA sugere conceito visual
  ↓
Humano aprova
  ↓
Python executa
  ↓
Vídeo
```

Somente depois:

``` text
Pauta
  ↓
IA escolhe conceito
  ↓
Python executa
  ↓
QA
  ↓
Publicação
```

------------------------------------------------------------------------

# 5. Biblioteca de linguagens visuais

Criar uma biblioteca de linguagens que a IA possa escolher.

## 5.1 Padrão / Standard

Uso:

-   notícia simples;
-   atualização factual;
-   notícia curta;
-   assuntos sem necessidade de recursos especiais.

Elementos:

-   apresentador;
-   headline;
-   screenshot;
-   lower third;
-   ticker.

É o fallback do sistema.

------------------------------------------------------------------------

## 5.2 Breaking News

Para acontecimentos recentes ou de alta relevância.

Elementos possíveis:

-   headline grande;
-   entrada rápida;
-   transições mais enérgicas;
-   alerta visual;
-   relógio/data;
-   fonte em destaque;
-   atualização de informações.

Evitar exagero para não transformar toda notícia em "breaking".

------------------------------------------------------------------------

## 5.3 Investigação / Dossiê

Ideal para:

-   denúncias;
-   investigações;
-   corrupção;
-   documentos;
-   relações entre pessoas;
-   cronologias complexas.

Linguagem:

-   fundo escuro;
-   documentos;
-   fotografias;
-   conexões;
-   linhas;
-   marcadores;
-   zoom;
-   destaques;
-   timeline.

O objetivo é transmitir sensação de investigação sem recorrer a clichês
exagerados.

------------------------------------------------------------------------

## 5.4 Documento

Quando a fonte principal é:

-   decisão judicial;
-   despacho;
-   relatório;
-   contrato;
-   publicação oficial;
-   documento administrativo;
-   tabela.

O documento vira o objeto principal da narrativa.

Exemplo:

``` text
documento inteiro
      ↓
aproximação
      ↓
trecho relevante
      ↓
destaque
      ↓
explicação do apresentador
```

Esse recurso pode substituir o simples screenshot estático.

------------------------------------------------------------------------

## 5.5 Timeline

Para acontecimentos em sequência.

Exemplo:

``` text
EVENTO 1 ─── EVENTO 2 ─── EVENTO 3 ─── HOJE
```

Cada acontecimento pode entrar progressivamente.

Ideal para:

-   crises;
-   processos judiciais;
-   decisões políticas;
-   investigações;
-   eleições;
-   mudanças legislativas.

------------------------------------------------------------------------

## 5.6 Comparação / Antes × Depois

Usar split-screen.

Exemplos:

-   promessa × resultado;
-   declaração antiga × declaração atual;
-   dado anterior × dado atual;
-   situação A × situação B.

A IA deve identificar automaticamente quando uma pauta possui uma
estrutura comparativa.

------------------------------------------------------------------------

## 5.7 Quote Card

Quando uma declaração é central.

Estrutura:

``` text
FOTO / VÍDEO

"IDEIA PRINCIPAL DA DECLARAÇÃO"

Fonte
Data
```

Depois:

**apresentador comenta o contexto.**

------------------------------------------------------------------------

## 5.8 Dados / Infográfico

Para:

-   inflação;
-   PIB;
-   impostos;
-   pesquisas;
-   gastos;
-   números de orçamento;
-   estatísticas;
-   crescimento/queda.

O número principal pode aparecer grande:

``` text
      5,7%

   INFLAÇÃO

       ↑
     +0,6 p.p.
```

A IA deve determinar quais dados realmente merecem visualização.

------------------------------------------------------------------------

## 5.9 Mapa

Para assuntos que envolvam localização.

Exemplos:

-   cidades;
-   estados;
-   países;
-   rotas;
-   fronteiras;
-   eleições;
-   comércio;
-   relações internacionais.

O mapa deve aparecer apenas quando acrescentar compreensão.

------------------------------------------------------------------------

## 5.10 Person Profile

Quando a notícia gira em torno de uma pessoa.

Possibilidades:

-   retrato;
-   cargo;
-   instituição;
-   histórico;
-   relação com outros personagens;
-   fatos relevantes.

Evitar transformar a tela em uma simples "foto de pessoa".

------------------------------------------------------------------------

## 5.11 Parallax / Foto com profundidade

Separar uma imagem em camadas:

``` text
BACKGROUND
     ↓
MIDDLE
     ↓
SUBJECT
     ↓
FOREGROUND
```

Adicionar movimento de câmera suave.

Objetivo:

dar vida a imagens estáticas sem precisar gerar um vídeo completo por
IA.

------------------------------------------------------------------------

## 5.12 Photo Wall

Para apresentar várias pessoas ou acontecimentos.

Pode utilizar:

-   mosaico;
-   entrada progressiva;
-   zoom;
-   destaque de uma pessoa;
-   agrupamento por tema.

------------------------------------------------------------------------

# 6. Componentes reutilizáveis

Em vez de criar cada vídeo manualmente, criar componentes visuais
parametrizados.

Sugestão inicial:

``` text
HeadlineReveal
DocumentZoom
DocumentHighlight
QuoteCard
Timeline
MapReveal
StatCounter
PhotoWall
PersonProfile
Comparison
BreakingNews
SourceCard
ImageFocus
ParallaxPhoto
ChapterCard
LocationCard
DataChart
```

Cada componente recebe parâmetros.

Exemplo:

``` json
{
  "component": "Timeline",
  "duration": 8,
  "events": [
    {
      "date": "2024",
      "label": "Evento inicial"
    },
    {
      "date": "2025",
      "label": "Nova decisão"
    },
    {
      "date": "2026",
      "label": "Situação atual"
    }
  ]
}
```

O Python executa o componente.

A IA decide como utilizá-lo.

------------------------------------------------------------------------

# 7. Scene Plan

O elemento central da nova arquitetura deve ser o **Scene Plan**.

Ele transforma uma decisão criativa em instruções executáveis.

Exemplo:

``` json
{
  "visual_concept": "dossie_institucional",
  "scenes": [
    {
      "start": 0,
      "end": 12,
      "component": "Presenter",
      "purpose": "hook"
    },
    {
      "start": 12,
      "end": 28,
      "component": "DocumentZoom",
      "purpose": "show_primary_source"
    },
    {
      "start": 28,
      "end": 40,
      "component": "QuoteCard",
      "purpose": "highlight_statement"
    },
    {
      "start": 40,
      "end": 55,
      "component": "Timeline",
      "purpose": "explain_sequence"
    }
  ]
}
```

O benefício é separar:

**decisão criativa**

de

**execução técnica**.

------------------------------------------------------------------------

# 8. HTML/CSS como motor gráfico

Uma tecnologia que merece ser investigada no pipeline é usar HTML/CSS
para componentes visuais.

Em vez de gerar tudo como PNG:

``` text
HTML/CSS
   ↓
Browser renderer
   ↓
frames
   ↓
vídeo
```

Isso permite construir componentes altamente parametrizados:

-   cards;
-   gráficos;
-   timelines;
-   documentos;
-   mapas;
-   comparações;
-   headlines;
-   tabelas;
-   animações;
-   painéis.

Vantagem:

um componente pode ser alterado por dados sem precisar ser redesenhado.

------------------------------------------------------------------------

# 9. Motion Graphics procedurais

Criar animações com código, e não necessariamente com geração de vídeo.

Exemplos:

-   números contando;
-   barras crescendo;
-   linhas de timeline;
-   documentos entrando;
-   zooms;
-   deslocamento de fotos;
-   transições;
-   mapas;
-   indicadores.

O sistema pode gerar dezenas de variações mantendo a mesma identidade.

------------------------------------------------------------------------

# 10. Dados → visual automaticamente

A IA deve analisar o roteiro e perguntar:

> Existe algum dado que ficaria mais claro visualmente?

Se sim:

``` text
texto
 ↓
extração de dados
 ↓
escolha do gráfico
 ↓
dados estruturados
 ↓
componente gráfico
 ↓
animação
```

Exemplos:

-   linha;
-   barras;
-   contador;
-   comparação;
-   ranking;
-   percentual.

------------------------------------------------------------------------

# 11. Visualização de fontes

Em vez de simplesmente colocar a página da fonte no background:

## Fluxo recomendado

``` text
captura da página
      ↓
identificação da informação relevante
      ↓
crop inteligente
      ↓
zoom
      ↓
destaque
      ↓
contextualização
```

A IA pode determinar:

-   qual trecho mostrar;
-   qual área destacar;
-   quando mudar;
-   quando voltar ao apresentador.

Isso cria uma sensação de direção de câmera.

------------------------------------------------------------------------

# 12. Visual Metaphor

A IA também deve procurar metáforas visuais adequadas.

Exemplos:

### Disputa

Split screen.

### Queda

Número + gráfico descendente.

### Crescimento

Indicador ascendente.

### Contradição

Antes × depois.

### Investigação

Dossiê + documentos + timeline.

### Relações entre pessoas

Mapa de relações.

### Processo longo

Timeline.

A metáfora deve melhorar a compreensão, não apenas decorar a tela.

------------------------------------------------------------------------

# 13. Análise do arquivo visual do canal

Criar um processo periódico de auditoria.

Selecionar:

-   últimos 10 vídeos;
-   últimos 30 vídeos;
-   ou uma amostra representativa.

Extrair frames.

A IA deve responder:

1.  quais padrões aparecem demais?
2.  quais componentes estão sendo subutilizados?
3.  quais tipos de notícia estão recebendo sempre o mesmo tratamento?
4.  quais novas linguagens poderiam ser introduzidas?
5.  o que está prejudicando a variedade?
6.  o que pode ser melhorado sem perder identidade?

------------------------------------------------------------------------

# 14. Índice de variedade visual

Criar métricas internas.

Exemplo:

``` text
APRESENTADOR       82%
SCREENSHOT         64%
LOWER THIRD        41%
TIMELINE            0%
MAPA                0%
INFOGRÁFICO         0%
QUOTE CARD         18%
DOCUMENTO            9%
SPLIT SCREEN         0%
PARALLAX            12%
```

Esses números não precisam ser métricas públicas.

Servem para orientar o diretor visual.

Se um formato estiver sendo usado em excesso, a IA deve procurar
alternativas.

------------------------------------------------------------------------

# 15. Regra de fadiga visual

Adicionar ao sistema uma regra:

> Evitar repetir a mesma estrutura visual em vídeos consecutivos quando
> a pauta permitir alternativa.

Exemplo:

``` text
Vídeo 101 → Standard
Vídeo 102 → Document
Vídeo 103 → Timeline
Vídeo 104 → Standard
Vídeo 105 → Comparison
```

Não significa obrigar variedade artificial.

A pauta sempre tem prioridade.

------------------------------------------------------------------------

# 16. Visual QA automático

Depois do render:

``` text
vídeo
 ↓
extração de frames
 ↓
IA analisa frames
 ↓
relatório
```

A análise deve verificar:

### Composição

-   apresentador bem enquadrado;
-   elementos não sobrepostos;
-   hierarquia visual.

### Legibilidade

-   textos suficientemente grandes;
-   contraste;
-   tempo de permanência.

### Consistência

-   identidade visual;
-   fontes;
-   margens;
-   posicionamento.

### Ritmo

-   excesso de cenas longas;
-   excesso de cortes;
-   repetição.

### Coerência

-   visual corresponde ao que está sendo narrado?
-   o elemento mostrado realmente ajuda?

------------------------------------------------------------------------

# 17. Ciclo Gauntlet Visual

O processo pode evoluir para:

``` text
CRIAR
  ↓
RENDERIZAR
  ↓
ANALISAR
  ↓
CRITICAR
  ↓
CORRIGIR
  ↓
RENDERIZAR NOVAMENTE
```

O crítico não deve saber apenas "se ficou bonito".

Deve avaliar contra um **quality bar**.

Exemplo:

``` text
Nota visual: 7,4/10

Problemas:
- screenshot permanece tempo demais;
- pouca variedade entre cenas;
- gráfico poderia substituir texto;
- transição 03 está abrupta.

Aprovado: NÃO
```

------------------------------------------------------------------------

# 18. Banco de referências visuais

Criar uma coleção de referências de:

-   telejornais;
-   documentários;
-   canais digitais;
-   broadcast graphics;
-   motion design;
-   infográficos;
-   visualização de dados;
-   document visualization.

A função da IA não é copiar estilos.

É identificar princípios:

-   composição;
-   ritmo;
-   hierarquia;
-   uso de espaço;
-   transições;
-   storytelling visual.

------------------------------------------------------------------------

# 19. Catálogo de novas tecnologias para investigar

O Diretor Visual deve periodicamente pesquisar tecnologias que possam
ser úteis.

Categorias:

### Broadcast graphics

Sistemas profissionais de gráficos em tempo real.

### Motion graphics procedural

Animação baseada em dados.

### Browser rendering

HTML/CSS/JS para produção visual.

### Data visualization

Gráficos animados.

### Maps

Mapas vetoriais e animações geográficas.

### Computer vision

Detecção de pessoas, documentos e regiões relevantes.

### Image generation

Criação de elementos visuais específicos.

### Video generation

B-roll curto quando fizer sentido.

### Depth / parallax

Animação de imagens estáticas.

### Virtual production

Ambientes e cenários virtuais.

### Automated editing

Detecção de ritmo, cortes e conteúdo.

A regra deve ser:

> Não adotar uma tecnologia porque é nova. Adotar quando ela resolver um
> problema visual real.

------------------------------------------------------------------------

# 20. Divisão entre modelos

Não usar necessariamente o modelo mais poderoso para todas as tarefas.

## Modelo avançado / Astra

Responsável por:

-   direção criativa;
-   análise de vídeos;
-   pesquisa de referências;
-   planejamento;
-   decisões complexas;
-   crítica visual;
-   descoberta de novas tecnologias.

## Modelos menores

Responsáveis por:

-   classificação;
-   extração;
-   tarefas repetitivas;
-   metadados;
-   transformações simples.

## Ferramentas especializadas

Quando necessário:

-   geração de imagens;
-   geração de vídeo;
-   voz;
-   remoção de fundo;
-   edição;
-   mapas;
-   gráficos.

## Python

Responsável por:

-   orquestração;
-   renderização;
-   FFmpeg;
-   captura de páginas;
-   gerenciamento de assets;
-   execução dos componentes;
-   montagem final.

------------------------------------------------------------------------

# 21. Fluxo de implementação recomendado

## Fase 0 --- Auditoria

Antes de mudar qualquer coisa:

-   catalogar componentes existentes;
-   catalogar estilos;
-   catalogar vídeos;
-   identificar padrões repetitivos;
-   registrar limitações atuais.

Resultado:

``` text
VISUAL_AUDIT.md
```

------------------------------------------------------------------------

## Fase 1 --- Visual Director manual

Criar um prompt para o modelo avançado.

Entrada:

-   roteiro;
-   fontes;
-   screenshots;
-   duração;
-   identidade visual.

Saída:

-   conceito;
-   linguagem visual;
-   sequência de cenas;
-   componentes necessários.

Ainda sem automação completa.

------------------------------------------------------------------------

## Fase 2 --- Scene Plan JSON

Transformar a saída em JSON estruturado.

O Python passa a consumir o plano.

------------------------------------------------------------------------

## Fase 3 --- Biblioteca de componentes

Criar os componentes mais importantes:

1.  DocumentZoom
2.  QuoteCard
3.  Timeline
4.  Comparison
5.  DataChart
6.  MapReveal
7.  ParallaxPhoto
8.  SourceCard

------------------------------------------------------------------------

## Fase 4 --- Motor HTML/CSS

Investigar quais componentes podem ser mais facilmente produzidos com
HTML/CSS e renderizados via navegador.

Prioridade:

-   cards;
-   gráficos;
-   timelines;
-   documentos;
-   comparações.

------------------------------------------------------------------------

## Fase 5 --- Visual QA

Automatizar:

``` text
render
 ↓
frames
 ↓
IA
 ↓
crítica
```

Inicialmente apenas gerar relatório.

Não corrigir automaticamente.

------------------------------------------------------------------------

## Fase 6 --- Correção automática

Depois de validar o QA:

``` text
crítica
 ↓
Scene Plan corrigido
 ↓
novo render
```

------------------------------------------------------------------------

## Fase 7 --- Análise do histórico

A IA recebe uma amostra dos vídeos anteriores.

Passa a considerar:

-   repetição;
-   frequência de componentes;
-   diversidade;
-   evolução visual.

------------------------------------------------------------------------

## Fase 8 --- Pesquisa contínua

Criar uma rotina periódica:

> "Encontre novas técnicas e tecnologias de storytelling visual que
> possam ser incorporadas ao pipeline do Vale da Liberdade."

A IA deve entregar:

-   tecnologia;
-   exemplo de uso;
-   benefício;
-   dificuldade;
-   custo;
-   compatibilidade;
-   prioridade.

------------------------------------------------------------------------

# 22. Matriz de prioridade

Cada nova ideia deve receber:

  Critério             Nota
  ----------------- -------
  Impacto visual      1--10
  Facilidade          1--10
  Reutilização        1--10
  Automação           1--10
  Custo               1--10
  Compatibilidade     1--10

Priorizar ideias que tenham:

**alto impacto + alta reutilização + boa automação + baixo custo.**

------------------------------------------------------------------------

# 23. Primeiros componentes a implementar

Sugestão de ordem:

### Prioridade 1

**DocumentZoom**

Porque já existem muitas matérias baseadas em páginas e documentos.

### Prioridade 2

**QuoteCard**

Baixa complexidade e grande impacto.

### Prioridade 3

**Timeline**

Muito útil para política e Justiça.

### Prioridade 4

**Comparison**

Ajuda a quebrar o padrão visual.

### Prioridade 5

**DataChart**

Eleva a percepção de qualidade.

### Prioridade 6

**ParallaxPhoto**

Grande impacto com custo relativamente baixo.

### Prioridade 7

**MapReveal**

Adicionar quando houver infraestrutura geográfica.

------------------------------------------------------------------------

# 24. O novo papel do apresentador

O apresentador deve continuar sendo uma constante de identidade.

Mas sua presença pode variar.

Exemplos:

### Plano A

Apresentador em tela cheia.

### Plano B

Apresentador lateral + conteúdo.

### Plano C

Apresentador em janela pequena.

### Plano D

Apenas voz enquanto o conteúdo ocupa a tela.

### Plano E

Entrada do apresentador depois de uma sequência visual.

Isso permite muito mais variedade sem perder a identidade do canal.

------------------------------------------------------------------------

# 25. Princípio de "menos, porém melhor"

A evolução visual não significa adicionar elementos continuamente.

Uma boa regra:

> Cada elemento na tela deve cumprir uma função.

Perguntar:

-   informa?
-   contextualiza?
-   direciona atenção?
-   melhora compreensão?
-   estabelece ritmo?

Se não fizer nenhuma dessas coisas, provavelmente deve ser removido.

------------------------------------------------------------------------

# 26. Resultado desejado

A evolução final deve permitir que dois vídeos sobre assuntos diferentes
pareçam pertencer ao mesmo canal, mas não pareçam ter sido produzidos
com exatamente o mesmo template.

Exemplo:

``` text
NOTÍCIA POLÍTICA
→ Presenter + Quote + Comparison

NOTÍCIA JUDICIAL
→ Presenter + Document + Timeline

NOTÍCIA ECONÔMICA
→ Presenter + DataChart + StatCounter

NOTÍCIA INTERNACIONAL
→ Presenter + Map + PhotoWall

INVESTIGAÇÃO
→ Presenter + Dossier + Document + Timeline
```

A identidade permanece.

A linguagem muda conforme a história.

------------------------------------------------------------------------

# 27. Prompt-base para o Diretor Visual

Este pode ser o ponto de partida para o agente:

> Você é o Diretor de Criação Visual do Vale da Liberdade. Analise a
> pauta, roteiro, fontes, imagens disponíveis e histórico visual recente
> do canal. Sua função não é simplesmente deixar o vídeo mais bonito,
> mas descobrir a melhor linguagem visual para contar esta história.
> Evite automaticamente o padrão apresentador + screenshot quando houver
> alternativa melhor. Procure oportunidades para usar documentos,
> timelines, comparações, gráficos, mapas, quote cards, parallax,
> visualizações de dados, motion graphics procedurais e outras técnicas
> adequadas. Preserve rigorosamente a identidade visual do canal.
> Priorize componentes reutilizáveis e soluções que possam ser
> automatizadas pelo pipeline Python. Explique o conceito, a função
> narrativa de cada cena, os componentes necessários, a dificuldade de
> implementação e possíveis tecnologias. Nunca introduza complexidade
> apenas por estética.

------------------------------------------------------------------------

# 28. Prompt para auditoria dos vídeos existentes

> Analise os vídeos recentes do Vale da Liberdade como um diretor de
> criação e especialista em broadcast design. Identifique padrões
> visuais repetitivos, componentes excessivamente utilizados, recursos
> subutilizados, oportunidades de melhoria, problemas de ritmo,
> composição, hierarquia e legibilidade. Depois proponha pelo menos 20
> linguagens visuais novas que possam ser incorporadas ao pipeline
> automatizado. Para cada uma, informe: quando usar, benefício
> narrativo, componentes necessários, dificuldade de implementação,
> potencial de reutilização e prioridade. Não recomende mudanças apenas
> por moda ou sofisticação técnica. Preserve a identidade visual
> existente.

------------------------------------------------------------------------

# 29. Prompt para pesquisa tecnológica

> Atue como pesquisador de tecnologia para produção automatizada de
> telejornalismo digital. Procure técnicas, ferramentas, bibliotecas e
> tecnologias que possam melhorar visualmente um pipeline Python que
> produz vídeos automaticamente. Priorize motion graphics procedural,
> HTML/CSS rendering, data visualization, mapas, computer vision,
> composição, parallax, geração de imagens, geração de vídeo e automação
> de edição. Para cada tecnologia encontrada, explique qual problema
> resolve, como poderia ser integrada ao pipeline, dificuldade, custo,
> dependências, limitações e prioridade. Não recomende tecnologia apenas
> porque é nova.

------------------------------------------------------------------------

# 30. Visão de longo prazo

A meta não é criar um gerador de vídeos cada vez mais complexo.

A meta é criar um:

## "Sistema de Direção Visual Automatizada"

Onde:

``` text
A história determina a linguagem.

A linguagem determina as cenas.

As cenas determinam os componentes.

Os componentes determinam a renderização.

O QA determina a próxima melhoria.
```

Isso permite que o sistema continue evoluindo mesmo quando o criador
humano não tiver uma nova ideia naquele dia.

O ser humano define:

**identidade, valores, qualidade e limites.**

A IA explora:

**possibilidades, combinações, referências e alternativas.**

O Python executa:

**produção, automação e escala.**

------------------------------------------------------------------------

# 31. Roadmap resumido

``` text
[ATUAL]
Apresentador + screenshots
        │
        ▼
[1]
Auditoria visual
        │
        ▼
[2]
Visual Director IA
        │
        ▼
[3]
Scene Plan JSON
        │
        ▼
[4]
Biblioteca de componentes
        │
        ├── Document
        ├── Timeline
        ├── Quote
        ├── Comparison
        ├── Data
        ├── Map
        └── Parallax
        │
        ▼
[5]
HTML/CSS + Motion Graphics
        │
        ▼
[6]
Visual QA
        │
        ▼
[7]
Correção automática
        │
        ▼
[8]
Análise dos vídeos anteriores
        │
        ▼
[9]
Pesquisa contínua de tecnologias
        │
        ▼
[OBJETIVO]
Direção Visual Automatizada
```

------------------------------------------------------------------------

# 32. Primeiro experimento recomendado

Antes de modificar o código do pipeline, realizar um experimento
controlado:

1.  selecionar 5 vídeos recentes;
2.  extrair aproximadamente 10--15 frames representativos de cada vídeo;
3.  fornecer os frames + roteiros ao modelo avançado;
4.  pedir uma auditoria visual;
5.  pedir 20 novas linguagens visuais;
6.  selecionar as 5 mais viáveis;
7.  escolher 2 componentes para implementação;
8.  implementar no pipeline;
9.  produzir novos vídeos;
10. comparar visualmente com os vídeos anteriores;
11. realizar nova avaliação por IA;
12. incorporar as melhorias que realmente funcionarem.

Esse experimento deve gerar evidências antes de uma grande refatoração.

------------------------------------------------------------------------

# 33. Critério final de sucesso

O pipeline será considerado visualmente evoluído quando:

-   a identidade do Vale da Liberdade continuar imediatamente
    reconhecível;
-   vídeos diferentes apresentarem estruturas visuais diferentes;
-   o tratamento visual for escolhido de acordo com a história;
-   screenshots deixarem de ser o principal recurso visual;
-   documentos puderem ser explorados cinematicamente;
-   dados puderem virar gráficos automaticamente;
-   acontecimentos puderem virar timelines;
-   declarações puderem virar quote cards;
-   localização puder virar mapa;
-   fotografias puderem ganhar movimento;
-   o apresentador continuar sendo a âncora;
-   o sistema conseguir descobrir novas linguagens sozinho;
-   e o QA conseguir identificar quando um vídeo está visualmente
    repetitivo.

**Objetivo maior: transformar a automação de produção em automação de
direção visual, sem perder o controle editorial humano.**

------------------------------------------------------------------------

# 34. Consolidação da Arquitetura V2 e Integração ao Repositório Real

A partir da auditoria técnica do repositório em setembro de 2026, o plano foi calibrado para se integrar diretamente aos scripts em produção, evitando reconstruções desnecessárias e custos excessivos de API.

### 34.1 Mapeamento com a Infraestrutura Existente
- **Motor Gráfico:** [`references/youtube/mockup-browser/mockup-brower.html`](references/youtube/mockup-browser/mockup-brower.html) já opera como canvas Full HD (1080p) com design tokens VDL e GSAP 3.14.2. Os novos componentes (`QuoteCard`, `DocumentZoom`, `Timeline`, `DataChart`, `Comparison`) são adicionados como extensões modulares neste mesmo arquivo.
- **Renderizador e Muxer:** [`scripts/bm_mockup_video.py`](scripts/bm_mockup_video.py) com Playwright headless, aceleração Intel VA-API (`h264_vaapi`) na GPU integrada Intel HD 630 e overlay do apresentador Peter Albuquerque com Chroma Key (`colorkey`).
- **Linha do Tempo:** [`scripts/bm_scene_timeline.py`](scripts/bm_scene_timeline.py) sincroniza as cenas proporcionalmente à contagem de palavras do áudio TTS sintetizado.

### 34.2 Principais Evoluções da Arquitetura V2
1. **`SceneBeat` v2 Semântico:** Desacoplamento entre `semantic_role` (papel narrativo), `visual_component` (qual card renderiza), `visual_variant` (estilo/animação) e `visual_payload` (dados).
2. **Visual Opportunity Detector (Nível 0 determinístico):** Varredura de citações, %, R$, decisões judiciais e termos temporais via regex e pontuação ponderada (scoring), chamando o Gemini apenas em caso de ambiguidade editorial (Nível 1).
3. **Visual Strategy & Densidade Visual:** Controle da proporção de tela do apresentador (30-45%), matérias (25-40%) e gráficos procedurais (20-35%), garantindo sobriedade jornalística.
4. **Memória Anti-Fadiga:** Rastreamento dos componentes dominantes dos últimos vídeos (`last_videos.json`) para impedir repetição do mesmo visual em edições consecutivas.
5. **QA Visual Bimodal:**
   - *Pré-render:* Validação instantânea de dados e integridade de arquivos antes de abrir o Playwright.
   - *Pós-render Amostral:* Inspeção rápida de 4 a 6 frames chave do MP4 final via FFmpeg/Pillow para aferir contraste e ausência de telas pretas sem re-renders pesados.

### 34.3 Pasta de Execução Técnica e Checklist
Toda a documentação técnica executável, contratos de dados, especificações GSAP/SVG e o guia passo a passo para marcação de tarefas foram centralizados em:
👉 **[`youtube/Evolucao-Visual/`](youtube/Evolucao-Visual/)**
- **[`CHECKLIST_IMPLEMENTACAO.md`](youtube/Evolucao-Visual/CHECKLIST_IMPLEMENTACAO.md):** Checklist simplificado com caixas `[ ]` e critérios de teste por etapa.
- **[`01_VISUAL_ARCHITECTURE_V2.md`](youtube/Evolucao-Visual/01_VISUAL_ARCHITECTURE_V2.md):** Arquitetura geral técnica.
- **[`02_SCHEMAS_E_CONTRATOS.md`](youtube/Evolucao-Visual/02_SCHEMAS_E_CONTRATOS.md):** Schemas JSON e dataclasses Python.
- **[`03_SPEC_COMPONENTES_GSAP.md`](youtube/Evolucao-Visual/03_SPEC_COMPONENTES_GSAP.md):** Markup HTML, SVG e timelines GSAP.
- **[`04_VISUAL_OPPORTUNITY_DETECTOR.md`](youtube/Evolucao-Visual/04_VISUAL_OPPORTUNITY_DETECTOR.md):** Regras de extração e scoring.
- **[`05_VISUAL_QA_E_METRICAS.md`](youtube/Evolucao-Visual/05_VISUAL_QA_E_METRICAS.md):** Protocolo de QA preventivo e amostral.

