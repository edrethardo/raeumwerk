"""Verdeckung durch Korbstaebe, Rahmen, Koerbe und Arm: Sichtbarkeit je Objekt per Strahlschnitt je Pixel.

Eine Szene (Liste ``Prim``) wird mit allen Pixelstrahlen der Kamera geschnitten. Je Zielobjekt:

* ``frei``  = Pixel, die das Objekt allein (ohne alle anderen Koerper) treffen wuerden; das Bild wird
  bei Bedarf ueber den Sensorrand hinaus fortgesetzt, damit abgeschnittene Teile als nicht sichtbar zaehlen;
* ``sichtbar`` = Pixel, in denen das Objekt der erste Treffer ist (nichts davor);
* ``gemessen`` = sichtbare Pixel im Betriebsabstand der Kamera (Kamerarahmen-z) und, beim Teller, mit
  Einfallswinkel unter ``winkel_max`` (wie ``sensor.aufnehmen``).

Mindestbedingungen fuer eine brauchbare Schaetzung aus ``schaetzer.py`` (alle Pixelzahlen auf Skala 2
umgerechnet, das ist die Aufloesung der Ensenso-Aufnahmen dort):

* Glas (``glas_schaetzen``): >= 30 Randpixel der Maske (``zu_wenig_kontur``) und >= 50 % der Randstrahlen
  streifen den Zylinder (``kontur_inlier_gering``). Verdeckungskanten sind keine Glaskontur: ein Randpixel
  zaehlt als *wahre Kontur*, wenn es an einen Nachbarn grenzt, den das Glas allein nicht trifft.
* Teller (``teller_schaetzen``): >= 60 gueltige Tiefenpunkte (``zu_wenig_punkte``) und ein Konturbogen von
  >= 40 Grad aus Punkten, die auf dem Tellerrand liegen (``bogen_zu_kurz``; Kontur = hoechster Punkt je
  4-mm-Streifen in der Tellerebene, Randpunkt = Abstand zum Rand < 2 mm + halbe Pixelbreite).

Das sind notwendige Bedingungen der Schaetzer, keine Genauigkeitsaussage.
"""
from __future__ import annotations

import math
from typing import Dict, List, Sequence, Tuple

import numpy as np

from .schaetzer import bogen_grad
from .strahlen import Kamera, Prim, naechster, schnitt

# Ensenso C57-6-S, Katalog 290 x 58 x 100 mm; die Reihenfolge der Kanten ist im Katalog nicht eindeutig
# (Breite 290 mm bei 240 mm Basislinie). Huellmass konservativ: 0,29 breit, je 0,10 hoch und tief.
KAMERA_MASSE = (0.29, 0.10, 0.10)       # rechts, unten, vorwaerts im Kamerarahmen
KAMERA_VOR_ORT = 0.02                   # Koerper ragt so weit vor das optische Zentrum, Rest dahinter
SAEULE_XY = (0.95, 0.0)                 # Mastsaeule auf der Platte hinter der Kante, rechts ausserhalb des Sichtfelds
SAEULE_QUER = 0.05
PLATTE_Z = 0.86

MIN_GLAS_RAND = 30
MIN_GLAS_INLIER = 0.5
MIN_TELLER_PUNKTE = 60
MIN_TELLER_BOGEN = 40.0
SKALA_SCHAETZER = 2.0


def kamera_huellen(C, A, saeule: bool = False, rand_m: float = 0.0, saeule_xy=SAEULE_XY,
                   platte_z: float = PLATTE_Z) -> List[Tuple[str, np.ndarray, np.ndarray]]:
    """Achsparallele Huellquader (Name, lo, hi) von Kamerakoerper und optional Mastsaeule + Ausleger.

    Der Kamerakoerper ist der orientierte Quader ``KAMERA_MASSE``, als Weltquader umschlossen
    (konservativ). Saeule: senkrechter Quader auf der Platte; Ausleger: je ein Balken in y (vom
    Saeulenfuss zur Kamera) und in x (zur Kamera), 0,07-0,11 m ueber dem Kameraort."""
    cam = Kamera.zielend("k", {"w": 1, "h": 1, "f": 1.0, "fy": 1.0}, C, A)
    C = np.asarray(C, float)
    mitte = C - cam.R[:, 2] * (KAMERA_MASSE[2] / 2.0 - KAMERA_VOR_ORT)
    ext = np.abs(cam.R) @ (np.array(KAMERA_MASSE) / 2.0)
    out = [("kamera", mitte - ext - rand_m, mitte + ext + rand_m)]
    if saeule:
        sx, sy = saeule_xy
        q = SAEULE_QUER / 2.0 + rand_m
        out.append(("saeule", np.array([sx - q, sy - q, platte_z]), np.array([sx + q, sy + q, C[2] + 0.11 + rand_m])))
        b = 0.02 + rand_m
        zl, zh = C[2] + 0.07 - rand_m, C[2] + 0.11 + rand_m
        y0, y1 = sorted((sy, float(C[1])))
        out.append(("ausleger_y", np.array([sx - b, y0 - b, zl]), np.array([sx + b, y1 + b, zh])))
        x0, x1 = sorted((float(C[0]), sx))
        out.append(("ausleger_x", np.array([x0 - b, C[1] - b, zl]), np.array([x1 + b, C[1] + b, zh])))
    return out


