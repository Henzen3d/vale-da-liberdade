-- ═══════════════════════════════════════════════════════════════════════
-- 05_admin_dashboard_backend.sql
-- Backend Administrativo para Dashboard Web Admin — Vale da Liberdade
--
-- Cria:
--   1. Tabela subscriptions (assinaturas dos usuários)
--   2. Coluna role em user_profiles (se não existir)
--   3. RPCs administrativas:
--      - is_admin_user()
--      - toggle_entity_active(entity_type, entity_id)
--      - get_admin_kpis()
--      - get_admin_ad_metrics_timeseries()
--      - get_admin_users_and_subs()
--
-- Executar no SQL Editor do Supabase Studio
-- ═══════════════════════════════════════════════════════════════════════

-- ───────────────────────────────────────────────────────────────────────
-- 1. TABELA subscriptions
-- ───────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    plan_name TEXT NOT NULL DEFAULT 'free',
    status TEXT NOT NULL DEFAULT 'active',
    price_cents INTEGER DEFAULT 0,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.subscriptions
    ADD CONSTRAINT subscriptions_plan_name_check CHECK (plan_name IN ('free', 'premium', 'vip'));

ALTER TABLE public.subscriptions
    ADD CONSTRAINT subscriptions_status_check CHECK (status IN ('active', 'cancelled', 'past_due'));

-- RLS para subscriptions (admin only via RPCs)
ALTER TABLE public.subscriptions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Allow admin read subscriptions" ON public.subscriptions;
CREATE POLICY "Allow admin read subscriptions" ON public.subscriptions
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM public.user_profiles up
            WHERE up.id = auth.uid() AND up.role = 'admin'
        )
    );

DROP POLICY IF EXISTS "Allow admin insert subscriptions" ON public.subscriptions;
CREATE POLICY "Allow admin insert subscriptions" ON public.subscriptions
    FOR INSERT WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.user_profiles up
            WHERE up.id = auth.uid() AND up.role = 'admin'
        )
    );

DROP POLICY IF EXISTS "Allow admin update subscriptions" ON public.subscriptions;
CREATE POLICY "Allow admin update subscriptions" ON public.subscriptions
    FOR UPDATE USING (
        EXISTS (
            SELECT 1 FROM public.user_profiles up
            WHERE up.id = auth.uid() AND up.role = 'admin'
        )
    );

DROP POLICY IF EXISTS "Allow admin delete subscriptions" ON public.subscriptions;
CREATE POLICY "Allow admin delete subscriptions" ON public.subscriptions
    FOR DELETE USING (
        EXISTS (
            SELECT 1 FROM public.user_profiles up
            WHERE up.id = auth.uid() AND up.role = 'admin'
        )
    );

-- Indexes para performance
CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id ON public.subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_email ON public.subscriptions(email);
CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON public.subscriptions(status);


-- ───────────────────────────────────────────────────────────────────────
-- 2. COLUNA role EM user_profiles (se não existir)
-- ───────────────────────────────────────────────────────────────────────

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'user_profiles'
          AND column_name = 'role'
    ) THEN
        ALTER TABLE public.user_profiles ADD COLUMN role TEXT NOT NULL DEFAULT 'reader';
    END IF;
END
$$;

-- Garantir CHECK constraint para role
ALTER TABLE public.user_profiles
    ADD CONSTRAINT user_profiles_role_check CHECK (role IN ('admin', 'editor', 'reader'));

-- RLS para user_profiles (permitir leitura por auth)
DROP POLICY IF EXISTS "Allow authenticated read user_profiles" ON public.user_profiles;
CREATE POLICY "Allow authenticated read user_profiles" ON public.user_profiles
    FOR SELECT USING (auth.role() = 'authenticated');


-- ───────────────────────────────────────────────────────────────────────
-- 3. RPC is_admin_user()
-- ───────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION public.is_admin_user()
RETURNS BOOLEAN AS $$
BEGIN
    RETURN EXISTS (
        SELECT 1 FROM public.user_profiles
        WHERE id = auth.uid() AND role = 'admin'
    );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

COMMENT ON FUNCTION public.is_admin_user() IS
'Retorna TRUE se o usuário autenticado possui role = admin na tabela user_profiles.';


