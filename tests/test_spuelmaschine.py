"""Spuelmaschine: Masse mit Quellen, Geometrie, Slots, Erreichbarkeit, Newton.

Ohne Newton laufen nur numpy-Tests (Geometrie, IK, Kollision). Der
Newton-Stabilitaetstest startet ``python -m spuelmaschine.stabilitaet`` mit
einem Python, in dem Newton installiert ist; er laeuft nur mit
``RAEUMWERK_RUN_NEWTON=1`` und ``RAEUMWERK_NEWTON_PYTHON`` (z. B. ein uvx-
oder venv-Python, Rechnung auf der CPU, siehe docs/spuelmaschine.md).
"""
from __future__ import annotations

import itertools
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("yaml")

from spuelmaschine import erreichbarkeit, geometrie, masse  # noqa: E402

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def m():
    return masse.load()


@pytest.fixture(scope="module")
def sc():
    return masse.load_szene()


@pytest.fixture(scope="module")
def sz(m, sc):
    return geometrie.baue(m, sc["pose"]["oberkorb_auszug_m"], sc["pose"]["unterkorb_auszug_m"])


@pytest.fixture(scope="module")
def pruefer(sc):
    return erreichbarkeit.Pruefer(erreichbarkeit.lage_aus_szene(sc), sc)


# --- Masse und Quellen --------------------------------------------------------

@pytest.mark.parametrize("datei", [masse.MASCHINE, masse.SZENE])
def test_every_value_has_source(datei):
    raw = masse.roh(datei)
    assert masse.ohne_quelle(raw) == []
    # jede genannte Quelle wird auch benutzt (keine toten Eintraege)
    text = datei.read_text(encoding="utf-8")
    for q in raw["quellen"]:
        assert f"src: {q}" in text, q


def test_ohne_quelle_findet_fehlende_quelle():
    raw = {"quellen": {"a": "x"}, "t": {"ok": {"wert": 1, "src": "a"}, "falsch": {"wert": 2, "src": "b"},
                                         "nackt": 3, "liste": [1, 2]}}
    assert sorted(masse.ohne_quelle(raw)) == ["t.falsch", "t.liste", "t.nackt"]


def test_masse_standard_60cm(m):
    n, ge, tu = m["nische"], m["geraet"], m["tuer"]
    assert n["breite_m"] == pytest.approx(0.60)
    assert 0.815 <= n["hoehe_m"] <= 0.875  # Bosch-Bereich, ASKO 820-870
    assert n["tiefe_m"] == pytest.approx(0.55)
    assert ge["breite_m"] <= n["breite_m"] and ge["tiefe_m"] <= n["tiefe_m"]
    # Tuer: Tiefe bei geoeffneter Tuer 1150 mm (Bosch) = Geraetetiefe + Tuerlaenge
    assert ge["tiefe_m"] + tu["laenge_m"] == pytest.approx(1.150)
    assert 0.06 <= tu["scharnier_hoehe_m"] <= 0.14  # ASKO-Sockelbereich
    ok, uk = m["oberkorb"], m["unterkorb"]
    innen = ge["breite_m"] - 2 * ge["wand_m"]
    assert ok["breite_m"] < innen and uk["breite_m"] < innen
    assert ok["tiefe_m"] < ge["tiefe_m"] - ge["rueckwand_m"]
    # Glas passt kopfueber unter die lichte Hoehe des Oberkorbs, Korb unter die Decke
    assert m["glas"]["hoehe_m"] < ok["lichte_hoehe_m"]
    assert ok["boden_hoehe_m"] + ok["lichte_hoehe_m"] < n["hoehe_m"] - ge["decke_m"]
    assert uk["boden_hoehe_m"] + uk["wand_hoehe_m"] < ok["boden_hoehe_m"]


# --- Geometrie ----------------------------------------------------------------

