"""URDF-Generator: igus ReBeL 6 DOF auf 7. Achse mit Parallelgreifer.

Quelle des Modells ist ``config/robot.yaml``; die URDF ist ein Erzeugnis und
liegt nicht im Repo. Alle Kollisionen sind Quader (gleiche Geometrie fuer den
CPU-Selbstkollisionstest und das Backend). Nullpunkt aller Armgelenke ist die
Kerzenpose aus dem Datenblatt (Arm senkrecht).

Kette::

    rail --axis7 (prismatisch, +x)--> carriage --fest--> base_link
      --joint1..joint6--> link_1..link_6 --fest--> gripper_base (= Flansch)
      --finger_left (prismatisch, +y)
      --finger_right (prismatisch, -y, mimic finger_left)
      --fest--> payload (nur Masse, im TCP; nur wenn payload_kg > 0)

    python -m rebel_model.urdf_gen [--payload KG] [-o datei.urdf]
"""
from __future__ import annotations

import argparse
import math
import sys
from typing import List, Optional, Sequence, Tuple
from xml.sax.saxutils import quoteattr

from .config import RobotConfig, load

Box = Tuple[Tuple[float, float, float], Tuple[float, float, float]]  # (groesse, mitte)

ARM_JOINTS = ["joint1", "joint2", "joint3", "joint4", "joint5", "joint6"]
ALL_DRIVEN = ["axis7"] + ARM_JOINTS + ["finger_left"]


def _f(x: float) -> str:
    return f"{x:.12g}"


def _vec(v: Sequence[float]) -> str:
    return " ".join(_f(float(a)) for a in v)


def _box_inertia(m: float, size: Sequence[float]) -> Tuple[float, float, float]:
    x, y, z = size
    return (m * (y * y + z * z) / 12.0, m * (x * x + z * z) / 12.0, m * (x * x + y * y) / 12.0)


class _Builder:
    def __init__(self, name: str):
        self.parts: List[str] = [f'<robot name="{name}">']

    def link(self, name: str, mass: float, boxes: List[Box], com: Optional[Sequence[float]] = None,
             inertia: Optional[Sequence[float]] = None) -> None:
        p = [f"  <link name={quoteattr(name)}>"]
        if mass > 0:
            if com is None or inertia is None:
                # Masse gleichmaessig auf den groessten Quader
                size, center = max(boxes, key=lambda b: b[0][0] * b[0][1] * b[0][2])
                com = center
                inertia = _box_inertia(mass, size)
            ixx, iyy, izz = inertia
            p.append(
                f'    <inertial><origin xyz="{_vec(com)}" rpy="0 0 0"/><mass value="{_f(mass)}"/>'
                f'<inertia ixx="{_f(ixx)}" ixy="0" ixz="0" iyy="{_f(iyy)}" iyz="0" izz="{_f(izz)}"/></inertial>'
            )
        for size, center in boxes:
            geo = f'<geometry><box size="{_vec(size)}"/></geometry>'
            org = f'<origin xyz="{_vec(center)}" rpy="0 0 0"/>'
            p.append(f"    <visual>{org}{geo}</visual>")
            p.append(f"    <collision>{org}{geo}</collision>")
        p.append("  </link>")
        self.parts.append("\n".join(p))

    def joint(self, name: str, jtype: str, parent: str, child: str, xyz: Sequence[float],
              axis: Optional[Sequence[float]] = None, lower: float = 0.0, upper: float = 0.0,
              effort: float = 0.0, velocity: float = 0.0, mimic: Optional[str] = None) -> None:
        p = [f'  <joint name={quoteattr(name)} type="{jtype}">',
             f'    <parent link="{parent}"/><child link="{child}"/>',
             f'    <origin xyz="{_vec(xyz)}" rpy="0 0 0"/>']
        if jtype != "fixed":
            p.append(f'    <axis xyz="{_vec(axis or (0, 0, 1))}"/>')
            p.append(f'    <limit lower="{_f(lower)}" upper="{_f(upper)}" effort="{_f(effort)}" velocity="{_f(velocity)}"/>')
        if mimic:
            p.append(f'    <mimic joint="{mimic}" multiplier="1" offset="0"/>')
        p.append("  </joint>")
        self.parts.append("\n".join(p))

    def text(self) -> str:
        return "\n".join(self.parts + ["</robot>", ""])


