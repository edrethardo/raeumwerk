"""Tests fuer den kopfueber haengenden Roboter an der senkrechten Hubachse (``raeumwerk aufbau``)."""
from __future__ import annotations

import copy
import math
from pathlib import Path

import numpy as np
import pytest

from spuelmaschine import aufbau as AU

REPO = Path(__file__).resolve().parents[1]
BEISPIEL = REPO / "beispiele" / "ueberkopf-z-achse-frontal.yaml"


def _aufbau(**rob):
    d = AU.lade_yaml(BEISPIEL)
    d["roboter"].update({"ursprung_xyz_m": [0.30, 0.45, 0.55], "gier_grad": 0, "neigung_grad": 0})
    d["roboter"].update(rob)
    return AU.Aufbau(d)


@pytest.mark.parametrize("gier,neigung", [(0, 0), (180, 30), (90, 30)])
def test_haengend_achse_bleibt_senkrecht(gier, neigung):
    """Kopfueber: Roboter-z zeigt nach unten (um die Neigung gekippt), die Achse faehrt trotzdem
    senkrecht: jede Achsstellung hebt Fuss und Gelenk 2 genau um ihren Wert in Welt-z."""
    A = _aufbau(gier_grad=gier, neigung_grad=neigung)
    p = A.pruefer(0.0, 0.0)
    q = p.chain.zero()
    lagen = {}
    for a7 in (0.0, 0.7):
        q[p.i7] = a7
        lagen[a7] = (p.T @ p.chain.fk(q, "base_link"), p.T @ p.chain.fk(q, "link_2"))
    Tb0, T20 = lagen[0.0]
    Tb1, T21 = lagen[0.7]
    assert np.allclose(Tb0[:3, 3], [0.30, 0.45, 0.55])
    assert np.allclose(Tb1[:3, 3] - Tb0[:3, 3], [0, 0, 0.7])
    assert np.allclose(T21[:3, 3] - T20[:3, 3], [0, 0, 0.7])
    assert Tb0[2, 2] == pytest.approx(-math.cos(math.radians(neigung)))  # Roboter-z nach unten
    assert T20[2, 3] < Tb0[2, 3] - 0.2                                    # Gelenk 2 haengt unter dem Fuss
    assert AU.haengend(A.d)


def test_haengend_neigung_zur_maschine():
    """Gier 180 + Neigung 30: der Arm haengt zur Maschine (-y), Gier 0 + Neigung 30 zum Raum."""
    zur = _aufbau(gier_grad=180, neigung_grad=30)
    weg = _aufbau(gier_grad=0, neigung_grad=30)
    for A, vz in ((zur, -1), (weg, 1)):
        p = A.pruefer(0.0, 0.0)
        z = (p.T @ p.chain.fk(p.chain.zero(), "base_link"))[:3, 2]
        assert np.sign(z[1]) == vz and z[1] == pytest.approx(vz * 0.5)


def test_stehende_z_achse_unveraendert():
    """Ohne Kipp/Neigung bleibt die stehende Z-Achse wie bisher (Fusslage, Gelenk 2 ueber dem Fuss)."""
    A = AU.Aufbau(AU.lade_yaml(REPO / "beispiele" / "z-achse-frontal.yaml"))
    p = A.pruefer(0.0, 0.0)
    q = p.chain.zero()
    q[p.i7] = 0.4
    Tb = p.T @ p.chain.fk(q, "base_link")
    assert Tb[2, 2] == pytest.approx(1.0) and not AU.haengend(A.d)
    assert (p.T @ p.chain.fk(q, "link_2"))[2, 3] > Tb[2, 3]


def test_haengend_eigengewicht_in_weltrichtung():
    """Kopfueber in der Kerze (Arm senkrecht nach unten): kein Schweremoment an J2; Arm waagerecht
    (J2 = 90 Grad): gleiches |Moment| wie stehend, weil die Schwerkraft in Welt-z wirkt."""
    A = _aufbau()
    p = A.pruefer(0.0, 0.0)
    q = p.chain.zero()
    q[p.i7] = 0.8
    assert AU.eigen(p, q)["joint2"] == pytest.approx(0.0, abs=1e-6)
    q[p.chain.index["joint2"]] = math.pi / 2
    stehend = AU.Aufbau(AU.normalisiere({"achse": {"richtung": "keine", "schiene": "platte"},
                                         "greifer": A.d["greifer"],
                                         "roboter": {"ursprung_xyz_m": [2.0, 2.0, 0.0]}}))
    ps = stehend.pruefer(0.0, 0.0)
    qs = ps.chain.zero()
    qs[ps.chain.index["joint2"]] = math.pi / 2
    assert AU.eigen(p, q)["joint2"] == pytest.approx(AU.eigen(ps, qs)["joint2"], abs=0.02)
    assert AU.eigen(p, q)["joint2"] > 5.0


