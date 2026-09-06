# 05 — VISUAL QA E MÉTRICAS DE VARIEDADE
> **Protocolo de Qualidade Visual Pré e Pós-Render**  
> **Script Alvo:** [`scripts/qa_visual_audit.py`](file:///j:/Arquivos%20Osmar/Hermes/web-jornal-vale-da-liberdade/scripts/qa_visual_audit.py)  
> **Objetivo:** Garantir qualidade broadcast sem desperdiçar tempo de GPU nem cota do YouTube  

---

## 1. Por que Dois QAs em Vez de um "Gauntlet Pesado"?

No modelo de estúdio independente com processamento local (Intel Core i5 com Intel HD 630):
* Um render de vídeo de 5 minutos no Playwright consome ~5 minutos de gravação + ~1-2 minutos de muxing FFmpeg com aceleração VA-API.
* Se implementássemos um ciclo "renderiza tudo ➔ IA avalia ➔ renderiza tudo de novo 3 vezes", cada episódio demoraria mais de 25 minutos para ser gerado. Isso inviabilizaria o cron de 20 minutos ([`scripts/bm-hourly-pipeline.sh`](file:///j:/Arquivos%20Osmar/Hermes/web-jornal-vale-da-liberdade/scripts/bm-hourly-pipeline.sh)) e geraria risco de fila acumulada.

A solução da arquitetura V2 divide o QA em **duas barreiras complementares**:
1. **QA Pré-Render (Preventivo e Barato):** Bloqueia erros estruturais de dados em **<1 segundo**, antes de iniciar a gravação.
2. **QA Pós-Render Amostral (Rápido e Não-Bloqueante):** Extrai **4 a 6 frames chave** do MP4 final e afere contraste, legibilidade e ausência de tela preta em **~3 segundos**.

---

## 2. QA Pré-Render (Preventivo)

Executado antes de abrir o Playwright em [`scripts/bm_mockup_video.py`](file:///j:/Arquivos%20Osmar/Hermes/web-jornal-vale-da-liberdade/scripts/bm_mockup_video.py):

```text
┌─────────────────────────────────────────────────────────────┐
│ 1. VALIDAÇÃO ESTRUTURAL DO SCENE PLAN                       │
│ • Cada beat tem duração entre 8.0s e 22.0s?                │
│ • Soma dos tempos dos beats bate com a duração do MP3?      │
│ • Ordem sequencial de t0 e t1 é contínua e sem sobreposição?│
├─────────────────────────────────────────────────────────────┤
│ 2. INTEGRIDADE DOS ASSETS LOCAIS                            │
│ • A imagem ou screenshot referenciada existe em disco?      │
│ • O arquivo PNG/JPG tem tamanho > 8 KB e não está corrompido?│
│ • O vídeo de loop do apresentador Peter Albuquerque existe? │
├─────────────────────────────────────────────────────────────┤
│ 3. HIGIENE DOS PAYLOADS                                     │
│ • O texto de citação (QuoteCard) tem mais de 20 caracteres? │
│ • Os números do gráfico (DataChart) são válidos (não NaN)?  │
│ • O documento oficial tem título e grifo preenchidos?       │
└─────────────────────────────────────────────────────────────┘
```

### Regra de Ouro do Fallback Gracioso
Se um componente especial (ex: `DocumentZoom` ou `QuoteCard`) falhar na validação pré-render (ex: imagem não encontrada ou texto corrompido), o sistema **não aborta a geração do vídeo**. Ele automaticamente rebaixa aquele beat para o componente `source` (screenshot padrão do navegador com a matéria jornalística) e registra um aviso no log.

---

## 3. QA Pós-Render Amostral (Inspeção de Frames Chave)

Após o FFmpeg muxar o vídeo final com a faixa de áudio e o apresentador ([`bm_mockup_video.py:compose_presenter`](file:///j:/Arquivos%20Osmar/Hermes/web-jornal-vale-da-liberdade/scripts/bm_mockup_video.py)), o script extrai frames chave estratégicos:

```bash
# Extração de 5 frames representativos sem re-encode (extremamente rápido)
ffmpeg -ss 00:00:12 -i final.mp4 -vframes 1 -q:v 2 frame_10pct.png
ffmpeg -ss 00:01:00 -i final.mp4 -vframes 1 -q:v 2 frame_30pct.png
ffmpeg -ss 00:02:30 -i final.mp4 -vframes 1 -q:v 2 frame_50pct.png
ffmpeg -ss 00:03:45 -i final.mp4 -vframes 1 -q:v 2 frame_75pct.png
ffmpeg -ss 00:04:30 -i final.mp4 -vframes 1 -q:v 2 frame_90pct.png
```

### Verificações Automatizadas nos Frames (Pillow / OpenCV)
1. **Detecção de Tela Preta / Uniforme:**
   * Desvio padrão de luminância global (`stddev`) > 12.0. Se for menor, significa tela em branco ou preta (falha de carregamento do Playwright).
2. **Presença do Lower Third Oficial:**
   * A região inferior (linhas 940 a 1040) deve apresentar contraste nítido da tarja preta/ouro e texto branco legível.
3. **Presença do Apresentador Peter:**
   * A área do avatar no canto inferior esquerdo deve conter pixels visíveis (verificação de que o Chroma Key `colorkey` não removeu o corpo inteiro).

### Relatório Gerado (`qa_report.json`)
```json
{
  "video_id": "yt_bm_20260905_01",
  "rendered_at": "2026-09-05T23:45:00",
  "status": "APPROVED",
  "metrics": {
    "total_duration_s": 298.4,
    "frames_analyzed": 5,
    "black_frames_detected": 0,
    "lower_third_detected": true,
    "presenter_detected": true,
    "average_contrast_ratio": 4.85
  },
  "warnings": []
}
```

---

## 4. Índice de Variedade Visual do Canal

Para auditar se o canal está mantendo diversidade ou caindo na monotonia de templates, o pipeline registra as estatísticas semanais:

```text
============================================================
ÍNDICE DE VARIEDADE VISUAL — VALE DA LIBERDADE (ÚLTIMOS 10 VÍDEOS)
============================================================
Apresentador em Destaque:     36% do tempo total de tela
Páginas / Fontes Reais:       31% do tempo total de tela
Cards do X / Redes:           14% do tempo total de tela
Citações Editoriais (Quote):  08% do tempo total de tela
Documentos Oficiais:          06% do tempo total de tela
Gráficos / Indicadores:       05% do tempo total de tela
Linhas do Tempo:              00% (Subutilizado no período)
------------------------------------------------------------
DIAGNÓSTICO DO DIRETOR VISUAL:
Saudável. Recomendação: Priorizar oportunidades de Timeline em
matérias jurídicas nos próximos episódios.
============================================================
```
