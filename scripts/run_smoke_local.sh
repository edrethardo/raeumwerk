#!/usr/bin/env bash
# Fuehrt den Smoke-Test auf DIESEM Rechner aus (aus dem Repo-Root), mit
# ss-ltnp-Mitschnitt alle 10 s. Rechnerneutral: Pfade aus config/local.env
# bzw. Umgebung. Auf einem geteilten GPU-Rechner nur unter dem GPU-Lock starten
# (scripts/remote_smoke.sh macht das).
#
#   scripts/run_smoke_local.sh <isaacsim|newton> [laeufe=3]
set -uo pipefail

cd "$(dirname "$0")/.."
if [ -f config/local.env ]; then set -a; . config/local.env; set +a; fi
export RAEUMWERK_HOME=${RAEUMWERK_HOME:-$HOME/raeumwerk}
export RAEUMWERK_RUNS=${RAEUMWERK_RUNS:-$(pwd)/ergebnis}
export OMNI_KIT_ACCEPT_EULA=YES
backend=${1:?isaacsim|newton}; runs=${2:-3}
case "$backend" in
  isaacsim) venv=isaacsim ;;
  newton) venv=isaaclab ;;
  *) echo "unbekanntes Backend $backend" >&2; exit 2 ;;
esac
PY="$RAEUMWERK_HOME/venvs/$venv/bin/python"
[ -x "$PY" ] || { echo "venv fehlt: scripts/install_backends.sh $venv" >&2; exit 3; }
mkdir -p "$RAEUMWERK_RUNS"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
sslog="$RAEUMWERK_RUNS/ss-$backend-$stamp.txt"
( while true; do echo "--- $(date -Is)"; ss -ltnp 2>/dev/null; sleep 10; done ) > "$sslog" 2>&1 &
sspid=$!
trap 'kill $sspid 2>/dev/null' EXIT
python3 scripts/smoke_runner.py --backend "$backend" --python "$PY" \
  --script "scripts/smoke_$backend.py" --runs "$runs" --out "$RAEUMWERK_RUNS"
rc=$?
echo "ss-Mitschnitt: $sslog"
exit $rc
