"""Kameratag-Auswertung: Katalog, Rechenbausteine auf synthetischen Wolken, Urteile, Beispielmessdatei."""
from __future__ import annotations

import hashlib
import json
import re
import struct
import sys
from pathlib import Path

import numpy as np
import pytest

WURZEL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WURZEL / "scripts"))

import kameratag_auswerten as KA  # noqa: E402

KATALOG = WURZEL / "config" / "kameratag_vorhersagen.yaml"
BEISPIEL = WURZEL / "beispiele" / "kameratag-messung-beispiel.yaml"


@pytest.fixture(scope="module")
def kat():
    return KA.lade_katalog(KATALOG)


def _urteile(kat, messungen, tmp_path=None):
    erg = KA.auswerten(kat, {"messungen": messungen}, tmp_path or Path("."))
    return {r["id"]: r for r in erg["zeilen"]}


# --- Katalog ----------------------------------------------------------------------------------------

def test_katalog_hat_13_zeilen_mit_allen_feldern(kat):
    assert sorted(kat["_zeilen"]) == list(range(1, 14))
    for zid, z in kat["_zeilen"].items():
        for feld in ("name", "einheit", "prioritaet", "aufwand", "vorhersage", "schwelle", "urteil", "konsequenz", "parameter"):
            assert z.get(feld), (zid, feld)
        assert z["aufwand"]["quelle"] in ("P4", "A"), zid
        arten = {h["art"] for h in z["vorhersage"]["herkunft"]}
        assert arten and arten <= {"D", "M", "A"}, zid
        for v in ("stimmt", "zu_optimistisch", "zu_pessimistisch"):
            assert z["urteil"][v] and z["konsequenz"][v], (zid, v)
    # die Annahmen sind als solche gekennzeichnet
    for zid in (9, 10, 11, 12, 13):
        assert any(h["art"] == "A" for h in kat["_zeilen"][zid]["vorhersage"]["herkunft"]), zid
    assert sorted(kat["_unbekannt"]) == ["u1", "u2", "u3"]
    for u in kat["_unbekannt"].values():
        assert u["begruendung"] and len(u["klassen"]) == 3
    assert [r["nr"] for r in kat["messreihenfolge"]] == [1, 2, 3, 4, 5]
    assert [r["minuten"] for r in kat["messreihenfolge"]] == [20, 45, 75, 35, 15]


def test_katalog_positionen_sind_in_sich_stimmig(kat):
    assert set(kat["positionen"]) == {"haupt", "hoeher", "bestand", "ausleger"}
    praefix = {"glas": "glas", "teller_ober": "oberteller", "teller_unter": "unterteller"}
    for name, p in kat["positionen"].items():
        assert len(p["plaetze"]) == 30 and set(p["referenz"]) == {"r1", "r2", "r3"}
        for ak in ("a0", "a225", "a450"):
            for g, pre in praefix.items():
                n = sum(1 for pn, e in p["plaetze"].items() if pn.startswith(pre + "_") and e[ak][3])
                assert n == p["gruppen"][ak][g]["nutzbar"][0], (name, ak, g)
    # Werte der Hauptposition gegen die Doku (Abstände 0,80 / 0,91 / 1,18 m; Gläser 16/16)
    h = kat["positionen"]["haupt"]
    assert [round(h["referenz"][r]["abstand_m"], 2) for r in ("r1", "r2", "r3")] == [0.80, 0.91, 1.18]
    assert h["gruppen"]["a225"]["glas"]["nutzbar"] == [16, 16] and h["gruppen"]["a450"]["teller_ober"]["nutzbar"] == [5, 8]
    assert kat["positionen"]["ausleger"]["gruppen"]["a450"]["teller_ober"]["nutzbar"] == [1, 8]


