# Sistema de Anúncios - Vale da Liberdade

**Data de implementação:** 2026-08-03  
**Status:** ✅ Implementado e sincronizado  
**Ambiente:** Supabase + PWA estática

---

## Arquitetura

O sistema possui dois tipos de anúncios totalmente independentes:

### 1. Tipo 1 — Patrocínio Embutido no Episódio (Conteúdo)
- **O que é:** O áudio do patrocinador já vem gravado junto do áudio do episódio no pipeline de produção (ex: "este episódio é oferecido por Citroën").
- **Funcionamento:** Não há seleção dinâmica no player. O backend catalogou as tabelas `sponsors` e `episode_sponsors` (relação N:M por data do episódio).
- **Exibição Frontend:** Exibe selos visuais em tempo real ("Apresentado por [Sponsor]") no Hero Card, nos cards da Timeline e no Player Expandido.
- **Comportamento:** A busca é feita via RPC `get_episode_sponsors()`. Se a busca live responder, ela atualiza a UI. Se falhar ou estiver offline, usa os dados estáticos gravados no `episodes.json`.

### 2. Tipo 2 — Anúncio Interstitial Entre Episódios (Estilo Spotify)
- **O que é:** Vinheta/anúncio exibido em modal fullscreen (`#adInterstitialOverlay`) durante a transição automática de episódios (quando um episódio chega ao fim).
- **Funcionamento:**
  - Quando o episódio emite o evento `ended`, o PWA chama a RPC `get_active_interstitial_ad()`.
  - Se houver anúncio ativo (campanha e criativo ativos, dentro do período de datas `start_date` e `end_date`), a RPC seleciona o criativo da **maior prioridade** (`MAX(priority)`) e aplica **amostragem aleatória ponderada pelo peso** (`-ln(random()) / weight`).
  - Se **não houver anúncio ativo**, o PWA passa para o próximo episódio instantaneamente sem exibir overlay.
- **Formatos de Mídia:** Suporta `video`, `image` e `gif`. Se a política do navegador bloquear autoplay unmuted de vídeo, o sistema muta o vídeo automaticamente e executa o áudio master (`audio_url`), mantendo a sincronia.
- **Contador de Pular:** Botão de pular é habilitado após `skip_after_seconds` (mínimo 3s).
- **Tracking & Métricas:** Todas as impressões, cliques, skips e erros são gravados na tabela `ad_events` via RPC `track_ad_event()`, com filtro anti-spam de 10s por sessão de usuário.

---

## Gestão Administrativa no Supabase (Admin V1)

A gestão de anunciantes e campanhas é feita diretamente via **Supabase Table Editor** (ou painel admin web futuro):

### Cadastrar Patrocinador (Tipo 1):
1. Inserir em `sponsors`: `name`, `logo_url`, `website_url`, `active = true`
2. Vincular em `episode_sponsors`: `episode_date` (formato "YYYY-MM-DD"), `sponsor_id`, `placement` (ex: "pre-roll")

### Cadastrar Campanha & Criativo Interstitial (Tipo 2):
1. Inserir em `ad_campaigns`: `advertiser_name`, `start_date`, `end_date`, `priority` (inteiro, padrão 0), `active = true`
2. Inserir em `ad_creatives`: `campaign_id`, `media_type` ('image', 'gif', 'video'), `media_url`, `audio_url` (opcional), `click_url`, `weight` (inteiro, padrão 100), `skip_after_seconds` (padrão 7), `active = true`

### Kill-Switch (Pausar Anúncio Imediatamente):
- Mudar `active = false` na campanha ou no criativo. O efeito é **imediato** para todos os ouvintes no site, sem precisar de novo deploy ou restart de serviços.

### Proteção Fiscal de Dados:
- Deletar campanhas/criativos com eventos gravados falhará de propósito (`ON DELETE RESTRICT`). Sempre desative usando `active = false` para preservar o histórico de faturamento de relatórios.

---

## Checklist para Deploy no Servidor

### 1. Confirmar que as tabelas e funções RPC foram criadas no Supabase:

```sql
-- Executar no SQL Editor do Supabase Studio (http://192.168.31.22:8080)
-- 1. Estrutura de tabelas
\i scripts/03_ads_monetization.sql

-- 2. Funções RPC
\i scripts/04_ads_rpc_functions.sql
```

### 2. Subir as alterações dos arquivos na pasta pública do servidor web:

