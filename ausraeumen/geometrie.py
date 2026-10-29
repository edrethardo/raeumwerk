"""Szene und Kollisionspruefung fuer das Ausraeumen.

Baut aus ``spuelmaschine.geometrie`` die Maschine (Korbauszug je Versuch),
die Zwischenablage, Podest und Boden sowie die vier Glaeser (Lage je Versuch).
Im Unterschied zu ``spuelmaschine.erreichbarkeit`` koennen Glaeser hier
beliebig gedreht sein (beim Umdrehen in der Hand): Zylinder gegen Quader und
Zylinder gegen Zylinder werden mit dem Trennachsensatz ueber die exakte
Stuetzfunktion des Zylinders geprueft. Dabei fehlen die Achsen der
Mantelkruemmung, der Test meldet also im Zweifel eine Kollision zu viel,
nie eine zu wenig.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

import numpy as np

from rebel_model.collision import obb_penetration
from spuelmaschine import geometrie as sg
from spuelmaschine.erreichbarkeit import Lage, lage_aus_szene, rz

from .konfig import Aufbau

KOPFUEBER = np.diag([1.0, -1.0, -1.0])  # 180 Grad um x: Glasboden oben


def rx(grad: float) -> np.ndarray:
    a = math.radians(grad)
    c, s = math.cos(a), math.sin(a)
    return np.array([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]])


def glas(name: str, mitte: Sequence[float], rot: np.ndarray, r: float, h: float) -> sg.Koerper:
    return sg.Koerper(name, "glas", "zylinder", np.asarray(mitte, float), np.array([r, r, h / 2.0]),
                      np.asarray(rot, float).copy())


def _senkrecht(k: sg.Koerper) -> bool:
    return abs(float(k.rot[2, 2])) > math.cos(math.radians(0.5))


def _stuetz(k: sg.Koerper, n: np.ndarray) -> float:
    """Halbe Ausdehnung des Koerpers entlang der Einheitsrichtung n."""
    if k.form == "zylinder":
        u = k.rot[:, 2]
        c = abs(float(n @ u))
        return c * float(k.halb[2]) + float(k.halb[0]) * math.sqrt(max(0.0, 1.0 - c * c))
    return float(np.sum(k.halb * np.abs(k.rot.T @ n)))


def ueberlappung(a: sg.Koerper, b: sg.Koerper, rand: float = 0.0) -> float:
    """> 0: Koerper durchdringen sich (bzw. kommen sich naeher als ``rand``)."""
    if a.form == "quader" and b.form == "quader":
        return sg.ueberlappung(a, b, rand)
    if a.form == "zylinder" and b.form == "zylinder" and _senkrecht(a) and _senkrecht(b):
        return sg.ueberlappung(a, b, rand)
    if b.form == "zylinder" and a.form == "quader":
        a, b = b, a
    if a.form == "zylinder" and b.form == "quader" and _senkrecht(a) and np.allclose(b.rot, np.eye(3)):
        return sg.ueberlappung(a, b, rand)  # exakter Kreisabstand
    achsen = [a.rot[:, i] for i in range(3)] + [b.rot[:, i] for i in range(3)]
    for i in range(3):
        for k in range(3):
            v = np.cross(a.rot[:, i], b.rot[:, k])
            n = np.linalg.norm(v)
            if n > 1e-9:
                achsen.append(v / n)
    d = b.mitte - a.mitte
    nd = np.linalg.norm(d)
    if nd > 1e-12:
        achsen.append(d / nd)
    best = math.inf
    for n in achsen:
        ov = _stuetz(a, n) + _stuetz(b, n) - abs(float(d @ n)) + rand
        best = min(best, ov)
        if best < 0:
            return best
    return best


@dataclass
class Welt:
    """Statische Szene + Glaslagen eines Versuchs (Kuechensystem)."""
    aufbau: Aufbau
    lage: Lage
    szene: sg.Szene
    statisch: List[sg.Koerper]       # Maschine, Platte, Schraenke, Zwischenablage, Podest, Boden
    glas_start: List[sg.Koerper]     # kopfueber im Korb (Lage je Versuch)
    glas_ziel: List[sg.Koerper]      # aufrecht auf der Ablage (Sollage)
    matten: List[sg.Koerper]         # Zwischenablagen (Matten auf der Platte)
    glas_r: float
    glas_h: float

    @property
    def zwischen(self) -> sg.Koerper:
        """Erste Zwischenablage (links)."""
        return self.matten[0]

    def matte_fuer(self, ablage: int) -> sg.Koerper:
        return self.matten[int(self.aufbau.a["zwischenablage"]["je_ablage"][ablage])]

    def get(self, name: str) -> sg.Koerper:
        for k in self.statisch:
            if k.name == name:
                return k
        raise KeyError(name)

    def glas_auf_zwischenablage(self, i: int, matte: Optional[sg.Koerper] = None) -> sg.Koerper:
        z = matte if matte is not None else self.zwischen
        return glas(f"glas_{i + 1}", (z.mitte[0], z.mitte[1], z.oben + self.glas_h / 2.0), KOPFUEBER,
                    self.glas_r, self.glas_h)


def podest(lage: Lage, cfg_achse7: Dict, rand: float) -> Optional[sg.Koerper]:
    h = lage.hoehe
    if h <= 1e-9:
        return None
    T = lage.matrix()
    L, W = float(cfg_achse7["laenge_m"]), float(cfg_achse7["breite_m"])
    mitte = T[:3, :3] @ np.array([L / 2.0, 0.0, -h / 2.0]) + T[:3, 3]
    return sg.Koerper("podest", "podest", "quader", mitte, np.array([L / 2.0 + rand, W / 2.0 + rand, h / 2.0]),
                      T[:3, :3].copy())


def baue(auf: Aufbau, cfg_achse7: Dict, lage: Optional[Lage] = None) -> Welt:
    m, sc, a, abw = auf.m, auf.sc, auf.a, auf.abw
    lage = lage or lage_aus_szene(sc)
    sz = sg.baue(m, auf.auszug, sc["pose"]["unterkorb_auszug_m"])
    r, h = m["glas"]["durchmesser_m"] / 2.0, m["glas"]["hoehe_m"]
    za = a["zwischenablage"]
    k2 = float(za["kante_m"]) / 2.0
    ok_ = float(za["oberkante_m"])
    matten = []
    for j, (zx, zy) in enumerate(za["matten_xy_m"]):
        matten.append(sg.quader(f"zwischenablage_{j + 1}", "zwischenablage", (zx - k2, zy - k2, ok_ - float(za["dicke_m"])),
                                (zx + k2, zy + k2, ok_)))
    statisch = list(sz.koerper) + matten + [sg.quader("boden", "boden", (-3, -3, -0.1), (3, 3, 0.0))]
    p = podest(lage, cfg_achse7, float(sc["podest"]["rand_m"]))
    if p is not None:
        statisch.append(p)
    start = []
    for i, s in enumerate(sz.slots):
        dx, dy = abw.glas_versatz_xy_m[i]
        rot = KOPFUEBER @ rz(abw.glas_gier_grad[i])
        start.append(glas(f"glas_{i + 1}", (s[0] + dx, s[1] + dy, s[2]), rot, r, h))
    ziel = [glas(f"glas_{i + 1}", p_, np.eye(3), r, h) for i, p_ in enumerate(sz.ablage)]
    return Welt(auf, lage, sz, statisch, start, ziel, matten, r, h)