def test_neue_dateien_ohne_ticketnummern_hostpfade_und_ips():
    teile = ["WB" + r"-\d", "/da" + "ta/", "/ho" + "me/", "/mn" + "t/", "raeumwerk_" + "artefakte", "tail" + "scale", "sphe" + "ron",
             r"\.ts" + r"\.net", r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"]
    verboten = re.compile("|".join(teile), re.I)
    dateien = [KATALOG, BEISPIEL, WURZEL / "scripts" / "kameratag_auswerten.py", Path(__file__),
               WURZEL / "docs" / "kameratag-vorhersagen.md", WURZEL / "docs" / "kameratag-messprotokoll.md"]
    for d in dateien:
        if not d.exists():
            continue
        for i, zeile in enumerate(d.read_text(encoding="utf-8").splitlines(), 1):
            assert not verboten.search(zeile), f"{d.name}:{i}: {zeile[:100]}"


def test_doku_traegt_pruefsumme_des_eingefrorenen_katalogs():
    doku = WURZEL / "docs" / "kameratag-vorhersagen.md"
    if not doku.exists():
        pytest.skip("Dokument noch nicht geschrieben")
    m = re.search(r"SHA-256 der Katalogdatei: `([0-9a-f]{64})`", doku.read_text(encoding="utf-8"))
    assert m, "Prüfsumme fehlt im Dokument"
    assert m.group(1) == hashlib.sha256(KATALOG.read_bytes()).hexdigest(), "Katalog nach dem Einfrieren verändert"


# --- Rechenbausteine auf synthetischen Wolken ---------------------------------------------------------

def test_wilson_bekannte_werte():
    lo, hi = KA.wilson(0, 10)
    assert lo == 0.0 and hi == pytest.approx(0.2775, abs=1e-3)
    lo, hi = KA.wilson(50, 100)
    assert (lo, hi) == pytest.approx((0.4038, 0.5962), abs=1e-3)


@pytest.mark.parametrize("sigma", [0.15, 0.3])
def test_sigma_aus_synthetischer_wolke(tmp_path, sigma):
    xyz = KA.synth_ebene(1000.0, sigma, rng=np.random.default_rng(3), kippung_grad=7.0)
    np.savez(tmp_path / "a.npz", xyz=xyz)
    z, s, n = KA.sigma_aus_wolke(tmp_path / "a.npz", roi_px=[10, 10, 150, 110])
    assert 0.98 < z < 1.02 or abs(z - 1.0) < 0.05
    # senkrechte Normalabstände sind um cos(kipp) kleiner als die z-Abweichung
    assert s == pytest.approx(sigma * np.cos(np.radians(7.0)), rel=0.08)
    assert n > 10000


def test_ply_ascii_und_binaer_gleiche_punkte(tmp_path):
    xyz = KA.synth_ebene(900.0, 0.2, hw=(30, 40), rng=np.random.default_rng(4)).reshape(-1, 3)
    kopf = "ply\nformat {}\nelement vertex {}\nproperty float x\nproperty float y\nproperty float z\nend_header\n"
    (tmp_path / "a.ply").write_bytes(kopf.format("ascii 1.0", len(xyz)).encode() + "".join(f"{a} {b} {c}\n" for a, b, c in xyz).encode())
    (tmp_path / "b.ply").write_bytes(kopf.format("binary_little_endian 1.0", len(xyz)).encode() + xyz.astype("<f4").tobytes())
    a, b = KA.lese_ply(tmp_path / "a.ply"), KA.lese_ply(tmp_path / "b.ply")
    assert a.shape == b.shape == xyz.shape
    assert np.allclose(b, xyz, atol=1e-4) and np.allclose(a, xyz, atol=1e-3)
    z, s, n = KA.sigma_aus_wolke(tmp_path / "b.ply")
    assert s == pytest.approx(0.2, rel=0.1)


def test_abdeckung_aus_synthetischer_wolke():
    xyz, maske = KA.synth_objekt(0.31, rng=np.random.default_rng(5))
    w = {"xyz": xyz.astype(float), "maske": maske, "organisiert": True}
    assert KA.abdeckung_pct(w) == pytest.approx(31.0, abs=3.0)
    with pytest.raises(ValueError):
        KA.abdeckung_pct({"xyz": xyz.reshape(-1, 3), "maske": None, "organisiert": False})


def test_punkt_streuung_trifft_das_eingesetzte_rauschen():
    wolken = [{"xyz": KA.synth_ebene(1000.0, 0.25, rng=np.random.default_rng(10 + i)).astype(float), "maske": None, "organisiert": True}
              for i in range(20)]
    s = KA.punkt_streuung(wolken)
    assert s["sigma_median_mm"] == pytest.approx(0.25, rel=0.1) and s["aufnahmen"] == 20
    assert s["z_m"] == pytest.approx(1.0, abs=0.01)


def test_kabsch_findet_versatz_und_drehung():
    rng = np.random.default_rng(6)
    ref = rng.uniform(-150, 150, (6, 3))
    a = np.radians(3.0)
    R = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])
    c = ref.mean(axis=0)
    station = (ref - c) @ R.T + c + np.array([2.4, -3.2, 0.0])           # 4,0 mm Versatz
    r = KA.kabsch(station, ref)
    assert r["versatz_mm"] == pytest.approx(4.0, abs=0.01)
    assert r["dreh_grad"] == pytest.approx(3.0, abs=0.01)
    assert r["rest_rms_mm"] < 1e-6
    with pytest.raises(ValueError):
        KA.kabsch(ref[:2], ref[:2])