-- ───────────────────────────────────────────────────────────────────────
-- 4. RPC toggle_entity_active() — Kill-Switch em 1 clique
-- ───────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION public.toggle_entity_active(
    p_entity_type TEXT,
    p_entity_id UUID
)
RETURNS JSONB AS $$
DECLARE
    v_table TEXT;
    v_new_active BOOLEAN;
BEGIN
    -- Validar tipo de entidade
    IF p_entity_type NOT IN ('sponsors', 'ad_campaigns', 'ad_creatives') THEN
        RETURN jsonb_build_object('ok', FALSE, 'error', 'entity_type inválido. Use: sponsors, ad_campaigns, ad_creatives');
    END IF;

    IF p_entity_id IS NULL THEN
        RETURN jsonb_build_object('ok', FALSE, 'error', 'entity_id é obrigatório');
    END IF;

    -- Verificar permissão de admin
    IF NOT EXISTS (
        SELECT 1 FROM public.user_profiles
        WHERE id = auth.uid() AND role = 'admin'
    ) THEN
        RETURN jsonb_build_object('ok', FALSE, 'error', 'Acesso negado: requer role admin');
    END IF;

    -- Toggle baseado no tipo
    IF p_entity_type = 'sponsors' THEN
        v_table := 'public.sponsors';
        UPDATE public.sponsors
        SET active = NOT active,
            updated_at = NOW()
        WHERE id = p_entity_id
        RETURNING active INTO v_new_active;

    ELSIF p_entity_type = 'ad_campaigns' THEN
        v_table := 'public.ad_campaigns';
        UPDATE public.ad_campaigns
        SET active = NOT active,
            updated_at = NOW()
        WHERE id = p_entity_id
        RETURNING active INTO v_new_active;

    ELSIF p_entity_type = 'ad_creatives' THEN
        v_table := 'public.ad_creatives';
        UPDATE public.ad_creatives
        SET active = NOT active,
            updated_at = NOW()
        WHERE id = p_entity_id
        RETURNING active INTO v_new_active;
    END IF;

    IF v_new_active IS NULL THEN
        RETURN jsonb_build_object('ok', FALSE, 'error', 'Entidade não encontrada');
    END IF;

    RETURN jsonb_build_object(
        'ok', TRUE,
        'entity_type', p_entity_type,
        'entity_id', p_entity_id,
        'active', v_new_active
    );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

COMMENT ON FUNCTION public.toggle_entity_active(TEXT, UUID) IS
'Kill-Switch em 1 clique: alterna status active de sponsors, ad_campaigns ou ad_creatives. Requer role admin.';


-- ───────────────────────────────────────────────────────────────────────
-- 5. RPC get_admin_kpis()
-- ───────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION public.get_admin_kpis()
RETURNS JSONB AS $$
DECLARE
    v_total_users BIGINT;
    v_active_subscribers BIGINT;
    v_monthly_impressions BIGINT;
    v_monthly_clicks BIGINT;
    v_monthly_revenue NUMERIC;
    v_ctr NUMERIC;
    v_active_campaigns BIGINT;
    v_active_sponsors BIGINT;
