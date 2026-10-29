#!/usr/bin/env python3
"""Baut einen Renderauftrag fuer scripts/isaac_render.py (ohne Isaac Sim).

    isaac_render_auftrag.py greifdemo AUFZEICHNUNG.npz --out auftrag.npz [--fps 30] [--halten 3]
    isaac_render_auftrag.py spuelmaschine --out auftrag.npz [--slot 1]

Die Aufzeichnung kommt aus ``scripts/run_greifen.sh … demo --aufzeichnen``.
Der Auftrag enthaelt Posen, Kamera und Szenenkoerper, keine Meshes.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = ap.add_subparsers(dest="szene", required=True)
    g = sub.add_parser("greifdemo")
    g.add_argument("aufzeichnung")
    g.add_argument("--fps", type=float, default=30.0)
    g.add_argument("--tempo", type=float, default=None)
    g.add_argument("--halten", type=float, default=3.0)
    g.add_argument("--kamerafahrt", type=float, default=14.0, help="Grad Kameraschwenk ueber das Video")
    g.add_argument("--out", required=True)
    s = sub.add_parser("spuelmaschine")
    s.add_argument("--slot", type=int, default=1)
    s.add_argument("--out", required=True)
    r = sub.add_parser("ausraeumen")
    r.add_argument("aufzeichnung")
    r.add_argument("--fps", type=float, default=30.0)
    r.add_argument("--video-s", type=float, default=50.0, help="Ziel-Videolaenge (Tempo daraus)")
    r.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    from isaac_render import auftrag as A
    if a.szene == "greifdemo":
        from greifen.aufzeichnung import laden
        auf = A.aus_aufzeichnung(laden(a.aufzeichnung), fps=a.fps, tempo=a.tempo, halten=a.halten,
                                 kamerafahrt_grad=a.kamerafahrt)
    elif a.szene == "ausraeumen":
        from greifen.aufzeichnung import laden
        auf = A.aus_ausraeumen(laden(a.aufzeichnung), fps=a.fps, video_s=a.video_s)
    else:
        auf = A.aus_spuelmaschine(a.slot)
    fehler = A.pruefen(auf)
    if fehler:
        print("Auftrag fehlerhaft:", fehler, file=sys.stderr)
        return 1
    A.speichern(auf, a.out)
    print(f"AUFTRAG {a.out}: {auf['szene']}, {len(auf['posen'])} Bilder, {len(auf['koerper'])} Koerper, "
          f"{len(auf['statisch'])} statische Koerper, Tempo {auf['tempo']:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
