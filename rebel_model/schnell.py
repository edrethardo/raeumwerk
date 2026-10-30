"""Schnelle Kinematik fuer viele Ziele: FK, Jacobi-Matrix und IK als numpy-Batch.

``SchnellKette`` liest die serielle Kette bis zu einem Link aus einer
``Chain`` (feste Gelenke werden zusammengefasst) und rechnet FK und
Jacobi-Matrix fuer N Gelenkvektoren auf einmal. ``ik_batch`` ist dieselbe
gedaempfte kleinste-Quadrate-IK wie ``Chain.ik`` (gleiche Schrittweite,
Daempfung, Gewichtung 0,5 m/rad, aktive Menge an den Gelenkgrenzen), nur
fuer alle Ziele gleichzeitig. ``SchnellChain`` ist eine ``Chain``, deren
``ik`` diesen Kern nutzt (Neustarts mit demselben Zufallsstrom wie
``Chain.ik``) und deren ``fk_all`` die Gelenkdrehungen vorberechnet.
"""
from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

import numpy as np

from .kinematics import Chain, transform


def _rodrigues(axis: np.ndarray, ang: np.ndarray) -> np.ndarray:
    """(N,) Winkel um eine feste Einheitsachse -> (N, 3, 3)."""
    k = np.array([[0.0, -axis[2], axis[1]], [axis[2], 0.0, -axis[0]], [-axis[1], axis[0], 0.0]])
    k2 = k @ k
    s, c = np.sin(ang), np.cos(ang)
    return np.eye(3)[None] + s[:, None, None] * k[None] + (1.0 - c)[:, None, None] * k2[None]


def rot_log_batch(r: np.ndarray) -> np.ndarray:
    """Rotationsvektor je Matrix (N, 3, 3) -> (N, 3); wie ``kinematics.rot_log``."""
    tr = np.trace(r, axis1=1, axis2=2)
    c = np.clip((tr - 1.0) / 2.0, -1.0, 1.0)
    ang = np.arccos(c)
    w = np.stack([r[:, 2, 1] - r[:, 1, 2], r[:, 0, 2] - r[:, 2, 0], r[:, 1, 0] - r[:, 0, 1]], axis=1)
    s = np.sin(ang)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = w * (ang / (2.0 * np.where(s == 0.0, 1.0, s)))[:, None]
    out[ang < 1e-9] = 0.0
    for i in np.nonzero(math.pi - ang < 1e-6)[0]:
        d = np.diag(r[i])
        j = int(np.argmax(d))
        v = r[i][:, j] + np.eye(3)[:, j]
        out[i] = v / np.linalg.norm(v) * ang[i]
    return out


