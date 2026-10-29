"""Bewertung des Ausraeumens je Glas und Gesamtbericht.

Eingabe: Plan (Phasenzeiten), Glas-Plaene (Zeitfenster je Glas), Welt
(Ziele, Standhoehe) und die Messung aus ``ausraeumen.sim_newton.Lauf.fahren``
(``t``, ``phase``, ``glas`` (n, 4, 7), ``tcp`` (n, 3), ``kontakt`` je Glas,
``finger_durchdringung_m``, ``nan``). Grenzen: ``bewertung`` in
``config/ausraeumen.yaml``. Fehlergruende je Glas in fester Reihenfolge:

    planung_fehlgeschlagen  Plan fehlt (IK, Grenzen, Kollision im Plan)
    simulation_instabil     NaN in der Simulation
    nicht_aus_dem_korb      Glas am Ende des Aushubs nicht >= hub_min ueber dem Slot
    gefallen                Glas in der Hand > 2 cm gegen den TCP gewandert
                            (verloren) oder steht am Ende nicht auf Plattenhoehe
    gekippt                 Glasachse am Ende >= kippung_max gegen die Senkrechte
                            (aufrecht = Glasboden unten; kopfueber = 180 Grad)
    nicht_am_ziel           Glasmitte > ziel_toleranz neben dem Ablagepunkt
    kontakt_korb            Roboter dringt in Korb/Glashalter ein (> kontakt_max)
    kontakt_tuer            ... in die Tuer
    kontakt_arbeitsplatte   ... in die Arbeitsplatte
    nachbar_verschoben      ein anderes Glas wandert waehrend dieses Glases > 5 mm
    durchdringung           Finger > durchdringung_max im Glas
    weggeschossen           Glas schneller als glas_v_max
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

GRUENDE = ["planung_fehlgeschlagen", "simulation_instabil", "nicht_aus_dem_korb", "gefallen", "gekippt",
           "nicht_am_ziel", "kontakt_korb", "kontakt_tuer", "kontakt_arbeitsplatte", "nachbar_verschoben",
           "durchdringung", "weggeschossen"]

TEXT = {
    "planung_fehlgeschlagen": "Planung fehlgeschlagen (IK/Grenzen/Kollision im Plan)",
    "simulation_instabil": "Simulation lieferte ungueltige Werte (NaN)",
    "nicht_aus_dem_korb": "Glas wurde nicht aus dem Korb gehoben (verklemmt oder nicht gegriffen)",
    "gefallen": "Glas ging in der Hand verloren oder steht am Ende nicht auf der Platte",
    "gekippt": "Glas steht am Ende nicht aufrecht",
    "nicht_am_ziel": "Glas steht nicht innerhalb der Toleranz am Ablagepunkt",
    "kontakt_korb": "Roboter hat Korb oder Glashalter beruehrt",
    "kontakt_tuer": "Roboter hat die Tuer beruehrt",
    "kontakt_arbeitsplatte": "Roboter hat die Arbeitsplatte beruehrt",
    "nachbar_verschoben": "Ein anderes Glas wurde verschoben",
    "durchdringung": "Finger dringen zu tief ins Glas ein",
    "weggeschossen": "Glas wurde weggeschleudert (zu schnell)",
}


def _kipp(q) -> float:
    x, y, z, w = (float(v) for v in q)
    rz = 1 - 2 * (x * x + y * y)
    return math.degrees(math.acos(max(-1.0, min(1.0, rz))))


def _idx(t, zeit: float) -> int:
    import numpy as np
    return int(min(len(t) - 1, max(0, np.searchsorted(t, zeit - 1e-9))))


def bewerte_glas(nr: int, gp, zeiten: Dict[str, tuple], welt, mess: Dict[str, Any], gr: Dict[str, Any]) -> Dict[str, Any]:
    import numpy as np

    s = gp.slot
    pfx = f"{s + 1}:"
    t = mess["t"]
    G = mess["glas"]           # (n, 4, 7)
    tcp = mess["tcp"]          # (n, 3)
    k: Dict[str, Dict[str, Any]] = {}
    nan = bool(mess.get("nan", False)) or len(t) == 0 or not np.all(np.isfinite(G))
    k["planung_fehlgeschlagen"] = {"ok": True, "wert": []}
    k["simulation_instabil"] = {"ok": not nan, "wert": bool(mess.get("nan", False))}
    if nan:
        return _fertig(nr, gp, k, {})
    start = G[0, s, :3]
    i_aus = _idx(t, zeiten[pfx + "aushub"][1])
    hub = float(G[i_aus, s, 2] - start[2])
    k["nicht_aus_dem_korb"] = {"ok": hub >= float(gr["hub_min_m"]), "wert": hub, "grenze": f">= {gr['hub_min_m']}"}
    # in der Hand: Abstand Glasmitte <-> TCP darf sich kaum aendern
    verloren = 0.0
    for a_, b_ in ((pfx + "greifen_korb", pfx + "loesen_zw"), (pfx + "greifen_seite", pfx + "loesen")):
        i0, i1 = _idx(t, zeiten[a_][1]), _idx(t, zeiten[b_][0])
        if i1 <= i0:
            continue
        d = np.linalg.norm(G[i0:i1, s, :3] - tcp[i0:i1], axis=1)
        verloren = max(verloren, float(np.max(np.abs(d - d[0]))))
    end = G[-1, s]
    ziel = welt.glas_ziel[gp.ablage].mitte
    steh = abs(float(end[2] - ziel[2]))
    k["gefallen"] = {"ok": verloren <= 0.02 and steh <= float(gr["stehhoehe_toleranz_m"]),
                     "wert": {"tcp_abstand_aenderung_max_m": verloren, "end_z_m": float(end[2]), "soll_z_m": float(ziel[2])},
                     "grenze": f"Hand <= 0.02, |z - soll| <= {gr['stehhoehe_toleranz_m']}"}
    kipp_end = _kipp(end[3:7])
    k["gekippt"] = {"ok": kipp_end < float(gr["kippung_max_grad"]), "wert": kipp_end,
                    "start_grad": _kipp(G[0, s, 3:7]), "grenze": f"< {gr['kippung_max_grad']}"}
    fehler = float(math.hypot(end[0] - ziel[0], end[1] - ziel[1]))
    k["nicht_am_ziel"] = {"ok": fehler <= float(gr["ziel_toleranz_m"]), "wert": fehler, "grenze": f"<= {gr['ziel_toleranz_m']}"}
    kon = mess["kontakt"][s]
    for grund, grp in (("kontakt_korb", "korb"), ("kontakt_tuer", "tuer"), ("kontakt_arbeitsplatte", "arbeitsplatte")):
        tiefe, ph = kon.get(grp, (0.0, ""))
        k[grund] = {"ok": tiefe <= float(gr["kontakt_max_m"]), "wert": float(tiefe), "phase": ph,
                    "grenze": f"<= {gr['kontakt_max_m']}"}
    # andere Glaeser im Zeitfenster dieses Glases
    i0, i1 = _idx(t, gp.t0), _idx(t, gp.t1)
    nachbar = {}
    for j in range(G.shape[1]):
        if j == s:
            continue
        nachbar[f"glas_{j + 1}"] = float(np.max(np.linalg.norm(G[i0:i1 + 1, j, :3] - G[i0, j, :3], axis=1)))
    nmax = max(nachbar.values()) if nachbar else 0.0
    k["nachbar_verschoben"] = {"ok": nmax <= float(gr["nachbar_verschiebung_max_m"]), "wert": nachbar,
                               "grenze": f"<= {gr['nachbar_verschiebung_max_m']}"}
    fd = float(mess["finger_durchdringung_m"][s])
    k["durchdringung"] = {"ok": fd <= float(gr["durchdringung_max_m"]), "wert": fd, "grenze": f"<= {gr['durchdringung_max_m']}",
                          "phase": (mess.get("finger_durchdringung_phase") or [""] * 4)[s]}
    dtm = np.diff(t)
    v = float(np.max(np.linalg.norm(np.diff(G[:, s, :3], axis=0), axis=1) / np.maximum(dtm, 1e-9))) if len(t) > 1 else 0.0
    k["weggeschossen"] = {"ok": v <= float(gr["glas_v_max_m_s"]), "wert": v, "grenze": f"<= {gr['glas_v_max_m_s']}"}
    werte = {"start_m": [float(x) for x in start], "ende_m": [float(x) for x in end[:3]],
             "ziel_m": [float(x) for x in ziel], "zielfehler_xy_m": fehler, "kippung_end_grad": kipp_end,
             "kippung_start_grad": _kipp(G[0, s, 3:7]), "aushub_m": hub,
             "kontakte_m": {g: float(v_[0]) for g, v_ in kon.items()}, "nachbar_max_m": nmax,
             "zwischenablage_kontakt_m": float(kon.get("zwischenablage", (0.0, ""))[0])}
    return _fertig(nr, gp, k, werte)


def _fertig(nr, gp, k, werte) -> Dict[str, Any]:
    for name in k:
        k[name]["ok"] = bool(k[name]["ok"])
    gruende = [g for g in GRUENDE if g in k and not k[g]["ok"]]
    return {"nr": nr, "glas": f"glas_{gp.slot + 1}", "slot": gp.slot + 1, "ablage": gp.ablage + 1,
            "zeitfenster_s": [round(gp.t0, 3), round(gp.t1, 3)], "erfolg": not gruende, "gruende": gruende,
            "texte": [TEXT[g] for g in gruende], "werte": werte, "kriterien": k, "plan": gp.info}


def bewerte(plan, glaeser, welt, mess, gr) -> Dict[str, Any]:
    zeiten = plan.phase_zeiten()
    out = [bewerte_glas(i, gp, zeiten, welt, mess, gr) for i, gp in enumerate(glaeser)]
    return gesamt(out)


def planfehler(zuordnung, grund: str) -> Dict[str, Any]:
    """Bericht, wenn schon die Planung scheitert: alle Glaeser Fehlversuch."""
    out = []
    for i, (s, z) in enumerate(zuordnung):
        k = {"planung_fehlgeschlagen": {"ok": False, "wert": [grund]}}
        out.append({"nr": i, "glas": f"glas_{s}", "slot": int(s), "ablage": int(z), "erfolg": False,
                    "gruende": ["planung_fehlgeschlagen"], "texte": [TEXT["planung_fehlgeschlagen"]],
                    "werte": {}, "kriterien": k, "plan": {}})
    return gesamt(out)


def gesamt(glaeser: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(glaeser)
    ok = sum(1 for g in glaeser if g["erfolg"])
    return {"erfolg": n > 0 and ok == n, "erfolge": ok, "glaeser_n": n, "glaeser": glaeser,
            "gruende": sorted({r for g in glaeser for r in g["gruende"]}, key=GRUENDE.index)}


def zusammenfassung(versuche: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Erfolgsquote je Glas und Haeufigkeit der Fehlergruende ueber mehrere Versuche."""
    je_glas: Dict[str, Dict[str, Any]] = {}
    zaehler: Dict[str, int] = {}
    for v in versuche:
        for g in v["bewertung"]["glaeser"]:
            e = je_glas.setdefault(g["glas"], {"versuche": 0, "erfolge": 0, "gruende": {}, "zielfehler_m": [],
                                               "kippung_grad": []})
            e["versuche"] += 1
            e["erfolge"] += int(g["erfolg"])
            for r in g["gruende"]:
                e["gruende"][r] = e["gruende"].get(r, 0) + 1
                zaehler[r] = zaehler.get(r, 0) + 1
            w = g.get("werte", {})
            if "zielfehler_xy_m" in w:
                e["zielfehler_m"].append(w["zielfehler_xy_m"])
                e["kippung_grad"].append(w["kippung_end_grad"])
    for e in je_glas.values():
        e["erfolgsquote"] = e["erfolge"] / e["versuche"] if e["versuche"] else 0.0
        zf, kp = e.pop("zielfehler_m"), e.pop("kippung_grad")
        e["zielfehler_max_m"] = max(zf) if zf else None
        e["kippung_max_grad"] = max(kp) if kp else None
    n = len(versuche)
    voll = sum(1 for v in versuche if v["bewertung"]["erfolg"])
    return {"versuche": n, "alle_4_erfolg": voll, "je_glas": dict(sorted(je_glas.items())),
            "fehlergruende": {g: zaehler[g] for g in GRUENDE if g in zaehler},
            "fehlversuche": [{"nr": v["versuch"]["nr"], "glaeser": {g["glas"]: g["gruende"] for g in v["bewertung"]["glaeser"]
                                                                    if not g["erfolg"]}}
                             for v in versuche if not v["bewertung"]["erfolg"]]}
