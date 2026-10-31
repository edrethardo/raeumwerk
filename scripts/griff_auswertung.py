#!/usr/bin/env python3
"""Auswertung der Griff-Laeufe: Wahrnehmung allein (AUSGABE/wahrnehmung/*.json aus
scripts/griff_wahrnehmung.py --alle) und Newton-Laeufe (AUSGABE/<reihe>-<seed>/versuch.json aus
scripts/griff_lauf.py bzw. scripts/griff_serie.sh). Druckt die Markdown-Tabellen von
docs/griff-verrauscht.md und schreibt AUSGABE/zusammenfassung.json.

    griff_auswertung.py AUSGABE
"""
from __future__ import annotations

import argparse
import json
import statistics as st
from pathlib import Path


def lade(p):
    try:
        return json.loads(Path(p).read_text())
    except Exception:  # noqa: BLE001
        return None


def mittel_max(xs, d=1):
    xs = [x for x in xs if x is not None]
    if not xs:
        return "–"
    return f"{st.mean(xs):.{d}f} / {max(xs):.{d}f}"


def spanne(xs, d=1):
    xs = [x for x in xs if x is not None]
    if not xs:
        return "–"
    return f"{min(xs):.{d}f}–{max(xs):.{d}f}"


def f(x, d=1):
    return "–" if x is None else f"{x:.{d}f}"


def mm(b, k):
    return 1e3 * b[k] if b.get(k) is not None else None


def wahrnehmung(o, out):
    print("## Wahrnehmung allein (Fehler gegen die Wahrheit, mm Mittel / Max)\n")
    print("| Objekt | Negativtest | angenommen | Ensenso | D405 | Griffpose (angenommen) | Gruende (Ablehnung) |")
    print("|---|---|---|---|---|---|---|")
    for p in sorted((o / "wahrnehmung").glob("*.json")):
        k = [r["kurz"] for r in (lade(p) or [])]
        art, _, neg = p.stem.partition("-")
        ok = sum(1 for r in k if r["ok"])
        gr = sorted({g for r in k for g in r["gruende"]})
        print(f"| {art} | {neg or '–'} | {ok}/{len(k)} | {mittel_max([r['ensenso_mm'] for r in k])} | "
              f"{mittel_max([r['d405_mm'] for r in k])} | {mittel_max([r['fehler_mm'] for r in k if r['ok']])} | "
              f"{', '.join(gr) or '–'} |")
        out[f"wahrnehmung_{p.stem}"] = {"angenommen": ok, "n": len(k), "zeilen": k}


def laeufe(o, out):
    reihen = {}
    for p in sorted(o.glob("*/versuch.json")):
        v = lade(p)
        n = p.parent.name
        if not v or "-" not in n:
            continue
        reihe, _, seed = n.rpartition("-")
        b = v.get("bewertung") or {}
        wn = v.get("wahrnehmung") or {}
        gv = b.get("griffversatz_xy_m")
        z = {"lauf": n, "seed": int(seed) if seed.isdigit() else seed, "voll": bool(v["args"].get("voll")),
             "variante": (v.get("variante") or {}).get("name", "–"), "erfolg": v.get("erfolg"),
             "abgebrochen": v.get("abgebrochen", False), "fehler": "fehler" in v,
             "gruende": b.get("gruende") if b else wn.get("gruende"),
             "wahrnehmung_mm": wn.get("fehler_mm"), "aushub_mm": mm(b, "aushub_m"), "hand_mm": mm(b, "hand_wanderung_m"),
             "kipp_hand": b.get("kippung_in_hand_grad"), "kipp_ende": b.get("kippung_end_grad"),
             "ziel_mm": mm(b, "zielfehler_xy_m"), "versatz_mm": 1e3 * (gv[0] ** 2 + gv[1] ** 2) ** 0.5 if gv else None,
             "nachbar_mm": mm(b, "nachbar_max_m"), "finger_mm": mm(b, "finger_durchdringung_m"),
             "finger_phase": b.get("finger_durchdringung_phase"), "wand_s": v.get("wand_gesamt_s"), "device": v.get("device")}
        reihen.setdefault(reihe, []).append(z)
    out["laeufe"] = reihen
    for reihe, zs in sorted(reihen.items()):
        zs.sort(key=lambda z: (str(type(z["seed"])), z["seed"]))
        voll = all(z["voll"] for z in zs)
        print(f"\n## Reihe `{reihe}` ({'voller Ablauf' if voll else 'Kurzlauf'}, Variante {zs[0]['variante']})\n")
        if voll:
            print("| Seed | Wahrn. mm | Erfolg | Gruende | Zielfehler mm | Kippung Ende ° | Aushub mm | Hand mm | Nachbar mm | Finger mm | Wand s |")
            print("|---|---|---|---|---|---|---|---|---|---|---|")
        else:
            print("| Seed | Wahrn. mm | Erfolg | Gruende | Aushub mm | Hand mm | Kippung in der Hand ° | Griffversatz mm | Nachbar mm | Finger mm | Wand s |")
            print("|---|---|---|---|---|---|---|---|---|---|---|")
        for z in zs:
            erf = "abgebrochen" if z["abgebrochen"] else ("Absturz Skript" if z["fehler"] else ("ja" if z["erfolg"] else "nein"))
            gr = ", ".join(z["gruende"] or []) or "–"
            if voll:
                print(f"| {z['seed']} | {f(z['wahrnehmung_mm'])} | {erf} | {gr} | {f(z['ziel_mm'])} | {f(z['kipp_ende'])} | "
                      f"{f(z['aushub_mm'], 0)} | {f(z['hand_mm'])} | {f(z['nachbar_mm'])} | {f(z['finger_mm'])} | {f(z['wand_s'], 0)} |")
            else:
                print(f"| {z['seed']} | {f(z['wahrnehmung_mm'])} | {erf} | {gr} | {f(z['aushub_mm'], 0)} | {f(z['hand_mm'])} | "
                      f"{f(z['kipp_hand'])} | {f(z['versatz_mm'])} | {f(z['nachbar_mm'])} | {f(z['finger_mm'])} | {f(z['wand_s'], 0)} |")
        ok = sum(1 for z in zs if z["erfolg"])
        ab = sum(1 for z in zs if z["abgebrochen"])
        r = [z for z in zs if not z["abgebrochen"]]
        teil = [f"Wahrnehmung {spanne([z['wahrnehmung_mm'] for z in zs])} mm"]
        if voll:
            teil += [f"Zielfehler {spanne([z['ziel_mm'] for z in r])} mm", f"Kippung Ende {spanne([z['kipp_ende'] for z in r])} °"]
        else:
            teil += [f"Kippung in der Hand {spanne([z['kipp_hand'] for z in r])} °"]
        teil += [f"Hand {spanne([z['hand_mm'] for z in r])} mm", f"Nachbarn {spanne([z['nachbar_mm'] for z in r])} mm",
                 f"Finger {spanne([z['finger_mm'] for z in r])} mm"]
        print(f"\n**{reihe}: {ok}/{len(zs)} erfolgreich** ({ab} Abbruch der Wahrnehmung) · " + " · ".join(teil))
        out[f"quote_{reihe}"] = {"erfolg": ok, "n": len(zs), "abgebrochen": ab}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("ausgabe")
    a = ap.parse_args()
    o = Path(a.ausgabe)
    out = {}
    if (o / "wahrnehmung").is_dir():
        wahrnehmung(o, out)
    laeufe(o, out)
    (o / "zusammenfassung.json").write_text(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
