"""Greifen mit den eigenen 100-mm-Fingern im Aufbau A1-S1 (Arm auf der Spuelmaschine).

Szene und Erreichbarkeit aus ``beispiele/auf-maschine-korb-aus-finger100.yaml``
(``spuelmaschine.aufbau``), Ablauf wie das Ausraeumen (``ausraeumen.plan``,
``ausraeumen.sim_newton``), angepasst an den Aufbau ohne 7. Achse:

    glaeser   8 Glaeser kopfueber aus den erreichbaren Plaetzen, Umgreifen ueber
              eine Matte (Seitgriff, Gelenk 6 um 180 Grad), aufrecht auf die Platte
    teller    6 Teller hochkant am Rand greifen (Wulst in der Fingerkerbe),
              senkrecht heraus, hochkant in einen Tellerstaender auf der Platte

Die Finger sind in der Simulation die Kollisionsquader aus ``finger.kollision``
(gleiche Parameter wie das CAD), mit weichen Auflagen und harten Flanken/Lippen.
Szenario-Werte: ``config/finger_a1.yaml``.
"""
from __future__ import annotations

import copy
import json
import math
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ausraeumen import bewertung as ab
from ausraeumen import geometrie as ag
from ausraeumen import konfig
from ausraeumen.plan import GlasPlan, Halt, Lagezustand, Planer, PlanFehler
from spuelmaschine import aufbau as AU
from spuelmaschine import geometrie as sg
from spuelmaschine import masse
from spuelmaschine.erreichbarkeit import r_greif, rz

from .parameter import Finger

REPO = Path(__file__).resolve().parents[1]
DATEI = REPO / "config" / "finger_a1.yaml"
CAD_JSON = REPO / "cad" / "finger" / "finger_100.json"
ERLAUBT = {"rail|podest", "carriage|podest", "rail|arbeitsplatte", "carriage|arbeitsplatte",
           "base_link|podest", "base_link|arbeitsplatte"}
TELLER_ROT = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0]])  # Zylinderachse -> -y? (z -> y)


def szenario(path=None) -> Dict[str, Any]:
    return masse.werte(masse.roh(path, DATEI))


def finger_masse_kg(f: Finger) -> float:
    vol = None
    if CAD_JSON.exists():
        vol = float(json.loads(CAD_JSON.read_text())["volumen_finger_mm3"])
    return f.masse_g(f.gewaehlt, vol) / 1000.0


def aufbau(sz: Dict[str, Any], f: Finger) -> AU.Aufbau:
    d = AU.lade_yaml(REPO / sz["aufbau"])
    g = sz["greifer"]
    d["greifer"].update({"finger_breite_m": float(g["finger_breite_m"]), "finger_dicke_m": float(g["finger_dicke_m"]),
                         "finger_masse_kg": round(finger_masse_kg(f), 4)})
    return AU.Aufbau(d)


def abweichung(n: int, rng: Optional[np.random.Generator] = None, versatz=0.005, gier=3.0, auszug=0.01,
               verklemmt: Optional[int] = None) -> konfig.Abweichung:
    if rng is None:
        return konfig.Abweichung([(0.0, 0.0)] * n, [0.0] * n, 0.0, verklemmt)
    # Korbauszug: der Korb steht am Anschlag (voll ausgezogen), Abweichung nur nach innen
    return konfig.Abweichung([tuple(float(v) for v in rng.uniform(-versatz, versatz, 2)) for _ in range(n)],
                             [float(v) for v in rng.uniform(-gier, gier, n)], -abs(float(rng.uniform(-auszug, auszug))),
                             verklemmt)


def _ausraeum_cfg(sz: Dict[str, Any], f: Finger, art: str) -> Dict[str, Any]:
    a = copy.deepcopy(konfig.load())
    a["ablauf"]["ruhepose_grad"] = dict(sz["ablauf"]["ruhepose_grad"])
    a["ablauf"]["ruhepose_achse7_m"] = 0.0
    a["planung"].update({k: v for k, v in sz.get("planung", {}).items()})
    a["greifer"]["greifkraft_n"] = float(f.p["greifkraft"]["sim_n"])
    a["greifer"]["finger_breite_m"] = float(sz["greifer"]["finger_breite_m"])
    if "umdrehen_anteil" in sz["greifer"]:
        a["greifer"]["umdrehen_anteil"] = float(sz["greifer"]["umdrehen_anteil"])
    if art == "glaeser":
        gl = sz["glaeser"]
        a["ablauf"]["zuordnung"] = [list(v) for v in gl["zuordnung"]]
        a["zwischenablage"]["matten_xy_m"] = [list(v) for v in gl["matten_xy_m"]]
        a["zwischenablage"]["je_ablage"] = list(gl["je_ablage"])
        a["zwischenablage"]["oberkante_m"] = float(a["zwischenablage"]["oberkante_m"]) + max(
            [float(v) for v in gl["matte_sockel_m"]] if isinstance(gl["matte_sockel_m"], list) else [float(gl["matte_sockel_m"])])
        a["zwischenablage"]["vorposition_m"] = float(gl["matte_vorposition_m"])
        a["seitgriff"]["vorposition_m"] = float(gl["seitgriff_vorposition_m"])
        a["seitgriff"]["rueckzug_m"] = float(gl["seitgriff_rueckzug_m"])
        a["seitgriff"]["absetzen_luft_m"] = float(gl["absetzen_luft_m"])
    else:
        a["ablauf"]["zuordnung"] = [list(v) for v in sz["teller"]["zuordnung"]]
        a["bewertung"].update({k: v for k, v in sz["bewertung"].items()})
    return a


# --- Welt ---------------------------------------------------------------------------

