# Inserção de Anúncios Tipo 1 — Patrocínio Embutido (manual, pré-dashboard)

**Data:** 2026-08-04
**Status:** ✅ Operacional no pipeline diário

## Visão geral
Um anúncio de patrocinador (~20s) é inserido por dia, exclusivamente no
**diário Peter+Ricardo**, em ~50% da duração do episódio, evitando blocos
sensíveis (morte/assassinato/violência). No futuro a seleção sai do
dashboard admin; por enquanto a fonte de verdade é `ads/schedule.json`.

## Arquivos
- `ads/schedule.json` — rotação (`rotation_order`), catálogo de takes
  (com transcrição), histórico de inserções e `sponsor_ids` (Supabase).
- `ads/clips/*.mp3` — takes pré-processados (44.1kHz mono, -16 LUFS, 192k).
  Origem bruta: `public/audio/Ads/*.wav` (não tocar).
- `scripts/ads_insert.py` — inseridor.
- `scripts/07_link_episode_sponsor.sql` — RPC idempotente criada no banco
  (já aplicada no Supabase local).

## Ponto de inserção
`ads_insert.py` procura silêncios longos (≥1.2s, silencedetect -35dB) entre
40% e 60% da duração do episódio (pausas entre quadros), escolhe o mais
próximo do meio e descarta candidatos cujo texto vizinho (±90 palavras no
`-tts.txt`) contenha termos sensíveis (morte, assassinato, feminicídio...).
Validado 2026-08-04: 524.3s = 51.5%, fronteira EDUCAÇÃO→POLÍTICA.

## Integração no pipeline
`cmd_full` (pipeline.py) chama `ads_insert.py --date X --no-republish` na
etapa 5.5 (após o áudio, antes de archive/publish). Nunca bloqueia o dia:
falha vira aviso. O publish republica o áudio já com anúncio.

### Reinserção segura
Se o áudio do dia for regenerado (cron/re-run de TTS), o check de
idempotência compara a duração atual com backup+anúncio e reinseri
automaticamente. Backup da versão sem anúncio: `audio/{date}-sem-ad.mp3`
(sempre sobrescrito = versão corrente sem anúncio).

## Backend Tipo 1 (Supabase)
- `upsert_sponsor_admin` — cria/atualiza patrocinador (funciona com anon key).
- `link_episode_sponsor` — vínculo idempotente `episode_sponsors`
  (ON CONFLICT episode_date+sponsor_id). Criada via `07_link_episode_sponsor.sql`.
- **Rota local obrigatória para chamadas de script:**
  `http://127.0.0.1:8080/rest/v1/rpc/...` — o `SUPABASE_URL` do .env é a
  URL pública via túnel Cloudflare, que bloqueia User-Agent Python
  (CF error 1010 / HTTP 403). O `ads_insert.py` tenta 127.0.0.1:8080
  primeiro e cai para o .env.
- Selos "Apresentado por": frontend já lê RPC `get_episode_sponsors` (live)
  com fallback estático no `episodes.json` — `publish_site.py` agora preenche
  `sponsors` a partir do histórico do `ads/schedule.json`.

## Rotação atual (7 takes, 2 marcas)
fix-servicos-01 → facilita-vistorias-01 → fix-02 → facilita-02 → fix-03 →
facilita-03 → facilita-04 → (volta ao início). Nunca repete take até esgotar
o ciclo.

## Operações
```bash
PY=/home/osmar/.hermes/hermes-agent/venv/bin/python3
cd /home/osmar/web-jornal-vale-da-liberdade

# Ver qual anúncio cairia hoje (sem alterar nada)
$PY scripts/ads_insert.py --date YYYY-MM-DD --dry-run

# Inserir manualmente (já roda sozinho na etapa 5.5 do cmd_full)
$PY scripts/ads_insert.py --date YYYY-MM-DD

# Forçar take específico
$PY scripts/ads_insert.py --date YYYY-MM-DD --force-ad facilita-vistorias-02

# Novo anunciante: (1) gravar WAV em public/audio/Ads/; (2) transcrever
# (Gemini generateContent audio/wav); (3) pré-processar:
#   ffmpeg -i novo.wav -af "loudnorm=I=-16:TP=-1.5:LRA=11,aresample=44100" \
#     -ac 1 -b:a 192k ads/clips/SLUG-01.mp3
# (4) adicionar entrada em ads/schedule.json (ads + rotation_order).
```

## Notas
- Exclusivo do diário: o pipeline BM (Peter solo) nunca chama ads_insert.
- Os takes já têm abertura/fechamento naturais ("Uma pausa rápida para o
  nosso patrocinador..." / "...voltamos às notícias"), então o splice fica
  fluido sem vinheta extra.
- `placement` registrado no banco: `mid-roll`.
