#!/usr/bin/env bash
# Backend-Test ReBeL + 7. Achse + Greifer in Newton (scripts/rebel_newton.py)
# auf DIESEM Rechner. Rechnerneutral: Pfade aus config/local.env bzw. Umgebung.
# Auf einem geteilten GPU-Rechner nur ueber die GPU-Warteschlange/den Lock
# starten (eigener systemd-run-Unit, kein eigenes Locking hier drin).
#
#   scripts/run_rebel_newton.sh [weitere Argumente fuer rebel_newton.py]
#
# Schreibt nach $RAEUMWERK_REBEL_RUNS/<Zeitstempel>/ (Standard
# $RAEUMWERK_HOME/runs/rebel): rebel.json, rebel.log, rebel.urdf, ss-ltnp.txt.
set -uo pipefail

cd "$(dirname "$0")/.."
if [ -f config/local.env ]; then set -a; . config/local.env; set +a; fi
RAEUMWERK_HOME=${RAEUMWERK_HOME:-$HOME/raeumwerk}
RUNS=${RAEUMWERK_REBEL_RUNS:-$RAEUMWERK_HOME/runs/rebel}
PY="$RAEUMWERK_HOME/venvs/isaaclab/bin/python"
[ -x "$PY" ] || { echo "venv fehlt: scripts/install_backends.sh isaaclab" >&2; exit 3; }
stamp=$(date -u +%Y%m%dT%H%M%SZ)
out="$RUNS/$stamp"
mkdir -p "$out"
( while true; do echo "--- $(date -Is)"; ss -ltnp 2>/dev/null; sleep 10; done ) > "$out/ss-ltnp.txt" 2>&1 &
sspid=$!
trap 'kill $sspid 2>/dev/null' EXIT
{
  echo "[$(date -Is)] start rebel_newton commit=$(git rev-parse --short HEAD 2>/dev/null || cat REVISION 2>/dev/null || echo ?)"
  nvidia-smi --query-gpu=name,memory.used,memory.total --format=csv,noheader 2>/dev/null || true
  free -m | head -2
} > "$out/rebel.log"
"$PY" scripts/rebel_newton.py --result "$out/rebel.json" --urdf-out "$out/rebel.urdf" "$@" >> "$out/rebel.log" 2>&1
rc=$?
echo "[$(date -Is)] ende rc=$rc" >> "$out/rebel.log"
grep -E '^(MOVE|REBEL_RESULT)' "$out/rebel.log" | tail -n 30
echo "Ergebnis: $out"
exit $rc
