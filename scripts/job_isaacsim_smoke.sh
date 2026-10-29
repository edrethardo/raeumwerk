#!/usr/bin/env bash
# Job fuer einen Rechner ohne ssh: Isaac Sim 6.2 installieren und den Smoke-Test 3x ausfuehren.
#
#   bash scripts/job_isaacsim_smoke.sh          # aus dem Repo-Root
#
# * Installiert idempotent nach $RAEUMWERK_HOME (Standard $HOME/raeumwerk,
#   nie ins Arbeitsverzeichnis). Kein sudo, kein ssh, keine Eingabe.
# * Schreibt nur nach ergebnis/ (bzw. $RAEUMWERK_RUNS): Smoke-JSONs + Logs,
#   umgebung.txt (check_env), listener-*.txt (ss -ltn), zusammenfassung.json.
# * EULA: setzt OMNI_KIT_ACCEPT_EULA=YES (offizieller nicht-interaktiver Weg,
#   siehe docs/umgebung.md). Wer den Auftrag schickt, nimmt damit die
#   NVIDIA Omniverse License Agreement an.
# * Exit 0 nur bei 3/3 ok. Gesamtfrist JOB_TIMEOUT_S (Standard 4 h).
set -euo pipefail

cd "$(dirname "$0")/.."
REPO=$(pwd)
if [ -f config/local.env ]; then set -a; . config/local.env; set +a; fi
export RAEUMWERK_HOME=${RAEUMWERK_HOME:-$HOME/raeumwerk}
export RAEUMWERK_RUNS=${RAEUMWERK_RUNS:-$REPO/ergebnis}
export OMNI_KIT_ACCEPT_EULA=YES
RUNS=${SMOKE_RUNS:-3}
JOB_TIMEOUT_S=${JOB_TIMEOUT_S:-14400}
INSTALL_TIMEOUT_S=${INSTALL_TIMEOUT_S:-7200}
RUN_TIMEOUT_S=${RUN_TIMEOUT_S:-1500}
START=$(date +%s)
START_UTC=$(date -u +%Y%m%dT%H%M%SZ)

case "$RAEUMWERK_HOME" in "$REPO"|"$REPO"/*)
  echo "RAEUMWERK_HOME darf nicht im Arbeitsverzeichnis liegen" >&2; exit 2 ;; esac
mkdir -p "$RAEUMWERK_RUNS"
log() { echo "[$(date -Is)] $*" | tee -a "$RAEUMWERK_RUNS/job.log"; }
left() { echo $(( JOB_TIMEOUT_S - ($(date +%s) - START) )); }

log "Job isaacsim-smoke: Start (Frist ${JOB_TIMEOUT_S}s, $RUNS Laeufe)"
RAEUMWERK_ROOT=$RAEUMWERK_HOME bash scripts/check_env.sh > "$RAEUMWERK_RUNS/umgebung.txt" 2>&1 || true
ss -ltn > "$RAEUMWERK_RUNS/listener-vorher.txt" 2>&1 || true

log "Installation (Frist ${INSTALL_TIMEOUT_S}s)"
if ! timeout "$INSTALL_TIMEOUT_S" bash -c 'nice -n 10 bash scripts/fetch_wheels.sh && nice -n 10 bash scripts/install_backends.sh isaacsim' \
     >> "$RAEUMWERK_RUNS/install-isaacsim.log" 2>&1; then
  log "FEHLER: Installation fehlgeschlagen, siehe install-isaacsim.log"; exit 10
fi
PY="$RAEUMWERK_HOME/venvs/isaacsim/bin/python"
log "installiert: $("$PY" -c "import importlib.metadata as m; print('isaacsim', m.version('isaacsim'))")"

# ss waehrend der Laeufe alle 20 s mitschreiben (Beleg: kein Listener ausser localhost)
( while sleep 20; do echo "--- $(date -Is)"; ss -ltn; done ) > "$RAEUMWERK_RUNS/listener-waehrend.txt" 2>&1 &
SSPID=$!
trap 'kill $SSPID 2>/dev/null || true' EXIT

budget=$(left)
[ "$budget" -gt 60 ] || { log "FEHLER: Frist nach Installation aufgebraucht"; exit 11; }
log "Smoke: $RUNS Laeufe (Restfrist ${budget}s)"
set +e
timeout "$budget" python3 scripts/smoke_runner.py --backend isaacsim --python "$PY" \
  --script scripts/smoke_isaacsim.py --runs "$RUNS" --timeout "$RUN_TIMEOUT_S" \
  --out "$RAEUMWERK_RUNS" 2>&1 | tee -a "$RAEUMWERK_RUNS/job.log"
rc=${PIPESTATUS[0]}
set -e
python3 - "$RAEUMWERK_RUNS" "$START_UTC" <<'EOF' | tee "$RAEUMWERK_RUNS/zusammenfassung.json"
import json, sys, pathlib
d = pathlib.Path(sys.argv[1])
runs = [json.loads(p.read_text()) for p in sorted(d.glob("isaacsim-*.json"))]
runs = [r for r in runs if r.get("started_utc", "") >= sys.argv[2]]  # nur dieser Job
keys = ("ok", "reason", "runtime_s", "ram_peak_mib", "vram_peak_mib", "root_free_gb_after", "started_utc")
print(json.dumps({"ok": sum(r["ok"] for r in runs), "runs": len(runs),
                  "details": [{k: r.get(k) for k in keys} for r in runs]}, indent=2))
EOF
log "Ende: Exit $rc, Dauer $(( $(date +%s) - START ))s"
exit "$rc"
