-- Feedback social: like/dislike/share/copy por episódio
CREATE TABLE IF NOT EXISTS public.user_feedback (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    episode_date TEXT NOT NULL,
    thumbs_up BOOLEAN DEFAULT FALSE,
    thumbs_down BOOLEAN DEFAULT FALSE,
    shared_at TIMESTAMPTZ,
    copied_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, episode_date)
);

ALTER TABLE public.user_feedback ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='user_feedback' AND policyname='uf_select_own') THEN
        CREATE POLICY uf_select_own ON public.user_feedback FOR SELECT USING (auth.uid() = user_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='user_feedback' AND policyname='uf_insert_own') THEN
        CREATE POLICY uf_insert_own ON public.user_feedback FOR INSERT WITH CHECK (auth.uid() = user_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='user_feedback' AND policyname='uf_update_own') THEN
        CREATE POLICY uf_update_own ON public.user_feedback FOR UPDATE USING (auth.uid() = user_id);
    END IF;
END $$;

-- Função pra toggle like (mutuamente exclusivo com dislike)
CREATE OR REPLACE FUNCTION public.fn_toggle_like(p_episode_date TEXT)
RETURNS JSON AS $$
DECLARE
    uid UUID := auth.uid();
    cur_up BOOLEAN := FALSE;
    new_state BOOLEAN;
BEGIN
    IF uid IS NULL THEN
        RAISE EXCEPTION 'not_authenticated';
    END IF;
    SELECT thumbs_up INTO cur_up FROM public.user_feedback WHERE user_id=uid AND episode_date=p_episode_date;
    IF NOT FOUND THEN
        INSERT INTO public.user_feedback (user_id, episode_date, thumbs_up)
        VALUES (uid, p_episode_date, TRUE)
        ON CONFLICT (user_id, episode_date)
        DO UPDATE SET thumbs_up=TRUE, thumbs_down=FALSE, updated_at=NOW();
        new_state := TRUE;
    ELSIF cur_up THEN
        UPDATE public.user_feedback SET thumbs_up=FALSE, updated_at=NOW()
        WHERE user_id=uid AND episode_date=p_episode_date;
        new_state := FALSE;
    ELSE
        UPDATE public.user_feedback SET thumbs_up=TRUE, thumbs_down=FALSE, updated_at=NOW()
        WHERE user_id=uid AND episode_date=p_episode_date;
        new_state := TRUE;
    END IF;
    RETURN json_build_object('thumbs_up', new_state);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE OR REPLACE FUNCTION public.fn_toggle_dislike(p_episode_date TEXT)
RETURNS JSON AS $$
DECLARE
    uid UUID := auth.uid();
    cur_down BOOLEAN := FALSE;
    new_state BOOLEAN;
BEGIN
    IF uid IS NULL THEN
        RAISE EXCEPTION 'not_authenticated';
    END IF;
    SELECT thumbs_down INTO cur_down FROM public.user_feedback WHERE user_id=uid AND episode_date=p_episode_date;
    IF NOT FOUND THEN
        INSERT INTO public.user_feedback (user_id, episode_date, thumbs_down)
        VALUES (uid, p_episode_date, TRUE)
        ON CONFLICT (user_id, episode_date)
        DO UPDATE SET thumbs_down=TRUE, thumbs_up=FALSE, updated_at=NOW();
        new_state := TRUE;
    ELSIF cur_down THEN
        UPDATE public.user_feedback SET thumbs_down=FALSE, updated_at=NOW()
        WHERE user_id=uid AND episode_date=p_episode_date;
        new_state := FALSE;
    ELSE
        UPDATE public.user_feedback SET thumbs_down=TRUE, thumbs_up=FALSE, updated_at=NOW()
        WHERE user_id=uid AND episode_date=p_episode_date;
        new_state := TRUE;
    END IF;
    RETURN json_build_object('thumbs_down', new_state);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Marcar share/copy (uma vez por usuário/episódio)
CREATE OR REPLACE FUNCTION public.fn_mark_shared(p_episode_date TEXT, p_kind TEXT)
RETURNS JSON AS $$
DECLARE
    uid UUID := auth.uid();
BEGIN
    IF uid IS NULL THEN
        RAISE EXCEPTION 'not_authenticated';
    END IF;
    IF p_kind = 'share' THEN
        INSERT INTO public.user_feedback (user_id, episode_date, shared_at)
        VALUES (uid, p_episode_date, NOW())
        ON CONFLICT (user_id, episode_date)
        DO UPDATE SET shared_at=NOW();
    ELSIF p_kind = 'copy' THEN
        INSERT INTO public.user_feedback (user_id, episode_date, copied_at)
        VALUES (uid, p_episode_date, NOW())
        ON CONFLICT (user_id, episode_date)
        DO UPDATE SET copied_at=NOW();
    END IF;
    RETURN json_build_object('ok', TRUE);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

COMMENT ON TABLE public.user_feedback IS 'Feedback social (like/dislike/share/copy) por episódio; rls por usuário';
