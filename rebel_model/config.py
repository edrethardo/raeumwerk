"""Laedt ``config/robot.yaml`` und liefert die Zahlenwerte ohne Quellenangaben."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

REPO = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO / "config" / "robot.yaml"


def _v(node: Any) -> Any:
    """``{wert: x, src: ...}`` -> x; alles andere unveraendert."""
    if isinstance(node, dict) and "wert" in node:
        return node["wert"]
    return node


@dataclass
class Gelenk:
    name: str
    achse: List[float]
    unten: float  # rad
    oben: float  # rad
    src: str


@dataclass
class RobotConfig:
    raw: Dict[str, Any]
    arm: Dict[str, Any] = field(default_factory=dict)
    achse7: Dict[str, Any] = field(default_factory=dict)
    greifer: Dict[str, Any] = field(default_factory=dict)
    gelenke: List[Gelenk] = field(default_factory=list)
    massen: Dict[str, float] = field(default_factory=dict)

    # --- abgeleitete Groessen ----------------------------------------------
    @property
    def min_oeffnung(self) -> float:
        return self.greifer["max_oeffnung_m"] - self.greifer["hub_gesamt_m"]

    @property
    def finger_hub(self) -> float:
        """Weg je Finger (Gelenkgrenze oben)."""
        return self.greifer["hub_gesamt_m"] / 2.0

    @property
    def greifer_masse(self) -> float:
        return self.greifer["masse_kg"] + 2.0 * self.greifer["finger_masse_kg"]

    @property
    def nutzlast_test(self) -> float:
        """Nutzlast fuer den Backend-Test: maximale Nutzlast minus Greifer."""
        return max(0.0, self.arm["nutzlast_max_kg"] - self.greifer_masse)

    def quelle(self, abschnitt: str, schluessel: str) -> str:
        node = self.raw[abschnitt][schluessel]
        return node.get("src", "") if isinstance(node, dict) else ""


def load(path: Path | str | None = None) -> RobotConfig:
    import yaml  # erst hier, damit ``import rebel_model`` ohne PyYAML geht

    p = Path(path) if path else DEFAULT_CONFIG
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    cfg = RobotConfig(raw=raw)
    for sect in ("arm", "achse7", "greifer"):
        d = {}
        for k, node in raw[sect].items():
            if k in ("gelenke", "massen_kg"):
                continue
            d[k] = _v(node)
        setattr(cfg, sect, d)
    for g in raw["arm"]["gelenke"]:
        cfg.gelenke.append(
            Gelenk(
                name=g["name"],
                achse=[float(a) for a in g["achse"]],
                unten=math.radians(float(g["unten_grad"])),
                oben=math.radians(float(g["oben_grad"])),
                src=g.get("src", ""),
            )
        )
    cfg.massen = {k: float(v) for k, v in raw["arm"]["massen_kg"].items() if k != "src"}
    return cfg
