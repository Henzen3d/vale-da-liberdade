-- Fix: push corrected fn_increment_view and fn_toggle_anonymous_like to Supabase
-- The bug: digest(text, 'sha256') fails because 'sha256' is inferred as unknown type
-- Fix: cast 'sha256'::text explicitly

-- Ensure pgcrypto extension is available
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 1. Contagem global de views por episódio
CREATE TABLE IF NOT EXISTS public.episode_view_counts (
    episode_id TEXT PRIMARY KEY,
    view_count INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE OR REPLACE FUNCTION public.fn_increment_view(p_episode_id TEXT)
RETURNS JSON AS $$
DECLARE
    v_ip TEXT := current_setting('request.header.x-forwarded-for', true);
    v_ua TEXT := current_setting('request.header.user-agent', true);
    v_fingerprint TEXT;
    v_last_view TIMESTAMPTZ;
    v_count INTEGER;
BEGIN
    IF p_episode_id IS NULL OR length(trim(p_episode_id)) = 0 THEN
        RAISE EXCEPTION 'invalid_episode_id';
    END IF;
    
    -- Gerar fingerprint do IP + UA (SHA256) — 'sha256'::text evita erro 42883
    v_fingerprint := encode(
        digest(v_ip || ':' || v_ua, 'sha256'::text),
        'hex'
    );
    
    -- Verificar se já viu nos últimos 5 minutos
    SELECT created_at INTO v_last_view
    FROM public.anonymous_feedback
    WHERE episode_id = p_episode_id
      AND identity_ref = v_fingerprint
      AND feedback_type = 'view'
    ORDER BY created_at DESC
    LIMIT 1;
    
    IF v_last_view IS NOT NULL AND v_last_view > NOW() - INTERVAL '5 minutes' THEN
        RETURN json_build_object('view_count', 0, 'incremented', FALSE);
    END IF;
    
    -- Registrar nova view
    INSERT INTO public.anonymous_feedback (episode_id, identity_ref, feedback_type)
    VALUES (p_episode_id, v_fingerprint, 'view')
    ON CONFLICT (episode_id, identity_ref, feedback_type) DO NOTHING;
    
    -- Incrementar contagem
    INSERT INTO public.episode_view_counts (episode_id, view_count, updated_at)
    VALUES (p_episode_id, 1, NOW())
    ON CONFLICT (episode_id) DO UPDATE SET
        view_count = episode_view_counts.view_count + 1,
        updated_at = NOW();
    
    SELECT view_count INTO v_count
    FROM public.episode_view_counts
    WHERE episode_id = p_episode_id;
    
    RETURN json_build_object('view_count', v_count, 'incremented', TRUE);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 2. RPC: toggle like anônimo
CREATE OR REPLACE FUNCTION public.fn_toggle_anonymous_like(p_episode_id TEXT)
RETURNS JSON AS $$
DECLARE
    v_ip TEXT := current_setting('request.header.x-forwarded-for', true);
    v_ua TEXT := current_setting('request.header.user-agent', true);
    v_fingerprint TEXT;
    v_exists BOOLEAN;
BEGIN
    IF p_episode_id IS NULL OR length(trim(p_episode_id)) = 0 THEN
        RAISE EXCEPTION 'invalid_episode_id';
    END IF;
    
    v_fingerprint := encode(
        digest(v_ip || ':' || v_ua, 'sha256'::text),
        'hex'
    );
    
    SELECT EXISTS (
        SELECT 1 FROM public.anonymous_feedback
        WHERE episode_id = p_episode_id
          AND identity_ref = v_fingerprint
          AND feedback_type = 'like'
    ) INTO v_exists;
    
    IF v_exists THEN
        DELETE FROM public.anonymous_feedback
        WHERE episode_id = p_episode_id
          AND identity_ref = v_fingerprint
          AND feedback_type = 'like';
        RETURN json_build_object('liked', FALSE);
    ELSE
        INSERT INTO public.anonymous_feedback (episode_id, identity_ref, feedback_type)
        VALUES (p_episode_id, v_fingerprint, 'like')
        ON CONFLICT (episode_id, identity_ref, feedback_type) DO NOTHING;
        RETURN json_build_object('liked', TRUE);
    END IF;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
