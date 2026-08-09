import React, { useState } from 'react';
import { DailyMetrics, Campaign, Subscription } from '../types';
import { FileSpreadsheet, Download, Calendar, BarChart2, TrendingUp, PieChart as PieIcon, ShieldCheck } from 'lucide-react';
import { AreaChart, Area, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend, PieChart, Pie, Cell } from 'recharts';

interface ReportsTabProps {
  metrics: DailyMetrics[];
  campaigns: Campaign[];
  subscriptions: Subscription[];
  onExportCSV: () => void;
  onExportCampaignsCSV: () => void;
  onExportUsersCSV: () => void;
}

export const ReportsTab: React.FC<ReportsTabProps> = ({
  metrics,
  campaigns,
  subscriptions,
  onExportCSV,
  onExportCampaignsCSV,
  onExportUsersCSV,
}) => {
  const [period, setPeriod] = useState<string>('7d');

  // Ad Format revenue stats
  const formatData = [
    { name: 'Áudio Ads', value: 45, color: '#4edea3' },
    { name: 'Banner Display', value: 35, color: '#3b82f6' },
    { name: 'Vídeo Pre-roll', value: 20, color: '#a855f7' }
  ];

  return (
    <div className="space-y-6">
      {/* Header & Export Bar */}
      <div className="bg-white/5 border border-white/10 rounded-2xl p-6 shadow-xl flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h2 className="text-xl font-bold text-white">Relatórios & Análise Estatística</h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Métricas detalhadas de impressões, cliques, CTR, skips, erros e exportação de relatórios.
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <div className="flex p-1 bg-[#18181b] rounded-xl border border-white/10">
            <button
              onClick={() => setPeriod('7d')}
              className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-all ${
                period === '7d' ? 'bg-emerald-600 text-white font-bold' : 'text-slate-400 hover:text-white'
              }`}
            >
              Últimos 7 dias
            </button>
            <button
              onClick={() => setPeriod('30d')}
              className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-all ${
                period === '30d' ? 'bg-emerald-600 text-white font-bold' : 'text-slate-400 hover:text-white'
              }`}
            >
              Mês Atual
            </button>
          </div>

          <button
            onClick={onExportCSV}
            className="px-4 py-2 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white transition-colors flex items-center gap-2"
          >
            <FileSpreadsheet className="w-4 h-4" />
            <span>Exportar CSV de Métricas</span>
          </button>
        </div>
      </div>

      {/* CSV Quick Download Section */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-white/5 border border-white/10 rounded-2xl p-4 flex items-center justify-between">
          <div>
            <p className="font-bold text-white text-xs">Relatório de Métricas Diárias</p>
            <p className="text-[10px] text-slate-400">Impressões, Clicks, CTR e Receita</p>
          </div>
          <button
            onClick={onExportCSV}
            className="p-2 bg-[#18181b] hover:bg-white/10 text-emerald-400 rounded-lg border border-white/10 transition-colors"
            title="Baixar CSV"
          >
            <Download className="w-4 h-4" />
          </button>
        </div>

        <div className="bg-white/5 border border-white/10 rounded-2xl p-4 flex items-center justify-between">
          <div>
            <p className="font-bold text-white text-xs">Relatório de Anúncios & Campanhas</p>
            <p className="text-[10px] text-slate-400">Desempenho por patrocinador</p>
          </div>
          <button
            onClick={onExportCampaignsCSV}
            className="p-2 bg-[#18181b] hover:bg-white/10 text-emerald-400 rounded-lg border border-white/10 transition-colors"
            title="Baixar CSV"
          >
            <Download className="w-4 h-4" />
          </button>
        </div>

        <div className="bg-white/5 border border-white/10 rounded-2xl p-4 flex items-center justify-between">
          <div>
            <p className="font-bold text-white text-xs">Base de Assinantes & Planos</p>
            <p className="text-[10px] text-slate-400">Usuários VIP, Premium e Free</p>
          </div>
          <button
            onClick={onExportUsersCSV}
            className="p-2 bg-[#18181b] hover:bg-white/10 text-emerald-400 rounded-lg border border-white/10 transition-colors"
            title="Baixar CSV"
          >
            <Download className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Main Bar Chart: Impressions vs Clicks */}
      <div className="bg-white/5 border border-white/10 rounded-2xl p-6 shadow-xl">
        <div className="flex justify-between items-center mb-6">
          <div>
            <h3 className="text-base font-bold text-white">Impressões vs. Cliques Diários</h3>
            <p className="text-xs text-slate-400">Volume total de visualizações de anúncios vs interações ativas</p>
          </div>
          <span className="text-xs font-mono text-emerald-400 font-bold">CTR Médio: 9.15%</span>
        </div>

        <div className="h-72 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={metrics}>
              <XAxis dataKey="date" stroke="#71717a" fontSize={11} tickLine={false} />
              <YAxis stroke="#71717a" fontSize={11} tickLine={false} axisLine={false} />
              <Tooltip
                contentStyle={{ backgroundColor: '#09090b', borderColor: 'rgba(255,255,255,0.1)', borderRadius: '12px' }}
                labelStyle={{ color: '#fff', fontWeight: 'bold' }}
              />
              <Legend wrapperStyle={{ fontSize: '12px', paddingTop: '10px' }} />
              <Bar dataKey="impressions" name="Impressões Exibidas" fill="#10b981" radius={[4, 4, 0, 0]} />
              <Bar dataKey="clicks" name="Cliques Gerados" fill="#3b82f6" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Grid: Skips & Error Rates + Revenue Distribution */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
        {/* CTR & Skips Chart (8 cols) */}
        <div className="xl:col-span-8 bg-white/5 border border-white/10 rounded-2xl p-6 shadow-xl">
          <h3 className="text-base font-bold text-white mb-1">Evolução de Skips & Erros de Reprodução</h3>
          <p className="text-xs text-slate-400 mb-6">Métricas de rejeição e falhas de streaming no player de áudio</p>

          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={metrics}>
                <XAxis dataKey="date" stroke="#71717a" fontSize={11} tickLine={false} />
                <YAxis stroke="#71717a" fontSize={11} tickLine={false} axisLine={false} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#09090b', borderColor: 'rgba(255,255,255,0.1)', borderRadius: '12px' }}
                />
                <Legend wrapperStyle={{ fontSize: '12px' }} />
                <Area type="monotone" dataKey="skips" stroke="#f59e0b" fill="#f59e0b" fillOpacity={0.2} name="Anúncios Pulados (Skips)" />
                <Area type="monotone" dataKey="errors" stroke="#ef4444" fill="#ef4444" fillOpacity={0.2} name="Erros de Play" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Ad Format Pie Chart (4 cols) */}
        <div className="xl:col-span-4 bg-white/5 border border-white/10 rounded-2xl p-6 shadow-xl flex flex-col justify-between">
          <div>
            <h3 className="text-base font-bold text-white mb-1">Distribuição por Formato</h3>
            <p className="text-xs text-slate-400 mb-4">Participação na receita total de publicidade</p>

            <div className="h-52 w-full flex items-center justify-center">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={formatData}
                    cx="50%"
                    cy="50%"
                    innerRadius={50}
                    outerRadius={75}
                    paddingAngle={5}
                    dataKey="value"
                  >
                    {formatData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{ backgroundColor: '#09090b', borderColor: 'rgba(255,255,255,0.1)', borderRadius: '12px' }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="space-y-2 border-t border-white/10 pt-3">
            {formatData.map((item, idx) => (
              <div key={idx} className="flex justify-between items-center text-xs">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: item.color }}></span>
                  <span className="text-slate-300">{item.name}</span>
                </div>
                <span className="font-bold text-white">{item.value}%</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
