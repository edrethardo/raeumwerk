#!/usr/bin/env python3
"""Auswertung der Erkennung gegen die Instanzkarten (Kameratag P3): Tabellen je Klasse und Bedingung, Montage.

    p3_auswertung.py SZENEN.json RENDERORDNER ERKENNUNGSORDNER --out ORDNER
                     [--verfahren baseline,maskrcnn] [--schwelle 0.5] [--tuning-einschliessen]

Schreibt ``objekte_<verfahren>.csv`` (eine Zeile je sichtbarem Objekt), ``tabelle_<verfahren>.md`` (Treffer, IoU,
Verwechslung, Nachbar, Verpasst, Fehldetektionen je Klasse und Bedingung, mit Wilson-95-%-Intervall) und
``montage_<verfahren>.jpg`` (schwierigste Faelle: kleinste IoU). Szenen mit Praefix ``t_`` (Tuning der
Baseline) zaehlen nicht mit. Definitionen: ``wahrnehmung/erkennung.py``.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from wahrnehmung import erkennung as E  # noqa: E402

FAKTOR = 4          # Auswertung auf jedem 4. Pixel (IoU-Fehler < 1 %), 16x schneller


def wilson(k: int, n: int, z: float = 1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def zeilen(szenen, render, erk_dir, verfahren, schwelle, tuning):
    rows, fehl = [], []
    for d in szenen:
        if d["id"].startswith("t_") and not tuning:
            continue
        ip = Path(render) / f"{d['id']}_inst.npz"
        ep = Path(erk_dir) / f"{d['id']}_{verfahren}.npz"
        if not ip.is_file() or not ep.is_file():
            continue
        z = np.load(ip)
        inst, namen = z["inst"][::FAKTOR, ::FAKTOR], [str(n) for n in z["namen"]]
        klassen = {o["name"]: o["klasse"] for o in d["objekte"]}
        unter = {o["name"]: o["unterklasse"] for o in d["objekte"]}
        erk = E.erk_laden(ep, FAKTOR)
        b = E.bewerten(inst, namen, klassen, erk, schwelle=schwelle, min_px=E.MIN_PX // (FAKTOR * FAKTOR))
        for n, r in b["objekte"].items():
            rows.append({"szene": d["id"], "korb": d["korb"], "licht": d["licht"], "nass": int(d["nass"]),
                         "auszug_m": d["auszug_m"], "objekt": n, "unterklasse": unter[n], **r})
        for f in b["fehldetektionen"]:
            fehl.append({"szene": d["id"], "korb": d["korb"], "licht": d["licht"], "nass": int(d["nass"]),
                         "auszug_m": d["auszug_m"], **f})
        rows.append({"szene": d["id"], "korb": d["korb"], "licht": d["licht"], "nass": int(d["nass"]),
                     "auszug_m": d["auszug_m"], "objekt": "_bild", "unterklasse": "", "klasse": "_bild",
                     "px": 0, "iou": 0.0, "treffer": False, "klassenfrei": False, "klassenfehler": False,
                     "nachbar": False, "ungenau": False, "verpasst": False, "best_iou": 0.0})
    return rows, fehl


def tabelle(rows, fehl, titel):
    bilder = [r for r in rows if r["objekt"] == "_bild"]
    obj = [r for r in rows if r["objekt"] != "_bild"]
    gruppen = [("alle", lambda r: True)]
    for k in ("ober", "unter"):
        gruppen.append((f"Korb {k}", lambda r, k=k: r["korb"] == k))
    for nv in (0, 1):
        gruppen.append(("nass" if nv else "trocken", lambda r, nv=nv: r["nass"] == nv))
    for li in ("tag", "kueche", "dunkel"):
        gruppen.append((f"Licht {li}", lambda r, li=li: r["licht"] == li))
    for a in (0.225, 0.45):
        gruppen.append((f"Auszug {'halb' if a < 0.3 else 'voll'}", lambda r, a=a: abs(r["auszug_m"] - a) < 1e-6))
    out = [f"### {titel}", "",
           "| Klasse | Bedingung | n sichtbar | Treffer % (95 %-Intervall) | klassenfrei % | IoU Treffer (Median) | IoU alle (Mittel) | Klassenfehler % | Nachbar % | ungenau % | verpasst % | Fehldet./Bild |",
           "|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for klasse in ("glas", "teller", "alle"):
        for gname, f in gruppen:
            sel = [r for r in obj if f(r) and (klasse == "alle" or r["klasse"] == klasse)]
            n = len(sel)
            if n == 0:
                continue
            k = sum(r["treffer"] for r in sel)
            lo, hi = wilson(k, n)
            ious_t = [r["iou"] for r in sel if r["treffer"]]
            iou_all = np.mean([r["iou"] if (r["treffer"] or r["klassenfrei"]) else 0.0 for r in sel])
            sz = {r["szene"] for r in bilder if f(r)}
            nf = sum(1 for x in fehl if x["szene"] in sz and (klasse == "alle" or x["klasse"] == klasse))
            out.append(f"| {klasse} | {gname} | {n} | {100 * k / n:.0f} ({100 * lo:.0f}-{100 * hi:.0f}) | "
                       f"{100 * sum(r['klassenfrei'] for r in sel) / n:.0f} | "
                       f"{np.median(ious_t) if ious_t else float('nan'):.2f} | {iou_all:.2f} | "
                       f"{100 * sum(r['klassenfehler'] for r in sel) / n:.0f} | {100 * sum(r['nachbar'] for r in sel) / n:.0f} | "
                       f"{100 * sum(r['ungenau'] for r in sel) / n:.0f} | {100 * sum(r['verpasst'] for r in sel) / n:.0f} | "
                       f"{nf / max(1, len(sz)):.1f} |")
    return "\n".join(out)


def montage(rows, szenen, render, erk_dir, verfahren, schwelle, pfad, n=8):
    import cv2
    from PIL import Image
    obj = [r for r in rows if r["objekt"] != "_bild"]
    schlecht = sorted(obj, key=lambda r: (r["iou"] if r["treffer"] else r["best_iou"] * 0.5, -r["px"]))[:n]
    S = {d["id"]: d for d in szenen}
    kacheln = []
    for r in schlecht:
        d = S[r["szene"]]
        rgb = np.asarray(Image.open(Path(render) / f"{d['id']}_rgb.png").convert("RGB")).copy()
        z = np.load(Path(render) / f"{d['id']}_inst.npz")
        namen = [str(x) for x in z["namen"]]
        gt = z["inst"] == namen.index(r["objekt"]) + 1
        erk = [e for e in E.erk_laden(Path(erk_dir) / f"{d['id']}_{verfahren}.npz") if e["score"] >= schwelle]
        ys, xs = np.nonzero(gt)
        y0, y1, x0, x1 = max(0, ys.min() - 80), ys.max() + 80, max(0, xs.min() - 80), xs.max() + 80
        for e in erk:
            if (e["maske"][y0:y1, x0:x1]).any():
                c, _ = cv2.findContours(e["maske"].astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                cv2.drawContours(rgb, c, -1, (255, 40, 40) if e["klasse"] == "glas" else (255, 160, 0), 4)
        c, _ = cv2.findContours(gt.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(rgb, c, -1, (0, 230, 0), 4)
        kach = cv2.resize(rgb[y0:y1, x0:x1], (360, int(360 * (y1 - y0) / max(1, x1 - x0))))
        kach = cv2.copyMakeBorder(kach, 0, 40, 0, 0, cv2.BORDER_CONSTANT, value=(30, 30, 30))
        txt = f"{r['szene']} {r['objekt']} {r['licht']} {'nass' if r['nass'] else 'trk'} IoU {r['iou'] if r['klassenfrei'] else r['best_iou']:.2f}"
        cv2.putText(kach, txt, (4, kach.shape[0] - 14), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1, cv2.LINE_AA)
        kacheln.append(kach)
    if not kacheln:
        return
    hmax = max(k.shape[0] for k in kacheln)
    kacheln = [cv2.copyMakeBorder(k, 0, hmax - k.shape[0], 0, 0, cv2.BORDER_CONSTANT, value=(30, 30, 30)) for k in kacheln]
    cols = 4
    zeilen_ = [np.hstack(kacheln[i:i + cols] + [np.zeros_like(kacheln[0])] * (cols - len(kacheln[i:i + cols])))
               for i in range(0, len(kacheln), cols)]
    Image.fromarray(np.vstack(zeilen_)).save(pfad, quality=88)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("szenen")
    ap.add_argument("render")
    ap.add_argument("erkennung")
    ap.add_argument("--out", required=True)
    ap.add_argument("--verfahren", default="baseline,maskrcnn")
    ap.add_argument("--schwelle", type=float, default=0.5)
    ap.add_argument("--schwelle-baseline", type=float, default=0.0)
    ap.add_argument("--tuning-einschliessen", action="store_true")
    ap.add_argument("--ohne-montage", action="store_true")
    a = ap.parse_args(argv)
    szenen = json.loads(Path(a.szenen).read_text(encoding="utf-8"))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    md = []
    for v in a.verfahren.split(","):
        sw = a.schwelle_baseline if v == "baseline" else a.schwelle
        rows, fehl = zeilen(szenen, a.render, a.erkennung, v, sw, a.tuning_einschliessen)
        if not rows:
            print(v, "keine Daten")
            continue
        with open(out / f"objekte_{v}.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        (out / f"fehldetektionen_{v}.json").write_text(json.dumps(fehl, indent=1), encoding="utf-8")
        t = tabelle(rows, fehl, f"{v} (Score >= {sw})")
        (out / f"tabelle_{v}.md").write_text(t + "\n", encoding="utf-8")
        if not a.ohne_montage:
            montage(rows, szenen, a.render, a.erkennung, v, sw, out / f"montage_{v}.jpg")
        md.append(t)
        print(t)
    (out / "tabellen.md").write_text("\n\n".join(md) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
