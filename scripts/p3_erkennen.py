#!/usr/bin/env python3
"""Erkennung auf den Renderbildern eines Laufs (Baseline und/oder Mask R-CNN), Ergebnis als .npz je Bild.

    p3_erkennen.py SZENEN.json RENDERORDNER --out ORDNER [--verfahren baseline,maskrcnn]
                   [--modell DATEI.pth] [--device cuda|cpu] [--ids a,b]

Schreibt ``<id>_baseline.npz`` / ``<id>_maskrcnn.npz`` (Masken im Korb-ROI, siehe ``wahrnehmung.erkennung``) und
``erkennen.json`` (Laufzeiten). Der ROI kommt aus der Korbgeometrie der Szene und der Stationspose, nicht aus dem
Bild. Die Gewichte holt ``scripts/p3_modell_holen.sh``.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from wahrnehmung import erkennung as E  # noqa: E402
from wahrnehmung import griffpose as WG  # noqa: E402


def geometrie_hinweise(d, cam):
    """Erwartete Bildgroessen (px) aus Kamera und Szene: Glasdeckel, Tellerdurchmesser, Glashoehe als Bildvektor."""
    ob = d["objekte"]
    gl = [np.asarray(o["mitte"], float) for o in ob if o["klasse"] == "glas"]
    c = np.mean(gl, 0) if gl else np.array([0.30, 0.15, 0.45])
    q = (c - cam.C) @ cam.R
    f = cam.modell["f"]
    px_glas = 2 * 0.0375 * f / q[2]
    top = c + np.array([0, 0, 0.055])
    bot = c - np.array([0, 0, 0.055])
    u, v, _ = cam.projiziere(np.array([top, bot]))
    hv = (float(u[1] - u[0]), float(v[1] - v[0]))
    tc = np.mean([np.asarray(o["mitte"], float) for o in ob if o["klasse"] == "teller"] or [c], 0)
    zt = ((tc - cam.C) @ cam.R)[2]
    return px_glas, [2 * 0.095 * f / zt, 2 * 0.13 * f / zt], hv


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("szenen")
    ap.add_argument("render")
    ap.add_argument("--out", required=True)
    ap.add_argument("--verfahren", default="baseline,maskrcnn")
    ap.add_argument("--modell", default=None)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--ids", default=None)
    a = ap.parse_args(argv)
    from PIL import Image
    szenen = json.loads(Path(a.szenen).read_text(encoding="utf-8"))
    if a.ids:
        szenen = [s for s in szenen if s["id"] in set(a.ids.split(","))]
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    verf = a.verfahren.split(",")
    modell = E.maskrcnn_laden(a.modell, a.device) if "maskrcnn" in verf else None
    cam = WG.ensenso(skala=1.0)
    zeiten = {}
    for d in szenen:
        rgb_pfad = Path(a.render) / f"{d['id']}_rgb.png"
        if not rgb_pfad.is_file():
            continue
        rgb = np.asarray(Image.open(rgb_pfad).convert("RGB"))
        roi = E.roi_aus_szene(d, cam)
        zt = {}
        if "baseline" in verf:
            t = time.monotonic()
            pg, pt, hv = geometrie_hinweise(d, cam)
            erk = E.baseline(rgb, roi, pg, pt, hv)
            E.erk_speichern(out / f"{d['id']}_baseline.npz", erk, roi, rgb.shape[:2])
            zt["baseline_s"] = round(time.monotonic() - t, 2)
            zt["baseline_n"] = len(erk)
        if modell is not None:
            t = time.monotonic()
            erk = E.maskrcnn(modell, rgb, roi, a.device)
            E.erk_speichern(out / f"{d['id']}_maskrcnn.npz", erk, roi, rgb.shape[:2])
            zt["maskrcnn_s"] = round(time.monotonic() - t, 2)
            zt["maskrcnn_n"] = len(erk)
        zeiten[d["id"]] = zt
        print("ERK", d["id"], zt, flush=True)
    (out / "erkennen.json").write_text(json.dumps(zeiten, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
