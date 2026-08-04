/**
 * admin_ads.js — Módulo de Anúncios (Tipo 1 e Tipo 2) com Kill-Switch
 */

const AdminAds = (() => {
  let supabase = null;
  let sponsors = [];
  let campaigns = [];
  let globalKillSwitch = false;

  // Placeholder SVG local — substitui via.placeholder.com (serviço fora do ar,
  // causa net::ERR_CONNECTION_CLOSED no console).
  const DEFAULT_LOGO_PLACEHOLDER = 'data:image/svg+xml;utf8,' + encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" width="150" height="50" viewBox="0 0 150 50">' +
    '<rect width="100%" height="100%" fill="#374151"/>' +
    '<text x="50%" y="50%" fill="#9CA3AF" dominant-baseline="middle" text-anchor="middle" font-family="sans-serif" font-size="12">Logo Anúncio</text>' +
    '</svg>'
  );

  // Troca URLs quebradas (vazias ou via.placeholder.com) pelo placeholder SVG.
  function resolveImgUrl(url) {
    if (!url || typeof url !== 'string' || url.indexOf('via.placeholder.com') !== -1) {
      return DEFAULT_LOGO_PLACEHOLDER;
    }
    return url;
  }

  // Fallback onerror: qualquer imagem que falhar cai no placeholder SVG.
  function handleImgError(img) {
    if (img && img.src !== DEFAULT_LOGO_PLACEHOLDER) {
      img.onerror = null;
      img.src = DEFAULT_LOGO_PLACEHOLDER;
    }
  }

  function init(supabaseClient) {
    supabase = supabaseClient;
    loadSponsors();
    loadCampaigns();
  }

  function getClient() {
    return supabase || (window.AdminAuth ? window.AdminAuth.getClient() : null);
  }

  async function loadSponsors() {
    try {
      const { data, error } = await supabase.rpc('get_admin_sponsors');
      if (error) throw error;
      sponsors = data || [];
      renderSponsorsTable();
      updateSponsorSelects();
    } catch (err) {
      console.error('[admin_ads] Error loading sponsors:', err);
      showToast('Erro ao carregar patrocinadores', 'error');
    }
  }

  async function loadCampaigns() {
    try {
      const { data, error } = await supabase.rpc('get_admin_campaigns');
      if (error) throw error;
      campaigns = data || [];
      renderCampaignsTables();
      updateKPIs();
    } catch (err) {
      console.error('[admin_ads] Error loading campaigns:', err);
      showToast('Erro ao carregar campanhas', 'error');
    }
  }

  function renderSponsorsTable() {
    const tbody = document.getElementById('sponsorsTableBody');
    if (!tbody) return;

    if (sponsors.length === 0) {
      tbody.innerHTML = '<tr><td colspan="5" class="empty-state"><div class="empty-state-title">Nenhum patrocinador cadastrado</div><div class="empty-state-desc">Cadastre patrocinadores para exibir selos nos episódios.</div></td></tr>';
      return;
    }

    tbody.innerHTML = sponsors.map(s => `
      <tr>
        <td>
          <div style="display:flex;align-items:center;gap:10px;">
            ${s.logo_url 
              ? `<img src="${resolveImgUrl(s.logo_url)}" alt="${escapeHtml(s.name)}" onerror="AdminAds._handleImgError(this)" style="width:32px;height:32px;border-radius:6px;object-fit:cover;border:1px solid rgba(255,255,255,0.1);">`
              : `<div style="width:32px;height:32px;border-radius:6px;background:rgba(16,185,129,0.2);display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;color:#10b981;">${s.name.charAt(0)}</div>`
            }
            <span style="font-weight:600;color:#fff;">${escapeHtml(s.name)}</span>
          </div>
        </td>
        <td style="color:var(--admin-text-muted);">${escapeHtml(s.email || '—')}</td>
        <td style="font-family:monospace;font-size:11px;">${s.contract_end || 'Indeterminado'}</td>
        <td>
          <span class="badge ${s.is_active ? 'badge-active' : 'badge-paused'}">
            ${s.is_active ? 'Ativo' : 'Pausado'}
          </span>
        </td>
        <td>
          <button class="btn btn-sm ${s.is_active ? 'btn-warning' : 'btn-primary'}" 
                  onclick="AdminAds.toggleSponsor('${s.sponsor_id}')">
            ${s.is_active ? 'Pausar' : 'Ativar'}
          </button>
          <button class="btn btn-sm btn-secondary" style="margin-left:6px;" 
                  onclick="AdminAds.editSponsor('${s.sponsor_id}')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12">
              <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
              <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
            </svg>
          </button>
        </td>
      </tr>
    `).join('');
  }

  function renderCampaignsTables() {
    // Overview panel table
    renderCampaignTable('campaignsTableBody', campaigns);

    // Ads panel table
    renderCampaignTable('campaignsTableBodyAds', campaigns);
  }

  function renderCampaignTable(tbodyId, campList) {
    const tbody = document.getElementById(tbodyId);
    if (!tbody) return;

    if (campList.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" class="empty-state"><div class="empty-state-title">Nenhuma campanha cadastrada</div><div class="empty-state-desc">Crie campanhas para exibir anúncios intersticiais.</div></td></tr>';
      return;
    }

    // BUGFIX: antes lia "globalPaused" diretamente, variável que só existia
    // no escopo de renderCampaignsTables() => ReferenceError interrompia o render.
    const isGlobalPaused = typeof window.globalPaused !== 'undefined'
      ? !!window.globalPaused
      : globalKillSwitch;

    tbody.innerHTML = campList.map(c => {
      const isPaused = !c.is_active || isGlobalPaused;
      return `
        <tr>
          <td>
            <div style="display:flex;align-items:center;gap:10px;">
              ${c.media_url 
                ? `<img src="${resolveImgUrl(c.media_url)}" alt="" onerror="AdminAds._handleImgError(this)" style="width:40px;height:28px;border-radius:4px;object-fit:cover;border:1px solid rgba(255,255,255,0.1);">`
                : `<div style="width:40px;height:28px;border-radius:4px;background:rgba(16,185,129,0.2);display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;color:#10b981;">${(c.format_type || 'audio').substring(0,3).toUpperCase()}</div>`
              }
              <div>
                <div style="font-weight:600;color:#fff;font-size:12px;">${escapeHtml(c.campaign_name)}</div>
                ${c.headline ? `<div style="font-size:10px;color:var(--admin-text-muted);font-style:italic;">"${escapeHtml(c.headline)}"</div>` : ''}
              </div>
            </div>
          </td>
          <td style="font-weight:600;color:#fff;">${escapeHtml(c.sponsor_name || '—')}</td>
          <td>
            <span style="padding:3px 8px;border-radius:4px;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);font-size:10px;font-weight:600;text-transform:uppercase;">
              ${escapeHtml(c.format_type || 'audio')}
            </span>
          </td>
          <td style="font-size:11px;color:var(--admin-text-muted);font-family:monospace;">
            ${c.start_date || '—'} até ${c.end_date || '—'}
          </td>
          <td>
            <span class="badge ${isPaused ? 'badge-paused' : 'badge-active'}">
              ${isPaused ? 'Pausado' : 'Ativo'}
            </span>
          </td>
          <td style="font-family:monospace;font-size:11px;">
            <span style="color:#fff;font-weight:600;">${(c.impressions || 0).toLocaleString('pt-BR')}</span>
            <span style="color:var(--admin-text-muted);margin:0 4px;">/</span>
            <span style="color:#10b981;font-weight:600;">${(c.clicks || 0).toLocaleString('pt-BR')}</span>
          </td>
          <td>
            <button class="btn btn-sm ${isPaused ? 'btn-primary' : 'btn-danger'}" 
                    onclick="AdminAds.toggleCampaign('${c.campaign_id}')"
                    ${isGlobalPaused ? 'disabled style="opacity:0.5;"' : ''}>
              ${isPaused ? 'Reativar' : 'Kill-Switch'}
            </button>
            <button class="btn btn-sm btn-secondary" style="margin-left:6px;" 
                    onclick="AdminAds.editCampaign('${c.campaign_id}')">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
              </svg>
            </button>
          </td>
        </tr>
      `;
    }).join('');
  }

  async function toggleSponsor(sponsorId) {
    try {
      const { data, error } = await supabase.rpc('toggle_entity_active', {
        p_entity_type: 'sponsors',
        p_entity_id: sponsorId,
      });

      if (error) throw error;
      
      if (data.ok) {
        await loadSponsors();
        showToast('Patrocinador atualizado com sucesso!');
      } else {
        showToast(data.error || 'Erro ao atualizar', 'error');
      }
    } catch (err) {
      console.error('[admin_ads] Error toggling sponsor:', err);
      showToast('Erro ao atualizar patrocinador', 'error');
    }
  }

  async function toggleCampaign(campaignId) {
    try {
      const { data, error } = await supabase.rpc('toggle_entity_active', {
        p_entity_type: 'ad_campaigns',
        p_entity_id: campaignId,
      });

      if (error) throw error;
      
      if (data.ok) {
        await loadCampaigns();
        showToast('Campanha atualizada com sucesso!');
      } else {
        showToast(data.error || 'Erro ao atualizar', 'error');
      }
    } catch (err) {
      console.error('[admin_ads] Error toggling campaign:', err);
      showToast('Erro ao atualizar campanha', 'error');
    }
  }

  async function toggleGlobalKillSwitch() {
    globalKillSwitch = !globalKillSwitch;
    
    const btn = document.getElementById('btnGlobalKillSwitch');
    const label = document.getElementById('killSwitchLabel');
    const banner = document.getElementById('heroBanner');

    if (globalKillSwitch) {
      btn.classList.add('active');
      label.textContent = 'Reativar Anúncios';
      banner.style.display = 'flex';
    } else {
      btn.classList.remove('active');
      label.textContent = 'Kill-Switch Global';
      banner.style.display = 'none';
    }

    renderCampaignsTables();
    showToast(globalKillSwitch ? 'Kill-Switch Global ATIVADO — todos os anúncios pausados' : 'Kill-Switch Global DESATIVADO — anúncios reativados');
  }

  function openCampaignModal(campaignId = null) {
    const modal = document.getElementById('campaignModal');
    const title = document.getElementById('campaignModalTitle');
    const form = document.getElementById('campaignForm');

    updateSponsorSelects();

    if (campaignId) {
      const camp = campaigns.find(c => c.campaign_id === campaignId);
      if (camp) {
        title.textContent = 'Editar Campanha';
        document.getElementById('campaignId').value = camp.campaign_id;
        document.getElementById('campaignName').value = camp.campaign_name || '';
        document.getElementById('campaignSponsor').value = camp.sponsor_id || '';
        document.getElementById('campaignFormat').value = camp.format_type || 'audio';
        document.getElementById('campaignHeadline').value = camp.headline || '';
        document.getElementById('campaignCtaUrl').value = camp.cta_url || '';
        document.getElementById('campaignStartDate').value = camp.start_date || '';
        document.getElementById('campaignEndDate').value = camp.end_date || '';
        document.getElementById('campaignMediaUrl').value = camp.media_url || '';
        document.getElementById('campaignPriority').value = camp.priority || 1;
      }
    } else {
      title.textContent = 'Nova Campanha';
      form.reset();
      document.getElementById('campaignId').value = '';
      document.getElementById('campaignStartDate').value = new Date().toISOString().slice(0, 10);
      document.getElementById('campaignEndDate').value = new Date(Date.now() + 30 * 86400000).toISOString().slice(0, 10);
    }

    modal.classList.add('active');
  }

  function closeCampaignModal() {
    document.getElementById('campaignModal').classList.remove('active');
  }

  async function saveCampaign() {
    const client = getClient();
    if (!client) {
      showToast('Cliente Supabase não inicializado', 'error');
      console.error('[admin_ads] supabase é null em saveCampaign');
      return;
    }

    const id = document.getElementById('campaignId').value;
    const sponsorId = document.getElementById('campaignSponsor').value;
    const name = document.getElementById('campaignName').value.trim();
    const format = document.getElementById('campaignFormat').value;
    const headline = document.getElementById('campaignHeadline').value.trim();
    const ctaUrl = document.getElementById('campaignCtaUrl').value.trim();
    const startDate = document.getElementById('campaignStartDate').value;
    const endDate = document.getElementById('campaignEndDate').value;
    const mediaUrl = document.getElementById('campaignMediaUrl').value.trim();
    const priority = parseInt(document.getElementById('campaignPriority').value) || 1;

    if (!name || !sponsorId) {
      showToast('Preencha nome e patrocinador', 'error');
      return;
    }

    try {
      const { data, error } = await client.rpc('upsert_campaign_admin', {
        p_campaign_id: id || null,
        p_sponsor_id: sponsorId,
        p_name: name,
        p_format_type: format,
        p_headline: headline,
        p_cta_url: ctaUrl,
        p_start_date: startDate || null,
        p_end_date: endDate || null,
        p_media_url: mediaUrl || null,
        p_priority: priority,
      });

      if (error) throw error;
      
      closeCampaignModal();
      await loadCampaigns();
      showToast('Campanha salva com sucesso!');
    } catch (err) {
      console.error('[admin_ads] Error saving campaign:', err);
      showToast('Erro ao salvar campanha', 'error');
    }
  }

  function editCampaign(campaignId) {
    openCampaignModal(campaignId);
  }

  function openSponsorModal(sponsorId = null) {
    const modal = document.getElementById('sponsorModal');
    const title = document.getElementById('sponsorModalTitle');
    const form = document.getElementById('sponsorForm');

    if (sponsorId) {
      const sp = sponsors.find(s => s.sponsor_id === sponsorId);
      if (sp) {
        title.textContent = 'Editar Patrocinador';
        document.getElementById('sponsorId').value = sp.sponsor_id;
        document.getElementById('sponsorName').value = sp.name || '';
        document.getElementById('sponsorCnpj').value = sp.cnpj || '';
        document.getElementById('sponsorEmail').value = sp.email || '';
        document.getElementById('sponsorLogoUrl').value = sp.logo_url || '';
        document.getElementById('sponsorWebsiteUrl').value = sp.website_url || '';
        document.getElementById('sponsorContractEnd').value = sp.contract_end || '';
      }
    } else {
      title.textContent = 'Novo Patrocinador';
      form.reset();
      document.getElementById('sponsorId').value = '';
    }

    modal.classList.add('active');
  }

  function closeSponsorModal() {
    document.getElementById('sponsorModal').classList.remove('active');
  }

  async function saveSponsor() {
    const client = getClient();
    if (!client) {
      showToast('Cliente Supabase não inicializado', 'error');
      console.error('[admin_ads] supabase é null em saveSponsor');
      return;
    }

    const id = document.getElementById('sponsorId').value;
    const name = document.getElementById('sponsorName').value.trim();
    const cnpj = document.getElementById('sponsorCnpj').value.trim();
    const email = document.getElementById('sponsorEmail').value.trim();
    const logoUrl = document.getElementById('sponsorLogoUrl').value.trim();
    const websiteUrl = document.getElementById('sponsorWebsiteUrl').value.trim();
    const contractEnd = document.getElementById('sponsorContractEnd').value;

    if (!name) {
      showToast('Informe o nome do patrocinador', 'error');
      return;
    }

    try {
      const { data, error } = await client.rpc('upsert_sponsor_admin', {
        p_sponsor_id: id || null,
        p_name: name,
        p_cnpj: cnpj || null,
        p_email: email || null,
        p_logo_url: logoUrl || null,
        p_website_url: websiteUrl || null,
        p_contract_end: contractEnd || null,
      });

      if (error) throw error;
      
      closeSponsorModal();
      await loadSponsors();
      await loadCampaigns();
      showToast('Patrocinador salvo com sucesso!');
    } catch (err) {
      console.error('[admin_ads] Error saving sponsor:', err);
      showToast('Erro ao salvar patrocinador', 'error');
    }
  }

  function editSponsor(sponsorId) {
    openSponsorModal(sponsorId);
  }

  function updateSponsorSelects() {
    const selects = ['campaignSponsor'];
    selects.forEach(selectId => {
      const select = document.getElementById(selectId);
      if (!select) return;
      
      const currentValue = select.value;
      select.innerHTML = '<option value="">Selecione...</option>' +
        sponsors.filter(s => s.is_active).map(s => 
          `<option value="${s.sponsor_id}">${escapeHtml(s.name)}</option>`
        ).join('');
      
      if (currentValue) select.value = currentValue;
    });
  }

  async function updateKPIs() {
    try {
      const { data, error } = await supabase.rpc('get_admin_kpis');
      if (error) throw error;

      if (data.total_users !== undefined) {
        document.getElementById('kpiTotalUsers').textContent = data.total_users.toLocaleString('pt-BR');
      }
      if (data.active_subscribers !== undefined) {
        document.getElementById('kpiActiveSubs').textContent = data.active_subscribers.toLocaleString('pt-BR');
      }
      if (data.monthly_impressions !== undefined) {
        document.getElementById('kpiImpressions').textContent = data.monthly_impressions.toLocaleString('pt-BR');
      }
      if (data.ctr_percent !== undefined) {
        document.getElementById('kpiCTR').textContent = data.ctr_percent + '%';
      }
      if (data.active_campaigns !== undefined) {
        document.getElementById('kpiActiveCampaigns').textContent = data.active_campaigns;
        document.getElementById('kpiTotalCampaigns').textContent = `Total: ${campaigns.length}`;
      }
      if (data.estimated_revenue_cents !== undefined) {
        const revenue = (data.estimated_revenue_cents / 100).toFixed(2);
        document.getElementById('kpiRevenue').textContent = 'R$ ' + revenue;
      }
    } catch (err) {
      console.error('[admin_ads] Error updating KPIs:', err);
    }
  }

  function showToast(message, type = 'success') {
    const container = document.getElementById('toastContainer');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16" style="flex-shrink:0;">
        ${type === 'success' 
          ? '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>'
          : '<circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>'
        }
      </svg>
      <div>
        <div class="toast-title">${escapeHtml(message)}</div>
      </div>
    `;

    container.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateX(100%)';
      setTimeout(() => toast.remove(), 200);
    }, 3000);
  }

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text || '';
    return div.innerHTML;
  }

  // Setup event listeners
  document.addEventListener('DOMContentLoaded', () => {
    // Close modals on overlay click
    document.querySelectorAll('.modal-overlay').forEach(overlay => {
      overlay.addEventListener('click', (e) => {
        if (e.target === overlay) {
          overlay.classList.remove('active');
        }
      });
    });
  });

  return {
    init,
    loadCampaigns,
    loadSponsors,
    toggleGlobalKillSwitch,
    toggleCampaign,
    toggleSponsor,
    openCampaignModal,
    closeCampaignModal,
    saveCampaign,
    editCampaign,
    openSponsorModal,
    closeSponsorModal,
    saveSponsor,
    editSponsor,
    _handleImgError: handleImgError, // fallback onerror das imagens das tabelas
  };
})();

window.adminAds = AdminAds;
window.AdminAds = AdminAds; // alias: admin_init.js referencia AdminAds (capital A)
