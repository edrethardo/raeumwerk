"""Bewertung eines Greifversuchs aus den Messwerten der Simulation.

Eingabe ist ein ``dict`` mit den Messwerten, die ``scripts/demo_greifen.py``
je Versuch sammelt (alle Laengen in m, Winkel in Grad)::

    plan_ok, plan_fehler          Planung (IK, Grenzen, Selbstkollision)
    endlage_m                     Glasmitte am Ende [x, y, z]
    ziel_xy_m                     Zielmitte [x, y]
    kippung_end_grad              Winkel Glasachse <-> Welt-z am Ende
    hub_max_m                     groesster Anstieg der Glasmitte waehrend "anheben"/"verfahren"
    transport_min_hub_m           kleinster Anstieg zwischen Ende "anheben" und Beginn "absetzen"
    stehhoehe_soll_m              Glasmitte, wenn es auf dem Tisch steht
    tisch_durchdringung_max_m     tiefste Durchdringung Roboter <-> Tisch (0 = nie)
    finger_durchdringung_max_m    tiefste Durchdringung Finger <-> Glas
    glas_v_max_m_s                hoechste Glasgeschwindigkeit
    nan                           Simulation lieferte NaN

Fehlergruende (Schluessel in ``gruende``), in fester Reihenfolge:

    planung_fehlgeschlagen, simulation_instabil, nicht_gegriffen, gefallen,
    gekippt, nicht_am_ziel, kollision_arm_tisch, durchdringung, weggeschossen
"""
from __future__ import annotations

import math
from typing import Any, Dict

GRUENDE = ["planung_fehlgeschlagen", "simulation_instabil", "nicht_gegriffen", "gefallen", "gekippt",
           "nicht_am_ziel", "kollision_arm_tisch", "durchdringung", "weggeschossen"]

TEXT = {
    "planung_fehlgeschlagen": "Planung fehlgeschlagen (IK/Grenzen/Selbstkollision)",
    "simulation_instabil": "Simulation lieferte ungueltige Werte (NaN)",
    "nicht_gegriffen": "Glas wurde nicht angehoben (nicht gegriffen)",
    "gefallen": "Glas ist waehrend des Transports gefallen oder steht am Ende nicht auf dem Tisch",
    "gekippt": "Glas ist am Ende gekippt",
    "nicht_am_ziel": "Glas steht nicht innerhalb der Toleranz am Ziel",
    "kollision_arm_tisch": "Arm/Greifer hat den Tisch beruehrt",
    "durchdringung": "Finger dringen zu tief ins Glas ein",
    "weggeschossen": "Glas wurde weggeschleudert (zu schnell)",
}


def _f(x: Any) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return math.nan
    return v


