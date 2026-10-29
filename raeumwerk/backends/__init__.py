"""Roboter-Schnittstellen: Simulation (Newton) und Hardware-Stub.

* ``basis``    abstrakte Klassen ``RobotBackend``, ``GripperBackend``, ``CameraBackend``
* ``sim``      Implementierung auf einem Newton-Versuchslauf
* ``hardware`` Stub fuer den echten Roboter, verweigert jede Bewegung
"""
from .basis import BewegungVerweigert, CameraBackend, GripperBackend, RobotBackend

__all__ = ["BewegungVerweigert", "CameraBackend", "GripperBackend", "RobotBackend"]
