#!/usr/bin/env bash
# CAD der eigenen 100-mm-Finger (finger/cad.py, build123d) -> STEP/STL/JSON.
#   scripts/finger_cad.sh [ZIELORDNER]     # Standard cad/finger/
# build123d kommt per uvx (Wheels, keine Systempakete).
set -euo pipefail
cd "$(dirname "$0")/.."
UVX=${UVX:-$(command -v uvx || echo "$HOME/.local/bin/uvx")}
[ -x "$UVX" ] || { echo "uvx fehlt (https://docs.astral.sh/uv/)" >&2; exit 3; }
exec "$UVX" -p 3.12 --with build123d==0.13.0 --with pyyaml --with numpy python -m finger.cad "$@"
