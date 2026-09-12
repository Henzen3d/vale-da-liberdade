#!/usr/bin/env node
/**
 * QA — Desktop Player (barra ≥1024px + painel Now Playing) + Consentimento v2.
 *
 * Desktop (1280px): barra visível com episódio, mini player oculto, full player
 *   mobile oculto, painel abre via expand/capa, volume persiste, prev/next ok.
 * Mobile  (390px) : mini player visível, barra desktop oculta (display:none),
 *   full player mobile continua abrindo (expanded).
 * Consent: sem vale-consent → banner visível; Aceitar → hidden + accepted + gtag;
 *   Rejeitar → rejected + gtag denied; AdSense não carrega antes da decisão.
 */
import { spawn } from "node:child_process";

const CHROME = "/home/osmar/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome";
const PORT = 9341;
const BASE = "http://127.0.0.1:8090/";

let failed = 0;
const assert = (cond, msg) => {
  if (cond) console.log("OK  :", msg);
  else { failed += 1; console.error("FAIL:", msg); }
};

const chrome = spawn(CHROME, [
  "--headless=new", "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
  "--autoplay-policy=no-user-gesture-required",
  `--remote-debugging-port=${PORT}`, "about:blank",
], { stdio: "ignore" });

// Garante que o Chrome headless NUNCA fique órfão queimando CPU:
// mata o processo em qualquer saída do script (normal, erro ou sinal).
const killChrome = () => { try { chrome.kill("SIGKILL"); } catch (_) {} };
process.on("exit", killChrome);
process.on("SIGINT", () => { killChrome(); process.exit(130); });
process.on("SIGTERM", () => { killChrome(); process.exit(143); });
process.on("uncaughtException", (err) => {
  console.error("uncaughtException:", err);
  killChrome();
  process.exit(1);
});

await new Promise((r) => setTimeout(r, 1600));

const targets = await (await fetch(`http://127.0.0.1:${PORT}/json`)).json();
const wsUrl = targets.find((t) => t.type === "page").webSocketDebuggerUrl;
const ws = new WebSocket(wsUrl);

let msgId = 0;
const pending = new Map();
const exceptions = [];
ws.onmessage = (ev) => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
  if (m.method === "Runtime.exceptionThrown") exceptions.push(m.params.exceptionDetails.text);
};
await new Promise((r) => { ws.onopen = r; });

const send = (method, params = {}) => new Promise((res) => {
  const id = ++msgId;
  pending.set(id, res);
  ws.send(JSON.stringify({ id, method, params }));
});
const ev = async (expression) =>
  (await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true }))
    .result?.result?.value;

await send("Runtime.enable");
await send("Page.enable");

const goto = async (url, w, h) => {
  await send("Emulation.setDeviceMetricsOverride", { width: w, height: h, deviceScaleFactor: 1, mobile: false });
  await send("Page.navigate", { url });
  await new Promise((r) => setTimeout(r, 3500)); // feed + scripts defer
};

const setViewport = async (w, h) => {
  await send("Emulation.setDeviceMetricsOverride", { width: w, height: h, deviceScaleFactor: 1, mobile: false });
  await new Promise((r) => setTimeout(r, 400));
};

const click = async (sel) => {
  await ev(`(() => { const el = document.querySelector(${JSON.stringify(sel)}); if (!el) return false; el.click(); return true; })()`);
};

// ============ 1. DESKTOP (1280px) ============
console.log("\n=== DESKTOP 1280px ===");
await goto(BASE, 1280, 900);

// limpar consent para testes
await ev(`try { localStorage.removeItem("vale_consent"); localStorage.removeItem("vld_consent_v1"); } catch(e){}`);

// esperar feed + auto-load do episódio de hoje
await new Promise((r) => setTimeout(r, 2500));
await ev(`(async () => { for (let i=0;i<40;i++){ if (window.PlayerManager && window.PlayerManager.getCurrentEpisode()) break; await new Promise(r=>setTimeout(r,250)); } return true; })()`);

const barVisible = await ev(`(() => {
  const bar = document.getElementById("desktopPlayerBar");
  if (!bar) return "sem barra";
  const cs = getComputedStyle(bar);
  return { hidden: bar.hidden, display: cs.display, height: cs.height };
})()`);
assert(barVisible && barVisible.display !== "none" && !barVisible.hidden,
  `barra desktop visível com episódio (display=${barVisible?.display}, hidden=${barVisible?.hidden})`);

const miniDesktop = await ev(`(() => {
  const m = document.getElementById("miniPlayer");
  return m ? getComputedStyle(m).display : "sem mini";
})()`);
assert(miniDesktop === "none", `mini player oculto no desktop (display=${miniDesktop})`);

