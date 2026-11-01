"""Tests fuer spuelmaschine.belastung (Arbeitsbelastung, Dauerlast, Ruhepose)."""
from __future__ import annotations

import copy
import math
from pathlib import Path

import numpy as np
import pytest

from spuelmaschine import aufbau as AU
from spuelmaschine import belastung as B

REPO = Path(__file__).resolve().parents[1]
DEMO = REPO / "beispiele" / "ueberkopf-045-demo.yaml"
BEDIENRAUM = ([-0.05, 0.0, 0.0], [0.65, 0.75, 1.0])


def _aufbau(gier=180, neigung=30, abstand=0.45):
    d = copy.deepcopy(AU.lade_yaml(DEMO))
    d["roboter"].update({"ursprung_xyz_m": [0.30, abstand, 0.55], "gier_grad": gier, "neigung_grad": neigung})
    return B.ruhe_aufbau(d, {"lo": [-0.6, -0.55, 1.45], "hi": [1.2, -0.20, 2.15]})


def test_statistik():
    s = B.statistik([2.0, -11.0, 8.0, 13.0])
    assert s == {"n": 4, "max": 13.0, "median": 9.5, "unter_nenn": 0.5, "unter_max": 0.75}
    assert B.statistik([])["n"] == 0


def test_rms_ablauf_gewichtet():
    assert B.rms_ablauf([(1.0, [3.0, -3.0])]) == pytest.approx(3.0)
    assert B.rms_ablauf([(0.5, [2.0]), (0.5, [0.0])]) == pytest.approx(math.sqrt(2.0))
    assert B.rms_ablauf([(3.0, [2.0]), (1.0, [6.0])]) == pytest.approx(math.sqrt((3 * 4 + 36) / 4))
    with pytest.raises(ValueError):
        B.rms_ablauf([(0.0, [1.0])])


def test_aabb_abstand():
    assert B.aabb_abstand([0, 0, 0], [1, 1, 1], [2, 0, 0], [3, 1, 1]) == pytest.approx(1.0)
    assert B.aabb_abstand([0, 0, 0], [1, 1, 1], [2, 2, 0], [3, 3, 1]) == pytest.approx(math.sqrt(2))
    assert B.aabb_abstand([0, 0, 0], [1, 1, 1], [0.9, 0, 0], [2, 1, 1]) == pytest.approx(-0.1)


@pytest.mark.parametrize("gier,neigung", [(180, 0), (180, 30), (270, 45)])
def test_schweremomente_wie_aufbau(gier, neigung):
    """Die schnelle Rechnung liefert dieselben Momente wie aufbau.schweremomente (mit und ohne Last)."""
    p = _aufbau(gier, neigung).pruefer(0.0, 0.0)
    rng = np.random.default_rng(3)
    for _ in range(5):
        q = p.chain.random_q(rng, AU.USE)
        for last in (0.0, 0.35):
            assert np.allclose(B.schweremomente(p, q, last), AU.schweremomente(p, q, last), atol=1e-9)


def test_weg_momente_enden():
    p = _aufbau().pruefer(0.0, 0.0)
    rng = np.random.default_rng(5)
    qa, qb = p.chain.random_q(rng, AU.USE), p.chain.random_q(rng, AU.USE)
    t = B.weg_momente(p, qa, qb, 0.25, n=7)
    assert t.shape == (7, len(qa))
    assert np.allclose(t[0], AU.schweremomente(p, qa, 0.25)) and np.allclose(t[-1], AU.schweremomente(p, qb, 0.25))


@pytest.mark.parametrize("neigung", [0, 30])
def test_ruhepose_ohne_bedienraum_haengt_im_lot(neigung):
    """Ohne Bedienraum findet die Suche den im Lot haengenden Arm: J2, J3 ~ 0 und stabil haengend."""
    A = _aufbau(neigung=neigung)
    r = B.suche_ruhepose(A, schritt_grad=30.0)
    assert r["ok"] and r["haengt"]
    assert r["summe_j2_j3"] < 0.05
    p = A.pruefer(0.0, 0.0)
    q = np.array(r["q"])
    assert abs(B.schweremomente(p, q)[p.chain.index["joint2"]]) < 0.05


def test_ruhepose_mit_bedienraum_frei_und_kollisionsfrei():
    """Mit Bedienraum: Abstand >= Rand, keine Kollision bei offener und geschlossener Tuer; die
    Lot-Pose derselben Achsstellung griffe dagegen in den Bedienraum ein."""
    A = _aufbau(neigung=30)
    r = B.suche_ruhepose(A, bedienraum=BEDIENRAUM, schritt_grad=30.0)
    assert r["ok"]
    q = np.array(r["q"])
    p_auf, p_zu = A.pruefer(0.0, 0.0), A.pruefer(0.0, 0.0, B.TUER_ZU)
    assert B.abstand_zu(p_auf, q, *BEDIENRAUM) >= 0.05 - 1e-9
    assert r["bedienraum_abstand_m"] >= 0.05
    assert not p_auf.kollisionen(q) and not p_zu.kollisionen(q)
    lot = B.suche_ruhepose(A, schritt_grad=30.0)
    assert B.abstand_zu(p_auf, np.array(lot["q"]), *BEDIENRAUM) < 0.0
    assert r["summe_j2_j3"] > lot["summe_j2_j3"]


def test_tuer_zu_ist_eine_andere_szene():
    A = _aufbau()
    tu = [h for h in A.pruefer(0.0, 0.0, B.TUER_ZU).hindernisse if h.name == "tuer"][0]
    to = [h for h in A.pruefer(0.0, 0.0).hindernisse if h.name == "tuer"][0]
    assert tu.aabb()[1][2] > 0.6 and to.aabb()[1][2] < 0.2   # zu: senkrecht, offen: waagerecht


def test_weg_frei_erkennt_kollision():
    A = _aufbau(neigung=0)
    p = A.pruefer(0.0, 0.0)
    lot = np.array(B.suche_ruhepose(A, schritt_grad=30.0)["q"])
    assert B.weg_frei([p], lot, lot, n=3) == {"ok": True, "kollisionen": [], "gelenkweg_max_grad": 0.0, "hub_m": 0.0}
    tief = lot.copy()
    tief[p.i7] = 0.0   # Arm im Lot ganz unten: steht in Tuer/Boden
    w = B.weg_frei([p], lot, tief, n=5)
    assert not w["ok"] and w["kollisionen"] and w["hub_m"] == pytest.approx(lot[p.i7])
