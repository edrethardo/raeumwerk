#!/usr/bin/env python3
"""Tabellen aus ``zeilen-*.jsonl`` von ``griff_prior.py`` (Markdown auf stdout).

Begriffe (je Zeile = ein Seed):
  ok          Griff liegt mechanisch im Fangbereich (``robustheit.erfolg_mechanisch``, gegen die WAHRHEIT);
              S0 blind / S1 D405 / S2 Fusion / N0 Nennlage blind zaehlen ohne Abbruchlogik.
  erfolg      Kette hat nicht abgebrochen UND der Griff ist ok.
  Abbruch     Kette bricht ab (kein Griff); (Fehlalarm) = die Pose waere trotzdem ok gewesen.
  unbemerkt   Kette bricht nicht ab, aber der Griff ist nicht ok (unbemerkter Fehlgriff).
  Kette       heutige Pruefung (Abbruch bei jedem Abbruchgrund), A = "neu hinsehen", B = Mechanik-Prior.
Spalten "Kreuzprobe schlaegt an" und "verworfen" sind getrennt: Kreuzprobe = Ensenso<->D405-Abstand
ueber der Toleranz; verworfen = der Schaetzer nimmt die D405-Schaetzung nicht an.
    griff_prior_auswerten.py ORDNER
"""
from __future__ import annotations

import json
import math
import statistics as st
import sys
from pathlib import Path


