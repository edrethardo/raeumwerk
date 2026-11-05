#!/usr/bin/env python3
"""Einfallswinkel der hochkant stehenden Teller (Normale entlang y) zum Sehstrahl der Mastkamera.

Der Winkel zwischen Tellernormale und Sehstrahl haengt nur vom Kameraort ab (nicht von der Neigung):
``cos(w) = |y_kamera - y_teller| / Abstand``. Der Schaetzer verlangt ``w < 60`` Grad (``winkel_max``).
Ausgabe (JSON): je Auszug (0,225 / 0,45 m) und Kameraort (y, z; x fest) die Zahl der Teller unter dem Grenzwinkel
und der groesste Winkel; dazu die beste Stelle im erlaubten Bereich und die Stelle im erweiterten Bereich, an der
alle 14 Teller unter 60 Grad liegen (falls es sie gibt). Optional: ``--wb1427`` rechnet den vordersten Oberkorb-Teller
der Griffpose-Szene nach (Widerspruchspruefung).

    mast_teller_winkel.py AUSGABE.json [--x 0.55] [--wb1427]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))
sys.path.insert(0, str(HIER))

import kamera_stationen as KS  # noqa: E402

GRENZEN = (60.0, 65.0, 70.0, 75.0, 80.0)
Y_ERLAUBT = np.round(np.arange(0.30, 0.7001, 0.05), 3)
Z_ERLAUBT = np.round(np.arange(1.15, 1.6001, 0.05), 3)
Y_WEIT = np.round(np.arange(0.30, 1.2001, 0.05), 3)
Z_WEIT = np.round(np.arange(0.80, 2.0001, 0.05), 3)


def teller_zentren(auszug: float):
    """Namen und Mittelpunkte der 14 Teller (8 Oberkorb, 6 Unterkorb) bei Auszug des jeweiligen Korbs."""
    out = []
    for was, (ao, au) in (("ober_teller", (auszug, 0.0)), ("unter", (0.0, auszug))):
        _, objekte = KS.welt(ao, au, was)
        out += [(o["name"], o["korb"], np.asarray(o["c"], float)) for o in objekte]
    return out


def winkel(C, P):
    d = np.asarray(C, float) - P
    return float(np.degrees(np.arccos(abs(d[1]) / np.linalg.norm(d))))


def raster(x, ys, zs, zentren):
    rows = []
    for y in ys:
        for z in zs:
            w = np.array([winkel((x, y, z), c) for _, _, c in zentren])
            rows.append(dict(y=float(y), z=float(z), winkel=[round(float(v), 1) for v in w],
                             w_max=round(float(w.max()), 1), w_median=round(float(np.median(w)), 1),
                             n_unter={str(g): int((w < g).sum()) for g in GRENZEN}))
    return rows


def wb1427_pruefung():
    import griff_wahrnehmung as GW
    from wahrnehmung import griffpose as WG
    from wahrnehmung import verdeckung as V
    from wahrnehmung.strahlen import Kamera
    w, nenn = GW.welt("teller", 1, 0)
    prims = WG.prims_aus_welt(w, "teller")
    ziel = w.glas_start[0].name
    p = next(q for q in prims if q.objekt == ziel)
    cam = WG.ensenso(2.0, None, None)
    r = V.sichtbarkeit(prims, cam, [ziel])[ziel]
    n = p.R[:, 2] / np.linalg.norm(p.R[:, 2])
    est = WG.schaetzen("teller", w, 0, nenn, seed=1)
    return dict(ziel=ziel, mitte=p.c.tolist(), halb=p.h.tolist(), normale=n.tolist(),
                winkel_mitte_grad=winkel(cam.C, p.c), sichtbarkeit={k: v for k, v in r.items()},
                schaetzen_ok=est["ok"], gruende=est["gruende"], stat_e=est.get("ensenso", {}).get("statistik"))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("ausgabe")
    ap.add_argument("--x", type=float, default=0.55)
    ap.add_argument("--wb1427", action="store_true")
    a = ap.parse_args()
    res = {"x": a.x, "grenzen": GRENZEN}
    for aus in (0.225, 0.45):
        zen = teller_zentren(aus)
        res[f"auszug_{aus}"] = dict(
            teller=[dict(name=n, korb=k, c=[round(float(v), 3) for v in c]) for n, k, c in zen],
            erlaubt=raster(a.x, Y_ERLAUBT, Z_ERLAUBT, zen), weit=raster(a.x, Y_WEIT, Z_WEIT, zen))
    # beste Stelle: Mittel der Teller unter 60 Grad ueber beide Auszuege
    for bereich in ("erlaubt", "weit"):
        r1, r2 = res["auszug_0.225"][bereich], res["auszug_0.45"][bereich]
        best = max(range(len(r1)), key=lambda i: (r1[i]["n_unter"]["60.0"] + r2[i]["n_unter"]["60.0"],
                                                  -(r1[i]["w_max"] + r2[i]["w_max"])))
        res[f"beste_{bereich}"] = dict(y=r1[best]["y"], z=r1[best]["z"], auszug_0225=r1[best], auszug_045=r2[best])
        alle = [i for i in range(len(r1)) if r1[i]["n_unter"]["60.0"] == 14 and r2[i]["n_unter"]["60.0"] == 14]
        res[f"alle_unter_60_{bereich}"] = [(r1[i]["y"], r1[i]["z"]) for i in alle]
    if a.wb1427:
        try:
            res["wb1427"] = wb1427_pruefung()
        except Exception as e:  # Pruefung ist Beiwerk
            res["wb1427"] = {"fehler": repr(e)}
    Path(a.ausgabe).parent.mkdir(parents=True, exist_ok=True)
    Path(a.ausgabe).write_text(json.dumps(res, indent=1, default=str))
    for k in ("beste_erlaubt", "beste_weit"):
        print(k, json.dumps(res[k], default=str))
    print("alle<60 erlaubt:", res["alle_unter_60_erlaubt"], " weit:", res["alle_unter_60_weit"][:12])
    if "wb1427" in res:
        print("wb1427", json.dumps(res["wb1427"], default=str)[:1500])


if __name__ == "__main__":
    main()
