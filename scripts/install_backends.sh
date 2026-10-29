#!/usr/bin/env bash
# Installiert die Simulations-Backends fuer Raeumwerk idempotent unter
# $RAEUMWERK_HOME (venvs, uv-Cache, Python-Interpreter). Rechnerneutral:
# Pfade kommen nur aus Umgebungsvariablen bzw. config/local.env.
#
#   scripts/install_backends.sh isaacsim|isaaclab|all
#
#   RAEUMWERK_HOME  Zielordner (Standard: $HOME/raeumwerk; nie das Arbeitsverzeichnis)
#   UV              uv-Binary (Standard: uv im PATH, sonst ~/.local/bin/uv)
#
# Braucht keine GPU und kein sudo. Lange Laeufe mit nice/ionice bzw. als
# systemd-run --user Unit starten (siehe docs/umgebung.md).
set -euo pipefail

cd "$(dirname "$0")/.."
# shellcheck disable=SC1091
if [ -f config/local.env ]; then set -a; . config/local.env; set +a; fi
RAEUMWERK_HOME=${RAEUMWERK_HOME:-${RAEUMWERK_ROOT:-$HOME/raeumwerk}}
UV=${UV:-$(command -v uv || echo "$HOME/.local/bin/uv")}
[ -x "$UV" ] || { echo "uv fehlt (https://docs.astral.sh/uv/)" >&2; exit 3; }

ISAACSIM_VERSION=${ISAACSIM_VERSION:-6.2.0.0}
ISAACLAB_VERSION=${ISAACLAB_VERSION:-3.0.0}
TORCH_VERSION=${TORCH_VERSION:-2.11.0}
TORCH_INDEX=${TORCH_INDEX:-https://download.pytorch.org/whl/cu130}

export UV_CACHE_DIR="${UV_CACHE_DIR:-$RAEUMWERK_HOME/uvcache}"
export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-$RAEUMWERK_HOME/uv-python}"
export UV_HTTP_TIMEOUT=${UV_HTTP_TIMEOUT:-600}
export UV_HTTP_RETRIES=${UV_HTTP_RETRIES:-10}   # grosse Wheels brachen mit "connection reset" ab
export UV_LOCK_TIMEOUT=${UV_LOCK_TIMEOUT:-7200} # parallele Installs teilen den Cache-Lock
export UV_LINK_MODE=${UV_LINK_MODE:-hardlink}   # Cache und venvs auf demselben Dateisystem
export PIP_CACHE_DIR="${PIP_CACHE_DIR:-$RAEUMWERK_HOME/pipcache}"

mkdir -p "$RAEUMWERK_HOME/venvs" "$UV_CACHE_DIR" "$UV_PYTHON_INSTALL_DIR"

stamp() { echo "[$(date -Is)] $*"; }
size() { du -sh "$1" 2>/dev/null | cut -f1; }
root_free() { df -BG --output=avail / | tail -1 | tr -d ' '; }
installed() { "$1/bin/python" -c "import importlib.metadata as m,sys; sys.exit(m.version('$2')!='$3')" 2>/dev/null; }

install_isaacsim() {
  local venv="$RAEUMWERK_HOME/venvs/isaacsim"
  if installed "$venv" isaacsim "$ISAACSIM_VERSION"; then
    stamp "isaacsim $ISAACSIM_VERSION schon installiert"; return 0
  fi
  stamp "isaacsim: venv anlegen (frei auf /: $(root_free))"
  [ -x "$venv/bin/python" ] || "$UV" venv -p 3.12 --seed "$venv"
  stamp "isaacsim: torch $TORCH_VERSION ($TORCH_INDEX)"
  "$UV" pip install --python "$venv/bin/python" \
    "torch==$TORCH_VERSION" --index-url "$TORCH_INDEX" \
    --extra-index-url https://pypi.org/simple --index-strategy unsafe-best-match
  stamp "isaacsim: isaacsim[all,extscache]==$ISAACSIM_VERSION"
  local fl=()
  # vorab resumierbar geladene Wheels (scripts/fetch_wheels.sh) bevorzugen
  [ -d "$RAEUMWERK_HOME/wheels" ] && fl=(--find-links "$RAEUMWERK_HOME/wheels")
  "$UV" pip install --python "$venv/bin/python" "${fl[@]}" \
    "isaacsim[all,extscache]==$ISAACSIM_VERSION" \
    --extra-index-url https://pypi.nvidia.com --index-strategy unsafe-best-match --prerelease=allow
  "$venv/bin/python" -c "import importlib.metadata as m; print('isaacsim', m.version('isaacsim')); print('torch', m.version('torch'))"
  stamp "isaacsim: fertig, venv $(size "$venv"), Cache $(size "$UV_CACHE_DIR"), frei auf /: $(root_free)"
}

install_isaaclab() {
  local venv="$RAEUMWERK_HOME/venvs/isaaclab"
  if installed "$venv" isaaclab "$ISAACLAB_VERSION"; then
    stamp "isaaclab $ISAACLAB_VERSION schon installiert"; return 0
  fi
  stamp "isaaclab: venv anlegen (frei auf /: $(root_free))"
  [ -x "$venv/bin/python" ] || "$UV" venv -p 3.12 --seed "$venv"
  stamp "isaaclab: isaaclab==$ISAACLAB_VERSION (Newton, ohne Isaac Sim)"
  "$UV" pip install --python "$venv/bin/python" \
    "isaaclab==$ISAACLAB_VERSION" --torch-backend cu130 \
    --index https://pypi.nvidia.com --index-strategy unsafe-best-match
  "$venv/bin/python" -c "import importlib.metadata as m
for p in ('isaaclab','newton','warp-lang','torch'):
    try: print(p, m.version(p))
    except Exception as e: print(p, 'fehlt', e)"
  stamp "isaaclab: fertig, venv $(size "$venv"), Cache $(size "$UV_CACHE_DIR"), frei auf /: $(root_free)"
}

case "${1:-all}" in
  isaacsim) install_isaacsim ;;
  isaaclab) install_isaaclab ;;
  all) install_isaaclab; install_isaacsim ;;
  *) echo "usage: $0 isaacsim|isaaclab|all" >&2; exit 2 ;;
esac
