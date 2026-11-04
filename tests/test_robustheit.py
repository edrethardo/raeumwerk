"""Posefehler und Heilungsstrategien: ``wahrnehmung.robustheit`` und ``griffpose.posedrift``."""
from __future__ import annotations

import math

import numpy as np
import pytest

from finger.parameter import Finger
from finger.tellergriff import varianten as TV
from wahrnehmung import griffpose as WG
from wahrnehmung import robustheit as RB

KOPF = np.diag([1.0, -1.0, -1.0])


# --- Bausteine ------------------------------------------------------------------------------------

def test_rodrigues_dreht_um_die_achse():
    assert RB.rodrigues([0, 0, 1], 90.0) @ np.array([1.0, 0.0, 0.0]) == pytest.approx([0.0, 1.0, 0.0], abs=1e-9)
    assert RB.rodrigues([1, 2, 3], 0.0) == pytest.approx(np.eye(3))


def test_drift_fest_hat_festen_betrag_und_winkel():
    for seed in range(5):
        dr = RB.drift_fest(np.random.default_rng(seed), 0.02, 15.0)
        assert np.linalg.norm(dr["dp"][:2]) == pytest.approx(0.02)     # seitlich, fester Betrag
        assert dr["dp"][2] == pytest.approx(0.0)
        assert dr["grad"] == pytest.approx(15.0)
        assert dr["R"] @ dr["R"].T == pytest.approx(np.eye(3), abs=1e-9)


def test_drift_hart_kappt_betrag_und_winkel():
    frei = [np.linalg.norm(RB.drift(np.random.default_rng(s), t_sigma_m=0.02, r_sigma_grad=15.0)["dp"])
            for s in range(40)]
    assert max(frei) > 0.02                                            # ungekappt geht es darueber hinaus
    for s in range(40):
        dr = RB.drift(np.random.default_rng(s), t_sigma_m=0.02, r_sigma_grad=15.0, t_max_m=0.02, r_max_grad=30.0)
        assert np.linalg.norm(dr["dp"]) <= 0.02 + 1e-12
        assert dr["grad"] <= 30.0 + 1e-12


def test_fusion_senkt_sigma_und_zieht_zum_genaueren():
    assert RB.sigma_fusion_mm(2.0, 2.0) == pytest.approx(2.0 / math.sqrt(2))
    # das genauere Mass (1 mm) zieht die Fusion zu sich (2 mm auf 0, 1 mm auf 10 mm)
    p = RB.fusionieren([0.0, 0.0, 0.0], [0.010, 0.0, 0.0], 2.0, 1.0)
    assert p[0] == pytest.approx(0.008)
    assert RB.sigma_fusion_mm(2.0, 1.0) < 1.0


def test_wende_an_verschiebt_positiv_und_dreht_die_normale():
    e = {"c": [0.5, 0.5, 0.6], "normale": [0.0, 1.0, 0.0]}
    RB.wende_an(e, {"dp": np.array([0.01, 0.0, 0.0]), "R": RB.rodrigues([0, 0, 1], 90.0)})
    assert e["c"] == pytest.approx([0.51, 0.5, 0.6])
    assert e["normale"] == pytest.approx([-1.0, 0.0, 0.0])
    assert e["gier_grad"] == pytest.approx(90.0)                      # Gier folgt der gedrehten Normale
    e2 = {"c": [0.5, 0.5]}                                            # Glas fuehrt nur x, y
    RB.wende_an(e2, {"dp": np.array([0.01, 0.02, 0.03]), "R": np.eye(3)})
    assert e2["c"] == pytest.approx([0.51, 0.52])


def test_mechanische_grenzen_aus_der_fingergeometrie():
    f = Finger.laden()                                                # 18-mm-Finger
    assert RB.fangbereich_glas_mm(f) == pytest.approx(9.0)
    breit = Finger.laden(**TV.laden()["breit_6n"].finger)             # 60-mm-Backe
    assert RB.fangbereich_glas_mm(breit) == pytest.approx(30.0)
    assert RB.gier_toleranz_teller_grad(breit) == pytest.approx(math.degrees(math.asin(4.0 / 30.0)))


def test_erfolg_mechanisch_grenzen():
    f = Finger.laden()
    assert RB.erfolg_mechanisch("glas", 8.0, 0.0, f)["ok"]
    assert not RB.erfolg_mechanisch("glas", 10.0, 0.0, f)["ok"]
    assert RB.erfolg_mechanisch("glas", 6.0, 40.0, f)["ok"]           # Drehung um die Hochachse egal
    breit = Finger.laden(**TV.laden()["breit_6n"].finger)
    assert RB.erfolg_mechanisch("teller", 3.0, 5.0, breit)["ok"]
    assert not RB.erfolg_mechanisch("teller", 3.0, 12.0, breit)["ok"]


