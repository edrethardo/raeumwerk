"""raeumwerk: Experimentdatei und ``run`` (mit Testdouble), CLI.

Ohne Simulator: ``run`` laeuft hier mit ``backend: attrappe`` (Testdouble aus
``raeumwerk.simulator``); der Newton-Weg ist im Abnahmelauf belegt
(docs/STATUS.md). ``report``/``next`` auf dem fixierten Beispiel-Run:
``tests/test_auswertung.py``.
"""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytest.importorskip("yaml")

from raeumwerk import auswertung, experiment as ex, lauf  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
BEISPIEL = REPO / "experimente" / "beispiel.yaml"


def _exp(tmp_path, **aend):
    d = {"name": "probe", "backend": "attrappe", "versuche": 4, "seed": 7,
         "parameter": {"greifkraft_n": {"bereich": [2.0, 20.0]}, "greif_versatz_y_m": {"bereich": [-0.035, 0.035]},
                       "reibung_glas": 0.2, "reibung_finger": {"werte": [0.3, 1.0]}}}
    d.update(aend)
    p = tmp_path / "exp.yaml"
    p.write_text(ex.nach_yaml(d) + "\n")
    return p


# --- Experimentdatei --------------------------------------------------------

def test_beispiel_experiment_is_valid():
    e = ex.laden(BEISPIEL)
    assert e.backend == "newton" and e.versuche >= 6
    assert e.stueck_max_minuten <= 30
    assert set(e.parameter) <= set(ex.PARAMETER)


def test_versuchsliste_deterministic_and_in_range(tmp_path):
    e = ex.laden(_exp(tmp_path))
    a, b = ex.versuchsliste(e), ex.versuchsliste(e)
    assert a == b and [v["nr"] for v in a] == [0, 1, 2, 3]
    for v in a:
        p = v["parameter"]
        assert 2.0 <= p["greifkraft_n"] <= 20.0 and -0.035 <= p["greif_versatz_y_m"] <= 0.035
        assert p["reibung_glas"] == 0.2 and p["reibung_finger"] in (0.3, 1.0)
    e2 = ex.laden(_exp(tmp_path, seed=8))
    assert ex.versuchsliste(e2) != a


@pytest.mark.parametrize("aend, text", [
    ({"parameter": {"windstaerke": 1.0}}, "unbekannte Parameter"),
    ({"parameter": {"greifkraft_n": 80.0}}, "ausserhalb"),
    ({"parameter": {"greifkraft_n": {"bereich": [10.0, 5.0]}}}, "unten > oben"),
    ({"parameter": {"greifkraft_n": {"irgendwie": 3}}}, "unbekannte Angabe"),
    ({"stueck": {"max_minuten": 45}}, "max_minuten"),
    ({"versuche": 0}, "versuche"),
    ({"backend": "isaac"}, "backend"),
    ({"name": "a b"}, "name"),
    ({"tempo": 3}, "unbekannte Schluessel"),
])
def test_experiment_rejects_bad_input(tmp_path, aend, text):
    with pytest.raises(ex.ExperimentFehler, match=text):
        ex.laden(_exp(tmp_path, **aend))


def test_yaml_writer_roundtrip():
    import yaml
    d = {"name": "x-n1", "versuche": 3, "seed": 1, "parameter": {"greifkraft_n": {"bereich": [1.5, 2.0]},
                                                                  "reibung_glas": {"fest": 0.2}},
         "stueck": {"max_minuten": 10.0}, "begruendung": ["a: [1, 2] (Regel 1)", "b \"c\""],
         "abgeleitet_von": {"run": "r", "konfig_hash": "ab"}}
    assert yaml.safe_load(ex.nach_yaml(d)) == d


def test_konfig_hash_changes_with_scene(tmp_path):
    e = ex.laden(_exp(tmp_path))
    h1, _ = ex.konfig_hash(e)
    szene = tmp_path / "scene.yaml"
    szene.write_text((REPO / "config" / "scene.yaml").read_text() + "\n# geaendert\n")
    e.szene = str(szene)
    h2, d = ex.konfig_hash(e)
    assert h1 != h2 and len(h1) == 64 and set(d) == {"szene", "roboter"}


