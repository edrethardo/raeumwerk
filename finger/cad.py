"""Parametrisches CAD der 100-mm-Finger (build123d), Ausgabe STEP und STL.

    scripts/finger_cad.sh [ZIELORDNER]      # Standard cad/finger/

Liest ``config/finger.yaml`` (finger.parameter) und baut:

    Schaft         Seitenprofil (y-z) ueber die Breite extrudiert: Anschlussplatte,
                   Verjuengung von dicke_wurzel auf dicke_spitze
    V-Kontur       flache Nut ueber die Breite, Flanken um winkel_grad geneigt
    Taschen        je V-Flanke eine Tasche fuer die 2-mm-Auflage
    Kerbe, Lippe   an der Spitze: Kerbe fuer den Tellerrandwulst, darunter die Lippe
                   mit Einlauffase
    Lochbild       2 x M4 mit Senkung in der Anschlussplatte (ANNAHME)

Schreibt ``finger_100.step``, ``finger_100.stl``, ``auflage.stl`` (eine Auflage)
und ``finger_100.json`` (Volumen, Massen je Werkstoff, Huellquader, angewandte
Merkmale). Laeuft mit ``uvx -p 3.12 --with build123d --with pyyaml --with numpy``.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from finger.parameter import Finger  # noqa: E402


def baue(f: Finger) -> Dict[str, Any]:
    from build123d import Axis, Box, Cylinder, Location, Plane, Polygon, Pos, Rot, chamfer, extrude, fillet

    p = f.p
    L, b = f.L, f.b
    a = p["anschluss"]
    g = p["geometrie"]
    zp = f.z_platte
    t0, t1, z1 = float(g["dicke_wurzel_mm"]), float(g["dicke_spitze_mm"]), float(g["verjuengung_bis_mm"])
    tp = float(a["platte_tiefe_mm"])
    merkmale: List[str] = []

    # Seitenprofil in der y-z-Ebene (Plane.YZ: u = y, v = z), ueber x extrudiert
    prof = Polygon((0.0, 0.0), (-tp, 0.0), (-tp, zp), (-t0, zp), (-t1, z1), (-t1, L), (0.0, L), align=None)
    teil = extrude(Plane.YZ * prof, amount=b / 2.0, both=True)
    merkmale.append("schaft")

    # V-Nut: Prisma mit Dreieck (x-y) von v_z[0] bis v_z[1]
    v0, v1 = f.v_z
    d = f.v_tiefe
    e = 0.5
    tri = Polygon((-b / 2 - e, e * math.tan(f.gamma)), (0.0, -d), (b / 2 + e, e * math.tan(f.gamma)),
                  (b / 2 + e, 5.0), (-b / 2 - e, 5.0), align=None)
    teil -= extrude(Plane.XY.offset(v0) * tri, amount=v1 - v0)
    merkmale.append("v_kontur")

    # Taschen auf beiden Flanken
    au = p["auflage"]
    xa0, xa1 = f.auflage_x
    za0, za1 = f.auflage_z
    w = (xa1 - xa0) / math.cos(f.gamma)
    tt = float(au["taschen_tiefe_mm"])
    for s in (1.0, -1.0):
        xc = s * (xa0 + xa1) / 2.0
        yc = f.flanke_y(xc)
        box = Box(w, 2.0 * tt, za1 - za0)
        teil -= Location((xc, yc, (za0 + za1) / 2.0), (0.0, 0.0, s * math.degrees(f.gamma))) * box
    merkmale.append("auflage_taschen")

    # Kerbe (ueber die ganze Breite) mit gerundetem Grund
    k0, k1 = f.kerbe
    kt = float(p["teller"]["kerbe_tiefe_mm"])
    teil -= Pos(0.0, (-kt + 5.0) / 2.0, (k0 + k1) / 2.0) * Box(b + 2.0, kt + 5.0, k1 - k0)
    merkmale.append("kerbe")
    rk = float(p["teller"]["kerbe_radius_mm"])
    try:
        kanten = [k for k in teil.edges().filter_by(Axis.X)
                  if abs(k.center().Y + kt) < 1e-3 and (abs(k.center().Z - k0) < 1e-3 or abs(k.center().Z - k1) < 1e-3)]
        if len(kanten) == 2 and rk > 0:
            teil = fillet(kanten, rk)
            merkmale.append("kerbe_radius")
    except Exception as ex:  # pragma: no cover - nur Protokoll
        merkmale.append(f"kerbe_radius_fehlgeschlagen:{type(ex).__name__}")

    # Einlauffase an der Lippe (Innenkanten der Spitzenflaeche)
    fs = float(p["teller"]["fase_spitze_mm"])
    try:
        kanten = [k for k in teil.edges() if abs(k.center().Z - L) < 1e-3 and k.center().Y > -d - 1e-3]
        if kanten and fs > 0:
            teil = chamfer(kanten, fs)
            merkmale.append("fase_spitze")
    except Exception as ex:  # pragma: no cover
        merkmale.append(f"fase_fehlgeschlagen:{type(ex).__name__}")

    # Lochbild in der Anschlussplatte (ANNAHME): Durchgang + Senkung von der Fingerseite
    n = int(a["loch_anzahl"])
    ab = float(a["loch_abstand_mm"])
    ym = float(a["loch_mitte_y_mm"])
    r, rs, ts = float(a["loch_d_mm"]) / 2.0, float(a["senkung_d_mm"]) / 2.0, float(a["senkung_tiefe_mm"])
    for i in range(n):
        y = ym + (i - (n - 1) / 2.0) * ab
        teil -= Pos(0.0, y, zp / 2.0) * Cylinder(r, zp + 2.0)
        teil -= Pos(0.0, y, zp - ts / 2.0 + 0.5) * Cylinder(rs, ts + 1.0)
    merkmale.append("lochbild")

    # Aussenkanten laengs (y = -dicke_spitze) runden
    rr = float(g["kanten_radius_mm"])
    try:
        kanten = [k for k in teil.edges().filter_by(Axis.Z) if abs(k.center().Y + t1) < 1e-3 and k.center().Z > z1]
        if kanten and rr > 0:
            teil = fillet(kanten, rr)
            merkmale.append("aussenkanten_radius")
    except Exception as ex:  # pragma: no cover
        merkmale.append(f"aussenkanten_fehlgeschlagen:{type(ex).__name__}")

    # eine Auflage (in Fingerlage, rechte Flanke)
    dck = float(au["dicke_mm"])
    xc = (xa0 + xa1) / 2.0
    auflage = Location((xc, f.flanke_y(xc) - tt + dck / 2.0, (za0 + za1) / 2.0),
                       (0.0, 0.0, math.degrees(f.gamma))) * Box(w - 0.2, dck, za1 - za0 - 0.2)
    return {"finger": teil, "auflage": auflage, "merkmale": merkmale}


def schreibe(f: Finger, out: Path) -> Dict[str, Any]:
    from build123d import export_step, export_stl

    out.mkdir(parents=True, exist_ok=True)
    t = baue(f)
    fi, au = t["finger"], t["auflage"]
    export_step(fi, str(out / "finger_100.step"))
    export_stl(fi, str(out / "finger_100.stl"), tolerance=0.02, angular_tolerance=0.2)
    export_stl(au, str(out / "auflage.stl"), tolerance=0.02, angular_tolerance=0.2)
    bb = fi.bounding_box()
    vol = float(fi.volume)
    info = {
        "volumen_finger_mm3": round(vol, 1),
        "volumen_auflage_mm3": round(float(au.volume), 1),
        "volumen_naeherung_mm3": round(f.volumen_mm3(), 1),
        "massen_g": {wk: round(f.masse_g(wk, vol), 1) for wk in f.werkstoffe},
        "huelle_mm": {"min": [round(v, 2) for v in (bb.min.X, bb.min.Y, bb.min.Z)],
                      "max": [round(v, 2) for v in (bb.max.X, bb.max.Y, bb.max.Z)]},
        "merkmale": t["merkmale"],
        "gueltig": bool(fi.is_valid),
    }
    (out / "finger_100.json").write_text(json.dumps(info, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return info


def main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="CAD der 100-mm-Finger (STEP/STL)")
    ap.add_argument("out", nargs="?", default=str(REPO / "cad" / "finger"))
    a = ap.parse_args(argv)
    info = schreibe(Finger.laden(), Path(a.out))
    print(json.dumps(info, indent=1, ensure_ascii=False))
    return 0 if info["gueltig"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