def bewerte(m: Dict[str, Any], grenzen: Dict[str, Any]) -> Dict[str, Any]:
    """Liefert ``{"erfolg", "gruende", "kriterien", "texte"}``.

    ``grenzen`` ist ``Szene.bewertung`` (Toleranzen aus ``config/scene.yaml``).
    Fehlende oder NaN-Messwerte zaehlen als nicht bestanden.
    """
    tol = float(grenzen["ziel_toleranz_m"])
    kipp_max = float(grenzen["kippung_max_grad"])
    hub_min = float(grenzen["hub_min_m"])
    steh_tol = float(grenzen["stehhoehe_toleranz_m"])
    tisch_tol = float(grenzen["tisch_kollision_m"])
    dd_max = float(grenzen["durchdringung_max_m"])
    v_max = float(grenzen["glas_v_max_m_s"])

    k: Dict[str, Dict[str, Any]] = {}
    k["planung_fehlgeschlagen"] = {"ok": bool(m.get("plan_ok", False)), "wert": m.get("plan_fehler", [])}
    werte = [m.get("endlage_m", [math.nan] * 3), [m.get("kippung_end_grad")], [m.get("hub_max_m")]]
    nan = bool(m.get("nan", False)) or any(math.isnan(_f(x)) for w in werte for x in w)
    k["simulation_instabil"] = {"ok": not nan, "wert": bool(m.get("nan", False))}

    hub = _f(m.get("hub_max_m"))
    k["nicht_gegriffen"] = {"ok": hub >= hub_min, "wert": hub, "grenze": f">= {hub_min}"}

    end = [_f(x) for x in m.get("endlage_m", [math.nan] * 3)]
    steh = _f(m.get("stehhoehe_soll_m"))
    trans = _f(m.get("transport_min_hub_m"))
    steht = abs(end[2] - steh) <= steh_tol
    # Gefallen: erst gegriffen, dann im Transport mehr als (hub - hub_min) abgesackt,
    # oder am Ende nicht auf Tischhoehe (liegt, steht auf dem Boden, haengt am Greifer)
    im_transport_gefallen = hub >= hub_min and not (trans >= hub_min)
    k["gefallen"] = {"ok": steht and not im_transport_gefallen,
                     "wert": {"end_z_m": end[2], "soll_z_m": steh, "transport_min_hub_m": trans},
                     "grenze": f"|z - soll| <= {steh_tol}, Transport-Hub >= {hub_min}"}

    kipp = _f(m.get("kippung_end_grad"))
    k["gekippt"] = {"ok": kipp < kipp_max, "wert": kipp, "grenze": f"< {kipp_max}"}

    ziel = [_f(x) for x in m.get("ziel_xy_m", [math.nan, math.nan])]
    fehler = math.hypot(end[0] - ziel[0], end[1] - ziel[1])
    k["nicht_am_ziel"] = {"ok": fehler <= tol, "wert": fehler, "grenze": f"<= {tol}"}

    td = _f(m.get("tisch_durchdringung_max_m", 0.0))
    k["kollision_arm_tisch"] = {"ok": td <= tisch_tol, "wert": td, "grenze": f"<= {tisch_tol}"}

    fd = _f(m.get("finger_durchdringung_max_m", 0.0))
    k["durchdringung"] = {"ok": fd <= dd_max, "wert": fd, "grenze": f"<= {dd_max}"}

    v = _f(m.get("glas_v_max_m_s", 0.0))
    k["weggeschossen"] = {"ok": v <= v_max, "wert": v, "grenze": f"<= {v_max}"}

    for name in k:
        k[name]["ok"] = bool(k[name]["ok"])  # NaN-Vergleiche sind False -> nicht bestanden
    gruende = [g for g in GRUENDE if not k[g]["ok"]]
    return {"erfolg": not gruende, "gruende": gruende, "texte": [TEXT[g] for g in gruende], "kriterien": k}


def zusammenfassung(ergebnisse: list) -> Dict[str, Any]:
    """Erfolgsquote und Haeufigkeit der Fehlergruende ueber mehrere Versuche."""
    n = len(ergebnisse)
    ok = sum(1 for e in ergebnisse if e["bewertung"]["erfolg"])
    zaehler: Dict[str, int] = {}
    for e in ergebnisse:
        for g in e["bewertung"]["gruende"]:
            zaehler[g] = zaehler.get(g, 0) + 1
    fehler_ziel = [e["bewertung"]["kriterien"]["nicht_am_ziel"]["wert"] for e in ergebnisse]
    kipp = [e["bewertung"]["kriterien"]["gekippt"]["wert"] for e in ergebnisse]
    gueltig = [x for x in fehler_ziel if not math.isnan(_f(x))]
    gk = [x for x in kipp if not math.isnan(_f(x))]
    return {
        "versuche": n, "erfolge": ok, "erfolgsquote": (ok / n) if n else 0.0,
        "fehlergruende": {g: zaehler[g] for g in GRUENDE if g in zaehler},
        "fehlversuche": [{"nr": e["versuch"]["nr"], "gruende": e["bewertung"]["gruende"]}
                         for e in ergebnisse if not e["bewertung"]["erfolg"]],
        "zielfehler_m": {"max": max(gueltig) if gueltig else None,
                         "mittel": sum(gueltig) / len(gueltig) if gueltig else None},
        "kippung_grad": {"max": max(gk) if gk else None},
    }
