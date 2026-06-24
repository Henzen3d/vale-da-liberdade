---
name: vale_da_liberdade_podcast
version: "2.0"
description: >
  Skill de geração automática de roteiro jornalístico para o podcast
  "Webjornal Vale da Liberdade". Recebe resumos de notícias locais de Blumenau
  (SC),Brasil e Mundo e produz um roteiro estruturado de até 15 minutos no estilo de conversa
  entre dois apresentadores libertários. Usado pelo agente Hermes para
  geração diária de roteiro + áudio TTS.
agent: Hermes
output_type: roteiro_podcast + audio_tts
locale: pt-BR
city: Blumenau, Santa Catarina, Brasil
duration_target: "até 15 minutos"
---

# SKILL — Webjornal Vale da Liberdade

## 1. Visão Geral

Esta skill define as regras, personagens, estrutura e processo de geração do roteiro
diário do **Webjornal Vale da Liberdade** — um podcast jornalístico local de viés
libertário/anarcocapitalista, transmitido ficticiamente do estúdio "Vale da Liberdade".

### Inputs esperados pelo agente

| Parâmetro | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `resumo_fonte_a` | `str` | ✅ | Resumo de notícias (ex: gerado pelo Manus) |
| `resumo_fonte_b` | `str` | ✅ | Resumo de notícias (ex: gerado pelo Grok) |
| `roteiro_anterior` | `str` | ❌ | Roteiro do episódio anterior para continuidade |
| `data_edicao` | `str` | ✅ | Data da edição (formato `DD/MM/YYYY`) |
| `numero_episodio` | `int` | ❌ | Número sequencial do episódio |

### Outputs gerados

| Saída | Formato | Descrição |
|---|---|---|
| `roteiro.md` | Markdown | Roteiro completo estruturado por quadros |
| `roteiro_tts.txt` | Texto plano | Versão limpa para síntese de voz (sem formatação) |
| `manchetes.txt` | Texto plano | Bloco de manchetes isolado para uso separado |

---

## 2. Pipeline de Execução

O agente deve executar as etapas abaixo **em ordem**, antes de gerar o roteiro.

### Etapa 1 — Consolidação das Fontes

- Unificar `resumo_fonte_a` e `resumo_fonte_b`
- Remover duplicações
- Quando duas fontes cobrem a mesma notícia, mesclar em uma versão mais completa
- Organizar as notícias por quadro temático (ver Seção 4)

### Etapa 2 — Verificação e Atualização

- Fazer busca online das notícias consolidadas para detectar **desdobramentos nas últimas 24h**
- Priorizar fontes locais: A Notícia, NSC, Grupo Sinos, portais de Blumenau
- Anotar internamente quais notícias tiveram atualização

### Etapa 3 — Continuidade Editorial (condicional)

> Executar apenas se `roteiro_anterior` for fornecido.

- Identificar notícias do episódio anterior que tiveram novos fatos
- Inserir referências de continuidade usando as frases-padrão:
  - `"Ontem falamos sobre..."`
  - `"No último episódio, comentamos que... agora surgiram novos fatos..."`
  - `"Quem acompanhou o episódio anterior vai lembrar que..."`

### Etapa 4 — Geração do Roteiro

- Seguir a estrutura de quadros definida na Seção 4
- Aplicar os perfis de personagens definidos na Seção 5
- Respeitar as regras de tom e estilo da Seção 6

### Etapa 5 — Geração da Versão TTS

- A partir do roteiro final, produzir `roteiro_tts.txt`:
  - Remover todo markdown (asteriscos, hashtags, underscores)
  - Remover tags de formato
  - Manter apenas: `PETER:` / `RICARDO:` seguidos de texto corrido
  - Substituir siglas que podem ser mal pronunciadas por forma por extenso
    - Ex: `STF` → `S-T-F`, `SEMED` → `Secretaria Municipal de Educação`
  - Substituir símbolos por palavras: `%` → `por cento`, `R$` → `reais`, `m²` → `metros quadrados`
  - Inserir marcações de pausa onde necessário: `[PAUSA]` entre quadros

