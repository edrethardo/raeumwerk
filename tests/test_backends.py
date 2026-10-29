"""Schnittstellen Roboter/Greifer/Kamera: Sim-Implementierung und Hardware-Stub.

Laeuft ohne Simulator (die Sim-Klassen bekommen einen Ersatz fuer den
Newton-Versuchslauf). Der Hardware-Stub muss jede Bewegung verweigern: ohne
ausdrueckliche Freigabe-Konfiguration ("keine Freigabe") und auch mit ihr
("ohne Treiber").
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from raeumwerk.backends import BewegungVerweigert, basis, hardware, sim

REPO = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("klasse, basisklasse", [
    (sim.SimRobot, basis.RobotBackend), (sim.SimGripper, basis.GripperBackend), (sim.SimCamera, basis.CameraBackend),
    (hardware.HardwareRobot, basis.RobotBackend), (hardware.HardwareGripper, basis.GripperBackend),
    (hardware.HardwareCamera, basis.CameraBackend),
])
def test_backends_implement_interfaces(klasse, basisklasse):
    assert issubclass(klasse, basisklasse)
    assert not getattr(klasse, "__abstractmethods__", None)


def test_interfaces_are_abstract():
    for k in (basis.RobotBackend, basis.GripperBackend, basis.CameraBackend):
        with pytest.raises(TypeError):
            k()  # type: ignore[abstract]


class _Arr:
    def __init__(self, werte):
        self.werte = list(werte)

    def numpy(self):
        return self.werte


class _Lauf:
    """Minimaler Ersatz fuer greifen.sim_newton.Versuchslauf (ohne Newton)."""

    def __init__(self):
        names = ["joint1", "axis7", "finger_left", "finger_right"]
        self.qi = {n: i for i, n in enumerate(names)}
        self.di = {n: i for i, n in enumerate(names)}
        self.tq, self.tqd = [0.0] * 4, [0.0] * 4

        class Z:
            joint_q = _Arr([0.1, 0.2, 0.01, 0.012])
            body_q = _Arr([[1, 2, 3, 0, 0, 0, 1]])
        self.zustand = Z()


def test_sim_backends_write_targets_and_read_state():
    lf = _Lauf()
    r = sim.SimRobot(lf, ["joint1", "axis7", "finger_left"])
    assert list(r.gelenknamen()) == ["joint1", "axis7"]
    r.setze_soll({"joint1": 0.5, "axis7": 0.3}, {"joint1": 0.1})
    assert lf.tq[:2] == [0.5, 0.3] and lf.tqd[:2] == [0.1, 0.0]
    with pytest.raises(KeyError):
        r.setze_soll({"finger_left": 0.0})  # Finger nur ueber den Greifer
    assert r.gelenke() == {"joint1": 0.1, "axis7": 0.2}
    r.halt()
    assert lf.tq[:2] == [0.1, 0.2] and lf.tqd[:2] == [0.0, 0.0]
    g = sim.SimGripper(lf, 0.005)
    g.setze_soll(0.03, 0.01)
    assert lf.tq[2:] == [0.03, 0.03] and lf.tqd[2:] == [0.01, 0.01]
    assert g.oeffnung() == pytest.approx(0.005 + 0.022)
    k = sim.SimCamera(lf, {"glas": 0})
    assert k.objektlage("glas") == ((1.0, 2.0, 3.0), (0.0, 0.0, 0.0, 1.0))
    assert k.objektlage("teller") is None and k.bild() is None


def test_newton_loop_drives_only_through_interfaces():
    """Der Newton-Ablauf schreibt Sollwerte nur ueber SimRobot/SimGripper."""
    quelle = (REPO / "greifen" / "sim_newton.py").read_text()
    schleife = quelle.split("for step in range(nsteps):", 1)[1].split("pipeline.collide(st0, contacts)\n        messen(nsteps", 1)[0]
    assert "self.roboter.setze_soll(" in schleife and "self.greifer.setze_soll(" in schleife
    assert "tq[" not in schleife and "tqd[" not in schleife


# --- Hardware-Stub ----------------------------------------------------------

UNGUELTIG = [
    None,
    {},
    {"hardware": None},
    {"hardware": {}},
    {"hardware": {"bewegung_freigegeben": False, "freigabe_durch": "x"}},
    {"hardware": {"bewegung_freigegeben": "true", "freigabe_durch": "x"}},
    {"hardware": {"bewegung_freigegeben": "ja", "freigabe_durch": "x"}},
    {"hardware": {"bewegung_freigegeben": 1, "freigabe_durch": "x"}},
    {"hardware": {"bewegung_freigegeben": True}},
    {"hardware": {"bewegung_freigegeben": True, "freigabe_durch": "  "}},
    {"bewegung_freigegeben": True, "freigabe_durch": "x"},
    "gibt-es-nicht.yaml",
]


@pytest.mark.parametrize("konfig", UNGUELTIG)
def test_hardware_stub_refuses_every_motion_without_release(konfig, tmp_path):
    """Fertig-Haken: ohne ausdrueckliche Freigabe-Konfiguration wird jede Bewegung verweigert."""
    if isinstance(konfig, str):
        konfig = tmp_path / konfig
    robot, greifer = hardware.HardwareRobot(konfig), hardware.HardwareGripper(konfig)
    assert robot.freigabe["freigegeben"] is False
    bewegungen = [lambda: robot.setze_soll({"joint1": 0.1}), lambda: robot.setze_soll({}, {}),
                  lambda: greifer.setze_soll(0.01), lambda: greifer.setze_soll(0.0, 0.1)]
    for b in bewegungen:
        with pytest.raises(BewegungVerweigert, match="verweigert: (keine|hardware|Abschnitt|Freigabe)"):
            b()
    assert robot.abgelehnt == 2 and greifer.abgelehnt == 2
    robot.halt()  # Anhalten ist immer erlaubt


def test_hardware_stub_refuses_even_with_release(tmp_path):
    pytest.importorskip("yaml")
    datei = tmp_path / "hardware.yaml"
    datei.write_text("hardware:\n  bewegung_freigegeben: true\n  freigabe_durch: Testperson\n")
    for konfig in (datei, {"hardware": {"bewegung_freigegeben": True, "freigabe_durch": "Testperson"}}):
        r = hardware.HardwareRobot(konfig)
        assert r.freigabe == {"freigegeben": True, "grund": "", "durch": "Testperson"}
        with pytest.raises(BewegungVerweigert, match="ohne Treiber"):
            r.setze_soll({"joint1": 0.1})
        with pytest.raises(BewegungVerweigert, match="ohne Treiber"):
            hardware.HardwareGripper(konfig).setze_soll(0.01)


def test_hardware_stub_has_no_io_and_reads_nothing():
    quelle = (REPO / "raeumwerk" / "backends" / "hardware.py").read_text()
    for verboten in ("import socket", "import serial", "requests", "urllib", "subprocess", "open("):
        assert verboten not in quelle, verboten
    with pytest.raises(hardware.NichtVerbunden):
        hardware.HardwareRobot().gelenke()
    with pytest.raises(hardware.NichtVerbunden):
        hardware.HardwareGripper().oeffnung()
    with pytest.raises(hardware.NichtVerbunden):
        hardware.HardwareCamera().bild()


def test_hardware_unreadable_release_file_is_no_release(tmp_path):
    pytest.importorskip("yaml")
    datei = tmp_path / "hw.yaml"
    datei.write_text("hardware: [unvollstaendig\n")
    assert hardware.freigabe_aus(datei)["freigegeben"] is False


def test_backends_import_without_simulator():
    code = ("import sys; sys.modules['newton'] = None; sys.modules['warp'] = None; "
            "import raeumwerk.backends.sim, raeumwerk.backends.hardware")
    r = subprocess.run([sys.executable, "-c", code], cwd=str(REPO), capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