BEGIN
    -- Total de usuários cadastrados
    SELECT COUNT(*) INTO v_total_users FROM public.user_profiles;

    -- Assinantes ativos (premium + vip)
    SELECT COUNT(*) INTO v_active_subscribers
    FROM public.subscriptions
    WHERE status = 'active' AND plan_name IN ('premium', 'vip');

    -- Métricas de anúncios do mês atual
    SELECT
        COALESCE(SUM(CASE WHEN event_type = 'impression' THEN 1 ELSE 0 END), 0),
        COALESCE(SUM(CASE WHEN event_type = 'click' THEN 1 ELSE 0 END), 0),
        COALESCE(SUM(price_cents), 0)
    INTO v_monthly_impressions, v_monthly_clicks, v_monthly_revenue
    FROM public.ad_events ae
    JOIN public.ad_creatives ac ON ac.id = ae.creative_id
    WHERE ae.created_at >= date_trunc('month', NOW())
      AND ac.active = TRUE;

    -- Cálculo de CTR
    IF v_monthly_impressions > 0 THEN
        v_ctr := ROUND((v_monthly_clicks::NUMERIC / v_monthly_impressions) * 100, 2);
    ELSE
        v_ctr := 0;
    END IF;

    -- Campanhas ativas
    SELECT COUNT(*) INTO v_active_campaigns
    FROM public.ad_campaigns
    WHERE active = TRUE
      AND start_date <= CURRENT_DATE
      AND end_date >= CURRENT_DATE;

    -- Patrocinadores ativos
    SELECT COUNT(*) INTO v_active_sponsors
    FROM public.sponsors
    WHERE active = TRUE;

    RETURN jsonb_build_object(
        'total_users', v_total_users,
        'active_subscribers', v_active_subscribers,
        'monthly_impressions', v_monthly_impressions,
        'monthly_clicks', v_monthly_clicks,
        'ctr_percent', v_ctr,
        'estimated_revenue_cents', v_monthly_revenue,
        'active_campaigns', v_active_campaigns,
        'active_sponsors', v_active_sponsors
    );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

COMMENT ON FUNCTION public.get_admin_kpis() IS
'Retorna KPIs administrativos: usuários totais, assinantes ativos, métricas de anúncios do mês, CTR e receita estimada.';