def _statisch(p) -> List[sg.Koerper]:
    return [k for k in p.hindernisse if k.gruppe != "glas" and not k.name.startswith(("slot_", "ablage_"))]


def _erledigt(start: List[sg.Koerper], ziel: List[sg.Koerper], zuordnung, erledigt) -> None:
    """Schon abgeraeumte Objekte (1-basiert) stehen an ihrem Ablageziel statt im Korb: so
    wird jedes Objekt der Reihe einzeln geplant und simuliert (Start und Ende Ruhepose)."""
    ab = {int(s): int(z) for s, z in zuordnung}
    for i in erledigt or ():
        z = ziel[ab[int(i)] - 1]
        start[int(i) - 1] = sg.Koerper(start[int(i) - 1].name, z.gruppe, z.form, z.mitte.copy(), z.halb.copy(), z.rot.copy())


def welt_glaeser(A: AU.Aufbau, sz: Dict[str, Any], f: Finger, abw: konfig.Abweichung, erledigt=()) -> ag.Welt:
    aus = float(A.d["ziele"]["slots"]["oberkorb_auszug_m"])
    p = A.pruefer(aus + abw.korbauszug_delta_m, 0.0)
    a = _ausraeum_cfg(sz, f, "glaeser")
    sc = copy.deepcopy(p.sc)
    sc["pose"]["oberkorb_auszug_m"] = aus
    auf = konfig.Aufbau(p.m, sc, a, abw)
    r, h = p.m["glas"]["durchmesser_m"] / 2.0, p.m["glas"]["hoehe_m"]
    za = a["zwischenablage"]
    gl_cfg = sz["glaeser"]
    k2, ok_ = float(za["kante_m"]) / 2.0, float(za["oberkante_m"])
    zap = p.szene.arbeitsplatte_z
    sockel_h = gl_cfg["matte_sockel_m"]
    n_m = len(za["matten_xy_m"])
    sockel_h = [float(v) for v in sockel_h] if isinstance(sockel_h, list) else [float(sockel_h)] * n_m
    d_m = float(za["dicke_m"])
    oben = [zap + d_m + sockel_h[j] for j in range(n_m)]
    matten = [sg.quader(f"zwischenablage_{j + 1}", "zwischenablage", (x - k2, y - k2, oben[j] - d_m),
                        (x + k2, y + k2, oben[j])) for j, (x, y) in enumerate(za["matten_xy_m"])]
    sockel = [sg.quader(f"zwischenablage_sockel_{j + 1}", "zwischenablage", (x - k2, y - k2, zap),
                        (x + k2, y + k2, oben[j] - d_m)) for j, (x, y) in enumerate(za["matten_xy_m"])
              if oben[j] - d_m > zap + 1e-6]
    start = []
    for i, s in enumerate(sz["glaeser"]["slots"]):
        m_ = p.szene.slots[int(s) - 1]
        dx, dy = abw.glas_versatz_xy_m[i]
        start.append(ag.glas(f"glas_{i + 1}", (m_[0] + dx, m_[1] + dy, m_[2]), ag.KOPFUEBER @ rz(abw.glas_gier_grad[i]), r, h))
    ziel = []
    for i, (x, y) in enumerate(sz["glaeser"]["ablage_xy_m"]):
        z_ziel = (oben[int(gl_cfg["je_ablage"][i])] if gl_cfg.get("ablage_auf_matte") else zap) + h / 2.0
        ziel.append(ag.glas(f"glas_{i + 1}", (float(x), float(y), z_ziel), np.eye(3), r, h))
    _erledigt(start, ziel, a["ablauf"]["zuordnung"], erledigt)
    w = ag.Welt(auf, A.lage, p.szene, _statisch(p) + matten + sockel, start, ziel, matten, r, h)
    w.pruefer = p
    return w


def teller_koerper(name: str, mitte, r: float, dicke: float, normale_x: bool = False) -> sg.Koerper:
    """Teller hochkant, fuer Planung und Kollision als flacher Zylinder; Normale entlang y
    (Korb) oder x (``normale_x``, Staender)."""
    rot = rz(90.0) @ TELLER_ROT if normale_x else TELLER_ROT.copy()
    return sg.Koerper(name, "glas", "zylinder", np.asarray(mitte, float), np.array([r, r, dicke / 2.0]), rot)


def _halter(name: str, gruppe: str, mitte, t: Dict[str, Any], wulst: float, boden_z: float,
            hoehe: Optional[float] = None, normale_x: bool = False) -> List[sg.Koerper]:
    """Zwei Paar Tellerstaebe beidseits des Tellers, je halter_x neben der Tellermitte."""
    out = []
    s, hx = float(t["halter_stab_m"]), float(t["halter_x_m"])
    hh = float(t["halter_hoehe_m"]) if hoehe is None else float(hoehe)
    off = wulst / 2.0 + float(t["halter_luft_m"]) + s / 2.0
    for i, dx in enumerate((-hx, hx)):
        for j, dy in enumerate((-off, off)):
            if normale_x:
                dx, dy = dy, dx
            x, y = mitte[0] + dx, mitte[1] + dy
            out.append(sg.quader(f"{name}_stab_{i}{j}", gruppe, (x - s / 2, y - s / 2, boden_z), (x + s / 2, y + s / 2, boden_z + hh)))
    return out