def build_urdf(cfg: Optional[RobotConfig] = None, payload_kg: float = 0.0) -> str:
    cfg = cfg or load()
    a, s, g = cfg.arm, cfg.achse7, cfg.greifer
    b = _Builder("rebel6_axis7_gripper")

    # --- 7. Achse --------------------------------------------------------
    L, W, H = s["laenge_m"], s["breite_m"], s["hoehe_m"]
    end = (L - s["hub_m"] - s["schlitten_laenge_m"]) / 2.0
    if end < 0:
        raise ValueError("achse7.laenge_m < hub_m + schlitten_laenge_m")
    b.link("rail", s["masse_schiene_kg"], [((L, W, H), (L / 2.0, 0.0, H / 2.0))])
    ch = s["schlitten_hoehe_m"]
    b.link("carriage", s["masse_schlitten_kg"], [((s["schlitten_laenge_m"], W, ch), (0.0, 0.0, ch / 2.0))])
    b.joint("axis7", "prismatic", "rail", "carriage", (end + s["schlitten_laenge_m"] / 2.0, 0.0, H),
            axis=(1, 0, 0), lower=0.0, upper=s["hub_m"], effort=s["kraft_n"], velocity=s["geschwindigkeit_m_s"])
    b.joint("carriage_to_base", "fixed", "carriage", "base_link", (0.0, 0.0, ch))

    # --- Arm -------------------------------------------------------------
    j1 = a["j1_hoehe_m"]
    fw = a["fuss_breite_m"]
    gw, hw = a["glied_breite_m"], a["hand_breite_m"]
    platte = 0.03  # Fussplatte (Annahme), darueber eine schmalere Saeule
    saeule = 0.11
    b.link("base_link", cfg.massen["base_link"], [
        ((fw, fw, platte), (0.0, 0.0, platte / 2.0)),
        ((saeule, saeule, j1 - platte), (0.0, 0.0, platte + (j1 - platte) / 2.0)),
    ], com=(0.0, 0.0, j1 / 2.0), inertia=_box_inertia(cfg.massen["base_link"], (fw, fw, j1)))

    seg = [  # (Link, Laenge bis zum naechsten Gelenk, Breite)
        ("link_1", a["j2_hoehe_m"] - j1, gw),
        ("link_2", a["oberarm_m"], gw),
        ("link_3", a["j4_ab_j3_m"], gw),
        ("link_4", a["unterarm_m"] - a["j4_ab_j3_m"], gw),
        ("link_5", a["j6_ab_j5_m"], hw),
        ("link_6", a["hand_m"] - a["j6_ab_j5_m"], a["flansch_durchmesser_m"]),
    ]
    for (lname, ln, w) in seg:
        if ln <= 0:
            raise ValueError(f"{lname}: Laenge {ln} <= 0")
        b.link(lname, cfg.massen[lname], [((w, w, ln), (0.0, 0.0, ln / 2.0))])

    vel = math.radians(a["geschwindigkeit_grad_s"])
    parents = ["base_link", "link_1", "link_2", "link_3", "link_4", "link_5"]
    offsets = [j1] + [ln for (_, ln, _) in seg[:5]]
    for gel, parent, child, off in zip(cfg.gelenke, parents, [x[0] for x in seg], offsets):
        b.joint(gel.name, "revolute", parent, child, (0.0, 0.0, off), axis=gel.achse,
                lower=gel.unten, upper=gel.oben, effort=a["moment_nm"], velocity=vel)

    # --- Greifer ---------------------------------------------------------
    kl, kb, kt = g["koerper_laenge_m"], g["koerper_breite_m"], g["koerper_tiefe_m"]
    b.link("gripper_base", g["masse_kg"], [((kt, kb, kl), (0.0, 0.0, kl / 2.0))])
    b.joint("flange", "fixed", "link_6", "gripper_base", (0.0, 0.0, seg[-1][1]))
    fb, fd, fl = g["finger_breite_m"], g["finger_dicke_m"], g["finger_laenge_m"]
    y0 = cfg.min_oeffnung / 2.0 + fd / 2.0  # Fingermitte bei q = 0 (zu)
    for side, sign in (("left", 1.0), ("right", -1.0)):
        b.link(f"finger_{side}", g["finger_masse_kg"], [((fb, fd, fl), (0.0, 0.0, fl / 2.0))])
        b.joint(f"finger_{side}", "prismatic", "gripper_base", f"finger_{side}", (0.0, sign * y0, kl),
                axis=(0, sign, 0), lower=0.0, upper=cfg.finger_hub, effort=g["kraft_n"],
                velocity=g["geschwindigkeit_m_s"], mimic=("finger_left" if side == "right" else None))
    if payload_kg > 0:
        r = 0.03
        i = 0.4 * payload_kg * r * r
        b.link("payload", payload_kg, [], com=(0, 0, 0), inertia=(i, i, i))
        b.joint("tcp_payload", "fixed", "gripper_base", "payload", (0.0, 0.0, g["tcp_ab_flansch_m"]))
    return b.text()


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("-o", "--out", help="Zieldatei (Standard: stdout)")
    ap.add_argument("--payload", type=float, default=0.0, help="Nutzlast im TCP in kg")
    ap.add_argument("--config", help="robot.yaml (Standard: config/robot.yaml)")
    args = ap.parse_args(argv)
    text = build_urdf(load(args.config), payload_kg=args.payload)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
