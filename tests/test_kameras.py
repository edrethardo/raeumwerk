"""Tests fuer den Kamerakatalog config/kameras.yaml (Ensenso-Kandidaten mit Quellen)."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
PFLICHT = ("name", "serie", "prinzip", "arbeitsbereich_m", "sichtfeld_mm", "z_genauigkeit_mm", "aufloesung_px",
           "farbe", "projektor", "bildrate_hz", "masse_kg", "masse_mm", "schnittstelle", "preis", "quelle")


def _kat():
    return yaml.safe_load((REPO / "config" / "kameras.yaml").read_text(encoding="utf-8"))


def test_kamerakatalog_felder_und_quellen():
    kat = _kat()
    assert kat["stand"] and len(kat["kameras"]) >= 6
    for name, k in kat["kameras"].items():
        fehlt = [f for f in PFLICHT if f not in k]
        assert not fehlt, (name, fehlt)
        assert k["quelle"], name
        for q in k["quelle"]:
            assert q in kat["quellen"] and kat["quellen"][q].startswith("https://"), (name, q)
        lo, hi = k["arbeitsbereich_m"]
        assert 0.0 < lo < hi <= 10.0, name
        assert k["farbe"] in (True, False), name


def test_preise_mit_quelle_oder_unklar():
    kat = _kat()
    for name, k in kat["kameras"].items():
        p = k["preis"]
        if p == "unklar":
            continue
        assert p["eur_ab"] is None or p["eur_ab"] > 0, name
        assert p["quelle"] in kat["quellen"] and p["stand"], name


def test_z_genauigkeit_waechst_quadratisch():
    """sigma(z) = k z^2: Tabellenwerte steigen mit dem Abstand, k aus der Tabelle trifft jeden Punkt auf 25 %."""
    kat = _kat()
    for name, k in kat["kameras"].items():
        tab = k["z_genauigkeit_mm"]
        if tab == "unklar":
            continue
        pts = sorted((float(z), float(s)) for z, s in tab.items())
        assert all(b[1] > a[1] for a, b in zip(pts, pts[1:])), name
        kk = float(k["sigma_k"])
        for z, s in pts:
            assert s == pytest.approx(kk * z * z * 1000.0, rel=0.25), (name, z, s)


def test_empfehlung_verweist_auf_katalog():
    kat = _kat()
    a = kat["auswahl"]
    for rolle in ("empfehlung", "sparvariante"):
        assert a[rolle]["kamera"] in kat["kameras"], rolle
        assert a[rolle]["montage"] and a[rolle]["begruendung"], rolle
    lo, hi = kat["kameras"][a["empfehlung"]["kamera"]]["arbeitsbereich_m"]
    d0, d1 = a["empfehlung"]["abstand_m"]
    assert lo <= d0 < d1 <= hi
