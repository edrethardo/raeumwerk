"""Kollisionsform der Finger fuer die Simulation: Quader, die der CAD-Kontur folgen.

Aus denselben Parametern wie das CAD (``finger.parameter``), im Fingersystem (m):
Ursprung Mitte der Anschlussflaeche, z zur Spitze, y zum Greifgut, x quer.

    platte, schaft_1, schaft_2   Anschlussplatte und Verjuengung (aussen, Huelle)
    kern                         Fingerkern hinter V-Nut und Kerbe (y <= -kerbe_tiefe)
    flanke_{l,r}_{v,lippe}       V-Flanken (um +-winkel um z gedreht), harter Werkstoff
    auflage_{l,r}                weiche Auflagen auf den Flanken (0,5 mm ueber der Flanke)

Die Kerbe bleibt frei (nur ``kern`` dahinter): dort liegt der Tellerwulst.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List

import numpy as np

from .parameter import Finger


@dataclass
class Quader:
    name: str
    mitte: np.ndarray      # m, Fingersystem
    halb: np.ndarray       # m
    rot: np.ndarray        # 3x3
    weich: bool            # Auflage (Reibwert/Steifigkeit der Auflage)


def _rz(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def quader(f: Finger) -> List[Quader]:
    mm = 1e-3
    out: List[Quader] = []

    def box(name, lo, hi, weich=False):
        lo, hi = np.array(lo, float), np.array(hi, float)
        out.append(Quader(name, (lo + hi) / 2 * mm, (hi - lo) / 2 * mm, np.eye(3), weich))

    b2 = f.b / 2.0
    zp = f.z_platte
    g = f.p["geometrie"]
    z1 = float(g["verjuengung_bis_mm"])
    zm = (zp + z1) / 2.0
    tp = float(f.p["anschluss"]["platte_tiefe_mm"])
    kt = float(f.p["teller"]["kerbe_tiefe_mm"])
    v0, v1 = f.v_z
    k0, k1 = f.kerbe
    box("platte", (-b2, -tp, 0.0), (b2, 0.0, zp))
    box("schaft_1", (-b2, -f.dicke(zp + 1e-6), zp), (b2, 0.0, zm))
    box("schaft_2", (-b2, -f.dicke(zm), zm), (b2, 0.0, v0))
    box("kern", (-b2, -f.dicke(v0), v0), (b2, -kt, f.L))
    # Flanken: Oberkante liegt auf der Flanke, Dicke bis unter den Kern-Rand
    g_ = f.gamma
    w = b2 / math.cos(g_)
    t = kt                                     # reicht von der Flanke bis in den Kern
    for s, seite in ((1.0, "r"), (-1.0, "l")):
        R = _rz(s * g_)
        n = R @ np.array([0.0, 1.0, 0.0])        # Flankennormale (nach innen)
        xc = s * b2 / 2.0
        oben = np.array([xc, f.flanke_y(xc), 0.0])
        for name, za, zb in (("v", v0, k0), ("lippe", k1, f.L)):
            m = oben - n * t / 2.0
            m[2] = (za + zb) / 2.0
            out.append(Quader(f"flanke_{seite}_{name}", m * mm, np.array([w / 2.0, t / 2.0, (zb - za) / 2.0]) * mm, R, False))
        xa0, xa1 = f.auflage_x
        a0, a1 = f.auflage_z
        xc = s * (xa0 + xa1) / 2.0
        wa = (xa1 - xa0) / math.cos(g_)
        dck = float(f.p["auflage"]["dicke_mm"])
        m = np.array([xc, f.flanke_y(xc), 0.0]) + n * (f.auflage_ueberstand - dck / 2.0)
        m[2] = (a0 + a1) / 2.0
        out.append(Quader(f"auflage_{seite}", m * mm, np.array([wa / 2.0, dck / 2.0, (a1 - a0) / 2.0]) * mm, R, True))
    return out


def innenflaeche_y(f: Finger, x_mm: float, z_mm: float) -> float:
    """Innerste Flaeche der Kollisionsform (mm) an (x, z): fuer Tests gegen das CAD-Profil."""
    best = -1e9
    for q in quader(f):
        Rt = q.rot.T
        # Punkte entlang y bei (x, z) pruefen: groesstes y, das noch im Quader liegt
        for y in np.arange(5.0, -30.0, -0.01):
            p = np.array([x_mm, y, z_mm]) * 1e-3
            d = np.abs(Rt @ (p - q.mitte)) - q.halb
            if np.all(d <= 1e-9):
                best = max(best, y)
                break
    return best
