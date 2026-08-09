-- ═══════════════════════════════════════════════════════════════════════
-- 04_ads_rpc_functions.sql
-- Funções RPC para Monetização por Anúncios — Vale da Liberdade
--
-- Exposição de API via RPC com SECURITY DEFINER (bypass em RLS para anon)
-- Executar no SQL Editor do Supabase Studio (http://192.168.31.22:8080)
-- ═══════════════════════════════════════════════════════════════════════


-- ┌────────────────────────────────────────────────────────┐
-- │ 1. get_active_interstitial_ad()                        │
-- │ Seleciona um criativo de maior prioridade ativa,       │
-- │ com rotação ponderada por peso entre a prioridade top. │
-- └────────────────────────────────────────────────────────┘

CREATE OR REPLACE FUNCTION public.get_active_interstitial_ad()
RETURNS JSONB AS $$
DECLARE
    result JSONB;
BEGIN
    WITH active_candidates AS (
        -- 1. Filtra apenas criativos e campanhas ativas no período (start_date <= hoje <= end_date)
        --    Garante kill-switch manual via ad_campaigns.active = TRUE E ad_creatives.active = TRUE
        SELECT 
            c.id AS creative_id,
            cmp.id AS campaign_id,
            c.media_type,
            c.media_url,
            c.audio_url,
            c.click_url,
            c.weight,
            c.alt_text,
            cmp.skip_after_seconds,
            cmp.advertiser_name,
            cmp.priority
        FROM public.ad_creatives c
        JOIN public.ad_campaigns cmp ON cmp.id = c.campaign_id
        WHERE c.active = TRUE
          AND cmp.active = TRUE
          AND cmp.start_date <= CURRENT_DATE
          AND cmp.end_date >= CURRENT_DATE
    ),
    top_priority AS (
        -- 2. Filtra apenas a(s) campanha(s) de MAIOR prioridade entre as ativas simultâneas
        SELECT * 
        FROM active_candidates
        WHERE priority = (SELECT MAX(priority) FROM active_candidates)
    )
    -- 3. Entre os criativos da prioridade top, aplica rotação ponderada por peso: ORDER BY -ln(random()) / weight ASC
    SELECT jsonb_build_object(
        'creative_id', creative_id,
        'campaign_id', campaign_id,
        'media_type', media_type,
        'media_url', media_url,
        'audio_url', audio_url,
        'click_url', click_url,
        'skip_after_seconds', skip_after_seconds,
        'advertiser_name', advertiser_name,
        'alt_text', alt_text
    ) INTO result
    FROM top_priority
    ORDER BY (-ln(random()) / weight) ASC
    LIMIT 1;

    -- Se não houver anúncio ativo no período, retorna NULL silenciosamente
    RETURN result;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

COMMENT ON FUNCTION public.get_active_interstitial_ad() IS
'Retorna 1 criativo ativo da campanha de maior prioridade (com rotação por peso entre empates de prioridade). Retorna NULL se zero campanhas ativas.';


-- ┌────────────────────────────────────────────────────────┐
-- │ 2. track_ad_event()                                    │
-- │ Registra impressões, cliques e skips com anti-spam     │
-- │ estendido para impression E click (janela de 10s).    │
-- └────────────────────────────────────────────────────────┘

CREATE OR REPLACE FUNCTION public.track_ad_event(
    p_creative_id UUID,
    p_event_type  TEXT,
    p_session_id  TEXT DEFAULT NULL
)
RETURNS JSONB AS $$
DECLARE
    v_campaign_id UUID;
    v_recent_count INT := 0;
    v_event_id UUID;
BEGIN
    -- 1. Validar tipo de evento
    IF p_event_type NOT IN ('impression', 'click', 'skip', 'error') THEN
        RAISE EXCEPTION 'Tipo de evento inválido: %. Esperado: impression, click, skip, error', p_event_type;
    END IF;

    -- 2. Buscar campaign_id correspondente ao criativo
    SELECT campaign_id INTO v_campaign_id
    FROM public.ad_creatives
    WHERE id = p_creative_id;

    IF v_campaign_id IS NULL THEN
        RETURN jsonb_build_object(
            'ok', FALSE,
            'error', 'Criativo não encontrado'
        );
    END IF;

    -- 3. Anti-spam para IMPRESSION e CLICK (mesmo creative + mesma sessão nos últimos 10 segundos)
    IF p_event_type IN ('impression', 'click') AND p_session_id IS NOT NULL AND p_session_id <> '' THEN
        SELECT COUNT(*) INTO v_recent_count
        FROM public.ad_events
        WHERE creative_id = p_creative_id
          AND session_id = p_session_id
          AND event_type = p_event_type
          AND created_at > (NOW() - INTERVAL '10 seconds');

        IF v_recent_count > 0 THEN
            RETURN jsonb_build_object(
                'ok', TRUE,
                'ignored', TRUE,
                'reason', 'rate_limit'
            );
        END IF;
    END IF;

    -- 4. Registrar o evento
    INSERT INTO public.ad_events (
        creative_id,
        campaign_id,
        event_type,
        session_id
    ) VALUES (
        p_creative_id,
        v_campaign_id,
        p_event_type,
        p_session_id
    )
    RETURNING id INTO v_event_id;

    RETURN jsonb_build_object(
        'ok', TRUE,
        'event_id', v_event_id,
        'ignored', FALSE
    );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

COMMENT ON FUNCTION public.track_ad_event(UUID, TEXT, TEXT) IS
'Insere métrica em ad_events (impression, click, skip) com janela anti-spam de 10s para impressões e cliques da mesma sessão.';


-- ┌────────────────────────────────────────────────────────┐
-- │ 3. get_episode_sponsors()                              │
-- │ Busca patrocinadores do Tipo 1 agrupados por episódio  │
-- └────────────────────────────────────────────────────────┘

CREATE OR REPLACE FUNCTION public.get_episode_sponsors(
    p_episode_dates TEXT[] DEFAULT NULL
)
RETURNS JSONB AS $$
DECLARE
    result JSONB;
BEGIN
    SELECT jsonb_object_agg(episode_date, sponsors_list) INTO result
    FROM (
        SELECT 
            es.episode_date,
            jsonb_agg(
                jsonb_build_object(
                    'sponsor_id', s.id,
                    'name', s.name,
                    'logo_url', s.logo_url,
                    'website_url', s.website_url,
                    'placement', es.placement
                )
            ) AS sponsors_list
        FROM public.episode_sponsors es
        JOIN public.sponsors s ON s.id = es.sponsor_id
        WHERE s.active = TRUE
          AND (p_episode_dates IS NULL OR es.episode_date = ANY(p_episode_dates))
        GROUP BY es.episode_date
    ) sub;

    RETURN COALESCE(result, '{}'::jsonb);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

COMMENT ON FUNCTION public.get_episode_sponsors(TEXT[]) IS
'Retorna patrocinadores ativos do Tipo 1 agrupados por data de episódio. Exemplo de retorno: {"2026-08-03": [{"name": "Citroën BR", ...}]}';

