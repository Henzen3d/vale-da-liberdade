-- Interações sociais por episódio (views, likes anônimos, saves)
-- Executar no SQL Editor do Supabase Studio ou via psql

-- 1. Contagem global de views por episódio (anônima)
CREATE TABLE IF NOT EXISTS public.episode_view_counts (
    episode_id TEXT PRIMARY KEY,
    view_count INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE public.episode_view_counts IS 
    'Contagem global de views por episódio; acessível publicamente';

-- 2. Feedback anônimo (like, view) por fingerprint hash
--    identity_ref = 'c:' + hash client-side (localStorage) OU 's:' + SHA256(ip + user_agent)
CREATE TABLE IF NOT EXISTS public.anonymous_feedback (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    episode_id TEXT NOT NULL,
    identity_ref TEXT NOT NULL,
    feedback_type TEXT NOT NULL CHECK (feedback_type IN ('like', 'view')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(episode_id, identity_ref, feedback_type)
);

COMMENT ON TABLE public.anonymous_feedback IS 
    'Feedback anônimo por episódio; histórico de views/likes (sem debounce de view)';

-- 3. RPC: incrementar view — SEM debounce, toda play conta
CREATE OR REPLACE FUNCTION public.fn_increment_view(p_episode_id TEXT, p_fingerprint TEXT DEFAULT NULL)
RETURNS JSON AS $function$
DECLARE
    v_ip TEXT := current_setting('request.header.x-forwarded-for', true);
    v_ua TEXT := current_setting('request.header.user-agent', true);
    v_fingerprint TEXT;
    v_count INTEGER;
BEGIN
    IF p_episode_id IS NULL OR length(trim(p_episode_id)) = 0 THEN
        RAISE EXCEPTION 'invalid_episode_id';
    END IF;

    -- Fingerprint do cliente (preferido — localStorage, por usuário real) 
    -- ou fallback hash de IP+UA. Prefixos 'c:'/'s:' separam as origens.
    IF p_fingerprint IS NOT NULL AND length(trim(p_fingerprint)) >= 32 THEN
        v_fingerprint := 'c:' || trim(p_fingerprint);
    ELSE
        v_ip := COALESCE(v_ip, '');
        v_ua := COALESCE(v_ua, '');
        v_fingerprint := 's:' || encode(
            extensions.digest(v_ip || ':' || v_ua, 'sha256'::text),
            'hex'
        );
    END IF;

    -- Sem debounce: toda play conta. Registro de feedback apenas para rastreio
    -- (ON CONFLICT DO NOTHING evita duplicar histórico, mas o contador incrementa SEMPRE).
    INSERT INTO public.anonymous_feedback (episode_id, identity_ref, feedback_type)
    VALUES (p_episode_id, v_fingerprint, 'view')
    ON CONFLICT (episode_id, identity_ref, feedback_type) DO NOTHING;

    -- Incrementar contagem sempre
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
$function$ LANGUAGE plpgsql SECURITY DEFINER;

-- 4. RPC: ler contagem (leitura pura, não incrementa — usada ao renderizar listas)
CREATE OR REPLACE FUNCTION public.fn_get_view_count(p_episode_id TEXT)
RETURNS JSON AS $function$
DECLARE
    v_count INTEGER;
BEGIN
    IF p_episode_id IS NULL OR length(trim(p_episode_id)) = 0 THEN
        RAISE EXCEPTION 'invalid_episode_id';
    END IF;
    SELECT view_count INTO v_count
    FROM public.episode_view_counts
    WHERE episode_id = p_episode_id;
    RETURN json_build_object('view_count', COALESCE(v_count, 0));
END;
$function$ LANGUAGE plpgsql SECURITY DEFINER;

-- 5. RPC: toggle like anônimo (primeiro like conta, segundo remove)
CREATE OR REPLACE FUNCTION public.fn_toggle_anonymous_like(p_episode_id TEXT)
RETURNS JSON AS $function$
DECLARE
    v_ip TEXT := current_setting('request.header.x-forwarded-for', true);
    v_ua TEXT := current_setting('request.header.user-agent', true);
    v_fingerprint TEXT;
    v_exists BOOLEAN;
BEGIN
    IF p_episode_id IS NULL OR length(trim(p_episode_id)) = 0 THEN
        RAISE EXCEPTION 'invalid_episode_id';
    END IF;
    
    v_ip := COALESCE(v_ip, '');
    v_ua := COALESCE(v_ua, '');
    
    v_fingerprint := encode(
        extensions.digest(v_ip || ':' || v_ua, 'sha256'::text),
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
$function$ LANGUAGE plpgsql SECURITY DEFINER;

COMMENT ON FUNCTION public.fn_increment_view(TEXT, TEXT) IS 
    'Incrementa view — SEM debounce, toda play conta. Aceita fingerprint client-side opcional.';
COMMENT ON FUNCTION public.fn_get_view_count(TEXT) IS 
    'Leitura pura da contagem de views (não incrementa).';
COMMENT ON FUNCTION public.fn_toggle_anonymous_like(TEXT) IS 
    'Toggle like anônimo por fingerprint (primeiro like conta, segundo remove)';

-- 6. Grant permissions
GRANT ALL ON FUNCTION public.fn_increment_view(TEXT, TEXT) TO anon;
GRANT ALL ON FUNCTION public.fn_increment_view(TEXT) TO anon;
GRANT ALL ON FUNCTION public.fn_get_view_count(TEXT) TO anon;
GRANT ALL ON FUNCTION public.fn_toggle_anonymous_like(TEXT) TO anon;
GRANT ALL ON TABLE public.anonymous_feedback TO anon;
