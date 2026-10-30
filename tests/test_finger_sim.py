"""Teller im Newton-Lauf starten in der Lage der Planungsform (Korb und Staender)."""
from __future__ import annotations

import numpy as np

from finger.a1 import teller_koerper
from finger.sim import RX_SCHEIBE, teller_koerper_rot


def _normale_welt(rot_koerper):
    # Scheibenachse im Koerpersystem: RX_SCHEIBE @ z
    return rot_koerper @ RX_SCHEIBE @ np.array([0.0, 0.0, 1.0])


def test_teller_im_korb_startet_ungedreht():
    k = teller_koerper("t", (0.0, 0.0, 0.0), 0.12, 0.01)
    assert np.allclose(teller_koerper_rot(k.rot), np.eye(3))


def test_teller_im_staender_startet_mit_normale_entlang_x():
    k = teller_koerper("t", (0.0, 0.0, 0.0), 0.12, 0.01, normale_x=True)
    R = teller_koerper_rot(k.rot)
    assert np.allclose(R @ R.T, np.eye(3)) and np.isclose(np.linalg.det(R), 1.0)
    n = _normale_welt(R)
    assert np.allclose(np.abs(n), [1.0, 0.0, 0.0])
    assert np.allclose(n, k.rot @ np.array([0.0, 0.0, 1.0]))
    assert np.allclose(R @ np.array([0.0, 0.0, 1.0]), [0.0, 0.0, 1.0])   # bleibt hochkant
