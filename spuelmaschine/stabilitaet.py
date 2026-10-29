"""Newton-Stabilitaetstest: 4 Glaeser liegen kopfueber im ausgezogenen Oberkorb.

Statische Szene aus ``spuelmaschine.geometrie`` (Korpus, Tuer, Koerbe,
Glashalter, Arbeitsplatte, Schraenke), dazu 4 freie Glaeser (Vollzylinder mit
Glasmasse) in ihren Slots. Ablauf: ``einschwingen_s`` absetzen lassen, dann
``dauer_s`` messen. Bestanden, wenn jedes Glas im Messfenster weniger als
``drift_max_m`` wandert, nicht tiefer als ``einsinken_max_m`` unter seine
Ruhelage sinkt (kein Durchfallen) und keine NaN auftreten. Gleicher Loeser
wie die Greifdemo (MuJoCo-Warp ueber Newton, Newton-Kollisionspipeline).

    uvx -p 3.12 --with newton==1.6.1 --with warp-lang==1.17.0 --with mujoco==3.12.0 \\
        --with mujoco-warp==3.12.0 --with numpy --with pyyaml \\
        python -m spuelmaschine.stabilitaet --device cpu --out ergebnis.json
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from typing import Dict, Optional, Sequence

import numpy as np

from . import geometrie, masse

VERSIONS_PAKETE = ("newton", "warp-lang", "mujoco", "mujoco-warp", "numpy")


def quat_aus_matrix(r: np.ndarray):
    """(x, y, z, w) einer Rotationsmatrix."""
    t = float(np.trace(r))
    if t > 0:
        s = math.sqrt(t + 1.0) * 2
        return ((r[2, 1] - r[1, 2]) / s, (r[0, 2] - r[2, 0]) / s, (r[1, 0] - r[0, 1]) / s, 0.25 * s)
    i = int(np.argmax(np.diag(r)))
    if i == 0:
        s = math.sqrt(1.0 + r[0, 0] - r[1, 1] - r[2, 2]) * 2
        return (0.25 * s, (r[0, 1] + r[1, 0]) / s, (r[0, 2] + r[2, 0]) / s, (r[2, 1] - r[1, 2]) / s)
    if i == 1:
        s = math.sqrt(1.0 + r[1, 1] - r[0, 0] - r[2, 2]) * 2
        return ((r[0, 1] + r[1, 0]) / s, 0.25 * s, (r[1, 2] + r[2, 1]) / s, (r[0, 2] - r[2, 0]) / s)
    s = math.sqrt(1.0 + r[2, 2] - r[0, 0] - r[1, 1]) * 2
    return ((r[0, 2] + r[2, 0]) / s, (r[1, 2] + r[2, 1]) / s, 0.25 * s, (r[1, 0] - r[0, 1]) / s)


def _kippung_grad(q) -> float:
    x, y, z, w = (float(v) for v in q)
    rz = 1 - 2 * (x * x + y * y)
    return math.degrees(math.acos(max(-1.0, min(1.0, rz))))


def versionen() -> Dict[str, Optional[str]]:
    import importlib.metadata as md
    out = {}
    for p in VERSIONS_PAKETE:
        try:
            out[p] = md.version(p)
        except md.PackageNotFoundError:
            out[p] = None
    return out


def laufen(device: Optional[str] = None, sc: Optional[Dict] = None, m: Optional[Dict] = None,
           entfernen: Sequence[str] = ()) -> Dict:
    """``entfernen``: Namen statischer Koerper, die fehlen sollen (Gegenprobe:
    ohne ``oberkorb_boden`` muessen die Glaeser durchfallen)."""
    import newton
    import warp as wp

    sc = sc or masse.load_szene()
    m = m or masse.load()
    nw = sc["newton"]
    pose = sc["pose"]
    sz = geometrie.baue(m, pose["oberkorb_auszug_m"], pose["unterkorb_auszug_m"])
    unbekannt = set(entfernen) - {k.name for k in sz.koerper}
    if unbekannt:
        raise ValueError(f"unbekannte Koerper: {sorted(unbekannt)}")
    wp.init()
    dev = device or ("cuda:0" if wp.is_cuda_available() else "cpu")

    def cfg(mu, dichte=0.0):
        s = newton.ModelBuilder.ShapeConfig(ke=float(nw["ke"]), kd=float(nw["kd"]), mu=float(mu),
                                            density=dichte, margin=0.0)
        s.mu_torsional = float(nw["reibung_torsion"])
        return s

    b = newton.ModelBuilder()
    newton.solvers.SolverMuJoCo.register_custom_attributes(b)
    statisch = 0
    for k in sz.koerper:
        if k.name in entfernen:
            continue
        mu = nw["reibung_korb"] if k.gruppe in ("oberkorb", "unterkorb", "glashalter") else nw["reibung_glas"]
        b.add_shape_box(-1, xform=wp.transform(tuple(float(v) for v in k.mitte), quat_aus_matrix(k.rot)),
                        hx=float(k.halb[0]), hy=float(k.halb[1]), hz=float(k.halb[2]), cfg=cfg(mu), label=k.name)
        statisch += 1
    b.add_ground_plane(cfg=cfg(nw["reibung_korb"]))
    g = m["glas"]
    r, h = g["durchmesser_m"] / 2.0, g["hoehe_m"]
    dichte = float(g["masse_kg"]) / (math.pi * r * r * h)
    glaeser = []
    # kopfueber: Zylinder ist symmetrisch, die Lage um 180 Grad um x gedreht
    # (Glasboden oben) aendert die Kollisionsgeometrie nicht
    q_kopf = (1.0, 0.0, 0.0, 0.0)
    for i, p in enumerate(sz.slots):
        bi = b.add_body(xform=wp.transform(tuple(float(v) for v in p), q_kopf), label=f"glas_{i + 1}")
        b.add_shape_cylinder(bi, radius=r, half_height=h / 2.0, cfg=cfg(nw["reibung_glas"], dichte), label=f"glas_{i + 1}")
        glaeser.append(bi)
    model = b.finalize(device=dev)
    massen = model.body_mass.numpy()[glaeser].tolist()
    solver = newton.solvers.SolverMuJoCo(model, use_mujoco_contacts=False, solver="newton",
                                         integrator="implicitfast", cone="elliptic", impratio=10.0,
                                         iterations=50, ls_iterations=50)
    pipeline = newton.CollisionPipeline(model)
    contacts = pipeline.contacts()
    s0, s1 = model.state(), model.state()
    control = model.control()
    newton.eval_fk(model, model.joint_q, model.joint_qd, s0)
    dt = float(nw["dt_s"])
    n_ein = int(round(float(nw["einschwingen_s"]) / dt))
    n_mess = int(round(float(nw["dauer_s"]) / dt))
    every = int(nw["messintervall_schritte"])
    start = s0.body_q.numpy()[glaeser][:, :3].copy()
    spur = []
    nan = False
    t0 = time.monotonic()
    for step in range(n_ein + n_mess + 1):
        if step >= n_ein and (step - n_ein) % every == 0:
            bq = s0.body_q.numpy()[glaeser]
            if not np.all(np.isfinite(bq)):
                nan = True
                break
            spur.append(bq.copy())
        if step == n_ein + n_mess:
            break
        pipeline.collide(s0, contacts)
        s0.clear_forces()
        solver.step(s0, s1, control, contacts, dt)
        s0, s1 = s1, s0
    wp.synchronize()
    wand = time.monotonic() - t0
    spur = np.array(spur)  # (t, glas, 7)
    ergebnis = {"device": dev, "versionen": versionen(), "dt_s": dt, "einschwingen_s": n_ein * dt,
                "mess_s": n_mess * dt, "wand_s": round(wand, 2), "statische_formen": statisch,
                "entfernt": sorted(entfernen), "glas_masse_kg": massen, "nan": nan, "glaeser": []}
    ok = not nan
    for i in range(len(glaeser)):
        if nan:
            break
        p = spur[:, i, :3]
        drift = float(np.max(np.linalg.norm(p - p[0], axis=1)))
        einsinken = float(sz.slots[i][2] - np.min(p[:, 2]))
        setzen = float(np.linalg.norm(p[0] - start[i]))
        # kopfueber gestartet: Kippung = Abweichung von 180 Grad
        kipp = max(abs(180.0 - _kippung_grad(q)) for q in spur[:, i, 3:7])
        e = {"glas": f"glas_{i + 1}", "slot_m": [round(float(v), 4) for v in sz.slots[i]],
             "drift_max_m": drift, "ende_minus_anfang_m": float(np.linalg.norm(p[-1] - p[0])),
             "einsinken_m": einsinken, "setzweg_einschwingen_m": setzen, "kippung_max_grad": kipp,
             "ende_m": [float(v) for v in p[-1]]}
        e["ok"] = drift < float(nw["drift_max_m"]) and einsinken < float(nw["einsinken_max_m"])
        ok = ok and e["ok"]
        ergebnis["glaeser"].append(e)
    ergebnis["ok"] = ok
    return ergebnis


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--device", help="cpu oder cuda:0 (Standard: GPU wenn vorhanden)")
    ap.add_argument("--out", help="JSON-Ergebnis")
    ap.add_argument("--ohne", action="append", default=[],
                    help="statischen Koerper weglassen (Gegenprobe, z. B. --ohne oberkorb_boden)")
    args = ap.parse_args(argv)
    e = laufen(args.device, entfernen=args.ohne)
    text = json.dumps(e, ensure_ascii=False, indent=1)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
    for g in e["glaeser"]:
        print(f"STABIL {g['glas']} ok={g['ok']} drift={g['drift_max_m'] * 1e3:.4f} mm "
              f"einsinken={g['einsinken_m'] * 1e3:.3f} mm kippung={g['kippung_max_grad']:.3f} Grad")
    print(f"STABILITAET ok={e['ok']} device={e['device']} wand={e['wand_s']} s nan={e['nan']}")
    return 0 if e["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