class SchnellKette:
    """Serielle Kette Wurzel -> ``link`` (+ ``offset``) einer ``Chain`` als Batch-Rechner."""

    def __init__(self, chain: Chain, link: str, offset: Optional[Sequence[float]] = None):
        self.chain = chain
        self.link = link
        self.n = len(chain.active)
        self.schritte: List[tuple] = []
        pre = np.eye(4)
        for j in chain.path(link):
            pre = pre @ j.origin
            if j.type == "fixed":
                continue
            if j.mimic is not None:
                lead, mult, off = j.mimic
            else:
                lead, mult, off = j.name, 1.0, 0.0
            a = j.axis / np.linalg.norm(j.axis)
            kind = "prismatic" if j.type == "prismatic" else "revolute"
            # Drehung um eine Koordinatenachse: Spalten mischen statt 3x3-Produkt
            k_ax, sgn = -1, 1.0
            nz = np.nonzero(np.abs(a) > 1e-12)[0]
            if nz.size == 1:
                k_ax, sgn = int(nz[0]), float(np.sign(a[nz[0]]))
            rot_id = bool(np.allclose(pre[:3, :3], np.eye(3), atol=0.0, rtol=0.0))
            self.schritte.append((pre[:3, :3].copy(), pre[:3, 3].copy(), rot_id, kind, a, chain.index[lead],
                                  float(mult), float(off), k_ax, sgn))
            pre = np.eye(4)
        self.tail = pre @ transform(np.eye(3), offset if offset is not None else (0.0, 0.0, 0.0))

    def fk_jac(self, Q: np.ndarray, jac: bool = True) -> Tuple[np.ndarray, Optional[np.ndarray]]:
        """Q (N, n) -> (T (N, 4, 4), J (N, 6, n) oder None)."""
        Q = np.atleast_2d(np.asarray(Q, float))
        N = Q.shape[0]
        R = np.broadcast_to(np.eye(3), (N, 3, 3)).copy()
        p = np.zeros((N, 3))
        rahmen = []
        for pre_R, pre_t, rot_id, kind, a, col, mult, off, k_ax, sgn in self.schritte:
            p = p + R @ pre_t
            if not rot_id:
                R = R @ pre_R
            val = mult * Q[:, col] + off
            if kind == "revolute":
                if k_ax >= 0:
                    aw = sgn * R[:, :, k_ax]
                    rahmen.append((aw, p, kind, col, mult))
                    th = sgn * val
                    c, s = np.cos(th)[:, None], np.sin(th)[:, None]
                    i, j = {0: (1, 2), 1: (2, 0), 2: (0, 1)}[k_ax]
                    Ri, Rj = R[:, :, i], R[:, :, j]
                    R = R.copy()
                    R[:, :, i] = c * Ri + s * Rj
                    R[:, :, j] = c * Rj - s * Ri
                else:
                    aw = R @ a
                    rahmen.append((aw, p, kind, col, mult))
                    R = R @ _rodrigues(a, val)
            else:
                aw = R @ a
                rahmen.append((aw, p, kind, col, mult))
                p = p + aw * val[:, None]
        p_end = p + R @ self.tail[:3, 3]
        R_end = R @ self.tail[:3, :3]
        T = np.zeros((N, 4, 4))
        T[:, :3, :3] = R_end
        T[:, :3, 3] = p_end
        T[:, 3, 3] = 1.0
        if not jac:
            return T, None
        J = np.zeros((N, 6, self.n))
        for aw, o, kind, col, mult in rahmen:
            if kind == "prismatic":
                J[:, :3, col] += mult * aw
            else:
                d = p_end - o
                J[:, 0, col] += mult * (aw[:, 1] * d[:, 2] - aw[:, 2] * d[:, 1])
                J[:, 1, col] += mult * (aw[:, 2] * d[:, 0] - aw[:, 0] * d[:, 2])
                J[:, 2, col] += mult * (aw[:, 0] * d[:, 1] - aw[:, 1] * d[:, 0])
                J[:, 3:, col] += mult * aw
        return T, J

    def fk(self, Q: np.ndarray) -> np.ndarray:
        return self.fk_jac(Q, jac=False)[0]

    def ik_batch(self, targets: np.ndarray, q0: np.ndarray, use: Sequence[str], orientation: bool = True,
                 tol_pos: float = 1e-5, tol_rot: float = 1e-4, iters: int = 300
                 ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Ein IK-Versuch (ohne Neustarts) je Ziel, alle gleichzeitig.

        targets (N, 4, 4), q0 (N, n) -> (q (N, n), Positionsfehler (N,), Winkelfehler (N,), ok (N,)).
        Rechnet je Ziel genau wie der erste Versuch von ``Chain.ik``.
        """
        targets = np.asarray(targets, float).reshape(-1, 4, 4)
        q = np.array(np.broadcast_to(np.asarray(q0, float), (targets.shape[0], self.n)))
        N = q.shape[0]
        idx = np.array([self.chain.index[n] for n in use])
        lo, hi = self.chain.lower[idx], self.chain.upper[idx]
        m = len(idx)
        ne = 6 if orientation else 3
        best_q, best_pe, best_re = q.copy(), np.full(N, np.inf), np.full(N, np.inf)
        out_q, out_pe, out_re = q.copy(), np.full(N, np.inf), np.full(N, np.inf)
        ok = np.zeros(N, bool)
        offen = np.arange(N)
        lam2 = 1e-4
        eye = np.eye(ne)
        for _ in range(iters):
            if offen.size == 0:
                break
            qa = q[offen]
            T, J = self.fk_jac(qa)
            tg = targets[offen]
            ep = tg[:, :3, 3] - T[:, :3, 3]
            if orientation:
                er = rot_log_batch(tg[:, :3, :3] @ np.transpose(T[:, :3, :3], (0, 2, 1)))
            else:
                er = np.zeros_like(ep)
            pe = np.linalg.norm(ep, axis=1)
            re = np.linalg.norm(er, axis=1)
            bpe, bre = best_pe[offen], best_re[offen]
            besser = (pe < bpe) | ((pe <= bpe + 1e-12) & (re < bre))
            bi = offen[besser]
            best_q[bi], best_pe[bi], best_re[bi] = qa[besser], pe[besser], re[besser]
            fertig = (pe < tol_pos) & ((re < tol_rot) if orientation else True)
            if fertig.any():
                fi = offen[fertig]
                out_q[fi], out_pe[fi], out_re[fi], ok[fi] = qa[fertig], pe[fertig], re[fertig], True
            weiter = ~fertig
            offen, qa, ep, er, J = offen[weiter], qa[weiter], ep[weiter], er[weiter], J[weiter]
            if offen.size == 0:
                break
            jac = J[:, :, idx]
            if orientation:
                e = np.concatenate([ep, er * 0.5], axis=1)
                jac = np.concatenate([jac[:, :3], jac[:, 3:] * 0.5], axis=1)
            else:
                e, jac = ep, jac[:, :3]
            qi = qa[:, idx]
            free = np.ones((offen.size, m), bool)
            dq = np.zeros((offen.size, m))
            aktiv = np.arange(offen.size)
            for _pass in range(m):
                jf = jac[aktiv] * free[aktiv][:, None, :]
                A = jf @ np.transpose(jf, (0, 2, 1)) + lam2 * eye
                d = np.einsum("nij,ni->nj", jf, np.linalg.solve(A, e[aktiv][:, :, None])[:, :, 0])
                dq[aktiv] = d
                qq = qi[aktiv]
                push = ((qq <= lo + 1e-12) & (d < 0)) | ((qq >= hi - 1e-12) & (d > 0))
                push &= free[aktiv]
                hat = push.any(axis=1)
                if not hat.any():
                    break
                free[aktiv[hat]] &= ~push[hat]
                aktiv = aktiv[hat]
            step = np.max(np.abs(dq), axis=1)
            gross = step > 0.3
            dq[gross] *= (0.3 / step[gross])[:, None]
            qn = qa.copy()
            qn[:, idx] = np.clip(qi + dq, lo, hi)
            q[offen] = qn
        rest = ~ok
        out_q[rest], out_pe[rest], out_re[rest] = best_q[rest], best_pe[rest], best_re[rest]
        return out_q, out_pe, out_re, ok


class SchnellChain(Chain):
    """``Chain`` mit schneller ``ik`` (Batch-Kern) und vorberechneten Gelenkdrehungen."""

    def __init__(self, urdf: str):
        super().__init__(urdf)
        self._ketten = {}
        self._k = {}
        for j in self.joints:
            if j.type in ("revolute", "continuous"):
                a = j.axis / np.linalg.norm(j.axis)
                k = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
                self._k[j.name] = (k, k @ k)

    def kette(self, link: str, offset: Optional[Sequence[float]] = None) -> SchnellKette:
        key = (link, None if offset is None else tuple(float(v) for v in offset))
        if key not in self._ketten:
            self._ketten[key] = SchnellKette(self, link, offset)
        return self._ketten[key]

    def _joint_motion(self, j, val: float) -> np.ndarray:
        if j.type in ("revolute", "continuous"):
            k, k2 = self._k[j.name]
            t = np.eye(4)
            t[:3, :3] += math.sin(val) * k + (1.0 - math.cos(val)) * k2
            return t
        return super()._joint_motion(j, val)

    def ik(self, target: np.ndarray, link: str, q0: np.ndarray, use: Sequence[str],
           offset: Optional[Sequence[float]] = None, orientation: bool = True,
           tol_pos: float = 1e-5, tol_rot: float = 1e-4, iters: int = 300,
           restarts: int = 50, rng: Optional[np.random.Generator] = None) -> Tuple[np.ndarray, float, float, bool]:
        """Wie ``Chain.ik``; Neustarts ziehen dieselben Zufallsposen in derselben Reihenfolge."""
        rng = rng or np.random.default_rng(0)
        k = self.kette(link, offset)
        idx = [self.index[n] for n in use]
        best = (q0.copy(), math.inf, math.inf)
        for attempt in range(restarts + 1):
            q = q0.copy() if attempt == 0 else self.random_q(rng, use)
            for i in range(len(q)):
                if i not in idx:
                    q[i] = q0[i]
            qs, pe, re, ok = k.ik_batch(target[None], q[None], use, orientation, tol_pos, tol_rot, iters)
            if ok[0]:
                return qs[0], float(pe[0]), float(re[0]), True
            if pe[0] < best[1] or (pe[0] <= best[1] + 1e-12 and re[0] < best[2]):
                best = (qs[0], float(pe[0]), float(re[0]))
        q, pe, re = best
        return q, pe, re, False
