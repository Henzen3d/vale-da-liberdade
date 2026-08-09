import React from 'react';
import { MainTab } from '../types';
import { LayoutDashboard, DollarSign, Users, BarChart3, User, Settings, ShieldCheck, ShieldAlert } from 'lucide-react';

interface SidebarProps {
  currentTab: MainTab;
  onSelectTab: (tab: MainTab) => void;
  isAdmin: boolean;
  onToggleRoleSim: () => void;
  isCollapsed: boolean;
  onToggleCollapse: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  currentTab,
  onSelectTab,
  isAdmin,
  onToggleRoleSim,
  isCollapsed,
  onToggleCollapse,
}) => {
  return (
    <aside
      className={`fixed left-0 top-0 h-screen bg-[#0f0f12] border-r border-white/5 transition-all duration-300 ease-in-out z-50 flex flex-col ${
        isCollapsed ? 'w-20' : 'w-64'
      }`}
    >
      {/* Header / Brand */}
      <div className="p-6 flex items-center justify-between border-b border-white/5">
        {!isCollapsed ? (
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-emerald-500 rounded-lg flex items-center justify-center font-bold text-black text-sm shrink-0">
              V
            </div>
            <div>
              <span className="font-bold text-lg tracking-tight text-white block leading-none">
                Vale Liberdade
              </span>
              <span className="text-[11px] text-slate-400 font-medium">Hermes Admin</span>
            </div>
          </div>
        ) : (
          <div className="w-8 h-8 bg-emerald-500 rounded-lg flex items-center justify-center font-bold text-black text-sm mx-auto">
            V
          </div>
        )}
        <button
          onClick={onToggleCollapse}
          className="text-slate-400 hover:text-white transition-colors p-1.5 rounded-lg hover:bg-white/5"
          title={isCollapsed ? 'Expandir Menu' : 'Recolher Menu'}
        >
          {isCollapsed ? '→' : '←'}
        </button>
      </div>

      {/* Navigation Links */}
      <nav className="flex-1 px-4 space-y-1.5 mt-4">
        <button
          onClick={() => onSelectTab('overview')}
          className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all text-sm font-medium ${
            currentTab === 'overview'
              ? 'bg-white/5 text-emerald-400 border border-white/10'
              : 'text-slate-400 hover:text-white hover:bg-white/5'
          }`}
          title="Visão Geral"
        >
          <LayoutDashboard className="w-5 h-5 shrink-0" />
          {!isCollapsed && <span>Visão Geral</span>}
        </button>

        <button
          onClick={() => onSelectTab('ads')}
          className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all text-sm font-medium ${
            currentTab === 'ads'
              ? 'bg-white/5 text-emerald-400 border border-white/10'
              : 'text-slate-400 hover:text-white hover:bg-white/5'
          }`}
          title="Monetização Ads"
        >
          <DollarSign className="w-5 h-5 shrink-0" />
          {!isCollapsed && <span>Monetização Ads</span>}
        </button>

        <button
          onClick={() => onSelectTab('users')}
          className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all text-sm font-medium ${
            currentTab === 'users'
              ? 'bg-white/5 text-emerald-400 border border-white/10'
              : 'text-slate-400 hover:text-white hover:bg-white/5'
          }`}
          title="Usuários"
        >
          <Users className="w-5 h-5 shrink-0" />
          {!isCollapsed && <span>Usuários</span>}
        </button>

        <button
          onClick={() => onSelectTab('reports')}
          className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all text-sm font-medium ${
            currentTab === 'reports'
              ? 'bg-white/5 text-emerald-400 border border-white/10'
              : 'text-slate-400 hover:text-white hover:bg-white/5'
          }`}
          title="Relatórios"
        >
          <BarChart3 className="w-5 h-5 shrink-0" />
          {!isCollapsed && <span>Relatórios</span>}
        </button>
      </nav>

      {/* Role Switcher & RBAC Status */}
      <div className="px-4 py-2">
        <button
          onClick={onToggleRoleSim}
          className={`w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl text-xs font-semibold border transition-all ${
            isAdmin
              ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400 hover:bg-emerald-500/20'
              : 'bg-rose-500/10 border-rose-500/20 text-rose-400 hover:bg-rose-500/20'
          }`}
          title="Clique para alternar simulação de Permissão Admin/Leitor"
        >
          <div className="flex items-center gap-2">
            {isAdmin ? <ShieldCheck className="w-4 h-4" /> : <ShieldAlert className="w-4 h-4" />}
            {!isCollapsed && <span>{isAdmin ? 'ROLE: ADMIN' : 'ROLE: LEITOR'}</span>}
          </div>
          {!isCollapsed && <span className="text-[10px] opacity-75">Alternar</span>}
        </button>
      </div>

      {/* User Footer */}
      <div className="p-4 border-t border-white/5 space-y-2 mt-auto">
        <div className="flex items-center gap-3 px-3 py-2 text-slate-400">
          <div className="w-9 h-9 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center text-xs font-bold text-white shrink-0">
            OA
          </div>
          {!isCollapsed && (
            <div className="overflow-hidden">
              <p className="text-sm font-semibold text-white truncate">Osmar Admin</p>
              <p className="text-xs text-slate-400 truncate">Gerente de TI</p>
            </div>
          )}
        </div>
      </div>
    </aside>
  );
};
