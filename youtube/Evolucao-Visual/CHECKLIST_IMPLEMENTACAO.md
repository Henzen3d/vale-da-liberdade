# CHECKLIST DE IMPLEMENTAÇÃO — EVOLUÇÃO VISUAL
> **Guia Prático de Execução Passo a Passo**  
> **Como usar:** Vá marcando com `[x]` cada tarefa à medida que for implementada e testada.  
> **Status Geral:** 🚀 Pronto para Início da Etapa 1  

---

## 📋 Resumo das Etapas de Implementação

| Etapa | Foco Principal | Risco | Status |
| :---: | :--- | :---: | :---: |
| **1** | Contrato de Dados: `SceneBeatV2` em `bm_scene_timeline.py` | 🟢 Baixo | `[ ] Não iniciada` |
| **2** | Visual Opportunity Detector (Heurística determinística Nível 0) | 🟢 Baixo | `[ ] Não iniciada` |
| **3** | Componente 1: `QuoteCard` no `mockup-brower.html` | 🟢 Baixo | `[ ] Não iniciada` |
| **4** | Componente 2: `DocumentZoom` no `mockup-brower.html` | 🟡 Médio | `[ ] Não iniciada` |
| **5** | Componente 3: `Timeline` no `mockup-brower.html` | 🟡 Médio | `[ ] Não iniciada` |
| **6** | Componente 4: `DataChart / StatCounter` no `mockup-brower.html` | 🟢 Baixo | `[ ] Não iniciada` |
| **7** | Componente 5: `Comparison` no `mockup-brower.html` | 🟢 Baixo | `[ ] Não iniciada` |
| **8** | Integração da Gravação Playwright no `bm_mockup_video.py` | 🟡 Médio | `[ ] Não iniciada` |
| **9** | Visual QA Pré e Pós-Render (`scripts/qa_visual_audit.py`) | 🟢 Baixo | `[ ] Não iniciada` |

---

## 🛠️ Detalhamento das Etapas

### ETAPA 1 — Contrato de Dados e `SceneBeatV2`
*Objetivo:* Definir a tipagem de dados sem alterar a renderização atual (100% retrocompatível).

