"""Wahrnehmung (Ensenso/D405-Simulation, Schaetzer) und Tellergriff-Varianten."""
from __future__ import annotations

import math

import numpy as np
import pytest

from finger.tellergriff import varianten as TV
from wahrnehmung import schaetzer as S
from wahrnehmung.sensor import Fehlermodell, aufnehmen, kalibrierfehler, maske_verrauschen
from wahrnehmung.strahlen import D405, ENSENSO, Kamera, Prim, d405_am_greifer, r_greif, schnitt

KOPF = np.diag([1.0, -1.0, -1.0])
TELLER_ROT = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0]])


def _boden():
    return Prim("korbboden", "oberkorb", "box", np.array([0.3, 0.2, 0.495]), np.array([0.3, 0.3, 0.005]))


def _glas(name, c, r=0.0375, h=0.11):
    return Prim(name, "glas", "zyl", np.array([c[0], c[1], 0.5 + h / 2]), np.array([r, r, h / 2]), KOPF, name)


def test_schnitt_box_und_zylinder():
    o = np.array([[0.0, 0.0, 1.0]])
    d = np.array([[0.0, 0.0, -1.0]])
    t, n = schnitt(Prim("b", "x", "box", np.zeros(3), np.array([0.1, 0.1, 0.1])), o, d)
    assert t[0] == pytest.approx(0.9)
    assert n[0] == pytest.approx([0, 0, 1])
    t, n = schnitt(Prim("z", "x", "zyl", np.zeros(3), np.array([0.05, 0.05, 0.2])), np.array([[1.0, 0.0, 0.0]]),
                   np.array([[-1.0, 0.0, 0.0]]))
    assert t[0] == pytest.approx(0.95)
    assert n[0] == pytest.approx([1, 0, 0])


def test_kreisfit_und_ransac_mit_ausreissern():
    rng = np.random.default_rng(1)
    a = rng.uniform(0, math.pi, 80)
    P = np.c_[0.02 + 0.095 * np.cos(a), -0.01 + 0.095 * np.sin(a)] + rng.normal(0, 3e-4, (80, 2))
    P = np.vstack([P, rng.uniform(-0.1, 0.1, (30, 2))])
    best = S.kreis_ransac(P, 0.095, rng)
    c, r, _ = S.kreis_lsq(P[best[1]], best[0], r=0.095)
    assert np.linalg.norm(c - [0.02, -0.01]) < 5e-4
    assert S.bogen_grad(P[best[1]], c) > 150


def _glas_szene(r=0.0375, h=0.11, nachbar=True):
    prims = [_boden(), _glas("glas_a", (0.30, 0.20), r, h)]
    if nachbar:
        prims.append(_glas("glas_b", (0.30 + 2 * r + 0.004, 0.20), r, h))
    return prims


def _d405_ueber(c, z_top):
    return d405_am_greifer(np.array([c[0], c[1], z_top - 0.022 + 0.10]), r_greif(0.0), skala=2.0)


def test_glas_silhouette_ohne_rauschen_trifft():
    prims = _glas_szene()
    fm = Fehlermodell(glas_an=False, nass_ausfall=0.0, kante_ausfall=0.0)
    auf = aufnehmen(prims, _d405_ueber((0.303, 0.198), 0.61), np.random.default_rng(0), fm)
    e = S.glas_schaetzen(auf, auf.maske_wahr("glas_a"), 0.5, (0.303, 0.198))
    assert e["ok"], e["gruende"]
    assert np.linalg.norm(np.asarray(e["c"]) - [0.30, 0.20]) < 5e-4
    assert e["modell"] == "Glas Ø 75 mm"


def test_glas_mit_transparenz_und_maskenrauschen():
    prims = _glas_szene()
    rng = np.random.default_rng(3)
    fm = Fehlermodell()
    auf = aufnehmen(prims, _d405_ueber((0.30, 0.20), 0.61), rng, fm)
    m = maske_verrauschen(auf.maske_wahr("glas_a"), rng, fm.maske_rand_kippen, fm.maske_versatz_px)
    e = S.glas_schaetzen(auf, m, 0.5, (0.30, 0.20), rng=rng)
    assert e["ok"], e["gruende"]
    assert np.linalg.norm(np.asarray(e["c"]) - [0.30, 0.20]) < 2e-3
    st = auf.statistik()
    assert st["glas_fehlt_%"] == pytest.approx(50, abs=3)
    assert st["glas_durchblick_%"] == pytest.approx(35, abs=3)
    assert st["glas_reflex_%"] == pytest.approx(15, abs=3)