# --- Urteile: je ein Fall stimmt / zu optimistisch / zu pessimistisch ------------------------------------

FAELLE = [
    # (Zeile, Schlüssel, Messwerte, erwartetes Urteil)
    ("z01", 1, {"ensenso": [{"z_m": 1.0, "sigma_mm": 0.25}]}, "stimmt"),
    ("z01", 1, {"ensenso": [{"z_m": 1.0, "sigma_mm": 0.6}]}, "zu_optimistisch"),
    ("z01", 1, {"ensenso": [{"z_m": 1.0, "sigma_mm": 0.08}]}, "zu_pessimistisch"),
    ("z02", 2, {"haupt": {"r1": 0.81, "r2": 0.92, "r3": 1.19}}, "stimmt"),
    ("z02", 2, {"haupt": {"r1": 0.81, "r2": 0.97, "r3": 1.19}}, "zu_optimistisch"),
    ("z02", 2, {"haupt": {"r1": 0.81, "r2": 0.88, "r3": 1.19}}, "zu_pessimistisch"),
    ("z05", 5, {"glas": {"abdeckung_pct": [30, 33, 29, 31, 32, 30, 28, 33]}}, "stimmt"),
    ("z05", 5, {"glas": {"abdeckung_pct": [10, 12, 9, 11, 10, 12, 8, 10]}}, "zu_optimistisch"),
    ("z05", 5, {"glas": {"abdeckung_pct": [55, 60, 52, 58, 61, 57, 54, 56]}}, "zu_pessimistisch"),
    ("z06", 6, {"glas_tag": {"k": 17, "n": 20}}, "stimmt"),
    ("z06", 6, {"glas_tag": {"k": 8, "n": 20}}, "zu_optimistisch"),
    ("z06", 6, {"teller_tag": {"k": 19, "n": 20}}, "zu_pessimistisch"),
    ("z07", 7, {"glas": {"fehler_mm": [1.0, 1.5, 1.2, 2.0, 1.4]}}, "stimmt"),
    ("z07", 7, {"glas": {"fehler_mm": [6.0, 7.5, 5.5, 8.0]}}, "zu_optimistisch"),
    ("z07", 7, {"glas": {"fehler_mm": [0.2, 0.4, 0.3, 0.5]}}, "zu_pessimistisch"),
    ("z09", 9, {"gier_grad": [0.5, -1.0, 1.4], "lage_mm": [2.0, 3.0]}, "stimmt"),
    ("z09", 9, {"gier_grad": [0.5, -1.0, 4.2], "lage_mm": [2.0, 3.0]}, "zu_optimistisch"),
    ("z09", 9, {"gier_grad": [0.2, -0.3, 0.4], "lage_mm": [1.0, 2.0]}, "zu_pessimistisch"),
    ("z10", 10, {"lage_mm": [3.0, 5.0], "neigung_grad": [1.0, 2.0]}, "stimmt"),
    ("z10", 10, {"lage_mm": [3.0, 11.0], "neigung_grad": [1.0, 2.0]}, "zu_optimistisch"),
    ("z10", 10, {"lage_mm": [1.0, 2.0], "neigung_grad": [0.2, 0.5]}, "zu_pessimistisch"),
    ("z11", 11, {"dicke_mm": [4.8, 5.2, 5.6]}, "stimmt"),
    ("z11", 11, {"dicke_mm": [5.0, 8.5, 9.0]}, "zu_optimistisch"),
    ("z11", 11, {"dicke_mm": [2.0, 2.4]}, "zu_pessimistisch"),
    ("z12", 12, {"versatz_mm": 3.0, "dreh_grad": 2.0}, "stimmt"),
    ("z12", 12, {"versatz_mm": 12.0, "dreh_grad": 2.0}, "zu_optimistisch"),
    ("z12", 12, {"versatz_mm": 0.8, "dreh_grad": 0.3}, "zu_pessimistisch"),
]


