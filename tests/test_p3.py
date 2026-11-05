"""Kameratag P3: Szenen, Maskenschalter in der Griffpose, Bewertung der Erkennung (ohne Isaac Sim)."""
from __future__ import annotations

import json

import numpy as np
import pytest

from wahrnehmung import erkennung as E
from wahrnehmung import griffpose as WG
from wahrnehmung import p3_szenen as P3
from wahrnehmung.sensor import Fehlermodell, aufnehmen
from wahrnehmung.strahlen import ENSENSO, Kamera


# --- Szenen --------------------------------------------------------------------------------------

def test_plan_ist_ausgewogen():
    p = P3.plan("ober", 3)
    assert len(p) == 36 and len({s["id"] for s in p}) == 36
    zellen = {(s["licht"], s["auszug_m"], s["nass"]) for s in p}
    assert len(zellen) == 12
    assert all(sum(1 for s in p if (s["licht"], s["auszug_m"], s["nass"]) == z) == 3 for z in zellen)


@pytest.mark.parametrize("korb", ["ober", "unter"])
def test_szene_reproduzierbar_und_serialisierbar(korb):
    spec = P3.plan(korb, 1)[3]
    a, b = P3.baue_szene(spec), P3.baue_szene(spec)
    assert json.dumps(a) == json.dumps(b)
    assert a["objekte"] and {o["klasse"] for o in a["objekte"]} <= {"glas", "teller"}
    prims = P3.prims_aus_szene(json.loads(json.dumps(a)))
    assert {o["name"] for o in a["objekte"]} <= {p.objekt for p in prims}
    # Auszug: nur der gewaehlte Korb ist ausgezogen
    assert (a["auszug_ober_m"], a["auszug_unter_m"]) == ((spec["auszug_m"], 0.0) if korb == "ober" else (0.0, spec["auszug_m"]))


def test_unterkorb_hat_essteller():
    d = P3.baue_szene({**P3.plan("unter", 1)[0], "layout": "ess_dessert"})
    assert {o["unterklasse"] for o in d["objekte"]} >= {"essteller"}


def test_szene_liegt_im_betriebsabstand_der_station():
    d = P3.baue_szene(P3.plan("ober", 1)[2])
    cam = WG.ensenso(skala=4.0)
    for o in d["objekte"]:
        z = ((np.asarray(o["mitte"]) - cam.C) @ cam.R)[2]
        assert ENSENSO["dmin"] <= z <= ENSENSO["dmax"], (o["name"], z)


def test_aufnahme_zeigt_objekte():
    d = P3.baue_szene(P3.plan("ober", 1)[0])
    auf = aufnehmen(P3.prims_aus_szene(d), WG.ensenso(skala=4.0), np.random.default_rng(0), Fehlermodell())
    sicht = [int(auf.maske_wahr(o["name"]).sum()) for o in d["objekte"]]
    assert sum(1 for s in sicht if s > 300) >= 0.7 * len(sicht)


# --- Maskenschalter in griffpose.schaetzen ------------------------------------------------------------

KOPF = np.diag([1.0, -1.0, -1.0])


def _welt():
    from types import SimpleNamespace as NS

    def k(name, gruppe, mitte, halb, rot=np.eye(3)):
        return NS(name=name, gruppe=gruppe, mitte=np.asarray(mitte, float), halb=np.asarray(halb, float), rot=rot)
    stat = [k("korbboden", "oberkorb", (0.3, 0.2, 0.495), (0.3, 0.3, 0.005))]
    gl = [k("glas_1", "glas", (0.30, 0.20, 0.555), (0.0375, 0.0375, 0.055), KOPF),
          k("glas_2", "glas", (0.385, 0.20, 0.555), (0.0375, 0.0375, 0.055), KOPF)]
    return NS(statisch_ohne_teller=stat, glas_start=gl, teller=[], aufbau=NS(abw=NS(korbauszug_delta_m=0.0)))


def _nenn(d):
    return {"mitte": np.array([0.30, 0.20 + d, 0.555]), "rot": KOPF, "halb": np.array([0.0375, 0.0375, 0.055])}


def _kw():
    return dict(seed=1, skala_ensenso=2.0, skala_d405=1.5)


def test_schalter_wahre_maske_ist_standard():
    est = WG.schaetzen("glas", _welt(), 0, _nenn, **_kw())
    assert est["maske_quelle"] == "wahr" and est["ok"], est["gruende"]


def test_schalter_externe_synthetische_maske():
    """Synthetische Maske (Strahlschnitt, volles Raster der Ensenso) statt maske_wahr: Pose bleibt gut."""
    w = _welt()
    prims = WG.prims_aus_welt(w, "glas")
    cam = WG.ensenso(1.0)          # volle Aufloesung 2472 x 2064; die Griffpose rechnet bei Skala 2
    auf = aufnehmen(prims, cam, np.random.default_rng(0), Fehlermodell(glas_an=False), roi=(np.array([0.30, 0.20, 0.555]), 0.16))
    maske = auf.maske_wahr("glas_1")
    assert maske.shape == (2064, 2472)
    est = WG.schaetzen("glas", w, 0, _nenn, maske_ensenso=maske, **_kw())
    assert est["maske_quelle"] == "extern"
    assert est["ensenso"]["maske_px"] > 100
    assert est["ensenso"]["fehler_mm"] < 6.0, est["ensenso"]


