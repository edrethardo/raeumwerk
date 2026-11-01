"""Tests fuer die Ablage auf der Arbeitsplatte ueber der Spuelmaschine (``raeumwerk aufbau``).

Das Beispiel ``beispiele/ablage-arbeitsplatte.yaml`` prueft die beste Lage des
Umpositionierungs-Rasters (Roboter kopfueber an der senkrechten Hubachse, 60 Grad zur Maschine,
Fussmitte 0,30 m vor der Front). Ziel ist die Arbeitsplatte ueber der Maschine (Oberkante 0,86 m).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from spuelmaschine import aufbau as AU
from spuelmaschine import belastung as B

REPO = Path(__file__).resolve().parents[1]
BEISPIEL = REPO / "beispiele" / "ablage-arbeitsplatte.yaml"

# Nachgerechnete Halte-Momente |J2| der 9 Beispielplaetze (Last 0,25 kg, ``belastung.schweremomente``).
# Der Wert ist loesungsabhaengig (IK-Starts, Nachbarglaeser als Hindernis); die Toleranz deckt kleine
# Startschwankungen ab, nicht eine andere Zahl. Nenn 10 Nm / Max 12,5 Nm.
MOMENT_GRENZE_NM = 12.5
ERWARTETE_J2_NM = {
    "p_x0.10_y+0.00": 4.95, "p_x0.30_y+0.00": 6.59, "p_x0.50_y+0.00": 4.95,
    "p_x0.10_y-0.20": 12.32, "p_x0.30_y-0.20": 12.33, "p_x0.50_y-0.20": 12.32,
    "p_x0.10_y-0.40": 16.03, "p_x0.30_y-0.40": 17.62, "p_x0.50_y-0.40": 16.03,
}
# Ausnahmen: die hinterste Reihe (y -0,40 m) liegt ueber Max und ist als solche ausgewiesen.
AUSNAHMEN_UEBER_MAX = {"p_x0.10_y-0.40", "p_x0.30_y-0.40", "p_x0.50_y-0.40"}


def test_ablage_platte_beispiel_hat_das_raster():
    """9 Belegungsplaetze (x 0,10/0,30/0,50 m, y 0,00/-0,20/-0,40 m) als stehende Glaeser auf 0,915 m."""
    d = AU.lade_yaml(BEISPIEL)
    a = [x for x in AU.aufgaben(d) if x["gruppe"] == "ablage"]
    assert len(a) == 9
    assert len({x["ziel"] for x in a}) == 9
    p = AU.Aufbau(d).pruefer(0.0, 0.0)
    z = sorted(round(g.mitte[2], 3) for n, g in p.extra_glaeser.items())
    assert z[0] == z[-1] == 0.915  # Glasmitte = Arbeitsplatte (0,86 m) + halbe Glashoehe
    assert len(p.extra_glaeser) == 9


def test_ablage_platte_vordere_reihen_absetzbar():
    """Bei 60 Grad / 0,30 m sind alle 9 Plaetze mit senkrechtem Greifer absetzbar (0,20 m Teilung)."""
    d = AU.lade_yaml(BEISPIEL)
    e = AU.lauf(d, jobs=4, cache=None, log=lambda *_: None)
    assert e["abdeckung"]["ablage_extra"] == {"ok": 9, "n": 9}
    assert all(r["ok"] for r in e["gruppen"]["ablage"])


def test_ablage_platte_j2_der_beispielplaetze_unter_der_momentgrenze():
    """Halte-|J2| der 9 Beispielplaetze: je Platz <= 12,5 Nm, ausser der ausgewiesenen hintersten Reihe.

    Rechnet die Schweremomente mit ``belastung.schweremomente`` (Last 0,25 kg) aus den IK-Posen des
    Beispiel-Laufs nach (q-Ordnung ``[axis7, J1..J6, Finger]`` -> J2 = Index 2). Eine falsche
    Momentaussage (z. B. die frueher behaupteten 4,2 Nm) faellt hier durch.
    """
    d = AU.lade_yaml(BEISPIEL)
    e = AU.lauf(d, jobs=4, cache=None, log=lambda *_: None)
    p = AU.Aufbau(d).pruefer(0.0, 0.0)
    i2 = p.chain.index["joint2"]
    gesehen = {}
    for r in e["gruppen"]["ablage"]:
        assert r["ok"], r["ziel"]
        j2 = abs(float(B.schweremomente(p, np.array(r["q"], float), 0.25)[i2]))
        gesehen[r["ziel"]] = round(j2, 2)
        if r["ziel"] in AUSNAHMEN_UEBER_MAX:
            assert j2 > MOMENT_GRENZE_NM, (r["ziel"], j2)
        else:
            assert j2 <= MOMENT_GRENZE_NM, (r["ziel"], j2)
    assert set(gesehen) == set(ERWARTETE_J2_NM)
    for ziel, soll in ERWARTETE_J2_NM.items():
        assert abs(gesehen[ziel] - soll) <= 0.05, (ziel, gesehen[ziel], soll)
