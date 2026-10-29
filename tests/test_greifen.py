"""Greifdemo: Szene, Ablaufplanung, Bewertung (ohne GPU) und Backend-Lauf.

Ohne Backend laufen nur numpy-Tests. Die Backend-Tests starten
``scripts/demo_greifen.py`` wirklich (Newton) und pruefen das JSON; sie laufen
nur mit ``RAEUMWERK_RUN_GPU_SMOKE=1`` und einem Python mit Newton
(``RAEUMWERK_GREIFEN_PYTHON`` oder ``$RAEUMWERK_ROOT/venvs/isaaclab/bin/python``),
auf einem geteilten GPU-Rechner nur unter dem GPU-Lock (siehe docs/START.md).
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("yaml")

from greifen import bewertung, szene  # noqa: E402
from greifen.plan import PHASEN, Planer, Versuch, versuche  # noqa: E402
from rebel_model.config import load  # noqa: E402
from rebel_model.kinematics import Chain  # noqa: E402
from rebel_model.urdf_gen import build_urdf  # noqa: E402

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def cfg():
    return load()


@pytest.fixture(scope="module")
def sz():
    return szene.load()


@pytest.fixture(scope="module")
def chain(cfg):
    return Chain(build_urdf(cfg))


@pytest.fixture(scope="module")
def planer(chain, cfg, sz):
    return Planer(chain, cfg, sz)


@pytest.fixture(scope="module")
def demo_plan(planer, sz):
    return planer.plane(versuche(sz, "demo")[0])


# --- Szene ------------------------------------------------------------------

def test_scene_glass_is_common_water_glass(sz):
    g = sz.glas
    assert 0.070 <= g["durchmesser_m"] <= 0.080
    assert 0.100 <= g["hoehe_m"] <= 0.120
    assert 0.200 <= g["masse_kg"] <= 0.300


def test_scene_every_value_has_source(sz):
    quellen = set(sz.raw["quellen"])
    for abschnitt, werte in sz.raw.items():
        if abschnitt == "quellen":
            continue
        for key, node in werte.items():
            assert isinstance(node, dict) and "wert" in node, f"{abschnitt}.{key} ohne wert"
            src = node.get("src")
            assert src == "annahme" or src in quellen, f"{abschnitt}.{key}: Quelle {src!r} unbekannt"


def test_scene_glass_fits_gripper(cfg, sz):
    assert cfg.min_oeffnung < sz.glas["durchmesser_m"] < cfg.greifer["max_oeffnung_m"]


def test_grip_force_is_limited(planer, cfg, sz):
    kraft = (planer.q_kontakt - planer.q_zu) * sz.greifen["finger_ke"]
    assert kraft == pytest.approx(sz.greifen["greifkraft_n"])
    assert 0 < kraft <= cfg.greifer["kraft_n"]
    # Haltekraft: zwei Reibkontakte muessen das Gewicht deutlich tragen
    assert 2 * sz.kontakt["reibung_finger"] * kraft > 3 * sz.glas["masse_kg"] * 9.81


def test_glass_and_targets_on_table(sz):
    tx, ty = sz.tisch["mitte_xy_m"]
    gx, gy, _ = sz.tisch["groesse_m"]
    r = sz.glas_radius
    d = sz.variation["streuung_xy_m"]
    for x, y, rand in ((*sz.glas["start_xy_m"], d), (*sz.glas["ziel_xy_m"], 0.0)):
        assert abs(x - tx) + r + rand < gx / 2
        assert abs(y - ty) + r + rand < gy / 2


# --- Planung ----------------------------------------------------------------

def test_plan_demo_phases_in_order(demo_plan):
    assert demo_plan.ok, demo_plan.fehler
    assert [s.phase for s in demo_plan.segmente] == PHASEN
    t = 0.0
    for s in demo_plan.segmente:
        assert s.t0 == pytest.approx(t) and s.dauer > 0
        t += s.dauer


def test_plan_demo_reaches_cartesian_targets(demo_plan, chain, cfg, sz):
    tcp = [0, 0, cfg.greifer["tcp_ab_flansch_m"]]
    ende = {s.phase: s.wege[-1] for s in demo_plan.segmente}
    for phase in ("anfahrt", "anheben", "verfahren", "absetzen", "rueckzug"):
        soll = demo_plan.tcp_soll["greifen" if phase == "anfahrt" else phase]
        t = chain.fk(ende[phase], "gripper_base", tcp)
        assert np.linalg.norm(t[:3, 3] - soll) < 1e-4, phase
        assert t[:3, 2] @ [0, 0, -1] > math.cos(math.radians(0.1)), "Greifer zeigt nicht senkrecht nach unten"
    hub = demo_plan.tcp_soll["anheben"][2] - demo_plan.tcp_soll["greifen"][2]
    assert hub == pytest.approx(0.10)


def test_plan_demo_uses_axis7_for_transport(demo_plan, chain):
    i7 = chain.index["axis7"]
    ende = {s.phase: s.wege[-1] for s in demo_plan.segmente}
    weg = ende["verfahren"][i7] - ende["anheben"][i7]
    assert weg > 0.25  # 30 cm Versatz entlang der Schiene


def test_plan_demo_respects_speed_limits(demo_plan, planer, chain, cfg):
    vmax = planer.max_geschwindigkeit(demo_plan)
    limit = {n: (cfg.achse7["geschwindigkeit_m_s"] if n == "axis7" else
                 cfg.greifer["geschwindigkeit_m_s"] if n == "finger_left" else
                 math.radians(cfg.arm["geschwindigkeit_grad_s"])) for n in chain.active}
    for n in chain.active:
        assert vmax[chain.index[n]] <= limit[n] * 1.001, n


def test_plan_demo_clear_of_table_and_self(demo_plan):
    assert demo_plan.tisch_abstand_min_m > 0.01
    assert demo_plan.selbstkollision == []


def test_plan_sample_is_continuous(demo_plan):
    dt = 0.002
    ts = np.arange(0, demo_plan.dauer, dt)
    qs = np.array([demo_plan.sample(t)[0] for t in ts])
    qds = np.array([demo_plan.sample(t)[1] for t in ts])
    # Lage = Integral der Vorsteuerung (Euler, grob) -> keine Spruenge
    assert np.max(np.abs(np.diff(qs, axis=0))) < 0.01
    assert np.max(np.abs(qs[1:] - qs[:-1] - qds[:-1] * dt)) < 1e-3


def test_plan_is_deterministic(planer, sz):
    v = versuche(sz, "demo")[0]
    a, b = planer.plane(v), planer.plane(v)
    for sa, sb in zip(a.segmente, b.segmente):
        assert np.array_equal(sa.wege, sb.wege)


def test_variation_trials_fixed_seed(sz):
    a, b = versuche(sz, "variation"), versuche(sz, "variation")
    assert len(a) == sz.variation["versuche"] >= 20
    assert [v.start_xy for v in a] == [v.start_xy for v in b]
    x0, y0 = sz.glas["start_xy_m"]
    d = sz.variation["streuung_xy_m"]
    assert all(abs(v.start_xy[0] - x0) <= d and abs(v.start_xy[1] - y0) <= d for v in a)
    assert len({v.start_xy for v in a}) == len(a)


@pytest.mark.parametrize("ecke", [(-1, -1), (-1, 1), (1, -1), (1, 1)])
def test_variation_corners_reachable(planer, sz, ecke):
    d = sz.variation["streuung_xy_m"]
    x0, y0 = sz.glas["start_xy_m"]
    v = Versuch(99, "variation", (x0 + ecke[0] * d, y0 + ecke[1] * d), tuple(sz.glas["ziel_xy_m"]))
    p = planer.plane(v)
    assert p.ok, p.fehler


def test_negative_grasp_point_misses_glass(planer, sz, cfg):
    v = versuche(sz, "negativ")[0]
    p = planer.plane(v)
    assert p.ok, p.fehler  # der Plan selbst ist ausfuehrbar, nur der Greifpunkt ist falsch
    gx, gy = v.start_xy
    tx, ty, _ = p.tcp_soll["greifen"]
    # Finger (Breite quer zur Schliessrichtung) liegen ganz neben dem Glas
    assert abs(ty - gy) - cfg.greifer["finger_breite_m"] / 2 > sz.glas_radius


# --- Bewertung --------------------------------------------------------------

def _messung(**kw):
    m = {"plan_ok": True, "plan_fehler": [], "endlage_m": [0.850, 0.330, 0.215], "ziel_xy_m": [0.85, 0.33],
         "kippung_end_grad": 0.1, "hub_max_m": 0.0999, "transport_min_hub_m": 0.0995, "stehhoehe_soll_m": 0.215,
         "tisch_durchdringung_max_m": 0.0, "finger_durchdringung_max_m": 0.001, "glas_v_max_m_s": 0.2,
         "nan": False}
    m.update(kw)
    return m


@pytest.mark.parametrize("aenderung, gruende", [
    ({}, []),
    ({"hub_max_m": -0.0001, "transport_min_hub_m": 0.0, "endlage_m": [0.55, 0.35, 0.215]},
     ["nicht_gegriffen", "nicht_am_ziel"]),
    ({"transport_min_hub_m": -0.05, "endlage_m": [0.7, 0.33, 0.0375], "kippung_end_grad": 90.0},
     ["gefallen", "gekippt", "nicht_am_ziel"]),
    ({"kippung_end_grad": 12.0}, ["gekippt"]),
    ({"endlage_m": [0.8615, 0.330, 0.215]}, ["nicht_am_ziel"]),
    ({"endlage_m": [0.859, 0.330, 0.215]}, []),
    ({"tisch_durchdringung_max_m": 0.002}, ["kollision_arm_tisch"]),
    ({"finger_durchdringung_max_m": 0.01}, ["durchdringung"]),
    ({"glas_v_max_m_s": 3.0}, ["weggeschossen"]),
    ({"plan_ok": False, "plan_fehler": ["IK"]}, ["planung_fehlgeschlagen"]),
    ({"nan": True}, ["simulation_instabil"]),
    ({"endlage_m": [float("nan")] * 3}, ["simulation_instabil", "gefallen", "nicht_am_ziel"]),
])
def test_bewertung_reasons(sz, aenderung, gruende):
    r = bewertung.bewerte(_messung(**aenderung), sz.bewertung)
    assert r["gruende"] == gruende
    assert r["erfolg"] is (not gruende)
    assert len(r["texte"]) == len(gruende)


def test_zusammenfassung_counts(sz):
    def rec(nr, **kw):
        return {"versuch": {"nr": nr}, "bewertung": bewertung.bewerte(_messung(**kw), sz.bewertung)}
    z = bewertung.zusammenfassung([rec(0), rec(1, kippung_end_grad=20.0), rec(2)])
    assert z["versuche"] == 3 and z["erfolge"] == 2
    assert z["erfolgsquote"] == pytest.approx(2 / 3)
    assert z["fehlergruende"] == {"gekippt": 1}
    assert z["fehlversuche"] == [{"nr": 1, "gruende": ["gekippt"]}]


# --- echter Lauf (Newton) ---------------------------------------------------

def _backend_python() -> str:
    if os.environ.get("RAEUMWERK_RUN_GPU_SMOKE") != "1":
        pytest.skip("RAEUMWERK_RUN_GPU_SMOKE=1 nicht gesetzt (Lauf nur unter dem GPU-Lock)")
    py = os.environ.get("RAEUMWERK_GREIFEN_PYTHON")
    if not py:
        root = os.environ.get("RAEUMWERK_ROOT")
        if not root:
            pytest.skip("weder RAEUMWERK_GREIFEN_PYTHON noch RAEUMWERK_ROOT gesetzt")
        py = str(Path(root) / "venvs" / "isaaclab" / "bin" / "python")
    if not Path(py).exists():
        pytest.skip(f"Python mit Newton fehlt: {py}")
    return py


def _run(art: str, out: Path) -> tuple:
    cmd = [_backend_python(), str(REPO / "scripts" / "demo_greifen.py"), "--art", art, "--out", str(out)]
    if os.environ.get("RAEUMWERK_GREIFEN_DEVICE"):
        cmd += ["--device", os.environ["RAEUMWERK_GREIFEN_DEVICE"]]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    zus = json.loads((out / "zusammenfassung.json").read_text())
    versuch = json.loads((out / "versuch-00.json").read_text())
    return proc, zus, versuch


def test_demo_greifen_backend(tmp_path, sz):
    out = Path(os.environ.get("RAEUMWERK_GREIFEN_OUT", str(tmp_path))) / "demo"
    proc, zus, v = _run("demo", out)
    assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-3000:]
    assert zus["ok"] and zus["zusammenfassung"]["erfolgsquote"] == 1.0
    assert v["erfolg"] and v["gruende"] == []
    assert v["position"]["fehler_xy_m"] <= sz.bewertung["ziel_toleranz_m"]
    assert v["kippung_grad"]["ende"] < sz.bewertung["kippung_max_grad"]
    assert v["messung"]["hub_max_m"] >= 0.095  # 10 cm angehoben
    assert v["dauer"]["ablauf_sim_s"] > 0 and v["dauer"]["wand_sim_s"] > 0
    assert v["messung"]["tisch_durchdringung_max_m"] <= sz.bewertung["tisch_kollision_m"]


def test_negativ_greifen_backend(tmp_path):
    out = Path(os.environ.get("RAEUMWERK_GREIFEN_OUT", str(tmp_path))) / "negativ"
    proc, zus, v = _run("negativ", out)
    assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-3000:]
    assert v["erfolg"] is False
    assert "nicht_gegriffen" in v["gruende"]
