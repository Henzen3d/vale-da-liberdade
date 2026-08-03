#!/usr/bin/env bash
# Fallback Edge TTS (voz única) + FX vocal do Ricardo — genérico por data.
# Uso:
#   bash scripts/tts_fallback_edge.sh                 # data de hoje
#   bash scripts/tts_fallback_edge.sh 2026-07-22
#
# Fluxo:
#   1) Lê episodes/YYYY-MM-DD-tts.txt (Peter:/Ricardo: por linha)
#   2) Sintetiza CADA fala em arquivo separado (edge-tts)
#   3) Aplica scripts/ricardo_voice_fx.py só nos chunks do Ricardo
#   4) Concatena via ffmpeg + loudnorm
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATE="${1:-$(date +%F)}"
AUDIO="$ROOT/audio"
EPISODES="$ROOT/episodes"
TTS_TXT="$EPISODES/${DATE}-tts.txt"
MD="$EPISODES/${DATE}.md"
VOICE="${EDGE_TTS_VOICE:-pt-BR-AntonioNeural}"
HERMES_PY="${HERMES_PY:-/home/osmar/.hermes/hermes-agent/venv/bin/python3}"
MIN_CHUNK_BYTES="${MIN_CHUNK_BYTES:-15000}"
MIN_FINAL_BYTES="${MIN_FINAL_BYTES:-1000000}"
FX_SCRIPT="$ROOT/scripts/ricardo_voice_fx.py"
FX_CONFIG="$ROOT/config/ricardo_voice_fx.yaml"
APPLY_RICARDO_FX="${APPLY_RICARDO_FX:-1}"

mkdir -p "$AUDIO"

if [[ ! -x "$HERMES_PY" ]]; then
  echo "FALHA: Python Hermes não encontrado: $HERMES_PY" >&2
  exit 2
fi

if ! "$HERMES_PY" -c "import edge_tts" 2>/dev/null; then
  echo "FALHA: edge_tts ausente no $HERMES_PY. Instale: $HERMES_PY -m pip install edge-tts" >&2
  exit 2
fi

if [[ ! -f "$TTS_TXT" ]]; then
  if [[ -f "$MD" ]]; then
    echo "TTS ausente — gerando a partir de $MD"
    "$HERMES_PY" "$ROOT/scripts/tts_preprocessor.py" \
      --input "$MD" \
      --output "$TTS_TXT" || true
  fi
fi

if [[ ! -f "$TTS_TXT" ]]; then
  echo "FALHA: não há $TTS_TXT nem $MD" >&2
  exit 2
fi

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

FILELIST="$AUDIO/${DATE}-edge-filelist.txt"
: > "$FILELIST"
index=0
kept=0
skipped=0
fx_ok=0
fx_skip=0

