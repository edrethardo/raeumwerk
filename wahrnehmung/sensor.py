"""Fehlermodell der Tiefenkameras und der Farbsegmentierung.

Raten (Annahmen, aus ``kamerasim`` der Kamerastudie uebernommen, dort begruendet):
  Glas (transparent): je gueltigem Glaspixel 50 % kein Wert (Ausfall), 35 % Durchblick (Tiefe des
  Hintergrunds hinter dem Glas), 15 % Reflex (Tiefe der Glasflaeche + 8 mm Streuung).
  Naesse: 5 % zufaellige Ausfaelle auf nassen Flaechen (Glas, Teller, Korb). Glanz: Ausfall, wenn
  die Flaechennormale weniger als 10 Grad vom Sehstrahl abweicht (Teller, Glas).
  Kanten: an Tiefenspruengen > 2 cm faellt jeder zweite Pixel aus. Flache Winkel: kein Wert ueber
  60 Grad (Ensenso) bzw. 70 Grad (D405) zwischen Normale und Sehstrahl.
  Rauschen entlang des Strahls: sigma = k * z^2 (Ensenso k = 1,533e-3 1/m, D405 k = 0,02 1/m).
Farbsegmentierung (Instanzmaske je Objekt): ideal aus dem Strahlschnitt, Randpixel kippen mit
50 % (+-1 px); Glas ist in der Farbe sichtbar (Kanten/Spiegelung), in der Tiefe aber nicht.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List

import numpy as np

from .strahlen import Kamera, Prim, naechster

GRUENDE = ["ok", "bereich", "winkel", "kante", "glas_fehlt", "nass_glanz"]


@dataclass
class Fehlermodell:
    glas_an: bool = True
    glas_fehlt: float = 0.50
    glas_durchblick: float = 0.35
    glas_reflex: float = 0.15
    reflex_sigma_m: float = 0.008
    nass_ausfall: float = 0.05
    glanz_winkel_grad: float = 10.0
    kante_sprung_m: float = 0.02
    kante_ausfall: float = 0.5
    maske_rand_kippen: float = 0.5
    # systematisch je Aufnahme: Maske gegen die Tiefe versetzt (Farb-Tiefe-Registrierung, Kantenunschaerfe)
    maske_versatz_px: float = 0.7
    # Kalibrierfehler je Aufnahme (Kamera -> Roboter): Ensenso (Mast) und D405 (Hand-Auge)
    kalib_ensenso_mm: float = 1.5
    kalib_ensenso_grad: float = 0.05
    kalib_d405_mm: float = 1.0
    kalib_d405_grad: float = 0.2
    nass: tuple = ("glas", "teller", "oberkorb", "glashalter", "tellerhalter")
    glanz: tuple = ("glas", "teller")

    def raten(self) -> Dict[str, float]:
        return {"glas_fehlt": self.glas_fehlt, "glas_durchblick": self.glas_durchblick, "glas_reflex": self.glas_reflex,
                "reflex_sigma_mm": 1e3 * self.reflex_sigma_m, "nass_ausfall": self.nass_ausfall,
                "glanz_winkel_grad": self.glanz_winkel_grad, "kante_ausfall": self.kante_ausfall,
                "maske_rand_kippen": self.maske_rand_kippen, "maske_versatz_px_sigma": self.maske_versatz_px,
                "kalib_ensenso_mm_grad": [self.kalib_ensenso_mm, self.kalib_ensenso_grad],
                "kalib_d405_mm_grad": [self.kalib_d405_mm, self.kalib_d405_grad]}


def kalibrierfehler(auf: "Aufnahme", rng: np.random.Generator, t_sigma_m: float, r_sigma_grad: float) -> None:
    """Die Auswertung kennt die Kamerapose nur mit Fehler: Strahlen aus einer gestoerten Pose,
    gemessene Distanzen bleiben (Punkte landen versetzt/verdreht in der Welt)."""
    ax = rng.normal(0.0, 1.0, 3)
    ax /= np.linalg.norm(ax)
    a = math.radians(rng.normal(0.0, r_sigma_grad))
    K = np.array([[0, -ax[2], ax[1]], [ax[2], 0, -ax[0]], [-ax[1], ax[0], 0]])
    dR = np.eye(3) + math.sin(a) * K + (1 - math.cos(a)) * K @ K
    cam = Kamera(auf.cam.name, auf.cam.modell, auf.cam.C + rng.normal(0.0, t_sigma_m, 3), dR @ auf.cam.R, auf.cam.skala)
    auf.cam = cam
    auf.d = auf.d @ dR.T


@dataclass
class Aufnahme:
    cam: Kamera
    hw: tuple
    d: np.ndarray            # Strahlrichtungen (N,3)
    t_wahr: np.ndarray       # wahre Distanz (N,)
    idx: np.ndarray          # getroffenes Primitiv (N,), -1 = nichts
    mess: np.ndarray         # gemessene Distanz (N,), nan = kein Wert
    grund: np.ndarray        # GRUENDE-Index (N,)
    glas_art: np.ndarray     # 0 kein Glas, 1 fehlt, 2 Durchblick, 3 Reflex
    prims: List[Prim] = field(default_factory=list)

    @property
    def P(self) -> np.ndarray:
        return self.cam.C + self.d * self.mess[:, None]

    def maske_wahr(self, objekt: str) -> np.ndarray:
        obj = np.array([p.objekt for p in self.prims] + [""])
        return (obj[self.idx] == objekt).reshape(self.hw)

    def statistik(self) -> Dict[str, float]:
        hit = self.idx >= 0
        out = {"pixel": int(hit.sum()), "gueltig_%": round(100.0 * float(np.isfinite(self.mess[hit]).mean()), 1)}
        g = self.glas_art > 0
        if g.any():
            for k, n in ((1, "glas_fehlt_%"), (2, "glas_durchblick_%"), (3, "glas_reflex_%")):
                out[n] = round(100.0 * float((self.glas_art[g] == k).mean()), 1)
        return out


def aufnehmen(prims: List[Prim], cam: Kamera, rng: np.random.Generator, fm: Fehlermodell = None,
              roi=None) -> Aufnahme:
    """Strahlschnitt + Fehlermodell. ``roi`` = (Mitte, Radius): nur Strahlen, die die Kugel treffen."""
    fm = fm or Fehlermodell()
    m = cam.modell
    d, hw = cam.strahlen()
    n = len(d)
    t = np.full(n, np.inf)
    idx = np.full(n, -1)
    nor = np.zeros((n, 3))
    sel = np.arange(n)
    if roi is not None:
        v = np.asarray(roi[0], float) - cam.C
        tp = d @ v
        dist2 = float(v @ v) - tp * tp
        sel = np.where((dist2 <= float(roi[1]) ** 2) & (tp > 0))[0]
    o = np.tile(cam.C, (len(sel), 1))
    t_s, i_s, n_s = naechster(prims, o, d[sel])
    t[sel], idx[sel], nor[sel] = t_s, i_s, n_s
    gr = np.array([p.gruppe for p in prims] + [""])[idx]
    zt = t * (d @ cam.R[:, 2])
    mess = t.copy()
    grund = np.zeros(n, int)
    grund[~np.isfinite(t)] = 1
    grund[(zt < m["dmin"]) | (zt > m["dmax"])] = 1
    cosw = np.abs(np.sum(nor * d, 1))
    grund[(grund == 0) & (cosw < math.cos(math.radians(m["winkel_max"])))] = 2
    h, w = hw
    T = np.where(np.isfinite(zt), zt, 10.0).reshape(h, w)
    pad = np.pad(T, 1, mode="edge")
    nb = np.stack([pad[i:i + h, j:j + w] for i in range(3) for j in range(3)])
    sprung = (nb.max(0) - nb.min(0)).ravel() > fm.kante_sprung_m
    grund[(grund == 0) & sprung & (rng.random(n) < fm.kante_ausfall)] = 3
    glas_art = np.zeros(n, int)
    if fm.glas_an:
        glas = (gr == "glas") & (grund == 0)
        zz = rng.random(n)
        fehlt = glas & (zz < fm.glas_fehlt)
        hint = glas & (zz >= fm.glas_fehlt) & (zz < fm.glas_fehlt + fm.glas_durchblick)
        refl = glas & (zz >= fm.glas_fehlt + fm.glas_durchblick)
        glas_art[fehlt], glas_art[hint], glas_art[refl] = 1, 2, 3
        grund[fehlt] = 4
        if hint.any():
            gi = np.where(hint)[0]
            t2, _, _ = naechster(prims, np.tile(cam.C, (len(gi), 1)), d[gi], ohne=lambda p: p.gruppe == "glas")
            mess[gi] = t2
            grund[gi[~np.isfinite(t2)]] = 1
        mess[refl] = t[refl] + rng.normal(0.0, fm.reflex_sigma_m, int(refl.sum()))
    nass = np.isin(gr, list(fm.nass)) & (grund == 0) & (glas_art == 0)
    grund[nass & (rng.random(n) < fm.nass_ausfall)] = 5
    glanz = np.isin(gr, list(fm.glanz)) & (grund == 0) & (glas_art == 0) & (cosw > math.cos(math.radians(fm.glanz_winkel_grad)))
    grund[glanz] = 5
    sig = m["sigma_k"] * np.nan_to_num(zt, nan=0.0, posinf=0.0) ** 2
    mess = mess + rng.normal(0.0, 1.0, n) * sig
    mess[grund != 0] = np.nan
    return Aufnahme(cam, hw, d, t, idx, mess, grund, glas_art, list(prims))


def maske_verrauschen(m: np.ndarray, rng: np.random.Generator, p_kippen: float = 0.5,
                      versatz_px: float = 0.0) -> np.ndarray:
    """Randpixel einer Instanzmaske kippen (+-1 px): innere Randpixel fallen weg, aeussere kommen dazu;
    dazu ein Versatz der ganzen Maske (gerundet, sigma ``versatz_px`` je Achse)."""
    if versatz_px > 0:
        dy, dx = (int(round(v)) for v in rng.normal(0.0, versatz_px, 2))
        m = np.roll(m, (dy, dx), (0, 1))
    pad = np.pad(m, 1)
    nb_any = np.zeros_like(m)
    nb_all = np.ones_like(m)
    for di, dj in ((0, 1), (1, 0), (1, 2), (2, 1)):
        s = pad[di:di + m.shape[0], dj:dj + m.shape[1]]
        nb_any |= s
        nb_all &= s
    rand_innen = m & ~nb_all
    rand_aussen = ~m & nb_any
    k = rng.random(m.shape) < p_kippen
    return (m & ~(rand_innen & k)) | (rand_aussen & k)
