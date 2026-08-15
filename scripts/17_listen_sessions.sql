-- Fatia 5: sessões de escuta (heartbeat). Tempo ouvido, não só posição máxima.

CREATE TABLE IF NOT EXISTS public.listen_sessions (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    started_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_beat_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    day               DATE NOT NULL DEFAULT (timezone('America/Sao_Paulo', NOW()))::date,
    episode_id        TEXT NOT NULL,
    identity_ref      TEXT,
    user_id           UUID,
    listened_seconds  INTEGER NOT NULL DEFAULT 0 CHECK (listened_seconds >= 0),
    duration_seconds  INTEGER,
    completed         BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS listen_sessions_day_idx
    ON public.listen_sessions (day DESC);
CREATE INDEX IF NOT EXISTS listen_sessions_episode_day_idx
    ON public.listen_sessions (episode_id, day DESC);

COMMENT ON TABLE public.listen_sessions IS
    'Sessão de play: soma de heartbeats (~60s). Sem IP. Fingerprint ou user_id.';

ALTER TABLE public.listen_sessions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS listen_sessions_no_direct ON public.listen_sessions;
CREATE POLICY listen_sessions_no_direct ON public.listen_sessions
    FOR ALL USING (false);

CREATE OR REPLACE FUNCTION public.fn_listen_heartbeat(
    p_episode_id TEXT,
    p_fingerprint TEXT DEFAULT NULL,
    p_session_id UUID DEFAULT NULL,
    p_delta_seconds INTEGER DEFAULT 60,
    p_duration_seconds INTEGER DEFAULT NULL,
    p_position_seconds INTEGER DEFAULT NULL
)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_delta INTEGER := LEAST(GREATEST(COALESCE(p_delta_seconds, 60), 1), 90);
    v_fp TEXT;
    v_sid UUID;
    v_row public.listen_sessions%ROWTYPE;
    v_dur INTEGER;
    v_listened INTEGER;
    v_completed BOOLEAN;
BEGIN
    IF p_episode_id IS NULL OR length(trim(p_episode_id)) = 0 THEN
        RAISE EXCEPTION 'invalid_episode_id';
    END IF;

    IF p_fingerprint IS NOT NULL AND length(trim(p_fingerprint)) >= 32 THEN
        v_fp := 'c:' || trim(p_fingerprint);
    ELSE
        v_fp := NULL;
    END IF;

    IF p_session_id IS NOT NULL THEN
        SELECT * INTO v_row
        FROM public.listen_sessions
        WHERE id = p_session_id
          AND episode_id = p_episode_id
          AND last_beat_at > NOW() - INTERVAL '20 minutes';
    END IF;

    IF v_row.id IS NULL THEN
        INSERT INTO public.listen_sessions (
            episode_id, identity_ref, user_id,
            listened_seconds, duration_seconds, completed
        ) VALUES (
            trim(p_episode_id),
            v_fp,
            auth.uid(),
            v_delta,
            NULLIF(p_duration_seconds, 0),
            FALSE
        )
        RETURNING * INTO v_row;
    ELSE
        UPDATE public.listen_sessions SET
            listened_seconds = listen_sessions.listened_seconds + v_delta,
            duration_seconds = COALESCE(NULLIF(p_duration_seconds, 0), listen_sessions.duration_seconds),
            last_beat_at = NOW(),
            user_id = COALESCE(auth.uid(), listen_sessions.user_id),
            identity_ref = COALESCE(v_fp, listen_sessions.identity_ref)
        WHERE id = v_row.id
        RETURNING * INTO v_row;
    END IF;

    v_sid := v_row.id;
    v_dur := v_row.duration_seconds;
    v_listened := v_row.listened_seconds;
    v_completed := v_row.completed
        OR (v_dur IS NOT NULL AND v_dur > 0 AND (
            v_listened >= CEIL(v_dur * 0.95)
            OR (p_position_seconds IS NOT NULL AND p_position_seconds >= CEIL(v_dur * 0.95))
        ));

    IF v_completed AND NOT v_row.completed THEN
        UPDATE public.listen_sessions SET completed = TRUE WHERE id = v_sid;
    END IF;

    RETURN json_build_object(
        'session_id', v_sid,
        'listened_seconds', v_listened,
        'duration_seconds', v_dur,
        'completed', v_completed
    );
END;
$$;

COMMENT ON FUNCTION public.fn_listen_heartbeat(TEXT, TEXT, UUID, INTEGER, INTEGER, INTEGER) IS
    'Acumula tempo ouvido (delta 1–90s). Sessão nova se >20 min ou outro episódio.';

GRANT EXECUTE ON FUNCTION public.fn_listen_heartbeat(TEXT, TEXT, UUID, INTEGER, INTEGER, INTEGER) TO anon;
GRANT EXECUTE ON FUNCTION public.fn_listen_heartbeat(TEXT, TEXT, UUID, INTEGER, INTEGER, INTEGER) TO authenticated;
GRANT EXECUTE ON FUNCTION public.fn_listen_heartbeat(TEXT, TEXT, UUID, INTEGER, INTEGER, INTEGER) TO service_role;

-- Amplia a RPC de stats com tempo médio / conclusão (sessões).
CREATE OR REPLACE FUNCTION public.get_admin_listen_stats(p_days INTEGER DEFAULT 30)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_days INTEGER := LEAST(GREATEST(COALESCE(p_days, 30), 1), 365);
    v_from DATE := (timezone('America/Sao_Paulo', NOW()))::date - (v_days - 1);
BEGIN
    IF NOT public.is_admin_user() THEN
        RETURN jsonb_build_object('ok', FALSE, 'error', 'Acesso negado: requer role admin');
    END IF;

    RETURN jsonb_build_object(
        'ok', TRUE,
        'days', v_days,
        'from', v_from,
        'total_plays', (SELECT COUNT(*) FROM public.listen_events WHERE day >= v_from),
        'unique_listeners', (
            SELECT COUNT(DISTINCT identity_ref)
            FROM public.listen_events
            WHERE day >= v_from AND identity_ref IS NOT NULL
        ),
        'logged_in_plays', (
            SELECT COUNT(*) FROM public.listen_events
            WHERE day >= v_from AND user_id IS NOT NULL
        ),
        'sessions', (SELECT COUNT(*) FROM public.listen_sessions WHERE day >= v_from),
        'avg_listened_sec', COALESCE((
            SELECT ROUND(AVG(listened_seconds))::int
            FROM public.listen_sessions
            WHERE day >= v_from AND listened_seconds > 0
        ), 0),
        'completion_pct', COALESCE((
            SELECT ROUND(100.0 * AVG(CASE WHEN completed THEN 1 ELSE 0 END), 1)
            FROM public.listen_sessions
            WHERE day >= v_from
        ), 0),
        'by_day', COALESCE((
            SELECT jsonb_agg(row_to_json(t)::jsonb ORDER BY t.day)
            FROM (
                SELECT day, COUNT(*)::int AS plays
                FROM public.listen_events
                WHERE day >= v_from
                GROUP BY day
            ) t
        ), '[]'::jsonb),
        'by_country', COALESCE((
            SELECT jsonb_agg(row_to_json(t)::jsonb)
            FROM (
                SELECT COALESCE(NULLIF(country, ''), '(sem país)') AS country,
                       COUNT(*)::int AS plays
                FROM public.listen_events
                WHERE day >= v_from
                GROUP BY 1
                ORDER BY plays DESC
                LIMIT 20
            ) t
        ), '[]'::jsonb),
        'by_city', COALESCE((
            SELECT jsonb_agg(row_to_json(t)::jsonb)
            FROM (
                SELECT COALESCE(NULLIF(city, ''), '(sem cidade)') AS city,
                       COALESCE(NULLIF(country, ''), '') AS country,
                       COUNT(*)::int AS plays
                FROM public.listen_events
                WHERE day >= v_from
                GROUP BY 1, 2
                ORDER BY plays DESC
                LIMIT 20
            ) t
        ), '[]'::jsonb),
        'by_tz', COALESCE((
            SELECT jsonb_agg(row_to_json(t)::jsonb)
            FROM (
                SELECT COALESCE(NULLIF(tz, ''), '(sem fuso)') AS tz,
                       COUNT(*)::int AS plays
                FROM public.listen_events
                WHERE day >= v_from
                GROUP BY 1
                ORDER BY plays DESC
                LIMIT 20
            ) t
        ), '[]'::jsonb),
        'by_episode', COALESCE((
            SELECT jsonb_agg(row_to_json(t)::jsonb)
            FROM (
                SELECT e.episode_id,
                       COUNT(*)::int AS plays,
                       COALESCE(s.avg_sec, 0) AS avg_sec,
                       COALESCE(s.completed, 0) AS completed
                FROM public.listen_events e
                LEFT JOIN (
                    SELECT episode_id,
                           ROUND(AVG(listened_seconds))::int AS avg_sec,
                           COUNT(*) FILTER (WHERE completed)::int AS completed
                    FROM public.listen_sessions
                    WHERE day >= v_from
                    GROUP BY episode_id
                ) s ON s.episode_id = e.episode_id
                WHERE e.day >= v_from
                GROUP BY e.episode_id, s.avg_sec, s.completed
                ORDER BY plays DESC
                LIMIT 15
            ) t
        ), '[]'::jsonb),
        'by_source', COALESCE((
            SELECT jsonb_agg(row_to_json(t)::jsonb)
            FROM (
                SELECT COALESCE(NULLIF(source, ''), '(direto)') AS source,
                       COUNT(*)::int AS plays
                FROM public.listen_events
                WHERE day >= v_from
                GROUP BY 1
                ORDER BY plays DESC
            ) t
        ), '[]'::jsonb)
    );
END;
$$;
