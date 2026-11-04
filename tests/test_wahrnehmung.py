"""Wahrnehmung (Ensenso/D405-Simulation, Schaetzer) und Tellergriff-Varianten."""
from __future__ import annotations

import math

import numpy as np
import pytest

from finger.tellergriff import varianten as TV
from wahrnehmung import griffpose as WG
from wahrnehmung import schaetzer as S
from wahrnehmung.sensor import Fehlermodell, aufnehmen, kalibrierfehler, maske_verrauschen
from wahrnehmung.strahlen import (D405, ENSENSO, ENSENSO_ALT, Kamera, Prim, d405_am_greifer, ensenso_modell,
                                  modell_aus_katalog, r_greif, schnitt)

KOPF = np.diag([1.0, -1.0, -1.0])
TELLER_ROT = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0]])
# Stationskamera: neuer Standard (C57-6-S, Mast 1,35 m) und alter Stand (B57, Mast 1,10 m)
STATION = pytest.mark.parametrize("kamera,pose", [(ENSENSO, WG.ENSENSO_POSE), (ENSENSO_ALT, WG.ENSENSO_POSE_ALT)],
                                  ids=["c57_6_s", "b57_alt"])


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


@STATION
def test_teller_ebene_und_kreis_aus_der_ensenso(kamera, pose):
    c = np.array([0.15, 0.30])
    prims = _teller_szene(c)
    cam = Kamera.zielend("e", kamera, *pose, skala=3.0)
    rng = np.random.default_rng(5)
    auf = aufnehmen(prims, cam, rng, Fehlermodell(), roi=(np.r_[c, 0.6], 0.2))
    e = S.teller_schaetzen(auf, auf.maske_wahr("teller_1"), [0, 1, 0], np.r_[c, 0.595], rng=rng)
    assert e["ok"], e["gruende"]
    assert np.linalg.norm(np.asarray(e["c"]) - np.r_[c, 0.595]) < 4e-3
    assert e["normale_winkel_grad"] < 2.0
    assert e["modell"] == "Teller Ø 190 mm"


@STATION
def test_negativ_teller_doppelt_wird_abgelehnt(kamera, pose):
    c = np.array([0.15, 0.30])
    prims = _teller_szene(c)
    cam = Kamera.zielend("e", kamera, *pose, skala=3.0)
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


def _nenn(mitte, rot, halb):
    """Nennlage laut Belegungsplan; der Korbauszug verschiebt sie entlang y."""
    return lambda d: {"mitte": np.asarray(mitte, float) + [0.0, d, 0.0], "rot": rot, "halb": np.asarray(halb, float)}


def _nenn_glas(xy=(0.30, 0.20)):
    return _nenn((xy[0], xy[1], 0.555), KOPF, (0.0375, 0.0375, 0.055))


@pytest.mark.parametrize("negativ,soll,ok,grund", [
    (None, (0.30, 0.20), True, None),
    (None, (0.30, 0.23), False, "nicht_am_erwarteten_platz"),
    ("versatz", (0.30, 0.20), False, "ensenso_d405_widerspruch"),
])
def test_griffpose_prueft_platz_und_widerspruch(negativ, soll, ok, grund):
    from wahrnehmung import griffpose as WG
    est = WG.schaetzen("glas", _welt_glas(), 0, _nenn_glas(soll), seed=1, negativ=negativ, skala_ensenso=2.0,
                       skala_d405=1.5)
    assert est["ok"] is ok, est["gruende"]
    if ok:
        assert est["fehler_mm"] < 4.0
    if grund:
        assert grund in est["gruende"]


