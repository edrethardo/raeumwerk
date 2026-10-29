"""Tests Ausraeumen (ohne GPU; Newton-Laeufe nur mit RAEUMWERK_RUN_NEWTON=1).

Planung, Geometrie, Bewertung, Befund und Video-Renderer ohne Simulator; der
Newton-Lauf (Demo mit einem Glas, Negativtest) startet nur mit Backend.
"""
from __future__ import annotations

import copy
import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from ausraeumen import bewertung, geometrie as ag, konfig  # noqa: E402
from spuelmaschine import geometrie as sg, masse  # noqa: E402

# --- Konfiguration --------------------------------------------------------


def test_every_value_has_source():
    assert masse.ohne_quelle(konfig.roh()) == []


# Korb- und Slotgeometrie festhalten (Review-Luecke: Korb +5 cm liess alle Tests gruen)
KORB_SOLL = {"oberkorb_boden_oben_z_m": 0.420, "oberkorb_rand_oben_z_m": 0.540, "oberkorb_vorne_y_m": 0.410,
             "oberkorb_x_m": [0.0375, 0.5625],
             "slots_m": [[0.45, 0.32, 0.475], [0.45, 0.22, 0.475], [0.33, 0.32, 0.475], [0.33, 0.22, 0.475]],
             "glashalter_oben_z_m": 0.455, "arbeitsplatte_oben_z_m": 0.860}


def korb_abweichungen(sz: sg.Szene, tol: float = 0.001):
    ist = {"oberkorb_boden_oben_z_m": sz.get("oberkorb_boden").oben,
           "oberkorb_rand_oben_z_m": sz.get("oberkorb_rand_vorne").oben,
           "oberkorb_vorne_y_m": float(sz.get("oberkorb_boden").aabb()[1][1]),
           "oberkorb_x_m": [float(v) for v in sz.get("oberkorb_boden").aabb()[:, 0]],
           "slots_m": [[float(v) for v in s] for s in sz.slots],
           "glashalter_oben_z_m": max(k.oben for k in sz.gruppe("glashalter")),
           "arbeitsplatte_oben_z_m": sz.get("arbeitsplatte").oben}
    out = []
    for k, soll in KORB_SOLL.items():
        a, b = np.asarray(ist[k], float), np.asarray(soll, float)
        if a.shape != b.shape or np.any(np.abs(a - b) > tol):
            out.append(f"{k}: ist {ist[k]}, soll {soll}")
    return out


def _szene_mit(aenderung) -> sg.Szene:
    m = copy.deepcopy(masse.load())
    aenderung(m)
    sc = masse.load_szene()
    return sg.baue(m, sc["pose"]["oberkorb_auszug_m"], sc["pose"]["unterkorb_auszug_m"])


def test_korb_und_slotgeometrie_festgehalten():
    assert korb_abweichungen(_szene_mit(lambda m: None)) == []


@pytest.mark.parametrize("schluessel,delta", [("boden_hoehe_m", 0.05), ("boden_hoehe_m", -0.05),
                                              ("wand_hoehe_m", 0.05), ("vorne_eingeschoben_y_m", 0.05),
                                              ("vorne_eingeschoben_y_m", -0.05)])
def test_korbaenderung_faellt_auf(schluessel, delta):
    """Gegenprobe in beide Richtungen: +-5 cm am Korb macht den Geometrietest rot."""
    def aendern(m):
        m["oberkorb"][schluessel] += delta
    assert korb_abweichungen(_szene_mit(aendern))


def test_slotaenderung_faellt_auf():
    def aendern(m):
        m["glashalter"]["reihen_x_m"] = [0.45, 0.28]
    assert any("slots_m" in a for a in korb_abweichungen(_szene_mit(aendern)))


# --- Geometrie --------------------------------------------------------------

