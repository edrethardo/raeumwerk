"""Erreichbarkeitswerkzeug ``raeumwerk aufbau <aufbau.yaml>``.

Bewertet eine Aufbau-Variante (Roboterfuss, optionale 7. Achse mit Richtung
und Hub, Halterungen, Ablagen) gegen Zielgruppen und schreibt eine
Abdeckungstabelle (Markdown + JSON), die Gelenkmomente beim Korbzug und
Standardbilder. Beschreibung des YAML-Formats: ``docs/aufbau-werkzeug.md``.

Zielgruppen (Verfahren wie in ``spuelmaschine.erreichbarkeit``):

* ``slots``  Glasplaetze im ausgezogenen Oberkorb: Vorposition -> senkrecht
  hinab -> Aushub mit getragenem Glas (``Pruefer.pruefe_ziel``).
* ``ablage`` Glas absetzen auf der Arbeitsplatte bzw. auf Ablageglaesern aus
  ``hindernisse`` (Tisch, Tablett).
* ``teller`` Tellerrand von oben greifen, Vorposition und Aushub senkrecht.
* ``zug``    Korbfront greifen und den Korb ausziehen bzw. einschieben; die
  Kollisionsszene faehrt im 1-cm-Raster mit, Momente aus Zug + Eigengewicht.

Schnell wird es durch: Batch-IK (``rebel_model.schnell``) ueber alle Startposen
eines Ziels, Warmstart entlang der Wege, Zufallsstarts nur bei Fehlschlag,
Prozesse ueber alle Ziele (``--jobs``) und einen Cache je Ziel (Schluessel:
Hash aus Aufbau, Ziel, Konfiguration und Code).
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from rebel_model.config import load as load_robot
from rebel_model.kinematics import transform
from rebel_model.schnell import SchnellChain
from rebel_model.urdf_gen import build_urdf

from . import geometrie, masse
from .erreichbarkeit import ARM, USE, Lage, Pruefer, r_greif, rz

REPO = Path(__file__).resolve().parents[1]
G = 9.81
FINGER_GREIF = {"finger_left", "finger_right", "gripper_base"}
CODE_DATEIEN = ["rebel_model/kinematics.py", "rebel_model/schnell.py", "rebel_model/collision.py",
                "rebel_model/urdf_gen.py", "rebel_model/config.py", "spuelmaschine/geometrie.py",
                "spuelmaschine/erreichbarkeit.py", "spuelmaschine/aufbau.py", "spuelmaschine/masse.py"]
CONFIG_DATEIEN = ["config/robot.yaml", "config/spuelmaschine.yaml", "config/scene_spuelmaschine.yaml"]


# --- Hilfen -------------------------------------------------------------------

def ry(grad: float) -> np.ndarray:
    a = math.radians(grad)
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]])


def rx(grad: float) -> np.ndarray:
    a = math.radians(grad)
    c, s = math.cos(a), math.sin(a)
    return np.array([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]])


def linie(a: np.ndarray, b: np.ndarray, schritt: float = 0.01) -> List[np.ndarray]:
    n = max(1, int(math.ceil(np.linalg.norm(b - a) / schritt - 1e-9)))
    return [a + (b - a) * i / n for i in range(n + 1)]


def r_waagerecht() -> np.ndarray:
    """Werkzeug zeigt waagerecht in die Maschine (-y), Finger schliessen entlang z."""
    z = np.array([0.0, -1.0, 0.0])
    y = np.array([0.0, 0.0, 1.0])
    return np.column_stack([np.cross(y, z), y, z])


def _tief_mischen(basis: Dict, neu: Dict) -> Dict:
    out = copy.deepcopy(basis)
    for k, v in (neu or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _tief_mischen(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _r(v, n=3):
    return [round(float(x), n) for x in v]


def code_hash() -> str:
    h = hashlib.sha256()
    for f in CODE_DATEIEN + CONFIG_DATEIEN:
        h.update(f.encode())
        h.update((REPO / f).read_bytes())
    return h.hexdigest()[:16]


# --- Aufbau -------------------------------------------------------------------

STANDARD = {
    "roboter": {"ursprung_xyz_m": [0.0, 0.0, 0.0], "gier_grad": 0.0, "kipp_grad": 0.0, "neigung_grad": 0.0},
    "achse": {"richtung": "x", "hub_m": None, "schiene": "standard", "podest": False},
    "greifer": {},
    "masse": {},
    "szene": {},
    "hindernisse": [],
    "erlaubt": [],
    "ziele": {},
    "momente": {"zugkraft_n": [20.0, 30.0]},
}


def lade_yaml(pfad: str | Path) -> Dict[str, Any]:
    import yaml

    roh = yaml.safe_load(Path(pfad).read_text(encoding="utf-8")) or {}
    return normalisiere(roh)


def normalisiere(roh: Dict[str, Any]) -> Dict[str, Any]:
    d = _tief_mischen(STANDARD, roh)
    rob = d["roboter"]
    if rob.get("montage") == "haengend":  # Fuss oben, Arm nach unten
        rob["kipp_grad"] = float(rob.get("kipp_grad", 0.0)) + 180.0
    if d["achse"]["richtung"] not in ("x", "y", "z", "keine"):
        raise ValueError(f"achse.richtung {d['achse']['richtung']!r}: erlaubt x, y, z, keine")
    for g in d["ziele"]:
        if g not in ("slots", "teller", "zug", "ablage"):
            raise ValueError(f"unbekannte Zielgruppe {g!r}")
    if d["achse"].get("saeule") is not None and d["achse"]["richtung"] != "z":
        raise ValueError("achse.saeule nur bei achse.richtung z")
    if isinstance(d["ziele"].get("teller"), list):
        teile = [t.get("praefix") for t in d["ziele"]["teller"]]
        if None in teile or len(set(teile)) != len(teile):
            raise ValueError("ziele.teller als Liste: jede Gruppe braucht ein eigenes praefix")
    return d


def senkrechte_achse(d: Dict[str, Any]) -> bool:
    """Vertikale Achse (``richtung: z``): die Achse bleibt senkrecht in der Welt; Kipp, Neigung
    und ``montage: haengend`` drehen nur den Roboter auf dem Schlitten."""
    return d["achse"]["richtung"] == "z"


def montage_matrix(rob: Dict[str, Any]) -> np.ndarray:
    return ry(float(rob["kipp_grad"])) @ rx(-float(rob["neigung_grad"]))


def haengend(d: Dict[str, Any]) -> bool:
    """Roboter kopfueber (Roboter-z zeigt nach unten)."""
    return float(montage_matrix(d["roboter"])[2, 2]) < 0.0


def teller_gruppen(z: Dict[str, Any]) -> List[Dict[str, Any]]:
    """``ziele.teller`` als Liste von Tellergruppen (eine Gruppe oder mehrere mit eigenem praefix)."""
    t = z.get("teller")
    if t is None:
        return []
    return list(t) if isinstance(t, list) else [t]


PLATTE_STANDARD_M = (0.25, 0.25)  # Schlittenplatte bei achse.schiene: platte ohne achse.platte_m


def platten_mass(achse: Dict[str, Any]) -> Tuple[float, float]:
    """Kantenlaengen (x, y im Roboterfuss-System) der Halterplatte bei ``schiene: platte``.
    ``achse.platte_m``: eine Zahl (quadratisch) oder [x, y]; Standard 0,25 x 0,25 m."""
    v = achse.get("platte_m")
    if v is None:
        return PLATTE_STANDARD_M
    if isinstance(v, (int, float)):
        v = [v, v]
    px, py = (float(w) for w in v)
    if px <= 0 or py <= 0:
        raise ValueError(f"achse.platte_m {v!r}: Kantenlaengen muessen > 0 sein")
    return px, py


def ueberstand_m(d: Dict[str, Any], kante_y: float) -> float:
    """Wie weit Fuss bzw. Halterplatte ueber eine Kante bei y = ``kante_y`` (+y = Raum) hinausragen
    (> 0: Ueberstand, <= 0: Abstand hinter der Kante). Fuss als Quader ``fuss_breite_m``, Platte aus
    ``platten_mass``, beide um die Gier des Roboters gedreht; nur stehend, ohne Kipp/Neigung."""
    rob = d["roboter"]
    if abs(float(rob.get("kipp_grad", 0.0))) > 1e-9 or abs(float(rob.get("neigung_grad", 0.0))) > 1e-9:
        raise ValueError("ueberstand_m: nur fuer stehende, nicht geneigte Roboter")
    fb = float(load_robot().arm["fuss_breite_m"])
    masse_xy = [(fb, fb)]
    if d["achse"]["schiene"] == "platte":
        masse_xy.append(platten_mass(d["achse"]))
    g = math.radians(float(rob.get("gier_grad", 0.0)))
    y0 = float(rob["ursprung_xyz_m"][1])
    vorne = max(y0 + 0.5 * (abs(math.sin(g)) * lx + abs(math.cos(g)) * ly) for lx, ly in masse_xy)
    return vorne - kante_y


class Aufbau:
    """Roboter, Kette und Szene einer Aufbau-Beschreibung (YAML als dict)."""

    def __init__(self, d: Dict[str, Any]):
        self.d = d
        self.cfg = load_robot()
        if d["greifer"]:
            self.cfg.greifer.update(d["greifer"])
            g = self.cfg.greifer
            if "griff_ab_spitze_m" in g:  # TCP folgt der Fingerlaenge: Griffpunkt so weit hinter der Spitze
                g["tcp_ab_flansch_m"] = float(g["koerper_laenge_m"]) + float(g["finger_laenge_m"]) \
                    - float(g["griff_ab_spitze_m"])
        self.chain = SchnellChain(self._urdf())
        rob = d["roboter"]
        if senkrechte_achse(d):  # Achse senkrecht, Kipp/Neigung sitzen zwischen Schlitten und Fuss
            R = rz(float(rob["gier_grad"]))
        else:
            R = rz(float(rob["gier_grad"])) @ montage_matrix(rob)
        self.T = transform(R, [float(v) for v in rob["ursprung_xyz_m"]])
        self.lage = _LageT(str(d.get("name", "aufbau")), tuple(float(v) for v in rob["ursprung_xyz_m"]),
                           float(rob["gier_grad"]), self.T)
        self.m0 = _tief_mischen(masse.load(), d["masse"])
        self.sc0 = _tief_mischen(masse.load_szene(), d["szene"])
        self.erlaubt = set(d["erlaubt"])
        self._pruefer: Dict[Tuple, "APruefer"] = {}

    def _urdf(self) -> str:
        import xml.etree.ElementTree as ET

        a = self.d["achse"]
        root = ET.fromstring(build_urdf(self.cfg))
        richtung = a["richtung"]
        if a["schiene"] == "platte":  # nur Schlittenplatte unter dem Fuss, Schiene ausgeblendet (1 cm Wuerfel)
            px, py = platten_mass(a)
            for ln in root.findall("link"):
                n = ln.get("name")
                if n not in ("rail", "carriage"):
                    continue
                for tag in ("visual", "collision"):
                    for el in ln.findall(tag):
                        box, org = el.find("geometry/box"), el.find("origin")
                        if n == "rail":
                            box.set("size", "0.01 0.01 0.01"); org.set("xyz", "0 0 0.005")
                        else:
                            box.set("size", f"{px:g} {py:g} 0.02"); org.set("xyz", "0 0 0.01")
        s = a.get("saeule")
        if s is not None:
            self._saeule_urdf(root, s)
        for j in root.findall("joint"):
            if j.get("name") == "carriage_to_base" and senkrechte_achse(self.d):
                rob = self.d["roboter"]
                org = j.find("origin")
                org.set("rpy", f"{-math.radians(float(rob['neigung_grad'])):.12g} "
                               f"{math.radians(float(rob['kipp_grad'])):.12g} 0")
                if haengend(self.d):  # Fuss haengt unter dem Schlitten, Platte liegt darueber
                    org.set("xyz", "0 0 0")
                continue
            if j.get("name") != "axis7":
                continue
            lim = j.find("limit")
            if richtung in ("z", "keine") or a["schiene"] == "platte":
                j.find("axis").set("xyz", {"x": "1 0 0", "y": "0 1 0", "z": "0 0 1", "keine": "0 0 1"}[richtung])
                j.find("origin").set("xyz", "0 0 0")
                lim.set("lower", "0")
            elif richtung == "y":
                j.find("axis").set("xyz", "0 1 0")
            hub = 0.0 if richtung == "keine" else a.get("hub_m")
            if hub is not None:
                lim.set("upper", str(float(hub)))
        return ET.tostring(root, encoding="unicode")

    def _saeule_urdf(self, root, s: Dict[str, Any]) -> None:
        """Hubachse mit bewegtem Profil (``achse.saeule``): das Profil faehrt mit dem Roboter und
        steht als Quader auf der Schlittenplatte (Link ``carriage``), versetzt um ``versatz_m``
        (Welt x, y ab Fussmitte), Querschnitt ``querschnitt_m``, Laenge ``laenge_m`` (Standard Hub
        + 0,15 m). Der Platzhalter der festen Schiene (Link ``rail``) wandert ueber das Profil
        (Fuehrungswagen am Portal), damit er nicht als Phantom im Arbeitsraum steht."""
        import xml.etree.ElementTree as ET

        rob = self.d["roboter"]
        vx, vy = (float(v) for v in s.get("versatz_m", [0.0, 0.15]))
        g = math.radians(float(rob["gier_grad"]))
        lx, ly = math.cos(g) * vx + math.sin(g) * vy, -math.sin(g) * vx + math.cos(g) * vy
        qx, qy = (float(v) for v in s.get("querschnitt_m", [0.08, 0.08]))
        hub = float(self.d["achse"].get("hub_m") or 0.0)
        L = float(s.get("laenge_m", hub + 0.15))
        cz = 0.02 + L / 2.0
        for ln in root.findall("link"):
            if ln.get("name") == "carriage":
                for tag in ("collision", "visual"):
                    el = ET.SubElement(ln, tag)
                    ET.SubElement(el, "origin", {"xyz": f"{lx:.6g} {ly:.6g} {cz:.6g}", "rpy": "0 0 0"})
                    geo = ET.SubElement(el, "geometry")
                    ET.SubElement(geo, "box", {"size": f"{qx:g} {qy:g} {L:g}"})
            if ln.get("name") == "rail":
                for tag in ("visual", "collision"):
                    for el in ln.findall(tag):
                        box, org = el.find("geometry/box"), el.find("origin")
                        box.set("size", "0.01 0.01 0.01")
                        org.set("xyz", f"{lx:.6g} {ly:.6g} {hub + 0.02 + L:.6g}")

    def masse_fuer(self, extra: Optional[Dict] = None) -> Dict:
        return _tief_mischen(self.m0, extra or {})

    def pruefer(self, ober: float, unter: float, masse_extra: Optional[Dict] = None) -> "APruefer":
        key = (round(ober, 4), round(unter, 4), json.dumps(masse_extra or {}, sort_keys=True))
        if key not in self._pruefer:
            sc = copy.deepcopy(self.sc0)
            sc["pose"]["oberkorb_auszug_m"] = ober
            sc["pose"]["unterkorb_auszug_m"] = unter
            self._pruefer[key] = APruefer(self, sc, self.masse_fuer(masse_extra))
        return self._pruefer[key]


class _LageT(Lage):
    def __init__(self, name, ursprung, gier, T):
        super().__init__(name, ursprung, gier)
        self._T = T

    def matrix(self) -> np.ndarray:
        return self._T.copy()


class APruefer(Pruefer):
    """``Pruefer`` fuer einen beliebigen Aufbau: Achse x/y/z/keine, Halterungen
    und Ablagen aus dem YAML, erlaubte Beruehrungen, schnelle Kollisionspruefung.
    Koerper werden nie aus der Szene entfernt, nur je Pruefung ausgeblendet."""

    def __init__(self, A: Aufbau, sc: Dict, m: Dict):
        self.A = A
        super().__init__(A.lage, sc, m, A.cfg, A.chain)
        self.extra_glaeser: Dict[str, geometrie.Koerper] = {}
        for h in A.d["hindernisse"]:
            if "glas_mitte" in h:
                k = self.szene.glas(h["glas_mitte"], h["name"])
                self.extra_glaeser[h["name"]] = k
            elif h["name"] == "podest":
                continue  # schon in _podest
            else:
                k = geometrie.quader(h["name"], h.get("gruppe", h["name"]), h["lo"], h["hi"])
            self.hindernisse.append(k)
        self._aabb = np.array([h.aabb() for h in self.hindernisse])
        self.achse = A.d["achse"]["richtung"]
        self._achsvektor = {"x": 0, "y": 1, "z": 2}.get(self.achse)
        self._sc_vor()

    def _podest(self) -> Optional[geometrie.Koerper]:
        for h in self.A.d["hindernisse"]:
            if h["name"] == "podest":
                return geometrie.quader("podest", h.get("gruppe", "podest"), h["lo"], h["hi"])
        if self.A.d["achse"].get("podest"):
            return super()._podest()
        return None

    # --- schnelle Kollision (gleiches Ergebnis wie Pruefer.kollisionen) ----------
    def _sc_vor(self) -> None:
        sc = self.self_coll
        self._links = [n for n in self.chain.order if self.chain.links[n].boxes]
        box_of = []
        for li, n in enumerate(self._links):
            box_of += [li] * len(self.chain.links[n].boxes)
        self._box_link = np.array(box_of)
        start = {}
        i = 0
        for n in self._links:
            start[n] = i
            i += len(self.chain.links[n].boxes)
        pa, pb = [], []
        for a, b in sc.pairs:
            for ia in range(len(self.chain.links[a].boxes)):
                for ib in range(len(self.chain.links[b].boxes)):
                    pa.append(start[a] + ia)
                    pb.append(start[b] + ib)
        self._pa, self._pb = np.array(pa, int), np.array(pb, int)
        self._pair_name = [f"{self._links[self._box_link[a]]}|{self._links[self._box_link[b]]}" for a, b in zip(pa, pb)]

    def kollisionen(self, q: np.ndarray, gegriffen: Optional[geometrie.Koerper] = None,
                    getragen: Optional[geometrie.Koerper] = None) -> List[str]:
        from rebel_model.collision import obb_penetration

        wb = self.self_coll.world_boxes(q)
        C, Rr, H = [], [], []
        for n in self._links:
            for c, r, h in wb[n]:
                C.append(c); Rr.append(r); H.append(h)
        C, Rr, H = np.array(C), np.array(Rr), np.array(H)
        ext = np.einsum("nij,nj->ni", np.abs(Rr), H)
        lo, hi = C - ext, C + ext
        hits: List[str] = []
        # Selbstkollision (Rand 0), AABB-Vorfilter vektorisiert
        pa, pb = self._pa, self._pb
        kand = np.nonzero(np.all(lo[pa] <= hi[pb], axis=1) & np.all(lo[pb] <= hi[pa], axis=1))[0]
        for k in kand:
            a, b = pa[k], pb[k]
            if obb_penetration(C[a], Rr[a], H[a], C[b], Rr[b], H[b]) > 0:
                hits.append(self._pair_name[k])
        # Roboter gegen Szene (Rand self.rand), in Weltkoordinaten
        Rw, tw = self.T[:3, :3], self.T[:3, 3]
        Cw = C @ Rw.T + tw
        Rw_b = np.einsum("ij,njk->nik", Rw, Rr)
        extw = np.einsum("nij,nj->ni", np.abs(Rw_b), H)
        lo_w, hi_w = Cw - extw - self.rand, Cw + extw + self.rand
        A = self._aabb
        nah = np.all(A[None, :, 0, :] <= hi_w[:, None, :], axis=2) & np.all(A[None, :, 1, :] >= lo_w[:, None, :], axis=2)
        name_g = gegriffen.name if gegriffen is not None else None
        for bi, hj in zip(*np.nonzero(nah)):
            link = self._links[self._box_link[bi]]
            h = self.hindernisse[hj]
            if h.name == name_g and (getragen is not None or link in ("finger_left", "finger_right")):
                continue
            if link in ("rail", "carriage") and h.name in ("podest", "boden"):
                continue
            rb = geometrie.Koerper(link, "roboter", "quader", Cw[bi], H[bi], Rw_b[bi])
            if geometrie.ueberlappung(rb, h, self.rand) > 0:
                hits.append(f"{link}|{h.name}")
        if getragen is not None:
            glo, ghi = getragen.aabb()
            for h in self.hindernisse:
                if h.name == name_g:
                    continue
                hl, hh = h.aabb()
                if np.any(hl > ghi + self.rand) or np.any(hh < glo - self.rand):
                    continue
                if geometrie.ueberlappung(getragen, h, self.rand) > 0:
                    hits.append(f"glas|{h.name}")
        return sorted(h for h in set(hits) if h not in self.A.erlaubt)

    # --- Startposen und Reichweite fuer jede Achsrichtung -----------------------
    def achswerte(self, pr: np.ndarray) -> List[float]:
        j7 = self.chain.by_name["axis7"]
        if self.achse == "keine" or j7.upper - j7.lower < 1e-9:
            return [0.0]
        i = self._achsvektor
        basis = self.chain.fk(self.chain.zero(), "base_link")[:3, 3]
        if self.achse == "z":
            if haengend(self.A.d):  # kopfueber: Gelenk 2 etwa 0,30 m ueber dem Ziel
                a7 = pr[2] - float(self.j2_0[2]) + 0.30
            else:
                a7 = pr[2] - 0.08  # Gelenk 2 etwas unter dem Ziel
        else:
            a7 = pr[i] - basis[i]
        return [float(np.clip(a7 + d7, j7.lower, j7.upper)) for d7 in (0.0, -0.25, 0.25)]

    def startwerte(self, p: np.ndarray, rng) -> List[np.ndarray]:
        pr = (self.Tinv @ np.append(p, 1.0))[:3]
        out = []
        for a7 in self.achswerte(pr):
            q = self.chain.zero()
            q[self.i7] = a7
            Tb = self.chain.fk(q, "base_link")
            d = Tb[:3, :3].T @ (pr - Tb[:3, 3])  # Richtung zum Ziel im Fusssystem (kopfueber gespiegelt)
            phi = math.atan2(d[1], d[0])
            for j2, j3, j5 in ((30.0, 90.0, 60.0), (0.0, 90.0, 90.0), (50.0, 60.0, 70.0),
                               (-30.0, -90.0, -60.0), (0.0, -90.0, -90.0), (-35.0, -50.0, -90.0)):
                qq = q.copy()
                qq[self.chain.index["joint1"]] = -phi
                qq[self.chain.index["joint2"]] = math.radians(j2)
                qq[self.chain.index["joint3"]] = math.radians(j3)
                qq[self.chain.index["joint5"]] = math.radians(j5)
                out.append(qq)
        for _ in range(4):
            out.append(self.chain.random_q(rng, USE))
        return out

    def zu_weit(self, p: np.ndarray, werkzeug_z: Optional[np.ndarray] = None) -> float:
        """> 0: der TCP-Punkt (Greifer senkrecht) liegt um so viel ausserhalb des Arbeitsraums,
        fuer jede Stellung der 7. Achse: weiter als ``arm`` oder naeher als die Mindestreichweite
        ``arm_min`` (Gelenk 3 am Anschlag) an Gelenk 2. ``werkzeug_z``: Werkzeugachse in Welt
        (Standard senkrecht nach unten); das Handgelenk liegt ``hand`` entgegen dieser Achse."""
        wz = np.array([0.0, 0.0, -1.0]) if werkzeug_z is None else np.asarray(werkzeug_z, float)
        w = (self.Tinv @ np.append(np.asarray(p, float) - self.hand * wz, 1.0))[:3]
        j2 = self.j2_0.copy()
        j7 = self.chain.by_name["axis7"]
        if self.achse != "keine" and j7.upper - j7.lower > 1e-9:
            ax = j7.axis / np.linalg.norm(j7.axis)
            s = float(np.clip(np.dot(w - j2, ax), j7.lower, j7.upper))
            d_min = float(np.linalg.norm(w - (j2 + s * ax)))
            d_max = max(float(np.linalg.norm(w - (j2 + t * ax))) for t in (j7.lower, j7.upper))
        else:
            d_min = d_max = float(np.linalg.norm(w - j2))
        return max(d_min - self.arm, self.arm_min - d_max)

    @property
    def arm_min(self) -> float:
        """Kleinster Abstand Gelenk 2 -> Gelenk 5 (Gelenk 3 an der Grenze, ~0,19 m)."""
        if not hasattr(self, "_arm_min"):
            q = self.chain.zero()
            i3 = self.chain.index["joint3"]
            werte = []
            for g in (self.chain.lower[i3], self.chain.upper[i3]):
                q[i3] = g
                werte.append(float(np.linalg.norm(self.chain.fk(q, "link_5")[:3, 3] - self.chain.fk(q, "link_2")[:3, 3])))
            self._arm_min = min(werte)
        return self._arm_min

    def lage_konflikte(self) -> List[str]:
        if self.podest is None:
            return []
        ign = {"podest", "boden"} | set(self.A.d.get("halter_beruehrt", []))
        return [f"podest|{h.name}" for h in self.hindernisse
                if h.name not in ign and geometrie.ueberlappung(self.podest, h, self.rand) > 0]


# --- IK entlang von Wegen, alle Startposen gleichzeitig ---------------------------

class Loeser:
    def __init__(self, p: APruefer):
        self.p = p
        self.k = p.chain.kette("gripper_base", p.tcp)
        self.ia = [p.chain.index[n] for n in ARM]

    def ziele(self, R: np.ndarray, punkte: Sequence[np.ndarray]) -> np.ndarray:
        out = np.zeros((len(punkte), 4, 4))
        for i, pt in enumerate(punkte):
            out[i] = self.p.Tinv @ transform(R, pt)
        return out

    def loese(self, T: np.ndarray, Q: np.ndarray, rng, restarts: int) -> Tuple[np.ndarray, ...]:
        """Erster Versuch aus Q fuer alle; Zufallsstarts nur fuer die, die nicht konvergieren."""
        q, pe, re, ok = self.k.ik_batch(T, Q, USE)
        for _ in range(restarts):
            bad = np.nonzero(~ok)[0]
            if bad.size == 0:
                break
            Qr = np.array([self._zufall(Q[i], rng) for i in bad])
            q2, pe2, re2, ok2 = self.k.ik_batch(T[bad], Qr, USE)
            besser = ok2 | (pe2 < pe[bad]) | ((pe2 <= pe[bad] + 1e-12) & (re2 < re[bad]))
            b = bad[besser]
            q[b], pe[b], re[b], ok[b] = q2[besser], pe2[besser], re2[besser], ok2[besser]
        return q, pe, re, ok

    def _zufall(self, q0: np.ndarray, rng) -> np.ndarray:
        q = self.p.chain.random_q(rng, USE)
        idx = set(self.p.chain.index[n] for n in USE)
        for i in range(len(q)):
            if i not in idx:
                q[i] = q0[i]
        return q

    def folge(self, T: np.ndarray, Q0: np.ndarray, rng, nachloesen: str = "ungenau",
              sprung_ohne: Sequence[int] = ()) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Warm gestartete IK entlang der Wegpunkte T (L, P, 4, 4) ab Q0 (L, n).

        Liefert (qs (L, P, n), geloest (L,) = Anzahl Wegpunkte bis zum Abriss, sprung (L,) rad).
        ``nachloesen``: 'ungenau' = Zufallsstarts, wenn Fehler > ik_max (wie die Weg-Skripte),
        'nicht_ok' = wenn nicht konvergiert (wie ``Pruefer.weg``)."""
        L, P = T.shape[:2]
        n = Q0.shape[1]
        qs = np.zeros((L, P, n))
        geloest = np.full(L, P)
        sprung = np.zeros(L)
        lebt = np.ones(L, bool)
        q = Q0.copy()
        ik_max = self.p.ik_max
        for i in range(P):
            a = np.nonzero(lebt)[0]
            if a.size == 0:
                break
            qn, pe, re, ok = self.k.ik_batch(T[a, i], q[a], USE)
            # Nachloesen wie die bisherigen Pruefungen: Zufallsstarts landen oft im selben
            # IK-Ast (kein Sprung), wenn der Warmstart an einer Grenze haengen bleibt.
            nach = (pe > ik_max) if nachloesen == "ungenau" else ~ok
            if nach.any():
                b = np.nonzero(nach)[0]
                q2, pe2, re2, ok2 = self.loese(T[a[b], i], q[a[b]], rng, 3)
                qn[b], pe[b], ok[b] = q2, pe2, ok2
            if i and i not in sprung_ohne:
                sp = np.max(np.abs((qn - q[a])[:, self.ia]), axis=1)
                sprung[a] = np.maximum(sprung[a], sp)
            bad = pe > ik_max
            geloest[a[bad]] = i
            lebt[a[bad]] = False
            good = a[~bad]
            qs[good, i] = qn[~bad]
            q[good] = qn[~bad]
        return qs, geloest, sprung


