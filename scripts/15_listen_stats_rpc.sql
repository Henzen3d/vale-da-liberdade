-- Fatia 2: RPC admin de estatísticas de escuta.
-- Requer is_admin_user(). Sem PII além de país/cidade/fuso já gravados.

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
        'total_plays', (
            SELECT COUNT(*) FROM public.listen_events WHERE day >= v_from
        ),
        'unique_listeners', (
            SELECT COUNT(DISTINCT identity_ref)
            FROM public.listen_events
            WHERE day >= v_from AND identity_ref IS NOT NULL
        ),
        'logged_in_plays', (
            SELECT COUNT(*) FROM public.listen_events
            WHERE day >= v_from AND user_id IS NOT NULL
        ),
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
                SELECT episode_id, COUNT(*)::int AS plays
                FROM public.listen_events
                WHERE day >= v_from
                GROUP BY episode_id
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

COMMENT ON FUNCTION public.get_admin_listen_stats(INTEGER) IS
    'Agregados de listen_events (plays, país, cidade, fuso, episódio). Só admin.';

GRANT EXECUTE ON FUNCTION public.get_admin_listen_stats(INTEGER) TO anon;
GRANT EXECUTE ON FUNCTION public.get_admin_listen_stats(INTEGER) TO authenticated;
GRANT EXECUTE ON FUNCTION public.get_admin_listen_stats(INTEGER) TO service_role;
