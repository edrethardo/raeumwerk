"""scripts/submit_gpu.sh und scripts/gpu_job.sh ohne echten GPU-Rechner.

Fakes (in tmp_path/fakes, vorn im PATH):

* ``ssh``        fuehrt den Befehl lokal aus; ``systemd-run`` startet das
                 Kommando in eigener Prozessgruppe mit ``timeout`` (wie
                 RuntimeMaxSec), ``systemctl --user stop`` beendet die ganze
                 Gruppe (wie die cgroup einer Unit), ``is-active`` prueft sie.
* ``gpu-lock.sh`` Lock mit acquire/release, Zustand in einer Datei.
* ``queue.sh``   externe Warteschlange: ``submit`` startet einen Hintergrund-
                 Runner, der den Fake-Lock nur waehrend des Jobs haelt.

Nichts davon fasst echte Locks, Warteschlangen oder fremde Prozesse an.
"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import textwrap
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
FRIST = 20.0  # grosszuegig: unter Last laufen die Fakes langsam

FAKE_SSH = textwrap.dedent("""\
    #!/usr/bin/env bash
    F="$(dirname "$0")"
    while [ $# -gt 0 ]; do case "$1" in -o) shift 2 ;; -*) shift ;; *) break ;; esac; done
    shift  # Rechnername
    echo "$*" >> "$F/ssh.log"
    systemd-run() {
      local unit= max=0
      while [ $# -gt 0 ]; do
        case "$1" in
          --unit=*) unit=${1#--unit=}; shift ;;
          -p) case "$2" in RuntimeMaxSec=*) max=${2#RuntimeMaxSec=} ;; esac; shift 2 ;;
          --*) shift ;;
          *) break ;;
        esac
      done
      echo "$unit max=$max" >> "$F/units.log"
      setsid timeout "$max" "$@" &
      local pid=$!
      echo "$pid" > "$F/unit-$unit.pid"
      wait "$pid"; local rc=$?
      rm -f "$F/unit-$unit.pid"
      return $rc
    }
    systemctl() {
      local last=${*: -1}; local unit=${last%.service}
      case " $* " in
        *" stop "*) echo "stop $unit" >> "$F/systemctl.log"
                    [ -f "$F/unit-$unit.pid" ] && kill -TERM -- "-$(cat "$F/unit-$unit.pid")" 2>/dev/null
                    return 0 ;;
        *" is-active "*) [ -f "$F/unit-$unit.pid" ]; return ;;
      esac
    }
    eval "$*"
    """)

FAKE_LOCK = textwrap.dedent("""\
    #!/usr/bin/env bash
    F="$(dirname "$0")"
    echo "$*" >> "$F/lock.log"
    cmd=$1; owner=$2
    case "$cmd" in
      acquire)
        [ "${FAKE_LOCK_BUSY:-0}" = 1 ] && exit 1
        if ( set -o noclobber; echo "$owner" > "$F/lock.held" ) 2>/dev/null; then exit 0; fi
        [ "$(cat "$F/lock.held")" = "$owner" ] && exit 0
        exit 1 ;;
      release)
        [ -f "$F/lock.held" ] && [ "$(cat "$F/lock.held")" = "$owner" ] && rm -f "$F/lock.held"
        exit 0 ;;
    esac
    exit 0
    """)

FAKE_QUEUE = textwrap.dedent("""\
    #!/usr/bin/env bash
    F="$(dirname "$0")"
    echo "$*" >> "$F/queue.log"
    case "$1" in
      submit)
        name=$2; shift 2
        while [ $# -gt 0 ] && [ "$1" != -- ]; do shift; done
        shift
        cmd="$*"
        ( until "$F/gpu-lock.sh" acquire fake-queue; do sleep 0.2; done
          echo "$name" > "$F/queue.running"
          "$F/ssh" box "$cmd" >> "$F/queue-job.log" 2>&1
          rm -f "$F/queue.running"
          "$F/gpu-lock.sh" release fake-queue ) < /dev/null > /dev/null 2>&1 &
        echo "queued $name" ;;
      cancel) echo "cancel $2" >> "$F/cancel.log" ;;
    esac
    """)

TESTJOB = textwrap.dedent("""\
    #!/usr/bin/env bash
    # testjob.sh <dir> sleep|rc N|weiter
    d=$1; echo $$ > "$d/job.pid"
    case "$2" in
      sleep) sleep 300 & echo $! > "$d/sleep.pid"; wait ;;
      rc) exit "$3" ;;
      weiter) n=$(cat "$d/zaehler" 2>/dev/null || echo 0); n=$((n + 1)); echo $n > "$d/zaehler"
              [ $n -lt 3 ] && exit 3; exit 0 ;;
    esac
    """)


@pytest.fixture
def umgebung(tmp_path):
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    for s in ("submit_gpu.sh", "gpu_job.sh"):
        shutil.copy(REPO / "scripts" / s, repo / "scripts")
    (repo / "scripts" / "testjob.sh").write_text(TESTJOB)
    fakes = tmp_path / "fakes"
    fakes.mkdir()
    for name, body in (("ssh", FAKE_SSH), ("gpu-lock.sh", FAKE_LOCK), ("queue.sh", FAKE_QUEUE)):
        (fakes / name).write_text(body)
        (fakes / name).chmod(0o755)
    daten = tmp_path / "daten"
    daten.mkdir()
    env = {
        "PATH": f"{fakes}:{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "GPU_HOST": "sim-box.example",
        "REMOTE_REPO": str(repo),
        "REMOTE_JOBS": str(tmp_path / "jobs"),
        "POLL_S": "1", "WAIT_MAX_S": "60", "GAP_S": "0",
    }
    return {"tmp": tmp_path, "repo": repo, "fakes": fakes, "daten": daten, "env": env}


def _env(u, weg, **extra):
    env = dict(u["env"])
    if weg == "lock":
        env["GPU_LOCK"] = str(u["fakes"] / "gpu-lock.sh")
    else:
        env["GPU_SUBMIT_CMD"] = f"{u['fakes'] / 'queue.sh'} submit"
        env["GPU_SUBMIT_ARGS"] = "--prio 20"
        env["GPU_CANCEL_CMD"] = f"{u['fakes'] / 'queue.sh'} cancel"
    env.update(extra)
    return env


def _log(u, name):
    p = u["fakes"] / name
    return p.read_text() if p.exists() else ""


def _submit(u, weg, *args, timeout=60, **extra):
    return subprocess.run(["bash", str(u["repo"] / "scripts" / "submit_gpu.sh"), *args],
                          env=_env(u, weg, **extra), capture_output=True, text=True, timeout=timeout)


def _lebt(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:  # Zombie zaehlt als tot
        return Path(f"/proc/{pid}/stat").read_text().split()[2] != "Z"
    except OSError:
        return False


def _prozesse_mit(marker: str):
    """PIDs (ausser diesem Prozess), deren Kommandozeile den Marker enthaelt."""
    out = []
    for p in Path("/proc").iterdir():
        if not p.name.isdigit() or int(p.name) == os.getpid():
            continue
        try:
            cmd = (p / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
        except OSError:
            continue
        if marker in cmd and _lebt(int(p.name)):
            out.append((int(p.name), cmd))
    return out


def _warte(bed, frist=FRIST):
    ende = time.monotonic() + frist
    while time.monotonic() < ende:
        if bed():
            return True
        time.sleep(0.1)
    return bed()


# --- Aufruf pruefen --------------------------------------------------------

@pytest.mark.parametrize("args, text", [
    (["Bad_Name", "--", "scripts/testjob.sh"], "ungueltiger Schritt"),
    (["-t", "31", "x", "--", "scripts/testjob.sh"], "1..30"),
    (["-t", "0", "x", "--", "scripts/testjob.sh"], "1..30"),
    (["x", "--", "/bin/sh"], "unter scripts/"),
    (["x", "--", "scripts/../../etc/passwd"], "kein .."),
    (["x", "--", "scripts/fehlt.sh"], "Skript fehlt"),
])
def test_submit_rejects_bad_calls(umgebung, args, text):
    proc = _submit(umgebung, "lock", *args)
    assert proc.returncode == 2, proc.stderr
    assert text in proc.stderr
    assert _log(umgebung, "lock.log") == "" and _log(umgebung, "ssh.log") == ""


def test_submit_needs_queue_or_lock(umgebung):
    proc = subprocess.run(["bash", str(umgebung["repo"] / "scripts" / "submit_gpu.sh"), "x", "--",
                           "scripts/testjob.sh"], env=umgebung["env"], capture_output=True, text=True, timeout=30)
    assert proc.returncode == 2 and "GPU_SUBMIT_CMD" in proc.stderr


# --- Lock-Weg (Fallback) ---------------------------------------------------

def test_lock_runs_job_with_runtime_limit_and_releases(umgebung):
    d = umgebung["daten"]
    proc = _submit(umgebung, "lock", "-t", "7", "probe", "--", "scripts/testjob.sh", str(d), "rc", "5")
    assert proc.returncode == 5, proc.stdout + proc.stderr
    lock = _log(umgebung, "lock.log")
    owner = lock.split()[1]
    assert owner.startswith("raeumwerk-probe-") and owner.endswith("-s1")
    assert f"release {owner}" in lock
    assert not (umgebung["fakes"] / "lock.held").exists()
    assert f"{owner} max=420" in _log(umgebung, "units.log")  # RuntimeMaxSec = 7 min
    jobs = umgebung["tmp"] / "jobs"
    assert (jobs / f"{owner}.rc").read_text().strip() == "5"
    assert "start " + owner in (jobs / f"{owner}.log").read_text()


def test_lock_wait_max_gives_up_without_touching_foreign_lock(umgebung):
    proc = _submit(umgebung, "lock", "probe", "--", "scripts/testjob.sh", str(umgebung["daten"]), "rc", "0",
                   WAIT_MAX_S="3", FAKE_LOCK_BUSY="1")
    assert proc.returncode == 4, proc.stderr
    lock = _log(umgebung, "lock.log")
    assert lock.count("acquire raeumwerk-probe-") >= 2
    assert "release" not in lock and _log(umgebung, "ssh.log") == ""


def test_lock_chunks_get_own_owner_names(umgebung):
    d = umgebung["daten"]
    proc = _submit(umgebung, "lock", "--weiter-rc", "3", "stueck", "--", "scripts/testjob.sh", str(d), "weiter")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    owners = [z.split()[1] for z in _log(umgebung, "lock.log").splitlines() if z.startswith("acquire")]
    assert [o[-3:] for o in owners] == ["-s1", "-s2", "-s3"]
    assert len(set(owners)) == 3
    assert _log(umgebung, "lock.log").count("release") == 3  # zwischen den Stuecken frei


def test_lock_sigterm_releases_lock_and_leaves_no_process(umgebung):
    """Fertig-Haken: abgebrochener Job (SIGTERM) gibt den Lock frei, kein Prozess bleibt."""
    d, fakes = umgebung["daten"], umgebung["fakes"]
    proc = subprocess.Popen(["bash", str(umgebung["repo"] / "scripts" / "submit_gpu.sh"), "-t", "5", "abbruch",
                             "--", "scripts/testjob.sh", str(d), "sleep"],
                            env=_env(umgebung, "lock"), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, start_new_session=True)
    try:
        assert _warte(lambda: (d / "sleep.pid").exists()), "Job ist nicht angelaufen"
        assert (fakes / "lock.held").exists()
        job_pid, sleep_pid = int((d / "job.pid").read_text()), int((d / "sleep.pid").read_text())
        assert _lebt(job_pid) and _lebt(sleep_pid)
        proc.send_signal(signal.SIGTERM)
        out, err = proc.communicate(timeout=FRIST)
        assert proc.returncode == 143, out + err
        assert not (fakes / "lock.held").exists(), "Lock nicht freigegeben"
        assert "release raeumwerk-abbruch-" in _log(umgebung, "lock.log")
        assert "stop raeumwerk-abbruch-" in _log(umgebung, "systemctl.log")
        assert _warte(lambda: not _lebt(job_pid) and not _lebt(sleep_pid)), "Jobprozess lebt noch"
        assert _warte(lambda: not _prozesse_mit(str(umgebung["tmp"]))), _prozesse_mit(str(umgebung["tmp"]))
        owner = _log(umgebung, "lock.log").split()[1]
        assert (umgebung["tmp"] / "jobs" / f"{owner}.rc").read_text().strip() == "143"
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)


# --- externe Warteschlange --------------------------------------------------

def test_queue_submits_and_waits_for_rc(umgebung):
    d = umgebung["daten"]
    proc = _submit(umgebung, "queue", "-t", "3", "probe", "--", "scripts/testjob.sh", str(d), "rc", "0")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    q = _log(umgebung, "queue.log")
    assert q.startswith("submit raeumwerk-probe-") and " --prio 20 -- systemd-run --user --collect --wait" in q
    assert "RuntimeMaxSec=180" in q and "scripts/gpu_job.sh" in q
    assert _log(umgebung, "lock.log").count("acquire fake-queue") >= 1
    assert "raeumwerk-probe" not in _log(umgebung, "lock.log")  # kein eigenes acquire
    assert _warte(lambda: not (umgebung["fakes"] / "lock.held").exists())


def test_queue_chunks_submitted_one_after_another(umgebung):
    d = umgebung["daten"]
    proc = _submit(umgebung, "queue", "--weiter-rc", "3", "stueck", "--", "scripts/testjob.sh", str(d), "weiter")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    submits = [z.split()[1] for z in _log(umgebung, "queue.log").splitlines() if z.startswith("submit")]
    assert [s[-3:] for s in submits] == ["-s1", "-s2", "-s3"]


def test_queue_nicht_warten_returns_after_submit(umgebung):
    d = umgebung["daten"]
    proc = _submit(umgebung, "queue", "--nicht-warten", "probe", "--", "scripts/testjob.sh", str(d), "rc", "0")
    assert proc.returncode == 0 and "eingereicht: raeumwerk-probe-" in proc.stdout
    assert _warte(lambda: not (umgebung["fakes"] / "lock.held").exists() and (d / "job.pid").exists())


def test_queue_sigterm_cancels_own_job_and_frees_lock(umgebung):
    d, fakes = umgebung["daten"], umgebung["fakes"]
    proc = subprocess.Popen(["bash", str(umgebung["repo"] / "scripts" / "submit_gpu.sh"), "abbruch", "--",
                             "scripts/testjob.sh", str(d), "sleep"],
                            env=_env(umgebung, "queue"), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, start_new_session=True)
    try:
        assert _warte(lambda: (d / "sleep.pid").exists()), "Job ist nicht angelaufen"
        assert (fakes / "lock.held").read_text().strip() == "fake-queue"
        job_pid, sleep_pid = int((d / "job.pid").read_text()), int((d / "sleep.pid").read_text())
        proc.send_signal(signal.SIGTERM)
        out, err = proc.communicate(timeout=FRIST)
        assert proc.returncode == 143, out + err
        owner = _log(umgebung, "queue.log").split()[1]
        assert _log(umgebung, "cancel.log").strip() == f"cancel {owner}"  # nur der eigene Eintrag
        assert f"stop {owner}" in _log(umgebung, "systemctl.log")
        assert _warte(lambda: not (fakes / "lock.held").exists()), "Warteschlange hat den Lock nicht freigegeben"
        assert _warte(lambda: not _lebt(job_pid) and not _lebt(sleep_pid))
        assert _warte(lambda: not _prozesse_mit(str(umgebung["tmp"]))), _prozesse_mit(str(umgebung["tmp"]))
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)


def test_runtime_limit_kills_whole_job(umgebung):
    """RuntimeMaxSec (hier per Fake-timeout) beendet den Job samt Kindprozessen."""
    d = umgebung["daten"]
    # -t 1 = 60 s ist fuer einen Test zu lang: Fake-systemd-run mit kurzer Frist ueber eine Kopie
    ssh = umgebung["fakes"] / "ssh"
    ssh.write_text(ssh.read_text().replace('setsid timeout "$max"', 'setsid timeout 2'))
    proc = _submit(umgebung, "lock", "-t", "1", "zeit", "--", "scripts/testjob.sh", str(d), "sleep")
    assert proc.returncode != 0
    assert not (umgebung["fakes"] / "lock.held").exists()
    assert _warte(lambda: not _lebt(int((d / "job.pid").read_text())) and not _lebt(int((d / "sleep.pid").read_text())))
