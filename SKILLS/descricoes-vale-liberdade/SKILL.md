---
name: descricoes-vale-liberdade
description: Gera descrições YouTube do Vale da Liberdade.
version: 1.1.0
author: Hermes Agent
license: MIT
category: content
platforms: [linux]
metadata:
  hermes:
    tags: [vale-da-liberdade, youtube, descricao, seo, ancap]
    related_skills: [youtube-journalistic-title-optimizer, web-jornal-production, vale-bm-mockup-video]
---

# Descrições — Vale da Liberdade

Esta skill orienta o **Hermes Agent** e os módulos do pipeline na criação e otimização de descrições para os vídeos publicados no canal do YouTube **Vale da Liberdade**.

## When to Use

- Gerar, revisar ou reescrever a descrição YouTube do **diário** (Peter Albuquerque + Ricardo Souto) ou do **especial Brasil & Mundo** (Peter Albuquerque solo).
- Pipeline diário etapa **2.6** (`pipeline.py full`) ou CLI `scripts/description_optimizer.py`.
- Pedido de descrição inline no chat (aplicar o prompt canônico em `prompts/hermes_agent_description_prompt.md`).

Não usar para títulos (skill `youtube-journalistic-title-optimizer` / `title_optimizer.py`).

## Motor automatizado (obrigatório)

Script canônico: `/home/osmar/web-jornal-vale-da-liberdade/scripts/description_optimizer.py`

| Fluxo | Como |
|---|---|
| Diário — Etapa 2.6 | `pipeline.py full` chama o script **depois** do título (2.5). Não bloqueia o dia. Grava `episodes/{date}-description.txt` e `pipeline.py` copia para `youtube_description` em `episodes/{date}-metadata.json`. O gerador de vídeo lê o mesmo `.txt`. |
| Diário — CLI | `python3 scripts/description_optimizer.py --date YYYY-MM-DD [--dry-run] [--force] [--print-prompt]` |
| BM — CLI | `python3 scripts/description_optimizer.py --video-id ID [--dry-run] [--print-prompt]` — lê `output/brasil_e_mundo/episodes/especial-{id}.json` |
| BM — upload | `bm_mockup_video.build_metadata` chama o mesmo motor e anexa capítulos pelos pontos altos do roteiro (não o nome do print). |
| Inline (agente) | Prompt canônico em `prompts/hermes_agent_description_prompt.md` (Prompt 1 diário / Prompt 2 BM) |

Backends: Gemini (`GEMINI_API_KEY`) → OpenRouter free → fallback determinístico. Compliance ANCAPSU e link do app são aplicados **depois** do LLM em `clean_youtube_description` / `strip_forbidden_urls`.

Cópias da skill: `.hermes/skills/content/descricoes-vale-liberdade/SKILL.md` (índice Hermes) e `SKILLS/descricoes-vale-liberdade/SKILL.md` (repo). Manter iguais.

## Regras de ouro (operacionais)

1. **ANCAPSU:** jamais incluir URLs ou menções de link do canal ANCAPSU (`@ancap_su`, `ancap.su`, youtube.com/@ancap_su, playlists/vídeos desse canal). Mesmo se vierem no JSON/transcrição, descartar.
2. **Persona do estúdio:** âncora libertário = **Peter Albuquerque** (ao lado de Ricardo Souto no diário; solo no BM). **Peter Turguniev** é o criador da rede — não citar como apresentador na bancada.
3. **Link canônico PWA:** sempre incluir `https://news.mob.tec.br` (única URL institucional obrigatória).
4. **Tamanho:** corpo 300–700 caracteres; total com rodapé + 0–3 hashtags ≤ ~1.000.

---

## 1. Função e Princípios Centrais

