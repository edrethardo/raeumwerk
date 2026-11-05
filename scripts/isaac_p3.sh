#!/usr/bin/env bash
# Rendert Kameratag-P3-Szenen (scripts/isaac_p3_render.py) mit Isaac Sim 6.2 RTX auf DIESEM Rechner (headless).
# Auf einem geteilten GPU-Rechner nur unter GPU-Lock/-Warteschlange starten (docs/kameratag-p3.md).
#
#   scripts/isaac_p3.sh <szenen.json> <name> [argumente fuer isaac_p3_render.py ...]
#
# Ergebnis: $RAEUMWERK_ISAAC_RENDER_RUNS/<name>/ mit <id>_rgb.png, <id>_tiefe.npz, <id>_inst.npz, <id>.json,
# messung.json (RAM-/VRAM-Spitze), lauf.log. Setzt OMNI_KIT_ACCEPT_EULA=YES (wer den Job startet, nimmt damit
# die NVIDIA-Lizenz an; Freigabe des Owners liegt vor) und HOME auf $RAEUMWERK_KIT_HOME, falls gesetzt.
set -uo pipefail

cd "$(dirname "$0")/.."
REPO=$(pwd)
if [ -f config/local.env ]; then set -a; . config/local.env; set +a; fi
export RAEUMWERK_HOME=${RAEUMWERK_HOME:-$HOME/raeumwerk}
RUNS=${RAEUMWERK_ISAAC_RENDER_RUNS:-$RAEUMWERK_HOME/runs/isaac_render}
export OMNI_KIT_ACCEPT_EULA=YES
szenen=${1:?szenen.json}; name=${2:?name}; shift 2
[[ $name =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$ ]] || { echo "ungueltiger Name '$name'" >&2; exit 2; }
[ -f "$szenen" ] || { echo "Szenen fehlen: $szenen" >&2; exit 2; }
PY="$RAEUMWERK_HOME/venvs/isaacsim/bin/python"
[ -x "$PY" ] || { echo "venv fehlt: scripts/install_backends.sh isaacsim" >&2; exit 3; }
out="$RUNS/$name"
mkdir -p "$out"
if [ -n "${RAEUMWERK_KIT_HOME:-}" ]; then mkdir -p "$RAEUMWERK_KIT_HOME"; export HOME="$RAEUMWERK_KIT_HOME"; fi
echo "[$(date -Is)] isaac_p3 $name: $(basename "$szenen") $*" | tee -a "$out/lauf.log"
python3 "$REPO/scripts/isaac_render_messen.py" --json "$out/messung.json" -- \
  "$PY" "$REPO/scripts/isaac_p3_render.py" "$szenen" --out "$out" "$@" >> "$out/lauf.log" 2>&1
rc=$?
grep -E '^(ISAAC_P3|MESSUNG|SZENE) ' "$out/lauf.log" | tail -12
echo "[$(date -Is)] ende rc=$rc, Ergebnis: $out" | tee -a "$out/lauf.log"
exit $rc
