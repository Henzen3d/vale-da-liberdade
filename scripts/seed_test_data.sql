-- Seed de Dados de Teste — Versão final
-- Criar users no auth.users (modo dev) e depois populou tabelas

-- ========================================
-- 0. CRIAR USERS NO AUTH.USERS
-- ========================================
INSERT INTO auth.users (
  instance_id, id, aud, role, email,
  encrypted_password, email_confirmed_at,
  recovery_sent_at, last_sign_in_at, raw_app_meta_data,
  raw_user_meta_data, created_at, updated_at
)
SELECT
  '00000000-0000-0000-0000-000000000000',
  gen_random_uuid(),
  'authenticated',
  'authenticated',
  'testuser' || gs || '@exemplo.com.br',
  encode(gen_random_bytes(32), 'base64'),
  now(),
  now(),
  now(),
  '{"provider":"email","providers":["email"]}',
  '{}',
  now(),
  now()
FROM generate_series(1, 20) AS gs
ON CONFLICT (id) DO NOTHING;

-- ========================================
-- 1. SPONSORS
-- ========================================
INSERT INTO public.sponsors (name, cnpj, email, logo_url, website_url, active, contract_end, notes)
VALUES
  ('TechCorp Brasil', '12.345.678/0001-95', 'contato@techcorp.com.br', 'data:image/svg+xml;utf8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%22150%22%20height%3D%2250%22%20viewBox%3D%220%200%20150%2050%22%3E%3Crect%20width%3D%22100%25%22%20height%3D%22100%25%22%20fill%3D%22%2310b981%22%2F%3E%3Ctext%20x%3D%2250%25%22%20y%3D%2250%25%22%20fill%3D%22%23ffffff%22%20dominant-baseline%3D%22middle%22%20text-anchor%3D%22middle%22%20font-family%3D%22sans-serif%22%20font-size%3D%2212%22%20font-weight%3D%22600%22%3ETech%3C%2Ftext%3E%3C%2Fsvg%3E', 'https://techcorp.com.br', true, '2027-03-01', 'Patrocinador principal'),
  ('Imobiliária Vale da Liberdade', '98.765.432/0001-10', 'comercial@valevalor.com.br', 'data:image/svg+xml;utf8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%22150%22%20height%3D%2250%22%20viewBox%3D%220%200%20150%2050%22%3E%3Crect%20width%3D%22100%25%22%20height%3D%22100%25%22%20fill%3D%22%233b82f6%22%2F%3E%3Ctext%20x%3D%2250%25%22%20y%3D%2250%25%22%20fill%3D%22%23ffffff%22%20dominant-baseline%3D%22middle%22%20text-anchor%3D%22middle%22%20font-family%3D%22sans-serif%22%20font-size%3D%2212%22%20font-weight%3D%22600%22%3EVale%3C%2Ftext%3E%3C%2Fsvg%3E', 'https://valevalor.com.br', true, '2026-12-31', 'Imobiliária local'),
  ('Supermercado Liberdade', '11.222.333/0001-44', 'faleconosco@superliberdade.com.br', 'data:image/svg+xml;utf8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%22150%22%20height%3D%2250%22%20viewBox%3D%220%200%20150%2050%22%3E%3Crect%20width%3D%22100%25%22%20height%3D%22100%25%22%20fill%3D%22%23f59e0b%22%2F%3E%3Ctext%20x%3D%2250%25%22%20y%3D%2250%25%22%20fill%3D%22%23ffffff%22%20dominant-baseline%3D%22middle%22%20text-anchor%3D%22middle%22%20font-family%3D%22sans-serif%22%20font-size%3D%2212%22%20font-weight%3D%22600%22%3ESuper%3C%2Ftext%3E%3C%2Fsvg%3E', 'https://superliberdade.com.br', true, '2026-11-30', 'Rede de supermercados'),
  ('Auto Center Vale', '55.666.777/0001-88', 'agendamento@autovale.com.br', 'data:image/svg+xml;utf8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%22150%22%20height%3D%2250%22%20viewBox%3D%220%200%20150%2050%22%3E%3Crect%20width%3D%22100%25%22%20height%3D%22100%25%22%20fill%3D%22%23ef4444%22%2F%3E%3Ctext%20x%3D%2250%25%22%20y%3D%2250%25%22%20fill%3D%22%23ffffff%22%20dominant-baseline%3D%22middle%22%20text-anchor%3D%22middle%22%20font-family%3D%22sans-serif%22%20font-size%3D%2212%22%20font-weight%3D%22600%22%3EAuto%3C%2Ftext%3E%3C%2Fsvg%3E', 'https://autovale.com.br', false, '2026-09-15', 'Contrato encerrado'),
  ('Farmácia Popular', '22.333.444/0001-55', 'contato@farmaciapopular.com.br', 'data:image/svg+xml;utf8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%22150%22%20height%3D%2250%22%20viewBox%3D%220%200%20150%2050%22%3E%3Crect%20width%3D%22100%25%22%20height%3D%22100%25%22%20fill%3D%22%23059669%22%2F%3E%3Ctext%20x%3D%2250%25%22%20y%3D%2250%25%22%20fill%3D%22%23ffffff%22%20dominant-baseline%3D%22middle%22%20text-anchor%3D%22middle%22%20font-family%3D%22sans-serif%22%20font-size%3D%2212%22%20font-weight%3D%22600%22%3EFarm%3C%2Ftext%3E%3C%2Fsvg%3E', 'https://farmaciapopular.com.br', true, '2027-06-30', 'Rede farmacêutica')
