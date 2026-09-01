# YouTube Growth & Algorithm Features via API — Implementation Plan (v4)

> **Revisão v4:** Atualizado com a infraestrutura Multi-Slot ativa (**20.000 unidades/dia** divididas em 2 contas/projetos Google Cloud de 10.000 unidades cada: `slot1` e `slot2`).
> **Mudanças vs v3:** Correção da cota diária de 10.000 para 20.000 unidades/dia; meta de 10 vídeos/dia é **100% viável hoje** com a rotação multi-slot já implementada; Fase 0 deixa de ser bloqueante fatal e passa a ser expansão recomendada.

**Goal:** Implementar automações via YouTube Data API v3 para maximizar alcance algorítmico, operando com **10 vídeos/dia**, rotação multi-slot de cota (**20.000 unidades/dia**) e **investimento zero** (MVP).

**Prioridade absoluta:** Os 10 vídeos devem subir diariamente. Nenhuma feature secundária pode impedir ou atrasar o upload.

**Tech Stack:** Python 3 (`.venv`), YouTube Data API v3 (`google-api-python-client` + `youtube_quota.py` multi-slot proxy), `gemini-3.5-flash-lite` para traduções leves e metadados.

---

## 📊 Capacidade e Matemática de Cota Atual (20.000 un/dia)

Com a arquitetura **Multi-Slot** implementada em `credentials/youtube_slots.json` e gerenciada por `scripts/youtube_quota.py`, o canal conta com **duas contas / projetos Google Cloud independentes** autorizados no mesmo canal (Vale da Liberdade):

* **`slot1`**: Projeto `hermes-youtube-uploader-506310` (10.000 unidades/dia)
* **`slot2`**: Projeto `youtube-hermes-uploader` (10.000 unidades/dia)
* **Total Diário:** **20.000 unidades/dia** (reset às 00:00 PST / 04:00 BRT)

### Balanço Diário para 10 Vídeos:

```
Operação                                      Cálculo           Consumo
────────────────────────────────────────────────────────────────────────
videos.insert (10 uploads)                    10 × 1.600 un   = 16.000 un
Playlists oficiais (sync 1-2 playlists)       10 × ~75 un     =    750 un
Playlist dinâmica "Últimas Notícias"          10 × ~101 un    =  1.010 un
Thumbnails personalizadas HD                  10 × 50 un      =    500 un
Cross-comment do canal                        10 × 50 un      =    500 un
────────────────────────────────────────────────────────────────────────
Subtotal Essencial Diário (10 vídeos)                         = 18.760 un
Cota Disponível (2 Slots)                                     = 20.000 un
────────────────────────────────────────────────────────────────────────
Margem de Segurança Operacional                               = +1.240 un  ✅
```

> **Conclusão:** **A meta de 10 vídeos/dia é totalmente viável hoje.**  
> O pipeline não está mais bloqueado pela cota padrão de 10k.  
> Para legendas (SRT pt-BR + en = ~900 un/vídeo), o envio pode ocorrer off-peak via cron às 04:30 BRT (logo após o reset diário do Google) ou mediante aumento de cota formal.

---

## ⚙️ Realidade do Código Atual (Auditoria Arquitetural)

> **IMPORTANTE:** O pipeline usa **subprocess** para orquestrar o upload a partir de `bm_mockup_video.py` e gerencia a cota com rotação automática em `scripts/youtube_quota.py`.

### Fluxo real de upload:

