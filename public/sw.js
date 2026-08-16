/* Service Worker — Vale da Liberdade PWA */
const CACHE = "vld-v1-202608160848";
// Shell estático. IMPORTANTE (2026-08-16): NÃO precachear "./assets/css/*.css"
// nem "./assets/js/*.js" SEM o ?v= de versão. O Cloudflare guarda a URL sem
// versão com TTL de 1 ano (max-age=31536000) e pode servir conteúdo antigo
// (cf-cache-status: HIT). Se o SW precacheia a URL sem versão, ele envenena o
// cache local com CSS/JS velho e o usuário fica preso no design antigo mesmo
// com hard refresh. Os assets versionados entram no cache em runtime (fetch
// network-first abaixo), usando as mesmas URLs ?v= que o index.html referencia.
const PRECACHE = [
  "./",
  "./index.html",
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
    caches.open(CACHE).then((cache) =>
      // add individual para um asset ausente não derrubar o install inteiro
      Promise.all(PRECACHE.map((u) => cache.add(u).catch(() => {})))
    )
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

  // NAVEGAÇÃO: network-first (2026-08-16). Antes era cache-first, então o hard
  // refresh (Shift+F5) servia o index.html velho do precache — o usuário não
  // conseguia forçar a atualização. Agora a navegação busca o HTML novo na rede
  // e só cai para o cache / offline.html quando está offline.
  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req)
        .then((res) => {
          if (res.ok && url.origin === self.location.origin) {
            const copy = res.clone();
            caches.open(CACHE).then((c) => c.put(req, copy));
          }
          return res;
        })
        .catch(() =>
          caches.match(req).then((c) => c || caches.match("./offline.html"))
        )
    );
    return;
  }

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

  // Demais (imagens, ícones, manifest): cache-first com fallback de rede.
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
        .catch(() => new Response("", { status: 503 }))
    })
  );
});