# --- Zielgruppen ---------------------------------------------------------------------

def _ergebnis(name: str, xyz, **kw) -> Dict[str, Any]:
    d = {"ziel": name, "xyz": _r(xyz) if xyz is not None else None, "ok": False, "grund": ""}
    d.update(kw)
    return d


def r_kipp(R: np.ndarray, kipp_grad: float, zum_roboter: Sequence[float]) -> np.ndarray:
    """Greiferlage ``R`` (Werkzeug senkrecht nach unten) um ``kipp_grad`` aus der Senkrechten
    kippen, so dass das Handgelenk zum Roboter (waagerechte Richtung ``zum_roboter``) wandert.
    Drehachse waagerecht, quer zu ``zum_roboter``; 0 = senkrecht, 90 = waagerecht (Seitgriff)."""
    if abs(kipp_grad) < 1e-9:
        return R
    d = np.array([float(zum_roboter[0]), float(zum_roboter[1]), 0.0])
    d /= np.linalg.norm(d)
    u = np.cross([0.0, 0.0, 1.0], d)
    a = math.radians(kipp_grad)
    K = np.array([[0.0, -u[2], u[1]], [u[2], 0.0, -u[0]], [-u[1], u[0], 0.0]])
    return (np.eye(3) + math.sin(a) * K + (1.0 - math.cos(a)) * K @ K) @ R


