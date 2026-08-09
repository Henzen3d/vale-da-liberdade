import React, { useState } from 'react';
import { UserProfile, Subscription, PlanType, RoleType, SubscriptionStatus } from '../types';
import { Search, Plus, UserCheck, Shield, Edit3, Trash2, Calendar, Crown, Award } from 'lucide-react';

interface UsersTabProps {
  users: UserProfile[];
  subscriptions: Subscription[];
  onSaveUser: (user: UserProfile) => void;
  onDeleteUser: (id: string) => void;
  onSaveSubscription: (sub: Subscription) => void;
}

export const UsersTab: React.FC<UsersTabProps> = ({
  users,
  subscriptions,
  onSaveUser,
  onDeleteUser,
  onSaveSubscription,
}) => {
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState<string>('all');
  const [planFilter, setPlanFilter] = useState<string>('all');

  // Edit User / Sub Modal
  const [editingUser, setEditingUser] = useState<UserProfile | null>(null);
  const [showAddModal, setShowAddModal] = useState(false);
  const [newName, setNewName] = useState('');
  const [newEmail, setNewEmail] = useState('');
  const [newRole, setNewRole] = useState<RoleType>('reader');
  const [newPlan, setNewPlan] = useState<PlanType>('premium');

  const filteredUsers = users.filter(u => {
    const matchesSearch =
      u.name.toLowerCase().includes(search.toLowerCase()) ||
      u.email.toLowerCase().includes(search.toLowerCase());
    const matchesRole = roleFilter === 'all' || u.role === roleFilter;

    const userSub = subscriptions.find(s => s.user_email === u.email);
    const matchesPlan = planFilter === 'all' || (userSub && userSub.plan === planFilter) || (!userSub && planFilter === 'free');

    return matchesSearch && matchesRole && matchesPlan;
  });

  const handleUpdateRole = (user: UserProfile, role: RoleType) => {
    onSaveUser({ ...user, role });
  };

  const handleUpdateSubPlan = (email: string, plan: PlanType) => {
    const existing = subscriptions.find(s => s.user_email === email);
    if (existing) {
      onSaveSubscription({
        ...existing,
        plan,
        price_monthly: plan === 'vip' ? 49.9 : plan === 'premium' ? 29.9 : 0
      });
    } else {
      const u = users.find(usr => usr.email === email);
      onSaveSubscription({
        id: `sub-${Date.now()}`,
        user_id: u?.id || `usr-${Date.now()}`,
        user_name: u?.name || 'Leitor',
        user_email: email,
        plan,
        status: 'active',
        price_monthly: plan === 'vip' ? 49.9 : plan === 'premium' ? 29.9 : 0,
        start_date: new Date().toISOString().slice(0, 10),
        expires_at: '2027-12-31'
      });
    }
  };

  const handleAddUserSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName || !newEmail) return;
    const userId = `usr-${Date.now()}`;
    const newUser: UserProfile = {
      id: userId,
      name: newName,
      email: newEmail,
      role: newRole,
      created_at: new Date().toISOString().slice(0, 10),
      last_login: new Date().toISOString().slice(0, 10)
    };
    onSaveUser(newUser);

    // Save initial subscription
    onSaveSubscription({
      id: `sub-${Date.now()}`,
      user_id: userId,
      user_name: newName,
      user_email: newEmail,
      plan: newPlan,
      status: 'active',
      price_monthly: newPlan === 'vip' ? 49.9 : newPlan === 'premium' ? 29.9 : 0,
      start_date: new Date().toISOString().slice(0, 10),
      expires_at: '2027-12-31'
    });

    setNewName('');
    setNewEmail('');
    setShowAddModal(false);
  };

  return (
    <div className="space-y-6">
      {/* Header Controls */}
      <div className="bg-white/5 border border-white/10 rounded-2xl p-6 shadow-xl flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h2 className="text-xl font-bold text-white">Usuários & Planos de Assinatura</h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Gerencie leitores, níveis de acesso e planos de assinatura.
          </p>
        </div>

        <button
          onClick={() => setShowAddModal(true)}
          className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-semibold transition-colors flex items-center gap-2"
        >
          <Plus className="w-4 h-4" />
          <span>Cadastrar Usuário / Leitor</span>
        </button>
      </div>

      {/* Filter Bar */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Buscar por nome ou e-mail do assinante..."
            className="w-full bg-[#18181b] border border-white/10 rounded-lg pl-9 pr-4 py-2 text-xs text-slate-200 focus:outline-none focus:border-emerald-500"
          />
        </div>

        <select
          value={roleFilter}
          onChange={e => setRoleFilter(e.target.value)}
          className="bg-[#18181b] border border-white/10 rounded-lg px-4 py-2 text-xs text-slate-200 focus:outline-none focus:border-emerald-500"
        >
          <option value="all">Todas as Permissões (Roles)</option>
          <option value="admin">Administradores (admin)</option>
          <option value="editor">Editores (editor)</option>
          <option value="reader">Leitores (reader)</option>
        </select>

        <select
          value={planFilter}
          onChange={e => setPlanFilter(e.target.value)}
          className="bg-[#18181b] border border-white/10 rounded-lg px-4 py-2 text-xs text-slate-200 focus:outline-none focus:border-emerald-500"
        >
          <option value="all">Todos os Planos</option>
          <option value="vip">VIP Anual</option>
          <option value="premium">Premium Mensal</option>
          <option value="free">Gratuito</option>
        </select>
      </div>

      {/* Users Table */}
      <div className="bg-white/5 border border-white/10 rounded-2xl overflow-hidden p-6 shadow-xl">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-white/5 text-slate-400 uppercase tracking-wider font-semibold border-b border-white/10">
              <tr>
                <th className="py-3.5 px-4">Usuário / Perfil</th>
                <th className="py-3.5 px-4">Permissão (Role)</th>
                <th className="py-3.5 px-4">Plano de Assinatura</th>
                <th className="py-3.5 px-4">Valor Mensal</th>
                <th className="py-3.5 px-4">Vencimento</th>
                <th className="py-3.5 px-4 text-right">Ações</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 text-slate-300">
              {filteredUsers.map(u => {
                const sub = subscriptions.find(s => s.user_email === u.email);
                const plan = sub?.plan || 'free';
                const price = sub?.price_monthly ?? 0;
                const expires = sub?.expires_at || 'Indeterminado';

                return (
                  <tr key={u.id} className="hover:bg-white/5 transition-colors">
                    <td className="py-4 px-4">
                      <div className="flex items-center gap-3">
                        {u.avatar_url ? (
                          <img
                            src={u.avatar_url}
                            alt=""
                            className="w-9 h-9 rounded-full object-cover border border-white/15"
                          />
                        ) : (
                          <div className="w-9 h-9 rounded-full bg-emerald-500/20 text-emerald-400 flex items-center justify-center font-bold text-xs">
                            {u.name[0]}
                          </div>
                        )}
                        <div>
                          <p className="font-bold text-white text-sm">{u.name}</p>
                          <p className="text-[11px] text-slate-400">{u.email}</p>
                        </div>
                      </div>
                    </td>

                    <td className="py-4 px-4">
                      <select
                        value={u.role}
                        onChange={e => handleUpdateRole(u, e.target.value as RoleType)}
                        className={`px-2.5 py-1 rounded-lg text-xs font-bold border bg-[#18181b] ${
                          u.role === 'admin'
                            ? 'text-emerald-400 border-emerald-500/30'
                            : u.role === 'editor'
                            ? 'text-blue-400 border-blue-500/30'
                            : 'text-slate-400 border-slate-700'
                        }`}
                      >
                        <option value="admin">ADMIN</option>
                        <option value="editor">EDITOR</option>
                        <option value="reader">LEITOR</option>
                      </select>
                    </td>

                    <td className="py-4 px-4">
                      <select
                        value={plan}
                        onChange={e => handleUpdateSubPlan(u.email, e.target.value as PlanType)}
                        className={`px-3 py-1 rounded-full text-xs font-bold border bg-[#18181b] ${
                          plan === 'vip'
                            ? 'text-yellow-400 border-yellow-500/40'
                            : plan === 'premium'
                            ? 'text-emerald-400 border-emerald-500/40'
                            : 'text-slate-400 border-slate-700'
                        }`}
                      >
                        <option value="free">PLANO FREE</option>
                        <option value="premium">PREMIUM (R$ 29,90)</option>
                        <option value="vip">VIP ANUAL (R$ 49,90)</option>
                      </select>
                    </td>

                    <td className="py-4 px-4 font-mono font-bold text-white">
                      R$ {price.toFixed(2)}
                    </td>

                    <td className="py-4 px-4 text-slate-400 text-[11px] font-mono">
                      {expires}
                    </td>

                    <td className="py-4 px-4 text-right">
                      <button
                        onClick={() => onDeleteUser(u.id)}
                        className="p-1.5 text-rose-400 hover:text-rose-300 hover:bg-rose-500/10 rounded-lg transition-colors"
                        title="Remover Usuário"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Add User Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-4">
          <form
            onSubmit={handleAddUserSubmit}
            className="bg-[#0f0f12] border border-white/10 rounded-2xl p-6 max-w-md w-full shadow-2xl space-y-4 text-xs"
          >
            <h3 className="text-base font-bold text-white mb-2">Cadastrar Novo Usuário / Leitor</h3>

            <div>
              <label className="block text-slate-400 font-semibold mb-1">Nome Completo</label>
              <input
                type="text"
                required
                value={newName}
                onChange={e => setNewName(e.target.value)}
                placeholder="ex: João da Silva"
                className="w-full bg-[#18181b] border border-white/10 rounded-lg px-4 py-2 text-xs text-slate-200 focus:outline-none focus:border-emerald-500"
              />
            </div>

            <div>
              <label className="block text-slate-400 font-semibold mb-1">E-mail</label>
              <input
                type="email"
                required
                value={newEmail}
                onChange={e => setNewEmail(e.target.value)}
                placeholder="joao@gmail.com"
                className="w-full bg-[#18181b] border border-white/10 rounded-lg px-4 py-2 text-xs text-slate-200 focus:outline-none focus:border-emerald-500"
              />
            </div>

            <div>
              <label className="block text-slate-400 font-semibold mb-1">Permissão de Acesso (Role)</label>
              <select
                value={newRole}
                onChange={e => setNewRole(e.target.value as RoleType)}
                className="w-full bg-[#18181b] border border-white/10 rounded-lg px-4 py-2 text-xs text-slate-200 focus:outline-none focus:border-emerald-500"
              >
                <option value="reader">Leitor (reader)</option>
                <option value="editor">Editor (editor)</option>
                <option value="admin">Administrador (admin)</option>
              </select>
            </div>

            <div>
              <label className="block text-slate-400 font-semibold mb-1">Plano Inicial</label>
              <select
                value={newPlan}
                onChange={e => setNewPlan(e.target.value as PlanType)}
                className="w-full bg-[#18181b] border border-white/10 rounded-lg px-4 py-2 text-xs text-slate-200 focus:outline-none focus:border-emerald-500"
              >
                <option value="free">Gratuito (Free)</option>
                <option value="premium">Premium (R$ 29,90/mês)</option>
                <option value="vip">VIP Anual (R$ 49,90/mês)</option>
              </select>
            </div>

            <div className="flex justify-end gap-2 pt-4 border-t border-white/10">
              <button
                type="button"
                onClick={() => setShowAddModal(false)}
                className="px-4 py-2 rounded-lg text-xs font-semibold text-slate-400 hover:bg-white/5"
              >
                Cancelar
              </button>
              <button
                type="submit"
                className="px-4 py-2 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white transition-colors"
              >
                Salvar Usuário
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
};
