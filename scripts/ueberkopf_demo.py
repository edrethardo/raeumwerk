#!/usr/bin/env python3
"""Physik-Demo: Roboter kopfueber an der senkrechten Hubachse (0,45 m vor der Front, 30 Grad zur
Maschine), Oberkorb (Glas, Teller) und danach Unterkorb (Teller), je Objekt ein Newton-Lauf.
Doku: ``docs/ueberkopf-demo.md``; Werte: ``config/ueberkopf_demo.yaml``.

    ueberkopf_demo.py --objekt glas|teller_ot|teller_ut --out DIR [--ziel N] [--seed S]
                      [--device cpu|cuda] [--aufzeichnen X.npz] [--nur-plan]

Szene: Aufbau ``beispiele/ueberkopf-045-demo.yaml`` (Hubachse als geregeltes Schubgelenk, der Arm
haengt am Schlitten). Oberkorb wie ``griff_lauf.py`` (8 Glaeser kopfueber, 6 Dessertteller), vom
Menschen 0,45 m ausgezogen; Unterkorb mit einer Reihe 26-cm-Teller, Oberkorb dann eingeschoben.
Abgelegt wird auf einem Wagen rechts neben der offenen Tuer: Glas ueber eine Matte umgegriffen und
aufrecht abgestellt, Teller hochkant in einen kleinen Staender. Was schon abgeraeumt ist, steht in
den folgenden Laeufen statisch auf dem Wagen. Griffposen aus der Wahrheit (keine Wahrnehmung).
Jeder Lauf beginnt und endet in derselben Parkpose; die Hubachse faehrt in der Anfahrt auf
Korbhoehe. Ausgabe: DIR/versuch.json (Plan, Bewertung, J2 je Phase) und Zeilen PLAN, ERGEBNIS, J2.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import sys
import time
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import numpy as np  # noqa: E402
import yaml  # noqa: E402

import griff_lauf as GL  # noqa: E402
from ausraeumen import geometrie as ag  # noqa: E402
from ausraeumen import konfig  # noqa: E402
from finger import a1  # noqa: E402
from finger.parameter import Finger  # noqa: E402
from finger.tellergriff import varianten as TV  # noqa: E402
from spuelmaschine import aufbau as AU  # noqa: E402
from spuelmaschine import geometrie as sg  # noqa: E402
from spuelmaschine.erreichbarkeit import r_greif, rz  # noqa: E402

DEMO = REPO / "config" / "ueberkopf_demo.yaml"
OBJEKTE = ("glas", "teller_ot", "teller_ut")
AUSZUG_M = 0.45
STAENDER_PLAETZE = 2          # Platz 1: Oberkorb-Teller, Platz 2: Unterkorb-Teller
# Phasen, in denen das Objekt in der Hand liegt (fuer die Last im J2-Moment; Greifen/Loesen
# zaehlen mit Last, also eher zu hoch)
HAND = {"greifen_korb", "aushub", "zur_zwischenablage", "absetzen_zw", "loesen_zw", "greifen_seite", "anheben",
        "umdrehen", "zur_ablage", "absetzen", "loesen"}


def demo_werte(path=None):
    return yaml.safe_load(Path(path or DEMO).read_text())


def korb_von(objekt):
    return "unterkorb" if objekt == "teller_ut" else "oberkorb"


def szenario_und_aufbau(objekt, variante=GL.TELLER_VARIANTE, ziel=None, D=None):
    """Demo-Werte, Tellergriff-Variante (Teller), Finger, Szenario und Aufbau fuer ein Objekt."""
    D = D or demo_werte()
    art = "glas" if objekt == "glas" else "teller"
    var = TV.laden()[variante] if art == "teller" and variante else None
    f = Finger.laden(**(var.finger if var else {}))
    sz = a1.szenario()
    sz["aufbau"] = D["aufbau"]
    sz["glaeser"]["slots"] = list(GL.GLAS_SLOTS)
    sz["glaeser"].update(copy.deepcopy(D["glaeser"]))
    sz["glaeser"]["zuordnung"] = [[ziel or 3, 1]]
    sz["zwischenposen_m"] = []
    t = sz["teller"]
    for k in ("staender_xy_m", "staender_teilung_m", "staender_gier_grad"):
        t[k] = copy.deepcopy(D["staender"][k])
    if objekt == "teller_ut":
        u = D["teller_ut"]
        t.update(durchmesser_m=float(u["durchmesser_m"]), masse_kg=float(u["masse_kg"]), aushub_m=float(u["aushub_m"]))
    if var is not None:
        sz["greifer"]["finger_breite_m"] = max(float(sz["greifer"]["finger_breite_m"]), var.breite_m())
        t["greifkraft_n"] = var.greifkraft_n
    t["zuordnung"] = [[ziel or 1, int(D["staender"]["platz_ut" if objekt == "teller_ut" else "platz_ot"])]]
    A = a1.aufbau(sz, f)
    achse_reserve(A, float(D.get("achse_reserve_m", 0.0)))
    return D, var, f, sz, A


def achse_reserve(A, m):
    """Planung haelt die Hubachse ``m`` unter dem oberen Anschlag (Newton behaelt den vollen Hub): am
    Anschlag ruckte der Schlitten im Newton-Lauf, und der Teller fiel am Ende des Aushubs aus der Hand."""
    if m <= 0:
        return
    j7 = A.chain.by_name["axis7"]
    j7.upper = float(j7.upper) - m
    i7 = A.chain.index["axis7"]
    A.chain.upper[i7] = j7.upper


def abweichung(objekt, seed, D):
    """Wie ``griff_lauf.abweichung``; Unterkorb mit so vielen Tellern wie die Reihe hat."""
    abw, tabw = GL.abweichung("glas" if objekt == "glas" else "teller", seed)
    if objekt == "teller_ut":
        n = len(D["teller_ut"]["tiefe_m"])
        if seed is None:
            tabw = {"teller": [(0.0, 0.0, 0.0)] * n}
        else:
            rng = np.random.default_rng(seed + 1000)
            tabw = {"teller": [(float(rng.uniform(-0.005, 0.005)), float(rng.uniform(-0.005, 0.005)),
                                float(rng.uniform(-1.0, 1.0))) for _ in range(n)]}
    return abw, tabw


# --- Welt ------------------------------------------------------------------------------------------

def pruefer(A, abw, korb):
    extra = {"glashalter": {"reihen_x_m": GL.GLAS_REIHEN_X}}
    d = abw.korbauszug_delta_m
    return A.pruefer(AUSZUG_M + d, 0.0, extra) if korb == "oberkorb" else A.pruefer(0.0, AUSZUG_M + d, extra)


def _wagen_als_ablage(statisch):
    """Die Wagenplatte ist die Ablageflaeche: Name ``arbeitsplatte``, damit der Planer das abgestellte
    Glas dort aufsetzen laesst wie auf der Arbeitsplatte (Kontaktgruppe ``arbeitsplatte``)."""
    return [sg.Koerper("arbeitsplatte", k.gruppe, k.form, k.mitte, k.halb, k.rot) if k.name == "wagen_platte" else k
            for k in statisch]


def teller_reihe(p, sz, f, tabw, korb, x, tiefe, delta):
    """Teller hochkant in einer Reihe (Normale y) mit Tellerstaeben und Rollsperre, wie
    ``griff_lauf.teller_liste``, aber fuer beide Koerbe."""
    t = sz["teller"]
    rt = float(t["durchmesser_m"]) / 2.0
    wulst = float(f.p["teller"]["wulst_dicke_mm"]) * 1e-3
    km = p.m[korb]
    boden = km["boden_hoehe_m"]
    vorne = km["vorne_eingeschoben_y_m"] + AUSZUG_M + delta
    teller, halter = [], []
    for k, dy in enumerate(tiefe):
        ex, ey, eg = tabw["teller"][k]
        yk = vorne - float(dy) + ey
        tk = a1.teller_koerper(f"teller_{k + 1}", np.array([x + ex, yk, boden + rt]), rt, wulst)
        teller.append(sg.Koerper(tk.name, "glas", tk.form, tk.mitte, tk.halb, rz(eg) @ tk.rot))
        halter += a1._halter(f"tellerhalter_{k + 1}", "tellerhalter", (x, yk), t, wulst, boden)
        yb = wulst / 2.0 + float(t["halter_luft_m"])
        for j, sx in enumerate((-1.0, 1.0)):
            x0, x1 = sorted((x + sx * 0.030, x + sx * 0.045))
            halter.append(sg.quader(f"tellerhalter_{k + 1}_mulde_{j}", "tellerhalter", (x0, yk - yb, boden),
                                    (x1, yk + yb, boden + 0.003)))
    return teller, halter, rt, wulst


def matten(D, sz):
    zap = float(D["wagen_oberkante_m"])
    za = konfig.load()["zwischenablage"]
    k2, d_m = float(za["kante_m"]) / 2.0, float(za["dicke_m"])
    out = []
    for j, (x, y) in enumerate(sz["glaeser"]["matten_xy_m"]):
        oben = zap + d_m + float(sz["glaeser"]["matte_sockel_m"][j])
        out.append(sg.quader(f"zwischenablage_{j + 1}", "zwischenablage", (x - k2, y - k2, oben - d_m), (x + k2, y + k2, oben)))
    return out


def staender(D, sz, f, rt):
    """Kleiner Tellerstaender auf dem Wagen (Boden + Staebe je Platz) und die Zielkoerper."""
    t = sz["teller"]
    zap = float(D["wagen_oberkante_m"])
    wulst = float(f.p["teller"]["wulst_dicke_mm"]) * 1e-3
    sb = float(t["staender_boden_m"])
    x0, y0 = (float(v) for v in t["staender_xy_m"])
    tx, ty = (float(v) for v in t["staender_teilung_m"])
    plaetze = [(x0 + k * tx, y0 + k * ty) for k in range(STAENDER_PLAETZE)]
    nx = abs(math.cos(math.radians(float(t["staender_gier_grad"])))) > 0.5
    lo = (min(pp[0] for pp in plaetze) - (0.03 if nx else 0.08), min(pp[1] for pp in plaetze) - (0.08 if nx else 0.03), zap)
    hi = (max(pp[0] for pp in plaetze) + (0.03 if nx else 0.08), max(pp[1] for pp in plaetze) + (0.08 if nx else 0.03), zap + sb)
    stat = [sg.quader("tellerstaender_boden", "tellerstaender", lo, hi)]
    ziel = []
    for k, (x, y) in enumerate(plaetze):
        stat += a1._halter(f"tellerstaender_{k + 1}", "tellerstaender", (x, y), t, wulst, zap + sb,
                           float(t["staender_halter_hoehe_m"]), normale_x=nx)
        ziel.append(a1.teller_koerper(f"teller_{k + 1}", (x, y, zap + sb + rt), rt, wulst, normale_x=nx))
    return stat, ziel, nx


def erledigt(D, sz, f, p, objekt):
    """Was in den vorigen Laeufen schon abgelegt wurde, als statische Koerper an der Nennlage:
    Glas aufrecht auf dem Wagen (ab Teller-Oberkorb), Oberkorb-Teller im Staenderplatz 1 (Unterkorb)."""
    out = []
    if objekt == "glas":
        return out
    r, h = p.m["glas"]["durchmesser_m"] / 2.0, p.m["glas"]["hoehe_m"]
    x, y = sz["glaeser"]["ablage_xy_m"][0]
    zap = float(D["wagen_oberkante_m"])
    out.append(sg.Koerper("abgelegt_glas", "glasfest", "quader", np.array([x, y, zap + h / 2.0]), np.array([r, r, h / 2.0]),
                          np.eye(3)))
    if objekt == "teller_ut":
        sz_ot = copy.deepcopy(sz)
        sz_ot["teller"]["durchmesser_m"] = float(a1.szenario()["teller"]["durchmesser_m"])
        _, ziel, _ = staender(D, sz_ot, f, float(sz_ot["teller"]["durchmesser_m"]) / 2.0)
        k = ziel[int(D["staender"]["platz_ot"]) - 1]
        out.append(sg.Koerper("abgelegt_teller_ot", "glasfest", "zylinder", k.mitte, k.halb, k.rot))
    return out


def welt_glas(A, sz, f, abw, tabw, D):
    """Wie ``griff_lauf.welt_glas``: 8 Glaeser frei, Teller statisch; Matte und Ablage auf dem Wagen."""
    p = pruefer(A, abw, "oberkorb")
    a = a1._ausraeum_cfg(sz, f, "glaeser")
    sc = copy.deepcopy(p.sc)
    sc["pose"]["oberkorb_auszug_m"] = AUSZUG_M
    auf = konfig.Aufbau(p.m, sc, a, abw)
    za = a["zwischenablage"]
    za["matten_xy_m"] = [list(v) for v in sz["glaeser"]["matten_xy_m"]]
    za["je_ablage"] = list(sz["glaeser"]["je_ablage"])
    mat = matten(D, sz)
    start, r, h = GL.glas_liste(p, abw)
    zap = float(D["wagen_oberkante_m"])
    ziel = [ag.glas(f"glas_{i + 1}", (float(x), float(y), zap + h / 2.0), np.eye(3), r, h)
            for i, (x, y) in enumerate(sz["glaeser"]["ablage_xy_m"])]
    teller, halter, rt, wulst = teller_reihe(p, sz, f, tabw, "oberkorb", GL.TELLER_X, GL.TELLER_TIEFE,
                                             abw.korbauszug_delta_m)
    st, _, _ = staender(D, sz, f, rt)
    statisch = _wagen_als_ablage(a1._statisch(p)) + mat + halter + st
    w = ag.Welt(auf, A.lage, p.szene, statisch + teller, start, ziel, mat, r, h)
    w.pruefer = p
    w.teller = [sg.Koerper(k.name, "teller", k.form, k.mitte, k.halb, k.rot) for k in teller]
    w.teller_r, w.teller_wulst = rt, wulst
    w.statisch_ohne_teller = statisch
    w.glaeser_statisch = []
    return w


def welt_teller(A, sz, f, abw, tabw, D, objekt, ziel_nr=1):
    """Teller frei, Glaeser (Oberkorb) statisch als Quader; Staender auf dem Wagen. Unterkorb: Oberkorb
    eingeschoben (sein Inhalt fehlt, er liegt ausser Reichweite in der Maschine)."""
    korb = korb_von(objekt)
    t = sz["teller"]
    p = pruefer(A, abw, korb)
    a = a1._ausraeum_cfg(sz, f, "teller")
    sc = copy.deepcopy(p.sc)
    sc["pose"]["oberkorb_auszug_m"] = AUSZUG_M if korb == "oberkorb" else 0.0
    m = copy.deepcopy(p.m)
    m["glas"] = dict(m["glas"], masse_kg=float(t["masse_kg"]))
    auf = konfig.Aufbau(m, sc, a, abw)
    if korb == "oberkorb":
        teller, halter, rt, wulst = teller_reihe(p, sz, f, tabw, korb, GL.TELLER_X, GL.TELLER_TIEFE, abw.korbauszug_delta_m)
        glaeser, gr, gh = GL.glas_liste(p, abw)
        glaeser = [sg.Koerper(k.name.replace("glas_", "glasfest_"), "glasfest", "quader", k.mitte,
                              np.array([gr, gr, gh / 2.0]), np.eye(3)) for i, k in enumerate(glaeser)
                   if i != int(sz["glaeser"]["zuordnung"][0][0]) - 1]          # das Glas steht schon auf dem Wagen
    else:
        u = D["teller_ut"]
        teller, halter, rt, wulst = teller_reihe(p, sz, f, tabw, korb, float(u["spalte_x_m"]), u["tiefe_m"],
                                                 abw.korbauszug_delta_m)
        glaeser = []
    st, ziel, _ = staender(D, sz, f, rt)
    statisch = _wagen_als_ablage(a1._statisch(p)) + halter + glaeser + st + matten(D, sz) + erledigt(D, sz, f, p, objekt)
    w = ag.Welt(auf, A.lage, p.szene, statisch, teller, ziel, [], rt, wulst)
    w.pruefer = p
    w.teller_r, w.teller_wulst = rt, wulst
    w.glaeser_statisch = glaeser
    return w


def welt(A, sz, f, abw, tabw, D, objekt):
    return welt_glas(A, sz, f, abw, tabw, D) if objekt == "glas" else welt_teller(A, sz, f, abw, tabw, D, objekt)


# --- Parkpose, J2 ----------------------------------------------------------------------------------

def parkpose(planer, D):
    """Gelenkwinkel der Parkpose: aus ``park_grad``/``park_achse7_m`` (falls gesetzt), sonst die erste
    kollisionsfreie IK-Loesung fuer ``park_tcp_m`` mit senkrechtem Greifer (fester Seed)."""
    from ausraeumen.plan import Lagezustand
    if D.get("park_grad"):
        return dict(D["park_grad"]), float(D["park_achse7_m"])
    rng = np.random.default_rng(0)
    q0 = planer.chain.zero()
    z = Lagezustand(list(planer.w.glas_start))
    for q in planer.kandidaten(q0, np.asarray(D["park_tcp_m"], float), r_greif(0.0), rng, None):
        q = q.copy()
        q[planer.ifg] = planer.q_offen
        if not planer.treffer(q, z):
            return ({n: round(math.degrees(float(q[planer.chain.index[n]])), 3) for n in AU.ARM},
                    round(float(q[planer.i7]), 4))
    raise RuntimeError("keine Parkpose gefunden")


def setze_park(w, grad, a7):
    w.aufbau.a["ablauf"]["ruhepose_grad"] = dict(grad)
    w.aufbau.a["ablauf"]["ruhepose_achse7_m"] = float(a7)


def phase_ohne_nr(ph):
    return ph.split(":", 1)[-1]


def j2_entlang(plan, p, last_kg, dt=0.05):
    """Schweremoment J2/J3 (Glieder am Schwerpunkt, ``aufbau.schweremomente``) entlang des Plans,
    Last im TCP in den Hand-Phasen; Maximum je Phase und Achsbereich. Kinematisch (Soll-Gelenkwinkel)."""
    i2, i3, i7 = p.chain.index["joint2"], p.chain.index["joint3"], p.chain.index["axis7"]
    je = {}
    a7 = []
    for t in np.arange(0.0, plan.dauer, dt):
        q, _, ph = plan.sample(float(t))
        name = phase_ohne_nr(ph)
        tg = AU.schweremomente(p, q, last_kg if name in HAND else 0.0)
        e = je.setdefault(name, {"j2_max_nm": 0.0, "j3_max_nm": 0.0, "last": name in HAND})
        e["j2_max_nm"] = round(max(e["j2_max_nm"], abs(float(tg[i2]))), 2)
        e["j3_max_nm"] = round(max(e["j3_max_nm"], abs(float(tg[i3]))), 2)
        a7.append(float(q[i7]))
    return {"phasen": je, "j2_max_nm": max(v["j2_max_nm"] for v in je.values()),
            "achse7_m": [round(min(a7), 3), round(max(a7), 3)]}


# --- Hauptablauf -----------------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--objekt", choices=OBJEKTE, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ziel", type=int, default=None, help="Glas: Index in GLAS_SLOTS (Std. 3); Teller: Nr. in der Reihe (Std. 1)")
    ap.add_argument("--variante", default=GL.TELLER_VARIANTE)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--device", default=None)
    ap.add_argument("--aufzeichnen", default=None)
    ap.add_argument("--nur-plan", action="store_true")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    rec = {"args": vars(args), "ok": False, "griffpose": "wahrheit"}
    try:
        from ausraeumen import sim_newton as sn
        objekt = args.objekt
        art = "glas" if objekt == "glas" else "teller"
        ziel = args.ziel or (3 if art == "glas" else 1)
        D, var, f, sz, A = szenario_und_aufbau(objekt, args.variante, ziel)
        abw, tabw = abweichung(objekt, args.seed, D)
        rec["abweichung"] = {"glas": abw.as_dict(), "teller": tabw}
        w = welt(A, sz, f, abw, tabw, D, objekt)
        if art == "glas":
            w.aufbau.a["ablauf"]["zuordnung"] = [[ziel, 1]]
        planer = a1.A1Planer(w, A.cfg, A.chain, sz, f, teller=(art == "teller"), pruefer=w.pruefer)
        grad, a7 = parkpose(planer, D)
        setze_park(w, grad, a7)
        rec["park"] = {"grad": grad, "achse7_m": a7}
        print("PARK", json.dumps(rec["park"]), flush=True)
        tp = time.monotonic()
        plan, gps = planer.plane_teller() if art == "teller" else planer.plane()
        rec["plan"] = {"ok": True, "dauer_s": round(plan.dauer, 3), "wand_s": round(time.monotonic() - tp, 1),
                       "objekte": [{"slot": g.slot + 1, **g.info} for g in gps],
                       "phasen": [[x.phase, round(x.t0, 3), round(x.t0 + x.dauer, 3)] for x in plan.segmente]}
        last = float(sz["teller"]["masse_kg"]) if art == "teller" else float(w.pruefer.m["glas"]["masse_kg"])
        rec["j2"] = j2_entlang(plan, w.pruefer, last)
        print("PLAN ok", rec["plan"]["dauer_s"], "s, wand", rec["plan"]["wand_s"], "s", flush=True)
        print("J2", json.dumps(rec["j2"]), flush=True)
        if args.nur_plan:
            raise SystemExit(0)
        ctx = sn.kontext(args.device)
        rec["device"] = ctx["device"]
        Lauf = GL.GlasLauf if art == "glas" else GL.TellerLauf
        lauf = Lauf(ctx, w, plan, A.cfg, A.chain, a1.urdf_sim(A), 30.0 if args.aufzeichnen else None)
        lauf.finger, lauf.sz = f, sz
        if var is not None:
            lauf.variante = var
        lauf.bauen()
        mess = lauf.fahren()
        gr = w.aufbau.a["bewertung"]
        bew = GL.bewerte_voll(mess, plan, gps, w, art, gr)
        rec.update(erfolg=bew["erfolg"], bewertung=bew, ok=bool(bew["erfolg"]),
                   dauer={"sim_s": round(plan.dauer, 3), "wand_sim_s": round(lauf.wand_s, 1)},
                   modell={"koerper": len(lauf.body_label), "dt_s": mess["dt"]})
        if args.aufzeichnen:
            stat = w.statisch_ohne_teller if art == "glas" else w.statisch
            meta = {"szene": "spuelmaschine", "art": art, "objekt": objekt, "korb": korb_von(objekt), "ziel": ziel - 1,
                    "voll": True, "statisch": [{"name": k.name, "gruppe": k.gruppe, "form": k.form, "mitte": k.mitte,
                                                "halb": k.halb, "rot": k.rot} for k in stat if k.name != "boden"],
                    "objekte": [{"name": k.name, "form": k.form, "halb": k.halb} for k in w.glas_start],
                    "teller_start": [{"name": g.name, "mitte": m_, "rot": R_} for g, (m_, R_) in
                                     zip(w.teller if art == "glas" else w.glas_start, lauf.teller_start)],
                    "teller_r_m": w.teller_r, "teller_wulst_m": w.teller_wulst,
                    "glas_radius_m": float(w.pruefer.m["glas"]["durchmesser_m"]) / 2.0,
                    "glas_hoehe_m": float(w.pruefer.m["glas"]["hoehe_m"]),
                    "auszug_m": {"oberkorb": AUSZUG_M if korb_von(objekt) == "oberkorb" else 0.0,
                                 "unterkorb": AUSZUG_M if korb_von(objekt) == "unterkorb" else 0.0},
                    "variante": args.variante if art == "teller" else None,
                    "phasen_s": [[x.phase, x.t0, x.t0 + x.dauer] for x in plan.segmente],
                    "bewertung": {k: v for k, v in bew.items() if k != "voll"}, "j2": rec["j2"], "park": rec["park"]}
            lauf.aufzeichner.speichern(args.aufzeichnen, lauf.body_label, sn.jsonable(meta))
        rec = sn.jsonable(rec)
    except SystemExit:
        pass
    except Exception:  # noqa: BLE001
        rec["fehler"] = traceback.format_exc()
        print(rec["fehler"], file=sys.stderr, flush=True)
    rec["wand_gesamt_s"] = round(time.monotonic() - t0, 1)
    (out / "versuch.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1, default=str))
    b = rec.get("bewertung", {})
    print("ERGEBNIS", json.dumps({k: b.get(k) for k in ("erfolg", "gruende", "aushub_m", "hand_wanderung_m",
                                                          "zielfehler_xy_m", "kippung_end_grad", "nachbar_max_m",
                                                          "finger_durchdringung_m")}, default=str), flush=True)
    print("LAUF_RESULT", json.dumps({"ok": rec.get("ok"), "wand_s": rec["wand_gesamt_s"], "fehler": "fehler" in rec}),
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
