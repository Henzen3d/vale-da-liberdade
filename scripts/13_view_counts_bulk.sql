-- Bulk view counts for the feed (one POST instead of N).
-- episode_id is TEXT in this schema (dates + "especial-…"), not UUID.
CREATE OR REPLACE FUNCTION public.fn_get_view_counts_bulk(p_episode_ids text[])
RETURNS json
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $function$
DECLARE
    v_result json;
    v_ids text[];
BEGIN
    IF p_episode_ids IS NULL OR cardinality(p_episode_ids) = 0 THEN
        RETURN '{}'::json;
    END IF;

    -- Cap to keep a single request cheap (feed is well under this).
    v_ids := p_episode_ids[1:500];

    SELECT COALESCE(
        json_object_agg(q.episode_id, q.view_count),
        '{}'::json
    )
    INTO v_result
    FROM (
        SELECT i.episode_id, COALESCE(c.view_count, 0) AS view_count
        FROM unnest(v_ids) AS i(episode_id)
        LEFT JOIN public.episode_view_counts c ON c.episode_id = i.episode_id
    ) q;

    RETURN COALESCE(v_result, '{}'::json);
END;
$function$;

ALTER FUNCTION public.fn_get_view_counts_bulk(text[]) OWNER TO postgres;
GRANT EXECUTE ON FUNCTION public.fn_get_view_counts_bulk(text[]) TO anon, authenticated;

-- Existing RPCs: keep grants + search_path (idempotent).
GRANT EXECUTE ON FUNCTION public.fn_get_view_count(text) TO anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_increment_view(text, text) TO anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_get_monetization_config() TO anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_get_active_ad(text) TO anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_episode_sponsors(text[]) TO anon, authenticated;

NOTIFY pgrst, 'reload schema';
