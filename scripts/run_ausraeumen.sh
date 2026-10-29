#!/usr/bin/env bash
# Ausraeumen (scripts/demo_ausraeumen.py) auf DIESEM Rechner, ein Befehl.
# Rechnerneutral: Pfade nur aus config/local.env bzw. Umgebung. Auf einem
# geteilten GPU-Rechner nur ueber die GPU-Warteschlange starten (eigene
# systemd-run-Unit, kein eigenes Locking hier drin).
#
#   scripts/run_ausraeumen.sh [--cpu] demo|negativ|beide [Argumente fuer demo_ausraeumen.py]
#
#   ohne --cpu  Python des Isaac-Lab-venv ($RAEUMWERK_HOME/venvs/isaaclab), GPU wenn vorhanden
#   --cpu       Newton mit festen Versionen per uvx, Rechnung auf der CPU
#   RAEUMWERK_PYTHON  eigenes Python mit Newton (ueberschreibt beides)
#
# Schreibt nach $RAEUMWERK_AUSRAEUMEN_RUNS/<Zeitstempel>/<art>/ (Standard
# $RAEUMWERK_HOME/runs/ausraeumen): versuch-00.json, zusammenfassung.json,
# lauf.log, ss-ltnp.txt. Exit 0 nur, wenn jede Art ihre Erwartung erfuellt
# (demo: 4/4 Glaeser; negativ: Klemmglas als Fehlversuch erkannt).
# Der Variationslauf geht ueber scripts/raeumwerk run experimente/ausraeumen_variation.yaml.
set -uo pipefail

cd "$(dirname "$0")/.."
_runs_env=${RAEUMWERK_AUSRAEUMEN_RUNS:-}
if [ -f config/local.env ]; then set -a; . config/local.env; set +a; fi
RAEUMWERK_HOME=${RAEUMWERK_HOME:-$HOME/raeumwerk}
RUNS=${_runs_env:-${RAEUMWERK_AUSRAEUMEN_RUNS:-$RAEUMWERK_HOME/runs/ausraeumen}}

cpu=0
if [ "${1:-}" = "--cpu" ]; then cpu=1; shift; fi
art=${1:-}
shift || true
case "$art" in
  demo|negativ) arten=("$art") ;;
  beide) arten=(demo negativ) ;;
  *) echo "Aufruf: $0 [--cpu] demo|negativ|beide [Argumente]" >&2; exit 2 ;;
esac

NEWTON_PINS=(--with newton==1.6.1 --with warp-lang==1.17.0 --with mujoco==3.12.0 --with mujoco-warp==3.12.0
             --with numpy --with pyyaml)
extra=()
if [ -n "${RAEUMWERK_PYTHON:-}" ]; then
  py=("$RAEUMWERK_PYTHON")
elif [ "$cpu" = 1 ]; then
  UVX=${UVX:-$(command -v uvx || echo "$HOME/.local/bin/uvx")}
  [ -x "$UVX" ] || { echo "uvx fehlt (https://docs.astral.sh/uv/)" >&2; exit 3; }
  py=("$UVX" -p 3.12 "${NEWTON_PINS[@]}" python)
  extra=(--device cpu)
else
  PY="$RAEUMWERK_HOME/venvs/isaaclab/bin/python"
  [ -x "$PY" ] || { echo "venv fehlt: scripts/install_backends.sh isaaclab (oder --cpu)" >&2; exit 3; }
  py=("$PY")
fi

stamp=${RAEUMWERK_STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}
base="$RUNS/$stamp"
mkdir -p "$base"
( while true; do echo "--- $(date -Is)"; ss -ltnp 2>/dev/null; sleep 10; done ) > "$base/ss-ltnp.txt" 2>&1 &
sspid=$!
trap 'kill $sspid 2>/dev/null' EXIT

rc=0
for a in "${arten[@]}"; do
  out="$base/$a"
  mkdir -p "$out"
  {
    echo "[$(date -Is)] start demo_ausraeumen art=$a commit=$(git rev-parse --short HEAD 2>/dev/null || cat REVISION 2>/dev/null || echo ?)"
    nvidia-smi --query-gpu=name,memory.used,memory.total --format=csv,noheader 2>/dev/null || true
    free -m | head -2
  } > "$out/lauf.log"
  "${py[@]}" scripts/demo_ausraeumen.py --art "$a" --out "$out" "${extra[@]}" "$@" >> "$out/lauf.log" 2>&1
  r=$?
  echo "[$(date -Is)] ende art=$a rc=$r" >> "$out/lauf.log"
  grep -E '^(VERSUCH|  glas_|AUSRAEUMEN_RESULT)' "$out/lauf.log" | cut -c1-400
  [ "$r" = 0 ] || rc=1
done
echo "Ergebnis: $base"
exit $rc
