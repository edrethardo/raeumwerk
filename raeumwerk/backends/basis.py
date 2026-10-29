"""Abstrakte Schnittstellen zwischen Ablauf und Roboter (Simulation oder Hardware).

Die Ablaufplanung (``greifen.plan``) erzeugt Soll-Trajektorien; wer sie
ausfuehrt, sieht nur diese drei Schnittstellen. Die Simulation implementiert
sie in ``raeumwerk.backends.sim`` (Newton), fuer echte Hardware gibt es nur
den Stub ``raeumwerk.backends.hardware``, der nichts bewegt.

Einheiten: Gelenke in rad (Drehgelenke) bzw. m (7. Achse, Finger),
Lagen in m, Kraefte in N, Zeiten in s.
"""
from __future__ import annotations

import abc
from typing import Dict, Optional, Sequence, Tuple  # noqa: F401


class BewegungVerweigert(RuntimeError):
    """Eine Bewegung wurde abgelehnt (fehlende Freigabe, kein Treiber)."""


class RobotBackend(abc.ABC):
    """Arm mit 6 Gelenken und 7. Achse (ohne Greifer)."""

    @abc.abstractmethod
    def gelenknamen(self) -> Sequence[str]:
        """Namen der gesteuerten Gelenke in der Reihenfolge von ``gelenke()``."""

    @abc.abstractmethod
    def gelenke(self) -> Dict[str, float]:
        """Aktuelle Gelenkwerte (gemessen bzw. simuliert)."""

    @abc.abstractmethod
    def setze_soll(self, q: Dict[str, float], qd: Optional[Dict[str, float]] = None) -> None:
        """Soll-Lage (und Soll-Geschwindigkeit als Vorsteuerung) fuer den naechsten Takt."""

    @abc.abstractmethod
    def halt(self) -> None:
        """Sofort anhalten (Soll = Ist, Geschwindigkeit 0)."""


class GripperBackend(abc.ABC):
    """Parallelgreifer; ``oeffnung`` ist der Abstand der Fingerinnenseiten."""

    @abc.abstractmethod
    def oeffnung(self) -> float:
        """Aktuelle Oeffnung in m."""

    @abc.abstractmethod
    def setze_soll(self, finger_q: float, finger_qd: float = 0.0) -> None:
        """Soll-Lage eines Fingers (m ab geschlossen), beide Finger symmetrisch."""


class CameraBackend(abc.ABC):
    """Kamera bzw. Wahrnehmung. In der Simulation die wahre Lage aus dem Modell."""

    @abc.abstractmethod
    def objektlage(self, name: str) -> Optional[Tuple[tuple, tuple]]:
        """Lage (Position, Quaternion x,y,z,w) eines Objekts oder ``None``, wenn nicht gesehen."""

    @abc.abstractmethod
    def bild(self):
        """Farbbild (H x W x 3) oder ``None``, wenn das Backend keine Bilder liefert."""
