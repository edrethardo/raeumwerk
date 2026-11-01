"""Arbeitsbelastung und Ruhepose eines Aufbaus (Ergaenzung zu ``raeumwerk aufbau``).

- ``statistik``: Maximum, Median und Anteil unter Nenn/Max einer Reihe von Haltemomenten.
- ``weg_momente``: Schweremomente entlang eines gelenklinearen Wegs (Schaetzung, ohne Kollision).
- ``rms_ablauf``: Dauerlast als RMS-Moment ueber einen Ablauf aus Phasen mit Zeitanteilen.
- ``suche_ruhepose``: Gelenkstellung mit kleinen Schweremomenten in J2/J3, kollisionsfrei bei
  offener und geschlossener Tuer (Koerbe eingeschoben) und ausserhalb eines Bedienraums
  (Quader, in dem der Mensch Tuer und Koerbe bedient).

Alle Momente ueber ``aufbau.schweremomente`` (Glieder am Schwerpunkt, Last im TCP).
"""
from __future__ import annotations

import copy
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import aufbau as AU

NENN_NM = 10.0
MAX_NM = 12.5
TUER_ZU = {"tuer": {"oeffnung_grad": 0.0}}


# --- Statistik und Dauerlast --------------------------------------------------------------

def statistik(werte: Sequence[float], nenn: float = NENN_NM, maxi: float = MAX_NM) -> Dict[str, Any]:
    """Betragsmaximum, Median und Anteile <= Nenn bzw. <= Max (leere Reihe: n = 0)."""
    w = np.abs(np.asarray(list(werte), float))
    if w.size == 0:
        return {"n": 0, "max": None, "median": None, "unter_nenn": None, "unter_max": None}
    return {"n": int(w.size), "max": round(float(w.max()), 2), "median": round(float(np.median(w)), 2),
            "unter_nenn": round(float(np.mean(w <= nenn)), 3), "unter_max": round(float(np.mean(w <= maxi)), 3)}


def rms_ablauf(phasen: Sequence[Tuple[float, Sequence[float]]]) -> float:
    """RMS-Moment eines Ablaufs: ``phasen`` = [(Zeitanteil, Momente in dieser Phase), ...];
    innerhalb einer Phase gleich verteilt, die Anteile werden auf 1 normiert."""
    summe, anteile = 0.0, 0.0
    for a, t in phasen:
        t = np.asarray(list(t), float)
        if t.size == 0 or a <= 0:
            continue
        summe += float(a) * float(np.mean(t ** 2))
        anteile += float(a)
    if anteile <= 0:
        raise ValueError("rms_ablauf: keine Phase mit Zeitanteil > 0")
    return math.sqrt(summe / anteile)


def schweremomente(p, q, last_kg: float = 0.0) -> np.ndarray:
    """Wie ``aufbau.schweremomente`` (gleiches Ergebnis), aber mit einer Vorwaertsrechnung je
    Stellung statt einer Jacobi-Matrix je Glied (~10x schneller, fuer Gitter-Suchen)."""
    ch = p.chain
    q = np.asarray(q, float)
    poses = ch.fk_all(q)
    g_rob = p.Tinv[:3, :3] @ np.array([0.0, 0.0, -AU.G])
    punkte = [(poses[n][:3, :3] @ ln.com + poses[n][:3, 3], ln.mass, n) for n, ln in ch.links.items()
              if ln.mass > 0 and n not in ("rail", "carriage")]
    if last_kg:
        T = poses["gripper_base"]
        punkte.append((T[:3, :3] @ np.asarray(p.tcp, float) + T[:3, 3], float(last_kg), "gripper_base"))
    tg = np.zeros(len(q))
    for pt, m, n in punkte:
        F = m * g_rob
        for j in ch.path(n):
            if j.type == "fixed":
                continue
            lead = j.mimic[0] if j.mimic else j.name
            if lead not in ch.index:
                continue
            mult = j.mimic[1] if j.mimic else 1.0
            fr = poses[j.parent] @ j.origin
            a = fr[:3, :3] @ (j.axis / np.linalg.norm(j.axis))
            if j.type == "prismatic":
                tg[ch.index[lead]] += mult * float(a @ F)
            else:
                tg[ch.index[lead]] += mult * float(a @ np.cross(pt - fr[:3, 3], F))
    return tg


def gelenkweg(q_a: np.ndarray, q_b: np.ndarray, n: int = 21) -> np.ndarray:
    """Gelenklinearer Weg (n Punkte, beide Enden eingeschlossen)."""
    s = np.linspace(0.0, 1.0, n)[:, None]
    return (1.0 - s) * np.asarray(q_a, float)[None] + s * np.asarray(q_b, float)[None]


