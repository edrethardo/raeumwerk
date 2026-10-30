"""Balkenrechnung der Finger: Biegespannung, Durchbiegung, Sicherheit, Masse.

Kragbalken, eingespannt an der Unterseite der Anschlussplatte (z = platte_dicke),
Rechteckquerschnitt b x h_netto(z) (Nut und Tasche konservativ ueber die ganze
Breite abgezogen, ``Finger.netto_hoehe``). Kein FEM. Lastfaelle (je Finger):

    glas_griff    Greifkraft F in Schliessrichtung am Griffpunkt (30 mm hinter der Spitze)
                  + Glasgewicht x Dynamik / 2 quer (Seitgriff, Greifer waagerecht)
    teller_lippe  Greifkraft F an der Lippe (Spitze, groesster Hebel)
                  + Tellermoment um die Schliessachse (Gewicht x Radius x Dynamik / 2):
                  der Teller haengt an der Spitze, jede Schraeglage oder Beschleunigung
                  dreht ihn um die Klemmstelle ("Teller-Hebel")
                  + Tellergewicht x Dynamik / 2 laengs (Zug, haengt am Wulst)

Biegung um x (Last in y) mit W_x = b h^2 / 6, Biegung um y mit W_y = h b^2 / 6;
die Spannungen werden konservativ addiert, an Kerbe und Wurzel mit Formzahl.
Durchbiegung w'' = M / (E I) numerisch integriert (Schliessrichtung).
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from .parameter import Finger

G = 9.81


def _schnitte(f: Finger, n: int = 921) -> List[float]:
    z0 = f.z_platte
    return [z0 + (f.L - z0) * i / (n - 1) for i in range(n)]


def lastfaelle(f: Finger, F: float) -> List[Dict[str, Any]]:
    p = f.p["festigkeit"]
    dyn = float(p["dynamik_faktor"])
    z_griff = f.L - float(f.p["greifkraft"]["griffpunkt_ab_spitze_mm"])
    z_lippe = (f.lippe[0] + f.lippe[1]) / 2.0
    m_g, m_t = float(p["glas_masse_kg"]), float(p["teller_masse_kg"])
    r_t = float(p["teller_radius_mm"])
    return [
        {"name": "glas_griff", "F_y": F, "z_F": z_griff, "F_x": m_g * G * dyn / 2.0, "z_Fx": z_griff,
         "M_y": 0.0, "F_z": 0.0},
        {"name": "teller_lippe", "F_y": F, "z_F": z_lippe, "F_x": 0.0, "z_Fx": z_lippe,
         "M_y": m_t * G * r_t * dyn / 2.0, "F_z": m_t * G * dyn / 2.0},
    ]


def spannung(f: Finger, lf: Dict[str, Any], z: float) -> Dict[str, float]:
    """Nennspannung und Spannung mit Formzahl (MPa) am Schnitt z."""
    h, bereich = f.netto_hoehe(z)
    b = f.b
    if bereich == "anschlussplatte":
        h = f.dicke(f.z_platte + 1e-6)  # Einspannstelle: Schaft direkt unter der Platte
    Mx = lf["F_y"] * max(0.0, lf["z_F"] - z)                 # Nmm, Biegung um x
    My = lf["F_x"] * max(0.0, lf["z_Fx"] - z) + (lf["M_y"] if z <= lf["z_F"] else 0.0)
    s = Mx / (b * h * h / 6.0) + My / (h * b * b / 6.0) + lf["F_z"] / (b * h)
    kt = 1.0
    fp = f.p["festigkeit"]
    if bereich == "kerbe":
        kt = float(fp["kt_kerbe"])
    elif z <= f.z_platte + 2.0:
        kt = float(fp["kt_wurzel"])
    return {"z": z, "h": h, "bereich": bereich, "nenn": s, "mit_kt": s * kt, "kt": kt}


def durchbiegung(f: Finger, lf: Dict[str, Any], E: float, n: int = 2001) -> float:
    """Durchbiegung der Spitze in Schliessrichtung (mm) unter F_y."""
    z0 = f.z_platte
    dz = (f.L - z0) / (n - 1)
    w, phi = 0.0, 0.0
    for i in range(n - 1):
        z = z0 + (i + 0.5) * dz
        h, _ = f.netto_hoehe(z)
        I = f.b * h ** 3 / 12.0
        M = lf["F_y"] * max(0.0, lf["z_F"] - z)
        kappa = M / (E * I)
        w += phi * dz + 0.5 * kappa * dz * dz
        phi += kappa * dz
    return w


def rechne(f: Finger, kraefte: Optional[List[float]] = None, volumen_mm3: Optional[float] = None) -> Dict[str, Any]:
    kraefte = kraefte or [float(v) for v in f.p["greifkraft"]["rechnung_n"]]
    s_min = float(f.p["festigkeit"]["sicherheit_min"])
    out: Dict[str, Any] = {"volumen_mm3": round(volumen_mm3 if volumen_mm3 is not None else f.volumen_mm3(), 1),
                           "volumen_quelle": "cad" if volumen_mm3 is not None else "naeherung",
                           "sicherheit_min": s_min, "werkstoffe": {}}
    zs = _schnitte(f)
    for wk in f.werkstoffe:
        w = f.p["werkstoffe"][wk]
        R = float(w["festigkeit_mpa"]) * float(w["abminderung"])
        E = float(w["e_mpa"])
        fall = []
        for F in kraefte:
            for lf in lastfaelle(f, F):
                sp = [spannung(f, lf, z) for z in zs]
                m = max(sp, key=lambda d: d["mit_kt"])
                fall.append({"lastfall": lf["name"], "F_n": F, "sigma_max_mpa": round(m["mit_kt"], 2),
                             "ort_z_mm": round(m["z"], 1), "bereich": m["bereich"], "kt": m["kt"],
                             "sicherheit": round(R / m["mit_kt"], 2) if m["mit_kt"] > 0 else math.inf,
                             "durchbiegung_spitze_mm": round(durchbiegung(f, lf, E), 3)})
        smin = min(c["sicherheit"] for c in fall)
        out["werkstoffe"][wk] = {"name": w["name"], "r_zul_mpa": round(R, 1), "e_mpa": E,
                                 "masse_g": round(f.masse_g(wk, out["volumen_mm3"]), 1),
                                 "faelle": fall, "sicherheit_min": smin, "ok": smin >= s_min,
                                 # Kraft je Finger, bei der die Mindestsicherheit gerade noch erreicht wird
                                 "f_grenze_n": round(max(kraefte) * smin / s_min, 1)}
    out["gewaehlt"] = f.gewaehlt
    out["ok"] = out["werkstoffe"][f.gewaehlt]["ok"]
    return out


def bericht_md(e: Dict[str, Any]) -> str:
    z = ["| Werkstoff | Masse je Finger | Lastfall | F je Finger | sigma max (Ort) | Sicherheit | Durchbiegung Spitze |",
         "|---|---|---|---|---|---|---|"]
    for wk, w in e["werkstoffe"].items():
        for c in w["faelle"]:
            z.append(f"| {w['name']} | {w['masse_g']:.1f} g | {c['lastfall']} | {c['F_n']:.0f} N | "
                     f"{c['sigma_max_mpa']:.2f} MPa (z {c['ort_z_mm']:.0f} mm, {c['bereich']}) | "
                     f"{c['sicherheit']:.1f} | {c['durchbiegung_spitze_mm']:.3f} mm |")
    return "\n".join(z)


def main(argv=None) -> int:
    import argparse
    import json
    from pathlib import Path

    ap = argparse.ArgumentParser(description="Balkenrechnung der Finger (config/finger.yaml)")
    ap.add_argument("--cad-json", help="finger_100.json aus finger.cad (echtes Volumen)")
    ap.add_argument("--md", action="store_true", help="Tabelle als Markdown")
    a = ap.parse_args(argv)
    f = Finger.laden()
    vol = None
    if a.cad_json and Path(a.cad_json).exists():
        vol = float(json.loads(Path(a.cad_json).read_text())["volumen_finger_mm3"])
    e = rechne(f, volumen_mm3=vol)
    print(bericht_md(e) if a.md else json.dumps(e, indent=1, ensure_ascii=False))
    return 0 if e["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
