"""Standardbilder fuer ``raeumwerk aufbau``: Uebersicht und kritische Posen (matplotlib).

Gezeichnet werden die Kollisionskoerper (Quader-Huellen in drei Ansichten),
nicht die Meshes; das sind Pruefbilder, keine Renderings.
"""
from __future__ import annotations

import itertools
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from . import geometrie
from .aufbau import ARM, Aufbau

FARBE = {"korpus": "0.55", "tuer": "tab:brown", "oberkorb": "tab:blue", "unterkorb": "tab:green",
         "glashalter": "tab:purple", "arbeitsplatte": "tan", "schrank": "0.8", "glas": "tab:cyan",
         "saeule": "dimgray", "halter": "dimgray", "podest": "dimgray", "tisch": "goldenrod"}
GEFUELLT = ("tuer", "arbeitsplatte", "saeule", "halter", "podest", "tisch", "schrank", "glas")
LINK = {"base_link": "k", "link_1": "tab:red", "link_2": "tab:orange", "link_3": "tab:red", "link_4": "tab:orange",
        "link_5": "tab:red", "link_6": "tab:orange", "gripper_base": "m", "finger_left": "m", "finger_right": "m",
        "carriage": "0.3", "rail": "0.3"}
EBENEN = {"xy": (0, 1, "Draufsicht: x entlang der Front, y in den Raum"),
          "yz": (1, 2, "Seitenansicht: y in den Raum, z hoch"),
          "xz": (0, 2, "Ansicht von vorn: x, z")}


def _ecken(k) -> np.ndarray:
    return np.array([k.mitte + k.rot @ (np.array(s) * k.halb) for s in itertools.product((-1, 1), repeat=3)])


