"""``raeumwerk run``: Versuche eines Experiments in einem Run-Verzeichnis.

Run-Verzeichnis::

    <run>/manifest.json          Git-SHA, Konfig-Hash, Versionen, Versuchsplan, Status, Stuecke
    <run>/experiment.yaml        Kopie der Experimentdatei
    <run>/versuche/versuch-NNN.json  Ergebnis + Messwerte je Versuch (= Checkpoint)
    <run>/messwerte.csv          eine Zeile je fertigem Versuch (Kernwerte)

Fortsetzen: Derselbe Aufruf mit ``--run-dir`` faehrt nur die Versuche, deren
``versuch-NNN.json`` fehlt. Der Konfig-Hash muss gleich sein, sonst Abbruch
(Exit 2), damit nie zwei Konfigurationen in einem Run landen.

Stuecke: ``--max-minuten`` (Standard ``stueck.max_minuten`` der
Experimentdatei, hoechstens 30) begrenzt die Laufzeit eines Aufrufs. Vor jedem
Versuch wird geschaetzt (laengster Versuch bisher), ob er noch ins Budget
passt; sonst endet das Stueck mit Exit 3 ("weiter"). Mindestens ein Versuch je
Stueck, damit es immer vorangeht.

Exit: 0 fertig, 1 Fehler, 2 Aufruf/Konfiguration, 3 Stueck zu Ende (weiter),
143 abgebrochen (SIGTERM; fertige Versuche bleiben, der laufende nicht).
"""
from __future__ import annotations

import contextlib
import csv
import datetime as _dt
import io
import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import __version__
from . import experiment as ex

SCHEMA = "raeumwerk-run/1"
EXIT_FERTIG, EXIT_FEHLER, EXIT_AUFRUF, EXIT_WEITER, EXIT_ABBRUCH = 0, 1, 2, 3, 143
CSV_SPALTEN = ["nr", "erfolg", "gruende", "fehler_xy_mm", "kippung_end_grad", "hub_max_mm",
               "tisch_durchdringung_mm", "finger_durchdringung_mm", "glas_v_max_m_s", "wand_s"]


class Abbruch(Exception):
    pass


def jetzt() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def git_stand(repo: Path = ex.REPO) -> Dict[str, Any]:
    """SHA und ob der Arbeitsstand vom Commit abweicht. Ohne .git aus der Datei REVISION."""
    try:
        sha = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True,
                             timeout=10)
        if sha.returncode == 0:
            st = subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=no"],
                                capture_output=True, text=True, timeout=10)
            return {"sha": sha.stdout.strip(), "dirty": bool(st.stdout.strip()), "quelle": "git"}
    except (OSError, subprocess.SubprocessError):
        pass
    rev = repo / "REVISION"
    if rev.is_file():
        teile = rev.read_text().split()
        return {"sha": teile[0] if teile else None, "dirty": "dirty" in teile[1:], "quelle": "REVISION"}
    return {"sha": None, "dirty": None, "quelle": "unbekannt"}


def runs_wurzel() -> Path:
    if os.environ.get("RAEUMWERK_EXPERIMENT_RUNS"):
        return Path(os.environ["RAEUMWERK_EXPERIMENT_RUNS"])
    home = os.environ.get("RAEUMWERK_HOME") or str(Path.home() / "raeumwerk")
    return Path(home) / "runs" / "experimente"


def run_pfad(angabe: Path | str) -> Path:
    """Run-Verzeichnis: ein Name ohne ``/`` liegt unter ``runs_wurzel()``, sonst Pfad wie angegeben."""
    s = str(angabe)
    if "/" not in s and not s.startswith("."):
        return runs_wurzel() / s
    return Path(s)


def _rel(p: Path) -> str:
    """Pfad relativ zum Repo; ausserhalb nur der Dateiname (keine Rechnerpfade im Manifest)."""
    try:
        return str(p.resolve().relative_to(ex.REPO))
    except ValueError:
        return p.name