def welt_teller(A: AU.Aufbau, sz: Dict[str, Any], f: Finger, abw: konfig.Abweichung, erledigt=()) -> ag.Welt:
    t = sz["teller"]
    cfg_t = A.d["ziele"]["teller"]
    aus = float(cfg_t["auszug_m"])
    p = A.pruefer(aus + abw.korbauszug_delta_m, 0.0, {"glashalter": {"reihen_x_m": []}})
    a = _ausraeum_cfg(sz, f, "teller")
    sc = copy.deepcopy(p.sc)
    sc["pose"]["oberkorb_auszug_m"] = aus
    m = copy.deepcopy(p.m)
    m["glas"] = dict(m["glas"], masse_kg=float(t["masse_kg"]))
    auf = konfig.Aufbau(m, sc, a, abw)
    r = float(t["durchmesser_m"]) / 2.0
    wulst = float(f.p["teller"]["wulst_dicke_mm"]) * 1e-3
    km = p.m["oberkorb"]
    boden = km["boden_hoehe_m"]
    vorne = km["vorne_eingeschoben_y_m"] + aus + abw.korbauszug_delta_m
    statisch = _statisch(p)
    start = []
    i = 0
    for x in t["spalten_x_m"]:
        for dy in t["tiefe_m"]:
            dx_, dy_ = abw.glas_versatz_xy_m[i]
            mitte = np.array([float(x) + dx_, vorne - float(dy) + dy_, boden + r])
            start.append(teller_koerper(f"glas_{i + 1}", mitte, r, wulst))
            statisch += _halter(f"tellerhalter_{i + 1}", "tellerhalter", (float(x), vorne - float(dy)), t, wulst, boden)
            i += 1
    zap = p.szene.arbeitsplatte_z
    sb = float(t["staender_boden_m"])
    x0, y0 = (float(v) for v in t["staender_xy_m"])
    tx, ty = (float(v) for v in t["staender_teilung_m"])
    plaetze = [(x0 + k * tx, y0 + k * ty) for k in range(len(start))]
    nx = abs(math.cos(math.radians(float(t["staender_gier_grad"])))) > 0.5   # Schliessen entlang x
    lo = (min(pp[0] for pp in plaetze) - (0.03 if nx else 0.08), min(pp[1] for pp in plaetze) - (0.08 if nx else 0.03), zap)
    hi = (max(pp[0] for pp in plaetze) + (0.03 if nx else 0.08), max(pp[1] for pp in plaetze) + (0.08 if nx else 0.03), zap + sb)
    statisch.append(sg.quader("tellerstaender_boden", "tellerstaender", lo, hi))
    ziel = []
    for k, (x, y) in enumerate(plaetze):
        statisch += _halter(f"tellerstaender_{k + 1}", "tellerstaender", (x, y), t, wulst, zap + sb,
                            float(t["staender_halter_hoehe_m"]), normale_x=nx)
        ziel.append(teller_koerper(f"glas_{k + 1}", (x, y, zap + sb + r), r, wulst, normale_x=nx))
    _erledigt(start, ziel, a["ablauf"]["zuordnung"], erledigt)
    w = ag.Welt(auf, A.lage, p.szene, statisch, start, ziel, [], r, wulst)
    w.pruefer = p
    return w


# --- Planung ------------------------------------------------------------------------

