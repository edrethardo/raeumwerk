"""Tests fuer das offene Regal ueber der Spuelmaschine als Ablageziel (``raeumwerk aufbau``).

Das Beispiel ``beispiele/regal-ueber-maschine.yaml`` prueft den Owner-Aufbau (kopfueber an der
senkrechten Hubachse, 45 Grad zur Maschine, Fussmitte 0,50 m). Regal = offenes Fach ohne Tuer.
"""
from __future__ import annotations

from pathlib import Path

from spuelmaschine import aufbau as AU

REPO = Path(__file__).resolve().parents[1]
BEISPIEL = REPO / "beispiele" / "regal-ueber-maschine.yaml"


def test_regal_beispiel_hat_das_raster():
    """24 Abstellplaetze (x 0,05..0,55 m, y -0,22..-0,50 m), je als stehendes Glas modelliert."""
    d = AU.lade_yaml(BEISPIEL)
    a = [x for x in AU.aufgaben(d) if x["gruppe"] == "ablage"]
    assert len(a) == 24
    assert len({x["ziel"] for x in a}) == 24
    p = AU.Aufbau(d).pruefer(0.0, 0.0)
    z = sorted(round(g.mitte[2], 3) for n, g in p.extra_glaeser.items())
    assert z[0] == z[-1] == 1.505  # Glasmitte = Fachboden (1,45 m) + halbe Glashoehe
    assert len(p.hindernisse) > 24  # Regalwaende + Fachboden sind Hindernisse


def test_regal_kein_platz_erreichbar():
    """Bei 45 Grad / 0,50 m liegt die Reichweitengrenze vor der Regalvorderkante: keiner der
    24 Plaetze ist mit senkrechtem Greifer absetzbar (Grund: ausserhalb der Reichweite)."""
    d = AU.lade_yaml(BEISPIEL)
    e = AU.lauf(d, jobs=4, cache=None, log=lambda *_: None)
    assert e["abdeckung"]["ablage_extra"] == {"ok": 0, "n": 24}
    assert all(not r["ok"] for r in e["gruppen"]["ablage"])
    assert all(r["grund"].startswith("ausserhalb der Reichweite") for r in e["gruppen"]["ablage"])