def _verschoben(w, s, d, gier_grad=0.0):
    """Kopie der Welt, in der nur die *Wahrheit* von Objekt s um d verschoben (und um die
    Hochachse gedreht) ist."""
    import copy
    w2 = copy.copy(w)
    w2.glas_start = list(w.glas_start)
    k = copy.copy(w.glas_start[s])
    k.mitte = np.asarray(k.mitte, float) + np.asarray(d, float)
    a = math.radians(gier_grad)
    k.rot = np.array([[math.cos(a), -math.sin(a), 0.0], [math.sin(a), math.cos(a), 0.0], [0.0, 0.0, 1.0]]) @ k.rot
    w2.glas_start[s] = k
    return w2


def test_griffpose_glas_liest_die_wahrheit_nicht():
    """Gleiche Szene, Wahrheit 4 mm verschoben: die Schaetzung bleibt bitgleich (der alte Startwert
    ``c0 = wahr`` und die ROI um die Wahrheit liessen sie mitlaufen); die Fehlerangabe folgt."""
    from wahrnehmung import griffpose as WG
    w = _welt_glas()
    prims = WG.prims_aus_welt(w, "glas")
    kw = dict(seed=1, skala_ensenso=2.0, skala_d405=1.5, prims=prims)
    a = WG.schaetzen("glas", w, 0, _nenn_glas(), **kw)
    b = WG.schaetzen("glas", _verschoben(w, 0, (0.004, -0.003, 0.002)), 0, _nenn_glas(), **kw)
    assert a["ok"], a["gruende"]
    assert b["pose_m"] == a["pose_m"]
    assert b["ensenso"]["c"] == a["ensenso"]["c"]
    for k in ("ensenso", "d405"):            # gleiche Pixel ausgewertet (ROI nicht um die Wahrheit)
        assert b[k]["statistik"] == a[k]["statistik"]
    assert b["fehler_mm"] != pytest.approx(a["fehler_mm"], abs=0.5)


def test_griffpose_glas_folgt_der_szene():
    """Szene (Glas) 4 mm verschoben, Nennlage gleich: die Schaetzung folgt der Aufnahme."""
    from wahrnehmung import griffpose as WG
    w = _welt_glas()
    w2 = _verschoben(w, 0, (0.004, 0.0, 0.0))
    # Rauschen und Greiferposition aendern sich mit dem Ensenso-Ergebnis: ueber vier Seeds mitteln
    delta, fehler = [], []
    for seed in (1, 2, 3, 4):
        a = WG.schaetzen("glas", w, 0, _nenn_glas(), seed=seed, skala_ensenso=2.0, skala_d405=1.5)
        b = WG.schaetzen("glas", w2, 0, _nenn_glas(), seed=seed, skala_ensenso=2.0, skala_d405=1.5)
        assert a["ok"] and b["ok"], (a["gruende"], b["gruende"])
        delta.append(b["pose_m"][0] - a["pose_m"][0])
        fehler.append(b["fehler_mm"])
    assert float(np.mean(delta)) == pytest.approx(0.004, abs=0.0015)
    assert max(fehler) < 4.0


def _welt_teller(c=(0.15, 0.30)):
    from types import SimpleNamespace as NS

    def k(name, gruppe, mitte, halb, rot=np.eye(3)):
        return NS(name=name, gruppe=gruppe, mitte=np.asarray(mitte, float), halb=np.asarray(halb, float), rot=rot)
    stat = [k("korbboden", "oberkorb", (0.3, 0.2, 0.495), (0.3, 0.3, 0.005))]
    tl = [k(f"teller_{j + 1}", "teller", (c[0], c[1] + dy, 0.595), (0.095, 0.095, 0.0025), TELLER_ROT)
          for j, dy in enumerate((0.0, -0.06, 0.06))]
    return NS(statisch=stat, glaeser_statisch=[], glas_start=tl, aufbau=NS(abw=NS(korbauszug_delta_m=0.0)))


def _nenn_teller(c=(0.15, 0.30)):
    return _nenn((c[0], c[1], 0.595), TELLER_ROT, (0.095, 0.095, 0.0025))


