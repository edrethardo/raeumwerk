"""Stub fuer den echten ReBeL. Bewegt ausdruecklich NICHTS.

Es gibt keinen Treiber: Kein Code in diesem Modul oeffnet eine Verbindung,
einen Port oder ein Geraet. Jede Bewegung (``setze_soll``) wird abgelehnt:

* ohne ausdrueckliche Freigabe-Konfiguration mit ``BewegungVerweigert``
  ("keine Freigabe");
* auch mit Freigabe mit ``BewegungVerweigert`` ("kein Treiber"), weil der
  Stub nichts ansteuern kann. Die Freigabe-Pruefung ist schon da, damit ein
  spaeterer Treiber sie nicht vergisst.

Ausdrueckliche Freigabe heisst: eine Konfiguration (Datei oder ``dict``) mit

    hardware:
      bewegung_freigegeben: true      # genau der bool true, kein "ja", keine 1
      freigabe_durch: <Name>          # wer freigegeben hat (nicht leer)

``halt()`` ist immer erlaubt und tut im Stub nichts. Lesen liefert nichts
(``BewegungVerweigert`` ist hier falsch, deshalb ``NichtVerbunden``).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Union

from .basis import BewegungVerweigert, CameraBackend, GripperBackend, RobotBackend

GELENKE = ["joint1", "joint2", "joint3", "joint4", "joint5", "joint6", "axis7"]


class NichtVerbunden(RuntimeError):
    """Der Stub hat keine Verbindung zu echter Hardware."""


def freigabe_aus(konfig: Union[None, str, Path, Mapping[str, Any]]) -> Dict[str, Any]:
    """Liest die Freigabe; fehlend/ungueltig = keine Freigabe (nie eine Ausnahme)."""
    if konfig is None:
        return {"freigegeben": False, "grund": "keine Freigabe-Konfiguration"}
    daten: Any = konfig
    if isinstance(konfig, (str, Path)):
        p = Path(konfig)
        if not p.is_file():
            return {"freigegeben": False, "grund": f"Freigabe-Datei fehlt: {p.name}"}
        try:
            import yaml
            daten = yaml.safe_load(p.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            return {"freigegeben": False, "grund": f"Freigabe-Datei unlesbar: {type(e).__name__}"}
    hw = daten.get("hardware") if isinstance(daten, Mapping) else None
    if not isinstance(hw, Mapping):
        return {"freigegeben": False, "grund": "Abschnitt 'hardware' fehlt"}
    if hw.get("bewegung_freigegeben") is not True:
        return {"freigegeben": False, "grund": "hardware.bewegung_freigegeben ist nicht true"}
    durch = hw.get("freigabe_durch")
    if not isinstance(durch, str) or not durch.strip():
        return {"freigegeben": False, "grund": "hardware.freigabe_durch fehlt"}
    return {"freigegeben": True, "grund": "", "durch": durch.strip()}


class _Freigabe:
    def __init__(self, konfig=None):
        self.freigabe = freigabe_aus(konfig)
        self.abgelehnt = 0  # Zaehler fuer Tests/Protokoll

    def _bewegen(self, was: str) -> None:
        self.abgelehnt += 1
        if not self.freigabe["freigegeben"]:
            raise BewegungVerweigert(f"{was} verweigert: {self.freigabe['grund']}")
        raise BewegungVerweigert(f"{was} verweigert: Hardware-Stub ohne Treiber, bewegt nichts")


class HardwareRobot(_Freigabe, RobotBackend):
    def gelenknamen(self) -> Sequence[str]:
        return list(GELENKE)

    def gelenke(self) -> Dict[str, float]:
        raise NichtVerbunden("Hardware-Stub: keine Verbindung zum Roboter")

    def setze_soll(self, q, qd=None) -> None:
        self._bewegen("Roboterbewegung")

    def halt(self) -> None:
        return None


class HardwareGripper(_Freigabe, GripperBackend):
    def oeffnung(self) -> float:
        raise NichtVerbunden("Hardware-Stub: keine Verbindung zum Greifer")

    def setze_soll(self, finger_q: float, finger_qd: float = 0.0) -> None:
        self._bewegen("Greiferbewegung")


class HardwareCamera(CameraBackend):
    """Platzhalter fuer die Eye-in-Hand-Kamera (geplant, siehe docs/architektur.md)."""

    def objektlage(self, name: str) -> Optional[tuple]:
        raise NichtVerbunden("Hardware-Stub: keine Kamera angebunden")

    def bild(self):
        raise NichtVerbunden("Hardware-Stub: keine Kamera angebunden")