@pytest.mark.parametrize("key,zid,mess,erwartet", FAELLE)
def test_urteil_je_fall(kat, key, zid, mess, erwartet):
    r = _urteile(kat, {key: mess})[zid]
    assert r["urteil"] == erwartet, r
    assert r["konsequenz"] and r["teile"]
    z = kat["_zeilen"][zid]
    if erwartet == "stimmt":
        assert r["konsequenz"] == z["konsequenz"]["stimmt"]


def test_konsequenz_stufen_dicke_und_gier(kat):
    k6 = _urteile(kat, {"z11": {"dicke_mm": [7.0]}})[11]["konsequenz"]
    k9 = _urteile(kat, {"z11": {"dicke_mm": [9.0]}})[11]["konsequenz"]
    assert "Grenzbereich" in k6 and "keine Station-Pose" in k9 and k6 != k9
    g25 = _urteile(kat, {"z09": {"gier_grad": [2.5]}})[9]["konsequenz"]
    g5 = _urteile(kat, {"z09": {"gier_grad": [5.0]}})[9]["konsequenz"]
    assert "weiten" in g25 and "verwerfen" in g5
    z12 = _urteile(kat, {"z12": {"versatz_mm": 3.0, "dreh_grad": 12.0}})[12]["konsequenz"]
    assert "K und A beim Teller tragen nicht" in z12                      # 12 Grad liegt über der 10-Grad-Grenze


def test_z12_aus_punktpaaren(kat):
    rng = np.random.default_rng(7)
    ref = rng.uniform(-150, 150, (5, 3))
    station = ref + np.array([0.0, 0.0, 6.5])                             # reiner Versatz 6,5 mm
    r = _urteile(kat, {"z12": {"station": station.tolist(), "referenz": ref.tolist()}})[12]
    assert r["urteil"] == "zu_optimistisch"
    assert r["teile"][0]["gemessen"] == pytest.approx(6.5, abs=0.01) and r["teile"][1]["gemessen"] == pytest.approx(0.0, abs=0.01)


def test_z13_ist_einordnung_ohne_urteil(kat):
    r = {s: _urteile(kat, {"z13": {"spiel_grad": [s]}})[13] for s in (2.0, 5.0, 9.0)}
    assert all(x["urteil"] == "unbekannt" for x in r.values())
    assert len({x["konsequenz"] for x in r.values()}) == 3


def test_z04_zaehlt_plaetze_und_ignoriert_auszug_null(kat):
    # Hauptposition 0,225 m: alle 16 Gläser nutzbar vorhergesagt
    ok = {"haupt": {"a225": {f"glas_{i}": True for i in range(1, 17)}}}
    assert _urteile(kat, {"z04": ok})[4]["urteil"] == "stimmt"
    schlecht = {"haupt": {"a225": {f"glas_{i}": i > 6 for i in range(1, 17)}}}
    r = _urteile(kat, {"z04": schlecht})[4]
    assert r["urteil"] == "zu_optimistisch" and any("glas_1" in h for h in r["hinweise"])
    mehr = {"haupt": {"a450": {f"oberteller_0_{i}": True for i in range(1, 5)}}}      # vorhergesagt: 3 der 4 nicht nutzbar
    assert _urteile(kat, {"z04": mehr})[4]["urteil"] == "zu_pessimistisch"
    a0 = {"haupt": {"a0": {f"glas_{i}": False for i in range(1, 17)}}}
    assert _urteile(kat, {"z04": a0})[4]["urteil"] == "unbekannt"                  # Auszug 0 wird nicht gewertet


