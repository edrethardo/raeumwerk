"""Tests fuer die Kollisionsform der Finger und den Aufbau A1-S1 (ohne Newton)."""
from __future__ import annotations

import math

import numpy as np
import pytest

from finger import a1
from finger import kollision as FK
from finger.parameter import Finger


@pytest.fixture(scope="module")
def f():
    return Finger.laden()


def test_kollisionsform_folgt_der_kontur(f):
    q = {k.name: k for k in FK.quader(f)}
    assert {"platte", "kern", "auflage_l", "auflage_r", "flanke_l_v", "flanke_r_lippe"} <= set(q)
    # Auflagen: 0,5 mm ueber der Flanke, an der Glas-Beruehrstelle
    x = 37.5 * math.sin(f.gamma)
    assert FK.innenflaeche_y(f, x, 60.0) == pytest.approx(f.flanke_y(x) + f.auflage_ueberstand, abs=0.05)
    # Kerbe frei bis auf den Kern (2,5 mm hinter der Bezugsebene)
    k0, k1 = f.kerbe
    assert FK.innenflaeche_y(f, 0.0, (k0 + k1) / 2) == pytest.approx(-float(f.p["teller"]["kerbe_tiefe_mm"]), abs=0.05)
    # Lippe: V-Flanke, Mitte im Nutgrund, Rand an der Bezugsebene
    l0, l1 = f.lippe
    assert FK.innenflaeche_y(f, 0.2, (l0 + l1) / 2) == pytest.approx(f.flanke_y(0.2), abs=0.1)
    assert FK.innenflaeche_y(f, 8.5, (l0 + l1) / 2) == pytest.approx(f.flanke_y(8.5), abs=0.1)
    # nichts ragt ueber Breite, Laenge oder die Auflagen hinaus
    for k in FK.quader(f):
        ecken = np.array([[sx, sy, sz] for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]) * k.halb
        p = (k.rot @ ecken.T).T + k.mitte
        assert np.all(np.abs(p[:, 0]) <= f.b / 2 * 1e-3 + 4e-4)
        assert np.all(p[:, 2] >= -1e-9) and np.all(p[:, 2] <= f.L * 1e-3 + 1e-9)
        assert np.all(p[:, 1] <= f.auflage_ueberstand * 1e-3 + 1e-6)


def test_szene_a1_glaeser_in_den_erreichbaren_plaetzen(f):
    sz = a1.szenario()
    A = a1.aufbau(sz, f)
    w = a1.welt_glaeser(A, sz, f, a1.abweichung(8))
    assert len(w.glas_start) == 8 and len(w.glas_ziel) == 8
    # Platz 1 = vorderste Stelle der rechten Reihe (x 0,48), Glaeser kopfueber
    assert w.glas_start[0].mitte[0] == pytest.approx(0.48)
    assert all(g.rot[2, 2] < -0.99 for g in w.glas_start)
    # Finger aus dem CAD (PA12) statt der Annahme 83 g
    assert A.cfg.greifer["finger_masse_kg"] == pytest.approx(0.0175, abs=0.002)
    assert A.cfg.greifer["tcp_ab_flansch_m"] == pytest.approx(0.12)
    pl = a1.A1Planer(w, A.cfg, A.chain, sz, f)
    from ausraeumen.plan import Lagezustand
    assert pl.treffer(pl.ruhepose(), Lagezustand(list(w.glas_start))) == []
    # Greifkraft: Ziel sim_n (7 N) hinter der Beruehrung
    assert (pl.q_kontakt - pl.q_zu) * float(pl.a["greifer"]["finger_ke"]) == pytest.approx(f.p["greifkraft"]["sim_n"])
    assert f.p["greifkraft"]["sim_n"] == pytest.approx(7.0)


def test_szene_a1_teller_hochkant_in_haltern(f):
    sz = a1.szenario()
    A = a1.aufbau(sz, f)
    w = a1.welt_teller(A, sz, f, a1.abweichung(6))
    assert len(w.glas_start) == 6
    halter = [k for k in w.statisch if k.gruppe == "tellerhalter"]
    staender = [k for k in w.statisch if k.gruppe == "tellerstaender"]
    assert len(halter) == 24 and len(staender) == 25
    assert not any(k.gruppe == "glashalter" for k in w.statisch)
    for t in w.glas_start:
        assert abs(t.rot[2, 2]) < 1e-9          # Tellernormale waagerecht
        assert t.halb[0] == pytest.approx(0.095)
