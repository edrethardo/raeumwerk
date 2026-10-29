"""Tests fuer das Erreichbarkeitswerkzeug (``raeumwerk aufbau``) und die Batch-IK."""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import numpy as np
import pytest

from rebel_model.config import load as load_robot
from rebel_model.kinematics import Chain
from rebel_model.schnell import SchnellChain, rot_log_batch
from rebel_model.kinematics import rot_log
from rebel_model.urdf_gen import build_urdf
from spuelmaschine import aufbau as AU
from spuelmaschine.erreichbarkeit import USE, Pruefer

REPO = Path(__file__).resolve().parents[1]
TCP = [0.0, 0.0, 0.08]


@pytest.fixture(scope="module")
def ketten():
    u = build_urdf(load_robot())
    return Chain(u), SchnellChain(u)


def _ziele(chain, n, seed):
    rng = np.random.default_rng(seed)
    qs = [chain.random_q(rng, USE) for _ in range(n)]
    T = np.array([chain.fk(q, "gripper_base", TCP) for q in qs])
    q0 = np.clip(np.array(qs) + rng.normal(0.0, 0.3, (n, len(qs[0]))), chain.lower, chain.upper)
    return T, q0


def test_fk_und_jacobi_batch_gleich_einzeln(ketten):
    c, s = ketten
    rng = np.random.default_rng(1)
    Q = np.array([c.random_q(rng, USE) for _ in range(50)])
    T, J = s.kette("gripper_base", TCP).fk_jac(Q)
    for i in range(len(Q)):
        assert np.abs(T[i] - c.fk(Q[i], "gripper_base", TCP)).max() < 1e-12
        assert np.abs(J[i] - c.jacobian(Q[i], "gripper_base", TCP)).max() < 1e-12


def test_ik_batch_gegen_einzel_ik_120_ziele(ketten):
    """Batch-IK gegen die bestehende Einzel-IK: gleiche Konvergenz, Fehler < 1 mm."""
    c, s = ketten
    T, q0 = _ziele(c, 120, 3)
    qb, pe, re, ok = s.kette("gripper_base", TCP).ik_batch(T, q0, USE)
    einzeln = [c.ik(T[i], "gripper_base", q0[i], USE, offset=TCP, restarts=0) for i in range(len(T))]
    ok_e = np.array([e[3] for e in einzeln])
    assert ok.sum() >= 100
    assert (ok == ok_e).all()
    for i in range(len(T)):
        assert np.abs(qb[i] - einzeln[i][0]).max() < 1e-6
        if ok[i]:
            fehler = np.linalg.norm(c.fk(qb[i], "gripper_base", TCP)[:3, 3] - T[i, :3, 3])
            assert fehler < 1e-3 and pe[i] < 1e-5


def test_schnelle_ik_mit_neustarts_wie_chain_ik(ketten):
    c, s = ketten
    T, q0 = _ziele(c, 12, 5)
    q0 = np.tile(c.zero(), (len(T), 1))  # aus der Kerze: manche brauchen Neustarts
    for i in range(len(T)):
        a = c.ik(T[i], "gripper_base", q0[i], USE, offset=TCP, restarts=3, rng=np.random.default_rng(i))
        b = s.ik(T[i], "gripper_base", q0[i], USE, offset=TCP, restarts=3, rng=np.random.default_rng(i))
        assert a[3] == b[3]
        assert np.abs(a[0] - b[0]).max() < 1e-6


def test_rot_log_batch_auch_bei_180_grad():
    R = np.array([np.eye(3), np.diag([1.0, -1.0, -1.0]), np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1.0]])])
    for r, v in zip(R, rot_log_batch(R)):
        assert np.allclose(v, rot_log(r))


# --- Kollision ------------------------------------------------------------------

@pytest.fixture(scope="module")
def z_aufbau():
    return AU.Aufbau(AU.lade_yaml(REPO / "beispiele" / "z-achse-frontal.yaml"))


def test_kollision_schnell_gleich_pruefer(z_aufbau):
    """Die vektorisierte Pruefung liefert dieselben Treffer wie Pruefer.kollisionen."""
    p = z_aufbau.pruefer(0.45, 0.0)
    rng = np.random.default_rng(4)
    gleich = treffer = 0
    for _ in range(60):
        q = p.chain.random_q(rng, USE)
        a = p.kollisionen(q)
        b = sorted(h for h in Pruefer.kollisionen(p, q) if h not in z_aufbau.erlaubt)
        assert a == b
        gleich += 1
        treffer += bool(a)
    assert gleich == 60 and 5 <= treffer < 60  # beide Faelle kommen vor


