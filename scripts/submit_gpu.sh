#!/usr/bin/env bash
# Reicht einen Job fuer den geteilten GPU-Rechner ein und wartet auf sein Ende.
# Laeuft auf dem steuernden Rechner (ssh zum GPU-Rechner), nie auf dem GPU-Rechner.
#
#   scripts/submit_gpu.sh [-t MIN] [--weiter-rc N] [--max-stuecke N] [--sync] [--nicht-warten] \
#       <schritt> -- <skript relativ zum Repo> [argumente ...]
#
# Beispiel (Experiment in Stuecken von hoechstens 10 min, raeumwerk run endet
# mit Exit 3, solange Versuche offen sind):
#   scripts/submit_gpu.sh -t 10 --weiter-rc 3 --sync beispiel -- \
#       scripts/raeumwerk run experimente/beispiel.yaml --run-dir beispiel-1 --max-minuten 8
#
# Jeder Job (jedes Stueck) bekommt einen eigenen Owner-/Unit-Namen
# raeumwerk-<schritt>-<UTC-Zeit>-s<n>. Auf dem GPU-Rechner laeuft er als
#   systemd-run --user --collect --wait --unit=<owner> -p RuntimeMaxSec=<t*60> \
#       bash <REMOTE_REPO>/scripts/gpu_job.sh <owner> <REMOTE_JOBS> <skript> <argumente>
# Die Laufzeitgrenze beendet die ganze Unit (alle Kindprozesse); gpu_job.sh
# schreibt Log und Exit-Code nach <REMOTE_JOBS>/<owner>.{log,rc}.
#
# Zwei Wege, gewaehlt ueber config/local.env (oder Umgebung):
#  1. GPU_SUBMIT_CMD gesetzt: externe GPU-Warteschlange. Aufruf
#       $GPU_SUBMIT_CMD <owner> $GPU_SUBMIT_ARGS -- '<befehl auf dem GPU-Rechner>'
#     Die Warteschlange haelt den GPU-Lock nur waehrend des Jobs. Danach wartet
#     dieses Skript per ssh auf <owner>.rc. Abbruch (SIGTERM/SIGINT): eigenen
#     Eintrag per $GPU_CANCEL_CMD <owner> entfernen (falls gesetzt) und die
#     eigene Unit stoppen; fremde Jobs werden nie angefasst.
#  2. sonst GPU_LOCK (Lock-Skript mit acquire/release): acquire ohne --wait,
#     alle POLL_S Sekunden neu (hoechstens WAIT_MAX_S), dann ssh mit dem Befehl
#     oben, release per trap. Abbruch: eigene Unit stoppen, ssh beenden, Lock frei.
#
# Stuecke: Mit --weiter-rc N wird nach einem Job mit Exit N das naechste Stueck
# eingereicht (hoechstens --max-stuecke). Zwischen zwei Stuecken ist der Lock
# frei (Lock-Weg: GAP_S Sekunden Pause; Warteschlange: das naechste Stueck
# wird erst nach dem Ende des vorigen eingereicht, wartende fremde Jobs kommen
# zuerst dran). -t ist hoechstens 30 (Minuten).
#
# Variablen: GPU_HOST, REMOTE_REPO (Repo-Kopie auf dem GPU-Rechner),
# REMOTE_JOBS (Standard: <REMOTE_REPO>/../jobs), GPU_SUBMIT_CMD, GPU_SUBMIT_ARGS,
# GPU_CANCEL_CMD, GPU_LOCK, POLL_S (10), WAIT_MAX_S (14400), GAP_S (60).
#
# Exit: Exit-Code des letzten Jobs; 2 Aufruf/Konfiguration; 4 Wartefrist
# abgelaufen; 124 Job ohne Exit-Code beendet (Zeitgrenze/abgeschossen);
# 143 abgebrochen.
set -uo pipefail

minuten=30; weiter_rc=; max_stuecke=20; sync=0; warten=1
need_arg() { [ $# -ge 2 ] || { echo "Option $1 braucht einen Wert" >&2; exit 2; }; }
while [ $# -gt 0 ]; do
  case "$1" in
    -t) need_arg "$@"; minuten=$2; shift 2 ;;
    --weiter-rc) need_arg "$@"; weiter_rc=$2; shift 2 ;;
    --max-stuecke) need_arg "$@"; max_stuecke=$2; shift 2 ;;
    --sync) sync=1; shift ;;
    --nicht-warten) warten=0; shift ;;
    -h|--help) sed -n '2,45p' "$0"; exit 0 ;;
    -*) echo "unbekannte Option: $1" >&2; exit 2 ;;
    *) break ;;
  esac