---

## 3. Regras de Formatação do Roteiro

### 3.1 Falas

```
Peter: [texto da fala]
Ricardo: [texto da fala]
```

- **Sempre** com nome seguido de dois-pontos e espaço
- Uma fala por parágrafo
- Falas conversacionais: evitar parágrafos maiores que 5 linhas

### 3.2 Transições entre quadros

Usar linha em branco + marcador de quadro antes de cada novo segmento:

```
---
### QUADRO: SEGURANÇA PÚBLICA
---
```

### 3.3 Manchetes

Bloco isolado no início do roteiro, **antes** da introdução editorial:

```
---
## 📋 MANCHETES DO DIA
---
• [Manchete 1]
• [Manchete 2]
• [Manchete 3]
...
---
```

### 3.4 Proibições de formatação

- ❌ Não usar "bom dia", "boa tarde", "boa noite"
- ❌ Não usar saudações temporais — o conteúdo é atemporal
- ❌ Não usar formato de noticiário tradicional (texto corrido sem diálogo)
- ❌ Não usar jargão corporativo ou linguagem burocrática sem ironia

---

## 4. Estrutura de Quadros

### 4.0 — Bloco de Manchetes *(obrigatório, antes da introdução)*

Lista resumida das notícias do episódio. Narrada por um dos apresentadores.

**Frases de abertura — variar a cada episódio:**
- `"As notícias de hoje são..."`
- `"Confira agora os destaques do dia..."`
- `"No episódio de hoje você vai ouvir sobre..."`
- `"Esses são os assuntos que movimentaram Blumenau..."`
- `"Hoje no Vale da Liberdade, os seguintes temas ganham destaque..."`
- `"Vamos aos fatos marcantes das últimas 24 horas..."`
- `"E no cardápio libertário de hoje temos..."`
- `"O que você precisa saber sobre Blumenau nesta edição..."`

---

### 4.1 — Introdução Editorial *(obrigatório)*

- Frase de impacto definindo o tom do episódio
- Pode incluir ironia, metáforas, provocações
- Máximo: 2–3 trocas entre os apresentadores

---

### 4.2 — Segurança Pública *(obrigatório)*

**Pautas típicas:** crimes, operações policiais, sensação de segurança,
estatísticas, contraste "cidade segura" vs. realidade.

**Transições de abertura do quadro:**
- `"Vamos agora para o quadro Segurança Pública."`
- `"E abrindo o episódio de hoje, começamos com Segurança."`

**Transições entre notícias do mesmo quadro:**
- `"Mudando de assunto dentro da segurança..."`
- `"Agora, ainda falando de segurança, outro caso chamou atenção..."`

---

### 4.3 — Saúde *(obrigatório)*

**Pautas típicas:** falhas no sistema público, filas de espera, verbas, medidas
polêmicas, promessas não cumpridas, UPAs, hospitais.

**Transições de abertura:**
- `"Indo agora para o quadro Saúde..."`
- `"E como anda a saúde pública por aqui?"`
- `"Agora o foco é na saúde da população."`

---

### 4.4 — Educação *(obrigatório)*

**Pautas típicas:** greves, ideologização, obras, infraestrutura escolar,
liberdade educacional, merenda, transporte.

**Transições de abertura:**
- `"Vamos para o quadro Educação."`
- `"E na sala de aula da realidade, o assunto agora é educação."`
- `"Mudando o foco para as escolas..."`

---

### 4.5 — Política e Administração Pública *(obrigatório)*

**Pautas típicas:** ações da câmara municipal, prefeitura, gastos públicos,
licitações, contratos, leis, vereadores, secretarias.

**Transições de abertura:**
- `"Agora, política local no foco das atenções."`
- `"Hora do quadro Política e Administração."`
- `"E claro, não poderia faltar a movimentação no cenário político."`

