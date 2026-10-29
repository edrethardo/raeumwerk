"""``raeumwerk report`` und ``raeumwerk next`` auf einem fixierten Beispiel-Run (ohne GPU).

``tests/daten/beispiel-abnahme/`` ist das unveraenderte Run-Verzeichnis des
Abnahmelaufs (``experimente/beispiel.yaml``, 8 Versuche, Newton 1.6.1 auf der
GPU, ueber ``scripts/submit_gpu.sh`` in 3 Stuecken; docs/STATUS.md). Die Tests
arbeiten auf einer Kopie, die Regelvarianten auf veraenderten Kopien.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from raeumwerk import auswertung, experiment as ex

REPO = Path(__file__).resolve().parents[1]
FIX = REPO / "tests" / "daten" / "beispiel-abnahme"


@pytest.fixture
def run(tmp_path):
    ziel = tmp_path / "beispiel-abnahme"
    shutil.copytree(FIX, ziel)
    return ziel


def _aendern(run: Path, versuche=None, manifest=None):
    """versuche: {nr: (erfolg, gruende)} oder callable(rec); manifest: callable(man)."""
    for f in sorted((run / "versuche").glob("versuch-*.json")):
        rec = json.loads(f.read_text())
        nr = rec["versuch"]["nr"]
        if callable(versuche):
            versuche(rec)
        elif versuche and nr in versuche:
            rec["erfolg"], rec["gruende"] = versuche[nr]
        f.write_text(json.dumps(rec))
    if manifest:
        man = json.loads((run / "manifest.json").read_text())
        manifest(man)
        (run / "manifest.json").write_text(json.dumps(man))


# --- der fixierte Run selbst (Abnahme: Manifest vollstaendig) ---------------

def test_fixture_manifest_is_complete():
    m = json.loads((FIX / "manifest.json").read_text())
    for feld in ("schema", "run", "name", "erstellt", "experiment_datei", "git", "konfig_hash", "dateien_sha256",
                 "experiment", "backend", "seed", "parameter_standard", "versuche_geplant", "versuche_plan",
                 "versionen", "device", "status", "versuche_fertig", "erfolge", "stuecke", "letzte_aenderung"):
        assert m.get(feld) not in (None, "", [], {}), feld
    assert len(m["git"]["sha"]) == 40 and m["git"]["dirty"] is False
    assert len(m["konfig_hash"]) == 64
    assert m["dateien_sha256"]["experiment"] == hashlib.sha256((FIX / "experiment.yaml").read_bytes()).hexdigest()
    assert m["versionen"]["newton"] == "1.6.1" and m["versionen"]["warp-lang"] == "1.17.0"
    assert m["device"] == "cuda:0" and m["backend"] == "newton" and m["status"] == "fertig"
    assert len(m["stuecke"]) == 3 and sorted(n for s in m["stuecke"] for n in s["versuche"]) == list(range(8))
    assert all(s["wand_s"] < s["budget_min"] * 60 + 60 for s in m["stuecke"])
    text = (FIX / "manifest.json").read_text() + "".join(p.read_text() for p in (FIX / "versuche").iterdir())
    assert not re.search(r'"/[A-Za-z]', text), "absoluter Pfad im Run"


# --- report -----------------------------------------------------------------

def test_report_on_fixture(run):
    b = auswertung.bericht(run)
    assert (b["versuche_geplant"], b["versuche_fertig"], b["erfolge"]) == (8, 8, 1)
    assert b["erfolgsquote"] == 0.125 and b["unvollstaendig"] is False and b["stuecke"] == 3
    assert b["fehlergruende"] == {"nicht_am_ziel": 7, "nicht_gegriffen": 5, "durchdringung": 1, "gekippt": 1}
    k = b["kollisionen"]
    assert k["arm_tisch"] == 0 and k["finger_glas_zu_tief"] == 1 and k["versuche_mit_kollision"] == [2]
    assert k["tisch_durchdringung_max_mm"] == 0.0 and k["finger_durchdringung_max_mm"] == pytest.approx(4.192, abs=1e-3)
    assert [f["nr"] for f in b["fehlversuche"]] == [0, 1, 2, 3, 5, 6, 7]
    assert b["fehlversuche"][2]["gruende"] == ["gekippt", "nicht_am_ziel", "durchdringung"]
    assert b["parameter"]["greifkraft_n"]["erfolge"] == [10.059517, 10.059517]
    assert b["parameter"]["greif_versatz_y_m"]["fehlversuche"] == [-0.034141, 0.034744]
    assert "reibung_glas" not in b["parameter"]  # fest, nicht variiert
    assert b["zielfehler_erfolge_mm"]["max"] == pytest.approx(0.838, abs=1e-3)


def test_report_text_and_files_via_cli(run):
    env = dict(os.environ, PYTHONPATH=str(REPO))
    r = subprocess.run([sys.executable, "-m", "raeumwerk", "report", str(run)], cwd=str(REPO), env=env,
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert "Versuche: 8/8, Erfolge 1" in r.stdout
    assert "Kollisionen: Arm/Tisch 0, Finger zu tief 1" in r.stdout
    assert "- nicht_gegriffen: 5" in r.stdout and "- Nr. 2: gekippt, nicht_am_ziel, durchdringung" in r.stdout
    assert json.loads((run / "bericht.json").read_text())["erfolge"] == 1
    assert (run / "bericht.md").read_text() == r.stdout


def test_report_marks_incomplete_run(run):
    (run / "versuche" / "versuch-007.json").unlink()
    b = auswertung.bericht(run)
    assert b["unvollstaendig"] is True and b["versuche_fertig"] == 7


# --- next -------------------------------------------------------------------

def test_next_on_fixture_rule_2(run):
    v = auswertung.vorschlag(run)
    assert v["name"] == "beispiel-n1" and v["seed"] == 32 and v["versuche"] == 8
    p = v["parameter"]
    assert p["greifkraft_n"]["bereich"] == pytest.approx([5.559517, 14.559517])
    assert p["greif_versatz_y_m"]["bereich"] == pytest.approx([-0.015004, 0.019996])
    assert p["reibung_finger"]["bereich"] == pytest.approx([0.330056, 0.730056])
    assert p["reibung_glas"] == {"fest": 0.2}
    assert v["abgeleitet_von"] == {"run": "beispiel-abnahme",
                                   "konfig_hash": json.loads((run / "manifest.json").read_text())["konfig_hash"]}
    assert len(v["begruendung"]) == 3 and all("(Regel 2)" in z for z in v["begruendung"])
    ex.aus_dict(v)


def test_next_cli_writes_loadable_experiment(run):
    env = dict(os.environ, PYTHONPATH=str(REPO))
    r = subprocess.run([sys.executable, "-m", "raeumwerk", "next", str(run)], cwd=str(REPO), env=env,
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert "(Regel 2)" in r.stdout
    pytest.importorskip("yaml")
    neu = ex.laden(run / "vorschlag.yaml")
    assert neu.name == "beispiel-n1" and neu.backend == "newton"
    assert neu.parameter["greifkraft_n"]["bereich"] == pytest.approx([5.559517, 14.559517])
    assert ex.versuchsliste(neu)  # sofort wieder fahrbar


def test_next_rule_1_narrows_to_successes(run):
    _aendern(run, {7: (True, [])})
    p = auswertung.vorschlag(run)["parameter"]
    assert p["greifkraft_n"]["bereich"] == [8.568105, 10.059517]
    assert p["greif_versatz_y_m"]["bereich"] == [-0.011878, 0.002496]


def test_next_rule_3_nicht_gegriffen_halves_offset(run):
    _aendern(run, {4: (False, ["nicht_gegriffen", "nicht_am_ziel"])})
    v = auswertung.vorschlag(run)
    assert v["parameter"]["greif_versatz_y_m"]["bereich"] == pytest.approx([-0.0175, 0.0175])
    assert v["parameter"]["greifkraft_n"]["bereich"] == [2.0, 20.0]
    assert any("Regel 3, nicht_gegriffen" in z for z in v["begruendung"])


def test_next_rule_3_gefallen_raises_lower_bounds(run):
    _aendern(run, lambda r: r.update(erfolg=False, gruende=["gefallen", "nicht_am_ziel"]))
    p = auswertung.vorschlag(run)["parameter"]
    assert p["greifkraft_n"]["bereich"] == [11.0, 20.0]
    assert p["reibung_finger"]["bereich"] == [0.6, 1.0]
    assert p["reibung_glas"] == {"fest": 0.2}


def test_next_rule_3_collision_grasps_higher(run):
    _aendern(run, lambda r: r.update(erfolg=False, gruende=["kollision_arm_tisch"]))
    v = auswertung.vorschlag(run)
    assert v["parameter"]["greif_versatz_z_m"] == {"fest": 0.005}
    ex.aus_dict(v)


def test_next_rule_3_penetration_lowers_force(run):
    _aendern(run, lambda r: r.update(erfolg=False, gruende=["durchdringung"]))
    assert auswertung.vorschlag(run)["parameter"]["greifkraft_n"]["bereich"] == [2.0, 11.0]


def test_next_rule_3_planning_shrinks_glass_position(run):
    def man(m):
        m["experiment"]["parameter"]["glas_x_m"] = {"bereich": [0.50, 0.60]}
    _aendern(run, lambda r: r.update(erfolg=False, gruende=["planung_fehlgeschlagen"]), man)
    assert auswertung.vorschlag(run)["parameter"]["glas_x_m"]["bereich"] == pytest.approx([0.525, 0.575])


def test_next_rule_4_keeps_successful_choices(run):
    def man(m):
        m["experiment"]["parameter"]["reibung_glas"] = {"werte": [0.2, 0.4]}
    _aendern(run, None, man)
    assert auswertung.vorschlag(run)["parameter"]["reibung_glas"] == {"werte": [0.2]}


def test_next_rule_5_random_search_when_no_rule(run):
    _aendern(run, lambda r: r.update(erfolg=False, gruende=["weggeschossen"]))
    v = auswertung.vorschlag(run)
    alt = json.loads((run / "manifest.json").read_text())["experiment"]["parameter"]
    assert v["parameter"] == alt and v["seed"] == 32
    assert v["begruendung"] == ["keine Regel griff: Zufallssuche im gleichen Raum mit Seed 32 (Regel 5)"]


def test_next_numbers_follow_up_names(run):
    def man(m):
        m["experiment"]["name"] = "beispiel-n1"
    _aendern(run, None, man)
    assert auswertung.vorschlag(run)["name"] == "beispiel-n2"
