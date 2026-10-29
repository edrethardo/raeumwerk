"""Laedt ``config/spuelmaschine.yaml`` und ``config/scene_spuelmaschine.yaml``.

Beide Dateien folgen dem Schema aus ``config/robot.yaml``: jede Zahl steht als
``{wert: x, src: <quelle|annahme>}``. ``werte`` liefert die Zahlen ohne
Quellen, ``ohne_quelle`` listet Blaetter ohne gueltige Quelle (fuer Tests).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

REPO = Path(__file__).resolve().parents[1]
MASCHINE = REPO / "config" / "spuelmaschine.yaml"
SZENE = REPO / "config" / "scene_spuelmaschine.yaml"


def _strip(node: Any) -> Any:
    if isinstance(node, dict):
        if "wert" in node:
            return node["wert"]
        return {k: _strip(v) for k, v in node.items()}
    return node


def roh(path: Path | str | None = None, standard: Path = MASCHINE) -> Dict[str, Any]:
    import yaml  # erst hier, damit ``import spuelmaschine`` ohne PyYAML geht

    return yaml.safe_load(Path(path or standard).read_text(encoding="utf-8"))


def werte(raw: Dict[str, Any]) -> Dict[str, Any]:
    return {k: _strip(v) for k, v in raw.items() if k != "quellen"}


def ohne_quelle(raw: Dict[str, Any]) -> List[str]:
    """Pfade aller Zahlenblaetter ohne ``src`` aus ``quellen`` oder ``annahme``."""
    erlaubt = set(raw.get("quellen", {})) | {"annahme"}
    fehlt: List[str] = []

    def lauf(node: Any, pfad: str) -> None:
        if isinstance(node, dict):
            if "wert" in node:
                if node.get("src") not in erlaubt:
                    fehlt.append(pfad)
                return
            for k, v in node.items():
                lauf(v, f"{pfad}.{k}" if pfad else k)
        elif isinstance(node, (int, float, list)):
            fehlt.append(pfad)

    for k, v in raw.items():
        if k != "quellen":
            lauf(v, k)
    return fehlt


def load(path: Path | str | None = None) -> Dict[str, Any]:
    """Masse der Maschine (Zahlen ohne Quellen)."""
    return werte(roh(path, MASCHINE))


def load_szene(path: Path | str | None = None) -> Dict[str, Any]:
    """Szene (Schienenlage, Greifparameter, Newton) ohne Quellen."""
    return werte(roh(path, SZENE))
