#!/usr/bin/env node
/**
 * QA — sticky topbar + abas (Diário/Brasil e Mundo) com vidro (glassmorphism).
 * Gate (skill web-jornal-frontend): ao rolar, topbarTop deve ficar ~0 e
 * tabsTop deve plateau em ~56px. Se desce linear com scrollY, sticky morreu.
 * Também inspeciona a cadeia de ancestrais (overflow/transform/filter) que
 * mata position:sticky.
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
  `--remote-debugging-port=${PORT}`, "about:blank",
], { stdio: "ignore" });
await new Promise((r) => setTimeout(r, 1600));

const targets = await (await fetch(`http://127.0.0.1:${PORT}/json`)).json();
const ws = new WebSocket(targets.find((t) => t.type === "page").webSocketDebuggerUrl);
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
await send("Emulation.setDeviceMetricsOverride", { width: 1280, height: 900, deviceScaleFactor: 1 });
await send("Page.navigate", { url: BASE });
await new Promise((r) => setTimeout(r, 5000));

const report = await ev(`(() => {
  const out = { scrolls: [] };
  const topbar = document.querySelector(".topbar");
  const tabs = document.querySelector(".category-tabs-wrapper");
  if (!topbar || !tabs) return { error: "topbar/tabs nao encontrados", topbar: !!topbar, tabs: !!tabs };

  const cs = (el) => getComputedStyle(el);
  out.topbarCSS = { position: cs(topbar).position, top: cs(topbar).top, backdrop: cs(topbar).backdropFilter, bg: cs(topbar).backgroundColor };
  out.tabsCSS = { position: cs(tabs).position, top: cs(tabs).top, bg: cs(tabs).backgroundColor, backdrop: cs(tabs).backdropFilter };

  for (const y of [0, 400, 800, 1200, 1600]) {
    window.scrollTo(0, y);
    out.scrolls.push({
      y,
      topbarTop: Math.round(topbar.getBoundingClientRect().top),
      tabsTop: Math.round(tabs.getBoundingClientRect().top),
    });
  }
  window.scrollTo(0, 0);
  return out;
})()`);

console.log("=== DESKTOP 1280 ===");
console.log(JSON.stringify(report, null, 1));
if (report.error) {
  assert(false, report.error);
} else {
  const s = report.scrolls;
  const plateau = s.filter((x) => x.y >= 800);
  assert(plateau.every((x) => x.topbarTop === 0), "topbar fixa no topo (topbarTop = 0 ao rolar)");
  assert(plateau.every((x) => Math.abs(x.tabsTop - 56) <= 2),
    `abas fixas em ~56px (${plateau.map((x) => x.tabsTop).join(",")})`);
  assert(report.topbarCSS.backdrop.includes("blur"), "topbar com blur (vidro)");
}

// === MOBILE ===
await send("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
await send("Page.navigate", { url: BASE });
await new Promise((r) => setTimeout(r, 5000));
const m = await ev(`(() => {
  const topbar = document.querySelector(".topbar");
  const tabs = document.querySelector(".category-tabs-wrapper");
  if (!topbar || !tabs) return { error: "topbar/tabs nao encontrados" };
  const out = { scrolls: [] };
  for (const y of [0, 300, 600, 1000]) {
    window.scrollTo(0, y);
    out.scrolls.push({ y, topbarTop: Math.round(topbar.getBoundingClientRect().top), tabsTop: Math.round(tabs.getBoundingClientRect().top) });
  }
  window.scrollTo(0, 0);
  return out;
})()`);
console.log("=== MOBILE 390 ===");
console.log(JSON.stringify(m, null, 1));
if (!m.error) {
  const mp = m.scrolls.filter((x) => x.y >= 600);
  assert(mp.every((x) => x.topbarTop === 0), "mobile: topbar fixa (0 ao rolar)");
  assert(mp.every((x) => Math.abs(x.tabsTop - 56) <= 2), `mobile: abas fixas ~56px (${mp.map((x) => x.tabsTop).join(",")})`);
}

assert(exceptions.length === 0, `0 excecoes (${exceptions.length})`);

ws.close();
chrome.kill();
if (failed) { console.error(`\n${failed} falha(s)`); process.exit(1); }
console.log("\nqa_sticky_topbar: OK");
