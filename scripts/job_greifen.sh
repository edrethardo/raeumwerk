#!/usr/bin/env bash
# Abnahmelauf der Greifdemo auf dem Simulationsrechner, als EIN Job (fuer die
# GPU-Warteschlange/den Lock; kein eigenes Locking hier drin):
#
#   1. scripts/run_greifen.sh alle   (demo, negativ, variation)
#   2. pytest tests/test_greifen.py mit RAEUMWERK_RUN_GPU_SMOKE=1: startet
#      Demo- und Negativlauf selbst und prueft deren JSON
#
#   scripts/job_greifen.sh
#
# Alles landet unter $RAEUMWERK_GREIFEN_RUNS/<Zeitstempel>/ (Standard
# $RAEUMWERK_HOME/runs/greifen); pytest-Ausgabe in pytest.log, Laeufe des
# Tests in pytest/.
set -uo pipefail

cd "$(dirname "$0")/.."
_runs_env=${RAEUMWERK_GREIFEN_RUNS:-}   # Umgebung geht vor config/local.env
if [ -f config/local.env ]; then set -a; . config/local.env; set +a; fi
RAEUMWERK_HOME=${RAEUMWERK_HOME:-$HOME/raeumwerk}
RUNS=${_runs_env:-${RAEUMWERK_GREIFEN_RUNS:-$RAEUMWERK_HOME/runs/greifen}}
export RAEUMWERK_GREIFEN_RUNS=$RUNS
export RAEUMWERK_STAMP=${RAEUMWERK_STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}
base="$RUNS/$RAEUMWERK_STAMP"
mkdir -p "$base"

scripts/run_greifen.sh alle
rc_lauf=$?

UVX=${UVX:-$(command -v uvx || echo "$HOME/.local/bin/uvx")}
export UV_CACHE_DIR=${UV_CACHE_DIR:-$RAEUMWERK_HOME/uvcache}
export UV_PYTHON_INSTALL_DIR=${UV_PYTHON_INSTALL_DIR:-$RAEUMWERK_HOME/uv-python}
RAEUMWERK_RUN_GPU_SMOKE=1 RAEUMWERK_ROOT="$RAEUMWERK_HOME" RAEUMWERK_GREIFEN_OUT="$base/pytest" \
  "$UVX" -p 3.10 --with numpy --with pyyaml --with pytest pytest -q -rs tests/test_greifen.py > "$base/pytest.log" 2>&1
rc_test=$?
tail -n 5 "$base/pytest.log"
echo "lauf_rc=$rc_lauf pytest_rc=$rc_test Ergebnis: $base"
[ "$rc_lauf" = 0 ] && [ "$rc_test" = 0 ]