const fullDesktop = await ev(`(() => {
  const f = document.getElementById("fullPlayerOverlay");
  return f ? getComputedStyle(f).display : "sem full";
})()`);
assert(fullDesktop === "none", `full player mobile oculto no desktop (display=${fullDesktop})`);

// Título na barra = episódio atual
const barTitle = await ev(`document.getElementById("dpTitle") ? document.getElementById("dpTitle").textContent : ""`);
assert(barTitle.length > 3, `título da barra populado: "${barTitle.slice(0, 40)}"`);

// Play/pause
const st0 = await ev(`(() => { const s = window.PlayerManager.getAudioState(); return { paused: s.paused, id: s.episode && s.episode.id }; })()`);
await click("#dpPlayPause");
await new Promise((r) => setTimeout(r, 600));
const st1 = await ev(`window.PlayerManager.getAudioState().paused`);
assert(st1 !== st0.paused, `play/pause alterna estado (antes paused=${st0.paused}, depois=${st1})`);

// Volume persiste
await ev(`window.PlayerManager.setVolume(0.35)`);
const volStored = await ev(`localStorage.getItem("vld_volume")`);
assert(volStored === "0.35", `volume persiste em localStorage (${volStored})`);
const volSlider = await ev(`document.getElementById("dpVolume") ? document.getElementById("dpVolume").value : ""`);
assert(volSlider === "35", `slider reflete volume (${volSlider})`);
// reload: volume restaurado
await send("Page.reload", { ignoreCache: true });
await new Promise((r) => setTimeout(r, 3500));
const volAfterReload = await ev(`window.PlayerManager.getVolume()`);
assert(Math.abs(volAfterReload - 0.35) < 0.01, `volume restaurado após reload (${volAfterReload})`);

// Painel abre via expandir
await click("#dpExpand");
await new Promise((r) => setTimeout(r, 500));
const panelOpen = await ev(`document.getElementById("nowPlayingPanel") ? document.getElementById("nowPlayingPanel").classList.contains("open") : false`);
assert(panelOpen, "painel Now Playing abre via expandir");

const panelTitle = await ev(`document.getElementById("npTitle") ? document.getElementById("npTitle").textContent : ""`);
assert(panelTitle.length > 3, `painel tem título: "${panelTitle.slice(0, 40)}"`);

const npOthers = await ev(`document.querySelectorAll("#npOtherList .np-other-item").length`);
assert(npOthers > 0, `painel lista outros episódios (${npOthers})`);

const npHosts = await ev(`!!document.querySelector(".np-hosts")`);
assert(npHosts, "cartão Peter & Ricardo presente no painel");

// Fecha via X
await click("#npClose");
await new Promise((r) => setTimeout(r, 500));
const panelClosed = await ev(`!document.getElementById("nowPlayingPanel").classList.contains("open")`);
assert(panelClosed, "painel fecha via X");

// "Mostrar notas" abre painel
await click("#dpNotes");
await new Promise((r) => setTimeout(r, 500));
const panelOpen2 = await ev(`document.getElementById("nowPlayingPanel").classList.contains("open")`);
assert(panelOpen2, "ícone mostrar notas abre o painel");

// Prev/next
const curId = await ev(`window.PlayerManager.getCurrentEpisode().id`);
await click("#dpPrev");
await new Promise((r) => setTimeout(r, 800));
const prevId = await ev(`window.PlayerManager.getCurrentEpisode().id`);
assert(prevId !== curId, `anterior navega (${String(curId).slice(0,18)} → ${String(prevId).slice(0,18)})`);
await click("#dpNext");
await new Promise((r) => setTimeout(r, 1200));
const nextId = await ev(`window.PlayerManager.getCurrentEpisode().id`);
assert(nextId === curId, `próximo volta ao original (${String(nextId).slice(0,18)})`);

// ============ 2. MOBILE (390px) ============
console.log("\n=== MOBILE 390px ===");
await setViewport(390, 844);
await new Promise((r) => setTimeout(r, 800));

const miniMobile = await ev(`(() => {
  const m = document.getElementById("miniPlayer");
  return m ? getComputedStyle(m).display : "sem mini";
})()`);
assert(miniMobile !== "none", `mini player visível no mobile (display=${miniMobile})`);

const barMobile = await ev(`(() => {
  const b = document.getElementById("desktopPlayerBar");
  return b ? getComputedStyle(b).display : "sem barra";
})()`);
assert(barMobile === "none", `barra desktop oculta no mobile (display=${barMobile})`);

// Full player mobile continua abrindo
await click("#miniExpand");
await new Promise((r) => setTimeout(r, 600));
const fullExpanded = await ev(`document.getElementById("fullPlayerOverlay").classList.contains("expanded")`);
assert(fullExpanded, "full player mobile abre via expandir no mobile");