def _teller_est(w, nenn=None, negativ=None, prims=None, seed=2):
    from wahrnehmung import griffpose as WG
    return WG.schaetzen("teller", w, 0, nenn or _nenn_teller(), seed=seed, negativ=negativ, skala_ensenso=2.5,
                        skala_d405=1.5, prims=prims)


def test_griffpose_teller_liest_die_wahrheit_nicht():
    """Wahrheit 35 mm verschoben und 3 Grad gedreht, Szene gleich: Schaetzung, Normalenpruefung und
    ausgewertete Pixel bleiben gleich (Suchfenster 30 mm um die Nennlage, nicht um die Wahrheit)."""
    from wahrnehmung import griffpose as WG
    w = _welt_teller()
    prims = WG.prims_aus_welt(w, "teller")
    a = _teller_est(w, prims=prims)
    b = _teller_est(_verschoben(w, 0, (0.035, 0.0, 0.0), gier_grad=3.0), prims=prims)
    assert a["ok"], a["gruende"]
    assert a["fehler_mm"] < 6.0
    assert b["pose_m"] == a["pose_m"]
    assert b["gier_grad"] == a["gier_grad"]
    for k in ("ensenso", "d405"):
        assert b[k]["normale_winkel_grad"] == a[k]["normale_winkel_grad"]
        assert b[k]["statistik"] == a[k]["statistik"]
    assert b["fehler_mm"] > 30.0


def test_griffpose_teller_startet_an_der_nennlage_nicht_an_der_wahrheit():
    """Teller 5 mm neben der Nennlage (so weit lassen die Staebe ihn wandern): gefunden, Fehler klein."""
    w = _welt_teller((0.155, 0.30))
    e = _teller_est(w, nenn=_nenn_teller((0.15, 0.30)))
    assert e["ok"], e["gruende"]
    assert e["fehler_mm"] < 6.0
    assert e["abstand_soll_mm"] == pytest.approx(5.0, abs=4.0)


def test_griffpose_teller_widerspruch_ensenso_d405():
    """Teller: Ensenso-Grobpose 15 mm daneben -> Ensenso und D405 widersprechen sich (TOL_TELLER_M);
    ohne Versatz liegt der Abstand klar unter der Toleranz."""
    from wahrnehmung import griffpose as WG
    w = _welt_teller()
    gut = _teller_est(w)
    assert gut["ok"], gut["gruende"]
    assert gut["ensenso_d405_abstand_mm"] < 1e3 * WG.TOL_TELLER_M
    v = _teller_est(w, negativ="versatz")
    assert v["ensenso_d405_abstand_mm"] > 1e3 * WG.TOL_TELLER_M
    assert v["gruende"] == ["ensenso_d405_widerspruch"]
    assert not v["ok"]


def test_standardkamera_ist_c57_6_s_aus_dem_katalog():
    """Brennweite aus dem Arbeitsvolumen 954 x 867 mm bei 1 m und 2472 x 2064 px; Betriebsabstand und
    sigma_k aus dem Katalog; der Standard der Station ist dieses Modell, der alte Stand bleibt waehlbar."""
    assert ENSENSO["w"] == 2472 and ENSENSO["h"] == 2064
    assert ENSENSO["f"] == pytest.approx(2472 / 0.954, rel=1e-9)        # 2591,2 px
    assert ENSENSO["fy"] == pytest.approx(2064 / 0.867, rel=1e-9)       # 2380,6 px
    assert (ENSENSO["dmin"], ENSENSO["dmax"]) == (0.75, 1.50)
    assert ENSENSO["sigma_k"] == pytest.approx(0.219e-3)
    # Rueckrechnung: bei 1 m deckt das Bild genau 954 x 867 mm
    assert 2472 / ENSENSO["f"] == pytest.approx(0.954)
    assert 2064 / ENSENSO["fy"] == pytest.approx(0.867)
    assert ensenso_modell() is ENSENSO and ensenso_modell(None) is ENSENSO
    assert ensenso_modell("b57_alt") is ENSENSO_ALT
    assert ENSENSO_ALT["f"] == pytest.approx(1628.7) and ENSENSO_ALT["dmin"] == 0.21
    assert WG.ensenso().modell is ENSENSO
    assert WG.ensenso(modell="b57_alt").modell is ENSENSO_ALT
    # anderer Katalogeintrag ueber den Schluessel: C57-8-S hat ein engeres Sichtfeld (738 mm) und 0,85-1,10 m
    m8 = modell_aus_katalog("c57_8_s")
    assert m8["f"] == pytest.approx(2472 / 0.738, rel=1e-3) and (m8["dmin"], m8["dmax"]) == (0.85, 1.10)
    with pytest.raises(KeyError):
        modell_aus_katalog("gibt_es_nicht")


