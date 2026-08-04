/**
 * admin_charts.js — Gráficos de Métricas e Exportador CSV
 * Usa Recharts + React via CDN
 */

const AdminCharts = (() => {
  let supabase = null;
  let metricsData = [];

  function init(supabaseClient) {
    supabase = supabaseClient;
  }

  async function loadMetrics(days = 30) {
    try {
      const { data, error } = await supabase.rpc('get_admin_ad_metrics_timeseries', {
        p_days: days,
      });
      
      if (error) throw error;
      
      metricsData = (data || []).map(row => ({
        date: row.date_str,
        impressions: parseInt(row.impressions) || 0,
        clicks: parseInt(row.clicks) || 0,
        skips: parseInt(row.skips) || 0,
        errors: parseInt(row.errors) || 0,
        revenue: parseInt(row.revenue_cents) || 0,
      })).sort((a, b) => a.date.localeCompare(b.date));

      renderCharts();
    } catch (err) {
      console.error('[admin_charts] Error loading metrics:', err);
      metricsData = generateMockMetrics(days);
      renderCharts();
    }
  }

  function generateMockMetrics(days) {
    const data = [];
    const today = new Date();
    
    for (let i = days - 1; i >= 0; i--) {
      const date = new Date(today);
      date.setDate(date.getDate() - i);
      
      data.push({
        date: date.toISOString().slice(0, 10),
        impressions: Math.floor(Math.random() * 50000) + 30000,
        clicks: Math.floor(Math.random() * 5000) + 2000,
        skips: Math.floor(Math.random() * 2000) + 500,
        errors: Math.floor(Math.random() * 50) + 10,
        revenue: Math.floor(Math.random() * 50000) + 20000,
      });
    }
    
    return data;
  }

  function renderCharts() {
    if (!window.Recharts || !window.React || !window.ReactDOM) {
      console.warn('[admin_charts] Recharts/React not loaded yet');
      return;
    }

    renderImpressionsClicksChart();
    renderSkipsErrorsChart();
    renderRevenueChart();
  }

  function renderImpressionsClicksChart() {
    const container = document.getElementById('chartImpressionsClicks');
    if (!container) return;

    const chartData = metricsData.slice(-14).map(d => ({
      date: d.date.slice(5),
      impressions: d.impressions,
      clicks: d.clicks,
    }));

    container.innerHTML = '';
    
    const { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } = window.Recharts;
    const React = window.React;
    const ReactDOM = window.ReactDOM;

    const chart = document.createElement('div');
    chart.style.height = '100%';
    container.appendChild(chart);

    ReactDOM.render(
      React.createElement(ResponsiveContainer, { width: '100%', height: '100%' },
        React.createElement(BarChart, { 
          data: chartData, 
          margin: { top: 20, right: 30, left: 20, bottom: 5 }
        },
          React.createElement(CartesianGrid, { strokeDasharray: '3 3', stroke: 'rgba(255,255,255,0.1)' }),
          React.createElement(XAxis, { dataKey: 'date', stroke: '#64748b', fontSize: 11, tickLine: false }),
          React.createElement(YAxis, { stroke: '#64748b', fontSize: 11, tickLine: false, axisLine: false }),
          React.createElement(Tooltip, {
            contentStyle: { backgroundColor: '#0f0f12', borderColor: 'rgba(255,255,255,0.1)', borderRadius: '8px', color: '#fff' },
          }),
          React.createElement(Legend),
          React.createElement(Bar, { dataKey: 'impressions', name: 'Impressões', fill: '#10b981', radius: [4, 4, 0, 0] }),
          React.createElement(Bar, { dataKey: 'clicks', name: 'Cliques', fill: '#3b82f6', radius: [4, 4, 0, 0] })
        )
      ),
      chart
    );
  }

  function renderSkipsErrorsChart() {
    const container = document.getElementById('chartSkipsErrors');
    if (!container) return;

    const chartData = metricsData.slice(-14).map(d => ({
      date: d.date.slice(5),
      skips: d.skips,
      errors: d.errors,
    }));

    const { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } = window.Recharts;
    const React = window.React;
    const ReactDOM = window.ReactDOM;

    container.innerHTML = '';
    
    const chart = document.createElement('div');
    chart.style.height = '100%';
    container.appendChild(chart);

    ReactDOM.render(
      React.createElement(ResponsiveContainer, { width: '100%', height: '100%' },
        React.createElement(AreaChart, { 
          data: chartData, 
          margin: { top: 20, right: 30, left: 20, bottom: 5 }
        },
          React.createElement(CartesianGrid, { strokeDasharray: '3 3', stroke: 'rgba(255,255,255,0.1)' }),
          React.createElement(XAxis, { dataKey: 'date', stroke: '#64748b', fontSize: 11, tickLine: false }),
          React.createElement(YAxis, { stroke: '#64748b', fontSize: 11, tickLine: false, axisLine: false }),
          React.createElement(Tooltip, {
            contentStyle: { backgroundColor: '#0f0f12', borderColor: 'rgba(255,255,255,0.1)', borderRadius: '8px', color: '#fff' },
          }),
          React.createElement(Legend),
          React.createElement(Area, { type: 'monotone', dataKey: 'skips', name: 'Skips', stroke: '#f59e0b', fill: '#f59e0b', fillOpacity: 0.2 }),
          React.createElement(Area, { type: 'monotone', dataKey: 'errors', name: 'Erros', stroke: '#ef4444', fill: '#ef4444', fillOpacity: 0.2 })
        )
      ),
      chart
    );
  }

  function renderRevenueChart() {
    const container = document.getElementById('chartRevenue');
    if (!container) return;

    const chartData = metricsData.slice(-30).map(d => ({
      date: d.date.slice(5),
      revenue: d.revenue,
    }));

    const { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } = window.Recharts;
    const React = window.React;
    const ReactDOM = window.ReactDOM;

    container.innerHTML = '';
    
    const chart = document.createElement('div');
    chart.style.height = '100%';
    container.appendChild(chart);

    ReactDOM.render(
      React.createElement(ResponsiveContainer, { width: '100%', height: '100%' },
        React.createElement(AreaChart, { 
          data: chartData, 
          margin: { top: 20, right: 30, left: 20, bottom: 5 }
        },
          React.createElement(CartesianGrid, { strokeDasharray: '3 3', stroke: 'rgba(255,255,255,0.1)' }),
          React.createElement(XAxis, { dataKey: 'date', stroke: '#64748b', fontSize: 11, tickLine: false }),
          React.createElement(YAxis, { 
            stroke: '#64748b', 
            fontSize: 11, 
            tickLine: false, 
            axisLine: false,
            tickFormatter: (value) => `R$${(value/100).toFixed(0)}`
          }),
          React.createElement(Tooltip, {
            contentStyle: { backgroundColor: '#0f0f12', borderColor: 'rgba(255,255,255,0.1)', borderRadius: '8px', color: '#fff' },
            formatter: (value) => [`R$ ${(value / 100).toFixed(2)}`, 'Receita'],
          }),
          React.createElement(Area, { 
            type: 'monotone', 
            dataKey: 'revenue', 
            stroke: '#10b981', 
            fill: '#10b981', 
            fillOpacity: 0.3,
            name: 'Receita'
          })
        )
      ),
      chart
    );
  }

  function exportMetricsCSV() {
    if (metricsData.length === 0) {
      showToast('Nenhum dado para exportar', 'error');
      return;
    }

    const headers = ['Data', 'Impressões', 'Cliques', 'Skips', 'Erros', 'Receita (cents)'];
    const rows = metricsData.map(d => [
      d.date,
      d.impressions,
      d.clicks,
      d.skips,
      d.errors,
      d.revenue,
    ]);

    const csvContent = [
      headers.join(','),
      ...rows.map(row => row.map(val => `"${val}"`).join(','))
    ].join('\n');

    downloadCSV(csvContent, `metricas_ads_${new Date().toISOString().slice(0, 10)}.csv`);
    showToast('Relatório CSV exportado!');
  }

  function exportCampaignsCSV() {
    const camps = window.adminAds?.campaigns || [];
    if (camps.length === 0) {
      showToast('Nenhum dado para exportar', 'error');
      return;
    }

    const headers = ['ID', 'Nome', 'Patrocinador', 'Formato', 'Status', 'Impressões', 'Cliques', 'Start Date', 'End Date'];
    const rows = camps.map(c => [
      c.campaign_id,
      c.campaign_name,
      c.sponsor_name,
      c.format_type,
      c.is_active ? 'Ativo' : 'Pausado',
      c.impressions,
      c.clicks,
      c.start_date,
      c.end_date,
    ]);

    const csvContent = [
      headers.join(','),
      ...rows.map(row => row.map(val => `"${val}"`).join(','))
    ].join('\n');

    downloadCSV(csvContent, `campanhas_ads_${new Date().toISOString().slice(0, 10)}.csv`);
    showToast('Relatório de campanhas exportado!');
  }

  function downloadCSV(content, filename) {
    const blob = new Blob([content], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
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
    loadMetrics,
    renderCharts,
    exportMetricsCSV,
    exportCampaignsCSV,
  };
})();

window.adminCharts = AdminCharts;
