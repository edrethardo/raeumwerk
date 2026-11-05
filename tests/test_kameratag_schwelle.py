"""Schwellenfall der Kameratag-Auswertung: genau auf der Grenze zaehlt als 'stimmt' (kein Gleitkomma-Rest)."""
from __future__ import annotations

import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WURZEL / "scripts"))

import kameratag_auswerten as KA  # noqa: E402


def test_schwelle_genau_getroffen_stimmt():
    # (0.778 - 0.798) * 1000 liefert -20.000000000000018: darf nicht als Abweichung zaehlen
    ab = (0.778 - 0.798) * 1000.0
    assert ab < -20.0
    assert KA.urteil_intervall(ab, -20.0, 20.0, True) == KA.STIMMT
    assert KA.urteil_intervall(-20.0001, -20.0, 20.0, True) == KA.PESS
    assert KA.urteil_intervall(20.0001, -20.0, 20.0, True) == KA.OPT
