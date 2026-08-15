-- LGPD: consentimento + exclusão. Nomes reais: listen_events.identity_ref, listen_sessions.

CREATE TABLE IF NOT EXISTS public.user_consent (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id               UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    fingerprint_hash      TEXT,
    essential_accepted_at TIMESTAMPTZ,
    plan_at_consent       TEXT CHECK (plan_at_consent IN ('free', 'premium', 'vip')),
    adsense_active        BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS user_consent_user_uidx
    ON public.user_consent (user_id) WHERE user_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS user_consent_fp_uidx
    ON public.user_consent (fingerprint_hash) WHERE fingerprint_hash IS NOT NULL;

COMMENT ON TABLE public.user_consent IS
    'Consentimento essencial. adsense_active deriva do plano (free=true; premium/vip=false). Sem toggle grátis.';

ALTER TABLE public.user_consent ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS user_consent_own ON public.user_consent;
CREATE POLICY user_consent_own ON public.user_consent
    FOR ALL USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

CREATE OR REPLACE FUNCTION public.get_my_plan()
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    uid UUID := auth.uid();
    v_plan TEXT;
BEGIN
    IF uid IS NULL THEN
        RETURN jsonb_build_object('logged_in', FALSE, 'plan', 'free');
    END IF;
    SELECT s.plan_name INTO v_plan
    FROM public.subscriptions s
    WHERE s.user_id = uid
      AND s.status = 'active'
      AND (s.expires_at IS NULL OR s.expires_at > NOW())
    ORDER BY CASE s.plan_name WHEN 'vip' THEN 3 WHEN 'premium' THEN 2 ELSE 1 END DESC
    LIMIT 1;
    RETURN jsonb_build_object(
        'logged_in', TRUE,
        'plan', COALESCE(v_plan, 'free')
    );
END;
$$;

GRANT EXECUTE ON FUNCTION public.get_my_plan() TO anon, authenticated;

CREATE OR REPLACE FUNCTION public.fn_record_consent(p_fingerprint TEXT DEFAULT NULL)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    uid UUID := auth.uid();
    v_plan TEXT := 'free';
    v_ads BOOLEAN := TRUE;
    v_fp TEXT;
BEGIN
    SELECT COALESCE((public.get_my_plan()->>'plan'), 'free') INTO v_plan;
    v_ads := (v_plan = 'free');
    v_fp := NULLIF(trim(COALESCE(p_fingerprint, '')), '');

    IF uid IS NOT NULL THEN
        UPDATE public.user_consent SET
            fingerprint_hash = COALESCE(v_fp, fingerprint_hash),
            essential_accepted_at = COALESCE(essential_accepted_at, NOW()),
            plan_at_consent = v_plan,
            adsense_active = v_ads,
            updated_at = NOW()
        WHERE user_id = uid;
        IF NOT FOUND THEN
            INSERT INTO public.user_consent (
                user_id, fingerprint_hash, essential_accepted_at,
                plan_at_consent, adsense_active, updated_at
            ) VALUES (uid, v_fp, NOW(), v_plan, v_ads, NOW());
        END IF;
    ELSIF v_fp IS NOT NULL THEN
        UPDATE public.user_consent SET
            essential_accepted_at = COALESCE(essential_accepted_at, NOW()),
            plan_at_consent = v_plan,
            adsense_active = v_ads,
            updated_at = NOW()
        WHERE fingerprint_hash = v_fp;
        IF NOT FOUND THEN
            INSERT INTO public.user_consent (
                fingerprint_hash, essential_accepted_at,
                plan_at_consent, adsense_active, updated_at
            ) VALUES (v_fp, NOW(), v_plan, v_ads, NOW());
        END IF;
    ELSE
        RETURN jsonb_build_object('ok', FALSE, 'error', 'sem identidade');
    END IF;

    RETURN jsonb_build_object('ok', TRUE, 'plan', v_plan, 'adsense_active', v_ads);
END;
$$;

GRANT EXECUTE ON FUNCTION public.fn_record_consent(TEXT) TO anon, authenticated;

CREATE OR REPLACE FUNCTION public.delete_user_tracking_data(
    target_id TEXT,
    is_fingerprint BOOLEAN DEFAULT FALSE
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    uid UUID := auth.uid();
    v_fp TEXT;
    v_uid UUID;
    n_events INT := 0;
    n_sess INT := 0;
    n_fb INT := 0;
    n_consent INT := 0;
BEGIN
    IF is_fingerprint THEN
        v_fp := NULLIF(trim(COALESCE(target_id, '')), '');
        IF v_fp IS NULL THEN
            RETURN jsonb_build_object('ok', FALSE, 'error', 'fingerprint vazio');
        END IF;
        IF position('c:' IN v_fp) <> 1 AND length(v_fp) >= 32 THEN
            v_fp := 'c:' || v_fp;
        END IF;
        DELETE FROM public.listen_events WHERE identity_ref = v_fp;
        GET DIAGNOSTICS n_events = ROW_COUNT;
        DELETE FROM public.listen_sessions WHERE identity_ref = v_fp;
        GET DIAGNOSTICS n_sess = ROW_COUNT;
        DELETE FROM public.anonymous_feedback WHERE identity_ref = v_fp;
        GET DIAGNOSTICS n_fb = ROW_COUNT;
        DELETE FROM public.user_consent
         WHERE fingerprint_hash IN (target_id, v_fp, replace(v_fp, 'c:', ''));
        GET DIAGNOSTICS n_consent = ROW_COUNT;
    ELSE
        BEGIN
            v_uid := target_id::uuid;
        EXCEPTION WHEN others THEN
            RETURN jsonb_build_object('ok', FALSE, 'error', 'user_id inválido');
        END;
        IF uid IS NULL OR uid <> v_uid THEN
            RETURN jsonb_build_object('ok', FALSE, 'error', 'só a própria conta');
        END IF;
        UPDATE public.listen_events
           SET user_id = NULL
         WHERE user_id = v_uid;
        GET DIAGNOSTICS n_events = ROW_COUNT;
        UPDATE public.listen_sessions
           SET user_id = NULL
         WHERE user_id = v_uid;
        GET DIAGNOSTICS n_sess = ROW_COUNT;
        DELETE FROM public.episode_progress WHERE user_id = v_uid;
        DELETE FROM public.listening_history WHERE user_id = v_uid;
        DELETE FROM public.user_consent WHERE user_id = v_uid;
        GET DIAGNOSTICS n_consent = ROW_COUNT;
    END IF;

    RETURN jsonb_build_object(
        'ok', TRUE,
        'listen_events', n_events,
        'listen_sessions', n_sess,
        'anonymous_feedback', n_fb,
        'consent', n_consent
    );
END;
$$;

COMMENT ON FUNCTION public.delete_user_tracking_data(TEXT, BOOLEAN) IS
    'LGPD: apaga/anonimiza tracking. Fingerprint livre (hash local). Conta só se auth.uid()=alvo.';

GRANT EXECUTE ON FUNCTION public.delete_user_tracking_data(TEXT, BOOLEAN) TO anon, authenticated;
