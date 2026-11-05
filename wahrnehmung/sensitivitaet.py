"""Sensitivitaetsanalyse der Wahrnehmungskette (Kameratag P4): Parameter, Zielgroessen, Sobol-Schaetzer.

Reine Logik ohne Raycast (testbar). Ausgewertet wird das geometrische Wahrnehmungsmodell mit wahrer
Maske (``scripts/sensitivitaet_lauf.py``); die Erkennungsrate und die Zielverwechslung gehen
*analytisch* als Wahrscheinlichkeiten ein (Mischung der Ergebnisse mit wahrer Maske), alles andere
ist ein Eingang des Modells.

Zielgroessen je Objekt (Glas, Teller) und Kette K (heutige Pruefung) / A (neu hinsehen) / B (Mechanik-Prior):
  erfolg      Anteil der Versuche, in denen die Kette greift UND der Griff mechanisch ok ist
  unbemerkt   Anteil der Versuche, in denen die Kette greift, der Griff aber nicht ok ist
  brauchbar   Anteil der Versuche mit brauchbaren Aufnahmen: beide Schaetzer (Station, D405) nehmen an
              und die D405-Pose liegt <= 10 mm neben der Wahrheit (Kreuzprobe der Kette nicht eingerechnet)
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence

import numpy as np

MAST = {   # Name: (Mast x, y, z, Neigung Grad). Haupt/hoeher/Ausleger aus dem Ast der Mastposition (P1), Bestand = main
    "haupt": ((0.55, 0.70, 1.25), 55.0),
    "hoeher": ((0.55, 0.70, 1.45), 60.0),
    "bestand": ((0.55, 0.50, 1.35), 60.0),
    "ausleger": ((0.55, 0.60, 1.30), 60.0),
}
MAST_NAMEN = list(MAST)

BRAUCHBAR_MM = 10.0            # D405-Pose gegen Wahrheit (Ablagetoleranz ``robustheit.TOL_ABLAGE_MM``)
GIER_PHYSIK_GRAD = 4.0         # Annahme: Newton-Eckfaelle: Gierfehler 2 Grad ok, ~6 Grad Fehlgriff -> 4 Grad dazwischen


@dataclass(frozen=True)
class Param:
    name: str
    text: str
    einheit: str
    lo: float
    hi: float
    plan: float
    quelle: str
    typ: str = "kont"          # kont | kat | wahrsch
    arten: tuple = ("glas", "teller")   # fuer welche Objekte das Modell den Parameter nutzt

    def wert(self, u: float) -> float:
        if self.typ == "kat":
            return float(min(int(u * (self.hi + 1)), int(self.hi)))
        return self.lo + float(u) * (self.hi - self.lo)


PARAMETER: List[Param] = [
    Param("dicke_mm", "Tellerrand-Dicke (Randwulst)", "mm", 3.0, 12.0, 5.0,
          "Auftrag 3-6 mm (config/finger.yaml, 5 mm); 12 mm = Szenenannahme ohne Quelle (docs/kameratag-p3.md)",
          arten=("teller",)),
    Param("gier_grad", "Teller-Gier im Staender (wahr, Betrag)", "Grad", 0.0, 8.0, 1.0,
          "Prior +-1 Grad (docs/griff-prior.md); Newton: 3 Grad ok, 7 Grad Fehlgriff", arten=("teller",)),
    Param("glas_lage_mm", "Glaslage im Slot (Welt +-)", "mm", 0.0, 10.0, 5.0,
          "Prior +-5 mm (Annahme, docs/griff-verrauscht.md); P2 testet bis +-15 mm", arten=("glas",)),
    Param("teller_lage_mm", "Tellerlage x/y im Korb (Welt +-)", "mm", 0.0, 15.0, 5.0,
          "Prior +-5 mm (Annahme); P2 testet bis +-15 mm", arten=("teller",)),
    Param("kalib_versatz_mm", "Kalibrierfehler Station: Versatz", "mm", 0.0, 30.0, 5.0,
          "Ticket 0-30 mm; P1/P2 rechnen sigma 20 mm; Plan-Wert 5 mm = nach Kalibrierung (Annahme)"),
    Param("kalib_dreh_grad", "Kalibrierfehler Station: Drehung", "Grad", 0.0, 20.0, 5.0,
          "Ticket 0-20 Grad; P1/P2 rechnen sigma 15 Grad; Plan-Wert 5 Grad (Annahme)"),
    Param("rausch_ens", "Tiefenrauschen Station (Faktor auf 0,219 mm*z^2)", "x", 0.5, 3.0, 1.0,
          "Datenblatt C57-6-S 0,219 mm bei 1 m; Spanne 0,5-3x laut Ticket"),
    Param("rausch_d405", "Tiefenrauschen D405 (Faktor)", "x", 0.5, 3.0, 1.0,
          "Modell k=0,02 1/m (Annahme, +-2 % bei 50 cm laut Datenblatt als 2 sigma); Spanne wie Station"),
    Param("maske_versatz_px", "Maske gegen Tiefe versetzt (sigma)", "px", 0.0, 3.0, 0.7,
          "Modellannahme 0,7 px (sensor.Fehlermodell); P3-Masken IoU 0,72-0,80 sprechen fuer mehr"),
    Param("maske_kipp", "Randpixel der Maske kippen (Wahrsch.)", "-", 0.0, 1.0, 0.5,
          "Modellannahme 0,5 (sensor.Fehlermodell)"),
    Param("maske_bias_px", "Maskenrand zu gross (+) / zu klein (-)", "px", -3.0, 3.0, 0.0,
          "Annahme; ersetzt die Streuung der Erkennungsmasken (P3: IoU 0,8 Median Baseline)"),
    Param("mast", "Mastposition (0 Haupt, 1 hoeher, 2 Bestand, 3 einfacher Ausleger)", "Klasse", 0.0, 3.0, 0.0,
          "Positionen aus dem Mast-Branch (docs/stationssichtbarkeit.md): Haupt (0,55;0,70;1,25) 55 Grad, "
          "hoeher (0,55;0,70;1,45) 60 Grad, Bestand (0,55;0,50;1,35) 60 Grad, Ausleger (0,55;0,60;1,30) 60 Grad",
          typ="kat"),
    Param("erk_glas", "Erkennungsrate Glas (Maske am Nennort gefunden)", "-", 0.0, 0.9, 0.55,
          "P3: Baseline 55 % (Tag 86, Kueche 66, dunkel 0), Mask R-CNN 31 %", typ="wahrsch", arten=("glas",)),
    Param("erk_teller", "Erkennungsrate Teller", "-", 0.0, 0.9, 0.45,
          "P3: Baseline 45 % (dunkel 31, Kueche 54); Mask R-CNN 0 % klassenrichtig", typ="wahrsch",
          arten=("teller",)),
    Param("verwechslung", "Zielverwechslung (Nachbarmaske, gegeben erkannt)", "-", 0.0, 0.2, 0.05,
          "Ticket 0-20 %; P3: Nachbarverwechslung Baseline 9 % (Glas), 16 % (Teller)", typ="wahrsch"),
]
NAME = [p.name for p in PARAMETER]
PHYS = [p for p in PARAMETER if p.typ != "wahrsch"]          # gehen ins Modell
WAHRSCH = [p for p in PARAMETER if p.typ == "wahrsch"]       # analytisch
PLAN = {p.name: p.plan for p in PARAMETER}


def von_einheit(u: Sequence[float], params: Sequence[Param] = PARAMETER) -> Dict[str, float]:
    """Punkt im Einheitswuerfel -> Parameterwerte."""
    return {p.name: p.wert(float(x)) for p, x in zip(params, u)}


def design(n: int, seed: int = 20261105, params: Sequence[Param] = PHYS) -> np.ndarray:
    """Scrambled-Sobol-Folge (n Punkte, Dimension = ``params``) im Einheitswuerfel; n = 2^k empfohlen."""
    from scipy.stats import qmc
    return qmc.Sobol(d=len(params), scramble=True, seed=seed).random(n)


# --- Zielgroessen aus einer Modellzeile ------------------------------------------------------------

def wilson(k: int, n: int, z: float = 1.96):
    if n == 0:
        return 0.0, 1.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def _ok(art: str, b: Optional[dict], physik: bool) -> Optional[bool]:
    """Griff ok? Geometrie (Modell) oder 'Physik' (Teller: Gierfehler <= GIER_PHYSIK_GRAD, Versatz <= 6 mm)."""
    if b is None:
        return None
    if not physik or art == "glas":
        return bool(b["ok"])
    return bool(b["mm"] <= 6.0 and b["gier_fehler"] <= GIER_PHYSIK_GRAD)


def ziele_zeile(z: dict, physik: bool = False) -> Dict[str, float]:
    """Saubere (wahre-Maske-)Ergebnisse einer Zeile als 0/1: Erfolg/Unbemerkt je Kette, brauchbar."""
    art = z["art"]
    out: Dict[str, float] = {}
    s1 = z.get("s1")
    o1 = bool(_ok(art, s1, physik))
    k_greift = bool(z.get("ok_std")) and s1 is not None
    out["erfolg_K"] = float(k_greift and o1)
    out["unb_K"] = float(k_greift and not o1)
    a_greift = bool(z.get("a_annahme")) and s1 is not None
    out["erfolg_A"] = float(a_greift and o1)
    out["unb_A"] = float(a_greift and not o1)
    b = z.get("b")
    ob = bool(_ok(art, b, physik))
    b_greift = bool(z.get("b_annahme")) and b is not None
    out["erfolg_B"] = float(b_greift and ob)
    out["unb_B"] = float(b_greift and not ob)
    d = z.get("d405_mm")
    out["brauch"] = float(bool(z.get("ensenso_ok")) and d is not None and d <= BRAUCHBAR_MM)
    return out


CHAINS = ("K", "A", "B")
KENN = [f"{m}_{c}" for m in ("erfolg", "unb") for c in CHAINS] + ["brauch"]


def mischen(sauber: Dict[str, float], erk: float, verw: float, unb_verw: Dict[str, float] | None = None) -> Dict[str, float]:
    """Erkennungsrate ``erk`` und Zielverwechslung ``verw`` (gegeben erkannt) analytisch einrechnen.

    Nicht erkannt: kein Griff (weder Erfolg noch unbemerkt noch brauchbar). Verwechselt: die Kette
    greift nie erfolgreich; unbemerkt mit der gemessenen Rate ``unb_verw`` je Kette (Standard 0, P2: 0/64).
    """
    unb_verw = unb_verw or {}
    out = {}
    for k, v in sauber.items():
        if k.startswith("erfolg") or k == "brauch":
            out[k] = erk * (1.0 - verw) * v
        else:
            out[k] = erk * ((1.0 - verw) * v + verw * unb_verw.get(k, 0.0))
    return out


# --- Sobol-Indizes (Saltelli 2010 / Jansen) -------------------------------------------------------

def sobol(f: Callable[[np.ndarray], np.ndarray], k: int, n: int = 4096, seed: int = 1, boot: int = 100):
    """Erste Ordnung S1 und Gesamt-Index ST je Eingang eines Einheitswuerfels [0,1]^k.

    ``f`` bildet (m, k) auf (m,) ab. Kosten n*(k+2) Auswertungen. Rueckgabe: dict mit s1, st, jeweils
    (Mittel, 2,5 %, 97,5 % aus Bootstrap ueber die Stichprobe), plus ``var``.
    """
    from scipy.stats import qmc
    ab = qmc.Sobol(d=2 * k, scramble=True, seed=seed).random(n)
    A, B = ab[:, :k], ab[:, k:]

    def f2(x):
        y = np.asarray(f(x), float)
        return y.reshape(len(x), -1)

    fA, fB = f2(A), f2(B)                                 # (n, T): T Zielgroessen gleichzeitig
    fAB = []
    for i in range(k):
        C = A.copy()
        C[:, i] = B[:, i]
        fAB.append(f2(C))
    fAB = np.array(fAB)                                   # (k, n, T)
    T = fA.shape[1]

    def idx(sel):
        a, b, c = fA[sel], fB[sel], fAB[:, sel, :]
        var = np.var(np.concatenate([a, b]), axis=0)      # (T,)
        ok = var > 1e-15
        v = np.where(ok, var, 1.0)
        s1 = np.mean(b[None] * (c - a[None]), axis=1) / v         # (k, T)
        st = 0.5 * np.mean((a[None] - c) ** 2, axis=1) / v
        return np.where(ok, s1, 0.0), np.where(ok, st, 0.0), var

    s1, st, var = idx(np.arange(n))
    rng = np.random.default_rng(seed + 1)
    bs1, bst = [], []
    for _ in range(boot):
        s = rng.integers(0, n, n)
        a, b, _v = idx(s)
        bs1.append(a)
        bst.append(b)
    sq = (lambda x: x[..., 0]) if T == 1 and np.asarray(f(A[:1])).ndim == 1 else (lambda x: x)
    return {"var": sq(var.reshape(1, -1))[0] if T == 1 else var, "s1": sq(s1), "st": sq(st),
            "s1_ci": sq(np.percentile(np.array(bs1), [2.5, 97.5], axis=0)) if boot else None,
            "st_ci": sq(np.percentile(np.array(bst), [2.5, 97.5], axis=0)) if boot else None}
