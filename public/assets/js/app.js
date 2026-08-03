/* Vale da Liberdade — Coordinador de la Aplicación (PWA) */
(() => {
  const DATA_URL = "./data/episodes.json";
  const $ = (sel, el = document) => el.querySelector(sel);
  const $$ = (sel, el = document) => el.querySelectorAll(sel);

  const state = {
    episodes: [],
    currentId: null,
    deferredPrompt: null,
    activeTab: "diario",
  };

  // Referencias a los elementos del DOM
  const els = {
    todayShell: $("#todayShell"),
    timeline: $("#timeline"),
    feedEnd: $("#feedEnd"),
    btnRefresh: $("#btnRefresh"),
    btnInstall: $("#btnInstall"),
    tabs: $$(".tab-btn"),

    // Menu Lateral (Side Drawer)
    btnMenu: $("#btnMenu"),
    drawerOverlay: $("#sideDrawerOverlay"),
    drawerCloseBtn: $("#drawerCloseBtn"),
    drawerThemeToggleBtn: $("#drawerThemeToggleBtn"),
    drawerThemeLabel: $("#drawerThemeLabel"),
    drawerNavItems: $$(".drawer-nav-item"),

    // Mini Player
    mini: $("#miniPlayer"),
    miniCover: $("#miniCover"),
    miniOpenFull: $("#miniOpenFull"),
    miniPlay: $("#miniPlay"),
    miniTitle: $("#miniTitle"),
    miniSub: $("#miniSub"),
    miniProgressFill: $(".mini-progress-fill"),
    miniSeekBar: $("#miniSeekBar"),
    miniSkipBack: $("#miniSkipBack"),
    miniSkipForward: $("#miniSkipForward"),
    miniExpand: $("#miniExpand"),

    // Expanded Player
    fullOverlay: $("#fullPlayerOverlay"),
    fullClose: $("#fullPlayerClose"),
    fullModalThemeToggle: $("#fullModalThemeToggle"),
    fullCover: $("#fullCover"),
    fullTitle: $("#fullEpisodeTitle"),
    fullMeta: $("#fullEpisodeMeta"),
    fullSlider: $("#fullScrubberSlider"),
    fullCurrentTime: $("#fullCurrentTime"),
    fullTotalDuration: $("#fullTotalDuration"),
    fullPlayPause: $("#fullPlayPause"),
    fullPrevEp: $("#fullPrevEp"),
    fullNextEp: $("#fullNextEp"),
    fullSkipBack: $("#fullSkipBack"),
    fullSkipForward: $("#fullSkipForward"),
    fullSpeedPill: $("#fullSpeedPill"),
    fullFav: $("#fullFavBtn"),
    fullShowNotes: $("#fullShowNotesContainer")
  };

  const QUADRO_LABEL = {
    seguranca: "#segurança",
    saude: "#saúde",
    educacao: "#educação",
    politica: "#política",
    esportes: "#esportes",
    brasil: "#brasil",
    mundo: "#mundo",
    rapidinhas: "#rapidinhas",
  };

  function formatDateBR(iso) {
    if (!iso) return "";
    const [y, m, d] = iso.split("-").map(Number);
    try {
      return new Date(y, m - 1, d).toLocaleDateString("pt-BR", {
        day: "2-digit",
        month: "short",
        year: "numeric",
      });
    } catch {
      return iso;
    }
  }

  function formatDuration(min) {
    if (!min && min !== 0) return "—";
    const total = Math.round(Number(min) * 60);
    const m = Math.floor(total / 60);
    const s = total % 60;
    if (m >= 60) {
      const h = Math.floor(m / 60);
      return `${h}h ${m % 60}min`;
    }
    return `${m} min`;
  }

  function fmtClock(sec) {
    if (!Number.isFinite(sec)) return "0:00";
    const s = Math.max(0, Math.floor(sec));
    const m = Math.floor(s / 60);
    const r = s % 60;
    return `${m}:${String(r).padStart(2, "0")}`;
  }

  function episodeUrl(ep) {
    try {
      const u = new URL(window.location.origin);
      u.hash = `ep-${ep.id}`;
      return u.href;
    } catch {
      return window.location.origin + "/";
    }
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  const SVG_CHEVRON = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0;margin-top:4px"><polyline points="9 18 15 12 9 6"></polyline></svg>`;
  const SVG_PLAY = `<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" style="vertical-align:-2px"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>`;
  const SVG_PAUSE = `<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" style="vertical-align:-2px"><rect x="6" y="4" width="4" height="16"></rect><rect x="14" y="4" width="4" height="16"></rect></svg>`;
  const SVG_FULL_PLAY = `<svg width="36" height="36" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-left:3px"><path d="M5 5a2 2 0 0 1 3.008-1.728l11.997 6.998a2 2 0 0 1 .003 3.458l-12 7A2 2 0 0 1 5 19z"></path></svg>`;
  const SVG_FULL_PAUSE = `<svg width="36" height="36" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="4" width="4" height="16" rx="1"></rect><rect x="14" y="4" width="4" height="16" rx="1"></rect></svg>`;
  const SVG_MINI_PLAY = `<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-left:2px"><path d="M5 5a2 2 0 0 1 3.008-1.728l11.997 6.998a2 2 0 0 1 .003 3.458l-12 7A2 2 0 0 1 5 19z"></path></svg>`;
  const SVG_MINI_PAUSE = `<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="4" width="4" height="16" rx="1"></rect><rect x="14" y="4" width="4" height="16" rx="1"></rect></svg>`;

  function renderShowNotes(manchetes) {
    if (!manchetes || !manchetes.length) return "";
    return `
      <div class="shownotes-list">
        ${manchetes.map(m => `
          <div class="shownote-item">
            <span class="shownote-icon">${SVG_CHEVRON}</span>
            <div class="shownote-content">
              <strong>${escapeHtml(m)}</strong>
            </div>
          </div>
        `).join("")}
      </div>`;
  }

  function tagsHtml(quadros = []) {
    return (quadros || [])
      .slice(0, 5)
      .map((q) => {
        const label = QUADRO_LABEL[q] || `#${q}`;
        return `<span class="tag">${escapeHtml(label)}</span>`;
      })
      .join("");
  }

  function linksHtml(ep) {
    const url = episodeUrl(ep);
    const date = escapeHtml(ep.date);
    const icons = {
      share: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"></path><polyline points="16 6 12 2 8 6"></polyline><line x1="12" y1="2" x2="12" y2="15"></line></svg>`,
      like: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"></path></svg>`,
      dislike: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3zm7-13h3a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-3"></path></svg>`,
      copy: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>`
    };
    return `
      <button type="button" class="card-icon" data-action="copy" data-date="${date}" data-url="${escapeHtml(url)}" aria-label="Copiar link" title="Copiar link">${icons.copy}</button>
      <button type="button" class="card-icon" data-action="share" data-date="${date}" data-url="${escapeHtml(url)}" aria-label="Compartilhar" title="Compartilhar">${icons.share}</button>
      <button type="button" class="card-icon like" data-action="like" data-date="${date}" aria-label="Gostei" title="Gostei">${icons.like}</button>
      <button type="button" class="card-icon dislike" data-action="dislike" data-date="${date}" aria-label="Não gostei" title="Não gostei">${icons.dislike}</button>`;
  }

  // SVGs para linha de ação (§6.7)
  const SVG_ACTION_PLAY = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>`;
  const SVG_ACTION_SHARE = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="18" cy="5" r="3"></circle><circle cx="6" cy="12" r="3"></circle><circle cx="18" cy="19" r="3"></circle><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"></line><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"></line></svg>`;
  const SVG_ACTION_SAVE = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path></svg>`;
  const SVG_ACTION_COPY = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>`;

  function feedActionRowHtml(epId, epDate, epUrl) {
    return `
      <div class="feed-action-row" role="toolbar" aria-label="Ações do episódio">
        <button type="button" class="feed-action-btn" data-play="${escapeHtml(epId)}" aria-label="Ouvir episódio">${SVG_ACTION_PLAY}</button>
        <button type="button" class="feed-action-btn" data-action="share" data-date="${escapeHtml(epDate)}" data-url="${escapeHtml(epUrl)}" aria-label="Compartilhar">${SVG_ACTION_SHARE}</button>
        <button type="button" class="feed-action-btn" data-action="copy" data-date="${escapeHtml(epDate)}" data-url="${escapeHtml(epUrl)}" aria-label="Copiar link">${SVG_ACTION_COPY}</button>
        <button type="button" class="feed-action-btn" data-action="save" data-date="${escapeHtml(epDate)}" aria-label="Salvar">${SVG_ACTION_SAVE}</button>
      </div>`;
  }

  function renderToday(ep) {
    if (!ep) {
      els.todayShell.innerHTML = `
        <div class="empty-today" style="padding: var(--space-5) var(--space-4); color: var(--color-ink-muted);">
          <h2 style="font-size:1.1rem;margin-bottom:8px">Sem episódio publicado</h2>
          <p>Rode o pipeline para gerar o episódio do dia.</p>
        </div>`;
      // PERF-004/009: libera o placeholder de CLS quando o empty state chega
      els.todayShell.classList.remove("is-loading");
      return;
    }

    const isEspecial = ep.type === "especial";
    const kickerText = isEspecial ? "ESPECIAL · BRASIL & MUNDO" : "DESTAQUE DO DIA";
    const epLabel = isEspecial ? "Peter Solo" : `Ep. ${escapeHtml(ep.episode ?? "—")}`;
    const epUrl = episodeUrl(ep);
    // Capa por episódio ainda não implementada — usa variações da capa padrão (geradas 1x por scripts/generate_cover_variants.py)
    const isCustomCover = Boolean(ep.cover_url);
    const heroWebpSet = isCustomCover ? null : "./assets/cover-400.webp 400w, ./assets/cover-800.webp 800w, ./assets/cover-1200.webp 1200w";
    const heroJpgSet = isCustomCover ? null : "./assets/cover-400.jpg 400w, ./assets/cover-800.jpg 800w, ./assets/cover-1200.jpg 1200w";
    const heroSizes = "(min-width: 1024px) 45vw, (min-width: 768px) 45vw, 100vw";
    // fallback universal: JPEG (trocado a pedido — JPG é suportado em todo lugar)
    const heroBackstop = isCustomCover ? ep.cover_url : "./assets/cover-800.jpg";

    let excerptText = ep.excerpt || "Uma análise profunda sobre os principais acontecimentos do Vale da Liberdade e Santa Catarina.";
    if (!isEspecial && ep.manchetes && ep.manchetes.length) {
      excerptText = ep.manchetes.slice(0, 3).join(" · ");
    }

    const heroImgMarkup = isCustomCover
      ? `<img src="${ep.cover_url}" alt="${escapeHtml(ep.title || 'Capa do Episódio')}" class="hero-cover-img" fetchpriority="high" decoding="async" onError="this.onerror=null;this.src='./assets/cover-800.jpg'" />`
      : `<picture>
          <source type="image/webp" srcset="${heroWebpSet}" sizes="${heroSizes}">
          <source type="image/jpeg" srcset="${heroJpgSet}" sizes="${heroSizes}">
          <img src="${heroBackstop}" alt="${escapeHtml(ep.title || 'Capa do Episódio')}" class="hero-cover-img" width="800" height="800" fetchpriority="high" decoding="sync" onError="this.onerror=null;this.src='./assets/cover.jpg'" />
        </picture>`;

    els.todayShell.innerHTML = `
      <article class="hero-card" data-id="${escapeHtml(ep.id)}">
        <!-- Badge Destaque -->
        <div class="hero-badge">
          <span class="pulse-dot"></span>
          <span>${kickerText}</span>
        </div>

        <!-- Cover Container (Esquerda) — reserva de espaço via aspect-ratio no CSS -->
        <div class="hero-cover-wrap">
          ${heroImgMarkup}
          <div class="hero-cover-overlay"></div>
        </div>

        <!-- Content Container (Direita) -->
        <div class="hero-content">
          <div>
            <h2 class="hero-title">${escapeHtml(ep.title || `Edição de ${formatDateBR(ep.date)}`)}</h2>
            <p class="hero-desc">${escapeHtml(excerptText)}</p>
          </div>

          <div class="hero-footer">
            <div class="hero-meta">
              <div class="host-avatars">
                <div class="avatar peter">P</div>
                ${!isEspecial ? `<div class="avatar ricardo">R</div>` : ''}
              </div>
              <div class="meta-info">
                <span class="meta-date">${escapeHtml(formatDateBR(ep.date))}</span>
                <span class="meta-dot">·</span>
                <span class="meta-duration">${escapeHtml(formatDuration(ep.duration_min))}</span>
              </div>
            </div>

            <button type="button" class="hero-play-btn" data-play="${escapeHtml(ep.id)}" title="Ouvir episódio">
              ${SVG_PLAY}
            </button>
          </div>
        </div>
      </article>`;
    // PERF-004/009: libera o placeholder de CLS quando o hero real chega
    els.todayShell.classList.remove("is-loading");
  }


  function parseEpisodeDate(epOrIso) {
    // Aceita objeto de episódio ou string (pubDate RFC2822 / ISO / YYYY-MM-DD).
    // Especiais BM: preferir pubDate (hora real). Diários: só date (YYYY-MM-DD),
    // pois published_at no catálogo é o horário do publish_site (igual p/ todos).
    // Retorna { date, hasTime } — hasTime=false evita "HÁ X MINUTOS" em data pura.
    let raw = epOrIso;
    if (epOrIso && typeof epOrIso === "object") {
      if (epOrIso.type === "especial") {
        raw = epOrIso.pubDate || epOrIso.date || "";
      } else {
        raw = epOrIso.date || epOrIso.pubDate || "";
      }
    }
    if (!raw) return null;

    // YYYY-MM-DD puro → meia-noite local + flag date-only
    if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) {
      const [y, m, d] = raw.split("-").map(Number);
      return { date: new Date(y, m - 1, d, 0, 0, 0), hasTime: false };
    }

    const t = Date.parse(raw);
    if (Number.isNaN(t)) return null;
    return { date: new Date(t), hasTime: true };
  }

  function isoWeekKey(date) {
    // ISO week key: YYYY-Www (útil p/ filtrar áudios por semana no futuro)
    const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
    const dayNum = d.getUTCDay() || 7;
    d.setUTCDate(d.getUTCDate() + 4 - dayNum);
    const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
    const weekNo = Math.ceil((((d - yearStart) / 86400000) + 1) / 7);
    return `${d.getUTCFullYear()}-W${String(weekNo).padStart(2, "0")}`;
  }

  function calendarDaysBetween(a, b) {
    // Diferença em dias de calendário local (ignora horário)
    const ua = Date.UTC(a.getFullYear(), a.getMonth(), a.getDate());
    const ub = Date.UTC(b.getFullYear(), b.getMonth(), b.getDate());
    return Math.floor((ub - ua) / 86400000);
  }

  function formatRelativeTime(epOrIso) {
    const parsed = parseEpisodeDate(epOrIso);
    if (!parsed) return "RECENTE";

    const now = new Date();
    const target = parsed.date;

    // Data pura (diários): HOJE / ONTEM / HÁ N DIAS / HÁ N SEMANAS
    if (!parsed.hasTime) {
      const dayDiff = calendarDaysBetween(target, now);
      if (dayDiff <= 0) return "HOJE";
      if (dayDiff === 1) return "ONTEM";
      if (dayDiff < 7) return `HÁ ${dayDiff} DIAS`;
      const weeks = Math.floor(dayDiff / 7);
      return weeks === 1 ? "HÁ 1 SEMANA" : `HÁ ${weeks} SEMANAS`;
    }

    // Timestamp real (especiais BM): minutos → horas → ontem → dias → semanas
    let diffMs = now - target;
    if (diffMs < 0) diffMs = 0;

    const sec = Math.floor(diffMs / 1000);
    const min = Math.floor(sec / 60);
    const hr = Math.floor(min / 60);
    const day = Math.floor(hr / 24);

    if (min < 1) return "HÁ 1 MINUTO";
    if (min < 60) return min === 1 ? "HÁ 1 MINUTO" : `HÁ ${min} MINUTOS`;
    if (hr < 24) return hr === 1 ? "HÁ 1 HORA" : `HÁ ${hr} HORAS`;
    if (day === 1) return "ONTEM";
    if (day < 7) return `HÁ ${day} DIAS`;

    const weeks = Math.floor(day / 7);
    return weeks === 1 ? "HÁ 1 SEMANA" : `HÁ ${weeks} SEMANAS`;
  }

  function renderCard(ep, isToday = false) {
    const isEspecial = ep.type === "especial";
    const cardClass = isEspecial ? "tweet-card especial-card" : "tweet-card";
    const avatarHtml = isEspecial
      ? `<div class="host-avatars" aria-hidden="true"><div class="avatar peter" title="Peter">P</div></div>`
      : `<div class="host-avatars" aria-hidden="true"><div class="avatar peter" title="Peter">P</div><div class="avatar ricardo" title="Ricardo">R</div></div>`;

    const parsed = parseEpisodeDate(ep);
    const relativeTime = formatRelativeTime(ep);
    const publishedIso = parsed ? parsed.date.toISOString() : "";
    const weekKey = parsed ? isoWeekKey(parsed.date) : "";

    return `
      <article class="${cardClass}" data-id="${escapeHtml(ep.id)}" data-published="${escapeHtml(publishedIso)}" data-week="${escapeHtml(weekKey)}" style="position: relative;">
        <!-- Top Right Action Icons (Stitch Mockup) -->
        <div style="position: absolute; top: 16px; right: 16px; display: flex; align-items: center; gap: 8px; color: var(--color-ink-muted);">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="opacity:0.7"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><circle cx="8.5" cy="8.5" r="1.5"></circle><polyline points="21 15 16 10 5 21"></polyline></svg>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="opacity:0.7"><circle cx="12" cy="12" r="1"></circle><circle cx="12" cy="5" r="1"></circle><circle cx="12" cy="19" r="1"></circle></svg>
        </div>

        <div class="card-body">
          <div class="card-head" style="margin-bottom: 6px;">
            <span class="date" style="font-family: var(--font-mono); font-size: 0.7rem; font-weight: 700; color: var(--color-accent); text-transform: uppercase;">${relativeTime}</span>
          </div>
          <h3 class="card-title">${escapeHtml(ep.title || `Edição de ${formatDateBR(ep.date)}`)}</h3>
          <p class="card-excerpt">${escapeHtml(ep.excerpt || (isEspecial ? "Comentário solo do Peter." : "Cobertura diária do Vale."))}</p>
          <div class="tags" style="margin-top: 10px; margin-bottom: 14px;">${tagsHtml(ep.quadros)}</div>

          <div class="card-actions" style="display: flex; align-items: center; justify-content: space-between; margin-top: 6px;">
            <div class="card-footer-left" style="display: flex; align-items: center; gap: 8px;">
              ${avatarHtml}
            </div>
            <div class="card-footer-right" style="display: flex; align-items: center; gap: 12px;">
              <span class="stat" style="font-family: var(--font-mono); font-size: 0.78rem;">${escapeHtml(formatDuration(ep.duration_min))}</span>
              <button type="button" class="hero-play-btn" data-play="${escapeHtml(ep.id)}" ${ep.audio_url ? "" : "disabled"} style="width: 36px; height: 36px;" title="Ouvir episódio">
                ${SVG_PLAY}
              </button>
            </div>
          </div>
        </div>
      </article>`;
  }

  function renderTimeline(list) {
    if (!list.length) {
      els.timeline.innerHTML = `<p class="muted" style="padding:16px; text-align:center;">Nenhum episódio no catálogo ainda.</p>`;
      els.feedEnd.hidden = true;
      return;
    }
    const adTpl = $("#adCardTemplate");
    let html = "";
    list.forEach((ep, i) => {
      html += renderCard(ep, i === 0);
      if ((i + 1) % 4 === 0 && adTpl) {
        html += adTpl.innerHTML;
      }
    });
    els.timeline.innerHTML = html;
    els.feedEnd.hidden = false;
    if (typeof window.__supabaseApplyThumbs === "function") {
      window.__supabaseApplyThumbs();
    }
  }

  function findEp(id) {
    return state.episodes.find((e) => e.id === id);
  }

  /** Ordena do mais recente → mais antigo (hero = list[0]). */
  function episodeRecencyMs(ep) {
    const parsed = parseEpisodeDate(ep);
    if (parsed && parsed.date && !Number.isNaN(parsed.date.getTime())) {
      return parsed.date.getTime();
    }
    // fallback estável
    const t = Date.parse(ep.published_at || ep.pubDate || ep.date || 0);
    return Number.isNaN(t) ? 0 : t;
  }

  function sortEpisodesNewestFirst(list) {
    return list.slice().sort((a, b) => {
      const diff = episodeRecencyMs(b) - episodeRecencyMs(a);
      if (diff !== 0) return diff;
      // desempate estável por id (evita reorder aleatório)
      return String(b.id || "").localeCompare(String(a.id || ""));
    });
  }

  function getFilteredEpisodes() {
    const filtered = state.episodes.filter(e => {
      if (state.activeTab === "especial") {
        return e.type === "especial";
      } else if (state.activeTab === "investimentos") {
        const q = (e.quadros || []).map(k => k.toLowerCase());
        return q.includes("economia") || q.includes("investimentos") || q.includes("mercado");
      } else if (state.activeTab === "tecnologia") {
        const q = (e.quadros || []).map(k => k.toLowerCase());
        return q.includes("tecnologia") || q.includes("cultura") || q.includes("ciência") || q.includes("ciencia");
      } else {
        // "todos" e "diario": mostrar tudo exceto especiais
        return e.type !== "especial";
      }
    });
    return sortEpisodesNewestFirst(filtered);
  }

  function findNextEpisode(currentId) {
    const list = getFilteredEpisodes();
    const idx = list.findIndex(e => e.id === currentId);
    if (idx !== -1 && idx < list.length - 1) {
      return list[idx + 1];
    }
    return null;
  }

  function updatePlayerUI(isPlaying) {
    // Atualiza todos os botões de play na página
    const currentId = state.currentId;
    document.querySelectorAll(".play-btn").forEach((btn) => {
      const isThisBtn = btn.getAttribute("data-play") === currentId;
      btn.classList.toggle("playing", isThisBtn && isPlaying);
      const icon = btn.querySelector(".play-icon");
      if (icon) {
        icon.innerHTML = isThisBtn && isPlaying ? SVG_PAUSE : SVG_PLAY;
      }
    });

    // Atualiza controles do Mini Player
    if (els.mini) {
      els.mini.dataset.playing = isPlaying ? "true" : "false";
    }
    if (els.miniPlay) {
      els.miniPlay.innerHTML = isPlaying ? SVG_MINI_PAUSE : SVG_MINI_PLAY;
    }

    // Atualiza controles do Expanded Player
    if (els.fullPlayPause) {
      els.fullPlayPause.innerHTML = isPlaying ? SVG_FULL_PAUSE : SVG_FULL_PLAY;
    }
  }

  function updateFullPlayerMetadata(ep) {
    if (!ep) return;
    if (els.fullTitle) els.fullTitle.textContent = ep.title || `Edição de ${formatDateBR(ep.date)}`;
    if (els.fullMeta) {
      els.fullMeta.textContent = ep.type === "especial" ? "Peter Albuquerque" : "Ricardo Souto";
    }
    if (els.fullCover) {
      els.fullCover.src = ep.cover || "./assets/cover.jpg";
    }
    if (els.fullFav) {
      els.fullFav.dataset.favDate = ep.date;
    }
  }

  function playEpisode(id) {
    const ep = findEp(id);
    if (!ep || !ep.audio_url) return;

    if (state.currentId !== id) {
      state.currentId = id;
      
      // Atualiza textos do Mini Player
      if (els.miniCover) els.miniCover.src = ep.cover || "./assets/cover.jpg";
      if (els.miniTitle) els.miniTitle.textContent = ep.title || ep.date;
      if (els.miniSub) {
        const totalSecs = ep.duration_min ? ep.duration_min * 60 : 0;
        els.miniSub.textContent = `${fmtClock(0)} / ${fmtClock(totalSecs)}`;
      }
      
      // Atualiza textos do Expanded Player
      updateFullPlayerMetadata(ep);
      
      // Reseta valores dos timelines
      if (els.miniProgressFill) els.miniProgressFill.style.width = "0%";
      if (els.fullSlider) els.fullSlider.value = 0;
      if (els.fullCurrentTime) els.fullCurrentTime.textContent = "0:00";
      if (els.fullTotalDuration) els.fullTotalDuration.textContent = "0:00";

      window.PlayerManager.load(ep);
    }

    if (els.mini) els.mini.classList.remove("hidden");
    window.PlayerManager.play();
  }

  // --- Subscripción a eventos del PlayerManager ---
  window.addEventListener("playerevent", (e) => {
    const { type, currentTime, duration, paused, episode } = e.detail;

    if (type === "play") {
      updatePlayerUI(true);
    } else if (type === "pause" || type === "ended") {
      updatePlayerUI(false);
    } else if (type === "timeupdate") {
      const validDur = (Number.isFinite(duration) && duration > 0) ? duration : 0;
      const pct = validDur ? Math.min(100, Math.max(0, (currentTime / validDur) * 100)) : 0;
      
      // Atualiza progresso do Mini Player
      if (els.miniProgressFill) els.miniProgressFill.style.width = `${pct}%`;
      if (els.miniSub) {
        const dur = validDur || (episode && episode.duration_min ? episode.duration_min * 60 : 0);
        els.miniSub.textContent = `${fmtClock(currentTime)} / ${fmtClock(dur)}`;
      }

      // Atualiza progresso do Expanded Player
      if (els.fullSlider) {
        els.fullSlider.value = pct;
      }
      if (els.fullCurrentTime) {
        els.fullCurrentTime.textContent = fmtClock(currentTime);
      }
    } else if (type === "loadedmetadata" || type === "durationchange") {
      if (els.fullTotalDuration) {
        els.fullTotalDuration.textContent = fmtClock(duration);
      }
      if (els.miniSub && duration) {
        els.miniSub.textContent = `${fmtClock(currentTime || 0)} / ${fmtClock(duration)}`;
      }
    }
  });

  function showToast(msg, ms = 2000) {
    let ex = document.getElementById("toast");
    if (!ex) {
      ex = document.createElement("div");
      ex.id = "toast";
      ex.style.cssText = "position:fixed;bottom:80px;left:50%;transform:translateX(-50%);background:var(--color-ink);color:var(--color-bg);padding:8px 16px;border-radius:var(--radius-pill);font-size:.85rem;z-index:9999;box-shadow:0 4px 12px rgba(0,0,0,.15);border:1px solid var(--color-border);font-weight:500;";
      document.body.appendChild(ex);
    }
    ex.textContent = msg;
    clearTimeout(showToast._t);
    showToast._t = setTimeout(() => ex.remove(), ms);
  }

  function bindSocialButtons() {
    document.addEventListener("click", async (ev) => {
      const btn = ev.target.closest("[data-action]");
      if (!btn) return;
      const action = btn.dataset.action;
      const date = btn.dataset.date;
      const url = btn.dataset.url || window.location.href;

      if (action === "copy") {
        ev.preventDefault();
        try {
          await navigator.clipboard.writeText(url);
          showToast("Link copiado!");
        } catch {
          const tmp = document.createElement("input");
          tmp.value = url;
          document.body.appendChild(tmp);
          tmp.select();
          try {
            document.execCommand("copy");
            showToast("Link copiado!");
          } catch {
            showToast("Não consegui copiar");
          }
          tmp.remove();
        }
        if (typeof window.__supabaseLogEvent === "function") {
          window.__supabaseLogEvent("copy", date);
        }
      }

      if (action === "share") {
        ev.preventDefault();
        const ep = state.episodes.find((x) => x.id === date);
        const title = ep?.title || "Vale da Liberdade";
        if (navigator.share) {
          try {
            await navigator.share({ title, text: `🎧 ${title}`, url });
            showToast("Compartilhado!");
          } catch (err) {
            if (String(err).includes("AbortError")) return;
            navigator.clipboard?.writeText(url).then(() => showToast("Link copiado para compartilhar"));
          }
        } else {
          navigator.clipboard?.writeText(url).then(() => showToast("Link copiado para compartilhar"));
        }
        if (typeof window.__supabaseLogEvent === "function") {
          window.__supabaseLogEvent("share", date);
        }
      }

      if (action === "like") {
        ev.preventDefault();
        await handleThumbs(btn, date, "like");
      }
      if (action === "dislike") {
        ev.preventDefault();
        await handleThumbs(btn, date, "dislike");
      }
    });
  }

  async function handleThumbs(btn, date, kind) {
    const sibling = btn.parentElement?.querySelector(`[data-action="${kind === "like" ? "dislike" : "like"}"]`);
    if (typeof window.__supabaseSetThumbs === "function") {
      try {
        const stateNew = await window.__supabaseSetThumbs(date, kind);
        btn.classList.toggle("active", !!stateNew?.[kind === "like" ? "thumbs_up" : "thumbs_down"]);
        if (sibling) sibling.classList.remove("active");
      } catch (err) {
        showToast("Faça login com o Google para avaliar");
      }
    } else {
      showToast("Faça login com o Google para avaliar");
    }
  }

  function bindUI() {
    // Menu Hamburguer (Side Drawer Navigation)
    const updateDrawerThemeUI = () => {
      const isDark = document.documentElement.getAttribute("data-theme") === "dark";
      if (els.drawerThemeLabel) {
        els.drawerThemeLabel.textContent = isDark ? "Modo Escuro" : "Modo Claro (Padrão)";
      }
    };

    const openDrawer = () => {
      if (els.drawerOverlay) {
        updateDrawerThemeUI();
        els.drawerOverlay.classList.add("active");
      }
    };

    const closeDrawer = () => {
      if (els.drawerOverlay) {
        els.drawerOverlay.classList.remove("active");
      }
    };

    if (els.btnMenu) {
      els.btnMenu.addEventListener("click", openDrawer);
    }

    if (els.drawerCloseBtn) {
      els.drawerCloseBtn.addEventListener("click", closeDrawer);
    }

    if (els.drawerOverlay) {
      els.drawerOverlay.addEventListener("click", (e) => {
        if (e.target === els.drawerOverlay) closeDrawer();
      });
    }

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") closeDrawer();
    });

    if (els.drawerThemeToggleBtn) {
      els.drawerThemeToggleBtn.addEventListener("click", () => {
        const toggleBtn = $("#themeToggle");
        if (toggleBtn) toggleBtn.click();
        updateDrawerThemeUI();
      });
    }

    if (els.drawerNavItems && els.drawerNavItems.length) {
      els.drawerNavItems.forEach(item => {
        item.addEventListener("click", () => {
          const tab = item.dataset.drawerTab;
          if (tab) {
            state.activeTab = tab;
            if (els.tabs && els.tabs.length) {
              els.tabs.forEach(b => {
                const active = b.dataset.tab === tab;
                b.classList.toggle("active", active);
                b.setAttribute("aria-selected", active ? "true" : "false");
              });
            }
            els.drawerNavItems.forEach(i => i.classList.toggle("active", i === item));
            renderFilteredFeed();
            closeDrawer();
          }
        });
      });
    }

    // Clique em qualquer Play na página
    document.addEventListener("click", (ev) => {
      const btn = ev.target.closest("[data-play]");
      if (!btn) return;
      const id = btn.getAttribute("data-play");
      if (!id) return;
      
      const audioState = window.PlayerManager.getAudioState();
      if (state.currentId === id && !audioState.paused) {
        window.PlayerManager.pause();
      } else {
        playEpisode(id);
      }
    });

    // Controles do Mini Player
    if (els.miniPlay) {
      els.miniPlay.addEventListener("click", (e) => {
        e.stopPropagation();
        const ep = findEp(state.currentId);
        window.PlayerManager.togglePlay(ep);
      });
    }

    if (els.miniSkipBack) {
      els.miniSkipBack.addEventListener("click", (e) => {
        e.stopPropagation();
        window.PlayerManager.skip(-10);
      });
    }

    if (els.miniSkipForward) {
      els.miniSkipForward.addEventListener("click", (e) => {
        e.stopPropagation();
        window.PlayerManager.skip(10);
      });
    }

    const openFullPlayer = () => {
      const currentEp = findEp(state.currentId);
      if (currentEp) updateFullPlayerMetadata(currentEp);
      if (els.fullOverlay) {
        els.fullOverlay.classList.add("expanded");
      }
    };

    if (els.miniOpenFull) {
      els.miniOpenFull.addEventListener("click", openFullPlayer);
    }

    if (els.miniExpand) {
      els.miniExpand.addEventListener("click", (e) => {
        e.stopPropagation();
        openFullPlayer();
      });
    }

    if (els.miniSeekBar) {
      els.miniSeekBar.addEventListener("click", (e) => {
        e.stopPropagation();
        const rect = els.miniSeekBar.getBoundingClientRect();
        if (rect.width <= 0) return;
        const clickX = e.clientX - rect.left;
        const pct = Math.max(0, Math.min(100, (clickX / rect.width) * 100));
        window.PlayerManager.seek(pct);
      });
    }

    // Controles do Player Expandido
    if (els.fullClose) {
      els.fullClose.addEventListener("click", () => {
        els.fullOverlay.classList.remove("expanded");
      });
    }

    if (els.fullModalThemeToggle) {
      els.fullModalThemeToggle.addEventListener("click", () => {
        const toggleBtn = $("#themeToggle");
        if (toggleBtn) toggleBtn.click();
      });
    }

    if (els.fullPlayPause) {
      els.fullPlayPause.addEventListener("click", () => {
        const ep = findEp(state.currentId);
        window.PlayerManager.togglePlay(ep);
      });
    }

    if (els.fullPrevEp) {
      els.fullPrevEp.addEventListener("click", () => {
        const list = getFilteredEpisodes();
        const idx = list.findIndex(e => e.id === state.currentId);
        if (idx > 0) {
          playEpisode(list[idx - 1].id);
        }
      });
    }

    if (els.fullNextEp) {
      els.fullNextEp.addEventListener("click", () => {
        const list = getFilteredEpisodes();
        const idx = list.findIndex(e => e.id === state.currentId);
        if (idx !== -1 && idx < list.length - 1) {
          playEpisode(list[idx + 1].id);
        }
      });
    }

    if (els.fullSkipBack) {
      els.fullSkipBack.addEventListener("click", () => {
        window.PlayerManager.skip(-15);
      });
    }

    if (els.fullSkipForward) {
      els.fullSkipForward.addEventListener("click", () => {
        window.PlayerManager.skip(15);
      });
    }

    if (els.fullSlider) {
      els.fullSlider.addEventListener("input", (e) => {
        window.PlayerManager.seek(parseFloat(e.target.value));
      });
    }

    const speeds = [1, 1.25, 1.5, 2];
    let currentSpeedIdx = 0;
    if (els.fullSpeedPill) {
      els.fullSpeedPill.addEventListener("click", () => {
        currentSpeedIdx = (currentSpeedIdx + 1) % speeds.length;
        const rate = speeds[currentSpeedIdx];
        window.PlayerManager.setPlaybackRate(rate);
        els.fullSpeedPill.textContent = `${rate}x`;
      });
    }

    if (els.fullFav) {
      els.fullFav.addEventListener("click", (e) => {
        const date = els.fullFav.dataset.favDate;
        if (date && typeof window.toggleFavoriteEpisode === "function") {
          window.toggleFavoriteEpisode(date, `Edição de ${formatDateBR(date)}`);
        } else {
          showToast("Função favoritar indisponível");
        }
      });
    }
  }

  function renderFilteredFeed() {
    // Mesma regra de filtro + ordenação (mais recente → mais antigo).
    // Hero = list[0]; timeline = list.slice(1) para não duplicar o destaque.
    const list = getFilteredEpisodes();

    const todayEp = list[0] || null;
    renderToday(todayEp);
    renderTimeline(list.slice(1));

    // Auto-carrega o primeiro episódio no miniplayer se houver áudio
    if (todayEp && todayEp.audio_url && !state.currentId) {
      state.currentId = todayEp.id;
      if (els.miniTitle) els.miniTitle.textContent = todayEp.title || todayEp.date;
      if (els.miniSub) {
        els.miniSub.textContent = todayEp.type === "especial"
          ? `${formatDateBR(todayEp.date)} · Peter (Solo)`
          : `${formatDateBR(todayEp.date)} · Peter & Ricardo`;
      }
      updateFullPlayerMetadata(todayEp);
      if (els.mini) els.mini.classList.remove("hidden");
      
      window.PlayerManager.load(todayEp);
    }
  }

  async function loadFeed() {
    try {
      const res = await fetch(`${DATA_URL}?t=${Date.now()}`, { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      state.episodes = Array.isArray(data.episodes) ? data.episodes : [];
      renderFilteredFeed();
    } catch (err) {
      console.error("loadFeed failed:", err);
      els.todayShell.innerHTML = `
        <div class="empty-today" style="padding: var(--space-5) var(--space-4); color: var(--color-ink-muted);">
          <h2 style="font-size:1.1rem;margin-bottom:8px">Feed temporariamente disponível</h2>
          <p>Verifique a conexão ou tente mais tarde.</p>
        </div>`;
    }
  }

  function bindTabs() {
    if (!els.tabs || !els.tabs.length) return;
    els.tabs.forEach(btn => {
      btn.addEventListener("click", () => {
        const tab = btn.dataset.tab;
        if (state.activeTab === tab) return;
        state.activeTab = tab;
        els.tabs.forEach(b => {
          const active = b.dataset.tab === tab;
          b.classList.toggle("active", active);
          b.setAttribute("aria-selected", active ? "true" : "false");
        });
        renderFilteredFeed();
      });
    });
  }
  function bindPWA() {
    const pwaModal = $("#pwaInstallModal");
    const pwaClose = $("#pwaModalClose");
    const pwaInstallBtn = $("#pwaInstallBtn");
    const pwaIosDismissBtn = $("#pwaIosDismissBtn");
    const pwaGenericBody = $("#pwaInstructionGeneric");
    const pwaIosBody = $("#pwaInstructionIos");

    // Track visit count
    let visitCount = Number(localStorage.getItem("vld_visit_count") || 0) + 1;
    localStorage.setItem("vld_visit_count", String(visitCount));

    // Check standalone mode (already installed)
    const isStandalone = window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true;
    if (isStandalone) return;

    // Check dismissal persistence (7 days)
    const lastDismissed = Number(localStorage.getItem("vld_install_dismissed_at") || 0);
    const SEVEN_DAYS_MS = 7 * 24 * 60 * 60 * 1000;
    if (Date.now() - lastDismissed < SEVEN_DAYS_MS) return;

    // Detect iOS
    const isIos = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;

    window.addEventListener("beforeinstallprompt", (e) => {
      e.preventDefault();
      state.deferredPrompt = e;
    });

    function dismissModal() {
      if (pwaModal) pwaModal.classList.add("hidden");
      localStorage.setItem("vld_install_dismissed_at", String(Date.now()));
    }

    if (pwaClose) pwaClose.addEventListener("click", dismissModal);
    if (pwaIosDismissBtn) pwaIosDismissBtn.addEventListener("click", dismissModal);

    if (pwaInstallBtn) {
      pwaInstallBtn.addEventListener("click", async () => {
        if (state.deferredPrompt) {
          state.deferredPrompt.prompt();
          await state.deferredPrompt.userChoice;
          state.deferredPrompt = null;
        }
        dismissModal();
      });
    }

    // Engagement filter: show modal after 15 seconds if visitCount >= 2
    if (visitCount >= 2 && pwaModal) {
      setTimeout(() => {
        if (isIos) {
          if (pwaGenericBody) pwaGenericBody.classList.add("hidden");
          if (pwaIosBody) pwaIosBody.classList.remove("hidden");
        }
        pwaModal.classList.remove("hidden");
      }, 15000);
    }

    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("./sw.js").catch(() => {});
    }
  }

  if (els.btnRefresh) {
    els.btnRefresh.addEventListener("click", () => loadFeed());
  }

  bindSocialButtons();
  bindUI();
  bindPWA();
  bindTabs();
  loadFeed();

  // Expor funções para uso pelo player.js (auto-play)
  window.getFilteredEpisodes = getFilteredEpisodes;
  window.findNextEpisode = findNextEpisode;
  window.playEpisode = playEpisode;
})();