def test_ueberlappung_gedrehter_zylinder():
    """Liegender Zylinder (Achse x) gegen Quader: Abstand ueber den Radius, nicht die Laenge."""
    liegend = ag.glas("g", (0.0, 0.0, 0.0), np.array([[0, 0, 1], [0, 1, 0], [-1, 0, 0]], float), 0.0375, 0.11)
    assert abs(liegend.rot[:, 2] @ np.array([1.0, 0, 0])) > 0.999  # Achse entlang x
    unter = sg.quader("q", "x", (-0.2, -0.2, -0.1), (0.2, 0.2, -0.04))   # 2,5 mm unter dem Mantel
    assert ag.ueberlappung(liegend, unter, 0.0) < 0
    assert ag.ueberlappung(liegend, unter, 0.005) > 0
    seitlich = sg.quader("q", "x", (0.06, -0.1, -0.1), (0.2, 0.1, 0.1))  # 5 mm vor der Stirnflaeche
    assert ag.ueberlappung(liegend, seitlich, 0.0) < 0
    assert ag.ueberlappung(liegend, seitlich, 0.006) > 0
    stehend = ag.glas("h", (0.0, 0.08, 0.0), np.eye(3), 0.0375, 0.11)  # Mantelabstand 5 mm
    assert ag.ueberlappung(liegend, stehend, 0.0) < 0


def test_welt_glaeser_kopfueber_und_ziele_aufrecht():
    w = ag.baue(konfig.aufbau(), _cfg().achse7)
    assert len(w.glas_start) == 4 and len(w.glas_ziel) == 4
    for g in w.glas_start:
        assert g.rot[2, 2] == pytest.approx(-1.0)  # Glasboden oben
        assert g.unten == pytest.approx(w.get("oberkorb_boden").oben)
    for z in w.glas_ziel:
        assert z.rot[2, 2] == pytest.approx(1.0)
        assert z.unten == pytest.approx(w.get("arbeitsplatte").oben)
    for zw in w.matten:
        assert zw.unten == pytest.approx(w.get("arbeitsplatte").oben)  # Matte liegt auf der Platte
        for z in w.glas_ziel:
            assert np.hypot(*(z.mitte[:2] - zw.mitte[:2])) > w.glas_r + float(zw.halb[0]) + 0.005
    # je Ablagepunkt die Matte auf derselben Seite des Roboterfusses (Schiene bei x = 0,78)
    x_fuss = float(w.lage.ursprung[0])
    for i, z in enumerate(w.glas_ziel):
        assert (w.matte_fuer(i).mitte[0] - x_fuss) * (z.mitte[0] - x_fuss) > 0


def test_variation_verschiebt_glas_und_korb():
    abw = konfig.abweichung_aus({"glas2_dx_m": 0.005, "glas2_dy_m": -0.004, "korbauszug_delta_m": 0.01,
                                 "glas2_gier_grad": 3.0})
    w0 = ag.baue(konfig.aufbau(), _cfg().achse7)
    w1 = ag.baue(konfig.aufbau(abw), _cfg().achse7)
    d = w1.glas_start[1].mitte - w0.glas_start[1].mitte
    assert d == pytest.approx([0.005, 0.01 - 0.004, 0.0], abs=1e-9)
    assert w1.glas_start[0].mitte[1] - w0.glas_start[0].mitte[1] == pytest.approx(0.01)
    # Glas 2 bleibt mit Versatz frei von den Haltern (2 mm Planungsrand)
    for k in w1.szene.gruppe("glashalter"):
        assert ag.ueberlappung(w1.glas_start[1], k, 0.002) <= 0


def test_klemmbacken_druecken_ins_glas_und_nicht_in_die_finger():
    from ausraeumen.sim_newton import klemmbacken
    w = ag.baue(konfig.aufbau(), _cfg().achse7)
    a = konfig.load()["negativtest"]
    backen = klemmbacken(w, 0, float(a["uebermass_m"]), float(a["backe_hoehe_m"]))
    g = w.glas_start[0]
    for b in backen:
        assert ag.ueberlappung(g, b) == pytest.approx(float(a["uebermass_m"]), abs=1e-6)
        for h in w.szene.gruppe("glashalter"):
            assert ag.ueberlappung(b, h) <= 0
    # Finger schliessen entlang Kuechen-x (Griff von oben): Backen liegen in y davor/dahinter
    assert all(abs(b.mitte[1] - g.mitte[1]) > 0.03 and abs(b.mitte[0] - g.mitte[0]) < 1e-9 for b in backen)


