#!/usr/bin/env python3
"""Glas-Greifdemo in Newton: ReBeL greift ein Glas, hebt, versetzt, setzt ab.

Gestartet von ``scripts/run_greifen.sh`` mit dem Python des Isaac-Lab-venv
(Newton 1.6). Rein headless, keine Netzwerkschnittstelle. Auf einem geteilten
GPU-Rechner nur ueber die GPU-Warteschlange/den Lock.

    demo_greifen.py --art demo|variation|negativ --out DIR [--device cpu] [--versuche N]

* ``demo``      ein Versuch mit der Startlage aus ``config/scene.yaml``
* ``variation`` ``variation.versuche`` Versuche, Startlage um +-2 cm gestreut
                (fester Seed); jeder Versuch in einer eigenen, frisch
                aufgebauten Simulation (nacheinander)
* ``negativ``   absichtlich falscher Greifpunkt; muss als Fehlversuch mit
                Grund ``nicht_gegriffen`` erkannt werden

Ablauf je Versuch: ``greifen.plan`` plant die Soll-Trajektorie (IK, fester
Seed), der Simulator faehrt sie mit PD-Antrieben und Geschwindigkeits-
vorsteuerung, misst alle ``simulation.messintervall_schritte`` die Glaslage und
die Kontakte, ``greifen.bewertung`` entscheidet Erfolg/Fehlergruende.

Ausgabe in ``--out``: ``versuch-NN.json`` je Versuch, ``zusammenfassung.json``.
Exit 0, wenn die Erwartung der Versuchsart erfuellt ist (demo: Erfolg;
negativ: erkannter Fehlversuch; variation: alle Versuche gelaufen).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

ROBOTER_GELENKE_EXTRA = ["finger_right"]


def _quat_rot(qx, qy, qz, qw):
    import numpy as np
    return np.array([
        [1 - 2 * (qy * qy + qz * qz), 2 * (qx * qy - qz * qw), 2 * (qx * qz + qy * qw)],
        [2 * (qx * qy + qz * qw), 1 - 2 * (qx * qx + qz * qz), 2 * (qy * qz - qx * qw)],
        [2 * (qx * qz - qy * qw), 2 * (qy * qz + qx * qw), 1 - 2 * (qx * qx + qy * qy)],
    ])


def _kippung_grad(quat) -> float:
    rz = _quat_rot(*quat)[2, 2]
    return math.degrees(math.acos(max(-1.0, min(1.0, float(rz)))))


def _jsonable(x):
    import numpy as np
    if isinstance(x, dict):
        return {k: _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple, set)):
        return [_jsonable(v) for v in x]
    if isinstance(x, (np.floating, float)):
        v = float(x)
        return None if math.isnan(v) or math.isinf(v) else v
    if isinstance(x, (np.integer, np.bool_)):
        return x.item()
    if isinstance(x, np.ndarray):
        return _jsonable(x.tolist())
    return x


class Versuchslauf:
    """Ein Versuch = eine frisch aufgebaute Newton-Simulation mit einer Welt.

    Mehrere Versuche als parallele Welten in einer Simulation wurden
    ausprobiert und verworfen: ab Welt 1 liefen die Antriebe in Newton 1.6.1
    mit diesem Modell wild (Gelenke ueber die Grenzen, Glas fiel durch den
    Tisch), Welt 0 war korrekt; siehe docs/greifdemo.md.
    """

    def __init__(self, ctx, versuch, plan):
        self.ctx, self.v, self.pl = ctx, versuch, plan

    def bauen(self):
        c = self.ctx
        newton, wp = c["newton"], c["wp"]
        sz, chain, cfg = c["sz"], c["chain"], c["cfg"]
        k, g = sz.kontakt, sz.greifen

        def shape_cfg(mu, density=0.0):
            s = newton.ModelBuilder.ShapeConfig(ke=float(k["ke"]), kd=float(k["kd"]), mu=float(mu),
                                                density=density, margin=0.0)
            s.mu_torsional = float(k["reibung_torsion"])
            return s

        b = newton.ModelBuilder()
        newton.solvers.SolverMuJoCo.register_custom_attributes(b)
        b.default_shape_cfg = shape_cfg(sz.tisch["reibung"])
        b.add_urdf(c["urdf"], floating=False, enable_self_collisions=False, collapse_fixed_joints=False)
        names = chain.active + ROBOTER_GELENKE_EXTRA
        jidx = {l.split("/")[-1]: j for j, l in enumerate(b.joint_label)}
        qi = {n: b.joint_q_start[jidx[n]] for n in names}
        di = {n: b.joint_qd_start[jidx[n]] for n in names}
        bl = {l.split("/")[-1]: i for i, l in enumerate(b.body_label)}
        robot_bodies = set(range(b.body_count))
        finger_bodies = {bl["finger_left"], bl["finger_right"]}
        finger_shapes = {s for s in range(b.shape_count) if b.shape_body[s] in finger_bodies}
        for s in finger_shapes:
            b.shape_material_mu[s] = float(k["reibung_finger"])
        gravcomp = b.custom_attributes["mujoco:gravcomp"]
        if gravcomp.values is None:
            gravcomp.values = {}
        for i in robot_bodies:
            gravcomp.values[i] = 1.0  # Schwerkraftkompensation wie in der Robotersteuerung
        mode_pos = int(newton.JointTargetMode.POSITION)
        gains = {"axis7": (5.0e4, 1.0e3), "finger_left": (float(g["finger_ke"]), float(g["finger_kd"]))}
        gains["finger_right"] = gains["finger_left"]
        q_home = self.pl.sample(0.0)[0]
        for n in names:
            src = "finger_left" if n == "finger_right" else n
            ke, kd = gains.get(n, (1.0e4, 3.0e2))
            b.joint_target_ke[di[n]] = ke
            b.joint_target_kd[di[n]] = kd
            b.joint_target_mode[di[n]] = mode_pos
            b.joint_q[qi[n]] = float(q_home[chain.index[src]])
            b.joint_target_q[di[n]] = float(q_home[chain.index[src]])
        # Tisch (statisch) und Glas (freier Koerper, Vollzylinder mit Glasmasse)
        tm, tg = sz.tisch["mitte_xy_m"], sz.tisch["groesse_m"]
        tisch = b.add_shape_box(-1, xform=wp.transform((tm[0], tm[1], tg[2] / 2.0), wp.quat_identity()),
                                hx=tg[0] / 2.0, hy=tg[1] / 2.0, hz=tg[2] / 2.0,
                                cfg=shape_cfg(sz.tisch["reibung"]), label="tisch")
        r, h = sz.glas_radius, float(sz.glas["hoehe_m"])
        dichte = float(sz.glas["masse_kg"]) / (math.pi * r * r * h)
        glas_b = b.add_body(xform=wp.transform((self.v.start_xy[0], self.v.start_xy[1], sz.glas_mitte_z),
                                               wp.quat_identity()), label="glas")
        glas_s = b.add_shape_cylinder(glas_b, radius=r, half_height=h / 2.0,
                                      cfg=shape_cfg(sz.glas["reibung"], dichte), label="glas")
        b.add_ground_plane(cfg=shape_cfg(k["reibung_boden"]))
        robot_shapes = {s for s in range(b.shape_count) if b.shape_body[s] in robot_bodies}
        self.model = b.finalize(device=c["device"])
        self.qi, self.di = qi, di
        self.glas_b, self.glas_s, self.tisch = glas_b, glas_s, tisch
        self.robot_shapes, self.finger_shapes = robot_shapes, finger_shapes
        # Plausibilitaet: Antriebswerte am erwarteten Index
        ke_np = self.model.joint_target_ke.numpy()
        if abs(float(ke_np[di["axis7"]]) - gains["axis7"][0]) > 1e-3:
            raise RuntimeError("Antriebswerte passen nicht zum Gelenkindex")
        self.glas_masse = float(self.model.body_mass.numpy()[glas_b])

    def fahren(self):
        c = self.ctx
        np, newton, wp = c["np"], c["newton"], c["wp"]
        sz, chain, cfg = c["sz"], c["chain"], c["cfg"]
        model, pl = self.model, self.pl
        dt = float(sz.simulation["dt_s"])
        every = int(sz.simulation["messintervall_schritte"])
        solver = newton.solvers.SolverMuJoCo(model, use_mujoco_contacts=False, solver="newton",
                                             integrator="implicitfast", cone="elliptic", impratio=10.0,
                                             iterations=50, ls_iterations=50)
        pipeline = newton.CollisionPipeline(model)
        contacts = pipeline.contacts()
        st0, st1 = model.state(), model.state()
        control = model.control()
        newton.eval_fk(model, model.joint_q, model.joint_qd, st0)
        shape_body = model.shape_body.numpy()
        tq = model.joint_target_q.numpy().copy()
        tqd = np.zeros_like(control.joint_target_qd.numpy())
        zeiten = pl.phase_zeiten()
        start = st0.body_q.numpy()[self.glas_b][:3].copy()
        m = {"hub_max_m": -math.inf, "transport_min_hub_m": math.inf, "tisch_durchdringung_max_m": 0.0,
             "finger_durchdringung_max_m": 0.0, "glas_v_max_m_s": 0.0, "kippung_max_grad": 0.0,
             "gelenk_folgefehler_max": {}, "phasen_ende": {}, "nan": False, "startlage_m": start.tolist()}
        st = {"last_pos": None, "last_phase": None}
        pair_tisch = self.tisch
        glas_s = self.glas_s

        def messen(t_now, ph):
            bq = st0.body_q.numpy()
            jq = st0.joint_q.numpy()
            n = int(contacts.rigid_contact_count.numpy()[0])
            if n:
                s0 = contacts.rigid_contact_shape0.numpy()[:n]
                s1 = contacts.rigid_contact_shape1.numpy()[:n]
                p0 = contacts.rigid_contact_point0.numpy()[:n]
                p1 = contacts.rigid_contact_point1.numpy()[:n]
                nrm = contacts.rigid_contact_normal.numpy()[:n]
                m0 = contacts.rigid_contact_margin0.numpy()[:n]
                m1 = contacts.rigid_contact_margin1.numpy()[:n]
                for kk in range(n):
                    a, b = int(s0[kk]), int(s1[kk])
                    pair = {a, b}
                    is_tisch = pair_tisch in pair and bool(pair & self.robot_shapes)
                    is_finger = glas_s in pair and bool(pair & self.finger_shapes)
                    if not (is_tisch or is_finger):
                        continue
                    pts = []
                    for sh, pt in ((a, p0[kk]), (b, p1[kk])):
                        bb = shape_body[sh]
                        if bb < 0:
                            pts.append(np.asarray(pt))
                        else:
                            tr = bq[bb]
                            pts.append(_quat_rot(*tr[3:7]) @ pt + tr[:3])
                    # Separation wie newton contact_surface_separation (< 0 = Durchdringung)
                    sep = float(nrm[kk] @ (pts[1] - pts[0]) - (m0[kk] + m1[kk]))
                    key = "tisch_durchdringung_max_m" if is_tisch else "finger_durchdringung_max_m"
                    if -sep > m[key]:
                        m[key] = -sep
                        if is_tisch:
                            m["tisch_kontakt_phase"] = ph
            tr = bq[self.glas_b]
            if not np.all(np.isfinite(tr)):
                m["nan"] = True
                return
            pos = tr[:3]
            tilt = _kippung_grad(tr[3:7])
            m["kippung_max_grad"] = max(m["kippung_max_grad"], tilt)
            if st["last_pos"] is not None:
                m["glas_v_max_m_s"] = max(m["glas_v_max_m_s"],
                                          float(np.linalg.norm(pos - st["last_pos"])) / (every * dt))
            st["last_pos"] = pos.copy()
            hub = float(pos[2] - start[2])
            if ph in ("anheben", "verfahren"):
                m["hub_max_m"] = max(m["hub_max_m"], hub)
            if zeiten["anheben"][1] <= t_now < zeiten["absetzen"][0]:
                m["transport_min_hub_m"] = min(m["transport_min_hub_m"], hub)
            q_soll = pl.sample(t_now)[0]
            for nme in chain.active:
                if nme == "finger_left" and ph in ("greifen", "anheben", "verfahren", "absetzen"):
                    continue  # Finger stehen am Glas an (gewollt)
                err = abs(float(jq[self.qi[nme]]) - float(q_soll[chain.index[nme]]))
                err = math.degrees(err) if nme.startswith("joint") else err * 1e3
                m["gelenk_folgefehler_max"][nme] = max(m["gelenk_folgefehler_max"].get(nme, 0.0), err)
            if st["last_phase"] is not None and ph != st["last_phase"]:
                fl, fr = float(jq[self.qi["finger_left"]]), float(jq[self.qi["finger_right"]])
                m["phasen_ende"][st["last_phase"]] = {
                    "t_s": round(t_now, 3), "glas_m": [round(float(x), 5) for x in pos],
                    "kippung_grad": round(tilt, 3), "oeffnung_m": round(cfg.min_oeffnung + fl + fr, 5),
                    "finger_links_rechts_m": [round(fl, 5), round(fr, 5)]}
            st["last_phase"] = ph

        nsteps = int(math.ceil(pl.dauer / dt))
        t_sim0 = time.monotonic()
        for step in range(nsteps):
            t_now = step * dt
            q, qd, ph = pl.sample(t_now)
            for nme in chain.active:
                tq[self.di[nme]] = q[chain.index[nme]]
                tqd[self.di[nme]] = qd[chain.index[nme]]
            tq[self.di["finger_right"]] = q[chain.index["finger_left"]]
            tqd[self.di["finger_right"]] = qd[chain.index["finger_left"]]
            control.joint_target_q.assign(tq)
            control.joint_target_qd.assign(tqd)
            pipeline.collide(st0, contacts)
            if step % every == 0:
                messen(t_now, ph)
            st0.clear_forces()
            solver.step(st0, st1, control, contacts, dt)
            st0, st1 = st1, st0
        pipeline.collide(st0, contacts)
        messen(nsteps * dt, "ende")
        wp.synchronize()
        self.wand_s = time.monotonic() - t_sim0
        self.sim_s = nsteps * dt
        tr = st0.body_q.numpy()[self.glas_b]
        m.update({
            "plan_ok": pl.ok, "plan_fehler": pl.fehler, "endlage_m": tr[:3].tolist(),
            "ziel_xy_m": list(self.v.ziel_xy), "stehhoehe_soll_m": sz.glas_mitte_z,
            "kippung_end_grad": _kippung_grad(tr[3:7]),
            "zielfehler_xy_m": float(math.hypot(tr[0] - self.v.ziel_xy[0], tr[1] - self.v.ziel_xy[1])),
        })
        self.messung = m
        return m


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--art", choices=["demo", "variation", "negativ"], default="demo")
    ap.add_argument("--out", required=True)
    ap.add_argument("--device", default=None)
    ap.add_argument("--versuche", type=int, default=None, help="nur die ersten N Versuche (zum Ausprobieren)")
    ap.add_argument("--seed", type=int, default=0, help="Seed der IK-Neustarts")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    meta: dict = {"art": args.art, "seed_ik": args.seed, "ok": False}
    t0 = time.monotonic()
    ergebnisse: list = []
    try:
        import importlib.metadata as md

        import numpy as np
        import newton
        import warp as wp

        from greifen import bewertung, szene
        from greifen.plan import Planer, versuche
        from rebel_model.config import load
        from rebel_model.kinematics import Chain
        from rebel_model.urdf_gen import build_urdf

        for p in ("newton", "warp-lang", "mujoco", "mujoco-warp"):
            try:
                meta[f"{p}_version"] = md.version(p)
            except md.PackageNotFoundError:
                meta[f"{p}_version"] = None

        cfg = load()
        sz = szene.load()
        meta["seed_variation"] = int(sz.variation["seed"])
        urdf = build_urdf(cfg)
        chain = Chain(urdf)
        planer = Planer(chain, cfg, sz, seed=args.seed)
        liste = versuche(sz, args.art)
        if args.versuche:
            liste = liste[: args.versuche]
        meta["versuche_geplant"] = len(liste)

        wp.init()
        device = args.device or ("cuda:0" if wp.is_cuda_available() else "cpu")
        meta["device"] = device
        ctx = {"np": np, "newton": newton, "wp": wp, "sz": sz, "chain": chain, "cfg": cfg,
               "urdf": urdf, "device": device}
        wand_sum = 0.0
        for v in liste:
            t_v = time.monotonic()
            pl = planer.plane(v)
            t_plan = time.monotonic() - t_v
            print("PLAN", json.dumps({"nr": v.nr, "ok": pl.ok, "fehler": pl.fehler, "dauer_s": round(pl.dauer, 3)}),
                  flush=True)
            lauf = Versuchslauf(ctx, v, pl)
            lauf.bauen()
            m = lauf.fahren()
            wand_sum += lauf.wand_s
            bew = bewertung.bewerte(m, sz.bewertung)
            rec = _jsonable({
                "versuch": v.as_dict(),
                "erfolg": bew["erfolg"], "gruende": bew["gruende"], "gruende_text": bew["texte"],
                "position": {"start_m": m["startlage_m"], "ende_m": m["endlage_m"], "ziel_xy_m": m["ziel_xy_m"],
                             "fehler_xy_m": m["zielfehler_xy_m"]},
                "kippung_grad": {"ende": m["kippung_end_grad"], "max": m["kippung_max_grad"]},
                "dauer": {"ablauf_sim_s": round(pl.dauer, 3),
                          "phasen_s": {p: [round(a, 3), round(b, 3)] for p, (a, b) in pl.phase_zeiten().items()},
                          "wand_sim_s": round(lauf.wand_s, 2), "wand_planung_s": round(t_plan, 2)},
                "plan": {"ok": pl.ok, "fehler": pl.fehler, "tcp_soll_m": pl.tcp_soll,
                         "ik_max_fehler_m": pl.ik_max_fehler_m, "tisch_abstand_min_m": pl.tisch_abstand_min_m},
                "modell": {"glas_masse_kg": lauf.glas_masse, "dt_s": float(sz.simulation["dt_s"])},
                "messung": m, "bewertung": bew, "device": device,
            })
            ergebnisse.append(rec)
            (out_dir / f"versuch-{v.nr:02d}.json").write_text(json.dumps(rec, indent=2))
            print("VERSUCH", json.dumps({"nr": v.nr, "erfolg": rec["erfolg"], "gruende": rec["gruende"],
                                         "fehler_xy_mm": round(m["zielfehler_xy_m"] * 1e3, 2),
                                         "kippung_grad": round(m["kippung_end_grad"], 3),
                                         "hub_max_mm": round(m["hub_max_m"] * 1e3, 1),
                                         "wand_s": round(lauf.wand_s, 1)}), flush=True)
        zus = bewertung.zusammenfassung(ergebnisse)
        meta["zusammenfassung"] = zus
        meta["wand_sim_summe_s"] = round(wand_sum, 2)
        if args.art == "demo":
            meta["erwartung"] = "Erfolg"
            meta["ok"] = zus["erfolge"] == zus["versuche"] == 1
        elif args.art == "negativ":
            meta["erwartung"] = "Fehlversuch mit Grund nicht_gegriffen"
            meta["ok"] = zus["versuche"] >= 1 and zus["erfolge"] == 0 and all(
                "nicht_gegriffen" in e["gruende"] for e in ergebnisse)
        else:
            meta["erwartung"] = "alle Versuche gelaufen"
            meta["ok"] = zus["versuche"] == len(liste) > 0
    except Exception as e:  # noqa: BLE001
        meta["error"] = f"{type(e).__name__}: {e}"
        meta["traceback"] = traceback.format_exc()[-4000:]
    finally:
        meta["total_s"] = round(time.monotonic() - t0, 2)
        (out_dir / "zusammenfassung.json").write_text(json.dumps(_jsonable(meta), indent=2))
        print("GREIFEN_RESULT", json.dumps(_jsonable({"art": meta["art"], "ok": meta["ok"],
                                                      "zusammenfassung": meta.get("zusammenfassung"),
                                                      "error": meta.get("error")})), flush=True)
    return 0 if meta["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
