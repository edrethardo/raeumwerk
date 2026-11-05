#!/usr/bin/env python3
"""Punktabdeckung je Objekt (Vorhersagezeile 5, Kameratag P3) aus dem Strahlschnitt-Simulator.

    p3_abdeckung.py SZENEN.json --out ORDNER [--skala 3] [--jobs 2]

Je Szene (ohne Tuning) einmal ``sensor.aufnehmen`` mit der Ensenso-C57-6-S-Pose und dem Fehlermodell
(``nass`` = Standard mit 5 % Ausfall auf nassen Flaechen, ``trocken`` = ohne); je sichtbarem Objekt der Anteil
der Pixel mit gueltigem Tiefenwert. Das ist das ANGENOMMENE Fehlermodell (``wahrnehmung/sensor.py``), keine
Messung und kein Isaac-Tiefenbild: RTX bildet weder das Projektormuster noch das Stereo-Matching nach.
Ausgabe: ``abdeckung.csv`` (je Objekt) und ``abdeckung.md`` (Median, P10-P90, Bootstrap-95-%-Intervall des Mittels).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from wahrnehmung import griffpose as WG  # noqa: E402
from wahrnehmung import p3_szenen as P3  # noqa: E402
from wahrnehmung.sensor import Fehlermodell, aufnehmen  # noqa: E402


def _szene(args):
    d, skala = args
    rows = []
    prims = P3.prims_aus_szene(d)
    cam = WG.ensenso(skala=skala)
    for nass in (False, True):
        fm = Fehlermodell(nass_ausfall=0.05 if nass else 0.0)
        auf = aufnehmen(prims, cam, np.random.default_rng(int(d["seed"]) + 11), fm)
        for o in d["objekte"]:
            m = auf.maske_wahr(o["name"]).ravel()
            n = int(m.sum())
            if n < 150:
                continue
            gueltig = float(np.isfinite(auf.mess[m]).mean())
            rows.append({"szene": d["id"], "korb": d["korb"], "licht": d["licht"], "nass_szene": int(d["nass"]),
                         "fehlermodell": "nass" if nass else "trocken", "objekt": o["name"], "klasse": o["klasse"],
                         "unterklasse": o["unterklasse"], "pixel": n, "abdeckung": gueltig})
    return rows


def boot(x, rng, n=2000):
    x = np.asarray(x, float)
    m = [rng.choice(x, len(x)).mean() for _ in range(n)]
    return np.percentile(m, [2.5, 97.5])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("szenen")
    ap.add_argument("--out", required=True)
    ap.add_argument("--skala", type=float, default=3.0)
    ap.add_argument("--jobs", type=int, default=2)
    a = ap.parse_args(argv)
    szenen = [d for d in json.loads(Path(a.szenen).read_text(encoding="utf-8")) if not d["id"].startswith("t_")]
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    with ProcessPoolExecutor(a.jobs) as ex:
        for r in ex.map(_szene, [(d, a.skala) for d in szenen]):
            rows += r
    with open(out / "abdeckung.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    rng = np.random.default_rng(0)
    md = ["| Klasse | Fehlermodell | n Objekte | Abdeckung Median | P10 | P90 | Mittel (Bootstrap-95-%) |", "|---|---|---:|---:|---:|---:|---|"]
    for k in ("glas", "teller"):
        for fmn in ("trocken", "nass"):
            x = [r["abdeckung"] for r in rows if r["klasse"] == k and r["fehlermodell"] == fmn]
            if not x:
                continue
            lo, hi = boot(x, rng)
            md.append(f"| {k} | {fmn} | {len(x)} | {100 * np.median(x):.0f} % | {100 * np.percentile(x, 10):.0f} % | "
                      f"{100 * np.percentile(x, 90):.0f} % | {100 * np.mean(x):.0f} % ({100 * lo:.0f}-{100 * hi:.0f}) |")
    (out / "abdeckung.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