# --- Befund: Umdrehen mit dem Griff von oben ------------------------------

def test_umdrehen_mit_griff_von_oben_stellt_greifer_in_die_platte():
    """Griff von oben am kopfueber stehenden Glas, Glas umgedreht und aufrecht
    abgestellt: der Greiferkoerper laege unter dem Glasboden in der Platte."""
    cfg = _cfg()
    sc = masse.load_szene()
    w = ag.baue(konfig.aufbau(), cfg.achse7)
    g = cfg.greifer
    tcp_ab_rand = float(sc["greifen"]["tcp_ueber_glasrand_m"])
    # aufrecht: Glasboden unten auf der Platte, der TCP liegt (h - 88 mm) ueber dem Boden,
    # der Greifer zeigt nach oben, sein Koerper reicht vom Flansch bis Fingerwurzel nach unten
    platte = w.get("arbeitsplatte")
    tcp_z = platte.oben + (w.glas_h - tcp_ab_rand)
    unten = tcp_z - float(g["tcp_ab_flansch_m"])                       # Flansch
    oben = tcp_z - float(g["tcp_ab_flansch_m"]) + float(g["koerper_laenge_m"])  # Fingerwurzel
    koerper = sg.quader("greifer", "roboter", (0.7 - 0.025, -0.03 - 0.075, unten), (0.7 + 0.025, -0.03 + 0.075, oben))
    tief = ag.ueberlappung(koerper, platte)
    assert oben < platte.oben and tief > 0.005  # Fingerwurzel 8 mm unter der Plattenoberkante


# --- Planung ----------------------------------------------------------------

def _cfg():
    from rebel_model.config import load
    return load()


@pytest.fixture(scope="module")
def plan_ein_glas():
    from ausraeumen.plan import Planer
    from rebel_model.kinematics import Chain
    from rebel_model.urdf_gen import build_urdf
    cfg = _cfg()
    chain = Chain(build_urdf(cfg))
    auf = konfig.aufbau()
    auf.a["ablauf"]["zuordnung"] = auf.a["ablauf"]["zuordnung"][:1]
    w = ag.baue(auf, cfg.achse7)
    p = Planer(w, cfg, chain)
    plan, gps = p.plane()
    return p, plan, gps, w, chain


def test_plan_phasen_in_reihenfolge(plan_ein_glas):
    p, plan, gps, w, chain = plan_ein_glas
    namen = [s.phase.split(":", 1)[-1] for s in plan.segmente]
    reihe = ["runter_korb", "greifen_korb", "aushub", "absetzen_zw", "loesen_zw", "hoch_zw", "zu_seite",
             "greifen_seite", "anheben", "umdrehen", "absetzen", "loesen", "rueckzug"]
    pos = [namen.index(n) for n in reihe]
    assert pos == sorted(pos)
    assert namen[0] == "start" and namen[-1] == "nachlauf"
    assert gps[0].t0 > 0 and gps[0].t1 < plan.dauer


def test_plan_umdrehen_nur_gelenk6_um_180_grad(plan_ein_glas):
    p, plan, gps, w, chain = plan_ein_glas
    seg = [s for s in plan.segmente if s.phase.endswith("umdrehen")][0]
    d = seg.wege[-1] - seg.wege[0]
    i6 = chain.index["joint6"]
    assert abs(abs(d[i6]) - math.pi) < 1e-9
    assert np.max(np.abs(np.delete(d, i6))) < 1e-12
    assert chain.within_limits(seg.wege[0]) and chain.within_limits(seg.wege[-1])


