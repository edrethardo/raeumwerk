"""CAD-Ansichten der Finger aus der STL (matplotlib, Pruefbild, kein Rendering).

    python -m finger.ansichten cad/finger/finger_100.stl --out <ordner>

Zeichnet Isometrie, Seitenansicht (y-z) und Draufsicht auf die Innenseite (x-z)
sowie den Querschnitt durch die Auflagezone, mit Massangaben aus config/finger.yaml.
"""
from __future__ import annotations

import struct
from pathlib import Path
from typing import List

import numpy as np

from .parameter import Finger


def lies_stl(pfad: Path | str) -> np.ndarray:
    """Dreiecke (n, 3, 3) aus einer binaeren oder ASCII-STL."""
    daten = Path(pfad).read_bytes()
    if daten[:5] == b"solid" and b"facet" in daten[:400]:
        v = [list(map(float, z.split()[1:4])) for z in daten.decode().splitlines() if z.strip().startswith("vertex")]
        return np.array(v).reshape(-1, 3, 3)
    n = struct.unpack("<I", daten[80:84])[0]
    a = np.frombuffer(daten[84:84 + 50 * n], dtype=np.dtype([("n", "<3f4"), ("v", "<9f4"), ("a", "<u2")]))
    return a["v"].reshape(-1, 3, 3).astype(float)


def _poly3d(ax, tri, farbe, licht=np.array([0.4, -0.5, 0.75])):
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    h = 0.35 + 0.65 * np.clip(n @ (licht / np.linalg.norm(licht)), 0, 1)
    c = np.clip(np.array(farbe)[None, :] * h[:, None], 0, 1)
    ax.add_collection3d(Poly3DCollection(tri, facecolors=c, edgecolors="none"))