def huell_prims(huellen) -> List[Prim]:
    return [Prim(n, "kamera", "box", (lo + hi) / 2.0, (hi - lo) / 2.0, np.eye(3), n) for n, lo, hi in huellen]


def arm_prims(boxen: Sequence[dict], name: str = "arm") -> List[Prim]:
    """Armquader aus Weltkoordinaten ``{"c": [3], "R": [[3]*3], "h": [3]}`` als Prims (Gruppe ``arm``)."""
    return [Prim(f"{name}_{i}", "arm", "box", np.asarray(b["c"], float), np.asarray(b["h"], float),
                 np.asarray(b["R"], float), name) for i, b in enumerate(boxen)]


# --- Strahlen ------------------------------------------------------------------------------------

def _gross(cam: Kamera, faktor: float = 1.6) -> Kamera:
    m = dict(cam.modell, w=int(cam.modell["w"] * faktor), h=int(cam.modell["h"] * faktor))
    return Kamera(cam.name + "_gross", m, cam.C, cam.R, cam.skala)


def _treffer(p: Prim, C: np.ndarray, d: np.ndarray):
    """Strahlen, die ``p`` allein treffen: (Indizes, t, Normalen)."""
    v = p.c - C
    tp = d @ v
    rad = float(np.linalg.norm(p.h))
    dist2 = float(v @ v) - tp * tp
    sel = np.where((dist2 <= rad * rad) & (tp > 0))[0]
    if len(sel) == 0:
        return sel, np.zeros(0), np.zeros((0, 3))
    t, nor = schnitt(p, np.tile(C, (len(sel), 1)), d[sel])
    hit = np.isfinite(t)
    return sel[hit], t[hit], nor[hit]


def _maske(idx: np.ndarray, hw: Tuple[int, int]) -> np.ndarray:
    m = np.zeros(hw[0] * hw[1], bool)
    m[idx] = True
    return m.reshape(hw)


def _rand(m: np.ndarray) -> np.ndarray:
    pad = np.pad(m, 1)
    inner = np.ones_like(m)
    for di, dj in ((0, 1), (1, 0), (1, 2), (2, 1)):
        inner &= pad[di:di + m.shape[0], dj:dj + m.shape[1]]
    return m & ~inner


def _nachbar_aus(frei: np.ndarray) -> np.ndarray:
    """Pixel, die an mindestens einen 4-Nachbarn grenzen, den das Objekt allein nicht trifft."""
    pad = np.pad(frei, 1)
    gr = np.zeros_like(frei)
    for di, dj in ((0, 1), (1, 0), (1, 2), (2, 1)):
        gr |= ~pad[di:di + frei.shape[0], dj:dj + frei.shape[1]]
    return gr


