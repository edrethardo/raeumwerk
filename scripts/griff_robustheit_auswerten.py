#!/usr/bin/env python3
"""Aggregiert die Raster-JSONs von ``griff_robustheit.py`` zu den Markdown-Tabellen der Doku.

    griff_robustheit_auswerten.py ORDNER      (liest robustheit-glas-*.json, robustheit-teller-*.json)

Spalten: Restfehler S0/S1/S2 (Mittel / Max, nur Zeilen mit Wert), S1 verworfen (D405 hat die
Schaetzung nicht angenommen), mechanisch ok (S0 blind, S1, S2 jeweils mit Wert), Kette = mechanisch ok
UND S3 schlaegt nicht an UND D405 nicht verworfen, S3: Kreuzprobe schlaegt an (ohne verworfene),
Fehlalarm (S3 schlaegt an, obwohl S0 mechanisch noch greift), S0-Fehlgriffe erkannt (S3 oder Verwerfen).
"""
from __future__ import annotations

import json
import statistics as st
import sys
from pathlib import Path


def _mm(rows, k):
    v = [r[k] for r in rows if r.get(k) is not None]
    return f"{st.mean(v):.1f} / {max(v):.1f}" if v else "–"


def zeile(name, rows):
    n = len(rows)
    ok = lambda k: sum(1 for r in rows if r.get("mech", {}).get(k))  # noqa: E731
    verw = sum(1 for r in rows if r.get("s1_verworfen"))
    alarm = [r for r in rows if r.get("s3_kreuz")]
    kette = lambda k: sum(1 for r in rows if r.get("mech", {}).get(k)  # noqa: E731
                          and not r.get("s3_kreuz") and not r.get("s1_verworfen"))
    s0_fehl = [r for r in rows if r.get("mech") and not r["mech"]["s0"]]
    fehl_erk = sum(1 for r in s0_fehl if r.get("s3_kreuz") or r.get("s1_verworfen"))
    falsch = sum(1 for r in alarm if r.get("mech", {}).get("s0"))
    gier = [r["s1_gier"] for r in rows if r.get("s1_gier") is not None]
    g = f"{st.mean(gier):.1f}" if gier else "–"
    return (f"| {name} | {n} | {_mm(rows, 's0_mm')} | {_mm(rows, 's1_mm')} | {_mm(rows, 's2_mm')} | {g} | "
            f"{ok('s0')} | {ok('s1')} | {ok('s2')} | {verw} | {kette('s1')} | {kette('s2')} | "
            f"{len(alarm)} | {falsch} | {fehl_erk}/{len(s0_fehl)} |")


KOPF = ("| Stufe | n | S0 mm | S1 mm | S2 mm | S1 Gier ° | S0 ok | S1 ok | S2 ok | D405 verworfen | "
        "S1 Kette | S2 Kette | S3 schlägt an | davon Fehlalarm | S0-Fehlgriffe erkannt |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")


def main(ordner):
    o = Path(ordner)
    for art in ("glas", "teller"):
        zs = []
        for p in sorted(o.glob(f"robustheit-{art}-*.json")):
            d = json.loads(p.read_text())
            zs += d["zeilen"]
            gr = d["grenzen"]
        if not zs:
            continue
        print(f"\n### {art}  (Grenzen {gr})\n\n{KOPF}")
        for r in (0.0, 5.0, 15.0):
            for t in (0.0, 5.0, 20.0):
                rows = [x for x in zs if x["stufe"] == "feste" and x["grad"] == r and x["t_mm"] == t]
                if rows:
                    print(zeile(f"{r:.0f}° / {t:.0f} mm", rows))
        for name in ("sigma_frei", "sigma_hart"):
            rows = [x for x in zs if x["stufe"] == name]
            if rows:
                print(zeile(name, rows))
                bet = [x["drift_betrag_mm"] for x in rows]
                gradw = [x["drift_grad"] for x in rows]
                print(f"<!-- {name}: Versatz Mittel {st.mean(bet):.1f} mm, Max {max(bet):.1f} mm, "
                      f"Drehung Mittel {st.mean(gradw):.1f}°, Max {max(gradw):.1f}° -->")


if __name__ == "__main__":
    main(sys.argv[1])
