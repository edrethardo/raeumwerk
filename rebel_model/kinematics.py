"""Kinematik aus der URDF (nur numpy): FK, geometrische Jacobi-Matrix, IK.

Liest jede URDF mit fixed/revolute/continuous/prismatic-Gelenken und
``mimic``. Ein Gelenkvektor ``q`` enthaelt die aktiven (nicht-mimic,
nicht-festen) Gelenke in URDF-Reihenfolge; ``Chain.active`` nennt sie.
"""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np


def rpy_to_matrix(r: float, p: float, y: float) -> np.ndarray:
    cr, sr, cp, sp, cy, sy = math.cos(r), math.sin(r), math.cos(p), math.sin(p), math.cos(y), math.sin(y)
    return np.array([
        [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
        [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
        [-sp, cp * sr, cp * cr],
    ])


def axis_angle(axis: np.ndarray, angle: float) -> np.ndarray:
    a = axis / np.linalg.norm(axis)
    k = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) + math.sin(angle) * k + (1 - math.cos(angle)) * (k @ k)


def rot_log(r: np.ndarray) -> np.ndarray:
    """Rotationsvektor (Achse * Winkel) einer Rotationsmatrix."""
    c = max(-1.0, min(1.0, (np.trace(r) - 1.0) / 2.0))
    ang = math.acos(c)
    if ang < 1e-9:
        return np.zeros(3)
    if math.pi - ang < 1e-6:
        # 180 Grad: Achse aus der Diagonale
        i = int(np.argmax(np.diag(r)))
        v = r[:, i] + np.eye(3)[:, i]
        return v / np.linalg.norm(v) * ang
    w = np.array([r[2, 1] - r[1, 2], r[0, 2] - r[2, 0], r[1, 0] - r[0, 1]])
    return w * ang / (2.0 * math.sin(ang))


def transform(rot: np.ndarray, pos: Sequence[float]) -> np.ndarray:
    t = np.eye(4)
    t[:3, :3] = rot
    t[:3, 3] = pos
    return t


@dataclass
class Joint:
    name: str
    type: str
    parent: str
    child: str
    origin: np.ndarray  # 4x4
    axis: np.ndarray
    lower: float = -math.inf
    upper: float = math.inf
    mimic: Optional[Tuple[str, float, float]] = None  # (Fuehrungsgelenk, Faktor, Offset)


@dataclass
class Link:
    name: str
    mass: float = 0.0
    boxes: List[Tuple[np.ndarray, np.ndarray]] = field(default_factory=list)  # (groesse, Ursprung 4x4)
    com: np.ndarray = field(default_factory=lambda: np.zeros(3))  # Schwerpunkt im Link-System (<inertial><origin>)


class Chain:
    def __init__(self, urdf: str):
        root = ET.fromstring(urdf)
        self.links: Dict[str, Link] = {}
        for el in root.findall("link"):
            ln = Link(el.get("name"))
            inert = el.find("inertial")
            if inert is not None and inert.find("mass") is not None:
                ln.mass = float(inert.find("mass").get("value"))
                ln.com = self._origin(inert.find("origin"))[:3, 3].copy()
            for col in el.findall("collision"):
                box = col.find("geometry/box")
                if box is None:
                    continue
                size = np.array([float(x) for x in box.get("size").split()])
                ln.boxes.append((size, self._origin(col.find("origin"))))
            self.links[ln.name] = ln
        self.joints: List[Joint] = []
        for el in root.findall("joint"):
            ax = el.find("axis")
            lim = el.find("limit")
            mim = el.find("mimic")
            j = Joint(
                name=el.get("name"),
                type=el.get("type"),
                parent=el.find("parent").get("link"),
                child=el.find("child").get("link"),
                origin=self._origin(el.find("origin")),
                axis=np.array([float(x) for x in (ax.get("xyz").split() if ax is not None else "1 0 0".split())]),
            )
            if lim is not None and j.type in ("revolute", "prismatic"):
                j.lower = float(lim.get("lower", "-inf"))
                j.upper = float(lim.get("upper", "inf"))
            if mim is not None:
                j.mimic = (mim.get("joint"), float(mim.get("multiplier", 1)), float(mim.get("offset", 0)))
            self.joints.append(j)
        self.by_child = {j.child: j for j in self.joints}
        self.by_name = {j.name: j for j in self.joints}
        children = {j.child for j in self.joints}
        roots = [n for n in self.links if n not in children]
        if len(roots) != 1:
            raise ValueError(f"URDF braucht genau eine Wurzel, gefunden: {roots}")
        self.root = roots[0]
        self.active = [j.name for j in self.joints if j.type != "fixed" and j.mimic is None]
        self.index = {n: i for i, n in enumerate(self.active)}
        self.lower = np.array([self.by_name[n].lower for n in self.active])
        self.upper = np.array([self.by_name[n].upper for n in self.active])
        # Links in topologischer Reihenfolge (Eltern vor Kindern)
        order, todo = [self.root], [self.root]
        while todo:
            p = todo.pop(0)
            for j in self.joints:
                if j.parent == p:
                    order.append(j.child)
                    todo.append(j.child)
        self.order = order

    @staticmethod
    def _origin(el) -> np.ndarray:
        if el is None:
            return np.eye(4)
        xyz = [float(x) for x in el.get("xyz", "0 0 0").split()]
        rpy = [float(x) for x in el.get("rpy", "0 0 0").split()]
        return transform(rpy_to_matrix(*rpy), xyz)

    # --- Gelenkwerte -----------------------------------------------------
    def joint_value(self, j: Joint, q: np.ndarray) -> float:
        if j.type == "fixed":
            return 0.0
        if j.mimic is not None:
            lead, mult, off = j.mimic
            return mult * float(q[self.index[lead]]) + off
        return float(q[self.index[j.name]])

    def zero(self) -> np.ndarray:
        return np.clip(np.zeros(len(self.active)), self.lower, self.upper)

    def q_from(self, values: Dict[str, float]) -> np.ndarray:
        q = self.zero()
        for k, v in values.items():
            q[self.index[k]] = v
        return q

    def within_limits(self, q: np.ndarray, tol: float = 1e-9) -> bool:
        return bool(np.all(q >= self.lower - tol) and np.all(q <= self.upper + tol))

    def random_q(self, rng: np.random.Generator, names: Optional[Sequence[str]] = None) -> np.ndarray:
        q = self.zero()
        for n in names or self.active:
            i = self.index[n]
            q[i] = rng.uniform(self.lower[i], self.upper[i])
        return q

    # --- Vorwaertskinematik ----------------------------------------------
    def _joint_motion(self, j: Joint, val: float) -> np.ndarray:
        if j.type in ("revolute", "continuous"):
            return transform(axis_angle(j.axis, val), (0, 0, 0))
        if j.type == "prismatic":
            return transform(np.eye(3), j.axis / np.linalg.norm(j.axis) * val)
        return np.eye(4)

    def fk_all(self, q: np.ndarray) -> Dict[str, np.ndarray]:
        """Weltlage (4x4) jedes Links; Wurzel = Weltursprung."""
        poses = {self.root: np.eye(4)}
        for name in self.order[1:]:
            j = self.by_child[name]
            poses[name] = poses[j.parent] @ j.origin @ self._joint_motion(j, self.joint_value(j, q))
        return poses

    def fk(self, q: np.ndarray, link: str, offset: Optional[Sequence[float]] = None) -> np.ndarray:
        t = self.fk_all(q)[link]
        if offset is not None:
            t = t @ transform(np.eye(3), offset)
        return t

    def path(self, link: str) -> List[Joint]:
        out = []
        while link != self.root:
            j = self.by_child[link]
            out.append(j)
            link = j.parent
        return out[::-1]

    def jacobian(self, q: np.ndarray, link: str, offset: Optional[Sequence[float]] = None,
                 use: Optional[Sequence[str]] = None) -> np.ndarray:
        """Geometrische Jacobi-Matrix 6 x len(active) (oben linear, unten Drehung)."""
        poses = self.fk_all(q)
        p = self.fk(q, link, offset)[:3, 3]
        jac = np.zeros((6, len(self.active)))
        use_set = set(use) if use is not None else set(self.active)
        for j in self.path(link):
            if j.type == "fixed":
                continue
            lead = j.mimic[0] if j.mimic else j.name
            if lead not in use_set:
                continue
            mult = j.mimic[1] if j.mimic else 1.0
            frame = poses[j.parent] @ j.origin
            a = frame[:3, :3] @ (j.axis / np.linalg.norm(j.axis))
            col = self.index[lead]
            if j.type == "prismatic":
                jac[:3, col] += mult * a
            else:
                o = frame[:3, 3]
                jac[:3, col] += mult * np.cross(a, p - o)
                jac[3:, col] += mult * a
        return jac

    # --- Inverse Kinematik -----------------------------------------------
    def ik(self, target: np.ndarray, link: str, q0: np.ndarray, use: Sequence[str],
           offset: Optional[Sequence[float]] = None, orientation: bool = True,
           tol_pos: float = 1e-5, tol_rot: float = 1e-4, iters: int = 300,
           restarts: int = 50, rng: Optional[np.random.Generator] = None) -> Tuple[np.ndarray, float, float, bool]:
        """Gedaempfte kleinste Quadrate mit Gelenkgrenzen und Neustarts.

        Liefert (q, Positionsfehler m, Winkelfehler rad, ok).
        """
        rng = rng or np.random.default_rng(0)
        idx = [self.index[n] for n in use]
        best = (q0.copy(), math.inf, math.inf)
        for attempt in range(restarts + 1):
            q = q0.copy() if attempt == 0 else self.random_q(rng, use)
            for k in range(len(q)):
                if k not in idx:
                    q[k] = q0[k]
            lam = 1e-2
            for _ in range(iters):
                t = self.fk(q, link, offset)
                ep = target[:3, 3] - t[:3, 3]
                er = rot_log(target[:3, :3] @ t[:3, :3].T) if orientation else np.zeros(3)
                pe, re = float(np.linalg.norm(ep)), float(np.linalg.norm(er))
                if pe < best[1] or (pe <= best[1] + 1e-12 and re < best[2]):
                    best = (q.copy(), pe, re)
                if pe < tol_pos and (not orientation or re < tol_rot):
                    return q, pe, re, True
                jac = self.jacobian(q, link, offset, use)[:, idx]
                if orientation:
                    e = np.concatenate([ep, er * 0.5])  # 0,5 m/rad Gewichtung
                    jac = np.vstack([jac[:3], jac[3:] * 0.5])
                else:
                    e, jac = ep, jac[:3]
                # Gelenke, die an einer Grenze anstehen und weiter hinaus wollen,
                # aus der Loesung nehmen (aktive Menge) und neu loesen.
                free = np.ones(len(idx), dtype=bool)
                qi = q[idx]
                for _pass in range(len(idx)):
                    jf = jac * free
                    dq = jf.T @ np.linalg.solve(jf @ jf.T + lam * lam * np.eye(len(e)), e)
                    push = ((qi <= self.lower[idx] + 1e-12) & (dq < 0)) | ((qi >= self.upper[idx] - 1e-12) & (dq > 0))
                    push &= free
                    if not push.any():
                        break
                    free &= ~push
                step = float(np.max(np.abs(dq)))
                if step > 0.3:
                    dq *= 0.3 / step
                q[idx] = np.clip(q[idx] + dq, self.lower[idx], self.upper[idx])
        q, pe, re = best
        return q, pe, re, False
