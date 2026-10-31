"""Tellergriff-Varianten: Kollisionsform der Finger aus Parametern (``varianten.yaml``).

Jede Variante besteht aus Zinken, das sind Kopien der Fingerkontur aus ``finger.kollision``
(mit eigenen Parametern, z. B. schmaler), die quer zur Schliessrichtung (x im Fingersystem)
nebeneinander liegen, und optional einem Steg (Joch) zwischen ihnen. Eine Zinke bei x = d
wird um den Bogenstich ``r - sqrt(r^2 - d^2)`` des Tellerrands verlaengert, damit ihre Lippe
genauso tief unter dem Wulst liegt wie die der mittigen Zinke.

Fingersystem wie ``finger.kollision``: Ursprung Mitte der Anschlussflaeche, z zur Spitze,
y zum Greifgut, x quer (m).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from spuelmaschine import masse

from .. import kollision as FK
from ..parameter import Finger

DATEI = Path(__file__).resolve().parent / "varianten.yaml"


@dataclass
class Variante:
    name: str
    beschreibung: str
    finger: Dict[str, Any]
    zinken_x_mm: List[float]
    joch: Optional[Dict[str, float]]
    greifkraft_n: float
    tempo: float = 1.0
    zusatz: Dict[str, Any] = field(default_factory=dict)

    def zinke(self) -> Finger:
        """Fingerparameter einer Zinke (``config/finger.yaml`` mit den Ueberschreibungen)."""
        return Finger.laden(**self.finger)

    def breite_m(self) -> float:
        """Gesamtbreite quer (Huelle aller Zinken), fuer den Kollisionsquader der Planung."""
        b = self.zinke().b
        xs = self.zinken_x_mm
        return (max(xs) - min(xs) + b) * 1e-3


def laden(path: Optional[Path] = None) -> Dict[str, Variante]:
    d = masse.werte(masse.roh(path, DATEI))
    out = {}
    for name, v in d["varianten"].items():
        out[name] = Variante(name, str(v["beschreibung"]), dict(v.get("finger") or {}),
                             [float(x) for x in v["zinken_x_mm"]], v.get("joch"), float(v["greifkraft_n"]),
                             float(v.get("tempo", 1.0)))
    return out


def bogenstich_mm(r_mm: float, x_mm: float) -> float:
    """Wie weit der Tellerrand bei x neben dem Scheitel tiefer liegt (mm)."""
    return r_mm - math.sqrt(max(r_mm * r_mm - x_mm * x_mm, 0.0))


def quader(v: Variante, teller_r_m: float) -> List[FK.Quader]:
    """Kollisionsquader aller Zinken (+ Joch) im Fingersystem (m)."""
    f = v.zinke()
    basis = FK.quader(f)
    out: List[FK.Quader] = []
    r_mm = teller_r_m * 1e3
    for k, x in enumerate(v.zinken_x_mm):
        dz = bogenstich_mm(r_mm, x)
        for q in basis:
            m = q.mitte.copy()
            h = q.halb.copy()
            m[0] += x * 1e-3
            if q.name in ("platte", "schaft_1"):
                pass
            else:
                # Zinke verlaengern: alles ab der Verjuengung um den Bogenstich zur Spitze schieben,
                # der Schaft davor wird entsprechend laenger
                if q.name == "schaft_2":
                    h[2] += dz * 1e-3 / 2.0
                    m[2] += dz * 1e-3 / 2.0
                else:
                    m[2] += dz * 1e-3
            out.append(FK.Quader(f"z{k}_{q.name}", m, h, q.rot.copy(), q.weich))
    if v.joch and len(v.zinken_x_mm) > 1:
        x0, x1 = min(v.zinken_x_mm), max(v.zinken_x_mm)
        z0, z1 = float(v.joch["z_von_mm"]), float(v.joch["z_bis_mm"])
        dck = f.dicke(z1)
        lo = np.array([x0, -dck, z0]) * 1e-3
        hi = np.array([x1, 0.0, z1]) * 1e-3
        out.append(FK.Quader("joch", (lo + hi) / 2.0, (hi - lo) / 2.0, np.eye(3), False))
    return out


def lippen_unter_rand_mm(v: Variante, teller_r_m: float, spitze_unter_rand_mm: float) -> List[float]:
    """Je Zinke: Abstand Lippenoberkante (Kerbenende) unter dem oertlichen Tellerrand (mm).
    Der TCP-Bezug ist der Scheitel; die Spitze der mittigen Zinke liegt ``spitze_unter_rand_mm``
    unter dem Scheitel."""
    f = v.zinke()
    out = []
    for x in v.zinken_x_mm:
        dz = bogenstich_mm(teller_r_m * 1e3, x)
        spitze = spitze_unter_rand_mm + dz             # unter dem Scheitel
        lippe_oben = spitze - (f.L - f.lippe[0])      # Kerbenende = Lippenanfang
        out.append(lippe_oben - dz)                   # unter dem oertlichen Rand
    return out


def joch_ueber_rand_mm(v: Variante, spitze_unter_rand_mm: float) -> Optional[float]:
    """Abstand Unterkante Joch ueber dem Scheitel des Tellerrands (mm), None ohne Joch."""
    if not v.joch or len(v.zinken_x_mm) < 2:
        return None
    f = v.zinke()
    return float(f.L - spitze_unter_rand_mm - float(v.joch["z_bis_mm"]))


def formen_anlegen(lauf, b, bl, shape_cfg, quader_liste: List[FK.Quader]) -> set:
    """Wie ``finger.sim.FingerLauf.finger_formen``, aber mit einer beliebigen Quaderliste."""
    from spuelmaschine.stabilitaet import quat_aus_matrix

    newton, wp = lauf.ctx["newton"], lauf.ctx["wp"]
    f = lauf.finger
    k = f.p["kontakt"]
    aus = ~int(newton.ShapeFlags.COLLIDE_SHAPES)
    seiten = {bl["finger_left"]: 1.0, bl["finger_right"]: -1.0}
    fest = {bl[n] for n in ("rail", "carriage") if n in bl}
    for s in range(b.shape_count):
        if b.shape_body[s] in seiten or b.shape_body[s] in fest:
            b.shape_flags[s] = int(b.shape_flags[s]) & aus
    fd = float(lauf.cfg.greifer["finger_dicke_m"])
    iv = float(f.p["anschluss"]["innen_versatz_mm"]) * 1e-3
    formen = set()
    for body, sign in seiten.items():
        M = np.diag([-1.0, -1.0, 1.0]) if sign > 0 else np.eye(3)
        off = np.array([0.0, -sign * (fd / 2.0 + iv), 0.0])
        for q in quader_liste:
            c = M @ q.mitte + off
            R = M @ q.rot
            mu = float(k["reibung_auflage"] if q.weich else k["reibung_finger"])
            s = b.add_shape_box(body, xform=wp.transform(tuple(float(x) for x in c), quat_aus_matrix(R)),
                                hx=float(q.halb[0]), hy=float(q.halb[1]), hz=float(q.halb[2]),
                                cfg=shape_cfg(mu, 0.0), label=f"finger_{q.name}")
            formen.add(s)
    return formen
