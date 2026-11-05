""""neu hinsehen" (A), Mechanik-Prior (B), skalierte Welt, Zielverwechslung (C)."""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from test_robustheit import TELLER_ROT, _nenn_glas, _nenn_teller, _welt_glas, _welt_teller  # noqa: E402
from wahrnehmung import griffpose as WG  # noqa: E402
from wahrnehmung import robustheit as RB  # noqa: E402

KW_G = dict(seed=1, skala_ensenso=2.0, skala_d405=1.5)
KW_T = dict(seed=1, skala_ensenso=2.5, skala_d405=1.5)


# --- Bausteine -------------------------------------------------------------------------------------

def test_gier_normale_rundlauf():
    n0 = np.array([0.0, -1.0, 0.0])                        # Nennnormale der Tellerreihe
    assert RB.gier_aus_normale(n0) == pytest.approx(0.0, abs=1e-9)
    for d in (-7.0, -1.0, 0.5, 3.0, 12.0):
        assert RB.gier_aus_normale(RB.normale_aus_gier(n0, d)) == pytest.approx(d, abs=1e-9)
    assert RB.gier_aus_normale(-RB.normale_aus_gier(n0, 3.0)) == pytest.approx(3.0, abs=1e-9)   # 180-periodisch


def test_wrap_und_beschneiden():
    assert RB.wrap_gier(95.0) == pytest.approx(-85.0)
    assert RB.wrap_gier(-91.0) == pytest.approx(89.0)
    assert RB.beschneiden([0.0, 0.02, -0.02], [0.001, 0.0, 0.0], [0.005, 0.005, 0.005]) == pytest.approx(
        [0.0, 0.005, -0.005])


def test_prior_standard_werte_und_skala():
    p = RB.prior_standard("teller")
    assert (p["tol_xy_m"], p["tol_gier_grad"]) == (0.005, 1.0)
    assert RB.prior_standard("glas")["tol_dreh_grad"] == 3.0
    assert RB.prior_standard("teller", 3.0)["tol_gier_grad"] == pytest.approx(3.0)
    assert RB.PRIOR_STANDARD["teller"]["tol_gier_grad"] == 1.0                       # Kopie, nicht veraendert


def test_abweichung_skala_eins_ist_bitgleich_und_skaliert_gleiche_ziehung():
    import griff_lauf as GL
    for art in ("glas", "teller"):
        a1_, t1 = GL.abweichung(art, 5)
        a2_, t2 = GL.abweichung(art, 5, 1.0, 1.0)
        assert a1_.glas_versatz_xy_m == a2_.glas_versatz_xy_m and a1_.glas_gier_grad == a2_.glas_gier_grad
        assert t1 == t2
    ag, tg = GL.abweichung("glas", 5)
    ag3, _ = GL.abweichung("glas", 5, 3.0, 2.0)
    assert np.allclose(np.array(ag3.glas_versatz_xy_m), 3.0 * np.array(ag.glas_versatz_xy_m))
    assert np.allclose(np.array(ag3.glas_gier_grad), 2.0 * np.array(ag.glas_gier_grad))
    assert ag3.korbauszug_delta_m == ag.korbauszug_delta_m
    _, t = GL.abweichung("teller", 5)
    _, t3 = GL.abweichung("teller", 5, 2.0, 6.0)
    for (x, y, g), (x3, y3, g3) in zip(t["teller"], t3["teller"]):
        assert (2 * x, 2 * y, 6 * g) == pytest.approx((x3, y3, g3))


# --- Standard unveraendert ---------------------------------------------------------------------------

def test_standard_ohne_schalter_hat_kein_prior_und_kein_neu_hinsehen():
    w = _welt_glas()
    dr = RB.drift_fest(np.random.default_rng(9001), 0.020, 15.0)
    a = WG.schaetzen("glas", w, 0, _nenn_glas(), posedrift=dr, **KW_G)
    b = WG.schaetzen("glas", w, 0, _nenn_glas(), posedrift=dr, neu_hinsehen=False, prior=None, **KW_G)
    assert "prior" not in a and "neu_hingesehen" not in a
    assert a["pose_m"] == b["pose_m"] and a["gruende"] == b["gruende"] and a["fehler_mm"] == b["fehler_mm"]
    assert "ensenso_d405_widerspruch" in a["gruende"] and not a["ok"]


# --- A: neu hinsehen ---------------------------------------------------------------------------------

def test_neu_hinsehen_nimmt_die_d405_pose_statt_abzubrechen():
    w = _welt_glas()
    dr = RB.drift_fest(np.random.default_rng(9001), 0.020, 15.0)
    std = WG.schaetzen("glas", w, 0, _nenn_glas(), posedrift=dr, **KW_G)
    a = WG.schaetzen("glas", w, 0, _nenn_glas(), posedrift=dr, neu_hinsehen=True, **KW_G)
    assert not std["ok"] and a["ok"] and a["neu_hingesehen"]
    assert a["pose_m"] == std["pose_m"]                                              # dieselbe D405-Pose
    assert a["gruende"] == [g for g in std["gruende"] if g != "ensenso_d405_widerspruch"]
    assert a["fehler_mm"] < 6.0