def pruefe_glas(p: APruefer, name: str, glas: geometrie.Koerper, art: str, gier: Sequence[float],
                seed: int, versuche: int = 6, einsetzen: bool = False,
                kipp: Sequence[float] = (0.0,)) -> Dict[str, Any]:
    """Wie ``Pruefer.pruefe_ziel``, nur alle Startposen eines Gierwinkels als Batch.
    ``einsetzen``: Slot zusaetzlich in Gegenrichtung (Glas getragen hinab in den Platz).
    ``kipp``: Griffrichtungen (Grad aus der Senkrechten, positiv = Handgelenk zum Roboter,
    negativ = vom Roboter weg, siehe ``r_kipp``); schraeg (< 60 Grad) faehrt der gekippte Greifer
    senkrecht an, seitlich entlang seiner Achse; der Aushub bleibt senkrecht."""
    g = p.sc["greifen"]
    rng = np.random.default_rng(seed)
    tcp_z = float(g["tcp_ueber_glasrand_m"])
    p_greif = np.array([glas.mitte[0], glas.mitte[1], glas.mitte[2] - float(glas.halb[2]) + tcp_z])
    zum_roboter = p.T[:2, 3] - p_greif[:2]
    if np.linalg.norm(zum_roboter) < 1e-6:
        zum_roboter = np.array([0.0, 1.0])
    res = _ergebnis(name, glas.mitte, grund="IK ohne Loesung")
    L = Loeser(p)
    offen = p.cfg.finger_hub
    ik_je = False
    p_greif0 = p_greif
    weit_alle = []
    for kw in [float(v) for v in kipp]:
        wz = r_kipp(np.eye(3), kw, zum_roboter)[:, 2] * -1.0  # Werkzeugachse (senkrecht: -z)
        # schraeg: gekippter Greifer faehrt senkrecht an (Finger und Glas gleiten senkrecht
        # in den Halter); seitlich (|kipp| >= 60 Grad): Anfahrt entlang der Werkzeugachse
        anfahrt = wz if abs(kw) >= 60.0 else np.array([0.0, 0.0, -1.0])
        p_greif = p_greif0
        if art == "slot":
            p_vor = p_greif - anfahrt * float(g["vorposition_m"])
            p_aus = p_greif + [0, 0, float(g["aushub_m"])]
            ab, auf = linie(p_vor, p_greif), linie(p_greif, p_aus)[1:]
        else:
            p_greif = p_greif + [0, 0, float(g["absetzen_luft_m"])]
            p_vor = p_greif - anfahrt * float(g["ablage_vorposition_m"])
            ab, auf = linie(p_vor, p_greif), []
        weit = max(p.zu_weit(pt, wz) for pt in ab + auf)
        if weit > 0:
            weit_alle.append(weit)
            continue
        st = p.startwerte(p_vor, rng)
        st = st[:versuche] + st[-4:]
        punkte = ab + auf
        r = _pruefe_glas_lagen(p, L, res, glas, art, gier, kw, zum_roboter, st, offen, ab, punkte, p_greif,
                               p_vor, rng, einsetzen, ik_je)
        ik_je = r
        if res["ok"]:
            return res
    if len(weit_alle) == len(list(kipp)):
        res["grund"] = f"ausserhalb der Reichweite ({min(weit_alle) * 1e3:.0f} mm)"
    return res


