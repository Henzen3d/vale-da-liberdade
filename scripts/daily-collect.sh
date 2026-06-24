#!/usr/bin/env bash
set -euo pipefail

TODAY="$(date +%Y-%m-%d)"
BASE="$HOME/web-jornal-vale-da-liberdade"
OUT="$BASE/episodes"
RAW="$OUT/raw-$TODAY.md"
ROTEIRO="$OUT/$TODAY.md"
INDEX="$BASE/archive/index.md"

mkdir -p "$OUT" "$BASE/archive"

cat > "$RAW" <<EOF
# Web Jornal Vale da Liberdade — RAW — $TODAY

## Fontes
- https://ndmais.com.br/blumenau/
- https://oblumenauense.com.br/
- https://altovaleagora.com.br/
- https://www.informeblumenau.com/
- https://ajnoticias.com.br/
- https://www.nsctotal.com.br/
- https://altovalenoticias.com.br/
- https://www.jatv.com.br/
- https://blogdojaime.com.br/

## Notícias brutas
EOF

cat <<'EOF' >> "$RAW"
Extração automática indisponível neste shell. Cole aqui o conteúdo consolidado das fontes antes de gerar o roteiro.
EOF

cat > "$ROTEIRO" <<EOF
# Web Jornal Vale da Liberdade — $TODAY
Confira agora os destaques do dia...

## Manchetes do dia
- 
- 
- 

## Abertura
Peter:
Ricardo:

## Quadro: Segurança Pública
Peter:
Ricardo:

## Quadro: Saúde
Peter:
Ricardo:

## Quadro: Educação
Peter:
Ricardo:

## Quadro: Política e Administração Pública
Peter:
Ricardo:

## Quadro: Esportes e Comunidade
Peter:
Ricardo:

## Quadro opcional: Rapidinhas da Loucura Estatal
Peter:
Ricardo:

## Fechamento
Peter:
Ricardo:

## Referências
- $RAW
EOF

touch "$INDEX"
grep -q "## $TODAY" "$INDEX" 2>/dev/null || echo "- $TODAY" >> "$INDEX"

echo "Gerado: $ROTEIRO"
