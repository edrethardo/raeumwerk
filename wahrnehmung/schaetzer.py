"""Schaetzer: Glas (Zylinderfit auf der Silhouette, Modellwahl) und Teller (Ebenen- + Kreisfit).

Glas: Die Tiefe des transparenten Glases ist unbrauchbar (Ausfall/Durchblick/Reflex), die Kontur
im Farbbild nicht. Jeder Randstrahl der Instanzmaske streift den Glaszylinder: sein kleinster
waagerechter Abstand zur Glasachse im Hoehenbereich des Glases ist der Radius. Gauss-Newton auf
die Achse (x, y), robuste Gewichte (Ausreisser: Verdeckungskanten). Hoehenbereich aus Korbmodell
und Glasmodell. Modellwahl ueber Restfehler und Anteil der Innenstrahlen, die das Glas treffen.

Teller: Tiefe gut (Keramik), RANSAC-Ebene auf den Maskenpunkten (Normale), dann in der Ebene die
obere Kontur (hoechster Punkt je 4-mm-Streifen) und ein Kreisfit mit dem Modellradius.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

GLAS_MODELLE = [("Glas Ø 75 mm", 0.0375, 0.110), ("Glas Ø 65 mm", 0.0325, 0.120), ("Becher Ø 84 mm", 0.042, 0.095)]
TELLER_MODELLE = [("Teller Ø 190 mm", 0.095), ("Teller Ø 215 mm", 0.1075), ("Teller Ø 260 mm", 0.130)]


# --- Kreis ---------------------------------------------------------------------------------------

def kreis3(a, b, c) -> Optional[Tuple[np.ndarray, float]]:
    ax, ay = a
    bx, by = b
    cx, cy = c
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-12:
        return None
    ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d
    return np.array([ux, uy]), math.hypot(ax - ux, ay - uy)


def kreis_lsq(P, c, r=None, it=20):
    """Geometrischer Kreisfit (Gauss-Newton); Radius fest, wenn ``r`` angegeben."""
    c = np.array(c, float)
    rr = float(r) if r is not None else float(np.mean(np.linalg.norm(P - c, axis=1)))
    for _ in range(it):
        v = P - c
        dist = np.maximum(np.linalg.norm(v, axis=1), 1e-9)
        res = dist - rr
        J = -v / dist[:, None]
        if r is None:
            J = np.column_stack([J, -np.ones(len(P))])
        dx = np.linalg.lstsq(J, -res, rcond=None)[0]
        c = c + dx[:2]
        if r is None:
            rr += dx[2]
        if np.linalg.norm(dx) < 1e-8:
            break
    return c, rr, np.linalg.norm(P - c, axis=1) - rr


def kreis_ransac(P, r_fest, rng, tol=0.0015, n=300, c_nahe=None, c_max=None):
    """Kreis mit festem Radius durch je zwei Punkte (beide Loesungen), Konsens = Punkte im Band."""
    best = None
    if len(P) < 3:
        return None
    for _ in range(n):
        i, j = rng.choice(len(P), 2, replace=False)
        a, b = P[i], P[j]
        m = (a + b) / 2
        q = np.linalg.norm(b - a)
        if q < 1e-4 or q > 2 * r_fest:
            continue
        hgt = math.sqrt(max(r_fest * r_fest - (q / 2) ** 2, 0.0))
        nrm = np.array([-(b - a)[1], (b - a)[0]]) / q
        for s in (1.0, -1.0):
            c = m + s * hgt * nrm
            if c_nahe is not None and np.linalg.norm(c - c_nahe) > c_max:
                continue
            inl = np.abs(np.linalg.norm(P - c, axis=1) - r_fest) < tol
            if best is None or inl.sum() > best[1].sum():
                best = (c, inl)
    return best


def bogen_grad(P, c) -> float:
    if len(P) < 2:
        return 0.0
    a = np.sort(np.arctan2(P[:, 1] - c[1], P[:, 0] - c[0]))
    gaps = np.diff(np.r_[a, a[0] + 2 * np.pi])
    return math.degrees(2 * np.pi - gaps.max())


# --- Glas: Zylinder auf der Silhouette -----------------------------------------------------------

def _achsabstand(O, D, c, z0, z1):
    """Kleinster waagerechter Abstand der Strahlen O + t D zur senkrechten Achse durch c,
    t beschraenkt auf den Hoehenbereich [z0, z1]. Liefert Abstand und naechsten Punkt (xy)."""
    dz = np.where(np.abs(D[:, 2]) < 1e-9, -1e-9, D[:, 2])
    ta, tb = (z0 - O[2]) / dz, (z1 - O[2]) / dz
    tlo, thi = np.minimum(ta, tb), np.maximum(ta, tb)
    dxy = D[:, :2]
    a = np.maximum(np.sum(dxy * dxy, 1), 1e-12)
    t = np.sum((c - O[:2]) * dxy, 1) / a
    t = np.clip(t, tlo, thi)
    p = O[:2] + t[:, None] * dxy
    return np.linalg.norm(p - c, axis=1), p


def zylinder_silhouette(O, D_rand, z0, z1, c0, r=None, it=30, r0=0.035):
    """Achse (x, y) [und Radius] aus Randstrahlen; robuste Huber-Gewichte (1 mm)."""
    c = np.array(c0, float)
    rr = float(r) if r is not None else float(r0)
    w = np.ones(len(D_rand))
    for _ in range(it):
        dist, p = _achsabstand(O, D_rand, c, z0, z1)
        res = dist - rr
        a = np.abs(res)
        w = np.where(a < 0.001, 1.0, 0.001 / np.maximum(a, 1e-9))
        w[a > 0.006] = 0.0
        J = -(p - c) / np.maximum(dist, 1e-9)[:, None]
        if r is None:
            J = np.column_stack([J, -np.ones(len(res))])
        sw = np.sqrt(w)
        if (w > 0).sum() < 6:
            break
        dx = np.linalg.lstsq(J * sw[:, None], -res * sw, rcond=None)[0]
        c = c + dx[:2]
        if r is None:
            rr += dx[2]
        if np.linalg.norm(dx) < 1e-8:
            break
    dist, _ = _achsabstand(O, D_rand, c, z0, z1)
    res = dist - rr
    return c, rr, res, np.abs(res) < 0.002


def _rand(m: np.ndarray) -> np.ndarray:
    pad = np.pad(m, 1)
    inner = np.ones_like(m)
    for di, dj in ((0, 1), (1, 0), (1, 2), (2, 1)):
        inner &= pad[di:di + m.shape[0], dj:dj + m.shape[1]]
    return m & ~inner


def glas_schaetzen(auf, maske: np.ndarray, z_boden: float, c0, modelle=GLAS_MODELLE, sigma_fit=0.0015,
                   rng=None) -> Dict:
    """Glas kopfueber im Halter: ``z_boden`` = Unterkante (Glasrand unten), Hoehe aus dem Modell."""
    rng = rng or np.random.default_rng(0)
    out: Dict = {"ok": False, "gruende": []}
    m = maske.ravel()
    rand = _rand(maske).ravel()
    n_rand = int(rand.sum())
    out["n_maske"], out["n_rand"] = int(m.sum()), n_rand
    if n_rand < 30:
        out["gruende"].append("zu_wenig_kontur")
        return out
    O = auf.cam.C
    D_rand, D_in = auf.d[rand], auf.d[m & ~rand]
    if len(D_in) > 3000:
        D_in = D_in[rng.choice(len(D_in), 3000, replace=False)]
    kand = []
    for name, r_m, h_m in modelle:
        c, _, res, inl = zylinder_silhouette(O, D_rand, z_boden, z_boden + h_m, c0, r=r_m)
        rms = float(np.sqrt(np.mean(np.minimum(np.abs(res), 0.01) ** 2)))
        di, _ = _achsabstand(O, D_in, c, z_boden, z_boden + h_m)
        innen = float(np.mean(di <= r_m + 0.0015)) if len(D_in) else 0.0
        s = math.exp(-0.5 * (rms / sigma_fit) ** 2) * innen
        kand.append(dict(name=name, r=r_m, h=h_m, c=c.tolist(), rms_mm=1e3 * rms, innen=innen, passwert=s,
                         inlier=float(inl.mean())))
    kand.sort(key=lambda k: -k["passwert"])
    best = kand[0]
    cf, rf, resf, _ = zylinder_silhouette(O, D_rand, z_boden, z_boden + best["h"], best["c"], r=None, r0=best["r"])
    # Reflexpunkte (gueltige Tiefe auf dem Glas): Hoehe der Oberkante zur Kontrolle
    P = auf.P[m & np.isfinite(auf.mess)]
    z_top = z_boden + best["h"]
    nahe = P[np.linalg.norm(P[:, :2] - np.asarray(best["c"]), axis=1) < best["r"] + 0.003] if len(P) else P
    out.update(c=best["c"], r=best["r"], modell=best["name"], passwert=best["passwert"], rms_mm=best["rms_mm"],
               innen=best["innen"], inlier=best["inlier"], r_frei_m=float(rf), kandidaten=kand,
               reflex_n=int(len(nahe)), reflex_z_median_m=float(np.median(nahe[:, 2])) if len(nahe) else None,
               z_oben_modell_m=z_top)
    if best["passwert"] < 0.3:
        out["gruende"].append("modell_passt_nicht")
    if abs(rf - best["r"]) > 0.004:
        out["gruende"].append("radius_frei_weicht_ab")
    if best["inlier"] < 0.5:
        out["gruende"].append("kontur_inlier_gering")
    out["ok"] = not out["gruende"]
    return out


# --- Teller: Ebene + Kreis -----------------------------------------------------------------------

def ebene_ransac(P, rng, tol=0.002, n=200) -> Tuple[np.ndarray, float, np.ndarray]:
    best = None
    for _ in range(n):
        a, b, c = P[rng.choice(len(P), 3, replace=False)]
        nv = np.cross(b - a, c - a)
        ln = np.linalg.norm(nv)
        if ln < 1e-9:
            continue
        nv /= ln
        inl = np.abs((P - a) @ nv) < tol
        if best is None or inl.sum() > best[2].sum():
            best = (nv, float(nv @ a), inl)
    nv, d, inl = best
    Q = P[inl]
    cm = Q.mean(0)
    _, _, vt = np.linalg.svd(Q - cm, full_matrices=False)
    nv = vt[2] * (1.0 if vt[2] @ nv >= 0 else -1.0)
    inl = np.abs((P - cm) @ nv) < tol
    return nv, float(nv @ cm), inl


def teller_schaetzen(auf, maske: np.ndarray, n_soll, c0, halbdicke=0.0025, modelle=TELLER_MODELLE, rng=None,
                     streifen=0.004) -> Dict:
    """``n_soll``: erwartete Tellernormale (Reihe), ``c0``: erwartete Mitte (Suchhilfe)."""
    rng = rng or np.random.default_rng(0)
    out: Dict = {"ok": False, "gruende": []}
    m = maske.ravel() & np.isfinite(auf.mess)
    P = auf.P[m]
    out["n_punkte"] = int(len(P))
    if len(P) < 60:
        out["gruende"].append("zu_wenig_punkte")
        return out
    if len(P) > 6000:
        P = P[rng.choice(len(P), 6000, replace=False)]
    nv, d, inl = ebene_ransac(P, rng)
    zur_kamera = auf.cam.C - P.mean(0)
    if nv @ zur_kamera < 0:
        nv, d = -nv, -d
    n_soll = np.asarray(n_soll, float) / np.linalg.norm(n_soll)
    winkel = math.degrees(math.acos(min(1.0, abs(float(nv @ n_soll)))))
    out.update(normale=nv.tolist(), ebene_inlier=float(inl.mean()), normale_winkel_grad=winkel)
    e1 = np.cross(nv, [0.0, 0.0, 1.0])
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(e1, nv)
    if e2[2] < 0:
        e2 = -e2
    o = P[inl].mean(0) - nv * halbdicke             # Punkt der Mittelebene (Kamera sieht eine Seitenflaeche)
    uv = np.stack([(P - o) @ e1, (P - o) @ e2], 1)
    b = np.floor(uv[:, 0] / streifen)
    kon = np.array([uv[b == k][np.argmax(uv[b == k, 1])] for k in np.unique(b)])
    c0 = np.asarray(c0, float)
    c0_uv = np.array([(c0 - o) @ e1, (c0 - o) @ e2])
    kand = []
    for name, r_m in modelle:
        rs = kreis_ransac(kon, r_m, rng, c_nahe=c0_uv, c_max=0.03)
        if rs is None or rs[1].sum() < 5:
            continue
        c, _, res = kreis_lsq(kon[rs[1]], rs[0], r=r_m)
        inl_k = np.abs(np.linalg.norm(kon - c, axis=1) - r_m) < 0.002
        rms = float(np.sqrt(np.mean(res ** 2)))
        kand.append(dict(name=name, r=r_m, c_uv=c.tolist(), rms_mm=1e3 * rms, n=int(inl_k.sum()),
                         anteil=float(inl_k.mean()), bogen=bogen_grad(kon[inl_k], c)))
    if not kand:
        out["gruende"].append("kein_kreis")
        return out
    kand.sort(key=lambda k: (-k["n"], k["rms_mm"]))
    best = kand[0]
    cu, cv = best["c_uv"]
    c3 = o + cu * e1 + cv * e2
    gier = math.degrees(math.atan2(-nv[0], nv[1])) if abs(nv[1]) > 1e-9 else 90.0
    if gier > 90:
        gier -= 180
    if gier < -90:
        gier += 180
    out.update(c=c3.tolist(), r=best["r"], modell=best["name"], rms_mm=best["rms_mm"], kontur_n=int(len(kon)),
               kontur_inlier=best["anteil"], bogen_grad=best["bogen"], gier_grad=gier, kandidaten=kand)
    if inl.mean() < 0.6:
        out["gruende"].append("ebene_inlier_gering")
    if winkel > 8.0:
        out["gruende"].append("normale_weicht_ab")
    if best["rms_mm"] > 2.0:
        out["gruende"].append("kreis_rms_gross")
    if best["bogen"] < 40.0:
        out["gruende"].append("bogen_zu_kurz")
    out["ok"] = not out["gruende"]
    return out
