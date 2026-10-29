"""Laedt ``config/scene.yaml`` (Werte ohne Quellenangaben)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

REPO = Path(__file__).resolve().parents[1]
DEFAULT_SCENE = REPO / "config" / "scene.yaml"


def _strip(node: Any) -> Any:
    if isinstance(node, dict):
        if "wert" in node:
            return node["wert"]
        return {k: _strip(v) for k, v in node.items()}
    return node


@dataclass
class Szene:
    raw: Dict[str, Any]
    tisch: Dict[str, Any]
    glas: Dict[str, Any]
    kontakt: Dict[str, Any]
    greifen: Dict[str, Any]
    bewertung: Dict[str, Any]
    variation: Dict[str, Any]
    negativtest: Dict[str, Any]
    simulation: Dict[str, Any]

    @property
    def tisch_oben(self) -> float:
        return float(self.tisch["groesse_m"][2])

    @property
    def glas_mitte_z(self) -> float:
        """Hoehe der Glasmitte, wenn das Glas auf dem Tisch steht."""
        return self.tisch_oben + self.glas["hoehe_m"] / 2.0

    @property
    def glas_radius(self) -> float:
        return self.glas["durchmesser_m"] / 2.0

    def quelle(self, abschnitt: str, schluessel: str) -> str:
        node = self.raw[abschnitt][schluessel]
        return node.get("src", "") if isinstance(node, dict) else ""


def load(path: Path | str | None = None) -> Szene:
    import yaml

    raw = yaml.safe_load(Path(path or DEFAULT_SCENE).read_text(encoding="utf-8"))
    parts = {k: _strip(raw[k]) for k in ("tisch", "glas", "kontakt", "greifen", "bewertung",
                                         "variation", "negativtest", "simulation")}
    return Szene(raw=raw, **parts)
