#!/usr/bin/env bash
# Mehrere Isaac-Renderlaeufe in EINEM GPU-Job (ein Platz in der Warteschlange):
#   1. Probe: ein Bild der Greifdemo (RTX Real-Time) - bricht bei Fehlern sofort ab
#   2. Spuelmaschinen-Standbild (Path Tracing, 1920x1080)
#   3. Greifdemo-Standbild (Path Tracing, 1920x1080, Bild --mitte)
#   4. Greifdemo-Video (RTX Real-Time, 1280x720), fortsetzbar
#   5. falls vorhanden: Ausraeumen-Video aus <auftrag-ausraeumen.npz> (Standard
#      auftrag-ausraeumen.npz unter $RAEUMWERK_ISAAC_RENDER_RUNS), fortsetzbar
#   Ist das Zeitbudget vor dem letzten Bild aufgebraucht, endet der Job mit
#   Exit 3 (dann denselben Befehl erneut einreichen: fertige Schritte und
#   Bilder werden uebersprungen).
#
#   scripts/isaac_render_paket.sh <auftrag-greifdemo.npz> <auftrag-spuelmaschine.npz> <praefix> \
#       [budget_minuten=26] [mitte=360] [auftrag-ausraeumen.npz]
#
# Ergebnisse unter $RAEUMWERK_ISAAC_RENDER_RUNS/<praefix>-{probe,spuelmaschine,standbild,video}/.
set -uo pipefail

cd "$(dirname "$0")/.."
greif=${1:?auftrag-greifdemo.npz}; spuel=${2:?auftrag-spuelmaschine.npz}; p=${3:?praefix}
budget=${4:-26}; mitte=${5:-360}
start=$(date +%s)
if [ -f config/local.env ]; then set -a; . config/local.env; set +a; fi
RUNS=${RAEUMWERK_ISAAC_RENDER_RUNS:-${RAEUMWERK_HOME:-$HOME/raeumwerk}/runs/isaac_render}
fertig() { [ -f "$RUNS/$1/render.json" ] && grep -q '"render_s"' "$RUNS/$1/render.json" && ! grep -q '"error"' "$RUNS/$1/render.json"; }
schritt() {  # name, argumente ...
  local n=$1; shift
  if fertig "$n" && [ "$n" != "$p-video" ]; then echo "[paket] $n schon fertig"; return 0; fi
  echo "[paket] $(date -Is) $n"
  bash scripts/isaac_render.sh "$@"
}
schritt "$p-probe" "$greif" "$p-probe" --von "$mitte" --bis "$((mitte + 1))" --einschwingen 30 || exit $?
schritt "$p-spuelmaschine" "$spuel" "$p-spuelmaschine" --modus pt --spp 64 --subframes 16 \
  --breite 1920 --hoehe 1080 || exit $?
schritt "$p-standbild" "$greif" "$p-standbild" --von "$mitte" --bis "$((mitte + 1))" --modus pt --spp 64 \
  --subframes 16 --breite 1920 --hoehe 1080 || exit $?
aus=${6:-auftrag-ausraeumen.npz}
case "$aus" in /*) ;; *) aus="$RUNS/$aus" ;; esac
if [ -f "$aus" ]; then
  schritt "$p-probe-ausraeumen" "$aus" "$p-probe-ausraeumen" --von 700 --bis 701 --einschwingen 30 || exit $?
fi
rest=$(( budget - ($(date +%s) - start) / 60 - 2 ))
[ "$rest" -ge 2 ] || { echo "[paket] kein Budget mehr fuer das Video"; exit 3; }
bash scripts/isaac_render.sh "$greif" "$p-video" --fortsetzen --max-minuten "$rest" --subframes 8 || exit $?
[ -f "$aus" ] || { echo "[paket] kein Ausraeumen-Auftrag ($aus)"; exit 0; }
rest=$(( budget - ($(date +%s) - start) / 60 - 2 ))
[ "$rest" -ge 2 ] || { echo "[paket] kein Budget mehr fuer das Ausraeumen-Video"; exit 3; }
bash scripts/isaac_render.sh "$aus" "$p-ausraeumen" --fortsetzen --max-minuten "$rest" --subframes 8
