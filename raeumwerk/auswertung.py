"""``raeumwerk report`` und ``raeumwerk next``: Auswertung eines Run-Verzeichnisses.

Nur Standardbibliothek (laeuft ohne numpy/pyyaml, z. B. auf dem Steuerrechner).

Bericht: Erfolge, Kollisionen (Arm/Tisch, Finger zu tief im Glas), Fehlergruende
mit Anzahl, je Fehlversuch Parameter und Gruende, je variiertem Parameter der
Wertebereich der Erfolge und der Fehlversuche.

Vorschlag (keine Optimierung, kein Training; Regeln in fester Reihenfolge):

1. ``bereich``-Parameter mit mindestens zwei Erfolgen: neuer Bereich = kleinster
   bis groesster Erfolgswert (Fehlversuche ausserhalb fallen weg).
2. ``bereich``-Parameter mit genau einem Erfolg: Bereich halber Breite um ihn.
3. Ohne Erfolg Regeln nach dem haeufigsten Fehlergrund:
   ``nicht_gegriffen`` -> Greifpunktversatz-Bereiche zur Mitte halbieren;
   ``gefallen`` -> untere Grenze von ``greifkraft_n``/``reibung_*`` auf die Mitte heben;
   ``kollision_arm_tisch`` -> ``greif_versatz_z_m`` um 5 mm anheben;
   ``durchdringung`` -> obere Grenze von ``greifkraft_n`` auf die Mitte senken;
   ``planung_fehlgeschlagen`` -> Glaslage-Bereiche zum Szenenwert halbieren.
4. ``werte``-Parameter: nur Werte behalten, die mindestens einen Erfolg hatten.
5. Greift keine Regel, Zufallssuche: gleicher Raum, neuer Seed.

Immer: Seed + 1, Name mit Folgenummer, ``abgeleitet_von`` (Run, Konfig-Hash)
und ``begruendung`` (eine Zeile je angewandter Regel).
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import experiment as ex
from .lauf import fertige_versuche, lies_manifest

KOLLISION = ("kollision_arm_tisch", "durchdringung")


def _f(x) -> Optional[float]:
    v = ex.optional_float(x)
    return None if v is None or math.isnan(v) else v


def _spanne(werte: List[float]) -> Optional[List[float]]:
    return [min(werte), max(werte)] if werte else None


def bericht(run: Path | str) -> Dict[str, Any]:
    run = Path(run)
    man = lies_manifest(run)
    recs = fertige_versuche(run)
    n = len(recs)
    erfolge = [r for r in recs.values() if r["erfolg"]]
    fehl = [r for r in recs.values() if not r["erfolg"]]
    gruende: Dict[str, int] = {}
    for r in fehl:
        for g in r["gruende"]:
            gruende[g] = gruende.get(g, 0) + 1
    gruende = dict(sorted(gruende.items(), key=lambda kv: (-kv[1], kv[0])))
    td = [_f(r.get("messung", {}).get("tisch_durchdringung_max_m")) for r in recs.values()]
    fd = [_f(r.get("messung", {}).get("finger_durchdringung_max_m")) for r in recs.values()]
    kollision = {
        "arm_tisch": sum(1 for r in recs.values() if "kollision_arm_tisch" in r["gruende"]),
        "finger_glas_zu_tief": sum(1 for r in recs.values() if "durchdringung" in r["gruende"]),
        "versuche_mit_kollision": sorted(r["versuch"]["nr"] for r in recs.values()
                                         if any(g in r["gruende"] for g in KOLLISION)),
        "tisch_durchdringung_max_mm": round(max((x for x in td if x is not None), default=0.0) * 1e3, 3),
        "finger_durchdringung_max_mm": round(max((x for x in fd if x is not None), default=0.0) * 1e3, 3),
    }
    varianten = man["experiment"].get("parameter", {})
    parameter = {}
    for name, spec in varianten.items():
        if "fest" in spec:
            continue
        ok = [r["parameter"][name] for r in erfolge if name in r.get("parameter", {})]
        nok = [r["parameter"][name] for r in fehl if name in r.get("parameter", {})]
        parameter[name] = {"raum": spec, "erfolge": _spanne(ok), "fehlversuche": _spanne(nok)}
    zf = [_f(r["position"]["fehler_xy_m"]) for r in erfolge]
    zf = [x for x in zf if x is not None]
    return {
        "run": man.get("run", run.name), "name": man["name"], "status": man["status"],
        "konfig_hash": man["konfig_hash"], "git_sha": man["git"].get("sha"), "backend": man.get("backend"),
        "versuche_geplant": man["versuche_geplant"], "versuche_fertig": n, "erfolge": len(erfolge),
        "erfolgsquote": round(len(erfolge) / n, 4) if n else 0.0,
        "unvollstaendig": n < man["versuche_geplant"],
        "fehlergruende": gruende, "kollisionen": kollision,
        "fehlversuche": [{"nr": r["versuch"]["nr"], "gruende": r["gruende"], "parameter": r.get("parameter", {})}
                         for r in sorted(fehl, key=lambda r: r["versuch"]["nr"])],
        "parameter": parameter,
        "zielfehler_erfolge_mm": {"max": round(max(zf) * 1e3, 3) if zf else None,
                                  "mittel": round(sum(zf) / len(zf) * 1e3, 3) if zf else None},
        "stuecke": len(man.get("stuecke", [])),
    }


def bericht_text(b: Dict[str, Any]) -> str:
    z = [f"# Bericht {b['run']} ({b['name']})", "",
         f"- Status: {b['status']}" + (" (unvollstaendig)" if b["unvollstaendig"] else ""),
         f"- Versuche: {b['versuche_fertig']}/{b['versuche_geplant']}, Erfolge {b['erfolge']} "
         f"(Quote {b['erfolgsquote']:.2f}), Stuecke {b['stuecke']}",
         f"- Git {str(b['git_sha'])[:12]}, Konfig-Hash {b['konfig_hash'][:12]}, Backend {b['backend']}",
         f"- Kollisionen: Arm/Tisch {b['kollisionen']['arm_tisch']}, Finger zu tief "
         f"{b['kollisionen']['finger_glas_zu_tief']} (max. Tisch {b['kollisionen']['tisch_durchdringung_max_mm']} mm, "
         f"Finger {b['kollisionen']['finger_durchdringung_max_mm']} mm)"]
    if b["zielfehler_erfolge_mm"]["max"] is not None:
        z.append(f"- Zielfehler der Erfolge: max {b['zielfehler_erfolge_mm']['max']} mm, "
                 f"Mittel {b['zielfehler_erfolge_mm']['mittel']} mm")
    z += ["", "## Fehlergruende", ""]
    z += [f"- {g}: {n}" for g, n in b["fehlergruende"].items()] or ["- keine"]
    z += ["", "## Fehlversuche", ""]
    z += [f"- Nr. {f['nr']}: {', '.join(f['gruende'])} | " +
          ", ".join(f"{k}={v}" for k, v in sorted(f["parameter"].items())) for f in b["fehlversuche"]] or ["- keine"]
    z += ["", "## Parameter (Spanne Erfolge / Fehlversuche)", ""]
    z += [f"- {k}: {v['erfolge']} / {v['fehlversuche']}" for k, v in b["parameter"].items()] or ["- keine variiert"]
    return "\n".join(z) + "\n"


def _mitte(a: float, b: float) -> float:
    return round((a + b) / 2.0, 6)


def vorschlag(run: Path | str) -> Dict[str, Any]:
    """Neue Experimentdatei (als dict) aus den Ergebnissen eines Runs."""
    run = Path(run)
    man = lies_manifest(run)
    b = bericht(run)
    alt = man["experiment"]
    neu_p: Dict[str, Dict[str, Any]] = json.loads(json.dumps(alt.get("parameter", {})))
    std = man.get("parameter_standard", {})
    recs = list(fertige_versuche(run).values())
    erfolge = [r for r in recs if r["erfolg"]]
    begr: List[str] = []

    for name, spec in sorted(neu_p.items()):
        ok = [float(r["parameter"][name]) for r in erfolge if name in r.get("parameter", {})]
        if "bereich" in spec and len(ok) >= 2 and [min(ok), max(ok)] != spec["bereich"]:
            spec["bereich"] = [min(ok), max(ok)]
            begr.append(f"{name}: Bereich auf die Erfolge eingeengt {spec['bereich']} (Regel 1)")
        elif "bereich" in spec and len(ok) == 1:
            a, c = spec["bereich"]
            h = (c - a) / 4.0
            spec["bereich"] = [round(max(a, ok[0] - h), 6), round(min(c, ok[0] + h), 6)]
            begr.append(f"{name}: halbe Breite um den einzigen Erfolg {spec['bereich']} (Regel 2)")
        elif "werte" in spec and erfolge:
            behalten = [w for w in spec["werte"] if w in ok]
            if behalten and behalten != spec["werte"]:
                spec["werte"] = behalten
                begr.append(f"{name}: nur Werte mit Erfolg {behalten} (Regel 4)")

    if not erfolge and recs:
        haupt = next(iter(b["fehlergruende"]), None)

        def zur_mitte(name: str, ziel: float) -> None:
            s = neu_p.get(name)
            if s and "bereich" in s:
                a, c = s["bereich"]
                s["bereich"] = [_mitte(a, ziel), _mitte(c, ziel)]
                begr.append(f"{name}: Bereich zum Wert {ziel} halbiert {s['bereich']} (Regel 3, {haupt})")

        if haupt == "nicht_gegriffen":
            for a in "xyz":
                zur_mitte(f"greif_versatz_{a}_m", 0.0)
        elif haupt == "gefallen":
            for name in ("greifkraft_n", "reibung_finger", "reibung_glas"):
                s = neu_p.get(name)
                if s and "bereich" in s:
                    s["bereich"][0] = _mitte(*s["bereich"])
                    begr.append(f"{name}: untere Grenze auf die Mitte gehoben {s['bereich']} (Regel 3, gefallen)")
        elif haupt == "kollision_arm_tisch":
            s = neu_p.setdefault("greif_versatz_z_m", {"fest": 0.0})
            lo, hi = ex.PARAMETER["greif_versatz_z_m"][1]
            for k in ("bereich", "fest"):
                if k in s:
                    s[k] = [min(hi, x + 0.005) for x in s[k]] if k == "bereich" else min(hi, s[k] + 0.005)
            begr.append(f"greif_versatz_z_m: 5 mm hoeher greifen {s} (Regel 3, kollision_arm_tisch)")
        elif haupt == "durchdringung":
            s = neu_p.get("greifkraft_n")
            if s and "bereich" in s:
                s["bereich"][1] = _mitte(*s["bereich"])
                begr.append(f"greifkraft_n: obere Grenze auf die Mitte gesenkt {s['bereich']} (Regel 3, durchdringung)")
        elif haupt == "planung_fehlgeschlagen":
            for name in ("glas_x_m", "glas_y_m"):
                if name in std:
                    zur_mitte(name, std[name])

    neu_seed = int(alt.get("seed", 0)) + 1
    if not begr:
        begr.append(f"keine Regel griff: Zufallssuche im gleichen Raum mit Seed {neu_seed} (Regel 5)")
    stamm = alt["name"].rsplit("-n", 1)
    folge = int(stamm[1]) + 1 if len(stamm) == 2 and stamm[1].isdigit() else 1
    neu = {
        "name": f"{stamm[0] if folge > 1 else alt['name']}-n{folge}",
        "beschreibung": f"Vorschlag aus {man.get('run', run.name)}: {b['erfolge']}/{b['versuche_fertig']} Erfolge",
        "backend": alt.get("backend", "newton"), "szene": alt.get("szene"), "roboter": alt.get("roboter"),
        "versuche": alt["versuche"], "seed": neu_seed, "parameter": neu_p,
        "stueck": alt.get("stueck", {"max_minuten": 25.0}),
        "abgeleitet_von": {"run": man.get("run", run.name), "konfig_hash": man["konfig_hash"]},
        "begruendung": begr,
    }
    ex.aus_dict(neu)  # muss eine gueltige Experimentdatei sein
    return neu
