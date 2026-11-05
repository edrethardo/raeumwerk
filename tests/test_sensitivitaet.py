"""Sensitivitaetsanalyse (Kameratag P4): Parametertabelle, Zielgroessen, Mischung, Sobol-Schaetzer."""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from wahrnehmung import sensitivitaet as SE  # noqa: E402


def test_parametertabelle_ist_stimmig():
    namen = [p.name for p in SE.PARAMETER]
    assert len(namen) == len(set(namen)) == 15
    for p in SE.PARAMETER:
        assert p.lo <= p.plan <= p.hi, p.name
        assert p.quelle.strip(), p.name                       # jede Spanne hat Quelle oder Annahme
    assert {p.name for p in SE.WAHRSCH} == {"erk_glas", "erk_teller", "verwechslung"}
    assert len(SE.PHYS) == 12 and len(SE.MAST_NAMEN) == 4


def test_von_einheit_und_kategorie():
    assert SE.von_einheit([0.0] * 12, SE.PHYS)["dicke_mm"] == 3.0
    th = SE.von_einheit([1.0] * 12, SE.PHYS)
    assert th["dicke_mm"] == 12.0 and th["kalib_versatz_mm"] == 30.0 and th["mast"] == 3.0
    ms = {SE.von_einheit([0.0] * 11 + [u], SE.PHYS)["mast"] for u in (0.0, 0.26, 0.51, 0.76, 0.999)}
    assert ms == {0.0, 1.0, 2.0, 3.0}


def test_design_liegt_im_wuerfel_und_ist_reproduzierbar():
    u = SE.design(64)
    assert u.shape == (64, 12) and u.min() >= 0.0 and u.max() <= 1.0
    assert np.array_equal(u, SE.design(64))


def _z(art="teller", **kw):
    b = {"mm": 2.0, "gier_fehler": 1.0, "ok": True}
    z = {"art": art, "ok_std": True, "s1": dict(b), "a_annahme": False, "b_annahme": True, "b": dict(b),
         "ensenso_ok": True, "d405_mm": 3.0}
    z.update(kw)
    return z


def test_ziele_zeile_erfolg_unbemerkt_abbruch():
    o = SE.ziele_zeile(_z())
    assert o["erfolg_K"] == 1 and o["unb_K"] == 0 and o["erfolg_B"] == 1 and o["brauch"] == 1
    bad = {"mm": 9.0, "gier_fehler": 1.0, "ok": False}
    o = SE.ziele_zeile(_z(s1=bad))
    assert o["erfolg_K"] == 0 and o["unb_K"] == 1                      # greift, aber daneben
    o = SE.ziele_zeile(_z(ok_std=False, a_annahme=True, s1=bad))
    assert o["erfolg_K"] == 0 and o["unb_K"] == 0                      # Kette bricht ab, kein Griff
    assert o["unb_A"] == 1                                             # A nimmt trotzdem an
    o = SE.ziele_zeile(_z(d405_mm=12.0))
    assert o["brauch"] == 0                                            # Pose > 10 mm daneben: unbrauchbar
    o = SE.ziele_zeile(_z(s1=None, b=None, b_annahme=False, d405_mm=None))
    assert o["erfolg_K"] == o["unb_K"] == o["erfolg_B"] == o["brauch"] == 0


def test_physik_grenze_gier():
    z = _z(s1={"mm": 2.0, "gier_fehler": 6.0, "ok": True})            # geometrisch ok (Kerbe 7,66 Grad), Physik nicht
    assert SE.ziele_zeile(z)["erfolg_K"] == 1
    assert SE.ziele_zeile(z, physik=True)["erfolg_K"] == 0
    zg = _z(art="glas", s1={"mm": 2.0, "gier_fehler": 0.0, "ok": True})
    assert SE.ziele_zeile(zg, physik=True)["erfolg_K"] == 1


