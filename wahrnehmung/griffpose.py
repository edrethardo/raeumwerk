"""Szene -> Ensenso-Grobpose -> D405-Feinpose -> Griffpose (oder Abbruch mit Grund).

Ablauf je Objekt:
  1. Ensenso (fest am Mast, Ausleger ueber der Korbkante) nimmt den Korb auf; Instanzmaske des
     Ziels aus der Farbsegmentierung (Randrauschen), Schaetzer -> Grobpose.
  2. Der Greifer faehrt in die Vorposition ueber die Grobpose; die D405 am Greifer (60 mm seitlich,
     20 Grad geneigt) nimmt auf, Schaetzer -> Feinpose (Suchfenster um die Grobpose).
  3. Plausibilitaet: jeder Schaetzer fuer sich, dazu Ensenso und D405 muessen uebereinstimmen.
     Sonst Abbruch (kein Griff).
Negativtests (``negativ``): ``zwei_glaeser`` (Maske des Nachbarglases mit im Segment),
``teller_doppelt`` (Nachbarteller im Segment), ``versatz`` (Grobpose 15 mm daneben, z. B.
Kalibrierfehler), ``nachbar`` (falsches Objekt segmentiert: Nachbar statt Ziel).
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional

import numpy as np

from . import schaetzer as S
from .sensor import Fehlermodell, aufnehmen, kalibrierfehler, maske_verrauschen
from .strahlen import ENSENSO, Kamera, Prim, d405_am_greifer, greifer_prims, r_greif

ENSENSO_POSE = ((0.55, 0.40, 1.10), (0.30, 0.17, 0.48))   # Mast + Ausleger, Blick auf die Korbmitte
GLAS_GRIFF_UNTER_OBERKANTE = 0.022
VORPOSITION = 0.10
TOL_GLAS_M = 0.006       # Ensenso <-> D405 (xy)
TOL_TELLER_M = 0.008     # Ensenso <-> D405 (xyz)
KORB_SIGMA_M = 0.0015    # Korbpose aus der Ensenso (ICP an den Streben), angenommene Streuung


def prims_aus_welt(w, art: str) -> List[Prim]:
    """Statische Szene + Glaeser + Teller als Primitive (Gruppen fuer das Fehlermodell)."""
    out: List[Prim] = []
    stat = w.statisch_ohne_teller if art == "glas" else w.statisch
    for k in stat:
        if k.name in ("boden", "podest") or k.gruppe in ("glasfest",):
            continue
        out.append(Prim(k.name, k.gruppe, "box", np.asarray(k.mitte, float), np.asarray(k.halb, float),
                        np.asarray(k.rot, float), k.gruppe))
    if art == "glas":
        glaeser = list(w.glas_start)
        teller = list(w.teller)
    else:
        glaeser = list(getattr(w, "glaeser_statisch", []))
        teller = list(w.glas_start)
    for k in glaeser:
        name = k.name.replace("glasfest_", "glas_")
        out.append(Prim(name, "glas", "zyl", np.asarray(k.mitte, float), np.asarray(k.halb, float),
                        np.asarray(k.rot, float), name))
    for k in teller:
        out.append(Prim(k.name, "teller", "zyl", np.asarray(k.mitte, float), np.asarray(k.halb, float),
                        np.asarray(k.rot, float), k.name))
    return out


def ensenso(skala=2.0) -> Kamera:
    return Kamera.zielend("ensenso", ENSENSO, ENSENSO_POSE[0], ENSENSO_POSE[1], skala)


def _nachbar(prims, ziel: Prim, gruppe: str) -> Prim:
    kand = [p for p in prims if p.gruppe == gruppe and p.objekt != ziel.objekt]
    return min(kand, key=lambda p: float(np.linalg.norm(p.c - ziel.c)))


def _maske(auf, ziel: Prim, rng, negativ, prims, gruppe, fm=None):
    m = auf.maske_wahr(ziel.objekt)
    if negativ == "nachbar":
        m = auf.maske_wahr(_nachbar(prims, ziel, gruppe).objekt)
    elif negativ in ("zwei_glaeser", "teller_doppelt"):
        m = m | auf.maske_wahr(_nachbar(prims, ziel, gruppe).objekt)
    fm = fm or Fehlermodell()
    return maske_verrauschen(m, rng, fm.maske_rand_kippen, fm.maske_versatz_px)


def _glas(auf, maske, z_boden, c0, rng):
    return S.glas_schaetzen(auf, maske, z_boden, c0, rng=rng)


def schaetzen(art: str, w, s: int, seed: int = 0, negativ: Optional[str] = None, fm: Optional[Fehlermodell] = None,
              skala_ensenso: float = 2.0, skala_d405: float = 1.0, mit_aufnahmen: bool = False,
              soll_m=None, soll_tol_m: float = 0.015) -> Dict:
    """Griffpose fuer Objekt ``s`` (0-basiert) der Welt ``w`` (art 'glas' | 'teller').
    ``soll_m``: Platz laut Belegungsplan (Korbpose aus der Ensenso); liegt die Schaetzung mehr als
    ``soll_tol_m`` daneben, ist es nicht das geplante Objekt (z. B. Nachbar segmentiert) -> Abbruch."""
    rng = np.random.default_rng(10_000 + int(seed))
    fm = fm or Fehlermodell()
    prims = prims_aus_welt(w, art)
    gruppe = "glas" if art == "glas" else "teller"
    ziel_k = w.glas_start[s]
    ziel = [p for p in prims if p.objekt == ziel_k.name][0]
    wahr = np.asarray(ziel_k.mitte, float)
    out: Dict = {"art": art, "negativ": negativ, "fehlermodell": fm.raten(), "wahr_m": wahr.tolist(), "gruende": []}
    # Korbpose (Ensenso, ICP an den Streben): kleine Streuung um die Wahrheit; der Korb steht am
    # Anschlag, weiter heraus als ganz ausgezogen geht nicht
    out["korbauszug_delta_m"] = min(0.0, float(w.aufbau.abw.korbauszug_delta_m + rng.normal(0.0, KORB_SIGMA_M)))
    # 1. Ensenso
    cam_e = ensenso(skala_ensenso)
    auf_e = aufnehmen(prims, cam_e, rng, fm, roi=(wahr, 0.16))
    m_e = _maske(auf_e, ziel, rng, negativ, prims, gruppe, fm)
    kalibrierfehler(auf_e, rng, fm.kalib_ensenso_mm * 1e-3, fm.kalib_ensenso_grad)
    out["ensenso"] = {"statistik": auf_e.statistik(), "maske_px": int(m_e.sum())}
    if mit_aufnahmen:
        out["_aufnahmen"] = {"ensenso": (auf_e, m_e)}
    if art == "glas":
        h = float(ziel_k.halb[2]) * 2.0
        z_boden = float(wahr[2] - h / 2.0)          # aus dem Korbmodell (Halterhoehe)
        nominal = wahr[:2]                           # Suchstart: Platzmitte reicht (+-5 mm)
        e = _glas(auf_e, m_e, z_boden, nominal, rng)
        if negativ == "versatz" and "c" in e:
            e["c"] = (np.asarray(e["c"]) + [0.015, 0.0]).tolist()
        out["ensenso"].update({k: v for k, v in e.items() if k != "kandidaten"}, kandidaten=e.get("kandidaten"))
        if not e["ok"]:
            out["gruende"] += [f"ensenso:{g}" for g in e["gruende"]]
            out["ok"] = False
            return out
        c_e = np.asarray(e["c"], float)
        out["ensenso"]["fehler_mm"] = float(1e3 * np.linalg.norm(c_e - wahr[:2]))
        gier = 0.0
        tcp_vor = np.array([c_e[0], c_e[1], z_boden + e["r"] * 0 + h - GLAS_GRIFF_UNTER_OBERKANTE + VORPOSITION])
        oeffnung = 0.099
    else:
        n_soll = np.asarray(ziel_k.rot, float)[:, 2]
        e = S.teller_schaetzen(auf_e, m_e, n_soll, wahr, halbdicke=float(ziel_k.halb[2]), rng=rng)
        if negativ == "versatz" and "c" in e:
            e["c"] = (np.asarray(e["c"]) + [0.015, 0.0, 0.0]).tolist()
        out["ensenso"].update({k: v for k, v in e.items() if k != "kandidaten"}, kandidaten=e.get("kandidaten"))
        if not e["ok"]:
            out["gruende"] += [f"ensenso:{g}" for g in e["gruende"]]
            out["ok"] = False
            return out
        c_e = np.asarray(e["c"], float)
        out["ensenso"]["fehler_mm"] = float(1e3 * np.linalg.norm(c_e - wahr))
        gier = 90.0
        r_t = float(ziel_k.halb[0])
        tcp_vor = np.array([c_e[0], c_e[1], c_e[2] + r_t + 0.02 + VORPOSITION])
        oeffnung = 0.035
    # 2. D405 in der Vorposition ueber der Grobpose
    Rt = r_greif(gier)
    cam_d = d405_am_greifer(tcp_vor, Rt, skala=skala_d405)
    gp = greifer_prims(tcp_vor, Rt, oeffnung)
    auf_d = aufnehmen(prims + gp, cam_d, rng, fm, roi=(c_e if art == "teller" else np.r_[c_e, wahr[2]], 0.15))
    m_d = _maske(auf_d, ziel, rng, negativ, prims, gruppe, fm)
    kalibrierfehler(auf_d, rng, fm.kalib_d405_mm * 1e-3, fm.kalib_d405_grad)
    out["d405"] = {"statistik": auf_d.statistik(), "maske_px": int(m_d.sum()), "kamera_m": cam_d.C.tolist(),
                   "tcp_vor_m": tcp_vor.tolist()}
    if art == "glas":
        d = _glas(auf_d, m_d, z_boden, c_e, rng)
    else:
        d = S.teller_schaetzen(auf_d, m_d, np.asarray(e["normale"]), c_e, halbdicke=float(ziel_k.halb[2]), rng=rng)
    out["d405"].update({k: v for k, v in d.items() if k != "kandidaten"}, kandidaten=d.get("kandidaten"))
    if mit_aufnahmen:
        out["_aufnahmen"]["d405"] = (auf_d, m_d)
    if not d["ok"]:
        out["gruende"] += [f"d405:{g}" for g in d["gruende"]]
        out["ok"] = False
        return out
    c_d = np.asarray(d["c"], float)
    if art == "glas":
        abw = float(np.linalg.norm(c_d - c_e))
        tol = TOL_GLAS_M
        pose = np.array([c_d[0], c_d[1], wahr[2]])   # Hoehe aus dem Korbmodell
        out["d405"]["fehler_mm"] = float(1e3 * np.linalg.norm(c_d - wahr[:2]))
    else:
        # D405 sieht nur den oberen Bogen: Ebene (Normale, Lage entlang der Normale) aus der Ensenso,
        # Lage im Teller (Bogen) aus der D405
        nv = np.asarray(e["normale"], float)
        c_d = c_d - nv * float((c_d - c_e) @ nv) * 0.5
        abw = float(np.linalg.norm(c_d - c_e))
        tol = TOL_TELLER_M
        pose = c_d
        out["d405"]["fehler_mm"] = float(1e3 * np.linalg.norm(c_d - wahr))
        out["gier_grad"] = float(e["gier_grad"])
    out["ensenso_d405_abstand_mm"] = 1e3 * abw
    if abw > tol:
        out["gruende"].append("ensenso_d405_widerspruch")
    if soll_m is not None:
        d_soll = float(np.linalg.norm(pose[:2] - np.asarray(soll_m, float)[:2]))
        out["abstand_soll_mm"] = 1e3 * d_soll
        if d_soll > soll_tol_m:
            out["gruende"].append("nicht_am_erwarteten_platz")
    out["pose_m"] = pose.tolist()
    out["fehler_mm"] = float(1e3 * (np.linalg.norm(pose[:2] - wahr[:2]) if art == "glas" else np.linalg.norm(pose - wahr)))
    out["fehler_xyz_mm"] = (1e3 * (pose - wahr)).tolist()
    out["ok"] = not out["gruende"]
    return out