# --- griffpose: Drift der Station ----------------------------------------------------------------

def _welt_glas():
    from types import SimpleNamespace as NS

    def k(name, gruppe, mitte, halb, rot=np.eye(3)):
        return NS(name=name, gruppe=gruppe, mitte=np.asarray(mitte, float), halb=np.asarray(halb, float), rot=rot)
    stat = [k("korbboden", "oberkorb", (0.3, 0.2, 0.495), (0.3, 0.3, 0.005))]
    gl = [k("glas_1", "glas", (0.30, 0.20, 0.555), (0.0375, 0.0375, 0.055), KOPF),
          k("glas_2", "glas", (0.385, 0.20, 0.555), (0.0375, 0.0375, 0.055), KOPF)]
    return NS(statisch_ohne_teller=stat, glas_start=gl, teller=[], aufbau=NS(abw=NS(korbauszug_delta_m=0.0)))


def _nenn_glas(xy=(0.30, 0.20)):
    return lambda d: {"mitte": np.array([xy[0], xy[1], 0.555]) + [0.0, d, 0.0], "rot": KOPF,
                      "halb": np.array([0.0375, 0.0375, 0.055])}


def test_griffpose_posedrift_null_aendert_nichts():
    """Ein Drift mit Betrag 0 ist wie kein Drift: der Pfad bleibt bitgleich (der Drift-Haken
    ist additiv, Pose und Fehler der Nahekorrektur bleiben gleich)."""
    w = _welt_glas()
    a = WG.schaetzen("glas", w, 0, _nenn_glas(), seed=1, skala_ensenso=2.0, skala_d405=1.5)
    dr0 = RB.drift_fest(np.random.default_rng(0), 0.0, 0.0)
    b = WG.schaetzen("glas", w, 0, _nenn_glas(), seed=1, skala_ensenso=2.0, skala_d405=1.5, posedrift=dr0)
    assert a["pose_m"] == b["pose_m"]
    assert a["fehler_mm"] == b["fehler_mm"]
    assert a["s0_pose_m"] == b["s0_pose_m"]


def test_griffpose_drift_verschiebt_s0_die_d405_heilt():
    """Drift 20 mm auf der Station: die S0-Grobpose wandert (blinder Griff 20 mm daneben), die
    Vorposition der D405 wandert mit, aber die Nahekorrektur schaetzt das Ziel neu (Restfehler
    klein). Ohne Drift ist beides klein."""
    w = _welt_glas()
    rng = np.random.default_rng(9000 + 1)
    dr = RB.drift_fest(rng, 0.020, 15.0)
    ohne = WG.schaetzen("glas", w, 0, _nenn_glas(), seed=1, skala_ensenso=2.0, skala_d405=1.5)
    mit = WG.schaetzen("glas", w, 0, _nenn_glas(), seed=1, skala_ensenso=2.0, skala_d405=1.5, posedrift=dr)
    assert ohne["s0_fehler_mm"] < 6.0
    assert mit["s0_fehler_mm"] > 14.0                                 # blinder Griff weit daneben
    assert mit["d405"]["kamera_m"] != ohne["d405"]["kamera_m"]        # Vorposition gewandert
    assert mit["fehler_mm"] < 6.0                                     # die D405 heilt


# --- Teller, Gauss-Drift, Kreuzprobe -------------------------------------------------------------

TELLER_ROT = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0]])


def _welt_teller(c=(0.15, 0.30)):
    from types import SimpleNamespace as NS

    def k(name, gruppe, mitte, halb, rot=np.eye(3)):
        return NS(name=name, gruppe=gruppe, mitte=np.asarray(mitte, float), halb=np.asarray(halb, float), rot=rot)
    stat = [k("korbboden", "oberkorb", (0.3, 0.2, 0.495), (0.3, 0.3, 0.005))]
    tl = [k(f"teller_{j + 1}", "teller", (c[0], c[1] + dy, 0.595), (0.095, 0.095, 0.0025), TELLER_ROT)
          for j, dy in enumerate((0.0, -0.06, 0.06))]
    return NS(statisch=stat, glaeser_statisch=[], glas_start=tl, aufbau=NS(abw=NS(korbauszug_delta_m=0.0)))


def _nenn_teller(c=(0.15, 0.30)):
    return lambda d: {"mitte": np.array([c[0], c[1], 0.595]) + [0.0, d, 0.0], "rot": TELLER_ROT,
                      "halb": np.array([0.095, 0.095, 0.0025])}