def zeichne(stl: Path, out: Path, auflage_stl: Path | None = None) -> List[Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    f = Finger.laden()
    tri = lies_stl(stl)
    au = lies_stl(auflage_stl) if auflage_stl and Path(auflage_stl).exists() else None
    au2 = None
    if au is not None:
        au2 = au.copy()
        au2[..., 0] *= -1  # gespiegelte zweite Auflage
    out.mkdir(parents=True, exist_ok=True)
    pfade = []
    grau, blau = (0.82, 0.82, 0.86), (0.25, 0.45, 0.85)

    # Isometrie
    fig = plt.figure(figsize=(7, 8), dpi=130)
    ax = fig.add_subplot(111, projection="3d", computed_zorder=False)
    _poly3d(ax, tri, grau)
    for a_ in (au, au2):
        if a_ is not None:
            _poly3d(ax, a_, blau)
    ax.set_xlim(-30, 30); ax.set_ylim(-40, 20); ax.set_zlim(0, 100)
    ax.set_box_aspect((60, 60, 100))
    ax.view_init(elev=22, azim=35)
    ax.set_xlabel("x (Breite) mm"); ax.set_ylabel("y (Schliessrichtung) mm"); ax.set_zlabel("z (zur Spitze) mm")
    ax.set_title("Finger 100 mm, Isometrie (Pruefbild aus der STL)\nblau: TPU-Auflagen 2 mm in den Taschen")
    p = out / "finger-isometrie.png"; fig.savefig(p, bbox_inches="tight"); plt.close(fig); pfade.append(p)

    # Seitenansicht y-z und Draufsicht x-z als Projektion der Kanten
    def proj(ax, ia, ib, titel, xl, yl):
        for t in (tri,):
            for k in range(3):
                a, b = t[:, k], t[:, (k + 1) % 3]
                d = np.abs(a - b).sum(axis=1) > 1e-6
                segs = np.stack([a[d][:, [ia, ib]], b[d][:, [ia, ib]]], axis=1)
                from matplotlib.collections import LineCollection
                ax.add_collection(LineCollection(segs, colors="0.45", linewidths=0.15))
        for a_ in (au, au2):
            if a_ is not None:
                ax.fill(a_[:, :, ia].ravel(), a_[:, :, ib].ravel(), color=blau, alpha=0.25, lw=0)
        ax.set_aspect("equal"); ax.autoscale(); ax.set_title(titel); ax.set_xlabel(xl); ax.set_ylabel(yl)
        ax.grid(alpha=0.3)

    fig, axs = plt.subplots(1, 3, figsize=(13, 8), dpi=130, gridspec_kw={"width_ratios": [1.2, 1, 1.1]})
    proj(axs[0], 1, 2, "Seitenansicht (y-z)", "y mm (innen +)", "z mm (Spitze oben)")
    k0, k1 = f.kerbe
    axs[0].annotate(f"Kerbe {k1 - k0:.0f} mm,\n{f.p['teller']['kerbe_tiefe_mm']} mm tief", (-2.5, (k0 + k1) / 2),
                    (-28, 84), arrowprops=dict(arrowstyle="->"), fontsize=8)
    axs[0].annotate("Lippe + Fase", (0, 98), (-24, 104), arrowprops=dict(arrowstyle="->"), fontsize=8)
    axs[0].annotate("Anschlussplatte\n2 x M4 (ANNAHME)", (-12, 4), (-36, 22), arrowprops=dict(arrowstyle="->"), fontsize=8)
    proj(axs[1], 0, 2, "Innenseite (x-z)", "x mm (Breite)", "z mm")
    a0, a1 = f.auflage_z
    axs[1].annotate(f"Auflagen z {a0:.0f}-{a1:.0f} mm", (5, (a0 + a1) / 2), (10, 60), arrowprops=dict(arrowstyle="->"),
                    fontsize=8)
    # Querschnitt in der Auflagezone (aus den Parametern)
    ax = axs[2]
    t = f.dicke(60.0)
    xs = np.linspace(-f.b / 2, f.b / 2, 200)
    ax.fill_between(xs, -t, [f.flanke_y(x) for x in xs], color="0.8")
    xa0, xa1 = f.auflage_x
    tt = float(f.p["auflage"]["taschen_tiefe_mm"]); dk = float(f.p["auflage"]["dicke_mm"])
    for s in (1, -1):
        xx = np.linspace(xa0, xa1, 20) * s
        y0 = np.array([f.flanke_y(x) for x in xx])
        ax.fill_between(xx, y0 - tt, y0 - tt + dk, color=blau, alpha=0.8)
    for dm, c in ((65, "g"), (75, "k"), (85, "r")):
        r = dm / 2.0
        # Glasachse parallel zur Fingerachse: Kreis beruehrt die Auflagen
        yc = f.flanke_y(r * np.sin(f.gamma)) + f.auflage_ueberstand + r * np.cos(f.gamma) - 0.0
        th = np.linspace(-0.6, 0.6, 100)
        ax.plot(r * np.sin(th), yc - r * np.cos(th), c, lw=0.8, label=f"Glas {dm} mm")
    ax.set_aspect("equal"); ax.set_ylim(-t - 2, 6); ax.set_xlim(-12, 12); ax.grid(alpha=0.3)
    ax.set_title(f"Querschnitt z 60 mm: V {f.p['v_kontur']['winkel_grad']} Grad,\nAuflagen {dk} mm in {tt} mm Taschen")
    ax.legend(fontsize=7, loc="lower right"); ax.set_xlabel("x mm"); ax.set_ylabel("y mm")
    fig.suptitle("Finger 100 mm fuer igus 0-LCA-GRI-0100 (eigene Konstruktion, Pruefbild)")
    p = out / "finger-ansichten.png"; fig.savefig(p, bbox_inches="tight"); plt.close(fig); pfade.append(p)
    return pfade


def main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("stl")
    ap.add_argument("--auflage")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    for p in zeichne(Path(a.stl), Path(a.out), Path(a.auflage) if a.auflage else None):
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
