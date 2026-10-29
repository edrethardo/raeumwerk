"""Ein Ausraeum-Versuch von der Planung bis zur Bewertung (Newton).

Benutzt von ``scripts/demo_ausraeumen.py`` und ``raeumwerk run`` (Backend
``ausraeumen``). ``ctx`` aus ``ausraeumen.sim_newton.kontext``; ohne ``ctx``
(``nur_plan``) wird nur geplant.
"""
from __future__ import annotations

import math
import time
from typing import Any, Dict, Optional, Tuple

from . import bewertung, geometrie as ag, konfig
from .konfig import PARAMETER, abweichung_aus  # noqa: F401  (raeumwerk run)


def roboter(cfg, a: Dict[str, Any]):
    """Robotermodell fuer das Ausraeumen: ``config/robot.yaml`` mit den
    Fingeraufsaetzen aus ``greifer.finger_breite_m`` (Rest unveraendert).
    Liefert (cfg, urdf, chain)."""
    import copy

    from rebel_model.kinematics import Chain
    from rebel_model.urdf_gen import build_urdf

    cfg = copy.deepcopy(cfg)
    fb = a["greifer"].get("finger_breite_m")
    if fb is not None:
        cfg.greifer["finger_breite_m"] = float(fb)
    urdf = build_urdf(cfg)
    return cfg, urdf, Chain(urdf)


def versuch(nr: int, art: str, abw: konfig.Abweichung, ctx, cfg, chain, urdf, merk=None, glaeser_n=None,
            aufzeichnen=None, nur_plan=False, zuweisungen=None) -> Tuple[Dict[str, Any], Dict]:
    from .plan import PlanFehler, Planer
    from . import sim_newton as sn

    auf = konfig.aufbau(abw, zuweisungen=zuweisungen)
    if glaeser_n:
        auf.a["ablauf"]["zuordnung"] = auf.a["ablauf"]["zuordnung"][:glaeser_n]
    w = ag.baue(auf, cfg.achse7)
    t0 = time.monotonic()
    planer = Planer(w, cfg, chain, merk=merk)
    rec: Dict[str, Any] = {"versuch": {"nr": nr, "art": art, "abweichung": abw.as_dict(),
                                       "zuweisungen": list(zuweisungen or [])},
                           "device": ctx["device"] if ctx else None}
    try:
        plan, gps = planer.plane()
    except PlanFehler as e:
        rec.update({"plan": {"ok": False, "fehler": str(e), "wand_s": round(time.monotonic() - t0, 1)},
                    "bewertung": bewertung.planfehler(auf.a["ablauf"]["zuordnung"], str(e)), "erfolg": False})
        return rec, dict(merk or {})
    rec["plan"] = {"ok": True, "dauer_s": round(plan.dauer, 3), "wand_s": round(time.monotonic() - t0, 1),
                   "zaehler": planer.zaehler,
                   "phasen": [[s.phase, round(s.t0, 3), round(s.t0 + s.dauer, 3)] for s in plan.segmente],
                   "glaeser": [{"slot": g.slot + 1, "ablage": g.ablage + 1, "t_s": [round(g.t0, 3), round(g.t1, 3)],
                                **g.info} for g in gps]}
    if nur_plan:
        rec["erfolg"] = None
        return rec, planer.merk
    lauf = sn.Lauf(ctx, w, plan, cfg, chain, urdf, 30.0 if aufzeichnen else None)
    if abw.verklemmt:
        ng = auf.a["negativtest"]
        lauf.zusatz = sn.klemmbacken(w, abw.verklemmt - 1, float(ng["uebermass_m"]), float(ng["backe_hoehe_m"]))
    lauf.bauen()
    mess = lauf.fahren()
    bew = bewertung.bewerte(plan, gps, w, mess, auf.a["bewertung"])
    rec.update({"erfolg": bew["erfolg"], "bewertung": bew,
                "dauer": {"ablauf_sim_s": round(plan.dauer, 3), "wand_sim_s": round(lauf.wand_s, 1)},
                "modell": {"glas_masse_kg": lauf.glas_masse, "statische_formen": lauf.n_statisch, "dt_s": mess["dt"]}})
    if aufzeichnen:
        meta = {
            "szene": "spuelmaschine",
            "statisch": [{"name": k.name, "gruppe": k.gruppe, "mitte": k.mitte, "halb": k.halb, "rot": k.rot}
                         for k in list(w.statisch) + list(lauf.zusatz) if k.name != "boden"],
            "glas_radius_m": w.glas_r, "glas_hoehe_m": w.glas_h,
            "ablage_m": [g.mitte for g in w.glas_ziel], "zwischenablage_m": [k.mitte for k in w.matten],
            "phasen_s": [[s.phase, s.t0, s.t0 + s.dauer] for s in plan.segmente],
            "glaeser": [{"glas": g["glas"], "erfolg": g["erfolg"], "gruende": g["gruende"],
                         "zielfehler_xy_m": g["werte"].get("zielfehler_xy_m"),
                         "kippung_end_grad": g["werte"].get("kippung_end_grad")} for g in bew["glaeser"]],
            "erfolg": bew["erfolg"], "erfolge": bew["erfolge"],
            "ziel_toleranz_m": float(auf.a["bewertung"]["ziel_toleranz_m"]),
            "kippung_grenze_grad": float(auf.a["bewertung"]["kippung_max_grad"])}
        lauf.aufzeichner.speichern(aufzeichnen, lauf.body_label, sn.jsonable(meta))
    return sn.jsonable(rec), planer.merk


def fuer_run(rec: Dict[str, Any], parameter: Dict[str, float]) -> Dict[str, Any]:
    """Datensatz im Format von ``raeumwerk run`` (Kernwerte = schlechtestes Glas)."""
    gl = rec.get("bewertung", {}).get("glaeser", [])
    zf = [g["werte"]["zielfehler_xy_m"] for g in gl if g.get("werte", {}).get("zielfehler_xy_m") is not None]
    kp = [g["werte"]["kippung_end_grad"] for g in gl if g.get("werte", {}).get("kippung_end_grad") is not None]
    fd = [g["kriterien"]["durchdringung"]["wert"] for g in gl if "durchdringung" in g.get("kriterien", {})]
    v = [g["kriterien"]["weggeschossen"]["wert"] for g in gl if "weggeschossen" in g.get("kriterien", {})]
    out = dict(rec)
    out.update({
        "erfolg": bool(rec.get("erfolg")),
        "gruende": [f"{g['glas']}:{r}" for g in gl for r in g["gruende"]],
        "erfolge_glaeser": sum(1 for g in gl if g["erfolg"]),
        "position": {"fehler_xy_m": max(zf) if len(zf) == len(gl) and gl else math.nan},
        "kippung_grad": {"ende": max(kp) if len(kp) == len(gl) and gl else math.nan},
        "messung": {"finger_durchdringung_max_m": max(fd) if fd else None, "glas_v_max_m_s": max(v) if v else None},
        "parameter": dict(parameter)})
    return out
