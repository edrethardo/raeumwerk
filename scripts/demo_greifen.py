#!/usr/bin/env python3
"""Glas-Greifdemo in Newton: ReBeL greift ein Glas, hebt, versetzt, setzt ab.

Gestartet von ``scripts/run_greifen.sh`` mit dem Python des Isaac-Lab-venv
(Newton 1.6). Rein headless, keine Netzwerkschnittstelle. Auf einem geteilten
GPU-Rechner nur ueber die GPU-Warteschlange/den Lock.

    demo_greifen.py --art demo|variation|negativ --out DIR [--device cpu] [--versuche N]

* ``demo``      ein Versuch mit der Startlage aus ``config/scene.yaml``
* ``variation`` ``variation.versuche`` Versuche, Startlage um +-2 cm gestreut
                (fester Seed); jeder Versuch in einer eigenen, frisch
                aufgebauten Simulation (nacheinander)
* ``negativ``   absichtlich falscher Greifpunkt; muss als Fehlversuch mit
                Grund ``nicht_gegriffen`` erkannt werden

Ablauf je Versuch: ``greifen.plan`` plant die Soll-Trajektorie (IK, fester
Seed), der Simulator (``greifen.sim_newton``) faehrt sie mit PD-Antrieben und
Geschwindigkeitsvorsteuerung, misst alle ``simulation.messintervall_schritte``
die Glaslage und die Kontakte, ``greifen.bewertung`` entscheidet
Erfolg/Fehlergruende. Parameterstudien: ``raeumwerk run`` (docs/architektur.md).

Ausgabe in ``--out``: ``versuch-NN.json`` je Versuch, ``zusammenfassung.json``.
Exit 0, wenn die Erwartung der Versuchsart erfuellt ist (demo: Erfolg;
negativ: erkannter Fehlversuch; variation: alle Versuche gelaufen).
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--art", choices=["demo", "variation", "negativ"], default="demo")
    ap.add_argument("--out", required=True)
    ap.add_argument("--device", default=None)
    ap.add_argument("--versuche", type=int, default=None, help="nur die ersten N Versuche (zum Ausprobieren)")
    ap.add_argument("--seed", type=int, default=0, help="Seed der IK-Neustarts")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    meta: dict = {"art": args.art, "seed_ik": args.seed, "ok": False}
    t0 = time.monotonic()
    ergebnisse: list = []
    jsonable = lambda x: x  # noqa: E731  (ersetzt, sobald numpy geladen ist)
    try:
        from greifen import bewertung, sim_newton, szene
        from greifen.plan import Planer, versuche
        from rebel_model.config import load
        from rebel_model.kinematics import Chain
        from rebel_model.urdf_gen import build_urdf

        jsonable = sim_newton.jsonable
        for p, ver in sim_newton.versionen().items():
            if p != "numpy":
                meta[f"{p}_version"] = ver

        cfg = load()
        sz = szene.load()
        meta["seed_variation"] = int(sz.variation["seed"])
        urdf = build_urdf(cfg)
        chain = Chain(urdf)
        planer = Planer(chain, cfg, sz, seed=args.seed)
        liste = versuche(sz, args.art)
        if args.versuche:
            liste = liste[: args.versuche]
        meta["versuche_geplant"] = len(liste)

        ctx = sim_newton.kontext(cfg, sz, urdf, chain, args.device)
        meta["device"] = ctx["device"]
        wand_sum = 0.0
        for v in liste:
            rec = sim_newton.versuch_ausfuehren(ctx, v, planer)
            print("PLAN", json.dumps({"nr": v.nr, "ok": rec["plan"]["ok"], "fehler": rec["plan"]["fehler"],
                                      "dauer_s": rec["dauer"]["ablauf_sim_s"]}), flush=True)
            wand_sum += rec["dauer"]["wand_sim_s"]
            ergebnisse.append(rec)
            (out_dir / f"versuch-{v.nr:02d}.json").write_text(json.dumps(rec, indent=2))
            m = rec["messung"]
            print("VERSUCH", json.dumps({"nr": v.nr, "erfolg": rec["erfolg"], "gruende": rec["gruende"],
                                         "fehler_xy_mm": round(m["zielfehler_xy_m"] * 1e3, 2),
                                         "kippung_grad": round(m["kippung_end_grad"], 3),
                                         "hub_max_mm": round(m["hub_max_m"] * 1e3, 1),
                                         "wand_s": round(rec["dauer"]["wand_sim_s"], 1)}), flush=True)
        zus = bewertung.zusammenfassung(ergebnisse)
        meta["zusammenfassung"] = zus
        meta["wand_sim_summe_s"] = round(wand_sum, 2)
        if args.art == "demo":
            meta["erwartung"] = "Erfolg"
            meta["ok"] = zus["erfolge"] == zus["versuche"] == 1
        elif args.art == "negativ":
            meta["erwartung"] = "Fehlversuch mit Grund nicht_gegriffen"
            meta["ok"] = zus["versuche"] >= 1 and zus["erfolge"] == 0 and all(
                "nicht_gegriffen" in e["gruende"] for e in ergebnisse)
        else:
            meta["erwartung"] = "alle Versuche gelaufen"
            meta["ok"] = zus["versuche"] == len(liste) > 0
    except Exception as e:  # noqa: BLE001
        meta["error"] = f"{type(e).__name__}: {e}"
        meta["traceback"] = traceback.format_exc()[-4000:]
    finally:
        meta["total_s"] = round(time.monotonic() - t0, 2)
        (out_dir / "zusammenfassung.json").write_text(json.dumps(jsonable(meta), indent=2))
        print("GREIFEN_RESULT", json.dumps(jsonable({"art": meta["art"], "ok": meta["ok"],
                                                     "zusammenfassung": meta.get("zusammenfassung"),
                                                     "error": meta.get("error")})), flush=True)
    return 0 if meta["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
