"""Tests fuer die Mastpositions-Auswertung: Nutzbarkeitsfenster, Einfallswinkel der Teller, Rand- gegen Flaechenzaehlung.

Die Erwartungswerte der Zaehlung stammen aus den Rohzeilen der Rechnung auf Schaetzerauflaesung (Skala 2) mit
dem Arm in der Ruhepose; der Test rechnet ohne Arm (Arm-Quader liegen nicht im Repo) und prueft dieselben Zahlen.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import mast_raster as MR  # noqa: E402
import mast_teller_winkel as MW  # noqa: E402
from wahrnehmung import griffpose as WG  # noqa: E402


def _platz(z, sichtbar=1.0, brauchbar=True, flaeche=True):
    return dict(z_mittel_m=z, anteil_sichtbar=sichtbar, brauchbar=brauchbar, brauchbar_flaeche=flaeche)


# --- nutzbar: z-Fenster 0,80-1,45 m (Betriebsabstand 0,75-1,50 m mit 5 cm Reserve) -------------------

def test_fenster_ist_betriebsabstand_mit_5_cm_reserve():
    assert MR.ENSENSO["dmin"] + MR.RESERVE_M == pytest.approx(0.80)
    assert MR.ENSENSO["dmax"] - MR.RESERVE_M == pytest.approx(1.45)


@pytest.mark.parametrize("z, erwartet", [(0.79, False), (0.799, False), (0.801, True), (1.0, True),
                                          (1.449, True), (1.451, False), (1.49, False), (0.5, False)])
def test_nutzbar_z_fenster(z, erwartet):
    assert MR.nutzbar("glas_1", _platz(z)) is erwartet
    assert MR.nutzbar("oberteller_0_1", _platz(z)) is erwartet


def test_nutzbar_braucht_sicht_und_brauchbar():
    assert not MR.nutzbar("glas_1", _platz(1.0, sichtbar=0.0))
    assert not MR.nutzbar("glas_1", _platz(None))
    assert not MR.nutzbar("glas_1", _platz(1.0, brauchbar=False))


def test_nutzbar_teller_flaeche_gegen_rand():
    p = _platz(1.0, brauchbar=True, flaeche=False)       # Rand reicht, Flaeche nicht
    assert MR.nutzbar("oberteller_0_1", p, teller_flaeche=False)
    assert not MR.nutzbar("oberteller_0_1", p, teller_flaeche=True)
    assert MR.nutzbar("glas_1", p)                          # Glas kennt nur ``brauchbar``


# --- Einfallswinkel: cos w = |dy| / Abstand, unabhaengig von der Neigung ---------------------------------

def test_teller_winkel_bekannter_fall():
    C = (0.55, 0.70, 1.25)
    P = np.array([0.15, 0.34, 0.515])
    d = np.array(C) - P                                     # (0,40; 0,36; 0,735)
    erwartet = float(np.degrees(np.arccos(0.36 / np.sqrt(0.40 ** 2 + 0.36 ** 2 + 0.735 ** 2))))
    assert MW.winkel(C, P) == pytest.approx(erwartet, abs=1e-9)
    assert MW.winkel(C, P) == pytest.approx(66.7, abs=0.1)
    assert np.linalg.norm(d) == pytest.approx(0.911, abs=1e-3)
    # Kamera genau vor dem Teller (gleiche x, z): Blick entlang der Normalen -> 0 Grad; seitlich in x: 90 Grad
    assert MW.winkel((0.15, 0.80, 0.515), P) == pytest.approx(0.0, abs=1e-9)
    assert MW.winkel((0.60, 0.34, 0.515), P) == pytest.approx(90.0, abs=1e-9)


def test_teller_winkel_haengt_nicht_von_der_neigung_ab():
    P = np.array([0.15, 0.34, 0.515])
    n60 = WG.ensenso_pose_aus((0.55, 0.70, 1.25), 60.0)[0]
    n55 = WG.ensenso_pose_aus((0.55, 0.70, 1.25), 55.0)[0]
    assert MW.winkel(n60, P) == pytest.approx(MW.winkel(n55, P))


def test_teller_winkel_hauptposition_gegen_rohtabelle():
    """Hauptposition (0,55; 0,70; 1,25): Rohtabelle 11/14 unter 60 Grad (groesster 62,4) bei 0,225 m, 3/14 (72,4) bei 0,45 m."""
    for aus, unter, w_max in ((0.225, 11, 62.4), (0.45, 3, 72.4)):
        zen = MW.teller_zentren(aus)
        assert len(zen) == 14
        w = np.array([MW.winkel((0.55, 0.70, 1.25), c) for _, _, c in zen])
        assert int((w < 60.0).sum()) == unter
        assert float(w.max()) == pytest.approx(w_max, abs=0.1)


# --- Rand- gegen Flaechenzaehlung an zwei Mastorten (Oberkorb-Teller, Auszug 0,45 m, Skala 2) -----------

def _teller_zaehlung(y, z, neigung):
    C, A = WG.ensenso_pose_aus((MR.MAST_X, y, z), neigung)
    r = MR.rechne_zustand(C, A, "ober_teller", 0.45, arm=None, skala=2.0)
    pl = r["plaetze"]
    return (sum(MR.nutzbar(k, v, True) for k, v in pl.items()),
            sum(MR.nutzbar(k, v, False) for k, v in pl.items()), len(pl))


@pytest.mark.parametrize("y, z, neigung, flaeche, rand", [
    (0.70, 1.25, 55.0, 5, 8),      # Hauptposition: Rohtabelle Flaeche 5/8, mit Rand 8/8
    (0.50, 1.35, 60.0, 0, 7),      # Bestand: Rohtabelle Flaeche 0/8, mit Rand 7/8 (ein Teller unter der 0,80-m-Reserve)
])
def test_teller_flaeche_gegen_rand_am_mastort(y, z, neigung, flaeche, rand):
    f, r, n = _teller_zaehlung(y, z, neigung)
    assert n == 8
    assert f == flaeche and r == rand
    assert r >= f                                           # der Rand ist die obere Schranke
