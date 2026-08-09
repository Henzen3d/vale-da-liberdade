-- 12_monetization_adsense.sql
-- Tabela de configuração de monetização via Google AdSense
-- Aplicar via: docker exec -i <container> psql -U postgres -d <db> < scripts/12_monetization_adsense.sql

-- ─── 1. Tabela ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.monetization_config (
  id              INT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  adsense_enabled BOOLEAN NOT NULL DEFAULT FALSE,
  adsense_client_id TEXT NOT NULL DEFAULT '',
  feed_slot_id    TEXT NOT NULL DEFAULT '',
  sidebar_slot_id TEXT NOT NULL DEFAULT '',
  fallback_adsense BOOLEAN NOT NULL DEFAULT FALSE,
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── 2. RLS ───────────────────────────────────────────────────────────────────
ALTER TABLE public.monetization_config ENABLE ROW LEVEL SECURITY;

-- Leitura pública (anon pode consultar)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename  = 'monetization_config'
      AND policyname = 'monetization_config_select_anon'
  ) THEN
    CREATE POLICY monetization_config_select_anon
      ON public.monetization_config
      FOR SELECT
      TO anon
      USING (true);
  END IF;
END$$;

-- ─── 3. Seed inicial ──────────────────────────────────────────────────────────
INSERT INTO public.monetization_config (id, adsense_enabled, adsense_client_id, feed_slot_id, sidebar_slot_id, fallback_adsense)
VALUES (1, FALSE, '', '', '', FALSE)
ON CONFLICT (id) DO NOTHING;

-- ─── 4. RPC pública: fn_get_monetization_config ───────────────────────────────
CREATE OR REPLACE FUNCTION public.fn_get_monetization_config()
RETURNS TABLE(
  adsense_enabled   BOOLEAN,
  adsense_client_id TEXT,
  feed_slot_id      TEXT,
  sidebar_slot_id   TEXT,
  fallback_adsense  BOOLEAN
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  RETURN QUERY
    SELECT
      mc.adsense_enabled,
      mc.adsense_client_id,
      mc.feed_slot_id,
      mc.sidebar_slot_id,
      mc.fallback_adsense
    FROM public.monetization_config mc
    WHERE mc.id = 1;
END;
$$;

GRANT EXECUTE ON FUNCTION public.fn_get_monetization_config() TO anon, authenticated;

-- ─── 5. RPC admin: get_admin_monetization_config ─────────────────────────────
CREATE OR REPLACE FUNCTION public.get_admin_monetization_config()
RETURNS TABLE(
  id                INT,
  adsense_enabled   BOOLEAN,
  adsense_client_id TEXT,
  feed_slot_id      TEXT,
  sidebar_slot_id   TEXT,
  fallback_adsense  BOOLEAN,
  updated_at        TIMESTAMPTZ
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  IF NOT public.is_admin_user() THEN
    RAISE EXCEPTION 'Acesso negado: requer role admin';
  END IF;

  RETURN QUERY
    SELECT
      mc.id,
      mc.adsense_enabled,
      mc.adsense_client_id,
      mc.feed_slot_id,
      mc.sidebar_slot_id,
      mc.fallback_adsense,
      mc.updated_at
    FROM public.monetization_config mc
    WHERE mc.id = 1;
END;
$$;

GRANT EXECUTE ON FUNCTION public.get_admin_monetization_config() TO authenticated;

-- ─── 6. RPC admin: upsert_admin_monetization_config ──────────────────────────
CREATE OR REPLACE FUNCTION public.upsert_admin_monetization_config(
  p_adsense_enabled   BOOLEAN,
  p_adsense_client_id TEXT,
  p_feed_slot_id      TEXT,
  p_sidebar_slot_id   TEXT,
  p_fallback_adsense  BOOLEAN DEFAULT FALSE
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  IF NOT public.is_admin_user() THEN
    RAISE EXCEPTION 'Acesso negado: requer role admin';
  END IF;

  INSERT INTO public.monetization_config (
    id, adsense_enabled, adsense_client_id, feed_slot_id, sidebar_slot_id, fallback_adsense, updated_at
  ) VALUES (
    1, p_adsense_enabled, p_adsense_client_id, p_feed_slot_id, p_sidebar_slot_id, p_fallback_adsense, NOW()
  )
  ON CONFLICT (id) DO UPDATE SET
    adsense_enabled   = EXCLUDED.adsense_enabled,
    adsense_client_id = EXCLUDED.adsense_client_id,
    feed_slot_id      = EXCLUDED.feed_slot_id,
    sidebar_slot_id   = EXCLUDED.sidebar_slot_id,
    fallback_adsense  = EXCLUDED.fallback_adsense,
    updated_at        = NOW();

  RETURN jsonb_build_object('ok', true);
END;
$$;

GRANT EXECUTE ON FUNCTION public.upsert_admin_monetization_config(BOOLEAN, TEXT, TEXT, TEXT, BOOLEAN) TO authenticated;
