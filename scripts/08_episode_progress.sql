-- Progresso de audição por usuário+episódio (UX-009)
-- Base para: estados visuais do feed (não ouvido / parcial / completo),
-- rail "Continuar ouvindo" e resume de playback.
-- Executar no SQL Editor do Supabase Studio (http://192.168.31.22:8080) ou via psql
--
-- Regras de negócio (implementadas no servidor, não no cliente):
--   * episode_id = id do catálogo episodes.json ('2026-08-01' | 'especial-<videoId>')
--   * percent = LEAST(100, progress_seconds/duration_seconds*100)
--   * completed = percent >= 95 (LATCH: uma vez true, nunca volta a false)
--   * completed_at = setado na 1ª vez que cruzar 95%; nunca sobrescrito
--   * progress é MONOTÔNICO: GREATEST(atual, recebido) — nunca regride
--     (protege contra saves atrasados e codifica a regra de merge
--      "maior progresso vence" também no servidor)

CREATE TABLE IF NOT EXISTS public.episode_progress (
    user_id          UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    episode_id       TEXT NOT NULL,
    episode_date     TEXT,
    progress_seconds INTEGER NOT NULL DEFAULT 0,
    duration_seconds INTEGER,
    percent          REAL NOT NULL DEFAULT 0,
    completed        BOOLEAN NOT NULL DEFAULT FALSE,
    first_played_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_played_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at     TIMESTAMPTZ,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, episode_id)
);

CREATE INDEX IF NOT EXISTS idx_ep_user_last
    ON public.episode_progress (user_id, last_played_at DESC);

ALTER TABLE public.episode_progress ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='episode_progress' AND policyname='ep_select_own') THEN
        CREATE POLICY ep_select_own ON public.episode_progress FOR SELECT USING (auth.uid() = user_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='episode_progress' AND policyname='ep_insert_own') THEN
        CREATE POLICY ep_insert_own ON public.episode_progress FOR INSERT WITH CHECK (auth.uid() = user_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='episode_progress' AND policyname='ep_update_own') THEN
        CREATE POLICY ep_update_own ON public.episode_progress FOR UPDATE USING (auth.uid() = user_id);
    END IF;
END $$;

-- RPC único de escrita: o cliente reporta (episode_id, progresso, duração);
-- o servidor decide percent/completed e retorna a linha final para a UI.
CREATE OR REPLACE FUNCTION public.fn_upsert_episode_progress(
    p_episode_id TEXT,
    p_episode_date TEXT,
    p_progress_seconds INTEGER,
    p_duration_seconds INTEGER
)
RETURNS JSON AS $$
DECLARE
    uid UUID := auth.uid();
    v_existing public.episode_progress%ROWTYPE;
    v_progress INTEGER;
    v_duration INTEGER;
    v_percent REAL := 0;
    v_completed BOOLEAN;
    v_completed_at TIMESTAMPTZ;
    v_first TIMESTAMPTZ := NOW();
BEGIN
    IF uid IS NULL THEN
        RAISE EXCEPTION 'not_authenticated';
    END IF;
    IF p_episode_id IS NULL OR length(trim(p_episode_id)) = 0 THEN
        RAISE EXCEPTION 'invalid_episode_id';
    END IF;
    IF p_progress_seconds IS NULL OR p_progress_seconds < 0 THEN
        RAISE EXCEPTION 'invalid_progress';
    END IF;

    SELECT * INTO v_existing
    FROM public.episode_progress
    WHERE user_id = uid AND episode_id = p_episode_id;

    IF FOUND THEN
        -- Monotônico: nunca regride um progresso já mais avançado
        v_progress := GREATEST(v_existing.progress_seconds, p_progress_seconds);
        -- Duração: usa a nova se vier válida, senão mantém a conhecida
        IF p_duration_seconds IS NOT NULL AND p_duration_seconds > 0 THEN
            v_duration := p_duration_seconds;
        ELSE
            v_duration := v_existing.duration_seconds;
        END IF;
        v_first := v_existing.first_played_at;
        v_completed_at := v_existing.completed_at;
    ELSE
        v_progress := p_progress_seconds;
        v_duration := NULLIF(p_duration_seconds, 0);
    END IF;

    IF v_duration IS NOT NULL AND v_duration > 0 THEN
        v_percent := LEAST(100.0, (v_progress::REAL / v_duration::REAL) * 100.0);
    END IF;

    -- Latch de conclusão: uma vez completo, nunca volta a parcial
    v_completed := (v_percent >= 95.0) OR (v_existing.completed = TRUE);
    IF v_completed AND v_completed_at IS NULL THEN
        v_completed_at := NOW();
    END IF;

    INSERT INTO public.episode_progress (
        user_id, episode_id, episode_date,
        progress_seconds, duration_seconds, percent, completed,
        first_played_at, last_played_at, completed_at, updated_at
    ) VALUES (
        uid, p_episode_id, p_episode_date,
        v_progress, v_duration, v_percent, v_completed,
        v_first, NOW(), v_completed_at, NOW()
    )
    ON CONFLICT (user_id, episode_id) DO UPDATE SET
        episode_date     = COALESCE(EXCLUDED.episode_date, public.episode_progress.episode_date),
        progress_seconds = EXCLUDED.progress_seconds,
        duration_seconds = EXCLUDED.duration_seconds,
        percent          = EXCLUDED.percent,
        completed        = EXCLUDED.completed,
        last_played_at   = EXCLUDED.last_played_at,
        completed_at     = COALESCE(public.episode_progress.completed_at, EXCLUDED.completed_at),
        updated_at       = NOW();

    RETURN json_build_object(
        'episode_id',       p_episode_id,
        'episode_date',     p_episode_date,
        'progress_seconds', v_progress,
        'duration_seconds', v_duration,
        'percent',          v_percent,
        'completed',        v_completed,
        'first_played_at',  v_first,
        'last_played_at',   NOW(),
        'completed_at',     v_completed_at
    );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

COMMENT ON TABLE public.episode_progress IS 'Progresso de audição por usuário+episódio; progress monotônico, completed latch em >=95%; rls por usuário';