def test_unbekannt_zeilen_liefern_ausgang(kat):
    u = _urteile(kat, {"u1": {"delta_erkennung_pp": -35}, "u2": {"ausreisser_pct": 1.0}, "u3": {"abdeckung_glas_pct": [2, 3]}})
    assert (u["u1"]["ausgang"], u["u2"]["ausgang"], u["u3"]["ausgang"]) == ("C", "A", "C")
    assert "Slot-Position" in u["u3"]["konsequenz"] and u["u3"]["urteil"] == "unbekannt"
    assert KA.auswerten(kat, {"messungen": {}}, Path("."))["zaehlung"] == {"nicht_gemessen": 16}


def test_fehlende_aufnahme_stoppt_nicht_die_anderen_zeilen(kat, tmp_path):
    mess = {"messungen": {"z01": {"ensenso": [{"aufnahme": "gibt_es_nicht.npz"}]}, "z12": {"versatz_mm": 3.0, "dreh_grad": 2.0}}}
    erg = KA.auswerten(kat, mess, tmp_path)
    z = {r["id"]: r for r in erg["zeilen"]}
    assert z[1]["urteil"] == "fehler" and "gibt_es_nicht" in z[1]["konsequenz"] and z[12]["urteil"] == "stimmt"
    assert erg["fehler"] == ["z01"]


# --- Beispiel: Aufnahmen aus synthetischen Daten, Ende zu Ende -----------------------------------------------

def test_beispielmessdatei_ende_zu_ende(kat, tmp_path):
    geschr = KA.demo_schreiben(tmp_path)
    assert len(geschr) == 2 + 20 + 4 + 8
    mess = KA.lade_yaml(BEISPIEL)
    erg = KA.auswerten(kat, mess, tmp_path)
    assert erg["fehler"] == []
    u = {r["id"]: r["urteil"] for r in erg["zeilen"]}
    assert u[1] == "zu_optimistisch"             # Ensenso 0,82 m und D405 0,20 m zu laut
    assert u[2] == "zu_optimistisch" and u[3] == "stimmt" and u[4] == "zu_optimistisch"
    assert u[5] == "stimmt" and u[6] == "zu_optimistisch" and u[7] == "zu_optimistisch"
    assert u[8] == "zu_pessimistisch" and u[9] == "zu_optimistisch" and u[10] == "stimmt" and u[11] == "stimmt"
    assert u[12] == "zu_pessimistisch" and u[13] == "unbekannt"
    assert (u["u1"], u["u2"], u["u3"]) == ("unbekannt",) * 3
    assert {r["id"]: r.get("ausgang") for r in erg["zeilen"] if isinstance(r["id"], str)} == {"u1": "B", "u2": "B", "u3": "C"}
    # die drei Urteilsarten kommen vor
    assert {"stimmt", "zu_optimistisch", "zu_pessimistisch"} <= set(u.values())


def test_kommandozeile_schreibt_markdown_und_json(tmp_path):
    aufn = tmp_path / "aufnahmen"
    assert KA.main(["--demo", str(aufn)]) == 0
    out = tmp_path / "ergebnis"
    assert KA.main([str(BEISPIEL), "--basis", str(aufn), "--out", str(out)]) == 0
    md = (out / "kameratag_ergebnis.md").read_text(encoding="utf-8")
    js = json.loads((out / "kameratag_ergebnis.json").read_text(encoding="utf-8"))
    assert "## Zeile 11" in md and "Konsequenz:" in md and "| 13 |" in md
    assert len(js["zeilen"]) == 16 and js["zaehlung"]["zu_pessimistisch"] == 2