def test_geometrie_teile(sz):
    gruppen = {k.gruppe for k in sz.koerper}
    assert {"korpus", "tuer", "oberkorb", "unterkorb", "glashalter", "arbeitsplatte"} <= gruppen
    namen = [k.name for k in sz.koerper]
    assert len(namen) == len(set(namen))
    # "wenige Staebe, keine tausend Draehte"
    assert len(sz.gruppe("oberkorb")) < 60 and len(sz.gruppe("unterkorb")) < 60
    tuer = sz.get("tuer").aabb()
    # Tuer liegt waagerecht vor der Maschine, Oberkante auf Scharnierhoehe
    assert tuer[1, 2] == pytest.approx(sz.m["tuer"]["scharnier_hoehe_m"])
    assert tuer[1, 1] == pytest.approx(sz.m["tuer"]["laenge_m"])
    assert tuer[0, 1] == pytest.approx(0.0, abs=1e-9)


def test_keine_ueberschneidungen(sz):
    """Zwischen Teilen verschiedener Gruppen hoechstens Beruehrung (z. B. Glashalter auf dem Korbboden)."""
    treffer = []
    for a, b in itertools.combinations(sz.koerper, 2):
        if a.gruppe == b.gruppe:
            continue  # Staebe eines Korbs stossen aneinander
        o = geometrie.ueberlappung(a, b)
        if o > 1e-6:
            treffer.append((a.name, b.name, round(o, 4)))
    assert treffer == []


def test_ueberlappung_erkennt_durchdringung(sz):
    g = sz.glas(sz.slots[0], "probe")
    tiefer = sz.glas(sz.slots[0] - [0, 0, 0.003], "probe")
    boden = sz.get("oberkorb_boden")
    assert geometrie.ueberlappung(g, boden) == pytest.approx(0.0, abs=1e-9)
    assert geometrie.ueberlappung(tiefer, boden) == pytest.approx(0.003, abs=1e-9)
    nachbar = sz.glas(sz.slots[0] + [0, 0.07, 0], "nachbar")
    assert geometrie.ueberlappung(g, nachbar) == pytest.approx(0.005, abs=1e-9)


def test_slots_vier_glaeser_kopfueber_im_korb(sz):
    assert len(sz.slots) == 4
    gl = sz.glaeser_im_korb()
    boden = sz.get("oberkorb_boden")
    r = sz.m["glas"]["durchmesser_m"] / 2
    korb = boden.aabb()
    wand = sz.m["gitter"]["stab_dicke_m"]
    for g in gl:
        # Rand (unten, kopfueber) liegt auf dem Korbboden
        assert g.unten == pytest.approx(boden.oben)
        assert korb[0, 0] + wand + r <= g.mitte[0] <= korb[1, 0] - wand - r
        assert korb[0, 1] + wand + r <= g.mitte[1] <= korb[1, 1] - wand - r
        assert g.oben < sz.oberkorb_boden_z + sz.m["oberkorb"]["lichte_hoehe_m"]
        # nur der Korbboden wird beruehrt, zu allem anderen >= 5 mm Luft
        for k in sz.koerper:
            if k.name == "oberkorb_boden":
                continue
            assert geometrie.ueberlappung(g, k, 0.005) <= 0, (g.name, k.name)
    for a, b in itertools.combinations(gl, 2):
        assert geometrie.ueberlappung(a, b, 0.02) <= 0  # mind. 2 cm zwischen den Glaesern
    # Glashalter: zu jedem Slot Streben auf beiden Seiten in y und x
    for g in gl:
        seiten = set()
        for k in sz.gruppe("glashalter"):
            d = k.mitte[:2] - g.mitte[:2]
            if abs(d[1]) < 0.07 and abs(d[0]) < 0.08:
                seiten.add(("y" if k.halb[0] > k.halb[1] else "x", np.sign(d[1] if k.halb[0] > k.halb[1] else d[0])))
        assert len(seiten) == 4, (g.name, seiten)


def test_ablage_auf_arbeitsplatte(sz):
    platte = sz.get("arbeitsplatte").aabb()
    gl = [sz.glas(p, f"a{i}") for i, p in enumerate(sz.ablage)]
    assert len(gl) == 4
    for g in gl:
        assert g.unten == pytest.approx(platte[1, 2])
        assert platte[0, 0] + 0.04 <= g.mitte[0] <= platte[1, 0] - 0.04
        assert platte[0, 1] + 0.04 <= g.mitte[1] <= platte[1, 1] - 0.04
        assert g.mitte[0] > sz.m["nische"]["breite_m"]  # neben der Maschine
    for a, b in itertools.combinations(gl, 2):
        assert geometrie.ueberlappung(a, b, 0.02) <= 0


