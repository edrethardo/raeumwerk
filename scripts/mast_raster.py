#!/usr/bin/env python3
"""Raster der Mastposition (y, z, Neigung) gegen Verdeckung, Auszugszustand und Einfallswinkel.

Je Kameraort werden 9 Szenen gerechnet: Oberkorb-Glaeser, Oberkorb-Teller, Unterkorb-Teller, jeweils mit dem
jeweiligen Korb 0 / 0,225 / 0,45 m ausgezogen (der andere Korb ist drin). Hindernisse: Korbstaebe, Rahmen,
Tuer, Platte (``kamera_stationen.welt``), Kamerakoerper, Mastsaeule + Ausleger, Arm in der Ruhepose. Die
Sichtbarkeit je Platz kommt aus ``wahrnehmung.verdeckung`` (Strahlschnitt je Pixel, Mindestbedingungen der Schaetzer).

    mast_raster.py arm   ROHDATEN                     # Armquader: Ruhepose und Greifposen aus der Basisrechnung
    mast_raster.py raster ROHDATEN [--probe]          # Raster -> ROHDATEN/raster.jsonl (fortsetzbar)
    mast_raster.py auswerten ROHDATEN [--top 20]      # Rangliste je Kennzahl
    mast_raster.py griff ROHDATEN --pos Y Z N [...]   # Arm in Greifpose als Hindernis fuer die gewaehlten Orte
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))
sys.path.insert(0, str(HIER))

import kamera_stationen as KS  # noqa: E402
from wahrnehmung import griffpose as WG  # noqa: E402
from wahrnehmung import verdeckung as V  # noqa: E402
from wahrnehmung.strahlen import ENSENSO, Kamera  # noqa: E402

MAST_X = 0.55
Y_WERTE = (0.30, 0.40, 0.50, 0.60, 0.70)
Z_WERTE = (1.15, 1.225, 1.30, 1.375, 1.45, 1.525, 1.60)
NEIGUNGEN = (50.0, 60.0, 70.0)
AUSZUEGE = (0.0, 0.225, 0.45)
SZENEN = ("ober_glas", "ober_teller", "unter")
RESERVE_M = 0.05
GRUPPEN = (("glas", "ober_glas", 16), ("teller_ober", "ober_teller", 8), ("teller_unter", "unter", 6))
KEEP = ("anteil_im_bild", "anteil_sichtbar", "anteil_gemessen", "brauchbar", "grund", "z_mittel_m", "z_min_m",
        "z_max_m", "sigma_mm", "winkel_median_grad", "anteil_winkel_ok", "brauchbar_flaeche", "punkte_flaeche_s2",
        "anteil_winkel_ok_flaeche", "kontur_wahr_px_s2", "kontur_inlier", "punkte_s2", "kontur_bogen_grad",
        "kontur_bogen_flaeche_grad", "rand_px_s2")
SKALA_RASTER = float(os.environ.get("MAST_SKALA", "4"))
_CACHE: dict = {}
_ARM: dict = {}


def szene(was: str, aus: float):
    k = (was, aus)
    if k not in _CACHE:
        ao, au = (0.0, aus) if was == "unter" else (aus, 0.0)
        _CACHE[k] = KS.welt(ao, au, was)
    return _CACHE[k]


def arm_boxen(p, q):
    """Weltquader (c, R, h) aller Armglieder in Stellung ``q`` (ohne Schiene/Schlitten)."""
    wb = p.self_coll.world_boxes(np.asarray(q, float))
    Rw, tw = p.T[:3, :3], p.T[:3, 3]
    out = []
    for n, boxen in wb.items():
        if n in ("rail", "carriage"):
            continue
        for c, r, h in boxen:
            out.append(dict(link=n, c=(Rw @ np.asarray(c, float) + tw).tolist(), R=(Rw @ np.asarray(r, float)).tolist(),
                            h=np.asarray(h, float).tolist()))
    return out


def korb_bild(prims, cam: Kamera, gruppe: str):
    """Hullquader des Korbs (alle Gitterkoerper der Gruppe) -> Anteil der Ecken im Bild und Bildbereich."""
    lo = np.full(3, np.inf)
    hi = np.full(3, -np.inf)
    for p in prims:
        if p.gruppe != gruppe:
            continue
        ext = np.abs(p.R) @ p.h
        lo, hi = np.minimum(lo, p.c - ext), np.maximum(hi, p.c + ext)
    ecken = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
    u, v, z = cam.projiziere(ecken)
    h, w, _, _ = cam.raster()
    im = (u >= 0) & (u < w) & (v >= 0) & (v < h) & (z > 0)
    return dict(ecken_im_bild=float(im.mean()), u_min=float(u.min() / w), u_max=float(u.max() / w),
                v_min=float(v.min() / h), v_max=float(v.max() / h), box_lo=lo.tolist(), box_hi=hi.tolist())


def rechne_zustand(C, A, was, aus, arm=None, skala=SKALA_RASTER, saeule=True, nur=None):
    prims, objekte = szene(was, aus)
    namen = [o["name"] for o in objekte]
    if nur is not None:
        namen = [n for n in namen if n in nur]
    extra = V.huell_prims(V.kamera_huellen(C, A, saeule=saeule))
    if arm:
        extra += V.arm_prims(arm)
    cam = Kamera.zielend("ensenso", ENSENSO, C, A, skala)
    res = V.sichtbarkeit(prims + extra, cam, namen)
    plaetze = {n: {k: r[k] for k in KEEP if k in r} for n, r in res.items()}
    korb = "unterkorb" if was == "unter" else "oberkorb"
    return dict(was=was, aus=aus, plaetze=plaetze, korb_bild=korb_bild(prims, cam, korb))


def aufgabe(t):
    y, z, n = t
    C, A = WG.ensenso_pose_aus((MAST_X, y, z), n)
    arm = _ARM.get("ruhe")
    t0 = time.monotonic()
    zust = [rechne_zustand(C, A, was, aus, arm) for was in SZENEN for aus in AUSZUEGE]
    return dict(y=y, z=z, neig=n, C=[float(v) for v in C], A=[float(v) for v in A], zustaende=zust,
                sekunden=round(time.monotonic() - t0, 1))


def lade_arm(roh: Path):
    f = roh / "arm_boxen.json"
    if f.is_file():
        _ARM.update(json.loads(f.read_text()))


def cmd_arm(a):
    from spuelmaschine import aufbau as AU
    sys.path.insert(0, str(HIER))
    import mast_gegenprobe as MG
    roh = Path(a.rohdaten)
    A = AU.Aufbau(AU.lade_yaml(MG.BEISPIEL))
    p = A.pruefer(0.0, 0.0)
    ruhe = json.loads((roh / "ruhepose" / "ruhepose.json").read_text())
    print("ruhepose keys", list(ruhe))
    e = json.loads((roh / "basis_ohne_kamera" / "ergebnis.json").read_text())
    out = {"ruhe": arm_boxen(p, ruhe["q"]), "ruhe_q": ruhe["q"], "ziele": {}}
    for g, rows in e["gruppen"].items():
        if g not in ("slots", "teller"):
            continue
        for r in rows:
            if r.get("q") is not None:
                out["ziele"][r["ziel"]] = dict(gruppe=g, ok=bool(r["ok"]), q=r["q"], boxen=arm_boxen(p, r["q"]))
    (roh / "arm_boxen.json").write_text(json.dumps(out))
    print("Armquader Ruhe:", len(out["ruhe"]), "Ziele mit q:", len(out["ziele"]),
          "davon ok:", sum(v["ok"] for v in out["ziele"].values()))
    print("Abdeckung Basis:", json.dumps(e["abdeckung"]))


def cmd_raster(a):
    import multiprocessing as mp
    roh = Path(a.rohdaten)
    lade_arm(roh)
    ys, zs, ns = (Y_WERTE, Z_WERTE, NEIGUNGEN)
    if a.probe:
        ys, zs, ns = (0.50,), (1.35,), (60.0,)
    if a.y:
        ys = tuple(a.y)
    if a.z:
        zs = tuple(a.z)
    if a.neigung:
        ns = tuple(a.neigung)
    ziel = roh / (a.datei or ("raster_probe.jsonl" if a.probe else "raster.jsonl"))
    fertig = set()
    if ziel.is_file():
        for zeile in ziel.read_text().splitlines():
            r = json.loads(zeile)
            fertig.add((r["y"], r["z"], r["neig"]))
    todo = [(y, z, n) for y in ys for z in zs for n in ns if (y, z, n) not in fertig]
    print(f"{len(todo)} Orte zu rechnen, {len(fertig)} fertig; Arm in Ruhe: {'ja' if _ARM.get('ruhe') else 'NEIN'}", flush=True)
    t0 = time.monotonic()
    with open(ziel, "a") as f, mp.get_context("fork").Pool(a.jobs) as pool:
        for i, r in enumerate(pool.imap_unordered(aufgabe, todo, chunksize=1)):
            f.write(json.dumps(r) + "\n")
            f.flush()
            print(f"  {i + 1}/{len(todo)} y={r['y']} z={r['z']} n={r['neig']} {r['sekunden']} s  (gesamt {time.monotonic() - t0:.0f} s)",
                  flush=True)


# --- Auswertung -----------------------------------------------------------------------------------

def nutzbar(name, r, teller_flaeche=True):
    z = r.get("z_mittel_m")
    if z is None or r.get("anteil_sichtbar", 0) <= 0:
        return False
    if not (ENSENSO["dmin"] + RESERVE_M <= z <= ENSENSO["dmax"] - RESERVE_M):
        return False
    if name.startswith("glas"):
        return bool(r["brauchbar"])
    return bool(r["brauchbar_flaeche"] if teller_flaeche else r["brauchbar"])


def kennzahlen(zust, teller_flaeche=True):
    """Je Szene: Zahl nutzbarer Plaetze, mittlere Sichtbarkeit; Teller: Winkelanteile."""
    out = {}
    for g, was, n in GRUPPEN:
        z = next(s for s in zust if s["was"] == was)
        pl = z["plaetze"]
        o = dict(n=len(pl), nutzbar=sum(nutzbar(k, v, teller_flaeche) for k, v in pl.items()),
                 sichtbar_mittel=float(np.mean([v["anteil_sichtbar"] for v in pl.values()])),
                 gemessen_mittel=float(np.mean([v["anteil_gemessen"] for v in pl.values()])),
                 reserve_ok=sum(1 for v in pl.values() if v["z_mittel_m"] is not None and
                                ENSENSO["dmin"] + RESERVE_M <= v["z_mittel_m"] <= ENSENSO["dmax"] - RESERVE_M),
                 im_bild_voll=sum(1 for v in pl.values() if v["anteil_im_bild"] >= 0.999),
                 korb_ecken_im_bild=z["korb_bild"]["ecken_im_bild"])
        if g != "glas":
            o["winkel_unter60"] = sum(1 for v in pl.values() if v["winkel_median_grad"] is not None and v["winkel_median_grad"] < 60.0)
            o["winkel_median_mittel"] = float(np.mean([v["winkel_median_grad"] for v in pl.values() if v["winkel_median_grad"] is not None] or [float("nan")]))
            o["nutzbar_mit_rand"] = sum(nutzbar(k, v, False) for k, v in pl.items())
        out[g] = o
    return out


def punktzahl(rec, auszuege=(0.225, 0.45), teller_flaeche=True):
    s = 0.0
    for aus in auszuege:
        zust = [z for z in rec["zustaende"] if z["aus"] == aus]
        k = kennzahlen(zust, teller_flaeche)
        s += sum(k[g]["nutzbar"] / n for g, _, n in GRUPPEN) / 3.0
    return s / len(auszuege)


def cmd_auswerten(a):
    roh = Path(a.rohdaten)
    recs = [json.loads(z) for z in (roh / (a.datei or "raster.jsonl")).read_text().splitlines()]
    zeilen = []
    for r in recs:
        row = dict(y=r["y"], z=r["z"], neig=r["neig"], punkte=punktzahl(r), punkte_mit_rand=punktzahl(r, teller_flaeche=False))
        for aus in AUSZUEGE:
            k = kennzahlen([z for z in r["zustaende"] if z["aus"] == aus])
            row[f"aus{aus}"] = {g: {kk: (round(vv, 3) if isinstance(vv, float) else vv) for kk, vv in v.items()} for g, v in k.items()}
        zeilen.append(row)
    (roh / (Path(a.datei or "raster.jsonl").stem + "_auswertung.json")).write_text(json.dumps(zeilen, indent=1))
    zeilen.sort(key=lambda r: -r["punkte"])
    print("Rang | y | z | Neigung | Punkte(Flaeche) | mit Rand | je Auszug 0,225/0,45: Glas ok /16, Teller oben ok /8, unten ok /6 | Teller <60 Grad (oben/unten) bei 0,45")
    for i, r in enumerate(zeilen[:a.top]):
        def f(aus):
            k = r[f"aus{aus}"]
            return f"{k['glas']['nutzbar']}/{k['teller_ober']['nutzbar']}/{k['teller_unter']['nutzbar']}"
        k45 = r["aus0.45"]
        print(f"{i + 1:3d} | {r['y']:.2f} | {r['z']:.3f} | {r['neig']:.0f} | {r['punkte']:.3f} | {r['punkte_mit_rand']:.3f} | "
              f"{f(0.225)}  {f(0.45)} | {k45['teller_ober']['winkel_unter60']}/{k45['teller_unter']['winkel_unter60']} | "
              f"Korb im Bild {min(r[f'aus{x}'][g]['korb_ecken_im_bild'] for x in (0.225, 0.45) for g in ('glas', 'teller_unter')):.2f}")


def cmd_detail(a):
    roh = Path(a.rohdaten)
    recs = {(r["y"], r["z"], r["neig"]): r for r in (json.loads(z) for z in (roh / "raster.jsonl").read_text().splitlines())}
    for dat in a.datei or []:
        for z in (roh / dat).read_text().splitlines():
            r = json.loads(z)
            recs[(r["y"], r["z"], r["neig"])] = r
    for i in range(0, len(a.pos), 3):
        key = tuple(a.pos[i:i + 3])
        r = recs[key]
        print(f"== y={key[0]} z={key[1]} Neigung {key[2]}  Kamera {np.round(r['C'], 3).tolist()} Blick auf {np.round(r['A'], 3).tolist()}")
        for aus in AUSZUEGE:
            zust = [z for z in r["zustaende"] if z["aus"] == aus]
            k = kennzahlen(zust)
            for g, was, n in GRUPPEN:
                pl = next(s for s in zust if s["was"] == was)["plaetze"]
                zm = [v["z_mittel_m"] for v in pl.values() if v["z_mittel_m"] is not None]
                zmin = min([v["z_min_m"] for v in pl.values() if v["z_min_m"] is not None] or [float("nan")])
                zmax = max([v["z_max_m"] for v in pl.values() if v["z_max_m"] is not None] or [float("nan")])
                w = [v["winkel_median_grad"] for v in pl.values() if v["winkel_median_grad"] is not None]
                kk = k[g]
                fehl = sorted(name for name, v in pl.items() if not nutzbar(name, v))
                print(f"  Auszug {aus:5.3f} {g:13s} nutzbar {kk['nutzbar']:2d}/{n}  sichtbar {kk['sichtbar_mittel'] * 100:3.0f} %  gemessen {kk['gemessen_mittel'] * 100:3.0f} %  "
                      f"z-Mitte {min(zm) if zm else float('nan'):.2f}-{max(zm) if zm else float('nan'):.2f} (Pixel {zmin:.2f}-{zmax:.2f})  Reserve ok {kk['reserve_ok']}/{n}  voll im Bild {kk['im_bild_voll']}/{n}  "
                      f"Korb-Ecken im Bild {kk['korb_ecken_im_bild']:.2f}  "
                      + (f"Winkel {min(w):.0f}-{max(w):.0f} Grad, <60: {kk['winkel_unter60']}, mit Rand nutzbar {kk['nutzbar_mit_rand']}  " if g != 'glas' and w else "")
                      + ("nicht nutzbar: " + ",".join(x.replace('oberteller_', 'ot').replace('unterteller_', 'ut').replace('glas_', 'g') for x in fehl) if fehl and a.fehlt else ""))


# --- Vorhersagezeilen ---------------------------------------------------------------------------------

def referenzpunkte():
    from spuelmaschine import masse
    m = masse.load()
    prims, _ = szene("ober_glas", 0.45)
    platte = next(p for p in prims if p.objekt == "arbeitsplatte")
    ok, uk = m["oberkorb"], m["unterkorb"]
    return {"R1 Mitte Plattenvorderkante (Oberseite)": np.array([0.30, float((platte.c + platte.h)[1]), float((platte.c + platte.h)[2])]),
            "R2 Mitte Oberkorb-Front am Boden (0,45 m aus)": np.array([0.30, ok["vorne_eingeschoben_y_m"] + 0.45, ok["boden_hoehe_m"]]),
            "R3 Mitte Unterkorb-Front am Boden (0,45 m aus)": np.array([0.30, uk["vorne_eingeschoben_y_m"] + 0.45, uk["boden_hoehe_m"]])}


def cmd_vorhersage(a):
    roh = Path(a.rohdaten)
    recs = [json.loads(z) for z in (roh / a.datei).read_text().splitlines()]
    refs = referenzpunkte()
    md = []
    for r in sorted(recs, key=lambda r: a.reihenfolge.index(f"{r['y']}/{r['z']}/{r['neig']:.0f}") if a.reihenfolge else 0):
        C = np.array(r["C"])
        cam = Kamera.zielend("e", ENSENSO, r["C"], r["A"], 1.0)
        md.append(f"### Mast ({MAST_X:.2f}; {r['y']:.2f}; {r['z']:.3f}) m, Neigung {r['neig']:.0f}°, Blick auf ({r['A'][0]:.2f}; {r['A'][1]:.2f}; {r['A'][2]:.2f}) m")
        md.append("")
        md.append("| Referenzpunkt | Abstand m | Kamerarahmen-z m |")
        md.append("|---|---|---|")
        for n, P in refs.items():
            md.append(f"| {n} | {np.linalg.norm(P - C):.3f} | {float(((P - C) @ cam.R)[2]):.3f} |")
        md.append("")
        md.append("| Auszug | Gruppe | z der Plätze m (Mitte min–max) | Sichtfeld an der mittleren Ebene mm | Korb im Bild (u / v Anteil) | sichtbar % (Mittel) | nutzbar |")
        md.append("|---|---|---|---|---|---|---|")
        for aus in AUSZUEGE:
            zust = [z for z in r["zustaende"] if z["aus"] == aus]
            k = kennzahlen(zust)
            for g, was, n in GRUPPEN:
                z_ = next(s for s in zust if s["was"] == was)
                zm = [v["z_mittel_m"] for v in z_["plaetze"].values() if v["z_mittel_m"] is not None]
                kb = z_["korb_bild"]
                zz = float(np.mean(zm)) if zm else float("nan")
                md.append(f"| {aus:.3f} | {g} | {min(zm):.2f}–{max(zm):.2f} | {zz * 954:.0f} × {zz * 867:.0f} | "
                          f"{kb['u_min']:.2f}–{kb['u_max']:.2f} / {kb['v_min']:.2f}–{kb['v_max']:.2f} | {k[g]['sichtbar_mittel'] * 100:.0f} | {k[g]['nutzbar']}/{n} |")
        md.append("")
        md.append("| Platz | " + " | ".join(f"Auszug {aus:.3f}: sichtbar % / z m / Winkel°" for aus in AUSZUEGE) + " |")
        md.append("|---|---|---|---|")
        for g, was, n in GRUPPEN:
            namen = list(next(s for s in r["zustaende"] if s["was"] == was)["plaetze"])
            for nm in namen:
                zel = []
                for aus in AUSZUEGE:
                    v = next(s for s in r["zustaende"] if s["was"] == was and s["aus"] == aus)["plaetze"][nm]
                    zel.append(f"{v['anteil_sichtbar'] * 100:.0f}{'' if nutzbar(nm, v) else ' ✗'} / "
                               f"{'–' if v['z_mittel_m'] is None else format(v['z_mittel_m'], '.2f')} / "
                               f"{'–' if v['winkel_median_grad'] is None else format(v['winkel_median_grad'], '.0f')}")
                md.append(f"| {nm} | " + " | ".join(zel) + " |")
        md.append("")
    (roh / a.ausgabe).write_text("\n".join(md))
    print("\n".join(md[:30]))


# --- Arm in Greifpose --------------------------------------------------------------------------------

def teller_namen():
    return [f"oberteller_{j}_{i + 1}" for j in range(2) for i in range(4)]


def cmd_griff(a):
    roh = Path(a.rohdaten)
    lade_arm(roh)
    arm = _ARM
    pos = [tuple(a.pos[i:i + 3]) for i in range(0, len(a.pos), 3)]
    skala = a.skala
    out = []
    for (y, z, n) in pos:
        C, A = WG.ensenso_pose_aus((MAST_X, y, z), n)
        rec = dict(y=y, z=z, neig=n, szenen={})
        for was in ("ober_glas", "ober_teller"):
            aus = 0.45
            alle = [o["name"] for o in szene(was, aus)[1]]
            ruhe = rechne_zustand(C, A, was, aus, arm["ruhe"], skala)
            basis_ok = {k: nutzbar(k, v) for k, v in ruhe["plaetze"].items()}
            zeilen = []
            for zname, zd in arm["ziele"].items():
                if (was == "ober_glas") != (zd["gruppe"] == "slots"):
                    continue
                if was == "ober_glas":
                    obj = f"glas_{int(zname.split('_')[1])}"
                else:
                    idx = list(arm["ziele"]).index(zname) - sum(1 for v in arm["ziele"].values() if v["gruppe"] == "slots")
                    obj = teller_namen()[idx]
                z_ = rechne_zustand(C, A, was, aus, zd["boxen"], skala)
                nz = {k: nutzbar(k, v) for k, v in z_["plaetze"].items()}
                andere = [k for k in alle if k != obj]
                verloren = [k for k in andere if basis_ok[k] and not nz[k]]
                zeilen.append(dict(ziel=zname, objekt=obj, erreicht=zd["ok"], eigen_nutzbar=nz[obj],
                                   andere_nutzbar=sum(nz[k] for k in andere), andere_vorher=sum(basis_ok[k] for k in andere),
                                   verloren=verloren))
            rec["szenen"][was] = dict(ruhe_nutzbar=sum(basis_ok.values()), n=len(basis_ok), ziele=zeilen)
            print(f"y={y} z={z} n={n} {was}: Ruhe {sum(basis_ok.values())}/{len(basis_ok)}; Greifposen:",
                  [(r['objekt'], r['andere_nutzbar'], r['andere_vorher'], r['eigen_nutzbar']) for r in zeilen], flush=True)
        out.append(rec)
    (roh / a.datei).write_text(json.dumps(out, indent=1))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("arm")
    s.add_argument("rohdaten")
    s = sp.add_parser("raster")
    s.add_argument("rohdaten")
    s.add_argument("--probe", action="store_true")
    s.add_argument("--jobs", type=int, default=6)
    s.add_argument("--y", type=float, nargs="*")
    s.add_argument("--z", type=float, nargs="*")
    s.add_argument("--neigung", type=float, nargs="*")
    s.add_argument("--datei", default=None)
    s = sp.add_parser("auswerten")
    s.add_argument("rohdaten")
    s.add_argument("--top", type=int, default=20)
    s.add_argument("--datei", default=None)
    s = sp.add_parser("detail")
    s.add_argument("rohdaten")
    s.add_argument("--pos", type=float, nargs="+", required=True)
    s.add_argument("--datei", nargs="*")
    s.add_argument("--fehlt", action="store_true")
    s = sp.add_parser("vorhersage")
    s.add_argument("rohdaten")
    s.add_argument("--datei", default="final.jsonl")
    s.add_argument("--ausgabe", default="vorhersage.md")
    s.add_argument("--reihenfolge", nargs="*", default=None, help="y/z/neig, z. B. 0.7/1.25/55")
    s = sp.add_parser("griff")
    s.add_argument("rohdaten")
    s.add_argument("--pos", type=float, nargs="+", required=True)
    s.add_argument("--skala", type=float, default=2.0)
    s.add_argument("--datei", default="griff.json")
    a = ap.parse_args()
    {"arm": cmd_arm, "raster": cmd_raster, "auswerten": cmd_auswerten, "griff": cmd_griff, "detail": cmd_detail,
     "vorhersage": cmd_vorhersage}[a.cmd](a)


if __name__ == "__main__":
    main()
