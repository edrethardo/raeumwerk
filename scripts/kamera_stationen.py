#!/usr/bin/env python3
"""Stationssichtbarkeit und Tiefenrauschen je Platz (Ensenso am Mast, Strahlschnitt, ohne Fehlermodell).

Je Objekt (16 Glasplaetze im Oberkorb, Dessertteller im Oberkorb, Teller im Unterkorb) werden
Zielpunkte (Glas: Oeffnung/Boden und Mantel, Teller: Rand und Flaechen) per Strahlschnitt auf
Verdeckung, Bildfeld und Betriebsabstand geprueft. Punkte ausserhalb des Betriebsabstands des Modells
(C57-6-S: 0,75-1,50 m) gelten als nicht gemessen. Ausgabe je Platz: Abstand (Kamerarahmen-z, Mitte und
Bereich), sigma = k z^2, Sichtbarkeit (frei + im Bild + im Bereich), und davon getrennt der Anteil
ohne Bereichsgrenze. Glas wird als Silhouette behandelt (Tiefe ist bei Glas nicht messbar).

    kamera_stationen.py AUSGABE_PREFIX [--kamera c57_6_s|b57_alt] [--pose neu|alt] [--auszug 0.45]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

from spuelmaschine import geometrie as G  # noqa: E402
from spuelmaschine import masse  # noqa: E402
from wahrnehmung import griffpose as WG  # noqa: E402
from wahrnehmung.strahlen import Kamera, Prim, ensenso_modell, schnitt  # noqa: E402

KOPF = np.diag([1.0, -1.0, -1.0])
TELLER_ROT = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0]])
GLAS_R, GLAS_H = 0.0375, 0.110
TELLER_R = 0.095
OBER_TELLER_X = (0.15, 0.45)
OBER_TELLER_TIEFE = (0.07, 0.13, 0.19, 0.25)     # 8 Teller (Aufbau ohne Ueberstand, ``ziele.teller``)
GLAS_REIHEN_X = (0.48, 0.36, 0.24, 0.12)         # 4 Reihen x 4 = 16 Glasplaetze
GLAS_JE_REIHE = 4
UNTER_TELLER_Y = (0.09, 0.15, 0.21)
UNTER_TELLER_X = (0.15, 0.45)


def _prim(k):
    return Prim(k.name, k.gruppe, "zyl" if k.form == "zylinder" else "box",
                np.asarray(k.mitte, float), np.asarray(k.halb, float), np.asarray(k.rot, float), k.name)


def welt(aus_o: float, aus_u: float, was: str):
    """Szene mit Oberkorb ``aus_o`` / Unterkorb ``aus_u`` ausgezogen.

    ``was``: ``ober_glas`` (4 Reihen x 4 = 16 Glasplaetze, Glashalter), ``ober_teller`` (8 Teller in
    zwei Reihen, ohne Glashalter, wie im Aufbau ohne Ueberstand) oder ``unter`` (Unterkorb-Teller)."""
    m = masse.load()
    m["glashalter"] = dict(m["glashalter"], reihen_x_m=list(GLAS_REIHEN_X) if was == "ober_glas" else [],
                           slots_je_reihe=GLAS_JE_REIHE)
    sz = G.baue(m, oberkorb_auszug=aus_o, unterkorb_auszug=aus_u)
    prims = [_prim(k) for k in sz.koerper if k.gruppe not in ("glas",)]
    objekte = []
    ok, uk = sz.m["oberkorb"], sz.m["unterkorb"]
    if was == "ober_glas":
        for i, p in enumerate(sz.slots):
            objekte.append(dict(name=f"glas_{i + 1}", korb="oberkorb", art="glas", c=np.asarray(p, float),
                                r=GLAS_R, h=GLAS_H, rot=KOPF))
    elif was == "ober_teller":
        vorne = ok["vorne_eingeschoben_y_m"] + aus_o
        for j, x in enumerate(OBER_TELLER_X):
            for i, dy in enumerate(OBER_TELLER_TIEFE):
                objekte.append(dict(name=f"oberteller_{j}_{i + 1}", korb="oberkorb", art="teller",
                                    c=np.array([x, vorne - dy, ok["boden_hoehe_m"] + TELLER_R]),
                                    r=TELLER_R, h=0.005, rot=TELLER_ROT))
    else:
        vorne = uk["vorne_eingeschoben_y_m"] + aus_u
        for j, x in enumerate(UNTER_TELLER_X):
            for i, dy in enumerate(UNTER_TELLER_Y):
                objekte.append(dict(name=f"unterteller_{j}_{i + 1}", korb="unterkorb", art="teller",
                                    c=np.array([x, vorne - dy, uk["boden_hoehe_m"] + TELLER_R]),
                                    r=TELLER_R, h=0.005, rot=TELLER_ROT))
    for o in objekte:
        grp = "glas" if o["art"] == "glas" else "teller"
        prims.append(Prim(o["name"], grp, "zyl", o["c"], np.array([o["r"], o["r"], o["h"] / 2]), o["rot"], o["name"]))
    return prims, objekte


def zielpunkte(o):
    c, r, h = o["c"], o["r"], o["h"]
    P = []
    if o["art"] == "glas":
        P.append(c + [0, 0, h / 2 + 0.001])
        for rr in (0.5, 0.85):
            for a in np.linspace(0, 2 * np.pi, 6, endpoint=False):
                P.append(c + [rr * r * math.cos(a), rr * r * math.sin(a), h / 2 + 0.001])
        for a in np.linspace(0, 2 * np.pi, 10, endpoint=False):
            P.append(c + [(r + 0.001) * math.cos(a), (r + 0.001) * math.sin(a), 0.0])
    else:
        dk = o["h"] / 2
        for a in np.radians(np.linspace(-62, 62, 13)):
            P.append(c + (r + 0.001) * np.array([math.sin(a), 0, math.cos(a)]))
        for sy in (-1, 1):
            for (u, v) in ((0, 0.8), (0.5, 0.5), (-0.5, 0.5), (0, 0.3)):
                P.append(c + [u * r, sy * (dk + 0.001), v * r])
    return np.array(P)


def pruefen(prims, cam: Kamera, P: np.ndarray, name: str):
    """(frei+im Bild, im Betriebsabstand, Kamerarahmen-z) je Punkt."""
    u, v, z = cam.projiziere(P)
    h, w, _, _ = cam.raster()
    im = (u >= 0) & (u < w) & (v >= 0) & (v < h) & (z > 0)
    dv = cam.C - P
    dist = np.linalg.norm(dv, axis=1)
    dv = dv / dist[:, None]
    frei = np.ones(len(P), bool)
    for p in prims:
        if p.objekt == name:
            continue
        b = float(np.linalg.norm(p.h)) + 1e-3
        w_ = p.c - P
        s = np.sum(w_ * dv, 1)
        quer2 = np.sum(w_ * w_, 1) - s * s
        sel = np.nonzero((quer2 <= b * b) & (s > -b) & (s < dist + b))[0]
        if len(sel) == 0:
            continue
        t, _ = schnitt(p, P[sel], dv[sel])
        frei[sel[t < dist[sel] - 1e-4]] = False
    m = cam.modell
    bereich = (z >= m["dmin"]) & (z <= m["dmax"])      # Kamerarahmen-z, wie im Sensormodell
    return frei & im, bereich, z


def tabelle(cam: Kamera, auszug: float):
    m = cam.modell
    zeilen = []
    for was, (ao, au) in (("ober_glas", (auszug, 0.0)), ("ober_teller", (auszug, 0.0)), ("unter", (0.0, auszug))):
        prims, objekte = welt(ao, au, was)
        for o in objekte:
            P = zielpunkte(o)
            sicht, bereich, z = pruefen(prims, cam, P, o["name"])
            zc = float(((o["c"] - cam.C) @ cam.R)[2])
            zeilen.append(dict(
                name=o["name"], korb=o["korb"], art=o["art"], z_mitte_m=round(zc, 3),
                z_min_m=round(float(z.min()), 3), z_max_m=round(float(z.max()), 3),
                sigma_mm=round(1e3 * m["sigma_k"] * zc ** 2, 3),
                frei_im_bild_prozent=round(100 * float(sicht.mean()), 1),
                im_bereich_prozent=round(100 * float(bereich.mean()), 1),
                sichtbar_prozent=round(100 * float((sicht & bereich).mean()), 1)))
    return zeilen


def markdown(zeilen, titel):
    out = [f"### {titel}", "", "| Platz | Korb | z Mitte m | z min–max m | σ mm | frei+Bild % | im Bereich % | sichtbar % |",
           "|---|---|---|---|---|---|---|---|"]
    for r in zeilen:
        out.append(f"| {r['name']} | {r['korb']} | {r['z_mitte_m']:.3f} | {r['z_min_m']:.2f}–{r['z_max_m']:.2f} | "
                   f"{r['sigma_mm']:.2f} | {r['frei_im_bild_prozent']:.0f} | {r['im_bereich_prozent']:.0f} | "
                   f"{r['sichtbar_prozent']:.0f} |")
    for gruppe, f in (("Gläser Oberkorb", lambda r: r["art"] == "glas"), ("Teller Oberkorb", lambda r: r["korb"] == "oberkorb" and r["art"] == "teller"),
                      ("Teller Unterkorb", lambda r: r["korb"] == "unterkorb")):
        sel = [r for r in zeilen if f(r)]
        if sel:
            out.append(f"| **{gruppe} (Mittel)** | | {np.mean([r['z_mitte_m'] for r in sel]):.3f} | "
                       f"{min(r['z_min_m'] for r in sel):.2f}–{max(r['z_max_m'] for r in sel):.2f} | "
                       f"{np.mean([r['sigma_mm'] for r in sel]):.2f} | {np.mean([r['frei_im_bild_prozent'] for r in sel]):.0f} | "
                       f"{np.mean([r['im_bereich_prozent'] for r in sel]):.0f} | {np.mean([r['sichtbar_prozent'] for r in sel]):.0f} |")
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("ausgabe", help="Pfad ohne Endung (.json und .md werden geschrieben)")
    ap.add_argument("--kamera", default=None)
    ap.add_argument("--pose", choices=["neu", "alt"], default="neu")
    ap.add_argument("--auszug", type=float, default=0.45, help="Auszug des gezeigten Korbs in m (Mensch zieht je einen)")
    a = ap.parse_args()
    pose = WG.ENSENSO_POSE if a.pose == "neu" else WG.ENSENSO_POSE_ALT
    modell = ensenso_modell(a.kamera)
    cam = Kamera.zielend("ensenso", modell, pose[0], pose[1], skala=4.0)
    zeilen = tabelle(cam, a.auszug)
    titel = (f"{modell['name']}, Mast {tuple(round(v, 2) for v in pose[0])}, Blick auf "
             f"{tuple(round(v, 2) for v in pose[1])}, Bereich {modell['dmin']}–{modell['dmax']} m, "
             f"σ = {1e3 * modell['sigma_k']:.3f} mm·z², Auszug {a.auszug} m")
    p = Path(a.ausgabe)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.with_suffix(".json").write_text(json.dumps({"titel": titel, "zeilen": zeilen}, indent=1, ensure_ascii=False))
    p.with_suffix(".md").write_text(markdown(zeilen, titel))
    print(markdown(zeilen, titel))


if __name__ == "__main__":
    main()
