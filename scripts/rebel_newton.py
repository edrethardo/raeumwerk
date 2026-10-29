#!/usr/bin/env python3
"""Backend-Test Newton: ReBeL-Modell laden, alle Achsen fahren, Selbstkollision.

Gestartet von ``scripts/run_rebel_newton.sh`` mit dem Python des
Isaac-Lab-venv (Newton 1.6). Rein headless, keine Netzwerkschnittstelle.
Auf einem geteilten GPU-Rechner nur ueber die GPU-Warteschlange/den Lock.

Ablauf:
1. URDF aus ``config/robot.yaml`` erzeugen (mit Nutzlast = max. Nutzlast -
   Greifermasse im TCP), mit Selbstkollision in Newton laden.
2. Massen, Grenzen und Mimic-Kopplung im geladenen Modell pruefen.
3. FK-Abgleich: Newton ``eval_fk`` gegen ``rebel_model.kinematics`` auf den
   Datenblattposen und 50 Zufallsposen.
4. Selbstkollision: Newton-Kollisionspipeline auf freien und
   selbstschneidenden Posen (Kontakte zwischen nicht benachbarten Gliedern).
5. Fahrt: SolverMuJoCo, Positionsantriebe; jedes Gelenk faehrt nacheinander
   zwei Ziele mit Datenblattgeschwindigkeit an, danach Haltezeit. Erreichter
   Wert je Ziel wird protokolliert. Toleranz: Drehgelenk < 1 Grad,
   Linearachse/Finger < 1 mm.

Ergebnis: JSON nach ``--result``; Exit 0 nur, wenn alles bestanden ist.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

TOL_REV = math.radians(1.0)
TOL_LIN = 1e-3


def _label_list(model, names):
    for n in names:
        v = getattr(model, n, None)
        if v:
            return list(v)
    return []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", required=True)
    ap.add_argument("--urdf-out", help="erzeugte URDF hier ablegen")
    ap.add_argument("--hold-s", type=float, default=1.5)
    ap.add_argument("--dt", type=float, default=0.002)
    ap.add_argument("--device", default=None)
    args = ap.parse_args()

    out: dict = {"backend": "newton", "ok": False, "checks": {}}
    t0 = time.monotonic()
    try:
        import numpy as np
        import warp as wp
        import newton
        import importlib.metadata as md

        from rebel_model.collision import SelfCollision
        from rebel_model.config import load
        from rebel_model.kinematics import Chain
        from rebel_model.urdf_gen import build_urdf

        for p in ("newton", "warp-lang", "mujoco", "mujoco-warp"):
            try:
                out[f"{p}_version"] = md.version(p)
            except md.PackageNotFoundError:
                out[f"{p}_version"] = None

        cfg = load()
        payload = cfg.nutzlast_test
        urdf = build_urdf(cfg, payload_kg=payload)
        if args.urdf_out:
            Path(args.urdf_out).write_text(urdf)
        chain = Chain(urdf)
        sc = SelfCollision(chain)
        out["payload_kg"] = payload

        wp.init()
        device = args.device or ("cuda:0" if wp.is_cuda_available() else "cpu")
        out["device"] = device

        builder = newton.ModelBuilder()
        newton.solvers.SolverMuJoCo.register_custom_attributes(builder)
        builder.add_urdf(urdf, floating=False, enable_self_collisions=True, collapse_fixed_joints=False)
        builder.add_ground_plane()

        jlabels = list(builder.joint_label) if getattr(builder, "joint_label", None) else list(builder.joint_key)

        def jname(lbl: str) -> str:
            return lbl.split("/")[-1]

        jidx = {jname(l): i for i, l in enumerate(jlabels)}
        qstart = list(builder.joint_q_start)
        dstart = list(builder.joint_qd_start)
        dof = {n: dstart[jidx[n]] for n in chain.active + ["finger_right"]}
        qi = {n: qstart[jidx[n]] for n in chain.active + ["finger_right"]}

        mode_pos = int(newton.JointTargetMode.POSITION)
        # PD-Antriebe mit Geschwindigkeitsvorsteuerung (joint_target_qd), damit
        # die Rampe ohne Schleppfehler laeuft; Kraft/Moment begrenzt die URDF.
        gains = {"axis7": (5.0e4, 1.0e3), "finger_left": (2.0e3, 1.0e2)}
        for n in chain.active:
            ke, kd = gains.get(n, (1.0e4, 3.0e2))
            builder.joint_target_ke[dof[n]] = ke
            builder.joint_target_kd[dof[n]] = kd
            builder.joint_target_mode[dof[n]] = mode_pos
        # finger_right: kein eigener Antrieb, folgt ueber mimic
        builder.joint_target_ke[dof["finger_right"]] = 0.0
        builder.joint_target_kd[dof["finger_right"]] = 0.0
        try:
            builder.joint_target_mode[dof["finger_right"]] = int(newton.JointTargetMode.NONE)
        except AttributeError:
            pass

        model = builder.finalize(device=device)
        out["startup_s"] = round(time.monotonic() - t0, 2)

        # --- 2. Modellpruefung ------------------------------------------
        blabels = [l.split("/")[-1] for l in _label_list(model, ["body_label", "body_key"])]
        masses = dict(zip(blabels, [float(m) for m in model.body_mass.numpy()]))
        arm_mass = sum(masses.get(n, 0.0) for n in ["base_link"] + [f"link_{i}" for i in range(1, 7)])
        out["masses_kg"] = {k: round(v, 4) for k, v in masses.items()}
        lo = model.joint_limit_lower.numpy()
        hi = model.joint_limit_upper.numpy()
        lim_err = max(max(abs(lo[dof[n]] - chain.by_name[n].lower), abs(hi[dof[n]] - chain.by_name[n].upper))
                      for n in chain.active)
        mimic_n = int(getattr(model, "constraint_mimic_count", 0) or 0)
        out["checks"]["masses"] = {
            "arm_kg": round(arm_mass, 4), "payload_kg": round(masses.get("payload", 0.0), 4),
            "ok": abs(arm_mass - cfg.arm["masse_gesamt_kg"]) < 1e-3 and abs(masses.get("payload", 0) - payload) < 1e-3,
        }
        out["checks"]["limits"] = {"max_abs_err": float(lim_err), "ok": bool(lim_err < 1e-5)}
        eff = model.joint_effort_limit.numpy()
        out["effort_limit"] = {n: float(eff[dof[n]]) for n in chain.active}
        out["checks"]["mimic"] = {"constraints": mimic_n, "ok": mimic_n >= 1}
        shape_body = model.shape_body.numpy()
        body_of_shape = [blabels[b] if b >= 0 else "world" for b in shape_body]
        out["shape_count"] = int(model.shape_count)

        # --- 3. FK-Abgleich ---------------------------------------------
        state = model.state()

        def set_q(qvec):
            jq = model.joint_q.numpy().copy()
            for n in chain.active:
                jq[qi[n]] = qvec[chain.index[n]]
            jq[qi["finger_right"]] = qvec[chain.index["finger_left"]]
            jq_wp = wp.array(jq, dtype=wp.float32, device=device)
            newton.eval_fk(model, jq_wp, model.joint_qd, state)
            return state.body_q.numpy()

        rng = np.random.default_rng(3)
        D = math.radians
        poses = [chain.zero(), chain.q_from({"joint2": D(90)}), chain.q_from({"joint2": D(90), "joint3": D(-90)}),
                 chain.q_from({"joint2": D(90), "joint5": D(90)}), chain.q_from({"joint1": D(90), "joint2": D(90)})]
        poses += [chain.random_q(rng) for _ in range(50)]
        fk_dev = 0.0
        gb = blabels.index("gripper_base")
        for q in poses:
            bq = set_q(q)
            ours = chain.fk(q, "gripper_base")[:3, 3]
            fk_dev = max(fk_dev, float(np.linalg.norm(bq[gb][:3] - ours)))
        out["checks"]["fk_newton_vs_numpy"] = {"poses": len(poses), "max_dev_m": fk_dev, "ok": fk_dev < 1e-4}

        # --- 4. Selbstkollision -----------------------------------------
        pipeline = newton.CollisionPipeline(model)
        contacts = pipeline.contacts()
        adjacent = sc.adjacent

        def _quat_rot(qx, qy, qz, qw):
            return np.array([
                [1 - 2 * (qy * qy + qz * qz), 2 * (qx * qy - qz * qw), 2 * (qx * qz + qy * qw)],
                [2 * (qx * qy + qz * qw), 1 - 2 * (qx * qx + qz * qz), 2 * (qy * qz - qx * qw)],
                [2 * (qx * qz - qy * qw), 2 * (qy * qz + qx * qw), 1 - 2 * (qx * qx + qy * qy)],
            ])

        def self_pairs(q):
            """Paare nicht benachbarter Glieder mit Durchdringung (Separation < 0).

            Die Pipeline meldet auch Kontakte innerhalb des Kontaktabstands
            (Vorschau); gezaehlt wird nur echte Durchdringung, berechnet wie
            ``contact_surface_separation`` in Newton.
            """
            bq = set_q(q)
            pipeline.collide(state, contacts)
            n = int(contacts.rigid_contact_count.numpy()[0])
            s0 = contacts.rigid_contact_shape0.numpy()[:n]
            s1 = contacts.rigid_contact_shape1.numpy()[:n]
            p0 = contacts.rigid_contact_point0.numpy()[:n]
            p1 = contacts.rigid_contact_point1.numpy()[:n]
            nrm = contacts.rigid_contact_normal.numpy()[:n]
            m0 = contacts.rigid_contact_margin0.numpy()[:n]
            m1 = contacts.rigid_contact_margin1.numpy()[:n]
            pairs: dict = {}
            for k in range(n):
                a, b = int(s0[k]), int(s1[k])
                ba, bb = body_of_shape[a], body_of_shape[b]
                if "world" in (ba, bb) or ba == bb:
                    continue  # Boden
                pair = tuple(sorted((ba, bb)))
                if pair in adjacent:
                    continue
                w = []
                for sh, pt in ((a, p0[k]), (b, p1[k])):
                    t = bq[shape_body[sh]]
                    w.append(_quat_rot(*t[3:7]) @ pt + t[:3])
                sep = float(nrm[k] @ (w[1] - w[0]) - (m0[k] + m1[k]))
                if sep < -1e-4:
                    pairs[pair] = min(sep, pairs.get(pair, 0.0))
            return pairs

        cases = {
            "frei_kerze": ({}, False),
            "frei_j2_90": ({"joint2": D(90)}, False),
            "frei_j3_140": ({"joint3": D(140)}, False),
            "frei_greifer_offen_achse_ende": ({"axis7": 1.0, "finger_left": 0.05}, False),
            "selbstschnitt_greifer_link1": ({"joint3": D(140), "joint5": D(95)}, True),
            "selbstschnitt_hand_fuss": ({"joint2": D(90), "joint3": D(140)}, True),
        }
        coll = {}
        coll_ok = True
        for name, (vals, expect) in cases.items():
            q = chain.q_from(vals)
            pairs = self_pairs(q)
            cpu = sorted(tuple(sorted((a, b))) for a, b, _ in sc.collisions(q))
            hit = bool(pairs)
            ok = hit == expect and (bool(cpu) == expect)
            coll_ok &= ok
            coll[name] = {"newton_pairs": {f"{p[0]}|{p[1]}": round(d, 5) for p, d in sorted(pairs.items())},
                          "cpu_pairs": [list(p) for p in cpu], "erwartet": expect, "ok": ok}
        out["checks"]["self_collision"] = {"cases": coll, "ok": coll_ok}

        # --- 5. Fahrt ---------------------------------------------------
        solver = newton.solvers.SolverMuJoCo(model)
        s0, s1 = model.state(), model.state()
        control = model.control()
        newton.eval_fk(model, model.joint_q, model.joint_qd, s0)
        dt = args.dt
        tgt = model.joint_target_q.numpy().copy() if model.joint_target_q is not None else None
        if tgt is None or control.joint_target_qd is None:
            raise RuntimeError("model.joint_target_q/joint_target_qd fehlt")
        tgt_qd = np.zeros_like(control.joint_target_qd.numpy())

        vel = {n: chain.by_name[n] for n in chain.active}
        vmax = {n: (cfg.achse7["geschwindigkeit_m_s"] if n == "axis7" else
                    cfg.greifer["geschwindigkeit_m_s"] if n == "finger_left" else
                    math.radians(cfg.arm["geschwindigkeit_grad_s"])) for n in chain.active}

        cur = {n: 0.0 for n in chain.active}
        sim_time = 0.0
        steps = 0
        max_track = {n: 0.0 for n in chain.active}

        def step_to(n, goal, hold):
            nonlocal sim_time, steps, s0, s1
            start = cur[n]
            dist = goal - start
            t_move = abs(dist) / vmax[n]
            nsteps = int(math.ceil((t_move + hold) / dt))
            for k in range(nsteps):
                tt = min(1.0, (k + 1) * dt / t_move) if t_move > 0 else 1.0
                cur[n] = start + dist * tt
                tq = tgt.copy()
                for m in chain.active:
                    tq[dof[m]] = cur[m]
                tqd = tgt_qd.copy()
                if tt < 1.0:
                    tqd[dof[n]] = dist / t_move
                control.joint_target_q.assign(tq)
                control.joint_target_qd.assign(tqd)
                s0.clear_forces()
                solver.step(s0, s1, control, None, dt)
                s0, s1 = s1, s0
                steps += 1
            sim_time += nsteps * dt

        def ranges(n):
            j = chain.by_name[n]
            if n == "axis7":
                return [0.8 * j.upper, 0.2 * j.upper]
            if n == "finger_left":
                return [0.045, 0.01]
            return [0.6 * j.upper, 0.6 * j.lower]

        moves = []
        drive_ok = True
        t_sim0 = time.monotonic()
        order = ["axis7"] + [n for n in chain.active if n.startswith("joint")] + ["finger_left"]
        for n in order:
            for goal in ranges(n):
                step_to(n, goal, args.hold_s)
                wp.synchronize()
                jq = s0.joint_q.numpy()
                reached = float(jq[qi[n]])
                err = reached - goal
                lin = chain.by_name[n].type == "prismatic"
                tol = TOL_LIN if lin else TOL_REV
                others = max(abs(float(jq[qi[m]]) - cur[m]) for m in chain.active if m != n)
                rec = {
                    "gelenk": n, "ziel": goal, "erreicht": reached,
                    "fehler": err, "einheit": "m" if lin else "rad",
                    "fehler_mm_oder_grad": err * 1e3 if lin else math.degrees(err),
                    "toleranz": "1 mm" if lin else "1 Grad",
                    "max_abweichung_andere_gelenke": others,
                    "ok": abs(err) < tol, "t_sim_s": round(sim_time, 3),
                }
                if n == "finger_left":
                    fr = float(jq[qi["finger_right"]])
                    rec["finger_right_mimic"] = fr
                    rec["mimic_fehler_mm"] = (fr - reached) * 1e3
                    rec["ok"] = rec["ok"] and abs(fr - goal) < TOL_LIN
                drive_ok &= rec["ok"]
                moves.append(rec)
                print("MOVE", json.dumps(rec), flush=True)
        # zurueck in die Kerze
        for n in reversed(order):
            step_to(n, 0.0, 0.0)
        step_to("joint1", 0.0, args.hold_s)
        wp.synchronize()
        jq = s0.joint_q.numpy()
        home_err = {n: float(jq[qi[n]]) for n in chain.active}
        out["checks"]["drive"] = {"moves": moves, "ok": drive_ok, "home_q_after": home_err,
                                  "sim_time_s": round(sim_time, 2), "steps": steps, "dt": dt,
                                  "wall_s": round(time.monotonic() - t_sim0, 2)}
        out["ok"] = all(c.get("ok") for c in out["checks"].values())
    except Exception as e:  # noqa: BLE001
        out["error"] = f"{type(e).__name__}: {e}"
        out["traceback"] = traceback.format_exc()[-4000:]
    finally:
        out["total_s"] = round(time.monotonic() - t0, 2)
        with open(args.result, "w") as f:
            json.dump(out, f, indent=2)
        summary = {k: (v.get("ok") if isinstance(v, dict) else v) for k, v in out.get("checks", {}).items()}
        print("REBEL_RESULT", json.dumps({"ok": out["ok"], "checks": summary, "error": out.get("error")}), flush=True)
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
