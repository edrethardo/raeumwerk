#!/usr/bin/env python3
"""Erreichbarkeits-Gegenprobe fuer eine Mastposition: ``raeumwerk aufbau`` mit Kamerakoerper als Hindernis.

Der Kamerakoerper (Ensenso C57-6-S, Huellquader nach Katalogmassen) sitzt in der Pose, die
``wahrnehmung.griffpose.ensenso_pose_aus`` aus Mast und Neigung liefert; als Hindernis geht seine
achsparallele Huelle (konservativ) in den Aufbau. Mit ``--saeule`` kommen die Mastsaeule auf der
Platte hinter der Kante und der Ausleger zur Kamera dazu. Ausgabe: ``ergebnis.json`` (je Ziel ok/Grund/q).

    mast_gegenprobe.py AUSGABE_DIR --mast 0.55 0.50 1.35 --neigung 60 [--saeule] [--jobs 6]
    mast_gegenprobe.py AUSGABE_DIR --ohne-kamera            # Bezug: Aufbau ohne Kamerakoerper
    mast_gegenprobe.py AUSGABE_DIR --ruhepose               # nur Ruhepose bestimmen
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

import numpy as np

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

from spuelmaschine import aufbau as AU  # noqa: E402
from spuelmaschine import belastung as BE  # noqa: E402
from wahrnehmung import griffpose as WG  # noqa: E402
from wahrnehmung import verdeckung as V  # noqa: E402

BEISPIEL = HIER.parent / "beispiele" / "auf-maschine-ohne-ueberstand.yaml"
BEDIENRAUM = ([-0.05, 0.05, 0.0], [0.65, 0.75, 2.0])      # Mensch vor der Platte (Annahme)


def aufbau_mit_kamera(mast=None, neigung=60.0, saeule=False, kamera=True, rand_m=0.0):
    d = copy.deepcopy(AU.lade_yaml(BEISPIEL))
    d["hindernisse"] = list(d.get("hindernisse") or [])
    if kamera and mast is not None:
        pose = WG.ensenso_pose_aus(mast, neigung)
        for name, lo, hi in V.kamera_huellen(pose[0], pose[1], saeule=saeule, rand_m=rand_m):
            d["hindernisse"].append({"name": name, "gruppe": "kamera", "lo": [float(v) for v in lo],
                                     "hi": [float(v) for v in hi]})
    return d


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("ausgabe")
    ap.add_argument("--mast", type=float, nargs=3, default=None)
    ap.add_argument("--neigung", type=float, default=60.0)
    ap.add_argument("--saeule", action="store_true")
    ap.add_argument("--ohne-kamera", action="store_true")
    ap.add_argument("--ruhepose", action="store_true")
    ap.add_argument("--jobs", type=int, default=6)
    a = ap.parse_args()
    out = Path(a.ausgabe)
    out.mkdir(parents=True, exist_ok=True)
    if a.ruhepose:
        A = AU.Aufbau(AU.lade_yaml(BEISPIEL))
        r = BE.suche_ruhepose(A, bedienraum=BEDIENRAUM, rand_m=0.05, schritt_grad=15.0)
        (out / "ruhepose.json").write_text(json.dumps(r, indent=1))
        print(json.dumps(r))
        return
    d = aufbau_mit_kamera(a.mast, a.neigung, a.saeule, kamera=not a.ohne_kamera)
    e = AU.lauf(d, jobs=a.jobs)
    AU.schreibe(e, out)
    print(json.dumps(e["abdeckung"]))
    print("Laufzeit", e["laufzeit_s"], "s")


if __name__ == "__main__":
    main()
