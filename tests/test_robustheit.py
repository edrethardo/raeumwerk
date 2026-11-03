"""Posefehler und Heilungsstrategien: ``wahrnehmung.robustheit`` und ``griffpose.posedrift``."""
from __future__ import annotations

import math

import numpy as np
import pytest

from finger.parameter import Finger
from finger.tellergriff import varianten as TV
from wahrnehmung import griffpose as WG
from wahrnehmung import robustheit as RB

KOPF = np.diag([1.0, -1.0, -1.0])


# --- Bausteine ------------------------------------------------------------------------------------

def test_rodrigues_dreht_um_die_achse():
    assert RB.rodrigues([0, 0, 1], 90.0) @ np.array([1.0, 0.0, 0.0]) == pytest.approx([0.0, 1.0, 0.0], abs=1e-9)
    assert RB.rodrigues([1, 2, 3], 0.0) == pytest.approx(np.eye(3))


def test_drift_fest_hat_festen_betrag_und_winkel():
    for seed in range(5):
        dr = RB.drift_fest(np.random.default_rng(seed), 0.02, 15.0)
        assert np.linalg.norm(dr["dp"][:2]) == pytest.approx(0.02)     # seitlich, fester Betrag
        assert dr["dp"][2] == pytest.approx(0.0)
        assert dr["grad"] == pytest.approx(15.0)
        assert dr["R"] @ dr["R"].T == pytest.approx(np.eye(3), abs=1e-9)


def test_drift_hart_kappt_betrag_und_winkel():
    frei = [np.linalg.norm(RB.drift(np.random.default_rng(s), t_sigma_m=0.02, r_sigma_grad=15.0)["dp"])
            for s in range(40)]
    assert max(frei) > 0.02                                            # ungekappt geht es darueber hinaus
    for s in range(40):
        dr = RB.drift(np.random.default_rng(s), t_sigma_m=0.02, r_sigma_grad=15.0, t_max_m=0.02, r_max_grad=30.0)
        assert np.linalg.norm(dr["dp"]) <= 0.02 + 1e-12
        assert dr["grad"] <= 30.0 + 1e-12


def test_fusion_senkt_sigma_und_zieht_zum_genaueren():
    assert RB.sigma_fusion_mm(2.0, 2.0) == pytest.approx(2.0 / math.sqrt(2))
    # das genauere Mass (1 mm) zieht die Fusion zu sich (2 mm auf 0, 1 mm auf 10 mm)
    p = RB.fusionieren([0.0, 0.0, 0.0], [0.010, 0.0, 0.0], 2.0, 1.0)
    assert p[0] == pytest.approx(0.008)
    assert RB.sigma_fusion_mm(2.0, 1.0) < 1.0


def test_wende_an_verschiebt_positiv_und_dreht_die_normale():
    e = {"c": [0.5, 0.5, 0.6], "normale": [0.0, 1.0, 0.0]}
    RB.wende_an(e, {"dp": np.array([0.01, 0.0, 0.0]), "R": RB.rodrigues([0, 0, 1], 90.0)})
    assert e["c"] == pytest.approx([0.51, 0.5, 0.6])
    assert e["normale"] == pytest.approx([-1.0, 0.0, 0.0])
    assert e["gier_grad"] == pytest.approx(90.0)                      # Gier folgt der gedrehten Normale
    e2 = {"c": [0.5, 0.5]}                                            # Glas fuehrt nur x, y
    RB.wende_an(e2, {"dp": np.array([0.01, 0.02, 0.03]), "R": np.eye(3)})
    assert e2["c"] == pytest.approx([0.51, 0.52])


def test_mechanische_grenzen_aus_der_fingergeometrie():
    f = Finger.laden()                                                # 18-mm-Finger
    assert RB.fangbereich_glas_mm(f) == pytest.approx(9.0)
    breit = Finger.laden(**TV.laden()["breit_6n"].finger)             # 60-mm-Backe
    assert RB.fangbereich_glas_mm(breit) == pytest.approx(30.0)
    assert RB.gier_toleranz_teller_grad(breit) == pytest.approx(math.degrees(math.asin(4.0 / 30.0)))


