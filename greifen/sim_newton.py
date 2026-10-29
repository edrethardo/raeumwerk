"""Newton-Teil der Greifdemo: ein Versuch = eine frisch aufgebaute Simulation.

Benutzt von ``scripts/demo_greifen.py`` und ``raeumwerk run``. Braucht Newton,
Warp und numpy (``ctx`` aus ``kontext()``). Der Ablauf faehrt die Soll-
Trajektorie aus ``greifen.plan`` ueber die Schnittstellen aus
``raeumwerk.backends`` (``SimRobot``, ``SimGripper``, ``SimCamera``); dieselbe
Schleife koennte spaeter ein Hardware-Backend bedienen.
"""
from __future__ import annotations

import math
import time

from raeumwerk.backends.sim import SimCamera, SimGripper, SimRobot

from . import bewertung

ROBOTER_GELENKE_EXTRA = ["finger_right"]
VERSIONS_PAKETE = ("newton", "warp-lang", "mujoco", "mujoco-warp", "numpy")


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


def jsonable(x):
    import numpy as np
    if isinstance(x, dict):
        return {k: jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple, set)):
        return [jsonable(v) for v in x]
    if isinstance(x, (np.floating, float)):
        v = float(x)
        return None if math.isnan(v) or math.isinf(v) else v
    if isinstance(x, (np.integer, np.bool_)):
        return x.item()
    if isinstance(x, np.ndarray):
        return jsonable(x.tolist())
    return x


def versionen() -> dict:
    import importlib.metadata as md
    out = {}
    for p in VERSIONS_PAKETE:
        try:
            out[p] = md.version(p)
        except md.PackageNotFoundError:
            out[p] = None
    return out


def kontext(cfg, sz, urdf, chain, device=None) -> dict:
    """Importiert Newton/Warp, waehlt das Geraet; ``ctx`` fuer ``Versuchslauf``."""
    import numpy as np
    import newton
    import warp as wp

    wp.init()
    dev = device or ("cuda:0" if wp.is_cuda_available() else "cpu")
    return {"np": np, "newton": newton, "wp": wp, "sz": sz, "chain": chain, "cfg": cfg,
            "urdf": urdf, "device": dev}


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
        sz, chain = c["sz"], c["chain"]
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
        self.zustand = st0
        shape_body = model.shape_body.numpy()
        self.tq = model.joint_target_q.numpy().copy()
        self.tqd = np.zeros_like(control.joint_target_qd.numpy())
        # Schnittstellen (raeumwerk.backends): Ablauf schreibt nur ueber diese
        self.roboter = SimRobot(self, chain.active)
        self.greifer = SimGripper(self, cfg.min_oeffnung)
        self.kamera = SimCamera(self, {"glas": self.glas_b})
        arm = [n for n in chain.active if n != "finger_left"]
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
        ifg = chain.index["finger_left"]
        t_sim0 = time.monotonic()
        for step in range(nsteps):
            t_now = step * dt
            q, qd, ph = pl.sample(t_now)
            self.roboter.setze_soll({n: q[chain.index[n]] for n in arm}, {n: qd[chain.index[n]] for n in arm})
            self.greifer.setze_soll(q[ifg], qd[ifg])
            control.joint_target_q.assign(self.tq)
            control.joint_target_qd.assign(self.tqd)
            pipeline.collide(st0, contacts)
            if step % every == 0:
                messen(t_now, ph)
            st0.clear_forces()
            solver.step(st0, st1, control, contacts, dt)
            st0, st1 = st1, st0
            self.zustand = st0
        pipeline.collide(st0, contacts)
        messen(nsteps * dt, "ende")
        wp.synchronize()
        self.wand_s = time.monotonic() - t_sim0
        self.sim_s = nsteps * dt
        pos, quat = self.kamera.objektlage("glas")
        m.update({
            "plan_ok": pl.ok, "plan_fehler": pl.fehler, "endlage_m": list(pos),
            "ziel_xy_m": list(self.v.ziel_xy), "stehhoehe_soll_m": sz.glas_mitte_z,
            "kippung_end_grad": _kippung_grad(quat),
            "zielfehler_xy_m": float(math.hypot(pos[0] - self.v.ziel_xy[0], pos[1] - self.v.ziel_xy[1])),
        })
        self.messung = m
        return m


def versuch_ausfuehren(ctx, v, planer) -> dict:
    """Plant, simuliert und bewertet einen Versuch; liefert den JSON-Datensatz."""
    sz = ctx["sz"]
    t_v = time.monotonic()
    pl = planer.plane(v)
    t_plan = time.monotonic() - t_v
    lauf = Versuchslauf(ctx, v, pl)
    lauf.bauen()
    m = lauf.fahren()
    bew = bewertung.bewerte(m, sz.bewertung)
    return jsonable({
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
        "messung": m, "bewertung": bew, "device": ctx["device"],
    })