def test_schalter_leere_maske_bricht_ab():
    est = WG.schaetzen("glas", _welt(), 0, _nenn, maske_ensenso=np.zeros((2064, 2472), bool), **_kw())
    assert est["ok"] is False and "ensenso:keine_erkennung" in est["gruende"]


def test_maske_auf_raster_nachbarpixel():
    m = np.zeros((8, 8), bool)
    m[2:6, 2:6] = True
    k = WG.maske_auf_raster(m, (4, 4))
    assert k.shape == (4, 4) and k[1:3, 1:3].all() and not k[0].any()
    assert WG.maske_auf_raster(m, (8, 8)) is not None


# --- Bewertung ------------------------------------------------------------------------------------------

def _scheibe(h, w, cy, cx, r):
    y, x = np.ogrid[:h, :w]
    return (y - cy) ** 2 + (x - cx) ** 2 <= r * r


def test_bewerten_treffer_nachbar_verpasst_fehldetektion():
    h, w = 120, 260
    a, b, c, d = (_scheibe(h, w, 40, x, 16) for x in (30, 66, 130, 200))
    inst = np.zeros((h, w), np.uint16)
    for i, m in enumerate((a, b, c, d), 1):
        inst[m] = i
    namen = ["glas_1", "glas_2", "teller_1", "teller_2"]
    klassen = {"glas_1": "glas", "glas_2": "glas", "teller_1": "teller", "teller_2": "teller"}
    erk = [
        {"maske": a | b, "klasse": "glas", "score": 0.9},                 # verschmilzt glas_1 + glas_2
        {"maske": c, "klasse": "glas", "score": 0.9},                      # teller_1 mit falscher Klasse
        {"maske": _scheibe(h, w, 100, 100, 8), "klasse": "teller", "score": 0.8},   # Fehldetektion
        {"maske": d, "klasse": "teller", "score": 0.3},                    # unter der Schwelle
    ]
    r = E.bewerten(inst, namen, klassen, erk, schwelle=0.5, min_px=100)
    o = r["objekte"]
    assert o["glas_1"]["nachbar"] and o["glas_2"]["nachbar"] and not o["glas_1"]["treffer"]
    assert o["teller_1"]["klassenfehler"] and not o["teller_1"]["treffer"] and o["teller_1"]["klassenfrei"]
    assert o["teller_2"]["verpasst"]
    assert len(r["fehldetektionen"]) == 1 and r["n_erkennungen"] == 3


def test_bewerten_exakter_treffer_iou_eins():
    h, w = 80, 80
    m = _scheibe(h, w, 40, 40, 15)
    inst = m.astype(np.uint16)
    r = E.bewerten(inst, ["glas_1"], {"glas_1": "glas"}, [{"maske": m, "klasse": "glas", "score": 0.99}], min_px=100)
    assert r["objekte"]["glas_1"]["treffer"] and r["objekte"]["glas_1"]["iou"] == pytest.approx(1.0)


def test_erk_ablage_rundlauf(tmp_path):
    h, w = 90, 100
    m = _scheibe(h, w, 40, 50, 12)
    E.erk_speichern(tmp_path / "x.npz", [{"maske": m, "klasse": "glas", "score": 0.7, "coco": 46}], (10, 20, 90, 80), (h, w))
    e = E.erk_laden(tmp_path / "x.npz")
    assert len(e) == 1 and e[0]["klasse"] == "glas" and e[0]["coco"] == 46
    assert (e[0]["maske"] == m).all()


def test_baseline_findet_ellipsen():
    cv2 = pytest.importorskip("cv2")
    cam = WG.ensenso(skala=1.0)
    d = P3.baue_szene({**P3.plan("ober", 1)[0], "layout": "glas"})
    vor = E.vorlagen_aus_szene(d, cam)
    # Testbild: Glasdeckel-Umriss und Dessertteller-Umriss als dunkle Linien auf hellem Grund
    img = np.full((2064, 2472, 3), 210, np.uint8)
    for poly, c in ((vor["glas"]["lid"], (900.0, 800.0)), (vor["teller"]["dessert"], (1500.0, 1100.0))):
        cv2.polylines(img, [np.round(poly + c).astype(np.int32)], True, (30, 30, 30), 5)
    erk = E.baseline(img, (400, 300, 2200, 1700), vor)
    best = {k: max((e for e in erk if e["klasse"] == k), key=lambda e: e["score"], default=None) for k in ("glas", "teller")}
    assert best["glas"] is not None and best["teller"] is not None
    ys, xs = np.nonzero(best["glas"]["maske"])
    assert abs(xs.mean() - (900.0 + vor["glas"]["versatz"][0] / 2)) < 40
    ys, xs = np.nonzero(best["teller"]["maske"])
    assert abs(xs.mean() - 1500.0) < 30 and abs(ys.mean() - 1100.0) < 30