def test_kollision_ein_aus(z_aufbau):
    p = z_aufbau.pruefer(0.0, 0.0)
    q = p.chain.zero()
    q[p.i7] = 0.6  # Kerze, Fuss auf 0,62 m: frei
    assert p.kollisionen(q) == []
    q2 = q.copy()
    q2[p.chain.index["joint2"]] = math.radians(90)  # Arm waagerecht in die Maschine (Roboter-x = -y)
    q2[p.i7] = 0.3
    assert any(h.split("|")[1] != "podest" for h in p.kollisionen(q2))
    # erlaubte Beruehrung: Fuss an der Saeule zaehlt nicht, ohne Freigabe schon
    q3 = q.copy()
    q3[p.i7] = 0.0
    p.A.erlaubt.discard("base_link|podest")
    try:
        mit = p.kollisionen(q3)
    finally:
        p.A.erlaubt.add("base_link|podest")
    ohne = p.kollisionen(q3)
    assert "base_link|podest" not in ohne
    assert ("base_link|podest" in mit) or mit == ohne


def test_korbszene_im_1cm_raster(z_aufbau):
    """Beim Korbzug faehrt die Kollisionsszene je Zentimeter mit (kein 5-cm-Raster)."""
    a = {"gruppe": "zug", "ziel": "x", "korb": "oberkorb", "x": 0.5, "griff": "waagerecht", "richtung": "aus"}
    d = copy.deepcopy(z_aufbau.d)
    d["ziele"]["zug"]["szene_raster_m"] = 0.01
    A = AU.Aufbau(d)
    AU.rechne_zug(A, a)
    auszuege = sorted({k[0] for k in A._pruefer})
    assert len(auszuege) >= 40 and np.allclose(np.diff(auszuege), 0.01)


# --- Momente ---------------------------------------------------------------------

def _aufbau_fest():
    return AU.Aufbau(AU.normalisiere({"name": "test", "achse": {"richtung": "keine", "schiene": "platte"},
                                      "roboter": {"ursprung_xyz_m": [2.0, 2.0, 0.0]}}))


def test_moment_handwert_zug():
    """Kerze, Zug 20 N waagerecht am TCP: J2 traegt F * Hebel (Oberarm + Unterarm + Hand + TCP)."""
    A = _aufbau_fest()
    p = A.pruefer(0.0, 0.0)
    q = p.chain.zero()
    m = AU.momente(p, [q], [20.0], richtung=(1.0, 0.0, 0.0))["20N"]
    hebel = 0.237 + 0.297 + 0.126 + 0.080
    assert m["zug"]["joint2"] == pytest.approx(20.0 * hebel, abs=0.01)  # 14,8 Nm
    assert m["schwerkraft"]["joint2"] == pytest.approx(0.0, abs=1e-6)
    assert m["urteil"] == "geht nicht"  # 14,8 > Max 12,5 (untere Grenze)


def test_moment_handwert_eigengewicht():
    """Arm waagerecht (J2 = 90 Grad): Eigengewicht an J2 = g * Summe Masse * Abstand (Link-Ursprung)."""
    A = _aufbau_fest()
    p = A.pruefer(0.0, 0.0)
    q = p.chain.zero()
    q[p.chain.index["joint2"]] = math.pi / 2
    mm = A.cfg.massen
    g = A.cfg.greifer
    hand = 0.237 + 0.297 + 0.126
    hand_wert = 9.81 * (mm["link_3"] * 0.237 + mm["link_4"] * (0.237 + 0.127) + mm["link_5"] * (0.237 + 0.297)
                        + mm["link_6"] * (0.237 + 0.297 + 0.1208) + g["masse_kg"] * hand
                        + 2 * g["finger_masse_kg"] * (hand + g["koerper_laenge_m"]))
    m = AU.momente(p, [q], [0.0])["0N"]
    assert m["schwerkraft"]["joint2"] == pytest.approx(hand_wert, abs=0.005)  # Ausgabe auf 0,01 Nm gerundet


