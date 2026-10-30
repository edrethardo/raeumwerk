"""Newton-Lauf des Ausraeumens: eine frisch aufgebaute Simulation je Versuch.

Statische Szene aus ``ausraeumen.geometrie`` (Maschine, offene Tuer, Koerbe,
Glashalter, Arbeitsplatte, Schraenke, Zwischenablage), der ReBeL an der
Schienenlage (URDF mit ``xform``, Kollision = Quader) und vier freie Glaeser
(Vollzylinder, Glasmasse) kopfueber in den Slots. Loeser wie Greifdemo und
Stabilitaetstest: MuJoCo-Warp ueber Newton, Newton-Kollisionspipeline,
elliptischer Reibkegel, dt 2 ms, Schwerkraftkompensation der Armglieder.

Gemessen wird alle ``messintervall_schritte``: Lage und Drehung jedes Glases,
die TCP-Lage, und aus den Kontakten die tiefste Durchdringung Roboter <->
Korb/Glashalter, Tuer, Arbeitsplatte, Zwischenablage sowie Finger <-> Glas,
jeweils dem Glas zugeordnet, das gerade bearbeitet wird (Phasenpraefix).
Die Bewertung macht ``ausraeumen.bewertung``.
"""
from __future__ import annotations

import math
import time
from typing import Dict, List, Optional

from greifen.sim_newton import _kippung_grad, jsonable, versionen  # noqa: F401  (versionen: Aufrufer)
from spuelmaschine.stabilitaet import quat_aus_matrix

ROBOTER_GELENKE_EXTRA = ["finger_right"]
KONTAKT_GRUPPEN = {"oberkorb": "korb", "glashalter": "korb", "klemmbacke": "korb", "tuer": "tuer",
                   "arbeitsplatte": "arbeitsplatte", "zwischenablage": "zwischenablage",
                   "tellerhalter": "korb", "tellerstaender": "staender", "podest": "arbeitsplatte"}


def kontext(device=None) -> dict:
    import numpy as np
    import newton
    import warp as wp

    wp.init()
    dev = device or ("cuda:0" if wp.is_cuda_available() else "cpu")
    return {"np": np, "newton": newton, "wp": wp, "device": dev}


def glas_nr(phase: str) -> Optional[int]:
    """'3:aushub' -> 2 (Index des Glases), sonst None."""
    kopf = phase.split(":", 1)[0]
    return int(kopf) - 1 if kopf.isdigit() else None


def klemmbacken(welt, nr: int, uebermass: float, hoehe: float):
    """Negativtest: zwei Quader vor/hinter (Kuechen-y) dem Glas ``nr`` mit Uebermass.

    In y, weil die Finger beim Griff von oben entlang x schliessen: die Backen
    halten das Glas fest, ohne den Fingern im Weg zu sein."""
    from spuelmaschine import geometrie as sg
    g = welt.glas_start[nr]
    r = welt.glas_r
    zb = g.mitte[2] - welt.glas_h / 2.0
    out = []
    for seite, s in (("vorne", 1.0), ("hinten", -1.0)):
        innen = g.mitte[1] + s * (r - uebermass)
        lo = (g.mitte[0] - 0.02, min(innen, innen + s * 0.01), zb)
        hi = (g.mitte[0] + 0.02, max(innen, innen + s * 0.01), zb + hoehe)
        out.append(sg.quader(f"klemmbacke_{seite}", "klemmbacke", lo, hi))
    return out


