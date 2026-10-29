"""Ablaufplanung: 4 Glaeser kopfueber aus dem Oberkorb, umdrehen, aufrecht abstellen.

Je Glas (``ablauf.zuordnung``: Slot -> Ablagepunkt)::

    anfahrt_korb     Gelenkfahrt ueber den Slot, Greifer senkrecht nach unten
    runter_korb      senkrecht hinab zur Greifpose (TCP 88 mm ueber dem Glasrand)
    greifen_korb     Finger schliessen
    aushub           senkrecht hoch (15 cm), Glas kommt aus dem Halter
    zur_zwischenablage  Gelenkfahrt ueber die Zwischenablage (Glas weiter kopfueber)
    absetzen_zw      senkrecht hinab, Glasrand 2 mm ueber dem Sockel
    loesen_zw        Finger oeffnen
    hoch_zw          senkrecht hoch
    anfahrt_seite    Gelenkfahrt vor das Glas, Greifer waagerecht
    zu_seite         waagerecht ans Glas (Glasmitte 15 mm vor dem TCP)
    greifen_seite    Finger schliessen (Seitgriff auf Hoehe der Glasmitte)
    anheben          senkrecht hoch (4 cm)
    umdrehen         nur Gelenk 6 um 180 Grad: das Glas dreht um die
                     Greiferachse und steht danach aufrecht
    zur_ablage       Gelenkfahrt ueber den Ablagepunkt (3 cm)
    absetzen         senkrecht hinab, Glasboden 2 mm ueber der Platte
    loesen           Finger oeffnen
    rueckzug         waagerecht vom Glas weg (10 cm)

dazu ``start`` und am Ende ``heim`` + ``nachlauf``. Warum Umgreifen:
``docs/ausraeumen.md`` Abschnitt 2 (mit einem starren Griff von oben zeigt
der Greifer nach dem Umdrehen nach oben, sein Koerper laege unter dem Glas).

Gerade TCP-Wege werden in 1-cm-Wegpunkte zerlegt und warm gestartet per IK
geloest (7. Achse + 6 Armgelenke, Lage und Orientierung); Gelenkfahrten
werden in 2-Grad-Schritten geprueft. Jeder Pruefpunkt: Gelenkgrenzen,
Selbstkollision, Roboterquader gegen Szene und ruhende Glaeser (5 mm Rand,
die Finger duerfen das zu greifende Glas beruehren), getragenes Glas gegen
Szene (2 mm Rand, ausser der Auflage beim Greifen/Absetzen) und gegen den
Greifer. Findet eine Gelenkfahrt keinen freien Weg, werden Zwischenpunkte
ueber Start und Ziel versucht (``planung.zwischenhub_m``). Einfache
Kollisionsvermeidung ueber Zwischenpunkte, kein Bewegungsplaner.
"""
from __future__ import annotations

import math
import os
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple

import numpy as np

from greifen.plan import Plan, Segment
from rebel_model.collision import SelfCollision, obb_penetration
from rebel_model.config import RobotConfig
from rebel_model.kinematics import Chain, axis_angle, rot_log, transform
from spuelmaschine import geometrie as sg
from spuelmaschine.erreichbarkeit import r_greif

from . import geometrie as ag

ARM = ["joint1", "joint2", "joint3", "joint4", "joint5", "joint6"]
USE = ["axis7"] + ARM
FINGER = {"finger_left", "finger_right"}
SCHIENE_UNTEN = {"rail", "carriage"}
T_MIN = 0.5
DREH_Z = np.diag([-1.0, -1.0, 1.0])  # 180 Grad um die Greiferachse


class PlanFehler(RuntimeError):
    pass


def r_seite(gier_grad: float, oben: float = 1.0) -> np.ndarray:
    """Greifer waagerecht: Anfahrrichtung (Greifer-z) unter ``gier_grad``,
    Greifer-x senkrecht (``oben`` = +1: nach oben), Schliessrichtung waagerecht."""
    a = math.radians(gier_grad)
    z = np.array([math.cos(a), math.sin(a), 0.0])
    x = np.array([0.0, 0.0, float(oben)])
    return np.column_stack([x, np.cross(z, x), z])


@dataclass
class Halt:
    """Glas in der Hand: Lage im TCP-System (Mitte, Drehung)."""
    glas: int
    mitte_tcp: np.ndarray
    rot_tcp: np.ndarray

    def koerper(self, t_tcp: np.ndarray, r: float, h: float) -> sg.Koerper:
        R, p = t_tcp[:3, :3], t_tcp[:3, 3]
        return ag.glas(f"glas_{self.glas + 1}", p + R @ self.mitte_tcp, R @ self.rot_tcp, r, h)


