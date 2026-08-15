/**
 * admin_init.js — Inicialização da Dashboard Admin
 * Usa o client único criado por admin_auth.js (sem segunda instância GoTrue).
 */

document.addEventListener('DOMContentLoaded', () => {
  console.log('[admin_init] boot');

  // Garante init do auth (idempotente)
  if (window.AdminAuth) {
    AdminAuth.init();
  } else {
    console.error('[admin_init] AdminAuth ausente');
    return;
  }

  let modulesInitialized = false; // guard local: mesmo se onAdminReady disparar 2x, módulos initam 1x

  AdminAuth.onAdminReady(() => {
    if (modulesInitialized) {
      console.log('[admin_init] módulos já inicializados — ignorando callback duplicado');
      return;
    }
    modulesInitialized = true;

    const supabaseClient = AdminAuth.getClient();
    if (!supabaseClient) {
      console.error('[admin_init] client Supabase ausente após auth');
      return;
    }

    console.log('[admin_init] admin ready — carregando módulos');

    if (window.AdminAds) AdminAds.init(supabaseClient);
    if (window.AdminUsers) AdminUsers.init(supabaseClient);
    if (window.AdminCharts) AdminCharts.init(supabaseClient);
    if (window.AdminAudience) AdminAudience.init(supabaseClient);

    if (window.AdminCharts && AdminCharts.loadMetrics) {
      AdminCharts.loadMetrics(30);
    }

    setupNavigation();
    setupSidebarToggle();

    const killSwitchBtn = document.getElementById('btnGlobalKillSwitch');
    if (killSwitchBtn && window.AdminAds) {
      killSwitchBtn.addEventListener('click', AdminAds.toggleGlobalKillSwitch);
    }

    const exportBtn = document.getElementById('btnExportCSV');
    if (exportBtn && window.AdminCharts) {
      exportBtn.addEventListener('click', () => AdminCharts.exportMetricsCSV());
    }
  });
});

function setupSidebarToggle() {
  const sidebar = document.getElementById('adminSidebar') || document.querySelector('.sidebar');
  const overlay = document.getElementById('sidebarOverlay');
  const toggleBtn = document.getElementById('btnSidebarToggle');
  if (!sidebar || !toggleBtn) return;

  function openSidebar() {
    sidebar.classList.add('open');
    if (overlay) overlay.classList.add('active');
    document.body.style.overflow = 'hidden';
  }

  function closeSidebar() {
    sidebar.classList.remove('open');
    if (overlay) overlay.classList.remove('active');
    document.body.style.overflow = '';
  }

  function toggleSidebar() {
    if (sidebar.classList.contains('open')) closeSidebar();
    else openSidebar();
  }

  toggleBtn.addEventListener('click', (e) => {
    e.preventDefault();
    toggleSidebar();
  });

  if (overlay) {
    overlay.addEventListener('click', closeSidebar);
  }

  // Fecha o menu ao navegar (mobile)
  document.querySelectorAll('.nav-item').forEach((item) => {
    item.addEventListener('click', () => {
      if (window.innerWidth <= 768) closeSidebar();
    });
  });

  // Fecha ao clicar em Sair/Tema também não precisa — mas Escape ajuda
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeSidebar();
  });

  window.addEventListener('resize', () => {
    if (window.innerWidth > 768) closeSidebar();
  });
}

function setupNavigation() {
  const navItems = document.querySelectorAll('.nav-item');
  const panels = document.querySelectorAll('.panel');
  const pageTitle = document.getElementById('pageTitle');

  const panelTitles = {
    overview: 'Visão Geral',
    ads: 'Monetização Ads',
    users: 'Usuários & Assinaturas',
    reports: 'Relatórios & Gráficos',
    audience: 'Audiência',
  };

  navItems.forEach((item) => {
    item.addEventListener('click', (e) => {
      e.preventDefault();
      const panelId = item.dataset.panel;

      navItems.forEach((n) => n.classList.remove('active'));
      item.classList.add('active');

      panels.forEach((p) => p.classList.remove('active'));
      const targetPanel = document.getElementById(`panel-${panelId}`);
      if (targetPanel) targetPanel.classList.add('active');

      if (pageTitle && panelTitles[panelId]) {
        pageTitle.textContent = panelTitles[panelId];
      }

      if (panelId === 'ads' && window.AdminAds) {
        AdminAds.loadCampaigns();
        AdminAds.loadSponsors();
      } else if (panelId === 'users' && window.AdminUsers) {
        AdminUsers.loadUsersAndSubs();
      } else if (panelId === 'reports' && window.AdminCharts) {
        AdminCharts.loadMetrics(30);
      } else if (panelId === 'overview' && window.AdminAds) {
        AdminAds.loadCampaigns();
      }
    });
  });
}
