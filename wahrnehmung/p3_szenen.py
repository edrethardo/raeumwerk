"""Szenen fuer den Kameratag (P3): Ober-/Unterkorb mit zufaelliger Belegung, nur Zahlen (kein Isaac).

Eine Szene (``dict``, JSON-tauglich) beschreibt die Spuelmaschine mit den Koerben (Quader aus
``spuelmaschine.geometrie.baue``), Glaeser/Teller als Objekte, Licht, Nasszustand und Auszug. Daraus
entstehen zwei Sichten auf dieselbe Welt:

* ``prims_aus_szene``: Primitive fuer den Strahlschnitt (``wahrnehmung.sensor``/``griffpose``),
* der Renderer ``scripts/isaac_p3_render.py`` liest dasselbe ``dict`` und baut daraus die USD-Szene.

Belegung und Lagejitter kommen aus ``seed`` (``numpy.random.default_rng``). Der Versuchsplan
``plan`` mischt je Korb Licht x Auszug x Nass gleichmaessig (3 x 2 x 2 = 12 Zellen) und wiederholt ihn.

Annahmen (kein Messwert): Dessertteller O 19 cm, Essteller O 26 cm, Glaeser wie
``config/spuelmaschine.yaml``; Teller stehen hochkant in Tellerstaeben (Normale entlang y) mit
Lagejitter, im Unterkorb zusaetzlich leicht angelehnt (+-8 Grad); Unterkorb-Glaeser stehen kopfueber auf dem
Korbboden. 20 % der Teller sind farbiges Steingut (blau), der Rest weisses Porzellan.
"""
from __future__ import annotations

import copy
import math
from typing import Dict, List, Optional

import numpy as np

from spuelmaschine import geometrie as sg
from spuelmaschine import masse

from .strahlen import Prim

LICHT = ("tag", "kueche", "dunkel")
AUSZUEGE = (0.225, 0.45)          # halb / voll (auszug_max_m 0,45)
NASS = (False, True)
DESSERT_R, ESS_R = 0.095, 0.13
TELLER_DICKE = 0.012              # Prim: flacher Zylinder (Wulst), nicht die Mulde
TELLER_ROT = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0]])   # Normale entlang -y
KOPFUEBER = np.diag([1.0, -1.0, -1.0])
MAST = (0.55, 0.50, 1.35)         # Ensenso C57-6-S, 60 Grad
GRUPPE_MATERIAL = {
    "korpus": "edelstahl", "tuer": "edelstahl", "oberkorb": "korb", "unterkorb": "korb",
    "glashalter": "korb_kunststoff", "tellerhalter": "korb_kunststoff", "arbeitsplatte": "arbeitsplatte_hell",
    "schrank": "schrank_weiss", "boden": "boden",
}


def rx(grad: float) -> np.ndarray:
    a = math.radians(grad)
    return np.array([[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]])


def rz(grad: float) -> np.ndarray:
    a = math.radians(grad)
    return np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]])


def plan(korb: str, n_je_zelle: int = 3, seed0: int = 0) -> List[Dict]:
    """Versuchsplan: je Licht x Auszug x Nass ``n_je_zelle`` Szenen (Belegung zufaellig)."""
    out = []
    k = 0
    for rep in range(n_je_zelle):
        for licht in LICHT:
            for auszug in AUSZUEGE:
                for nass in NASS:
                    out.append({"id": f"{korb}_{k:03d}", "korb": korb, "seed": seed0 + 1000 * rep + k, "licht": licht,
                                "auszug_m": auszug, "nass": nass})
                    k += 1
    return out


def _obj(name, klasse, unter, c, R, r, h, farbe, nass):
    return {"name": name, "klasse": klasse, "unterklasse": unter, "mitte": [float(v) for v in c],
            "rot": [[float(v) for v in row] for row in R], "radius": float(r), "hoehe": float(h),
            "farbe": farbe, "nass": bool(nass)}


def _quader(k: sg.Koerper) -> Dict:
    return {"name": k.name, "gruppe": k.gruppe, "mitte": [float(v) for v in k.mitte],
            "halb": [float(v) for v in k.halb], "rot": [[float(v) for v in row] for row in k.rot]}