ON CONFLICT DO NOTHING;

-- ========================================
-- 2. EPISODE_SPONSORS
-- ========================================
INSERT INTO public.episode_sponsors (episode_date, sponsor_id, placement, notes)
SELECT '2026-08-01', s.id, 'pre-roll', 'Menção nos primeiros 30s'
FROM public.sponsors s WHERE s.name = 'TechCorp Brasil'
ON CONFLICT DO NOTHING;

INSERT INTO public.episode_sponsors (episode_date, sponsor_id, placement, notes)
SELECT '2026-08-02', s.id, 'mid-roll', 'Menção no meio do episódio'
FROM public.sponsors s WHERE s.name = 'Supermercado Liberdade'
ON CONFLICT DO NOTHING;

INSERT INTO public.episode_sponsors (episode_date, sponsor_id, placement, notes)
SELECT '2026-08-03', s.id, 'pre-roll', 'Patrocínio integral'
FROM public.sponsors s WHERE s.name = 'TechCorp Brasil'
ON CONFLICT DO NOTHING;

-- ========================================
-- 3. AD_CAMPAIGNS
-- ========================================
INSERT INTO public.ad_campaigns (
  advertiser_name, sponsor_id, title, start_date, end_date, active, skip_after_seconds, priority, notes
)
SELECT
  'TechCorp — Lançamento Q3', s.id, 'Lançamento Smartphones 2026',
  CURRENT_DATE - INTERVAL '5 days', CURRENT_DATE + INTERVAL '25 days',
  true, 5, 10, 'Campanha principal Q3'
FROM public.sponsors s WHERE s.name = 'TechCorp Brasil'
ON CONFLICT DO NOTHING;

INSERT INTO public.ad_campaigns (
  advertiser_name, sponsor_id, title, start_date, end_date, active, skip_after_seconds, priority, notes
)
SELECT
  'Imobiliária Vale — Imóveis', NULL, 'Imóveis Residenciais 2026',
  CURRENT_DATE - INTERVAL '2 days', CURRENT_DATE + INTERVAL '28 days',
  true, 7, 5, 'Campanha secundária'
FROM public.sponsors s WHERE s.name = 'Imobiliária Vale da Liberdade'
ON CONFLICT DO NOTHING;

INSERT INTO public.ad_campaigns (
  advertiser_name, sponsor_id, title, start_date, end_date, active, skip_after_seconds, priority, notes
)
SELECT
  'Supermercado Liberdade — Ofertas', s.id, 'Ofertas da Semana',
  CURRENT_DATE - INTERVAL '1 day', CURRENT_DATE + INTERVAL '6 days',
  true, 4, 3, 'Campanha curta'
