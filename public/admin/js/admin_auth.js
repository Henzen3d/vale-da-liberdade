/**
 * admin_auth.js — Guard RBAC para Dashboard Admin
 * Verifica se a sessão do Supabase tem role = 'admin' via RPC is_admin_user()
 */

const AdminAuth = (() => {
  let supabase = null;
  let currentUser = null;
  let isAdmin = false;
  let authCallbacks = [];

  function init() {
    const supabaseUrl = window.SUPABASE_URL;
    const supabaseKey = window.SUPABASE_ANON_KEY;
    
    console.log('[admin_auth] Iniciando...', {
      url: supabaseUrl,
      hasSdk: !!window.supabase,
      hasKeys: !!(supabaseUrl && supabaseKey)
    });
    
    if (!window.supabase || !supabaseUrl || !supabaseKey) {
      console.error('[admin_auth] Supabase SDK ou chaves ausentes');
      alert('Erro: Configuração do Supabase não encontrada.');
      return;
    }

    supabase = window.supabase.createClient(supabaseUrl, supabaseKey, {
      auth: {
        detectSessionInUrl: true,
        persistSession: true,
        autoRefreshToken: true,
        flowType: 'pkce',
      },
    });

    // Check existing session
    supabase.auth.getSession().then(({ data, error }) => {
      console.log('[admin_auth] getSession:', { 
        hasSession: !!data?.session, 
        userId: data?.session?.user?.id,
        error: error?.message 
      });
      
      currentUser = data?.session?.user || null;
      if (currentUser) {
        console.log('[admin_auth] Usuário identificado:', currentUser.email);
        checkAdminRole();
      } else {
        console.log('[admin_auth] Nenhuma sessão encontrada');
        showAuthScreen();
      }
    });

    // Listen for auth changes
    supabase.auth.onAuthStateChange((event, session) => {
      console.log('[admin_auth] Auth state change:', event, {
        hasSession: !!session,
        userId: session?.user?.id,
        email: session?.user?.email
      });
      
      currentUser = session ? session.user : null;
      if (currentUser) {
        console.log('[admin_auth] Usuário logado:', currentUser.email);
        checkAdminRole();
      } else {
        console.log('[admin_auth] Usuário desconectado');
        showAuthScreen();
        isAdmin = false;
        notifyCallbacks();
      }
    });
  }

  async function checkAdminRole() {
    if (!supabase || !currentUser) {
      console.log('[admin_auth] checkAdminRole: supabase ou currentUser não disponíveis');
      return;
    }

    console.log('[admin_auth] Verificando permissão de admin...');
    
    try {
      const { data, error } = await supabase.rpc('is_admin_user');
      
      console.log('[admin_auth] Resultado RPC is_admin_user:', {
        data: data,
        error: error?.message || error
      });
      
      if (error) {
        console.error('[admin_auth] Erro na RPC is_admin_user:', error);
        isAdmin = false;
        showAuthError('Erro ao verificar permissão: ' + error.message);
        // Não faz signOut — apenas mostra o erro
        return;
      }

      isAdmin = !!data;
      console.log('[admin_auth] É admin?', isAdmin);

      if (isAdmin) {
        hideAuthScreen();
        updateUserUI();
        notifyCallbacks();
      } else {
        console.warn('[admin_auth] Usuário não é admin');
        showAuthError('Sua conta não possui permissão de administrador. Execute no Supabase:\n\nUPDATE public.user_profiles SET role = \'admin\' WHERE email = \'henzen3d@gmail.com\';');
        // Não faz signOut — permite que o usuário veja o erro e tente novamente
      }
    } catch (err) {
      console.error('[admin_auth] Exceção ao verificar admin:', err);
      isAdmin = false;
      showAuthError('Erro na verificação: ' + err.message);
    }
  }

  async function signInWithGoogle() {
    if (!supabase) {
      console.error('[admin_auth] supabase não inicializado');
      return;
    }

    console.log('[admin_auth] Iniciando login com Google...');
    
    const { error } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo: window.location.origin + '/admin/',
        queryParams: { access_type: 'offline', prompt: 'consent' },
      },
    });

    if (error) {
      console.error('[admin_auth] Erro no OAuth:', error);
      alert('Falha ao iniciar login com Google: ' + error.message);
    }
  }

  async function signOut() {
    if (!supabase) return;
    await supabase.auth.signOut();
    currentUser = null;
    isAdmin = false;
    showAuthScreen();
    notifyCallbacks();
  }

  function showAuthScreen() {
    document.getElementById('authScreen').style.display = 'flex';
    document.getElementById('dashboardLayout').style.display = 'none';
    document.getElementById('authError').style.display = 'none';
  }

  function hideAuthScreen() {
    document.getElementById('authScreen').style.display = 'none';
    document.getElementById('dashboardLayout').style.display = 'flex';
  }

  function showAuthError(message) {
    const errorEl = document.getElementById('authError');
    if (errorEl) {
      errorEl.querySelector('.alert-message').innerHTML = message.replace(/\n/g, '<br>');
      errorEl.style.display = 'flex';
    }
  }

  function updateUserUI() {
    if (!currentUser) return;

    const name = currentUser.user_metadata?.full_name || 
                 currentUser.user_metadata?.name || 
                 currentUser.email?.split('@')[0] || 'Admin';
    const avatar = currentUser.user_metadata?.avatar_url || 
                   currentUser.user_metadata?.picture || '';
    const initials = name.substring(0, 2).toUpperCase();

    const avatarEl = document.getElementById('sidebarAvatar');
    const nameEl = document.getElementById('sidebarUserName');

    if (avatarEl) {
      if (avatar) {
        avatarEl.innerHTML = `<img src="${avatar}" alt="" style="width:100%;height:100%;object-fit:cover;">`;
      } else {
        avatarEl.textContent = initials;
      }
    }

    if (nameEl) {
      nameEl.textContent = name;
    }
  }

  function onAdminReady(callback) {
    authCallbacks.push(callback);
    if (isAdmin) {
      callback();
    }
  }

  function notifyCallbacks() {
    authCallbacks.forEach(cb => {
      if (isAdmin) cb();
    });
  }

  function getCurrentUser() {
    return currentUser;
  }

  function isAdminUser() {
    return isAdmin;
  }

  // Initialize on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Setup login button
  document.addEventListener('DOMContentLoaded', () => {
    const loginBtn = document.getElementById('btnGoogleLogin');
    if (loginBtn) {
      loginBtn.addEventListener('click', signInWithGoogle);
    }

    const logoutBtn = document.getElementById('btnLogout');
    if (logoutBtn) {
      logoutBtn.addEventListener('click', signOut);
    }
  });

  return {
    init,
    signInWithGoogle,
    signOut,
    onAdminReady,
    getCurrentUser,
    isAdminUser,
  };
})();

// Expose to window
window.AdminAuth = AdminAuth;
