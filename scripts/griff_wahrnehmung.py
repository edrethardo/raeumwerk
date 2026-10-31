#!/usr/bin/env python3
"""Wahrnehmung allein (ohne Newton): Glas/Teller je Seed schaetzen, Negativtests, Pruefbilder.
Liefert die Tabellen "Wahrnehmung allein" und "Negativtests" in docs/griff-verrauscht.md
(zusammen mit scripts/griff_auswertung.py).

    griff_wahrnehmung.py --art glas|teller --seeds 1-20 [--negativ MODUS] [--ziel N]
                         [--bild DATEI.png] [--json DATEI.json]
    griff_wahrnehmung.py --alle AUSGABE     # 20 Seeds je Objekt + 3 Negativtests je 5 Seeds

Negativtests: glas zwei_glaeser | versatz | nachbar, teller teller_doppelt | versatz | nachbar.
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

import griff_lauf as GL  # noqa: E402
from wahrnehmung import griffpose as WG  # noqa: E402

NEGATIV = {"glas": ("zwei_glaeser", "versatz", "nachbar"), "teller": ("teller_doppelt", "versatz", "nachbar")}


def welt(art, seed, s):
    """Wahre Welt (Lageabweichung aus dem Seed) und Nennlage laut Belegungsplan."""
    var, f, sz, A = GL.szenario_und_aufbau(art, None, s + 1)
    abw, tabw = GL.abweichung(art, seed)
    w = (GL.welt_glas if art == "glas" else GL.welt_teller)(A, sz, f, abw, tabw)
    return w, GL.nennlage_fn(A, sz, f, art, s)


def bild(est, pfad, titel):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(2, 2, figsize=(12, 9))
    for j, k in enumerate(("ensenso", "d405")):
        if k not in est["_aufnahmen"]:
            ax[0, j].set_axis_off()
            ax[1, j].set_axis_off()
            ax[0, j].set_title(f"{k}: not reached (aborted before)")
            continue
        auf, m = est["_aufnahmen"][k]
        h, w = auf.hw
        zt = (auf.mess * (auf.d @ auf.cam.R[:, 2])).reshape(h, w)
        ax[0, j].imshow(zt, cmap="viridis")
        ax[0, j].set_title(f"{k}: depth (nan = no value)")
        ov = np.zeros((h, w, 3))
        ov[..., 0] = m
        ov[..., 1] = np.isfinite(auf.mess).reshape(h, w) * 0.6
        ov[..., 2] = (auf.glas_art.reshape(h, w) == 2) * 1.0
        ax[1, j].imshow(ov)
        ax[1, j].set_title(f"{k}: mask (red), valid depth (green), see-through (blue)")
        ys, xs = np.where(m)
        if len(xs):
            for a_ in (ax[0, j], ax[1, j]):
                a_.set_xlim(max(0, xs.min() - 80), min(w, xs.max() + 80))
                a_.set_ylim(min(h, ys.max() + 80), max(0, ys.min() - 80))
    fig.suptitle(titel)
    fig.tight_layout()
    fig.savefig(pfad, dpi=80)


def reihe(art, lo, hi, negativ=None, ziel=None, bild_pfad=None, json_pfad=None):
    s = (ziel or (3 if art == "glas" else 1)) - 1
    rows = []
    for seed in range(lo, hi + 1):
        w, nenn = welt(art, seed, s)
        t0 = time.monotonic()
        est = WG.schaetzen(art, w, s, nenn, seed=seed, negativ=negativ, mit_aufnahmen=bool(bild_pfad))
        dt = time.monotonic() - t0
        if bild_pfad and seed == lo:
            bild(est, bild_pfad, f"{art} seed {seed} negative {negativ}: ok={est['ok']} {est['gruende']}")
        est.pop("_aufnahmen", None)
        r = {"seed": seed, "ok": est["ok"], "gruende": est["gruende"], "fehler_mm": est.get("fehler_mm"),
             "ensenso_mm": est.get("ensenso", {}).get("fehler_mm"), "d405_mm": est.get("d405", {}).get("fehler_mm"),
             "abstand_mm": est.get("ensenso_d405_abstand_mm"), "abstand_soll_mm": est.get("abstand_soll_mm"),
             "modell_e": est.get("ensenso", {}).get("modell"), "modell_d": est.get("d405", {}).get("modell"),
             "stat_e": est.get("ensenso", {}).get("statistik"), "stat_d": est.get("d405", {}).get("statistik"),
             "s": round(dt, 1)}
        rows.append({"kurz": r, "voll": est})
        print(json.dumps(r, default=str), flush=True)
    if json_pfad:
        Path(json_pfad).write_text(json.dumps(rows, indent=1, default=str))
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--art", choices=["glas", "teller"])
    ap.add_argument("--seeds", default="1-3")
    ap.add_argument("--negativ", default=None)
    ap.add_argument("--ziel", type=int, default=None)
    ap.add_argument("--bild", default=None)
    ap.add_argument("--json", default=None)
    ap.add_argument("--alle", default=None, help="Ausgabeordner: alle Reihen der Doku (wahrnehmung/*.json, bilder/)")
    a = ap.parse_args()
    if a.alle:
        o = Path(a.alle)
        (o / "wahrnehmung").mkdir(parents=True, exist_ok=True)
        (o / "bilder").mkdir(parents=True, exist_ok=True)
        for art in ("glas", "teller"):
            reihe(art, 1, 20, json_pfad=o / "wahrnehmung" / f"{art}.json")
            for n in NEGATIV[art]:
                reihe(art, 1, 5, negativ=n, json_pfad=o / "wahrnehmung" / f"{art}-{n}.json",
                      bild_pfad=o / "bilder" / f"negativ-{art}-{n}.png")
        return
    if not a.art:
        ap.error("--art oder --alle")
    lo, hi = (int(x) for x in a.seeds.split("-"))
    reihe(a.art, lo, hi, a.negativ, a.ziel, a.bild, a.json)


if __name__ == "__main__":
    main()
