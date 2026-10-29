"""Geometrie-Generator: Spuelmaschine, Koerbe, Glashalter, Arbeitsplatte, Glaeser.

Alle Kollisionskoerper sind Quader (Mitte, halbe Kantenlaengen, Rotation)
oder stehende Zylinder (Glaeser). Die Korbwaende sind ein Gitter-Ersatz aus
wenigen Staeben, der Korbboden eine duenne Platte. Der Korbauszug ist ein
Schiebeweg entlang +y (``auszug`` 0 .. ``auszug_max_m``); in der Szene wird er
als feste, ausgezogene Pose benutzt (``Szene.korbgelenke`` beschreibt das
Schubgelenk fuer spaetere Simulationen mit beweglichem Korb).

Koordinaten: Kuechensystem aus ``config/spuelmaschine.yaml`` (Boden z = 0,
Korpusfront y = 0, +y in den Raum).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import numpy as np

from . import masse


@dataclass
class Koerper:
    name: str
    gruppe: str  # korpus | tuer | oberkorb | unterkorb | glashalter | arbeitsplatte | schrank | glas
    form: str  # quader | zylinder
    mitte: np.ndarray
    halb: np.ndarray  # Quader: halbe Kanten; Zylinder: (r, r, h/2)
    rot: np.ndarray = field(default_factory=lambda: np.eye(3))

    @property
    def unten(self) -> float:
        return float(self.mitte[2] - np.sum(np.abs(self.rot[2, :]) * self.halb))

    @property
    def oben(self) -> float:
        return float(self.mitte[2] + np.sum(np.abs(self.rot[2, :]) * self.halb))

    def aabb(self) -> np.ndarray:
        """(2, 3): min, max (fuer Zylinder das umschliessende Quader)."""
        e = np.abs(self.rot) @ self.halb
        return np.array([self.mitte - e, self.mitte + e])


def quader(name: str, gruppe: str, lo: Sequence[float], hi: Sequence[float]) -> Koerper:
    lo, hi = np.asarray(lo, float), np.asarray(hi, float)
    if np.any(hi <= lo):
        raise ValueError(f"{name}: leerer Quader {lo} .. {hi}")
    return Koerper(name, gruppe, "quader", (lo + hi) / 2.0, (hi - lo) / 2.0)


@dataclass
class Szene:
    m: Dict
    koerper: List[Koerper]
    slots: List[np.ndarray]  # Glasmitte je Slot (kopfueber im Oberkorb)
    ablage: List[np.ndarray]  # Glasmitte je Ablagepunkt
    oberkorb_auszug: float
    unterkorb_auszug: float
    korbgelenke: List[Dict] = field(default_factory=list)

    def gruppe(self, g: str) -> List[Koerper]:
        return [k for k in self.koerper if k.gruppe == g]

    def get(self, name: str) -> Koerper:
        for k in self.koerper:
            if k.name == name:
                return k
        raise KeyError(name)

    @property
    def oberkorb_boden_z(self) -> float:
        return float(self.m["oberkorb"]["boden_hoehe_m"])

    @property
    def arbeitsplatte_z(self) -> float:
        return float(self.m["nische"]["hoehe_m"] + self.m["arbeitsplatte"]["dicke_m"])

    def glas(self, mitte: Sequence[float], name: str) -> Koerper:
        g = self.m["glas"]
        r, h = g["durchmesser_m"] / 2.0, g["hoehe_m"]
        return Koerper(name, "glas", "zylinder", np.asarray(mitte, float), np.array([r, r, h / 2.0]))

    def glaeser_im_korb(self) -> List[Koerper]:
        return [self.glas(p, f"glas_{i + 1}") for i, p in enumerate(self.slots)]


def _korb(name: str, km: Dict, gi: Dict, x_mitte: float, auszug: float, out: List[Koerper]) -> Dict:
    """Korbboden + Gitterwaende; liefert die Korbkanten."""
    s, bd, ab = gi["stab_dicke_m"], gi["boden_dicke_m"], gi["stab_abstand_m"]
    b, t, hw, zb = km["breite_m"], km["tiefe_m"], km["wand_hoehe_m"], km["boden_hoehe_m"]
    vorne = km["vorne_eingeschoben_y_m"] + auszug
    hinten = vorne - t
    x0, x1 = x_mitte - b / 2.0, x_mitte + b / 2.0
    out.append(quader(f"{name}_boden", name, (x0, hinten, zb - bd), (x1, vorne, zb)))
    zo = zb + hw
    # obere Randstaebe
    out.append(quader(f"{name}_rand_vorne", name, (x0, vorne - s, zo - s), (x1, vorne, zo)))
    out.append(quader(f"{name}_rand_hinten", name, (x0, hinten, zo - s), (x1, hinten + s, zo)))
    out.append(quader(f"{name}_rand_links", name, (x0, hinten, zo - s), (x0 + s, vorne, zo)))
    out.append(quader(f"{name}_rand_rechts", name, (x1 - s, hinten, zo - s), (x1, vorne, zo)))
    # senkrechte Wandstaebe im Abstand ``ab`` (Ecken eingeschlossen)
    def reihe(a: float, c: float) -> List[float]:
        n = max(1, int(math.ceil((c - a) / ab)))
        return [a + (c - a) * i / n for i in range(n + 1)]

    for i, x in enumerate(reihe(x0 + s / 2, x1 - s / 2)):
        for seite, y in (("vorne", vorne - s / 2), ("hinten", hinten + s / 2)):
            out.append(quader(f"{name}_stab_{seite}_{i}", name, (x - s / 2, y - s / 2, zb), (x + s / 2, y + s / 2, zo - s)))
    for i, y in enumerate(reihe(hinten + s / 2, vorne - s / 2)[1:-1]):
        for seite, x in (("links", x0 + s / 2), ("rechts", x1 - s / 2)):
            out.append(quader(f"{name}_stab_{seite}_{i}", name, (x - s / 2, y - s / 2, zb), (x + s / 2, y + s / 2, zo - s)))
    return {"x0": x0, "x1": x1, "vorne": vorne, "hinten": hinten, "boden": zb, "oben": zo}


def baue(m: Optional[Dict] = None, oberkorb_auszug: Optional[float] = None,
         unterkorb_auszug: float = 0.0) -> Szene:
    """Erzeugt die Szene. ``oberkorb_auszug`` None = ganz ausgezogen."""
    m = m or masse.load()
    n, ge, tu = m["nische"], m["geraet"], m["tuer"]
    ok, uk, gi, gh = m["oberkorb"], m["unterkorb"], m["gitter"], m["glashalter"]
    ap = m["arbeitsplatte"]
    a_o = ok["auszug_max_m"] if oberkorb_auszug is None else float(oberkorb_auszug)
    a_u = float(unterkorb_auszug)
    for nm, a, km in (("oberkorb", a_o, ok), ("unterkorb", a_u, uk)):
        if not 0.0 <= a <= km["auszug_max_m"] + 1e-12:
            raise ValueError(f"{nm}: Auszug {a} ausserhalb 0..{km['auszug_max_m']}")
    H, T = n["hoehe_m"], n["tiefe_m"]
    gx0 = (n["breite_m"] - ge["breite_m"]) / 2.0
    gx1 = gx0 + ge["breite_m"]
    w, rw, de, wo = ge["wand_m"], ge["rueckwand_m"], ge["decke_m"], ge["wanne_oben_m"]
    yh = -ge["tiefe_m"]
    k: List[Koerper] = []
    # --- Korpus (Bottich mit offener Front) ------------------------------
    k.append(quader("korpus_links", "korpus", (gx0, yh, 0.0), (gx0 + w, 0.0, H)))
    k.append(quader("korpus_rechts", "korpus", (gx1 - w, yh, 0.0), (gx1, 0.0, H)))
    k.append(quader("korpus_rueckwand", "korpus", (gx0 + w, yh, 0.0), (gx1 - w, yh + rw, H)))
    k.append(quader("korpus_decke", "korpus", (gx0 + w, yh + rw, H - de), (gx1 - w, 0.0, H)))
    k.append(quader("korpus_wanne", "korpus", (gx0 + w, yh + rw, 0.0), (gx1 - w, 0.0, wo)))
    # --- Tuer (Scharnier unten an der Front) -----------------------------
    th = math.radians(tu["oeffnung_grad"])
    L, d, hz = tu["laenge_m"], tu["dicke_m"], tu["scharnier_hoehe_m"]
    # geschlossen: y 0..d, z hz..hz+L; Drehung um x durch (0, hz) um -th
    c, s_ = math.cos(-th), math.sin(-th)
    rot = np.array([[1, 0, 0], [0, c, -s_], [0, s_, c]])
    mitte_lok = np.array([0.0, d / 2.0, L / 2.0])
    mitte = np.array([(gx0 + gx1) / 2.0, 0.0, hz]) + rot @ mitte_lok
    k.append(Koerper("tuer", "tuer", "quader", mitte, np.array([tu["breite_m"] / 2.0, d / 2.0, L / 2.0]), rot))
    # --- Koerbe -----------------------------------------------------------
    xm = n["breite_m"] / 2.0
    o = _korb("oberkorb", ok, gi, xm, a_o, k)
    _korb("unterkorb", uk, gi, xm, a_u, k)
    # --- Glashalter-Reihen im Oberkorb -----------------------------------
    hg = m["glas"]["hoehe_m"]
    tl, nr = gh["teilung_m"], int(gh["slots_je_reihe"])
    y1 = o["vorne"] - gh["erster_slot_ab_korbfront_m"]
    sd, sh, la = gi["stab_dicke_m"], gh["strebe_hoehe_m"], gh["laengsstrebe_abstand_m"]
    zb = o["boden"]
    slots = []
    for ri, xs in enumerate(gh["reihen_x_m"]):
        ys = [y1 - i * tl for i in range(nr)]
        slots += [np.array([float(xs), y, zb + hg / 2.0]) for y in ys]
        y_vorn, y_hint = ys[0] + tl / 2.0, ys[-1] - tl / 2.0
        for i in range(nr + 1):
            y = y_vorn - i * tl
            k.append(quader(f"glashalter_{ri}_quer_{i}", "glashalter", (xs - la, y - sd / 2, zb), (xs + la, y + sd / 2, zb + sh)))
        for seite, x in (("links", xs - la), ("rechts", xs + la)):
            k.append(quader(f"glashalter_{ri}_laengs_{seite}", "glashalter", (x - sd / 2, y_hint - sd / 2, zb),
                            (x + sd / 2, y_vorn + sd / 2, zb + sh)))
    # --- Arbeitsplatte und Nachbarschraenke ------------------------------
    k.append(quader("arbeitsplatte", "arbeitsplatte", (ap["links_x_m"], -T, H),
                    (ap["rechts_x_m"], -T + ap["tiefe_m"], H + ap["dicke_m"])))
    if ap["links_x_m"] < 0:
        k.append(quader("schrank_links", "schrank", (ap["links_x_m"], -T, 0.0), (0.0, 0.0, H)))
    if ap["rechts_x_m"] > n["breite_m"]:
        k.append(quader("schrank_rechts", "schrank", (n["breite_m"], -T, 0.0), (ap["rechts_x_m"], 0.0, H)))
    zap = H + ap["dicke_m"]
    ablage = [np.array([float(x), float(y), zap + hg / 2.0]) for x, y in m["ablage"]["punkte_xy_m"]]
    gelenke = [
        {"name": "oberkorb_auszug", "typ": "prismatic", "achse": [0, 1, 0], "unten": 0.0,
         "oben": ok["auszug_max_m"], "wert": a_o, "gruppe": "oberkorb"},
        {"name": "unterkorb_auszug", "typ": "prismatic", "achse": [0, 1, 0], "unten": 0.0,
         "oben": uk["auszug_max_m"], "wert": a_u, "gruppe": "unterkorb"},
    ]
    return Szene(m, k, slots, ablage, a_o, a_u, gelenke)


def ueberlappung(a: Koerper, b: Koerper, rand: float = 0.0) -> float:
    """> 0: Koerper durchdringen sich (um mehr als ``-rand``); Zylinder als Quader.

    Fuer Zylinder gegen achsparallele Quader wird zusaetzlich der echte
    Kreisabstand in der Ebene benutzt (Quader-Huelle waere zu grob).
    """
    from rebel_model.collision import obb_penetration

    if a.form == "zylinder" and b.form == "zylinder":
        d = float(np.hypot(*(a.mitte[:2] - b.mitte[:2])))
        radial = a.halb[0] + b.halb[0] - d
        axial = a.halb[2] + b.halb[2] - abs(float(a.mitte[2] - b.mitte[2]))
        return min(radial, axial) + rand
    if a.form == "quader" and b.form == "zylinder":
        a, b = b, a
    if a.form == "zylinder" and np.allclose(b.rot, np.eye(3)):
        lo, hi = b.mitte - b.halb, b.mitte + b.halb
        axial = a.halb[2] + b.halb[2] - abs(float(a.mitte[2] - b.mitte[2]))
        q = np.clip(a.mitte[:2], lo[:2], hi[:2])
        d = float(np.hypot(*(a.mitte[:2] - q)))
        inside = d == 0.0
        if inside:
            radial = a.halb[0] + float(np.min(np.concatenate([a.mitte[:2] - lo[:2], hi[:2] - a.mitte[:2]])))
        else:
            radial = a.halb[0] - d
        return min(radial, axial) + rand
    return float(obb_penetration(a.mitte, a.rot, a.halb + rand / 2.0, b.mitte, b.rot, b.halb + rand / 2.0))
