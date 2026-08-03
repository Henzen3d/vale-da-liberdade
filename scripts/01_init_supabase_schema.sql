-- Schema de Autenticação e Dados do Usuário para o Web Jornal Vale da Liberdade
-- Executar no SQL Editor do Supabase Studio (http://192.168.31.22:8080) ou via psql

-- 1. Tabela de Perfis de Usuário
CREATE TABLE IF NOT EXISTS public.user_profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT UNIQUE NOT NULL,
    full_name TEXT,
    avatar_url TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. Tabela de Episódios Favoritados
CREATE TABLE IF NOT EXISTS public.user_favorites (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    episode_date TEXT NOT NULL,
    title TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, episode_date)
);

-- 3. Tabela de Histórico de Escuta e Progresso
CREATE TABLE IF NOT EXISTS public.listening_history (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    episode_date TEXT NOT NULL,
    progress_seconds INTEGER DEFAULT 0,
    completed BOOLEAN DEFAULT FALSE,
    last_listened_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, episode_date)
);

-- Habilitar Row Level Security (RLS) em todas as tabelas
ALTER TABLE public.user_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_favorites ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.listening_history ENABLE ROW LEVEL SECURITY;

-- Políticas de Segurança RLS (Cada usuário acessa apenas seus próprios dados)

-- Políticas para user_profiles
CREATE POLICY "Usuários podem ver próprio perfil" 
    ON public.user_profiles FOR SELECT 
    USING (auth.uid() = id);

CREATE POLICY "Usuários podem atualizar próprio perfil" 
    ON public.user_profiles FOR UPDATE 
    USING (auth.uid() = id);

-- Políticas para user_favorites
CREATE POLICY "Usuários podem ver seus favoritos" 
    ON public.user_favorites FOR SELECT 
    USING (auth.uid() = user_id);

CREATE POLICY "Usuários podem adicionar favoritos" 
    ON public.user_favorites FOR INSERT 
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Usuários podem remover favoritos" 
    ON public.user_favorites FOR DELETE 
    USING (auth.uid() = user_id);

-- Políticas para listening_history
CREATE POLICY "Usuários podem ver seu histórico de escuta" 
    ON public.listening_history FOR SELECT 
    USING (auth.uid() = user_id);

CREATE POLICY "Usuários podem atualizar ou criar seu histórico de escuta" 
    ON public.listening_history FOR ALL 
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- Trigger para criar perfil automaticamente no primeiro login
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.user_profiles (id, email, full_name, avatar_url)
    VALUES (
        new.id,
        new.email,
        new.raw_user_meta_data->>'full_name',
        new.raw_user_meta_data->>'avatar_url'
    )
    ON CONFLICT (id) DO UPDATE SET
        full_name = EXCLUDED.full_name,
        avatar_url = EXCLUDED.avatar_url,
        updated_at = NOW();
    RETURN new;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Ativar o Trigger ao cadastrar/logar novo usuário
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT OR UPDATE ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();
