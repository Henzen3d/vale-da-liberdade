# Evolução Visual — Web Jornal Vale da Liberdade
> **Pasta Oficial de Arquitetura e Implementação da Nova Camada Visual**  
> **Módulo:** YouTube & Vídeo Procedural Broadcast  
> **Status:** Especificado / Pronto para Implementação em Fases  
> **Data de Criação:** Setembro de 2026  

---

## 📌 Visão Geral

Esta pasta reúne a documentação técnica executável e os contratos para transformar a produção de vídeo do **Vale da Liberdade** em um **sistema de direção visual procedural inteligente**.

Em vez de reconstruir o pipeline de vídeo, a nova arquitetura se apoia diretamente nos scripts em produção:
* **Motor Gráfico:** [`references/youtube/mockup-browser/mockup-brower.html`](file:///j:/Arquivos%20Osmar/Hermes/web-jornal-vale-da-liberdade/references/youtube/mockup-browser/mockup-brower.html) (HTML5, SVG procedural, Design Tokens VDL e animações GSAP 3.14.2).
* **Renderizador / Muxer:** [`scripts/bm_mockup_video.py`](file:///j:/Arquivos%20Osmar/Hermes/web-jornal-vale-da-liberdade/scripts/bm_mockup_video.py) (Playwright headless em 1080p, aceleração Intel VA-API `h264_vaapi` e overlay do avatar Peter Albuquerque).
* **Timeline de Cenas:** [`scripts/bm_scene_timeline.py`](file:///j:/Arquivos%20Osmar/Hermes/web-jornal-vale-da-liberdade/scripts/bm_scene_timeline.py) (sincronização proporcional por contagem de palavras do áudio).
* **Gestão de Cota & Publicação:** [`scripts/youtube_uploader.py`](file:///j:/Arquivos%20Osmar/Hermes/web-jornal-vale-da-liberdade/scripts/youtube_uploader.py) e [`scripts/youtube_quota.py`](file:///j:/Arquivos%20Osmar/Hermes/web-jornal-vale-da-liberdade/scripts/youtube_quota.py) (rotação multi-slot de 20.000 unidades/dia).

---

## 🗺️ Índice da Documentação

| Arquivo | Descrição |
| :--- | :--- |
| **[`CHECKLIST_IMPLEMENTACAO.md`](file:///j:/Arquivos%20Osmar/Hermes/web-jornal-vale-da-liberdade/youtube/Evolucao-Visual/CHECKLIST_IMPLEMENTACAO.md)** | **Documento prático de checklist passo a passo** com caixas de checagem `[ ]`, critérios de aceite e testes para acompanhar a execução sem se perder. |
| **[`01_VISUAL_ARCHITECTURE_V2.md`](file:///j:/Arquivos%20Osmar/Hermes/web-jornal-vale-da-liberdade/youtube/Evolucao-Visual/01_VISUAL_ARCHITECTURE_V2.md)** | **Arquitetura Geral V2:** Fluxo ponta a ponta, modelo de 3 níveis de IA (Determinístico, Refinamento Barato e Diretor Avançado), controle de densidade visual e memória anti-fadiga. |
| **[`02_SCHEMAS_E_CONTRATOS.md`](file:///j:/Arquivos%20Osmar/Hermes/web-jornal-vale-da-liberdade/youtube/Evolucao-Visual/02_SCHEMAS_E_CONTRATOS.md)** | **Contratos de Dados:** Definição do novo `SceneBeat` v2 (`semantic_role`, `visual_component`, `visual_variant`, `visual_payload`), schemas JSON dos 5 novos componentes e payload de oportunidades visuais. |
| **[`03_SPEC_COMPONENTES_GSAP.md`](file:///j:/Arquivos%20Osmar/Hermes/web-jornal-vale-da-liberdade/youtube/Evolucao-Visual/03_SPEC_COMPONENTES_GSAP.md)** | **Especificação dos 5 Novos Componentes:** Layouts, CSS, SVGs procedurais e linhas do tempo GSAP para `QuoteCard`, `DocumentZoom`, `Timeline`, `DataChart` e `Comparison`. |
| **[`04_VISUAL_OPPORTUNITY_DETECTOR.md`](file:///j:/Arquivos%20Osmar/Hermes/web-jornal-vale-da-liberdade/youtube/Evolucao-Visual/04_VISUAL_OPPORTUNITY_DETECTOR.md)** | **Detector de Oportunidades Visuais:** Regras determinísticas (regex de `%`, `R$`, aspas, termos judiciais), cálculo de pontuação (scoring) de candidatos e algoritmo de decisão. |
| **[`05_VISUAL_QA_E_METRICAS.md`](file:///j:/Arquivos%20Osmar/Hermes/web-jornal-vale-da-liberdade/youtube/Evolucao-Visual/05_VISUAL_QA_E_METRICAS.md)** | **Controle de Qualidade:** Validação pré-render (barata e preventiva) e QA pós-render amostral (4 a 6 frames chave) para evitar telas pretas e sobreposições sem re-renders pesados. |

---

## 🚀 Como Utilizar

1. Leia primeiro o **[`CHECKLIST_IMPLEMENTACAO.md`](file:///j:/Arquivos%20Osmar/Hermes/web-jornal-vale-da-liberdade/youtube/Evolucao-Visual/CHECKLIST_IMPLEMENTACAO.md)** para entender a ordem das fases.
2. Cada fase implementada deve ser testada de acordo com as instruções do checklist antes de avançar para a próxima.
3. Consulte os documentos numerados para obter os schemas, trechos de código e especificações exatas.
