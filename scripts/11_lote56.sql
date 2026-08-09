-- LOTE 5 + LOTE 6 — Vale da Liberdade (aplicar via docker exec supabase-db)
-- 2026-08-07
--
-- LOTE 5:
--   (nada de SQL — apenas frontend: meta dinâmica, skip mobile, favoritos no
--   drawer, manchetes accordion, fim do polling)
--
-- LOTE 6:
--   6.3  RPCs de ads (fn_get_active_ad / fn_record_ad_event) + RLS anon
--   3.3  Tabela user_saved_episodes ("Ouvir depois" sync) com RLS por usuário

-- ── 6.3: Ads dinâmicos via Supabase ─────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.fn_get_active_ad(p_format text DEFAULT 'audio')
RETURNS jsonb
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT jsonb_build_object(
    'creative_id', c.id,
    'campaign_id', camp.id,
    'media_type', c.media_type,
    'media_url', c.media_url,
    'audio_url', c.audio_url,
    'click_url', c.click_url,
    'alt_text', c.alt_text,
    'advertiser_name', camp.advertiser_name,
    'headline', camp.headline,
    'format_type', camp.format_type,
    'skip_after_seconds', camp.skip_after_seconds
  )
  FROM ad_creatives c
  JOIN ad_campaigns camp ON camp.id = c.campaign_id
  WHERE c.active = true
    AND camp.active = true
    AND camp.start_date <= CURRENT_DATE
    AND camp.end_date >= CURRENT_DATE
    AND (p_format IS NULL OR camp.format_type = p_format)
  ORDER BY camp.priority DESC, c.weight DESC, random()
  LIMIT 1
$$;

CREATE OR REPLACE FUNCTION public.fn_record_ad_event(
  p_creative_id uuid,
  p_campaign_id uuid,
  p_event_type text,
  p_session_id text DEFAULT NULL
)
RETURNS boolean
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
AS $$
  INSERT INTO ad_events (creative_id, campaign_id, event_type, session_id)
  VALUES (p_creative_id, p_campaign_id, p_event_type, p_session_id)
  RETURNING true
$$;

GRANT EXECUTE ON FUNCTION public.fn_get_active_ad(text) TO anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_record_ad_event(uuid, uuid, text, text) TO anon, authenticated;

DROP POLICY IF EXISTS "anon_read_active_ads" ON public.ad_creatives;
CREATE POLICY "anon_read_active_ads" ON public.ad_creatives
  FOR SELECT TO anon USING (active = true);
DROP POLICY IF EXISTS "anon_read_active_campaigns" ON public.ad_campaigns;
CREATE POLICY "anon_read_active_campaigns" ON public.ad_campaigns
  FOR SELECT TO anon USING (active = true);

-- ── 3.3: "Ouvir depois" com sync (tabela espelho de user_favorites) ─────────
CREATE TABLE IF NOT EXISTS public.user_saved_episodes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  episode_date text NOT NULL,
  title text,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, episode_date)
);

ALTER TABLE public.user_saved_episodes ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "saved insert own" ON public.user_saved_episodes;
CREATE POLICY "saved insert own" ON public.user_saved_episodes
  FOR INSERT WITH CHECK (auth.uid() = user_id);
DROP POLICY IF EXISTS "saved delete own" ON public.user_saved_episodes;
CREATE POLICY "saved delete own" ON public.user_saved_episodes
  FOR DELETE USING (auth.uid() = user_id);
DROP POLICY IF EXISTS "saved select own" ON public.user_saved_episodes;
CREATE POLICY "saved select own" ON public.user_saved_episodes
  FOR SELECT USING (auth.uid() = user_id);
