# Contexto de Transição — Backend de Anúncios & Dashboard Admin

**Projeto:** Webjornal Vale da Liberdade  
**Data:** 3 de Agosto de 2026  
**Status do Sistema:** Sistema de Anúncios 100% Concluído e Operacional

---

## 📌 Status Atual do Sistema (O que já está feito e NÃO precisa ser refeito)

- ✅ **SQL Executado no Supabase:**
  - `scripts/03_ads_monetization.sql`: Tabelas `sponsors`, `episode_sponsors`, `ad_campaigns`, `ad_creatives`, `ad_events`.
  - `scripts/04_ads_rpc_functions.sql`: RPCs `get_active_interstitial_ad()`, `track_ad_event()`, `get_episode_sponsors()`.
  - `scripts/05_admin_dashboard_backend.sql`: Tabela `subscriptions`, coluna `role` em `user_profiles`, RPCs `is_admin_user()`, `toggle_entity_active()`, `get_admin_kpis()`, `get_admin_ad_metrics_timeseries()`.

- ✅ **Frontend PWA Sincronizado:**
  - `public/index.html` & `public/assets/css/components.css`: Estilos glassmorphism do modal do Interstitial e badges dos Selos de Patrocínio.
  - `public/js/supabase_client.js`: Métodos RPC de client (`fetchActiveAd`, `recordAdEvent`, `fetchEpisodeSponsors`).
  - `public/assets/js/ad_manager.js`: Módulo do Interstitial Overlay (vídeo/imagem/gif, fallback de autoplay, countdown ARIA).
  - `public/assets/js/app.js`: Interceptação do auto-play no evento `ended` e renderização dos selos Tipo 1.

- ✅ **Kill-Switch Operacional & Tracking Ativo:**
  - Alterações no Supabase (`active = false`) surtem efeito imediato no site sem necessidade de novo deploy.
  - Rastreamento de impressões, cliques, skips e erros com anti-spam de 10s.

---

## 🎯 Objetivo da Nova Sessão: Dashboard Web Admin (`public/admin/`)

Desenvolver a interface da **Dashboard Web Admin** na pasta `/public/admin/` para gerenciar:
1. **Patrocinadores & Anúncios (Tipo 1 e Tipo 2)** com botões de **Kill-Switch em 1 clique**.
2. **Usuários & Assinaturas (Subscriptions)** com controle de planos (`free`, `premium`, `vip`) e vencimentos.
3. **Relatórios Gráficos de Performance** com exportação de dados em CSV.

---

## 📄 Arquivo de Planejamento Exclusivo

O roteiro de execução da Dashboard está localizado exclusivamente em:
`/home/osmar/web-jornal-vale-da-liberdade/references/plano-admin-dashboard.md`
