/**
 * admin_audience.js — Aba Audiência (listen_events).
 */
const AdminAudience = (() => {
  let supabase = null;

  function init(supabaseClient) {
    supabase = supabaseClient;
    const sel = document.getElementById('audienceDays');
    if (sel && !sel.dataset.bound) {
      sel.dataset.bound = '1';
      sel.addEventListener('change', () => load(Number(sel.value) || 30));
    }
    load(Number(sel && sel.value) || 30);
  }

  function getClient() {
    return supabase || (window.AdminAuth ? window.AdminAuth.getClient() : null);
  }

  function esc(s) {
    return String(s ?? '').replace(/[&<>"']/g, (c) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
  }

  function rowsHtml(items, cols) {
    if (!items || !items.length) {
      return '<tr><td colspan="' + cols + '" class="empty-state"><div class="empty-state-title">Sem dados ainda</div><div class="empty-state-desc">Os plays passam a gravar a partir da fatia 1. Cidade só aparece se o Cloudflare mandar header.</div></td></tr>';
    }
    return items.map((r) => {
      const cells = Object.values(r).map((v) => '<td>' + esc(v) + '</td>').join('');
      return '<tr>' + cells + '</tr>';
    }).join('');
  }

  async function load(days) {
    const status = document.getElementById('audienceStatus');
    try {
      const client = getClient();
      if (!client) throw new Error('Supabase client não disponível');
      if (status) status.textContent = 'Carregando…';
      const { data, error } = await client.rpc('get_admin_listen_stats', { p_days: days });
      if (error) throw error;
      const d = data && typeof data === 'object' ? data : {};
      if (d.ok === false) throw new Error(d.error || 'RPC recusou');

      const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
      set('audTotalPlays', d.total_plays ?? '—');
      set('audUnique', d.unique_listeners ?? '—');
      set('audLoggedIn', d.logged_in_plays ?? '—');
      set('audFrom', d.from || '—');

      const dayBody = document.getElementById('audByDay');
      if (dayBody) {
        dayBody.innerHTML = (d.by_day || []).length
          ? d.by_day.map((r) => '<tr><td>' + esc(r.day) + '</td><td>' + esc(r.plays) + '</td></tr>').join('')
          : rowsHtml([], 2);
      }
      const ctry = document.getElementById('audByCountry');
      if (ctry) {
        ctry.innerHTML = (d.by_country || []).length
          ? d.by_country.map((r) => '<tr><td>' + esc(r.country) + '</td><td>' + esc(r.plays) + '</td></tr>').join('')
          : rowsHtml([], 2);
      }
      const city = document.getElementById('audByCity');
      if (city) {
        city.innerHTML = (d.by_city || []).length
          ? d.by_city.map((r) => '<tr><td>' + esc(r.city) + '</td><td>' + esc(r.country) + '</td><td>' + esc(r.plays) + '</td></tr>').join('')
          : rowsHtml([], 3);
      }
      const tz = document.getElementById('audByTz');
      if (tz) {
        tz.innerHTML = (d.by_tz || []).length
          ? d.by_tz.map((r) => '<tr><td>' + esc(r.tz) + '</td><td>' + esc(r.plays) + '</td></tr>').join('')
          : rowsHtml([], 2);
      }
      const ep = document.getElementById('audByEpisode');
      if (ep) {
        ep.innerHTML = (d.by_episode || []).length
          ? d.by_episode.map((r) => '<tr><td>' + esc(r.episode_id) + '</td><td>' + esc(r.plays) + '</td></tr>').join('')
          : rowsHtml([], 2);
      }
      if (status) status.textContent = 'Últimos ' + (d.days || days) + ' dias';
    } catch (err) {
      console.error('[admin_audience]', err);
      if (status) status.textContent = 'Erro: ' + (err.message || err);
    }
  }

  window.adminAudience = { init, load };
  window.AdminAudience = window.adminAudience;
  return window.adminAudience;
})();
