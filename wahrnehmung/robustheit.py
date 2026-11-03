"""Posefehler der geschaetzten Objektpose und Heilungsstrategien S0..S6.

Aufbau: Der Fehler wird auf die *geschaetzte* Objektpose gelegt (Versatz plus Drehung),
simuliert wird weiter in der wahren Welt (``griffpose.schaetzen(..., posedrift=)``). Er
sitzt auf der Station (Ensenso) — die D405 am Handgelenk sieht das Ziel unabhaengig neu.

Die Streuung je Kamera kommt aus der eigenen Messung, nicht aus einem Datenblatt:
``docs/griff-verrauscht.md``, Tabelle "Wahrnehmung allein" (20 Seeds, Fehler gegen die
Wahrheit): Ensenso 2,0 mm (Glas) / 3,0 mm (Teller), D405 1,3 mm / 3,2 mm. Beide Werte
sind der Mittelwert der dortigen Reihen; als 1-sigma der jeweiligen Pose genommen.

Strategien (Rueckgabe der Auswertung, siehe ``scripts/griff_robustheit.py``):
  S0 blind        nur Stationskamera, Griff auf der gestoerten Grobpose, keine Korrektur
  S1 Nahkorrektur D405 schaetzt in der (falschen) Vorposition neu
  S2 Fusion       Ensenso- und D405-Schaetzung invers-varianz-gewichtet
  S3 Kreuzprobe   Ensenso<->D405-Abweichung ueber der Schwelle: neu hinsehen oder Abbruch
  S4 Greifer      mechanisch geschluckter Fehler (V-Kontur, Kerbe/Lippe)
  S5 Nachfassen   zweiter Versuch nach Loesen, neu ansehen (setzt S1 voraus)
  S6 Pruefen      Greifweite beim Schliessen gegen die Objektbreite, Ablagepruefung
"""
from __future__ import annotations

import math
from typing import Dict, Optional

import numpy as np

# 1-sigma der Objektpose je Kamera in mm, aus docs/griff-verrauscht.md (Mittel der Reihen)
SIGMA_MM: Dict[str, Dict[str, float]] = {"glas": {"ensenso": 2.0, "d405": 1.3},
                                         "teller": {"ensenso": 3.0, "d405": 3.2}}
# Annahme: eine Achse ist so unsicher wie die andere (die Tabelle misst den 3D-Abstand)
TOL_ABLAGE_MM = 10.0            # Zielfehler der Ablage (ausraeumen.bewertung, docs/verrauscht)
FREIHEITSGRAD = {"glas": ["x", "y"], "teller": ["x", "y", "z"]}


def rodrigues(achse: np.ndarray, grad: float) -> np.ndarray:
    """Drehmatrix um ``achse`` (normiert) um ``grad`` (Grad), Rodrigues-Formel."""
    a = np.asarray(achse, float)
    a = a / np.linalg.norm(a)
    th = math.radians(grad)
    K = np.array([[0.0, -a[2], a[1]], [a[2], 0.0, -a[0]], [-a[1], a[0], 0.0]])
    return np.eye(3) + math.sin(th) * K + (1.0 - math.cos(th)) * K @ K


def drift(rng: np.random.Generator, t_sigma_m: float = 0.0, r_sigma_grad: float = 0.0,
          t_max_m: Optional[float] = None, r_max_grad: Optional[float] = None) -> Dict:
    """Posefehler: Versatz ``dp`` (3D, Gauss um 0 mit ``t_sigma_m``) und eine Drehung um
    eine gleichverteilte Achse mit Winkel ``grad``. ``t_max_m``/``r_max_grad`` kappen den
    Betrag hart (die "hart begrenzte Variante" des Tickets). ``grad`` ist der gezogene
    *Betrag* (immer >= 0)."""
    dp = rng.normal(0.0, t_sigma_m, 3) if t_sigma_m > 0 else np.zeros(3)
    if t_max_m is not None and np.linalg.norm(dp) > t_max_m:
        dp = dp * (t_max_m / np.linalg.norm(dp))
    grad = float(rng.normal(0.0, r_sigma_grad)) if r_sigma_grad > 0 else 0.0
    if r_max_grad is not None:
        grad = float(np.clip(grad, -r_max_grad, r_max_grad))
    ax = rng.normal(0.0, 1.0, 3)
    ax = ax / np.linalg.norm(ax)
    return {"dp": dp, "R": rodrigues(ax, grad), "grad": abs(grad),
            "betrag_m": float(np.linalg.norm(dp)), "achse": ax.tolist()}