class A1Planer(Planer):
    """Ausraeum-Planer fuer den Aufbau ohne 7. Achse (Fuss auf der Platte), Finger mit
    Kontaktversatz; Teller (``teller=True``): Neigung = Tellerebene gegen die Senkrechte."""

    def __init__(self, welt, cfg, chain, sz: Dict[str, Any], f: Finger, teller: bool = False, seed=None, merk=None,
                 pruefer=None):
        super().__init__(welt, cfg, chain, seed=seed, merk=merk)
        self.teller = teller
        self.sz, self.f = sz, f
        # schnelle Pruefung (vektorisiert, spuelmaschine.aufbau) gegen genau die statische Szene der Welt
        self.p = pruefer
        if pruefer is not None:
            pruefer.hindernisse = list(welt.statisch)
            pruefer._aabb = np.array([k.aabb() for k in pruefer.hindernisse])
        g = self.a["greifer"]
        vs = float(sz["greifer"]["kontakt_versatz_m"])
        if teller:
            # Lippen (Bezugsebene, 2,5 mm vor der Backe) klemmen die Fahne
            iv = float(f.p["anschluss"]["innen_versatz_mm"]) * 1e-3
            fahne = float(f.p["teller"]["fahne_dicke_mm"]) * 1e-3
            self.q_kontakt = (fahne + 2.0 * iv - cfg.min_oeffnung) / 2.0
            self.q_offen = (0.030 + 2.0 * iv - cfg.min_oeffnung) / 2.0
            self.q_zu = 0.0  # ganz zu; Kraft ueber die Fingersteifigkeit (finger.sim)
        else:
            self.q_kontakt = (welt.glas_r * 2.0 - 2.0 * vs - cfg.min_oeffnung) / 2.0
            self.q_zu = self.q_kontakt - float(g["greifkraft_n"]) / float(g["finger_ke"])

    def kandidaten(self, qs, ziel_p, ziel_R, rng, merkname):
        """Wie ``Planer.kandidaten``, die Startposen aber als Batch-IK (``spuelmaschine.aufbau``)
        mit den Startposen und Zufallsstarts des Aufbau-Werkzeugs: die Einzel-IK fand die
        waagerechten Seitgriff-Posen neben dem Fuss nicht."""
        if self.p is None:
            yield from super().kandidaten(qs, ziel_p, ziel_R, rng, merkname)
            return
        gesehen: List[np.ndarray] = []

        def neu(q) -> bool:
            for g_ in gesehen:
                if float(np.max(np.abs((g_ - q)[self.arm_idx]))) < math.radians(3.0):
                    return False
            gesehen.append(q)
            return True

        if merkname and merkname in self.merk:
            q, pe, ok = self.ik(ziel_p, ziel_R, self.merk[merkname].copy(), 0, rng)
            if ok and neu(q):
                yield q
        from rebel_model.kinematics import axis_angle, rot_log
        ta = self.tcp_welt(qs)
        dr = rot_log(ziel_R @ ta[:3, :3].T)
        q, ok = qs.copy(), True
        for i in range(1, 9):
            fr = i / 8.0
            ang = float(np.linalg.norm(dr))
            Ri = (axis_angle(dr / ang, ang * fr) if ang > 1e-9 else np.eye(3)) @ ta[:3, :3]
            q, pe, ok = self.ik(ta[:3, 3] + (ziel_p - ta[:3, 3]) * fr, Ri, q, 0, rng)
            if not ok:
                break
        if ok and neu(q):
            yield q
        if not hasattr(self, "_loeser"):
            self._loeser = AU.Loeser(self.p)
        L = self._loeser
        T = L.ziele(ziel_R, [np.asarray(ziel_p, float)])[0]
        Q0 = np.array([qs] + self.p.startwerte(np.asarray(ziel_p, float), rng))
        Q0[:, self.ifg] = qs[self.ifg]
        qq, pe, _, okk = L.loese(np.repeat(T[None], len(Q0), axis=0), Q0, rng, 3)
        rest = [qq[k].copy() for k in range(len(Q0)) if okk[k] and pe[k] <= self.ik_max]
        rest = [q for q in rest if neu(q)]
        rest.sort(key=lambda q: float(np.max(np.abs(q - qs) / self.vmax)))
        yield from rest

    def lin(self, a, b, R, q0, z, rng, pruefen=True, R_ende=None):
        """Gerader Weg; der Weg mit Drehung (nur ``zur_ablage`` nach dem Umdrehen) geht erst
        waagerecht ueber das Ziel und dann senkrecht hinab: die Matte steht auf einem Sockel
        hoeher als die Ablage, der schraege Weg fuehrte das Glas durch Matte und Sockel."""
        a, b = np.asarray(a, float), np.asarray(b, float)
        if R_ende is None or a[2] - b[2] < 0.02:
            return super().lin(a, b, R, q0, z, rng, pruefen, R_ende)
        mitte = np.array([b[0], b[1], a[2]])
        w1 = super().lin(a, mitte, R, q0, z, rng, pruefen, R_ende)
        w2 = super().lin(mitte, b, R_ende, w1[-1], z, rng, pruefen)
        return w1 + w2[1:]

    def verbinde(self, qa, Ra, ziel_p, ziel_R, z, rng, folge=None, merkname=None):
        """Wie ``Planer.verbinde``; scheitert das, erst waagerecht 6/10/14 cm zum Ziel hin
        ausweichen (der senkrechte Greifer kommt neben dem Fuss kaum hoeher, die
        Zwischenpunkte darueber sind dort oft nicht erreichbar)."""
        try:
            return super().verbinde(qa, Ra, ziel_p, ziel_R, z, rng, folge, merkname)
        except PlanFehler as e0:
            letzter = str(e0)
        pa = self.tcp_welt(qa)[:3, 3]
        u = np.asarray(ziel_p, float) - pa
        u[2] = 0.0
        n = float(np.linalg.norm(u))
        if n < 0.05:
            raise PlanFehler(letzter)
        u /= n
        for d in (0.06, 0.10, 0.14):
            if d > n:
                break
            try:
                weg = self.lin(pa, pa + u * d, Ra, qa, z, rng)
                stuecke, qz, erg = super().verbinde(weg[-1], Ra, ziel_p, ziel_R, z, rng, folge,
                                                    f"{merkname}@aus{d}" if merkname else None)
                return [weg] + stuecke, qz, erg
            except PlanFehler as e:
                letzter = f"{letzter} | ausweichen {d:.2f} m: {e}"
        # Zwischenpose mit gleicher Greiferlage (z. B. ueber dem Fuss): zwei kurze Gelenkfahrten
        # statt einer langen, die das getragene Glas zu stark neigt
        gross = float(self.pl["glas_abstand_ptp_m"])
        kipp = float(self.pl["glas_kipp_max_grad"])
        ref = 1.0
        if z.halt is not None:
            ref = 1.0 if z.halt.koerper(self.tcp_welt(qa), self.w.glas_r, self.w.glas_h).rot[2, 2] >= 0 else -1.0
        zp = Lagezustand(z.ruhend, set(), z.halt, z.auflage, gross, set(), kipp, ref)
        for via in self.sz.get("zwischenposen_m", []):
            via = np.asarray(via, float)
            for qv in list(self.kandidaten(qa, via, Ra, rng, None))[:4]:
                qv[self.ifg] = qa[self.ifg]
                if self.treffer(qv, zp) or self.ptp_frei(qa, qv, zp):
                    continue
                try:
                    stuecke, qz, erg = super().verbinde(qv, Ra, ziel_p, ziel_R, z, rng, folge,
                                                        f"{merkname}@via{via.tolist()}" if merkname else None)
                    return [[qa, qv]] + stuecke, qz, erg
                except PlanFehler as e:
                    letzter = f"{letzter} | ueber {np.round(via, 2).tolist()}: {e}"
        raise PlanFehler(letzter)

    def treffer(self, q, z: Lagezustand) -> List[str]:
        if self.p is None:
            return self._treffer_langsam(q, z)
        self.zaehler["pruefpunkte"] += 1
        if not self.chain.within_limits(q, 1e-6):
            return ["gelenkgrenze"]
        # Selbstkollision + Roboter gegen Szene (5 mm), erlaubte Beruehrungen des Fusses ausgenommen
        hits = list(self.p.kollisionen(q))
        R, t = self.T[:3, :3], self.T[:3, 3]
        wb = self.p.self_coll.world_boxes(q)
        getragen = z.halt.koerper(self.tcp_welt(q), self.w.glas_r, self.w.glas_h) if z.halt else None
        if getragen is not None and z.kipp_max_grad is not None:
            if self.teller:   # Tellerebene bleibt senkrecht: Normale (Zylinderachse) waagerecht
                neigung = math.degrees(math.asin(min(1.0, abs(float(getragen.rot[2, 2])))))
            else:
                neigung = math.degrees(math.acos(max(-1.0, min(1.0, z.kipp_ref * float(getragen.rot[2, 2])))))
            if neigung > z.kipp_max_grad:
                hits.append(f"getragen|kippt_{neigung:.0f}_grad")
        g_aabb = np.array([k.aabb() for k in z.ruhend]) if z.ruhend else np.zeros((0, 2, 3))
        for link, boxes in wb.items():
            for c, r, h in boxes:
                rb = sg.Koerper(link, "roboter", "quader", R @ c + t, h, R @ r)
                lo, hi = rb.aabb()
                if len(g_aabb):
                    gmax = self.rand if z.glas_abstand is None else z.glas_abstand
                    near = np.where(np.all(g_aabb[:, 0] <= hi + gmax, axis=1) & np.all(g_aabb[:, 1] >= lo - gmax, axis=1))[0]
                    for i in near:
                        k = z.ruhend[i]
                        if link in ("finger_left", "finger_right") and k.name in z.finger_frei:
                            continue
                        gr_ = self.rand if k.name in z.nah else gmax
                        if ag.ueberlappung(rb, k, gr_) > 0:
                            hits.append(f"{link}|{k.name}")
                if getragen is not None and link not in ("finger_left", "finger_right"):
                    if ag.ueberlappung(rb, getragen, self.rand) > 0:
                        hits.append(f"{link}|getragen")
        if getragen is not None:
            lo, hi = getragen.aabb()
            for k in list(self.statisch) + list(z.ruhend):
                if k.name in z.auflage:
                    continue
                kl, kh = k.aabb()
                if np.any(kl > hi + self.glas_rand) or np.any(kh < lo - self.glas_rand):
                    continue
                if ag.ueberlappung(getragen, k, self.glas_rand) > 0:
                    hits.append(f"getragen|{k.name}")
        return sorted(h for h in set(hits) if h not in ERLAUBT)

    def _treffer_langsam(self, q, z: Lagezustand) -> List[str]:
        if self.teller and z.halt is not None and z.kipp_max_grad is not None:
            hits = super().treffer(q, replace(z, kipp_max_grad=None))
            getragen = z.halt.koerper(self.tcp_welt(q), self.w.glas_r, self.w.glas_h)
            neigung = math.degrees(math.asin(min(1.0, abs(float(getragen.rot[2, 2])))))  # Normale gegen waagerecht
            if neigung > z.kipp_max_grad:
                hits.append(f"getragen|kippt_{neigung:.0f}_grad")
        else:
            hits = super().treffer(q, z)
        return [h for h in hits if h not in ERLAUBT]

    # Teller: Rand von oben greifen, senkrecht heraus, hochkant in den Staender ----------
    def plane_teller(self):
        from greifen.plan import Plan, Segment
        from ausraeumen.plan import T_MIN

        w, a, t = self.w, self.a, self.sz["teller"]
        rng = np.random.default_rng(self.seed)
        plan = Plan(self.chain, None)
        tt = [0.0]
        v_lin, a_lin = float(self.pl["tcp_v_max_m_s"]), float(self.pl["tcp_a_max_m_s2"])

        def add(phase, wege, t_min=T_MIN, extra=0.0):
            arr = np.array(wege)
            d = self.dauer_fuer(arr, t_min)
            if len(arr) > 1:
                L = float(np.linalg.norm(self.tcp_welt(arr[-1])[:3, 3] - self.tcp_welt(arr[0])[:3, 3]))
                d = max(d, 1.875 * L / v_lin, math.sqrt(5.77 * L / a_lin))
            d += extra
            plan.segmente.append(Segment(phase, tt[0], d, arr))
            tt[0] += d

        def finger(qs, wert):
            out = []
            for q in qs:
                q = q.copy()
                q[self.ifg] = wert
                out.append(q)
            return out

        halte = float(a["greifer"]["haltezeit_s"])
        r = w.glas_r
        ft = self.f.p["teller"]
        ueber_rand = float(self.f.p["greifkraft"]["griffpunkt_ab_spitze_mm"]) * 1e-3 - float(ft["spitze_unter_rand_mm"]) * 1e-3
        ruhend: Dict[int, sg.Koerper] = {i: k for i, k in enumerate(w.glas_start)}
        q = self.ruhepose()
        q[self.ifg] = self.q_offen
        h0 = self.treffer(q, Lagezustand(list(ruhend.values())))
        if h0:
            raise PlanFehler("Ruhepose kollidiert: " + ", ".join(h0))
        add("start", [q], t_min=0.3)
        gps: List[GlasPlan] = []
        luft = float(t["absetzen_luft_m"])
        for nr, (s1, z1) in enumerate(a["ablauf"]["zuordnung"]):
            s, zi = int(s1) - 1, int(z1) - 1
            gp = GlasPlan(nr, s, zi, t0=tt[0])
            G = w.glas_start[s]
            name = G.name
            pfx = f"{s + 1}:"
            halter = {k.name for k in w.statisch if k.name.startswith(f"tellerhalter_{s + 1}_")}
            andere = lambda: [k for i, k in ruhend.items() if i != s]  # noqa: E731
            rand_z = G.mitte[2] + r
            p_greif = np.array([G.mitte[0], G.mitte[1], rand_z + ueber_rand])
            p_vor = p_greif + [0, 0, float(t["vorposition_m"])]
            p_aus = p_greif + [0, 0, float(t["aushub_m"])]
            z_frei = Lagezustand(list(ruhend.values()), {name})
            ergebnis, letzter = None, ""
            for gier in (90.0, 270.0):
                R = r_greif(gier)

                def folge_korb(qv, R=R):
                    runter = self.lin(p_vor, p_greif, R, qv, z_frei, rng)
                    halt = Halt(s, self._mitte_tcp(runter[-1], G.mitte), self._rot_tcp(runter[-1], G.rot))
                    z_trag = Lagezustand(andere(), set(), halt, halter | {"oberkorb_boden"})
                    hoch = self.lin(p_greif, p_aus, R, finger([runter[-1]], self.q_zu)[0], z_trag, rng)
                    return runter, halt, hoch

                try:
                    q0 = q.copy()
                    stuecke, qv, erg = self.verbinde(q0, self._rot(q0), p_vor, R, Lagezustand(list(ruhend.values())),
                                                     rng, folge_korb, f"teller{s}:{gier:.0f}")
                    ergebnis = (R, gier, stuecke) + erg
                    break
                except PlanFehler as e:
                    letzter = str(e)
            if ergebnis is None:
                raise PlanFehler(f"Teller {s + 1}: Griff im Korb nicht planbar ({letzter})")
            R, gier, stuecke, runter, halt, hoch = ergebnis
            for st in stuecke:
                add(pfx + "anfahrt_korb", finger(st, self.q_offen))
            add(pfx + "runter_korb", finger(runter, self.q_offen))
            add(pfx + "greifen_korb", [finger([runter[-1]], self.q_offen)[0], finger([runter[-1]], self.q_zu)[0]],
                extra=halte)
            add(pfx + "aushub", hoch)
            gp.info["gier_korb_grad"] = gier
            del ruhend[s]
            q = hoch[-1]

            Z = w.glas_ziel[zi]
            staender = {k.name for k in w.statisch if k.name.startswith(f"tellerstaender_{zi + 1}_")}
            ziel_m = Z.mitte + [0, 0, luft]
            g_st = float(t["staender_gier_grad"])
            nx = abs(math.cos(math.radians(g_st))) > 0.5
            glas_fertig = teller_koerper(name, Z.mitte, r, w.glas_h, normale_x=nx)
            z_trag = Lagezustand(list(ruhend.values()), set(), halt)
            z_ab = Lagezustand(list(ruhend.values()), set(), halt, staender | {"tellerstaender_boden"})
            ergebnis, letzter = None, ""
            for g_ in (g_st, g_st + 180.0):
                R_st = r_greif(g_)
                p_ab = self._tcp_fuer_glas(ziel_m, R_st, halt)
                p_ab_vor = p_ab + [0, 0, float(t["staender_vorposition_m"])]

                def folge_ab(qv, R_st=R_st, p_ab=p_ab, p_ab_vor=p_ab_vor):
                    ab_ = self.lin(p_ab_vor, p_ab, R_st, qv, z_ab, rng)
                    z_los = Lagezustand(list(ruhend.values()) + [glas_fertig], {name})
                    hoch_ = self.lin(p_ab, p_ab_vor, R_st, finger([ab_[-1]], self.q_offen)[0], z_los, rng)
                    return ab_, hoch_

                try:
                    stuecke, qv, (ab_, hoch_) = self.verbinde(q, R, p_ab_vor, R_st, z_trag, rng, folge_ab,
                                                              f"staender{zi}:{g_:.0f}")
                    ergebnis = (g_, stuecke, ab_, hoch_)
                    break
                except PlanFehler as e:
                    letzter += f" | Gier {g_:.0f}: {e}"
            if ergebnis is None:
                raise PlanFehler(f"Teller {s + 1}: Staenderplatz {zi + 1} nicht planbar ({letzter})")
            g_, stuecke, ab_, hoch_ = ergebnis
            gp.info["gier_staender_grad"] = g_
            for st in stuecke:
                add(pfx + "zur_ablage", st)
            add(pfx + "absetzen", ab_)
            add(pfx + "loesen", [ab_[-1], finger([ab_[-1]], self.q_offen)[0]], extra=halte)
            add(pfx + "rueckzug", hoch_)
            ruhend[s] = glas_fertig
            q = hoch_[-1]
            gp.t1 = tt[0]
            gps.append(gp)
        qh = self.ruhepose()
        qh[self.ifg] = self.q_offen
        z_end = Lagezustand(list(ruhend.values()))
        hh = self.ptp_frei(q, qh, z_end)
        if hh:
            raise PlanFehler("Rueckfahrt in die Ruhepose kollidiert: " + ", ".join(hh[:3]))
        add("heim", [q, qh])
        add("nachlauf", [qh], t_min=float(a["greifer"]["nachlauf_s"]))
        return plan, gps