def _halter(name, x, y, z0, dicke, quader):
    """Zwei Paar Tellerstaebe beidseits des Tellers (wie ``finger.a1._halter``, vereinfacht)."""
    s, hx, hh = 0.004, 0.05, 0.05
    off = dicke / 2 + 0.002 + s / 2
    i = 0
    for dx in (-hx, hx):
        for dy in (-off, off):
            quader.append({"name": f"{name}_stab_{i}", "gruppe": "tellerhalter",
                           "mitte": [x + dx, y + dy, z0 + hh / 2], "halb": [s / 2, s / 2, hh / 2],
                           "rot": np.eye(3).tolist()})
            i += 1


def baue_szene(spec: Dict) -> Dict:
    """Erzeugt aus ``spec`` (siehe ``plan``) die Szene mit Belegung. ``spec['layout']`` optional
    (Oberkorb: gemischt | glas | teller; Unterkorb: ess_dessert | ess_glas)."""
    rng = np.random.default_rng(int(spec["seed"]))
    korb = spec["korb"]
    nass = bool(spec["nass"])
    m = copy.deepcopy(masse.load())
    glas_r = m["glas"]["durchmesser_m"] / 2.0
    glas_h = m["glas"]["hoehe_m"]
    objekte: List[Dict] = []
    stat_extra: List[Dict] = []
    layout = spec.get("layout")
    if korb == "ober":
        layout = layout or str(rng.choice(["gemischt", "glas", "teller"], p=[0.5, 0.25, 0.25]))
        rows = {"gemischt": [0.48, 0.36], "glas": [0.48, 0.36, 0.24], "teller": []}[layout]
        m["glashalter"] = dict(m["glashalter"], reihen_x_m=rows, slots_je_reihe=4)
        auszug_o, auszug_u = float(spec["auszug_m"]), 0.0
    else:
        layout = layout or str(rng.choice(["ess_dessert", "ess_glas"]))
        m["glashalter"] = dict(m["glashalter"], reihen_x_m=[], slots_je_reihe=4)
        auszug_o, auszug_u = 0.0, float(spec["auszug_m"])
    sz = sg.baue(m, auszug_o, auszug_u)

    def farbe():
        return "steingut_blau" if rng.random() < 0.2 else "porzellan"

    n_gl = n_te = 0
    if korb == "ober":
        for s in sz.slots:               # Glaeser kopfueber auf dem Glashalter
            if rng.random() < 0.65:
                d = rng.uniform(-0.004, 0.004, 2)
                n_gl += 1
                objekte.append(_obj(f"glas_{n_gl}", "glas", "glas", (s[0] + d[0], s[1] + d[1], s[2]),
                                    KOPFUEBER @ rz(float(rng.uniform(-3, 3))), glas_r, glas_h, "klar", nass))
        if layout in ("gemischt", "teller"):
            ok = m["oberkorb"]
            vorne = ok["vorne_eingeschoben_y_m"] + auszug_o
            boden = ok["boden_hoehe_m"]
            xs = [0.15] if layout == "gemischt" else [0.15, 0.40]
            for x0 in xs:
                for k, dy in enumerate([0.07, 0.13, 0.19, 0.25, 0.31, 0.37]):
                    if rng.random() < 0.75:
                        x, y = x0 + rng.uniform(-0.005, 0.005), vorne - dy + rng.uniform(-0.004, 0.004)
                        R = rz(float(rng.uniform(-1.5, 1.5))) @ rx(float(rng.uniform(-1.5, 1.5))) @ TELLER_ROT
                        n_te += 1
                        objekte.append(_obj(f"teller_{n_te}", "teller", "dessert", (x, y, boden + DESSERT_R), R,
                                            DESSERT_R, TELLER_DICKE, farbe(), nass))
                        _halter(f"tellerhalter_{n_te}", x0, y, boden, TELLER_DICKE, stat_extra)
    else:
        uk = m["unterkorb"]
        vorne = uk["vorne_eingeschoben_y_m"] + auszug_u
        boden = uk["boden_hoehe_m"]
        for k in range(9):               # Essteller, linke Haelfte
            if rng.random() < 0.8:
                x, y = 0.17 + rng.uniform(-0.006, 0.006), vorne - 0.05 - 0.05 * k + rng.uniform(-0.004, 0.004)
                tilt = float(rng.uniform(-8, 8))
                R = rz(float(rng.uniform(-2, 2))) @ rx(tilt) @ TELLER_ROT
                n_te += 1
                objekte.append(_obj(f"teller_{n_te}", "teller", "essteller",
                                    (x, y, boden + ESS_R * math.cos(math.radians(tilt)) + 0.004), R, ESS_R,
                                    TELLER_DICKE, farbe(), nass))
                _halter(f"tellerhalter_{n_te}", 0.17, y, boden, TELLER_DICKE, stat_extra)
        if layout == "ess_dessert":      # rechte Haelfte: Dessertteller
            for k in range(8):
                if rng.random() < 0.75:
                    x, y = 0.42 + rng.uniform(-0.006, 0.006), vorne - 0.05 - 0.055 * k + rng.uniform(-0.004, 0.004)
                    tilt = float(rng.uniform(-6, 6))
                    R = rz(float(rng.uniform(-2, 2))) @ rx(tilt) @ TELLER_ROT
                    n_te += 1
                    objekte.append(_obj(f"teller_{n_te}", "teller", "dessert",
                                        (x, y, boden + DESSERT_R * math.cos(math.radians(tilt)) + 0.004), R,
                                        DESSERT_R, TELLER_DICKE, farbe(), nass))
                    _halter(f"tellerhalter_{n_te}", 0.42, y, boden, TELLER_DICKE, stat_extra)
        else:                            # rechte Haelfte: Glaeser kopfueber
            for xg in (0.38, 0.48):
                for k in range(4):
                    if rng.random() < 0.7:
                        x, y = xg + rng.uniform(-0.005, 0.005), vorne - 0.08 - 0.11 * k + rng.uniform(-0.005, 0.005)
                        n_gl += 1
                        objekte.append(_obj(f"glas_{n_gl}", "glas", "glas", (x, y, boden + glas_h / 2 + 0.003),
                                            KOPFUEBER @ rz(float(rng.uniform(-3, 3))), glas_r, glas_h, "klar", nass))
    statisch = [_quader(k) for k in sz.koerper] + stat_extra
    statisch.append({"name": "boden", "gruppe": "boden", "mitte": [0.3, 0.3, -0.01], "halb": [4.0, 4.0, 0.01],
                     "rot": np.eye(3).tolist()})
    return {"id": spec["id"], "korb": korb, "seed": int(spec["seed"]), "licht": spec["licht"],
            "auszug_m": float(spec["auszug_m"]), "nass": nass, "layout": layout, "mast_m": list(MAST),
            "auszug_ober_m": auszug_o, "auszug_unter_m": auszug_u, "objekte": objekte, "statisch": statisch}


def prims_aus_szene(d: Dict) -> List[Prim]:
    """Primitive der Szene (Gruppen wie ``griffpose.prims_aus_welt``: glas, teller, oberkorb, ...)."""
    out: List[Prim] = []
    for k in d["statisch"]:
        if k["gruppe"] == "boden":
            continue
        out.append(Prim(k["name"], k["gruppe"], "box", np.asarray(k["mitte"], float), np.asarray(k["halb"], float),
                        np.asarray(k["rot"], float), k["gruppe"]))
    for o in d["objekte"]:
        r, h = o["radius"], o["hoehe"]
        out.append(Prim(o["name"], o["klasse"], "zyl", np.asarray(o["mitte"], float),
                        np.array([r, r, h / 2.0]), np.asarray(o["rot"], float), o["name"]))
    return out


def kamera(mast=MAST, neigung_grad: float = 60.0):
    """(Ort, Blickpunkt) der Ensenso wie ``griffpose.ensenso_pose_aus`` (hier ohne Import-Zyklus)."""
    from .griffpose import ensenso_pose_aus
    return ensenso_pose_aus(mast, neigung_grad)