def drift_fest(rng: np.random.Generator, t_m: float, r_grad: float, achse=None) -> Dict:
    """Drift mit *festem* Betrag ``t_m`` und fester Drehung ``r_grad`` — fuer das Raster des
    Tickets ({0,5,15} Grad x {0,5,20} mm). Der Versatz liegt in der Waagerechten (die
    Kalibrierung der Station wirkt vor allem seitlich), die Achse ist sonst zufaellig
    (``achse=[0,0,1]`` fuer den Teller: die Gier ist die wirksame Drehlage)."""
    v = rng.normal(0.0, 1.0, 2)
    if np.linalg.norm(v) < 1e-9:
        v = np.array([1.0, 0.0])
    dp = np.array([v[0], v[1], 0.0]) / np.linalg.norm(v) * float(t_m)
    if achse is None:
        ax = rng.normal(0.0, 1.0, 3)
        ax = ax / np.linalg.norm(ax)
    else:
        ax = np.asarray(achse, float)
    return {"dp": dp, "R": rodrigues(ax, r_grad), "grad": abs(float(r_grad)),
            "betrag_m": float(t_m), "achse": np.asarray(ax, float).tolist()}


def wende_an(e: Dict, dr: Dict) -> Dict:
    """Legt den Drift auf eine Ensenso-Schaetzung ``e`` (in place): ``c`` verschieben (das Glas
    fuehrt nur x, y), eine vorhandene ``normale`` drehen und die Gier daraus neu ableiten (Teller)."""
    c = np.asarray(e["c"], float)
    dp = np.asarray(dr["dp"], float)[:c.shape[0]]
    e["c"] = (c + dp).tolist()
    if e.get("normale") is not None:
        nv = np.asarray(dr["R"], float) @ np.asarray(e["normale"], float)
        nv = nv / (np.linalg.norm(nv) or 1.0)
        e["normale"] = nv.tolist()
        gg = math.degrees(math.atan2(-nv[0], nv[1])) if abs(nv[1]) > 1e-9 else 90.0
        if gg > 90.0:
            gg -= 180.0
        if gg < -90.0:
            gg += 180.0
        e["gier_grad"] = gg
    return e


def fusionieren(a, b, s_a_mm: float, s_b_mm: float) -> np.ndarray:
    """Inverse-Varianz-Fusion zweier Posen (gleicher Rahmen). Liefert den gewichteten
    Mittelwert; die resultierende Streuung ist ``1/sqrt(1/s_a^2+1/s_b^2)``."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    wa, wb = 1.0 / float(s_a_mm) ** 2, 1.0 / float(s_b_mm) ** 2
    return (wa * a + wb * b) / (wa + wb)


def sigma_fusion_mm(s_a_mm: float, s_b_mm: float) -> float:
    """Streuung der Fusion zweier unabhaengiger Schaetzungen."""
    return 1.0 / math.sqrt(1.0 / float(s_a_mm) ** 2 + 1.0 / float(s_b_mm) ** 2)


# --- S4: mechanisch geschluckter Fehler (Geometrie der Finger) ------------------------------------

def fangbereich_glas_mm(f) -> float:
    """Lateraler Fangbereich der V-Kontur: das Glas wird bis zur halben Fingerbreite
    ``b/2`` von den zwei Flanken gefuehrt (Fingerkontur ``config/finger.yaml``)."""
    return float(f.b) / 2.0


def gier_toleranz_teller_grad(f) -> float:
    """Zulaessige Gierabweichung des Tellers: der Wulst (Kerbengeometrie) bleibt ueber die
    Fingerbreite im 8-mm-Kerbenband. Axialer Versatz ueber die halbe Fingerbreite
    ``b/2`` ist ``b/2 * sin(theta)``; er darf die halbe Kerbenlaenge nicht ueberschreiten."""
    k0, k1 = f.kerbe
    return math.degrees(math.asin(min(1.0, (k1 - k0) / 2.0 / (float(f.b) / 2.0))))


def erfolg_mechanisch(art: str, fehler_mm: float, gier_grad: float, f,
                      versatz_max_mm: float = 6.0) -> Dict:
    """S4: schluckt der Greifer die geplante Lage noch? Glas oder Teller (Kerbe/Lippe).
    ``versatz_max_mm`` = zulaessige Verschiebung des Greifpunkts (Teller, quer)."""
    if art == "glas":
        grenze = fangbereich_glas_mm(f)
        ok = fehler_mm <= grenze
        return {"ok": bool(ok), "grund": None if ok else "ausserhalb_fangbereich",
                "grenze_mm": grenze, "fehler_mm": float(fehler_mm)}
    grenze = gier_toleranz_teller_grad(f)
    ok = abs(gier_grad) <= grenze and fehler_mm <= versatz_max_mm
    grund = None
    if abs(gier_grad) > grenze:
        grund = "gier_ausserhalb_kerbe"
    elif fehler_mm > versatz_max_mm:
        grund = "greifpunkt_verschoben"
    return {"ok": bool(ok), "grund": grund, "grenze_grad": grenze, "grenze_mm": versatz_max_mm,
            "gier_grad": float(gier_grad), "fehler_mm": float(fehler_mm)}
