# Brasil e Mundo — Contrato de Pacing, Fontes, Sync e Anti-bot

Documento canônico do ritmo editorial, volumetria de fontes, sincronização áudio ↔ mockup e boas práticas de captura para o especial **Brasil e Mundo (BM)** do Webjornal Vale da Liberdade.

---

## 1. Duração Alvo e Volumetria de Palavras

- **Duração do áudio falado:** 4:00 a 5:00 minutos.
- **Piso de palavras:** 680 palavras (~3m50s a 175 wpm).
- **Alvo central:** 820 palavras (~4m40s).
- **Teto de palavras:** 900 palavras (~5m08s).
- **Ritmo de fala medido (Peter):** ~170–180 palavras por minuto.
- **Teto máximo de segurança do mockup:** 330 segundos (5m30s).

### Regra do Gate de Duração
- Se a geração inicial tiver menos de 680 palavras, o condensador realiza retry automático solicitando aprofundamento factual com base no briefing de fontes extras.
- Se após retries o roteiro continuar abaixo de 680 palavras, o pipeline registra `GATE duração: N palavras < 680` e **não publica vídeo** (o áudio pode seguir para o catálogo do site).

---

## 2. Aprofundar ≠ Enrolar

Quando o vídeo de origem do YouTube for curto ou superficial:
1. **Buscar matérias extras:** O pipeline consulta matérias complementares sobre o mesmo tema via feeds RSS ativos ou via busca leve (`gemini-3.5-flash-lite`).
2. **Adicionar fato novo e análise:** O apresentador (Peter) contextualiza os desdobramentos, histórico ou ramificações do caso a partir de dados dessas fontes.
3. **Proibido padding artificial:** Não repetir a mesma frase, não pedir para "falar mais devagar" e não incluir parágrafos de enrolação genérica sem dados factuais.

---

## 3. Fontes Visuais e Metadados

- **Quantidade de referências no JSON:** 6 a 10 URLs externas úteis (veículos de imprensa legítimos, sem contar YouTube, ANCAPSU ou links do próprio site).
- **Teto de captura visual no vídeo:** Até **8 cenas** por episódio (`MAX_SCENES = 8`).
- **Campos estendidos em `fonte_referencias`:**
  - `veiculo`: Nome legível do jornal/portal (ex: "CNN Brasil", "Folha", "G1").
  - `url`: Link sanitizado (sem parâmetros UTM).
  - `role`: `"primary"` (fonte principal), `"supporting"` (fonte de suporte/aprofundamento), ou `"visual"` (apenas para screenshot).
  - `origin`: `"youtube_description"`, `"rss"`, ou `"search"`.
  - `quoted_in`: Bloco do roteiro associado (`"abertura"`, `"desenvolvimento"`, `"fechamento"`).

---

## 4. Sincronização Áudio ↔ Imagem (Timeline de Cenas)

- **Vínculo Fala ↔ Fonte:** Cada item de fala nos blocos de `abertura`, `desenvolvimento` e `fechamento` pode conter opcionalmente o campo `"fonte_url": "https://..."`.
- **Duração por contagem de palavras:** O tempo de cada fala no áudio é estimado proporcionalmente ao número de palavras.
- **Piso por cena:** Mínimo de **8,0 segundos** na tela para cada matéria de fonte externa (evita transições rápidas/epilépticas).
- **Fallback de cena:** Se a fala não declarar `fonte_url`, o mockup avança sequencialmente entre as capturas disponíveis ou mantém a última matéria.

---

## 5. Política Anti-bloqueio (Captura Educada)

1. **Cache em disco:** Screenshots em `output/brasil_e_mundo/capture-cache/`. A chave inclui `CAPTURE_CACHE_VERSION` (`handler-v2` desde 2026-09-02) + URL — bump da versão invalida prints corrompidos sem precisar apagar o diretório. Se o arquivo existir, tiver menos de 36 horas e tamanho > 8 KB, não revisitar o site.
2. **Delays aleatórios com jitter:**
   - Entre 3,5s e 8,0s de espera entre requisições para domínios diferentes.
   - Entre 8,0s e 15,0s de espera se duas URLs consecutivas forem do mesmo domínio.
3. **Teto por domínio:** Máximo de 2 URLs do mesmo *registrable domain* por episódio.
4. **Sem interação agressiva:** Uma página = um print. Não clicar em "leia mais", não abrir galerias nem navegar em paginações.
5. **Tratamento de bloqueios:** Em caso de 403, Cloudflare challenge ou login-wall persistente, registrar `skip:blocked` e descartar a screenshot sem tentar bypass ou criar loops de retry. **Não** usar `blocked-page-recovery` / `recover_page.py` para consertar print: essa escada é só texto (pauta/roteiro). O vídeo captura a URL original no Chromium.
6. **Agendamento:** A captura Playwright ocorre exclusivamente no job do vídeo (máximo 1 execução por hora). Proibido rodar captura contínua no condensador.

---

## 6. B-Roll (Clipes de Transição)

- **Biblioteca local:** `references/youtube/broll/` com manifesto machine-readable `_index.json`.
- **Duração do clip:** 0,8 a 1,5 segundos.
- **Uso:** Transição entre matérias em trocas de bloco do roteiro ou pausas respiratórias, **apenas** quando houver clips disponíveis na biblioteca.
- **Fallback:** Caso a pasta esteja vazia (`"clips": []`), o pipeline realiza corte direto ou transição padrão sem gerar erros.

---

## 7. Bumper de Encerramento (Drop-in)

- **Arquivo reservado:** `references/youtube/end-bumper/outro.mp4`.
- **Contrato:** 1920×1080, 30fps, H.264, áudio AAC com música e CTA visual (like/compartilhe).
- **Sem fala de TTS:** O apresentador (Peter) **não** lê comandos de "deixe seu like" por cima do encerramento; toda a chamada de ação mora no vídeo/música do bumper.
- **Comportamento do pipeline:** Se o arquivo `outro.mp4` estiver ausente, o episódio encerra normalmente no fechamento falado (no-op). Quando o arquivo for adicionado, o compositor concatena após o onair.
