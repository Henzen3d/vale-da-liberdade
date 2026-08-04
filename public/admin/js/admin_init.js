/**
 * admin_init.js — Inicialização da Dashboard Admin
 * Orquestra a carga dos módulos e navegação entre abas
 */

document.addEventListener('DOMContentLoaded', () => {
  const supabaseUrl = window.SUPABASE_URL;
  const supabaseKey = window.SUPABASE_ANON_KEY;

  if (!window.supabase || !supabaseUrl || !supabaseKey) {
    console.error('[admin_init] Supabase SDK ou chaves ausentes');
    alert('Configuração do Supabase não encontrada.');
    return;
  }

  const supabaseClient = window.supabase.createClient(supabaseUrl, supabaseKey, {
    auth: {
      detectSessionInUrl: true,
      persistSession: true,
      autoRefreshToken: true,
      flowType: 'pkce',
    },
  });

  // Initialize auth first
  AdminAuth.init();

  // When admin is ready, initialize other modules
  AdminAuth.onAdminReady(() => {
    // Initialize modules
    AdminAds.init(supabaseClient);
    AdminUsers.init(supabaseClient);
    AdminCharts.init(supabaseClient);

    // Load chart metrics
    AdminCharts.loadMetrics(30);

    // Setup navigation
    setupNavigation();

    // Setup kill switch button
    const killSwitchBtn = document.getElementById('btnGlobalKillSwitch');
    if (killSwitchBtn) {
      killSwitchBtn.addEventListener('click', AdminAds.toggleGlobalKillSwitch);
    }

    // Setup export CSV button
    const exportBtn = document.getElementById('btnExportCSV');
    if (exportBtn) {
      exportBtn.addEventListener('click', () => {
        AdminCharts.exportMetricsCSV();
      });
    }
  });
});

function setupNavigation() {
  const navItems = document.querySelectorAll('.nav-item');
  const panels = document.querySelectorAll('.panel');
  const pageTitle = document.getElementById('pageTitle');

  const panelTitles = {
    overview: 'Visão Geral',
    ads: 'Monetização Ads',
    users: 'Usuários & Assinaturas',
    reports: 'Relatórios & Gráficos',
  };

  navItems.forEach(item => {
    item.addEventListener('click', (e) => {
      e.preventDefault();
      
      const panelId = item.dataset.panel;
      
      // Update nav active state
      navItems.forEach(n => n.classList.remove('active'));
      item.classList.add('active');

      // Show corresponding panel
      panels.forEach(p => p.classList.remove('active'));
      const targetPanel = document.getElementById(`panel-${panelId}`);
      if (targetPanel) {
        targetPanel.classList.add('active');
      }

      // Update page title
      if (pageTitle && panelTitles[panelId]) {
        pageTitle.textContent = panelTitles[panelId];
      }

      // Reload data when switching panels
      if (panelId === 'ads') {
        AdminAds.loadCampaigns();
        AdminAds.loadSponsors();
      } else if (panelId === 'users') {
        AdminUsers.loadUsersAndSubs();
      } else if (panelId === 'reports') {
        AdminCharts.loadMetrics(30);
      } else if (panelId === 'overview') {
        AdminAds.loadCampaigns();
      }
    });
  });
}
