"""Befund: Wie tief koennte das Podest mit einem Seitgriff an der Ablage sein?

Nur Kinematik (IK + Kollision gegen die statische Szene, kein Newton). Fuer
jede Podesthoehe wird geprueft, ob die Teilwege des Ablaufs erreichbar und
kollisionsfrei sind:

* ``slot``:   Griff von oben im Korb (Vorposition -> Greifpose -> Aushub)
* ``matte``:  Glas kopfueber mit Griff von oben auf der Zwischenablage absetzen
* ``seite``:  Seitgriff an der Zwischenablage + Anheben + Umdrehen (Gelenk 6)
* ``ablage``: Seitgriff aufrecht auf jedem Ablagepunkt absetzen + Rueckzug

    python -m ausraeumen.befund [--hoehen 0.4 0.5 0.55 0.6 0.65] [--out befund.json]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from typing import Dict, List, Optional, Sequence

import numpy as np

from rebel_model.config import load as load_robot
from rebel_model.kinematics import Chain
from rebel_model.urdf_gen import build_urdf
from spuelmaschine.erreichbarkeit import Lage, lage_aus_szene, r_greif

from . import geometrie as ag, konfig
from .plan import Halt, Lagezustand, PlanFehler, Planer, r_seite


def _weg(p: Planer, punkte, R, z, rng) -> bool:
    """Erste Pose per IK (Haltungen), dann gerade Wege zwischen den Punkten."""
    for q0 in p.startwerte(punkte[0], rng):
        q0 = q0.copy()
        q0[p.ifg] = p.q_offen
        q, pe, ok = p.ik(punkte[0], R, q0, 1, rng)
        if not ok or p.treffer(q, z):
            continue
        try:
            for a, b in zip(punkte[:-1], punkte[1:]):
                q = p.lin(a, b, R, q, z, rng)[-1]
        except PlanFehler:
            continue
        return True
    return False


def pruefe_hoehe(h: float, cfg=None, chain=None, zuweisungen=None) -> Dict[str, object]:
    cfg = cfg or load_robot()
    chain = chain or Chain(build_urdf(cfg))
    auf = konfig.aufbau(zuweisungen=zuweisungen)
    l0 = lage_aus_szene(auf.sc)
    lage = Lage(l0.name, (l0.ursprung[0], l0.ursprung[1], float(h)), l0.gier_grad)
    w = ag.baue(auf, cfg.achse7, lage)
    p = Planer(w, cfg, chain)
    rng = np.random.default_rng(0)
    g, sg_, za = auf.sc["greifen"], auf.a["seitgriff"], auf.a["zwischenablage"]
    leer = Lagezustand([])
    out: Dict[str, object] = {"podest_m": h}
    # Slots: Griff von oben
    slots = []
    for G in w.glas_start:
        rand = G.mitte[2] - w.glas_h / 2.0
        pg = np.array([G.mitte[0], G.mitte[1], rand + float(g["tcp_ueber_glasrand_m"])])
        pts = [pg + [0, 0, float(g["vorposition_m"])], pg, pg + [0, 0, float(g["aushub_m"])]]
        z = Lagezustand([], {G.name})
        slots.append(any(_weg(p, pts, r_greif(gier), z, rng) for gier in g["slot_gier_grad"]))
    out["slot"] = slots
    # Matte: Glas kopfueber von oben absetzen (TCP 88 mm ueber dem Glasrand)
    zg = w.glas_auf_zwischenablage(0)
    pm = np.array([zg.mitte[0], zg.mitte[1], w.zwischen.oben + float(za["absetzen_luft_m"]) + float(g["tcp_ueber_glasrand_m"])])
    out["matte"] = any(_weg(p, [pm + [0, 0, float(za["vorposition_m"])], pm], r_greif(gier), Lagezustand([], {zg.name}), rng)
                       for gier in g["slot_gier_grad"])
    # Seitgriff an der Matte (ohne Umdrehen-Pruefung: nur Erreichbarkeit)
    d = float(sg_["hoehe_ab_glasboden_m"])
    pgl = np.array([zg.mitte[0], zg.mitte[1], zg.oben - d])
    seite = False
    for psi in sg_["gier_kandidaten_grad"]:
        Rs = r_seite(float(psi))
        ps = pgl - float(sg_["tiefe_m"]) * Rs[:, 2]
        if _weg(p, [ps - float(sg_["vorposition_m"]) * Rs[:, 2], ps, ps + [0, 0, float(sg_["anheben_m"])]], Rs,
                Lagezustand([zg], {zg.name}), rng):
            seite = True
            break
    out["seite"] = seite
    # Ablage: aufrecht mit Seitgriff
    abl = []
    for Z in w.glas_ziel:
        ok = False
        pz = np.array([Z.mitte[0], Z.mitte[1], Z.unten + float(sg_["absetzen_luft_m"]) + d])
        for psi in sg_["gier_kandidaten_grad"]:
            Rs = r_seite(float(psi))
            pa = pz - float(sg_["tiefe_m"]) * Rs[:, 2]
            if _weg(p, [pa + [0, 0, float(sg_["ablage_vorposition_m"])], pa, pa - float(sg_["rueckzug_m"]) * Rs[:, 2]],
                    Rs, Lagezustand([], {Z.name}), rng):
                ok = True
                break
        abl.append(ok)
    out["ablage"] = abl
    out["alles"] = all(slots) and out["matte"] and seite and all(abl)
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--hoehen", type=float, nargs="+", default=[0.30, 0.40, 0.50, 0.55, 0.60, 0.65])
    ap.add_argument("--set", action="append", default=[], metavar="ABSCHNITT.WERT=JSON",
                    help="Wert aus config/ausraeumen.yaml ueberschreiben (z. B. andere Zwischenablage)")
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    cfg = load_robot()
    chain = Chain(build_urdf(cfg))
    res = []
    for h in args.hoehen:
        t = time.monotonic()
        r = pruefe_hoehe(h, cfg, chain, args.set)
        r["zuweisungen"] = list(args.set)
        r["sekunden"] = round(time.monotonic() - t, 1)
        print(json.dumps(r), flush=True)
        res.append(r)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(res, fh, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
