#!/usr/bin/env python3
"""Posefehler der geschaetzten Objektpose (Raster {0,5,15} Grad x {0,5,20} mm und
Gauss-sigma 15 Grad / 2 cm) und die Heilungsstrategien S0..S4, Wahrnehmung allein (ohne Newton).

Der Fehler liegt auf der Station (Ensenso), die D405 am Handgelenk sieht unabhaengig neu
(``griffpose.schaetzen(..., posedrift=)``). Simuliert wird in der wahren Welt. Je Objekt und
Fehlerstufe: Restfehler S0/S1/S2 (mm, Gier Grad), Erfolg nach der mechanischen Grenze (S4),
Kreuzprobe (S3). S5 (Nachfassen) und S6 (Greifweite) sind nicht gerechnet, nur Entwurf.

sigma-Varianten: echte Gauss-Ziehung (``robustheit.drift``: Versatz 3D N(0; 2 cm), Drehwinkel
N(0; 15 Grad), zufaellige Achse). ``sigma_frei`` ohne Kappung, ``sigma_hart`` mit Kappung
|dp| <= 2 cm, |dR| <= 30 Grad aus derselben Ziehung.

    griff_robustheit.py --art glas|teller --seeds 16 --out ORDNER [--nur alle|fest|sigma]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))
sys.path.insert(0, str(HIER))

import numpy as np  # noqa: E402

import griff_wahrnehmung as GW  # noqa: E402
from finger import a1 as A1  # noqa: E402
from finger.tellergriff import varianten as TV  # noqa: E402
from wahrnehmung import griffpose as WG  # noqa: E402
from wahrnehmung import robustheit as RB  # noqa: E402

RASTER = [(0.0, 0.0), (5.0, 0.0), (15.0, 0.0), (0.0, 5.0), (5.0, 5.0), (15.0, 5.0),
          (0.0, 20.0), (5.0, 20.0), (15.0, 20.0)]
SIGMA = [("sigma_frei", 15.0, 20.0, False), ("sigma_hart", 15.0, 20.0, True)]


def finger(art):
    var = TV.laden()["breit_6n"] if art == "teller" else None
    return A1.Finger.laden(**(var.finger if var else {})), var


def drift_von(art, seed, r_grad, t_mm, hart, sigma=False):
    """Raster: fester Betrag (``drift_fest``). sigma: echte Gauss-Ziehung (``RB.drift``), ``hart``
    kappt dieselbe Ziehung (frei und hart nutzen denselben Seed)."""
    rng = np.random.default_rng(9000 + seed)
    if sigma:
        kap = dict(t_max_m=0.02, r_max_grad=30.0) if hart else {}
        return RB.drift(rng, t_sigma_m=t_mm * 1e-3, r_sigma_grad=r_grad, **kap)
    ax = [0.0, 0.0, 1.0] if art == "teller" else None      # Teller: Gier ist die wirksame Drehlage
    return RB.drift_fest(rng, t_mm * 1e-3, r_grad, achse=ax)


def _resid(art, pose, wahr):
    """Restfehler der Griffpose gegen die Wahrheit: Glas nur in der Korbebene (x, y), Teller 3D."""
    p, w = np.asarray(pose, float), np.asarray(wahr, float)
    d = p[:2] - w[:2] if art == "glas" else p - w[:3]
    return float(1e3 * np.linalg.norm(d))


def eine(art, seed, r_grad, t_mm, hart, s, f, sig, sigma=False):
    w, nenn = GW.welt(art, seed, s)
    dr = drift_von(art, seed, r_grad, t_mm, hart, sigma)
    est = WG.schaetzen(art, w, s, nenn, seed=seed, posedrift=dr)
    wahr = np.asarray(est["wahr_m"], float)
    zeile = {"art": art, "seed": seed, "grad": r_grad, "t_mm": t_mm, "hart": hart, "sigma": sigma,
             "drift_betrag_mm": 1e3 * float(dr["betrag_m"]), "drift_grad": float(dr["grad"]),
             "verworfen_ensenso": "s0_pose_m" not in est}
    if "s0_pose_m" not in est:                     # Station hat das Ziel gar nicht gefunden
        return zeile
    p0 = np.asarray(est["s0_pose_m"], float)
    zeile["s0_mm"] = _resid(art, p0, wahr)
    zeile["s0_gier"] = float(est.get("s0_gier_grad", 0.0))
    if not est.get("ok") and not est.get("pose_m"):            # D405 verloren oder Widerspruch
        zeile["s1_verworfen"] = True
        zeile["gruende"] = est.get("gruende")
        zeile["abstand_mm"] = est.get("ensenso_d405_abstand_mm")
        zeile["s3_kreuz"] = False                              # keine Kreuzprobe; Verwerfen wird getrennt gezaehlt
        zeile["mech"] = {"s0": bool(RB.erfolg_mechanisch(art, zeile["s0_mm"], zeile.get("s0_gier", 0.0), f)["ok"]),
                         "s1": False, "s2": False}
        return zeile
    p1 = np.asarray(est["pose_m"], float)
    g1 = float(est.get("gier_grad", 0.0))
    p2 = RB.fusionieren(p0, p1, sig["ensenso"], sig["d405"])
    zeile.update(s1_mm=_resid(art, p1, wahr), s1_gier=g1, s2_mm=_resid(art, p2, wahr), s2_gier=g1,
                 d405_ok=bool(est.get("d405", {}).get("ok")),
                 abstand_mm=est.get("ensenso_d405_abstand_mm"), gruende=est.get("gruende"))
    mech = {k: RB.erfolg_mechanisch(art, zeile[f"{k}_mm"], zeile[f"{k}_gier"], f) for k in ("s0", "s1", "s2")}
    zeile["mech"] = {k: v["ok"] for k, v in mech.items()}
    tol_ab = 1e3 * (WG.TOL_GLAS_M if art == "glas" else WG.TOL_TELLER_M)
    zeile["s3_kreuz"] = bool(est.get("ensenso_d405_abstand_mm") is not None and est["ensenso_d405_abstand_mm"] > tol_ab)
    zeile["s3_norm"] = bool("ensenso_d405_widerspruch" in (est.get("gruende") or []))
    # S6 (Greifweite beim Schliessen) ist nicht modelliert und wird nicht bewertet (waere tautologisch).
    return zeile


def reihe(art, seeds, out, nur="alle"):
    f, _ = finger(art)
    s = 2 if art == "glas" else 0                 # Glas Platz 5 (Index 3 des Slots), vorderster Teller
    sig = RB.SIGMA_MM[art]
    faenge = {"s4_glas_mm": RB.fangbereich_glas_mm(f), "s4_teller_grad": RB.gier_toleranz_teller_grad(f)}
    stufen = [("feste", r, t, False, False) for r, t in RASTER] + [(n, g, 20.0, ha, True) for n, g, ha in
                                                                  [(x[0], x[1], x[3]) for x in SIGMA]]
    if nur == "sigma":
        stufen = [x for x in stufen if x[4]]
    elif nur == "fest":
        stufen = [x for x in stufen if not x[4]]
    zeilen = []
    for name, r, t, ha, sg in stufen:
        for seed in range(1, seeds + 1):
            z = eine(art, seed, r, t, ha, s, f, sig, sg)
            z["stufe"] = name
            zeilen.append(z)
        print(f"{art} {name} {r}/{t}: {sum(1 for z in zeilen if z['stufe']==name and z.get('mech',{}).get('s1'))}"
              f"/{seeds} S1 ok", flush=True)
    erg = {"art": art, "variant": ("breit_6n" if art == "teller" else "finger100"), "seeds": seeds,
           "grenzen": faenge, "sigma_mm": sig, "zeilen": zeilen}
    (Path(out) / f"robustheit-{art}-{nur}.json").write_text(json.dumps(erg, indent=1, default=str))
    tab(erg)
    return erg


def _m(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def tab(erg):
    z = erg["zeilen"]
    print(f"\n## {erg['art']} (Grenze {erg['grenzen']})\n")
    print("| Stufe | n | S0 mm | S1 mm | S2 mm | S1 Gier | S0 ok | S1 ok | S2 ok | S3 erkannt |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for name in dict.fromkeys(x["stufe"] for x in z):
        g = [x for x in z if x["stufe"] == name]
        ok = {k: sum(1 for x in g if x.get("mech", {}).get(k)) for k in ("s0", "s1", "s2")}
        s3 = sum(1 for x in g if x.get("s3_kreuz") or x.get("s1_verworfen"))

        def fm(k):
            v = _m([x.get(k) for x in g])
            return "–" if v is None else f"{v:.1f}"
        print(f"| {name} | {len(g)} | {fm('s0_mm')} | {fm('s1_mm')} | {fm('s2_mm')} | "
              f"{fm('s1_gier')} | {ok['s0']}/{len(g)} | {ok['s1']}/{len(g)} | {ok['s2']}/{len(g)} | "
              f"{s3}/{len(g)} |")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--art", choices=["glas", "teller"], default=None)
    ap.add_argument("--seeds", type=int, default=16)
    ap.add_argument("--nur", choices=["alle", "fest", "sigma"], default="alle")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    Path(a.out).mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    for art in ([a.art] if a.art else ["glas", "teller"]):
        reihe(art, a.seeds, a.out, a.nur)
    print(f"\nWand {time.monotonic() - t0:.0f} s")


if __name__ == "__main__":
    main()
