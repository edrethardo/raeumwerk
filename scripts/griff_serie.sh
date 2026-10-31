#!/usr/bin/env bash
# Newton-Laeufe von scripts/griff_lauf.py nacheinander (docs/griff-verrauscht.md).
#
#   scripts/griff_serie.sh AUSGABE LISTE
#
# LISTE: je Zeile "<name> <Argumente fuer griff_lauf.py>" (ohne --out/--aufzeichnen), z. B.
#   t6-1 --art teller --seed 1 --wahrnehmung --device cuda
# Je Lauf: AUSGABE/<name>/versuch.json, AUSGABE/<name>.log, AUSGABE/<name>.npz (Aufzeichnung).
# Vorhandene versuch.json werden uebersprungen (fortsetzbar). uvx: $UVX oder uvx im PATH.
set -u
D="$(cd "$(dirname "$0")" && pwd)"
O="$(mkdir -p "$1" && cd "$1" && pwd)"
LISTE="$2"
UVX="${UVX:-$(command -v uvx)}"
while read -r name rest; do
  [ -z "$name" ] && continue
  case "$name" in \#*) continue ;; esac
  [ -f "$O/$name/versuch.json" ] && continue
  # shellcheck disable=SC2086
  "$UVX" -p 3.12 --with newton==1.6.1 --with warp-lang==1.17.0 --with mujoco==3.12.0 \
    --with mujoco-warp==3.12.0 --with numpy --with pyyaml --with scipy \
    python "$D/griff_lauf.py" --out "$O/$name" --aufzeichnen "$O/$name.npz" $rest > "$O/$name.log" 2>&1
  echo "rc=$?" >> "$O/$name.log"
done < "$LISTE"
echo fertig > "$O/fertig-$(basename "$LISTE")"
