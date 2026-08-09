/* Service Worker — Vale da Liberdade PWA */
const CACHE = "vld-v1-202608090907";
const PRECACHE = [
  "./",
  "./index.html",
  "./assets/css/tokens.css",
  "./assets/css/base.css",
  "./assets/css/components.css",
  "./assets/js/theme.js",
  "./assets/js/player.js",
  "./assets/js/listen_progress.js",
  "./assets/js/ad_manager.js",
  "./assets/js/app.js",
  "./js/supabase_client.js",
  "./manifest.webmanifest",
  "./offline.html",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
  "./icons/apple-touch-icon.png",
  "./icons/favicon-32.png",
  "./data/episodes.json",
  // LCP image pre-cache (item C) — evita competir com fetch da primeira visita
  "./assets/cover-400.webp",
  "./assets/cover-800.webp",
  "./assets/cover-1200.webp",
  "./assets/cover-800.jpg",
];

self.addEventListener("install", (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(PRECACHE))
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);

  // Network-first para catálogo e scripts/estilos (para atualizar alterações instantaneamente)
  if (
    url.pathname.endsWith("/data/episodes.json") ||
    url.pathname.endsWith("episodes.json") ||
    url.pathname.endsWith(".js") ||
    url.pathname.endsWith(".css")
  ) {
    const isCatalog =
      url.pathname.endsWith("/data/episodes.json") ||
      url.pathname.endsWith("episodes.json");
    // Cache key estável p/ catálogo (ignora ?t= se algum client ainda mandar)
    const cacheReq = isCatalog
      ? new Request(url.origin + url.pathname, { credentials: req.credentials })
      : req;
    event.respondWith(
      fetch(req)
        .then((res) => {
          if (res.ok && url.origin === self.location.origin) {
            const copy = res.clone();
            caches.open(CACHE).then((c) => c.put(cacheReq, copy));
          }
          return res;
        })
        .catch(() => caches.match(cacheReq).then((c) => c || caches.match(req)))
    );
    return;
  }

  // Áudio: network-first (deixa navegador lidar com Range Requests).
  // Offline → cache dedicado "vld-audio-v1" (baixado pelo app.js após ouvir ≥30s).
  if (url.pathname.includes("/audio/") || url.pathname.endsWith(".mp3")) {
    event.respondWith(
      fetch(req).catch(() =>
        caches
          .match(url.pathname, { cacheName: "vld-audio-v1" })
          .then((c) => c || caches.match(req))
      )
    );
    return;
  }

  event.respondWith(
    caches.match(req).then((cached) => {
      if (cached) return cached;
      return fetch(req)
        .then((res) => {
          if (res.ok && url.origin === self.location.origin) {
            const copy = res.clone();
            caches.open(CACHE).then((c) => c.put(req, copy));
          }
          return res;
        })
        .catch(() => (req.mode === "navigate" ? caches.match("./offline.html") : new Response("", { status: 503 })));
    })
  );
});
