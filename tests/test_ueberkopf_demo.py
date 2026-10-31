"""Tests fuer die Physik-Demo ueber Kopf an der Hubachse (``scripts/ueberkopf_demo.py``): Aufbau-Konsistenz
mit ``raeumwerk aufbau``, Welten beider Koerbe, Ablagewagen, J2 entlang des Plans. Ohne Newton."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

import ueberkopf_demo as UD  # noqa: E402
from spuelmaschine import aufbau as AU  # noqa: E402

PRUEF = REPO / "beispiele" / "ueberkopf-z-achse-frontal.yaml"


@pytest.fixture(scope="module")
def demo():
    return UD.demo_werte()


@pytest.fixture(scope="module")
def yaml_demo(demo):
    return AU.lade_yaml(REPO / demo["aufbau"])


def _wagen(d):
    return {h["name"]: h for h in d["hindernisse"]}


def test_demo_aufbau_ist_die_gepruefte_lage(yaml_demo):
    """Gleicher Roboter, gleiche Achse wie das Pruefbeispiel, nur Fussmitte 0,45 m vor der Front (Rasterlage
    mit dem kleinsten J2), 30 Grad zur Maschine."""
    p = AU.lade_yaml(PRUEF)
    assert yaml_demo["roboter"]["ursprung_xyz_m"] == [0.30, 0.45, 0.55]
    for k in ("gier_grad", "montage", "neigung_grad"):
        assert yaml_demo["roboter"][k] == p["roboter"][k]
    assert yaml_demo["roboter"]["neigung_grad"] == 30
    assert yaml_demo["achse"] == p["achse"]
    assert yaml_demo["greifer"] == p["greifer"]
    assert "zug" not in yaml_demo["ziele"]          # Koerbe zieht der Mensch


def test_ablageplaetze_der_demo_stehen_im_aufbau_und_auf_dem_wagen(demo, yaml_demo):
    """Matte, Glasablage und Staenderplaetze der Demo sind genau die Ablageziele ``wagen_*`` des Aufbau-YAML
    und liegen auf der Wagenplatte (Oberkante = ``wagen_oberkante_m``)."""
    h = _wagen(yaml_demo)
    platte = h["wagen_platte"]
    assert platte["hi"][2] == pytest.approx(demo["wagen_oberkante_m"])
    st = demo["staender"]
    plaetze = [tuple(demo["glaeser"]["matten_xy_m"][0]), tuple(demo["glaeser"]["ablage_xy_m"][0])]
    plaetze += [(st["staender_xy_m"][0] + k * st["staender_teilung_m"][0], st["staender_xy_m"][1] + k * st["staender_teilung_m"][1])
                for k in range(UD.STAENDER_PLAETZE)]
    ziele = {tuple(np.round(h[n]["glas_mitte"][:2], 4)) for n in yaml_demo["ziele"]["ablage"]["glaeser"]}
    for i, (x, y) in enumerate(plaetze):
        if i < 3:
            assert (round(x, 4), round(y, 4)) in ziele
        assert platte["lo"][0] < x < platte["hi"][0] and platte["lo"][1] < y < platte["hi"][1]
    # Tuer x 0..0,60: der Unterbau steht daneben, nur die Platte kragt ueber die Tuerkante
    assert h["wagen_unterbau"]["lo"][0] > 0.60


def _staenderplatz_2(d, demo):
    """Aufbau-YAML mit dem Stellvertreter wagen_3 auf Staenderplatz 2 (5 cm weiter in x)."""
    import copy
    d = copy.deepcopy(d)
    st = demo["staender"]
    for h in d["hindernisse"]:
        if h["name"] == "wagen_3":
            h["glas_mitte"][0] = round(h["glas_mitte"][0] + st["staender_teilung_m"][0], 4)
            h["glas_mitte"][1] = round(h["glas_mitte"][1] + st["staender_teilung_m"][1], 4)
    return d


def test_ablage_mit_raeumwerk_aufbau_erreichbar(yaml_demo, demo):
    """``raeumwerk aufbau`` rechnet die Wagenplaetze: alle erreichbar und kollisionsfrei (Glas kopfueber von oben,
    Stellvertreter auch fuer beide Staenderplaetze)."""
    for d, nur in ((yaml_demo, None), (_staenderplatz_2(yaml_demo, demo), "wagen_3")):
        A = AU.Aufbau(d)
        aufg = [a for a in AU.aufgaben(d) if a["gruppe"] == "ablage"]
        assert [a["ziel"] for a in aufg] == d["ziele"]["ablage"]["glaeser"]
        for a in aufg:
            if nur and a["ziel"] != nur:
                continue
            r = AU.rechne(A, a)
            assert r["ok"], (a["ziel"], r.get("grund"))


@pytest.fixture(scope="module")
def welten(demo):
    out = {}
    for o in UD.OBJEKTE:
        D, var, f, sz, A = UD.szenario_und_aufbau(o, D=demo)
        abw, tabw = UD.abweichung(o, None, D)
        out[o] = (UD.welt(A, sz, f, abw, tabw, D, o), sz, A)
    return out


def test_welt_glas_oberkorb_ausgezogen_ablage_auf_dem_wagen(welten, demo):
    w, sz, A = welten["glas"]
    assert w.pruefer.sc["pose"]["oberkorb_auszug_m"] == pytest.approx(UD.AUSZUG_M)
    assert w.pruefer.sc["pose"]["unterkorb_auszug_m"] == pytest.approx(0.0)
    z = demo["wagen_oberkante_m"]
    assert w.matten[0].aabb()[0][2] == pytest.approx(z)
    assert w.glas_ziel[0].mitte[2] == pytest.approx(z + w.glas_h / 2.0)
    assert any(k.name == "arbeitsplatte" and k.aabb()[1][2] == pytest.approx(z) for k in w.statisch)
    assert len(w.glas_start) == 8 and len(w.teller) == 6


def test_welt_unterkorb_oberkorb_eingeschoben_teller_auf_dem_korbboden(welten, demo):
    w, sz, A = welten["teller_ut"]
    p = w.pruefer
    assert p.sc["pose"]["oberkorb_auszug_m"] == pytest.approx(0.0)
    assert p.sc["pose"]["unterkorb_auszug_m"] == pytest.approx(UD.AUSZUG_M)
    u = demo["teller_ut"]
    assert len(w.glas_start) == len(u["tiefe_m"])
    boden = p.m["unterkorb"]["boden_hoehe_m"]
    vorne = p.m["unterkorb"]["vorne_eingeschoben_y_m"] + UD.AUSZUG_M
    for k, dy in zip(w.glas_start, u["tiefe_m"]):
        assert k.mitte[2] == pytest.approx(boden + u["durchmesser_m"] / 2.0)
        assert k.mitte[1] == pytest.approx(vorne - dy)
    namen = {k.name for k in w.statisch}
    assert {"abgelegt_glas", "abgelegt_teller_ot"} <= namen      # was die Laeufe davor abgelegt haben
    assert not [k for k in w.statisch if k.name.startswith("glasfest_")]


def test_teller_ot_ohne_das_schon_abgeraeumte_glas(welten):
    w, sz, A = welten["teller_ot"]
    fest = [k.name for k in w.statisch if k.name.startswith("glasfest_")]
    assert len(fest) == 7 and "glasfest_3" not in fest
    assert "abgelegt_glas" in {k.name for k in w.statisch}
    assert sz["teller"]["zuordnung"] == [[1, 2]]
    assert welten["teller_ut"][1]["teller"]["zuordnung"] == [[1, 1]]


class _Plan:
    def __init__(self, q):
        self.q, self.dauer = q, 1.0

    def sample(self, t):
        return self.q, None, "1:aushub" if t < 0.5 else "heim"


def test_j2_entlang_mit_last_nur_in_der_hand(welten):
    w, sz, A = welten["glas"]
    p = w.pruefer
    q = p.chain.zero()
    q[p.chain.index["joint2"]] = 0.6
    q[p.chain.index["joint3"]] = 0.8
    j = UD.j2_entlang(_Plan(q), p, 0.5, dt=0.1)
    ohne = abs(float(AU.schweremomente(p, q, 0.0)[p.chain.index["joint2"]]))
    mit = abs(float(AU.schweremomente(p, q, 0.5)[p.chain.index["joint2"]]))
    assert j["phasen"]["heim"]["j2_max_nm"] == pytest.approx(ohne, abs=0.01)
    assert j["phasen"]["aushub"]["j2_max_nm"] == pytest.approx(mit, abs=0.01)
    assert mit != pytest.approx(ohne)
    assert j["j2_max_nm"] == pytest.approx(max(mit, ohne), abs=0.01)