def test_korbauszug_ist_schubgelenk(m):
    innen = geometrie.baue(m, oberkorb_auszug=0.0)
    aussen = geometrie.baue(m)
    a0, a1 = innen.get("oberkorb_boden").aabb(), aussen.get("oberkorb_boden").aabb()
    assert a1[0, 1] - a0[0, 1] == pytest.approx(m["oberkorb"]["auszug_max_m"])
    assert np.allclose(a1[:, [0, 2]], a0[:, [0, 2]])  # nur entlang y verschoben
    assert a0[1, 1] < 0  # eingeschoben ganz in der Maschine
    assert aussen.slots[0][1] - innen.slots[0][1] == pytest.approx(m["oberkorb"]["auszug_max_m"])
    g = {j["name"]: j for j in aussen.korbgelenke}
    assert g["oberkorb_auszug"]["typ"] == "prismatic" and g["oberkorb_auszug"]["achse"] == [0, 1, 0]
    with pytest.raises(ValueError):
        geometrie.baue(m, oberkorb_auszug=m["oberkorb"]["auszug_max_m"] + 0.01)


# --- Erreichbarkeit ---------------------------------------------------------------

def test_gewaehlte_lage_erreicht_alles_kollisionsfrei(pruefer, sc):
    assert pruefer.lage_konflikte() == []
    res = pruefer.pruefe(seed=int(sc["raster"]["seed"]))
    assert [e.ziel for e in res] == [f"slot_{i}" for i in range(1, 5)] + [f"ablage_{i}" for i in range(1, 5)]
    for e in res:
        assert e.ok, (e.ziel, e.grund)
        assert e.ik_fehler_max_m < 0.001
        assert e.kollisionen == []
        assert e.j5_max_grad <= 95.0 + 1e-6
        assert e.gelenksprung_max_grad <= sc["greifen"]["gelenksprung_max_grad"]
    # Slots: Vorposition -> Greifen -> Aushub in 1-cm-Schritten (10 + 15 + 1)
    assert all(e.wegpunkte == 26 for e in res[:4])


def test_greifpose_trifft_glas(pruefer, sc):
    """FK der gefundenen Greifpose: TCP ueber der Glasmitte, Greifer senkrecht nach unten."""
    z = pruefer.ziele()[0]
    e = pruefer.pruefe_ziel(z, int(sc["raster"]["seed"]))
    t = pruefer.tcp_welt(np.array(e.q_greif))
    soll = z.glas.mitte[2] - z.glas.halb[2] + sc["greifen"]["tcp_ueber_glasrand_m"]
    assert np.allclose(t[:3, 3], [z.glas.mitte[0], z.glas.mitte[1], soll], atol=1e-4)
    assert t[2, 2] == pytest.approx(-1.0, abs=1e-6)


def test_kollision_mit_hindernis_wird_erkannt(pruefer, sc):
    """Gegenprobe: ein Quader im Anfahrweg ueber Slot 1 macht den Slot unerreichbar."""
    z = pruefer.ziele()[0]
    c = z.glas.mitte
    sperre = geometrie.quader("sperre", "test", (c[0] - 0.12, c[1] - 0.12, c[2] + 0.25), (c[0] + 0.12, c[1] + 0.12, c[2] + 0.27))
    alt_h, alt_a = pruefer.hindernisse, pruefer._aabb
    try:
        pruefer.hindernisse = alt_h + [sperre]
        pruefer._aabb = np.array([h.aabb() for h in pruefer.hindernisse])
        e = pruefer.pruefe_ziel(z, int(sc["raster"]["seed"]), versuche=2)
    finally:
        pruefer.hindernisse, pruefer._aabb = alt_h, alt_a
    assert not e.ok
    assert any("sperre" in k for k in e.kollisionen)