@pytest.mark.parametrize("seed", [1, 2])
def test_griffpose_teller_posedrift_null_aendert_nichts(seed):
    """Teller: ein Drift 0 (Gier wird in ``wende_an`` aus der Normalen neu berechnet) laesst
    Pose, Fehler, Gier und die Ensenso-Mitte bitgleich."""
    w = _welt_teller()
    kw = dict(seed=seed, skala_ensenso=2.5, skala_d405=1.5)
    a = WG.schaetzen("teller", w, 0, _nenn_teller(), **kw)
    for dr0 in (RB.drift_fest(np.random.default_rng(0), 0.0, 0.0, achse=[0.0, 0.0, 1.0]),
                RB.drift(np.random.default_rng(0))):
        b = WG.schaetzen("teller", w, 0, _nenn_teller(), posedrift=dr0, **kw)
        assert "pose_m" in a                                   # D405 hat geschaetzt (ok kann am Plan scheitern)
        assert a["pose_m"] == b["pose_m"]
        assert a["fehler_mm"] == b["fehler_mm"]
        assert a["gier_grad"] == b["gier_grad"]
        assert a["s0_pose_m"] == b["s0_pose_m"]
        assert a["s0_gier_grad"] == b["s0_gier_grad"]
        assert a["ensenso"]["c"] == b["ensenso"]["c"]


def test_drift_gauss_statistik_und_kappung():
    """Echte Gauss-Ziehung: Versatz 3D N(0; sigma) je Achse, Drehwinkel N(0; sigma) mit zufaelliger
    Achse; ``hart`` kappt dieselbe Ziehung (gleicher Seed) auf 2 cm / 30 Grad, ohne sie zu verbiegen."""
    n = 4000
    frei = [RB.drift(np.random.default_rng(s), t_sigma_m=0.02, r_sigma_grad=15.0) for s in range(n)]
    dp = np.array([d["dp"] for d in frei])
    assert np.abs(dp.mean(axis=0)).max() < 0.002
    assert dp.std(axis=0) == pytest.approx([0.02] * 3, rel=0.06)
    betr = np.linalg.norm(dp, axis=1)
    assert 0.75 < (betr > 0.02).mean() < 0.85                # chi-3: P(|dp| > sigma) = 0,80 -> oft ueber 2 cm
    gr = np.array([d["grad"] for d in frei])
    assert gr.mean() == pytest.approx(15.0 * math.sqrt(2.0 / math.pi), rel=0.05)
    assert gr.max() > 30.0                                     # frei: keine Kappung
    hart = [RB.drift(np.random.default_rng(s), t_sigma_m=0.02, r_sigma_grad=15.0, t_max_m=0.02, r_max_grad=30.0)
            for s in range(n)]
    for f, h in zip(frei, hart):
        assert np.linalg.norm(h["dp"]) <= 0.02 + 1e-12 and h["grad"] <= 30.0 + 1e-12
        if np.linalg.norm(f["dp"]) <= 0.02:                  # unterhalb der Kappung dieselbe Ziehung
            assert h["dp"] == pytest.approx(f["dp"])
        if f["grad"] <= 30.0:
            assert h["grad"] == pytest.approx(f["grad"])


def test_griff_robustheit_sigma_nutzt_gauss_nicht_festen_betrag():
    """``scripts/griff_robustheit.drift_von``: sigma_frei/hart sind Gauss-Ziehungen (Betrag streut),
    das Raster dagegen hat festen Betrag."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import griff_robustheit as GR
    fest = {round(GR.drift_von("glas", s, 15.0, 20.0, False)["betrag_m"], 9) for s in range(1, 9)}
    frei = [GR.drift_von("glas", s, 15.0, 20.0, False, sigma=True)["betrag_m"] for s in range(1, 17)]
    hart = [GR.drift_von("glas", s, 15.0, 20.0, True, sigma=True)["betrag_m"] for s in range(1, 17)]
    assert fest == {0.02}
    assert len({round(b, 6) for b in frei}) > 10 and max(frei) > 0.02
    assert max(hart) <= 0.02 + 1e-12


def test_s3_kreuzprobe_schlaegt_auch_bei_noch_greifbarem_fehler_an():
    """Fehlalarm: Station 8 mm daneben (S0 greift noch, Fangbereich 9 mm) liegt ueber der
    Kreuzprobentoleranz, ohne Drift liegt der Abstand darunter. S3 'Abbruch' wuerfe den Griff weg."""
    w = _welt_glas()
    kw = dict(seed=1, skala_ensenso=2.0, skala_d405=1.5)
    ohne = WG.schaetzen("glas", w, 0, _nenn_glas(), **kw)
    mit = WG.schaetzen("glas", w, 0, _nenn_glas(), posedrift=RB.drift_fest(np.random.default_rng(1), 0.008, 0.0), **kw)
    tol = 1e3 * WG.TOL_GLAS_M
    assert ohne["ensenso_d405_abstand_mm"] < tol
    assert mit["ensenso_d405_abstand_mm"] > tol
    assert "ensenso_d405_widerspruch" in mit["gruende"]
    assert mit["s0_fehler_mm"] < RB.fangbereich_glas_mm(Finger.laden())   # S0 haette noch gegriffen