def _atomar(p: Path, text: str) -> None:
    tmp = p.with_name(f"{p.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, p)


@contextlib.contextmanager
def _sperre(run: Path):
    """Exklusive Dateisperre auf ``<run>/.manifest.lock`` (mehrere Prozesse, ``--teil``)."""
    import fcntl

    with open(run / ".manifest.lock", "a+", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def lies_manifest(run: Path) -> Dict[str, Any]:
    return json.loads((run / "manifest.json").read_text(encoding="utf-8"))


def fertige_versuche(run: Path) -> Dict[int, Dict[str, Any]]:
    out = {}
    for f in sorted((run / "versuche").glob("versuch-*.json")):
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue  # halb geschriebene Datei gibt es nicht (atomar), unlesbar = nicht fertig
        out[int(rec["versuch"]["nr"])] = rec
    return out


def _mm(x) -> Optional[float]:
    v = ex.optional_float(x)
    return None if v is None else round(v * 1e3, 3)


def schreibe_csv(run: Path, recs: Dict[int, Dict[str, Any]]) -> None:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_SPALTEN + sorted({k for r in recs.values() for k in r.get("parameter", {})}))
    pnamen = sorted({k for r in recs.values() for k in r.get("parameter", {})})
    for nr in sorted(recs):
        r = recs[nr]
        m = r.get("messung", {})
        w.writerow([nr, int(bool(r["erfolg"])), "|".join(r["gruende"]), _mm(r["position"]["fehler_xy_m"]),
                    r["kippung_grad"]["ende"], _mm(m.get("hub_max_m")), _mm(m.get("tisch_durchdringung_max_m")),
                    _mm(m.get("finger_durchdringung_max_m")), m.get("glas_v_max_m_s"),
                    r.get("dauer", {}).get("wand_sim_s")] + [r["parameter"].get(k) for k in pnamen])
    _atomar(run / "messwerte.csv", buf.getvalue())


def neues_manifest(exp: ex.Experiment, exp_pfad: Path, run: Path, khash: str, dateien: Dict[str, str],
                   plan: List[Dict[str, Any]], standard: Dict[str, float]) -> Dict[str, Any]:
    return {
        "schema": SCHEMA, "run": run.name, "name": exp.name, "erstellt": jetzt(),
        "experiment_datei": _rel(exp_pfad),
        "git": git_stand(), "konfig_hash": khash,
        "dateien_sha256": {"experiment": ex.sha256_datei(exp_pfad), **dateien},
        "experiment": exp.als_dict(), "backend": exp.backend, "seed": exp.seed,
        "parameter_standard": standard, "versuche_geplant": len(plan), "versuche_plan": plan,
        "versionen": {}, "device": None, "status": "neu", "versuche_fertig": 0, "erfolge": 0, "stuecke": [],
    }


def run(exp_pfad: Path | str, run_dir: Optional[Path | str] = None, max_minuten: Optional[float] = None,
        device: Optional[str] = None, backend: Optional[str] = None, log=print,
        teil: Optional[Tuple[int, int]] = None) -> int:
    """``teil=(k, n)``: nur die Versuche mit ``nr % n == k`` (mehrere Prozesse auf
    einem Run-Verzeichnis; das Manifest wird unter einer Dateisperre gemischt)."""
    exp_pfad = Path(exp_pfad)
    if teil is not None and not (teil[1] >= 1 and 0 <= teil[0] < teil[1]):
        log(f"FEHLER --teil {teil}: k/n mit 0 <= k < n")
        return EXIT_AUFRUF
    try:
        exp = ex.laden(exp_pfad)
        if backend:
            exp.backend = ex.aus_dict(dict(exp.als_dict(), backend=backend)).backend
        khash, dateien = ex.konfig_hash(exp)
    except (ex.ExperimentFehler, OSError) as e:
        log(f"FEHLER Experiment: {e}")
        return EXIT_AUFRUF
    budget_min = float(max_minuten if max_minuten is not None else exp.stueck_max_minuten)
    if not 0 < budget_min <= 30:
        log("FEHLER --max-minuten: 0 < x <= 30 (Stuecke hoechstens 30 min)")
        return EXIT_AUFRUF
    if run_dir is None:
        run_dir = runs_wurzel() / f"{exp.name}-{_dt.datetime.now(_dt.timezone.utc):%Y%m%dT%H%M%SZ}"
    run = run_pfad(run_dir)
    (run / "versuche").mkdir(parents=True, exist_ok=True)

    standard = ex.standardwerte_fuer(exp)
    with _sperre(run):
        if (run / "manifest.json").exists():
            man = lies_manifest(run)
            if man.get("konfig_hash") != khash:
                log(f"FEHLER {run.name}: Konfig-Hash {khash[:12]} passt nicht zum Run ({str(man.get('konfig_hash'))[:12]})")
                return EXIT_AUFRUF
            git = git_stand()
            if git.get("sha") != man["git"].get("sha"):
                man.setdefault("git_spaeter", []).append(dict(git, ab_stueck=len(man["stuecke"])))
        else:
            man = neues_manifest(exp, exp_pfad, run, khash, dateien, ex.versuchsliste(exp), standard)
            shutil.copyfile(exp_pfad, run / "experiment.yaml")
        plan = man["versuche_plan"]

        stueck = {"nr": len(man["stuecke"]), "id": f"{os.getpid()}-{time.time_ns()}", "start": jetzt(), "ende": None,
                  "budget_min": budget_min, "versuche": [], "grund_ende": None}
        if teil is not None:
            stueck["teil"] = f"{teil[0]}/{teil[1]}"
        man["stuecke"].append(stueck)
        man["status"] = "laeuft"
        _atomar(run / "manifest.json", json.dumps(man, indent=2))
    eigen = {"git_spaeter", "versionen", "device", "fehler_traceback", "letzte_aenderung", "status"}

    def mischen(status: Optional[str] = None) -> None:
        """Eigenes Stueck und eigene Felder ins Manifest auf der Platte mischen."""
        with _sperre(run):
            m = lies_manifest(run)
            m["stuecke"] = sorted([s for s in m["stuecke"] if s.get("id") != stueck["id"]] + [stueck],
                                  key=lambda s: s["nr"])
            for k in eigen:
                if k in man:
                    m[k] = man[k]
            if status:
                m["status"] = status
            f = fertige_versuche(run)
            m["versuche_fertig"] = len(f)
            m["erfolge"] = sum(1 for r in f.values() if r["erfolg"])
            if len(f) == len(plan):
                m["status"] = "fertig"
            man["erfolge"], man["versuche_fertig"] = m["erfolge"], m["versuche_fertig"]
            schreibe_csv(run, f)
            _atomar(run / "manifest.json", json.dumps(m, indent=2))
            man["status"] = m["status"]

    def term(signum, frame):  # noqa: ARG001
        raise Abbruch()

    alt = signal.signal(signal.SIGTERM, term)
    t0 = time.monotonic()
    rc = EXIT_FEHLER
    try:
        sim = None
        fertig = fertige_versuche(run)
        offen = [v for v in plan if v["nr"] not in fertig
                 and (teil is None or v["nr"] % teil[1] == teil[0])]
        dauern = [float(r.get("wand_gesamt_s") or 0.0) for r in fertig.values()]
        for v in offen:
            vergangen = time.monotonic() - t0
            schaetzung = max(dauern) if dauern else 0.0
            if stueck["versuche"] and vergangen + schaetzung > budget_min * 60:
                stueck["grund_ende"] = f"Budget: {vergangen:.0f} s + ~{schaetzung:.0f} s > {budget_min * 60:.0f} s"
                break
            if sim is None:
                from . import simulator
                sim = simulator.erzeugen(exp, exp.backend, device)
                man["versionen"] = dict(sim.versionen, python=platform.python_version(),
                                        raeumwerk=__version__, plattform=platform.machine())
                man["device"] = sim.device
            tv = time.monotonic()
            rec = sim.versuch(v["nr"], v["parameter"])
            rec["wand_gesamt_s"] = round(time.monotonic() - tv, 2)
            _atomar(run / "versuche" / f"versuch-{v['nr']:03d}.json", json.dumps(rec, indent=2))
            fertig[v["nr"]] = rec
            dauern.append(rec["wand_gesamt_s"])
            stueck["versuche"].append(v["nr"])
            log("VERSUCH " + json.dumps({"nr": v["nr"], "erfolg": rec["erfolg"], "gruende": rec["gruende"],
                                         "parameter": v["parameter"], "wand_s": rec["wand_gesamt_s"]}))
            mischen()
        fertig = fertige_versuche(run)
        eigene_offen = [v for v in plan if v["nr"] not in fertig and (teil is None or v["nr"] % teil[1] == teil[0])]
        if len(fertig) == len(plan):
            man["status"], rc = "fertig", EXIT_FERTIG
            stueck["grund_ende"] = stueck["grund_ende"] or "alle Versuche fertig"
        elif teil is not None and not eigene_offen:
            man["status"], rc = "laeuft", EXIT_FERTIG
            stueck["grund_ende"] = stueck["grund_ende"] or f"Teil {teil[0]}/{teil[1]} fertig, andere Teile offen"
        else:
            man["status"], rc = "unvollstaendig", EXIT_WEITER
    except Abbruch:
        man["status"], rc = "abgebrochen", EXIT_ABBRUCH
        stueck["grund_ende"] = "SIGTERM"
    except Exception as e:  # noqa: BLE001
        man["status"], rc = "fehler", EXIT_FEHLER
        stueck["grund_ende"] = f"{type(e).__name__}: {e}"
        man["fehler_traceback"] = traceback.format_exc()[-4000:]
    finally:
        signal.signal(signal.SIGTERM, alt)
        stueck["ende"] = jetzt()
        stueck["wand_s"] = round(time.monotonic() - t0, 2)
        man["letzte_aenderung"] = jetzt()
        mischen(man["status"])
    log("RUN_RESULT " + json.dumps({"run": run.name, "status": man["status"], "rc": rc,
                                    "fertig": man["versuche_fertig"], "geplant": len(plan),
                                    "erfolge": man["erfolge"], "stueck": stueck["nr"],
                                    "grund_ende": stueck["grund_ende"]}))
    log(f"Run: {run}")
    sys.stdout.flush()
    return rc
