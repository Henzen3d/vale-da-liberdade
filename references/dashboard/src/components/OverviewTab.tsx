import React from 'react';
import { Campaign, Sponsor, Subscription, DailyMetrics } from '../types';
import { DollarSign, Eye, MousePointerClick, TrendingUp, Power, FileSpreadsheet, Plus, AlertCircle, CheckCircle2 } from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';

interface OverviewTabProps {
  campaigns: Campaign[];
  sponsors: Sponsor[];
  subscriptions: Subscription[];
  metrics: DailyMetrics[];
  globalKillSwitch: boolean;
  onToggleGlobalKillSwitch: () => void;
  onToggleCampaignActive: (id: string) => void;
  onNavigateToCreateAd: () => void;
  onExportCSV: () => void;
}

export const OverviewTab: React.FC<OverviewTabProps> = ({
  campaigns,
  sponsors,
  subscriptions,
  metrics,
  globalKillSwitch,
  onToggleGlobalKillSwitch,
  onToggleCampaignActive,
  onNavigateToCreateAd,
  onExportCSV,
}) => {
  const activeCampaigns = campaigns.filter(c => c.is_active && !globalKillSwitch);
  const activeSponsors = sponsors.filter(s => s.is_active);
  const totalImpressions = campaigns.reduce((acc, c) => acc + c.impressions, 0);
  const totalClicks = campaigns.reduce((acc, c) => acc + c.clicks, 0);
  const avgCtr = totalImpressions > 0 ? ((totalClicks / totalImpressions) * 100).toFixed(2) : '0';
  const totalRevenue = metrics.reduce((acc, m) => acc + m.revenue, 0);
  const activeSubscribersCount = subscriptions.filter(s => s.status === 'active' && s.plan !== 'free').length;

  return (
    <div className="space-y-6">
      {/* Top Banner / Hero */}
      <div className="bg-white/5 backdrop-blur-md border border-white/10 rounded-2xl p-6 relative overflow-hidden">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 relative z-10">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 uppercase tracking-wider">
                Sistemas Hermes Admin
              </span>
              <span className="text-xs text-slate-400">Jornal Vale da Liberdade</span>
            </div>
            <h2 className="text-2xl font-bold text-white tracking-tight">Visão Geral & Métricas</h2>
            <p className="text-sm text-slate-400 mt-1">
              Monetização de anúncios, assinaturas pagas e métricas de engajamento em tempo real.
            </p>
          </div>

          <div className="flex flex-wrap gap-3">
            <button
              onClick={onToggleGlobalKillSwitch}
              className={`px-4 py-2 rounded-lg text-xs font-bold border transition-all flex items-center gap-2 ${
                globalKillSwitch
                  ? 'bg-rose-500/20 border-rose-500/40 text-rose-400 hover:bg-rose-500/30'
                  : 'bg-[#18181b] border-white/10 text-white hover:bg-white/5'
              }`}
            >
              <Power className="w-4 h-4" />
              <span>{globalKillSwitch ? 'DESATIVAR KILL-SWITCH' : 'KILL-SWITCH GLOBAL'}</span>
            </button>

            <button
              onClick={onExportCSV}
              className="px-4 py-2 rounded-lg text-xs font-semibold bg-[#18181b] border border-white/10 text-slate-200 hover:bg-white/5 transition-colors flex items-center gap-2"
            >
              <FileSpreadsheet className="w-4 h-4 text-emerald-400" />
              <span>Exportar CSV</span>
            </button>

            <button
              onClick={onNavigateToCreateAd}
              className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-semibold transition-colors flex items-center gap-2"
            >
              <Plus className="w-4 h-4" />
              <span>Novo Anúncio</span>
            </button>
          </div>
        </div>
      </div>

      {/* Kill Switch Alert Banner */}
      {globalKillSwitch && (
        <div className="bg-rose-500/10 border border-rose-500/30 rounded-2xl p-4 flex items-center justify-between text-rose-300">
          <div className="flex items-center gap-3">
            <AlertCircle className="w-6 h-6 text-rose-400 shrink-0" />
            <div>
              <p className="font-bold text-sm text-white">KILL-SWITCH GLOBAL ATIVO</p>
              <p className="text-xs text-slate-300">
                Todas as exibições de publicidade no portal do Jornal Vale da Liberdade foram pausadas.
              </p>
            </div>
          </div>
          <button
            onClick={onToggleGlobalKillSwitch}
            className="px-3 py-1.5 bg-rose-600 text-white rounded-lg text-xs font-bold hover:bg-rose-500 transition-colors"
          >
            Reativar Anúncios
          </button>
        </div>
      )}

      {/* KPI Cards Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        {/* Card 1 */}
        <div className="bg-white/5 backdrop-blur-md border border-white/10 p-5 rounded-2xl">
          <p className="text-slate-400 text-sm">Receita Mensal</p>
          <div className="flex items-end justify-between mt-1">
            <p className="text-2xl font-bold text-white">R$ {totalRevenue.toLocaleString('pt-BR')}</p>
            <span className="text-emerald-400 text-xs font-bold">+12% ↑</span>
          </div>
        </div>

        {/* Card 2 */}
        <div className="bg-white/5 backdrop-blur-md border border-white/10 p-5 rounded-2xl">
          <p className="text-slate-400 text-sm">Anúncios Ativos</p>
          <div className="flex items-end justify-between mt-1">
            <p className="text-2xl font-bold text-white">{activeCampaigns.length}</p>
            <span className="text-slate-400 text-xs">Total {campaigns.length}</span>
          </div>
        </div>

        {/* Card 3 */}
        <div className="bg-white/5 backdrop-blur-md border border-white/10 p-5 rounded-2xl">
          <p className="text-slate-400 text-sm">Novos Assinantes</p>
          <div className="flex items-end justify-between mt-1">
            <p className="text-2xl font-bold text-white">{activeSubscribersCount}</p>
            <span className="text-emerald-400 text-xs font-bold">+8% ↑</span>
          </div>
        </div>

        {/* Card 4 */}
        <div className="bg-white/5 backdrop-blur-md border border-white/10 p-5 rounded-2xl">
          <p className="text-slate-400 text-sm">Taxa de Cliques (CTR)</p>
          <div className="flex items-end justify-between mt-1">
            <p className="text-2xl font-bold text-white">{avgCtr}%</p>
            <span className="text-emerald-400 text-xs font-bold">+1.4% ↑</span>
          </div>
        </div>
      </div>

      {/* Main Grid: Revenue Chart & Side Cards */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Revenue Chart */}
        <div className="lg:col-span-2 bg-white/5 border border-white/10 p-6 rounded-2xl">
          <div className="flex justify-between items-center mb-6">
            <div>
              <h3 className="font-bold text-white text-base">Evolução de Desempenho & Receita</h3>
              <p className="text-xs text-slate-400">Histórico de receita de anúncios e audiência diária</p>
            </div>
            <span className="text-xs text-emerald-400 font-bold bg-emerald-500/10 px-3 py-1 rounded-full border border-emerald-500/20">
              Supabase Live
            </span>
          </div>

          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={metrics}>
                <defs>
                  <linearGradient id="colorRev" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#10b981" stopOpacity={0.0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="date" stroke="#64748b" fontSize={11} tickLine={false} />
                <YAxis stroke="#64748b" fontSize={11} tickLine={false} axisLine={false} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#0f0f12', borderColor: 'rgba(255,255,255,0.1)', borderRadius: '12px', color: '#fff' }}
                />
                <Area type="monotone" dataKey="revenue" stroke="#10b981" strokeWidth={3} fillOpacity={1} fill="url(#colorRev)" name="Receita (R$)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Right Column: Desempenho Semanal & Database Status */}
        <div className="space-y-6">
          <div className="bg-white/5 border border-white/10 p-6 rounded-2xl">
            <h3 className="text-sm font-bold mb-4 text-white">Desempenho Semanal</h3>
            <div className="flex items-end justify-between h-24 gap-2">
              <div className="w-full bg-emerald-500/20 rounded-t h-[40%]"></div>
              <div className="w-full bg-emerald-500/20 rounded-t h-[65%]"></div>
              <div className="w-full bg-emerald-500/20 rounded-t h-[50%]"></div>
              <div className="w-full bg-emerald-500/20 rounded-t h-[85%]"></div>
              <div className="w-full bg-emerald-500/60 rounded-t h-[95%]"></div>
              <div className="w-full bg-emerald-500/20 rounded-t h-[45%]"></div>
              <div className="w-full bg-emerald-500/10 rounded-t h-[30%]"></div>
            </div>
            <div className="flex justify-between text-[10px] text-slate-500 mt-2 font-mono">
              <span>SEG</span><span>TER</span><span>QUA</span><span>QUI</span><span>SEX</span><span>SAB</span><span>DOM</span>
            </div>
          </div>

          <div className="bg-emerald-600 p-6 rounded-2xl text-white relative overflow-hidden shadow-lg shadow-emerald-950/30">
            <div className="relative z-10">
              <h3 className="text-sm font-bold">Backup Supabase</h3>
              <p className="text-xs mt-1 opacity-90">Última sincronização há 12 min.</p>
              <button
                onClick={onExportCSV}
                className="mt-4 px-4 py-2 bg-white text-emerald-600 hover:bg-slate-100 rounded-lg text-xs font-bold w-full transition-colors"
              >
                Ver Logs Database
              </button>
            </div>
            <div className="absolute -right-4 -bottom-4 w-24 h-24 bg-white/10 rounded-full blur-2xl pointer-events-none"></div>
          </div>
        </div>
      </div>

      {/* Campanhas Recentes Table */}
      <div className="bg-white/5 border border-white/10 rounded-2xl overflow-hidden">
        <div className="px-6 py-4 border-b border-white/10 flex justify-between items-center">
          <div>
            <h2 className="font-bold text-white text-base">Campanhas Recentes</h2>
            <p className="text-xs text-slate-400">Gerenciamento direto do Kill-Switch individual</p>
          </div>
          <button
            onClick={onNavigateToCreateAd}
            className="text-xs text-emerald-400 font-semibold underline hover:text-emerald-300"
          >
            Ver todas
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead className="bg-white/5 text-xs uppercase tracking-wider text-slate-400 font-semibold">
              <tr>
                <th className="px-6 py-3 font-semibold">Patrocinador</th>
                <th className="px-6 py-3 font-semibold">Plano</th>
                <th className="px-6 py-3 font-semibold">Status</th>
                <th className="px-6 py-3 font-semibold text-right">Ação</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 text-sm">
              {campaigns.map(c => {
                const isPaused = !c.is_active || globalKillSwitch;

                return (
                  <tr key={c.id} className="hover:bg-white/5 transition-colors">
                    <td className="px-6 py-4 font-medium text-white">{c.sponsor_name}</td>
                    <td className="px-6 py-4 text-slate-300">{c.name} ({c.format.toUpperCase()})</td>
                    <td className="px-6 py-4">
                      <span
                        className={`px-2.5 py-1 text-[10px] rounded-full uppercase font-bold border ${
                          isPaused
                            ? 'bg-amber-500/10 text-amber-500 border-amber-500/20'
                            : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                        }`}
                      >
                        {isPaused ? 'Pausado' : 'Ativo'}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <button
                        onClick={() => onToggleCampaignActive(c.id)}
                        disabled={globalKillSwitch}
                        className={`px-3 py-1 text-xs rounded transition-all border font-medium ${
                          isPaused
                            ? 'bg-slate-500/10 text-slate-300 hover:bg-white/10 border-white/10'
                            : 'bg-rose-500/10 text-rose-400 hover:bg-rose-500 hover:text-white border-rose-500/20'
                        } ${globalKillSwitch ? 'opacity-50 cursor-not-allowed' : ''}`}
                      >
                        {isPaused ? 'Reativar' : 'Kill-Switch'}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
