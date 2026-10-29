"""Experimentdatei: Szene, Roboter, Parameterraum, Anzahl Versuche.

Beispiel (``experimente/beispiel.yaml``)::

    name: beispiel
    backend: newton            # newton | attrappe (Testdouble ohne Simulator)
    szene: config/scene.yaml   # relativ zum Repo
    roboter: config/robot.yaml
    versuche: 8
    seed: 31                   # Seed der Stichprobe (nicht der IK)
    parameter:                 # nicht genannte Parameter: Wert aus der Szene
      greifkraft_n: {bereich: [3.0, 20.0]}     # gleichverteilt
      reibung_glas: {fest: 0.3}                # fest (auch: reibung_glas: 0.3)
      glas_x_m: {werte: [0.54, 0.56]}          # Auswahl
    stueck:
      max_minuten: 25          # Zeitbudget je Stueck (raeumwerk run --max-minuten)

Die Versuchsliste ist deterministisch (``random.Random(seed)``, Parameter in
alphabetischer Reihenfolge) und wird ins Manifest geschrieben, damit ein
fortgesetzter Lauf dieselben Versuche faehrt.
"""
from __future__ import annotations

import copy
import hashlib
import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parents[1]
BACKENDS = ("newton", "attrappe")

# Parameter -> (Beschreibung, erlaubte Grenzen)
PARAMETER: Dict[str, Tuple[str, Tuple[float, float]]] = {
    "glas_x_m": ("Glasstart x (Schienenrichtung)", (0.25, 1.15)),
    "glas_y_m": ("Glasstart y (quer)", (0.27, 0.57)),
    "greif_versatz_x_m": ("Greifpunkt neben der Glasmitte, x", (-0.10, 0.10)),
    "greif_versatz_y_m": ("Greifpunkt neben der Glasmitte, y", (-0.10, 0.10)),
    "greif_versatz_z_m": ("Greifpunkt hoeher/tiefer", (-0.03, 0.05)),
    "reibung_finger": ("Reibwert Fingerbelag", (0.0, 2.0)),
    "reibung_glas": ("Reibwert Glas", (0.0, 2.0)),
    "reibung_tisch": ("Reibwert Tisch", (0.0, 2.0)),
    "greifkraft_n": ("Greifkraft je Finger (<= Antriebsgrenze)", (0.5, 50.0)),
}


class ExperimentFehler(ValueError):
    pass


@dataclass
class Experiment:
    name: str
    backend: str
    szene: str
    roboter: str
    versuche: int
    seed: int
    parameter: Dict[str, Dict[str, Any]]
    stueck_max_minuten: float = 25.0
    beschreibung: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    def als_dict(self) -> Dict[str, Any]:
        d = {"name": self.name, "backend": self.backend, "szene": self.szene, "roboter": self.roboter,
             "versuche": self.versuche, "seed": self.seed, "parameter": self.parameter,
             "stueck": {"max_minuten": self.stueck_max_minuten}}
        if self.beschreibung:
            d["beschreibung"] = self.beschreibung
        d.update(self.extra)
        return d

    def pfad(self, rel: str) -> Path:
        p = Path(rel)
        return p if p.is_absolute() else REPO / p