```
bm_mockup_video.py:process_one()
  │
  ├─ 1. Gera vídeo mockup (Playwright + FFmpeg)
  │
  ├─ 2. publish_youtube(mp4, title, desc, tags, privacy)
  │    └─ subprocess.run(["python", "youtube_uploader.py", "upload", ...])
  │       ├─ youtube_quota.py (consome slot1 até 9.700 un; migra automático para slot2)
  │       ├─ cmd_upload() → video_resource_body() → yt.videos().insert() [1.600 un]
  │       └─ choose_playlists() → sync_official_playlists() [~80 un]
  │
  ├─ 3. set_youtube_thumbnail(yt_id, image)
  │    └─ subprocess.run(["python", "youtube_uploader.py", "thumbnail", ...]) [50 un]
  │
  ├─ 4. attach_captions_and_en(video_id, yt_id, audio, title, desc)
  │    ├─ Whisper → SRT pt-BR
  │    ├─ Gemini → translate cues → SRT en
  │    ├─ upload_caption(pt-BR) + upload_caption(en) [800 un]
  │    └─ set_english_localization(yt_id, title_en, desc_en) [51 un]  ← [Otimizar na Fase 1]
  │
  ├─ 5. post_channel_cross_comment(yt_id, prev) [50 un]  ← JÁ EXISTE!
  │
  └─ 6. save_state() → output/brasil_e_mundo/videos_published.json
```

### Features que JÁ existem no código:
- ✅ Rotação Multi-Slot de Cota (20.000 un/dia em `youtube_quota.py` + `credentials/youtube_slots.json`)
- ✅ Cross-comment do canal (`post_channel_cross_comment`)
- ✅ Playlists oficiais (`sync_official_playlists`)
- ✅ Localização EN via `set_english_localization`
- ✅ Legendas SRT pt + en (`attach_captions_and_en`)

---

## 💰 Orçamento Detalhado de Cota por Vídeo

### Tabela de Custos Unitários por Operação:

| Operação | Método / Endpoint | Custo Unitário | Por Vídeo | 10 Vídeos / Dia |
|---|---|---|---|---|
| `videos.insert` (upload do MP4) | `POST /videos` | 1.600 un | 1.600 un | 16.000 un |
| `playlistItems.list` (5 oficiais) | `GET /playlistItems` | 1 un | 5 un | 50 un |
| `playlistItems.insert` (~1.5 playlists) | `POST /playlistItems` | 50 un | 75 un | 750 un |
| `thumbnails.set` (capa personalizada) | `POST /thumbnails/set` | 50 un | 50 un | 500 un |
| `commentThreads.insert` (cross-comment) | `POST /commentThreads` | 50 un | 50 un | 500 un |
| `playlistItems` (playlist dinâmica rotativa) | `GET + POST + DEL` | ~101 un | ~101 un | 1.010 un |
| `videos.list` (leitura pós-upload EN) | `GET /videos` | 1 un | 1 un | 10 un *(eliminado na Fase 1)* |
| `videos.update` (aplicação pós-upload EN) | `PUT /videos` | 50 un | 50 un | 500 un *(eliminado na Fase 1)* |
| `captions.list` (checagem pt-BR + en) | `GET /captions` | 50 un | 100 un | 1.000 un |
| `captions.insert` (SRT pt-BR + en) | `POST /captions` | 400 un | 800 un | 8.000 un |

---

## 🎯 Cenários de Capacidade Diária

### Cenário 1: Cota Atual (20.000 un/dia — 2 Slots Ativos) — RECOMENDADO

* **Uploads Principais (10 vídeos/dia):** Upload (16.000) + Playlists oficiais (800) + Playlist dinâmica (1.010) + Thumbs (500) + Cross-comment (500) = **~18.810 unidades**.
* **Localização EN/ES:** Custo ZERO (embutida no `videos.insert` via Fase 1).
* **Legendas (PT/EN):** Executadas em modo batch off-peak via cron às 04:30 BRT ou sob demanda nos vídeos de maior destaque.
* **Resultado:** **10 vídeos/dia publicados com máxima qualidade visual e algorítmica.**

### Cenário 2: Cota Expandida (50.000 un/dia — Aumento de Cota / 3º Slot)

* **Uploads Principais (10 a 15 vídeos/dia):** ~26.000 unidades.
* **Legendas Completas Inline (PT+EN+ES):** ~12.000 unidades aplicadas instantaneamente no momento do upload.
* **A/B Testing de Títulos:** ~500 unidades para reotimização contínua de vídeos com baixo desempenho.
* **Total:** ~38.500 / 50.000 unidades (folga ampla para crescimento).

---

## 🛠️ Fases de Implementação Atualizadas

