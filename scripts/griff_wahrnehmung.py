#!/usr/bin/env python3
"""Wahrnehmung allein (ohne Newton): Glas/Teller je Seed schaetzen, Negativtests, Pruefbilder.
Liefert die Tabellen "Wahrnehmung allein" und "Negativtests" in docs/griff-verrauscht.md
(zusammen mit scripts/griff_auswertung.py).

    griff_wahrnehmung.py --art glas|teller --seeds 1-20 [--negativ MODUS] [--ziel N]
                         [--bild DATEI.png] [--json DATEI.json]
    griff_wahrnehmung.py --alle AUSGABE     # 20 Seeds je Objekt + 3 Negativtests je 5 Seeds
    griff_wahrnehmung.py --vergleich AUSGABE [--seeds 1-16]   # altes Sichtfeld gegen C57-6-S

Stationskamera: ``--kamera`` (Standard c57_6_s; ``b57_alt`` = altes Sichtfeld), ``--mast X,Y,Z`` und
``--neigung GRAD`` (Standard Mast 0,55;0,50;1,35 und 60 Grad), ``--pose-alt`` = Mast des alten Stands
(0,55;0,40;1,10, Blick auf (0,30;0,17;0,48)).

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


def reihe(art, lo, hi, negativ=None, ziel=None, bild_pfad=None, json_pfad=None, kamera=None, pose=None):
    s = (ziel or (3 if art == "glas" else 1)) - 1
    rows = []
    for seed in range(lo, hi + 1):
        w, nenn = welt(art, seed, s)
        t0 = time.monotonic()
        est = WG.schaetzen(art, w, s, nenn, seed=seed, negativ=negativ, mit_aufnahmen=bool(bild_pfad),
                          ensenso_kamera=kamera, ensenso_pose=pose)
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


VARIANTEN = {
    # Name: (Kamera, Pose): alt = Stand der Vorstudien; neu = C57-6-S am Mast 1,35 m; dazwischen je eine
    # Achse geaendert, damit sichtbar wird, was Modell und was Mastpose verschiebt
    "alt": ("b57_alt", WG.ENSENSO_POSE_ALT),
    "c57_alter_mast": ("c57_6_s", WG.ENSENSO_POSE_ALT),
    "b57_neuer_mast": ("b57_alt", WG.ENSENSO_POSE),
    "neu": ("c57_6_s", WG.ENSENSO_POSE),
}


def zusammenfassung(rows):
    """Angenommen (Sichtbarkeit), Lagefehler Median/Max gegen die Wahrheit und Abbruchgruende."""
    from collections import Counter
    ok = [r for r in rows if r["kurz"]["ok"]]
    fe = [r["kurz"]["fehler_mm"] for r in rows if r["kurz"]["fehler_mm"] is not None]
    fe_ok = [r["kurz"]["fehler_mm"] for r in ok]
    gr = Counter(g for r in rows for g in r["kurz"]["gruende"])
    stat = [r["kurz"]["stat_e"] for r in rows if r["kurz"]["stat_e"]]
    px = [r["voll"].get("ensenso", {}).get("maske_px", 0) for r in rows]
    return {"n": len(rows), "angenommen": len(ok),
            "fehler_median_mm": float(np.median(fe)) if fe else None,
            "fehler_max_mm": float(max(fe)) if fe else None,
            "fehler_angenommen_median_mm": float(np.median(fe_ok)) if fe_ok else None,
            "fehler_angenommen_max_mm": float(max(fe_ok)) if fe_ok else None,
            "ensenso_maske_px_median": float(np.median(px)),
            "ensenso_gueltig_prozent_median": float(np.median([s["gueltig_%"] for s in stat])) if stat else None,
            "gruende": dict(gr.most_common())}


def vergleich(o: Path, lo: int, hi: int):
    """Glas Platz 5 und vorderster Teller in allen Varianten mit denselben Seeds."""
    o.mkdir(parents=True, exist_ok=True)
    erg = {}
    for name, (kam, pose) in VARIANTEN.items():
        erg[name] = {"kamera": kam, "mast": list(pose[0])}
        for art in ("glas", "teller"):
            rows = reihe(art, lo, hi, kamera=kam, pose=pose)
            (o / f"{art}-{name}.json").write_text(json.dumps(rows, indent=1, default=str))
            erg[name][art] = zusammenfassung(rows)
            print(name, art, json.dumps(erg[name][art]), flush=True)
    (o / "zusammenfassung.json").write_text(json.dumps({"seeds": [lo, hi], "varianten": erg}, indent=1))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--art", choices=["glas", "teller"])
    ap.add_argument("--seeds", default=None, help="Bereich LO-HI (Standard 1-3, bei --vergleich 1-16)")
    ap.add_argument("--kamera", default=None, help="Stationsmodell: c57_6_s (Standard) | b57_alt (altes Sichtfeld)")
    ap.add_argument("--mast", default=None, help="X,Y,Z des Masts (Standard 0.55,0.50,1.35)")
    ap.add_argument("--neigung", type=float, default=WG.ENSENSO_NEIGUNG_GRAD, help="Blickneigung unter der Waagerechten")
    ap.add_argument("--pose-alt", action="store_true", help="Mastpose des alten Stands (1,10 m)")
    ap.add_argument("--vergleich", default=None, help="Ausgabeordner: Glas Platz 5 / vorderster Teller, alt gegen neu")
    ap.add_argument("--negativ", default=None)
    ap.add_argument("--ziel", type=int, default=None)
    ap.add_argument("--bild", default=None)
    ap.add_argument("--json", default=None)
    ap.add_argument("--alle", default=None, help="Ausgabeordner: alle Reihen der Doku (wahrnehmung/*.json, bilder/)")
    a = ap.parse_args()
    pose = None
    if a.pose_alt:
        pose = WG.ENSENSO_POSE_ALT
    elif a.mast:
        pose = WG.ensenso_pose_aus([float(v) for v in a.mast.split(",")], a.neigung)
    elif a.neigung != WG.ENSENSO_NEIGUNG_GRAD:
        pose = WG.ensenso_pose_aus(WG.ENSENSO_POSE[0], a.neigung)
    if a.vergleich:
        lo, hi = (int(x) for x in (a.seeds or "1-16").split("-"))
        vergleich(Path(a.vergleich), lo, hi)
        return
    if a.alle:
        o = Path(a.alle)
        (o / "wahrnehmung").mkdir(parents=True, exist_ok=True)
        (o / "bilder").mkdir(parents=True, exist_ok=True)
        for art in ("glas", "teller"):
            reihe(art, 1, 20, json_pfad=o / "wahrnehmung" / f"{art}.json", kamera=a.kamera, pose=pose)
            for n in NEGATIV[art]:
                reihe(art, 1, 5, negativ=n, json_pfad=o / "wahrnehmung" / f"{art}-{n}.json",
                      bild_pfad=o / "bilder" / f"negativ-{art}-{n}.png", kamera=a.kamera, pose=pose)
        return
    if not a.art:
        ap.error("--art oder --alle")
    lo, hi = (int(x) for x in (a.seeds or "1-3").split("-"))
    reihe(a.art, lo, hi, a.negativ, a.ziel, a.bild, a.json, a.kamera, pose)


if __name__ == "__main__":
    main()