def test_neu_hinsehen_bricht_ab_wenn_die_d405_pose_nicht_im_plan_liegt():
    """Der Widerspruch allein wird uebergangen; liegt die D405-Pose neben dem Plan (soll_tol_m), bleibt der Abbruch."""
    w = _welt_glas()
    dr = RB.drift_fest(np.random.default_rng(9001), 0.020, 15.0)
    a = WG.schaetzen("glas", w, 0, _nenn_glas(), posedrift=dr, neu_hinsehen=True, soll_tol_m=0.0005, **KW_G)
    assert not a["ok"] and "nicht_am_erwarteten_platz" in a["gruende"]


def test_neu_hinsehen_ohne_widerspruch_aendert_nichts():
    w = _welt_glas()
    a = WG.schaetzen("glas", w, 0, _nenn_glas(), **KW_G)
    b = WG.schaetzen("glas", w, 0, _nenn_glas(), neu_hinsehen=True, **KW_G)
    assert "neu_hingesehen" not in b
    assert a["pose_m"] == b["pose_m"] and a["gruende"] == b["gruende"]


# --- B: Mechanik-Prior -------------------------------------------------------------------------------

def test_prior_glas_beschneidet_station_und_pose_auf_die_toleranz():
    w = _welt_glas()
    dr = RB.drift_fest(np.random.default_rng(9001), 0.020, 15.0)
    b = WG.schaetzen("glas", w, 0, _nenn_glas(), posedrift=dr, prior=RB.prior_standard("glas"), **KW_G)
    nenn = np.array(b["nenn_m"])                                                     # Nennlage mit gemessenem Korbauszug
    assert b["prior"]["station_roh_abw_mm"] > 12.0                                   # Station roh weit weg
    assert np.max(np.abs(np.array(b["prior"]["station_c_m"]) - nenn[:2])) <= 0.005 + 1e-12
    assert np.max(np.abs(np.array(b["pose_m"])[:2] - nenn[:2])) <= 0.005 + 1e-12
    assert b["s0_fehler_mm"] > 14.0                                                  # S0 bleibt die rohe Station
    assert b["ok"] and not b["prior"]["widerspruch_xy"]


def test_prior_glas_d405_widerspruch_wenn_die_lage_ausserhalb_liegt():
    """Der Prior stimmt nicht (Glas 20 mm neben der Nennlage): die D405 sieht es, die Plausibilitaet schlaegt an."""
    w = _welt_glas()
    w.glas_start[0].mitte = w.glas_start[0].mitte + np.array([0.020, 0.0, 0.0])
    b = WG.schaetzen("glas", w, 0, _nenn_glas(), prior=RB.prior_standard("glas"), **KW_G)
    assert b["prior"]["widerspruch_xy"] and "prior_widerspruch" in b["gruende"] and not b["ok"]
    assert b["prior"]["d405_roh_abw_mm"] > 15.0


def test_prior_teller_gier_aus_dem_prior_nicht_aus_der_station():
    w = _welt_teller()
    dr = RB.drift_fest(np.random.default_rng(9001), 0.0, 15.0, achse=[0.0, 0.0, 1.0])
    std = WG.schaetzen("teller", w, 0, _nenn_teller(), posedrift=dr, **KW_T)
    b = WG.schaetzen("teller", w, 0, _nenn_teller(), posedrift=dr, prior=RB.prior_standard("teller"), **KW_T)
    assert abs(std["s0_gier_grad"]) > 10.0                                           # Station 15 Grad Messfehler
    assert abs(b["prior"]["gier_abw_roh_grad"]) > 10.0 and b["prior"]["widerspruch_gier"]
    assert abs(b["gier_grad"]) <= 1.0 + 1e-9                                         # Gier aus dem Prior
    assert "pose_m" in b                                                             # D405 sieht von der Prior-Normalen
    assert b["s0_gier_grad"] == std["s0_gier_grad"]


def test_prior_teller_ohne_drift_laesst_kleine_gier_unveraendert():
    w = _welt_teller()
    b = WG.schaetzen("teller", w, 0, _nenn_teller(), prior=RB.prior_standard("teller"), **KW_T)
    assert not b["prior"]["widerspruch_gier"]
    assert b["gier_grad"] == pytest.approx(b["prior"]["gier_roh_grad"], abs=1e-9)    # innerhalb Toleranz: roh


# --- C: Zielverwechslung ---------------------------------------------------------------------------------

def test_nachbarmaske_wird_abgelehnt_ohne_kreuzprobe():
    """Beide Kameras segmentieren den Nachbarn: Kreuzprobe sieht nichts (beide gleich), der Nennlage-Check schon."""
    w = _welt_glas()
    n = WG.schaetzen("glas", w, 0, _nenn_glas(), negativ="nachbar", **KW_G)
    assert not n["ok"]                                  # Schaetzer lehnt ab (ensenso:*) oder Nennlage-Check
    assert "ensenso_d405_widerspruch" not in n["gruende"]                            # die Kameras widersprechen sich nicht
    a = WG.schaetzen("glas", w, 0, _nenn_glas(), negativ="nachbar", neu_hinsehen=True, **KW_G)
    assert not a["ok"]                                                               # A schuetzt weiter


def test_nachbarmaske_mit_prior_wird_abgelehnt():
    w = _welt_glas()
    b = WG.schaetzen("glas", w, 0, _nenn_glas(), negativ="nachbar", prior=RB.prior_standard("glas"), **KW_G)
    assert not b["ok"] and b["gruende"]
