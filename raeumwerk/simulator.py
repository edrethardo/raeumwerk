"""Versuchs-Ausfuehrer fuer ``raeumwerk run``.

* ``NewtonSimulator``  echte Physik (``greifen.sim_newton``), eine frische
  Simulation je Versuch; braucht Newton/Warp/numpy.
* ``Attrappe``         Testdouble ohne Simulator: leitet Messwerte mit
  einfachen Formeln aus den Parametern ab und bewertet sie mit derselben
  ``greifen.bewertung``. Nur fuer Tests der Job-Mechanik (Stuecke,
  Checkpoints, Abbruch), nicht als Physik zu lesen.

Beide liefern je Versuch ein ``dict`` im Format von ``versuch-NN.json`` der
Greifdemo, ergaenzt um ``parameter``.
"""
from __future__ import annotations

import math
import os
import time
from typing import Any, Dict

from . import experiment as ex


class NewtonSimulator:
    def __init__(self, exp: ex.Experiment, device=None):
        from greifen import sim_newton, szene
        from rebel_model.config import load
        from rebel_model.kinematics import Chain
        from rebel_model.urdf_gen import build_urdf

        self._sim = sim_newton
        self.cfg = load(exp.pfad(exp.roboter))
        self.sz = szene.load(exp.pfad(exp.szene))
        urdf = build_urdf(self.cfg)
        self.chain = Chain(urdf)
        self.ctx = sim_newton.kontext(self.cfg, self.sz, urdf, self.chain, device)
        self.device = self.ctx["device"]
        self.versionen = sim_newton.versionen()

    def versuch(self, nr: int, parameter: Dict[str, float]) -> Dict[str, Any]:
        from greifen.plan import Planer, Versuch

        sz = ex.szene_fuer(self.sz, parameter)
        v = Versuch(nr, "experiment", tuple(float(x) for x in sz.glas["start_xy_m"]),
                    tuple(float(x) for x in sz.glas["ziel_xy_m"]), ex.greif_versatz(parameter))
        planer = Planer(self.chain, self.cfg, sz, seed=0)
        rec = self._sim.versuch_ausfuehren(dict(self.ctx, sz=sz), v, planer)
        rec["parameter"] = dict(parameter)
        return rec


class Attrappe:
    """Deterministisches Testdouble. ``RAEUMWERK_ATTRAPPE_WAND_S`` = Wartezeit je Versuch."""

    device = "keins"
    versionen: Dict[str, Any] = {}

    def __init__(self, exp: ex.Experiment, device=None):
        from greifen import szene

        self.sz = szene.load(exp.pfad(exp.szene))
        self.wand_s = float(os.environ.get("RAEUMWERK_ATTRAPPE_WAND_S", "0"))

    def versuch(self, nr: int, parameter: Dict[str, float]) -> Dict[str, Any]:
        from greifen import bewertung

        t0 = time.monotonic()
        if self.wand_s:
            time.sleep(self.wand_s)
        sz = ex.szene_fuer(self.sz, parameter)
        dx, dy, dz = ex.greif_versatz(parameter)
        r = sz.glas_radius
        start = [float(v) for v in sz.glas["start_xy_m"]]
        ziel = [float(v) for v in sz.glas["ziel_xy_m"]]
        mu = max(float(sz.kontakt["reibung_finger"]), float(sz.glas["reibung"]))
        kraft = float(sz.greifen["greifkraft_n"])
        gewicht = float(sz.glas["masse_kg"]) * 9.81
        getroffen = abs(dy) < r - 0.01 and abs(dx) < 0.02
        haelt = getroffen and 2 * mu * kraft > 1.5 * gewicht
        z_steh = sz.glas_mitte_z
        if not getroffen:
            ende, hub, trans = [start[0], start[1], z_steh], 0.0, 0.0
        elif not haelt:
            ende, hub, trans = [start[0] + 0.1, start[1], 0.0375], 0.1, -0.05
        else:
            ende, hub, trans = [ziel[0] + 0.0009 + dx * 0.1, ziel[1] + dy * 0.1, z_steh], 0.0999, 0.0995
        m = {"plan_ok": True, "plan_fehler": [], "endlage_m": ende, "ziel_xy_m": ziel,
             "kippung_end_grad": 0.1 if haelt or not getroffen else 90.0, "hub_max_m": hub,
             "transport_min_hub_m": trans, "stehhoehe_soll_m": z_steh,
             "tisch_durchdringung_max_m": 0.001 if dz < -0.015 else 0.0,
             "finger_durchdringung_max_m": kraft / float(sz.greifen["finger_ke"]) * 0.2,
             "glas_v_max_m_s": 0.18, "nan": False}
        bew = bewertung.bewerte(m, sz.bewertung)
        return {"versuch": {"nr": nr, "art": "experiment"}, "parameter": dict(parameter),
                "erfolg": bew["erfolg"], "gruende": bew["gruende"], "gruende_text": bew["texte"],
                "position": {"start_m": start + [z_steh], "ende_m": ende, "ziel_xy_m": ziel,
                             "fehler_xy_m": math.hypot(ende[0] - ziel[0], ende[1] - ziel[1])},
                "kippung_grad": {"ende": m["kippung_end_grad"], "max": m["kippung_end_grad"]},
                "dauer": {"wand_sim_s": round(time.monotonic() - t0, 3)},
                "messung": m, "bewertung": bew, "device": self.device, "attrappe": True}


class AusraeumSimulator:
    """Backend ``ausraeumen``: 4 Glaeser aus dem Oberkorb (``ausraeumen.ablauf``), Newton.

    Die IK-Warmstarts kommen aus dem Nennplan (einmal je Prozess geplant),
    damit jeder Versuch dieselben Haltungen je Stelle sucht."""

    def __init__(self, exp: ex.Experiment, device=None):
        from ausraeumen import ablauf, konfig, sim_newton
        from rebel_model.config import load

        self.cfg, self.urdf, self.chain = ablauf.roboter(load(exp.pfad(exp.roboter)), konfig.load(exp.pfad(exp.szene)))
        self.ctx = sim_newton.kontext(device)
        self.device = self.ctx["device"]
        self.versionen = sim_newton.versionen()
        self.merk = None

    def versuch(self, nr: int, parameter: Dict[str, float]) -> Dict[str, Any]:
        from ausraeumen import ablauf, konfig

        if self.merk is None:
            _, self.merk = ablauf.versuch(-1, "nennplan", konfig.Abweichung(), None, self.cfg, self.chain, self.urdf,
                                          nur_plan=True)
        rec, _ = ablauf.versuch(nr, "experiment", ablauf.abweichung_aus(parameter), self.ctx, self.cfg, self.chain,
                                self.urdf, self.merk)
        return ablauf.fuer_run(rec, parameter)


def erzeugen(exp: ex.Experiment, backend: str, device=None):
    return {"newton": NewtonSimulator, "attrappe": Attrappe, "ausraeumen": AusraeumSimulator}[backend](exp, device)
