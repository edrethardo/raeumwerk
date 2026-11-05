#!/usr/bin/env python3
"""Kameratag P4: Modellauswertungen fuer die Sensitivitaetsanalyse (Wahrnehmung allein, CPU, wahre Maske).

Je Zeile ein Parametersatz ``th`` (siehe ``wahrnehmung/sensitivitaet.py: PARAMETER``), ein Objekt (Glas, Teller)
und ein Seed; ausgewertet werden die heutige Kette (K), "neu hinsehen" (A) und der Mechanik-Prior (B) wie in
``scripts/griff_prior.py``. Erkennungsrate und Zielverwechslung gehen NICHT hier ein (analytisch, Auswertung).

    sensitivitaet_lauf.py --out ORDNER --teil design|sweep|conf|val [--n 256] [--von 0] [--seeds 8] [--jobs 4]

  design  Sobol-Design ueber alle physikalischen Parameter, 1 Seed je Punkt (Seed = 100 + Punkt-Index)
  sweep   Eindimensionale Laeufe um den Plan-Wert (Gitter je Parameter), ``--seeds`` Seeds je Punkt
  conf    Design-Punkte ``--von`` .. ``--von``+``--n`` mit Nachbarmaske (``negativ='nachbar'``): unbemerkte Verwechslung
  val     Validierung des Metamodells: ``--n`` frische Zufallspunkte x ``--seeds`` Seeds

Schreibt ``zeilen-<teil>.jsonl`` (fortsetzbar, eine Zeile je Punkt/Objekt/Seed).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))
sys.path.insert(0, str(HIER))

import numpy as np  # noqa: E402

from wahrnehmung import sensitivitaet as SE  # noqa: E402

GITTER = {   # Sweep-Gitter je physikalischem Parameter; der Plan-Wert kommt als eigener Punkt dazu
    "dicke_mm": [3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
    "gier_grad": [0, 1, 2, 3, 4, 5, 6, 7, 8],
    "glas_lage_mm": [0, 2.5, 5, 7.5, 10],
    "teller_lage_mm": [0, 5, 10, 15],
    "kalib_versatz_mm": [0, 2.5, 5, 7.5, 10, 15, 20, 30],
    "kalib_dreh_grad": [0, 5, 10, 15, 20],
    "rausch_ens": [0.5, 1, 2, 3],
    "rausch_d405": [0.5, 1, 2, 3],
    "maske_versatz_px": [0, 0.7, 1.5, 3],
    "maske_kipp": [0, 0.5, 1],
    "maske_bias_px": [-3, -2, -1, 0, 1, 2, 3],
    "mast": [0, 1, 2, 3],
}

_G = {"inst": False, "d405k": 1.0, "bias": 0}


def _installiere():
    """Haengt Rauschfaktor D405 und Maskenrand-Bias in ``griffpose`` ein (pro Prozess einmal)."""
    if _G["inst"]:
        return
    from scipy import ndimage

    from wahrnehmung import griffpose as WG
    from wahrnehmung import strahlen as ST

    orig_d = WG.d405_am_greifer
    orig_m = WG.maske_verrauschen

    def d405(*a, **kw):
        cam = orig_d(*a, **kw)
        if _G["d405k"] != 1.0:
            mod = dict(cam.modell, sigma_k=cam.modell["sigma_k"] * _G["d405k"])
            cam = ST.Kamera(cam.name, mod, cam.C, cam.R, cam.skala)
        return cam

    def maske(m, rng, p_kippen=0.5, versatz_px=0.0):
        k = int(_G["bias"])
        if k > 0:
            m = ndimage.binary_dilation(m, iterations=k)
        elif k < 0:
            m = ndimage.binary_erosion(m, iterations=-k)
        return orig_m(m, rng, p_kippen, versatz_px)

    WG.d405_am_greifer = d405
    WG.maske_verrauschen = maske
    _G["inst"] = True


def _szene(art, dicke_mm):
    """Wie ``griff_lauf.szenario_und_aufbau`` (Standard-Finger), nur mit waehlbarer Randdicke des Tellers."""
    import griff_lauf as GL
    from finger import a1 as A1
    from finger.parameter import Finger

    f = Finger.laden(**({"teller__wulst_dicke_mm": float(dicke_mm)} if art == "teller" else {}))
    sz = A1.szenario()
    sz["glaeser"]["slots"] = list(GL.GLAS_SLOTS)
    GL.auf_neue_lage(sz)
    return f, sz, A1.aufbau(sz, f)


def _bew(art, pose, gier, wahr, g_wahr, f_mech):
    import griff_robustheit as GR
    from wahrnehmung import robustheit as RB
    mm = GR._resid(art, pose, wahr)
    ge = abs(RB.wrap_gier(float(gier) - float(g_wahr))) if art == "teller" else 0.0
    return {"mm": mm, "gier_fehler": ge, "ok": bool(RB.erfolg_mechanisch(art, mm, ge, f_mech)["ok"])}


def auswerten(art, th, seed, negativ=None):
    """Eine Modellauswertung (Glas oder Teller) -> Zeile (dict)."""
    import griff_lauf as GL
    import griff_robustheit as GR
    from wahrnehmung import griffpose as WG
    from wahrnehmung import robustheit as RB
    from wahrnehmung.sensor import Fehlermodell
    from wahrnehmung.strahlen import ensenso_modell

    _installiere()
    t0 = time.monotonic()
    s = 2 if art == "glas" else 0
    _G["d405k"] = float(th["rausch_d405"])
    _G["bias"] = int(round(th["maske_bias_px"]))
    f, sz, A = _szene(art, th["dicke_mm"])
    f_mech, _ = GR.finger(art)
    lage = th["glas_lage_mm"] if art == "glas" else th["teller_lage_mm"]
    abw, tabw = GL.abweichung(art, seed, lage / 5.0, 1.0)
    g_wahr = 0.0
    if art == "teller":
        vz = 1.0 if np.random.default_rng(seed + 7).random() < 0.5 else -1.0
        t = list(tabw["teller"])
        t[s] = (t[s][0], t[s][1], vz * float(th["gier_grad"]))
        tabw["teller"] = t
    w = (GL.welt_glas if art == "glas" else GL.welt_teller)(A, sz, f, abw, tabw)
    nenn = GL.nennlage_fn(A, sz, f, art, s)
    dr = RB.drift_fest(np.random.default_rng(9000 + seed), th["kalib_versatz_mm"] * 1e-3, th["kalib_dreh_grad"],
                       achse=[0.0, 0.0, 1.0] if art == "teller" else None)
    mast, neig = SE.MAST[SE.MAST_NAMEN[int(th["mast"])]]
    pose = WG.ensenso_pose_aus(mast, neig)
    mod = dict(ensenso_modell(None))
    mod["sigma_k"] = mod["sigma_k"] * float(th["rausch_ens"])
    fm = Fehlermodell(maske_rand_kippen=float(th["maske_kipp"]), maske_versatz_px=float(th["maske_versatz_px"]))
    kw = dict(seed=seed, negativ=negativ, posedrift=dr, fm=fm, ensenso_kamera=mod, ensenso_pose=pose)
    z = {"art": art, "seed": seed, "th": th, "negativ": negativ}
    est = WG.schaetzen(art, w, s, nenn, **kw)
    wahr = np.asarray(est["wahr_m"], float)
    if art == "teller":
        g_wahr = RB.gier_aus_normale(np.asarray(w.glas_start[s].rot, float)[:, 2])
    z["gier_wahr"] = g_wahr
    z["ensenso_ok"] = "s0_pose_m" in est
    z["gruende"] = est.get("gruende")
    z["ok_std"] = bool(est.get("ok"))
    z["abstand_mm"] = est.get("ensenso_d405_abstand_mm")
    z["d405_mm"] = est.get("d405", {}).get("fehler_mm") if "pose_m" in est else None
    z["s1"] = None
    z["a_annahme"] = False
    if "pose_m" in est:
        z["s1"] = _bew(art, est["pose_m"], float(est.get("gier_grad", 0.0)), wahr, g_wahr, f_mech)
        z["a_annahme"] = bool(set(est.get("gruende") or []) <= {"ensenso_d405_widerspruch"})
    ep = WG.schaetzen(art, w, s, nenn, prior=RB.prior_standard(art), **kw)
    z["b_gruende"] = ep.get("gruende")
    z["b_annahme"] = bool(ep.get("ok"))
    z["b"] = (_bew(art, ep["pose_m"], float(ep.get("gier_grad", 0.0)), wahr, g_wahr, f_mech)
              if "pose_m" in ep else None)
    z["wand_s"] = round(time.monotonic() - t0, 2)
    return z


def _init():
    try:
        os.nice(10)
    except OSError:
        pass


def _lauf(task):
    kind, idx, art, th, seed, negativ = task
    try:
        z = auswerten(art, th, seed, negativ)
    except Exception:  # noqa: BLE001
        z = {"art": art, "seed": seed, "th": th, "negativ": negativ, "fehler": traceback.format_exc()[-800:]}
    z.update(kind=kind, idx=idx)
    return z


def aufgaben(teil, n, von, seeds):
    out = []
    if teil in ("design", "conf"):
        u = SE.design(int(2 ** np.ceil(np.log2(max(n + von, 2)))))
        for i in range(von, von + n):
            th = SE.von_einheit(u[i], SE.PHYS)
            for art in ("glas", "teller"):
                out.append((teil, i, art, th, 100 + i, "nachbar" if teil == "conf" else None))
    elif teil == "sweep":
        plan = {p.name: p.plan for p in SE.PHYS}
        pts = [("plan", 0.0, dict(plan))]
        for name, werte in GITTER.items():
            for v in werte:
                th = dict(plan)
                th[name] = float(v)
                pts.append((name, float(v), th))
        for j, (name, v, th) in enumerate(pts):
            for sd in range(1, seeds + 1):
                for art in ("glas", "teller"):
                    out.append((f"sweep:{name}:{v}", j, art, th, 5000 + sd, None))
    elif teil == "val":
        u = np.random.default_rng(777).random((n, len(SE.PHYS)))
        for i in range(n):
            th = SE.von_einheit(u[i], SE.PHYS)
            for sd in range(1, seeds + 1):
                for art in ("glas", "teller"):
                    out.append((f"val:{i}", i, art, th, 8000 + sd, None))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--teil", choices=["design", "sweep", "conf", "val"], required=True)
    ap.add_argument("--n", type=int, default=256)
    ap.add_argument("--von", type=int, default=0)
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--jobs", type=int, default=4)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    kap = out / "kappung.json"      # optional: {"conf": {"n": 64}, "val": {"n": 16, "seeds": 4}, "design": {"max_index": 512}}
    max_index = None
    if kap.exists():
        k = json.loads(kap.read_text()).get(a.teil, {})
        a.n, a.seeds = min(a.n, k.get("n", a.n)), min(a.seeds, k.get("seeds", a.seeds))
        max_index = k.get("max_index")
    pfad = out / f"zeilen-{a.teil}.jsonl"
    fertig = set()
    if pfad.exists():
        for ln in pfad.read_text().splitlines():
            if ln.strip():
                z = json.loads(ln)
                if "fehler" not in z:
                    fertig.add((z["kind"], z["idx"], z["art"], z["seed"]))
    todo = [t for t in aufgaben(a.teil, a.n, a.von, a.seeds) if (t[0], t[1], t[2], t[4]) not in fertig
            and (max_index is None or t[1] < max_index)]
    print(f"{len(todo)} Laeufe offen ({len(fertig)} fertig)", flush=True)
    t0 = time.monotonic()
    n = 0
    with open(pfad, "a") as fh, ProcessPoolExecutor(max_workers=a.jobs, initializer=_init) as ex:
        for z in ex.map(_lauf, todo, chunksize=1):
            fh.write(json.dumps(z, default=float) + "\n")
            fh.flush()
            n += 1
            if n % 20 == 0:
                print(f"{n}/{len(todo)} {time.monotonic() - t0:.0f} s", flush=True)
    print(f"fertig, Wand {time.monotonic() - t0:.0f} s", flush=True)


if __name__ == "__main__":
    main()
