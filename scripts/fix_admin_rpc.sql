-- FIX: Corrigir RPCs administrativas para colunas existentes nas tabelas

-- 1. CORRIJIR get_admin_kpis()
CREATE OR REPLACE FUNCTION public.get_admin_kpis()
RETURNS JSONB AS $$
DECLARE
    v_total_users BIGINT;
    v_active_subscribers BIGINT;
    v_monthly_impressions BIGINT;
    v_monthly_clicks BIGINT;
    v_ctr NUMERIC;
    v_active_campaigns BIGINT;
    v_active_sponsors BIGINT;
BEGIN
    SELECT COUNT(*) INTO v_total_users FROM public.user_profiles;
    SELECT COUNT(*) INTO v_active_subscribers FROM public.subscriptions WHERE status = 'active' AND plan_name IN ('premium', 'vip');
    SELECT COALESCE(SUM(CASE WHEN event_type = 'impression' THEN 1 ELSE 0 END), 0), COALESCE(SUM(CASE WHEN event_type = 'click' THEN 1 ELSE 0 END), 0) INTO v_monthly_impressions, v_monthly_clicks FROM public.ad_events ae JOIN public.ad_creatives ac ON ac.id = ae.creative_id WHERE ae.created_at >= date_trunc('month', NOW()) AND ac.active = TRUE;
    IF v_monthly_impressions > 0 THEN v_ctr := ROUND((v_monthly_clicks::NUMERIC / v_monthly_impressions) * 100, 2); ELSE v_ctr := 0; END IF;
    SELECT COUNT(*) INTO v_active_campaigns FROM public.ad_campaigns WHERE active = TRUE AND start_date <= CURRENT_DATE AND end_date >= CURRENT_DATE;
    SELECT COUNT(*) INTO v_active_sponsors FROM public.sponsors WHERE active = TRUE;
    RETURN jsonb_build_object('total_users', v_total_users, 'active_subscribers', v_active_subscribers, 'monthly_impressions', v_monthly_impressions, 'monthly_clicks', v_monthly_clicks, 'ctr_percent', v_ctr, 'active_campaigns', v_active_campaigns, 'active_sponsors', v_active_sponsors);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

-- 2. CORRIJIR get_admin_sponsors()
DROP FUNCTION IF EXISTS public.get_admin_sponsors();
CREATE FUNCTION public.get_admin_sponsors()
RETURNS TABLE (
    sponsor_id UUID,
    name TEXT,
    cnpj TEXT,
    email TEXT,
    logo_url TEXT,
    website_url TEXT,
    is_active BOOLEAN,
    contract_end DATE,
    created_at TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY SELECT s.id, s.name, NULL::TEXT, NULL::TEXT, s.logo_url, s.website_url, s.active, NULL::DATE, s.created_at FROM public.sponsors s ORDER BY s.name;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

-- 3. CORRIJIR get_admin_campaigns()
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
    RETURN QUERY SELECT ac.id, ac.advertiser_name, ac.sponsor_id, s.name, ac.format_type, ac.headline, ac.title, ac.start_date, ac.end_date, NULL::TEXT, NULL::TEXT, NULL::BIGINT, ac.active, 0, 0, 0, 0, ac.priority FROM public.ad_campaigns ac LEFT JOIN public.sponsors s ON s.id = ac.sponsor_id ORDER BY ac.created_at DESC;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

-- 4. CORRIJIR get_admin_users_and_subs()
DROP FUNCTION IF EXISTS public.get_admin_users_and_subs();
CREATE FUNCTION public.get_admin_users_and_subs()
RETURNS TABLE (
    user_id UUID,
    email TEXT,
    name TEXT,
    role TEXT,
    avatar_url TEXT,
    created_at TIMESTAMPTZ,
    last_login TIMESTAMPTZ,
    sub_id UUID,
    sub_plan_name TEXT,
    sub_status TEXT,
    sub_price_cents INTEGER,
    sub_started_at TIMESTAMPTZ,
    sub_expires_at TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY SELECT up.id, up.email, up.full_name, up.role, up.avatar_url, up.created_at, NULL::TIMESTAMPTZ, s.id, s.plan_name, s.status, s.price_cents, s.started_at, s.expires_at FROM public.user_profiles up LEFT JOIN public.subscriptions s ON s.user_id = up.id WHERE up.id != auth.uid() ORDER BY up.created_at DESC;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

-- Testar as RPCs
SELECT 'get_admin_kpis' as rpc, * FROM get_admin_kpis();
SELECT 'get_admin_sponsors' as rpc, * FROM get_admin_sponsors();
SELECT 'get_admin_campaigns' as rpc, * FROM get_admin_campaigns();
SELECT 'get_admin_users_and_subs' as rpc, * FROM get_admin_users_and_subs();
SELECT 'get_admin_ad_metrics_timeseries' as rpc, * FROM get_admin_ad_metrics_timeseries(p_days := 30);