FROM public.sponsors s WHERE s.name = 'Supermercado Liberdade'
ON CONFLICT DO NOTHING;

-- ========================================
-- 4. AD_CREATIVES
-- ========================================
INSERT INTO public.ad_creatives (campaign_id, media_type, media_url, click_url, weight, alt_text, active)
SELECT ac.id, 'image', 'data:image/svg+xml;utf8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%22480%22%20height%3D%22320%22%20viewBox%3D%220%200%20480%20320%22%3E%3Crect%20width%3D%22100%25%22%20height%3D%22100%25%22%20fill%3D%22%2310b981%22%2F%3E%3Ctext%20x%3D%2250%25%22%20y%3D%2250%25%22%20fill%3D%22%23ffffff%22%20dominant-baseline%3D%22middle%22%20text-anchor%3D%22middle%22%20font-family%3D%22sans-serif%22%20font-size%3D%2228%22%20font-weight%3D%22600%22%3ETechCorp%3C%2Ftext%3E%3C%2Fsvg%3E', 'https://techcorp.com.br/landing', 3, 'TechCorp Smartphones', true
FROM public.ad_campaigns ac WHERE ac.advertiser_name LIKE 'TechCorp%'
ON CONFLICT DO NOTHING;

INSERT INTO public.ad_creatives (campaign_id, media_type, media_url, click_url, weight, alt_text, active)
SELECT ac.id, 'image', 'data:image/svg+xml;utf8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%22480%22%20height%3D%22320%22%20viewBox%3D%220%200%20480%20320%22%3E%3Crect%20width%3D%22100%25%22%20height%3D%22100%25%22%20fill%3D%22%23059669%22%2F%3E%3Ctext%20x%3D%2250%25%22%20y%3D%2250%25%22%20fill%3D%22%23ffffff%22%20dominant-baseline%3D%22middle%22%20text-anchor%3D%22middle%22%20font-family%3D%22sans-serif%22%20font-size%3D%2228%22%20font-weight%3D%22600%22%3ETech5G%3C%2Ftext%3E%3C%2Fsvg%3E', 'https://techcorp.com.br/5g', 2, 'TechCorp 5G', true
FROM public.ad_campaigns ac WHERE ac.advertiser_name LIKE 'TechCorp%'
ON CONFLICT DO NOTHING;

INSERT INTO public.ad_creatives (campaign_id, media_type, media_url, click_url, weight, alt_text, active)
SELECT ac.id, 'image', 'data:image/svg+xml;utf8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%22480%22%20height%3D%22320%22%20viewBox%3D%220%200%20480%20320%22%3E%3Crect%20width%3D%22100%25%22%20height%3D%22100%25%22%20fill%3D%22%233b82f6%22%2F%3E%3Ctext%20x%3D%2250%25%22%20y%3D%2250%25%22%20fill%3D%22%23ffffff%22%20dominant-baseline%3D%22middle%22%20text-anchor%3D%22middle%22%20font-family%3D%22sans-serif%22%20font-size%3D%2228%22%20font-weight%3D%22600%22%3EImobVale%3C%2Ftext%3E%3C%2Fsvg%3E', 'https://valevalor.com.br', 2, 'Imobiliária Vale', true
FROM public.ad_campaigns ac WHERE ac.advertiser_name LIKE 'Imobiliária%'
ON CONFLICT DO NOTHING;

INSERT INTO public.ad_creatives (campaign_id, media_type, media_url, click_url, weight, alt_text, active)
SELECT ac.id, 'image', 'data:image/svg+xml;utf8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%22480%22%20height%3D%22320%22%20viewBox%3D%220%200%20480%20320%22%3E%3Crect%20width%3D%22100%25%22%20height%3D%22100%25%22%20fill%3D%22%23f59e0b%22%2F%3E%3Ctext%20x%3D%2250%25%22%20y%3D%2250%25%22%20fill%3D%22%23ffffff%22%20dominant-baseline%3D%22middle%22%20text-anchor%3D%22middle%22%20font-family%3D%22sans-serif%22%20font-size%3D%2228%22%20font-weight%3D%22600%22%3ESuperLiberdade%3C%2Ftext%3E%3C%2Fsvg%3E', 'https://superliberdade.com.br', 2, 'Supermercado Liberdade', true
FROM public.ad_campaigns ac WHERE ac.advertiser_name LIKE 'Supermercado%'
ON CONFLICT DO NOTHING;