def sichtbarkeit(prims: List[Prim], cam: Kamera, ziele: Sequence[str], schaetzer_skala: float = SKALA_SCHAETZER,
                 mit_bogen: bool = True) -> Dict[str, Dict]:
    """Sichtbarkeit der Zielobjekte (``Prim.objekt`` in ``ziele``) gegen alle anderen ``prims``.

    Liefert je Ziel: Pixelzahlen (Skala der Kamera), Anteile, Tiefe der gemessenen Pixel, Konturkennwerte
    und die Brauchbarkeit nach den Schaetzer-Bedingungen (Modulkopf). Glas hat Gruppe ``glas``, Teller
    Gruppe ``teller``."""
    m = cam.modell
    d, hw = cam.strahlen()
    o = np.tile(cam.C, (len(d), 1))
    _, idx_all, _ = naechster(prims, o, d)
    fwd = d @ cam.R[:, 2]
    skal = cam.skala / schaetzer_skala                       # Pixel dieser Skala -> Skala des Schaetzers
    gross = None
    out: Dict[str, Dict] = {}
    for name in ziele:
        j = next(i for i, p in enumerate(prims) if p.objekt == name)
        p = prims[j]
        sel, t, nor = _treffer(p, cam.C, d)
        frei = _maske(sel, hw)
        n_frei = int(len(sel))
        n_voll = n_frei
        if frei[0].any() or frei[-1].any() or frei[:, 0].any() or frei[:, -1].any() or n_frei == 0:
            if gross is None:
                gross = _gross(cam)
                dg, _ = gross.strahlen()
            sg, _, _ = _treffer(p, cam.C, dg)
            n_voll = int(len(sg))
        vis_sel = idx_all[sel] == j
        vis_idx = sel[vis_sel]
        vis = _maske(vis_idx, hw)
        zt = t[vis_sel] * fwd[vis_idx]
        cosw = np.abs(np.sum(nor[vis_sel] * d[vis_idx], 1))
        ok_pix = (zt >= m["dmin"]) & (zt <= m["dmax"])
        if p.gruppe == "teller":
            ok_pix &= cosw >= math.cos(math.radians(m["winkel_max"]))
        gem = int(ok_pix.sum())
        nv = len(vis_idx)
        r = dict(n_voll=n_voll, n_im_bild=n_frei, n_sichtbar=int(nv), n_gemessen=gem,
                 anteil_im_bild=n_frei / n_voll if n_voll else 0.0,
                 anteil_sichtbar=nv / n_voll if n_voll else 0.0,
                 anteil_verdeckt_im_bild=1.0 - nv / n_frei if n_frei else 1.0,
                 anteil_gemessen=gem / n_voll if n_voll else 0.0)
        if nv:
            r.update(z_mittel_m=float(zt.mean()), z_min_m=float(zt.min()), z_max_m=float(zt.max()),
                     sigma_mm=1e3 * m["sigma_k"] * float(zt.mean()) ** 2)
        else:
            r.update(z_mittel_m=None, z_min_m=None, z_max_m=None, sigma_mm=None)
        if p.gruppe == "glas":
            rd = _rand(vis)
            n_rand = int(rd.sum())
            wahr = int((rd & _nachbar_aus(frei)).sum())
            r.update(rand_px_s2=n_rand * skal, kontur_wahr_px_s2=wahr * skal,
                     kontur_inlier=(wahr / n_rand) if n_rand else 0.0)
            r["brauchbar"] = bool(r["kontur_wahr_px_s2"] >= MIN_GLAS_RAND and r["kontur_inlier"] >= MIN_GLAS_INLIER)
            r["grund"] = "" if r["brauchbar"] else ("zu_wenig_kontur" if r["kontur_wahr_px_s2"] < MIN_GLAS_RAND
                                                    else "kontur_inlier_gering")
        else:
            r["punkte_s2"] = gem * skal * skal
            bogen, n_kon = 0.0, 0
            if mit_bogen and gem >= 3:
                P = cam.C + d[vis_idx][ok_pix] * t[vis_sel][ok_pix][:, None]
                bogen, n_kon = _tellerbogen(p, P, cam)
            r.update(kontur_bogen_grad=bogen, kontur_punkte=n_kon)
            r["brauchbar"] = bool(r["punkte_s2"] >= MIN_TELLER_PUNKTE and bogen >= MIN_TELLER_BOGEN)
            r["grund"] = "" if r["brauchbar"] else ("zu_wenig_punkte" if r["punkte_s2"] < MIN_TELLER_PUNKTE
                                                    else "bogen_zu_kurz")
        out[name] = r
    return out


def _tellerbogen(p: Prim, P: np.ndarray, cam: Kamera, streifen: float = 0.004) -> Tuple[float, int]:
    """Konturbogen (Grad) aus gemessenen Tellerpunkten: hoechster Punkt je Streifen, nur Randpunkte."""
    n = p.R[:, 2] / np.linalg.norm(p.R[:, 2])
    e1 = np.cross(n, [0.0, 0.0, 1.0])
    if np.linalg.norm(e1) < 1e-9:
        return 0.0, 0
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(e1, n)
    if e2[2] < 0:
        e2 = -e2
    uv = np.stack([(P - p.c) @ e1, (P - p.c) @ e2], 1)
    b = np.floor(uv[:, 0] / streifen).astype(int)
    kon = []
    for k in np.unique(b):
        s = uv[b == k]
        kon.append(s[np.argmax(s[:, 1])])
    kon = np.array(kon)
    r = float(p.h[0])
    pix = float(np.mean(np.linalg.norm(P - cam.C, axis=1))) * cam.skala / cam.modell["f"]
    tol = 0.002 + 0.5 * pix
    inl = np.abs(np.linalg.norm(kon, axis=1) - r) < tol
    if inl.sum() < 2:
        return 0.0, int(inl.sum())
    return bogen_grad(kon[inl], np.zeros(2)), int(inl.sum())