def test_mischen_erkennung_und_verwechslung():
    s = {"erfolg_K": 1.0, "unb_K": 0.0, "brauch": 1.0}
    m = SE.mischen(s, 0.5, 0.2)
    assert m["erfolg_K"] == pytest.approx(0.4) and m["brauch"] == pytest.approx(0.4) and m["unb_K"] == 0.0
    s = {"erfolg_K": 0.0, "unb_K": 1.0}
    assert SE.mischen(s, 1.0, 0.0)["unb_K"] == 1.0
    assert SE.mischen(s, 0.5, 0.2, {"unb_K": 0.1})["unb_K"] == pytest.approx(0.5 * (0.8 + 0.02))
    assert SE.mischen(s, 0.0, 0.2)["unb_K"] == 0.0                     # nichts erkannt, nichts gegriffen


def test_wilson_grenzen():
    lo, hi = SE.wilson(0, 64)
    assert lo == 0.0 and hi == pytest.approx(0.057, abs=0.001)         # die 5,7 % aus P2 (0/64)
    assert SE.wilson(0, 0) == (0.0, 1.0)


def test_sobol_ishigami():
    a, b = 7.0, 0.1

    def f(u):
        x = (u - 0.5) * 2 * math.pi
        return np.sin(x[:, 0]) + a * np.sin(x[:, 1]) ** 2 + b * x[:, 2] ** 4 * np.sin(x[:, 0])

    r = SE.sobol(f, 3, n=8192, boot=0)
    # analytisch: S1 = 0.314, 0.442, 0; ST = 0.558, 0.442, 0.244
    assert r["s1"] == pytest.approx([0.314, 0.442, 0.0], abs=0.05)
    assert r["st"] == pytest.approx([0.558, 0.442, 0.244], abs=0.05)


def test_sobol_irrelevanter_eingang_hat_null():
    r = SE.sobol(lambda u: 3.0 * u[:, 0] + u[:, 1] * u[:, 2], 4, n=2048, boot=20)
    assert r["st"][3] == pytest.approx(0.0, abs=1e-9) and r["s1"][3] == pytest.approx(0.0, abs=0.02)
    assert r["st"][0] > 0.6 and (r["st_ci"][0][0] <= r["st"][0] <= r["st_ci"][1][0])


def test_auswerten_glas_plan_ist_stimmig():
    import sensitivitaet_lauf as L
    th = {p.name: p.plan for p in SE.PHYS}
    z = L.auswerten("glas", th, 101)
    assert z["ensenso_ok"] and z["s1"] is not None and z["s1"]["mm"] < 9.0
    assert 0.0 <= SE.ziele_zeile(z)["brauch"] <= 1.0


def test_teller_dicke_eckfall_wie_p3():
    """Dasselbe Ziel: 5 mm Randwulst liefert eine Station-Pose, 12 mm nicht (P3: 96/131 gegen 0/131)."""
    import sensitivitaet_lauf as L
    th = {p.name: p.plan for p in SE.PHYS}
    dick = dict(th, dicke_mm=12.0)
    z5, z12 = L.auswerten("teller", th, 101), L.auswerten("teller", dick, 101)
    assert z5["ensenso_ok"] and not z12["ensenso_ok"]
    assert any("ebene_inlier_gering" in g for g in z12["gruende"])


def test_gitter_und_aufgaben():
    import sensitivitaet_lauf as L
    P = {p.name: p for p in SE.PHYS}
    assert set(L.GITTER) == set(P)
    for n, werte in L.GITTER.items():
        assert min(werte) >= P[n].lo and max(werte) <= P[n].hi, n
    assert len(L.aufgaben("design", 4, 0, 1)) == 8                    # 4 Punkte x Glas/Teller
    conf = L.aufgaben("conf", 2, 0, 1)
    assert all(t[5] == "nachbar" for t in conf) and len(conf) == 4
    sweep = L.aufgaben("sweep", 0, 0, 2)
    assert len(sweep) == 2 * 2 * (1 + sum(len(v) for v in L.GITTER.values()))
    assert len(L.aufgaben("val", 3, 0, 2)) == 3 * 2 * 2
    # Design-Punkte mit gleichem Index sind unabhaengig von n (Sobol-Praefix)
    a = {(t[1], t[2]): t[3] for t in L.aufgaben("design", 4, 0, 1)}
    b = {(t[1], t[2]): t[3] for t in L.aufgaben("design", 4, 4, 1)}
    assert a[(0, "glas")] != b[(4, "glas")]