def weg_momente(p, q_a, q_b, last_kg: float = 0.0, n: int = 21) -> np.ndarray:
    """Signierte Schweremomente (n, len(q)) entlang ``gelenkweg(q_a, q_b, n)``."""
    return np.array([schweremomente(p, q, last_kg) for q in gelenkweg(q_a, q_b, n)])


# --- Geometrie: Roboterquader, Abstaende ------------------------------------------------------

def roboter_aabbs(p, q) -> Tuple[List[str], np.ndarray]:
    """Weltachsen-Huellquader (n, 2, 3) aller Kollisionsquader des Roboters in Stellung q."""
    wb = p.self_coll.world_boxes(np.asarray(q, float))
    Rw, tw = p.T[:3, :3], p.T[:3, 3]
    namen, out = [], []
    for n, boxes in wb.items():
        for c, r, h in boxes:
            cw = Rw @ c + tw
            ext = np.abs(Rw @ r) @ h
            namen.append(n)
            out.append([cw - ext, cw + ext])
    return namen, np.array(out)


def aabb_abstand(lo1, hi1, lo2, hi2) -> float:
    """Abstand zweier achsparalleler Quader; < 0: Eindringtiefe (kleinste Ueberlappung)."""
    lo1, hi1, lo2, hi2 = (np.asarray(v, float) for v in (lo1, hi1, lo2, hi2))
    luecke = np.maximum(lo2 - hi1, lo1 - hi2)
    if np.any(luecke > 0):
        return float(np.linalg.norm(np.maximum(luecke, 0.0)))
    return float(np.max(luecke))


def abstand_zu(p, q, lo, hi, ohne: Sequence[str] = ("rail", "carriage")) -> float:
    """Kleinster Abstand der Roboterquader (ohne Schiene/Schlitten) zum Quader lo..hi."""
    namen, bb = roboter_aabbs(p, q)
    w = [aabb_abstand(b[0], b[1], lo, hi) for n, b in zip(namen, bb) if n not in ohne]
    return min(w) if w else float("inf")


def tiefster_punkt(p, q, ohne: Sequence[str] = ("rail", "carriage")) -> float:
    namen, bb = roboter_aabbs(p, q)
    return float(min(b[0][2] for n, b in zip(namen, bb) if n not in ohne))


# --- Ruhepose -------------------------------------------------------------------------------

def ruhe_aufbau(d: Dict[str, Any], schrank: Optional[Dict[str, Any]] = None) -> "AU.Aufbau":
    """Aufbau fuer die Ruhepose: wie ``d`` (normalisiert), optional mit Haengeschrank als Hindernis
    (``{"lo": [...], "hi": [...]}``)."""
    d = copy.deepcopy(d)
    if schrank is not None:
        d["hindernisse"] = list(d.get("hindernisse", [])) + [
            {"name": "haengeschrank", "gruppe": "schrank", "lo": list(schrank["lo"]), "hi": list(schrank["hi"])}]
    return AU.Aufbau(d)


def haengt(p, q) -> bool:
    """True, wenn der Schwerpunkt aller Glieder hinter Gelenk 2 unter Gelenk 2 liegt (stabil haengend)."""
    q = np.asarray(q, float)
    ch = p.chain
    weiter = False
    m, s = 0.0, np.zeros(3)
    for name in ch.order:
        if name == "link_2":
            weiter = True
        ln = ch.links[name]
        if not weiter or ln.mass <= 0:
            continue
        m += ln.mass
        s += ln.mass * (p.T @ ch.fk(q, name, ln.com))[:3, 3]
    j2 = (p.T @ ch.fk(q, "link_2"))[:3, 3]
    return bool(m > 0 and s[2] / m < j2[2])


def _ziel(t: np.ndarray, i1: int, i2: int, i3: int) -> float:
    return abs(float(t[i2])) + abs(float(t[i3])) + 0.1 * abs(float(t[i1]))