# --- Bewertung Teller -----------------------------------------------------------------

def bewerte_teller(nr, gp, zeiten, welt, mess, gr) -> Dict[str, Any]:
    """Wie ``ausraeumen.bewertung.bewerte_glas``; Hand: greifen_korb..loesen, Kippung der
    Tellerebene gegen die Senkrechte, Ziel = Staenderplatz (x, y), Kontakt auch zum Staender."""
    s = gp.slot
    pfx = f"{s + 1}:"
    t, G, tcp = mess["t"], mess["glas"], mess["tcp"]
    k: Dict[str, Dict[str, Any]] = {"planung_fehlgeschlagen": {"ok": True, "wert": []}}
    nan = bool(mess.get("nan", False)) or len(t) == 0 or not np.all(np.isfinite(G))
    k["simulation_instabil"] = {"ok": not nan, "wert": bool(mess.get("nan", False))}
    if nan:
        return ab._fertig(nr, gp, k, {})
    start = G[0, s, :3]
    i_aus = ab._idx(t, zeiten[pfx + "aushub"][1])
    hub = float(G[i_aus, s, 2] - start[2])
    k["nicht_aus_dem_korb"] = {"ok": hub >= float(gr["hub_min_m"]), "wert": hub, "grenze": f">= {gr['hub_min_m']}"}
    i0, i1 = ab._idx(t, zeiten[pfx + "greifen_korb"][1]), ab._idx(t, zeiten[pfx + "loesen"][0])
    verloren = 0.0
    if i1 > i0:
        d = np.linalg.norm(G[i0:i1, s, :3] - tcp[i0:i1], axis=1)
        verloren = float(np.max(np.abs(d - d[0])))
    end = G[-1, s]
    ziel = welt.glas_ziel[gp.ablage].mitte
    steh = abs(float(end[2] - ziel[2]))
    k["gefallen"] = {"ok": verloren <= 0.02 and steh <= float(gr["stehhoehe_toleranz_m"]),
                     "wert": {"tcp_abstand_aenderung_max_m": verloren, "end_z_m": float(end[2]), "soll_z_m": float(ziel[2])},
                     "grenze": f"Hand <= 0.02, |z - soll| <= {gr['stehhoehe_toleranz_m']}"}
    kipp_end = ab._kipp(end[3:7])
    k["gekippt"] = {"ok": kipp_end < float(gr["kippung_max_grad"]), "wert": kipp_end, "start_grad": ab._kipp(G[0, s, 3:7]),
                    "grenze": f"< {gr['kippung_max_grad']}"}
    fehler = float(math.hypot(end[0] - ziel[0], end[1] - ziel[1]))
    k["nicht_am_ziel"] = {"ok": fehler <= float(gr["ziel_toleranz_m"]), "wert": fehler, "grenze": f"<= {gr['ziel_toleranz_m']}"}
    kon = mess["kontakt"][s]
    for grund, grp in (("kontakt_korb", "korb"), ("kontakt_tuer", "tuer"), ("kontakt_arbeitsplatte", "arbeitsplatte")):
        tiefe, ph = kon.get(grp, (0.0, ""))
        k[grund] = {"ok": tiefe <= float(gr["kontakt_max_m"]), "wert": float(tiefe), "phase": ph, "grenze": f"<= {gr['kontakt_max_m']}"}
    tiefe, ph = kon.get("staender", (0.0, ""))
    k["kontakt_arbeitsplatte"]["staender_m"] = float(tiefe)
    if tiefe > float(gr["kontakt_max_m"]):
        k["kontakt_arbeitsplatte"]["ok"] = False
    a0, a1 = ab._idx(t, gp.t0), ab._idx(t, gp.t1)
    nachbar = {f"teller_{j + 1}": float(np.max(np.linalg.norm(G[a0:a1 + 1, j, :3] - G[a0, j, :3], axis=1)))
               for j in range(G.shape[1]) if j != s}
    nmax = max(nachbar.values()) if nachbar else 0.0
    k["nachbar_verschoben"] = {"ok": nmax <= float(gr["nachbar_verschiebung_max_m"]), "wert": nachbar,
                               "grenze": f"<= {gr['nachbar_verschiebung_max_m']}"}
    fd = float(mess["finger_durchdringung_m"][s])
    k["durchdringung"] = {"ok": fd <= float(gr["durchdringung_max_m"]), "wert": fd, "grenze": f"<= {gr['durchdringung_max_m']}",
                          "phase": mess["finger_durchdringung_phase"][s]}
    v = float(np.max(np.linalg.norm(np.diff(G[:, s, :3], axis=0), axis=1) / np.maximum(np.diff(t), 1e-9)))
    k["weggeschossen"] = {"ok": v <= float(gr["glas_v_max_m_s"]), "wert": v, "grenze": f"<= {gr['glas_v_max_m_s']}"}
    werte = {"start_m": [float(x) for x in start], "ende_m": [float(x) for x in end[:3]], "ziel_m": [float(x) for x in ziel],
             "zielfehler_xy_m": fehler, "kippung_end_grad": kipp_end, "kippung_start_grad": ab._kipp(G[0, s, 3:7]),
             "aushub_m": hub, "in_der_hand_gewandert_m": verloren,
             "kontakte_m": {g: float(v_[0]) for g, v_ in kon.items()}, "nachbar_max_m": nmax}
    out = ab._fertig(nr, gp, k, werte)
    out["glas"] = f"teller_{s + 1}"
    return out


