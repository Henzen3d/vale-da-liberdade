# Plano de Execução — Dashboard Web Admin (`public/admin/`)

**Projeto:** Webjornal Vale da Liberdade  
**Arquivo de Planejamento:** `plano-admin-dashboard.md`  
**Objetivo:** Criar um painel administrativo web próprio, seguro e completo para gestão de anúncios (Tipo 1 e Tipo 2), usuários, assinaturas (subscriptions) e gráficos de relatórios com kill-switch em 1 clique.

---

## 📋 Visão Geral do Sistema Administrativo

A nova Dashboard ficará localizada em `public/admin/` e terá o seguinte ecossistema:

```
public/admin/
├── index.html                 # Single Page Application (SPA) do Dashboard Admin
├── admin.css                  # Design System Glassmorphism Dark Mode
└── js/
    ├── admin_auth.js          # Guard de Autenticação RBAC (Role-Based Access Control)
    ├── admin_ads.js           # Módulo de Anúncios (Tipo 1, Tipo 2 e Kill-Switch)
    ├── admin_users.js         # Módulo de Usuários e Assinaturas (Subscriptions)
    └── admin_charts.js        # Gráficos de Métricas e Exportador de Relatórios em CSV
```

---

## 🛠️ Fases de Execução Detalhadas

### **Fase 1: Backend SQL & RPCs de Segurança (`scripts/05_admin_dashboard_backend.sql`) — [SCRIPT PRONTO PARA EXECUÇÃO]**

O arquivo `scripts/05_admin_dashboard_backend.sql` **já foi gerado** e contém o seguinte conteúdo DDL/RPC:

1. **Tabela `subscriptions` (Assinaturas / Inscrições):**
   ```sql
   CREATE TABLE IF NOT EXISTS public.subscriptions (
       id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
       user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
       email TEXT NOT NULL,
       plan_name TEXT NOT NULL DEFAULT 'free', -- 'free', 'premium', 'vip'
       status TEXT NOT NULL DEFAULT 'active',  -- 'active', 'cancelled', 'past_due'
       price_cents INTEGER DEFAULT 0,
       started_at TIMESTAMPTZ DEFAULT NOW(),
       expires_at TIMESTAMPTZ,
       created_at TIMESTAMPTZ DEFAULT NOW()
   );
   ```

2. **Verificação de Regra Admin (`is_admin_user`):**
   Função `SECURITY DEFINER` que checa se o usuário logado possui `role = 'admin'` na tabela `user_profiles`.

3. **RPCs de Gestão Administrativa:**
   - `get_admin_kpis()`: Retorna totais de usuários, assinantes ativos, impressões do mês, cliques, CTR % e receita estimada.
   - `toggle_entity_active(p_entity_type, p_entity_id)`: **Kill-Switch em 1 clique** para alterar status ativo/inativo de `sponsors`, `ad_campaigns` ou `ad_creatives`.
   - `upsert_sponsor_admin()`, `upsert_campaign_admin()`, `upsert_creative_admin()`.
   - `get_admin_ad_metrics_timeseries()`: Série temporal para alimentar os gráficos.
   - `get_admin_users_and_subs()`: Lista consolidada de usuários e inscrições.

---

### **Fase 2: Estrutura Frontend & Auth Guard (`public/admin/`)**

1. **Interface SPA (`index.html`):**
   - Header com perfil do admin logado e botão "Sair".
   - Sidebar com 4 abas principais:
     1. 📊 **Visão Geral (KPIs)**
     2. 📢 **Monetização Ads** (Patrocinadores Tipo 1 & Interstitiais Tipo 2)
     3. 👥 **Usuários & Assinaturas**
     4. 📈 **Relatórios & Gráficos**

2. **Design System (`admin.css`):**
   - Tema escuro nativo (Glassmorphism), cartões de KPI com indicadores de variação (+12%), badges coloridas de status (`Ativo`, `Pausado`, `Erro`), tabelas limpas e modais responsivos.

3. **Autenticação RBAC (`admin_auth.js`):**
   - Valida a sessão do Supabase Auth e chama a RPC `is_admin_user()`.
   - Se o usuário não for admin, bloqueia o acesso e exibe a tela de login elegante.

---

### **Fase 3: Módulo de Monetização Ads & Kill-Switch (`admin_ads.js`)**

1. **Aba Patrocinadores (Tipo 1):**
   - Tabela com logo, nome, site e episódios vinculados.
   - **Botão Toggle (Kill-Switch):** Alterna `active = true/false` instantaneamente em 1 clique.
   - Modal para cadastrar/editar patrocinador e vincular a datas de episódio.

2. **Aba Campanhas Interstitiais (Tipo 2):**
   - Tabela hierárquica por Campanha ➔ Criativos.
   - Exibição visual de prioridade, peso, tipo de mídia (imagem/gif/vídeo) e contagem de pular.
   - **Kill-Switch em 1 clique** em nível de campanha e de criativo.
   - Formulário de upload/link de mídias com preview em tempo real.

---

### **Fase 4: Módulo de Usuários e Assinaturas (`admin_users.js`)**

1. **Aba Usuários:**
   - Lista completa de ouvintes cadastrados via Google Auth (`user_profiles`).
   - Métricas de engajamento (quantidade de curtidas/feedbacks e episódios ouvidos).

2. **Aba Assinaturas:**
   - Gestão dos planos dos leitores/ouvintes (Gratuito, Premium, VIP).
   - Alteração manual de status (Ativo, Cancelado, Inadimplente) e data de vencimento.

---

### **Fase 5: Analytics, Gráficos & Exportação de Relatórios (`admin_charts.js`)**

1. **Gráficos Visuais:**
   - Gráfico de linha/barras de Desempenho de Anúncios (Impressões x Cliques x CTR x Skips).
   - Funil de conversão de anúncios e evolução de assinantes.

2. **Exportação CSV:**
   - Botão **"Exportar Relatório CSV"** configurável por período de datas, pronto para enviar relatórios fiscais aos anunciantes.

---

## 🔍 Checklist de Verificação

- [ ] Executar o script `scripts/05_admin_dashboard_backend.sql` no Supabase.
- [ ] Criar a pasta `public/admin/` e seus subarquivos HTML, CSS e JS.
- [ ] Testar login de admin e bloqueio de usuários não autorizados.
- [ ] Testar o Kill-Switch em 1 clique e validar o impacto imediato no player do site.
- [ ] Testar a geração e exportação do arquivo CSV de métricas.

---
*Arquivo gerado e pronto para execução.*
