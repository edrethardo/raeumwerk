#!/usr/bin/env bash
# Laeuft AUF dem GPU-Rechner, gestartet von scripts/submit_gpu.sh als
# systemd-run-Unit (Laufzeitgrenze RuntimeMaxSec, beim Stoppen/Ueberschreiten
# beendet systemd die ganze Unit, also jeden Kindprozess).
#
#   scripts/gpu_job.sh <owner> <jobs-ordner> <skript relativ zum Repo> [argumente ...]
#
# Schreibt <jobs-ordner>/<owner>.start (Startzeit), <owner>.log (Ausgabe) und
# zuletzt <owner>.rc (Exit-Code). SIGTERM (Stoppen, Zeitgrenze) wird an das
# Skript weitergereicht; dann steht 143 in <owner>.rc.
# Kein Locking hier drin: Lock bzw. Warteschlange haelt der Aufrufer.
set -uo pipefail

owner=${1:?owner}; jobs=${2:?jobs-ordner}; skript=${3:?skript}; shift 3
cd "$(dirname "$0")/.."
case "$skript" in
  scripts/*) ;;
  *) echo "Skript muss unter scripts/ liegen: $skript" >&2; exit 2 ;;
esac
case "$skript" in *..*) echo "kein .. im Skriptpfad" >&2; exit 2 ;; esac
[ -f "$skript" ] || { echo "Skript fehlt: $skript" >&2; exit 2; }

mkdir -p "$jobs"
log="$jobs/$owner.log"
date -Is > "$jobs/$owner.start"
{
  echo "[$(date -Is)] start $owner: $skript $*"
  echo "revision $(git rev-parse --short HEAD 2>/dev/null || cat REVISION 2>/dev/null || echo ?)"
} >> "$log"

kind=
abbruch() {
  echo "[$(date -Is)] SIGTERM -> $skript" >> "$log"
  [ -n "$kind" ] && kill -TERM "$kind" 2>/dev/null
  wait "$kind" 2>/dev/null
  echo 143 > "$jobs/$owner.rc.tmp" && mv "$jobs/$owner.rc.tmp" "$jobs/$owner.rc"
  exit 143
}
trap abbruch TERM INT

bash "$skript" "$@" >> "$log" 2>&1 &
kind=$!
wait "$kind"
rc=$?
echo "[$(date -Is)] ende $owner rc=$rc" >> "$log"
echo "$rc" > "$jobs/$owner.rc.tmp" && mv "$jobs/$owner.rc.tmp" "$jobs/$owner.rc"
exit "$rc"
