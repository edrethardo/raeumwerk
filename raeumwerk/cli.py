"""Kommandozeile ``raeumwerk`` (auch ``python -m raeumwerk``).

    raeumwerk run <experiment.yaml> [--run-dir DIR] [--max-minuten M] [--device cpu] [--backend attrappe]
    raeumwerk report <run-dir> [--json] [--nicht-schreiben]
    raeumwerk next <run-dir> [--out datei.yaml]
    raeumwerk aufbau <aufbau.yaml> [--jobs N] [--out DIR] [--cache DIR | --kein-cache] [--gruppen ...] [--ohne-bilder]

Keine Netzwerkschnittstelle: Steuerung nur ueber Argumente, Dateien und die
GPU-Warteschlange (``scripts/submit_gpu.sh``). Exit-Codes von ``run`` siehe
``raeumwerk.lauf``.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _aufbau(a) -> int:
    import os
    import time

    from spuelmaschine import aufbau

    t = time.monotonic()
    pfad = Path(a.aufbau)
    if not pfad.is_file():
        print(f"FEHLER: Aufbau-Datei fehlt: {pfad}", file=sys.stderr)
        return 2
    try:
        d = aufbau.lade_yaml(pfad)
    except (ValueError, KeyError) as e:
        print(f"FEHLER in {pfad}: {e}", file=sys.stderr)
        return 2
    cache = None
    if not a.kein_cache:
        cache = Path(a.cache) if a.cache else Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "raeumwerk" / "aufbau"
    out = Path(a.out) if a.out else Path(f"aufbau-{pfad.stem}")
    e = aufbau.lauf(d, jobs=a.jobs, cache=cache, gruppen=a.gruppen, log=lambda s: print(s, flush=True))
    if not a.ohne_bilder and d.get("bilder", True):
        from spuelmaschine import aufbau_bilder

        e["bilder"] = aufbau_bilder.zeichne_alle(d, e, out)
    e["laufzeit_gesamt_s"] = round(time.monotonic() - t, 1)
    aufbau.schreibe(e, out)
    print(aufbau.bericht_md(e).split("\n## ")[1].split("\n## ")[0] if "\n## " in aufbau.bericht_md(e) else "")
    print(f"Ergebnis: {out / 'ergebnis.md'} ({e['laufzeit_gesamt_s']} s)")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="raeumwerk", description="Raeumwerk-Experimente headless")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="Versuche eines Experiments fahren (fortsetzbar)")
    r.add_argument("experiment")
    r.add_argument("--run-dir", default=None, help="Run-Verzeichnis (Fortsetzen: dasselbe angeben)")
    r.add_argument("--max-minuten", type=float, default=None, help="Zeitbudget dieses Stuecks (<= 30)")
    r.add_argument("--device", default=None, help="z. B. cpu oder cuda:0 (Standard: GPU, wenn da)")
    r.add_argument("--backend", default=None, choices=["newton", "attrappe", "ausraeumen"])
    r.add_argument("--teil", default=None, metavar="K/N",
                   help="nur Versuche mit nr %% N == K (mehrere Prozesse auf einem Run-Verzeichnis)")
    p = sub.add_parser("report", help="Erfolge, Kollisionen, Fehlergruende zusammenfassen")
    p.add_argument("run")
    p.add_argument("--json", action="store_true", help="JSON statt Text ausgeben")
    p.add_argument("--nicht-schreiben", action="store_true", help="bericht.json/.md nicht ins Run-Verzeichnis")
    n = sub.add_parser("next", help="neuen Parametervorschlag aus Fehlversuchen ableiten")
    n.add_argument("run")
    n.add_argument("--out", default=None, help="Zieldatei (Standard <run>/vorschlag.yaml)")
    au = sub.add_parser("aufbau", help="Erreichbarkeit einer Aufbau-Variante (IK, Kollision, Momente)")
    au.add_argument("aufbau", help="Aufbau-Beschreibung (YAML, Beispiele in beispiele/)")
    au.add_argument("--jobs", type=int, default=None, help="Prozesse (Standard: alle Kerne)")
    au.add_argument("--out", default=None, help="Ausgabeordner (Standard: aufbau-<Dateiname>)")
    au.add_argument("--cache", default=None, help="Cache-Ordner (Standard: ~/.cache/raeumwerk/aufbau)")
    au.add_argument("--kein-cache", action="store_true", help="ohne Cache rechnen (nichts lesen, nichts schreiben)")
    au.add_argument("--gruppen", nargs="+", default=None, help="nur diese Zielgruppen (slots teller zug ablage)")
    au.add_argument("--ohne-bilder", action="store_true", help="keine PNGs zeichnen")
    a = ap.parse_args(argv)

    if a.cmd == "aufbau":
        return _aufbau(a)
    if a.cmd == "run":
        from . import lauf
        teil = None
        if a.teil:
            try:
                k, n = (int(x) for x in a.teil.split("/"))
                teil = (k, n)
            except ValueError:
                print(f"FEHLER --teil {a.teil}: K/N erwartet, z. B. 0/3", file=sys.stderr)
                return 2
        return lauf.run(a.experiment, a.run_dir, a.max_minuten, a.device, a.backend,
                        log=lambda s: print(s, flush=True), teil=teil)

    from . import auswertung, experiment as ex
    from .lauf import run_pfad
    run = run_pfad(a.run)
    if not (run / "manifest.json").is_file():
        print(f"FEHLER: kein Run-Verzeichnis (manifest.json fehlt): {run}", file=sys.stderr)
        return 2
    if a.cmd == "report":
        b = auswertung.bericht(run)
        text = auswertung.bericht_text(b)
        if not a.nicht_schreiben:
            (run / "bericht.json").write_text(json.dumps(b, indent=2), encoding="utf-8")
            (run / "bericht.md").write_text(text, encoding="utf-8")
        print(json.dumps(b, indent=2) if a.json else text, end="" if not a.json else "\n")
        return 0
    v = auswertung.vorschlag(run)
    out = Path(a.out) if a.out else run / "vorschlag.yaml"
    kopf = "# Parametervorschlag von 'raeumwerk next' (Regeln: raeumwerk/auswertung.py)\n"
    out.write_text(kopf + ex.nach_yaml(v) + "\n", encoding="utf-8")
    for z in v["begruendung"]:
        print("-", z)
    print(f"Vorschlag: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
