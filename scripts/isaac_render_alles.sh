#!/usr/bin/env bash
# Alles in einem Job auf einem Rechner mit Isaac-Sim-venv (ohne ssh, z. B. zweiter Rechner):
# Assets holen, Greifdemo auf der CPU aufzeichnen, Renderauftraege bauen, mit
# Isaac Sim rendern (scripts/isaac_render_paket.sh) und - falls ffmpeg da ist -
# das Video kodieren.
#
#   bash scripts/isaac_render_alles.sh [praefix=r1] [budget_minuten=120]
#
# Ergebnis unter $RAEUMWERK_ISAAC_RENDER_RUNS (Standard
# $RAEUMWERK_HOME/runs/isaac_render): <praefix>-{probe,spuelmaschine,standbild,video}/,
# auftrag-*.npz, demo.npz und, mit ffmpeg, <praefix>-greifdemo-isaac.mp4.
# Braucht uv/uvx (CPU-Demo und Auftraege) und das venv aus
# scripts/install_backends.sh isaacsim. Setzt OMNI_KIT_ACCEPT_EULA=YES.
set -euo pipefail

cd "$(dirname "$0")/.."
p=${1:-r1}; budget=${2:-120}
if [ -f config/local.env ]; then set -a; . config/local.env; set +a; fi
export RAEUMWERK_HOME=${RAEUMWERK_HOME:-$HOME/raeumwerk}
RUNS=${RAEUMWERK_ISAAC_RENDER_RUNS:-$RAEUMWERK_HOME/runs/isaac_render}
export RAEUMWERK_ISAAC_RENDER_RUNS=$RUNS
mkdir -p "$RUNS"
UVX=${UVX:-$(command -v uvx || echo "$HOME/.local/bin/uvx")}
log() { echo "[$(date -Is)] $*"; }

log "Assets"; bash scripts/fetch_assets.sh
if [ ! -f "$RUNS/demo.npz" ]; then
  log "Greifdemo (CPU) mit Aufzeichnung"
  UVX=$UVX RAEUMWERK_GREIFEN_RUNS="$RUNS/greifen" bash scripts/run_greifen.sh --cpu demo --aufzeichnen "$RUNS/demo.npz"
fi
log "Renderauftraege"
"$UVX" -p 3.12 --with numpy --with pyyaml python scripts/isaac_render_auftrag.py greifdemo "$RUNS/demo.npz" \
  --out "$RUNS/auftrag-greifdemo.npz"
"$UVX" -p 3.12 --with numpy --with pyyaml python scripts/isaac_render_auftrag.py spuelmaschine \
  --out "$RUNS/auftrag-spuelmaschine.npz"
log "Rendern"
set +e
bash scripts/isaac_render_paket.sh auftrag-greifdemo.npz auftrag-spuelmaschine.npz "$p" "$budget"
rc=$?
set -e
log "Rendern rc=$rc"
if [ "$rc" = 0 ] && command -v ffmpeg >/dev/null; then
  "$UVX" -p 3.12 --with numpy --with pyyaml --with pillow python scripts/isaac_render_video.py "$RUNS/$p-video" \
    --auftrag "$RUNS/auftrag-greifdemo.npz" --out "$RUNS/$p-greifdemo-isaac.mp4"
fi
exit "$rc"
