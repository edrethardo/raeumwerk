"""Smoke-Tests fuer die Simulationsbackends.

* Ohne Backend laufen nur die Logiktests des Runners (fallender Wuerfel wird
  mit einem Fake-Backend simuliert), die echten Backendtests werden sauber
  uebersprungen.
* Die echten Backendtests laufen nur, wenn ``RAEUMWERK_RUN_GPU_SMOKE=1`` gesetzt
  ist, ``RAEUMWERK_ROOT`` auf das Datenlaufwerk zeigt, das venv des Backends
  existiert und ``nvidia-smi`` da ist. Gestartet werden sie nur unter dem
  GPU-Lock (siehe docs/umgebung.md), nie nebenbei.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

import smoke_runner  # noqa: E402

BACKENDS = {
    # Name -> (venv-Unterordner, Skript)
    "isaacsim": ("isaacsim", REPO / "scripts" / "smoke_isaacsim.py"),
    "newton": ("isaaclab", REPO / "scripts" / "smoke_newton.py"),
}


# --- Logik des Runners (immer) ---------------------------------------------

def _res(z, steps=300, **kw):
    return {"final_height": z, "steps": steps, **kw}


@pytest.mark.parametrize(
    "result, ok",
    [
        (_res(0.05), True),
        (_res(0.065), True),
        (_res(0.08), False),      # liegt nicht auf dem Boden
        (_res(1.0), False),       # ist nicht gefallen
        (_res(-0.5), False),      # durch den Boden gefallen
        (_res(float("nan")), False),
        (_res(0.05, steps=10), False),
        (_res(0.05, error="boom"), False),
        (None, False),
    ],
)
def test_evaluate(result, ok):
    assert smoke_runner.evaluate(result)[0] is ok


def test_mask_hides_interface_addresses():
    assert smoke_runner.mask("0.0.0.0:22") == "*:22"
    assert smoke_runner.mask("[::]:22") == "*:22"
    assert smoke_runner.mask("10.1.2.3:8211") == "<iface>:8211"
    assert smoke_runner.non_local({"127.0.0.1:8211", "[::1]:1", "0.0.0.0:22"}) == ["0.0.0.0:22"]


FAKE_BACKEND = textwrap.dedent(
    """
    import argparse, json, os, time
    ap = argparse.ArgumentParser(); ap.add_argument("--result"); a = ap.parse_args()
    sc = json.loads(os.environ["RAEUMWERK_SCENARIO"])
    buf = bytearray(32 * 2**20)  # 32 MiB, damit die RAM-Spitze messbar ist
    time.sleep(1.2)
    json.dump({"steps": sc["steps"], "final_height": float(os.environ.get("FAKE_Z", "0.05"))},
              open(a.result, "w"))
    """
)


@pytest.mark.parametrize("z, ok", [("0.05", True), ("0.9", False)])
def test_runner_with_fake_backend(tmp_path, monkeypatch, z, ok):
    script = tmp_path / "fake_backend.py"
    script.write_text(FAKE_BACKEND)
    monkeypatch.setenv("FAKE_Z", z)
    rep = smoke_runner.run_smoke("fake", sys.executable, str(script), tmp_path / "out", timeout=60)
    assert rep["ok"] is ok, rep["reason"]
    assert rep["runtime_s"] >= 1.0
    assert rep["ram_peak_mib"] >= 32
    saved = json.loads((tmp_path / "out" / f"fake-{rep['started_utc']}.json").read_text())
    assert saved["ok"] is ok
    assert set(saved) >= {"ok", "runtime_s", "ram_peak_mib", "vram_peak_mib"}


def test_sampler_does_not_shadow_thread_internals():
    """Regression: ein Attribut _stop ueberschrieb Thread._stop; join() stuerzte unter Python 3.10 ab."""
    import threading

    sampler = smoke_runner.Sampler(os.getpid(), interval=0.05)
    own = set(vars(sampler)) - set(vars(threading.Thread()))
    shadowed = own & set(dir(threading.Thread))
    assert not shadowed
    sampler.start()
    sampler.stop()
    sampler.join(timeout=5)
    assert not sampler.is_alive()


def test_runner_timeout(tmp_path):
    script = tmp_path / "hang.py"
    script.write_text("import time\ntime.sleep(60)\n")
    rep = smoke_runner.run_smoke("hang", sys.executable, str(script), tmp_path / "out", timeout=2)
    assert rep["ok"] is False and rep["timed_out"] is True


# --- scripts/remote_smoke.sh (ohne echten ssh, ohne echten Lock) -------------

FAKE_LOCK = textwrap.dedent(
    """\
    #!/usr/bin/env bash
    echo "$@" >> "$(dirname "$0")/lock.log"
    [ "$1" = acquire ] && [ "${FAKE_LOCK_FREE:-0}" != 1 ] && exit 1
    exit 0
    """
)
FAKE_SSH = '#!/usr/bin/env bash\necho "$@" >> "$(dirname "$0")/ssh.log"\nexit 0\n'


def _remote_smoke(tmp_path, *args, lock_free=False):
    """Kopie des Skripts ohne config/local.env; Werte kommen aus der Umgebung."""
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    shutil.copy(REPO / "scripts" / "remote_smoke.sh", repo / "scripts")
    fakes = tmp_path / "fakes"
    fakes.mkdir()
    for name, body in (("gpu-lock.sh", FAKE_LOCK), ("ssh", FAKE_SSH)):
        (fakes / name).write_text(body)
        (fakes / name).chmod(0o755)
    env = {
        "PATH": f"{fakes}:{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "GPU_HOST": "sim-box.example",
        "GPU_LOCK": str(fakes / "gpu-lock.sh"),
        "REMOTE_REPO": "/srv/raeumwerk/repo",
        "WAIT_MAX_S": "1",
        "POLL_S": "1",
        "FAKE_LOCK_FREE": "1" if lock_free else "0",
    }
    proc = subprocess.run(["bash", str(repo / "scripts" / "remote_smoke.sh"), *args],
                          env=env, capture_output=True, text=True, timeout=30)
    log = lambda n: (fakes / n).read_text() if (fakes / n).exists() else ""  # noqa: E731
    return proc, log("lock.log"), log("ssh.log")


def test_remote_smoke_gives_up_after_wait_max(tmp_path):
    proc, lock_log, ssh_log = _remote_smoke(tmp_path, "newton", "1", "5")
    assert proc.returncode == 4, proc.stderr
    assert "WAIT_MAX_S=1" in proc.stderr
    assert lock_log.count("acquire raeumwerk-smoke-newton") >= 2  # hat gepollt
    assert "release" not in lock_log  # fremden Lock nie freigeben
    assert ssh_log == ""


@pytest.mark.parametrize("backend", ["bogus", "", "newton;id"])
def test_remote_smoke_rejects_invalid_backend(tmp_path, backend):
    proc, lock_log, ssh_log = _remote_smoke(tmp_path, backend)
    assert proc.returncode == 2, proc.stderr
    assert "ungueltiges Backend" in proc.stderr
    assert lock_log == "" and ssh_log == ""


def test_remote_smoke_runs_ssh_and_releases_lock(tmp_path):
    proc, lock_log, ssh_log = _remote_smoke(tmp_path, "isaacsim", "2", lock_free=True)
    assert proc.returncode == 0, proc.stderr
    assert "run_smoke_local.sh 'isaacsim' '2'" in ssh_log
    assert "release raeumwerk-smoke-isaacsim" in lock_log


# --- echte Backends (nur mit GPU, venv und ausdruecklicher Freigabe) --------

@pytest.mark.parametrize("backend", sorted(BACKENDS))
def test_smoke_backend(backend, tmp_path):
    if os.environ.get("RAEUMWERK_RUN_GPU_SMOKE") != "1":
        pytest.skip("RAEUMWERK_RUN_GPU_SMOKE=1 nicht gesetzt (GPU-Lauf nur unter gpu-lock)")
    root = os.environ.get("RAEUMWERK_ROOT")
    if not root:
        pytest.skip("RAEUMWERK_ROOT nicht gesetzt")
    venv, script = BACKENDS[backend]
    python = Path(root) / "venvs" / venv / "bin" / "python"
    if not python.exists():
        pytest.skip(f"Backend {backend} nicht installiert ({venv}-venv fehlt)")
    if not shutil.which("nvidia-smi"):
        pytest.skip("keine NVIDIA-GPU")
    out = Path(os.environ.get("RAEUMWERK_SMOKE_OUT", str(Path(root) / "runs" / "smoke")))
    rep = smoke_runner.run_smoke(backend, str(python), str(script), out, timeout=1500)
    assert rep["ok"], rep["reason"]