def test_szene_fuer_applies_parameters():
    from greifen import szene
    basis = szene.load()
    sz = ex.szene_fuer(basis, {"reibung_finger": 0.3, "reibung_glas": 0.2, "reibung_tisch": 0.4,
                               "greifkraft_n": 5.0, "glas_x_m": 0.56})
    assert sz.kontakt["reibung_finger"] == 0.3 and sz.glas["reibung"] == 0.2 and sz.tisch["reibung"] == 0.4
    assert sz.greifen["greifkraft_n"] == 5.0 and sz.glas["start_xy_m"] == [0.56, 0.35]
    assert basis.kontakt["reibung_finger"] == 1.0  # Basis unveraendert
    assert ex.greif_versatz({"greif_versatz_y_m": 0.02}) == (0.0, 0.02, 0.0)


# --- run (Testdouble) -------------------------------------------------------

MANIFEST_FELDER = {"schema", "run", "name", "erstellt", "experiment_datei", "git", "konfig_hash", "dateien_sha256",
                   "experiment", "backend", "seed", "parameter_standard", "versuche_geplant", "versuche_plan",
                   "versionen", "device", "status", "versuche_fertig", "erfolge", "stuecke", "letzte_aenderung"}


def test_run_writes_complete_run_dir(tmp_path):
    run = tmp_path / "run"
    assert lauf.run(_exp(tmp_path), run, log=lambda s: None) == lauf.EXIT_FERTIG
    m = lauf.lies_manifest(run)
    assert MANIFEST_FELDER <= set(m)
    assert m["status"] == "fertig" and m["versuche_fertig"] == 4
    assert len(m["git"]["sha"] or "") == 40 and m["git"]["quelle"] in ("git", "REVISION")
    assert len(m["konfig_hash"]) == 64 and set(m["dateien_sha256"]) == {"experiment", "szene", "roboter"}
    assert m["versionen"]["python"] and m["versionen"]["raeumwerk"]
    assert [v["nr"] for v in m["versuche_plan"]] == [0, 1, 2, 3]
    assert m["stuecke"][0]["versuche"] == [0, 1, 2, 3] and m["stuecke"][0]["grund_ende"] == "alle Versuche fertig"
    assert sorted(p.name for p in (run / "versuche").iterdir()) == [f"versuch-{i:03d}.json" for i in range(4)]
    zeilen = (run / "messwerte.csv").read_text().splitlines()
    assert len(zeilen) == 5 and zeilen[0].startswith("nr,erfolg,gruende")
    assert (run / "experiment.yaml").read_text() == _exp(tmp_path).read_text()
    # keine Rechnerpfade im Manifest
    text = (run / "manifest.json").read_text()
    assert str(tmp_path) not in text and not re.search(r'"/[A-Za-z]', text)


def test_run_in_chunks_resumes_from_checkpoints(tmp_path, monkeypatch):
    monkeypatch.setenv("RAEUMWERK_ATTRAPPE_WAND_S", "1.0")
    run, e = tmp_path / "run", _exp(tmp_path)
    budget = 2.4 / 60  # 2,4 s: zwei Versuche zu je 1 s, der dritte passt nicht mehr
    assert lauf.run(e, run, max_minuten=budget, log=lambda s: None) == lauf.EXIT_WEITER
    m = lauf.lies_manifest(run)
    assert m["status"] == "unvollstaendig" and m["versuche_fertig"] == 2
    assert m["stuecke"][0]["grund_ende"].startswith("Budget")
    t_vorher = (run / "versuche" / "versuch-000.json").stat().st_mtime_ns
    assert lauf.run(e, run, max_minuten=budget, log=lambda s: None) == lauf.EXIT_FERTIG
    m = lauf.lies_manifest(run)
    assert m["status"] == "fertig" and [s["versuche"] for s in m["stuecke"]] == [[0, 1], [2, 3]]
    assert (run / "versuche" / "versuch-000.json").stat().st_mtime_ns == t_vorher  # nicht neu gerechnet


