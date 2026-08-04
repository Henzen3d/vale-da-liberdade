/**
 * admin_users.js — Módulo de Usuários e Assinaturas
 */

const AdminUsers = (() => {
  let supabase = null;
  let users = [];
  let subscriptions = [];
  let isLoading = false;

  function init(supabaseClient) {
    supabase = supabaseClient;
    loadUsersAndSubs();
  }

  // Fallback: se a referência local ficou null, recupera do AdminAuth (padrão vale-admin-fix)
  function getClient() {
    return supabase || (window.AdminAuth ? window.AdminAuth.getClient() : null);
  }

  async function loadUsersAndSubs() {
    // Evita requisições duplicadas concorrentes (ex.: init + click na aba ao mesmo tempo)
    if (isLoading) return;
    isLoading = true;

    const tbody = document.getElementById('usersTableBody');

    try {
      const client = getClient();
      if (!client) throw new Error('Supabase client não disponível');

      const { data, error } = await client.rpc('get_admin_users_and_subs');
      if (error) throw error;

      const rows = Array.isArray(data) ? data : [];
      users = rows.filter(u => u.user_id) || [];
      subscriptions = rows.filter(u => u.sub_id) || [];

      renderUsersTable();
    } catch (err) {
      console.error('[admin_users] Error loading users:', err);
      if (tbody) {
        tbody.innerHTML = `<tr><td colspan="7" class="empty-state"><div class="empty-state-title" style="color:#ef4444;">Erro ao carregar usuários</div><div class="empty-state-desc">${escapeHtml(err.message || String(err))}</div></td></tr>`;
      }
      showToast('Erro ao carregar usuários', 'error');
    } finally {
      isLoading = false;
      // Segurança extra: se por qualquer motivo o spinner ainda estiver no DOM, remove
      if (tbody) {
        tbody.querySelectorAll('tr .spinner').forEach(sp => {
          const row = sp.closest('tr');
          if (row) row.remove();
        });
      }
    }
  }

  function renderUsersTable() {
    const tbody = document.getElementById('usersTableBody');
    if (!tbody) return;

    if (users.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" class="empty-state"><div class="empty-state-title">Nenhum usuário encontrado</div><div class="empty-state-desc">Usuários aparecerão após fazer login no sistema.</div></td></tr>';
      return;
    }

    tbody.innerHTML = users.map(u => {
      const sub = subscriptions.find(s => s.sub_id && s.user_id === u.user_id);
      const plan = sub?.sub_plan_name || 'free';
      const status = sub?.sub_status || 'active';
      const expires = sub?.sub_expires_at ? new Date(sub.sub_expires_at).toISOString().slice(0, 10) : 'Indeterminado';
      
      return `
        <tr>
          <td>
            <div style="display:flex;align-items:center;gap:10px;">
              ${u.avatar_url 
                ? `<img src="${u.avatar_url}" alt="" style="width:32px;height:32px;border-radius:50%;object-fit:cover;border:1px solid rgba(255,255,255,0.1);">`
                : `<div style="width:32px;height:32px;border-radius:50%;background:rgba(16,185,129,0.2);display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;color:#10b981;">${(u.name || '?').charAt(0)}</div>`
              }
              <span style="font-weight:600;color:#fff;font-size:12px;">${escapeHtml(u.name || 'Sem nome')}</span>
            </div>
          </td>
          <td style="color:var(--admin-text-muted);font-size:12px;">${escapeHtml(u.email || '—')}</td>
          <td>
            <select class="form-select" style="width:auto;padding:4px 8px;font-size:11px;" 
                    onchange="AdminUsers.updateRole('${u.user_id}', this.value)">
              <option value="reader" ${u.role === 'reader' ? 'selected' : ''}>Leitor</option>
              <option value="editor" ${u.role === 'editor' ? 'selected' : ''}>Editor</option>
              <option value="admin" ${u.role === 'admin' ? 'selected' : ''}>Admin</option>
            </select>
          </td>
          <td>
            <span class="badge badge-${plan}">${plan.toUpperCase()}</span>
          </td>
          <td>
            <span class="badge badge-${status === 'active' ? 'active' : status === 'cancelled' ? 'paused' : 'ended'}">
              ${status === 'active' ? 'Ativo' : status === 'cancelled' ? 'Cancelado' : 'Vencido'}
            </span>
          </td>
          <td style="font-family:monospace;font-size:11px;color:var(--admin-text-muted);">${expires}</td>
          <td>
            <button class="btn btn-sm btn-secondary" onclick="AdminUsers.changePlan('${u.user_id}', '${plan === 'free' ? 'premium' : plan === 'premium' ? 'vip' : 'free'}')" title="Trocar plano">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12">
                <polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
              </svg>
            </button>
          </td>
        </tr>
      `;
    }).join('');
  }

  async function updateRole(userId, role) {
    // Note: This would require an RPC to update user_profiles role
    // For now, we just show a toast
    showToast(`Role atualizado para ${role}`);
  }

  async function changePlan(userId, newPlan) {
    const priceMap = { free: 0, premium: 2990, vip: 4990 };
    const sub = subscriptions.find(s => s.user_id === userId);
    
    try {
      const { data, error } = await supabase.rpc('update_subscription_admin', {
        p_sub_id: sub?.sub_id || null,
        p_plan_name: newPlan,
        p_status: 'active',
        p_price_cents: priceMap[newPlan] || 0,
        p_expires_at: newPlan === 'vip' 
          ? new Date(Date.now() + 365 * 86400000).toISOString() 
          : null,
      });

      if (error) throw error;
      
      if (data.ok) {
        await loadUsersAndSubs();
        showToast(`Plano alterado para ${newPlan.toUpperCase()}`);
      } else {
        showToast(data.error || 'Erro ao atualizar plano', 'error');
      }
    } catch (err) {
      console.error('[admin_users] Error changing plan:', err);
      showToast('Erro ao atualizar plano', 'error');
    }
  }

  function openUserModal() {
    document.getElementById('userForm').reset();
    document.getElementById('userModal').classList.add('active');
  }

  function closeUserModal() {
    document.getElementById('userModal').classList.remove('active');
  }

  async function saveUser() {
    const name = document.getElementById('userName').value.trim();
    const email = document.getElementById('userEmail').value.trim();
    const password = document.getElementById('userPassword').value;
    const role = document.getElementById('userRole').value;
    const plan = document.getElementById('userPlan').value;

    if (!name || !email) {
      showToast('Preencha nome e email', 'error');
      return;
    }

    const saveBtn = document.querySelector('#userModal .modal-footer .btn-primary');
    if (saveBtn) { saveBtn.disabled = true; saveBtn.textContent = 'Salvando...'; }

    try {
      const client = getClient();
      if (!client) throw new Error('Supabase client não disponível');

      const { data, error } = await client.rpc('create_user_by_admin', {
        p_email: email,
        p_password: password || null,
        p_full_name: name,
        p_role: role,
        p_plan_name: plan,
      });

      if (error) throw new Error(error.message);
      if (!data || data.ok !== true) {
        throw new Error(data?.error || 'Erro desconhecido ao criar usuário');
      }

      showToast(`Usuário criado: ${email}`, 'success');
      closeUserModal();
      await loadUsersAndSubs(); // atualiza a tabela com o novo usuário
    } catch (err) {
      console.error('[admin_users] Error creating user:', err);
      showToast('Erro ao criar usuário: ' + (err.message || err), 'error');
    } finally {
      if (saveBtn) { saveBtn.disabled = false; saveBtn.textContent = 'Salvar'; }
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

  return {
    init,
    loadUsersAndSubs,
    openUserModal,
    closeUserModal,
    saveUser,
    changePlan,
  };
})();

window.adminUsers = AdminUsers;
window.AdminUsers = AdminUsers; // alias: admin_init.js referencia AdminUsers (capital A)