def test_saeule_faehrt_mit_und_kollidiert():
    """``achse.saeule``: Hubprofil als zweiter Quader am Schlitten, faehrt mit der Achse, steht
    raumseitig hinter dem Fuss und zaehlt in der Kollision; der Schienenplatzhalter liegt darueber."""
    A = _aufbau()
    p = A.pruefer(0.0, 0.0)
    assert len(p.chain.links["carriage"].boxes) == 2
    q = p.chain.zero()
    mitten = []
    for a7 in (0.0, 0.5):
        q[p.i7] = a7
        prof = max(p.roboterquader(q)["carriage"], key=lambda k: k.halb[2])
        mitten.append(prof.mitte)
        assert np.allclose(prof.halb, [0.04, 0.04, (1.2 + 0.15) / 2])
    assert np.allclose(mitten[0][:2], [0.30, 0.60])
    assert mitten[1][2] - mitten[0][2] == pytest.approx(0.5)
    schiene = p.roboterquader(q)["rail"][0]
    assert schiene.mitte[2] > 0.55 + 1.2 + 1.0
    # Hindernis im Profil: Kollision carriage|...; ohne Profil keine
    d = copy.deepcopy(A.d)
    d["hindernisse"] = [{"name": "balken", "lo": [0.25, 0.55, 1.20], "hi": [0.35, 0.65, 1.30]}]
    pb = AU.Aufbau(d).pruefer(0.0, 0.0)
    q[p.i7] = 0.0
    assert "carriage|balken" in pb.kollisionen(q)
    d["achse"].pop("saeule")
    assert "carriage|balken" not in AU.Aufbau(d).pruefer(0.0, 0.0).kollisionen(q)


def test_saeule_versatz_in_welt_unabhaengig_von_gier():
    for gier in (0, 90, 180):
        p = _aufbau(gier_grad=gier).pruefer(0.0, 0.0)
        prof = max(p.roboterquader(p.chain.zero())["carriage"], key=lambda k: k.halb[2])
        assert np.allclose(prof.mitte[:2], [0.30, 0.60], atol=1e-9), gier


def test_teller_gruppen_als_liste():
    d = AU.lade_yaml(BEISPIEL)
    a = [x for x in AU.aufgaben(d) if x["gruppe"] == "teller"]
    assert len(a) == 28 and {x["teil"] for x in a} == {0, 1}
    assert sum(x["ziel"].startswith("ot_") for x in a) == 8 and sum(x["ziel"].startswith("ut_") for x in a) == 20
    rows = [{"ziel": "ot_1", "ok": True, "teil": "ot"}, {"ziel": "ot_2", "ok": False, "teil": "ot"},
            {"ziel": "ut_1", "ok": True, "teil": "ut"}]
    assert AU.abdeckung({"teller": rows}) == {"teller_ot": {"ok": 1, "n": 2}, "teller_ut": {"ok": 1, "n": 1}}
    with pytest.raises(ValueError):
        AU.normalisiere({"ziele": {"teller": [{"korb": "oberkorb"}, {"korb": "unterkorb"}]}})
    with pytest.raises(ValueError):
        AU.normalisiere({"achse": {"richtung": "x", "saeule": {}}})


def test_haengend_teller_unterkorb_erreichbar():
    """Ein Unterkorb-Teller vorn in der Mitte: kopfueber greifbar, Achse faehrt dafuer herunter;
    die Startposen zeigen zum Ziel (Fusssystem kopfueber gespiegelt)."""
    A = _aufbau()
    a = next(x for x in AU.aufgaben(A.d) if x["ziel"] == "ut_0.30_0.40")
    r = AU.rechne(A, a)
    assert r["ok"], r["grund"]
    assert r["teil"] == "ut" and 0.0 <= r["achse7"][0] <= r["achse7"][1] <= 1.2
    assert 0.55 + r["achse7"][0] > r["xyz"][2] + 0.3  # der Fuss haengt ueber dem Teller


def test_beispiel_ueberkopf_regression():
    """Voller Lauf des Beispiels (Abstand 0,60 m, 30 Grad zur Maschine): Glasplaetze, Teller beider
    Koerbe und Korbzug muessen die dokumentierten Werte liefern (Grundlage der Owner-Pruefung)."""
    d = AU.lade_yaml(BEISPIEL)
    e = AU.lauf(d, jobs=6, cache=None, gruppen=["slots", "teller", "zug"], log=lambda *_: None)
    ab = e["abdeckung"]
    assert (ab["slots"]["ok"], ab["slots"]["n"]) == (12, 16)
    erreicht = {int(r["ziel"].split("_")[1]) for r in e["gruppen"]["slots"] if r["ok"]}
    assert erreicht == {1, 2, 3, 5, 6, 7, 9, 10, 11, 13, 14, 15}
    assert ab["teller_ot"] == {"ok": 8, "n": 8} and ab["teller_ut"] == {"ok": 15, "n": 20}
    assert all(not r["ok"] for r in e["gruppen"]["teller"] if r["ziel"].endswith("_0.04"))  # hinterste Reihe
    assert ab["zug_oberkorb"]["wege_ok"] == "4/4" and ab["zug_unterkorb"]["wege_ok"] == "4/4"
    j2 = max(r["momente"]["20N"]["gesamt"]["joint2"] for r in e["gruppen"]["zug"] if r["ok"])
    assert 14.0 < j2 < 17.0  # Korbzug 20 N: J2 ueber dem igus-Maximum 12,5 Nm
