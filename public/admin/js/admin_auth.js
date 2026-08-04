/**
 * admin_auth.js — Guard RBAC para Dashboard Admin
 * Reutiliza instância do Supabase da página pai (evita conflito de instâncias)
 */

const AdminAuth = (() => {
  let supabase = null;
  let currentUser = null;
  let isAdmin = false;
  let authCallbacks = [];

  function init() {
    // Tenta reutilizar instância do Supabase já carregada na página pai
    if (window.supabaseClient && typeof window.supabaseClient.auth !== 'undefined') {
      supabase = window.supabaseClient;
      console.log('[admin_auth] Reutilizando instância do Supabase da página pai');
    } else if (window.supabase && window.SUPABASE_URL && window.SUPABASE_ANON_KEY) {
      // Cria nova instância apenas se necessário
      supabase = window.supabase.createClient(window.SUPABASE_URL, window.SUPABASE_ANON_KEY, {
        auth: {
          detectSessionInUrl: true,
          persistSession: true,
          autoRefreshToken: true,
          flowType: 'pkce',
        },
      });
      console.log('[admin_auth] Criando nova instância do Supabase');
    } else {
      console.error('[admin_auth] Supabase não disponível');
      alert('Erro: Supabase não configurado. Verifique as credenciais.');
      return;
    }

    console.log('[admin_auth] Iniciando verificação de sessão...');
    
    // Check existing session
    supabase.auth.getSession().then(({ data, error }) => {
      console.log('[admin_auth] getSession:', { 
        hasSession: !!data?.session, 
        userId: data?.session?.user?.id,
        email: data?.session?.user?.email,
        error: error?.message 
      });
      
      currentUser = data?.session?.user || null;
      if (currentUser) {
        console.log('[admin_auth] Sessão encontrada:', currentUser.email);
        checkAdminRole();
      } else {
        console.log('[admin_auth] Nenhuma sessão ativa — aguardando login');
        showAuthScreen();
      }
    }).catch(err => {
      console.error('[admin_auth] Erro ao obter sessão:', err);
      showAuthScreen();
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

    console.log('[admin_auth] Verificando permissão de admin para:', currentUser.email);
    
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
        return;
      }

      isAdmin = !!data;
      console.log('[admin_auth] É admin?', isAdmin);

      if (isAdmin) {
        console.log('[admin_auth] Acesso permitido!');
        hideAuthScreen();
        updateUserUI();
        notifyCallbacks();
      } else {
        console.warn('[admin_auth] Usuário não tem role=admin');
        showAuthError('Sua conta não possui permissão de administrador.<br><br><strong>Para resolver, execute no Supabase:</strong><br><code>UPDATE public.user_profiles SET role = \'admin\' WHERE email = \'henzen3d@gmail.com\';</code>');
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
    
    // Usa a mesma URL de redirecionamento da página principal
    const redirectUrl = window.location.origin + '/';
    console.log('[admin_auth] Redirect URL:', redirectUrl);
    
    const { data, error } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo: redirectUrl,
        queryParams: { access_type: 'offline', prompt: 'consent' },
      },
    });

    if (error) {
      console.error('[admin_auth] Erro no OAuth:', error);
      alert('Falha ao iniciar login: ' + error.message);
    } else {
      console.log('[admin_auth] Redirecionando para Google...');
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
      errorEl.querySelector('.alert-message').innerHTML = message;
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
