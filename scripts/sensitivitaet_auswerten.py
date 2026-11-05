#!/usr/bin/env python3
"""Kameratag P4: Auswertung der Sensitivitaetslaeufe (Tornado, Metamodell, Sobol, Messreihenfolge).

    sensitivitaet_auswerten.py ROHDATEN_ORDNER --out ORDNER [--sobol-n 2048]

Liest ``zeilen-{sweep,design,conf,val}.jsonl`` (``sensitivitaet_lauf.py``) und schreibt in ``--out``:
``ergebnis.json`` (alle Zahlen), ``tabellen.md`` (Markdown-Tabellen), PNGs (tornado, sobol, metamodell, sweeps).

Alles gilt fuer das geometrische Wahrnehmungsmodell mit wahrer Maske; die Erkennungsrate und die
Zielverwechslung gehen als Wahrscheinlichkeiten analytisch ein (``sensitivitaet.mischen``).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

import numpy as np  # noqa: E402

from wahrnehmung import sensitivitaet as SE  # noqa: E402

ARTEN = ("glas", "teller")
PHYSNAMEN = [p.name for p in SE.PHYS]
KONT = [n for n in PHYSNAMEN if n != "mast"]
FEATURES = KONT + [f"mast_{i}" for i in range(4)]
PLAN = SE.PLAN
LABEL = {p.name: p.text for p in SE.PARAMETER}

# Messaufwand am Kameratag (ANNAHMEN, keine Messwerte): Minuten, Hilfsmittel, Paket
MESS = {
    "dicke_mm": (20, "Messschieber, 3 echte Dessertteller, Ensenso-Aufnahme in Mastpose", "Teller-Rand"),
    "gier_grad": (20, "Winkelmesser/Lehre an 6 Tellern im Staender (+ Newton-Reihe 3-7 Grad, ohne Kameratag)", "Lage"),
    "glas_lage_mm": (15, "Messschieber/Lehre an 8 Glas-Slots", "Lage"),
    "teller_lage_mm": (15, "Messschieber/Lehre an 6 Tellerplaetzen", "Lage"),
    "kalib_versatz_mm": (45, "Kalibriertafel, TCP auf 3-5 Referenzpunkte, Station + Hand-Auge", "Kalibrierung"),
    "kalib_dreh_grad": (0, "gleiche Messung wie Versatz (ein Durchgang liefert beides)", "Kalibrierung"),
    "rausch_ens": (20, "ebene Platte, 3 Abstaende, je 5 Aufnahmen", "Rauschen"),
    "rausch_d405": (15, "ebene Platte, 2 Abstaende, je 5 Aufnahmen", "Rauschen"),
    "maske_versatz_px": (15, "Schachbrett/scharfe Kante, Farbe gegen Tiefe", "Erkennung"),
    "maske_kipp": (0, "nicht einzeln messbar (Teil der Maskenguete, im Paket Erkennung)", "Erkennung"),
    "maske_bias_px": (0, "aus denselben Bildern wie Erkennungsrate (Masken gegen Handmaske)", "Erkennung"),
    "mast": (120, "Mast/Ausleger auf 4 Positionen umbauen, je 30 min (Umbau + Aufnahme)", "Mast"),
    "erk_glas": (60, "20+ Aufnahmen bei 3 Lichtlagen, Handlabel, Erkennungslauf (Baseline/Mask R-CNN)", "Erkennung"),
    "erk_teller": (0, "gleiche Aufnahmen wie Glas", "Erkennung"),
    "verwechslung": (15, "aus denselben Aufnahmen: Treffer auf Nachbarn zaehlen", "Erkennung"),
}


# --- Laden ------------------------------------------------------------------------------------------

def lade(ordner: Path):
    rows = defaultdict(list)
    fehler = 0
    for p in sorted(Path(ordner).glob("zeilen-*.jsonl")):
        for ln in p.read_text().splitlines():
            if not ln.strip():
                continue
            z = json.loads(ln)
            if "fehler" in z:
                fehler += 1
                continue
            rows[p.stem.split("-", 1)[1]].append(z)
    return rows, fehler


def sauber_mittel(zs, physik=False):
    ys = [SE.ziele_zeile(z, physik) for z in zs]
    return {k: float(np.mean([y[k] for y in ys])) for k in SE.KENN}, len(ys)


# --- Zielgroessen a-d aus den sauberen Mitteln je Objekt ------------------------------------------------

def ziele(sb, erk_g, erk_t, verw, kette, unb_verw=None):
    """sb: {art: sauber-dict}; liefert a (Glas Erfolg), b (Teller Erfolg), c (unbemerkt, Mittel/Glas/Teller), d (brauchbar)."""
    uv = unb_verw or {}
    g = SE.mischen(sb["glas"], erk_g, verw, uv.get("glas"))
    t = SE.mischen(sb["teller"], erk_t, verw, uv.get("teller"))
    return {"a_glas_erfolg": g[f"erfolg_{kette}"], "b_teller_erfolg": t[f"erfolg_{kette}"],
            "c_glas_unb": g[f"unb_{kette}"], "c_teller_unb": t[f"unb_{kette}"],
            "c_unb": 0.5 * (g[f"unb_{kette}"] + t[f"unb_{kette}"]),
            "d_glas_brauch": g["brauch"], "d_teller_brauch": t["brauch"],
            "d_brauch": 0.5 * (g["brauch"] + t["brauch"])}


ZIELNAMEN = ["a_glas_erfolg", "b_teller_erfolg", "c_glas_unb", "c_teller_unb", "c_unb",
             "d_glas_brauch", "d_teller_brauch", "d_brauch"]
VIER = ["a_glas_erfolg", "b_teller_erfolg", "c_unb", "d_brauch"]


# --- Sweep / Tornado ------------------------------------------------------------------------------------------

def sweep_auswerten(rows, unb_verw):
    sw = defaultdict(lambda: defaultdict(list))        # (param, wert) -> art -> [zeilen]
    for z in rows:
        _, name, v = z["kind"].split(":")
        sw[(name, float(v))][z["art"]].append(z)
    plan = sw[("plan", 0.0)]
    res = {"punkte": {}, "tornado": {}}
    for (name, v), per in sorted(sw.items()):
        sb = {a: sauber_mittel(per[a])[0] for a in ARTEN if per.get(a)}
        phys = {a: sauber_mittel(per[a], True)[0] for a in ARTEN if per.get(a)}
        n = {a: len(per[a]) for a in ARTEN if per.get(a)}
        res["punkte"][f"{name}:{v}"] = {"param": name, "wert": v, "n": n, "sauber": sb, "sauber_physik": phys}
    pl = res["punkte"]["plan:0.0"]
    for kette in SE.CHAINS:
        for physik in (False, True):
            tag = f"{kette}{'_physik' if physik else ''}"
            key = "sauber_physik" if physik else "sauber"
            base = ziele(pl[key], PLAN["erk_glas"], PLAN["erk_teller"], PLAN["verwechslung"], kette, unb_verw)
            tor = {}
            for p in SE.PARAMETER:
                if p.typ == "wahrsch":
                    lo = ziele(pl[key], *[(p.lo if q == p.name else PLAN[q]) for q in ("erk_glas", "erk_teller", "verwechslung")], kette, unb_verw)
                    hi = ziele(pl[key], *[(p.hi if q == p.name else PLAN[q]) for q in ("erk_glas", "erk_teller", "verwechslung")], kette, unb_verw)
                    tor[p.name] = {"lo": lo, "hi": hi, "lo_wert": p.lo, "hi_wert": p.hi}
                    continue
                werte = sorted(v for (n_, v) in sw if n_ == p.name)
                if not werte:
                    continue
                lo = res["punkte"][f"{p.name}:{werte[0]}"][key]
                hi = res["punkte"][f"{p.name}:{werte[-1]}"][key]
                tor[p.name] = {"lo": ziele(lo, PLAN["erk_glas"], PLAN["erk_teller"], PLAN["verwechslung"], kette, unb_verw),
                               "hi": ziele(hi, PLAN["erk_glas"], PLAN["erk_teller"], PLAN["verwechslung"], kette, unb_verw),
                               "lo_wert": werte[0], "hi_wert": werte[-1]}
                if p.typ == "kat":      # Kategorie: alle Werte (Haupt = Plan)
                    tor[p.name]["alle"] = {int(w): ziele(res["punkte"][f"{p.name}:{w}"][key], PLAN["erk_glas"], PLAN["erk_teller"], PLAN["verwechslung"], kette, unb_verw) for w in werte}
            res["tornado"][tag] = {"basis": base, "param": tor}
    res["n_plan"] = {a: len(plan[a]) for a in ARTEN if plan.get(a)}
    return res


# --- Metamodell ---------------------------------------------------------------------------------------------

def features(th):
    x = [float(th[n]) for n in KONT]
    m = int(th["mast"])
    return x + [1.0 if m == i else 0.0 for i in range(4)]


def feat_aus_einheit(U, eng=None):
    """Einheitswuerfel (m, 15) -> Features (m, 15) + erk_glas, erk_teller, verw. ``eng``: {Name: (lo, hi)}
    engt Spannen ein (bedingte Rangfolge, z. B. nach einer Messung)."""
    P = {p.name: p for p in SE.PARAMETER}
    eng = eng or {}
    X = np.zeros((len(U), len(FEATURES)))
    for j, n in enumerate(KONT):
        lo, hi = eng.get(n, (P[n].lo, P[n].hi))
        X[:, j] = lo + U[:, SE.NAME.index(n)] * (hi - lo)
    mast = np.minimum((U[:, SE.NAME.index("mast")] * 4).astype(int), 3)
    for i in range(4):
        X[:, len(KONT) + i] = (mast == i)
    pr = {}
    for n in ("erk_glas", "erk_teller", "verwechslung"):
        lo, hi = eng.get(n, (P[n].lo, P[n].hi))
        pr[n] = lo + U[:, SE.NAME.index(n)] * (hi - lo)
    return X, pr


def modelle_trainieren(design_rows, val_rows, seed=1):
    from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
    from sklearn.model_selection import KFold
    from sklearn.multioutput import MultiOutputRegressor

    by = defaultdict(dict)
    for z in design_rows:
        by[z["idx"]][z["art"]] = z
    idx = sorted(i for i, d in by.items() if len(d) == 2)
    X = np.array([features(by[i]["glas"]["th"]) for i in idx])
    out = {"n": len(idx), "modelle": {}, "gueten": {}}
    rng = np.random.default_rng(seed)
    perm = rng.permutation(len(idx))
    cut = int(0.8 * len(idx))
    tr, te = perm[:cut], perm[cut:]

    def r2(y, p):
        ss = ((y - y.mean(0)) ** 2).sum(0)
        return np.where(ss > 1e-9, 1 - ((y - p) ** 2).sum(0) / np.where(ss > 1e-9, ss, 1), np.nan)

    # Validierung: frische Punkte, Mittel ueber Seeds = Wahrscheinlichkeit
    vby = defaultdict(lambda: defaultdict(list))
    for z in val_rows:
        vby[z["idx"]][z["art"]].append(z)
    for art in ARTEN:
        for physik in (False, True):
            if physik and art == "glas":
                continue
            tag = f"{art}{'_physik' if physik else ''}"
            Y = np.array([[SE.ziele_zeile(by[i][art], physik)[k] for k in SE.KENN] for i in idx])
            rf = RandomForestRegressor(n_estimators=300, min_samples_leaf=3, random_state=seed, n_jobs=2)
            gb = MultiOutputRegressor(GradientBoostingRegressor(n_estimators=150, max_depth=3, learning_rate=0.08,
                                                                subsample=0.8, random_state=seed))
            rf.fit(X[tr], Y[tr])
            gb.fit(X[tr], Y[tr])
            g = {"R2_holdout_rf": dict(zip(SE.KENN, map(_f, r2(Y[te], rf.predict(X[te]))))),
                 "R2_holdout_gbm": dict(zip(SE.KENN, map(_f, r2(Y[te], gb.predict(X[te]))))),
                 "n_train": int(len(tr)), "n_test": int(len(te)), "mittel": dict(zip(SE.KENN, map(float, Y.mean(0))))}
            cv = []
            for a, b in KFold(5, shuffle=True, random_state=seed).split(X):
                m = RandomForestRegressor(n_estimators=150, min_samples_leaf=3, random_state=seed, n_jobs=2).fit(X[a], Y[a])
                cv.append(r2(Y[b], m.predict(X[b])))
            g["R2_cv5_rf"] = dict(zip(SE.KENN, map(_f, np.nanmean(np.array(cv), axis=0))))
            if vby:
                vi = sorted(i for i, d in vby.items() if d.get(art))
                Xv = np.array([features(vby[i][art][0]["th"]) for i in vi])
                Yv = np.array([[np.mean([SE.ziele_zeile(z, physik)[k] for z in vby[i][art]]) for k in SE.KENN] for i in vi])
                g["n_val_punkte"] = len(vi)
                g["n_val_seeds"] = int(np.mean([len(vby[i][art]) for i in vi]))
                g["R2_val_rf"] = dict(zip(SE.KENN, map(_f, r2(Yv, rf.predict(Xv)))))
                g["R2_val_gbm"] = dict(zip(SE.KENN, map(_f, r2(Yv, gb.predict(Xv)))))
                g["val_mae_rf"] = dict(zip(SE.KENN, map(float, np.abs(Yv - rf.predict(Xv)).mean(0))))
                g["_val"] = (Yv.tolist(), rf.predict(Xv).tolist())
            g["_test"] = (Y[te].tolist(), rf.predict(X[te]).tolist())
            pt_ = np.clip(rf.predict(X[te]), 0, 1)
            vy = Y[te].var(0)
            g["R2_rauschgrenze"] = dict(zip(SE.KENN, map(_f, np.where(vy > 1e-9, 1 - (pt_ * (1 - pt_)).mean(0) / np.where(vy > 1e-9, vy, 1), np.nan))))
            out["gueten"][tag] = g
            # Endmodelle auf allen Daten fuer die Sobol-Rechnung
            rf_all = RandomForestRegressor(n_estimators=400, min_samples_leaf=3, random_state=seed, n_jobs=2).fit(X, Y)
            gb_all = MultiOutputRegressor(GradientBoostingRegressor(n_estimators=150, max_depth=3, learning_rate=0.08,
                                                                    subsample=0.8, random_state=seed)).fit(X, Y)
            out["modelle"][tag] = {"rf": rf_all, "gbm": gb_all}
    return out


def _f(x):
    return None if not np.isfinite(x) else float(x)


# --- Sobol auf dem Metamodell (+ analytische Erkennung/Verwechslung) --------------------------------------

def sobol_meta(mod, unb_verw, art_modell="rf", n=2048, physik_teller=False, seed=3, eng=None):
    names = SE.NAME            # 15 Eingaenge, Reihenfolge = SE.PARAMETER
    kette_liste = SE.CHAINS

    def f(U):
        X, pr = feat_aus_einheit(U, eng)
        pg = mod["modelle"]["glas"][art_modell].predict(X)
        pt = mod["modelle"]["teller_physik" if physik_teller else "teller"][art_modell].predict(X)
        pg, pt = np.clip(pg, 0, 1), np.clip(pt, 0, 1)
        cols = []
        res = []
        for kette in kette_liste:
            g = {k: pg[:, j] for j, k in enumerate(SE.KENN)}
            t = {k: pt[:, j] for j, k in enumerate(SE.KENN)}
            gm = SE.mischen(g, pr["erk_glas"], pr["verwechslung"], (unb_verw or {}).get("glas"))
            tm = SE.mischen(t, pr["erk_teller"], pr["verwechslung"], (unb_verw or {}).get("teller"))
            res += [gm[f"erfolg_{kette}"], tm[f"erfolg_{kette}"], gm[f"unb_{kette}"], tm[f"unb_{kette}"],
                    0.5 * (gm[f"unb_{kette}"] + tm[f"unb_{kette}"]), gm["brauch"], tm["brauch"],
                    0.5 * (gm["brauch"] + tm["brauch"])]
        return np.column_stack(res)

    r = SE.sobol(f, len(names), n=n, seed=seed, boot=100)
    namen_t = [f"{k}:{z}" for k in kette_liste for z in ZIELNAMEN]
    return {"eingaenge": names, "ziele": namen_t, "s1": r["s1"], "st": r["st"], "s1_ci": r["s1_ci"], "st_ci": r["st_ci"],
            "var": r["var"]}


# --- Ausgabe -------------------------------------------------------------------------------------------------

def pct(x):
    return "–" if x is None or not np.isfinite(x) else f"{100 * x:.0f}"


def plots(out, sw, mod, sob, rows_sweep):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # Tornado fuer Kette K und B
    for kette in ("K", "B"):
        tor = sw["tornado"][kette]
        fig, axs = plt.subplots(2, 2, figsize=(15, 10))
        for ax, z in zip(axs.ravel(), VIER):
            base = tor["basis"][z]
            lst = []
            for n, d in tor["param"].items():
                lst.append((n, d["lo"][z] - base, d["hi"][z] - base))
            lst.sort(key=lambda t: max(abs(t[1]), abs(t[2])))
            y = np.arange(len(lst))
            ax.barh(y - 0.2, [100 * t[1] for t in lst], 0.4, label="untere Spannengrenze", color="tab:blue")
            ax.barh(y + 0.2, [100 * t[2] for t in lst], 0.4, label="obere Spannengrenze", color="tab:orange")
            ax.set_yticks(y)
            ax.set_yticklabels([t[0] for t in lst], fontsize=8)
            ax.axvline(0, color="k", lw=0.8)
            ax.set_title(f"{z}  (Plan {100 * base:.0f} %)", fontsize=10)
            ax.set_xlabel("Aenderung gegen Plan (Prozentpunkte)")
            ax.legend(fontsize=7)
        fig.suptitle(f"Tornado, Kette {kette}: je ein Parameter von Plan auf Spannengrenzen (Modell, wahre Maske)")
        fig.tight_layout()
        fig.savefig(out / f"tornado_{kette}.png", dpi=90)
        plt.close(fig)
    # Sobol (ST, Fehlerbalken 95 %)
    for kette in ("K", "B"):
        fig, axs = plt.subplots(1, 4, figsize=(20, 6))
        for ax, z in zip(axs, VIER):
            j = sob["ziele"].index(f"{kette}:{z}")
            st = sob["st"][:, j]
            ci = sob["st_ci"][:, :, j]
            o = np.argsort(st)
            ax.barh(np.arange(len(o)), st[o], xerr=[st[o] - ci[0][o], ci[1][o] - st[o]], color="tab:green", capsize=2)
            ax.set_yticks(np.arange(len(o)))
            ax.set_yticklabels([sob["eingaenge"][i] for i in o], fontsize=8)
            ax.set_title(f"{z}", fontsize=10)
            ax.set_xlabel("Sobol ST (Gesamtindex)")
        fig.suptitle(f"Sobol-Gesamtindex auf dem Random-Forest-Metamodell, Kette {kette}")
        fig.tight_layout()
        fig.savefig(out / f"sobol_{kette}.png", dpi=90)
        plt.close(fig)
    # Metamodell-Guete
    tags = [t for t in mod["gueten"] if "physik" not in t]
    fig, axs = plt.subplots(len(tags), 3, figsize=(13, 4.2 * len(tags)))
    axs = np.atleast_2d(axs)
    for r, tag in enumerate(tags):
        g = mod["gueten"][tag]
        y, p = np.array(g["_test"][0]), np.array(g["_test"][1])
        for c, k in enumerate(("erfolg_K", "erfolg_B", "brauch")):
            j = SE.KENN.index(k)
            ax = axs[r, c]
            ax.scatter(y[:, j] + np.random.default_rng(0).normal(0, 0.02, len(y)), p[:, j], s=6, alpha=0.5)
            ax.plot([0, 1], [0, 1], "k--", lw=0.8)
            ax.set_title(f"{tag} {k}: R2 hold-out {g['R2_holdout_rf'][k]}", fontsize=9)
            ax.set_xlabel("Modell (0/1, 1 Seed)")
            ax.set_ylabel("Metamodell")
    fig.tight_layout()
    fig.savefig(out / "metamodell.png", dpi=80)
    plt.close(fig)
    # Sweeps
    pts = sw["punkte"]
    params = [p.name for p in SE.PHYS]
    fig, axs = plt.subplots(len(params), 2, figsize=(11, 3 * len(params)))
    for r, n in enumerate(params):
        vals = sorted(v["wert"] for v in pts.values() if v["param"] == n)
        for c, art in enumerate(ARTEN):
            ax = axs[r, c]
            for kette, col in (("K", "tab:red"), ("A", "tab:orange"), ("B", "tab:green")):
                ax.plot(vals, [pts[f"{n}:{v}"]["sauber"][art][f"erfolg_{kette}"] for v in vals], "o-", color=col, label=f"Erfolg {kette}")
                ax.plot(vals, [pts[f"{n}:{v}"]["sauber"][art][f"unb_{kette}"] for v in vals], "x:", color=col, label=f"unbemerkt {kette}")
            ax.set_title(f"{art}: {n}", fontsize=9)
            ax.set_ylim(-0.05, 1.05)
            if r == 0:
                ax.legend(fontsize=6, ncol=3)
    fig.tight_layout()
    fig.savefig(out / "sweeps.png", dpi=70)
    plt.close(fig)


def tabellen(out, sw, mod, sob, sob_gbm, sob_phys, conf, rows_n, unb_verw, bed=()):
    L = []
    L.append("## Zeilenzahlen\n")
    L.append("| Teil | Zeilen |\n|---|---:|")
    for k, v in rows_n.items():
        L.append(f"| {k} | {v} |")
    L.append("\n## Metamodell-Güte (Random Forest, 80/20-Hold-out, 5-fold-CV, frische Validierungspunkte)\n")
    L.append("| Objekt | Ziel | R² Hold-out RF | R² Hold-out GBM | R² 5-fold RF | Rauschgrenze R² (1 Seed, binär) | R² Validierung RF (Mittel über Seeds) | MAE Validierung |")
    L.append("|---|---|---:|---:|---:|---:|---:|---:|")
    for tag, g in mod["gueten"].items():
        for k in SE.KENN:
            if g["mittel"][k] < 0.005 and not (g["R2_holdout_rf"][k]):
                L.append(f"| {tag} | {k} | (Anteil {100 * g['mittel'][k]:.1f} %, keine Varianz) | | | | | |")
                continue
            v = g.get("R2_val_rf", {}).get(k)
            rg = g["R2_rauschgrenze"][k]
            L.append(f"| {tag} | {k} | {g['R2_holdout_rf'][k] if g['R2_holdout_rf'][k] is None else round(g['R2_holdout_rf'][k], 2)} | "
                     f"{None if g['R2_holdout_gbm'][k] is None else round(g['R2_holdout_gbm'][k], 2)} | "
                     f"{None if g['R2_cv5_rf'][k] is None else round(g['R2_cv5_rf'][k], 2)} | "
                     f"{'–' if rg is None else round(rg, 2)} | "
                     f"{'–' if v is None else round(v, 2)} | {'–' if 'val_mae_rf' not in g else round(g['val_mae_rf'][k], 3)} |")
    for kette in ("K", "B", "A"):
        tor = sw["tornado"][kette]
        L.append(f"\n## Tornado, Kette {kette} (Plan-Punkt, Prozent; Änderung auf untere / obere Spannengrenze)\n")
        L.append("Basis: " + ", ".join(f"{z} {pct(tor['basis'][z])} %" for z in VIER) + "\n")
        L.append("| Parameter | lo→hi | a Glas-Erfolg lo / hi | b Teller-Erfolg lo / hi | c unbemerkt lo / hi | d brauchbar lo / hi |")
        L.append("|---|---|---|---|---|---|")
        rows = []
        for n, d in tor["param"].items():
            sp = max(abs(d["lo"][z] - tor["basis"][z]) + abs(d["hi"][z] - tor["basis"][z]) for z in VIER)
            rows.append((sp, n, d))
        for sp, n, d in sorted(rows, key=lambda t: -t[0]):
            cells = " | ".join(f"{pct(d['lo'][z])} / {pct(d['hi'][z])}" for z in VIER)
            L.append(f"| {n} | {d['lo_wert']:g}→{d['hi_wert']:g} | {cells} |")
    # Sobol
    def sob_tab(s, titel, kette):
        L.append(f"\n## {titel}, Kette {kette}: Sobol ST (S1) mit 95-%-Bootstrap auf ST\n")
        L.append("| Parameter | " + " | ".join(VIER) + " | Mittel ST | Rang |")
        L.append("|---|" + "---|" * (len(VIER) + 2))
        js = [s["ziele"].index(f"{kette}:{z}") for z in VIER]
        mean = np.mean([s["st"][:, j] for j in js], axis=0)
        order = np.argsort(-mean)
        for rk, i in enumerate(order, 1):
            cells = " | ".join(f"{s['st'][i, j]:.2f} ({s['s1'][i, j]:.2f}) [{s['st_ci'][0][i, j]:.2f}–{s['st_ci'][1][i, j]:.2f}]" for j in js)
            L.append(f"| {s['eingaenge'][i]} | {cells} | {mean[i]:.2f} | {rk} |")
    for kette in ("K", "B"):
        sob_tab(sob, "Sobol (RF, geometrisches Erfolgsmaß)", kette)
    sob_tab(sob_phys, "Sobol (RF, Teller-Erfolg mit Physik-Gierlimit 4°)", "K")
    sob_tab(sob_phys, "Sobol (RF, Teller-Erfolg mit Physik-Gierlimit 4°)", "B")
    for titel, s in bed:
        for kette in ("K", "B"):
            sob_tab(s, titel, kette)
    L.append("\n## Mittlere Anteile über das Design (gleichverteilt über alle Spannen, saubere Maske, ohne Erkennung)\n")
    L.append("| Objekt | " + " | ".join(SE.KENN) + " |\n|---|" + "---:|" * len(SE.KENN))
    for tag, g in mod["gueten"].items():
        L.append(f"| {tag} | " + " | ".join(f"{100 * g['mittel'][k]:.1f}" for k in SE.KENN) + " |")
    # Rangstabilitaet RF vs GBM
    from scipy.stats import spearmanr
    L.append("\n## Rangstabilität: RF gegen GBM (Spearman über die 15 ST-Werte)\n")
    L.append("| Kette | Ziel | Spearman |\n|---|---|---:|")
    for kette in SE.CHAINS:
        for z in VIER:
            j = sob["ziele"].index(f"{kette}:{z}")
            rho = spearmanr(sob["st"][:, j], sob_gbm["st"][:, j])[0]
            L.append(f"| {kette} | {z} | {rho:.2f} |")
    # Verwechslung
    L.append("\n## Zielverwechslung (Nachbarmaske beider Kameras), unbemerkte Fehlgriffe\n")
    L.append("| Objekt | Kette | n | unbemerkt | Erfolg | Wilson-95-%-Obergrenze unbemerkt |\n|---|---|---:|---:|---:|---:|")
    for art in ARTEN:
        for kette in SE.CHAINS:
            c = conf.get(art, {}).get(kette)
            if c:
                L.append(f"| {art} | {kette} | {c['n']} | {c['unb']} | {c['erfolg']} | {100 * c['ober']:.1f} % |")
    # Sweeps
    L.append("\n## Sweeps um den Plan-Punkt: sauberer Erfolg (wahre Maske, ohne Erkennung) und unbemerkt, Prozent\n")
    L.append("Je Wert n Seeds (siehe Spalte n); K / A / B = Erfolg; unb = unbemerkt K / A / B; br = brauchbar.\n")
    L.append("| Parameter | Wert | n | Glas Erfolg K/A/B | Glas unb K/A/B | Glas br | Teller Erfolg K/A/B | Teller unb K/A/B | Teller br | Teller Erfolg K/A/B (Physik) |")
    L.append("|---|---:|---:|---|---|---:|---|---|---:|---|")
    for key, v in sw["punkte"].items():
        g, t = v["sauber"]["glas"], v["sauber"]["teller"]
        tp = v["sauber_physik"]["teller"]
        L.append(f"| {v['param']} | {v['wert']:g} | {v['n']['glas']} | " +
                 "/".join(pct(g[f'erfolg_{c}']) for c in SE.CHAINS) + " | " +
                 "/".join(pct(g[f'unb_{c}']) for c in SE.CHAINS) + f" | {pct(g['brauch'])} | " +
                 "/".join(pct(t[f'erfolg_{c}']) for c in SE.CHAINS) + " | " +
                 "/".join(pct(t[f'unb_{c}']) for c in SE.CHAINS) + f" | {pct(t['brauch'])} | " +
                 "/".join(pct(tp[f'erfolg_{c}']) for c in SE.CHAINS) + " |")
    # Messreihenfolge
    L.append("\n## Messprioritäten: Einfluss (Sobol ST, Mittel der vier Ziele) gegen Aufwand\n")
    L.append("Aufwand = Annahme (Minuten am Kameratag), Pakete teilen sich den Aufbau.\n")
    L.append("| Parameter | ST Mittel K | ST Mittel B | ST max (K/B, 4 Ziele) | Aufwand min | Paket | Hilfsmittel |")
    L.append("|---|---:|---:|---:|---:|---|---|")
    mk = {}
    for kette in ("K", "B"):
        js = [sob["ziele"].index(f"{kette}:{z}") for z in VIER]
        mk[kette] = (np.mean([sob["st"][:, j] for j in js], axis=0), np.max([sob["st"][:, j] for j in js], axis=0))
    order = np.argsort(-(mk["K"][0] + mk["B"][0]))
    for i in order:
        n = sob["eingaenge"][i]
        a = MESS[n]
        L.append(f"| {n} | {mk['K'][0][i]:.2f} | {mk['B'][0][i]:.2f} | {max(mk['K'][1][i], mk['B'][1][i]):.2f} | {a[0]} | {a[2]} | {a[1]} |")
    L.append("\n| Paket | Aufwand min | Summe ST K | Summe ST B | ST je Stunde (K+B)/2 |\n|---|---:|---:|---:|---:|")
    pk = defaultdict(lambda: [0, 0.0, 0.0])
    for i, n in enumerate(sob["eingaenge"]):
        p = MESS[n][2]
        pk[p][0] += MESS[n][0]
        pk[p][1] += mk["K"][0][i]
        pk[p][2] += mk["B"][0][i]
    for p, (m, sk, sb_) in sorted(pk.items(), key=lambda t: -(t[1][1] + t[1][2])):
        L.append(f"| {p} | {m} | {sk:.2f} | {sb_:.2f} | {((sk + sb_) / 2) / (m / 60 if m else 1):.2f} |")
    (out / "tabellen.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    return mk


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("rohdaten")
    ap.add_argument("--out", required=True)
    ap.add_argument("--sobol-n", type=int, default=2048)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rows, fehler = lade(Path(a.rohdaten))
    rows_n = {k: len(v) for k, v in rows.items()}
    rows_n["Fehlerzeilen (verworfen)"] = fehler
    print(rows_n, flush=True)
    # Verwechslung: unbemerkt-Rate je Objekt/Kette aus den Nachbarmasken-Laeufen
    conf, unb_verw = {}, {}
    for art in ARTEN:
        zs = [z for z in rows.get("conf", []) if z["art"] == art]
        if not zs:
            continue
        ys = [SE.ziele_zeile(z) for z in zs]
        conf[art], unb_verw[art] = {}, {}
        for kette in SE.CHAINS:
            k = int(sum(y[f"unb_{kette}"] for y in ys))
            n = len(ys)
            conf[art][kette] = {"n": n, "unb": k, "erfolg": int(sum(y[f"erfolg_{kette}"] for y in ys)), "ober": SE.wilson(k, n)[1]}
            unb_verw[art][kette_key(kette)] = k / n
    sw = sweep_auswerten(rows["sweep"], unb_verw or None) if rows.get("sweep") else None
    mod = modelle_trainieren(rows["design"], rows.get("val", []))
    uv = unb_verw or None
    sob = sobol_meta(mod, uv, "rf", a.sobol_n)
    sob_gbm = sobol_meta(mod, uv, "gbm", max(512, a.sobol_n // 4))
    sob_phys = sobol_meta(mod, uv, "rf", a.sobol_n, physik_teller=True)
    # Upper-Bound-Variante der Verwechslung (Wilson-Obergrenze) als Robustheit
    uv_hi = {a_: {f"unb_{c}": conf[a_][c]["ober"] for c in SE.CHAINS} for a_ in conf} if conf else None
    sob_hi = sobol_meta(mod, uv_hi, "rf", max(512, a.sobol_n // 2)) if uv_hi else None
    bed = [("Bedingte Rangfolge nach Messung Tellerrand <= 6 mm (RF)", sobol_meta(mod, uv, "rf", a.sobol_n, eng={"dicke_mm": (3.0, 6.0)})),
           ("Bedingte Rangfolge nach Tellerrand <= 6 mm UND Kalibrierung klein (Versatz <= 5 mm, Drehung <= 5°) (RF)",
            sobol_meta(mod, uv, "rf", a.sobol_n, eng={"dicke_mm": (3.0, 6.0), "kalib_versatz_mm": (0.0, 5.0), "kalib_dreh_grad": (0.0, 5.0)})),
           ("Bedingte Rangfolge bei grosser Kalibrierabweichung (Versatz 10-30 mm, Drehung 10-20°) und Tellerrand <= 6 mm (RF)",
            sobol_meta(mod, uv, "rf", a.sobol_n, eng={"dicke_mm": (3.0, 6.0), "kalib_versatz_mm": (10.0, 30.0), "kalib_dreh_grad": (10.0, 20.0)}))]
    mk = tabellen(out, sw, mod, sob, sob_gbm, sob_phys, conf, rows_n, uv, bed)
    plots(out, sw, mod, sob, rows.get("sweep"))
    ser = {"zeilen": rows_n, "unb_verw": uv, "verwechslung_conf": conf,
           "gueten": {t: {k: v for k, v in g.items() if not k.startswith("_")} for t, g in mod["gueten"].items()},
           "sobol_rf": _js(sob), "sobol_gbm": _js(sob_gbm), "sobol_physik": _js(sob_phys),
           "sobol_bedingt": [{"titel": t, **_js(s)} for t, s in bed],
           "sobol_unb_ober": _js(sob_hi) if sob_hi else None, "tornado": sw["tornado"], "sweep_punkte": sw["punkte"]}
    (out / "ergebnis.json").write_text(json.dumps(ser, indent=1, default=float), encoding="utf-8")
    print("fertig", flush=True)


def kette_key(k):
    return f"unb_{k}"


def _js(s):
    return {k: (v.tolist() if hasattr(v, "tolist") else v) for k, v in s.items()}


if __name__ == "__main__":
    main()
