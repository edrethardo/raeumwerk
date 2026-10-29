"""Selbstkollision auf den Kollisionsquadern der URDF (CPU, numpy).

Quader-Quader-Test nach dem Trennachsensatz (15 Achsen). Paare aus Eltern-
und Kind-Link (direkt per Gelenk verbunden) sind ausgenommen, wie im Backend
(``collision_filter_parent``). Weitere Ausnahmen gibt es nicht.
"""
from __future__ import annotations

from itertools import combinations
from typing import Dict, List, Set, Tuple

import numpy as np

from .kinematics import Chain


def obb_penetration(c1: np.ndarray, r1: np.ndarray, h1: np.ndarray,
                    c2: np.ndarray, r2: np.ndarray, h2: np.ndarray) -> float:
    """Kleinste Ueberlappung entlang einer Trennachse (> 0: Quader durchdringen sich).

    c: Mitte, r: Rotation (Spalten = Quaderachsen), h: halbe Kantenlaengen.
    """
    axes = [r1[:, i] for i in range(3)] + [r2[:, i] for i in range(3)]
    for i in range(3):
        for k in range(3):
            v = np.cross(r1[:, i], r2[:, k])
            n = np.linalg.norm(v)
            if n > 1e-9:
                axes.append(v / n)
    d = c2 - c1
    best = np.inf
    for a in axes:
        p1 = np.sum(h1 * np.abs(r1.T @ a))
        p2 = np.sum(h2 * np.abs(r2.T @ a))
        overlap = p1 + p2 - abs(float(d @ a))
        if overlap < best:
            best = overlap
            if best < 0:
                return best
    return float(best)


class SelfCollision:
    def __init__(self, chain: Chain, margin: float = 0.0):
        self.chain = chain
        self.margin = margin
        adjacent: Set[Tuple[str, str]] = set()
        for j in chain.joints:
            adjacent.add(tuple(sorted((j.parent, j.child))))  # type: ignore[arg-type]
        self.adjacent = adjacent
        with_geo = [n for n in chain.order if chain.links[n].boxes]
        self.pairs: List[Tuple[str, str]] = [
            (a, b) for a, b in combinations(with_geo, 2) if tuple(sorted((a, b))) not in adjacent
        ]

    def world_boxes(self, q: np.ndarray) -> Dict[str, List[Tuple[np.ndarray, np.ndarray, np.ndarray]]]:
        poses = self.chain.fk_all(q)
        out = {}
        for name, link in self.chain.links.items():
            boxes = []
            for size, org in link.boxes:
                t = poses[name] @ org
                boxes.append((t[:3, 3], t[:3, :3], size / 2.0))
            out[name] = boxes
        return out

    def collisions(self, q: np.ndarray) -> List[Tuple[str, str, float]]:
        """Liste (Link A, Link B, Eindringtiefe m) aller kollidierenden Paare."""
        wb = self.world_boxes(q)
        hits = []
        for a, b in self.pairs:
            depth = max(
                (obb_penetration(c1, r1, h1, c2, r2, h2) for (c1, r1, h1) in wb[a] for (c2, r2, h2) in wb[b]),
                default=-np.inf,
            )
            if depth > -self.margin:
                hits.append((a, b, float(depth)))
        return hits