class Lauf:
    def __init__(self, ctx, welt, plan, cfg, chain, urdf, aufzeichnen_fps=None):
        self.ctx, self.w, self.pl, self.cfg, self.chain, self.urdf = ctx, welt, plan, cfg, chain, urdf
        self.aufzeichnen_fps = aufzeichnen_fps
        self.aufzeichner = None
        self.zusatz = []  # weitere statische Koerper (Negativtest)

    def bauen(self):
        c = self.ctx
        newton, wp, np = c["newton"], c["wp"], c["np"]
        a = self.w.aufbau.a
        si, gr = a["simulation"], a["greifer"]

        def shape_cfg(mu, density=0.0):
            s = newton.ModelBuilder.ShapeConfig(ke=float(si["ke"]), kd=float(si["kd"]), mu=float(mu),
                                                density=density, margin=0.0)
            s.mu_torsional = float(si["reibung_torsion"])
            return s

        b = newton.ModelBuilder()
        newton.solvers.SolverMuJoCo.register_custom_attributes(b)
        b.default_shape_cfg = shape_cfg(si["reibung_platte"])
        T = self.w.lage.matrix()
        b.add_urdf(self.urdf, xform=wp.transform(tuple(float(v) for v in T[:3, 3]), quat_aus_matrix(T[:3, :3])),
                   floating=False, enable_self_collisions=False, collapse_fixed_joints=False)
        chain = self.chain
        names = chain.active + ROBOTER_GELENKE_EXTRA
        jidx = {l.split("/")[-1]: j for j, l in enumerate(b.joint_label)}
        qi = {n: b.joint_q_start[jidx[n]] for n in names}
        di = {n: b.joint_qd_start[jidx[n]] for n in names}
        bl = {l.split("/")[-1]: i for i, l in enumerate(b.body_label)}
        robot_bodies = set(range(b.body_count))
        finger_bodies = {bl["finger_left"], bl["finger_right"]}
        finger_shapes = self.finger_formen(b, bl, shape_cfg)
        gravcomp = b.custom_attributes["mujoco:gravcomp"]
        if gravcomp.values is None:
            gravcomp.values = {}
        for i in robot_bodies:
            gravcomp.values[i] = 1.0
        mode_pos = int(newton.JointTargetMode.POSITION)
        gains = {"axis7": (5.0e4, 1.0e3), "finger_left": (float(gr["finger_ke"]), float(gr["finger_kd"]))}
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
        robot_shapes = {s for s in range(b.shape_count) if b.shape_body[s] in robot_bodies}
        # statische Szene (Podest und Boden ohne Physik: die Schiene ist fest, Boden = Ebene)
        gruppe_von: Dict[int, str] = {}
        for k in list(self.w.statisch) + list(self.zusatz):
            if k.name in ("podest", "boden"):
                continue
            mu = si["reibung_korb"] if k.gruppe in ("oberkorb", "unterkorb", "glashalter") else si["reibung_platte"]
            if k.gruppe == "klemmbacke":
                mu = a["negativtest"]["backe_reibung"]
            s = b.add_shape_box(-1, xform=wp.transform(tuple(float(v) for v in k.mitte), quat_aus_matrix(k.rot)),
                                hx=float(k.halb[0]), hy=float(k.halb[1]), hz=float(k.halb[2]), cfg=shape_cfg(mu),
                                label=k.name)
            gruppe_von[s] = KONTAKT_GRUPPEN.get(k.gruppe, k.gruppe)
        b.add_ground_plane(cfg=shape_cfg(si["reibung_korb"]))
        self.glas_b, self.glas_s = [], []
        self.objekt_von_shape: Dict[int, int] = {}
        self.objekte(b, shape_cfg)
        self.model = b.finalize(device=c["device"])
        self.body_label = [l.split("/")[-1] for l in b.body_label]
        self.qi, self.di = qi, di
        self.robot_shapes, self.finger_shapes = robot_shapes, finger_shapes
        self.gruppe_von = gruppe_von
        self.gripper_b = bl["gripper_base"]
        ke_np = self.model.joint_target_ke.numpy()
        if abs(float(ke_np[di["axis7"]]) - gains["axis7"][0]) > 1e-3:
            raise RuntimeError("Antriebswerte passen nicht zum Gelenkindex")
        self.glas_masse = [float(v) for v in self.model.body_mass.numpy()[self.glas_b]]
        self.n_statisch = len(gruppe_von)

    def finger_formen(self, b, bl, shape_cfg) -> set:
        """Kollisionsformen der Finger (Standard: die Quader aus dem URDF, Reibwert der
        Finger). Unterklassen ersetzen sie (z. B. eigene Fingerkontur, finger.sim)."""
        si = self.w.aufbau.a["simulation"]
        finger_bodies = {bl["finger_left"], bl["finger_right"]}
        shapes = {s for s in range(b.shape_count) if b.shape_body[s] in finger_bodies}
        for s in shapes:
            b.shape_material_mu[s] = float(si["reibung_finger"])
        return shapes

    def objekte(self, b, shape_cfg) -> None:
        """Freie Koerper (Standard: Glaeser als Vollzylinder). Fuellt ``glas_b`` (Koerper)
        und ``objekt_von_shape`` (Form -> Objektindex, fuer die Fingerdurchdringung)."""
        wp = self.ctx["wp"]
        si = self.w.aufbau.a["simulation"]
        r, h = self.w.glas_r, self.w.glas_h
        dichte = float(self.w.aufbau.m["glas"]["masse_kg"]) / (math.pi * r * r * h)
        for i, g in enumerate(self.w.glas_start):
            bi = b.add_body(xform=wp.transform(tuple(float(v) for v in g.mitte), quat_aus_matrix(g.rot)), label=g.name)
            si_ = b.add_shape_cylinder(bi, radius=r, half_height=h / 2.0, cfg=shape_cfg(si["reibung_glas"], dichte),
                                       label=g.name)
            self.glas_b.append(bi)
            self.glas_s.append(si_)
            self.objekt_von_shape[si_] = i

    def fahren(self) -> dict:
        from raeumwerk.backends.sim import SimGripper, SimRobot

        c = self.ctx
        np, newton, wp = c["np"], c["newton"], c["wp"]
        chain, cfg, pl = self.chain, self.cfg, self.pl
        model = self.model
        si = self.w.aufbau.a["simulation"]
        dt = float(si["dt_s"])
        every = int(si["messintervall_schritte"])
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
        self.roboter = SimRobot(self, chain.active)
        self.greifer = SimGripper(self, cfg.min_oeffnung)
        arm = [n for n in chain.active if n != "finger_left"]
        tcp_off = np.array([0.0, 0.0, float(cfg.greifer["tcp_ab_flansch_m"])])
        glas_s = dict(self.objekt_von_shape) or {s: i for i, s in enumerate(self.glas_s)}
        n_g = len(self.glas_b)
        spur = {"t": [], "phase": [], "glas": [], "tcp": []}
        kontakt = [dict() for _ in range(n_g + 1)]  # je Glas (+ ohne Glas): Gruppe -> (tiefe, phase)
        finger = [0.0] * n_g
        finger_phase = [""] * n_g
        nan = [False]

        def messen(t_now, ph):
            bq = st0.body_q.numpy()
            if not np.all(np.isfinite(bq)):
                nan[0] = True
                return
            gi = glas_nr(ph)
            slot = n_g if gi is None else gi
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
                    a_, b_ = int(s0[kk]), int(s1[kk])
                    rob = a_ in self.robot_shapes or b_ in self.robot_shapes
                    if not rob:
                        continue
                    other = b_ if a_ in self.robot_shapes else a_
                    grp = self.gruppe_von.get(other)
                    is_finger = other in glas_s and (a_ in self.finger_shapes or b_ in self.finger_shapes)
                    if grp is None and not is_finger:
                        continue
                    pts = []
                    for sh, pt in ((a_, p0[kk]), (b_, p1[kk])):
                        bb = shape_body[sh]
                        pts.append(np.asarray(pt) if bb < 0 else _rot(np, bq[bb][3:7]) @ pt + bq[bb][:3])
                    sep = float(nrm[kk] @ (pts[1] - pts[0]) - (m0[kk] + m1[kk]))
                    if is_finger:
                        gidx = glas_s[other]
                        if -sep > finger[gidx]:
                            finger[gidx] = -sep
                            finger_phase[gidx] = ph
                    elif -sep > kontakt[slot].get(grp, (0.0, ""))[0]:
                        kontakt[slot][grp] = (-sep, ph)
            gb = bq[self.gripper_b]
            spur["t"].append(t_now)
            spur["phase"].append(ph)
            spur["glas"].append(bq[self.glas_b].copy())
            spur["tcp"].append(_rot(np, gb[3:7]) @ tcp_off + gb[:3])

        nsteps = int(math.ceil(pl.dauer / dt))
        ifg = chain.index["finger_left"]
        rec = None
        if self.aufzeichnen_fps:
            from greifen.aufzeichnung import Aufzeichner
            rec = self.aufzeichner = Aufzeichner(dt, self.aufzeichnen_fps)
        t_sim0 = time.monotonic()
        for step in range(nsteps):
            t_now = step * dt
            q, qd, ph = pl.sample(t_now)
            if rec is not None and rec.faellig(step):
                rec.add(t_now, st0.body_q.numpy(), ph)
            self.roboter.setze_soll({n: q[chain.index[n]] for n in arm}, {n: qd[chain.index[n]] for n in arm})
            self.greifer.setze_soll(q[ifg], qd[ifg])
            control.joint_target_q.assign(self.tq)
            control.joint_target_qd.assign(self.tqd)
            pipeline.collide(st0, contacts)
            if step % every == 0:
                messen(t_now, ph)
                if nan[0]:
                    break
            st0.clear_forces()
            solver.step(st0, st1, control, contacts, dt)
            st0, st1 = st1, st0
            self.zustand = st0
        if not nan[0]:
            pipeline.collide(st0, contacts)
            messen(nsteps * dt, "ende")
        if rec is not None and rec.faellig(nsteps):
            rec.add(nsteps * dt, st0.body_q.numpy(), "ende")
        wp.synchronize()
        self.wand_s = time.monotonic() - t_sim0
        self.sim_s = nsteps * dt
        return {"t": np.array(spur["t"]), "phase": spur["phase"], "glas": np.array(spur["glas"]),
                "tcp": np.array(spur["tcp"]), "kontakt": kontakt, "finger_durchdringung_m": finger,
                "finger_durchdringung_phase": finger_phase,
                "nan": nan[0], "dt": dt}


def _rot(np, q):
    x, y, z, w = (float(v) for v in q)
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