- [ ] **1.1** Abrir [`scripts/bm_scene_timeline.py`](file:///j:/Arquivos%20Osmar/Hermes/web-jornal-vale-da-liberdade/scripts/bm_scene_timeline.py).
- [ ] **1.2** Adicionar a nova dataclass `SceneBeatV2` com os campos `semantic_role`, `visual_component`, `visual_variant` e `visual_payload`.
- [ ] **1.3** Manter compatibilidade com código existente implementando método de conversão `to_legacy_beat()` ou garantindo que campos antigos continuem acessíveis.
- [ ] **1.4** Criar teste de unidade em `tests/test_bm_scene_timeline_v2.py` validando a serialização para JSON.
- **Critério de Aceite:** O teste roda e valida que um beat antigo se converte perfeitamente para o novo formato.
- **Comando de Teste:**
  ```powershell
  python -m pytest tests/test_bm_scene_timeline.py
  ```

---

### ETAPA 2 — Visual Opportunity Detector (Nível 0)
*Objetivo:* Fazer o analisador de roteiro encontrar citações, números, documentos e cronologias no texto sem gastar chamadas de API.

- [ ] **2.1** Criar a função `detect_visual_opportunities(text, url, veiculo)` dentro de [`scripts/bm_scene_timeline.py`](file:///j:/Arquivos%20Osmar/Hermes/web-jornal-vale-da-liberdade/scripts/bm_scene_timeline.py).
- [ ] **2.2** Adicionar as expressões regulares de extração (aspas, %, R$, decisões judiciais, marcos temporais).
- [ ] **2.3** Implementar a fórmula de pontuação (scoring) dos candidatos.
- [ ] **2.4** Adicionar fallback para o componente `source` quando a pontuação não atingir o limiar de confiança (0.75).
- **Critério de Aceite:** Passar um texto de exemplo com citação e verificar que a função retorna `chosen_component: "quote"` com payload estruturado.
- **Comando de Teste:**
  ```powershell
  python -c "from scripts.bm_scene_timeline import detect_visual_opportunities; print(detect_visual_opportunities('O prefeito garantiu: \"Não haverá aumento no IPTU neste ano.\"', '', ''))"
  ```

---

### ETAPA 3 — Componente 1: `QuoteCard` (Citação Editorial)
*Objetivo:* Implementar o card de declaração marcante com design broadcast ouro/grafite.

- [ ] **3.1** Abrir [`references/youtube/mockup-browser/mockup-brower.html`](file:///j:/Arquivos%20Osmar/Hermes/web-jornal-vale-da-liberdade/references/youtube/mockup-browser/mockup-brower.html).
- [ ] **3.2** Adicionar a marcação HTML do `#quoteCard` (aspas SVG douradas, texto em destaque, avatar e identificação).
- [ ] **3.3** Adicionar os estilos CSS com safe zone (centralizado, `margin-top: -65px`, borda dourada sutil).
- [ ] **3.4** Adicionar no objeto `VDL_MOCKUP_ENGINE` a função `transitionToQuote(data)` com animação GSAP.
- - [ ] **3.5** Testar visualmente abrindo o arquivo no navegador local com query parameters de teste.
- **Critério de Aceite:** Ao acionar `VDL_MOCKUP.update({ kind: 'quote', quote_text: '...', author_name: '...' })`, o navegador desce suavemente e o card de citação surge no centro.
- **Teste Visual:** Abrir no navegador: `http://localhost:8080/mockup-brower.html?kind=quote&titulo=Declaracao`

---

### ETAPA 4 — Componente 2: `DocumentZoom` (Documento Oficial)
*Objetivo:* Criar a experiência de documento judicial com aproximação de câmera e grifo amarelo animado.

- [ ] **4.1** Adicionar a estrutura HTML do `#documentCard` no `mockup-brower.html`.
- [ ] **4.2** Implementar a folha de documento A4 estilizada e o elemento de marca-texto (`.highlighter-sweep`).
- [ ] **4.3** Criar o método `transitionToDocument(data)` no `VDL_MOCKUP_ENGINE` com GSAP (`scale: 1.25` na folha e expansão da largura do grifo de 0% a 100%).
- **Critério de Aceite:** O documento aparece, a câmera aproxima suavemente no texto e a tarja amarela grifa a frase relevante.

---

### ETAPA 5 — Componente 3: `Timeline` (Cronologia dos Fatos)
*Objetivo:* Exibir linhas do tempo com nós cronológicos para matérias de processos longos ou crises.

- [ ] **5.1** Adicionar o container `#timelineCard` com linha SVG conectora no `mockup-brower.html`.
- [ ] **5.2** Adicionar lógica no JavaScript para instanciar dinamicamente de 2 a 4 nós de eventos com datas e descrições.
- [ ] **5.3** Adicionar animação GSAP progressiva (linha dourada conecta os nós da esquerda para a direita).
- **Critério de Aceite:** Os marcos temporais entram sequencialmente e destacam o evento atual.

---

### ETAPA 6 — Componente 4: `DataChart / StatCounter` (Big Number)
*Objetivo:* Exibir estatísticas e números de grande impacto com contador procedural.

- [ ] **6.1** Adicionar a marcação `#dataChartCard` no `mockup-brower.html`.
- [ ] **6.2** Adicionar ícone de tendência SVG (seta verde para alta / vermelha para queda) e barra de progresso.
- [ ] **6.3** Criar a função `transitionToChart(data)` com GSAP animando o valor numérico de 0 até o total final.
- **Critério de Aceite:** O número sobe de forma fluida e formata em português (ex: `R$ 145,8 mi`).

---

### ETAPA 7 — Componente 5: `Comparison` (Antes × Depois)
*Objetivo:* Exibir comparações visuais diretas (promessas vs. realidade).

- [ ] **7.1** Adicionar a estrutura `#comparisonCard` no `mockup-brower.html` com grid split-screen (50/50) e divisor central "VS".
- [ ] **7.2** Estilizar a coluna da esquerda com tons neutros/alerta e a coluna da direita com tons dourados.
- [ ] **7.3** Criar a função `transitionToComparison(data)` com animação de entrada lateral das duas colunas.
- **Critério de Aceite:** As duas colunas entram em sincronia e permanecem perfeitamente legíveis sem conflito com o Lower Third.

---

### ETAPA 8 — Integração da Gravação Playwright no `bm_mockup_video.py`
*Objetivo:* Conectar o loop de gravação aos novos componentes.

- [ ] **8.1** Abrir [`scripts/bm_mockup_video.py`](file:///j:/Arquivos%20Osmar/Hermes/web-jornal-vale-da-liberdade/scripts/bm_mockup_video.py).
- [ ] **8.2** No método `record_mockup()`, atualizar a chamada `page.evaluate()` para repassar o `visual_payload` completo do `SceneBeatV2`.
- [ ] **8.3** Adicionar registro anti-fadiga em `output/brasil_e_mundo/last_videos.json` ao salvar o estado do vídeo.
- **Critério de Aceite:** Executar um teste de renderização em modo dry-run / teste e verificar que o Playwright grava a transição sem erros no console.
- **Comando de Teste:**
  ```powershell
  python scripts/bm_mockup_video.py --help
  ```

---

### ETAPA 9 — Visual QA Pré e Pós-Render
*Objetivo:* Blindar o pipeline contra telas pretas e sobreposições antes da publicação no YouTube.

- [ ] **9.1** Criar o script [`scripts/qa_visual_audit.py`](file:///j:/Arquivos%20Osmar/Hermes/web-jornal-vale-da-liberdade/scripts/qa_visual_audit.py).
- [ ] **9.2** Implementar a função `validate_pre_render(scene_plan)` (validação de schema e integridade de assets).
- [ ] **9.3** Implementar a função `inspect_post_render(mp4_path)` (extração de 5 frames via FFmpeg e checagem de luminância/contraste).
- [ ] **9.4** Conectar a verificação ao final de `bm_mockup_video.py` antes de despachar para o `youtube_uploader.py`.
- **Critério de Aceite:** O script gera o relatório `qa_report.json` com status `APPROVED` em vídeos saudáveis e emite alerta caso haja frames uniformes.