def _in_der_hand(gp, zeiten, mess) -> float:
    """Glas: groesste Wanderung gegen den TCP in beiden Griffen (m)."""
    s = gp.slot
    pfx = f"{s + 1}:"
    t, G, tcp = mess["t"], mess["glas"], mess["tcp"]
    out = 0.0
    for a_, b_ in ((pfx + "greifen_korb", pfx + "loesen_zw"), (pfx + "greifen_seite", pfx + "loesen")):
        if a_ not in zeiten or b_ not in zeiten:
            continue
        i0, i1 = ab._idx(t, zeiten[a_][1]), ab._idx(t, zeiten[b_][0])
        if i1 > i0:
            d = np.linalg.norm(G[i0:i1, s, :3] - tcp[i0:i1], axis=1)
            out = max(out, float(np.max(np.abs(d - d[0]))))
    return out


# --- Ein Versuch --------------------------------------------------------------------

def urdf_sim(A: AU.Aufbau) -> str:
    """URDF fuer Newton: MuJoCo verlangt bei der (festen) 7. Achse eine Spanne > 0;
    1 mm, der Antrieb haelt sie bei 0."""
    import xml.etree.ElementTree as ET

    root = ET.fromstring(A._urdf())
    for j in root.findall("joint"):
        if j.get("name") == "axis7":
            lim = j.find("limit")
            if float(lim.get("upper")) - float(lim.get("lower")) < 1e-6:
                lim.set("upper", str(float(lim.get("lower")) + 0.001))
    return ET.tostring(root, encoding="unicode")


