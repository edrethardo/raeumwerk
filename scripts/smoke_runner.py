#!/usr/bin/env python3
"""Gemeinsamer Smoke-Runner fuer Raeumwerk-Simulationsbackends.

Startet ein Backend-Skript (z. B. ``smoke_isaacsim.py``) als Kindprozess mit dem
Python des jeweiligen venv, misst von aussen

* Laufzeit (Wanduhr, inkl. Start/Shutdown),
* RAM-Spitze (Summe RSS des gesamten Prozessbaums, aus /proc),
* VRAM-Spitze (nur die PIDs des eigenen Prozessbaums, aus nvidia-smi;
  die GPU wird mit anderen Jobs geteilt, deshalb nicht ``memory.used``),
* TCP-Listener ausserhalb von localhost, die waehrend des Laufs neu
  aufgetaucht sind (``ss -ltnH``; vorher vorhandene Listener zaehlen nicht),

und schreibt ein JSON mit ``ok``. Das Backend-Skript schreibt sein Physik-
Ergebnis (Endhoehe des Wuerfels) als JSON nach ``--result``.

Nur Standardbibliothek, laeuft mit Python >= 3.8 (System-Python des GPU-Rechners).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

# Physik-Szenario, gemeinsam fuer alle Backends (Einheiten: m, s)
SCENARIO = {
    "steps": 300,
    "dt": 1.0 / 60.0,
    "cube_size": 0.1,       # Kantenlaenge
    "start_height": 1.0,    # Mittelpunkt ueber Boden
    "tolerance": 0.02,      # erlaubte Abweichung der Endhoehe von cube_size/2
}

LOCAL_ADDR = re.compile(r"^(127\.\d+\.\d+\.\d+|\[::1\]|::1|\[::ffff:127\.[0-9.]+\])(:|$)")


def evaluate(result: dict | None, scenario: dict = SCENARIO) -> tuple[bool, str]:
    """Prueft das Physik-Ergebnis eines Backends. Rein, ohne Seiteneffekte."""
    if not result:
        return False, "kein Ergebnis vom Backend"
    if result.get("error"):
        return False, f"Backend-Fehler: {result['error']}"
    if result.get("steps") != scenario["steps"]:
        return False, f"falsche Schrittzahl: {result.get('steps')}"
    z = result.get("final_height")
    if not isinstance(z, (int, float)) or z != z:  # NaN
        return False, f"keine gueltige Endhoehe: {z!r}"
    expected = scenario["cube_size"] / 2.0
    if abs(z - expected) > scenario["tolerance"]:
        return False, f"Endhoehe {z:.4f} m, erwartet {expected:.3f} +- {scenario['tolerance']} m"
    return True, f"Endhoehe {z:.4f} m (erwartet {expected:.3f} +- {scenario['tolerance']} m)"


def _ppid_map() -> dict[int, list[int]]:
    """Eltern -> Kinder fuer alle Prozesse (aus /proc/<pid>/stat, alle Threads abgedeckt)."""
    kids: dict[int, list[int]] = {}
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        try:
            with open(f"/proc/{d}/stat") as f:
                stat = f.read()
        except OSError:
            continue
        ppid = int(stat[stat.rindex(")") + 2:].split()[1])
        kids.setdefault(ppid, []).append(int(d))
    return kids


def process_tree(root: int) -> list[int]:
    kids = _ppid_map()
    seen, todo = [], [root]
    while todo:
        p = todo.pop()
        if p in seen:
            continue
        seen.append(p)
        todo.extend(kids.get(p, []))
    return seen


def rss_bytes(pid: int) -> int:
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) * 1024
    except OSError:
        pass
    return 0


def gpu_mem_by_pid() -> dict[int, int]:
    """VRAM je PID in MiB (Compute-Apps). Leeres Dict ohne nvidia-smi."""
    if not shutil.which("nvidia-smi"):
        return {}
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-compute-apps=pid,used_memory", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    res: dict[int, int] = {}
    for line in out.splitlines():
        parts = [x.strip() for x in line.split(",")]
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            res[int(parts[0])] = res.get(int(parts[0]), 0) + int(parts[1])
    return res


def gpu_used_total() -> int | None:
    if not shutil.which("nvidia-smi"):
        return None
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        ).stdout.split()
        return int(out[0]) if out else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def listeners() -> set[str]:
    """Lokale Adressen aller lauschenden TCP-Sockets (``ss -ltnH``)."""
    if not shutil.which("ss"):
        return set()
    out = subprocess.run(["ss", "-ltnH"], capture_output=True, text=True).stdout
    return {line.split()[3] for line in out.splitlines() if len(line.split()) >= 4}


def non_local(addrs: set[str]) -> list[str]:
    return sorted(a for a in addrs if not LOCAL_ADDR.match(a))


def mask(addr: str) -> str:
    """Maskiert konkrete Interface-IPs, damit keine Adresse im JSON landet."""
    host, _, port = addr.rpartition(":")
    if host in ("0.0.0.0", "[::]", "*"):
        return f"*:{port}"
    return f"<iface>:{port}"


class Sampler(threading.Thread):
    def __init__(self, pid: int, interval: float = 0.5):
        super().__init__(daemon=True)
        self.pid, self.interval = pid, interval
        self.ram_peak = 0
        self.vram_peak = 0
        self.gpu_total_peak = 0
        self.listeners_seen: set[str] = set()
        self.samples = 0
        self._halt = threading.Event()  # nicht _stop: das ist ein interner Name von threading.Thread

    def run(self) -> None:
        n = 0
        while not self._halt.is_set():
            tree = process_tree(self.pid)
            self.ram_peak = max(self.ram_peak, sum(rss_bytes(p) for p in tree))
            if n % 2 == 0:  # nvidia-smi/ss seltener
                mem = gpu_mem_by_pid()
                self.vram_peak = max(self.vram_peak, sum(mem.get(p, 0) for p in tree))
                tot = gpu_used_total()
                if tot is not None:
                    self.gpu_total_peak = max(self.gpu_total_peak, tot)
                self.listeners_seen |= listeners()
            self.samples += 1
            n += 1
            self._halt.wait(self.interval)

    def stop(self) -> None:
        self._halt.set()


def root_free_gb() -> float:
    st = os.statvfs("/")
    return round(st.f_bavail * st.f_frsize / 1e9, 1)


def run_smoke(backend: str, python: str, script: str, out_dir: Path, timeout: float,
              extra_env: dict[str, str] | None = None) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = out_dir / f"{backend}-{stamp}.log"
    with tempfile.NamedTemporaryFile(prefix="smoke-", suffix=".json", delete=False) as tf:
        result_path = Path(tf.name)
    result_path.unlink()

    env = dict(os.environ)
    # Optional eigenes HOME nur fuer den Kindprozess (Kit-/Shader-Caches weg von /)
    if os.environ.get("RAEUMWERK_KIT_HOME"):
        Path(os.environ["RAEUMWERK_KIT_HOME"]).mkdir(parents=True, exist_ok=True)
        env["HOME"] = os.environ["RAEUMWERK_KIT_HOME"]
    env.update(extra_env or {})
    env["RAEUMWERK_SCENARIO"] = json.dumps(SCENARIO)
    before = listeners()
    t0 = time.monotonic()
    with open(log_path, "w") as log:
        proc = subprocess.Popen([python, "-u", script, "--result", str(result_path)],
                                stdout=log, stderr=subprocess.STDOUT, env=env,
                                start_new_session=True)
        sampler = Sampler(proc.pid)
        sampler.start()
        timed_out = False
        try:
            rc = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                rc = proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                rc = proc.wait()
        finally:
            sampler.stop()
            sampler.join(timeout=5)
    runtime = time.monotonic() - t0

    result = None
    if result_path.exists():
        try:
            result = json.loads(result_path.read_text())
        except ValueError as e:
            result = {"error": f"Ergebnis-JSON unlesbar: {e}"}
        result_path.unlink()

    ok, reason = evaluate(result)
    if timed_out:
        ok, reason = False, f"Timeout nach {timeout:.0f} s"
    elif rc != 0 and ok:
        ok, reason = False, f"Exit-Code {rc} trotz gueltigem Ergebnis"

    new_ext = non_local(sampler.listeners_seen - before)
    if new_ext:
        ok, reason = False, f"neuer Listener ausserhalb localhost: {[mask(a) for a in new_ext]}"

    report = {
        "ok": ok,
        "reason": reason,
        "backend": backend,
        "started_utc": stamp,
        "runtime_s": round(runtime, 2),
        "ram_peak_mib": round(sampler.ram_peak / 2**20, 1),
        "vram_peak_mib": sampler.vram_peak,
        "gpu_used_total_peak_mib": sampler.gpu_total_peak,
        "exit_code": rc,
        "timed_out": timed_out,
        "samples": sampler.samples,
        "listeners_non_local_before": [mask(a) for a in non_local(before)],
        "listeners_non_local_new_during_run": [mask(a) for a in new_ext],
        "root_free_gb_after": root_free_gb(),
        "scenario": SCENARIO,
        "result": result,
        "log": log_path.name,
    }
    (out_dir / f"{backend}-{stamp}.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Raeumwerk-Smoke-Runner")
    ap.add_argument("--backend", required=True, help="Name im Dateinamen, z. B. isaacsim oder newton")
    ap.add_argument("--python", required=True, help="Python des Backend-venv")
    ap.add_argument("--script", required=True, help="Backend-Skript, z. B. scripts/smoke_newton.py")
    ap.add_argument("--out", default=None, help="Ausgabeordner (Standard: $RAEUMWERK_RUNS, sonst ergebnis/)")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--timeout", type=float, default=1200.0, help="Sekunden je Lauf")
    args = ap.parse_args(argv)

    out = args.out or os.environ.get("RAEUMWERK_RUNS") or "ergebnis"
    reports = []
    for i in range(args.runs):
        r = run_smoke(args.backend, args.python, args.script, Path(out), args.timeout)
        reports.append(r)
        print(json.dumps({k: r[k] for k in ("ok", "reason", "backend", "runtime_s", "ram_peak_mib",
                                            "vram_peak_mib", "root_free_gb_after", "started_utc")}),
              flush=True)
    passed = sum(r["ok"] for r in reports)
    print(f"{args.backend}: {passed}/{len(reports)} ok", flush=True)
    return 0 if passed == len(reports) else 1


if __name__ == "__main__":
    sys.exit(main())