def test_modellwahl_erkennt_schmales_glas():
    prims = _glas_szene(r=0.0325, h=0.12, nachbar=False)
    fm = Fehlermodell(glas_an=False, nass_ausfall=0.0, kante_ausfall=0.0)
    auf = aufnehmen(prims, _d405_ueber((0.30, 0.20), 0.62), np.random.default_rng(0), fm)
    e = S.glas_schaetzen(auf, auf.maske_wahr("glas_a"), 0.5, (0.30, 0.20))
    assert e["modell"] == "Glas Ø 65 mm"


def test_negativ_zwei_glaeser_in_einer_maske_wird_abgelehnt():
    prims = _glas_szene()
    fm = Fehlermodell(glas_an=False, nass_ausfall=0.0, kante_ausfall=0.0)
    auf = aufnehmen(prims, _d405_ueber((0.32, 0.20), 0.61), np.random.default_rng(0), fm)
    m = auf.maske_wahr("glas_a") | auf.maske_wahr("glas_b")
    e = S.glas_schaetzen(auf, m, 0.5, (0.32, 0.20))
    assert not e["ok"]
    assert e["gruende"]


def _teller_szene(c):
    prims = [_boden()]
    for k, dy in enumerate((-0.06, 0.0, 0.06)):
        m = np.array([c[0], c[1] + dy, 0.5 + 0.095])
        prims.append(Prim(f"teller_{k}", "teller", "zyl", m, np.array([0.095, 0.095, 0.0025]), TELLER_ROT, f"teller_{k}"))
    return prims


def test_teller_ebene_und_kreis_aus_der_ensenso():
    c = np.array([0.15, 0.30])
    prims = _teller_szene(c)
    cam = Kamera.zielend("e", ENSENSO, (0.55, 0.40, 1.10), (0.30, 0.17, 0.48), skala=3.0)
    rng = np.random.default_rng(5)
    auf = aufnehmen(prims, cam, rng, Fehlermodell(), roi=(np.r_[c, 0.6], 0.2))
    e = S.teller_schaetzen(auf, auf.maske_wahr("teller_1"), [0, 1, 0], np.r_[c, 0.595], rng=rng)
    assert e["ok"], e["gruende"]
    assert np.linalg.norm(np.asarray(e["c"]) - np.r_[c, 0.595]) < 4e-3
    assert e["normale_winkel_grad"] < 2.0
    assert e["modell"] == "Teller Ø 190 mm"


def test_negativ_teller_doppelt_wird_abgelehnt():
    c = np.array([0.15, 0.30])
    prims = _teller_szene(c)
    cam = Kamera.zielend("e", ENSENSO, (0.55, 0.40, 1.10), (0.30, 0.17, 0.48), skala=3.0)
    rng = np.random.default_rng(5)
    auf = aufnehmen(prims, cam, rng, Fehlermodell(), roi=(np.r_[c, 0.6], 0.2))
    m = auf.maske_wahr("teller_1") | auf.maske_wahr("teller_0")
    e = S.teller_schaetzen(auf, m, [0, 1, 0], np.r_[c, 0.595], rng=rng)
    assert not e["ok"]


def test_kalibrierfehler_null_aendert_nichts_und_sigma_verschiebt():
    prims = [_boden()]
    cam = Kamera("d", D405, np.array([0.3, 0.2, 0.8]), r_greif(0.0), skala=8.0)
    auf = aufnehmen(prims, cam, np.random.default_rng(0), Fehlermodell(nass_ausfall=0.0, kante_ausfall=0.0))
    P0 = auf.P.copy()
    kalibrierfehler(auf, np.random.default_rng(1), 0.0, 0.0)
    ok = np.isfinite(P0[:, 0])
    assert np.allclose(auf.P[ok], P0[ok])
    kalibrierfehler(auf, np.random.default_rng(1), 0.002, 0.0)
    assert 1e-4 < float(np.median(np.linalg.norm(auf.P[ok] - P0[ok], axis=1))) < 0.01


