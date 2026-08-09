import React, { useState } from 'react';
import { MainTab } from '../types';
import { Bell, Search, Plus, Power, Shield } from 'lucide-react';

interface HeaderProps {
  currentTab: MainTab;
  onNewAdClick: () => void;
  globalKillSwitch: boolean;
  onToggleGlobalKillSwitch: () => void;
  userRole: string;
}

export const Header: React.FC<HeaderProps> = ({
  currentTab,
  onNewAdClick,
  globalKillSwitch,
  onToggleGlobalKillSwitch,
  userRole,
}) => {
  const [showNotifications, setShowNotifications] = useState(false);

  const getPageTitle = () => {
    switch (currentTab) {
      case 'overview':
        return 'Dashboard Admin';
      case 'ads':
        return 'Monetização & Anúncios';
      case 'users':
        return 'Gestão de Usuários';
      case 'reports':
        return 'Relatórios & Métricas';
      default:
        return 'Dashboard Admin';
    }
  };

  return (
    <header className="h-20 border-b border-white/5 px-8 flex items-center justify-between bg-[#09090b]/80 backdrop-blur-md sticky top-0 z-40">
      {/* Title */}
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-bold text-white tracking-tight">{getPageTitle()}</h1>
      </div>

      {/* Right Actions */}
      <div className="flex items-center gap-4">
        {/* Search */}
        <div className="relative hidden md:block">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            placeholder="Pesquisar campanhas..."
            className="bg-[#18181b] border border-white/10 rounded-lg pl-9 pr-4 py-2 w-64 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-emerald-500 transition-colors"
          />
        </div>

        {/* Global Kill Switch */}
        <button
          onClick={onToggleGlobalKillSwitch}
          className={`px-3 py-2 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all border ${
            globalKillSwitch
              ? 'bg-rose-500/20 border-rose-500/50 text-rose-400 hover:bg-rose-500/30'
              : 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/20'
          }`}
          title={
            globalKillSwitch
              ? 'TODOS OS ANÚNCIOS PAUSADOS! Clique para reativar.'
              : 'Ads Ativos. Clique para acionar Kill-Switch Global.'
          }
        >
          <Power className="w-3.5 h-3.5" />
          <span>{globalKillSwitch ? 'KILL-SWITCH ATIVO' : 'ADS ATIVOS'}</span>
        </button>

        {/* Notifications Dropdown */}
        <div className="relative">
          <button
            onClick={() => setShowNotifications(!showNotifications)}
            className="text-slate-400 hover:text-white transition-colors p-2 rounded-lg hover:bg-white/5 relative"
            title="Notificações"
          >
            <Bell className="w-5 h-5" />
            <span className="w-2 h-2 bg-emerald-500 rounded-full absolute top-1.5 right-1.5"></span>
          </button>

          {showNotifications && (
            <div className="absolute right-0 mt-2 w-80 bg-[#0f0f12] border border-white/10 rounded-xl shadow-2xl p-4 z-50 text-xs text-slate-300">
              <div className="flex justify-between items-center mb-3 pb-2 border-b border-white/10 font-bold">
                <span className="text-white">Notificações do Sistema</span>
                <span className="text-[10px] text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full font-bold">
                  Live
                </span>
              </div>
              <div className="space-y-2 max-h-60 overflow-y-auto">
                <div className="p-2.5 rounded-lg bg-white/5 border border-white/5">
                  <p className="font-semibold text-white">Campanha Aprovada</p>
                  <p className="text-slate-400 mt-0.5">Supermercado Ideal iniciou novo lote VIP.</p>
                  <span className="text-[10px] text-slate-500">Há 12 min</span>
                </div>
                <div className="p-2.5 rounded-lg bg-white/5 border border-white/5">
                  <p className="font-semibold text-white">Nova Assinatura VIP</p>
                  <p className="text-slate-400 mt-0.5">Carlos Eduardo renovou plano Anual.</p>
                  <span className="text-[10px] text-slate-500">Há 45 min</span>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Primary Action Button */}
        <button
          onClick={onNewAdClick}
          className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-sm font-semibold transition-colors flex items-center gap-2 shadow-lg shadow-emerald-950/40"
        >
          <Plus className="w-4 h-4" />
          <span>Novo Anúncio</span>
        </button>
      </div>
    </header>
  );
};
