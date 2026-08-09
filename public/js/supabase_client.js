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
  // Exponha a instância para outros scripts (interaction_bar.js, supabase_client hooks, etc.)
  window.supabaseClient = supabaseClient;

  supabaseClient.auth.getSession().then(({ data }) => {
    currentUser = data?.session?.user || null;
    updateAuthUI(currentUser);
    if (currentUser) loadUserFeedback();
    if (currentUser) loadProgress();
  }).catch((err) => {
    console.warn("[auth] getSession error:", err);
    updateAuthUI(null);
  });

  supabaseClient.auth.onAuthStateChange((_event, session) => {
    currentUser = session ? session.user : null;
    updateAuthUI(currentUser);
    if (currentUser) loadUserFeedback();
    if (currentUser) loadUserFavorites();
    if (currentUser) loadProgress();
    if (currentUser) syncSavedEpisodes();
    else {
      _userFeedback = {};
      _userFavorites = {};
      applyThumbsToDom();
      applyFavoritesToDom();
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
  try {
    await supabaseClient.auth.signOut();
  } catch (err) {
    console.warn("[auth] signOut error:", err);
  }
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
      .eq("user_id", currentUser.id)
      .limit(1000);
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

// ---------- Favoritos ----------
let _userFavorites = {}; // date → true

/* LOTE 6 (3.3): sync de "Ouvir depois" no login — puxa os remotos e empurra
 * os locais (merge por união; nunca apaga). Roda fire-and-forget. */
async function syncSavedEpisodes() {
  if (!currentUser || !supabaseClient) return;
  try {
    const { data, error } = await supabaseClient
      .from("user_saved_episodes")
      .select("episode_date")
      .eq("user_id", currentUser.id)
      .limit(500);
    if (error) throw error;

    const remote = new Set((data || []).map((r) => r.episode_date));
    const local = (typeof window.InteractionBar?.getSavedEpisodes === "function")
      ? window.InteractionBar.getSavedEpisodes()
      : [];

    // Puxa remotos → local
    const merged = new Set(local);
    remote.forEach((d) => merged.add(d));
    if (typeof window.InteractionBar?.setSavedEpisodes === "function") {
      window.InteractionBar.setSavedEpisodes([...merged]);
    }

    // Empurra locais que faltam no servidor
    const toPush = [...merged].filter((d) => !remote.has(d));
    if (toPush.length) {
      try {
        await supabaseClient
          .from("user_saved_episodes")
          .insert(toPush.map((episode_date) => ({ user_id: currentUser.id, episode_date })));
      } catch (err) {
        console.warn("[saved] push local→server:", err);
      }
    }
  } catch (err) {
    console.warn("[saved] sync:", err);
  }
}

async function loadUserFavorites() {
  if (!currentUser || !supabaseClient) return;
  try {
    const { data, error } = await supabaseClient
      .from("user_favorites")
      .select("episode_date")
      .eq("user_id", currentUser.id)
      .limit(500);
    if (error) throw error;
    _userFavorites = {};
    (data || []).forEach((row) => {
      _userFavorites[row.episode_date] = true;
    });
    applyFavoritesToDom();
  } catch (err) {
    console.warn("[auth] favorites load:", err);
  }
}

function applyFavoritesToDom() {
  document.querySelectorAll("#fullFavBtn").forEach((btn) => {
    const date = btn.dataset.favDate;
    if (!date) return;
    btn.classList.toggle("active", !!_userFavorites[date]);
  });
  // LOTE 5 (3.4): avisa o app (lista de favoritos no drawer) que o conjunto mudou
  try {
    window.dispatchEvent(new CustomEvent("favoriteschange"));
  } catch { /* non-blocking */ }
}

async function toggleFavoriteEpisode(date, title) {
  if (!currentUser || !supabaseClient) {
    throw new Error("not_authenticated");
  }
  const isFav = !!_userFavorites[date];
  try {
    if (isFav) {
      const { error } = await supabaseClient
        .from("user_favorites")
        .delete()
        .match({ user_id: currentUser.id, episode_date: date });
      if (error) throw error;
      delete _userFavorites[date];
    } else {
      const { error } = await supabaseClient
        .from("user_favorites")
        .insert({ user_id: currentUser.id, episode_date: date, title });
      if (error) throw error;
      _userFavorites[date] = true;
    }
    applyFavoritesToDom();
    return { favorited: !isFav };
  } catch (err) {
    console.warn("[auth] toggleFavorite:", err);
    throw err;
  }
}

// ---------- Progresso de audição (UX-009) ----------
let _progressSaveQueue = Promise.resolve();

async function loadProgress() {
  if (!currentUser || !supabaseClient) return;
  try {
    const { data, error } = await supabaseClient
      .from("episode_progress")
      .select("episode_id, episode_date, progress_seconds, duration_seconds, percent, completed, first_played_at, last_played_at, completed_at")
      .eq("user_id", currentUser.id)
      .order("last_played_at", { ascending: false })
      .limit(500);
    if (error) throw error;
    if (typeof window.ListenProgress === "undefined") return;
    // Merge no store local: maior progresso vence por episode_id.
    const behindIds = window.ListenProgress.mergeServer(data || []);
    // Empurra progresso local que está à frente do servidor (nunca regride:
    // o RPC usa GREATEST no servidor).
    for (const id of behindIds || []) {
      const rec = window.ListenProgress.get(id);
      if (!rec) continue;
      try {
        await supabaseClient.rpc("fn_upsert_episode_progress", {
          p_episode_id: id,
          p_episode_date: rec.episode_date || "",
          p_progress_seconds: rec.progress_seconds,
          p_duration_seconds: rec.duration_seconds || 0,
        });
      } catch (err) {
        console.warn("[progress] push local→server:", err);
      }
    }
  } catch (err) {
    console.warn("[progress] load:", err);
  }
}

function saveProgress(episodeId, episodeDate, progressSeconds, durationSeconds) {
  if (!currentUser || !supabaseClient || !episodeId) return Promise.resolve(null);
  // Serializa saves do mesmo episódio para não enviar ordem trocada
  _progressSaveQueue = _progressSaveQueue
    .then(() =>
      supabaseClient.rpc("fn_upsert_episode_progress", {
        p_episode_id: episodeId,
        p_episode_date: episodeDate || "",
        p_progress_seconds: Math.max(0, Math.floor(progressSeconds || 0)),
        p_duration_seconds: Math.max(0, Math.floor(durationSeconds || 0)),
      })
    )
    .then(({ data, error }) => {
      if (error) throw error;
      return data;
    })
    .catch((err) => {
      console.warn("[progress] save:", err.message || err);
      return null;
    });
  return _progressSaveQueue;
}

window.toggleFavoriteEpisode = toggleFavoriteEpisode;
window.__supabaseLoadProgress = loadProgress;
window.__supabaseSaveProgress = saveProgress;
/* LOTE 5 (3.4): acesso ao conjunto de favoritos p/ a lista do drawer */
window.__supabaseGetFavorites = () => Object.keys(_userFavorites);
window.__supabaseIsLoggedIn = () => !!currentUser;
/* LOTE 6 (3.3): id do usuário p/ sync de "Ouvir depois" (interaction_bar) */
window.__supabaseUserId = () => currentUser ? currentUser.id : null;

/* LOTE 4: Newsletter real — insere e-mail em newsletter_subscribers (anon INSERT via RLS).
 * Retorna { ok, error? }. Sem supabaseClient disponível, resolve com erro. */
async function subscribeNewsletter(email, source = "site") {
  const value = String(email || "").trim().toLowerCase();
  if (!value || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) {
    return { ok: false, error: "email inválido" };
  }
  if (!supabaseClient) {
    return { ok: false, error: "serviço indisponível" };
  }
  try {
    const { error } = await supabaseClient
      .from("newsletter_subscribers")
      .insert({ email: value, source });
    if (error) return { ok: false, error: error.message };
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err.message || String(err) };
  }
}
window.subscribeNewsletter = subscribeNewsletter;

/* LOTE 6 (6.3): Ads dinâmicos via Supabase — interstitial e sidebar.
 * Busca o criativo ativo (RPC fn_get_active_ad) e registra eventos
 * (impression/click/skip/error) em ad_events. Sem supabaseClient, resolve null. */
async function fetchActiveAd(format = "audio") {
  if (!supabaseClient) return null;
  try {
    const { data, error } = await supabaseClient.rpc("fn_get_active_ad", {
      p_format: format || null,
    });
    if (error) throw error;
    return data || null;
  } catch (err) {
    console.warn("[ads] fetchActiveAd:", err);
    return null;
  }
}
window.__supabaseFetchActiveAd = fetchActiveAd;

function recordAdEvent(creativeId, campaignId, eventType, sessionId) {
  if (!supabaseClient || !creativeId) return;
  try {
    supabaseClient
      .rpc("fn_record_ad_event", {
        p_creative_id: creativeId,
        p_campaign_id: campaignId || null,
        p_event_type: eventType,
        p_session_id: sessionId || null,
      })
      .then(() => {})
      .catch((err) => console.warn("[ads] recordAdEvent:", err));
  } catch (err) {
    console.warn("[ads] recordAdEvent:", err);
  }
}
window.__supabaseRecordAdEvent = recordAdEvent;

/* MONETIZAÇÃO: busca configuração pública do AdSense (fn_get_monetization_config).
 * Retorna o primeiro objeto do array (ou o próprio objeto); null em caso de erro. */
async function fetchMonetizationConfig() {
  if (!supabaseClient) return null;
  try {
    const { data, error } = await supabaseClient.rpc("fn_get_monetization_config");
    if (error) throw error;
    // RPC pode retornar array ou objeto único dependendo da versão do SDK
    return Array.isArray(data) ? (data[0] || null) : (data || null);
  } catch (err) {
    console.warn("[monetization] fetchMonetizationConfig:", err);
    return null;
  }
}
window.__supabaseFetchMonetizationConfig = fetchMonetizationConfig;

/* MONETIZAÇÃO: busca patrocinadores por datas de episódio (get_episode_sponsors).
 * episodeDates: array de strings ou null → retorna mapa date→sponsors (objeto).
 * Em caso de erro retorna {} para não quebrar o fluxo. */
async function fetchEpisodeSponsors(episodeDates = null) {
  if (!supabaseClient) return {};
  try {
    const { data, error } = await supabaseClient.rpc("get_episode_sponsors", {
      p_episode_dates: Array.isArray(episodeDates) ? episodeDates : null,
    });
    if (error) throw error;
    return data || {};
  } catch (err) {
    console.warn("[monetization] fetchEpisodeSponsors:", err);
    return {};
  }
}
window.__supabaseFetchEpisodeSponsors = fetchEpisodeSponsors;

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (m) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m])
  );
}
function escapeAttr(s) { return escapeHtml(s).replace(/`/g, ""); }

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initSupabase);
} else {
  initSupabase();
}
