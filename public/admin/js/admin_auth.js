/**
 * admin_auth.js — Guard RBAC para Dashboard Admin
 * Página independente: cria um único client Supabase e compartilha com os módulos.
 */

const AdminAuth = (() => {
  let supabase = null;
  let currentUser = null;
  let isAdmin = false;
  let authCallbacks = [];
  let initialized = false;
  let buttonsBound = false;
  // Guard contra loop: callbacks de "admin ready" disparam UMA vez por usuário.
  // onAuthStateChange emite INITIAL_SESSION + SIGNED_IN + TOKEN_REFRESHED,
  // e cada checkAdminRole() antigo re-disparava todos os módulos (loop de init).
  let modulesLoadedForUserId = null;
  // Dedupe de chamadas concorrentes de checkAdminRole (3 eventos de auth no boot).
  let adminCheckInFlight = null;

  function getConfig() {
    return {
      url: window.SUPABASE_URL || 'https://news.mob.tec.br',
      key: window.SUPABASE_ANON_KEY || '',
    };
  }

  function createClient() {
    const { url, key } = getConfig();
    if (!window.supabase || !window.supabase.createClient) {
      throw new Error('Supabase SDK não carregado');
    }
    if (!key) {
      throw new Error('SUPABASE_ANON_KEY ausente');
    }

    // Mesma storage key padrão do hostname (sb-news-auth-token) —
    // assim a sessão da home e do admin é compartilhada no mesmo domínio.
    const client = window.supabase.createClient(url, key, {
      auth: {
        detectSessionInUrl: true,
        persistSession: true,
        autoRefreshToken: true,
        flowType: 'pkce',
      },
    });

    window.supabaseClient = client;
    return client;
  }

  function init() {
    if (initialized && supabase) {
      console.log('[admin_auth] Já inicializado');
      return supabase;
    }

    console.log('[admin_auth] Iniciando...');
    console.log('[admin_auth] SDK:', !!window.supabase);
    console.log('[admin_auth] URL:', getConfig().url);
    console.log('[admin_auth] KEY:', getConfig().key ? 'ok' : 'AUSENTE');

    try {
      supabase = createClient();
      initialized = true;
      console.log('[admin_auth] Client criado');
    } catch (err) {
      console.error('[admin_auth]', err.message);
      showAuthError('Configuração do Supabase não encontrada: ' + err.message);
      return null;
    }

    bindButtons();
    watchAuth();
    checkExistingSession();
    return supabase;
  }

  function watchAuth() {
    supabase.auth.onAuthStateChange((event, session) => {
      console.log('[admin_auth] Auth state:', event, {
        hasSession: !!session,
        email: session?.user?.email,
      });

      currentUser = session?.user || null;
      if (currentUser) {
        // Garante limpeza da URL também quando o SIGNED_IN do OAuth chega
        // antes do checkExistingSession (cleanAuthUrl é idempotente).
        if (event === 'SIGNED_IN' || event === 'INITIAL_SESSION') {
          cleanAuthUrl();
        }
        checkAdminRole();
      } else if (event === 'SIGNED_OUT') {
        isAdmin = false;
        showAuthScreen();
        notifyCallbacks();
      }
    });
  }

  async function checkExistingSession() {
    // Limpa erros de OAuth na URL (ex.: ?error=server_error)
    try {
      const params = new URLSearchParams(window.location.search);
      if (params.get('error')) {
        const desc = params.get('error_description') || params.get('error');
        console.error('[admin_auth] OAuth error na URL:', desc);
        showAuthError('Falha no login: ' + decodeURIComponent(desc));
        // remove query suja
        window.history.replaceState({}, '', window.location.pathname);
      }
    } catch (_) { /* ignore */ }

    console.log('[admin_auth] Verificando sessão...');
    const { data, error } = await supabase.auth.getSession();
    console.log('[admin_auth] getSession:', {
      hasSession: !!data?.session,
      email: data?.session?.user?.email,
      error: error?.message,
    });

    currentUser = data?.session?.user || null;
    if (currentUser) {
      cleanAuthUrl();
      await checkAdminRole();
    } else {
      showAuthScreen();
    }
  }

  // Remove artefatos de OAuth (?code=, ?state=, tokens) da barra de endereços
  // DEPOIS que a sessão já foi processada. Sem isso, o ?code= fica na URL e o
  // SDK re-processa a troca de token a cada refresh/reload da página.
  // Idempotente: se a query já está limpa, não faz nada.
  function cleanAuthUrl() {
    try {
      const search = window.location.search;
      if (!search) return;
      const hasAuthArtifact =
        /[?&](code|state|access_token|refresh_token|token_type|expires_in|expires_at|error_description)=/.test(search);
      if (hasAuthArtifact) {
        const cleanUrl = window.location.protocol + '//' + window.location.host + window.location.pathname;
        window.history.replaceState({ path: window.location.pathname }, '', cleanUrl);
        console.log('[admin_auth] Parâmetros OAuth removidos da URL');
      }
    } catch (_) { /* ignore */ }
  }

  async function checkAdminRole() {
    if (!supabase || !currentUser) return;

    // Se este usuário já foi validado como admin nesta sessão, não re-checa.
    // Evita RPCs redundantes a cada evento onAuthStateChange (TOKEN_REFRESHED etc.)
    if (isAdmin && modulesLoadedForUserId === currentUser.id) {
      console.log('[admin_auth] Admin já validado para', currentUser.email, '— pulando re-check');
      return;
    }

    // Dedupe de chamadas concorrentes: no boot, getSession() + INITIAL_SESSION +
    // SIGNED_IN disparam 3 checkAdminRole() quase juntos. O primeiro emite a RPC;
    // os demais aguardam o mesmo resultado em vez de disparar RPCs extras.
    const uid = currentUser.id;
    if (adminCheckInFlight && adminCheckInFlight.uid === uid) {
      console.log('[admin_auth] checkAdminRole já em voo para', currentUser.email, '— reutilizando');
      return adminCheckInFlight.promise;
    }

    adminCheckInFlight = { uid, promise: doCheckAdminRole() };
    try {
      return await adminCheckInFlight.promise;
    } finally {
      adminCheckInFlight = null;
    }
  }

  async function doCheckAdminRole() {
    console.log('[admin_auth] Checando admin:', currentUser.email);
    try {
      const { data, error } = await supabase.rpc('is_admin_user');
      console.log('[admin_auth] is_admin_user:', { data, error: error?.message || error });

      if (error) {
        isAdmin = false;
        showAuthError('Erro ao verificar permissão: ' + error.message);
        return;
      }

      isAdmin = !!data;
      if (isAdmin) {
        console.log('[admin_auth] Acesso permitido');
        hideAuthScreen();
        updateUserUI();
        notifyCallbacks();
      } else {
        showAuthError(
          'Sua conta não possui permissão de administrador.<br>' +
          'Email: <strong>' + (currentUser.email || '') + '</strong>'
        );
        showAuthScreen();
      }
    } catch (err) {
      console.error('[admin_auth] exceção admin:', err);
      isAdmin = false;
      showAuthError('Erro na verificação: ' + err.message);
    }
  }

  async function signInWithGoogle() {
    if (!supabase) {
      init();
    }
    if (!supabase) {
      alert('Supabase não inicializado.');
      return;
    }

    const redirectTo = window.location.origin + '/admin/';
    console.log('[admin_auth] OAuth Google →', redirectTo);

    const { error } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo,
        queryParams: { access_type: 'offline', prompt: 'select_account' },
      },
    });

    if (error) {
      console.error('[admin_auth] OAuth error:', error);
      alert('Falha ao iniciar login: ' + error.message);
    }
  }

  async function signOut() {
    if (!supabase) return;
    await supabase.auth.signOut();
    currentUser = null;
    isAdmin = false;
    modulesLoadedForUserId = null; // permite re-init ao logar novamente
    showAuthScreen();
    notifyCallbacks();
  }

  function showAuthScreen() {
    const auth = document.getElementById('authScreen');
    const dash = document.getElementById('dashboardLayout');
    if (auth) auth.style.display = 'flex';
    if (dash) dash.style.display = 'none';
  }

  function hideAuthScreen() {
    const auth = document.getElementById('authScreen');
    const dash = document.getElementById('dashboardLayout');
    if (auth) auth.style.display = 'none';
    if (dash) dash.style.display = 'flex';
    const err = document.getElementById('authError');
    if (err) err.style.display = 'none';
  }

  function showAuthError(message) {
    const errorEl = document.getElementById('authError');
    if (!errorEl) return;
    const msg = errorEl.querySelector('.alert-message');
    if (msg) msg.innerHTML = message;
    errorEl.style.display = 'flex';
    showAuthScreen();
  }

  function updateUserUI() {
    if (!currentUser) return;
    const name =
      currentUser.user_metadata?.full_name ||
      currentUser.user_metadata?.name ||
      currentUser.email?.split('@')[0] ||
      'Admin';
    const avatar =
      currentUser.user_metadata?.avatar_url ||
      currentUser.user_metadata?.picture ||
      '';
    const initials = name.substring(0, 2).toUpperCase();

    const avatarEl = document.getElementById('sidebarAvatar');
    const nameEl = document.getElementById('sidebarUserName');
    if (avatarEl) {
      avatarEl.innerHTML = avatar
        ? `<img src="${avatar}" alt="" style="width:100%;height:100%;object-fit:cover;border-radius:inherit;">`
        : initials;
    }
    if (nameEl) nameEl.textContent = name;
  }

  function onAdminReady(callback) {
    authCallbacks.push(callback);
    if (isAdmin) callback();
  }

  function notifyCallbacks() {
    if (!isAdmin || !currentUser) return;
    // Guard: notifica apenas UMA vez por usuário logado.
    if (modulesLoadedForUserId === currentUser.id) {
      console.log('[admin_auth] Módulos já carregados para', currentUser.email, '— ignorando notify duplicado');
      return;
    }
    modulesLoadedForUserId = currentUser.id;
    console.log('[admin_auth] Admin validado — carregando módulos uma única vez');
    authCallbacks.forEach((cb) => {
      try { cb(); } catch (e) { console.error(e); }
    });
  }

  function bindButtons() {
    if (buttonsBound) return;
    buttonsBound = true;
    const loginBtn = document.getElementById('btnGoogleLogin');
    if (loginBtn) loginBtn.addEventListener('click', (e) => {
      e.preventDefault();
      signInWithGoogle();
    });
    const logoutBtn = document.getElementById('btnLogout');
    if (logoutBtn) logoutBtn.addEventListener('click', (e) => {
      e.preventDefault();
      signOut();
    });
  }

  function getClient() {
    return supabase || window.supabaseClient || null;
  }

  // Boot: espera DOM + SDK (script do SDK não usa defer; modules usam defer)
  function boot() {
    bindButtons();
    // Se SDK ainda não estiver pronto (ordem rara), tenta de novo
    if (!window.supabase) {
      let tries = 0;
      const t = setInterval(() => {
        tries += 1;
        if (window.supabase || tries > 50) {
          clearInterval(t);
          init();
        }
      }, 100);
      return;
    }
    init();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }

  return {
    init,
    signInWithGoogle,
    signOut,
    onAdminReady,
    getCurrentUser: () => currentUser,
    isAdminUser: () => isAdmin,
    getClient,
  };
})();

window.AdminAuth = AdminAuth;
