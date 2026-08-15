/**
 * Consentimento LGPD + gate AdSense por plano.
 * Play ou "Entendi" = aceite. Premium/VIP nunca vê banner nem AdSense.
 */
(function (window) {
  const LS_KEY = 'vld_' + 'consent_' + 'v1';
  let plan = 'free';
  let loggedIn = false;
  let ready = false;

  function readLocal() {
    try { return JSON.parse(localStorage.getItem(LS_KEY) || 'null'); } catch { return null; }
  }
  function writeLocal(obj) {
    try { localStorage.setItem(LS_KEY, JSON.stringify(obj)); } catch {}
  }
  function hasConsent() {
    const c = readLocal();
    return !!(c && c.essential_accepted_at);
  }
  function isPaid() {
    return plan === 'premium' || plan === 'vip';
  }

  async function fp() {
    if (window.InteractionBar && InteractionBar.generateFingerprint) {
      return InteractionBar.generateFingerprint();
    }
    return null;
  }

  async function refreshPlan() {
    try {
      const client = window.supabaseClient;
      if (!client || typeof client.rpc !== 'function') return;
      const { data, error } = await client.rpc('get_my_plan');
      if (error) throw error;
      const d = data && typeof data === 'object' ? data : {};
      loggedIn = !!d.logged_in;
      plan = d.plan === 'premium' || d.plan === 'vip' ? d.plan : 'free';
    } catch (err) {
      console.warn('[consent] plan', err);
      plan = 'free';
    }
  }

  async function recordConsent() {
    const now = new Date().toISOString();
    writeLocal({ essential_accepted_at: now, plan_at_consent: plan });
    hideBanner();
    try {
      const client = window.supabaseClient;
      if (!client) return;
      const hash = await fp();
      await client.rpc('fn_record_consent', { p_fingerprint: hash || null });
    } catch (err) {
      console.warn('[consent] record', err);
    }
  }

  function hideBanner() {
    const el = document.getElementById('consentBanner');
    if (el) el.hidden = true;
  }

  function showBanner() {
    const el = document.getElementById('consentBanner');
    if (el) el.hidden = false;
  }

  function maybeShowBanner() {
    if (isPaid() || hasConsent()) hideBanner();
    else showBanner();
  }

  window.__consentAllowsAdsense = function () {
    return !isPaid();
  };
  window.__getUserPlan = function () {
    return { plan: plan, logged_in: loggedIn };
  };
  window.__recordConsent = recordConsent;
  window.__deleteMyTracking = async function () {
    const client = window.supabaseClient;
    if (!client) throw new Error('sem cliente');
    const hash = await fp();
    const results = [];
    if (hash) {
      const a = await client.rpc('delete_user_tracking_data', {
        target_id: hash,
        is_fingerprint: true,
      });
      if (a.error) throw a.error;
      results.push(a.data);
    }
    if (loggedIn && window.__supabaseUserId) {
      const uid = window.__supabaseUserId();
      if (uid) {
        const b = await client.rpc('delete_user_tracking_data', {
          target_id: String(uid),
          is_fingerprint: false,
        });
        if (b.error) throw b.error;
        results.push(b.data);
      }
    }
    try { localStorage.removeItem(LS_KEY); } catch {}
    hideBanner();
    return results;
  };

  function wrapMonetization() {
    const orig = window.__supabaseFetchMonetizationConfig;
    if (typeof orig !== 'function' || orig.__consentWrapped) return;
    const wrapped = async function () {
      const cfg = await orig();
      if (!cfg) return cfg;
      if (!window.__consentAllowsAdsense()) {
        return Object.assign({}, cfg, { adsense_enabled: false });
      }
      return cfg;
    };
    wrapped.__consentWrapped = true;
    window.__supabaseFetchMonetizationConfig = wrapped;
  }

  function bindUi() {
    const ok = document.getElementById('consentUnderstand');
    if (ok) ok.addEventListener('click', () => recordConsent());
    window.addEventListener('playerevent', (e) => {
      const t = e.detail && e.detail.type;
      if (t === 'play' && !isPaid() && !hasConsent()) recordConsent();
    });
  }

  async function boot() {
    wrapMonetization();
    await refreshPlan();
    ready = true;
    wrapMonetization();
    maybeShowBanner();
    bindUi();
  }

  wrapMonetization();
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => setTimeout(boot, 200));
  } else {
    setTimeout(boot, 200);
  }
  window.addEventListener('authchange', () => { refreshPlan().then(maybeShowBanner); });
})(window);
