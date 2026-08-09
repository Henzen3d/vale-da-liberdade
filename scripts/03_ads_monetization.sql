-- ═══════════════════════════════════════════════════════════════════════
-- 03_ads_monetization.sql
-- Backend de Monetização por Anúncios — Vale da Liberdade
-- Tipo 1: Patrocínio embutido no episódio (dado de produção)
-- Tipo 2: Interstitial entre episódios (campanha dinâmica)
--
-- Executar no SQL Editor do Supabase Studio (http://192.168.31.22:8080)
-- ═══════════════════════════════════════════════════════════════════════


-- ┌─────────────────────────────────────────────────┐
-- │  TIPO 1 — Patrocínio Embutido                   │
-- └─────────────────────────────────────────────────┘

-- Patrocinadores do podcast
CREATE TABLE IF NOT EXISTS public.sponsors (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    name        TEXT NOT NULL,                      -- "Citroën BR"
    logo_url    TEXT,                               -- URL da logo (R2/CDN)
    website_url TEXT,                               -- link de destino ao clicar
    active      BOOLEAN DEFAULT TRUE,               -- ativo para uso em novos episódios
    notes       TEXT,                               -- notas internas do admin
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Vínculo episódio ↔ patrocinador (tabela-ponte)
-- Não existe tabela `episodes` no Supabase (catálogo é JSON estático via feed.json).
-- episode_date TEXT segue o formato das tabelas existentes (user_feedback, etc).
CREATE TABLE IF NOT EXISTS public.episode_sponsors (
    id           UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    episode_date TEXT NOT NULL,                     -- "2026-08-03"
    sponsor_id   UUID NOT NULL REFERENCES public.sponsors(id) ON DELETE CASCADE,
    placement    TEXT DEFAULT 'pre-roll',           -- pre-roll / mid-roll / post-roll / full
    notes        TEXT,                              -- "Menção nos primeiros 30s"
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(episode_date, sponsor_id)
);

COMMENT ON TABLE public.sponsors IS 'Patrocinadores do podcast — dados de produção para selo visual e relatório';
COMMENT ON TABLE public.episode_sponsors IS 'Vínculo episódio↔patrocinador (Tipo 1: patrocínio embutido no áudio)';


-- ┌─────────────────────────────────────────────────┐
-- │  TIPO 2 — Interstitial entre Episódios           │
-- └─────────────────────────────────────────────────┘

-- Campanhas de anúncio interstitial
CREATE TABLE IF NOT EXISTS public.ad_campaigns (
    id                   UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    advertiser_name      TEXT NOT NULL,              -- "Citroën BR"
    sponsor_id           UUID REFERENCES public.sponsors(id) ON DELETE SET NULL,  -- vínculo opcional com Tipo 1
    title                TEXT,                       -- nome interno da campanha
    start_date           DATE NOT NULL,              -- início da veiculação
    end_date             DATE NOT NULL,              -- fim da veiculação (inclusive)
    active               BOOLEAN DEFAULT TRUE,       -- kill-switch manual
    skip_after_seconds   INTEGER DEFAULT 7,          -- delay antes de mostrar botão "Pular" (3-60s)
    priority             INTEGER DEFAULT 0,          -- prioridade (maior = preferência em conflito)
    notes                TEXT,                       -- notas internas
    -- Campos para futura integração com ad networks (inertes por ora)
    external_campaign_id TEXT,                       -- ID na rede externa (AdsWizz, etc)
    external_source      TEXT,                       -- "adswizz" / "spotify_audience_network" / null
    created_at           TIMESTAMPTZ DEFAULT NOW(),
    updated_at           TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT chk_campaign_dates CHECK (end_date >= start_date),
    CONSTRAINT chk_skip_range CHECK (skip_after_seconds >= 3 AND skip_after_seconds <= 60)
);

-- Criativos de campanhas interstitial (múltiplos por campanha, rotação por peso)
CREATE TABLE IF NOT EXISTS public.ad_creatives (
    id           UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    campaign_id  UUID NOT NULL REFERENCES public.ad_campaigns(id) ON DELETE CASCADE,
    media_type   TEXT NOT NULL CHECK (media_type IN ('image', 'gif', 'video')),
    media_url    TEXT NOT NULL,                     -- URL da imagem/gif/vídeo (R2/CDN)
    audio_url    TEXT,                              -- áudio próprio do anúncio (null se vídeo tem áudio nativo)
    click_url    TEXT,                              -- URL de destino ao clicar no anúncio
    weight       INTEGER DEFAULT 1 CHECK (weight > 0),  -- peso para rotação ponderada
    alt_text     TEXT,                              -- acessibilidade da mídia visual
    active       BOOLEAN DEFAULT TRUE,              -- habilitar/desabilitar criativo individual
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);

-- Índice para busca rápida de criativos ativos por campanha
CREATE INDEX IF NOT EXISTS idx_ad_creatives_campaign
    ON public.ad_creatives(campaign_id) WHERE active = TRUE;

-- Eventos de anúncio (impressão/clique/skip) — sem dados pessoais identificáveis
-- ⚠️ ON DELETE RESTRICT: impede exclusão acidental de campanha/criativo
--    que tenha eventos registrados. Use active=false em vez de DELETE.
--    Para limpar dados de teste: DELETE explícito nos eventos primeiro.
CREATE TABLE IF NOT EXISTS public.ad_events (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    creative_id UUID NOT NULL REFERENCES public.ad_creatives(id) ON DELETE RESTRICT,
    campaign_id UUID NOT NULL REFERENCES public.ad_campaigns(id) ON DELETE RESTRICT,
    event_type  TEXT NOT NULL CHECK (event_type IN ('impression', 'click', 'skip', 'error')),
    session_id  TEXT,                               -- UUID efêmero gerado no client (sessionStorage), não identificável
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Índice para relatórios por campanha e período
CREATE INDEX IF NOT EXISTS idx_ad_events_campaign_date
    ON public.ad_events(campaign_id, created_at);

-- Índice para anti-spam (busca por creative + session recente)
CREATE INDEX IF NOT EXISTS idx_ad_events_dedup
    ON public.ad_events(creative_id, session_id, created_at DESC);

COMMENT ON TABLE public.ad_campaigns IS 'Campanhas de anúncio interstitial (Tipo 2: entre episódios no auto-play)';
COMMENT ON TABLE public.ad_creatives IS 'Criativos de campanhas interstitial — mídia visual + áudio, rotação por peso';
COMMENT ON TABLE public.ad_events IS 'Eventos de anúncio (impressão/clique/skip) — sem dados pessoais identificáveis. ON DELETE RESTRICT protege histórico de faturamento.';


-- ┌─────────────────────────────────────────────────┐
-- │  ROW LEVEL SECURITY                             │
-- └─────────────────────────────────────────────────┘
-- Todas as tabelas de ads bloqueiam acesso direto pelo client anônimo.
-- Leitura pública: SOMENTE via RPC functions SECURITY DEFINER (Fase 2).
-- Escrita: SOMENTE via RPC controlada ou Table Editor autenticado (service_role).

ALTER TABLE public.sponsors ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.episode_sponsors ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ad_campaigns ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ad_creatives ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ad_events ENABLE ROW LEVEL SECURITY;

-- Nenhuma CREATE POLICY para role 'anon' = zero acesso direto.
-- service_role (Table Editor / RPCs SECURITY DEFINER) bypassa RLS automaticamente.