done
schritt=${1:-}; shift || true
[ "${1:-}" = -- ] && shift
skript=${1:-}; shift || true

fehler() { echo "submit_gpu: $*" >&2; exit 2; }
[[ $schritt =~ ^[a-z0-9][a-z0-9-]{0,39}$ ]] || fehler "ungueltiger Schritt '$schritt' (a-z 0-9 -, hoechstens 40 Zeichen)"
[[ $minuten =~ ^[0-9]+$ ]] && [ "$minuten" -ge 1 ] && [ "$minuten" -le 30 ] || fehler "-t: 1..30 Minuten (Stuecke hoechstens 30 min)"
[ -z "$weiter_rc" ] || [[ $weiter_rc =~ ^[0-9]+$ ]] || fehler "--weiter-rc: Zahl"
[[ $max_stuecke =~ ^[0-9]+$ ]] && [ "$max_stuecke" -ge 1 ] || fehler "--max-stuecke: Zahl >= 1"
case "$skript" in scripts/*) ;; *) fehler "Skript muss unter scripts/ liegen: '$skript'" ;; esac
case "$skript" in *..*) fehler "kein .. im Skriptpfad" ;; esac

cd "$(dirname "$0")/.."
[ -f "$skript" ] || fehler "Skript fehlt: $skript"
if [ -f config/local.env ]; then set -a; . config/local.env; set +a; fi
: "${GPU_HOST:?GPU_HOST in config/local.env}" "${REMOTE_REPO:?REMOTE_REPO in config/local.env}"
REMOTE_JOBS=${REMOTE_JOBS:-$(dirname "$REMOTE_REPO")/jobs}
POLL_S=${POLL_S:-10}; WAIT_MAX_S=${WAIT_MAX_S:-14400}; GAP_S=${GAP_S:-60}
GPU_LOCK=${GPU_LOCK:-}; GPU_LOCK=${GPU_LOCK/#\~/$HOME}
if [ -n "${GPU_SUBMIT_CMD:-}" ]; then weg=warteschlange
elif [ -n "$GPU_LOCK" ]; then weg=lock
else fehler "weder GPU_SUBMIT_CMD noch GPU_LOCK gesetzt (config/local.env)"; fi
[ "$warten" = 1 ] || [ "$weg" = warteschlange ] || fehler "--nicht-warten nur mit der Warteschlange"

SSH=(ssh -n -o BatchMode=yes -o ServerAliveInterval=60 "$GPU_HOST")
ts() { date -Is; }
sp=
pause() { sleep "$1" & sp=$!; wait "$sp"; sp=; }   # unterbrechbar durch Traps

if [ "$sync" = 1 ]; then
  rev="$(git rev-parse HEAD)"; git diff --quiet HEAD -- || rev="$rev dirty"
  "${SSH[@]}" "mkdir -p $(printf %q "$REMOTE_REPO")" || exit 1
  git ls-files -z | rsync -a --from0 --files-from=- ./ "$GPU_HOST:$REMOTE_REPO/" || exit 1
  "${SSH[@]}" "printf '%s\n' $(printf %q "$rev") > $(printf %q "$REMOTE_REPO/REVISION")" || exit 1
  echo "[$(ts)] Stand $rev nach $GPU_HOST:REMOTE_REPO kopiert"
fi

stamp=$(date -u +%Y%m%dT%H%M%SZ)
owner=; ssh_pid=; lock_owner=
quote_args() { local out=; for a in "$@"; do out+=" $(printf %q "$a")"; done; printf '%s' "$out"; }
args_q=$(quote_args "$@")

remote_befehl() {  # $1 = owner
  printf 'systemd-run --user --collect --wait --quiet --unit=%s -p RuntimeMaxSec=%s bash %q %s %q %q%s' \
    "$1" "$((minuten * 60))" "$REMOTE_REPO/scripts/gpu_job.sh" "$1" "$REMOTE_JOBS" "$skript" "$args_q"
}

eigene_unit_stoppen() {
  [ -n "$owner" ] || return 0
  "${SSH[@]}" "systemctl --user stop $(printf %q "$owner.service") 2>/dev/null; true" >/dev/null 2>&1 || true
}

aufraeumen() {
  trap '' TERM INT
  [ -n "$sp" ] && kill "$sp" 2>/dev/null
  echo "[$(ts)] Abbruch: raeume eigenen Job $owner auf" >&2
  if [ "$weg" = warteschlange ] && [ -n "${GPU_CANCEL_CMD:-}" ] && [ -n "$owner" ]; then
    $GPU_CANCEL_CMD "$owner" >/dev/null 2>&1 || true
  fi
  eigene_unit_stoppen
  if [ -n "$ssh_pid" ]; then kill -TERM "$ssh_pid" 2>/dev/null; wait "$ssh_pid" 2>/dev/null; fi
  exit 143   # EXIT-Trap gibt den Lock frei
}
lock_frei() {
  if [ -n "$lock_owner" ]; then
    "$GPU_LOCK" release "$lock_owner" >/dev/null 2>&1 || true
    echo "[$(ts)] Lock $lock_owner freigegeben"
    lock_owner=
  fi
}
trap lock_frei EXIT
trap aufraeumen TERM INT

rc_lesen() {  # gibt rc aus oder leer; "weg" wenn gestartet, beendet, ohne rc
  "${SSH[@]}" "j=$(printf %q "$REMOTE_JOBS/$1"); if [ -f \"\$j.rc\" ]; then cat \"\$j.rc\"; elif [ -f \"\$j.start\" ] && ! systemctl --user is-active --quiet $(printf %q "$1.service"); then echo weg; fi" 2>/dev/null
}

ein_job_warteschlange() {
  local cmd; cmd=$(remote_befehl "$owner")
  # shellcheck disable=SC2086  # GPU_SUBMIT_CMD/ARGS sind bewusst Wortlisten
  $GPU_SUBMIT_CMD "$owner" ${GPU_SUBMIT_ARGS:-} -- "$cmd" || { echo "Einreichen fehlgeschlagen" >&2; return 1; }
  echo "[$(ts)] eingereicht: $owner"
  [ "$warten" = 1 ] || return 0
  local start; start=$(date +%s); local r= weg_seit=
  while :; do
    r=$(rc_lesen "$owner")
    if [[ $r =~ ^[0-9]+$ ]]; then return "$r"; fi
    if [ "$r" = weg ]; then
      # Unit beendet, aber (noch) kein rc: kurz nachsehen, dann als abgeschossen werten
      [ -n "$weg_seit" ] || weg_seit=$(date +%s)
      [ $(( $(date +%s) - weg_seit )) -ge $(( POLL_S * 2 )) ] && { echo "[$(ts)] $owner ohne Exit-Code beendet" >&2; return 124; }
    fi
    if [ $(( $(date +%s) - start )) -ge "$WAIT_MAX_S" ]; then
      echo "[$(ts)] $owner nach ${WAIT_MAX_S}s nicht fertig (WAIT_MAX_S); Eintrag wird zurueckgezogen" >&2
      [ -n "${GPU_CANCEL_CMD:-}" ] && $GPU_CANCEL_CMD "$owner" >/dev/null 2>&1
      eigene_unit_stoppen
      return 4
    fi
    pause "$POLL_S"
  done
}

ein_job_lock() {
  local start; start=$(date +%s)
  echo "[$(ts)] warte auf GPU-Lock als $owner"
  until "$GPU_LOCK" acquire "$owner" -m "Raeumwerk $schritt" -t "$minuten" >/dev/null 2>&1; do
    if [ $(( $(date +%s) - start )) -ge "$WAIT_MAX_S" ]; then
      echo "[$(ts)] Lock nach $(( $(date +%s) - start ))s nicht erhalten (WAIT_MAX_S=$WAIT_MAX_S)" >&2
      return 4
    fi
    pause "$POLL_S"
  done
  lock_owner=$owner
  echo "[$(ts)] Lock erhalten"
  "${SSH[@]}" "$(remote_befehl "$owner")" &
  ssh_pid=$!
  wait "$ssh_pid"; local r=$?
  ssh_pid=
  lock_frei
  return "$r"
}

rc=0
for (( n=1; n<=max_stuecke; n++ )); do
  owner="raeumwerk-$schritt-$stamp-s$n"
  if [ "$weg" = warteschlange ]; then ein_job_warteschlange; else ein_job_lock; fi
  rc=$?
  echo "[$(ts)] Stueck $n ($owner) Exit $rc"
  [ "$warten" = 1 ] || break
  if [ -n "$weiter_rc" ] && [ "$rc" = "$weiter_rc" ] && [ "$n" -lt "$max_stuecke" ]; then
    [ "$weg" = lock ] && pause "$GAP_S"
    continue
  fi
  break
done
owner=
exit "$rc"
