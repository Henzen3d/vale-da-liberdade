-- FIX: Corrigir RPC get_admin_campaigns() - tipos corretos

DROP FUNCTION IF EXISTS public.get_admin_campaigns();
CREATE FUNCTION public.get_admin_campaigns()
RETURNS TABLE (
    campaign_id UUID,
    campaign_name TEXT,
    sponsor_id UUID,
    sponsor_name TEXT,
    format_type TEXT,
    headline TEXT,
    cta_url TEXT,
    start_date DATE,
    end_date DATE,
    media_url TEXT,
    media_name TEXT,
    media_size BIGINT,
    is_active BOOLEAN,
    impressions BIGINT,
    clicks BIGINT,
    skips BIGINT,
    errors BIGINT,
    priority INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        ac.id,
        ac.advertiser_name,
        ac.sponsor_id,
        s.name,
        ac.format_type,
        ac.headline,
        ac.title,
        ac.start_date,
        ac.end_date,
        NULL::TEXT,
        NULL::TEXT,
        NULL::BIGINT,
        ac.active,
        0::BIGINT,
        0::BIGINT,
        0::BIGINT,
        0::BIGINT,
        ac.priority
    FROM public.ad_campaigns ac
    LEFT JOIN public.sponsors s ON s.id = ac.sponsor_id
    ORDER BY ac.created_at DESC;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

-- Testar
SELECT * FROM get_admin_campaigns();