# --- Griffpose (Ensenso -> D405 -> Pruefung) -----------------------------------------------------

def _welt_glas():
    from types import SimpleNamespace as NS

    def k(name, gruppe, mitte, halb, rot=np.eye(3)):
        return NS(name=name, gruppe=gruppe, mitte=np.asarray(mitte, float), halb=np.asarray(halb, float), rot=rot)
    stat = [k("korbboden", "oberkorb", (0.3, 0.2, 0.495), (0.3, 0.3, 0.005))]
    gl = [k("glas_1", "glas", (0.30, 0.20, 0.555), (0.0375, 0.0375, 0.055), KOPF),
          k("glas_2", "glas", (0.385, 0.20, 0.555), (0.0375, 0.0375, 0.055), KOPF)]
    return NS(statisch_ohne_teller=stat, glas_start=gl, teller=[], aufbau=NS(abw=NS(korbauszug_delta_m=0.0)))


@pytest.mark.parametrize("negativ,soll,ok,grund", [
    (None, (0.30, 0.20), True, None),
    (None, (0.30, 0.23), False, "nicht_am_erwarteten_platz"),
    ("versatz", (0.30, 0.20), False, None),
])
def test_griffpose_prueft_platz_und_widerspruch(negativ, soll, ok, grund):
    from wahrnehmung import griffpose as WG
    est = WG.schaetzen("glas", _welt_glas(), 0, seed=1, negativ=negativ, skala_ensenso=2.0, skala_d405=1.5, soll_m=soll)
    assert est["ok"] is ok, est["gruende"]
    if ok:
        assert est["fehler_mm"] < 4.0
    if grund:
        assert grund in est["gruende"]


def test_maskenversatz_verschiebt_ganze_maske():
    m = np.zeros((20, 20), bool)
    m[5:10, 5:10] = True
    rng = np.random.default_rng(2)
    out = maske_verrauschen(m, rng, 0.0, 5.0)
    assert out.sum() == m.sum()


# --- Tellergriff-Varianten -----------------------------------------------------------------------

def test_varianten_vollstaendig():
    v = TV.laden()
    assert set(v) >= {"basis", "gabel", "breit", "kraft"}
    assert v["gabel"].breite_m() == pytest.approx(0.060)
    assert v["breit"].breite_m() == pytest.approx(0.060)
    assert v["basis"].breite_m() == pytest.approx(0.018)
    assert v["kraft"].greifkraft_n == pytest.approx(2 * v["basis"].greifkraft_n)


def test_gabel_lippen_liegen_an_beiden_zinken_gleich_tief_unter_dem_rand():
    v = TV.laden()
    basis = TV.lippen_unter_rand_mm(v["basis"], 0.095, 10.0)[0]
    zinken = TV.lippen_unter_rand_mm(v["gabel"], 0.095, 10.0)
    assert len(zinken) == 2
    assert zinken == pytest.approx([basis, basis])
    # Bogenstich bei 25 mm: 3,35 mm
    assert TV.bogenstich_mm(95.0, 25.0) == pytest.approx(95 - math.sqrt(95 ** 2 - 25 ** 2))


def test_gabel_joch_bleibt_ueber_dem_rand_und_zinken_verlaengert():
    v = TV.laden()["gabel"]
    assert TV.joch_ueber_rand_mm(v, 10.0) >= 15.0
    q = {k.name: k for k in TV.quader(v, 0.095)}
    assert "joch" in q
    lippe = [k for n, k in q.items() if n.endswith("flanke_r_lippe")]
    assert len(lippe) == 2
    spitze = max(k.mitte[2] + k.halb[2] for k in lippe)
    assert spitze == pytest.approx(0.100 + TV.bogenstich_mm(95.0, 25.0) * 1e-3, abs=1e-6)
    xs = sorted(k.mitte[0] for k in lippe)
    assert xs[1] - xs[0] == pytest.approx(0.050, abs=0.003)