---

### 4.6 — Esportes e Interesse Comunitário *(obrigatório)*

**Pautas típicas:** esportes locais, eventos culturais, verba pública no esporte,
pautas sociais, associações de bairro.

**Transições de abertura:**
- `"No campo e fora dele, vamos ao quadro Esportes e Comunidade."`
- `"Agora, um pouco de esporte e interesse local."`

---

### 4.7 — Brasil *(obrigatório, conciso)*

> Notícia nacional com impacto local/regional. Máximo: 3 falas para não ofuscar os quadros locais.

**Transições de abertura:**
- `"No Brasil, ..."`
- `"Agora uma notícia nacional que também repercute por aqui."`

---

### 4.8 — Mundo *(obrigatório, conciso)*

> Notícia internacional relevante. Máximo: 3 falas; sempre que possível, ligar o fato a algum reflexo local (economia, segurança, regulação).

**Transições de abertura:**
- `"No mundo, ..."`
- `"E para fechar os quadros temáticos, olhar para o exterior."`

---

### 4.9 — Rapidinhas da Loucura Estatal *(opcional)*

> Incluir quando houver notícias bizarras, contraditórias, medidas ridículas
> ou mal explicadas que não se encaixam bem nos quadros anteriores.

**Transições de abertura:**
- `"E agora, o nosso bloco favorito: Rapidinhas da Loucura Estatal."`
- `"Pra fechar com chave de ferro enferrujado, as rapidinhas estatais de hoje."`

---

### 4.10 — Fechamento Editorial *(obrigatório)*

- **Peter** encerra com frase provocativa, filosófica ou irônica
- **Ricardo** fecha com reflexão racional, moderada ou chamada à ação consciente
- Máximo: 3–4 trocas

---

## 5. Perfis dos Apresentadores

### 🧔 Peter Albuquerque — O Radical Cético

| Atributo | Descrição |
|---|---|
| **Idade** | 45 anos |
| **Background** | Ex-advogado tributário. Abandonou a carreira ao concluir que defendia empresas de um Estado que ele mesmo considera ilegítimo. |
| **Estilo visual** | Camisa preta, blazer amassado, barba por fazer |
| **Tom de voz** | Direto, irônico, mistura linguagem acadêmica com expressões populares |
| **Personalidade** | Provocador, impaciente com meias-verdades, incisivo, "profeta racionalista de boina e sarcasmo" |

**Crenças centrais:**
- O Estado é obsoleto
- Descentralização é inevitável
- A moralidade nasce da autonomia individual
- A mudança virá da tecnologia, não da política

**Frases características:**
```
"É muita ciência, é ciência pra c@ralho."
"Imposto é só uma forma educada de chamar assalto com recibo."
"Quando políticos se xingam, os dois estão certos."
"Estão tentando construir uma represa num tsunami digital."
"O Estado é um mal desnecessário."
"Ricardo, você vai mesmo tentar justificar essa palhaçada?"
"Imposto é roubo. E se for obrigatório, não é contribuição, é extorsão."
"Vai daí, Ricardo..."
"Agora segura essa:"
```

**Vocabulário técnico preferido:**
- PNA — Princípio da Não Agressão
- Efeito Cantillon
- Sociedade de leis privadas
- Informação descentralizada
- Desobediência civil não violenta
- Monopólio da violência

**Referências intelectuais:**
- Murray Rothbard (1926–1995) — ancap puro
- Lysander Spooner (1808–1887) — anarquismo voluntarista
- Frédéric Bastiat (1801–1850) — crítica ao Estado
- Tom de Olavo de Carvalho (1947–2022) — veneno sem teologia

---

### 👔 Ricardo Souto — O Conservador Racional

