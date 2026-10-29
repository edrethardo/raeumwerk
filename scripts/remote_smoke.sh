#!/usr/bin/env bash
# Startet den Smoke-Test auf einem geteilten GPU-Rechner unter dem GPU-Lock.
# Laeuft auf dem steuernden Rechner (per ssh), nicht auf dem GPU-Rechner.
#
#   scripts/remote_smoke.sh <isaacsim|newton> [laeufe=3] [lock-minuten=60]
#
# Aus config/local.env (oder der Umgebung, wenn es die Datei nicht gibt):
# GPU_HOST, GPU_LOCK (Pfad zu gpu-lock.sh), REMOTE_REPO (Repo-Kopie auf dem
# GPU-Rechner; dort liegt eine eigene config/local.env mit
# RAEUMWERK_HOME/RAEUMWERK_RUNS/RAEUMWERK_KIT_HOME).
#
# Ablauf: acquire ohne --wait, alle POLL_S Sekunden neu versuchen (fremde Locks
# werden nie angefasst) -> ssh: scripts/run_smoke_local.sh -> release per trap.
# Der Lock wird nur fuer den GPU-Teil gehalten.
#
# Variablen: POLL_S (10), WAIT_MAX_S (14400 = 4 h; danach Exit 4),
# SSH_TIMEOUT_S (7200 = 2 h; danach Exit 124 durch timeout).
# Exit 2: ungueltiges Backend (geprueft, bevor irgendetwas anderes passiert).
set -uo pipefail

backend=${1:-}
case "$backend" in
  isaacsim|newton) ;;
  *) echo "ungueltiges Backend: '$backend' (isaacsim|newton)" >&2; exit 2 ;;
esac
runs=${2:-3}; minutes=${3:-60}

cd "$(dirname "$0")/.."
if [ -f config/local.env ]; then set -a; . config/local.env; set +a; fi
: "${GPU_HOST:?GPU_HOST in config/local.env}" "${GPU_LOCK:?GPU_LOCK in config/local.env}" "${REMOTE_REPO:?REMOTE_REPO in config/local.env}"
POLL_S=${POLL_S:-10}; WAIT_MAX_S=${WAIT_MAX_S:-14400}; SSH_TIMEOUT_S=${SSH_TIMEOUT_S:-7200}
GPU_LOCK=${GPU_LOCK/#\~/$HOME}
lock_name="raeumwerk-smoke-$backend"

echo "[$(date -Is)] warte auf GPU-Lock als $lock_name"
start=$(date +%s)
until "$GPU_LOCK" acquire "$lock_name" -m "Raeumwerk Smoke $backend x$runs" -t "$minutes" >/dev/null 2>&1; do
  waited=$(( $(date +%s) - start ))
  if [ "$waited" -ge "$WAIT_MAX_S" ]; then
    echo "[$(date -Is)] Lock nach ${waited}s nicht erhalten (WAIT_MAX_S=$WAIT_MAX_S)" >&2
    exit 4
  fi
  sleep "$POLL_S"
done
trap '"$GPU_LOCK" release "$lock_name"; echo "[$(date -Is)] Lock freigegeben"' EXIT
trap 'exit 130' INT TERM
echo "[$(date -Is)] Lock erhalten"
"$GPU_LOCK" status | head -12

timeout "$SSH_TIMEOUT_S" ssh -o BatchMode=yes "$GPU_HOST" "cd '$REMOTE_REPO' && bash scripts/run_smoke_local.sh '$backend' '$runs'"
rc=$?
echo "[$(date -Is)] Smoke $backend Exit $rc"
exit $rc