def test_erfolg_mechanisch_grenzen():
    f = Finger.laden()
    assert RB.erfolg_mechanisch("glas", 8.0, 0.0, f)["ok"]
    assert not RB.erfolg_mechanisch("glas", 10.0, 0.0, f)["ok"]
    assert RB.erfolg_mechanisch("glas", 6.0, 40.0, f)["ok"]           # Drehung um die Hochachse egal
    breit = Finger.laden(**TV.laden()["breit_6n"].finger)
    assert RB.erfolg_mechanisch("teller", 3.0, 5.0, breit)["ok"]
    assert not RB.erfolg_mechanisch("teller", 3.0, 12.0, breit)["ok"]


# --- griffpose: Drift der Station ----------------------------------------------------------------

def _welt_glas():
    from types import SimpleNamespace as NS

    def k(name, gruppe, mitte, halb, rot=np.eye(3)):
        return NS(name=name, gruppe=gruppe, mitte=np.asarray(mitte, float), halb=np.asarray(halb, float), rot=rot)
    stat = [k("korbboden", "oberkorb", (0.3, 0.2, 0.495), (0.3, 0.3, 0.005))]
    gl = [k("glas_1", "glas", (0.30, 0.20, 0.555), (0.0375, 0.0375, 0.055), KOPF),
          k("glas_2", "glas", (0.385, 0.20, 0.555), (0.0375, 0.0375, 0.055), KOPF)]
    return NS(statisch_ohne_teller=stat, glas_start=gl, teller=[], aufbau=NS(abw=NS(korbauszug_delta_m=0.0)))


def _nenn_glas(xy=(0.30, 0.20)):
    return lambda d: {"mitte": np.array([xy[0], xy[1], 0.555]) + [0.0, d, 0.0], "rot": KOPF,
                      "halb": np.array([0.0375, 0.0375, 0.055])}


def test_griffpose_posedrift_null_aendert_nichts():
    """Ein Drift mit Betrag 0 ist wie kein Drift: der Pfad bleibt bitgleich (der Drift-Haken
    ist additiv, Pose und Fehler der Nahekorrektur bleiben gleich)."""
    w = _welt_glas()
    a = WG.schaetzen("glas", w, 0, _nenn_glas(), seed=1, skala_ensenso=2.0, skala_d405=1.5)
    dr0 = RB.drift_fest(np.random.default_rng(0), 0.0, 0.0)
    b = WG.schaetzen("glas", w, 0, _nenn_glas(), seed=1, skala_ensenso=2.0, skala_d405=1.5, posedrift=dr0)
    assert a["pose_m"] == b["pose_m"]
    assert a["fehler_mm"] == b["fehler_mm"]
    assert a["s0_pose_m"] == b["s0_pose_m"]


def test_griffpose_drift_verschiebt_s0_die_d405_heilt():
    """Drift 20 mm auf der Station: die S0-Grobpose wandert (blinder Griff 20 mm daneben), die
    Vorposition der D405 wandert mit, aber die Nahekorrektur schaetzt das Ziel neu (Restfehler
    klein). Ohne Drift ist beides klein."""
    w = _welt_glas()
    rng = np.random.default_rng(9000 + 1)
    dr = RB.drift_fest(rng, 0.020, 15.0)
    ohne = WG.schaetzen("glas", w, 0, _nenn_glas(), seed=1, skala_ensenso=2.0, skala_d405=1.5)
    mit = WG.schaetzen("glas", w, 0, _nenn_glas(), seed=1, skala_ensenso=2.0, skala_d405=1.5, posedrift=dr)
    assert ohne["s0_fehler_mm"] < 6.0
    assert mit["s0_fehler_mm"] > 14.0                                 # blinder Griff weit daneben
    assert mit["d405"]["kamera_m"] != ohne["d405"]["kamera_m"]        # Vorposition gewandert
    assert mit["fehler_mm"] < 6.0                                     # die D405 heilt
