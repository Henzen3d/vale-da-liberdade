#!/bin/bash
# ============================================================================
# dev-sync.sh — Sync rápido do shell estático: new-ux/public → public
# ============================================================================
#
# USO:
#   scripts/dev-sync.sh                 # sync do shell estático (default)
#   scripts/dev-sync.sh --no-cache-bust # idem, sem reescrever CACHE do sw.js
#   scripts/dev-sync.sh -c | --full     # inclui data/, feed* e sw.js
#   scripts/dev-sync.sh -h | --help     # esta ajuda
#
# O QUE COPIA (default — mesmo conjunto de sync_ux_assets() em
# scripts/publish_site.py):
#   index.html, assets/css, assets/js, assets/cover.jpg, assets/cover.png,
#   manifest.webmanifest, offline.html, llms.txt, icons/, ads.txt,
#   js/supabase_client.js
#
# O QUE NUNCA É SOBRESCRITO SEM -c/--full:
#   public/data/ (catálogo), public/feed.xml|feed.json|feed-brasil-e-mundo.xml
#   e public/sw.js — esses são gerados/atualizados por scripts/publish_site.py
#   (agendado às 06:00 UTC via scripts/cron-wrapper.sh).
#
# EXEMPLOS:
#   scripts/dev-sync.sh                 # testar uma edição de frontend rápido
#   scripts/dev-sync.sh --no-cache-bust # sem bump da versão de cache do sw
#   scripts/dev-sync.sh --full          # sync total (shell + data + feeds + sw)
#
# AVISO: este script NÃO regenera episódios nem feeds — para produção, use
# scripts/publish_site.py.
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SRC="$PROJECT_DIR/new-ux/public"
DST="$PROJECT_DIR/public"

FULL=0
CACHE_BUST=1

for arg in "$@"; do
    case "$arg" in
        -c|--full) FULL=1 ;;
        --no-cache-bust) CACHE_BUST=0 ;;
        -h|--help)
            echo "Uso: $0 [--full|-c] [--no-cache-bust]"
            echo "  (default)        sync do shell estático (sem data/, feed*, sw.js)"
            echo "  -c, --full       inclui data/, feed* e sw.js (com cache-bust)"
            echo "  --no-cache-bust  não reescreve a constante CACHE do sw.js"
            exit 0
            ;;
        *)
            echo "❌ Argumento desconhecido: $arg" >&2
            echo "   Uso: $0 [--full|-c] [--no-cache-bust]" >&2
            exit 1
            ;;
    esac
done

if [ ! -d "$SRC" ]; then
    echo "❌ $SRC não existe — nada a sincronizar." >&2
    exit 1
fi
mkdir -p "$DST"

copy_file() {
    local src="$1" dst="$2"
    if [ -f "$src" ]; then
        mkdir -p "$(dirname "$dst")"
        cp -p "$src" "$dst"
        echo "  🔁 arquivo: $src → $dst"
    fi
}

copy_dir() {
    local src="$1" dst="$2"
    [ -d "$src" ] || return 0
    mkdir -p "$dst"
    local copied=0
    for f in "$src"/*; do
        if [ -f "$f" ]; then
            cp -p "$f" "$dst/"
            copied=1
        fi
    done
    if [ "$copied" = "1" ]; then
        echo "  🔁 diretório: $src → $dst"
    fi
}

echo "📡 dev-sync: $SRC → $DST"

# --- Shell estático (default) ---
copy_file "$SRC/index.html" "$DST/index.html"
copy_dir  "$SRC/assets/css" "$DST/assets/css"
copy_dir  "$SRC/assets/js"  "$DST/assets/js"
copy_file "$SRC/assets/cover.jpg" "$DST/assets/cover.jpg"
copy_file "$SRC/assets/cover.png" "$DST/assets/cover.png"
copy_file "$SRC/manifest.webmanifest" "$DST/manifest.webmanifest"
copy_file "$SRC/offline.html" "$DST/offline.html"
copy_file "$SRC/llms.txt" "$DST/llms.txt"
copy_dir  "$SRC/icons" "$DST/icons"
copy_file "$SRC/ads.txt" "$DST/ads.txt"
copy_file "$SRC/js/supabase_client.js" "$DST/js/supabase_client.js"

# --- Modo completo: catálogo, feeds e service worker ---
if [ "$FULL" = "1" ]; then
    echo "  ⚠️  Modo --full: copiando também data/, feed* e sw.js"
    copy_dir  "$SRC/data" "$DST/data"
    copy_file "$SRC/feed.xml" "$DST/feed.xml"
    copy_file "$SRC/feed.json" "$DST/feed.json"
    copy_file "$SRC/feed-brasil-e-mundo.xml" "$DST/feed-brasil-e-mundo.xml"
    copy_file "$SRC/sw.js" "$DST/sw.js"
    if [ "$CACHE_BUST" = "1" ] && [ -f "$DST/sw.js" ]; then
        stamp="$(date -u +%Y%m%d%H%M)"
        sed -i "s/const CACHE = \"[^\"]*\"/const CACHE = \"vld-v1-$stamp\"/" "$DST/sw.js"
        echo "  ♻️  Cache-bust sw.js → vld-v1-$stamp"
    fi
else
    echo "  ℹ️  data/, feed* e sw.js NÃO foram tocados (use -c/--full para incluí-los)"
fi

echo "✅ dev-sync concluído."
