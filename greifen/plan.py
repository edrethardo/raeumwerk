"""Ablaufplanung der Greifdemo: kleine Zustandsmaschine ueber IK-Wegpunkte.

Phasen (in dieser Reihenfolge, jede genau einmal)::

    start -> vorposition -> anfahrt -> greifen -> anheben -> verfahren
          -> absetzen -> loesen -> rueckzug -> nachlauf

Der Greifer zeigt senkrecht nach unten, die Finger schliessen entlang der
Schiene (Welt-x). Die 7. Achse folgt der x-Lage des TCP (Fuss steht ueber
dem Glas), den Rest loest die IK der sechs Armgelenke. Gerade TCP-Wege
(Anfahrt, Anheben, Verfahren, Absetzen, Rueckzug) werden in Wegpunkte von
hoechstens 1 cm zerlegt und je Wegpunkt per IK geloest (warm gestartet).

Zeitverlauf je Phase: ruckarmes Profil s(tau) = 10 tau^3 - 15 tau^4 + 6 tau^5
ueber die Wegpunkte; die Dauer folgt aus den Datenblattgeschwindigkeiten
(Anteil ``greifen.geschwindigkeit_anteil``). Ergebnis ist eine Soll-Trajektorie
q(t), qd(t) fuer alle aktiven Gelenke, die der Simulator als Positionsziel mit
Geschwindigkeitsvorsteuerung faehrt. Alles deterministisch (fester Seed fuer
die IK-Neustarts).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from rebel_model.collision import SelfCollision, obb_penetration
from rebel_model.config import RobotConfig
from rebel_model.kinematics import Chain

from .szene import Szene

ARM = ["joint1", "joint2", "joint3", "joint4", "joint5", "joint6"]
PHASEN = ["start", "vorposition", "anfahrt", "greifen", "anheben", "verfahren",
          "absetzen", "loesen", "rueckzug", "nachlauf"]
# Greifer senkrecht nach unten; Greifer-y (Schliessrichtung) = Welt -x
R_GREIF = np.array([[0.0, -1.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 0.0, -1.0]])
HOME = {"joint1": -90.0, "joint2": 0.0, "joint3": 90.0, "joint5": 90.0}  # Grad
SCHRITT_M = 0.01
T_MIN = 0.5


@dataclass
class Versuch:
    nr: int
    art: str  # demo | variation | negativ
    start_xy: Tuple[float, float]
    ziel_xy: Tuple[float, float]
    greif_versatz: Tuple[float, float, float] = (0.0, 0.0, 0.0)

    def as_dict(self) -> dict:
        return {"nr": self.nr, "art": self.art, "start_xy_m": list(self.start_xy),
                "ziel_xy_m": list(self.ziel_xy), "greif_versatz_m": list(self.greif_versatz)}


@dataclass
class Segment:
    phase: str
    t0: float
    dauer: float
    wege: np.ndarray  # (k+1, n_aktiv), gleichmaessig in s


@dataclass
class Plan:
    chain: Chain
    versuch: Versuch
    segmente: List[Segment] = field(default_factory=list)
    ok: bool = True
    fehler: List[str] = field(default_factory=list)
    tcp_soll: Dict[str, List[float]] = field(default_factory=dict)
    ik_max_fehler_m: float = 0.0
    tisch_abstand_min_m: float = math.inf
    selbstkollision: List[str] = field(default_factory=list)

    @property
    def dauer(self) -> float:
        s = self.segmente[-1]
        return s.t0 + s.dauer

    def phase_zeiten(self) -> Dict[str, Tuple[float, float]]:
        return {s.phase: (s.t0, s.t0 + s.dauer) for s in self.segmente}

    def sample(self, t: float) -> Tuple[np.ndarray, np.ndarray, str]:
        """Soll-Lage, Soll-Geschwindigkeit und Phase zur Zeit t."""
        seg = self.segmente[-1]
        for s in self.segmente:
            if t < s.t0 + s.dauer:
                seg = s
                break
        tau = min(1.0, max(0.0, (t - seg.t0) / seg.dauer))
        sv = tau ** 3 * (10 - 15 * tau + 6 * tau * tau)
        dsv = 30 * tau * tau * (1 - tau) ** 2 / seg.dauer
        k = len(seg.wege) - 1
        if k == 0:
            return seg.wege[0].copy(), np.zeros(seg.wege.shape[1]), seg.phase
        x = sv * k
        i = min(int(x), k - 1)
        f = x - i
        q = seg.wege[i] + f * (seg.wege[i + 1] - seg.wege[i])
        qd = (seg.wege[i + 1] - seg.wege[i]) * k * dsv
        return q, qd, seg.phase


def tcp_offset(cfg: RobotConfig) -> List[float]:
    return [0.0, 0.0, cfg.greifer["tcp_ab_flansch_m"]]


def finger_q(cfg: RobotConfig, oeffnung: float) -> float:
    """Fingergelenkwert fuer eine Oeffnung (Abstand der Fingerinnenseiten)."""
    return (oeffnung - cfg.min_oeffnung) / 2.0


def tisch_box(sz: Szene) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    gx, gy, gz = sz.tisch["groesse_m"]
    mx, my = sz.tisch["mitte_xy_m"]
    return np.array([mx, my, gz / 2.0]), np.eye(3), np.array([gx, gy, gz]) / 2.0


def basis_x0(chain: Chain) -> float:
    """x des Roboterfusses bei Achswert 0."""
    return float(chain.fk(chain.zero(), "base_link")[0, 3])


def versuche(sz: Szene, art: str) -> List[Versuch]:
    """Versuchsliste: ``demo`` (1), ``variation`` (N, fester Seed), ``negativ`` (1)."""
    start = tuple(float(v) for v in sz.glas["start_xy_m"])
    ziel = tuple(float(v) for v in sz.glas["ziel_xy_m"])
    if art == "demo":
        return [Versuch(0, "demo", start, ziel)]
    if art == "negativ":
        return [Versuch(0, "negativ", start, ziel, tuple(float(v) for v in sz.negativtest["greifpunkt_versatz_m"]))]
    if art == "variation":
        rng = np.random.default_rng(int(sz.variation["seed"]))
        d = float(sz.variation["streuung_xy_m"])
        out = []
        for i in range(int(sz.variation["versuche"])):
            dx, dy = rng.uniform(-d, d, size=2)
            out.append(Versuch(i, "variation", (start[0] + float(dx), start[1] + float(dy)), ziel))
        return out
    raise ValueError(f"unbekannte Versuchsart {art!r}")


class Planer:
    def __init__(self, chain: Chain, cfg: RobotConfig, sz: Szene, seed: int = 0):
        self.chain, self.cfg, self.sz = chain, cfg, sz
        self.tcp = tcp_offset(cfg)
        self.seed = seed
        self.sc = SelfCollision(chain)
        self.x0 = basis_x0(chain)
        anteil = float(sz.greifen["geschwindigkeit_anteil"])
        self.vmax = np.array([
            anteil * (cfg.achse7["geschwindigkeit_m_s"] if n == "axis7" else
                      cfg.greifer["geschwindigkeit_m_s"] if n == "finger_left" else
                      math.radians(cfg.arm["geschwindigkeit_grad_s"]))
            for n in chain.active])
        self.i7 = chain.index["axis7"]
        self.ifg = chain.index["finger_left"]
        self.q_offen = cfg.finger_hub
        dg = sz.glas["durchmesser_m"]
        self.q_kontakt = finger_q(cfg, dg)
        self.q_zu = self.q_kontakt - float(sz.greifen["greifkraft_n"]) / float(sz.greifen["finger_ke"])
        self.tisch = tisch_box(sz)

    # --- Bausteine -------------------------------------------------------
    def home(self) -> np.ndarray:
        q = self.chain.q_from({k: math.radians(v) for k, v in HOME.items()})
        q[self.i7] = self.achse7_fuer(float(self.sz.glas["start_xy_m"][0]))
        q[self.ifg] = self.q_offen
        return q

    def achse7_fuer(self, x: float) -> float:
        j = self.chain.by_name["axis7"]
        return float(min(j.upper, max(j.lower, x - self.x0)))

    def ik(self, p: Sequence[float], q0: np.ndarray, rng: np.random.Generator) -> Tuple[np.ndarray, float, bool]:
        t = np.eye(4)
        t[:3, :3] = R_GREIF
        t[:3, 3] = p
        q0 = q0.copy()
        q0[self.i7] = self.achse7_fuer(p[0])
        q, pe, re, ok = self.chain.ik(t, "gripper_base", q0, ARM, offset=self.tcp, restarts=8, rng=rng,
                                      tol_pos=1e-5, tol_rot=1e-4)
        return q, pe, ok

    def tisch_abstand(self, q: np.ndarray) -> float:
        """Kleinster Abstand (negativ = Durchdringung) Roboterquader <-> Tisch, grob ueber SAT."""
        c2, r2, h2 = self.tisch
        best = math.inf
        for name, boxes in self.sc.world_boxes(q).items():
            for c1, r1, h1 in boxes:
                best = min(best, -obb_penetration(c1, r1, h1, c2, r2, h2))
        return best

    def dauer_fuer(self, wege: np.ndarray, t_min: float = T_MIN) -> float:
        k = len(wege) - 1
        if k == 0:
            return t_min
        dqds = np.max(np.abs(np.diff(wege, axis=0)), axis=0) * k
        return float(max(t_min, np.max(1.875 * dqds / self.vmax)))

    # --- Ablauf ----------------------------------------------------------
    def plane(self, v: Versuch) -> Plan:
        sz, g = self.sz, self.sz.greifen
        plan = Plan(self.chain, v)
        rng = np.random.default_rng(self.seed)
        dx, dy, dz = v.greif_versatz
        z_greif = sz.tisch_oben + float(g["tcp_ueber_tisch_m"]) + dz
        p_greif = np.array([v.start_xy[0] + dx, v.start_xy[1] + dy, z_greif])
        p_vor = p_greif + [0, 0, float(g["vorposition_ueber_greifpunkt_m"])]
        p_hub = p_greif + [0, 0, float(g["hub_m"])]
        p_ab = np.array([v.ziel_xy[0] + dx, v.ziel_xy[1] + dy, z_greif + float(g["absetzen_luft_m"])])
        p_zhub = np.array([p_ab[0], p_ab[1], p_hub[2]])
        p_rueck = p_ab + [0, 0, float(g["rueckzug_m"])]
        plan.tcp_soll = {"greifen": p_greif.tolist(), "vorposition": p_vor.tolist(), "anheben": p_hub.tolist(),
                         "verfahren": p_zhub.tolist(), "absetzen": p_ab.tolist(), "rueckzug": p_rueck.tolist()}

        q = self.home()
        t = 0.0

        def add(phase: str, wege: List[np.ndarray], t_min: float = T_MIN, extra: float = 0.0):
            nonlocal t
            w = np.array(wege)
            d = self.dauer_fuer(w, t_min) + extra
            plan.segmente.append(Segment(phase, t, d, w))
            t += d

        def gerade(a: np.ndarray, b: np.ndarray, q_start: np.ndarray) -> List[np.ndarray]:
            n = max(1, int(math.ceil(np.linalg.norm(b - a) / SCHRITT_M)))
            out, qc = [q_start.copy()], q_start.copy()
            for i in range(1, n + 1):
                p = a + (b - a) * i / n
                qn, pe, ok = self.ik(p, qc, rng)
                plan.ik_max_fehler_m = max(plan.ik_max_fehler_m, pe)
                if not ok:
                    plan.ok = False
                    plan.fehler.append(f"IK ohne Loesung bei {np.round(p, 4).tolist()} (Fehler {pe * 1e3:.2f} mm)")
                qn[self.ifg] = q_start[self.ifg]
                out.append(qn)
                qc = qn
            return out

        add("start", [q], t_min=0.3)
        q_vor, pe, ok = self.ik(p_vor, q, rng)
        plan.ik_max_fehler_m = max(plan.ik_max_fehler_m, pe)
        if not ok:
            plan.ok = False
            plan.fehler.append(f"IK ohne Loesung fuer die Vorposition (Fehler {pe * 1e3:.2f} mm)")
        q_vor[self.ifg] = self.q_offen
        add("vorposition", [q, q_vor])
        w = gerade(p_vor, p_greif, q_vor)
        add("anfahrt", w)
        q_g = w[-1].copy()
        q_zu = q_g.copy()
        q_zu[self.ifg] = self.q_zu
        add("greifen", [q_g, q_zu], extra=float(g["haltezeit_s"]))
        w = gerade(p_greif, p_hub, q_zu)
        add("anheben", w)
        w = gerade(p_hub, p_zhub, w[-1])
        add("verfahren", w)
        w = gerade(p_zhub, p_ab, w[-1])
        add("absetzen", w)
        q_ab = w[-1].copy()
        q_los = q_ab.copy()
        q_los[self.ifg] = self.q_offen
        add("loesen", [q_ab, q_los], extra=float(g["haltezeit_s"]))
        w = gerade(p_ab, p_rueck, q_los)
        add("rueckzug", w)
        add("nachlauf", [w[-1]], t_min=float(g["nachlauf_s"]))

        # kinematische Vorpruefung jedes Wegpunkts
        for s in plan.segmente:
            for qq in s.wege:
                if not self.chain.within_limits(qq, 1e-6):
                    plan.ok = False
                    plan.fehler.append(f"Gelenkgrenze verletzt in Phase {s.phase}")
                    break
                plan.tisch_abstand_min_m = min(plan.tisch_abstand_min_m, self.tisch_abstand(qq))
                for a, b, d in self.sc.collisions(qq):
                    tag = f"{s.phase}:{a}|{b}"
                    if tag not in plan.selbstkollision:
                        plan.selbstkollision.append(tag)
        if plan.selbstkollision:
            plan.ok = False
            plan.fehler.append("Selbstkollision im Plan: " + ", ".join(plan.selbstkollision[:5]))
        if plan.tisch_abstand_min_m < 0:
            plan.ok = False
            plan.fehler.append(f"Plan beruehrt den Tisch ({plan.tisch_abstand_min_m * 1e3:.1f} mm)")
        return plan

    def max_geschwindigkeit(self, plan: Plan, dt: float = 0.002) -> np.ndarray:
        """Groesste Soll-Geschwindigkeit je Gelenk (zum Pruefen gegen die Grenzen)."""
        ts = np.arange(0.0, plan.dauer, dt)
        return np.max(np.abs(np.array([plan.sample(t)[1] for t in ts])), axis=0)