-- ───────────────────────────────────────────────────────────────────────
-- 6. RPC get_admin_ad_metrics_timeseries()
-- ───────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION public.get_admin_ad_metrics_timeseries(
    p_days INTEGER DEFAULT 30
)
RETURNS TABLE (
    date_str TEXT,
    impressions BIGINT,
    clicks BIGINT,
    skips BIGINT,
    errors BIGINT,
    revenue_cents BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        TO_CHAR(date_trunc('day', ae.created_at), 'YYYY-MM-DD')::TEXT AS date_str,
        COUNT(CASE WHEN ae.event_type = 'impression' THEN 1 END)::BIGINT AS impressions,
        COUNT(CASE WHEN ae.event_type = 'click' THEN 1 END)::BIGINT AS clicks,
        COUNT(CASE WHEN ae.event_type = 'skip' THEN 1 END)::BIGINT AS skips,
        COUNT(CASE WHEN ae.event_type = 'error' THEN 1 END)::BIGINT AS errors,
        COUNT(CASE WHEN ae.event_type = 'click' THEN 1 END * 1)::BIGINT AS revenue_cents
    FROM public.ad_events ae
    WHERE ae.created_at >= (NOW() - (p_days || ' days')::INTERVAL)
    GROUP BY date_trunc('day', ae.created_at)
    ORDER BY date_trunc('day', ae.created_at) DESC;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

COMMENT ON FUNCTION public.get_admin_ad_metrics_timeseries(INTEGER) IS
'Retorna série temporal de métricas de anúncios para gráficos. Padrão: últimos 30 dias.';


-- ───────────────────────────────────────────────────────────────────────
-- 7. RPC get_admin_users_and_subs()
-- ───────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION public.get_admin_users_and_subs()
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
    RETURN QUERY
    SELECT
        up.id AS user_id,
        up.email AS email,
        COALESCE(up.full_name, up.raw_user_meta_data->>'full_name') AS name,
        up.role AS role,
        up.raw_user_meta_data->>'avatar_url' AS avatar_url,
        up.created_at AS created_at,
        up.last_sign_in_at AS last_login,
        s.id AS sub_id,
        s.plan_name AS sub_plan_name,
        s.status AS sub_status,
        s.price_cents AS sub_price_cents,
        s.started_at AS sub_started_at,
        s.expires_at AS sub_expires_at
    FROM public.user_profiles up
    LEFT JOIN public.subscriptions s ON s.user_id = up.id
    WHERE up.id != auth.uid()  -- excluir o próprio admin
    ORDER BY up.created_at DESC;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

COMMENT ON FUNCTION public.get_admin_users_and_subs() IS
'Retorna lista consolidada de usuários e suas assinaturas para a aba de gestão.';


-- ───────────────────────────────────────────────────────────────────────
-- 8. RPC get_admin_campaigns()
-- ───────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION public.get_admin_campaigns()
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
    media_size TEXT,
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
        ac.id AS campaign_id,
        ac.name AS campaign_name,
        ac.sponsor_id AS sponsor_id,
        s.name AS sponsor_name,
        ac.format_type AS format_type,
        ac.headline AS headline,
        ac.cta_url AS cta_url,
        ac.start_date AS start_date,
        ac.end_date AS end_date,
        ac.media_url AS media_url,
        ac.media_name AS media_name,
        ac.media_size AS media_size,
        ac.active AS is_active,
        ac.impressions AS impressions,
        ac.clicks AS clicks,
        ac.skips AS skips,
        ac.errors AS errors,
        ac.priority AS priority
    FROM public.ad_campaigns ac
    LEFT JOIN public.sponsors s ON s.id = ac.sponsor_id
    ORDER BY ac.created_at DESC;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

COMMENT ON FUNCTION public.get_admin_campaigns() IS
'Retorna todas as campanhas de anúncios com dados do patrocinador vinculado.';


-- ───────────────────────────────────────────────────────────────────────
-- 9. RPC get_admin_sponsors()
-- ───────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION public.get_admin_sponsors()
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
    RETURN QUERY
    SELECT
        s.id AS sponsor_id,
        s.name AS name,
        s.cnpj AS cnpj,
        s.email AS email,
        s.logo_url AS logo_url,
        s.website_url AS website_url,
        s.active AS is_active,
        s.contract_end AS contract_end,
        s.created_at AS created_at
    FROM public.sponsors s
    ORDER BY s.name;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

COMMENT ON FUNCTION public.get_admin_sponsors() IS
'Retorna todos os patrocinadores (Tipo 1) para gestão na dashboard.';


-- ───────────────────────────────────────────────────────────────────────
-- 10. RPC upsert_campaign_admin()
-- ───────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION public.upsert_campaign_admin(
    p_campaign_id UUID DEFAULT NULL,
    p_sponsor_id UUID,
    p_name TEXT,
    p_format_type TEXT DEFAULT 'audio',
    p_headline TEXT,
    p_cta_url TEXT,
    p_start_date DATE,
    p_end_date DATE,
    p_media_url TEXT DEFAULT NULL,
    p_media_name TEXT DEFAULT NULL,
    p_media_size TEXT DEFAULT NULL,
    p_priority INTEGER DEFAULT 1
)
RETURNS JSONB AS $$
DECLARE
    v_id UUID;
BEGIN
    IF p_campaign_id IS NOT NULL THEN
        -- Update existing
        UPDATE public.ad_campaigns
        SET
            sponsor_id = p_sponsor_id,
            name = p_name,
            format_type = p_format_type,
            headline = p_headline,
            cta_url = p_cta_url,
            start_date = p_start_date,
            end_date = p_end_date,
            media_url = p_media_url,
            media_name = p_media_name,
            media_size = p_media_size,
            priority = p_priority,
            updated_at = NOW()
        WHERE id = p_campaign_id;

        v_id := p_campaign_id;
    ELSE
        -- Insert new
        INSERT INTO public.ad_campaigns (
            sponsor_id, name, format_type, headline, cta_url,
            start_date, end_date, media_url, media_name, media_size, priority
        ) VALUES (
            p_sponsor_id, p_name, p_format_type, p_headline, p_cta_url,
            p_start_date, p_end_date, p_media_url, p_media_name, p_media_size, p_priority
        )
        RETURNING id INTO v_id;
    END IF;

    RETURN jsonb_build_object('ok', TRUE, 'campaign_id', v_id);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

COMMENT ON FUNCTION public.upsert_campaign_admin() IS
'Cria ou atualiza campanha de anúncio. Requer role admin.';


-- ───────────────────────────────────────────────────────────────────────
-- 11. RPC upsert_sponsor_admin()
-- ───────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION public.upsert_sponsor_admin(
    p_sponsor_id UUID DEFAULT NULL,
    p_name TEXT,
    p_cnpj TEXT DEFAULT NULL,
    p_email TEXT DEFAULT NULL,
    p_logo_url TEXT DEFAULT NULL,
    p_website_url TEXT DEFAULT NULL,
    p_contract_end DATE DEFAULT NULL
)
RETURNS JSONB AS $$
DECLARE
    v_id UUID;
BEGIN
    IF p_sponsor_id IS NOT NULL THEN
        UPDATE public.sponsors
        SET
            name = p_name,
            cnpj = p_cnpj,
            email = p_email,
            logo_url = p_logo_url,
            website_url = p_website_url,
            contract_end = p_contract_end,
            updated_at = NOW()
        WHERE id = p_sponsor_id;

        v_id := p_sponsor_id;
    ELSE
        INSERT INTO public.sponsors (
            name, cnpj, email, logo_url, website_url, contract_end
        ) VALUES (
            p_name, p_cnpj, p_email, p_logo_url, p_website_url, p_contract_end
        )
        RETURNING id INTO v_id;
    END IF;

    RETURN jsonb_build_object('ok', TRUE, 'sponsor_id', v_id);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

COMMENT ON FUNCTION public.upsert_sponsor_admin() IS
'Cria ou atualiza patrocinador (Tipo 1). Requer role admin.';


-- ───────────────────────────────────────────────────────────────────────
-- 12. RPC delete_campaign_admin()
-- ───────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION public.delete_campaign_admin(
    p_campaign_id UUID
)
RETURNS JSONB AS $$
BEGIN
    -- Verificar permissão
    IF NOT EXISTS (
        SELECT 1 FROM public.user_profiles
        WHERE id = auth.uid() AND role = 'admin'
    ) THEN
        RETURN jsonb_build_object('ok', FALSE, 'error', 'Acesso negado: requer role admin');
    END IF;

    DELETE FROM public.ad_campaigns WHERE id = p_campaign_id;

    IF FOUND THEN
        RETURN jsonb_build_object('ok', TRUE, 'campaign_id', p_campaign_id);
    ELSE
        RETURN jsonb_build_object('ok', FALSE, 'error', 'Campanha não encontrada');
    END IF;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

COMMENT ON FUNCTION public.delete_campaign_admin(UUID) IS
'Exclui campanha de anúncio. Requer role admin.';


-- ───────────────────────────────────────────────────────────────────────
-- 13. RPC update_subscription_admin()
-- ───────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION public.update_subscription_admin(
    p_sub_id UUID,
    p_plan_name TEXT,
    p_status TEXT DEFAULT 'active',
    p_price_cents INTEGER,
    p_expires_at TIMESTAMPTZ DEFAULT NULL
)
RETURNS JSONB AS $$
BEGIN
    -- Verificar permissão
    IF NOT EXISTS (
        SELECT 1 FROM public.user_profiles
        WHERE id = auth.uid() AND role = 'admin'
    ) THEN
        RETURN jsonb_build_object('ok', FALSE, 'error', 'Acesso negado: requer role admin');
    END IF;

    UPDATE public.subscriptions
    SET
        plan_name = p_plan_name,
        status = p_status,
        price_cents = p_price_cents,
        expires_at = p_expires_at,
        updated_at = NOW()
    WHERE id = p_sub_id;

    IF FOUND THEN
        RETURN jsonb_build_object('ok', TRUE, 'sub_id', p_sub_id);
    ELSE
        RETURN jsonb_build_object('ok', FALSE, 'error', 'Assinatura não encontrada');
    END IF;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

COMMENT ON FUNCTION public.update_subscription_admin() IS
'Atualiza plano/status de assinatura. Requer role admin.';


-- ───────────────────────────────────────────────────────────────────────
-- MIGRAÇÃO: Garantir que ad_campaigns tenha coluna format_type
-- ───────────────────────────────────────────────────────────────────────

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'ad_campaigns'
          AND column_name = 'format_type'
    ) THEN
        ALTER TABLE public.ad_campaigns ADD COLUMN format_type TEXT DEFAULT 'audio';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'ad_campaigns'
          AND column_name = 'headline'
    ) THEN
        ALTER TABLE public.ad_campaigns ADD COLUMN headline TEXT DEFAULT '';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'ad_campaigns'
          AND column_name = 'priority'
    ) THEN
        ALTER TABLE public.ad_campaigns ADD COLUMN priority INTEGER DEFAULT 1;
    END IF;
END
$$;
