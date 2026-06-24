# Fontes de Notícias — Web Jornal Vale da Liberdade

Atualizado: 2026-06-22  
Base: diretrizes de monitoramento automatizado para o Vale do Itajaí e SC.  
Versão do sources.json: v1.2 (16 feeds nacionais adicionados).

## Blumenau / Vale do Itajaí
- ndmais.com.br/blumenau
- oblumenauense.com.br
- informeblumenau.com (bastidores políticos, prefeitura)
- blogdojaime.com.br (utilidade pública, pequenos delitos, eventos)
- mesorregional.com.br (segurança pública, ocorrências policiais)
- ajnoticias.com.br (trânsito, ocorrências pontuais)
- pancho.com.br (infraestrutura, mobilidade, crônicas locais)

## Alto Vale / SC
- altovaleagora.com.br (artigos de opinião, debates comerciais)
- altovalenoticias.com
- gcd.com.br (principal veículo do Alto Vale, Rio do Sul)
- jatv.com.br (cobertura hiperlocal, pequenos municípios)
- jav.inf.br (pré-candidaturas, transparência, educação)

## Santa Catarina
- nsctotal.com.br (colunas Café com Ânderson, Estela Benetti)
- ndmais.com.br/sc (cobertura regionalizada)
- blogdoprisco.com.br (bastidores Alesc, articulações partidárias)
- upiara.scc10.com.br (análise eleitoral)
- jovempan.com.br/sc
- reuters.com (edição BR)

## Brasil — Veículos Nacionais (RSS, v1.2)
> Adicionados em 2026-06-22 após validação em 3 rodadas via `validate_feeds.py`.
> Fontes descartadas na validação: Brasil 247 (vazio), Terra histórico (morto), Alexandre Garcia (404), Valor Política (404).

**Geral:**
- oglobo.globo.com — O Globo (100 itens, tier 1)
- correiobraziliense.com.br — Correio Braziliense (20 itens, tier 1)
- estadao.com.br — Estadão Política via Arc outboundfeeds (20 itens, tier 1)
- terrabrasilnoticias.com — Terra Brasil Notícias (74 itens, tier 2)
- metropoles.com — Metrópoles (127 itens, tier 1)
- veja.abril.com.br — Veja (20 itens, tier 1)
- valor.globo.com — Valor Econômico geral (100 itens, tier 1)

**Política (editorias segmentadas):**
- cnnbrasil.com.br — CNN Brasil Política (60 itens, tier 1)
- gazetadopovo.com.br — Gazeta do Povo Política (tier 1, intermitente)
- oglobo.globo.com — O Globo Política (31 itens, tier 1)
- g1.globo.com — G1 Política (20 itens, tier 1)
- veja.abril.com.br — Veja Política (20 itens, tier 1)
- metropoles.com — Metrópoles Política (intermitente, tier 1)

**Economia (editorias segmentadas):**
- gazetadopovo.com.br — Gazeta do Povo Economia (10 itens, tier 1)
- oglobo.globo.com — O Globo Economia (50 itens, tier 1)
- g1.globo.com — G1 Economia (20 itens, tier 1)
- veja.abril.com.br — Veja Economia (14 itens, tier 1)

## Brasil — Agências e Portais (v1.1, já existiam)
- g1.globo.com/brasil — G1 Brasil (tier 1, 0 itens em 22/06 — pode precisar URL alternativa)
- g1.globo.com/sc — G1 Santa Catarina (14 itens, tier 1)
- agenciabrasil.ebc.com.br — Agência Brasil (10 itens, tier 1)
- cnnbrasil.com.br — CNN Brasil geral (60 itens, tier 1)
- bbc.com/portuguese — BBC Brasil (29 itens, tier 1)

## Internacional (v1.1)
- bbc.com/news/world — BBC World Service (33 itens, tier 1)
- reuters.com — Reuters Brasil (~~enabled: false~~ feeds.reuters.com não responde)
- apnews.com — AP News (~~enabled: false~~ rsshub.app não responde)

## Brasil — Planejados / A testar
- g1.globo.com — G1 Brasil (tentar `/dynamo/brasil/rss2.xml` se persistir vazio)
- folha.uol.com.br — Folha de S.Paulo (paywall, sem RSS público confiável)
- gov.br / camara.leg.br / senado.leg.br — Portais governamentais (sem RSS)
- exame.com — Revista Exame (sem RSS público)
- neofeed.com.br — Neofeed (sem RSS público)
- bloomberg.com — Bloomberg (EN, paywall)

## Economia — Planejados / A testar
- bloomberg.com (EN)
- exame.com

## Tech / IA
- arxiv.org
- techcrunch.com
- theverge.com
- wired.com

## Segurança / Jurídico
- gov.br/mj
- pf.gov.br
- ssp.sc.gov.br
- defesacivil.sc.gov.br
- casanoficial (saneamento)

## Esportes
- ge.globo.com
- lance.com.br

## Saúde
- gov.br/saude
- fiocruz.br

## Educação
- gov.br/educacao
- ubec.edu.br
- capes.gov.br

---
## Perfis e Canais Sociais
- Valther Ostermann — @falavalther (Instagram, crônicas políticas Blumenau)
- Portal Mesorregional — @mesorregional (YouTube/Instagram, segurança)
- Defesa Civil SC — @DefesaCivilSC (X/Instagram, alertas meteorológicos)
- CASAN — @casanoficial (X/YouTube, saneamento)
- SSP/SC — @sspsc_oficial (X/Portal, segurança pública)
- Prefeitura de Blumenau — @prefeituradebnu (decretos, nomeações)

## Formato Recomendado por Fonte
- RSS Feed: informeblumenau, oblumenauense, jatv, blogdoprisco, ndmais
- Scraping WordPress: blogdojaime, mesorregional
- API JSON: ndmais.com.br/sc
- Scraping categorias: gcd.com.br
- Scraping sitemap: upiara.scc10.com.br
- Scraping home: ajnoticias.com.br, pancho.com.br
