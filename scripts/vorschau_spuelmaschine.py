#!/usr/bin/env python3
"""Vorschau-Standbild der Spuelmaschinen-Szene (matplotlib, ohne GPU).

Zeichnet Korpus, offene Tuer, ausgezogenen Oberkorb mit Glashaltern und den
4 kopfueber stehenden Glaesern, Unterkorb, Arbeitsplatte mit Ablagepunkten,
Podest und den ReBeL (Kollisionsquader) in der Greifpose eines Slots aus der
Erreichbarkeitsanalyse. Der Renderer (scripts/render_video.py) bleibt
unberuehrt.

    python scripts/vorschau_spuelmaschine.py --out spuelmaschine.png [--slot 1]
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

FARBEN = {
    "korpus": ("#b8bec6", 0.35), "tuer": ("#8d949c", 0.8), "oberkorb": ("#3d6fb6", 0.9),
    "unterkorb": ("#5a86c2", 0.6), "glashalter": ("#d9822b", 1.0), "arbeitsplatte": ("#c9a46c", 0.45),
    "schrank": ("#e3d9c6", 0.25), "podest": ("#6b6b6b", 0.3), "roboter": ("#e8e8e8", 1.0),
    "glas": ("#7fd3e6", 0.85), "ablage": ("#7fd3e6", 0.35),
}


def quader_flaechen(mitte, halb, rot):
    s = np.array([[sx, sy, sz] for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)], float)
    p = (rot @ (s * halb).T).T + mitte
    idx = [(0, 1, 3, 2), (4, 5, 7, 6), (0, 1, 5, 4), (2, 3, 7, 6), (0, 2, 6, 4), (1, 3, 7, 5)]
    return [[p[i] for i in f] for f in idx]


def zylinder_flaechen(mitte, r, hh, n=18):
    a = np.linspace(0, 2 * math.pi, n + 1)
    f = []
    for i in range(n):
        p = [(math.cos(a[i]), math.sin(a[i])), (math.cos(a[i + 1]), math.sin(a[i + 1]))]
        f.append([mitte + [r * p[0][0], r * p[0][1], -hh], mitte + [r * p[1][0], r * p[1][1], -hh],
                  mitte + [r * p[1][0], r * p[1][1], hh], mitte + [r * p[0][0], r * p[0][1], hh]])
    oben = [mitte + [r * math.cos(t), r * math.sin(t), hh] for t in a[:-1]]
    return f + [oben]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--slot", type=int, default=1, help="Roboter in der Greifpose dieses Slots (0 = ohne Roboter)")
    args = ap.parse_args(argv)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    from spuelmaschine import erreichbarkeit, masse

    sc = masse.load_szene()
    lage = erreichbarkeit.lage_aus_szene(sc)
    pr = erreichbarkeit.Pruefer(lage, sc)
    sz = pr.szene
    teile = []  # (flaechen, gruppe)
    for k in sz.koerper:
        teile.append((quader_flaechen(k.mitte, k.halb, k.rot), k.gruppe))
    gegriffen = None
    if args.slot:
        z = [zz for zz in pr.ziele() if zz.name == f"slot_{args.slot}"][0]
        e = pr.pruefe_ziel(z, int(sc["raster"]["seed"]))
        if e.q_greif is None:
            print(f"Slot {args.slot}: keine Greifpose ({e.grund})", file=sys.stderr)
            return 1
        gegriffen = z.glas.name
        q = np.array(e.q_greif)
        for boxes in pr.roboterquader(q).values():
            for b in boxes:
                teile.append((quader_flaechen(b.mitte, b.halb, b.rot), "roboter"))
        print(f"Roboter: Slot {args.slot}, erreichbar={e.ok}, IK-Fehler {e.ik_fehler_max_m * 1e3:.4f} mm, "
              f"Kollisionen {len(e.kollisionen)}")
    for g in pr.glaeser_korb:
        teile.append((zylinder_flaechen(g.mitte, g.halb[0], g.halb[2]), "glas"))
    for g in pr.glaeser_ablage:
        teile.append((zylinder_flaechen(g.mitte, g.halb[0], g.halb[2]), "ablage"))
    if pr.podest is not None:
        p = pr.podest
        teile.append((quader_flaechen(p.mitte, p.halb, p.rot), "podest"))

    fig = plt.figure(figsize=(14, 7), dpi=110)
    ansichten = [("Schrägansicht aus dem Raum", 28, 58), ("Draufsicht", 89, -90)]
    # feste Zeichenreihenfolge (matplotlib sortiert Flaechen in 3D unzuverlaessig)
    reihe = ["schrank", "korpus", "tuer", "unterkorb", "podest", "oberkorb", "glashalter", "glas",
             "roboter", "arbeitsplatte", "ablage"]
    teile.sort(key=lambda t: reihe.index(t[1]))
    for i, (titel, elev, azim) in enumerate(ansichten):
        ax = fig.add_subplot(1, 2, i + 1, projection="3d", computed_zorder=False)
        for fl, gr in teile:
            farbe, alpha = FARBEN[gr]
            pc = Poly3DCollection(fl, facecolor=farbe, edgecolor="#333333", linewidths=0.2, alpha=alpha)
            ax.add_collection3d(pc)
        ax.set_xlim(-0.2, 1.3)
        ax.set_ylim(-0.6, 1.4)
        ax.set_zlim(0.0, 1.5)
        ax.set_box_aspect((1.5, 2.0, 1.5))
        ax.view_init(elev=elev, azim=azim)
        ax.set_xlabel("x (m)")
        ax.set_ylabel("y (m)")
        if elev > 80:
            ax.set_zticks([])
        else:
            ax.set_zlabel("z (m)")
        ax.set_title(titel)
    o = lage.ursprung
    fig.suptitle("60-cm-Spülmaschine: Tür offen, Oberkorb ausgezogen, 4 Gläser kopfüber; Ablage auf der "
                 f"Arbeitsplatte; ReBeL auf 7. Achse (Podest {o[2]:.2f} m, Schiene x = {o[0]:.2f} m)"
                 + (f", Greifpose Slot {args.slot}" if gegriffen else ""), fontsize=10)
    fig.tight_layout()
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out)
    print("Standbild:", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
