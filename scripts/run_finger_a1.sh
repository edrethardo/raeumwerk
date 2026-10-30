#!/usr/bin/env bash
# Greifen mit den eigenen Fingern im Aufbau A1-S1 (scripts/demo_finger_a1.py), Newton auf der CPU.
#   scripts/run_finger_a1.sh [Argumente fuer demo_finger_a1.py, ohne --device]
# Pfade nur aus config/local.env bzw. Umgebung; RAEUMWERK_PYTHON ueberschreibt uvx.
set -uo pipefail
cd "$(dirname "$0")/.."
if [ -f config/local.env ]; then set -a; . config/local.env; set +a; fi
if [ -n "${RAEUMWERK_PYTHON:-}" ]; then
  py=("$RAEUMWERK_PYTHON")
else
  UVX=${UVX:-$(command -v uvx || echo "$HOME/.local/bin/uvx")}
  [ -x "$UVX" ] || { echo "uvx fehlt (https://docs.astral.sh/uv/)" >&2; exit 3; }
  py=("$UVX" -p 3.12 --with newton==1.6.1 --with warp-lang==1.17.0 --with mujoco==3.12.0 --with mujoco-warp==3.12.0
      --with numpy --with pyyaml python)
fi
exec "${py[@]}" scripts/demo_finger_a1.py --device cpu "$@"