A descrição do YouTube no Vale da Liberdade cumpre 5 papéis:
1. **Gancho e Retenção Inicial:** As 2 a 3 primeiras linhas (visíveis antes do botão "mostrar mais") devem entregar com clareza sobre o que é o vídeo, a pergunta central e por que o tema importa.
2. **Descoberta e SEO Natural:** Contexto rico e vocabulário orgânico de pesquisa (entidades, órgãos, leis, cidades, valores financeiros) para o algoritmo do YouTube indexar com precisão, **sem empilhamento artificial de palavras-chave (keyword stuffing)**.
3. **Conversão e Comunidade:** Estimular comentários reais através de uma pergunta instigante ao final e direcionar ouvintes para o ecossistema (App PWA `https://news.mob.tec.br`).
4. **Alinhamento Editorial Libertário:** A análise sob a ótica da liberdade individual, propriedade privada, livre mercado e ceticismo contra o monopólio estatal da força — sem tom de manifesto panfletário ou comunicado corporativo.
5. **Separação Fato vs. Opinião:** Explicar o acontecimento de forma cristalina antes de apresentar a interpretação crítica do canal.

---

## 2. Formatos do Canal no Sistema

O sistema do Vale da Liberdade produz dois formatos principais de vídeo:

### Formato A: Webjornal Diário (Episódio Completo)
- **Apresentadores:** Peter Albuquerque (visão ancap/radical) e Ricardo Souto (visão conservadora/econômica).
- **Conteúdo:** 5 a 8 blocos de notícias (Segurança Pública, Saúde, Educação, Política Municipal/SC, Esportes e Comunidade, Brasil, Mundo e Rapidinhas).
- **Insumos de Entrada:**
  - Título otimizado do episódio (gerado por `title_optimizer.py` em `episodes/{date}-title.txt`).
  - Manchetes do dia e roteiro estruturado (`episodes/roteiro-{date}.json` ou `episodes/raw-{date}.md`).
- **Destino do arquivo:** `episodes/{date}-description.txt` e metadados em `episodes/{date}-metadata.json`.

### Formato B: Especiais Brasil & Mundo (BM)
- **Apresentador:** Peter Albuquerque (solo).
- **Conteúdo:** Comentário de 5 a 6 minutos focado em um acontecimento nacional ou internacional urgente.
- **Insumos de Entrada:**
  - Título do especial e matérias capturadas (`output/brasil_e_mundo/episodes/especial-{video_id}.json`).
  - URLs de referência jornalística (`fonte_referencias`).
- **Destino:** CLI `--video-id` imprime a descrição; o upload YouTube (`bm_mockup_video.py` / `youtube_uploader.py`) deve usar texto já higienizado (sem ANCAPSU, com `https://news.mob.tec.br`).

---

## 3. Identidade Editorial e Tom de Voz

- **Tom:** Direto, inteligente, provocativo, informal, brasileiro, crítico e analítico. Sarcasmo em nível moderado (2 a 3 numa escala de 1 a 5) — usado como tempero argumentativo, não como ataque descontrolado.
- **Personas no Estúdio:**
  - **Peter Albuquerque:** O âncora libertário. Ex-advogado tributário cético, focado em incentivos estatais perversos, custos invisíveis e legitimidade das ações estatais.
  - **Ricardo Souto:** O economista pragmático. Focado em dados, contas públicas, reflexos na vida prática do cidadão e soluções descentralizadas.
  *(Nota do Sistema: o apresentador na bancada é Peter Albuquerque. O nome Peter Turguniev refere-se ao criador por trás do ecossistema e não é usado como o locutor no estúdio).*

---

## 4. Estrutura Padrão da Descrição

A descrição final é formatada em blocos limpos e diretos:

### 1. Gancho + Tema Central (Prioridade Máxima — primeiras 2-3 linhas)
- O que aparece antes do "Mostrar mais" no YouTube (primeiros 150–200 caracteres).
- Começa direto no assunto.
- ❌ **PROIBIDO** saudações clichês: *"Olá pessoal"*, *"Sejam bem-vindos ao canal"*, *"No vídeo de hoje vamos falar"*, *"Fala galera"*, *"Bom dia/boa tarde"*.
- Responde de imediato: o que aconteceu e qual o conflito central.