```
┌────────────────────────────────────────────────────────────────────────┐
│ Fase -1: Auditoria Read-Only & Multi-Slot 20k (CONCLUÍDA ✅)           │
├────────────────────────────────────────────────────────────────────────┤
│ Fase 0: Solicitação de Aumento de Cota 50k (Expansão Operacional)      │
├────────────────────────────────────────────────────────────────────────┤
│ Fase 1: publishAt + Localizations Embutidos no Insert (CUSTO ZERO)     │
├────────────────────────────────────────────────────────────────────────┤
│ Fase 2: Playlist Dinâmica "Últimas Notícias" (Custo ~101 un/vídeo)     │
├────────────────────────────────────────────────────────────────────────┤
│ Fase 3: Quota Tracker + Legendas Off-Peak (04:30 BRT)                  │
├────────────────────────────────────────────────────────────────────────┤
│ Fase 4: Otimizador A/B de Títulos sob Demanda (50 un/teste)            │
└────────────────────────────────────────────────────────────────────────┘
```

---

### Fase -1: Auditoria Read-Only & Multi-Slot (CONCLUÍDA ✅)

- Mapeamento completo do pipeline documentado em `YOUTUBE_PIPELINE_MAP.md`.
- Sistema multi-slot de 20.000 un/dia ativo em `scripts/youtube_quota.py` e `credentials/youtube_slots.json`.
- Tokens OAuth 2.0 permanentes configurados em produção para `slot1` e `slot2`.

---

### Fase 0: Solicitar Aumento de Cota YouTube API (Expansão)

> **Nota:** Com os 2 slots (20.000 un/dia), esta fase **NÃO é bloqueante** para a meta de 10 vídeos/dia. Ela é recomendada para permitir legendas inline instantâneas.

#### Subetapas:
```
0.1  Acessar Google Cloud Console → APIs & Services → YouTube Data API v3 → Quotas
0.2  Verificar uso atual de cota nos projetos slot1 e slot2
0.3  Clicar em "Request Quota Increase" no projeto principal
0.4  Solicitar 50.000 unidades/dia (justificativa: canal de jornalismo com 10 vídeos diários e legendas)
0.5  Acompanhar deferimento pelo Google Cloud Support (3-7 dias úteis)
```

---

### Fase 1: publishAt + Localizations Embutidos no Insert (CUSTO ZERO)

#### Insight Chave:
Tanto `publishAt` (agendamento) quanto `localizations` (títulos e descrições em múltiplos idiomas) podem ser injetados diretamente no body do `videos.insert(part="snippet,status,recordingDetails,localizations")`.

* **Custo extra:** **0 unidades**.
* **Economia:** **51 unidades por vídeo** (elimina `videos.list` + `videos.update` pós-upload).

#### Subetapas:
```
1.1   [youtube_captions.py] Criar translate_title_desc_multi(title_pt, desc_pt)
      → Retorna {"en": {"title": ..., "description": ...}, "es": {...}}
      → Único prompt Gemini com cache em output/brasil_e_mundo/translations_cache.json

1.2   [youtube_channel_policy.py] Criar next_publication_slot(now_dt, slots)
      → Slots recomendados: ["07:00", "11:30", "18:00"]
      → Se dentro da janela nobre (±30min) → publicação imediata; caso contrário, agenda próximo slot

1.3   [youtube_channel_policy.py] Expandir video_resource_body():
        def video_resource_body(
            title, description, tags, privacy, *,
            category_id=None, recording_date=None, kind="news",
            publish_at=None, localizations=None,
        ) -> dict:
      → Se publish_at: privacyStatus = "private", publishAt = publish_at
      → Se localizations: body["localizations"] = localizations

1.4   [youtube_uploader.py] Adicionar argumentos no CLI upload:
        --publish-at (ISO datetime)
        --localizations-file (JSON com localizações EN/ES)
      → Incluir "localizations" no parâmetro part do insert quando fornecido

1.5   [bm_mockup_video.py] Atualizar publish_youtube():
      → Invoca tradução EN/ES antes do upload e passa flags para youtube_uploader.py

1.6   [youtube_captions.py] Atualizar attach_captions_and_en():
      → Pular set_english_localization() quando localizações já forem embutidas no insert
```

