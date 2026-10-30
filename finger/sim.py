"""Newton-Lauf mit den eigenen Fingern (Kollisionsquader aus ``finger.kollision``).

``FingerLauf`` ersetzt im Ausraeum-Lauf (``ausraeumen.sim_newton.Lauf``) die
Fingerquader des URDF durch die CAD-nahe Kontur (Flanken, Kern, Lippe, weiche
Auflagen mit eigenem Reibwert) und schaltet die Kollision der Fussplatte ab
(sie steht fest auf der Arbeitsplatte). ``TellerLauf`` setzt statt der Glaeser
Teller ein: flache Scheibe (Fahne) mit Randwulst als Kapselring, hochkant.
"""
from __future__ import annotations

import math

import numpy as np

from ausraeumen import sim_newton as sn
from spuelmaschine.stabilitaet import quat_aus_matrix

from . import kollision as FK


class FingerLauf(sn.Lauf):
    finger = None   # finger.parameter.Finger (setzt finger.a1.versuch)
    sz = None       # config/finger_a1.yaml

    def finger_formen(self, b, bl, shape_cfg) -> set:
        newton, wp = self.ctx["newton"], self.ctx["wp"]
        f = self.finger
        k = f.p["kontakt"]
        aus = ~int(newton.ShapeFlags.COLLIDE_SHAPES)
        seiten = {bl["finger_left"]: 1.0, bl["finger_right"]: -1.0}
        fest = {bl[n] for n in ("rail", "carriage") if n in bl}
        for s in range(b.shape_count):
            if b.shape_body[s] in seiten or b.shape_body[s] in fest:
                b.shape_flags[s] = int(b.shape_flags[s]) & aus
        fd = float(self.cfg.greifer["finger_dicke_m"])
        iv = float(f.p["anschluss"]["innen_versatz_mm"]) * 1e-3
        formen = set()
        for body, sign in seiten.items():
            # Fingersystem -> Gliedsystem: links (Backe bei +y) zeigt die Innenseite nach -y
            M = np.diag([-1.0, -1.0, 1.0]) if sign > 0 else np.eye(3)
            off = np.array([0.0, -sign * (fd / 2.0 + iv), 0.0])
            for q in FK.quader(f):
                c = M @ q.mitte + off
                R = M @ q.rot
                mu = float(k["reibung_auflage"] if q.weich else k["reibung_finger"])
                s = b.add_shape_box(body, xform=wp.transform(tuple(float(v) for v in c), quat_aus_matrix(R)),
                                    hx=float(q.halb[0]), hy=float(q.halb[1]), hz=float(q.halb[2]),
                                    cfg=shape_cfg(mu, 0.0), label=f"finger_{q.name}")
                formen.add(s)
        return formen


class TellerLauf(FingerLauf):
    def bauen(self):
        # Teller: Kraft ueber die Fingersteifigkeit (Ziel "ganz zu", Kontakt an der Fahne)
        g = self.w.aufbau.a["greifer"]
        iv = float(self.finger.p["anschluss"]["innen_versatz_mm"]) * 1e-3
        fahne = float(self.finger.p["teller"]["fahne_dicke_mm"]) * 1e-3
        q_kontakt = (fahne + 2.0 * iv - self.cfg.min_oeffnung) / 2.0
        g["finger_ke"] = float(self.sz["teller"]["greifkraft_n"]) / q_kontakt
        super().bauen()

    def objekte(self, b, shape_cfg) -> None:
        wp = self.ctx["wp"]
        si = self.w.aufbau.a["simulation"]
        t = self.sz["teller"]
        ft = self.finger.p["teller"]
        r = float(t["durchmesser_m"]) / 2.0
        wulst = float(ft["wulst_dicke_mm"]) * 1e-3 / 2.0
        fahne = float(ft["fahne_dicke_mm"]) * 1e-3 / 2.0
        n = int(t["wulst_segmente"])
        rr = r - wulst
        seg = 2.0 * math.pi * rr / n
        v_scheibe = math.pi * rr * rr * 2.0 * fahne
        v_kapsel = math.pi * wulst * wulst * seg + 4.0 / 3.0 * math.pi * wulst ** 3
        dichte = float(t["masse_kg"]) / (v_scheibe + n * v_kapsel)
        cfg = shape_cfg(si["reibung_glas"], dichte)
        Rx = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0]])  # Scheibenachse z -> y
        for i, g in enumerate(self.w.glas_start):
            # Koerpersystem: z senkrecht (hochkant, Kippung wie beim Glas), Tellernormale y
            bi = b.add_body(xform=wp.transform(tuple(float(v) for v in g.mitte), quat_aus_matrix(np.eye(3))), label=g.name)
            s0 = b.add_shape_cylinder(bi, xform=wp.transform((0.0, 0.0, 0.0), quat_aus_matrix(Rx)), radius=rr,
                                      half_height=fahne, cfg=cfg, label=f"{g.name}_fahne")
            self.glas_b.append(bi)
            self.glas_s.append(s0)
            self.objekt_von_shape[s0] = i
            for k in range(n):
                phi = 2.0 * math.pi * (k + 0.5) / n
                c = (rr * math.cos(phi), 0.0, rr * math.sin(phi))
                th = -phi
                Ry = np.array([[math.cos(th), 0.0, math.sin(th)], [0.0, 1.0, 0.0], [-math.sin(th), 0.0, math.cos(th)]])
                s = b.add_shape_capsule(bi, xform=wp.transform(c, quat_aus_matrix(Ry)), radius=wulst,
                                        half_height=seg / 2.0, cfg=cfg, label=f"{g.name}_wulst_{k}")
                self.objekt_von_shape[s] = i