def test_standardpose_neigung_und_beide_koerbe_im_betriebsabstand():
    (c, a) = WG.ENSENSO_POSE
    assert c == (0.55, 0.50, 1.35)
    v = np.asarray(a) - np.asarray(c)
    assert math.degrees(math.atan2(-v[2], math.hypot(v[0], v[1]))) == pytest.approx(60.0)
    # Alter Mast: Blickachse ebenfalls ~60 Grad (Vorstudien)
    va = np.asarray(WG.ENSENSO_POSE_ALT[1]) - np.asarray(WG.ENSENSO_POSE_ALT[0])
    assert math.degrees(math.atan2(-va[2], math.hypot(va[0], va[1]))) == pytest.approx(61.0, abs=1.0)
    # eigene Neigung: 45 Grad
    c2, a2 = WG.ensenso_pose_aus((0.55, 0.50, 1.35), 45.0)
    v2 = np.asarray(a2) - np.asarray(c2)
    assert math.degrees(math.atan2(-v2[2], math.hypot(v2[0], v2[1]))) == pytest.approx(45.0)


def _boden_punkte_kamera(modell, z):
    boden = Prim("boden", "tisch", "box", np.array([0.0, 0.0, -0.005]), np.array([2.0, 2.0, 0.005]))
    cam = Kamera("k", modell, np.array([0.0, 0.0, z]), r_greif(0.0), skala=8.0)
    fm = Fehlermodell(nass_ausfall=0.0, kante_ausfall=0.0)
    return aufnehmen([boden], cam, np.random.default_rng(3), fm)


@pytest.mark.parametrize("z,wert", [(0.70, False), (0.74, False), (0.76, True), (1.00, True), (1.49, True), (1.51, False),
                                    (1.80, False)])
def test_betriebsabstand_ausserhalb_ist_nicht_gemessen(z, wert):
    """Punkte ausserhalb 0,75-1,50 m (Kamerarahmen-z) haben keinen Wert (Grund 'bereich'); der Rest schon.
    Kamera senkrecht ueber ebenem Boden: z der Bodenpunkte = Hoehe der Kamera."""
    auf = _boden_punkte_kamera(ENSENSO, z)
    treffer = np.isfinite(auf.t_wahr)
    assert treffer.sum() > 100
    gueltig = float(np.isfinite(auf.mess[treffer]).mean())
    if wert:
        assert gueltig > 0.9
    else:
        assert gueltig == 0.0
        assert np.all(auf.grund[treffer] == 1)


def test_altes_modell_misst_im_nahbereich_das_neue_nicht():
    """Gleiche Szene, 0,6 m: altes B57 (0,21-2,0 m) misst, C57-6-S (ab 0,75 m) nicht."""
    assert np.isfinite(_boden_punkte_kamera(ENSENSO_ALT, 0.6).mess).mean() > 0.5
    assert np.isfinite(_boden_punkte_kamera(ENSENSO, 0.6).mess).sum() == 0


