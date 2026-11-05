"""Tests fuer wahrnehmung.verdeckung: bekannter Fall (Objekt hinter einem Stab teilweise verdeckt)."""
from __future__ import annotations

import numpy as np
import pytest

from wahrnehmung import verdeckung as V
from wahrnehmung.strahlen import ENSENSO, Kamera, Prim

KAMERA = dict(ENSENSO)


def _cam(skala=8.0):
    # Kamera 1,0 m ueber dem Ursprung, blickt senkrecht nach unten (Kamerarahmen: z = Welt -z)
    return Kamera.zielend("t", KAMERA, [0.0, 0.0, 1.0], [0.0, 0.1, 0.0], skala)


def _glas(c=(0.0, 0.0, 0.1)):
    return Prim("g", "glas", "zyl", np.array(c, float), np.array([0.0375, 0.0375, 0.055]), np.eye(3), "g")


def _teller(c=(0.0, 0.0, 0.1)):
    # liegender Teller (Achse senkrecht): Kamera sieht die Flaeche von oben
    return Prim("t", "teller", "zyl", np.array(c, float), np.array([0.095, 0.095, 0.0025]), np.eye(3), "t")


def _stab(x, breite=0.006):
    # Stab in y-Richtung, 0,3 m ueber dem Objekt, in x bei ``x``
    return Prim("stab", "oberkorb", "box", np.array([x, 0.0, 0.5]), np.array([breite / 2, 0.3, 0.003]), np.eye(3), "stab")


def test_ohne_hindernis_voll_sichtbar():
    r = V.sichtbarkeit([_glas()], _cam(), ["g"])["g"]
    assert r["anteil_sichtbar"] == pytest.approx(1.0)
    assert r["anteil_im_bild"] == pytest.approx(1.0)
    assert r["brauchbar"]


def test_stab_vor_glas_verdeckt_streifen():
    """Ein 6-mm-Stab genau ueber der Glasachse verdeckt einen Streifen: Anteil ~ Streifenbreite im Glasbild.

    Stab in 0,5 m Hoehe, Kamera in 1,0 m: der Stab erscheint 2x vergroessert gegenueber der Glasoberkante
    (Glas bei 0,155, Abstaende 0,5 vs 0,845 m) -> verdeckte Breite am Glas = 6 mm * 0,845 / 0,5 = 10,1 mm von
    75 mm Durchmesser; Flaeche der Kreisscheibe: Streifen durch die Mitte ~ 10,1/75 * 4/pi ~ 17 %."""
    cam = _cam(skala=4.0)
    voll = V.sichtbarkeit([_glas()], cam, ["g"])["g"]
    mit = V.sichtbarkeit([_glas(), _stab(0.0)], cam, ["g"])["g"]
    erwartet = 1.0 - (0.006 * 0.845 / 0.5 / 0.075) * 4 / np.pi
    assert mit["n_voll"] == voll["n_voll"]
    assert mit["anteil_sichtbar"] == pytest.approx(erwartet, abs=0.03)
    assert mit["anteil_sichtbar"] < voll["anteil_sichtbar"] - 0.1


def test_stab_neben_glas_aendert_nichts():
    cam = _cam()
    r = V.sichtbarkeit([_glas(), _stab(0.2)], cam, ["g"])["g"]
    assert r["anteil_sichtbar"] == pytest.approx(1.0)


def test_vollstaendig_verdeckt_nicht_brauchbar():
    platte = Prim("platte", "oberkorb", "box", np.array([0.0, 0.0, 0.5]), np.array([0.3, 0.3, 0.003]), np.eye(3), "platte")
    r = V.sichtbarkeit([_glas(), platte], _cam(), ["g"])["g"]
    assert r["anteil_sichtbar"] == 0.0 and not r["brauchbar"]


def test_stab_verdeckungskante_ist_keine_glaskontur():
    """Hinter einem breiten Balken ist die Hälfte weg: die Kante des Balkens zählt nicht als Glaskontur."""
    balken = Prim("balken", "oberkorb", "box", np.array([0.2, 0.0, 0.5]), np.array([0.2, 0.3, 0.003]),
                  np.eye(3), "balken")           # Kante bei x = 0 (Perspektive um die Kameraachse laesst x = 0 stehen)
    cam = _cam(skala=4.0)
    r = V.sichtbarkeit([_glas(), balken], cam, ["g"])["g"]
    assert 0.3 < r["anteil_sichtbar"] < 0.7
    assert r["kontur_inlier"] < 0.9          # ein Teil der Randpixel ist Balkenkante


def test_teller_bogen_voll_und_verdeckt():
    """Stehender Teller (Normale in y, wie im Korb), Kamera schraeg von vorn oben; eine Wand ueber die
    halbe Tellerbreite nimmt die rechte Haelfte, der obere Konturbogen schrumpft von ~180 auf ~90 Grad."""
    rot = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0]])
    teller = Prim("t", "teller", "zyl", np.array([0.0, 0.0, 0.1]), np.array([0.095, 0.095, 0.0025]), rot, "t")
    cam = Kamera.zielend("t", KAMERA, [0.0, 0.9, 0.9], [0.0, 0.0, 0.1], 4.0)
    voll = V.sichtbarkeit([teller], cam, ["t"])["t"]
    assert voll["brauchbar"] and voll["kontur_bogen_grad"] > 150
    halb = Prim("b", "oberkorb", "box", np.array([0.3, 0.45, 0.0]), np.array([0.3, 0.003, 1.0]), np.eye(3), "b")
    r = V.sichtbarkeit([teller, halb], cam, ["t"])["t"]
    assert 0.3 < r["anteil_sichtbar"] < 0.7
    assert r["kontur_bogen_grad"] < voll["kontur_bogen_grad"]


def test_bereichsgrenze_zaehlt_als_nicht_gemessen():
    """Kamera 0,6 m ueber dem Objekt (unter dem Betriebsabstand 0,75 m): sichtbar, aber nicht gemessen."""
    cam = Kamera.zielend("t", KAMERA, [0.0, 0.0, 0.7], [0.0, 0.1, 0.0], 8.0)
    r = V.sichtbarkeit([_teller()], cam, ["t"])["t"]
    assert r["anteil_sichtbar"] > 0.9 and r["anteil_gemessen"] == 0.0 and not r["brauchbar"]


def test_ausserhalb_bild_zaehlt_nicht_sichtbar():
    cam = _cam()
    r = V.sichtbarkeit([_glas((0.6, 0.0, 0.1))], cam, ["g"])["g"]       # 0,6 m neben der Achse: aus dem Bild
    assert r["n_voll"] > 0 and r["n_im_bild"] == 0 and r["anteil_sichtbar"] == 0.0


def test_kamera_huellen_enthalten_ort_und_saeule():
    h = V.kamera_huellen([0.55, 0.5, 1.35], [0.3, 0.17, 0.63], saeule=True)
    assert [n for n, _, _ in h] == ["kamera", "saeule", "ausleger_y", "ausleger_x"]
    lo, hi = h[0][1], h[0][2]
    assert np.all(lo < [0.55, 0.5, 1.35]) and np.all(hi > [0.55, 0.5, 1.35])
    assert hi[0] - lo[0] >= 0.29 - 1e-9
    s_lo, s_hi = h[1][1], h[1][2]
    assert s_lo[2] == pytest.approx(0.86) and s_hi[2] > 1.35