-- ========================================
-- 5. AD_EVENTS
-- ========================================
INSERT INTO public.ad_events (creative_id, campaign_id, event_type, session_id, created_at)
SELECT
  ci.id, ci.campaign_id,
  CASE (random() * 100)::int WHEN 0 THEN 'click' WHEN 1 THEN 'skip' ELSE 'impression' END,
  md5((random()::text || now()::text || gs::text)),
  NOW() - (random() * INTERVAL '30 days')
FROM public.ad_creatives ci
CROSS JOIN generate_series(1, 25) AS gs
WHERE ci.active = true
ON CONFLICT DO NOTHING;

-- Mais eventos para TechCorp
INSERT INTO public.ad_events (creative_id, campaign_id, event_type, session_id, created_at)
SELECT
  ci.id, ci.campaign_id,
  CASE (random() * 100)::int WHEN 0 THEN 'click' WHEN 1 THEN 'skip' ELSE 'impression' END,
  md5((random()::text || now()::text || gs::text || 'tech')),
  NOW() - (random() * INTERVAL '15 days')
FROM public.ad_creatives ci
JOIN public.ad_campaigns ac ON ac.id = ci.campaign_id
CROSS JOIN generate_series(1, 40) AS gs
WHERE ci.active = true AND ac.advertiser_name LIKE 'TechCorp%'
ON CONFLICT DO NOTHING;

-- ========================================
-- 6. USER_PROFILES
-- ========================================
INSERT INTO public.user_profiles (id, email, full_name, role, avatar_url, created_at)
SELECT
  u.id,
  u.email,
  'Usuário Teste ' || row_number() OVER (),
  CASE (row_number() OVER () % 10) WHEN 0 THEN 'admin' WHEN 1 THEN 'editor' ELSE 'reader' END,
  'https://www.gravatar.com/avatar/' || md5(u.email) || '?d=identicon',
  u.created_at
FROM auth.users u
WHERE u.aud = 'authenticated'
ON CONFLICT (id) DO UPDATE SET
  email = EXCLUDED.email;

-- ========================================
-- 7. SUBSCRIPTIONS
-- ========================================
INSERT INTO public.subscriptions (user_id, email, plan_name, status, price_cents, started_at, expires_at)
SELECT
  up.id, up.email,
  CASE (random() * 3)::int WHEN 0 THEN 'premium' WHEN 1 THEN 'vip' ELSE 'free' END,
  'active',
  CASE (random() * 3)::int WHEN 0 THEN 2990 WHEN 1 THEN 4990 ELSE 0 END,
  NOW() - (random() * INTERVAL '60 days'),
  NOW() + (random() * INTERVAL '30 days')
FROM public.user_profiles up
WHERE up.role IN ('reader', 'editor')
LIMIT 12
ON CONFLICT DO NOTHING;

-- ========================================
-- VERIFICAÇÃO
-- ========================================
SELECT 'sponsors' AS tabela, COUNT(*) AS total FROM public.sponsors
UNION ALL SELECT 'ad_campaigns', COUNT(*) FROM public.ad_campaigns
UNION ALL SELECT 'ad_creatives', COUNT(*) FROM public.ad_creatives WHERE active = true
UNION ALL SELECT 'ad_events', COUNT(*) FROM public.ad_events
UNION ALL SELECT 'user_profiles', COUNT(*) FROM public.user_profiles
UNION ALL SELECT 'subscriptions', COUNT(*) FROM public.subscriptions WHERE status = 'active';

SELECT 'KPIs' AS info, get_admin_kpis() AS kpis;
