#!/usr/bin/env python3
"""Greifen mit den eigenen 100-mm-Fingern im Aufbau A1-S1 (Newton, headless).

Gestartet von ``scripts/run_finger_a1.sh``. Keine Netzwerkschnittstelle.

    demo_finger_a1.py --art glaeser|teller --out DIR [--device cpu] [--nur-plan]
                      [--objekte N] [--zuordnung 1:3,2:4] [--variation SEED]
                      [--negativ K] [--aufzeichnen DATEI.npz]

* ``--variation SEED``  Lage je Objekt +-5 mm / +-3 Grad, Korbauszug +-1 cm (gewuerfelt)
* ``--negativ K``       Objekt K (1-basiert) steckt zwischen Klemmbacken mit Uebermass, der
                        Planung unbekannt; muss als Fehlversuch ``nicht_aus_dem_korb`` erkannt werden
* ``--zuordnung``       nur diese Paare Objekt:Ablage (Teilauftrag, Rest bleibt im Korb)

Ausgabe: ``versuch.json`` und eine Zeile ``FINGER_RESULT`` (Exit 0, wenn die Erwartung erfuellt ist).
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


def drucken(rec: dict) -> None:
    b = rec.get("bewertung", {})
    print("VERSUCH", json.dumps({"erfolg": rec.get("erfolg"), "erfolge": b.get("erfolge"),
                                 "objekte": {g["glas"]: g["gruende"] for g in b.get("glaeser", [])},
                                 "plan_ok": rec.get("plan", {}).get("ok"), "plan_s": rec.get("plan", {}).get("dauer_s"),
                                 "plan_fehler": rec.get("plan", {}).get("fehler"),
                                 "wand_s": rec.get("wand_gesamt_s")}, ensure_ascii=False), flush=True)
    for g in b.get("glaeser", []):
        w = g.get("werte", {})
        if w:
            fd = g["kriterien"]["durchdringung"]["wert"]
            print(f"  {g['glas']}: erfolg={g['erfolg']} zielfehler={w['zielfehler_xy_m'] * 1e3:.2f} mm "
                  f"kippung={w['kippung_end_grad']:.2f} Grad (start {w['kippung_start_grad']:.1f}) "
                  f"aushub={w['aushub_m'] * 1e3:.0f} mm hand={w.get('in_der_hand_gewandert_m', 0) * 1e3:.1f} mm "
                  f"finger={fd * 1e3:.2f} mm kontakte_mm={ {k: round(v * 1e3, 3) for k, v in w['kontakte_m'].items()} } "
                  f"nachbar={w['nachbar_max_m'] * 1e3:.2f} mm", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--art", choices=["glaeser", "teller"], default="glaeser")
    ap.add_argument("--out", required=True)
    ap.add_argument("--device", default=None)
    ap.add_argument("--nur-plan", action="store_true")
    ap.add_argument("--objekte", type=int, default=None)
    ap.add_argument("--zuordnung", default=None)
    ap.add_argument("--variation", type=int, default=None)
    ap.add_argument("--negativ", type=int, default=None)
    ap.add_argument("--erledigt", default=None, help="schon abgeraeumte Objekte (1-basiert, Komma), stehen am Ziel")
    ap.add_argument("--aufzeichnen", default=None)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    meta: dict = {"art": args.art, "ok": False, "variation": args.variation, "negativ": args.negativ}
    t0 = time.monotonic()
    try:
        import numpy as np

        from finger import a1

        sz = a1.szenario()
        n = len(sz["glaeser"]["slots"]) if args.art == "glaeser" else len(sz["teller"]["spalten_x_m"]) * len(sz["teller"]["tiefe_m"])
        rng = np.random.default_rng(args.variation) if args.variation is not None else None
        abw = a1.abweichung(n, rng, verklemmt=args.negativ)
        zo = None
        if args.zuordnung:
            zo = [[int(v) for v in p.split(":")] for p in args.zuordnung.split(",")]
        ctx = None
        if not args.nur_plan:
            from ausraeumen import sim_newton as sn
            ctx = sn.kontext(args.device)
            meta.update({"device": ctx["device"], "versionen": sn.versionen()})
        erl = [int(v) for v in args.erledigt.split(",")] if args.erledigt else []
        rec, _ = a1.versuch(args.art, 0, abw, ctx, nur_plan=args.nur_plan, objekte_n=args.objekte, sz=sz,
                            aufzeichnen=args.aufzeichnen, zuordnung=zo, erledigt=erl)
        rec["wand_gesamt_s"] = round(time.monotonic() - t0, 1)
        (out / "versuch.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1))
        drucken(rec)
        if args.nur_plan:
            meta["ok"] = bool(rec["plan"]["ok"])
        elif args.negativ:
            name = ("teller_" if args.art == "teller" else "glas_") + str(args.negativ)
            g = [g for g in rec["bewertung"]["glaeser"] if g["glas"] == name]
            meta["ok"] = bool(g and not g[0]["erfolg"] and "nicht_aus_dem_korb" in g[0]["gruende"])
        else:
            meta["ok"] = bool(rec["erfolg"])
        meta["erfolge"] = rec.get("bewertung", {}).get("erfolge")
        meta["objekte_n"] = rec.get("bewertung", {}).get("glaeser_n")
    except Exception:  # noqa: BLE001
        meta["fehler"] = traceback.format_exc()
        print(meta["fehler"], file=sys.stderr)
    meta["wand_s"] = round(time.monotonic() - t0, 1)
    (out / "zusammenfassung.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1, default=str))
    print("FINGER_RESULT", json.dumps({k: meta.get(k) for k in ("art", "ok", "erfolge", "objekte_n", "wand_s",
                                                                    "variation", "negativ")}), flush=True)
    return 0 if meta["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
