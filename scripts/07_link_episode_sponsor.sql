CREATE OR REPLACE FUNCTION public.link_episode_sponsor(
    p_episode_date TEXT,
    p_sponsor_id UUID,
    p_placement TEXT DEFAULT 'mid-roll',
    p_notes TEXT DEFAULT NULL
)
RETURNS JSONB AS $$
DECLARE
    v_id UUID;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM public.sponsors WHERE id = p_sponsor_id) THEN
        RETURN jsonb_build_object('ok', FALSE, 'error', 'sponsor_id não encontrado');
    END IF;

    INSERT INTO public.episode_sponsors (episode_date, sponsor_id, placement, notes)
    VALUES (p_episode_date, p_sponsor_id, p_placement, p_notes)
    ON CONFLICT (episode_date, sponsor_id) DO UPDATE
        SET placement = EXCLUDED.placement,
            notes = EXCLUDED.notes
    RETURNING id INTO v_id;

    RETURN jsonb_build_object('ok', TRUE, 'episode_sponsor_id', v_id);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

COMMENT ON FUNCTION public.link_episode_sponsor(TEXT, UUID, TEXT, TEXT) IS
'Vincula patrocinador Tipo 1 a um episódio por data (idempotente via UNIQUE). Usado pelo pipeline de inserção de anúncios.';

GRANT EXECUTE ON FUNCTION public.link_episode_sponsor(TEXT, UUID, TEXT, TEXT) TO anon, authenticated;