def test_sichtfeld_ist_954_x_867_mm_bei_1_m():
    """Das Bild der C57-6-S deckt bei 1 m eine Flaeche von 954 x 867 mm ab: Randpunkte projizieren auf die
    Bildraender (Raster volle Aufloesung)."""
    cam = Kamera("k", ENSENSO, np.array([0.0, 0.0, 1.0]), r_greif(0.0), skala=1.0)
    h, w, _, _ = cam.raster()
    assert (w, h) == (2472, 2064)
    # r_greif(0): Bild-rechts = Welt-y, Bild-unten = Welt-x; Kamera 1 m ueber dem Boden
    Q = (np.array([[0.0, 0.477, 0.0], [0.0, -0.477, 0.0], [0.4335, 0.0, 0.0], [-0.4335, 0.0, 0.0]]) - cam.C) @ cam.R
    u = Q[:, 0] / Q[:, 2] * cam.raster()[2]
    v = Q[:, 1] / Q[:, 2] * cam.raster()[3]
    assert u[:2] == pytest.approx([w / 2, -w / 2], abs=1e-6)
    assert v[2:] == pytest.approx([h / 2, -h / 2], abs=1e-6)


@pytest.mark.parametrize("modell,z", [(ENSENSO, 1.0), (ENSENSO_ALT, 0.6), (D405, 0.3)])
def test_tiefenrauschen_sigma_wie_datenblatt(modell, z):
    """Rauschen entlang des Strahls: Streuung = sigma_k * z^2 (C57-6-S 0,219 mm bei 1 m, altes Modell
    0,55 mm bei 0,6 m, D405 1,8 mm bei 0,3 m). Mit sigma 0 (Mutation) oder doppeltem sigma wird der Test rot."""
    boden = Prim("boden", "tisch", "box", np.array([0.0, 0.0, -0.005]), np.array([0.5, 0.5, 0.005]))
    cam = Kamera("k", modell, np.array([0.0, 0.0, z]), r_greif(0.0), skala=4.0)
    fm = Fehlermodell(nass_ausfall=0.0, kante_ausfall=0.0)
    auf = aufnehmen([boden], cam, np.random.default_rng(7), fm)
    ok = np.isfinite(auf.mess)
    zt = auf.t_wahr[ok] * (auf.d[ok] @ cam.R[:, 2])
    r = (auf.mess[ok] - auf.t_wahr[ok]) / (modell["sigma_k"] * zt ** 2)
    assert ok.sum() > 500
    assert float(np.std(r)) == pytest.approx(1.0, abs=0.1)
    assert abs(float(np.mean(r))) < 0.15


def test_maskenversatz_verschiebt_ganze_maske():
    m = np.zeros((20, 20), bool)
    m[5:10, 5:10] = True
    out = maske_verrauschen(m, np.random.default_rng(2), 0.0, 5.0)
    dy, dx = (int(round(v)) for v in np.random.default_rng(2).normal(0.0, 5.0, 2))
    assert (dy, dx) != (0, 0)
    assert out.sum() == m.sum()
    assert np.array_equal(out, np.roll(m, (dy, dx), (0, 1)))
    ys, xs = np.nonzero(out)
    assert (ys.mean() - 7.0, xs.mean() - 7.0) == pytest.approx((dy, dx))
    assert np.array_equal(maske_verrauschen(m, np.random.default_rng(2), 0.0, 0.0), m)


def test_teller_lage_trennt_neigung_und_drehung_in_der_ebene():
    """Vollablauf-Bewertung Teller: Drehung um die Tellernormale (Koerper-y) ist keine Kippung."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import griff_lauf as GL

    def quat(achse, grad):
        a = math.radians(grad) / 2
        return [*(math.sin(a) * np.asarray(achse, float)), math.cos(a)]
    e, d = GL.teller_lage_grad(quat([0, 1, 0], 7.5))
    assert e == pytest.approx(0.0, abs=1e-9)
    assert abs(d) == pytest.approx(7.5)
    e, d = GL.teller_lage_grad(quat([1, 0, 0], 5.0))
    assert e == pytest.approx(5.0)
    assert d == pytest.approx(0.0, abs=1e-9)


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
