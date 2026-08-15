-- Fatia 1: eventos de escuta com geo grosseira (sem IP).
-- Aplicar no Postgres do Supabase (psql / Studio).
-- Compatível com o fn_increment_view atual (2 args): recria com args extras opcionais.

CREATE TABLE IF NOT EXISTS public.listen_events (
    id            BIGSERIAL PRIMARY KEY,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    day           DATE NOT NULL DEFAULT (timezone('America/Sao_Paulo', NOW()))::date,
    episode_id    TEXT NOT NULL,
    identity_ref  TEXT,
    user_id       UUID,
    country       TEXT,
    region        TEXT,
    city          TEXT,
    tz            TEXT,
    source        TEXT
);

CREATE INDEX IF NOT EXISTS listen_events_day_idx
    ON public.listen_events (day DESC);
CREATE INDEX IF NOT EXISTS listen_events_country_idx
    ON public.listen_events (country, day DESC);
CREATE INDEX IF NOT EXISTS listen_events_episode_day_idx
    ON public.listen_events (episode_id, day DESC);

COMMENT ON TABLE public.listen_events IS
    'Um play = uma linha. País/cidade só de headers CF + fuso do browser. Sem IP/UA.';

ALTER TABLE public.listen_events ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS listen_events_no_direct ON public.listen_events;
CREATE POLICY listen_events_no_direct ON public.listen_events
    FOR ALL USING (false);

GRANT SELECT ON public.listen_events TO authenticated;

DROP FUNCTION IF EXISTS public.fn_increment_view(TEXT);
DROP FUNCTION IF EXISTS public.fn_increment_view(TEXT, TEXT);

CREATE OR REPLACE FUNCTION public.fn_increment_view(
    p_episode_id TEXT,
    p_fingerprint TEXT DEFAULT NULL,
    p_timezone TEXT DEFAULT NULL,
    p_source TEXT DEFAULT NULL
)
RETURNS JSON AS $function$
DECLARE
    v_ip TEXT := current_setting('request.header.x-forwarded-for', true);
    v_ua TEXT := current_setting('request.header.user-agent', true);
    v_country TEXT := nullif(upper(trim(current_setting('request.header.cf-ipcountry', true))), '');
    v_region TEXT := nullif(trim(current_setting('request.header.cf-region', true)), '');
    v_city TEXT := nullif(trim(current_setting('request.header.cf-ipcity', true)), '');
    v_fingerprint TEXT;
    v_count INTEGER;
    v_tz TEXT;
    v_src TEXT;
BEGIN
    IF p_episode_id IS NULL OR length(trim(p_episode_id)) = 0 THEN
        RAISE EXCEPTION 'invalid_episode_id';
    END IF;

    IF v_country IN ('XX', 'T1') THEN
        v_country := NULL;
    END IF;

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

    INSERT INTO public.anonymous_feedback (episode_id, identity_ref, feedback_type)
    VALUES (p_episode_id, v_fingerprint, 'view')
    ON CONFLICT (episode_id, identity_ref, feedback_type) DO NOTHING;

    INSERT INTO public.episode_view_counts (episode_id, view_count, updated_at)
    VALUES (p_episode_id, 1, NOW())
    ON CONFLICT (episode_id) DO UPDATE SET
        view_count = episode_view_counts.view_count + 1,
        updated_at = NOW();

    SELECT view_count INTO v_count
    FROM public.episode_view_counts
    WHERE episode_id = p_episode_id;

    v_tz := left(trim(COALESCE(p_timezone, '')), 64);
    IF v_tz = '' THEN
        v_tz := NULL;
    END IF;
    v_src := left(trim(COALESCE(p_source, '')), 64);
    IF v_src = '' THEN
        v_src := NULL;
    END IF;

    INSERT INTO public.listen_events (
        episode_id, identity_ref, user_id,
        country, region, city, tz, source
    ) VALUES (
        p_episode_id,
        v_fingerprint,
        auth.uid(),
        NULLIF(left(COALESCE(v_country, ''), 2), ''),
        NULLIF(left(COALESCE(v_region, ''), 64), ''),
        NULLIF(left(COALESCE(v_city, ''), 80), ''),
        v_tz,
        v_src
    );

    RETURN json_build_object('view_count', v_count, 'incremented', TRUE);
END;
$function$ LANGUAGE plpgsql SECURITY DEFINER;

COMMENT ON FUNCTION public.fn_increment_view(TEXT, TEXT, TEXT, TEXT) IS
    'Incrementa view e grava listen_event (geo por header CF + timezone). Sem persistir IP.';

GRANT ALL ON FUNCTION public.fn_increment_view(TEXT, TEXT, TEXT, TEXT) TO anon;
GRANT ALL ON FUNCTION public.fn_increment_view(TEXT, TEXT, TEXT, TEXT) TO authenticated;
GRANT ALL ON FUNCTION public.fn_increment_view(TEXT, TEXT, TEXT, TEXT) TO service_role;
