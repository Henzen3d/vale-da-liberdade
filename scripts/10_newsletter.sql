-- LOTE 4 (2026-08-07): Newsletter real — tabela de inscritos.
-- Aplicar: docker exec -i supabase-db psql -U postgres -d postgres < scripts/10_newsletter.sql
CREATE TABLE IF NOT EXISTS public.newsletter_subscribers (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  email text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  source text NOT NULL DEFAULT 'site',
  UNIQUE (email)
);

ALTER TABLE public.newsletter_subscribers ENABLE ROW LEVEL SECURITY;

-- Anon pode inserir (assinatura de newsletter); leitura só via service role
CREATE POLICY "newsletter_anon_insert" ON public.newsletter_subscribers
  FOR INSERT TO anon
  WITH CHECK (email <> '' AND email LIKE '%@%');

GRANT INSERT ON public.newsletter_subscribers TO anon;