def test_plan_glas_steht_nach_dem_umdrehen_aufrecht(plan_ein_glas):
    """Modell des Griffs: Glasachse vor dem Umdrehen nach unten (kopfueber), danach nach oben."""
    from ausraeumen.plan import Halt
    p, plan, gps, w, chain = plan_ein_glas
    seg_g = [s for s in plan.segmente if s.phase.endswith("zu_seite")][0]
    q_g = seg_g.wege[-1]
    glas_zw = w.glas_auf_zwischenablage(gps[0].slot)
    halt = Halt(0, p._mitte_tcp(q_g, glas_zw.mitte), p._rot_tcp(q_g, glas_zw.rot))
    seg = [s for s in plan.segmente if s.phase.endswith("umdrehen")][0]
    vor = halt.koerper(p.tcp_welt(seg.wege[0]), w.glas_r, w.glas_h)
    nach = halt.koerper(p.tcp_welt(seg.wege[-1]), w.glas_r, w.glas_h)
    assert vor.rot[2, 2] < -0.999 and nach.rot[2, 2] > 0.999
    ab = [s for s in plan.segmente if s.phase.endswith(":absetzen")][0]
    ende = halt.koerper(p.tcp_welt(ab.wege[-1]), w.glas_r, w.glas_h)
    ziel = w.glas_ziel[gps[0].ablage]
    assert np.hypot(*(ende.mitte[:2] - ziel.mitte[:2])) < 1e-4
    assert ende.unten - ziel.unten == pytest.approx(0.002, abs=1e-4)


def test_plan_dicht_abgetastet_kollisionsfrei(plan_ein_glas):
    """Unabhaengige Nachpruefung: Soll-Trajektorie alle 50 ms gegen die statische
    Szene (Roboter, 5 mm Rand) und auf Gelenkgrenzen."""
    from ausraeumen.plan import Lagezustand
    p, plan, gps, w, chain = plan_ein_glas
    z = Lagezustand([])
    treffer = set()
    for t in np.arange(0.0, plan.dauer, 0.05):
        q, qd, ph = plan.sample(float(t))
        assert chain.within_limits(q, 1e-6)
        for h in p.treffer(q, z):
            if "glas" not in h and "getragen" not in h:
                treffer.add(f"{ph}:{h}")
    assert not treffer, sorted(treffer)[:5]


def test_plan_getragenes_glas_neigt_sich_kaum(plan_ein_glas):
    """Bei den Fahrten mit Glas in der Hand bleibt die Glasachse nahe der Senkrechten
    (kopfueber zur Zwischenablage, aufrecht zur Ablage); nur das Umdrehen kippt es."""
    from ausraeumen.plan import Halt
    p, plan, gps, w, chain = plan_ein_glas
    s = gps[0].slot
    q_oben = [x for x in plan.segmente if x.phase.endswith("runter_korb")][0].wege[-1]
    g0 = w.glas_start[s]
    halt1 = Halt(s, p._mitte_tcp(q_oben, g0.mitte), p._rot_tcp(q_oben, g0.rot))
    q_seite = [x for x in plan.segmente if x.phase.endswith("zu_seite")][0].wege[-1]
    gz = w.glas_auf_zwischenablage(s)
    halt2 = Halt(s, p._mitte_tcp(q_seite, gz.mitte), p._rot_tcp(q_seite, gz.rot))
    grenze = konfig.load()["planung"]["glas_kipp_max_grad"]
    for name, halt, ref in (("zur_zwischenablage", halt1, -1.0), ("zur_ablage", halt2, 1.0)):
        segs = [x for x in plan.segmente if x.phase.endswith(name)]
        assert segs
        for sgm in segs:
            for t in np.linspace(sgm.t0, sgm.t0 + sgm.dauer, 40):
                q = plan.sample(float(t))[0]
                rz = halt.koerper(p.tcp_welt(q), w.glas_r, w.glas_h).rot[2, 2]
                assert math.degrees(math.acos(min(1.0, ref * rz))) <= grenze + 0.5, (name, t)


def test_plan_geschwindigkeit_in_grenzen(plan_ein_glas):
    p, plan, gps, w, chain = plan_ein_glas
    ts = np.arange(0.0, plan.dauer, 0.004)
    v = np.max(np.abs(np.array([plan.sample(float(t))[1] for t in ts])), axis=0)
    assert np.all(v <= p.vmax * 1.001)


# --- Bewertung --------------------------------------------------------------

class _Plan:
    def __init__(self, zeiten):
        self._z = zeiten

    def phase_zeiten(self):
        return self._z