def _pruefe_glas_lagen(p, L, res, glas, art, gier, kw, zum_roboter, st, offen, ab, punkte, p_greif, p_vor,
                       rng, einsetzen, ik_je) -> bool:
    """Alle Gierwinkel einer Kipplage; schreibt in ``res``, liefert, ob je eine IK-Loesung kam."""
    ik_je = False
    for gi, gw in enumerate(gier):
        if gi == 1 and not ik_je:
            break
        R = r_kipp(r_greif(gw), kw, zum_roboter)
        Q0all = np.array(st)
        Q0all[:, p.ifg] = offen
        Tv = L.ziele(R, [p_vor])[0]
        Tp = L.ziele(R, punkte)
        extra = int(p.A.d.get("ik", {}).get("zufallsstarts_bei_fehlschlag", 12))
        for stueck in STUECKE(len(Q0all)) + ([None] if extra > 0 else []):
            if stueck is None:  # alle Startposen gescheitert: Zufallsstarts nachlegen (eigener Strom)
                r2 = np.random.default_rng(int(rng.integers(2 ** 31)))
                Qx = np.array([p.chain.random_q(r2, USE) for _ in range(extra)])
                Qx[:, p.ifg] = offen
                Q0all = np.vstack([Q0all, Qx])
                stueck = np.arange(len(Q0all) - extra, len(Q0all))
            qv, pe, _, ok = L.loese(np.repeat(Tv[None], len(stueck), axis=0), Q0all[stueck], rng, 3)
            gut = ok & (pe <= p.ik_max)
            if not gut.any():
                continue
            ik_je = True
            idx = np.nonzero(gut)[0]
            T = np.repeat(Tp[None], idx.size, axis=0)
            qs, geloest, sprung = L.folge(T, qv[idx], rng, "nicht_ok", sprung_ohne=(len(ab),))
            for k in range(idx.size):
                if geloest[k] < len(punkte):
                    if res["grund"] == "IK ohne Loesung":
                        res["grund"] = "IK-Weg abgerissen"
                    continue
                if sprung[k] > p.sprung_max:
                    res.update(grund="Gelenksprung (kein durchgehender Griff)", gier=gw)
                    continue
                hits: List[str] = []
                letzt = len(ab) - 1
                for i, q in enumerate(qs[k]):
                    q = q.copy()
                    q[p.ifg] = offen
                    if i < len(ab) and (art == "slot" or i == letzt):
                        hits += p.kollisionen(q, gegriffen=glas)
                        if einsetzen and art == "slot" and i < letzt:
                            hits += p.kollisionen(q, gegriffen=glas, getragen=p._mitgefuehrt(glas, q, p_greif))
                    else:
                        hits += p.kollisionen(q, gegriffen=glas, getragen=p._mitgefuehrt(glas, q, p_greif))
                hits = sorted(set(hits))
                a7 = qs[k][:, p.i7]
                info = dict(gier=gw, achse7=_r([a7.min(), a7.max()]), q=_r(qs[k][len(ab) - 1], 5),
                            j5_max_grad=round(float(np.degrees(np.max(np.abs(qs[k][:, p.chain.index["joint5"]])))), 1))
                if kw:
                    info["kipp"] = kw
                if hits:
                    res.update(grund="Kollision: " + ", ".join(hits[:4]), kollisionen=hits, **info)
                    continue
                res.update(ok=True, grund="", **info)
                if art == "slot":  # Haltemoment beim Aushub mit Glas (Eigengewicht + Glas)
                    m_glas = float(p.m.get("glas", {}).get("masse_kg", 0.25))
                    res["eigen"] = {n: max(eigen(p, q, m_glas)[n] for q in qs[k][len(ab) - 1:]) for n in ARM}
                return True
    return ik_je