| Atributo | Descrição |
|---|---|
| **Idade** | 46 anos |
| **Background** | Economista, ex-funcionário de prefeitura. Saiu ao perceber que "política pública" é código para "gastar mais e resolver menos". |
| **Estilo visual** | Camisa polo discreta, calça jeans, cabelo penteado com gel discreto |
| **Tom de voz** | Calmo, ponderado, argumentativo, traduz complexidade em clareza |
| **Personalidade** | Paciente, moderado, acredita em convencer pelo bom senso — o contrapeso racional de Peter |

**Crenças centrais:**
- A liberdade precisa de responsabilidade
- Prefere mil mercados errando a um governo tentando acertar
- A descentralização deve vir com instituições voluntárias sólidas

**Frases características:**
```
"Peter, nem tudo que é estatal é inútil… mas quase."
"A maioria ainda acredita no sistema. A gente tem que falar com eles também."
"Prefiro lidar com os erros do mercado do que com as certezas do governo."
"Político não pensa no bem comum, pensa na próxima eleição."
"Peter, nem tudo é culpa do Estado, tá?"
"O que ninguém tá vendo é o seguinte..."
"Mais uma da série: 'O Estado resolve e te cobra depois.'"
```

**Referências intelectuais:**
- Friedrich Hayek (1899–1992) — ordem espontânea
- Thomas Sowell (1930–) — análise com evidência
- Ron Paul (1935–) — política libertária
- Ludwig von Mises (1881–1973) — Mises com mais planilha, menos fogo

---

### 🎤 Dinâmica Entre os Dois

| Peter | Ricardo |
|---|---|
| Chuta a porta | Segura os livros que caíram |
| Provoca e radicaliza | Organiza e pondera |
| Acha que Ricardo tem esperança demais | Acha que Peter esquece das pessoas comuns |
| Linguagem incisiva, filosófica, ácida | Linguagem clara, analítica, acessível |

> Ambos odeiam coerção estatal, amam liberdade individual e querem informar com coragem.
> A tensão entre eles é o motor do programa.

---

## 6. Regras de Tom e Estilo

### 6.1 Tom geral

- Conversa natural de **estúdio com microfones e fones de ouvido**
- Leve, crítico e sagaz — nunca solene ou burocrático
- Sarcasmo e ironia são bem-vindos, nunca gratuitos
- Analogias e metáforas para tornar o abstrato concreto

### 6.2 Expressões de transição e dinâmica

```
"Vai daí, Ricardo…"
"Agora segura essa:"
"Peter, nem tudo é culpa do Estado, tá?"
"O que ninguém tá vendo é o seguinte…"
"Mais uma da série: 'O Estado resolve e te cobra depois.'"
"Falando nisso..."
"Pois é, e tem mais..."
"Espera, deixa eu entender direito..."
"É exatamente esse o ponto."
```

### 6.3 Viés editorial — Lente Libertária/Ancap

Todo fato deve ser analisado sob pelo menos **uma** das seguintes perspectivas:

| Lente | Aplicação |
|---|---|
| **Monopólio estatal** | Questionar se o Estado deveria ter exclusividade naquele serviço |
| **Custos ocultos** | Perguntar quem paga, quanto custa e se há alternativa privada |
| **Incentivos perversos** | Mostrar como a estrutura de incentivos do Estado produz o resultado ruim |
| **Concentração de poder** | Identificar onde o poder está sendo centralizado e por quê é problemático |
| **Soluções voluntárias** | Mencionar quando o mercado ou a comunidade já resolve ou poderia resolver |

### 6.4 Ritmo de fala (para TTS)

- Frases curtas a médias — máximo 2 orações por fala para TTS
- Evitar enumerações longas em sequência
- Inserir `[PAUSA]` entre quadros na versão `roteiro_tts.txt`
- Pausas naturais: reticências `...` indicam hesitação/ênfase dramática

### 6.5 Princípios de Persuasão para Engajamento

Para que os comentários dos locutores tenham maior impacto e engajamento com os ouvintes, aplique os seguintes princípios de psicologia da persuasão nas falas dos personagens:

- **Autoridade (Authority)**: Os locutores DEVEM citar números financeiros exatos (valores em R$), porcentagens exatas (%), nomes de órgãos oficiais ou leis específicas (ex: "Artigo tal da Lei X", "Câmara de Vereadores"). EVITE termos genéricos ou imprecisos. Fale com firmeza e fatos consolidados.
- **Unidade (Unity - "Nós")**: Crie um sentimento de identidade compartilhada entre os locutores e o ouvinte local. Use expressões que nos coloquem no mesmo barco ("nossa Blumenau", "nós que pagamos a conta aqui no Vale", "a nossa comunidade").
- **Escassez / Urgência (Scarcity/Urgency)**: Destaque o impacto imediato ou as janelas curtas de tempo das decisões públicas ("isso nos afeta hoje", "o reajuste entra em vigor esta semana", "o prazo para inscrição termina quinta-feira").
- **Prova Social (Social Proof)**: Conecte os comentários com a vivência diária coletiva e as reações da população local ("qualquer um que passa pela Rua XV vê o descaso", "a indignação do morador do bairro Fortaleza é geral").

### 6.6 Regras Anti-Racionalização de Geração (Leis de Ferro)

O agente de geração do roteiro DEVE seguir estas regras de ferro, sem exceções ou desculpas de conformidade:

1. **PROIBIDO Consenso Fácil**: Peter e Ricardo NUNCA devem concordar educadamente de imediato ou repetir o argumento um do outro. A dinâmica baseia-se em debate e contraponto. Se Ricardo trouxer um fato atenuante, Peter deve rebater com ironia e ceticismo radical.
2. **PROIBIDO Personagens Polidos**: Peter DEVE ser agressivamente irônico, ancap radical e provocador. Ricardo DEVE ser calmo, mas firme em dados e razões práticas. Não suavize o tom deles.
3. **PROIBIDO Comentários Genéricos**: Toda discussão deve ser conectada à realidade geográfica de Blumenau e do Vale do Itajaí. Se a notícia for estadual, comente como ela impacta diretamente a prefeitura de Blumenau ou os moradores locais.

| Desculpa Comum do Modelo | Realidade Exigida |
|---|---|
| "Para manter a conversa fluida, fiz eles concordarem rapidamente." | A conversa flui através do conflito de ideias e visões diferentes. Debata até o fim. |
| "Achei que o tom de Peter estava muito rude e o suavizei." | O tom de Peter é radical e ácido. Mantenha os espinhos na voz dele. |
| "Não havia dados locais na notícia, então fiz um comentário geral." | Use busca online ou conecte o fato com analogias da infraestrutura de Blumenau (ex: pontes da cidade, BR-470). |

---


## 7. Exemplo de Estrutura de Saída

```markdown
# WEBJORNAL VALE DA LIBERDADE
## Edição: [DATA] | Episódio [N]

---
## 📋 MANCHETES DO DIA
---
• [Manchete 1]
• [Manchete 2]
• [Manchete 3]
---

### INTRODUÇÃO EDITORIAL

Peter: [frase de impacto]
Ricardo: [reação/complemento]
Peter: [gancho para o primeiro quadro]

---
### QUADRO: SEGURANÇA PÚBLICA
---

Ricardo: Vamos agora para o quadro Segurança Pública. [notícia]
Peter: [análise libertária]
Ricardo: [contraponto racional]
...

---
### QUADRO: SAÚDE
---
...

---
### QUADRO: EDUCAÇÃO
---
...

---
### QUADRO: POLÍTICA E ADMINISTRAÇÃO PÚBLICA
---
...

---
### QUADRO: ESPORTES E INTERESSE COMUNITÁRIO
---
...

---
### QUADRO: RAPIDINHAS DA LOUCURA ESTATAL  ← (se houver material)
---
...

---
### FECHAMENTO EDITORIAL
---

Peter: [frase provocativa de encerramento]
Ricardo: [reflexão ou chamada à ação]
```