def versuch(art: str, nr: int, abw: konfig.Abweichung, ctx=None, nur_plan: bool = False, objekte_n: Optional[int] = None,
            merk=None, sz=None, aufzeichnen=None, zuordnung=None, erledigt=()) -> Tuple[Dict[str, Any], Dict]:
    from ausraeumen import sim_newton as sn

    from . import sim as fs

    f = Finger.laden()
    sz = sz or szenario()
    A = aufbau(sz, f)
    teller = art == "teller"
    w = (welt_teller if teller else welt_glaeser)(A, sz, f, abw, erledigt)
    if zuordnung:
        w.aufbau.a["ablauf"]["zuordnung"] = [list(v) for v in zuordnung]
    if objekte_n:
        w.aufbau.a["ablauf"]["zuordnung"] = w.aufbau.a["ablauf"]["zuordnung"][:objekte_n]
    t0 = time.monotonic()
    planer = A1Planer(w, A.cfg, A.chain, sz, f, teller=teller, merk=merk, pruefer=w.pruefer)
    rec: Dict[str, Any] = {"versuch": {"nr": nr, "art": art, "abweichung": abw.as_dict(), "erledigt": list(erledigt or [])},
                           "finger": {"masse_kg": A.cfg.greifer["finger_masse_kg"], "werkstoff": f.gewaehlt},
                           "device": ctx["device"] if ctx else None}
    zo = w.aufbau.a["ablauf"]["zuordnung"]
    try:
        plan, gps = planer.plane_teller() if teller else planer.plane()
    except PlanFehler as e:
        bew = ab.planfehler(zo, str(e))
        rec.update({"plan": {"ok": False, "fehler": str(e), "wand_s": round(time.monotonic() - t0, 1),
                             "zaehler": planer.zaehler}, "bewertung": bew, "erfolg": False})
        return rec, planer.merk
    rec["plan"] = {"ok": True, "dauer_s": round(plan.dauer, 3), "wand_s": round(time.monotonic() - t0, 1),
                   "zaehler": planer.zaehler,
                   "phasen": [[s.phase, round(s.t0, 3), round(s.t0 + s.dauer, 3)] for s in plan.segmente],
                   "objekte": [{"slot": g.slot + 1, "ablage": g.ablage + 1, "t_s": [round(g.t0, 3), round(g.t1, 3)], **g.info}
                               for g in gps]}
    if nur_plan:
        rec["erfolg"] = None
        return rec, planer.merk
    lauf = (fs.TellerLauf if teller else fs.FingerLauf)(ctx, w, plan, A.cfg, A.chain, urdf_sim(A),
                                                         30.0 if aufzeichnen else None)
    lauf.finger = f
    lauf.sz = sz
    if abw.verklemmt:
        ng = w.aufbau.a["negativtest"]
        lauf.zusatz = sn.klemmbacken(w, abw.verklemmt - 1, float(ng["uebermass_m"]), float(ng["backe_hoehe_m"]))
    lauf.bauen()
    mess = lauf.fahren()
    gr = w.aufbau.a["bewertung"]
    zeiten = plan.phase_zeiten()
    if teller:
        bew = ab.gesamt([bewerte_teller(i, gp, zeiten, w, mess, gr) for i, gp in enumerate(gps)])
    else:
        bew = ab.bewerte(plan, gps, w, mess, gr)
        for g, gp in zip(bew["glaeser"], gps):
            if g.get("werte"):
                g["werte"]["in_der_hand_gewandert_m"] = _in_der_hand(gp, zeiten, mess)
    rec.update({"erfolg": bew["erfolg"], "bewertung": bew,
                "dauer": {"ablauf_sim_s": round(plan.dauer, 3), "wand_sim_s": round(lauf.wand_s, 1)},
                "modell": {"objekt_masse_kg": lauf.glas_masse, "statische_formen": lauf.n_statisch, "dt_s": mess["dt"],
                           "finger_formen": len(lauf.finger_shapes)}})
    if aufzeichnen:
        meta = {"szene": "spuelmaschine", "art": art,
                "statisch": [{"name": k.name, "gruppe": k.gruppe, "mitte": k.mitte, "halb": k.halb, "rot": k.rot}
                             for k in list(w.statisch) + list(lauf.zusatz) if k.name != "boden"],
                "objekte": [{"name": k.name, "form": k.form, "halb": k.halb} for k in w.glas_start],
                "glas_radius_m": w.glas_r, "glas_hoehe_m": w.glas_h, "ablage_m": [k.mitte for k in w.glas_ziel],
                "phasen_s": [[s.phase, s.t0, s.t0 + s.dauer] for s in plan.segmente],
                "erfolg": bew["erfolg"], "erfolge": bew["erfolge"]}
        lauf.aufzeichner.speichern(aufzeichnen, lauf.body_label, sn.jsonable(meta))
    return sn.jsonable(rec), planer.merk