def test_befund_schiene_am_boden_reicht_nicht(sc):
    """Ohne Podest liegt die Ablage (Arbeitsplatte 0,86 m) ausserhalb der Reichweite."""
    for lage in (erreichbarkeit.Lage("senkrecht_zur_front", (0.78, 0.06, 0.0), 90.0),
                 erreichbarkeit.Lage("parallel_zur_front", (-0.10, 0.75, 0.0), 0.0)):
        p = erreichbarkeit.Pruefer(lage, sc)
        z = [zz for zz in p.ziele() if zz.art == "ablage"][0]
        e = p.pruefe_ziel(z)
        assert not e.ok and e.grund.startswith("ausserhalb der Reichweite"), e.grund


def test_podest_neben_der_tuer_wird_abgelehnt(sc):
    p = erreichbarkeit.Pruefer(erreichbarkeit.Lage("senkrecht_zur_front", (0.70, 0.06, 0.65), 90.0), sc)
    assert "podest|tuer" in p.lage_konflikte()


def test_rastersuche_waehlt_lage_mit_nachbarn():
    def r(x, h, ok=True, j5=80.0):
        return {"lage": {"lage": "senkrecht_zur_front", "ursprung_xyz_m": [x, 0.06, h], "gier_grad": 90.0},
                "ok": ok, "j5_max_grad": j5}
    raster = [r(0.74, 0.60), r(0.90, 0.55), r(0.74, 0.65), r(0.78, 0.65), r(0.78, 0.60, ok=False)]
    w = erreichbarkeit.waehle(raster)
    assert w is not None
    assert w["lage"]["ursprung_xyz_m"] == [0.74, 0.06, 0.60]
    assert w["nachbarn_ok"] == 2
    assert erreichbarkeit.waehle([r(0.8, 0.6, ok=False)]) is None


def test_szene_yaml_ist_rasterwahl(sc):
    """Die gewaehlte Lage steht im Raster und ist die einzige Quelle der Schienenlage."""
    o = sc["schiene"]["ursprung_xyz_m"]
    assert o[0] in sc["raster"]["senkrecht_x_m"] and o[1] in sc["raster"]["senkrecht_y_m"]
    assert o[2] in sc["raster"]["hoehe_m"] and sc["schiene"]["gier_grad"] == 90.0


# --- Vorschau ---------------------------------------------------------------------

def test_vorschau_standbild(tmp_path):
    pytest.importorskip("matplotlib")
    out = tmp_path / "v.png"
    proc = subprocess.run([sys.executable, str(REPO / "scripts" / "vorschau_spuelmaschine.py"), "--out", str(out)],
                          capture_output=True, text=True, timeout=600)
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert out.stat().st_size > 20000
    assert "Kollisionen 0" in proc.stdout


# --- Newton -----------------------------------------------------------------------

def _newton_python() -> str:
    if os.environ.get("RAEUMWERK_RUN_NEWTON") != "1":
        pytest.skip("RAEUMWERK_RUN_NEWTON=1 nicht gesetzt")
    py = os.environ.get("RAEUMWERK_NEWTON_PYTHON")
    if not py or not Path(py).exists():
        pytest.skip("RAEUMWERK_NEWTON_PYTHON (Python mit Newton) fehlt")
    return py


def _stabil(tmp_path, *extra):
    out = tmp_path / "stabil.json"
    cmd = [_newton_python(), "-m", "spuelmaschine.stabilitaet", "--device",
           os.environ.get("RAEUMWERK_NEWTON_DEVICE", "cpu"), "--out", str(out), *extra]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800, cwd=REPO)
    return proc, json.loads(out.read_text())


def test_newton_glaeser_liegen_ruhig(tmp_path, sc):
    proc, e = _stabil(tmp_path)
    assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-3000:]
    assert e["ok"] and not e["nan"] and len(e["glaeser"]) == 4
    assert e["mess_s"] >= 2.0
    for g in e["glaeser"]:
        assert g["drift_max_m"] < 0.001
        assert g["einsinken_m"] < sc["newton"]["einsinken_max_m"]


def test_newton_gegenprobe_ohne_korbboden(tmp_path):
    proc, e = _stabil(tmp_path, "--ohne", "oberkorb_boden")
    assert proc.returncode == 1
    assert not e["ok"]
    assert all(g["einsinken_m"] > 0.05 for g in e["glaeser"])