def _messung(w, aendern=None):
    """Synthetische Messung fuer Glas 1 (Slot 1 -> Ablage 3): alles in Ordnung."""
    from ausraeumen.plan import GlasPlan
    zeiten = {"1:greifen_korb": (1.0, 2.0), "1:aushub": (2.0, 3.0), "1:loesen_zw": (4.0, 5.0),
              "1:greifen_seite": (6.0, 7.0), "1:loesen": (9.0, 10.0)}
    gp = GlasPlan(0, 0, 2, t0=0.5, t1=11.0)
    t = np.arange(0.0, 12.0, 0.01)
    n = len(t)
    G = np.zeros((n, 4, 7))
    for j, g in enumerate(w.glas_start):
        G[:, j, :3] = g.mitte
        G[:, j, 3:7] = (1.0, 0.0, 0.0, 0.0)  # kopfueber
    tcp = np.zeros((n, 3))
    start, ziel = w.glas_start[0].mitte, w.glas_ziel[2].mitte
    for i, tt in enumerate(t):
        if tt < 2.0:
            p = start
        elif tt < 3.0:
            p = start + [0, 0, 0.15 * (tt - 2.0)]
        elif tt < 9.0:
            p = start + [0, 0, 0.15] + (ziel - start - [0, 0, 0.15]) * (tt - 3.0) / 6.0
        else:
            p = ziel
        G[i, 0, :3] = p
        if tt >= 8.0:
            G[i, 0, 3:7] = (0.0, 0.0, 0.0, 1.0)  # aufrecht
        tcp[i] = p + [0, 0, 0.03]
    mess = {"t": t, "phase": ["x"] * n, "glas": G, "tcp": tcp, "kontakt": [dict() for _ in range(5)],
            "finger_durchdringung_m": [0.0015, 0, 0, 0], "nan": False, "dt": 0.002}
    if aendern:
        aendern(mess, G, t)
    return _Plan(zeiten), [gp], mess


def _gr():
    return konfig.load()["bewertung"]


def test_bewertung_erfolg():
    w = ag.baue(konfig.aufbau(), _cfg().achse7)
    pl, gps, mess = _messung(w)
    b = bewertung.bewerte(pl, gps, w, mess, _gr())
    g = b["glaeser"][0]
    assert b["erfolg"] and g["gruende"] == []
    assert g["werte"]["kippung_start_grad"] == pytest.approx(180.0)
    assert g["werte"]["kippung_end_grad"] == pytest.approx(0.0, abs=1e-6)


def _klemmen(mess, G, t):
    G[:, 0, :3] = G[0, 0, :3]


def _kippen(mess, G, t):
    G[t >= 8.0, 0, 3:7] = (math.sin(math.radians(6.0)), 0.0, 0.0, math.cos(math.radians(6.0)))  # 12 Grad


def _daneben(mess, G, t):
    G[:, 0, 0] += 0.012 * np.clip(t - 8.0, 0.0, 1.0)  # langsam 12 mm daneben (kein Sprung)


def _tuer(mess, G, t):
    mess["kontakt"][0]["tuer"] = (0.0004, "1:zur_ablage")


def _korb(mess, G, t):
    mess["kontakt"][0]["korb"] = (0.002, "1:aushub")


def _nachbar(mess, G, t):
    G[:, 1, 1] += 0.006 * np.clip(t - 5.0, 0.0, 1.0)


def _verloren(mess, G, t):
    # rutscht zwischen Aushub und Zwischenablage 5 cm in der Hand ab (konstruiert)
    G[:, 0, 2] -= 0.05 * np.clip((t - 3.2) / 0.5, 0.0, 1.0) * (t < 4.0)


@pytest.mark.parametrize("aendern,gruende", [
    (_klemmen, ["nicht_aus_dem_korb", "gefallen", "nicht_am_ziel"]),
    (_kippen, ["gekippt"]),
    (_daneben, ["nicht_am_ziel"]),
    (_tuer, ["kontakt_tuer"]),
    (_korb, ["kontakt_korb"]),
    (_nachbar, ["nachbar_verschoben"]),
    (_verloren, ["gefallen", "weggeschossen"]),
])
def test_bewertung_gruende(aendern, gruende):
    w = ag.baue(konfig.aufbau(), _cfg().achse7)
    pl, gps, mess = _messung(w, aendern)
    b = bewertung.bewerte(pl, gps, w, mess, _gr())
    assert b["glaeser"][0]["gruende"] == gruende
    assert not b["erfolg"]


