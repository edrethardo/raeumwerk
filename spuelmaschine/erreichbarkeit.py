"""Erreichbarkeit: ReBeL auf der 7. Achse vor der Spuelmaschine.

Fuer eine Schienenlage (Ursprung, Gierwinkel, Podesthoehe) prueft
``Pruefer`` jeden Glas-Slot im ausgezogenen Oberkorb und jeden Ablagepunkt
auf der Arbeitsplatte:

* Glas-Slot (Griff von oben am kopfueber stehenden Glas): Vorposition ->
  senkrecht hinab zur Greifpose -> senkrecht hinauf zum Aushub (Glas getragen).
* Ablagepunkt: Vorposition (Glas getragen) -> senkrecht hinab zum Absetzen.

Jeder Wegpunkt (1 cm Abstand) wird mit der vorhandenen IK
(``rebel_model.kinematics.Chain.ik``, 7. Achse + 6 Armgelenke, Lage und
Orientierung) warm gestartet geloest. Ein Ziel gilt als erreichbar, wenn jeder
Wegpunkt IK-Fehler < ``kollision.ik_fehler_max_m`` hat, kein Gelenk zwischen
zwei Wegpunkten mehr als ``gelenksprung_max_grad`` springt (durchgehender
Griff, kein Umgreifen), keine Selbstkollision auftritt
(``rebel_model.collision.SelfCollision``) und kein Roboterquader -- und kein
getragenes Glas -- der Szene naeher als ``sicherheitsrand_m`` kommt (gleicher
Quadertest nach dem Trennachsensatz).

    python -m spuelmaschine.erreichbarkeit            # gewaehlte Lage pruefen, Tabelle
    python -m spuelmaschine.erreichbarkeit --raster   # Rastersuche ueber alle Lagen
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from rebel_model.collision import SelfCollision, obb_penetration
from rebel_model.config import RobotConfig
from rebel_model.config import load as load_robot
from rebel_model.kinematics import Chain, transform
from rebel_model.urdf_gen import build_urdf

from . import geometrie, masse

ARM = ["joint1", "joint2", "joint3", "joint4", "joint5", "joint6"]
USE = ["axis7"] + ARM
FINGER = {"finger_left", "finger_right"}
SCHIENE_UNTEN = {"rail", "carriage"}


def rz(grad: float) -> np.ndarray:
    a = math.radians(grad)
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def r_greif(gier_grad: float) -> np.ndarray:
    """Greifer senkrecht nach unten; Greifer-y (Schliessrichtung) unter ``gier_grad`` in der Ebene."""
    y = rz(gier_grad) @ np.array([1.0, 0.0, 0.0])
    z = np.array([0.0, 0.0, -1.0])
    x = np.cross(y, z)
    return np.column_stack([x, y, z])


@dataclass
class Lage:
    name: str  # senkrecht_zur_front | parallel_zur_front
    ursprung: Tuple[float, float, float]
    gier_grad: float

    @property
    def hoehe(self) -> float:
        return float(self.ursprung[2])

    def matrix(self) -> np.ndarray:
        return transform(rz(self.gier_grad), self.ursprung)

    def as_dict(self) -> dict:
        return {"lage": self.name, "ursprung_xyz_m": [round(float(v), 4) for v in self.ursprung],
                "gier_grad": self.gier_grad}


def lage_aus_szene(sc: Dict) -> Lage:
    s = sc["schiene"]
    return Lage(s["lage"], tuple(float(v) for v in s["ursprung_xyz_m"]), float(s["gier_grad"]))


@dataclass
class Ziel:
    name: str
    art: str  # slot | ablage
    glas: geometrie.Koerper  # Glas in Ruhelage (im Korb bzw. abgestellt)
    gier: List[float]


@dataclass
class Ergebnis:
    ziel: str
    ok: bool
    grund: str = ""
    gier_grad: Optional[float] = None
    wegpunkte: int = 0
    ik_fehler_max_m: float = math.inf
    winkel_fehler_max_grad: float = math.inf
    gelenksprung_max_grad: float = math.inf
    achse7_m: Tuple[float, float] = (math.nan, math.nan)
    j5_max_grad: float = math.nan
    kollisionen: List[str] = field(default_factory=list)
    q_greif: Optional[List[float]] = None

    def as_dict(self) -> dict:
        d = dict(self.__dict__)
        d["achse7_m"] = [round(float(v), 4) for v in self.achse7_m]
        return d


class Pruefer:
    def __init__(self, lage: Lage, sc: Optional[Dict] = None, m: Optional[Dict] = None,
                 cfg: Optional[RobotConfig] = None, chain: Optional[Chain] = None):
        self.sc = sc or masse.load_szene()
        self.m = m or masse.load()
        self.cfg = cfg or load_robot()
        self.chain = chain or Chain(build_urdf(self.cfg))
        self.lage = lage
        self.T = lage.matrix()
        self.Tinv = np.linalg.inv(self.T)
        pose = self.sc["pose"]
        self.szene = geometrie.baue(self.m, pose["oberkorb_auszug_m"], pose["unterkorb_auszug_m"])
        self.self_coll = SelfCollision(self.chain)
        self.tcp = [0.0, 0.0, float(self.cfg.greifer["tcp_ab_flansch_m"])]
        k, g = self.sc["kollision"], self.sc["greifen"]
        self.rand = float(k["sicherheitsrand_m"])
        self.ik_max = float(k["ik_fehler_max_m"])
        self.sprung_max = math.radians(float(g["gelenksprung_max_grad"]))
        self.ifg = self.chain.index["finger_left"]
        self.i7 = self.chain.index["axis7"]
        self.x0 = float(self.chain.fk(self.chain.zero(), "base_link")[0, 3])
        # Reichweiten-Vorfilter: Handgelenk (J5) liegt bei senkrechtem Greifer
        # ``hand`` ueber dem TCP und hoechstens ``arm`` von Gelenk 2 entfernt
        q0 = self.chain.zero()
        p2 = self.chain.fk(q0, "link_2")[:3, 3]
        p5 = self.chain.fk(q0, "link_5")[:3, 3]
        self.hand = float(np.linalg.norm(self.chain.fk(q0, "gripper_base", self.tcp)[:3, 3] - p5))
        self.arm = float(np.linalg.norm(p5 - p2))
        self.j2_0 = p2
        # Hindernisse: Szene + Glaeser in allen Slots und auf allen Ablagepunkten
        # (konservativ: jedes Ziel wird mit allen anderen Glaesern geprueft)
        self.glaeser_korb = self.szene.glaeser_im_korb()
        self.glaeser_ablage = [self.szene.glas(p, f"ablage_{i + 1}") for i, p in enumerate(self.szene.ablage)]
        self.podest = self._podest()
        boden = geometrie.quader("boden", "boden", (-3, -3, -0.1), (3, 3, 0.0))
        self.hindernisse = list(self.szene.koerper) + self.glaeser_korb + self.glaeser_ablage + [boden]
        if self.podest is not None:
            self.hindernisse.append(self.podest)
        self._aabb = np.array([h.aabb() for h in self.hindernisse])

    # --- Szene -----------------------------------------------------------
    def _podest(self) -> Optional[geometrie.Koerper]:
        h = self.lage.hoehe
        if h <= 1e-9:
            return None
        a7 = self.cfg.achse7
        r = float(self.sc["podest"]["rand_m"])
        L, W = float(a7["laenge_m"]), float(a7["breite_m"])
        mitte_lok = np.array([L / 2.0, 0.0, -h / 2.0])
        mitte = self.T[:3, :3] @ mitte_lok + self.T[:3, 3]
        return geometrie.Koerper("podest", "podest", "quader", mitte,
                                 np.array([L / 2.0 + r, W / 2.0 + r, h / 2.0]), self.T[:3, :3].copy())

    def ziele(self) -> List[Ziel]:
        g = self.sc["greifen"]
        out = [Ziel(f"slot_{i + 1}", "slot", gl, [float(v) for v in g["slot_gier_grad"]])
               for i, gl in enumerate(self.glaeser_korb)]
        out += [Ziel(f"ablage_{i + 1}", "ablage", gl, [float(v) for v in g["ablage_gier_grad"]])
                for i, gl in enumerate(self.glaeser_ablage)]
        return out

    def roboterquader(self, q: np.ndarray, wb=None) -> Dict[str, List[geometrie.Koerper]]:
        R, t = self.T[:3, :3], self.T[:3, 3]
        out = {}
        for link, boxes in (wb or self.self_coll.world_boxes(q)).items():
            out[link] = [geometrie.Koerper(link, "roboter", "quader", R @ c + t, h, R @ r) for c, r, h in boxes]
        return out

    def selbstkollision(self, wb) -> List[str]:
        """Wie ``SelfCollision.collisions`` (gleiche Paare, Rand 0), mit AABB-Vorfilter."""
        aabb = {}
        for link, boxes in wb.items():
            aabb[link] = [(c - np.abs(r) @ h, c + np.abs(r) @ h) for c, r, h in boxes]
        hits = []
        for a, b in self.self_coll.pairs:
            for (c1, r1, h1), (l1, u1) in zip(wb[a], aabb[a]):
                for (c2, r2, h2), (l2, u2) in zip(wb[b], aabb[b]):
                    if np.any(l1 > u2) or np.any(l2 > u1):
                        continue
                    if obb_penetration(c1, r1, h1, c2, r2, h2) > 0:
                        hits.append(f"{a}|{b}")
        return hits

    def kollisionen(self, q: np.ndarray, gegriffen: Optional[geometrie.Koerper] = None,
                    getragen: Optional[geometrie.Koerper] = None) -> List[str]:
        """Treffer als 'A|B'. ``gegriffen``: Glas zwischen den Fingern (Finger
        duerfen es beruehren); ``getragen``: mitgefuehrtes Glas (statt in Ruhelage)."""
        wb = self.self_coll.world_boxes(q)
        hits = self.selbstkollision(wb)
        name_g = gegriffen.name if gegriffen is not None else None
        for link, boxes in self.roboterquader(q, wb).items():
            for rb in boxes:
                lo, hi = rb.aabb()
                lo, hi = lo - self.rand, hi + self.rand
                near = np.where(np.all(self._aabb[:, 0] <= hi, axis=1) & np.all(self._aabb[:, 1] >= lo, axis=1))[0]
                for i in near:
                    h = self.hindernisse[i]
                    if h.name == name_g and (getragen is not None or link in FINGER):
                        continue  # getragen: Ruhelage leer; sonst duerfen die Finger das Glas fassen
                    if link in SCHIENE_UNTEN and h.name in ("podest", "boden"):
                        continue  # Schiene steht auf Podest bzw. Boden
                    if geometrie.ueberlappung(rb, h, self.rand) > 0:
                        hits.append(f"{link}|{h.name}")
        if getragen is not None:
            lo, hi = getragen.aabb()
            for h in self.hindernisse:
                if h.name == name_g:
                    continue
                hl, hh = h.aabb()
                if np.any(hl > hi + self.rand) or np.any(hh < lo - self.rand):
                    continue
                if geometrie.ueberlappung(getragen, h, self.rand) > 0:
                    hits.append(f"glas|{h.name}")
        return sorted(set(hits))

    # --- IK --------------------------------------------------------------
    def tcp_welt(self, q: np.ndarray) -> np.ndarray:
        return self.T @ self.chain.fk(q, "gripper_base", self.tcp)

    def _ik(self, p: np.ndarray, gier: float, q0: np.ndarray, restarts: int, rng) -> Tuple[np.ndarray, float, float, bool]:
        tw = transform(r_greif(gier), p)
        tr = self.Tinv @ tw
        return self.chain.ik(tr, "gripper_base", q0, USE, offset=self.tcp, restarts=restarts, rng=rng,
                             tol_pos=1e-5, tol_rot=1e-4)

    def zu_weit(self, p: np.ndarray) -> float:
        """> 0: TCP-Punkt mit senkrechtem Greifer liegt um so viel ausserhalb der Armreichweite
        (fuer jede Stellung der 7. Achse)."""
        w = (self.Tinv @ np.append(np.asarray(p, float) + [0.0, 0.0, self.hand], 1.0))[:3]
        j7 = self.chain.by_name["axis7"]
        x = float(np.clip(w[0] - self.j2_0[0], j7.lower, j7.upper))
        j2 = self.j2_0 + np.array([x, 0.0, 0.0])
        return float(np.linalg.norm(w - j2) - self.arm)

    def startwerte(self, p: np.ndarray, rng) -> List[np.ndarray]:
        """Startposen: Fuss so nah wie moeglich am Ziel, Arm Richtung Ziel."""
        pr = (self.Tinv @ np.append(p, 1.0))[:3]
        j7 = self.chain.by_name["axis7"]
        a7 = float(np.clip(pr[0] - self.x0, j7.lower, j7.upper))
        out = []
        for d7 in (0.0, -0.25, 0.25):
            q = self.chain.zero()
            q[self.i7] = float(np.clip(a7 + d7, j7.lower, j7.upper))
            base = self.chain.fk(q, "base_link")[:3, 3]
            # joint1 dreht um -z: Winkel so, dass der Arm (Gelenk 2 knickt um y) zum Ziel zeigt
            phi = math.atan2(pr[1] - base[1], pr[0] - base[0])
            for j2, j3, j5 in ((30.0, 90.0, 60.0), (0.0, 90.0, 90.0), (50.0, 60.0, 70.0),
                               (-30.0, -90.0, -60.0), (0.0, -90.0, -90.0), (-35.0, -50.0, -90.0)):
                qq = q.copy()
                qq[self.chain.index["joint1"]] = -phi
                qq[self.chain.index["joint2"]] = math.radians(j2)
                qq[self.chain.index["joint3"]] = math.radians(j3)
                qq[self.chain.index["joint5"]] = math.radians(j5)
                out.append(qq)
        for _ in range(4):  # dazu Zufallsposen (fester Seed), falls keine Haltung passt
            out.append(self.chain.random_q(rng, USE))
        return out  # zuerst alle Haltungen bei Achswert unter dem Ziel

    def weg(self, punkte: Sequence[np.ndarray], gier: float, q_start: np.ndarray,
            rng) -> Tuple[List[np.ndarray], float, float, float, bool]:
        """Warm gestartete IK entlang der Punkte; (qs, pe_max, re_max, sprung_max, ok)."""
        qs, pe_m, re_m, sp_m = [], 0.0, 0.0, 0.0
        q = q_start.copy()
        for i, p in enumerate(punkte):
            qn, pe, re, ok = self._ik(p, gier, q, 0 if i else 0, rng)
            if not ok:
                qn, pe, re, ok = self._ik(p, gier, q, 3, rng)
            if i:
                sp_m = max(sp_m, float(np.max(np.abs((qn - q)[[self.chain.index[n] for n in ARM]]))))
            pe_m, re_m = max(pe_m, pe), max(re_m, re)
            if pe > self.ik_max:
                return qs, pe_m, re_m, sp_m, False
            qs.append(qn)
            q = qn
        return qs, pe_m, re_m, sp_m, True

    def pruefe_ziel(self, z: Ziel, seed: int = 0, versuche: int = 6) -> Ergebnis:
        g = self.sc["greifen"]
        rng = np.random.default_rng(seed)
        r_glas = float(z.glas.halb[2])
        rand_glas = z.glas.mitte[2] - r_glas
        schritt = float(g["wegpunkt_abstand_m"])
        tcp_z = float(g["tcp_ueber_glasrand_m"])

        def linie(a: np.ndarray, b: np.ndarray) -> List[np.ndarray]:
            n = max(1, int(math.ceil(np.linalg.norm(b - a) / schritt - 1e-9)))
            return [a + (b - a) * i / n for i in range(n + 1)]

        p_greif = np.array([z.glas.mitte[0], z.glas.mitte[1], rand_glas + tcp_z])
        if z.art == "slot":
            p_vor = p_greif + [0, 0, float(g["vorposition_m"])]
            p_aus = p_greif + [0, 0, float(g["aushub_m"])]
            ab, auf = linie(p_vor, p_greif), linie(p_greif, p_aus)[1:]
        else:
            p_greif = p_greif + [0, 0, float(g["absetzen_luft_m"])]
            p_vor = p_greif + [0, 0, float(g["ablage_vorposition_m"])]
            ab, auf = linie(p_vor, p_greif), []
        best = Ergebnis(z.name, False, "IK ohne Loesung")
        weit = max(self.zu_weit(p) for p in ab + auf)
        if weit > 0:
            best.grund = f"ausserhalb der Reichweite ({weit * 1e3:.0f} mm)"
            return best
        offen = self.cfg.finger_hub
        ik_je = False
        st = self.startwerte(p_vor, rng)
        for gi_, gier in enumerate(z.gier):
            if gi_ == 1 and not ik_je:
                break  # senkrechter Greifer: Gierwinkel aendert nur J6 -> IK fuer alle unloesbar
            for q0 in st[:versuche] + st[-4:]:
                q0 = q0.copy()
                q0[self.ifg] = offen
                qv, pe, re, ok = self._ik(p_vor, gier, q0, 3, rng)
                if not ok or pe > self.ik_max:
                    continue
                ik_je = True
                qs_ab, pe1, re1, sp1, ok1 = self.weg(ab, gier, qv, rng)
                if not ok1:
                    best = _besser(best, Ergebnis(z.name, False, "IK-Weg abgerissen", gier, len(qs_ab), pe1, math.degrees(re1)))
                    continue
                qs_auf, pe2, re2, sp2, ok2 = self.weg(auf, gier, qs_ab[-1], rng) if auf else ([], 0.0, 0.0, 0.0, True)
                if not ok2:
                    best = _besser(best, Ergebnis(z.name, False, "IK-Weg abgerissen", gier, len(qs_ab) + len(qs_auf), max(pe1, pe2)))
                    continue
                sprung = max(sp1, sp2)
                res = Ergebnis(z.name, False, "", gier, len(qs_ab) + len(qs_auf), max(pe, pe1, pe2),
                               math.degrees(max(re, re1, re2)), math.degrees(sprung))
                # Kollisionen: Abfahrt mit Glas in Ruhelage (Slot) bzw. getragen (Ablage),
                # Aushub mit getragenem Glas
                hits: List[str] = []
                letzt = len(qs_ab) - 1
                for i, q in enumerate(qs_ab):
                    q = q.copy()
                    q[self.ifg] = offen
                    if z.art == "slot" or i == letzt:
                        # Slot: Glas steht noch im Korb; Ablage letzter Punkt: Glas abgesetzt
                        hits += self.kollisionen(q, gegriffen=z.glas)
                    else:
                        hits += self.kollisionen(q, gegriffen=z.glas, getragen=self._mitgefuehrt(z.glas, q, p_greif))
                for q in qs_auf:
                    q = q.copy()
                    q[self.ifg] = offen
                    hits += self.kollisionen(q, gegriffen=z.glas, getragen=self._mitgefuehrt(z.glas, q, p_greif))
                res.kollisionen = sorted(set(hits))
                alle = qs_ab + qs_auf
                a7 = [float(q[self.i7]) for q in alle]
                res.achse7_m = (min(a7), max(a7))
                res.j5_max_grad = max(abs(math.degrees(float(q[self.chain.index["joint5"]]))) for q in alle)
                res.q_greif = [round(float(v), 6) for v in qs_ab[-1]]
                if sprung > self.sprung_max:
                    res.grund = "Gelenksprung (kein durchgehender Griff)"
                elif res.kollisionen:
                    res.grund = "Kollision: " + ", ".join(res.kollisionen[:4])
                else:
                    res.ok = True
                    return res
                best = _besser(best, res)
        return best

    def _mitgefuehrt(self, glas: geometrie.Koerper, q: np.ndarray, p_greif: np.ndarray) -> geometrie.Koerper:
        """Getragenes Glas: Lage folgt dem TCP (``p_greif`` = TCP, wenn das Glas in Ruhelage steht)."""
        p = self.tcp_welt(q)[:3, 3]
        mitte = glas.mitte + (p - p_greif)
        return geometrie.Koerper(glas.name + "_getragen", "glas", "zylinder", mitte, glas.halb.copy())

    def lage_konflikte(self) -> List[str]:
        """Podest (mit Rand) gegen die Szene; die Schiene prueft ``kollisionen`` je Pose."""
        if self.podest is None:
            return []
        return [f"podest|{h.name}" for h in self.hindernisse
                if h.name not in ("podest", "boden") and geometrie.ueberlappung(self.podest, h, self.rand) > 0]

    def pruefe(self, fail_fast: bool = False, seed: int = 0) -> List[Ergebnis]:
        out = []
        konflikt = self.lage_konflikte()
        for i, z in enumerate(self.ziele()):
            e = Ergebnis(z.name, False, "Podest kollidiert: " + ", ".join(konflikt), kollisionen=konflikt) \
                if konflikt else self.pruefe_ziel(z, seed + i)
            out.append(e)
            if fail_fast and not e.ok:
                break
        return out


def _besser(a: Ergebnis, b: Ergebnis) -> Ergebnis:
    """Behaelt den aussagekraeftigeren Fehlversuch (weiter gekommen, weniger Kollisionen)."""
    ka = (a.wegpunkte, -len(a.kollisionen))
    kb = (b.wegpunkte, -len(b.kollisionen))
    return b if kb > ka else a


# --- Rastersuche -----------------------------------------------------------

def kandidaten(sc: Dict) -> List[Lage]:
    r = sc["raster"]
    out = []
    for h in r["hoehe_m"]:
        for x in r["senkrecht_x_m"]:
            for y in r["senkrecht_y_m"]:
                out.append(Lage("senkrecht_zur_front", (float(x), float(y), float(h)), 90.0))
        for y in r["parallel_y_m"]:
            for x in r["parallel_x_m"]:
                out.append(Lage("parallel_zur_front", (float(x), float(y), float(h)), 0.0))
    return out


def _bewerte(args) -> dict:
    lage, seed = args
    t = time.monotonic()
    p = Pruefer(lage)
    # schwerste Ziele zuerst (fruehes Aus spart Zeit): Ablage, dann Slots von hinten
    ziele = p.ziele()
    ziele = [z for z in ziele if z.art == "ablage"][::-1] + [z for z in ziele if z.art == "slot"][::-1]
    res = []
    konflikt = p.lage_konflikte()
    if konflikt:
        res = [Ergebnis(ziele[0].name, False, "Podest kollidiert: " + ", ".join(konflikt[:3]))]
    for i, z in enumerate(ziele if not konflikt else []):
        e = p.pruefe_ziel(z, seed + i)
        res.append(e)
        if not e.ok:
            break
    ok = len(res) == len(ziele) and all(e.ok for e in res)
    return {"lage": lage.as_dict(), "ok": ok, "geprueft": len(res), "ziele": len(ziele),
            "erster_fehler": None if ok else {"ziel": res[-1].ziel, "grund": res[-1].grund,
                                               "ik_fehler_mm": _mm(res[-1].ik_fehler_max_m)},
            "j5_max_grad": max((e.j5_max_grad for e in res if e.ok), default=None) if ok else None,
            "sekunden": round(time.monotonic() - t, 1)}


def _mm(v: float) -> Optional[float]:
    return None if not math.isfinite(v) else round(v * 1e3, 4)


def rastersuche(sc: Dict, prozesse: int = 4) -> List[dict]:
    seed = int(sc["raster"]["seed"])
    jobs = [(lage, seed) for lage in kandidaten(sc)]
    if prozesse > 1:
        from multiprocessing import Pool

        with Pool(prozesse) as pool:
            return pool.map(_bewerte, jobs, chunksize=1)
    return [_bewerte(j) for j in jobs]


def waehle(raster: List[dict]) -> Optional[dict]:
    """Lage mit den meisten erfolgreichen Nachbarn im Raster (+-5 cm Lage, +-5 cm
    Hoehe; Abstand zur Grenze des machbaren Bereichs), dann niedrigstes Podest,
    dann kleinste J5-Auslenkung."""
    ok = [r for r in raster if r["ok"]]
    if not ok:
        return None

    def nachbarn(r: dict) -> int:
        a = r["lage"]
        n = 0
        for s in ok:
            b = s["lage"]
            if s is r or a["lage"] != b["lage"]:
                continue
            d = np.abs(np.array(a["ursprung_xyz_m"]) - np.array(b["ursprung_xyz_m"]))
            n += int(np.all(d <= 0.05 + 1e-9))
        return n

    for r in ok:
        r["nachbarn_ok"] = nachbarn(r)
    return min(ok, key=lambda r: (-r["nachbarn_ok"], r["lage"]["ursprung_xyz_m"][2], r["j5_max_grad"]))


def tabelle(ergebnisse: List[Ergebnis]) -> str:
    zeilen = ["| Ziel | erreichbar | Gier ° | Wegpunkte | IK-Fehler max. mm | Winkelfehler max. ° | "
              "Gelenksprung max. ° | Achse 7 m | J5 max. ° | Kollisionen |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for e in ergebnisse:
        zeilen.append(
            f"| {e.ziel} | {'ja' if e.ok else 'nein: ' + e.grund} | {e.gier_grad if e.gier_grad is not None else '–'} | "
            f"{e.wegpunkte} | {_fmt(e.ik_fehler_max_m * 1e3, 4)} | {_fmt(e.winkel_fehler_max_grad, 4)} | "
            f"{_fmt(e.gelenksprung_max_grad, 2)} | {_fmt(e.achse7_m[0], 3)}–{_fmt(e.achse7_m[1], 3)} | "
            f"{_fmt(e.j5_max_grad, 1)} | {len(e.kollisionen) or 'keine'} |")
    return "\n".join(zeilen)


def _fmt(v: float, n: int) -> str:
    return "–" if v is None or not math.isfinite(v) else f"{v:.{n}f}"


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--raster", action="store_true", help="Rastersuche ueber alle Kandidaten")
    ap.add_argument("--prozesse", type=int, default=4)
    ap.add_argument("--out", help="JSON-Ausgabe")
    args = ap.parse_args(argv)
    sc = masse.load_szene()
    if args.raster:
        t = time.monotonic()
        raster = rastersuche(sc, args.prozesse)
        wahl = waehle(raster)
        for r in raster:
            print(json.dumps(r, ensure_ascii=False))
        print("WAHL", json.dumps(wahl, ensure_ascii=False))
        print(f"Dauer {time.monotonic() - t:.0f} s, {sum(r['ok'] for r in raster)}/{len(raster)} Lagen ok")
        if args.out:
            with open(args.out, "w", encoding="utf-8") as fh:
                json.dump({"raster": raster, "wahl": wahl}, fh, ensure_ascii=False, indent=1)
        return 0 if wahl else 1
    lage = lage_aus_szene(sc)
    p = Pruefer(lage, sc)
    res = p.pruefe(seed=int(sc["raster"]["seed"]))
    print("Lage:", json.dumps(lage.as_dict(), ensure_ascii=False))
    print(tabelle(res))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump({"lage": lage.as_dict(), "ergebnisse": [e.as_dict() for e in res]}, fh, ensure_ascii=False, indent=1)
    return 0 if all(e.ok for e in res) else 1


if __name__ == "__main__":
    sys.exit(main())