---

### Fase 2: Playlist Dinâmica "Últimas Notícias"

#### Motivação Algorítmica:
Autoplay contínuo retém o espectador por múltiplos vídeos consecutivos. Uma playlist rotativa mantendo os últimos 10 episódios potencializa o watch time.

* **Custo de cota por vídeo:** **~101 unidades** (1 list + 1 insert + 1 delete eventual de item antigo).

#### Subetapas:
```
2.1  [YouTube Studio] Criar playlist "Últimas Notícias — Vale da Liberdade" (obter PL...)
2.2  [config/youtube.json] Cadastrar dynamic_playlist com playlist_id e max_items=10
2.3  [scripts/youtube_playlist_sync.py] Implementar sync_dynamic_playlist(yt, playlist_id, video_id)
2.4  [bm_mockup_video.py] Integrar sincronização da playlist após upload do vídeo
```

---

### Fase 3: Quota Tracker + Legendas Off-Peak

* Com 20.000 un/dia, os uploads prioritários ocorrem ao longo do dia comercial.
* O processamento de legendas pesadas (800 un por vídeo) pode rodar às **04:30 BRT** (07:30 UTC), logo após o reset da cota do Pacífico (00:00 PST = 04:00 BRT).

#### Subetapas:
```
3.1  [youtube_captions.py] Adicionar modo batch:
     python scripts/youtube_captions.py --batch-pending --max 10
3.2  [cron] Agendar execução diária às 04:30 BRT para processar vídeos pendentes
3.3  [bm_mockup_video.py] Integrar verificação de folga de cota via youtube_quota.py
```

---

### Fase 4: Otimizador A/B de Títulos (Sob Demanda)

* Monitora vídeos com taxa de cliques/views abaixo de 60% da média dos últimos 7 dias.
* Gera títulos alternativos via Gemini e aplica via `videos.update` (**50 unidades**).
* Execução manual ou sob demanda semanal para preservar cota dos uploads.

---

## 📋 Resumo Comparativo: 10k vs 20k vs 50k

| Recurso / Feature | Cota 10k (1 Conta Antiga) | Cota 20k (2 Slots Atuais) | Cota 50k (Expansão Futura) |
|---|---|---|---|
| **Uploads diários possíveis** | Máx 6 vídeos/dia ❌ | **10 a 11 vídeos/dia** ✅ | **18+ vídeos/dia** ✅ |
| **Status da Meta (10 vídeos)** | Impossível (déficit -6k) | **100% Viável Hoje** | **100% Viável com Ampla Folga** |
| **publishAt + Localizations** | ✅ (Custo zero) | ✅ (Custo zero) | ✅ (Custo zero) |
| **Playlists Oficiais** | ✅ (~750 un) | ✅ (~750 un) | ✅ (~750 un) |
| **Playlist Dinâmica** | ❌ (Sem cota) | ✅ (~1.010 un) | ✅ (~1.010 un) |
| **Thumbnails HD** | ✅ (500 un) | ✅ (500 un) | ✅ (500 un) |
| **Cross-Comment** | ❌ (Sem cota) | ✅ (500 un) | ✅ (500 un) |
| **Legendas PT+EN** | ❌ Desativadas | ✅ Modo Off-Peak (04:30 BRT) | ✅ Inline instantâneo (todas) |
| **A/B Testing de Títulos** | ❌ Desativado | ✅ Sob demanda | ✅ Automático contínuo |

---

## 🔍 Critérios de Validação e Sucesso

1. **Uploads Estáveis:** 10 vídeos publicados diariamente sem erros de `quotaExceeded`.
2. **Rotação Transparente:** `youtube_quota.py` consome `slot1` até ~9.700 unidades e transiciona suavemente para o `slot2`.
3. **Economia Confirmada:** Eliminação de 51 unidades por vídeo na Fase 1 com localizações embutidas diretamente no `videos.insert`.
4. **Resiliência:** Falhas em legendas, comentários ou playlists não bloqueiam nem cancelam a publicação do vídeo.
