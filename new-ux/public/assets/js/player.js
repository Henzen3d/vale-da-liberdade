/* Vale da Liberdade — Gerenciador de Áudio (Player) */
(() => {
  let audio = null;
  let currentEpisode = null;
  let _pendingEpisode = null;

  function initPlayer() {
    audio = document.getElementById("audioEl");
    if (!audio) {
      audio = document.createElement("audio");
      audio.id = "audioEl";
      audio.preload = "metadata";
      document.body.appendChild(audio);
    }

    // Encaminha eventos do elemento de áudio para o objeto global window
    const events = ["play", "pause", "timeupdate", "ended", "loadedmetadata", "durationchange", "error"];
    events.forEach(evt => {
      audio.addEventListener(evt, (e) => {
        window.dispatchEvent(new CustomEvent("playerevent", {
          detail: {
            type: evt,
            currentTime: audio.currentTime,
            duration: audio.duration || 0,
            paused: audio.paused,
            episode: currentEpisode,
            error: audio.error
          }
        }));
      });
    });

    // Auto-play do próximo episódio quando o atual termina
    audio.addEventListener("ended", () => {
      try {
        if (typeof window.getFilteredEpisodes === "function" && typeof window.playEpisode === "function") {
          const nextEp = window.findNextEpisode(currentEpisode && currentEpisode.id);
          if (nextEp) {
            window.playEpisode(nextEp.id);
          }
        }
      } catch (err) {
        console.warn("auto-play failed:", err);
      }
    });
  }

  function resolveAudioUrl(url) {
    if (!url) return "";
    if (url.startsWith("http://") || url.startsWith("https://") || url.startsWith("blob:")) return url;
    if (url.startsWith("./")) url = url.slice(1);
    if (!url.startsWith("/")) url = "/" + url;
    try {
      return new URL(url, window.location.origin).href;
    } catch {
      return url;
    }
  }

  function load(episode) {
    if (!episode || !episode.audio_url) return;

    // Durante prerender (Speculation Rules) adia o fetch de áudio: requisições
    // de mídia em conteúdo prerenderizado são deferidas e abortadas quando a
    // cópia é descartada (net::ERR_CONNECTION_FAILED no /audio/<hoje>.mp3).
    // Só carrega de fato quando a página é ativada (ver prerenderingchange).
    if (document.prerendering) {
      _pendingEpisode = episode;
      return;
    }

    const sameEpisode = currentEpisode && currentEpisode.id === episode.id;
    currentEpisode = episode;

    const src = resolveAudioUrl(episode.audio_url);
    if (!sameEpisode || audio.src !== src) {
      audio.src = src;
      audio.load();
    }
  }

  function play(episode) {
    if (episode) {
      load(episode);
    }
    
    if (!audio || !audio.src) return;

    const p = audio.play();
    if (p && typeof p.then === "function") {
      p.catch(err => {
        console.warn("audio.play notice:", err.message || err);
      });
    }

    // Configura metadados do MediaSession no celular/sistema
    if (navigator.mediaSession && currentEpisode) {
      try {
        navigator.mediaSession.metadata = new MediaMetadata({
          title: currentEpisode.title || `Edição ${currentEpisode.date}`,
          artist: currentEpisode.type === "especial" ? "Peter (Solo)" : "Peter & Ricardo",
          album: currentEpisode.type === "especial" ? "Brasil & Mundo" : "Web Jornal",
          artwork: [
            { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
            { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" }
          ]
        });

        // Configura ações de controle no MediaSession
        navigator.mediaSession.setActionHandler("play", () => play());
        navigator.mediaSession.setActionHandler("pause", () => pause());
        navigator.mediaSession.setActionHandler("seekbackward", (details) => skip(details.seekOffset || -15));
        navigator.mediaSession.setActionHandler("seekforward", (details) => skip(details.seekOffset || 15));
      } catch (err) {
        console.warn("MediaSession initialization failed:", err);
      }
    }
  }

  function pause() {
    if (audio) audio.pause();
  }

  function togglePlay(episode) {
    if (!audio || !audio.src) {
      if (episode) {
        play(episode);
      }
      return;
    }

    if (episode && currentEpisode && currentEpisode.id !== episode.id) {
      play(episode);
      return;
    }

    if (audio.paused) {
      play();
    } else {
      pause();
    }
  }

  function seek(percentage) {
    if (!audio) return;
    const dur = audio.duration;
    if (Number.isFinite(dur) && dur > 0) {
      const pct = Math.max(0, Math.min(100, Number(percentage) || 0));
      audio.currentTime = (pct / 100) * dur;
    }
  }

  function skip(seconds) {
    if (!audio) return;
    const dur = audio.duration;
    const cur = audio.currentTime || 0;
    const delta = Number(seconds) || 0;
    if (Number.isFinite(dur) && dur > 0) {
      audio.currentTime = Math.max(0, Math.min(dur, cur + delta));
    } else {
      audio.currentTime = Math.max(0, cur + delta);
    }
  }

  function setPlaybackRate(rate) {
    if (audio) {
      audio.playbackRate = parseFloat(rate);
    }
  }

  function getPlaybackRate() {
    return audio ? audio.playbackRate : 1.0;
  }

  function getCurrentEpisode() {
    return currentEpisode;
  }

  function getAudioState() {
    return {
      currentTime: audio ? audio.currentTime : 0,
      duration: audio ? audio.duration : 0,
      paused: audio ? audio.paused : true,
      playbackRate: audio ? audio.playbackRate : 1.0,
      episode: currentEpisode
    };
  }

  // Inicializa quando o script carrega
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initPlayer);
  } else {
    initPlayer();
  }

  // Ao ativar uma página que estava em prerender, carrega o áudio pendente
  if (document.prerendering) {
    document.addEventListener("prerenderingchange", () => {
      const ep = _pendingEpisode;
      _pendingEpisode = null;
      if (ep) load(ep);
    });
  }

  window.PlayerManager = {
    load,
    play,
    pause,
    togglePlay,
    seek,
    skip,
    setPlaybackRate,
    getPlaybackRate,
    getCurrentEpisode,
    getAudioState
  };
})();