**Arquivos frontend (origem → build):**
- `new-ux/public/index.html` → `public/index.html`
- `new-ux/public/assets/css/components.css` → `public/assets/css/components.css`
- `new-ux/public/js/supabase_client.js` → `public/js/supabase_client.js`
- `new-ux/public/assets/js/ad_manager.js` → `public/assets/js/ad_manager.js`
- `new-ux/public/assets/js/app.js` → `public/assets/js/app.js`

**Comando de deploy:**
```bash
cd /home/osmar/web-jornal-vale-da-liberdade
python3 scripts/publish_site.py
```

### 3. Verificar no browser:
- Acessar `http://127.0.0.1:8090` (local) ou `https://news.mob.tec.br` (produção)
- Confirmar que o overlay de anúncio aparece ao finalizar um episódio (se houver campanha ativa)
- Verificar selos de patrocinadores nos cards
- Console do navegador: 0 erros relacionados a `[ads]`

---

## Estrutura de Tabelas (Supabase)

### Tipo 1 - Patrocínio Embutido:
```sql
CREATE TABLE sponsors (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    name TEXT NOT NULL,
    logo_url TEXT,
    website_url TEXT,
    active BOOLEAN DEFAULT TRUE,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE episode_sponsors (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    episode_date TEXT NOT NULL,  -- "2026-08-03"
    sponsor_id UUID REFERENCES public.sponsors(id) ON DELETE CASCADE,
    placement TEXT DEFAULT 'pre-roll',
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(episode_date, sponsor_id)
);
```

### Tipo 2 - Interstitial:
```sql
CREATE TABLE ad_campaigns (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    advertiser_name TEXT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    priority INTEGER DEFAULT 0,
    active BOOLEAN DEFAULT TRUE,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE ad_creatives (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    campaign_id UUID REFERENCES public.ad_campaigns(id) ON DELETE CASCADE,
    media_type TEXT NOT NULL CHECK (media_type IN ('image', 'gif', 'video')),
    media_url TEXT NOT NULL,
    audio_url TEXT,
    click_url TEXT,
    weight INTEGER DEFAULT 100,
    skip_after_seconds INTEGER DEFAULT 7,
    alt_text TEXT,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE ad_events (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    creative_id UUID NOT NULL REFERENCES public.ad_creatives(id) ON DELETE RESTRICT,
    campaign_id UUID NOT NULL REFERENCES public.ad_campaigns(id) ON DELETE RESTRICT,
    event_type TEXT NOT NULL CHECK (event_type IN ('impression', 'click', 'skip', 'error')),
    session_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## Funções RPC (Supabase)

### `get_active_interstitial_ad()`
Retorna 1 criativo ativo da campanha de maior prioridade (com rotação por peso entre empates de prioridade). Retorna NULL se zero campanhas ativas.

### `track_ad_event(p_creative_id, p_event_type, p_session_id)`
Insere métrica em `ad_events` com janela anti-spam de 10s para impressões e cliques da mesma sessão.

### `get_episode_sponsors(p_episode_dates)`
Retorna patrocinadores ativos do Tipo 1 agrupados por data de episódio.

---

## Arquivos do Sistema

### Backend (Supabase):
- `scripts/03_ads_monetization.sql` - Estrutura das tabelas
- `scripts/04_ads_rpc_functions.sql` - Funções RPC

### Frontend (PWA):
- `public/assets/js/ad_manager.js` - Gerenciador do overlay interstitial
- `public/assets/js/supabase_client.js` - Integração com RPCs de anúncios
- `public/assets/js/app.js` - Integração com player e renderização
- `public/assets/css/components.css` - Estilos do overlay
- `public/index.html` - Markup do overlay

---

## Próximos Passos

1. **Executar SQL no Supabase** para criar as tabelas e funções RPC
2. **Cadastrar dados de teste** para validação:
   - Um patrocinador (Tipo 1)
   - Uma campanha + criativo (Tipo 2)
3. **Testar no browser** local (`:8090`) e produção (`news.mob.tec.br`)
4. **Configurar métricas** no Supabase para tracking de impressões/cliques
5. **Implementar dashboard admin** (fase futura) para gestão visual

---

## Notas de Implementação

- O sistema foi implementado mantendo a consistência com a arquitetura existente do web-jornal
- A integração com o player é feita via eventos customizados (`playerevent`)
- O kill-switch funciona em tempo real via update de tabela
- O tracking de eventos é assíncrono e não bloqueante
- A proteção fiscal garante que campanhas não sejam deletadas acidentalmente