def pruefe_weg(p: APruefer, R: np.ndarray, punkte: List[np.ndarray], rng, ignoriere=None, szenen=None,
               versuche: int = 12) -> Tuple[Dict[str, Any], Optional[np.ndarray]]:
    """Wie die Weg-Pruefung der Machbarkeitsskripte: IK ab mehreren Startposen, dann
    Kollision je Wegpunkt (``szenen(i)`` liefert den Pruefer des Wegpunkts)."""
    senk = np.allclose(R[:, 2], [0, 0, -1])
    weit = max(p.zu_weit(pt) for pt in punkte) if senk else -1
    if weit > 0:
        return {"ok": False, "grund": f"ausser Reichweite ({weit * 1e3:.0f} mm)"}, None
    best: Dict[str, Any] = {"ok": False, "grund": "IK ohne Loesung"}
    best_qs = None
    L = Loeser(p)
    st = p.startwerte(punkte[0], rng)
    st = st[:versuche - 4] + st[-4:]
    Q0 = np.array(st)
    Q0[:, p.ifg] = p.cfg.finger_hub
    T = L.ziele(R, punkte)
    extra = int(p.A.d.get("ik", {}).get("zufallsstarts_bei_fehlschlag", 12))
    stuecke = STUECKE(len(Q0)) + ([None] if extra > 0 else [])
    for stueck in stuecke:
        if stueck is None:  # alle Startposen gescheitert: Zufallsstarts nachlegen (eigener Strom)
            r2 = np.random.default_rng(int(rng.integers(2 ** 31)))
            Qx = np.array([p.chain.random_q(r2, USE) for _ in range(extra)])
            Qx[:, p.ifg] = p.cfg.finger_hub
            Q0 = np.vstack([Q0, Qx])
            stueck = np.arange(len(Q0) - extra, len(Q0))
        qv, pe, _, ok = L.loese(np.repeat(T[0][None], len(stueck), axis=0), Q0[stueck], rng, 3)
        idx = np.nonzero(pe <= p.ik_max)[0]
        if idx.size == 0:
            continue
        qs, geloest, sprung = L.folge(np.repeat(T[None], idx.size, axis=0), qv[idx], rng, "ungenau")
        for k in range(idx.size):
            if geloest[k] < len(punkte):
                best = {"ok": False, "grund": f"IK-Weg abgerissen ({geloest[k]}/{len(punkte)})"}
                continue
            if sprung[k] > p.sprung_max:
                best = {"ok": False, "grund": f"Gelenksprung {math.degrees(sprung[k]):.0f} Grad"}
                continue
            hits = set()
            for i, q in enumerate(qs[k]):
                q = q.copy()
                q[p.ifg] = p.cfg.finger_hub
                pp = szenen(i) if szenen else p
                for hit in pp.kollisionen(q):
                    link, h = hit.split("|", 1)
                    if not (ignoriere and ignoriere(link, h)):
                        hits.add(hit)
            a7 = qs[k][:, p.i7]
            res = {"ok": not hits, "grund": ("Kollision: " + ", ".join(sorted(hits)[:4])) if hits else "",
                   "achse7": _r([a7.min(), a7.max()])}
            if res["ok"]:
                return res, qs[k]
            best, best_qs = res, qs[k]
    return best, best_qs


def STUECKE(n: int) -> List[np.ndarray]:
    """Startposen stueckweise: erst die erste allein (meist reicht sie), dann der Rest als Batch."""
    return [np.arange(0, min(1, n)), np.arange(1, min(4, n)), np.arange(4, n)][: 3 if n > 4 else 2]


def grenzen(cfg) -> Dict[str, Tuple[float, float]]:
    """(Nenn, Max) Nm je Armgelenk aus ``config/robot.yaml`` (untere Werte = konservativ)."""
    return {g.name: (float(g.nennmoment[0]), float(g.max_moment[0])) for g in cfg.gelenke}