def lade(o):
    z = []
    for p in sorted(Path(o).glob("zeilen-*.jsonl")):
        z += [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    return z


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def ok(x):
    return bool(x and x.get("ok"))


def kette(z, wer):
    """(erfolg, abbruch, fehlalarm, unbemerkt) fuer 'kette' | 'a' | 'b'."""
    if z.get("ensenso_fehlt"):
        return (0, 1, 0, 0)
    if wer == "kette":
        acc, pose = z["ok_std"], z.get("s1")
    elif wer == "a":
        acc, pose = z["a_annahme"], z.get("s1")
    else:
        acc, pose = z["b_annahme"], z.get("b")
    g = ok(pose)
    if acc:
        return (int(g), 0, 0, int(not g))
    return (0, 1, int(g), 0)


def mm(rows, getter):
    v = [getter(r) for r in rows]
    v = [x for x in v if x is not None]
    return f"{st.mean(v):.1f} / {max(v):.1f}" if v else "–"


def zahl(rows, f):
    return sum(1 for r in rows if f(r))


KOPF = ("| {k} | n | N0 ok | S0 ok | S1 ok | S2 ok | Kette erfolg | Kette Abbruch (davon Fehlalarm) | "
        "Kette unbemerkt | A erfolg | A Abbruch (Fehlalarm) | A unbemerkt | B erfolg | B Abbruch (Fehlalarm) | "
        "B unbemerkt |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")


def zeile(name, rows):
    n = len(rows)
    k = {w: [kette(r, w) for r in rows] for w in ("kette", "a", "b")}
    s = lambda w, i: sum(x[i] for x in k[w])  # noqa: E731
    return (f"| {name} | {n} | {zahl(rows, lambda r: ok(r.get('n0')))} | {zahl(rows, lambda r: ok(r.get('s0')))} | "
            f"{zahl(rows, lambda r: ok(r.get('s1')))} | {zahl(rows, lambda r: ok(r.get('s2')))} | "
            f"{s('kette', 0)} | {s('kette', 1)} ({s('kette', 2)}) | {s('kette', 3)} | "
            f"{s('a', 0)} | {s('a', 1)} ({s('a', 2)}) | {s('a', 3)} | "
            f"{s('b', 0)} | {s('b', 1)} ({s('b', 2)}) | {s('b', 3)} |")


def mm_zeile(name, rows):
    g = lambda k: (lambda r: (r.get(k) or {}).get("mm"))  # noqa: E731
    gg = lambda k: (lambda r: (r.get(k) or {}).get("gier_fehler"))  # noqa: E731
    return (f"| {name} | {mm(rows, g('n0'))} | {mm(rows, g('s0'))} | {mm(rows, g('s1'))} | {mm(rows, g('s2'))} | "
            f"{mm(rows, g('b'))} | {mm(rows, gg('s0'))} | {mm(rows, gg('s1'))} | {mm(rows, gg('b'))} |")


MMKOPF = ("| {k} | N0 mm | S0 mm | S1 mm | S2 mm | B mm | S0 Gier-F. ° | S1 Gier-F. ° | B Gier-F. ° |\n"
          "|---|---|---|---|---|---|---|---|---|")


def raster(zs, art):
    rows = [z for z in zs if z["art"] == art and z["kind"] == "raster"]
    if not rows:
        return
    namen = list(dict.fromkeys(z["stufe"] for z in rows))
    print(f"\n### {art}: Raster und Gauss-σ (Welt wie in der Griffrobustheit-Reihe, Prior stimmt)\n\n{KOPF.format(k='Stufe')}")
    for n in namen:
        print(zeile(n, [z for z in rows if z["stufe"] == n]))
    print(f"\nRestfehler gegen die Wahrheit (Mittel / Max; Gier-Fehler gegen die wahre Gier)\n\n{MMKOPF.format(k='Stufe')}")
    for n in namen:
        print(mm_zeile(n, [z for z in rows if z["stufe"] == n]))
    g = [z for z in rows if z["stufe"] in ("sigma_frei", "sigma_hart")]
    if g:
        print("\nGezogener Drift: " + "; ".join(
            f"{n}: Versatz {st.mean([z['drift_betrag_mm'] for z in g if z['stufe'] == n]):.1f} mm, Drehung "
            f"{st.mean([z['drift_grad'] for z in g if z['stufe'] == n]):.1f}°" for n in ("sigma_frei", "sigma_hart")))


def welt(zs, art):
    rows = [z for z in zs if z["art"] == art and z["kind"] == "welt"]
    ref = [z for z in zs if z["art"] == art and z["kind"] == "raster" and z["stufe"].startswith("sigma")]
    if not rows:
        return
    print(f"\n### {art}: der Prior selbst liegt daneben (σ 15°/2 cm; Welt-Versatz ×k, Welt-Drehung/Gier ×m)\n"
          f"\n{KOPF.format(k='Stufe, Welt')}")
    for z in ref:
        pass
    for n in ("sigma_frei", "sigma_hart"):
        print(zeile(f"{n}, Welt ×1/×1 (Prior stimmt)", [z for z in ref if z["stufe"] == n]))
    for sk in dict.fromkeys((z["skala_xy"], z["skala_dreh"]) for z in rows):
        for n in ("sigma_frei", "sigma_hart"):
            g = [z for z in rows if (z["skala_xy"], z["skala_dreh"]) == sk and z["stufe"] == n]
            print(zeile(f"{n}, Welt ×{sk[0]:g}/×{sk[1]:g}", g))
    print(f"\nRestfehler\n\n{MMKOPF.format(k='Stufe, Welt')}")
    for n in ("sigma_frei", "sigma_hart"):
        print(mm_zeile(f"{n}, Welt ×1/×1", [z for z in ref if z["stufe"] == n]))
    for sk in dict.fromkeys((z["skala_xy"], z["skala_dreh"]) for z in rows):
        for n in ("sigma_frei", "sigma_hart"):
            print(mm_zeile(f"{n}, Welt ×{sk[0]:g}/×{sk[1]:g}",
                           [z for z in rows if (z["skala_xy"], z["skala_dreh"]) == sk and z["stufe"] == n]))
    # Prior-Plausibilitaet: schlaegt sie an, wenn der Prior daneben liegt?
    print("\nPrior-Plausibilität (D405 gegen Prior ± 3σ): Alarm-Rate je Welt\n\n| Welt | n | D405 widerspricht Prior (xy) | "
          "Gier-Alarm (Station > Tol + Band) | davon B ok trotz Alarm xy |\n|---|---|---|---|---|")
    for sk, n_ in [((1.0, 1.0), None)] + [(k, None) for k in dict.fromkeys((z["skala_xy"], z["skala_dreh"]) for z in rows)]:
        g = [z for z in (ref if sk == (1.0, 1.0) else rows) if (z["skala_xy"], z["skala_dreh"]) == sk]
        w = [z for z in g if (z.get("b_prior") or {}).get("widerspruch_xy")]
        ga = [z for z in g if (z.get("b_prior") or {}).get("widerspruch_gier")]
        print(f"| ×{sk[0]:g}/×{sk[1]:g} | {len(g)} | {len(w)} | {len(ga)} | {sum(1 for z in w if ok(z.get('b')))} |")


def fehlalarm(zs):
    print("\n### Fehlalarmrate bei 0 / 5 mm Versatz (S0 greift noch; Wilson-95%-Intervall)\n\n"
          "| Objekt | Stufe | n | S0 greift | Kreuzprobe schlägt an (Fehlalarm = S0 greift) | Kette-Abbruch Fehlalarm | "
          "A-Abbruch Fehlalarm | B-Abbruch Fehlalarm |\n|---|---|---|---|---|---|---|---|")
    for art in ("glas", "teller"):
        for stufe in ("0°/0 mm", "0°/5 mm", "5°/0 mm", "5°/5 mm", "15°/0 mm", "15°/5 mm"):
            g = [z for z in zs if z["art"] == art and z["kind"] == "raster" and z["stufe"] == stufe]
            if not g:
                continue
            s0 = [z for z in g if ok(z.get("s0"))]
            f3 = zahl(s0, lambda z: z.get("s3_kreuz"))
            fk = sum(kette(z, "kette")[2] for z in s0)
            fa = sum(kette(z, "a")[2] for z in s0)
            fb = sum(kette(z, "b")[2] for z in s0)

            def w(k, n=len(s0)):
                lo, hi = wilson(k, n)
                return f"{k}/{n} ({100 * lo:.0f}–{100 * hi:.0f} %)"
            print(f"| {art} | {stufe} | {len(g)} | {len(s0)} | {w(f3)} | {w(fk)} | {w(fa)} | {w(fb)} |")
    print("\n(Fehlalarm-Spalten zählen nur Seeds, bei denen der blinde Griff S0 mechanisch noch greift; "
          "bei Kette/A/B zählt ein Abbruch, obwohl die eigene Pose ok gewesen wäre, in `Abbruch (Fehlalarm)` oben.)")


def zielverwechslung(zs, art):
    rows = [z for z in zs if z["art"] == art and z["kind"] == "c"]
    if not rows:
        return
    print(f"\n### {art}: Zielverwechslung (beide Kameras segmentieren das falsche Objekt)\n\n"
          "| Maske | Drift | n | Nachbar-Abstand mm | Schätzer lehnt selbst ab (ensenso:/d405:) | Nennlage-Check schlägt an | "
          "Kreuzprobe schlägt an | B: prior_widerspruch | Kette unbemerkt | A unbemerkt | B unbemerkt "
          "| unbemerkt: Fehler mm (Mittel / Max) |\n|---|---|---|---|---|---|---|---|---|---|---|---|")
    tot = {"kette": [0, 0], "a": [0, 0], "b": [0, 0]}
    for neg in dict.fromkeys(z["negativ"] for z in rows):
        for dn in ("ohne", "sigma_hart"):
            g = [z for z in rows if z["negativ"] == neg and z["stufe"] == dn]
            if not g:
                continue
            nb = [z["nachbar_abstand_mm"] for z in g if z.get("nachbar_abstand_mm")]
            ablehn = zahl(g, lambda z: z.get("ensenso_fehlt") or any(x.startswith(("ensenso:", "d405:")) for x in (z.get("gruende") or [])))
            nenn = zahl(g, lambda z: "nicht_am_erwarteten_platz" in (z.get("gruende") or []))
            kreuz = zahl(g, lambda z: z.get("s3_kreuz"))
            pw = zahl(g, lambda z: "prior_widerspruch" in (z.get("b_gruende") or []))
            u = {w: [z for z in g if kette(z, w)[3]] for w in ("kette", "a", "b")}
            for w in tot:
                tot[w][0] += len(u[w])
                tot[w][1] += len(g)
            fehl = [(z.get("b") if w == "b" else z.get("s1"))["mm"] for w in u for z in u[w]
                    if (z.get("b") if w == "b" else z.get("s1"))]
            print(f"| {neg} | {dn} | {len(g)} | {st.mean(nb):.0f} | {ablehn}/{len(g)} | {nenn}/{len(g)} | {kreuz}/{len(g)} | "
                  f"{pw}/{len(g)} | {len(u['kette'])} | {len(u['a'])} | {len(u['b'])} | "
                  f"{'%.0f / %.0f' % (st.mean(fehl), max(fehl)) if fehl else '– (keine unbemerkte Verwechslung)'} |")
    print("\n**Unbemerkte Verwechslungsrate u** (gegeben: Nachbarmaske; Wilson-95%-Intervall über alle Zeilen dieses Objekts):\n")
    print("| Kette | unbemerkt / Verwechslungen | u (95 %) |\n|---|---|---|")
    for w, nm in (("kette", "heutige Kette"), ("a", "A neu hinsehen"), ("b", "B Prior")):
        k, n = tot[w]
        lo, hi = wilson(k, n)
        print(f"| {nm} | {k}/{n} | {100 * k / n:.1f} % ({100 * lo:.1f}–{100 * hi:.1f} %) |")
    # Mischung: Erwartungswert je p, Normalfall aus Raster 0/0 und sigma_hart (gleiche Drift)
    print("\n**Erwartungswert je Verwechslungswahrscheinlichkeit p** (Mischung aus Normalfall und Verwechslung; "
          "Normalfall = Raster 0°/0 mm und σ hart je zur Hälfte; Verwechslung = alle Zeilen oben; "
          "Erwartungswert aus Zellenanteilen, keine Ziehung):\n")
    norm = [z for z in zs if z["art"] == art and z["kind"] == "raster" and z["stufe"] in ("0°/0 mm", "sigma_hart")]
    print("| p | Kette: erfolg / Abbruch / unbemerkt Fehlgriff | A | B |\n|---|---|---|---|")
    for p in (0.0, 0.05, 0.10, 0.20):
        cell = []
        for w in ("kette", "a", "b"):
            kn = [kette(z, w) for z in norm]
            kc = [kette(z, w) for z in rows]
            e = (1 - p) * sum(x[0] for x in kn) / len(kn) + p * sum(x[0] for x in kc) / len(kc)
            a = (1 - p) * sum(x[1] for x in kn) / len(kn) + p * sum(x[1] for x in kc) / len(kc)
            u = (1 - p) * sum(x[3] for x in kn) / len(kn) + p * sum(x[3] for x in kc) / len(kc)
            hi = (1 - p) * sum(x[3] for x in kn) / len(kn) + p * wilson(tot[w][0], tot[w][1])[1]
            cell.append(f"{100 * e:.1f} / {100 * a:.1f} / {100 * u:.1f} % (u ≤ {100 * hi:.1f} %)")
        print(f"| {100 * p:.0f} % | " + " | ".join(cell) + " |")


def main(o):
    zs = lade(o)
    print(f"<!-- {len(zs)} Zeilen -->")
    for art in ("glas", "teller"):
        raster(zs, art)
        welt(zs, art)
    fehlalarm(zs)
    for art in ("glas", "teller"):
        zielverwechslung(zs, art)


if __name__ == "__main__":
    main(sys.argv[1])
