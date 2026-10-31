"""Primitive, Strahlschnitt und Kameramodelle (Lochkamera, Datenblattwerte)."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

# Ensenso B57 (Farbvariante): Datenblatt 2024-09: Pixel 0,307 mm bei 500 mm -> f = 1628,7 px,
# 2024 x 2061 px, z-Genauigkeit 0,383 mm bei 500 mm (waechst mit d^2: 1,533 mm bei 1 m),
# Bereich 0,21-2,0 m, Farbe laut Handbuch bis 0,8 m.
ENSENSO = dict(name="ensenso", f=1628.7, fy=1628.7, w=2024, h=2061, dmin=0.21, dmax=2.0,
               sigma_k=1.533e-3, winkel_max=60.0)
# D405: Tiefe 87 x 58 Grad, 848 x 480, Min-Z 7 cm, ideal 7-50 cm, +-2 % bei 50 cm (als 2 sigma, ~d^2).
D405 = dict(name="d405", f=424 / math.tan(math.radians(43.5)), fy=240 / math.tan(math.radians(29.0)),
            w=848, h=480, dmin=0.07, dmax=0.50, sigma_k=0.02, winkel_max=70.0)


@dataclass
class Prim:
    name: str
    gruppe: str
    art: str                      # box | zyl
    c: np.ndarray
    h: np.ndarray                 # box: halbe Kanten; zyl: (r, r, halbe Hoehe)
    R: np.ndarray = field(default_factory=lambda: np.eye(3))
    objekt: str = ""


def schnitt(p: Prim, o: np.ndarray, d: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Strahlen o + t d (N,3): Abstand t (inf = kein Treffer) und Flaechennormale (N,3)."""
    n = len(d)
    eps = 1e-6
    ol = (o - p.c) @ p.R
    dl = d @ p.R
    if p.art == "box":
        with np.errstate(divide="ignore", invalid="ignore"):
            inv = 1.0 / np.where(np.abs(dl) < 1e-12, 1e-12, dl)
            t1 = (-p.h - ol) * inv
            t2 = (p.h - ol) * inv
        tn, tf = np.minimum(t1, t2), np.maximum(t1, t2)
        tmin, tmax = tn.max(1), tf.min(1)
        ok = (tmax >= tmin) & (tmin > eps)
        t = np.where(ok, tmin, np.inf)
        ax = tn.argmax(1)
        nl = np.zeros((n, 3))
        nl[np.arange(n), ax] = -np.sign(dl[np.arange(n), ax])
        return t, nl @ p.R.T
    r, hh = float(p.h[0]), float(p.h[2])
    ox, oy, oz = ol[:, 0], ol[:, 1], ol[:, 2]
    dx, dy, dz = dl[:, 0], dl[:, 1], dl[:, 2]
    a = dx * dx + dy * dy
    b = 2 * (ox * dx + oy * dy)
    cc = ox * ox + oy * oy - r * r
    disc = b * b - 4 * a * cc
    with np.errstate(invalid="ignore", divide="ignore"):
        ts = (-b - np.sqrt(np.maximum(disc, 0))) / (2 * a)
    zs = oz + ts * dz
    side = (disc > 0) & (a > 1e-12) & (ts > eps) & (np.abs(zs) <= hh)
    t = np.where(side, ts, np.inf)
    nor = np.stack([(ox + ts * dx) / r, (oy + ts * dy) / r, np.zeros(n)], 1)
    for s in (1.0, -1.0):
        with np.errstate(invalid="ignore", divide="ignore"):
            tc = (s * hh - oz) / np.where(np.abs(dz) < 1e-12, 1e-12, dz)
        qx, qy = ox + tc * dx, oy + tc * dy
        cap = (tc > eps) & (qx * qx + qy * qy <= r * r) & (tc < t)
        t = np.where(cap, tc, t)
        nor[cap] = [0.0, 0.0, s]
    return t, nor @ p.R.T


def naechster(prims: List[Prim], o, d, ohne=None):
    n = len(d)
    best = np.full(n, np.inf)
    idx = np.full(n, -1)
    nor = np.zeros((n, 3))
    for i, p in enumerate(prims):
        if ohne is not None and ohne(p):
            continue
        # Grobtest: Strahlen, die die Huellkugel verfehlen, ueberspringen
        rad = float(np.linalg.norm(p.h))
        v = p.c - o
        tp = np.sum(v * d, 1)
        dist2 = np.sum(v * v, 1) - tp * tp
        m = (dist2 <= rad * rad) & (tp > -rad)
        if not m.any():
            continue
        sel = np.where(m)[0]
        t, nn = schnitt(p, o[sel], d[sel])
        bes = t < best[sel]
        k = sel[bes]
        best[k] = t[bes]
        idx[k] = i
        nor[k] = nn[bes]
    return best, idx, nor


