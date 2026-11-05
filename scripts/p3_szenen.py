#!/usr/bin/env python3
"""Szenenliste fuer den Kameratag-Renderlauf schreiben (ohne Isaac Sim).

    p3_szenen.py --out szenen.json [--je-zelle 3] [--tuning 6]

Je Korb (ober, unter) 12 Zellen (Licht x Auszug x Nass) mal ``--je-zelle`` Wiederholungen; dazu ``--tuning``
getrennte Szenen (Seeds ab 90000, Praefix ``t_``) zum Einstellen der Erkennung. Auswertung nur ueber die
Nicht-Tuning-Szenen.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wahrnehmung import p3_szenen as P3  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--je-zelle", type=int, default=3)
    ap.add_argument("--tuning", type=int, default=6)
    a = ap.parse_args(argv)
    specs = []
    for korb in ("ober", "unter"):
        specs += P3.plan(korb, a.je_zelle, seed0=0)
    tun = []
    for korb in ("ober", "unter"):
        for s in P3.plan(korb, 1, seed0=90000)[: a.tuning // 2]:
            s["id"] = "t_" + s["id"]
            tun.append(s)
    szenen = [P3.baue_szene(s) for s in tun + specs]
    Path(a.out).write_text(json.dumps(szenen), encoding="utf-8")
    n_obj = {k: sum(len(s["objekte"]) for s in szenen if s["korb"] == k) for k in ("ober", "unter")}
    print(f"{len(szenen)} Szenen ({len(tun)} Tuning), Objekte ober/unter: {n_obj}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
