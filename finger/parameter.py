"""Parameter der Finger aus ``config/finger.yaml`` und daraus abgeleitete Masse.

Alle Laengen hier in mm (wie im CAD), Fingersystem siehe ``config/finger.yaml``:
z von der Anschlussflaeche zur Spitze, y in Schliessrichtung zum Greifgut,
x quer. Die Innenbezugsebene y = 0 geht durch die Kanten der V-Kontur.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from spuelmaschine import masse

REPO = Path(__file__).resolve().parents[1]
DATEI = REPO / "config" / "finger.yaml"


def roh(path: Path | str | None = None) -> Dict[str, Any]:
    return masse.roh(path, DATEI)


def load(path: Path | str | None = None) -> Dict[str, Any]:
    return masse.werte(roh(path))


@dataclass
class Finger:
    p: Dict[str, Any]

    @classmethod
    def laden(cls, path: Path | str | None = None, **ueber) -> "Finger":
        """``ueber``: ``abschnitt__schluessel=wert`` ueberschreibt einen Parameter."""
        p = load(path)
        for k, v in ueber.items():
            a, s = k.split("__", 1)
            p[a][s] = v
        return cls(p)

    # --- Grundmasse ------------------------------------------------------
    @property
    def L(self) -> float:
        return float(self.p["geometrie"]["laenge_mm"])

    @property
    def b(self) -> float:
        return float(self.p["geometrie"]["breite_mm"])

    @property
    def z_platte(self) -> float:
        return float(self.p["anschluss"]["platte_dicke_mm"])

    @property
    def gamma(self) -> float:
        return math.radians(float(self.p["v_kontur"]["winkel_grad"]))

    @property
    def v_tiefe(self) -> float:
        """Tiefe der V-Nut in der Mitte hinter der Bezugsebene."""
        return self.b / 2.0 * math.tan(self.gamma)

    def dicke(self, z: float) -> float:
        """Dicke in Schliessrichtung (ohne Nut/Taschen/Kerbe) an der Stelle z."""
        g = self.p["geometrie"]
        t0, t1, z1 = float(g["dicke_wurzel_mm"]), float(g["dicke_spitze_mm"]), float(g["verjuengung_bis_mm"])
        if z <= self.z_platte:
            return float(self.p["anschluss"]["platte_tiefe_mm"])
        if z >= z1:
            return t1
        return t0 + (t1 - t0) * (z - self.z_platte) / (z1 - self.z_platte)

    # --- Bereiche entlang z ----------------------------------------------
    @property
    def kerbe(self) -> Tuple[float, float]:
        t = self.p["teller"]
        z1 = self.L - float(t["lippe_laenge_mm"])
        return z1 - float(t["kerbe_laenge_mm"]), z1

    @property
    def lippe(self) -> Tuple[float, float]:
        return self.L - float(self.p["teller"]["lippe_laenge_mm"]), self.L

    @property
    def auflage_z(self) -> Tuple[float, float]:
        a = self.p["auflage"]
        return float(a["von_mm"]), float(a["bis_mm"])

    @property
    def v_z(self) -> Tuple[float, float]:
        v = self.p["v_kontur"]
        return float(v["von_mm"]), float(v["bis_mm"])

    @property
    def auflage_x(self) -> Tuple[float, float]:
        """x-Bereich einer Auflage (Projektion, je Seite)."""
        a = self.p["auflage"]
        x0 = float(a["steg_mitte_mm"])
        return x0, x0 + float(a["breite_mm"]) * math.cos(self.gamma)

    @property
    def auflage_ueberstand(self) -> float:
        a = self.p["auflage"]
        return float(a["dicke_mm"]) - float(a["taschen_tiefe_mm"])

    def flanke_y(self, x: float) -> float:
        """y der V-Flanke bei x (Bezugsebene 0, Mitte -v_tiefe)."""
        return -self.v_tiefe + abs(x) * math.tan(self.gamma)

    # --- Netto-Querschnitt fuer die Balkenrechnung -------------------------
    def netto_hoehe(self, z: float) -> Tuple[float, str]:
        """Kleinste tragende Hoehe in Schliessrichtung an der Stelle z (konservativ:
        Nut und Tasche ueber die ganze Breite abgezogen) und Bereichsname."""
        h = self.dicke(z)
        k0, k1 = self.kerbe
        a0, a1 = self.auflage_z
        v0, v1 = self.v_z
        if z <= self.z_platte:
            return h, "anschlussplatte"
        if k0 <= z < k1:
            return h - float(self.p["teller"]["kerbe_tiefe_mm"]), "kerbe"
        abzug = 0.0
        name = "schaft"
        if v0 <= z <= v1:
            abzug += self.v_tiefe
            name = "v_kontur"
        if a0 <= z <= a1:
            abzug += float(self.p["auflage"]["taschen_tiefe_mm"])
            name = "auflagetasche"
        if z >= self.lippe[0]:
            name = "lippe"
        return h - abzug, name

    # --- Volumen (Naeherung, Kontrolle gegen das CAD) ---------------------
    def volumen_mm3(self, n: int = 2000) -> float:
        """Finger ohne Auflagen: Flaeche des Netto-Profils ueber z integriert, aber
        mit der echten (mittleren) Nut- und Taschentiefe statt der konservativen."""
        a = self.p["anschluss"]
        v_platte = self.b * float(a["platte_tiefe_mm"]) * self.z_platte
        r = float(a["loch_d_mm"]) / 2.0
        rs = float(a["senkung_d_mm"]) / 2.0
        ts = float(a["senkung_tiefe_mm"])
        n_l = int(a["loch_anzahl"])
        v_platte -= n_l * math.pi * (r * r * (self.z_platte - ts) + rs * rs * ts)
        z0 = self.z_platte
        dz = (self.L - z0) / n
        v = 0.0
        k0, k1 = self.kerbe
        a0, a1 = self.auflage_z
        v0, v1 = self.v_z
        xa0, xa1 = self.auflage_x
        tasche = 2.0 * (xa1 - xa0) / math.cos(self.gamma) * float(self.p["auflage"]["taschen_tiefe_mm"])
        for i in range(n):
            z = z0 + (i + 0.5) * dz
            fl = self.b * self.dicke(z)
            if k0 <= z < k1:
                fl = self.b * (self.dicke(z) - float(self.p["teller"]["kerbe_tiefe_mm"]))
            else:
                if v0 <= z <= v1:
                    fl -= self.b * self.v_tiefe / 2.0
                if a0 <= z <= a1:
                    fl -= tasche
            v += fl * dz
        return v_platte + v

    def masse_g(self, werkstoff: str, volumen_mm3: Optional[float] = None) -> float:
        rho = float(self.p["werkstoffe"][werkstoff]["dichte_g_cm3"])
        return rho * (volumen_mm3 if volumen_mm3 is not None else self.volumen_mm3()) / 1000.0

    @property
    def werkstoffe(self) -> List[str]:
        return [k for k in self.p["werkstoffe"] if k != "gewaehlt"]

    @property
    def gewaehlt(self) -> str:
        return str(self.p["werkstoffe"]["gewaehlt"])

    # --- Greifer ----------------------------------------------------------
    def bezug_oeffnung(self, backen_oeffnung_mm: float) -> float:
        """Abstand der Innenbezugsebenen beider Finger bei gegebener Backenoeffnung."""
        return backen_oeffnung_mm - 2.0 * float(self.p["anschluss"]["innen_versatz_mm"])