def momente(p: APruefer, qs: Sequence[np.ndarray], kraefte: Sequence[float],
            richtung=(0.0, -1.0, 0.0)) -> Dict[str, Any]:
    """Max |tau| je Gelenk ueber den Weg: Zug allein (tau = J^T F), Schwerkraft der Glieder
    (jede Gliedmasse im Schwerpunkt, siehe ``schweremomente``) und |Schwerkraft| + |Zug|."""
    grenze = grenzen(p.cfg)
    out = {}
    tg_list, J_list = [], []
    for q in qs:
        J_list.append(p.chain.jacobian(q, "gripper_base", p.tcp))
        tg_list.append(schweremomente(p, q))
    for F in kraefte:
        Fl = p.Tinv[:3, :3] @ (float(F) * np.asarray(richtung, float))
        zug = {n: 0.0 for n in ARM}
        ges = {n: 0.0 for n in ARM}
        grav = {n: 0.0 for n in ARM}
        ax = 0.0
        for J, tg in zip(J_list, tg_list):
            tau = J[:3].T @ Fl
            for n in ARM:
                i = p.chain.index[n]
                zug[n] = max(zug[n], abs(float(tau[i])))
                grav[n] = max(grav[n], abs(float(tg[i])))
                ges[n] = max(ges[n], abs(float(tau[i])) + abs(float(tg[i])))
            ax = max(ax, abs(float(tau[p.i7] + tg[p.i7])))
        nenn = all(ges[n] <= grenze[n][0] for n in ARM)
        maxi = all(ges[n] <= grenze[n][1] for n in ARM)
        out[f"{F:.0f}N"] = {"zug": {k: round(v, 2) for k, v in zug.items()},
                            "schwerkraft": {k: round(v, 2) for k, v in grav.items()},
                            "gesamt": {k: round(v, 2) for k, v in ges.items()},
                            "achse7_N": round(ax, 1),
                            "urteil": "geht" if nenn else ("knapp (ueber Nenn, unter Max)" if maxi else "geht nicht"),
                            "zug_allein_unter_nenn": all(zug[n] <= grenze[n][0] for n in ARM)}
    return out


# --- Aufgaben ----------------------------------------------------------------------------

