#!/usr/bin/env node
/**
 * UX-016 — cadeia de autoplay em background.
 * RED até o player encadear no mesmo #audioEl, sem await e sem new Audio().
 */
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const require = createRequire(import.meta.url);
const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const chain = require(join(root, "public/assets/js/autoplay_chain.js"));

let failed = 0;
function assert(cond, msg) {
  if (!cond) {
    failed += 1;
    console.error("FAIL:", msg);
  } else {
    console.log("OK  :", msg);
  }
}

const next = { id: "2026-08-14", title: "Amanhã", date: "2026-08-14" };
const adAudio = { audio_url: "https://cdn.example/ad.mp3", creative_id: "c1", campaign_id: "p1" };
const adVisual = { media_url: "https://cdn.example/ad.jpg", creative_id: "c2", campaign_id: "p2" };

assert(chain.decideAutoPlayTransition({ isShowingAd: true, nextEp: next }).action === "noop", "ad já na tela → noop");
assert(chain.decideAutoPlayTransition({ isAdMode: true, nextEp: next }).action === "noop", "já tocando ad no player → noop");
assert(chain.decideAutoPlayTransition({ nextEp: null }).action === "stop", "fim da fila → stop");
assert(
  chain.decideAutoPlayTransition({ nextEp: next, cachedAd: adAudio, hidden: true }).action === "play-ad-on-player",
  "ad com áudio em background → mesmo elemento",
);
assert(
  chain.decideAutoPlayTransition({ nextEp: next, cachedAd: adVisual, hidden: true }).action === "play-next",
  "ad só visual em background → pula e segue o próximo",
);
assert(
  chain.decideAutoPlayTransition({ nextEp: next, cachedAd: adVisual, hidden: false }).action === "show-visual-interstitial",
  "ad só visual em foreground → overlay",
);
assert(
  chain.decideAutoPlayTransition({ nextEp: next, cachedAd: null, hidden: true }).action === "play-next",
  "sem ad em cache + hidden → próximo na hora (sem await)",
);
assert(chain.isEndedLike({ currentTime: 599.8, duration: 600 }) === true, "quase no fim = ended-like");
assert(chain.isEndedLike({ currentTime: 12, duration: 600 }) === false, "no meio não é ended-like");

const app = readFileSync(join(root, "public/assets/js/app.js"), "utf8");
const player = readFileSync(join(root, "public/assets/js/player.js"), "utf8");
const ads = readFileSync(join(root, "public/assets/js/ad_manager.js"), "utf8");
const html = readFileSync(join(root, "public/index.html"), "utf8");

assert(!/async function handleAutoPlayNext/.test(app), "handleAutoPlayNext não é async (await quebra o gesto)");
const handleSlice = (app.split("function handleAutoPlayNext")[1] || "").slice(0, 900);
assert(!/await\s+window\.__supabaseFetchActiveAd/.test(handleSlice), "ended não espera fetch do anúncio");
assert(/AutoplayChain\.decideAutoPlayTransition/.test(app), "app.js usa AutoplayChain");
assert(/__cachedActiveAd/.test(app), "app.js tem cache síncrono do anúncio");
assert(/function playUrl/.test(player) || /playUrl:playUrl/.test(player), "PlayerManager.playUrl existe");
assert(/isAdMode/.test(player), "PlayerManager.isAdMode existe");
assert(/isPlayBlocked/.test(player), "PlayerManager.isPlayBlocked existe");
assert(/PlayerManager\.playUrl/.test(ads), "ad_manager toca no mesmo #audioEl via playUrl");
assert(!/masterAudio=new Audio\(adData\.audio_url\)/.test(ads) || /playUrl/.test(ads), "ad com áudio não depende só de new Audio()");
assert(/autoplay_chain\.js/.test(html), "index.html carrega autoplay_chain.js");

if (failed) {
  console.error(`\n${failed} falha(s)`);
  process.exit(1);
}
console.log("\nqa_background_autoplay: OK");
