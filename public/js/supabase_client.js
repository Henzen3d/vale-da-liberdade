/**
 * Supabase Auth (Google) — Vale da Liberdade PWA
 * Usa window.SUPABASE_URL + window.SUPABASE_ANON_KEY (injetados no index.html)
 * Expõe hooks:
 *   window.__supabaseSetThumbs(date, kind) → like/dislike (toggle)
 *   window.__supabaseLogEvent(kind, date) → share/copy retro
 *   window.__supabaseApplyThumbs() → aplica estado ao DOM
 */
let supabaseClient = null;
let currentUser = null;
let _userFeedback = {}; // date → {thumbs_up, thumbs_down}

function initSupabase() {
  const supabaseUrl = window.SUPABASE_URL || "";
  const supabaseKey = window.SUPABASE_ANON_KEY || "";
  if (!window.supabase || !supabaseUrl || !supabaseKey) {
    console.warn("[auth] Supabase SDK ou chaves ausentes");
    const el = document.getElementById("auth-container");
    if (el) el.innerHTML = "";
    return;
  }
  supabaseClient = window.supabase.createClient(supabaseUrl, supabaseKey, {
    auth: {
      detectSessionInUrl: true,
      persistSession: true,
      autoRefreshToken: true,
      flowType: "pkce",
    },
  });
  window.supabaseClient = supabaseClient;

  supabaseClient.auth.getSession().then(({ data }) => {
    currentUser = data?.session?.user || null;
    updateAuthUI(currentUser);
    if (currentUser) loadUserFeedback();
  });

  supabaseClient.auth.onAuthStateChange((_event, session) => {
    currentUser = session ? session.user : null;
    updateAuthUI(currentUser);
    if (currentUser) loadUserFeedback();
    else {
      _userFeedback = {};
      applyThumbsToDom();
    }
  });
}

async function signInWithGoogle() {
  if (!supabaseClient) {
    alert("Login indisponível no momento.");
    return;
  }
  const { error } = await supabaseClient.auth.signInWithOAuth({
    provider: "google",
    options: {
      redirectTo: window.location.origin + "/",
      queryParams: { access_type: "offline", prompt: "consent" },
    },
  });
  if (error) {
    console.error("[auth] Google OAuth:", error);
    alert("Falha ao iniciar login com Google: " + error.message);
  }
}

async function signOutUser() {
  if (!supabaseClient) return;
  await supabaseClient.auth.signOut();
  currentUser = null;
  updateAuthUI(null);
}

function updateAuthUI(user) {
  const authContainer = document.getElementById("auth-container");
  if (!authContainer) return;

  if (user) {
    const avatar = user.user_metadata?.avatar_url || user.user_metadata?.picture || "";
    const name = user.user_metadata?.full_name || user.user_metadata?.name || user.email || "Ouvinte";
    const first = String(name).split(/\s+/)[0];
    authContainer.innerHTML = `
      <div class="user-chip" title="${escapeAttr(user.email || name)}">
        ${avatar
          ? `<img class="user-avatar" src="${escapeAttr(avatar)}" alt="" referrerpolicy="no-referrer" />`
          : `<span class="user-avatar fallback">${escapeHtml(first.charAt(0).toUpperCase())}</span>`}
        <span class="user-name">${escapeHtml(first)}</span>
        <button type="button" class="btn-logout" id="btnLogout">Sair</button>
      </div>`;
    document.getElementById("btnLogout")?.addEventListener("click", (e) => {
      e.preventDefault();
      signOutUser();
    });
  } else {
    authContainer.innerHTML = `
      <button type="button" class="btn-google" id="btnGoogleLogin" title="Entrar com Google" aria-label="Entrar com Google">
        <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">
          <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
          <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
          <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"/>
          <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"/>
        </svg>
        <span>Entrar</span>
      </button>`;
    document.getElementById("btnGoogleLogin")?.addEventListener("click", (e) => {
      e.preventDefault();
      signInWithGoogle();
    });
  }
}

// ---------- Feedback social (like/dislike/share/copy) ----------
async function loadUserFeedback() {
  if (!currentUser || !supabaseClient) return;
  try {
    const { data, error } = await supabaseClient
      .from("user_feedback")
      .select("episode_date, thumbs_up, thumbs_down")
      .eq("user_id", currentUser.id);
    if (error) throw error;
    _userFeedback = {};
    (data || []).forEach((row) => {
      _userFeedback[row.episode_date] = {
        thumbs_up: !!row.thumbs_up,
        thumbs_down: !!row.thumbs_down,
      };
    });
    applyThumbsToDom();
  } catch (err) {
    console.warn("[auth] feedback load:", err);
  }
}

function applyThumbsToDom() {
  document.querySelectorAll("[data-action]").forEach((btn) => {
    const date = btn.dataset.date;
    const action = btn.dataset.action;
    if (!date || !action) return;
    if (action === "like") {
      const on = !!(_userFeedback[date]?.thumbs_up);
      btn.classList.toggle("active", on);
    } else if (action === "dislike") {
      const on = !!(_userFeedback[date]?.thumbs_down);
      btn.classList.toggle("active", on);
    }
  });
}

async function setThumbs(date, kind) {
  if (!currentUser || !supabaseClient) {
    throw new Error("not_authenticated");
  }
  const fn = kind === "like" ? "fn_toggle_like" : "fn_toggle_dislike";
  const { data, error } = await supabaseClient.rpc(fn, { p_episode_date: date });
  if (error) throw error;
  // Optimistic UI: update local state from response
  if (kind === "like") {
    const up = !!data?.thumbs_up;
    _userFeedback[date] = {
      thumbs_up: up,
      thumbs_down: up ? false : (_userFeedback[date]?.thumbs_down || false),
    };
  } else {
    const down = !!data?.thumbs_down;
    _userFeedback[date] = {
      thumbs_down: down,
      thumbs_up: down ? false : (_userFeedback[date]?.thumbs_up || false),
    };
  }
  applyThumbsToDom();
  return data;
}

async function logEvent(kind, date) {
  if (!currentUser || !supabaseClient) return;
  try {
    await supabaseClient.rpc("fn_mark_shared", {
      p_episode_date: date,
      p_kind: kind, // "share" | "copy"
    });
  } catch (err) {
    // non-blocking
    console.warn("[auth] logEvent:", err);
  }
}

window.__supabaseSetThumbs = setThumbs;
window.__supabaseLogEvent = logEvent;
window.__supabaseApplyThumbs = applyThumbsToDom;

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (m) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m])
  );
}
function escapeAttr(s) { return escapeHtml(s).replace(/`/g, ""); }

document.addEventListener("DOMContentLoaded", initSupabase);