def aufgaben(d: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Alle Einzelziele der Beschreibung (je Ziel eine Aufgabe fuer einen Prozess)."""
    A = Aufbau(d)
    out: List[Dict[str, Any]] = []
    z = d["ziele"]
    if "slots" in z:
        cfg = z["slots"] or {}
        p = A.pruefer(float(cfg.get("oberkorb_auszug_m", 0.45)), 0.0)
        for i, gl in enumerate(p.glaeser_korb):
            out.append({"gruppe": "slots", "ziel": f"slot_{i + 1}", "i": i})
    if "ablage" in z:
        cfg = z["ablage"] or {}
        p = A.pruefer(0.0, 0.0)
        if cfg.get("platte", True):
            for i in range(len(p.glaeser_ablage)):
                out.append({"gruppe": "ablage", "ziel": f"platte_{i + 1}", "i": i})
        for n in cfg.get("glaeser", []):
            out.append({"gruppe": "ablage", "ziel": n, "glas": n})
        if cfg.get("seitgriff"):
            for i in range(len(A.m0["ablage"]["punkte_xy_m"])):
                out.append({"gruppe": "ablage", "ziel": f"seit_{i + 1}", "seit": i})
    if "teller" in z:
        tg = teller_gruppen(z)
        for ti, tc in enumerate(tg):
            for name, pt in teller_ziele(A, tc):
                a = {"gruppe": "teller", "ziel": name, "xyz": _r(pt, 4)}
                if isinstance(z["teller"], list):
                    a["teil"] = ti
                out.append(a)
    if "zug" in z:
        cfg = z["zug"] or {}
        for korb in cfg.get("koerbe", ["unterkorb", "oberkorb"]):
            for xg in cfg.get("x_m", [0.30, 0.50]):
                for griff in cfg.get("griffe", ["waagerecht"]):
                    for richtung in cfg.get("richtungen", ["aus", "ein"]):
                        out.append({"gruppe": "zug", "ziel": f"{korb}_x{float(xg):.2f}_{griff}_{richtung}",
                                    "korb": korb, "x": float(xg), "griff": griff, "richtung": richtung})
    return out


def teller_ziele(A: Aufbau, cfg: Dict[str, Any]) -> List[Tuple[str, np.ndarray]]:
    korb = cfg.get("korb", "unterkorb")
    km = A.m0[korb]
    z_rand = km["boden_hoehe_m"] + float(cfg.get("rand_ueber_boden_m", 0.26))
    vorne = km["vorne_eingeschoben_y_m"] + float(cfg.get("auszug_m", 0.45))
    unter = float(cfg.get("greif_unter_rand_m", 0.01))
    praefix = cfg.get("praefix", "t")
    return [(f"{praefix}_{xx:.2f}_{vorne - dy:.2f}", np.array([xx, vorne - dy, z_rand - unter]))
            for xx in cfg.get("x_m", [0.10, 0.20, 0.30, 0.40, 0.50])
            for dy in cfg.get("tiefe_m", [0.04, 0.16, 0.28, 0.40])]


def rechne(A: Aufbau, a: Dict[str, Any]) -> Dict[str, Any]:
    z = A.d["ziele"]
    g = a["gruppe"]
    if g == "slots":
        cfg = z["slots"] or {}
        p = A.pruefer(float(cfg.get("oberkorb_auszug_m", 0.45)), 0.0)
        gl = p.glaeser_korb[a["i"]]
        return pruefe_glas(p, a["ziel"], gl, "slot", [float(v) for v in cfg.get("gier_grad", [0.0, 180.0])], a["i"],
                           einsetzen=bool(cfg.get("einsetzen", False)),
                           kipp=[float(v) for v in cfg.get("kipp_grad", [0.0])])
    if g == "ablage":
        cfg = z["ablage"] or {}
        if "seit" in a:
            return rechne_seitgriff(A, a)
        p = A.pruefer(0.0, 0.0)
        gl = p.glaeser_ablage[a["i"]] if "i" in a else p.extra_glaeser[a["glas"]]
        seed = a.get("i", 0) if "i" in a else len(p.glaeser_ablage) + list(p.extra_glaeser).index(a["glas"])
        return pruefe_glas(p, a["ziel"], gl, "ablage", [float(v) for v in cfg.get("gier_grad", [0, 90, 180, 270])], seed)
    if g == "teller":
        return rechne_teller(A, a)
    if g == "zug":
        return rechne_zug(A, a)
    raise ValueError(g)


def r_seit() -> np.ndarray:
    """Greifer waagerecht in -y (zur Wand), Finger schliessen entlang x (Seitgriff am stehenden Glas)."""
    z = np.array([0.0, -1.0, 0.0])
    y = np.array([1.0, 0.0, 0.0])
    return np.column_stack([np.cross(y, z), y, z])


def rechne_seitgriff(A: Aufbau, a: Dict[str, Any]) -> Dict[str, Any]:
    """Ablage im Seitgriff (Glas aufrecht): TCP in Glasmitte-Hoehe, 10 cm waagerecht von vorn
    anfahren, 2 cm absenken. Hintere Reihe zuerst: in der Szene stehen nur die schon
    abgestellten Glaeser (weiter hinten bzw. in derselben Reihe links) und das Zielglas."""
    cfg = A.d["ziele"]["ablage"]
    pkt = [list(map(float, v)) for v in A.m0["ablage"]["punkte_xy_m"]]
    x, y = pkt[a["seit"]]
    schon = [pp for pp in pkt if pp[1] < y - 1e-9 or (abs(pp[1] - y) < 1e-9 and pp[0] < x - 1e-9)]
    p = A.pruefer(0.0, 0.0, {"ablage": {"punkte_xy_m": schon + [[x, y]]}})
    ziel_name = f"ablage_{len(schon) + 1}"
    zap = p.szene.arbeitsplatte_z
    mitte = float(cfg.get("griff_hoehe_m", 0.055))
    pt = np.array([x, y, zap + mitte + 0.02])
    pts = linie(pt + [0, float(cfg.get("anfahrt_m", 0.10)), 0], pt) + linie(pt, pt - [0, 0, 0.02])[1:]
    rng = np.random.default_rng(5 + a["seit"])

    def ign(link, h):
        return h == ziel_name and link in FINGER_GREIF

    res, qs = pruefe_weg(p, r_seit(), pts, rng, ign)
    res["q"] = None if qs is None else _r(qs[-1], 5)
    if qs is not None:
        res["eigen"] = eigen(p, qs[-1], float(cfg.get("last_kg", 0.25)))
    return {"ziel": a["ziel"], "xyz": [x, y, round(zap + mitte, 3)], **res}


def rechne_teller(A: Aufbau, a: Dict[str, Any]) -> Dict[str, Any]:
    cfg = teller_gruppen(A.d["ziele"])[a.get("teil", 0)]
    korb = cfg.get("korb", "unterkorb")
    aus = float(cfg.get("auszug_m", 0.45))
    extra = None if cfg.get("glashalter", True) else {"glashalter": {"reihen_x_m": []}}
    p = A.pruefer(aus if korb == "oberkorb" else 0.0, aus if korb == "unterkorb" else 0.0, extra)
    pt = np.array(a["xyz"])
    namen = [n for n, _ in teller_ziele(A, cfg)]
    rng = np.random.default_rng(7 + namen.index(a["ziel"]))
    vor, aush = float(cfg.get("vorposition_m", 0.10)), float(cfg.get("aushub_m", 0.30))
    res, qs = {}, None
    for gw in [float(v) for v in cfg.get("gier_grad", [90.0, 0.0])]:
        R = r_greif(gw)
        pts = linie(pt + [0, 0, vor], pt) + linie(pt, pt + [0, 0, aush])[1:]
        res, qs = pruefe_weg(p, R, pts, rng)
        res["gier"] = gw
        if res["ok"]:
            break
    n_vor = len(linie(pt + [0, 0, vor], pt))
    res["q"] = None if qs is None else _r(qs[n_vor - 1], 5)
    if qs is not None and cfg.get("last_kg") is not None:
        res["eigen"] = eigen(p, qs[-1], float(cfg["last_kg"]))
    if "teil" in a:
        res["teil"] = cfg["praefix"]
    return {"ziel": a["ziel"], "xyz": _r(pt), **res}


def schweremomente(p: APruefer, q, last_kg: float = 0.0) -> np.ndarray:
    """Signiertes Schweremoment je aktivem Gelenk (tau = J^T m g), jede Gliedmasse in ihrem
    Schwerpunkt (URDF ``<inertial><origin>``, Annahme Quadermitte), die Last ``last_kg`` im TCP.
    Schiene und Schlitten tragen die Achse, nicht die Armgelenke, und zaehlen nicht."""
    q = np.asarray(q, float)
    g_rob = p.Tinv[:3, :3] @ np.array([0, 0, -G])
    tg = np.zeros(len(q))
    for name, link in p.chain.links.items():
        if link.mass <= 0 or name in ("rail", "carriage"):
            continue
        tg += p.chain.jacobian(q, name, link.com)[:3].T @ (link.mass * g_rob)
    if last_kg:
        tg += p.chain.jacobian(q, "gripper_base", p.tcp)[:3].T @ (last_kg * g_rob)
    return tg


def eigen(p: APruefer, q, last_kg: float = 0.0) -> Dict[str, float]:
    """|Schweremoment| je Armgelenk in Nm (Glieder am Schwerpunkt, Last im TCP)."""
    tg = schweremomente(p, q, last_kg)
    return {n: round(abs(float(tg[p.chain.index[n]])), 2) for n in ARM}


def rechne_zug(A: Aufbau, a: Dict[str, Any]) -> Dict[str, Any]:
    cfg = A.d["ziele"]["zug"] or {}
    korb, xg, griff, richtung = a["korb"], a["x"], a["griff"], a["richtung"]
    km = A.m0[korb]
    z_rand = km["boden_hoehe_m"] + km["wand_hoehe_m"] - 0.003
    y0 = km["vorne_eingeschoben_y_m"] - 0.003
    hub = float(cfg.get("hub_m", km["auszug_max_m"]))
    anf = float(cfg.get("anfahrt_m", 0.08))
    raster = float(cfg.get("szene_raster_m", 0.01))
    p = A.pruefer(0.0, 0.0)
    rng = np.random.default_rng(11)
    if griff == "oben":
        R = r_greif(90.0)
        start = np.array([xg, y0, z_rand + 0.005])
        vor = start + [0, 0, anf]
    else:
        R = r_waagerecht()
        start = np.array([xg, y0, z_rand])
        vor = start + [0, anf, 0]
    zug = linie(start, start + [0, hub, 0])
    pts = linie(vor, start) + zug[1:]
    n_vor = len(linie(vor, start))
    n = len(pts)

    def szene(i):
        if richtung == "ein":
            i = n - 1 - i
        aus = 0.0 if i < n_vor else min(hub, (i - n_vor + 1) * 0.01)
        aus = round(round(aus / raster) * raster, 4)
        return A.pruefer(aus, 0.0) if korb == "oberkorb" else A.pruefer(0.0, aus)

    def ignoriere(link, hname):
        return link in FINGER_GREIF and hname.startswith(korb + "_") and ("vorne" in hname or "rand" in hname)

    if richtung == "ein":
        res, qs = pruefe_weg(szene(0), R, pts[::-1], rng, ignoriere, szene)
        if qs is not None:
            qs = qs[::-1]
    else:
        res, qs = pruefe_weg(p, R, pts, rng, ignoriere, szene)
    if qs is not None and len(qs) == n:
        kr = [float(v) for v in A.d["momente"].get("zugkraft_n", [20.0, 30.0])]
        res["momente"] = momente(p, qs[n_vor - 1:], kr)
        res["q_start"] = _r(qs[n_vor - 1], 5)
        res["q_mitte"] = _r(qs[(n_vor - 1 + n - 1) // 2], 5)
        res["q_ende"] = _r(qs[-1], 5)
    return {"ziel": a["ziel"], "korb": korb, "xyz": _r(start), **res}


# --- Lauf: Cache, Prozesse, Ausgabe ---------------------------------------------------------

_A_CACHE: Dict[str, Aufbau] = {}


def _schluessel(d: Dict[str, Any], a: Dict[str, Any], ch: str) -> str:
    ohne = {k: v for k, v in d.items() if k not in ("name", "beschreibung", "bilder", "vergleich")}
    s = json.dumps({"code": ch, "aufbau": ohne, "aufgabe": a}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(s.encode()).hexdigest()


def _arbeiter(args) -> Tuple[Dict[str, Any], Dict[str, Any], float]:
    d, a = args
    k = json.dumps(d, sort_keys=True)
    if k not in _A_CACHE:
        _A_CACHE.clear()
        _A_CACHE[k] = Aufbau(d)
    t = time.monotonic()
    r = rechne(_A_CACHE[k], a)
    return a, r, time.monotonic() - t


KOSTEN = {"zug": 0, "slots": 1, "teller": 2, "ablage": 3}


def lauf(d: Dict[str, Any], jobs: Optional[int] = None, cache: Optional[Path] = None,
         gruppen: Optional[Sequence[str]] = None, log=print) -> Dict[str, Any]:
    t0 = time.monotonic()
    if gruppen:
        d = copy.deepcopy(d)
        d["ziele"] = {k: v for k, v in d["ziele"].items() if k in gruppen}
    ch = code_hash()
    alle = aufgaben(d)
    ergebnisse: Dict[str, Dict[str, Any]] = {}
    offen = []
    for a in alle:
        key = _schluessel(d, a, ch)
        f = cache / f"{key}.json" if cache else None
        if f is not None and f.is_file():
            ergebnisse[a["ziel"] + "|" + a["gruppe"]] = json.loads(f.read_text(encoding="utf-8"))
        else:
            offen.append((a, f))
    log(f"{len(alle)} Ziele, {len(alle) - len(offen)} aus dem Cache, {len(offen)} zu rechnen")
    jobs = jobs or os.cpu_count() or 1
    offen.sort(key=lambda af: KOSTEN[af[0]["gruppe"]])
    zeiten: Dict[str, float] = {}

    def fertig(a, r, dt, f):
        r["sekunden"] = round(dt, 2)
        ergebnisse[a["ziel"] + "|" + a["gruppe"]] = r
        zeiten[a["gruppe"]] = zeiten.get(a["gruppe"], 0.0) + dt
        if f is not None:
            f.parent.mkdir(parents=True, exist_ok=True)
            tmp = f.with_suffix(".tmp")
            tmp.write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
            tmp.replace(f)
        log(f"  {a['gruppe']:7s} {a['ziel']:34s} {'ok  ' if r['ok'] else 'nein'} {dt:6.1f} s  {r.get('grund', '')[:70]}")

    if offen and jobs > 1 and len(offen) > 1:
        import multiprocessing as mp

        ctx = mp.get_context("fork")
        datei = {json.dumps(a, sort_keys=True): f for a, f in offen}
        with ctx.Pool(min(jobs, len(offen))) as pool:
            for a, r, dt in pool.imap_unordered(_arbeiter, [(d, a) for a, _ in offen], chunksize=1):
                fertig(a, r, dt, datei[json.dumps(a, sort_keys=True)])
    else:
        for a, f in offen:
            a2, r, dt = _arbeiter((d, a))
            fertig(a, r, dt, f)
    gr: Dict[str, List[Dict[str, Any]]] = {}
    for a in alle:
        gr.setdefault(a["gruppe"], []).append(ergebnisse[a["ziel"] + "|" + a["gruppe"]])
    A = Aufbau(d)
    konfl = {}
    for zust in ((0.0, 0.0), (0.45, 0.0), (0.0, 0.45)):
        konfl[f"oberkorb {zust[0]:.2f} / unterkorb {zust[1]:.2f}"] = A.pruefer(*zust).lage_konflikte()
    return {"name": d.get("name", ""), "beschreibung": d.get("beschreibung", ""), "aufbau": d,
            "code": ch, "lage_konflikte": konfl, "ueberstand_kante_m": _ueberstand_platte(A),
            "gruppen": gr, "abdeckung": abdeckung(gr),
            "abgleich": abgleich(d, abdeckung(gr)),
            "laufzeit_s": round(time.monotonic() - t0, 1), "gerechnet": len(offen), "aus_cache": len(alle) - len(offen),
            "rechenzeit_je_gruppe_s": {k: round(v, 1) for k, v in zeiten.items()}, "jobs": jobs}


def _ueberstand_platte(A: Aufbau) -> Optional[float]:
    """Ueberstand von Fuss/Halterplatte ueber die Arbeitsplatten-Vorderkante (m, > 0 = ragt hinaus),
    nur fuer einen stehenden Roboter ohne Achse bzw. mit Platte auf Hoehe der Arbeitsplatte, sonst None."""
    d = A.d
    rob = d["roboter"]
    if d["achse"]["richtung"] != "keine" or abs(float(rob.get("kipp_grad", 0.0))) > 1e-9 \
            or abs(float(rob.get("neigung_grad", 0.0))) > 1e-9:
        return None
    platte = next((h for h in A.pruefer(0.0, 0.0).hindernisse if h.name == "arbeitsplatte"), None)
    if platte is None:
        return None
    lo, hi = platte.aabb()
    if abs(float(rob["ursprung_xyz_m"][2]) - float(hi[2])) > 0.005:  # Fuss steht nicht auf der Platte
        return None
    return round(ueberstand_m(d, float(hi[1])), 4)


def abdeckung(gr: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for g, rows in gr.items():
        if g == "zug":
            for korb in sorted({r["korb"] for r in rows}):
                rr = [r for r in rows if r["korb"] == korb]
                ok = [r["ziel"] for r in rr if r["ok"]]
                out[f"zug_{korb}"] = {"ok": bool(ok), "wege_ok": f"{len(ok)}/{len(rr)}", "gelungen": ok}
            continue
        if g == "ablage":
            for teil, sel in (("ablage_platte", lambda r: r["ziel"].startswith("platte_")),
                              ("ablage_seitgriff", lambda r: r["ziel"].startswith("seit_")),
                              ("ablage_extra", lambda r: not r["ziel"].startswith(("platte_", "seit_")))):
                rr = [r for r in rows if sel(r)]
                if rr:
                    out[teil] = {"ok": sum(r["ok"] for r in rr), "n": len(rr)}
            continue
        if g == "teller" and any("teil" in r for r in rows):  # mehrere Tellergruppen (praefix)
            for teil in dict.fromkeys(r.get("teil") for r in rows):
                rr = [r for r in rows if r.get("teil") == teil]
                out[f"teller_{teil}"] = {"ok": sum(r["ok"] for r in rr), "n": len(rr)}
            continue
        out[g] = {"ok": sum(r["ok"] for r in rows), "n": len(rows)}
    return out


# --- Bericht ------------------------------------------------------------------------------

def abgleich(d: Dict[str, Any], abd: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Vergleich mit den Referenzwerten aus ``vergleich`` im YAML (frueher gerechnete Pruefungen)."""
    out = []
    for k, soll in (d.get("vergleich") or {}).items():
        ist = abd.get(k, {}).get("ok")
        if isinstance(soll, bool):
            diff = 0 if bool(ist) == soll else 1
        else:
            diff = None if ist is None else int(ist) - int(soll)
        out.append({"gruppe": k, "referenz": soll, "werkzeug": ist, "abweichung": diff})
    return out


def bericht_md(e: Dict[str, Any]) -> str:
    z = [f"# Erreichbarkeit: {e['name']}", ""]
    if e.get("beschreibung"):
        z += [e["beschreibung"].strip(), ""]
    rob = e["aufbau"]["roboter"]
    ach = e["aufbau"]["achse"]
    z += [f"- Fuß/Achsursprung {rob['ursprung_xyz_m']} m, Gier {rob['gier_grad']}°, Kipp {rob['kipp_grad']}°, "
          f"Neigung {rob['neigung_grad']}°; Achse {ach['richtung']} (Hub {ach.get('hub_m')} m)",
          f"- Laufzeit {e['laufzeit_s']} s mit {e['jobs']} Prozessen; {e['gerechnet']} Ziele gerechnet, "
          f"{e['aus_cache']} aus dem Cache; Code-Stand {e['code']}",
          f"- Lagekonflikte der Halterung: {json.dumps(e['lage_konflikte'], ensure_ascii=False)}"]
    ub = e.get("ueberstand_kante_m")
    if ub is not None:
        z.append(f"- Fuss/Halterplatte {'ragen ' + format(ub * 1000, '.0f') + ' mm ueber' if ub > 0.0005 else 'enden ' + format(abs(min(ub, 0.0)) * 1000, '.0f') + ' mm hinter'} "
                 f"der Arbeitsplatten-Vorderkante")
    z += ["", "## Abdeckung", "", "| Zielgruppe | erreicht |", "|---|---|"]
    for g, v in e["abdeckung"].items():
        if "n" in v:
            z.append(f"| {g} | {v['ok']}/{v['n']} |")
        else:
            z.append(f"| {g} | {'ja' if v['ok'] else 'nein'} ({v['wege_ok']} Wege: {', '.join(v['gelungen']) or '–'}) |")
    if e.get("abgleich"):
        z += ["", "## Abgleich mit der Referenz", "", "| Zielgruppe | Referenz | Werkzeug | Abweichung |", "|---|---|---|---|"]
        for r in e["abgleich"]:
            z.append(f"| {r['gruppe']} | {r['referenz']} | {r['werkzeug']} | {r['abweichung']} |")
    for g, rows in e["gruppen"].items():
        z += ["", f"## {g}", "", "| Ziel | ok | Grund | Achse 7 m | s |", "|---|---|---|---|---|"]
        for r in rows:
            a7 = r.get("achse7")
            z.append(f"| {r['ziel']} | {'ja' if r['ok'] else 'nein'} | {r.get('grund', '')[:90]} | "
                     f"{'–' if not a7 else f'{a7[0]:.3f}–{a7[1]:.3f}'} | {r.get('sekunden', '')} |")
    zr = [r for r in e["gruppen"].get("zug", []) if r.get("momente")]
    if zr:
        z += ["", "## Momente beim Korbzug (max. über den Zugweg, Nm)", "",
              "Zug allein = |Jᵀ F|, Kraft entlang der Werkzeugachse; gesamt = |Schwerkraft| + |Zug|.", "",
              "| Weg | Kraft | J1 | J2 | J3 | J4 | J5 | J6 | J2 Eigengewicht | J2 gesamt | Urteil gesamt | Zug allein ≤ Nenn |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in zr:
            for k, v in r["momente"].items():
                zu = v["zug"]
                z.append(f"| {r['ziel']}{'' if r['ok'] else ' (Kollision)'} | {k} | " + " | ".join(f"{zu[n]:.1f}" for n in ARM) +
                         f" | {v['schwerkraft']['joint2']:.1f} | {v['gesamt']['joint2']:.1f} | {v['urteil']} | "
                         f"{'ja' if v['zug_allein_unter_nenn'] else 'nein'} |")
    return "\n".join(z) + "\n"


def schreibe(e: Dict[str, Any], out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "ergebnis.json").write_text(json.dumps(e, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "ergebnis.md").write_text(bericht_md(e), encoding="utf-8")
