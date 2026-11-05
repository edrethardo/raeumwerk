#!/usr/bin/env python3
"""Lagefehler der Griffpose mit erkannter Maske gegen die wahre Maske (Kameratag P3).

    p3_lage.py SZENEN.json RENDERORDNER ERKENNUNGSORDNER --out ORDNER
               [--quellen wahr,maskrcnn,baseline] [--je-szene 3] [--jobs 2] [--schwelle 0.5] [--auswerten-nur]

Je Szene (ohne Tuning ``t_``) bis zu ``--je-szene`` sichtbare Ziele (Glas oder Teller, Instanzkarte >= MIN_PX).
Quelle ``wahr``: ``maske_wahr`` mit Randrauschen (bisheriger Stand). Quelle ``maskrcnn``/``baseline``: die Erkennung
im Bild der Stationskamera; ausgewaehlt wird die Erkennung der passenden Klasse, deren Maske den Nennort des Ziels
(Belegungsplan, Korbauszug wie gemessen) im Bild enthaelt bzw. am naechsten liegt (maximal 0,6 Objektradius
entfernt) — die Wahrheit geht nicht in die Auswahl ein. Keine Erkennung -> Abbruch ``ensenso:keine_erkennung``.
Tiefe, Fehlermodell und Pose-Schaetzer sind die des Strahlschnitt-Simulators (kein Isaac-Tiefenbild); Nass-Szenen
rechnen mit dem Standard-Fehlermodell (5 % Ausfall auf nassen Flaechen), trockene ohne.
Schreibt ``lage.jsonl`` (eine Zeile je Ziel und Quelle) und ``lage.md`` (Tabelle).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from wahrnehmung import erkennung as E  # noqa: E402
from wahrnehmung import griffpose as WG  # noqa: E402
from wahrnehmung import p3_szenen as P3  # noqa: E402
from wahrnehmung.sensor import Fehlermodell  # noqa: E402

AUSZUG_VOLL = 0.45
KOPF = P3.KOPFUEBER


def ziele_waehlen(d, render, n, rng):
    z = np.load(Path(render) / f"{d['id']}_inst.npz")
    namen = [str(x) for x in z["namen"]]
    sicht = {nm: int((z["inst"] == i + 1).sum()) for i, nm in enumerate(namen)}
    kand = [o for o in d["objekte"] if sicht.get(o["name"], 0) >= E.MIN_PX]
    idx = rng.permutation(len(kand))[:n]
    return [kand[i] for i in sorted(idx)]


def _lauf(args):
    d, o, quelle, erk_pfad, schwelle, seed, dicke = args
    if dicke is not None:           # andere Tellerdicke (m) als in der Szenendatei
        d = P3.dicke_anwenden(d, dicke)
        o = next(x for x in d["objekte"] if x["name"] == o["name"])
    prims = P3.prims_aus_szene(d)
    art = o["klasse"]
    r, h = o["radius"], o["hoehe"]
    ziel = NS(name=o["name"], gruppe=art, mitte=np.asarray(o["mitte"], float), halb=np.array([r, r, h / 2.0]),
              rot=np.asarray(o["rot"], float))
    voll = np.asarray(o["nenn_mitte"], float) + [0.0, AUSZUG_VOLL - d["auszug_m"], 0.0]
    rot_n = KOPF if art == "glas" else P3.TELLER_ROT
    w = NS(glas_start=[ziel], teller=[], statisch_ohne_teller=[], aufbau=NS(abw=NS(korbauszug_delta_m=d["auszug_m"] - AUSZUG_VOLL)))

    def nenn(delta):
        return {"mitte": voll + [0.0, delta, 0.0], "rot": rot_n, "halb": np.array([r, r, h / 2.0])}

    fm = Fehlermodell(nass_ausfall=0.05 if d["nass"] else 0.0)
    mask = None
    t0 = time.monotonic()
    if quelle != "wahr":
        cam1 = WG.ensenso(skala=2.0)
        erk = [e for e in E.erk_laden(erk_pfad, 2) if e["score"] >= schwelle and e["klasse"] == art]
        u, v, _ = cam1.projiziere(np.array([voll + [0.0, d["auszug_m"] - AUSZUG_VOLL, 0.0]]))
        px, py = float(u[0]), float(v[0])
        rad = 0.6 * r * cam1.raster()[2] / max(1e-6, ((voll - cam1.C) @ cam1.R)[2])
        best, bd = None, 1e9
        for e in erk:
            ys, xs = np.nonzero(e["maske"])
            if len(xs) == 0:
                continue
            drin = e["maske"][int(np.clip(py, 0, e["maske"].shape[0] - 1)), int(np.clip(px, 0, e["maske"].shape[1] - 1))]
            dist = 0.0 if drin else float(np.hypot(xs.mean() - px, ys.mean() - py))
            if dist < bd:
                best, bd = e, dist
        if best is not None and bd <= max(rad, 5.0):
            mask = best["maske"]
        else:
            mask = np.zeros((1, 1), bool)
    est = WG.schaetzen(art, w, 0, nenn, seed=seed, prims=prims, fm=fm, skala_ensenso=2.0, skala_d405=1.0,
                       maske_ensenso=mask)
    return {"szene": d["id"], "korb": d["korb"], "licht": d["licht"], "nass": int(d["nass"]), "auszug_m": d["auszug_m"],
            "objekt": o["name"], "klasse": art, "unterklasse": o["unterklasse"], "quelle": quelle, "ok": bool(est["ok"]),
            "gruende": est["gruende"], "fehler_mm": est.get("fehler_mm"),
            "ensenso_mm": est.get("ensenso", {}).get("fehler_mm"), "d405_mm": est.get("d405", {}).get("fehler_mm"),
            "maske_px": est.get("ensenso", {}).get("maske_px"), "s": round(time.monotonic() - t0, 1)}


def tabelle(rows):
    out = ["| Klasse | Quelle | Bedingung | n | Griff freigegeben % | Fehler Median (mm) | P90 (mm) | Abbruchgruende |",
           "|---|---|---|---:|---:|---:|---:|---|"]
    bed = [("alle", lambda r: True), ("trocken", lambda r: not r["nass"]), ("nass", lambda r: r["nass"]),
           ("Licht tag", lambda r: r["licht"] == "tag"), ("Licht kueche", lambda r: r["licht"] == "kueche"),
           ("Licht dunkel", lambda r: r["licht"] == "dunkel"), ("Auszug halb", lambda r: r["auszug_m"] < 0.3),
           ("Auszug voll", lambda r: r["auszug_m"] > 0.3)]
    from collections import Counter
    for klasse in ("glas", "teller"):
        for q in sorted({r["quelle"] for r in rows}):
            for name, f in bed:
                sel = [r for r in rows if r["klasse"] == klasse and r["quelle"] == q and f(r)]
                if not sel:
                    continue
                fe = [r["fehler_mm"] for r in sel if r["ok"] and r["fehler_mm"] is not None]
                gr = Counter(g.split(":")[-1] for r in sel if not r["ok"] for g in (r["gruende"] or ["?"]))
                out.append(f"| {klasse} | {q} | {name} | {len(sel)} | {100 * sum(r['ok'] for r in sel) / len(sel):.0f} | "
                           f"{np.median(fe) if fe else float('nan'):.1f} | {np.percentile(fe, 90) if fe else float('nan'):.1f} | "
                           f"{', '.join(f'{k} {v}' for k, v in gr.most_common(4)) or '-'} |")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("szenen")
    ap.add_argument("render")
    ap.add_argument("erkennung")
    ap.add_argument("--out", required=True)
    ap.add_argument("--quellen", default="wahr,maskrcnn")
    ap.add_argument("--je-szene", type=int, default=3)
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--schwelle", type=float, default=0.5)
    ap.add_argument("--schwelle-baseline", type=float, default=0.6)
    ap.add_argument("--auswerten-nur", action="store_true")
    ap.add_argument("--teller-dicke-mm", type=float, default=None,
                    help="Tellerdicke (Randwulst) in mm statt der Szenendatei (Standard dort 12 mm)")
    ap.add_argument("--klassen", default="glas,teller", help="auszuwertende Klassen (Zielwahl bleibt dieselbe)")
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    jl = out / "lage.jsonl"
    if not a.auswerten_nur:
        szenen = [d for d in json.loads(Path(a.szenen).read_text(encoding="utf-8")) if not d["id"].startswith("t_")]
        fertig = set()
        if jl.is_file():
            for z in jl.read_text().splitlines():
                r = json.loads(z)
                fertig.add((r["szene"], r["objekt"], r["quelle"]))
        jobs = []
        for d in szenen:
            if not (Path(a.render) / f"{d['id']}_inst.npz").is_file():
                continue
            rng = np.random.default_rng(int(d["seed"]) + 5)
            for o in ziele_waehlen(d, a.render, a.je_szene, rng):
                if o["klasse"] not in a.klassen.split(","):
                    continue
                for q in a.quellen.split(","):
                    ep = Path(a.erkennung) / f"{d['id']}_{q}.npz"
                    if (d["id"], o["name"], q) in fertig or (q != "wahr" and not ep.is_file()):
                        continue
                    jobs.append((d, o, q, ep, a.schwelle_baseline if q == "baseline" else a.schwelle, int(d["seed"]) % 1000,
                                 None if a.teller_dicke_mm is None else a.teller_dicke_mm / 1000.0))
        print(len(jobs), "Laeufe", flush=True)
        with ProcessPoolExecutor(a.jobs) as ex, open(jl, "a", encoding="utf-8") as fh:
            for r in ex.map(_lauf, jobs):
                fh.write(json.dumps(r) + "\n")
                fh.flush()
    rows = [json.loads(z) for z in jl.read_text().splitlines()] if jl.is_file() else []
    (out / "lage.md").write_text(tabelle(rows) + "\n", encoding="utf-8")
    print(tabelle(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