@dataclass
class Kamera:
    name: str
    modell: dict
    C: np.ndarray
    R: np.ndarray       # Spalten: rechts, unten, vorwaerts (Welt)
    skala: float = 1.0  # Pixel zusammenfassen (Rechenzeit)

    @staticmethod
    def zielend(name, modell, C, A, skala=1.0) -> "Kamera":
        C = np.asarray(C, float)
        f = np.asarray(A, float) - C
        f /= np.linalg.norm(f)
        r = np.cross(f, [0.0, 0.0, 1.0])
        r /= np.linalg.norm(r)
        return Kamera(name, modell, C, np.column_stack([r, np.cross(f, r), f]), skala)

    def raster(self) -> Tuple[int, int, float, float]:
        m = self.modell
        return int(m["h"] / self.skala), int(m["w"] / self.skala), m["f"] / self.skala, m["fy"] / self.skala

    def strahlen(self) -> Tuple[np.ndarray, Tuple[int, int]]:
        h, w, fx, fy = self.raster()
        u, v = np.meshgrid(np.arange(w) + 0.5 - w / 2, np.arange(h) + 0.5 - h / 2)
        d = np.stack([u / fx, v / fy, np.ones_like(u)], -1).reshape(-1, 3) @ self.R.T
        return d / np.linalg.norm(d, axis=1, keepdims=True), (h, w)

    def projiziere(self, P: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Welt -> Pixel (Spalte, Zeile) im Raster und Tiefe z."""
        h, w, fx, fy = self.raster()
        q = (np.asarray(P, float) - self.C) @ self.R
        z = q[:, 2]
        return q[:, 0] / z * fx + w / 2, q[:, 1] / z * fy + h / 2, z


def r_greif(gier_grad: float) -> np.ndarray:
    """Werkzeugdrehung Griff von oben (z nach unten), Schliessrichtung y unter der Gier."""
    a = math.radians(gier_grad)
    y = np.array([math.cos(a), math.sin(a), 0.0])
    z = np.array([0.0, 0.0, -1.0])
    return np.column_stack([np.cross(y, z), y, z])


def d405_am_greifer(tcp, Rt, seitlich=0.06, ueber_tcp=0.13, neigung_grad=20.0, skala=1.0) -> Kamera:
    """D405 auf dem Halter zwischen Flansch und Greifer: ``seitlich`` neben der Werkzeugachse
    (x des Werkzeugs), ``ueber_tcp`` ueber dem TCP, um ``neigung_grad`` zur Achse hin geneigt."""
    th = math.radians(neigung_grad)
    c_t = np.array([seitlich, 0.0, -ueber_tcp])
    f_t = np.array([-math.sin(th), 0.0, math.cos(th)])
    r_t = np.array([0.0, 1.0, 0.0])
    R = Rt @ np.column_stack([r_t, np.cross(f_t, r_t), f_t])
    return Kamera("d405", D405, np.asarray(tcp, float) + Rt @ c_t, R, skala)


def greifer_prims(tcp, Rt, oeffnung: float, finger_breite=0.018, finger_laenge=0.10) -> List[Prim]:
    """Greifer und offene Finger als Quader im TCP-Rahmen (Selbstverdeckung im D405-Bild)."""
    tcp = np.asarray(tcp, float)

    def box(name, lo, hi):
        lo, hi = np.array(lo, float), np.array(hi, float)
        return Prim(name, "greifer", "box", tcp + Rt @ ((lo + hi) / 2), (hi - lo) / 2, Rt.copy(), "greifer")
    yo = oeffnung / 2 + 0.006
    b2 = finger_breite / 2
    zs = -(finger_laenge - 0.03)
    return [box("greifer", (-0.025, -0.075, -0.12), (0.025, 0.075, zs)),
            box("finger_l", (-b2, yo - 0.006, zs), (b2, yo + 0.006, 0.03)),
            box("finger_r", (-b2, -yo - 0.006, zs), (b2, -yo + 0.006, 0.03))]