def suche_ruhepose(A, a7: Optional[float] = None, bedienraum: Optional[Tuple[Sequence[float], Sequence[float]]] = None,
                   rand_m: float = 0.05, schritt_grad: float = 15.0, verfeinern: bool = True,
                   max_pruefungen: int = 4000) -> Dict[str, Any]:
    """Ruhepose mit kleinstem |tau2| + |tau3| (+ 0,1 |tau1|) bei Achsstellung ``a7`` (Standard:
    5 cm unter dem oberen Anschlag). Bedingungen: keine Kollision bei offener und geschlossener
    Tuer mit eingeschobenen Koerben; mit ``bedienraum`` (lo, hi) halten alle Roboterquader mindestens
    ``rand_m`` Abstand davon. Grobes Gitter J1/J2/J3 (J4 = J6 = 0, J5 = 0), dann lokal feiner mit J5.
    Liefert q, Momente (signiert, Nm), Abstand zum Bedienraum, tiefsten Punkt, Haengen ja/nein;
    ``ok`` False, wenn keine Stellung alle Bedingungen erfuellt."""
    p_auf = A.pruefer(0.0, 0.0)
    p_zu = A.pruefer(0.0, 0.0, TUER_ZU)
    ch = p_auf.chain
    i1, i2, i3, i5 = (ch.index[n] for n in ("joint1", "joint2", "joint3", "joint5"))
    j7 = ch.by_name["axis7"]
    if a7 is None:
        a7 = max(j7.lower, j7.upper - 0.05)

    def grenzen(i):
        return math.degrees(ch.lower[i]), math.degrees(ch.upper[i])

    def gitter(i, schritt, um=None, breite=None):
        lo, hi = grenzen(i)
        if um is not None:
            lo, hi = max(lo, um - breite), min(hi, um + breite)
        return np.radians(np.arange(lo, hi + 1e-9, schritt))

    def kandidaten(werte1, werte2, werte3, werte5):
        out = []
        for a in werte1:
            for b in werte2:
                for c in werte3:
                    for e in werte5:
                        q = ch.zero()
                        q[p_auf.i7] = a7
                        q[i1], q[i2], q[i3], q[i5] = a, b, c, e
                        out.append(q)
        return out

    def zulaessig(q) -> Tuple[bool, float]:
        frei = float("inf")
        if bedienraum is not None:
            frei = abstand_zu(p_auf, q, bedienraum[0], bedienraum[1])
            if frei < rand_m:
                return False, frei
        if p_auf.kollisionen(q) or p_zu.kollisionen(q):
            return False, frei
        return True, frei

    def bester(qs):
        taus = [schweremomente(p_auf, q) for q in qs]
        reihen = sorted(range(len(qs)), key=lambda k: _ziel(taus[k], i1, i2, i3))
        geprueft = 0
        for k in reihen[:max_pruefungen]:
            geprueft += 1
            ok, frei = zulaessig(qs[k])
            if ok:
                return qs[k], taus[k], frei, geprueft
        return None, None, None, geprueft

    q, t, frei, n1 = bester(kandidaten(gitter(i1, schritt_grad), gitter(i2, schritt_grad),
                                       gitter(i3, schritt_grad), [0.0]))
    if q is None:
        return {"ok": False, "a7": round(float(a7), 3), "geprueft": n1}
    n2 = 0
    if verfeinern:
        f = schritt_grad / 3.0
        g = [math.degrees(q[i]) for i in (i1, i2, i3)]
        q2, t2, frei2, n2 = bester(kandidaten(gitter(i1, f, g[0], schritt_grad), gitter(i2, f, g[1], schritt_grad),
                                              gitter(i3, f, g[2], schritt_grad), np.radians([-60, -30, 0, 30, 60])))
        if q2 is not None and _ziel(t2, i1, i2, i3) <= _ziel(t, i1, i2, i3):
            q, t, frei = q2, t2, frei2
    arm = {n: round(float(t[ch.index[n]]), 3) for n in AU.ARM}
    return {"ok": True, "q": [round(float(v), 5) for v in q], "a7": round(float(a7), 3),
            "momente": arm, "summe_j2_j3": round(abs(arm["joint2"]) + abs(arm["joint3"]), 3),
            "max_arm": round(max(abs(v) for v in arm.values()), 3),
            "bedienraum_abstand_m": None if bedienraum is None else round(float(frei), 3),
            "tiefster_punkt_m": round(tiefster_punkt(p_auf, q), 3), "haengt": haengt(p_auf, q),
            "geprueft": n1 + n2}


def weg_frei(ps: Sequence[Any], q_a, q_b, n: int = 31) -> Dict[str, Any]:
    """Gelenklinearer Weg q_a -> q_b, Kollision in jeder Szene aus ``ps`` (Pruefer) je Wegpunkt.
    Liefert ok, erste Kollisionen und den groessten Gelenkweg der Armgelenke (Grad) sowie den Hub (m)."""
    hits: List[str] = []
    for q in gelenkweg(q_a, q_b, n):
        for p in ps:
            hits += p.kollisionen(q)
        if hits:
            break
    p0 = ps[0]
    ia = [p0.chain.index[k] for k in AU.ARM]
    dq = np.abs(np.asarray(q_b, float) - np.asarray(q_a, float))
    return {"ok": not hits, "kollisionen": sorted(set(hits))[:4],
            "gelenkweg_max_grad": round(float(np.degrees(dq[ia].max())), 1),
            "hub_m": round(float(dq[p0.i7]), 3)}