def _spec(name: str, roh: Any) -> Dict[str, Any]:
    lo, hi = PARAMETER[name][1]

    def zahl(x):
        if isinstance(x, bool) or not isinstance(x, (int, float)):
            raise ExperimentFehler(f"{name}: Zahl erwartet, nicht {x!r}")
        if not lo <= float(x) <= hi:
            raise ExperimentFehler(f"{name}: {x} ausserhalb der erlaubten Grenzen [{lo}, {hi}]")
        return float(x)

    if isinstance(roh, (int, float)) and not isinstance(roh, bool):
        return {"fest": zahl(roh)}
    if not isinstance(roh, dict) or len(roh) != 1:
        raise ExperimentFehler(f"{name}: genau einer von fest|bereich|werte erwartet")
    art, wert = next(iter(roh.items()))
    if art == "fest":
        return {"fest": zahl(wert)}
    if art == "bereich":
        if not isinstance(wert, list) or len(wert) != 2:
            raise ExperimentFehler(f"{name}: bereich braucht [unten, oben]")
        a, b = zahl(wert[0]), zahl(wert[1])
        if a > b:
            raise ExperimentFehler(f"{name}: bereich unten > oben")
        return {"bereich": [a, b]}
    if art == "werte":
        if not isinstance(wert, list) or not wert:
            raise ExperimentFehler(f"{name}: werte braucht eine nicht leere Liste")
        return {"werte": [zahl(x) for x in wert]}
    raise ExperimentFehler(f"{name}: unbekannte Angabe {art!r} (fest|bereich|werte)")


def aus_dict(d: Dict[str, Any]) -> Experiment:
    if not isinstance(d, dict):
        raise ExperimentFehler("Experimentdatei: Abbildung erwartet")
    bekannt = {"name", "backend", "szene", "roboter", "versuche", "seed", "parameter", "stueck",
               "beschreibung", "abgeleitet_von", "begruendung"}
    unbekannt = sorted(set(d) - bekannt)
    if unbekannt:
        raise ExperimentFehler(f"unbekannte Schluessel: {', '.join(unbekannt)}")
    name = str(d.get("name") or "")
    if not name or not all(c.isalnum() or c in "-_." for c in name):
        raise ExperimentFehler("name fehlt oder enthaelt andere Zeichen als A-Z a-z 0-9 - _ .")
    backend = d.get("backend", "newton")
    if backend not in BACKENDS:
        raise ExperimentFehler(f"backend {backend!r} unbekannt ({'|'.join(BACKENDS)})")
    n = d.get("versuche")
    if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= 1000:
        raise ExperimentFehler("versuche: ganze Zahl 1..1000")
    seed = d.get("seed", 0)
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ExperimentFehler("seed: ganze Zahl")
    params = d.get("parameter") or {}
    if not isinstance(params, dict):
        raise ExperimentFehler("parameter: Abbildung erwartet")
    falsch = sorted(set(params) - set(PARAMETER))
    if falsch:
        raise ExperimentFehler(f"unbekannte Parameter: {', '.join(falsch)} (erlaubt: {', '.join(sorted(PARAMETER))})")
    stueck = d.get("stueck") or {}
    mm = float(stueck.get("max_minuten", 25.0))
    if not 0 < mm <= 30:
        raise ExperimentFehler("stueck.max_minuten: 0 < x <= 30 (Stuecke hoechstens 30 min)")
    extra = {k: d[k] for k in ("abgeleitet_von", "begruendung") if k in d}
    return Experiment(name=name, backend=backend, szene=str(d.get("szene", "config/scene.yaml")),
                      roboter=str(d.get("roboter", "config/robot.yaml")), versuche=n, seed=seed,
                      parameter={k: _spec(k, params[k]) for k in sorted(params)},
                      stueck_max_minuten=mm, beschreibung=str(d.get("beschreibung", "")), extra=extra)


def laden(pfad: Path | str) -> Experiment:
    import yaml

    p = Path(pfad)
    try:
        d = yaml.safe_load(p.read_text(encoding="utf-8"))
    except OSError as e:
        raise ExperimentFehler(f"Experimentdatei nicht lesbar: {e}") from e
    return aus_dict(d)


def versuchsliste(exp: Experiment) -> List[Dict[str, Any]]:
    """``[{"nr": i, "parameter": {name: wert}}]`` - nur die im Experiment genannten Parameter."""
    rng = random.Random(exp.seed)
    out = []
    for i in range(exp.versuche):
        p: Dict[str, float] = {}
        for name in sorted(exp.parameter):
            s = exp.parameter[name]
            if "fest" in s:
                p[name] = s["fest"]
            elif "bereich" in s:
                a, b = s["bereich"]
                p[name] = round(rng.uniform(a, b), 6)
            else:
                p[name] = s["werte"][rng.randrange(len(s["werte"]))]
        out.append({"nr": i, "parameter": p})
    return out