### 2. Contexto e Destaques
- No **Diário**: sintetiza os principais temas abordados no episódio (ex.: decisão judicial, aumento de impostos local, pauta de segurança ou geopolítica) sem reescrever o roteiro inteiro.
- No **Especial BM**: contextualiza a notícia central, citando os órgãos, envolvidos e o impacto econômico/social.

### 3. Análise Libertária
- A leitura crítica: quem realmente paga a conta, quais os incentivos distorcidos criados pelo Estado e como a liberdade individual foi afetada.

### 4. Pergunta de Encerramento (Chamada para Interação)
- Uma pergunta provocativa e inteligente convidando o público a responder nos comentários (evita o pedido genérico "inscreva-se e deixe o like").

### 5. Links Canônicos e Rodapé Institucional
- **Link do App:** Sempre incluir:
  ```
  📱 Ouça no nosso app: https://news.mob.tec.br
  ```
- **Fontes Oficiais:** Citar URLs jornalísticas fornecidas nos dados de entrada (nunca inventar links).
- **Rede de Canais:** Quando aplicável, pode referenciar o portal irmão: `pimentanocafe.com.br/visaolibertaria`.

---

## 5. Regras Rígidas de Compliance e URLs

### 🚫 Regra Proibitiva sobre o Canal ANCAPSU
**É TERMINANTEMENTE PROIBIDO incluir URLs do canal ANCAPSU na descrição do YouTube**, em qualquer uma das suas variações:
- `https://www.youtube.com/@ancap_su`
- `@ancap_su`
- `https://ancap.su/`
- Links de vídeos ou playlists do ANCAPSU ou ANCAPSU Classic.

*Mesmo que esses links estejam presentes na transcrição ou dados brutos de entrada, o gerador deve descartá-los obrigatoriamente.*

### 🚫 Proibição de Alucinação de Links
- Nunca invente links, redes sociais ou URLs que não estejam explicitamente no contexto do episódio.
- Os únicos links padrão permitidos sem necessidade de estarem na notícia são:
  - `https://news.mob.tec.br` (App Oficial PWA)
  - `pimentanocafe.com.br/visaolibertaria` (quando houver referência contextual à rede)

---

## 6. Tamanho e Limites

- **Corpo:** 300 a 700 caracteres de texto principal.
- **Teto:** ~1.000 caracteres no total (corpo + rodapé do app + fontes + 0 a 3 hashtags).
- O limite do YouTube é de 5.000 caracteres, mas descrições concisas e focadas retêm mais e evitam flags de spam.

---

## 7. Hashtags

- **Quantidade:** De 0 a 3 hashtags no final.
- **Padrão sugerido:**
  - Diário: `#Webjornal #ValedaLiberdade #Noticias` (ou tag específica do tema principal como `#Economia` ou `#SantaCatarina`).
  - Brasil & Mundo: `#BrasilEMundo #Economia #Liberdade` (ou `#Geopolitica`, `#Impostos`).
- Nunca empilhar mais que 3 hashtags.

---

## 8. Formato de Saída Obrigatório

Ao ser acionado para produzir a descrição, retorne diretamente:

```markdown
### DESCRIÇÃO

[Texto da descrição com gancho inicial, contexto da pauta, análise crítica e pergunta final]

📱 Ouça também no nosso app: https://news.mob.tec.br

[Fontes de notícias reais, se houver]

### HASHTAGS

#Hashtag1 #Hashtag2 #Hashtag3
```

O motor Python já remove os cabeçalhos `### DESCRIÇÃO` / `### HASHTAGS` ao gravar o `.txt` final.

---

## 9. Exemplos de Saída

### Exemplo 1: Episódio Diário do Webjornal
**Entrada:**
- Título: *Câmara de Blumenau aprova novo IPTU e obras da BR-470 atrasam de novo*
- Destaques: Aumento de impostos municipais, atraso crônico na infraestrutura federal e nova regulação do SUS estadual.

