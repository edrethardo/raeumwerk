"""Simulations-Implementierung der Schnittstellen aus ``basis`` (Newton).

Die Klassen arbeiten auf einem laufenden ``greifen.sim_newton.Versuchslauf``:
``setze_soll`` schreibt in dessen Soll-Puffer (``tq``/``tqd``, Index je Gelenk
``di``), der Lauf uebertraegt sie vor jedem Physikschritt an Newton. Gelesen
wird aus dem aktuellen Zustand (``zustand.joint_q``/``body_q``). Kein Import
von Newton hier: die Klassen brauchen nur Objekte mit ``.numpy()``.
"""
from __future__ import annotations

from typing import Dict, Optional, Sequence

from .basis import CameraBackend, GripperBackend, RobotBackend

FINGER = ("finger_left", "finger_right")


class SimRobot(RobotBackend):
    def __init__(self, lauf, gelenke: Sequence[str]):
        self.lauf = lauf
        self._namen = [n for n in gelenke if n not in FINGER]

    def gelenknamen(self) -> Sequence[str]:
        return list(self._namen)

    def gelenke(self) -> Dict[str, float]:
        jq = self.lauf.zustand.joint_q.numpy()
        return {n: float(jq[self.lauf.qi[n]]) for n in self._namen}

    def setze_soll(self, q: Dict[str, float], qd: Optional[Dict[str, float]] = None) -> None:
        for n, v in q.items():
            if n not in self._namen:
                raise KeyError(f"unbekanntes Gelenk {n!r}")
            self.lauf.tq[self.lauf.di[n]] = v
            self.lauf.tqd[self.lauf.di[n]] = (qd or {}).get(n, 0.0)

    def halt(self) -> None:
        self.setze_soll(self.gelenke())


class SimGripper(GripperBackend):
    """Zwei Finger mit eigenem PD-Antrieb und gleichem Ziel (siehe docs/greifdemo.md)."""

    def __init__(self, lauf, min_oeffnung: float):
        self.lauf = lauf
        self.min_oeffnung = float(min_oeffnung)

    def oeffnung(self) -> float:
        jq = self.lauf.zustand.joint_q.numpy()
        return self.min_oeffnung + sum(float(jq[self.lauf.qi[f]]) for f in FINGER)

    def setze_soll(self, finger_q: float, finger_qd: float = 0.0) -> None:
        for f in FINGER:
            self.lauf.tq[self.lauf.di[f]] = finger_q
            self.lauf.tqd[self.lauf.di[f]] = finger_qd


class SimCamera(CameraBackend):
    """Ideale Wahrnehmung: wahre Lage aus dem Modell, keine Bilder (kein Renderer)."""

    def __init__(self, lauf, koerper: Dict[str, int]):
        self.lauf = lauf
        self.koerper = dict(koerper)

    def objektlage(self, name: str):
        if name not in self.koerper:
            return None
        tr = self.lauf.zustand.body_q.numpy()[self.koerper[name]]
        return (tuple(float(x) for x in tr[:3]), tuple(float(x) for x in tr[3:7]))

    def bild(self):
        return None