def test_zusammenfassung_je_glas():
    def v(nr, ok1, ok2):
        return {"versuch": {"nr": nr}, "bewertung": bewertung.gesamt([
            {"glas": "glas_1", "erfolg": ok1, "gruende": [] if ok1 else ["gekippt"], "werte": {"zielfehler_xy_m": 0.001,
                                                                                            "kippung_end_grad": 0.5}},
            {"glas": "glas_2", "erfolg": ok2, "gruende": [] if ok2 else ["nicht_am_ziel"], "werte": {}}])}
    z = bewertung.zusammenfassung([v(0, True, True), v(1, False, True), v(2, True, False)])
    assert z["versuche"] == 3 and z["alle_4_erfolg"] == 1
    assert z["je_glas"]["glas_1"]["erfolgsquote"] == pytest.approx(2 / 3)
    assert z["fehlergruende"] == {"gekippt": 1, "nicht_am_ziel": 1}
    assert [f["nr"] for f in z["fehlversuche"]] == [1, 2]


def test_planfehler_bericht():
    b = bewertung.planfehler([[1, 3], [2, 4]], "IK ohne Loesung")
    assert not b["erfolg"] and b["gruende"] == ["planung_fehlgeschlagen"] and b["glaeser_n"] == 2


# --- raeumwerk run (Backend ausraeumen) -------------------------------------

def test_experiment_ausraeumen_laedt_und_hasht():
    from raeumwerk import experiment as ex
    e = ex.laden(REPO / "experimente" / "ausraeumen_variation.yaml")
    assert e.backend == "ausraeumen" and e.versuche >= 10
    liste = ex.versuchsliste(e)
    for v in liste:
        p = v["parameter"]
        assert all(abs(p[f"glas{i}_{a}_m"]) <= 0.005 for i in range(1, 5) for a in ("dx", "dy"))
        assert all(abs(p[f"glas{i}_gier_grad"]) <= 3.0 for i in range(1, 5))
        assert abs(p["korbauszug_delta_m"]) <= 0.01
    _, dateien = ex.konfig_hash(e)
    assert {"szene", "roboter", "spuelmaschine", "scene_spuelmaschine"} <= set(dateien)
    assert ex.standardwerte_fuer(e)["korbauszug_delta_m"] == 0.0
    with pytest.raises(ex.ExperimentFehler):
        ex.aus_dict(dict(e.als_dict(), parameter={"greifkraft_n": 5.0}))


def test_fuer_run_datensatz():
    from ausraeumen import ablauf
    rec = {"erfolg": False, "versuch": {"nr": 3}, "bewertung": bewertung.gesamt([
        {"glas": "glas_1", "erfolg": True, "gruende": [], "werte": {"zielfehler_xy_m": 0.002, "kippung_end_grad": 0.3},
         "kriterien": {"durchdringung": {"wert": 0.0017}, "weggeschossen": {"wert": 0.2}}},
        {"glas": "glas_2", "erfolg": False, "gruende": ["gekippt"], "werte": {"zielfehler_xy_m": 0.004,
                                                                            "kippung_end_grad": 15.0},
         "kriterien": {"durchdringung": {"wert": 0.001}, "weggeschossen": {"wert": 0.3}}}])}
    r = ablauf.fuer_run(rec, {"korbauszug_delta_m": 0.01})
    assert r["gruende"] == ["glas_2:gekippt"] and r["erfolge_glaeser"] == 1
    assert r["position"]["fehler_xy_m"] == pytest.approx(0.004)
    assert r["kippung_grad"]["ende"] == pytest.approx(15.0)
    assert r["messung"]["finger_durchdringung_max_m"] == pytest.approx(0.0017)


# --- Video ------------------------------------------------------------------

