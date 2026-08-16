#!/usr/bin/env bash
# QA — cadeia de entrega do Vale da Liberdade (regressão 2026-08-16)
#
# Verifica que:
#  1. sw.js sai com Cache-Control no-cache na origem (:8090) — regra
#     `location = /sw.js` do deploy/nginx.conf. Sem ela, o Cloudflare cacheia
#     o sw.js com TTL de 1 ano e o PWA NUNCA recebe updates (usuário fica com
#     shell antigo mesmo após publish).
#  2. Cloudflare responde BYPASS para sw.js (não HIT com idade longa).
#  3. Prod responde 200 e o CSS versionado contém as correções de UX:
#     hero desktop horizontal (row 45/55) e vidro na barra de abas.
#
# Uso: bash scripts/qa_delivery_chain.sh   (saída em stdout; exit 1 se falhar)
# Rodar após publish_site.py ou após mexer em deploy/nginx.conf.
set -u
BASE_LOCAL="http://127.0.0.1:8090"
BASE_PROD="https://news.mob.tec.br"
FAIL=0

ok()   { echo "OK  : $1"; }
bad()  { echo "FAIL: $1"; FAIL=1; }

# 1) sw.js na origem: no-cache obrigatório
local_cc=$(curl -sI "$BASE_LOCAL/sw.js" | tr -d '\r' | grep -i '^cache-control:' | head -1)
if echo "$local_cc" | grep -qi 'no-cache'; then ok "sw.js local no-cache ($local_cc)"; else bad "sw.js local NAO esta no-cache: $local_cc"; fi

# 2) sw.js na prod: CF deve estar BYPASS (nunca HIT com TTL longo)
prod_cf=$(curl -sI "$BASE_PROD/sw.js" | tr -d '\r' | grep -i 'cf-cache-status' | head -1)
if echo "$prod_cf" | grep -qi 'BYPASS'; then ok "sw.js prod cf-cache-status BYPASS"; else bad "sw.js prod cf-cache-status = $prod_cf (esperado BYPASS)"; fi

# 3) Prod responde 200
code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE_PROD/")
if [ "$code" = "200" ]; then ok "prod index HTTP 200"; else bad "prod index HTTP $code"; fi

# 4) CSS versionado da prod contém as correções de UX
vb=$(curl -s "$BASE_PROD/" | grep -o 'components.css?v=[0-9]*' | head -1)
css=$(curl -s "$BASE_PROD/assets/css/$vb")
if echo "$css" | grep -q 'hero-card{flex-direction:row;max-height:240px}'; then
  ok "hero desktop horizontal presente na prod"
else
  bad "hero desktop horizontal AUSENTE na prod (regressao do 611eee3 voltou?)"
fi
if echo "$css" | grep -q 'category-tabs-wrapper{position:sticky;top:var(--topbar-sticky-offset,56px);z-index:90;background-color:rgba(248,249,250,0.85)'; then
  ok "vidro na barra de abas presente na prod"
else
  bad "vidro na barra de abas AUSENTE na prod"
fi

# 5) base.css versionado da prod usa overflow-x:clip (nao hidden — mata sticky)
bb=$(curl -s "$BASE_PROD/" | grep -o 'base.css?v=[0-9]*' | head -1)
bcss=$(curl -s "$BASE_PROD/assets/css/$bb")
if echo "$bcss" | grep -q 'overflow-x:clip'; then
  ok "base.css com overflow-x:clip (sticky preservado)"
else
  bad "base.css SEM overflow-x:clip — sticky da topbar/abas morre na prod (cache-buster desatualizado?)"
fi

if [ "$FAIL" -ne 0 ]; then echo; echo "qa_delivery_chain: $FAIL falha(s) — ver deploy/nginx.conf (regra sw.js) e docker compose up -d --force-recreate web"; exit 1; fi
echo
echo "qa_delivery_chain: OK — cadeia de entrega saudavel"
