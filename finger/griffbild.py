"""Griffbilder (Pruefbild, matplotlib) aus den Fingerparametern: Glas im Griff von oben
(Schnitt durch die Auflagen und Seitenansicht) und Teller am Rand (Seitenansicht mit
Wulst in der Kerbe). Masse aus ``config/finger.yaml``, kein Rendering.

    python -m finger.griffbild --out <ordner>
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from .parameter import Finger


def _profil(f: Finger):
    """Seitenprofil (y, z) des Fingers in mm, Innenseite y = 0."""
    g = f.p["geometrie"]
    t0, t1, z1 = float(g["dicke_wurzel_mm"]), float(g["dicke_spitze_mm"]), float(g["verjuengung_bis_mm"])
    tp, zp = float(f.p["anschluss"]["platte_tiefe_mm"]), f.z_platte
    k0, k1 = f.kerbe
    kt = float(f.p["teller"]["kerbe_tiefe_mm"])
    return [(0, 0), (-tp, 0), (-tp, zp), (-t0, zp), (-t1, z1), (-t1, f.L), (0, f.L), (0, k1), (-kt, k1), (-kt, k0),
            (0, k0), (0, 0)]


def _querschnitt(f: Finger, z: float):
    """Querschnitt (x, y) in mm bei z: Rechteck mit V-Nut."""
    t = f.dicke(z)
    b2 = f.b / 2
    return [(-b2, -t), (b2, -t), (b2, 0), (0, -f.v_tiefe), (-b2, 0), (-b2, -t)]


def zeichne(out: Path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle, Polygon, Rectangle

    f = Finger.laden()
    iv = float(f.p["anschluss"]["innen_versatz_mm"])
    ue = f.auflage_ueberstand
    xa0, xa1 = f.auflage_x
    tt, dk = float(f.p["auflage"]["taschen_tiefe_mm"]), float(f.p["auflage"]["dicke_mm"])
    out.mkdir(parents=True, exist_ok=True)
    fig, axs = plt.subplots(1, 3, figsize=(16, 7), dpi=130)

    # 1) Glas, Schnitt z 60 mm (Draufsicht, Schliessrichtung waagerecht)
    ax = axs[0]
    r = 37.5
    # Glas beruehrt die Auflagen: Abstand Glasmitte -> Bezugsebene
    xk = r * math.sin(f.gamma)
    d = f.flanke_y(xk) + ue - r * math.cos(f.gamma) * 0  # Auflagenoberflaeche an der Beruehrstelle
    abst = r * math.cos(f.gamma) - (f.flanke_y(xk) + ue)  # Bezugsebene -> Glasmitte (entlang Schliessrichtung)
    for s in (1, -1):
        # Fingersystem (x quer, y zum Glas) -> Bild (u = Schliessrichtung, v = quer)
        poly = [(s * -(abst - y) * -1 if False else s * (abst - y), x) for x, y in _querschnitt(f, 60.0)]
        poly = [(s * (abst - y), x) for x, y in _querschnitt(f, 60.0)]
        ax.add_patch(Polygon(poly, closed=True, fc="0.8", ec="0.3"))
        for sx in (1, -1):
            xx = np.linspace(xa0, xa1, 10) * sx
            yy = np.array([f.flanke_y(x) for x in xx])
            pts = [(s * (abst - (y - tt)), x) for x, y in zip(xx, yy)] + \
                  [(s * (abst - (y - tt + dk)), x) for x, y in zip(xx[::-1], yy[::-1])]
            ax.add_patch(Polygon(pts, closed=True, fc=(0.25, 0.45, 0.85), ec="none"))
    ax.add_patch(Circle((0, 0), r, fc=(0.8, 0.9, 1.0, 0.5), ec="b"))
    for dm, c in ((65, "g"), (85, "r")):
        ax.add_patch(Circle((0, 0), dm / 2, fc="none", ec=c, ls="--", lw=0.8))
    ax.set_xlim(-65, 65); ax.set_ylim(-40, 40); ax.set_aspect("equal"); ax.grid(alpha=0.3)
    ax.set_xlabel("Schliessrichtung mm"); ax.set_ylabel("quer mm")
    ax.set_title(f"Glas 75 mm im Griff, Schnitt durch die Auflagen\nBeruehrung je Finger auf 2 Linien bei +-{xk:.1f} mm"
                 f" (Ø 65/85 gestrichelt)", fontsize=9)

    # 2) Glas, Seitenansicht: kopfueber im Korb, TCP 88 mm ueber dem Glasrand
    ax = axs[1]
    tcp = 30.0  # Griffpunkt hinter der Spitze
    for s in (1, -1):
        poly = [(s * (abst - y), f.L - z) for y, z in _profil(f)]
        ax.add_patch(Polygon(poly, closed=True, fc="0.8", ec="0.3"))
        a0, a1 = f.auflage_z
        ax.add_patch(Rectangle((s * abst - (s > 0) * 0.0 - (0.5 if s > 0 else -0.5) * 0, f.L - a1), 0, 0))
        ax.add_patch(Rectangle((min(s * (abst - ue), s * (abst - ue + dk)), f.L - a1), dk, a1 - a0,
                               fc=(0.25, 0.45, 0.85)))
    # Glas: Rand unten bei z = Spitze - 58 mm ... (TCP 88 mm ueber dem Rand, Spitze 30 mm unter dem TCP)
    rand = tcp - 88.0
    ax.add_patch(Rectangle((-r, rand), 2 * r, 110, fc=(0.8, 0.9, 1.0, 0.5), ec="b"))
    ax.plot([0], [tcp], "k+", ms=12)
    ax.annotate("TCP", (0, tcp), (8, tcp + 6), fontsize=8)
    ax.axhline(0, color="0.6", lw=0.5)
    ax.set_xlim(-70, 70); ax.set_ylim(-70, 115); ax.set_aspect("equal"); ax.grid(alpha=0.3)
    ax.set_xlabel("Schliessrichtung mm"); ax.set_ylabel("mm ueber der Fingerspitze")
    ax.set_title("Glas kopfueber, Griff von oben (Seitenansicht)\nAuflagen blau, Glasboden oben", fontsize=9)

    # 3) Teller: Rand von oben, Wulst in der Kerbe, Lippen klemmen die Fahne
    ax = axs[2]
    ft = f.p["teller"]
    fahne, wulst = float(ft["fahne_dicke_mm"]), float(ft["wulst_dicke_mm"])
    unter = float(ft["spitze_unter_rand_mm"])
    abst_t = fahne / 2  # Bezugsebene (Lippe) liegt an der Fahne
    for s in (1, -1):
        poly = [(s * (abst_t - y), f.L - z) for y, z in _profil(f)]
        ax.add_patch(Polygon(poly, closed=True, fc="0.8", ec="0.3"))
    # Teller (Ausschnitt): Fahne bis zur Kante, Wulst oben, Kante 10 mm ueber der Spitze
    kante = unter
    ax.add_patch(Rectangle((-fahne / 2, -60), fahne, kante - wulst / 2 + 60, fc=(0.95, 0.85, 0.7), ec="k"))
    ax.add_patch(Circle((0, kante - wulst / 2), wulst / 2, fc=(0.95, 0.85, 0.7), ec="k"))
    ax.set_xlim(-30, 30); ax.set_ylim(-20, 40); ax.set_aspect("equal"); ax.grid(alpha=0.3)
    ax.set_xlabel("Schliessrichtung mm"); ax.set_ylabel("mm ueber der Fingerspitze")
    ax.set_title(f"Teller am Rand (Seitenansicht, Ausschnitt)\nFahne {fahne:.0f} mm zwischen den Lippen, "
                 f"Wulst {wulst:.0f} mm in der Kerbe", fontsize=9)
    fig.suptitle("Griffbilder der 100-mm-Finger (Pruefbild aus den CAD-Parametern, kein Rendering)")
    p = out / "griffbild.png"
    fig.savefig(p, bbox_inches="tight")
    plt.close(fig)
    return p


def main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--out", required=True)
    print(zeichne(Path(ap.parse_args(argv).out)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
