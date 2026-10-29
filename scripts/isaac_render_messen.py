#!/usr/bin/env python3
"""Startet einen Befehl und misst von aussen RAM-/VRAM-Spitze und Listener.

    python3 scripts/isaac_render_messen.py --json mess.json -- <befehl> [argumente ...]

RAM = Summe RSS des Prozessbaums, VRAM = nur PIDs des eigenen Baums
(nvidia-smi, die GPU ist geteilt), Listener = TCP-Sockets ausserhalb von
localhost, die waehrend des Laufs neu auftauchen (dann Exit 9).
Nur Standardbibliothek; nutzt die Messfunktionen aus ``smoke_runner.py``.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import smoke_runner as sr  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--json", required=True)
    ap.add_argument("--intervall", type=float, default=0.5)
    ap.add_argument("befehl", nargs=argparse.REMAINDER)
    a = ap.parse_args(argv)
    cmd = a.befehl[1:] if a.befehl[:1] == ["--"] else a.befehl
    if not cmd:
        ap.error("Befehl fehlt")
    vorher = sr.listeners()
    t0 = time.monotonic()
    proc = subprocess.Popen(cmd, start_new_session=True)

    def weiter(sig, _frame):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            pass
    signal.signal(signal.SIGTERM, weiter)
    signal.signal(signal.SIGINT, weiter)
    s = sr.Sampler(proc.pid, a.intervall)
    s.start()
    rc = proc.wait()
    s.stop()
    s.join(timeout=15)
    neu = sr.non_local(s.listeners_seen - vorher)
    out = {
        "rc": rc, "wand_s": round(time.monotonic() - t0, 2),
        "ram_peak_mib": round(s.ram_peak / 2**20), "vram_peak_mib": s.vram_peak,
        "gpu_gesamt_peak_mib": s.gpu_total_peak, "messungen": s.samples,
        "neue_listener_nicht_lokal": [sr.mask(x) for x in neu],
    }
    Path(a.json).parent.mkdir(parents=True, exist_ok=True)
    Path(a.json).write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("MESSUNG", json.dumps(out), flush=True)
    if neu:
        return 9
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