while IFS= read -r line || [[ -n "$line" ]]; do
  [[ -z "${line// /}" ]] && continue
  [[ "$line" =~ ^\[ ]] && continue
  [[ "$line" =~ ^# ]] && continue

  speaker="ricardo"
  transcript="$line"
  if [[ "$line" =~ ^[Pp]eter:[[:space:]]*(.*) ]]; then
    speaker="peter"
    transcript="${BASH_REMATCH[1]}"
  elif [[ "$line" =~ ^[Rr]icardo:[[:space:]]*(.*) ]]; then
    speaker="ricardo"
    transcript="${BASH_REMATCH[1]}"
  fi

  transcript="${transcript#"${transcript%%[![:space:]]*}"}"
  transcript="${transcript%"${transcript##*[![:space:]]}"}"
  transcript="${transcript//\[PAUSA_CURTA\]/ }"
  transcript="${transcript//\[PAUSA\]/ }"

  wc=$(echo "$transcript" | wc -w | tr -d ' ')
  if [[ -z "$transcript" || "$wc" -lt 3 ]]; then
    skipped=$((skipped + 1))
    continue
  fi

  index=$((index + 1))
  raw_out="$AUDIO/${DATE}-edge-${speaker}-$(printf '%03d' "$index").mp3"
  final_chunk="$raw_out"

  if ! "$HERMES_PY" -m edge_tts --text "$transcript" --voice "$VOICE" --write-media "$raw_out"; then
    echo "AVISO: falha edge_tts no chunk $index — pulando" >&2
    skipped=$((skipped + 1))
    rm -f "$raw_out"
    continue
  fi

  size=$(stat -c%s "$raw_out" 2>/dev/null || echo 0)
  if [[ "$size" -lt "$MIN_CHUNK_BYTES" ]]; then
    echo "AVISO: chunk $index pequeno (${size}B) — NÃO concatena"
    skipped=$((skipped + 1))
    rm -f "$raw_out"
    continue
  fi

  # --- FX Ricardo (formant/pitch/EQ) antes do concat ---
  if [[ "$speaker" == "ricardo" && "$APPLY_RICARDO_FX" == "1" && -f "$FX_SCRIPT" ]]; then
    fx_out="$AUDIO/${DATE}-edge-ricardo-$(printf '%03d' "$index")-fx.mp3"
    if "$HERMES_PY" "$FX_SCRIPT" --in "$raw_out" --out "$fx_out" --config "$FX_CONFIG" --force 2>/tmp/ricardo_fx_err.txt; then
      if [[ -f "$fx_out" ]]; then
        fxs=$(stat -c%s "$fx_out" 2>/dev/null || echo 0)
        if [[ "$fxs" -ge "$MIN_CHUNK_BYTES" ]]; then
          final_chunk="$fx_out"
          fx_ok=$((fx_ok + 1))
        else
          echo "AVISO: FX Ricardo $index saída pequena — usa raw"
          fx_skip=$((fx_skip + 1))
        fi
      fi
    else
      echo "AVISO: FX Ricardo falhou no chunk $index — usa raw"
      tail -2 /tmp/ricardo_fx_err.txt 2>/dev/null || true
      fx_skip=$((fx_skip + 1))
    fi
  fi

  printf "file '%s'\n" "$final_chunk" >> "$FILELIST"
  kept=$((kept + 1))
  echo "ok $index $speaker $(stat -c%s "$final_chunk")B chunk=$(basename "$final_chunk")"
done < "$TTS_TXT"

echo "chunks kept=$kept skipped=$skipped | ricardo_fx ok=$fx_ok fail/skip=$fx_skip"

if [[ "$kept" -lt 5 ]]; then
  echo "FALHA: poucos chunks úteis ($kept). Abortando concat." >&2
  exit 3
fi

FINAL_TMP="$AUDIO/${DATE}-edge-concat.mp3"
FINAL="$AUDIO/${DATE}.mp3"
FINAL_NAMED="$AUDIO/${DATE}-vale-da-liberdade.mp3"

ffmpeg -y -f concat -safe 0 -i "$FILELIST" -c copy "$FINAL_TMP" >/dev/null 2>&1

ffmpeg -y -i "$FINAL_TMP" \
  -af "highpass=f=80,loudnorm=I=-16:TP=-1.5:LRA=11" \
  -ar 44100 -ac 1 -b:a 192k \
  "$FINAL_NAMED" >/dev/null 2>&1

cp -f "$FINAL_NAMED" "$FINAL"
rm -f "$FINAL_TMP"

final_size=$(stat -c%s "$FINAL")
if [[ "$final_size" -lt "$MIN_FINAL_BYTES" ]]; then
  echo "FALHA: MP3 final pequeno demais (${final_size}B < ${MIN_FINAL_BYTES})" >&2
  exit 3
fi

dur=$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$FINAL" 2>/dev/null || echo 0)
echo "✅ Fallback Edge OK: $FINAL (${final_size} bytes, ${dur}s)"
echo "   named: $FINAL_NAMED | kept=$kept skipped=$skipped | FX Ricardo=$fx_ok"
