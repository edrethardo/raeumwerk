#!/usr/bin/env python3
"""Kameratag P2: Mechanik-Prior-Kette, "neu hinsehen", Zielverwechslung.

Wahrnehmung allein (ohne Newton), CPU. Je Objekt/Seed/Fehlerstufe zwei Schaetzungen:

  * Standard (``griffpose.schaetzen`` ohne Schalter): S0 blind, S1 Nahekorrektur, S2 Fusion,
    Kette = heutige Pruefung (Abbruch bei Widerspruch), A = "neu hinsehen" (D405-Pose zaehlt,
    solange sie im Plan liegt; abgeleitet aus den Abbruchgruenden, Gleichheit mit dem Schalter
    ``neu_hinsehen=True`` steht in ``tests/test_prior.py``), N0 = Nennlage blind (nur Prior).
  * Prior (``prior=``): B = Schaetzung auf Nennlage +- Toleranz beschnitten.

Teile:  raster (Raster {0,5,15} Grad x {0,5,20} mm + Gauss-sigma frei/hart, Welt wie in der Griffrobustheit-Reihe),
        welt   (sigma frei/hart; die WELT weicht um das 1x..Nx von dem ab, was der Prior annimmt),
        c      (Zielverwechslung: Nachbarmaske fuer beide Kameras).

Gier-Fehler wird gegen die WAHRE Gier der Welt gerechnet (``WG``-Normale des Ziels), nicht gegen
0 Grad wie in ``griff_robustheit.py`` (dort ist die wahre Gier +-1 Grad klein gegen die Drift).

    griff_prior.py --out ORDNER [--teil raster|welt|c|alle] [--seeds 16] [--arten glas,teller] [--jobs 4]

Schreibt ``zeilen-<teil>.jsonl`` (eine Zeile je Lauf, fortsetzbar).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))
sys.path.insert(0, str(HIER))

import numpy as np  # noqa: E402

import griff_lauf as GL  # noqa: E402
import griff_robustheit as GR  # noqa: E402
from wahrnehmung import griffpose as WG  # noqa: E402
from wahrnehmung import robustheit as RB  # noqa: E402

# Skalierung der WELT (Versatz, Drehung/Gier) gegen das, was der Prior annimmt
SKALEN = {"glas": [(2.0, 2.0), (3.0, 3.0)],
          "teller": [(2.0, 2.0), (3.0, 3.0), (1.0, 3.0), (1.0, 6.0)]}
NEGATIV = {"glas": ("nachbar", "zwei_glaeser"), "teller": ("nachbar", "teller_doppelt")}
C_DRIFT = [("ohne", 0.0, 0.0, False, False), ("sigma_hart", 15.0, 20.0, True, True)]


def welt(art, seed, s, sk):
    var, f, sz, A = GL.szenario_und_aufbau(art, None, s + 1)
    abw, tabw = GL.abweichung(art, seed, sk[0], sk[1])
    w = (GL.welt_glas if art == "glas" else GL.welt_teller)(A, sz, f, abw, tabw)
    return w, GL.nennlage_fn(A, sz, f, art, s)


def gier_fehler(g, g_wahr):
    return abs(RB.wrap_gier(float(g) - float(g_wahr)))


def bew(art, pose, gier, wahr, g_wahr, f):
    mm = GR._resid(art, pose, wahr)
    ge = gier_fehler(gier, g_wahr) if art == "teller" else 0.0
    return {"mm": mm, "gier_fehler": ge, "ok": bool(RB.erfolg_mechanisch(art, mm, ge, f)["ok"])}


def _nachbar_abstand_mm(art, w, s):
    prims = WG.prims_aus_welt(w, art)
    ziel = [p for p in prims if p.objekt == w.glas_start[s].name][0]
    nb = WG._nachbar(prims, ziel, "glas" if art == "glas" else "teller")
    return float(1e3 * np.linalg.norm(nb.c - ziel.c))


def lauf(task):
    art, kind, name, r, t, hart, sigma, sk, negativ, seed = task
    s = 2 if art == "glas" else 0
    f, _ = GR.finger(art)
    t0 = time.monotonic()
    w, nenn = welt(art, seed, s, sk)
    dr = GR.drift_von(art, seed, r, t, hart, sigma)
    z = {"art": art, "kind": kind, "stufe": name, "grad": r, "t_mm": t, "hart": hart, "sigma": sigma,
         "skala_xy": sk[0], "skala_dreh": sk[1], "negativ": negativ, "seed": seed,
         "drift_betrag_mm": 1e3 * float(dr["betrag_m"]), "drift_grad": float(dr["grad"])}
    kw = dict(seed=seed, negativ=negativ, posedrift=dr)
    est = WG.schaetzen(art, w, s, nenn, **kw)
    wahr = np.asarray(est["wahr_m"], float)
    g_wahr = RB.gier_aus_normale(np.asarray(w.glas_start[s].rot, float)[:, 2]) if art == "teller" else 0.0
    z["gier_wahr"] = g_wahr
    if negativ:
        z["nachbar_abstand_mm"] = _nachbar_abstand_mm(art, w, s)
    if "s0_pose_m" not in est:
        z["ensenso_fehlt"] = True
        z["gruende"] = est.get("gruende")
        z["wand_s"] = time.monotonic() - t0
        return z
    z["n0"] = bew(art, est["nenn_m"], 0.0, wahr, g_wahr, f)          # Nennlage blind (nur Prior, keine Kamera)
    z["s0"] = bew(art, est["s0_pose_m"], est.get("s0_gier_grad", 0.0), wahr, g_wahr, f)
    gr = est.get("gruende") or []
    z["gruende"] = gr
    z["ok_std"] = bool(est.get("ok"))
    z["abstand_mm"] = est.get("ensenso_d405_abstand_mm")
    z["s3_kreuz"] = "ensenso_d405_widerspruch" in gr
    z["d405_verworfen"] = "pose_m" not in est
    if "pose_m" in est:
        p0, p1 = np.asarray(est["s0_pose_m"], float), np.asarray(est["pose_m"], float)
        g1 = float(est.get("gier_grad", 0.0))
        z["s1"] = bew(art, p1, g1, wahr, g_wahr, f)
        z["s2"] = bew(art, RB.fusionieren(p0, p1, RB.SIGMA_MM[art]["ensenso"], RB.SIGMA_MM[art]["d405"]), g1,
                      wahr, g_wahr, f)
        z["a_annahme"] = bool(set(gr) <= {"ensenso_d405_widerspruch"})
    else:
        z["s1"] = z["s2"] = None
        z["a_annahme"] = False
    ep = WG.schaetzen(art, w, s, nenn, prior=RB.prior_standard(art), **kw)
    z["b_gruende"] = ep.get("gruende")
    z["b_annahme"] = bool(ep.get("ok"))
    pr = ep.get("prior") or {}
    z["b_prior"] = {k: v for k, v in pr.items() if k in ("widerspruch_xy", "widerspruch_gier", "station_roh_abw_mm",
                                                       "d405_roh_abw_mm", "gier_roh_grad", "gier_abw_roh_grad",
                                                       "kreuzprobe_roh_anschlag")}
    if "pose_m" in ep:
        z["b"] = bew(art, ep["pose_m"], float(ep.get("gier_grad", 0.0)), wahr, g_wahr, f)
    else:
        z["b"] = None
    z["wand_s"] = time.monotonic() - t0
    return z


def aufgaben(teil, seeds, arten):
    out = []
    for art in arten:
        if teil in ("raster", "alle"):
            stufen = [(f"{r:.0f}°/{t:.0f} mm", r, t, False, False) for r, t in GR.RASTER]
            stufen += [("sigma_frei", 15.0, 20.0, False, True), ("sigma_hart", 15.0, 20.0, True, True)]
            out += [(art, "raster", n, r, t, h, sg, (1.0, 1.0), None, sd)
                    for n, r, t, h, sg in stufen for sd in range(1, seeds + 1)]
        if teil in ("welt", "alle"):
            out += [(art, "welt", n, 15.0, 20.0, h, True, sk, None, sd)
                    for sk in SKALEN[art] for n, h in (("sigma_frei", False), ("sigma_hart", True))
                    for sd in range(1, seeds + 1)]
        if teil in ("c", "alle"):
            out += [(art, "c", n, r, t, h, sg, (1.0, 1.0), neg, sd)
                    for neg in NEGATIV[art] for n, r, t, h, sg in C_DRIFT for sd in range(1, seeds + 1)]
    return out


def schluessel(z):
    return (z["art"], z["kind"], z["stufe"], z["skala_xy"], z["skala_dreh"], z["negativ"], z["seed"])


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--teil", choices=["raster", "welt", "c", "alle"], default="alle")
    ap.add_argument("--seeds", type=int, default=16)
    ap.add_argument("--arten", default="glas,teller")
    ap.add_argument("--jobs", type=int, default=4)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    pfad = out / f"zeilen-{a.teil}.jsonl"
    fertig = set()
    if pfad.exists():
        for ln in pfad.read_text().splitlines():
            if ln.strip():
                fertig.add(schluessel(json.loads(ln)))
    todo = [x for x in aufgaben(a.teil, a.seeds, a.arten.split(","))
            if (x[0], x[1], x[2], x[7][0], x[7][1], x[8], x[9]) not in fertig]
    print(f"{len(todo)} Laeufe offen ({len(fertig)} fertig)", flush=True)
    t0 = time.monotonic()
    n = 0
    with open(pfad, "a") as fh, ProcessPoolExecutor(max_workers=a.jobs) as ex:
        for z in ex.map(lauf, todo, chunksize=1):
            fh.write(json.dumps(z, default=float) + "\n")
            fh.flush()
            n += 1
            if n % 20 == 0:
                print(f"{n}/{len(todo)} {time.monotonic() - t0:.0f} s", flush=True)
    print(f"fertig, Wand {time.monotonic() - t0:.0f} s", flush=True)


if __name__ == "__main__":
    main()
