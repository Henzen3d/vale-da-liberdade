-- ═══════════════════════════════════════════════════════════════════════
-- 06_create_user_by_admin.sql
-- RPC administrativa para criação de usuários pelo painel admin
--
-- Cria:
--   - create_user_by_admin(p_email, p_password, p_full_name, p_role, p_plan_name)
--
-- Por que via RPC (SECURITY DEFINER) e não supabase.auth.signUp no client?
--   * signUp no painel logado trocava a sessão do admin (deslogava);
--   * a chave service_role não pode ir para o frontend.
-- A função roda como owner (postgres), insere direto em auth.users com
-- hash bcrypt, e o trigger on_auth_user_created cria o user_profiles.
--
-- Executar no SQL Editor do Supabase Studio (idempotente)
-- ═══════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION public.create_user_by_admin(
    p_email     TEXT,
    p_password  TEXT            DEFAULT NULL,
    p_full_name TEXT            DEFAULT NULL,
    p_role      TEXT            DEFAULT 'reader',
    p_plan_name TEXT            DEFAULT 'free'
)
RETURNS JSONB AS $$
DECLARE
    v_user_id    UUID;
    v_email      TEXT;
    v_price      INTEGER;
    v_expires_at TIMESTAMPTZ;
    v_pwd_hash   TEXT;
BEGIN
    -- ── 1. Validação de permissão (somente admin) ────────────────────
    IF NOT public.is_admin_user() THEN
        RETURN jsonb_build_object(
            'ok', FALSE,
            'error', 'Acesso negado: apenas administradores podem criar usuários.'
        );
    END IF;

    -- ── 2. Validação de parâmetros ───────────────────────────────────
    v_email := lower(trim(COALESCE(p_email, '')));

    IF v_email = '' OR position('@' in v_email) < 2 THEN
        RETURN jsonb_build_object('ok', FALSE, 'error', 'Email inválido ou ausente.');
    END IF;

    IF p_role NOT IN ('reader', 'editor', 'admin') THEN
        RETURN jsonb_build_object('ok', FALSE, 'error', 'Role inválida. Use: reader, editor ou admin.');
    END IF;

    IF p_plan_name NOT IN ('free', 'premium', 'vip') THEN
        RETURN jsonb_build_object('ok', FALSE, 'error', 'Plano inválido. Use: free, premium ou vip.');
    END IF;

    IF p_password IS NOT NULL AND trim(p_password) <> '' AND length(trim(p_password)) < 6 THEN
        RETURN jsonb_build_object('ok', FALSE, 'error', 'A senha deve ter pelo menos 6 caracteres.');
    END IF;

    -- Email já cadastrado?
    IF EXISTS (SELECT 1 FROM auth.users WHERE lower(email) = v_email) THEN
        RETURN jsonb_build_object('ok', FALSE, 'error', 'Email já cadastrado: ' || v_email);
    END IF;

    -- ── 3. Hash da senha (bcrypt) ou NULL (login via recuperação) ────
    IF p_password IS NOT NULL AND trim(p_password) <> '' THEN
        v_pwd_hash := extensions.crypt(trim(p_password), extensions.gen_salt('bf', 8));
    ELSE
        v_pwd_hash := NULL;
    END IF;

    -- ── 4. Inserir em auth.users ─────────────────────────────────────
    -- O trigger on_auth_user_created cria o registro em user_profiles.
    -- IMPORTANTE: todos os campos de token devem ser '' (não NULL),
    -- pois o GoTrue faz scan como string não-nula (NULL causa 500 no login).
    INSERT INTO auth.users (
        instance_id, id, aud, role, email, encrypted_password,
        email_confirmed_at, confirmation_sent_at,
        last_sign_in_at, raw_app_meta_data, raw_user_meta_data,
        is_super_admin, created_at, updated_at,
        confirmation_token, recovery_token,
        email_change_token_new, email_change_token_current, email_change,
        phone, phone_change, phone_change_token,
        reauthentication_token,
        is_sso_user, is_anonymous
    ) VALUES (
        '00000000-0000-0000-0000-000000000000',
        gen_random_uuid(),
        'authenticated',
        'authenticated',
        v_email,
        v_pwd_hash,
        NOW(),                     -- email já confirmado (criado pelo admin)
        NOW(),
        NULL,
        jsonb_build_object('provider', 'email', 'providers', jsonb_build_array('email')),
        jsonb_build_object('full_name', COALESCE(p_full_name, '')),
        FALSE,
        NOW(), NOW(),
        '', '', '', '', '',
        NULL, '', '',
        '',
        FALSE, FALSE
    )
    RETURNING id INTO v_user_id;

    -- ── 5. Aplicar role solicitada no user_profiles ──────────────────
    UPDATE public.user_profiles
       SET role = p_role,
           full_name = COALESCE(NULLIF(trim(p_full_name), ''), full_name),
           updated_at = NOW()
     WHERE id = v_user_id;

    -- ── 6. Criar assinatura inicial ──────────────────────────────────
    v_price := CASE p_plan_name
                   WHEN 'premium' THEN 2990
                   WHEN 'vip'     THEN 4990
                   ELSE 0
               END;
    v_expires_at := CASE p_plan_name
                        WHEN 'premium' THEN NOW() + INTERVAL '30 days'
                        WHEN 'vip'     THEN NOW() + INTERVAL '365 days'
                        ELSE NULL
                    END;

    INSERT INTO public.subscriptions (user_id, email, plan_name, status, price_cents, started_at, expires_at)
    VALUES (v_user_id, v_email, p_plan_name, 'active', v_price, NOW(), v_expires_at);

    RETURN jsonb_build_object(
        'ok', TRUE,
        'user_id', v_user_id,
        'email', v_email,
        'role', p_role,
        'plan', p_plan_name,
        'has_password', v_pwd_hash IS NOT NULL,
        'message', CASE
                       WHEN v_pwd_hash IS NOT NULL
                       THEN 'Usuário criado com sucesso (login por email/senha habilitado).'
                       ELSE 'Usuário criado sem senha: ele deverá usar "Esqueci minha senha" para definir uma.'
                   END
    );

EXCEPTION
    WHEN unique_violation THEN
        RETURN jsonb_build_object('ok', FALSE, 'error', 'Email já cadastrado: ' || v_email);
    WHEN OTHERS THEN
        RETURN jsonb_build_object('ok', FALSE, 'error', 'Falha ao criar usuário: ' || SQLERRM);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

COMMENT ON FUNCTION public.create_user_by_admin(TEXT, TEXT, TEXT, TEXT, TEXT) IS
'Cria usuário (auth.users + user_profiles + subscriptions) a partir do painel admin. Requer role admin. Senha opcional: se omitida, o usuário define via recuperação de senha.';

-- Permissões (mesmo padrão das demais RPCs admin; execução sem JWT de admin retorna erro)
GRANT EXECUTE ON FUNCTION public.create_user_by_admin(TEXT, TEXT, TEXT, TEXT, TEXT) TO anon;
GRANT EXECUTE ON FUNCTION public.create_user_by_admin(TEXT, TEXT, TEXT, TEXT, TEXT) TO authenticated;
GRANT EXECUTE ON FUNCTION public.create_user_by_admin(TEXT, TEXT, TEXT, TEXT, TEXT) TO service_role;
