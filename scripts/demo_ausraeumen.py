#!/usr/bin/env python3
"""Ausraeumen in Newton: 4 Glaeser kopfueber aus dem Oberkorb, umdrehen, aufrecht abstellen.

Gestartet von ``scripts/run_ausraeumen.sh`` (Python mit Newton 1.6). Rein
headless, keine Netzwerkschnittstelle. Auf einem geteilten GPU-Rechner nur
ueber die GPU-Warteschlange. Der Variationslauf geht ueber ``raeumwerk run``
(``experimente/ausraeumen_variation.yaml``, Backend ``ausraeumen``).

    demo_ausraeumen.py --art demo|negativ --out DIR [--device cpu]
                       [--glaeser N] [--aufzeichnen DATEI.npz] [--nur-plan]

* ``demo``     Nennlage (fester Seed), alle 4 Glaeser in Folge
* ``negativ``  Glas ``negativtest.glas`` steckt in einem zu schmalen Halter
               (Klemmbacken mit Uebermass, der Planung unbekannt); muss als
               Fehlversuch mit Grund ``nicht_aus_dem_korb`` erkannt werden

Ausgabe in ``--out``: ``versuch-00.json`` (Bewertung je Glas, Messwerte,
Plan), ``zusammenfassung.json``. Exit 0, wenn die Erwartung erfuellt ist
(demo: alle Glaeser Erfolg; negativ: Klemmglas als Fehlversuch mit
``nicht_aus_dem_korb`` erkannt; --nur-plan: Plan gefunden).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def drucken(nr: int, rec: dict) -> None:
    b = rec.get("bewertung", {})
    print("VERSUCH", json.dumps({"nr": nr, "erfolg": rec.get("erfolg"), "erfolge": b.get("erfolge"),
                                 "glaeser": {g["glas"]: g["gruende"] for g in b.get("glaeser", [])},
                                 "plan_ok": rec.get("plan", {}).get("ok"), "plan_s": rec.get("plan", {}).get("dauer_s"),
                                 "wand_s": rec.get("wand_gesamt_s")}, ensure_ascii=False), flush=True)
    for g in b.get("glaeser", []):
        w = g.get("werte", {})
        if w:
            print(f"  {g['glas']}: erfolg={g['erfolg']} zielfehler={w['zielfehler_xy_m'] * 1e3:.2f} mm "
                  f"kippung={w['kippung_end_grad']:.2f} Grad (start {w['kippung_start_grad']:.1f}) "
                  f"aushub={w['aushub_m'] * 1e3:.0f} mm kontakte_mm={ {k: round(v * 1e3, 3) for k, v in w['kontakte_m'].items()} } "
                  f"nachbar={w['nachbar_max_m'] * 1e3:.2f} mm", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--art", choices=["demo", "negativ"], default="demo")
    ap.add_argument("--out", required=True)
    ap.add_argument("--device", default=None)
    ap.add_argument("--glaeser", type=int, default=None, help="nur die ersten N Glaeser der Zuordnung")
    ap.add_argument("--aufzeichnen", default=None, metavar="DATEI.npz",
                    help="Posen aller Koerper (30 Bilder je Simsekunde) fuer scripts/render_ausraeumen.py")
    ap.add_argument("--nur-plan", action="store_true", help="nur planen (ohne Newton)")
    ap.add_argument("--set", action="append", default=[], metavar="ABSCHNITT.WERT=JSON",
                    help="Wert aus config/ausraeumen.yaml ueberschreiben (zum Ausprobieren)")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    meta: dict = {"art": args.art, "ok": False, "glaeser": args.glaeser}
    t0 = time.monotonic()
    try:
        from ausraeumen import ablauf, konfig
        from rebel_model.config import load

        a = konfig.setze(konfig.load(), args.set)
        cfg, urdf, chain = ablauf.roboter(load(), a)
        meta["finger_breite_m"] = cfg.greifer["finger_breite_m"]
        ctx = None
        if not args.nur_plan:
            from ausraeumen import sim_newton as sn
            ctx = sn.kontext(args.device)
            meta.update({"device": ctx["device"], "versionen": sn.versionen()})
        k = int(a["negativtest"]["glas"])
        abw = konfig.Abweichung(verklemmt=k) if args.art == "negativ" else konfig.Abweichung()
        rec, _ = ablauf.versuch(0, args.art, abw, ctx, cfg, chain, urdf, None, args.glaeser, args.aufzeichnen,
                                args.nur_plan, args.set)
        rec["wand_gesamt_s"] = round(time.monotonic() - t0, 1)
        (out / "versuch-00.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1))
        drucken(0, rec)
        if args.nur_plan:
            meta["ok"] = bool(rec["plan"]["ok"])
        elif args.art == "demo":
            meta["ok"] = bool(rec["erfolg"])
        else:
            g = [g for g in rec["bewertung"]["glaeser"] if g["glas"] == f"glas_{k}"]
            meta["ok"] = bool(g and not g[0]["erfolg"] and "nicht_aus_dem_korb" in g[0]["gruende"])
        meta["erfolge"] = rec.get("bewertung", {}).get("erfolge")
    except Exception:  # noqa: BLE001
        meta["fehler"] = traceback.format_exc()
        print(meta["fehler"], file=sys.stderr)
    meta["wand_s"] = round(time.monotonic() - t0, 1)
    (out / "zusammenfassung.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1, default=str))
    print("AUSRAEUMEN_RESULT", json.dumps({k_: meta.get(k_) for k_ in ("art", "ok", "erfolge", "wand_s", "device")}),
          flush=True)
    return 0 if meta["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