def test_run_refuses_other_config_in_same_dir(tmp_path):
    run = tmp_path / "run"
    assert lauf.run(_exp(tmp_path), run, log=lambda s: None) == 0
    assert lauf.run(_exp(tmp_path, seed=99), run, log=lambda s: None) == lauf.EXIT_AUFRUF


def test_run_rejects_chunk_over_30_minutes(tmp_path):
    assert lauf.run(_exp(tmp_path), tmp_path / "run", max_minuten=31, log=lambda s: None) == lauf.EXIT_AUFRUF


def test_run_name_resolves_under_runs_root(tmp_path, monkeypatch):
    monkeypatch.setenv("RAEUMWERK_EXPERIMENT_RUNS", str(tmp_path / "runs"))
    assert lauf.run_pfad("abc") == tmp_path / "runs" / "abc"
    assert lauf.run_pfad("./abc") == Path("./abc")
    assert lauf.run(_exp(tmp_path), "abc", log=lambda s: None) == 0
    assert (tmp_path / "runs" / "abc" / "manifest.json").is_file()


def test_run_sigterm_keeps_finished_trials(tmp_path):
    run = tmp_path / "run"
    env = dict(os.environ, RAEUMWERK_ATTRAPPE_WAND_S="1.5", PYTHONPATH=str(REPO))
    proc = subprocess.Popen([sys.executable, "-m", "raeumwerk", "run", str(_exp(tmp_path)), "--run-dir", str(run)],
                            cwd=str(REPO), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    ende = time.monotonic() + 30
    while time.monotonic() < ende and not (run / "versuche" / "versuch-000.json").exists():
        time.sleep(0.1)
    proc.send_signal(signal.SIGTERM)
    out, err = proc.communicate(timeout=30)
    assert proc.returncode == lauf.EXIT_ABBRUCH, out + err
    m = lauf.lies_manifest(run)
    assert m["status"] == "abgebrochen" and m["stuecke"][-1]["grund_ende"] == "SIGTERM"
    assert 1 <= m["versuche_fertig"] < 4
    assert not list((run / "versuche").glob("*.tmp"))


def test_cli_report_and_next_on_attrappe_run(tmp_path):
    run = tmp_path / "run"
    lauf.run(_exp(tmp_path, versuche=8), run, log=lambda s: None)
    env = dict(os.environ, PYTHONPATH=str(REPO))
    r = subprocess.run([sys.executable, "-m", "raeumwerk", "report", str(run), "--json"], cwd=str(REPO), env=env,
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    b = json.loads(r.stdout)
    assert b["versuche_fertig"] == 8 and (run / "bericht.md").is_file()
    n = subprocess.run([sys.executable, "-m", "raeumwerk", "next", str(run), "--out", str(tmp_path / "v.yaml")],
                       cwd=str(REPO), env=env, capture_output=True, text=True, timeout=60)
    assert n.returncode == 0, n.stderr
    neu = ex.laden(tmp_path / "v.yaml")
    assert neu.name == "probe-n1" and neu.seed == 8
    r2 = subprocess.run([sys.executable, "-m", "raeumwerk", "report", str(tmp_path / "fehlt")], cwd=str(REPO),
                        env=env, capture_output=True, text=True, timeout=60)
    assert r2.returncode == 2


def test_auswertung_is_stdlib_only():
    """report/next laufen auf dem Steuerrechner ohne numpy/pyyaml."""
    code = ("import sys; sys.modules['yaml'] = None; sys.modules['numpy'] = None; "
            "import raeumwerk.auswertung, raeumwerk.cli")
    r = subprocess.run([sys.executable, "-c", code], cwd=str(REPO), capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert auswertung.bericht  # Modul geladen
