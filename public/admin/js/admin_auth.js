/**
 * admin_auth.js — Guard RBAC para Dashboard Admin
 * Solução: Usa a sessão existente da página principal
 */

const AdminAuth = (() => {
  let supabase = null;
  let currentUser = null;
  let isAdmin = false;
  let authCallbacks = [];

  function init() {
    console.log('[admin_auth] Iniciando inicialização...');
    
    // Tenta usar a instância do Supabase da página principal
    const waitForSupabase = setInterval(() => {
      if (window.supabaseClient) {
        clearInterval(waitForSupabase);
        console.log('[admin_auth] Supabase da página principal encontrado!');
        supabase = window.supabaseClient;
        checkExistingSession();
      } else if (window.__supabaseReady || window.supabase) {
        // Supabase SDK disponível mas instância não criada ainda
        console.log('[admin_auth] Aguardando inicialização do Supabase...');
        setTimeout(() => {
          if (window.supabaseClient) {
            clearInterval(waitForSupabase);
            console.log('[admin_auth] Supabase encontrado!');
            supabase = window.supabaseClient;
            checkExistingSession();
          }
        }, 500);
      }
    }, 100);

    // Timeout de 5 segundos
    setTimeout(() => {
      clearInterval(waitForSupabase);
      if (!supabase) {
        console.error('[admin_auth] Timeout ao aguardar Supabase');
        showAuthError('Erro ao conectar com o servidor. Certifique-se de estar na página principal e fazer login primeiro.');
      }
    }, 5000);
  }

  async function checkExistingSession() {
    if (!supabase) return;
    
    console.log('[admin_auth] Verificando sessão existente...');
    
    const { data, error } = await supabase.auth.getSession();
    console.log('[admin_auth] getSession:', { 
      hasSession: !!data?.session, 
      userId: data?.session?.user?.id,
      email: data?.session?.user?.email
    });
    
    currentUser = data?.session?.user || null;
    if (currentUser) {
      console.log('[admin_auth] Sessão encontrada:', currentUser.email);
      checkAdminRole();
    } else {
      console.log('[admin_auth] Nenhuma sessão ativa — mostrando tela de login');
      showAuthScreen();
    }
  }

  async function checkAdminRole() {
    if (!supabase || !currentUser) return;

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
        showAuthError('Sua conta não possui permissão de administrador.');
      }
    } catch (err) {
      console.error('[admin_auth] Exceção:', err);
      isAdmin = false;
      showAuthError('Erro na verificação: ' + err.message);
    }
  }

  async function signInWithGoogle() {
    // Se não tiver Supabase, redireciona para a página principal fazer login
    if (!window.supabaseClient) {
      console.log('[admin_auth] Supabase não disponível, redirecionando para página principal...');
      window.location.href = 'https://news.mob.tec.br/';
      return;
    }

    console.log('[admin_auth] Iniciando login com Google...');
    
    // O callback vai para a página principal, que depois redireciona para admin
    const redirectUrl = 'https://news.mob.tec.br/';
    console.log('[admin_auth] Redirect URL:', redirectUrl);
    
    const { error } = await window.supabaseClient.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo: redirectUrl,
        queryParams: { access_type: 'offline', prompt: 'consent' },
      },
    });

    if (error) {
      console.error('[admin_auth] Erro no OAuth:', error);
      alert('Falha ao iniciar login: ' + error.message);
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
