"""Tests fuer die eigenen 100-mm-Finger: Parameter, CAD-Ergebnis, Balkenrechnung."""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from finger import festigkeit as FE
from finger.parameter import Finger, roh
from spuelmaschine import masse

REPO = Path(__file__).resolve().parents[1]
CAD = REPO / "cad" / "finger"


@pytest.fixture(scope="module")
def f():
    return Finger.laden()


def test_jeder_wert_hat_quelle_oder_annahme():
    assert masse.ohne_quelle(roh()) == []


def test_masse_im_auftragsrahmen(f):
    assert f.L == 100.0
    assert 15.0 <= f.b <= 20.0


@pytest.mark.parametrize("d_mm", [65.0, 75.0, 85.0])
def test_v_kontur_beruehrt_glas_auf_beiden_auflagen(f, d_mm):
    """Ein Glas (Achse parallel zum Finger) liegt auf beiden Flanken innerhalb der Auflagen."""
    x = d_mm / 2.0 * math.sin(f.gamma)
    xa0, xa1 = f.auflage_x
    assert xa0 + 0.5 <= x <= xa1 - 0.5


def test_greifer_oeffnet_fuer_85_mm_und_klemmt_die_tellerfahne(f):
    ab = f.auflage_ueberstand
    # ganz offen (105 mm Backen): Auflagen 5 mm Luft je Seite zum 85-mm-Glas
    assert f.bezug_oeffnung(105.0) - 2 * ab >= 85.0 + 2 * 5.0
    # ganz zu (5 mm Backen): die Lippen (Bezugsebene) kommen enger als die Fahne zusammen
    assert f.bezug_oeffnung(5.0) < float(f.p["teller"]["fahne_dicke_mm"])
    # in der Kerbe hat der Randwulst Platz, ueber die Lippen kommt er nicht
    kt = float(f.p["teller"]["kerbe_tiefe_mm"])
    wulst = float(f.p["teller"]["wulst_dicke_mm"])
    fahne = float(f.p["teller"]["fahne_dicke_mm"])
    assert fahne + 2 * kt > wulst > fahne
    assert f.p["teller"]["kerbe_laenge_mm"] > wulst


def test_lippe_steht_hinter_den_auflagen(f):
    """Beim Glasgriff beruehren die weichen Auflagen zuerst, nicht die harte Lippe."""
    r = 37.5
    x = r * math.sin(f.gamma)
    # Glasoberflaeche ueber der Fingermitte (Scheitel) vs. Lippenmitte (V-Grund)
    scheitel = f.flanke_y(x) + f.auflage_ueberstand - r * (1 - math.cos(f.gamma))
    assert scheitel > -f.v_tiefe


def test_balken_gleichfoermig_wie_formel(f):
    """Durchbiegung eines gleichfoermigen Kragbalkens = F l^3 / (3 E I)."""
    g = Finger.laden()
    g.p["geometrie"].update(dicke_wurzel_mm=10.0, dicke_spitze_mm=10.0)
    g.netto_hoehe = lambda z: (10.0, "schaft")
    lf = {"F_y": 10.0, "z_F": g.L}
    l = g.L - g.z_platte
    soll = 10.0 * l ** 3 / (3 * 1650.0 * g.b * 1000.0 / 12.0)
    assert FE.durchbiegung(g, lf, 1650.0) == pytest.approx(soll, rel=1e-3)


def test_gewaehlter_werkstoff_sicherheit_mindestens_2(f):
    e = FE.rechne(f)
    w = e["werkstoffe"][f.gewaehlt]
    assert e["ok"] and w["sicherheit_min"] >= 2.0
    assert {c["lastfall"] for c in w["faelle"]} == {"glas_griff", "teller_lippe"}
    assert max(c["F_n"] for c in w["faelle"]) >= 20.0
    # PETG (Lagenhaftung) faellt bei 20 N an der Lippe durch: die Rechnung unterscheidet
    assert not e["werkstoffe"]["petg_fdm"]["ok"]


def test_doppelte_greifkraft_halbiert_die_sicherheit(f):
    a = FE.rechne(f, [10.0])["werkstoffe"]["pa12_sls"]["sicherheit_min"]
    b = FE.rechne(f, [20.0])["werkstoffe"]["pa12_sls"]["sicherheit_min"]
    assert b < a * 0.6


def test_cad_dateien_passen_zu_den_parametern(f):
    info = json.loads((CAD / "finger_100.json").read_text())
    assert info["gueltig"]
    assert set(info["merkmale"]) >= {"schaft", "v_kontur", "auflage_taschen", "kerbe", "kerbe_radius",
                                     "fase_spitze", "lochbild", "aussenkanten_radius"}
    assert info["huelle_mm"]["max"][2] == pytest.approx(f.L, abs=0.01)
    assert info["huelle_mm"]["max"][0] - info["huelle_mm"]["min"][0] == pytest.approx(f.b, abs=0.01)
    assert info["volumen_finger_mm3"] == pytest.approx(f.volumen_mm3(), rel=0.03)
    for wk in f.werkstoffe:
        assert info["massen_g"][wk] == pytest.approx(f.masse_g(wk, info["volumen_finger_mm3"]), abs=0.15)
    for n in ("finger_100.step", "finger_100.stl", "auflage.stl"):
        p = CAD / n
        assert p.exists() and 0 < p.stat().st_size < 2_000_000
    assert (CAD / "finger_100.step").read_text(errors="ignore").startswith("ISO-10303-21")