// ============ 3. CONSENTIMENTO ============
console.log("\n=== CONSENTIMENTO ===");
await goto(BASE, 1280, 900);
await ev(`try { localStorage.removeItem("vale_consent"); localStorage.removeItem("vld_consent_v1"); } catch(e){}`);
await new Promise((r) => setTimeout(r, 3000));

const bannerVisible = await ev(`(() => {
  const b = document.getElementById("consentBanner");
  return b ? !b.hidden : "sem banner";
})()`);
assert(bannerVisible === true, "banner visível na 1ª visita (sem consentimento)");

// AdSense não carrega antes da decisão
const adsenseBefore = await ev(`!!document.querySelector('script[src*="adsbygoogle.js"]')`);
const allowsBefore = await ev(`window.__consentAllowsAdsense ? window.__consentAllowsAdsense() : "sem fn"`);
assert(!adsenseBefore && allowsBefore === false, `AdSense não carrega antes da decisão (script=${adsenseBefore}, allows=${allowsBefore})`);

// Aceitar tudo
await click("#consentAcceptAll");
await new Promise((r) => setTimeout(r, 500));
const afterAccept = await ev(`(() => {
  const b = document.getElementById("consentBanner");
  const stored = localStorage.getItem("vale_consent");
  const dl = (window.dataLayer || []).filter(x => Array.isArray(x) && x[0] === "consent");
  return { hidden: b.hidden, stored, consentCalls: dl.length, last: dl.length ? dl[dl.length-1] : null };
})()`);
assert(afterAccept.hidden === true, "banner some após Aceitar");
assert(afterAccept.stored === "accepted", `vale-consent=accepted (${afterAccept.stored})`);
assert(afterAccept.consentCalls > 0, `gtag consent registrado (${afterAccept.consentCalls} chamadas)`);
const acceptedState = afterAccept.last && afterAccept.last[2] && afterAccept.last[2].ad_storage;
assert(acceptedState === "granted", `ad_storage=granted após aceitar (${acceptedState})`);
const allowsAfterAccept = await ev(`window.__consentAllowsAdsense()`);
assert(allowsAfterAccept === true, "AdSense permitido após aceitar (free)");

// Reload: banner não volta
await send("Page.reload", { ignoreCache: true });
await new Promise((r) => setTimeout(r, 3000));
const bannerAfterReload = await ev(`document.getElementById("consentBanner").hidden`);
assert(bannerAfterReload === true, "banner não reaparece após reload com consentimento salvo");

// Rejeitar (novo contexto)
await ev(`try { localStorage.removeItem("vale_consent"); localStorage.removeItem("vld_consent_v1"); } catch(e){}`);
await send("Page.reload", { ignoreCache: true });
await new Promise((r) => setTimeout(r, 3000));
await click("#consentRejectAll");
await new Promise((r) => setTimeout(r, 500));
const afterReject = await ev(`(() => {
  const stored = localStorage.getItem("vale_consent");
  const dl = (window.dataLayer || []).filter(x => Array.isArray(x) && x[0] === "consent");
  const last = dl.length ? dl[dl.length-1] : null;
  return { stored, ad: last && last[2] && last[2].ad_storage, allows: window.__consentAllowsAdsense() };
})()`);
assert(afterReject.stored === "rejected", `vale-consent=rejected (${afterReject.stored})`);
assert(afterReject.ad === "denied", `ad_storage=denied após rejeitar (${afterReject.ad})`);
assert(afterReject.allows === false, "AdSense bloqueado após rejeitar");

// Migração: vld_consent_v1 antigo → accepted
await ev(`try { localStorage.removeItem("vale_consent"); localStorage.setItem("vld_consent_v1", JSON.stringify({ essential_accepted_at: new Date().toISOString(), plan_at_consent: "free" })); } catch(e){}`);
await send("Page.reload", { ignoreCache: true });
await new Promise((r) => setTimeout(r, 3000));
const migrated = await ev(`(() => {
  const b = document.getElementById("consentBanner");
  const allows = window.__consentAllowsAdsense ? window.__consentAllowsAdsense() : null;
  return { hidden: b.hidden, allows };
})()`);
assert(migrated.hidden === true && migrated.allows === true,
  `migração vld_consent_v1 → accepted (banner hidden=${migrated.hidden}, allows=${migrated.allows})`);

// ============ RESUMO ============
console.log("\nExceções de console:", exceptions.length);
if (exceptions.length) console.log(exceptions.slice(0, 5).join("\n"));
console.log(failed === 0 ? "\n✅ QA DESKTOP PLAYER + CONSENT: TUDO PASSOU" : `\n❌ ${failed} asserções falharam`);
process.exit(failed === 0 ? 0 : 1);
