#!/usr/bin/env bash
# Rendert einen Renderauftrag mit Isaac Sim 6.2 RTX auf DIESEM Rechner (headless).
# Auf einem geteilten GPU-Rechner nur ueber GPU-Warteschlange bzw. -Lock starten
# (scripts/submit_gpu.sh, siehe docs/START.md "Rendern mit Isaac Sim").
#
#   scripts/isaac_render.sh <auftrag.npz> <name> [argumente fuer isaac_render.py ...]
#
# Auftrag relativ zu $RAEUMWERK_ISAAC_RENDER_RUNS (Standard
# $RAEUMWERK_HOME/runs/isaac_render) oder absolut. Ergebnis:
# $RAEUMWERK_ISAAC_RENDER_RUNS/<name>/ mit bild_*.png, render.json (Zeiten,
# Replay-Fehler), messung.json (RAM-/VRAM-Spitze, Listener), lauf.log.
# Setzt OMNI_KIT_ACCEPT_EULA=YES (nicht-interaktiver Weg laut NVIDIA-Doku;
# wer den Job startet, nimmt damit die NVIDIA-Lizenz an) und HOME auf
# $RAEUMWERK_KIT_HOME (Kit-/Shader-Caches nicht auf /), falls gesetzt.
set -uo pipefail

cd "$(dirname "$0")/.."
REPO=$(pwd)
if [ -f config/local.env ]; then set -a; . config/local.env; set +a; fi
export RAEUMWERK_HOME=${RAEUMWERK_HOME:-$HOME/raeumwerk}
RUNS=${RAEUMWERK_ISAAC_RENDER_RUNS:-$RAEUMWERK_HOME/runs/isaac_render}
export RAEUMWERK_ASSETS=${RAEUMWERK_ASSETS:-$RAEUMWERK_HOME/assets}
export OMNI_KIT_ACCEPT_EULA=YES
auftrag=${1:?auftrag.npz}; name=${2:?name}; shift 2
[[ $name =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$ ]] || { echo "ungueltiger Name '$name'" >&2; exit 2; }
case "$auftrag" in /*) ;; *) auftrag="$RUNS/$auftrag" ;; esac
[ -f "$auftrag" ] || { echo "Auftrag fehlt: $auftrag" >&2; exit 2; }
PY="$RAEUMWERK_HOME/venvs/isaacsim/bin/python"
[ -x "$PY" ] || { echo "venv fehlt: scripts/install_backends.sh isaacsim" >&2; exit 3; }
out="$RUNS/$name"
mkdir -p "$out"
if [ -n "${RAEUMWERK_KIT_HOME:-}" ]; then mkdir -p "$RAEUMWERK_KIT_HOME"; export HOME="$RAEUMWERK_KIT_HOME"; fi
echo "[$(date -Is)] isaac_render $name: $(basename "$auftrag") $*" | tee -a "$out/lauf.log"
python3 "$REPO/scripts/isaac_render_messen.py" --json "$out/messung.json" -- \
  "$PY" "$REPO/scripts/isaac_render.py" "$auftrag" --out "$out" "$@" >> "$out/lauf.log" 2>&1
rc=$?
grep -E '^(ISAAC_RENDER|MESSUNG|BILD) ' "$out/lauf.log" | tail -8
echo "[$(date -Is)] ende rc=$rc, Ergebnis: $out" | tee -a "$out/lauf.log"
exit $rc