def test_render_ausraeumen_kleines_mp4(tmp_path):
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg fehlt")
    pytest.importorskip("matplotlib")
    from greifen.aufzeichnung import Aufzeichner
    from rebel_model.urdf_gen import build_urdf
    sys.path.insert(0, str(REPO / "scripts"))
    import render_ausraeumen as ra
    from rebel_model.kinematics import Chain

    cfg = _cfg()
    urdf = build_urdf(cfg)
    chain = Chain(urdf)
    w = ag.baue(konfig.aufbau(), cfg.achse7)
    T = w.lage.matrix()
    from spuelmaschine.stabilitaet import quat_aus_matrix
    labels = list(chain.links) + [g.name for g in w.glas_start]
    rec = Aufzeichner(0.002, 10.0)
    q = chain.zero()
    poses = chain.fk_all(q)
    for k in range(6):
        bq = []
        for name in chain.links:
            M = T @ poses[name]
            bq.append(list(M[:3, 3]) + list(quat_aus_matrix(M[:3, :3])))
        for g in w.glas_start:
            bq.append(list(g.mitte + [0, 0, 0.01 * k]) + [1.0, 0.0, 0.0, 0.0])
        rec.add(k * 0.1, bq, "1:aushub" if k < 3 else "1:umdrehen")
    meta = {"szene": "spuelmaschine", "glas_radius_m": w.glas_r, "glas_hoehe_m": w.glas_h,
            "statisch": [{"name": k.name, "gruppe": k.gruppe, "mitte": k.mitte.tolist(), "halb": k.halb.tolist(),
                          "rot": k.rot.tolist()} for k in w.statisch if k.name != "boden"],
            "ablage_m": [g.mitte.tolist() for g in w.glas_ziel], "erfolg": True, "erfolge": 4,
            "glaeser": [{"glas": "glas_1", "erfolg": True, "gruende": [], "zielfehler_xy_m": 0.001,
                         "kippung_end_grad": 0.2}]}
    pfad = rec.speichern(tmp_path / "a.npz", labels, meta)
    from greifen.aufzeichnung import laden
    out = tmp_path / "v.mp4"
    info = ra.rendern(laden(pfad), urdf, out, breite=320, hoehe=180, fps=10, tempo=1.0, halten=0.2,
                      standbild=tmp_path / "s.png", jobs=1)
    assert out.stat().st_size > 1000 and (tmp_path / "s.png").exists()
    assert info["bilder"] == 6 + 2
    if shutil.which("ffprobe"):
        p = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=codec_name,pix_fmt", "-of", "json", str(out)], capture_output=True, text=True)
        s = json.loads(p.stdout)["streams"][0]
        assert s["codec_name"] == "h264" and s["pix_fmt"] == "yuv420p"
    assert "Glas 1/4" in ra.phase_text("1:umdrehen", 4) and "Umdrehen" in ra.phase_text("1:umdrehen", 4)


# --- Newton (nur mit Backend) -----------------------------------------------

def _newton_python() -> str:
    py = os.environ.get("RAEUMWERK_NEWTON_PYTHON")
    if not os.environ.get("RAEUMWERK_RUN_NEWTON") or not py:
        pytest.skip("Newton-Lauf nur mit RAEUMWERK_RUN_NEWTON=1 und RAEUMWERK_NEWTON_PYTHON")
    return py


def _demo(tmp_path, art, *extra):
    py = _newton_python()
    r = subprocess.run([py, str(REPO / "scripts" / "demo_ausraeumen.py"), "--art", art, "--out", str(tmp_path),
                        "--device", os.environ.get("RAEUMWERK_DEVICE", "cpu"), *extra],
                       capture_output=True, text=True, timeout=3600)
    return r.returncode, json.loads((tmp_path / "versuch-00.json").read_text())


def test_newton_ein_glas_umdrehen(tmp_path):
    rc, rec = _demo(tmp_path, "demo", "--glaeser", "1")
    g = rec["bewertung"]["glaeser"][0]
    assert rc == 0 and g["erfolg"], g["gruende"]
    assert g["werte"]["kippung_start_grad"] > 170 and g["werte"]["kippung_end_grad"] < 10
    assert g["werte"]["zielfehler_xy_m"] <= 0.01


def test_newton_negativ_verklemmt(tmp_path):
    rc, rec = _demo(tmp_path, "negativ", "--glaeser", "1")
    g = rec["bewertung"]["glaeser"][0]
    assert rc == 0 and not g["erfolg"] and "nicht_aus_dem_korb" in g["gruende"]