**Saída:**
```markdown
### DESCRIÇÃO

Mais um aumento de imposto aprovado na Câmara municipal e novas promessas de conclusão da BR-470 que continuam apenas no papel. Quem realmente paga a conta dessa máquina pública?

Na edição de hoje do Webjornal Vale da Liberdade, Peter Albuquerque e Ricardo Souto analisam as recentes votações fiscais em Blumenau, os impactos diretos no bolso do pagador de impostos e a eterna ineficiência das obras estatais em Santa Catarina.

Você acredita que mais dinheiro na mão do governo vai resolver os gargalos da nossa região? Deixe sua opinião nos comentários.

📱 Ouça a edição completa no app: https://news.mob.tec.br

### HASHTAGS

#Webjornal #ValedaLiberdade #Blumenau
```

### Exemplo 2: Especial Brasil & Mundo (BM)
**Entrada:**
- Título: *Governo estuda criar nova taxa sobre compras internacionais*
- Contexto: Discussão sobre alíquotas de importação, lobby varejista e impacto sobre o consumidor comum.
- Fontes: `https://g1.globo.com/economia/...`

**Saída:**
```markdown
### DESCRIÇÃO

Sob a justificativa de "proteger a indústria nacional", o governo volta a articular o aumento de tarifas sobre compras internacionais. Mas proteção para quem?

Peter Albuquerque disseca o verdadeiro mecanismo por trás do lobby protecionista: como a aliança entre burocratas e grupos de interesse encarece a vida do consumidor para manter privilégios fiscais intactos. Porque quando o Estado fala em igualdade de concorrência, significa apenas igualdade na hora de cobrar impostos.

Qual será o limite para a taxação sobre o consumidor brasileiro? Comente abaixo.

📱 Acompanhe as análises no app: https://news.mob.tec.br

Fontes:
- G1 Economia: https://g1.globo.com/economia/...

### HASHTAGS

#BrasilEMundo #Economia #Impostos
```

---

## 10. Checklist antes de entregar

- [ ] Gancho funciona sozinho (tema claro antes de "mostrar mais")
- [ ] Sem clichês de abertura
- [ ] Zero URLs/menções de link ANCAPSU (`@ancap_su`, `ancap.su`)
- [ ] Apresentador = Peter Albuquerque (nunca Turguniev na bancada)
- [ ] `https://news.mob.tec.br` no rodapé
- [ ] 0 a 3 hashtags
- [ ] Corpo 300–700; total ≤ ~1.000

## Common Pitfalls

- Copiar links do ANCAPSU que vieram em `fonte_referencias` / descrição YouTube original — o strip é obrigatório.
- Citar Peter Turguniev como âncora (é o criador da rede, não o locutor).
- Começar com saudação; o higienizador remove algumas, mas o texto deve já nascer direto no fato.
- Inventar URLs de fonte. Só as que estão no contexto.
- Keyword stuffing e mais de 3 hashtags.
- Tratar a skill só como texto: o caminho executável do diário é `description_optimizer.py` na etapa 2.6; no BM o upload (`bm_mockup_video.build_metadata`) **precisa** chamar o mesmo motor — senão o YouTube recebe o início cru do roteiro.
- Capítulos YouTube do BM: rótulo = ponto alto do roteiro (`highlight_from_script`), nunca o nome do veículo do print ao fundo.

## Verification Checklist

- [ ] `skill_view(name='descricoes-vale-liberdade')` resolve para `content/descricoes-vale-liberdade`
- [ ] `python3 scripts/test_description_optimizer.py` passa
- [ ] Diário: `episodes/{date}-description.txt` sem ancap.su e com news.mob.tec.br
- [ ] BM: `python3 scripts/description_optimizer.py --video-id ID --dry-run` obedece as mesmas regras