def test_gelenkgrenzen_aus_igus_quelle():
    cfg = load_robot()
    assert "igus_getriebe" in cfg.raw["quellen"]
    gr = {g.name: g for g in cfg.gelenke}
    for n in ("joint1", "joint2", "joint3"):
        assert gr[n].nennmoment == (10.0, 15.0) and gr[n].max_moment == (12.5, 20.0) and gr[n].baugroesse == 105
    for n in ("joint4", "joint5", "joint6"):
        assert gr[n].nennmoment == (2.0, 2.0) and gr[n].max_moment == (2.5, 3.0) and gr[n].baugroesse == 80
    for g in cfg.raw["arm"]["gelenke"]:
        assert g["moment_src"] == "igus_getriebe" and g["baugroesse_src"] == "annahme"
    assert "moment_nm" not in cfg.arm  # die alten 40 Nm sind weg
    c = Chain(build_urdf(cfg))
    assert c is not None
    assert 'effort="20"' in build_urdf(cfg) and 'effort="3"' in build_urdf(cfg)


# --- Cache und Lauf ----------------------------------------------------------------

def _klein():
    d = AU.lade_yaml(REPO / "beispiele" / "z-achse-frontal.yaml")
    d["ziele"] = {"ablage": {"platte": True, "glaeser": ["tisch_1"], "gier_grad": [0, 90]}}
    return d


def test_cache_und_invalidierung(tmp_path):
    d = _klein()
    e1 = AU.lauf(d, jobs=1, cache=tmp_path, log=lambda s: None)
    assert e1["gerechnet"] == 5 and e1["aus_cache"] == 0
    assert e1["abdeckung"]["ablage_platte"] == {"ok": 0, "n": 4}
    assert e1["abdeckung"]["ablage_extra"] == {"ok": 1, "n": 1}
    e2 = AU.lauf(d, jobs=1, cache=tmp_path, log=lambda s: None)
    assert e2["gerechnet"] == 0 and e2["aus_cache"] == 5
    assert e2["gruppen"] == {g: [dict(r, sekunden=r["sekunden"]) for r in rows] for g, rows in e1["gruppen"].items()}
    d2 = copy.deepcopy(d)
    d2["masse"]["tuer"] = {"oeffnung_grad": 80.0}  # Szene geaendert -> alles neu
    e3 = AU.lauf(d2, jobs=1, cache=tmp_path, log=lambda s: None)
    assert e3["gerechnet"] == 5
    d3 = copy.deepcopy(d)
    d3["name"] = "nur umbenannt"  # Name gehoert nicht zum Schluessel
    assert AU.lauf(d3, jobs=1, cache=tmp_path, log=lambda s: None)["aus_cache"] == 5


def test_cache_schluessel_haengt_am_code(monkeypatch):
    d = _klein()
    a = AU.aufgaben(d)[0]
    k1 = AU._schluessel(d, a, AU.code_hash())
    assert k1 != AU._schluessel(d, a, "anderer-code")
    assert k1 != AU._schluessel(d, dict(a, i=3), AU.code_hash())


def test_cli_aufbau(tmp_path):
    from raeumwerk.cli import main

    y = tmp_path / "klein.yaml"
    import yaml

    roh = yaml.safe_load((REPO / "beispiele" / "z-achse-frontal.yaml").read_text(encoding="utf-8"))
    roh["ziele"] = {"ablage": {"platte": True, "glaeser": []}}
    y.write_text(yaml.safe_dump(roh), encoding="utf-8")
    out = tmp_path / "aus"
    assert main(["aufbau", str(y), "--jobs", "2", "--kein-cache", "--ohne-bilder", "--out", str(out)]) == 0
    e = json.loads((out / "ergebnis.json").read_text(encoding="utf-8"))
    assert e["abdeckung"]["ablage_platte"] == {"ok": 0, "n": 4}
    assert "| ablage_platte | 0/4 |" in (out / "ergebnis.md").read_text(encoding="utf-8")
    assert main(["aufbau", str(tmp_path / "fehlt.yaml")]) == 2


def test_beispiele_laden():
    for f in sorted((REPO / "beispiele").glob("*.yaml")):
        d = AU.lade_yaml(f)
        assert AU.aufgaben(d), f.name


def test_yaml_fehler():
    with pytest.raises(ValueError):
        AU.normalisiere({"achse": {"richtung": "w"}})
    with pytest.raises(ValueError):
        AU.normalisiere({"ziele": {"besteck": {}}})
