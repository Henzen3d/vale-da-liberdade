#!/usr/bin/env node
/**
 * QA — restauração do hero desktop (card horizontal: capa 45% esq., info 55% dir.)
 * Desktop (1280px): flex-direction row, max-height 240px, split 45/55.
 * Mobile  (390px) : regressão — continua vertical (flex-direction column).
 */
import { spawn } from "node:child_process";
import { readFileSync } from "node:fs";

const CHROME = "/home/osmar/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome";
const PORT = 9339;
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

async function measure(viewport) {
  await send("Emulation.setDeviceMetricsOverride", {
    width: viewport.width, height: viewport.height,
    deviceScaleFactor: 1, mobile: viewport.mobile ?? false,
  });
  await send("Page.navigate", { url: BASE });
  await new Promise((r) => setTimeout(r, 5000)); // feed + hero render
  return ev(`(() => {
    const card = document.querySelector(".hero-card");
    if (!card) return { error: "hero-card nao encontrado" };
    const cs = (el) => getComputedStyle(el);
    const cover = card.querySelector(".hero-cover-wrap");
    const content = card.querySelector(".hero-content");
    const cardW = card.getBoundingClientRect().width;
    const coverW = cover.getBoundingClientRect().width;
    const contentW = content.getBoundingClientRect().width;
    return {
      flexDirection: cs(card).flexDirection,
      maxHeight: cs(card).maxHeight,
      cardW: Math.round(cardW),
      coverW: Math.round(coverW),
      contentW: Math.round(contentW),
      coverPct: Math.round((coverW / cardW) * 100),
      contentPct: Math.round((contentW / cardW) * 100),
      coverAR: cs(cover).aspectRatio,
      titleSize: cs(card.querySelector(".hero-title")).fontSize,
    };
  })()`);
}

console.log("=== DESKTOP 1280 ===");
const d = await measure({ width: 1280, height: 900 });
console.log(JSON.stringify(d));
assert(!d.error, "hero renderizado no desktop");
if (!d.error) {
  assert(d.flexDirection === "row", `desktop: flex-direction row (${d.flexDirection})`);
  assert(d.maxHeight === "240px", `desktop: max-height 240px (${d.maxHeight})`);
  assert(d.coverPct >= 40 && d.coverPct <= 50, `desktop: capa ~45% (${d.coverPct}%)`);
  assert(d.contentPct >= 50 && d.contentPct <= 62, `desktop: conteudo ~55% (${d.contentPct}%)`);
}

console.log("=== MOBILE 390 ===");
const m = await measure({ width: 390, height: 844, mobile: true });
console.log(JSON.stringify(m));
assert(!m.error, "hero renderizado no mobile");
if (!m.error) {
  assert(m.flexDirection === "column", `mobile: continua vertical (${m.flexDirection})`);
  assert(m.coverPct >= 95, `mobile: capa largura total (${m.coverPct}%)`);
}

console.log("=== CONSOLE ===");
assert(exceptions.length === 0, `0 excecoes no console (${exceptions.length})`);

ws.close();
chrome.kill();
if (failed) { console.error(`\n${failed} falha(s)`); process.exit(1); }
console.log("\nqa_hero_desktop_restore: OK");
