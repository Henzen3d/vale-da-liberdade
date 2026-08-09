import React from 'react';
import { ShieldAlert, ArrowLeft, RefreshCw } from 'lucide-react';

interface AccessDeniedGuardProps {
  onSwitchToAdmin: () => void;
}

export const AccessDeniedGuard: React.FC<AccessDeniedGuardProps> = ({ onSwitchToAdmin }) => {
  return (
    <div className="min-h-screen bg-[#09090b] flex items-center justify-center p-6 text-center text-slate-300">
      <div className="bg-[#0f0f12] rounded-2xl p-8 max-w-md w-full shadow-2xl border border-rose-500/30 space-y-5 relative overflow-hidden">
        <div className="w-16 h-16 rounded-2xl bg-rose-500/10 border border-rose-500/30 text-rose-400 flex items-center justify-center mx-auto">
          <ShieldAlert className="w-8 h-8" />
        </div>

        <div>
          <span className="px-3 py-1 rounded-full text-[10px] font-bold bg-rose-500/15 text-rose-400 border border-rose-500/30 uppercase tracking-widest">
            RBAC Guard: 403 Forbidden
          </span>
          <h2 className="text-xl font-bold text-white mt-3">Acesso Restrito a Administradores</h2>
          <p className="text-xs text-slate-400 mt-2 leading-relaxed">
            A verificação de segurança confirmou que seu e-mail não possui permissão de administrador (<code className="text-rose-300 font-mono">role = 'admin'</code>).
          </p>
        </div>

        <div className="p-3 bg-[#18181b] rounded-xl text-left border border-white/10 space-y-1 text-[11px] font-mono text-slate-400">
          <p className="text-emerald-400 font-bold">// Para autorizar seu e-mail no banco:</p>
          <p className="text-slate-300">UPDATE public.user_profiles</p>
          <p className="text-slate-300">SET role = 'admin'</p>
          <p className="text-slate-300">WHERE email = 'seu-email-admin@gmail.com';</p>
        </div>

        <div className="pt-2">
          <button
            onClick={onSwitchToAdmin}
            className="w-full py-3 px-4 rounded-xl text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white transition-colors flex items-center justify-center gap-2 shadow-lg"
          >
            <RefreshCw className="w-4 h-4" />
            <span>Simular Login com Perfil ADMIN</span>
          </button>
        </div>
      </div>
    </div>
  );
};
