#!/usr/bin/env python3
"""Griff nach einem Glas bzw. einem Teller im gemischt belegten Oberkorb (Aufbau ohne Ueberstand),
Newton, Griffpose wahlweise aus der Wahrheit oder aus der verrauschten Wahrnehmung (Ensenso + D405).
Doku: ``docs/griff-verrauscht.md``.

Szene: 8 Glaeser kopfueber (Plaetze 1..8, rechte Korbhaelfte), 6 Dessertteller Ø 19 cm hochkant in
der Tellerreihe x 0,15 (Teilung 6 cm, Rollsperren). Geplant wird in der Welt, die die Wahrnehmung
liefert, simuliert in der wahren Welt.

    griff_lauf.py --art glas|teller --out DIR [--ziel N] [--variante NAME] [--seed S]
                  [--wahrnehmung] [--negativ MODUS] [--voll] [--device cpu|cuda]
                  [--aufzeichnen X.npz] [--nur-plan]

--seed     Lageabweichung im Korb (Glas +-5 mm / +-3 Grad, Korb 0..-1 cm; Teller x +-5 mm, Reihe
           y +-5 mm, Gier +-1 Grad) und Rauschseed der Wahrnehmung.
Kurzlauf (Standard): Start ueber dem Objekt, runter, greifen, Aushub; Teller zusaetzlich die erste
Querfahrt zum Staender, dann 1 s halten.
--voll     ganzer Ablauf: Glas Griff -> Aushub -> Umgreifen ueber die Zwischenablage -> Ablage;
           Teller Griff -> Aushub -> Transport -> Ablage im Staender. Bewertung wie
           ``ausraeumen.bewertung.bewerte_glas`` bzw. ``finger.a1.bewerte_teller``.
Glas-Lauf: Teller statisch, Glaeser frei. Teller-Lauf: Glaeser statisch (Quader), Teller frei.
Ausgabe: DIR/versuch.json und die Zeilen WAHRNEHMUNG, PLAN, ERGEBNIS, LAUF_RESULT. Exit 0.
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

import numpy as np  # noqa: E402

from ausraeumen import bewertung as ab  # noqa: E402
from ausraeumen import geometrie as ag  # noqa: E402
from ausraeumen import konfig  # noqa: E402
from finger import a1  # noqa: E402
from finger import sim as fs  # noqa: E402
from finger.parameter import Finger  # noqa: E402
from finger.tellergriff import varianten as TV  # noqa: E402
from spuelmaschine import geometrie as sg  # noqa: E402
from spuelmaschine.erreichbarkeit import rz  # noqa: E402

GLAS_REIHEN_X = [0.48, 0.36]
GLAS_SLOTS = [1, 2, 5, 6, 3, 4, 7, 8]        # Index 3 (1-basiert) = Platz 5
TELLER_X = 0.15
TELLER_TIEFE = [0.07, 0.13, 0.19, 0.25, 0.31, 0.37]
AUFBAU_NEU = "beispiele/auf-maschine-ohne-ueberstand.yaml"
FUSS_ALT = (0.30, 0.00)
TELLER_VARIANTE = "breit_6n"


def auf_neue_lage(sz):
    """Szenario (Ablagen, Zwischenposen, Staender) auf den Fuss des Aufbaus ohne Ueberstand verschieben."""
    import yaml
    sz["aufbau"] = AUFBAU_NEU
    neu = yaml.safe_load((REPO / AUFBAU_NEU).read_text())["roboter"]["ursprung_xyz_m"]
    dx, dy = neu[0] - FUSS_ALT[0], neu[1] - FUSS_ALT[1]
    gl = sz["glaeser"]
    for k in ("ablage_xy_m", "matten_xy_m"):
        gl[k] = [[round(x + dx, 4), round(y + dy, 4)] for x, y in gl[k]]
    sz["zwischenposen_m"] = [[round(x + dx, 4), round(y + dy, 4), z] for x, y, z in sz["zwischenposen_m"]]
    x0, y0 = sz["teller"]["staender_xy_m"]
    sz["teller"]["staender_xy_m"] = [round(x0 + dx, 4), round(y0 + dy, 4)]


# --- Abweichungen ------------------------------------------------------------------------------

def abweichung(art, seed):
    """Glas: +-5 mm, +-3 Grad je Glas, Korb 0..-1 cm (am Anschlag). Teller: je Teller x +-5 mm,
    Reihe y +-5 mm (Staebe wandern mit), Gier +-1 Grad (Staebe, 1 mm Luft)."""
    n = len(GLAS_SLOTS)
    if seed is None:
        return a1.abweichung(n), {"teller": [(0.0, 0.0, 0.0)] * len(TELLER_TIEFE)}
    rng = np.random.default_rng(seed)
    abw = a1.abweichung(n, rng)
    tel = [(float(rng.uniform(-0.005, 0.005)), float(rng.uniform(-0.005, 0.005)), float(rng.uniform(-1.0, 1.0)))
           for _ in TELLER_TIEFE]
    return abw, {"teller": tel}


# --- Welt ------------------------------------------------------------------------------------------

def _korb(A, abw, aus):
    return A.pruefer(aus + abw.korbauszug_delta_m, 0.0, {"glashalter": {"reihen_x_m": GLAS_REIHEN_X}})


def teller_liste(p, sz, f, abw, tabw, aus):
    t = sz["teller"]
    rt = float(t["durchmesser_m"]) / 2.0
    wulst = float(f.p["teller"]["wulst_dicke_mm"]) * 1e-3
    km = p.m["oberkorb"]
    boden = km["boden_hoehe_m"]
    vorne = km["vorne_eingeschoben_y_m"] + aus + abw.korbauszug_delta_m
    teller, halter = [], []
    for k, dy in enumerate(TELLER_TIEFE):
        ex, ey, eg = tabw["teller"][k]
        yk = vorne - dy + ey
        mitte = np.array([TELLER_X + ex, yk, boden + rt])
        tk = a1.teller_koerper(f"teller_{k + 1}", mitte, rt, wulst)
        tk = sg.Koerper(tk.name, "glas", tk.form, tk.mitte, tk.halb, rz(eg) @ tk.rot)
        teller.append(tk)
        halter += a1._halter(f"tellerhalter_{k + 1}", "tellerhalter", (TELLER_X, yk), t, wulst, boden)
        yb = wulst / 2.0 + float(t["halter_luft_m"])
        for j, sx in enumerate((-1.0, 1.0)):
            x0, x1 = sorted((TELLER_X + sx * 0.030, TELLER_X + sx * 0.045))
            halter.append(sg.quader(f"tellerhalter_{k + 1}_mulde_{j}", "tellerhalter", (x0, yk - yb, boden),
                                    (x1, yk + yb, boden + 0.003)))
    return teller, halter, rt, wulst


def glas_liste(p, abw):
    r, h = p.m["glas"]["durchmesser_m"] / 2.0, p.m["glas"]["hoehe_m"]
    out = []
    for i, s in enumerate(GLAS_SLOTS):
        m_ = p.szene.slots[int(s) - 1]
        dx, dy = abw.glas_versatz_xy_m[i]
        out.append(ag.glas(f"glas_{i + 1}", (m_[0] + dx, m_[1] + dy, m_[2]), ag.KOPFUEBER @ rz(abw.glas_gier_grad[i]), r, h))
    return out, r, h


def welt_glas(A, sz, f, abw, tabw):
    aus = float(A.d["ziele"]["slots"]["oberkorb_auszug_m"])
    p = _korb(A, abw, aus)
    a = a1._ausraeum_cfg(sz, f, "glaeser")
    sc = copy.deepcopy(p.sc)
    sc["pose"]["oberkorb_auszug_m"] = aus
    auf = konfig.Aufbau(p.m, sc, a, abw)
    za = a["zwischenablage"]
    gl_cfg = sz["glaeser"]
    k2 = float(za["kante_m"]) / 2.0
    zap = p.szene.arbeitsplatte_z
    n_m = len(za["matten_xy_m"])
    sockel_h = gl_cfg["matte_sockel_m"]
    sockel_h = [float(v) for v in sockel_h] if isinstance(sockel_h, list) else [float(sockel_h)] * n_m
    d_m = float(za["dicke_m"])
    oben = [zap + d_m + sockel_h[j] for j in range(n_m)]
    matten = [sg.quader(f"zwischenablage_{j + 1}", "zwischenablage", (x - k2, y - k2, oben[j] - d_m),
                        (x + k2, y + k2, oben[j])) for j, (x, y) in enumerate(za["matten_xy_m"])]
    sockel = [sg.quader(f"zwischenablage_sockel_{j + 1}", "zwischenablage", (x - k2, y - k2, zap),
                        (x + k2, y + k2, oben[j] - d_m)) for j, (x, y) in enumerate(za["matten_xy_m"])
              if oben[j] - d_m > zap + 1e-6]
    start, r, h = glas_liste(p, abw)
    ziel = []
    for i, (x, y) in enumerate(gl_cfg["ablage_xy_m"]):
        z_ziel = (oben[int(gl_cfg["je_ablage"][i])] if gl_cfg.get("ablage_auf_matte") else zap) + h / 2.0
        ziel.append(ag.glas(f"glas_{i + 1}", (float(x), float(y), z_ziel), np.eye(3), r, h))
    teller, halter, rt, wulst = teller_liste(p, sz, f, abw, tabw, aus)
    statisch = a1._statisch(p) + matten + sockel + halter
    w = ag.Welt(auf, A.lage, p.szene, statisch + teller, start, ziel, matten, r, h)
    w.pruefer = p
    w.teller = [sg.Koerper(k.name, "teller", k.form, k.mitte, k.halb, k.rot) for k in teller]
    w.teller_r, w.teller_wulst = rt, wulst
    w.statisch_ohne_teller = statisch
    w.glaeser_statisch = []
    return w


def welt_teller(A, sz, f, abw, tabw):
    t = sz["teller"]
    aus = float(A.d["ziele"]["teller"]["auszug_m"])
    p = _korb(A, abw, aus)
    a = a1._ausraeum_cfg(sz, f, "teller")
    sc = copy.deepcopy(p.sc)
    sc["pose"]["oberkorb_auszug_m"] = aus
    m = copy.deepcopy(p.m)
    m["glas"] = dict(m["glas"], masse_kg=float(t["masse_kg"]))
    auf = konfig.Aufbau(m, sc, a, abw)
    teller, halter, rt, wulst = teller_liste(p, sz, f, abw, tabw, aus)
    glaeser, gr, gh = glas_liste(p, abw)
    glaeser = [sg.Koerper(k.name.replace("glas_", "glasfest_"), "glasfest", "quader", k.mitte,
                          np.array([gr, gr, gh / 2.0]), np.eye(3)) for k in glaeser]
    statisch = a1._statisch(p) + halter + glaeser
    zap = p.szene.arbeitsplatte_z
    sb = float(t["staender_boden_m"])
    x0, y0 = (float(v) for v in t["staender_xy_m"])
    tx, ty = (float(v) for v in t["staender_teilung_m"])
    plaetze = [(x0 + k * tx, y0 + k * ty) for k in range(len(teller))]
    nx = abs(math.cos(math.radians(float(t["staender_gier_grad"])))) > 0.5
    lo = (min(pp[0] for pp in plaetze) - (0.03 if nx else 0.08), min(pp[1] for pp in plaetze) - (0.08 if nx else 0.03), zap)
    hi = (max(pp[0] for pp in plaetze) + (0.03 if nx else 0.08), max(pp[1] for pp in plaetze) + (0.08 if nx else 0.03), zap + sb)
    statisch.append(sg.quader("tellerstaender_boden", "tellerstaender", lo, hi))
    ziel = []
    for k, (x, y) in enumerate(plaetze):
        statisch += a1._halter(f"tellerstaender_{k + 1}", "tellerstaender", (x, y), t, wulst, zap + sb,
                               float(t["staender_halter_hoehe_m"]), normale_x=nx)
        ziel.append(a1.teller_koerper(f"teller_{k + 1}", (x, y, zap + sb + rt), rt, wulst, normale_x=nx))
    w = ag.Welt(auf, A.lage, p.szene, statisch, teller, ziel, [], rt, wulst)
    w.pruefer = p
    w.teller_r, w.teller_wulst = rt, wulst
    w.glaeser_statisch = glaeser
    return w


def nennlage_fn(A, sz, f, art, s):
    """Nennlage laut Belegungsplan: Welt ohne Lageabweichung, Korbauszug wie von der Ensenso
    gemessen. Liefert ``korbauszug_delta_m -> {mitte, rot, halb}`` fuer ``griffpose.schaetzen``."""
    from wahrnehmung import griffpose as WG
    n = len(GLAS_SLOTS)

    def nenn(korbauszug_delta_m: float):
        abw0 = konfig.Abweichung([(0.0, 0.0)] * n, [0.0] * n, float(korbauszug_delta_m), None)
        tabw0 = {"teller": [(0.0, 0.0, 0.0)] * len(TELLER_TIEFE)}
        w0 = (welt_glas if art == "glas" else welt_teller)(A, sz, f, abw0, tabw0)
        return WG.nennlage_aus_koerper(w0.glas_start[s])
    return nenn


def szenario_und_aufbau(art, variante=None, ziel=None):
    """Finger (ggf. Tellergriff-Variante), Szenario auf dem Aufbau ohne Ueberstand, Aufbau."""
    var = TV.laden()[variante] if (art == "teller" and variante) else None
    f = Finger.laden(**(var.finger if var else {}))
    sz = a1.szenario()
    sz["glaeser"]["slots"] = list(GLAS_SLOTS)
    auf_neue_lage(sz)
    if var is not None:
        sz["greifer"]["finger_breite_m"] = max(float(sz["greifer"]["finger_breite_m"]), var.breite_m())
        sz["teller"]["greifkraft_n"] = var.greifkraft_n
        sz["teller"]["zuordnung"] = [[ziel or 1, 1]]
    return var, f, sz, a1.aufbau(sz, f)


# --- Newton-Laeufe ---------------------------------------------------------------------------------

def _teller_formen(lauf, b, bi, g, cfg, T0, shapes, objekt_idx):
    """Teller als Scheibe + Kapselring; eine Kapsel (nicht eine Ecke) unten (sonst rollt er)."""
    wp = lauf.ctx["wp"]
    t = lauf.sz["teller"]
    ft = lauf.finger.p["teller"]
    r = float(t["durchmesser_m"]) / 2.0
    wulst = float(ft["wulst_dicke_mm"]) * 1e-3 / 2.0
    fahne = float(ft["fahne_dicke_mm"]) * 1e-3 / 2.0
    n = int(t["wulst_segmente"])
    rr = r - wulst
    seg = 2.0 * math.pi * rr / n

    def xf(c, R):
        return wp.transform(tuple(float(v) for v in (T0[1] @ np.asarray(c, float) + T0[0])), fs.quat_aus_matrix(T0[1] @ R))

    s0 = b.add_shape_cylinder(bi, xform=xf((0.0, 0.0, 0.0), fs.RX_SCHEIBE), radius=rr, half_height=fahne, cfg=cfg,
                              label=f"{g.name}_fahne")
    shapes.append(s0)
    if objekt_idx is not None:
        lauf.objekt_von_shape[s0] = objekt_idx
    for k in range(n):
        phi = 2.0 * math.pi * (k + 0.5) / n
        c = (rr * math.cos(phi), 0.0, rr * math.sin(phi))
        th = -phi
        Ry = np.array([[math.cos(th), 0.0, math.sin(th)], [0.0, 1.0, 0.0], [-math.sin(th), 0.0, math.cos(th)]])
        s = b.add_shape_capsule(bi, xform=xf(c, Ry), radius=wulst, half_height=seg / 2.0, cfg=cfg,
                                label=f"{g.name}_wulst_{k}")
        shapes.append(s)
        if objekt_idx is not None:
            lauf.objekt_von_shape[s] = objekt_idx


def _teller_dichte(sz, f):
    t = sz["teller"]
    ft = f.p["teller"]
    r = float(t["durchmesser_m"]) / 2.0
    wulst = float(ft["wulst_dicke_mm"]) * 1e-3 / 2.0
    fahne = float(ft["fahne_dicke_mm"]) * 1e-3 / 2.0
    n = int(t["wulst_segmente"])
    rr = r - wulst
    seg = 2.0 * math.pi * rr / n
    return float(t["masse_kg"]) / (math.pi * rr * rr * 2.0 * fahne + n * (math.pi * wulst * wulst * seg + 4.0 / 3.0 * math.pi * wulst ** 3))


def _teller_lage(g, sz, f):
    t = sz["teller"]
    rr = float(t["durchmesser_m"]) / 2.0 - float(f.p["teller"]["wulst_dicke_mm"]) * 1e-3 / 2.0
    ph = math.pi / int(t["wulst_segmente"])
    Ryh = np.array([[math.cos(ph), 0.0, math.sin(ph)], [0.0, 1.0, 0.0], [-math.sin(ph), 0.0, math.cos(ph)]])
    return np.asarray(g.mitte, float) - [0.0, 0.0, rr * (1.0 - math.cos(ph))], fs.teller_koerper_rot(g.rot) @ Ryh


class GlasLauf(fs.FingerLauf):
    """8 Glaeser frei, Teller statisch."""

    def bauen(self):
        w_plan = self.w
        w_sim = copy.copy(w_plan)
        w_sim.statisch = list(w_plan.statisch_ohne_teller)
        self.w = w_sim
        self.teller_shapes, self.teller_start = [], []
        try:
            super().bauen()
        finally:
            self.w = w_plan
        for s in self.teller_shapes:
            self.gruppe_von[s] = "teller"

    def objekte(self, b, shape_cfg):
        super().objekte(b, shape_cfg)
        si = self.w.aufbau.a["simulation"]
        cfg = shape_cfg(si["reibung_glas"], 0.0)
        for g in self.w.teller:
            m, R = _teller_lage(g, self.sz, self.finger)
            self.teller_start.append((m, R))
            _teller_formen(self, b, -1, g, cfg, (m, R), self.teller_shapes, None)


class TellerLauf(fs.TellerLauf):
    """6 Teller frei (Kapselring, Rollsperre), Glaeser statisch, Finger aus einer Tellergriff-Variante."""
    variante = None

    def finger_formen(self, b, bl, shape_cfg):
        return TV.formen_anlegen(self, b, bl, shape_cfg, TV.quader(self.variante, self.w.teller_r))

    def objekte(self, b, shape_cfg):
        wp = self.ctx["wp"]
        si = self.w.aufbau.a["simulation"]
        cfg = shape_cfg(si["reibung_glas"], _teller_dichte(self.sz, self.finger))
        self.teller_start = []
        for i, g in enumerate(self.w.glas_start):
            m, R = _teller_lage(g, self.sz, self.finger)
            self.teller_start.append((m, R))
            bi = b.add_body(xform=wp.transform(tuple(float(v) for v in m), fs.quat_aus_matrix(R)), label=g.name)
            self.glas_b.append(bi)
            sh = []
            _teller_formen(self, b, bi, g, cfg, (np.zeros(3), np.eye(3)), sh, i)
            self.glas_s.append(sh[0])


# --- Plan kuerzen + Bewertung ----------------------------------------------------------------------

def kuerzen(plan, art, tempo=1.0):
    from greifen.plan import Plan, Segment
    segs = plan.segmente
    i0 = [i for i, s in enumerate(segs) if s.phase.endswith("runter_korb")][0]
    if art == "teller":
        # nur die erste Teilfahrt zum Staender (Querfahrt): dort fiel der Teller mit dem Randgriff
        i1 = min(i for i, s in enumerate(segs) if s.phase.endswith("zur_ablage"))
    else:
        i1 = [i for i, s in enumerate(segs) if s.phase.endswith("aushub")][0]
    neu = Plan(plan.chain, None)
    neu.segmente.append(Segment("ruhe", 0.0, 0.5, segs[i0].wege[:1].copy()))
    t = 0.5
    for s in segs[i0:i1 + 1]:
        d = s.dauer / (tempo if not s.phase.endswith("greifen_korb") else 1.0)
        neu.segmente.append(Segment(s.phase, t, d, s.wege))
        t += d
    neu.segmente.append(Segment("halten", t, 1.0, segs[i1].wege[-1:].copy()))
    return neu


def _idx(t, x):
    return int(min(len(t) - 1, max(0, np.searchsorted(t, x))))


def bewerte_kurz(mess, plan, s, art, gr):
    t, G, tcp = mess["t"], mess["glas"], mess["tcp"]
    out = {"nan": bool(mess["nan"])}
    if mess["nan"] or len(t) == 0 or not np.all(np.isfinite(G)):
        out.update(erfolg=False, gruende=["simulation_instabil"])
        return out
    z = plan.phase_zeiten()
    pfx = f"{s + 1}:"
    i_g = _idx(t, z[pfx + "greifen_korb"][1])
    i_a = _idx(t, z[pfx + "aushub"][1])
    hub = float(G[i_a, s, 2] - G[0, s, 2])
    d = np.linalg.norm(G[i_g:, s, :3] - tcp[i_g:], axis=1)
    hand = float(np.max(np.abs(d - d[0])))
    k = np.array([ab._kipp(G[i, s, 3:7]) for i in range(len(t))])
    if art == "glas":
        k = 180.0 - k
    dk = float(np.max(np.abs(k[i_g:] - k[i_g])))
    versatz = (G[i_g, s, :2] - tcp[i_g, :2]).tolist()
    nachbar = {}
    for j in range(G.shape[1]):
        if j != s:
            nachbar[str(j + 1)] = float(np.max(np.linalg.norm(G[:, j, :3] - G[0, j, :3], axis=1)))
    nmax = max(nachbar.values()) if nachbar else 0.0
    fd = float(mess["finger_durchdringung_m"][s])
    kon = {g: [float(v[0]), v[1]] for g, v in mess["kontakt"][s].items()}
    gruende = []
    if hub < float(gr["hub_min_m"]):
        gruende.append("nicht_aus_dem_korb")
    if hand > 0.02:
        gruende.append("gefallen_oder_gerutscht")
    if dk >= 10.0:
        gruende.append("verdreht_in_der_hand")
    if nmax > float(gr["nachbar_verschiebung_max_m"]):
        gruende.append("nachbar_verschoben")
    if fd > float(gr["durchdringung_max_m"]):
        gruende.append("durchdringung")
    for grp, (tief, _ph) in kon.items():
        if grp in ("korb", "tuer", "arbeitsplatte") and tief > float(gr["kontakt_max_m"]):
            gruende.append(f"kontakt_{grp}")
    out.update(erfolg=not gruende, gruende=gruende, aushub_m=hub, hand_wanderung_m=hand,
               kippung_in_hand_grad=dk, kippung_start_grad=float(k[0]), kippung_ende_grad=float(k[-1]),
               griffversatz_xy_m=versatz, nachbar_max_m=nmax, nachbar_m=nachbar, finger_durchdringung_m=fd,
               finger_durchdringung_phase=mess["finger_durchdringung_phase"][s], kontakte=kon,
               objekt_ende_m=G[-1, s, :3].tolist(), tcp_ende_m=tcp[-1].tolist())
    return out


def teller_lage_grad(q):
    """Tellerkoerper (Quaternion x, y, z, w; Normale = Koerper-y): Neigung der Tellerebene gegen die
    Senkrechte und Drehung in der Tellerebene (Koerper-z gegen oben). Der Kapselring startet um ein
    halbes Segment gedreht (``_teller_lage``, 7,5 Grad bei 24 Segmenten); ``ab._kipp`` (Koerper-z
    gegen die Senkrechte) zaehlt diese Drehung in der Ebene als Kippung mit."""
    x, y, z, w = (float(v) for v in q)
    R = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                  [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                  [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    n, zk = R[:, 1], R[:, 2]
    ebene = math.degrees(math.asin(min(1.0, abs(float(n[2])))))
    drehung = math.degrees(math.atan2(float(np.dot(np.cross([0.0, 0.0, 1.0], zk), n)), float(zk[2])))
    return ebene, drehung


def bewerte_voll(mess, plan, gps, w, art, gr):
    """Ganzer Ablauf: Kriterien der Ausraeum-Bewertung (Zielfehler, Kippung am Ende, Hand, Nachbarn,
    Kontakte, Durchdringung) fuer das eine Objekt; flache Kennzahlen dazu. Teller: ``gekippt`` misst
    die Neigung der Tellerebene (``teller_lage_grad``), nicht die Drehung in der Ebene; der Wert nach
    ``finger.a1.bewerte_teller`` steht als ``kippung_koerper_grad`` daneben."""
    zeiten = plan.phase_zeiten()
    gp = gps[0]
    extra = {}
    if art == "teller":
        b = a1.bewerte_teller(0, gp, zeiten, w, mess, gr)
        G = mess["glas"]
        if b.get("werte") and np.all(np.isfinite(G)):
            e0, d0 = teller_lage_grad(G[0, gp.slot, 3:7])
            e1, d1 = teller_lage_grad(G[-1, gp.slot, 3:7])
            k = b["kriterien"]["gekippt"]
            extra = {"kippung_koerper_grad": k["wert"], "kippung_ebene_grad": e1, "drehung_in_ebene_grad": d1 - d0}
            k.update(ok=bool(e1 < float(gr["kippung_max_grad"])), wert=e1, koerper_grad=extra["kippung_koerper_grad"],
                     drehung_in_ebene_grad=d1 - d0, start_grad=e0)
            b["werte"]["kippung_end_grad"] = e1
            b["gruende"] = [g for g in ab.GRUENDE if g in b["kriterien"] and not b["kriterien"][g]["ok"]]
            b["erfolg"] = not b["gruende"]
    else:
        b = ab.bewerte_glas(0, gp, zeiten, w, mess, gr)
        if b.get("werte"):
            b["werte"]["in_der_hand_gewandert_m"] = a1._in_der_hand(gp, zeiten, mess)
    wv = b.get("werte") or {}
    hand = wv.get("in_der_hand_gewandert_m")
    if hand is None:
        hand = ((b.get("kriterien", {}).get("gefallen") or {}).get("wert") or {}).get("tcp_abstand_aenderung_max_m")
    return {"erfolg": b["erfolg"], "gruende": b["gruende"], "zielfehler_xy_m": wv.get("zielfehler_xy_m"),
            "kippung_end_grad": wv.get("kippung_end_grad"), "aushub_m": wv.get("aushub_m"),
            "hand_wanderung_m": hand, "nachbar_max_m": wv.get("nachbar_max_m"),
            "finger_durchdringung_m": float(mess["finger_durchdringung_m"][gp.slot]),
            "finger_durchdringung_phase": mess["finger_durchdringung_phase"][gp.slot],
            "objekt_ende_m": wv.get("ende_m"), "ziel_m": wv.get("ziel_m"), **extra, "voll": b}


# --- Hauptablauf -----------------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--art", choices=["glas", "teller"], required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ziel", type=int, default=None, help="Glas: Index in GLAS_SLOTS (Std. 3); Teller: 1..6 (Std. 1)")
    ap.add_argument("--variante", default=TELLER_VARIANTE, help="Tellergriff-Variante (finger/tellergriff/varianten.yaml)")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--wahrnehmung", action="store_true")
    ap.add_argument("--negativ", default=None)
    ap.add_argument("--ohne-pruefung", action="store_true", help="Negativtest: Griff trotz Abbruchgrund")
    ap.add_argument("--voll", action="store_true")
    ap.add_argument("--nur-plan", action="store_true")
    ap.add_argument("--device", default=None)
    ap.add_argument("--aufzeichnen", default=None)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    rec = {"args": vars(args), "ok": False}
    try:
        from ausraeumen import sim_newton as sn
        art = args.art
        ziel = args.ziel or (3 if art == "glas" else 1)
        s = ziel - 1
        var, f, sz, A = szenario_und_aufbau(art, args.variante, ziel)
        if var is not None:
            rec["variante"] = {"name": var.name, "beschreibung": var.beschreibung, "breite_m": var.breite_m(),
                               "greifkraft_n": var.greifkraft_n, "tempo": var.tempo}
        abw, tabw = abweichung(art, args.seed)
        rec["abweichung"] = {"glas": abw.as_dict(), "teller": tabw}
        welt = welt_glas if art == "glas" else welt_teller
        w_true = welt(A, sz, f, abw, tabw)
        # Geplant wird in der Welt, die die Wahrnehmung liefert (Ziel aus der Schaetzung)
        abw_p, tabw_p = copy.deepcopy(abw), copy.deepcopy(tabw)
        if args.wahrnehmung:
            from wahrnehmung import griffpose as WL
            est = WL.schaetzen(art, w_true, s, nennlage_fn(A, sz, f, art, s), seed=args.seed or 0,
                               negativ=args.negativ)
            rec["wahrnehmung"] = est
            print("WAHRNEHMUNG", json.dumps({k: est[k] for k in ("ok", "gruende", "fehler_mm") if k in est}), flush=True)
            if not est["ok"] and not args.ohne_pruefung:
                rec.update(ok=False, abgebrochen=True, erfolg=None)
                raise SystemExit(0)
            p_est = np.asarray(est["pose_m"], float)
            abw_p.korbauszug_delta_m = float(est["korbauszug_delta_m"])
            if art == "glas":
                aus = float(A.d["ziele"]["slots"]["oberkorb_auszug_m"])
                pk = _korb(A, abw_p, aus)
                m_ = pk.szene.slots[GLAS_SLOTS[s] - 1]
                v = list(abw_p.glas_versatz_xy_m)
                v[s] = (float(p_est[0] - m_[0]), float(p_est[1] - m_[1]))
                abw_p.glas_versatz_xy_m = v
            else:
                aus = float(A.d["ziele"]["teller"]["auszug_m"])
                km = w_true.pruefer.m["oberkorb"]
                vorne = km["vorne_eingeschoben_y_m"] + aus + abw_p.korbauszug_delta_m
                tl = list(tabw_p["teller"])
                tl[s] = (float(p_est[0] - TELLER_X), float(p_est[1] - (vorne - TELLER_TIEFE[s])), float(est.get("gier_grad", 0.0)))
                tabw_p["teller"] = tl
        w_plan = welt(A, sz, f, abw_p, tabw_p)
        if art == "glas":
            w_plan.aufbau.a["ablauf"]["zuordnung"] = [[ziel, ziel]]
        planer = a1.A1Planer(w_plan, A.cfg, A.chain, sz, f, teller=(art == "teller"), pruefer=w_plan.pruefer)
        tp = time.monotonic()
        plan, gps = planer.plane_teller() if art == "teller" else planer.plane()
        rec["plan"] = {"ok": True, "dauer_s": round(plan.dauer, 3), "wand_s": round(time.monotonic() - tp, 1),
                       "objekte": [{"slot": g.slot + 1, **g.info} for g in gps]}
        if not args.voll:
            plan = kuerzen(plan, art, var.tempo if var else 1.0)
        rec["plan"]["phasen"] = [[x.phase, round(x.t0, 3), round(x.t0 + x.dauer, 3)] for x in plan.segmente]
        rec["plan"]["sim_s"] = round(plan.dauer, 3)
        print("PLAN ok", rec["plan"]["dauer_s"], "s, sim", rec["plan"]["sim_s"], "s, wand", rec["plan"]["wand_s"], flush=True)
        if args.nur_plan:
            raise SystemExit(0)
        ctx = sn.kontext(args.device)
        rec["device"] = ctx["device"]
        Lauf = GlasLauf if art == "glas" else TellerLauf
        lauf = Lauf(ctx, w_true, plan, A.cfg, A.chain, a1.urdf_sim(A), 30.0 if args.aufzeichnen else None)
        lauf.finger, lauf.sz = f, sz
        if var is not None:
            lauf.variante = var
        lauf.bauen()
        mess = lauf.fahren()
        gr = w_true.aufbau.a["bewertung"]
        if args.voll:
            bew = bewerte_voll(mess, plan, gps, w_true, art, gr)
        else:
            bew = bewerte_kurz(mess, plan, s, art, gr)
        rec.update(erfolg=bew["erfolg"], bewertung=bew, ok=bool(bew["erfolg"]),
                   dauer={"sim_s": round(plan.dauer, 3), "wand_sim_s": round(lauf.wand_s, 1)},
                   modell={"koerper": len(lauf.body_label), "dt_s": mess["dt"]})
        if args.aufzeichnen:
            meta = {"szene": "spuelmaschine", "art": art, "ziel": s, "voll": bool(args.voll),
                    "statisch": [{"name": k.name, "gruppe": k.gruppe, "mitte": k.mitte, "halb": k.halb, "rot": k.rot}
                                 for k in (w_true.statisch_ohne_teller if art == "glas" else w_true.statisch) if k.name != "boden"],
                    "objekte": [{"name": k.name, "form": k.form, "halb": k.halb} for k in w_true.glas_start],
                    "teller_start": [{"name": g.name, "mitte": m_, "rot": R_} for g, (m_, R_) in
                                     zip(w_true.teller if art == "glas" else w_true.glas_start, lauf.teller_start)],
                    "teller_r_m": w_true.teller_r, "teller_wulst_m": w_true.teller_wulst,
                    "glas_radius_m": float(w_true.pruefer.m["glas"]["durchmesser_m"]) / 2.0,
                    "glas_hoehe_m": float(w_true.pruefer.m["glas"]["hoehe_m"]),
                    "variante": args.variante, "phasen_s": [[x.phase, x.t0, x.t0 + x.dauer] for x in plan.segmente],
                    "bewertung": {k: v for k, v in bew.items() if k != "voll"}, "wahrnehmung": rec.get("wahrnehmung")}
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
                                                          "kippung_in_hand_grad", "zielfehler_xy_m", "kippung_end_grad",
                                                          "nachbar_max_m", "finger_durchdringung_m")}, default=str), flush=True)
    print("LAUF_RESULT", json.dumps({"ok": rec.get("ok"), "abgebrochen": rec.get("abgebrochen", False),
                                     "wand_s": rec["wand_gesamt_s"], "fehler": "fehler" in rec}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