def _huelle(P) -> np.ndarray:
    P = sorted(map(tuple, P))
    if len(P) <= 2:
        return np.array(P)

    def kreuz(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, hi = [], []
    for p in P:
        while len(lo) >= 2 and kreuz(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(P):
        while len(hi) >= 2 and kreuz(hi[-2], hi[-1], p) <= 0:
            hi.pop()
        hi.append(p)
    return np.array(lo[:-1] + hi[:-1])


def _zeichne(plt, ax, k, a, b, farbe, fill=False, alpha=0.5, ls="-", lw=0.7, z=1):
    if k.form == "zylinder" and (a, b) == (0, 1):
        ax.add_patch(plt.Circle((k.mitte[0], k.mitte[1]), k.halb[0], fill=fill, color=farbe, alpha=alpha, lw=lw, zorder=z))
        return
    H = _huelle(_ecken(k)[:, [a, b]])
    ax.add_patch(plt.Polygon(H, closed=True, fill=fill, fc=farbe, ec=farbe, alpha=alpha, ls=ls, lw=lw, zorder=z))


def _szene(plt, ax, p, a, b, gestrichelt=()):
    for h in p.hindernisse:
        if h.name == "boden":
            continue
        fill = h.gruppe in GEFUELLT
        _zeichne(plt, ax, h, a, b, FARBE.get(h.gruppe, "0.6"), fill=fill, alpha=0.35 if fill else 0.8)
    for h in gestrichelt:
        if h.gruppe in ("oberkorb", "unterkorb"):
            _zeichne(plt, ax, h, a, b, FARBE[h.gruppe], ls="--", alpha=0.6, lw=0.6)


def _roboter(plt, ax, p, q, a, b, alpha=0.85):
    for link, ks in p.roboterquader(np.asarray(q, float)).items():
        for k in ks:
            _zeichne(plt, ax, k, a, b, LINK.get(link, "k"), fill=True, alpha=alpha, z=5)


def _achsen(ax, a, b, titel):
    ax.set_aspect("equal")
    ax.grid(alpha=0.3)
    ax.set_title(titel, fontsize=8)
    lims = {0: (-0.65, 1.3), 1: (-0.65, 1.5), 2: (0.0, 2.2)}
    ax.set_xlim(*lims[a]); ax.set_ylim(*lims[b])
    ax.set_xlabel("xyz"[a] + " [m]", fontsize=7); ax.set_ylabel("xyz"[b] + " [m]", fontsize=7)
    ax.tick_params(labelsize=6)


def _zustand(d: Dict[str, Any], gruppe: str, r: Dict[str, Any]) -> Tuple[float, float, Optional[Dict]]:
    z = d["ziele"]
    if gruppe == "slots":
        return float((z["slots"] or {}).get("oberkorb_auszug_m", 0.45)), 0.0, None
    if gruppe == "teller":
        from .aufbau import teller_gruppen
        tg = teller_gruppen(z)
        cfg = next((t for t in tg if t.get("praefix") == r.get("teil")), tg[0])
        aus = float(cfg.get("auszug_m", 0.45))
        extra = None if cfg.get("glashalter", True) else {"glashalter": {"reihen_x_m": []}}
        return (aus, 0.0, extra) if cfg.get("korb", "unterkorb") == "oberkorb" else (0.0, aus, extra)
    return 0.0, 0.0, None


def _posen(e: Dict[str, Any]) -> List[Tuple[str, Dict[str, Any], List[List[float]]]]:
    """Kritische Posen: Korbzug mit dem groessten J2-Moment (Start/Ende), je Gruppe ein
    erreichtes Ziel (das mit der hoechsten Achsstellung) und ein knapper Fehlschlag."""
    out = []
    zr = [r for r in e["gruppen"].get("zug", []) if r.get("ok") and r.get("momente")]
    if zr:
        def j2(r):
            return max(v["gesamt"]["joint2"] for v in r["momente"].values())
        r = max(zr, key=j2)
        out.append(("zug", r, [r["q_start"], r["q_ende"]]))
    for g in ("slots", "teller", "ablage"):
        ok = [r for r in e["gruppen"].get(g, []) if r.get("ok") and r.get("q")]
        if ok:
            r = max(ok, key=lambda r: (r.get("achse7") or [0, 0])[1])
            out.append((g, r, [r["q"]]))
        nein = [r for r in e["gruppen"].get(g, []) if not r.get("ok") and r.get("q")]
        if nein:
            out.append((g, nein[0], [nein[0]["q"]]))
    return out


def zeichne_alle(d: Dict[str, Any], e: Dict[str, Any], out: Path) -> List[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out.mkdir(parents=True, exist_ok=True)
    A = Aufbau(d)
    namen = []
    posen = _posen(e)
    # Uebersicht
    p0 = A.pruefer(0.0, 0.0)
    aus = geometrie.baue(A.m0, 0.45, 0.45 if "unterkorb" in str(d["ziele"]) else 0.0)
    fig, axs = plt.subplots(1, 2, figsize=(15, 7.5))
    for ax, eb in zip(axs, ("xy", "yz")):
        a, b, ti = EBENEN[eb]
        _szene(plt, ax, p0, a, b, gestrichelt=aus.koerper)
        for i, (g, r, qs) in enumerate(posen[:3]):
            _roboter(plt, ax, p0, qs[0], a, b, alpha=0.75 if i == 0 else 0.3)
        _achsen(ax, a, b, ti)
    ab = ", ".join(f"{k} {v['ok']}/{v['n']}" if "n" in v else f"{k} {'ja' if v['ok'] else 'nein'}"
                   for k, v in e["abdeckung"].items())
    fig.suptitle(f"{e['name']} — {ab}", fontsize=10)
    fig.text(0.01, 0.01, "Durchgezogen: Koerbe eingeschoben; gestrichelt: ausgezogen. Grau: Halterung; "
             "Roboter = Kollisionsquader in kritischen Posen (Pruefbild, kein Rendering).", fontsize=7)
    fig.tight_layout(rect=(0, 0.03, 1, 0.96))
    f = out / "uebersicht.png"
    fig.savefig(f, dpi=100); plt.close(fig)
    namen.append(f.name)
    # Posen
    for g, r, qs in posen:
        ober, unter, extra = _zustand(d, g, r)
        p = A.pruefer(ober, unter, extra)
        fig, axs = plt.subplots(1, 3, figsize=(18, 6.5))
        for ax, eb in zip(axs, ("xy", "yz", "xz")):
            a, b, ti = EBENEN[eb]
            _szene(plt, ax, p, a, b)
            for i, q in enumerate(qs):
                _roboter(plt, ax, p, q, a, b, alpha=0.85 if i == 0 else 0.3)
            if r.get("xyz"):
                ax.plot(r["xyz"][a], r["xyz"][b], "r*", ms=10, zorder=9)
            _achsen(ax, a, b, ti)
        q = np.asarray(qs[0], float)
        tcp = p.tcp_welt(q)[:3, 3]
        gel = ", ".join(f"J{i + 1} {math.degrees(q[p.chain.index[n]]):.0f}°" for i, n in enumerate(ARM))
        info = (f"{e['name']} — {g} {r['ziel']}: {'erreichbar, kollisionsfrei (Rand 5 mm)' if r['ok'] else 'NICHT ok: ' + r.get('grund', '')[:80]}"
                f"\nTCP {np.round(tcp, 3).tolist()} | Achse {q[p.i7]:.3f} m | {gel}")
        if r.get("momente"):
            info += "\n" + " | ".join(f"{k}: Zug J1 {v['zug']['joint1']:.1f} / J2 {v['zug']['joint2']:.1f} / J3 {v['zug']['joint3']:.1f} Nm, "
                                      f"mit Eigengewicht J2 {v['gesamt']['joint2']:.1f} Nm ({v['urteil']})"
                                      for k, v in r["momente"].items())
        fig.suptitle(info, fontsize=9)
        fig.tight_layout(rect=(0, 0, 1, 0.88))
        f = out / f"pose-{g}-{r['ziel']}.png".replace(" ", "_")
        fig.savefig(f, dpi=100); plt.close(fig)
        namen.append(f.name)
    return namen
