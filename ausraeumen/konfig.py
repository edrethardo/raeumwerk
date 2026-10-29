"""Laedt ``config/ausraeumen.yaml`` und baut die Szene fuer einen Versuch.

Ein ``Aufbau`` buendelt alles, was Planung und Simulation brauchen: Masse der
Maschine, Schienenlage, Ausraeum-Parameter und die Abweichungen eines
Versuchs (Glasversatz, Glasgier, Korbauszug, Negativtest).
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from spuelmaschine import masse

REPO = Path(__file__).resolve().parents[1]
DATEI = REPO / "config" / "ausraeumen.yaml"


def roh(path: Path | str | None = None) -> Dict[str, Any]:
    return masse.roh(path, DATEI)


def load(path: Path | str | None = None) -> Dict[str, Any]:
    return masse.werte(roh(path))


@dataclass
class Abweichung:
    """Abweichungen eines Versuchs von der Nennlage (der Planung bekannt)."""
    glas_versatz_xy_m: List[Tuple[float, float]] = field(default_factory=lambda: [(0.0, 0.0)] * 4)
    glas_gier_grad: List[float] = field(default_factory=lambda: [0.0] * 4)
    korbauszug_delta_m: float = 0.0
    verklemmt: Optional[int] = None  # Glasnummer 1..4 im zu schmalen Halter

    def as_dict(self) -> dict:
        return {"glas_versatz_xy_m": [list(v) for v in self.glas_versatz_xy_m],
                "glas_gier_grad": list(self.glas_gier_grad), "korbauszug_delta_m": self.korbauszug_delta_m,
                "verklemmt": self.verklemmt}


@dataclass
class Aufbau:
    m: Dict[str, Any]       # config/spuelmaschine.yaml
    sc: Dict[str, Any]      # config/scene_spuelmaschine.yaml
    a: Dict[str, Any]       # config/ausraeumen.yaml
    abw: Abweichung

    @property
    def auszug(self) -> float:
        return float(self.sc["pose"]["oberkorb_auszug_m"]) + self.abw.korbauszug_delta_m


def setze(a: Dict[str, Any], zuweisungen) -> Dict[str, Any]:
    """``["greifer.greifkraft_n=40", ...]`` in die Werte von ``config/ausraeumen.yaml``
    schreiben (zum Ausprobieren; die Zuweisungen landen im Versuchs-JSON)."""
    import json as _json
    for z in zuweisungen or []:
        pfad, wert = z.split("=", 1)
        teile = pfad.split(".")
        knoten = a
        for t in teile[:-1]:
            knoten = knoten[t]
        if teile[-1] not in knoten:
            raise KeyError(f"unbekannter Wert {pfad}")
        knoten[teile[-1]] = _json.loads(wert)
    return a


def aufbau(abw: Optional[Abweichung] = None, m: Optional[Dict] = None, sc: Optional[Dict] = None,
           a: Optional[Dict] = None, zuweisungen=None) -> Aufbau:
    m = copy.deepcopy(m or masse.load())
    sc = copy.deepcopy(sc or masse.load_szene())
    a = setze(copy.deepcopy(a or load()), zuweisungen)
    abw = abw or Abweichung()
    # Variation des Korbauszugs um den Nennwert: der Nennwert ist der
    # Anschlag; +delta steht fuer eine Maschine mit etwas laengerem Auszug
    soll = float(sc["pose"]["oberkorb_auszug_m"]) + abw.korbauszug_delta_m
    if soll > m["oberkorb"]["auszug_max_m"]:
        m["oberkorb"]["auszug_max_m"] = soll
    return Aufbau(m, sc, a, abw)


# Parameter von ``raeumwerk run`` (Backend ausraeumen) -> Abweichung; Grenzen
# grosszuegiger als der Variationslauf (+-5 mm, +-3 Grad, +-1 cm)
PARAMETER = {**{f"glas{i}_{a}_m": (f"Glas {i}: Versatz im Slot, {a[1]}", (-0.01, 0.01))
                for i in range(1, 5) for a in ("dx", "dy")},
             **{f"glas{i}_gier_grad": (f"Glas {i}: Drehung um die Glasachse", (-10.0, 10.0)) for i in range(1, 5)},
             "korbauszug_delta_m": ("Korbauszug um den Nennwert", (-0.02, 0.02))}


def abweichung_aus(parameter: Dict[str, float]) -> Abweichung:
    p = {k: float(v) for k, v in parameter.items()}
    return Abweichung([(p.get(f"glas{i}_dx_m", 0.0), p.get(f"glas{i}_dy_m", 0.0)) for i in range(1, 5)],
                      [p.get(f"glas{i}_gier_grad", 0.0) for i in range(1, 5)], p.get("korbauszug_delta_m", 0.0))