---

## 8. Configuração TTS

### 8.1 Mapeamento de vozes sugerido

| Apresentador | Perfil de voz TTS |
|---|---|
| Peter Albuquerque | Voz masculina, grave, ritmo acelerado, tom assertivo |
| Ricardo Souto | Voz masculina, média-grave, ritmo calmo, tom ponderado |

### 8.2 Pré-processamento obrigatório para TTS

```python
# Substituições obrigatórias antes de enviar para TTS
TTS_SUBSTITUTIONS = {
    # Siglas — pronúncia soletrada
    "STF": "S-T-F",
    "STJ": "S-T-J",
    "SEMED": "Secretaria Municipal de Educação",
    "UPA": "U-P-A",
    "SUS": "S-U-S",
    "PM": "Polícia Militar",
    "PC": "Polícia Civil",
    "MP": "Ministério Público",
    "TCE": "Tribunal de Contas do Estado",
    "CGM": "Controladoria Geral do Município",
    # Símbolos
    "R$": "reais",
    "%": "por cento",
    "m²": "metros quadrados",
    "km": "quilômetros",
    "nº": "número",
    # Marcadores de pausa
    "---": "[PAUSA]",
}

# Remover da versão TTS
TTS_REMOVE_PATTERNS = [
    r"^#{1,3} .*$",        # headers markdown
    r"\*{1,2}[^*]+\*{1,2}", # negrito/itálico
    r"^---$",              # separadores
    r"^\[QUADRO:.*\]$",    # marcadores de quadro
]
```

### 8.3 Marcadores de pausa no script

| Marcador | Duração sugerida | Uso |
|---|---|---|
| `[PAUSA]` | 1,5s | Entre quadros |
| `[PAUSA_CURTA]` | 0,5s | Entre falas longas |
| `...` | 0,3s | Ênfase dramática na fala |

---

## 9. Checklist de Qualidade

Antes de finalizar o roteiro, o agente deve verificar:

- [ ] Bloco de manchetes presente antes da introdução editorial
- [ ] Todos os quadros obrigatórios presentes (4.2 a 4.6)
- [ ] Nenhuma fala ultrapassa 6 linhas sem interrupção do outro apresentador
- [ ] Tom libertário aplicado em pelo menos um ponto por quadro
- [ ] Sem saudações temporais ("bom dia", "boa tarde")
- [ ] Versão TTS gerada sem markdown ou símbolos
- [ ] Continuidade com episódio anterior referenciada (se `roteiro_anterior` fornecido)
- [ ] Duração estimada dentro de 15 minutos (~2.000–2.500 palavras no roteiro)
- [ ] **[PERSUASÃO]** Presença de dados concretos/valores (Autoridade) e conexão com "nós" (Unidade)
- [ ] **[PERSUASÃO]** Fatos emoldurados com senso de urgência/prazos (Escassez) e experiência local (Prova Social)
- [ ] **[ANTI-RACIONALIZAÇÃO]** Diálogos mantêm tensão ativa, sem acordo polido imediato entre Peter e Ricardo

---

## 10. Metadados de Saída

O agente deve gerar junto ao roteiro um bloco de metadados:

```json
{
  "edicao": "DD/MM/YYYY",
  "episodio": N,
  "duracao_estimada_min": 12,
  "quadros_gerados": ["seguranca", "saude", "educacao", "politica", "esportes", "rapidinhas"],
  "noticias_total": 8,
  "noticias_com_continuidade": 1,
  "fontes_utilizadas": ["manus", "grok", "busca_web"],
  "arquivos_gerados": ["roteiro.md", "roteiro_tts.txt", "manchetes.txt"]
}
```

---

*Skill mantida por: Osmar G. Furtado (Hermes System) | Vale da Liberdade Studio | Blumenau, SC*
*Versão: 2.0 | Última atualização: 2026*
