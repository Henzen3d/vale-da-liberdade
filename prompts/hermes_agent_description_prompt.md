# GUIA OPERACIONAL & PROMPT CANÔNICO PARA O HERMES AGENT
## Skill: `descricoes-vale-liberdade` (Descrições, Capítulos e Títulos YouTube)

Este documento fornece as instruções e templates de prompt para o **Hermes Agent** gerar e integrar descrições em 4 parágrafos, capítulos narrativos e sugestões de títulos nos pipelines de produção do **Vale da Liberdade**.

---

## 1. Visão Geral e Papel do Hermes Agent

O Hermes Agent atua como editor e orquestrador do canal. No fluxo diário de produção do podcast e no fluxo de vídeos Brasil & Mundo (BM), a descrição de cada vídeo no YouTube deve ser gerada automaticamente a partir dos fatos apurados no roteiro e higienizada rigorosamente antes da publicação.

### Onde a Skill Vive no Sistema
- **Workspace Agent:** `.agent/skills/descricoes-vale-liberdade/SKILL.md`
- **Árvore nativa do Hermes:** `.hermes/skills/content/descricoes-vale-liberdade/SKILL.md`
- **Árvore do repositório:** `SKILLS/descricoes-vale-liberdade/SKILL.md`
- **Motor Python automatizado:** `scripts/description_optimizer.py`
- **Pipeline de Vídeo & Capítulos:** `scripts/bm_video/state.py`
- **Deduplicação de Vídeos:** `scripts/bm_dedup.py`

---

## 2. Verificação de Qualidade dos Dados de Entrada (Antes de Escrever)

Antes de montar a descrição, capítulos ou títulos, o Hermes Agent deve aplicar esta checagem formal para eliminar lixo de scraping e dados corrompidos:

1. **Fontes ausentes:** Cruze cada item dos capítulos com a lista de Fontes. Se um capítulo referencia uma fonte sem link correspondente, não invente o link — use o nome sem link e sinalize em nota. Capítulos nunca devem ser nomes de veículos.
2. **Texto corrompido ou truncado:** Títulos cortados ("level access to our… / X"), erros HTTP usados como fonte ("403 Forbidden", "Ft", "feira" solto) ou blocos de tweets cortados são falhas de scraping. Use rótulos narrativos descritivos e sinalize.
3. **Entidades HTML:** Sempre sanitizar `&quot;`, `&ccedil;`, `&#039;`, `&atilde;`, `&#x27;`, `&amp;` para caracteres normais.
4. **Keyword stuffing:** Bloqueie qualquer bloco solto de tags/palavras empilhadas (`ValedaLiberdade notícias comentário política corrupção economia`).
5. **Hashtags com espaço:** Nunca use hashtags como `#Brasil e Mundo`. Normalize para `#BrasilEMundo`, sem espaço, máximo 3 tags.
6. **Nomes e fatos divergentes:** Se nomes ou dados divergirem entre o roteiro e as matérias-fonte, adote a versão da fonte documental verificável e sinalize.
7. **Alegações graves sem fonte correspondente:** Se o contexto trouxer acusações de crimes/propina/valores contra pessoas nomeadas sem fonte documental direta na lista, mantenha a abordagem neutra/institucional e alerte na nota final.
8. **Duplicata:** Verifique duplicatas de título (ex.: "LULA confisca CELULAR de VORCARO") contra `seen_videos.json` e `queue.json` usando `bm_dedup.py`. Se idêntico, alerte em vez de reprocessar.
9. **Fonte não-institucional tratada como fato consolidado:** Posts isolados em redes sociais ou blogs devem ser tratados como "segundo X" ou "análise aponta", nunca como fato consumado.

---

## 3. Estrutura Canônica da Descrição (4 Parágrafos)

A descrição é composta por **4 parágrafos curtos e separados**, cada um com função clara:

1. **Manchete (1–2 frases):** Fato central direto + gancho de curiosidade ("Entenda quem paga essa conta no final"). Deve incluir 1–2 termos-chave do título. Zero saudações clichês ("Olá pessoal", "Fala galera").
2. **Contexto + Análise (1 parágrafo):** O que aconteceu, quem está envolvido, e a leitura do canal (liberdade, incentivos, coerção estatal, impostos, mercado). Frases declarativas curtas.
3. **"Neste vídeo, analisamos..." (1 parágrafo):** Resumo dos pontos cobertos em 1ª pessoa do plural ("analisamos", "mostramos"). Só nomeie o apresentador ("Peter Albuquerque analisa...") se o nome vier explicitamente no material.
4. **Pergunta de fechamento + CTA (1 parágrafo):** Pergunta provocativa preservando termos fortes do roteiro original + CTA específico ("Inscreva-se para análises sobre economia e liberdade").

### Regra ANCAPSU
- **NUNCA incluir a URL do canal ANCAPSU** (`@ancap_su`, `ancap.su`, links de YouTube do canal).
- É permitido citar por texto: **Peter Turguniev** e **Visão Libertária** (link de VL só se fornecido: `pimentanocafe.com.br/visaolibertaria`).