@dataclass
class Lagezustand:
    """Was beim Pruefen eines Wegpunkts in der Szene steht."""
    ruhend: List[sg.Koerper]                  # Glaeser in Ruhe (Korb, Zwischenablage, Ablage)
    finger_frei: Set[str] = field(default_factory=set)   # duerfen die Finger beruehren
    halt: Optional[Halt] = None
    auflage: Set[str] = field(default_factory=set)       # Auflage des getragenen Glases (nicht pruefen)
    glas_abstand: Optional[float] = None                  # Rand zu ruhenden Glaesern (sonst roboter_rand)
    nah: Set[str] = field(default_factory=set)            # Glaeser, fuer die trotzdem roboter_rand gilt
    kipp_max_grad: Optional[float] = None                 # getragenes Glas: hoechste Neigung gegen die Startlage
    kipp_ref: float = 1.0                                 # +1: Glas aufrecht getragen, -1: kopfueber


@dataclass
class GlasPlan:
    nr: int                  # 0..3
    slot: int                # 0..3
    ablage: int              # 0..3
    t0: float = 0.0
    t1: float = 0.0
    info: Dict = field(default_factory=dict)


class Planer:
    def __init__(self, welt: ag.Welt, cfg: RobotConfig, chain: Chain, seed: Optional[int] = None,
                 merk: Optional[Dict[str, np.ndarray]] = None):
        """``merk``: IK-Loesungen eines frueheren Plans je Stelle (Warmstart, z. B.
        aus dem Nennplan fuer die Variation)."""
        self.merk: Dict[str, np.ndarray] = dict(merk or {})
        self.w, self.cfg, self.chain = welt, cfg, chain
        a = welt.aufbau.a
        self.a = a
        self.pl = a["planung"]
        self.seed = int(self.pl["seed"] if seed is None else seed)
        self.T = welt.lage.matrix()
        self.Tinv = np.linalg.inv(self.T)
        self.sc = SelfCollision(chain)
        self.tcp = [0.0, 0.0, float(cfg.greifer["tcp_ab_flansch_m"])]
        self.i7 = chain.index["axis7"]
        self.ifg = chain.index["finger_left"]
        self.i6 = chain.index["joint6"]
        self.arm_idx = [chain.index[n] for n in ARM]
        self.rand = float(self.pl["roboter_rand_m"])
        self.glas_rand = float(self.pl["glas_rand_m"])
        self.ik_max = float(self.pl["ik_fehler_max_m"])
        self.sprung = math.radians(float(self.pl["gelenksprung_max_grad"]))
        self.ptp_schritt = math.radians(float(self.pl["ptp_schritt_grad"]))
        g = a["greifer"]
        self.q_offen = (float(g["oeffnung_offen_m"]) - cfg.min_oeffnung) / 2.0
        self.q_kontakt = (welt.glas_r * 2.0 - cfg.min_oeffnung) / 2.0
        self.q_zu = self.q_kontakt - float(g["greifkraft_n"]) / float(g["finger_ke"])
        anteil = float(g["geschwindigkeit_anteil"])
        self.vmax = np.array([
            anteil * (cfg.achse7["geschwindigkeit_m_s"] if n == "axis7" else
                      cfg.greifer["geschwindigkeit_m_s"] if n == "finger_left" else
                      math.radians(cfg.arm["geschwindigkeit_grad_s"]))
            for n in chain.active])
        self.x0 = float(chain.fk(chain.zero(), "base_link")[0, 3])
        self.statisch = welt.statisch
        self._aabb = np.array([k.aabb() for k in self.statisch])
        self.zaehler = {"ik": 0, "pruefpunkte": 0}

    # --- Kinematik -------------------------------------------------------
    def tcp_welt(self, q: np.ndarray) -> np.ndarray:
        return self.T @ self.chain.fk(q, "gripper_base", self.tcp)

    def ik(self, p: Sequence[float], R: np.ndarray, q0: np.ndarray, restarts: int, rng) -> Tuple[np.ndarray, float, bool]:
        self.zaehler["ik"] += 1
        tr = self.Tinv @ transform(R, p)
        q, pe, re, ok = self.chain.ik(tr, "gripper_base", q0, USE, offset=self.tcp, restarts=restarts, rng=rng,
                                      tol_pos=1e-5, tol_rot=1e-4)
        return q, pe, bool(ok and pe <= self.ik_max)

    def startwerte(self, p: np.ndarray, rng, q_warm: Optional[np.ndarray] = None) -> List[np.ndarray]:
        """Warmstart, dann Haltungen mit dem Fuss nahe am Ziel, dann Zufallsposen."""
        out = [] if q_warm is None else [q_warm.copy()]
        pr = (self.Tinv @ np.append(p, 1.0))[:3]
        j7 = self.chain.by_name["axis7"]
        a7 = float(np.clip(pr[0] - self.x0, j7.lower, j7.upper))
        for d7 in (0.0, 0.2, -0.2):
            q = self.chain.zero()
            q[self.i7] = float(np.clip(a7 + d7, j7.lower, j7.upper))
            base = self.chain.fk(q, "base_link")[:3, 3]
            phi = math.atan2(pr[1] - base[1], pr[0] - base[0])
            for j2, j3, j5 in ((30.0, 90.0, 60.0), (0.0, 90.0, 90.0), (50.0, 60.0, 70.0), (20.0, 100.0, -20.0),
                               (-30.0, -90.0, -60.0), (0.0, -90.0, -90.0)):
                qq = q.copy()
                qq[self.chain.index["joint1"]] = -phi
                qq[self.chain.index["joint2"]] = math.radians(j2)
                qq[self.chain.index["joint3"]] = math.radians(j3)
                qq[self.chain.index["joint5"]] = math.radians(j5)
                out.append(qq)
        for _ in range(4):
            out.append(self.chain.random_q(rng, USE))
        return out

    # --- Kollision -------------------------------------------------------
    def treffer(self, q: np.ndarray, z: Lagezustand) -> List[str]:
        self.zaehler["pruefpunkte"] += 1
        if not self.chain.within_limits(q, 1e-6):
            return ["gelenkgrenze"]
        wb = self.sc.world_boxes(q)
        hits = []
        for a_, b_ in self.sc.pairs:
            for c1, r1, h1 in wb[a_]:
                for c2, r2, h2 in wb[b_]:
                    if np.linalg.norm(c1 - c2) > float(np.sum(h1) + np.sum(h2)):
                        continue
                    if obb_penetration(c1, r1, h1, c2, r2, h2) > 0:
                        hits.append(f"{a_}|{b_}")
        R, t = self.T[:3, :3], self.T[:3, 3]
        getragen = z.halt.koerper(self.tcp_welt(q), self.w.glas_r, self.w.glas_h) if z.halt else None
        if getragen is not None and z.kipp_max_grad is not None:
            neigung = math.degrees(math.acos(max(-1.0, min(1.0, z.kipp_ref * float(getragen.rot[2, 2])))))
            if neigung > z.kipp_max_grad:
                hits.append(f"getragen|kippt_{neigung:.0f}_grad")
        g_aabb = np.array([k.aabb() for k in z.ruhend]) if z.ruhend else np.zeros((0, 2, 3))
        for link, boxes in wb.items():
            for c, r, h in boxes:
                rb = sg.Koerper(link, "roboter", "quader", R @ c + t, h, R @ r)
                lo, hi = rb.aabb()
                lo, hi = lo - self.rand, hi + self.rand
                near = np.where(np.all(self._aabb[:, 0] <= hi, axis=1) & np.all(self._aabb[:, 1] >= lo, axis=1))[0]
                for i in near:
                    k = self.statisch[i]
                    if link in SCHIENE_UNTEN and k.name in ("podest", "boden"):
                        continue
                    if ag.ueberlappung(rb, k, self.rand) > 0:
                        hits.append(f"{link}|{k.name}")
                if len(g_aabb):
                    gmax = self.rand if z.glas_abstand is None else z.glas_abstand
                    near = np.where(np.all(g_aabb[:, 0] <= hi + gmax, axis=1) & np.all(g_aabb[:, 1] >= lo - gmax, axis=1))[0]
                    for i in near:
                        k = z.ruhend[i]
                        if link in FINGER and k.name in z.finger_frei:
                            continue
                        gr_ = self.rand if k.name in z.nah else gmax
                        if ag.ueberlappung(rb, k, gr_) > 0:
                            hits.append(f"{link}|{k.name}")
                if getragen is not None and link not in FINGER:
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
        return sorted(set(hits))

    # --- Wege ------------------------------------------------------------
    def lin(self, a: np.ndarray, b: np.ndarray, R: np.ndarray, q0: np.ndarray, z: Lagezustand,
            rng, pruefen: bool = True, R_ende: Optional[np.ndarray] = None) -> List[np.ndarray]:
        """Gerader TCP-Weg a -> b, warm gestartete IK. Orientierung fest ``R`` oder
        (``R_ende``) gleichmaessig von ``R`` nach ``R_ende`` gedreht."""
        schritt = float(self.pl["wegpunkt_abstand_m"])
        n = max(1, int(math.ceil(np.linalg.norm(b - a) / schritt - 1e-9)))
        dr = rot_log(R_ende @ R.T) if R_ende is not None else np.zeros(3)
        ang = float(np.linalg.norm(dr))
        n = max(n, int(math.ceil(math.degrees(ang) / 3.0)))  # hoechstens 3 Grad Drehung je Wegpunkt
        out, q = [q0.copy()], q0.copy()
        for i in range(1, n + 1):
            p = a + (b - a) * i / n
            Ri = (axis_angle(dr / ang, ang * i / n) @ R) if ang > 1e-9 else R
            qn, pe, ok = self.ik(p, Ri, q, 0, rng)
            if not ok:
                raise PlanFehler(f"IK-Weg abgerissen bei {np.round(p, 3).tolist()} ({pe * 1e3:.2f} mm)")
            qn[self.ifg] = q0[self.ifg]
            if float(np.max(np.abs((qn - q)[self.arm_idx]))) > self.sprung:
                dq = np.degrees((qn - q)[self.arm_idx])
                raise PlanFehler(f"Gelenksprung bei {np.round(p, 3).tolist()} (J1..J6 {np.round(dq, 0).tolist()} Grad, "
                                 f"J5 {math.degrees(float(qn[self.chain.index['joint5']])):.0f})")
            if pruefen:
                h = self.treffer(qn, z)
                if h:
                    raise PlanFehler("Kollision auf geradem Weg: " + ", ".join(h[:4]))
            out.append(qn)
            q = qn
        return out

    def ptp_frei(self, qa: np.ndarray, qb: np.ndarray, z: Lagezustand) -> List[str]:
        d = float(np.max(np.abs((qb - qa)[self.arm_idx]))) if len(self.arm_idx) else 0.0
        d7 = abs(float(qb[self.i7] - qa[self.i7]))
        n = max(1, int(math.ceil(max(d / self.ptp_schritt, d7 / 0.01))))
        for i in range(1, n + 1):
            h = self.treffer(qa + (qb - qa) * i / n, z)
            if h:
                return h
        return []

    def kandidaten(self, qs: np.ndarray, ziel_p: np.ndarray, ziel_R: np.ndarray, rng, merkname: Optional[str]):
        """IK-Loesungen der Zielpose, die naechstliegenden zuerst: gemerkte Loesung
        (frueheres Glas, gleiche Stelle), Fortsetzung entlang des Wegs von der
        Startpose aus, Warmstart, dann Haltungen und Zufallsposen."""
        gesehen: List[np.ndarray] = []

        def neu(q) -> bool:
            for g in gesehen:
                if float(np.max(np.abs((g - q)[self.arm_idx]))) < math.radians(3.0) and abs(g[self.i7] - q[self.i7]) < 0.01:
                    return False
            gesehen.append(q)
            return True

        if merkname and merkname in self.merk:
            q, pe, ok = self.ik(ziel_p, ziel_R, self.merk[merkname].copy(), 0, rng)
            if ok and neu(q):
                yield q
        # Fortsetzung: Pose in 8 Schritten von der Start- zur Zielpose, je warm gestartet
        ta = self.tcp_welt(qs)
        dr = rot_log(ziel_R @ ta[:3, :3].T)
        q, ok = qs.copy(), True
        for i in range(1, 9):
            f = i / 8.0
            ang = float(np.linalg.norm(dr))
            Ri = (axis_angle(dr / ang, ang * f) if ang > 1e-9 else np.eye(3)) @ ta[:3, :3]
            q, pe, ok = self.ik(ta[:3, 3] + (ziel_p - ta[:3, 3]) * f, Ri, q, 0, rng)
            if not ok:
                break
        if ok and neu(q):
            yield q
        rest = []
        for q0 in self.startwerte(ziel_p, rng, q_warm=qs):
            q0 = q0.copy()
            q0[self.ifg] = qs[self.ifg]
            q, pe, ok = self.ik(ziel_p, ziel_R, q0, 1, rng)
            if ok and neu(q):
                rest.append(q)
        rest.sort(key=lambda q: float(np.max(np.abs(q - qs) / self.vmax)))
        yield from rest

    def verbinde(self, qa: np.ndarray, Ra: np.ndarray, ziel_p: np.ndarray, ziel_R: np.ndarray, z: Lagezustand,
                 rng, folge=None, merkname: Optional[str] = None) -> Tuple[List[List[np.ndarray]], np.ndarray, object]:
        """Gelenkfahrt von qa zur Zielpose; bei Kollision ueber Zwischenpunkte
        senkrecht ueber Start und Ziel. ``folge(q_ziel)`` prueft den Weg danach
        (z. B. hinab zum Greifen) und liefert dessen Ergebnis oder wirft PlanFehler.

        Liefert (Wegstuecke [lin hoch, ptp, lin hinab], q am Ziel, folge-Ergebnis).
        """
        pa = self.tcp_welt(qa)[:3, 3]
        letzter = "kein Startwert"
        # Gelenkfahrten: groesserer Abstand zu ruhenden Glaesern (Folgefehler der Antriebe),
        # ausser zu Glaesern, denen Start oder Ziel schon naeher sind (z. B. gerade abgestellt)
        gross = float(self.pl["glas_abstand_ptp_m"])
        kipp = float(self.pl["glas_kipp_max_grad"])
        ref = 1.0
        if z.halt is not None:
            ref = 1.0 if z.halt.koerper(self.tcp_welt(qa), self.w.glas_r, self.w.glas_h).rot[2, 2] >= 0 else -1.0

        def nahe_glaeser(*qs_):
            zz = Lagezustand(z.ruhend, set(), None, set(), gross)
            return {h.split("|")[1] for q_ in qs_ for h in self.treffer(q_, zz) if "|glas_" in h}

        for hub in [float(v) for v in self.pl["zwischenhub_m"]]:
            try:
                hoch = self.lin(pa, pa + [0, 0, hub], Ra, qa, z, rng) if hub > 0 else [qa.copy()]
            except PlanFehler as e:
                letzter = f"Zwischenpunkt ueber dem Start: {e}"
                continue
            qs = hoch[-1]
            ziel_vor = ziel_p + [0, 0, hub]
            name = f"{merkname}@{hub}" if merkname else None
            for qv in self.kandidaten(qs, ziel_vor, ziel_R, rng, name):
                qv[self.ifg] = qa[self.ifg]
                zp = Lagezustand(z.ruhend, set(), z.halt, z.auflage, gross, nahe_glaeser(qs, qv), kipp, ref)
                h = self.treffer(qv, zp)
                if h:
                    letzter = "Ziel kollidiert: " + ", ".join(h[:3])
                    continue
                try:
                    runter = self.lin(ziel_vor, ziel_p, ziel_R, qv, z, rng) if hub > 0 else [qv]
                except PlanFehler as e:
                    letzter = f"Zwischenpunkt ueber dem Ziel: {e}"
                    continue
                h = self.ptp_frei(qs, qv, zp)
                ueber = None
                if h:
                    # Zwischenpunkt Ruhepose (Arm hoch ueber dem Fuss), Finger wie am Start
                    qr = self.ruhepose()
                    qr[self.ifg] = qa[self.ifg]
                    if not self.ptp_frei(qs, qr, zp) and not self.ptp_frei(qr, qv, zp):
                        ueber = qr
                    else:
                        letzter = "Gelenkfahrt kollidiert: " + ", ".join(h[:3])
                        continue
                qz = runter[-1]
                try:
                    erg = folge(qz) if folge else None
                except PlanFehler as e:
                    letzter = f"Folgeweg: {e}"
                    continue
                if name:
                    self.merk[name] = qv.copy()
                stuecke = []
                if hub > 0:
                    stuecke.append(hoch)
                if ueber is not None:
                    stuecke += [[qs, ueber], [ueber, qv]]
                else:
                    stuecke.append([qs, qv])
                if hub > 0:
                    stuecke.append(runter)
                return stuecke, qz, erg
        raise PlanFehler(letzter)

    # --- Ablauf ----------------------------------------------------------
    def ruhepose(self) -> np.ndarray:
        r = self.a["ablauf"]
        q = self.chain.q_from({k: math.radians(v) for k, v in r["ruhepose_grad"].items()})
        q[self.i7] = float(r["ruhepose_achse7_m"])
        q[self.ifg] = self.q_offen
        return q

    def dauer_fuer(self, wege: np.ndarray, t_min: float = T_MIN) -> float:
        k = len(wege) - 1
        if k == 0:
            return t_min
        dqds = np.max(np.abs(np.diff(wege, axis=0)), axis=0) * k
        return float(max(t_min, np.max(1.875 * dqds / self.vmax)))

    def plane(self) -> Tuple[Plan, List[GlasPlan]]:
        w, a, g = self.w, self.a, self.w.aufbau.sc["greifen"]
        rng = np.random.default_rng(self.seed)
        plan = Plan(self.chain, None)
        t = 0.0

        v_lin = float(a["planung"]["tcp_v_max_m_s"])
        a_lin = float(a["planung"]["tcp_a_max_m_s2"])

        def add(phase: str, wege, t_min: float = T_MIN, extra: float = 0.0, tempo: float = 1.0):
            nonlocal t
            arr = np.array(wege)
            d = self.dauer_fuer(arr, t_min) / tempo
            if len(arr) > 1:
                # TCP-Weg: ruckarmes Profil hat Spitzengeschwindigkeit 1,875 L/T und
                # Spitzenbeschleunigung 5,77 L/T^2 -> Mindestdauer je Grenze
                L = float(np.linalg.norm(self.tcp_welt(arr[-1])[:3, 3] - self.tcp_welt(arr[0])[:3, 3]))
                d = max(d, 1.875 * L / v_lin, math.sqrt(5.77 * L / a_lin))
            d += extra
            plan.segmente.append(Segment(phase, t, d, arr))
            t += d
            if os.environ.get("RAEUMWERK_PLAN_LOG"):
                print(f"PLAN {phase} t={t:.1f} ik={self.zaehler['ik']} pruef={self.zaehler['pruefpunkte']}",
                      file=sys.stderr, flush=True)

        def finger(qs, wert):
            out = []
            for q in qs:
                q = q.copy()
                q[self.ifg] = wert
                out.append(q)
            return out

        halte = float(a["greifer"]["haltezeit_s"])
        r_, h_ = w.glas_r, w.glas_h
        ruhend: Dict[int, sg.Koerper] = {i: k for i, k in enumerate(w.glas_start)}
        q = self.ruhepose()
        h0 = self.treffer(q, Lagezustand(list(ruhend.values())))
        if h0:
            raise PlanFehler("Ruhepose kollidiert: " + ", ".join(h0))
        add("start", [q], t_min=0.3)
        glaeser: List[GlasPlan] = []
        za, sg_ = a["zwischenablage"], a["seitgriff"]
        for nr, (s1, z1) in enumerate(a["ablauf"]["zuordnung"]):
            s, zi = int(s1) - 1, int(z1) - 1
            gp = GlasPlan(nr, s, zi, t0=t)
            G = w.glas_start[s]
            name = G.name
            pfx = f"{s + 1}:"
            andere = lambda: [k for i, k in ruhend.items() if i != s]  # noqa: E731

            # 1) Griff von oben im Korb ------------------------------------
            rand_z = G.mitte[2] - h_ / 2.0
            p_greif = np.array([G.mitte[0], G.mitte[1], rand_z + float(g["tcp_ueber_glasrand_m"])])
            p_vor = p_greif + [0, 0, float(g["vorposition_m"])]
            p_aus = p_greif + [0, 0, float(g["aushub_m"])]
            z_frei = Lagezustand(list(ruhend.values()), {name})
            ergebnis = None
            letzter = ""
            for gier in [float(v) for v in g["slot_gier_grad"]]:
                R = r_greif(gier)

                def folge_korb(qv, R=R):
                    runter = self.lin(p_vor, p_greif, R, qv, z_frei, rng)
                    halt = Halt(s, self._mitte_tcp(runter[-1], G.mitte), self._rot_tcp(runter[-1], G.rot))
                    z_trag = Lagezustand(andere(), set(), halt, {"oberkorb_boden"})
                    hoch = self.lin(p_greif, p_aus, R, finger([runter[-1]], self.q_zu)[0], z_trag, rng)
                    return runter, halt, hoch

                try:
                    # Gelenkfahrt: Finger duerfen das Glas NICHT beruehren (nur beim geraden Hinabfahren)
                    stuecke, qv, (runter, halt, hoch) = self.verbinde(q, self._rot(q), p_vor, R,
                                                                      Lagezustand(list(ruhend.values())), rng, folge_korb,
                                                                      f"korb{s}:{gier:.0f}")
                    ergebnis = (R, gier, stuecke, runter, halt, hoch)
                    break
                except PlanFehler as e:
                    letzter = str(e)
            if ergebnis is None:
                raise PlanFehler(f"Glas {s + 1}: Griff im Korb nicht planbar ({letzter})")
            R, gier, stuecke, runter, halt, hoch = ergebnis
            for st in stuecke:
                add(pfx + "anfahrt_korb", st)
            add(pfx + "runter_korb", runter)
            add(pfx + "greifen_korb", [runter[-1], finger([runter[-1]], self.q_zu)[0]], extra=halte)
            add(pfx + "aushub", hoch)
            gp.info["gier_oben_grad"] = gier
            del ruhend[s]
            q = hoch[-1]

            # 2) Glas kopfueber auf die Zwischenablage ----------------------
            zw = w.matte_fuer(zi)
            ziel_zw = w.glas_auf_zwischenablage(s, zw)
            ziel_zw.mitte[2] += float(za["absetzen_luft_m"])
            p_zw = self._tcp_fuer_glas(ziel_zw.mitte, R, halt)
            p_zw_vor = p_zw + [0, 0, float(za["vorposition_m"])]
            z_trag = Lagezustand(list(ruhend.values()), set(), halt)
            z_ab = Lagezustand(list(ruhend.values()), set(), halt, {zw.name})
            glas_zw = w.glas_auf_zwischenablage(s, zw)
            gp.info["zwischenablage"] = zw.name

            def folge_zw(qv):
                ab = self.lin(p_zw_vor, p_zw, R, qv, z_ab, rng)
                z_los = Lagezustand(list(ruhend.values()) + [glas_zw], {name})
                hoch_ = self.lin(p_zw, p_zw_vor, R, finger([ab[-1]], self.q_offen)[0], z_los, rng)
                return ab, hoch_

            stuecke, qv, (ab, hoch_zw) = self.verbinde(q, R, p_zw_vor, R, z_trag, rng, folge_zw, f"zw:{gier:.0f}")
            for st in stuecke:
                add(pfx + "zur_zwischenablage", st)
            add(pfx + "absetzen_zw", ab)
            add(pfx + "loesen_zw", [ab[-1], finger([ab[-1]], self.q_offen)[0]], extra=halte)
            add(pfx + "hoch_zw", hoch_zw)
            q = hoch_zw[-1]
            ruhend[s] = glas_zw

            # 3) Seitgriff, anheben, umdrehen ---------------------------------
            d_griff = float(sg_["hoehe_ab_glasboden_m"])
            # kopfueber: Glasboden oben
            p_glas_griff = np.array([glas_zw.mitte[0], glas_zw.mitte[1], glas_zw.oben - d_griff])
            ergebnis = None
            letzter = ""
            z_frei = Lagezustand(list(ruhend.values()), {name})
            for psi in [float(v) for v in sg_["gier_kandidaten_grad"]]:
                for oben in (1.0, -1.0):
                    Rs = r_seite(psi, oben)
                    av = Rs[:, 2]
                    p_s = p_glas_griff - float(sg_["tiefe_m"]) * av
                    p_s_vor = p_s - float(sg_["vorposition_m"]) * av
                    p_s_hub = p_s + [0, 0, float(sg_["anheben_m"])]

                    def folge_seite(qv, Rs=Rs, p_s=p_s, p_s_vor=p_s_vor, p_s_hub=p_s_hub):
                        hin = self.lin(p_s_vor, p_s, Rs, qv, z_frei, rng)
                        q_g = finger([hin[-1]], self.q_zu)[0]
                        halt2 = Halt(s, self._mitte_tcp(hin[-1], glas_zw.mitte), self._rot_tcp(hin[-1], glas_zw.rot))
                        andere_ = [k for i, k in ruhend.items() if i != s]
                        z_t = Lagezustand(andere_, set(), halt2, {zw.name})
                        hub = self.lin(p_s, p_s_hub, Rs, q_g, z_t, rng)
                        q6 = float(hub[-1][self.i6])
                        q_f = hub[-1].copy()
                        q_f[self.i6] = q6 - math.pi if q6 > 0 else q6 + math.pi
                        if not self.chain.within_limits(q_f, 1e-6):
                            raise PlanFehler(f"Umdrehen: Gelenk 6 bei {math.degrees(q6):.1f} Grad, "
                                             f"+-180 Grad liegt ausserhalb der Grenzen")
                        z_t2 = Lagezustand(andere_, set(), halt2)
                        hh = self.ptp_frei(hub[-1], q_f, z_t2)
                        if hh:
                            raise PlanFehler("Umdrehen kollidiert: " + ", ".join(hh[:3]))
                        return hin, halt2, hub, q_f

                    try:
                        stuecke, qv, erg = self.verbinde(q, R, p_s_vor, Rs, Lagezustand(list(ruhend.values())), rng,
                                                          folge_seite, f"seite:{psi:.0f}:{oben:.0f}")
                        ergebnis = (psi, oben, Rs, stuecke) + erg
                        break
                    except PlanFehler as e:
                        letzter += f" | Gier {psi:.0f}/{oben:+.0f}: {e}"
                if ergebnis is not None:
                    break
            if ergebnis is None:
                raise PlanFehler(f"Glas {s + 1}: Seitgriff/Umdrehen nicht planbar ({letzter})")
            psi, oben, Rs, stuecke, hin, halt2, hub, q_f = ergebnis
            for st in stuecke:
                add(pfx + "anfahrt_seite", st)
            add(pfx + "zu_seite", hin)
            add(pfx + "greifen_seite", [hin[-1], finger([hin[-1]], self.q_zu)[0]], extra=halte)
            add(pfx + "anheben", hub)
            # Gelenk 6 allein: Tempo relativ zu geschwindigkeit_anteil (<= Datenblatt)
            add(pfx + "umdrehen", [hub[-1], q_f],
                tempo=min(float(a["greifer"]["umdrehen_anteil"]), 1.0) / float(a["greifer"]["geschwindigkeit_anteil"]))
            gp.info.update({"gier_seite_grad": psi, "greifer_x_oben": oben,
                            "j6_vor_grad": math.degrees(float(hub[-1][self.i6])),
                            "j6_nach_grad": math.degrees(float(q_f[self.i6])),
                            "j5_umdrehen_grad": math.degrees(float(q_f[self.chain.index["joint5"]]))})
            del ruhend[s]
            q = q_f
            R_f = self._rot(q)

            # 4) aufrecht auf die Ablage ---------------------------------------
            Z = w.glas_ziel[zi]
            ziel_m = Z.mitte + [0, 0, float(sg_["absetzen_luft_m"])]
            ergebnis = None
            letzter = ""
            # erst gerader Weg mit Drehung um die Senkrechte (Glas bleibt aufrecht),
            # sonst Gelenkfahrt mit Neigungsgrenze und Zwischenpunkten
            p_f = self.tcp_welt(q)[:3, 3]
            gross = float(self.pl["glas_abstand_ptp_m"])
            for modus in [str(m_) for m_ in self.pl["ablage_wege"]]:
                for psi2 in [float(v) for v in sg_["gier_kandidaten_grad"]]:
                    R2 = r_seite(psi2, -oben)
                    p_ab = self._tcp_fuer_glas(ziel_m, R2, halt2)
                    p_ab_vor = p_ab + [0, 0, float(sg_["ablage_vorposition_m"])]
                    a2 = R2[:, 2]
                    p_rueck = p_ab - float(sg_["rueckzug_m"]) * a2
                    z_t = Lagezustand(list(ruhend.values()), set(), halt2)
                    z_ab = Lagezustand(list(ruhend.values()), set(), halt2, {"arbeitsplatte"})
                    glas_fertig = ag.glas(name, Z.mitte, np.eye(3), r_, h_)

                    def folge_ab(qv, R2=R2, p_ab=p_ab, p_ab_vor=p_ab_vor, p_rueck=p_rueck, z_ab=z_ab, glas_fertig=glas_fertig):
                        ab_ = self.lin(p_ab_vor, p_ab, R2, qv, z_ab, rng)
                        z_los = Lagezustand(list(ruhend.values()) + [glas_fertig], {name})
                        rueck = self.lin(p_ab, p_rueck, R2, finger([ab_[-1]], self.q_offen)[0], z_los, rng)
                        return ab_, rueck

                    try:
                        if modus == "gerade":
                            weg = self.lin(p_f, p_ab_vor, R_f, q, Lagezustand(list(ruhend.values()), set(), halt2,
                                                                             set(), gross), rng, R_ende=R2)
                            ab_, rueck = folge_ab(weg[-1])
                            stuecke = [weg]
                        else:
                            stuecke, qv, (ab_, rueck) = self.verbinde(q, R_f, p_ab_vor, R2, z_t, rng, folge_ab,
                                                                       f"ablage{zi}:{psi2:.0f}")
                        ergebnis = (psi2, stuecke, ab_, rueck, glas_fertig)
                        break
                    except PlanFehler as e:
                        letzter += f" | {modus} Gier {psi2:.0f}: {e}"
                if ergebnis is not None:
                    gp.info["weg_zur_ablage"] = modus
                    break
            if ergebnis is None:
                raise PlanFehler(f"Glas {s + 1}: Ablage {zi + 1} nicht planbar ({letzter})")
            psi2, stuecke, ab_, rueck, glas_fertig = ergebnis
            for st in stuecke:
                add(pfx + "zur_ablage", st)
            add(pfx + "absetzen", ab_)
            add(pfx + "loesen", [ab_[-1], finger([ab_[-1]], self.q_offen)[0]], extra=halte)
            add(pfx + "rueckzug", rueck)
            gp.info["gier_ablage_grad"] = psi2
            ruhend[s] = glas_fertig
            q = rueck[-1]
            gp.t1 = t
            glaeser.append(gp)

        # zurueck in die Ruhepose (bei Bedarf erst senkrecht hoch)
        z_end = Lagezustand(list(ruhend.values()))
        qh = self.ruhepose()
        if self.ptp_frei(q, qh, z_end):
            pa = self.tcp_welt(q)[:3, 3]
            hoch = self.lin(pa, pa + [0, 0, 0.1], self._rot(q), q, z_end, rng)
            hh = self.ptp_frei(hoch[-1], qh, z_end)
            if hh:
                raise PlanFehler("Rueckfahrt in die Ruhepose kollidiert: " + ", ".join(hh[:3]))
            add("hoch_heim", hoch)
            q = hoch[-1]
        add("heim", [q, qh])
        add("nachlauf", [qh], t_min=float(a["greifer"]["nachlauf_s"]))
        return plan, glaeser

    # --- Hilfen ----------------------------------------------------------
    def _rot(self, q: np.ndarray) -> np.ndarray:
        return self.tcp_welt(q)[:3, :3]

    def _mitte_tcp(self, q: np.ndarray, mitte: np.ndarray) -> np.ndarray:
        t = self.tcp_welt(q)
        return t[:3, :3].T @ (np.asarray(mitte) - t[:3, 3])

    def _rot_tcp(self, q: np.ndarray, rot: np.ndarray) -> np.ndarray:
        return self._rot(q).T @ rot

    @staticmethod
    def _tcp_fuer_glas(mitte: np.ndarray, R: np.ndarray, halt: Halt) -> np.ndarray:
        """TCP-Lage, bei der die Glasmitte bei ``mitte`` liegt (Orientierung R)."""
        return np.asarray(mitte, float) - R @ halt.mitte_tcp