def sha256_datei(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def konfig_hash(exp: Experiment) -> Tuple[str, Dict[str, str]]:
    """Hash ueber Experiment (geparst) und die Bytes von Szene und Roboter."""
    dateien = {"szene": sha256_datei(exp.pfad(exp.szene)), "roboter": sha256_datei(exp.pfad(exp.roboter))}
    kern = {k: v for k, v in exp.als_dict().items() if k not in ("beschreibung", "begruendung")}
    roh = json.dumps({"experiment": kern, "dateien": dateien}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(roh.encode()).hexdigest(), dateien


def szene_fuer(basis, parameter: Dict[str, float]):
    """Kopie der Szene mit den Parametern eines Versuchs."""
    sz = copy.deepcopy(basis)
    if "reibung_finger" in parameter:
        sz.kontakt["reibung_finger"] = parameter["reibung_finger"]
    if "reibung_glas" in parameter:
        sz.glas["reibung"] = parameter["reibung_glas"]
    if "reibung_tisch" in parameter:
        sz.tisch["reibung"] = parameter["reibung_tisch"]
    if "greifkraft_n" in parameter:
        sz.greifen["greifkraft_n"] = parameter["greifkraft_n"]
    x, y = (float(v) for v in sz.glas["start_xy_m"])
    sz.glas["start_xy_m"] = [parameter.get("glas_x_m", x), parameter.get("glas_y_m", y)]
    return sz


def greif_versatz(parameter: Dict[str, float]) -> Tuple[float, float, float]:
    return tuple(float(parameter.get(f"greif_versatz_{a}_m", 0.0)) for a in "xyz")  # type: ignore[return-value]


def standardwerte(sz) -> Dict[str, float]:
    """Werte der Szene fuer alle Parameter (fuer Manifest und Vorschlag)."""
    return {"glas_x_m": float(sz.glas["start_xy_m"][0]), "glas_y_m": float(sz.glas["start_xy_m"][1]),
            "greif_versatz_x_m": 0.0, "greif_versatz_y_m": 0.0, "greif_versatz_z_m": 0.0,
            "reibung_finger": float(sz.kontakt["reibung_finger"]), "reibung_glas": float(sz.glas["reibung"]),
            "reibung_tisch": float(sz.tisch["reibung"]), "greifkraft_n": float(sz.greifen["greifkraft_n"])}


def nach_yaml(d: Any, einrueck: int = 0) -> str:
    """Kleiner YAML-Schreiber fuer Experimentdateien (dict/list/str/Zahl), ohne pyyaml."""
    sp = "  " * einrueck

    def skalar(v):
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, (int, float)):
            return repr(v)
        if isinstance(v, list) and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v):
            return "[" + ", ".join(repr(x) for x in v) + "]"
        if isinstance(v, dict) and len(v) == 1 and isinstance(next(iter(v.values())), (int, float, list)) \
                and not isinstance(next(iter(v.values())), bool):
            k, w = next(iter(v.items()))
            return "{" + f"{k}: {skalar(w)}" + "}"
        if isinstance(v, str):
            return json.dumps(v, ensure_ascii=False)
        return None

    zeilen = []
    if isinstance(d, dict):
        for k, v in d.items():
            s = skalar(v)
            if s is not None:
                zeilen.append(f"{sp}{k}: {s}")
            else:
                zeilen.append(f"{sp}{k}:")
                zeilen.append(nach_yaml(v, einrueck + 1))
    elif isinstance(d, list):
        for v in d:
            s = skalar(v)
            zeilen.append(f"{sp}- {s}" if s is not None else f"{sp}-\n" + nach_yaml(v, einrueck + 1))
    else:
        zeilen.append(sp + (skalar(d) or "null"))
    return "\n".join(zeilen)


def optional_float(x: Any) -> Optional[float]:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None