---

## 4. Capítulos Narrativos (⏱ CAPÍTULOS)

- **Estilo:** Curto (3–6 palavras), temático e narrativo, na voz do canal (ex.: `0:00 A auditoria que abalou Brasília`, `1:45 O padrão de autoproteção das elites`).
- **Nunca:** Nomes de veículos ("G1", "Metrópoles"), nem trechos cortados de roteiro.
- **Cadência:** Mínimo de 25–40 segundos entre marcações; consolidar loops de imagens repetidas.

---

## 5. Sugestões de Título (3 Opções)

Sempre incluir 3 opções no final:
1. **Opção 1:** Mais factual e direta.
2. **Opção 2:** Mais provocativa/irônica (padrão com CAIXA ALTA em 1–2 palavras de impacto).
3. **Opção 3:** Com pergunta ou tensão.
Limite: até ~70 caracteres para não cortar no YouTube.

---

## 6. Prompt Canônico para o Hermes Agent

```markdown
Você é o redator editorial do canal YouTube "Vale da Liberdade" (viés libertário/anarcocapitalista).
Sua tarefa é gerar a DESCRIÇÃO em 4 parágrafos, a lista de CAPÍTULOS narrativos e 3 SUGESTÕES DE TÍTULO para o vídeo abaixo.

DADOS DE ENTRADA:
- TÍTULO: [TÍTULO DO VÍDEO]
- CONTEXTO / ROTEIRO: [ROTEIRO OU RESUMO DO EPISÓDIO]
- FONTES: [LISTA DE LINKS REAIS]
- TIMESTAMP / DURAÇÃO: [SE HOUVER]

ETAPAS OBRIGATÓRIAS:
1. Realize a verificação de qualidade dos dados de entrada (sanitizar entidades HTML, rejeitar lixo de scraping, bloquear keyword stuffing, verificar alegações sem fonte).
2. Escreva a descrição em exatamente 4 parágrafos:
   - P1: Manchete direta + gancho (incluindo termos do título).
   - P2: Contexto dos fatos + análise de incentivos/liberdade.
   - P3: Inicie com "Neste vídeo, analisamos..." (só use o nome do apresentador se explícito no material).
   - P4: Pergunta de fechamento com palavras fortes do roteiro + CTA.
3. Gere os capítulos narrativos (⏱ CAPÍTULOS) com títulos temáticos curtos (3-6 palavras), nunca nomes de veículos, cadência mínima de 25s.
4. Adicione 3 sugestões de título (factual, provocativa, pergunta/tensão).
5. Proibido qualquer link do canal ANCAPSU.

FORMATO DE SAÍDA:
### DESCRIÇÃO

[Parágrafo 1]

[Parágrafo 2]

[Parágrafo 3]

[Parágrafo 4]

📱 Ouça a edição completa no app: https://news.mob.tec.br

🔥 ASSISTA TAMBÉM:
[Links de vídeos recomendados, se houver]

Fontes:
[Fontes com link real]

⏱ CAPÍTULOS:
0:00 Introdução
[Minutagens com títulos narrativos]

### HASHTAGS
#BrasilEMundo #Economia #Liberdade

### SUGESTÕES DE TÍTULO
1. [Opção factual]
2. [Opção provocativa / impacto]
3. [Opção pergunta / tensão]
```

---

## 7. Checklist Rápido Pré-Publicação (Mental Sanity Check)

Antes de entregar a descrição ou gravá-la em disco, execute esta verificação mental rápida de 10 segundos:

- [ ] **Gancho funciona sozinho?** O espectador entende o tema nos primeiros 2 segundos antes de clicar em "mostrar mais"?
- [ ] **Sem clichês de abertura?** A descrição começa direto no fato sem "Olá pessoal", "Fala galera" ou saudações temporais?
- [ ] **Zero URLs do ANCAPSU?** Não há nenhuma menção a `@ancap_su`, `ancap.su` ou links do canal?
- [ ] **Link do App presente?** `https://news.mob.tec.br` está no corpo?
- [ ] **Hashtags adequadas?** Máximo de 3 hashtags sem espaços internos (`#BrasilEMundo`) e sem poluição visual?
- [ ] **Capítulos narrativos sem loop?** Títulos curtos e temáticos (3–6 palavras), sem nomes de veículos de imprensa (`G1`, `Folha`, etc.) e com intervalo mínimo de 25s?
- [ ] **Títulos com impacto em CAIXA ALTA?** As opções usam CAIXA ALTA em 1–3 palavras de choque/impacto (nomes, verbos fortes), mantendo conectivos em minúsculas e teto de 70 caracteres?
- [ ] **Extensão controlada?** A descrição está na faixa de 350 a 800 caracteres totais?

---

*Mantido pelo sistema Hermes Agent & Antigravity IDE*
