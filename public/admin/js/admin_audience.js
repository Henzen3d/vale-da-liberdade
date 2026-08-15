/**
 * admin_audience.js — Aba Audiência (listen_events).
 */
const AdminAudience = (() => {
  let supabase = null;
  let map = null;
  let markers = null;

  function init(supabaseClient) {
    supabase = supabaseClient;
    const sel = document.getElementById('audienceDays');
    if (sel && !sel.dataset.bound) {
      sel.dataset.bound = '1';
      sel.addEventListener('change', () => load(Number(sel.value) || 30));
    }
    load(Number(sel && sel.value) || 30);
  }

  function ensureMap() {
    const el = document.getElementById('audienceMap');
    if (!el || typeof L === 'undefined') return null;
    if (map) return map;
    map = L.map(el, { scrollWheelZoom: false, attributionControl: true }).setView([-14.2, -51.9], 4);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 12,
      attribution: '&copy; OpenStreetMap',
    }).addTo(map);
    markers = L.layerGroup().addTo(map);
    return map;
  }

  function renderMap(points) {
    const hint = document.getElementById('audienceMapHint');
    const m = ensureMap();
    if (!m || !markers) {
      if (hint) hint.textContent = 'Leaflet ainda não carregou — recarregue a aba.';
      return;
    }
    markers.clearLayers();
    const pts = Array.isArray(points) ? points : [];
    if (!pts.length) {
      if (hint) hint.textContent = 'Sem pontos neste período.';
      setTimeout(() => m.invalidateSize(), 80);
      return;
    }
    const bounds = [];
    const maxPlays = Math.max(...pts.map((p) => Number(p.plays) || 1));
    pts.forEach((p) => {
      const lat = Number(p.lat);
      const lon = Number(p.lon);
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
      const plays = Number(p.plays) || 1;
      const r = 8 + Math.round(18 * Math.sqrt(plays / maxPlays));
      const color = p.level === 'city' ? '#34d399' : (p.level === 'country' ? '#60a5fa' : '#fbbf24');
      const circle = L.circleMarker([lat, lon], {
        radius: r,
        color,
        weight: 2,
        fillColor: color,
        fillOpacity: 0.45,
      });
      circle.bindPopup('<strong>' + esc(p.label) + '</strong><br>' + plays + ' play(s) · ' + esc(p.level));
      circle.addTo(markers);
      bounds.push([lat, lon]);
    });
    if (hint) {
      hint.textContent = pts.length + ' ponto(s) · verde=cidade · azul=país · amarelo=só fuso';
    }
    setTimeout(() => {
      m.invalidateSize();
      if (bounds.length === 1) m.setView(bounds[0], 5);
      else if (bounds.length > 1) m.fitBounds(bounds, { padding: [28, 28], maxZoom: 6 });
    }, 80);
  }

  function onShow() {
    if (map) setTimeout(() => map.invalidateSize(), 60);
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
      const avg = Number(d.avg_listened_sec) || 0;
      set('audAvgTime', avg ? (avg >= 60 ? Math.round(avg / 60) + ' min' : avg + 's') : '—');
      set('audSessions', (d.sessions || 0) + ' sessões');
      set('audCompletion', (d.completion_pct != null ? d.completion_pct : '—') + '%');

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
      const src = document.getElementById('audBySource');
      if (src) {
        src.innerHTML = (d.by_source || []).length
          ? d.by_source.map((r) => '<tr><td>' + esc(r.source) + '</td><td>' + esc(r.plays) + '</td></tr>').join('')
          : rowsHtml([], 2);
      }
      const ep = document.getElementById('audByEpisode');
      if (ep) {
        ep.innerHTML = (d.by_episode || []).length
          ? d.by_episode.map((r) => {
              const avg = Number(r.avg_sec) || 0;
              const avgLabel = avg >= 60 ? Math.round(avg / 60) + ' min' : avg + 's';
              return '<tr><td>' + esc(r.episode_id) + '</td><td>' + esc(r.plays) + '</td><td>' + esc(avgLabel) + '</td><td>' + esc(r.completed || 0) + '</td></tr>';
            }).join('')
          : rowsHtml([], 4);
      }
      if (status) status.textContent = 'Últimos ' + (d.days || days) + ' dias';

      try {
        const geo = await client.rpc('get_admin_listen_map', { p_days: days });
        if (geo.error) throw geo.error;
        const g = geo.data && typeof geo.data === 'object' ? geo.data : {};
        if (g.ok === false) throw new Error(g.error || 'mapa recusou');
        renderMap(g.points || []);
        const hint = document.getElementById('audienceMapHint');
        if (hint && g.unmapped) {
          hint.textContent += ' · ' + g.unmapped + ' play(s) sem centroide';
        }
      } catch (mapErr) {
        console.warn('[admin_audience] mapa:', mapErr);
      }
    } catch (err) {
      console.error('[admin_audience]', err);
      if (status) status.textContent = 'Erro: ' + (err.message || err);
    }
  }

  window.adminAudience = { init, load, onShow };
  window.AdminAudience = window.adminAudience;
  return window.adminAudience;
})();
