"""Aufzeichnung der Koerperposen eines Greifversuchs (fuer das Demo-Video).

Ohne Newton benutzbar (nur numpy): ``Aufzeichner`` sammelt in festen
Simzeit-Abstaenden (Standard 30 Bilder/s) die Posen aller Koerper
(``body_q``: x, y, z, qx, qy, qz, qw je Koerper) und die Ablaufphase;
``speichern`` schreibt eine ``.npz``, ``laden`` liest sie wieder.
Gerendert wird mit ``scripts/render_video.py``.

Inhalt der Datei:
    t            (F,)      Simzeit je Bild in s
    body_q       (F, B, 7) Posen der Koerper (Linkursprung, Quaternion xyzw)
    phase        (F,)      Ablaufphase je Bild (greifen.plan.PHASEN)
    body_label   (B,)      Koerpernamen (URDF-Linkname bzw. ``glas``)
    fps          ()        Bildrate der Aufzeichnung (Simzeit)
    meta_json    ()        JSON: Szene (Tisch, Glas, Ziel) und Ergebnis des Versuchs
"""
from __future__ import annotations

import json
import math
from pathlib import Path


def anzahl_bilder(dauer_s: float, fps: float) -> int:
    """Bilder einer Aufzeichnung ueber ``dauer_s`` (Bild 0 bei t = 0, letztes bei <= dauer_s)."""
    return int(math.floor(dauer_s * fps + 1e-9)) + 1


class Aufzeichner:
    def __init__(self, dt: float, fps: float = 30.0):
        self.dt, self.fps = float(dt), float(fps)
        self.t: list = []
        self.body_q: list = []
        self.phase: list = []

    def faellig(self, step: int) -> bool:
        """True, wenn Schritt ``step`` das naechste Bild liefert (t = k / fps)."""
        k = len(self.t)
        return step * self.dt + 0.5 * self.dt >= k / self.fps

    def add(self, t: float, body_q, phase: str) -> None:
        import numpy as np
        self.t.append(float(t))
        self.body_q.append(np.array(body_q, dtype=np.float32).reshape(-1, 7))
        self.phase.append(str(phase))

    def speichern(self, pfad, body_label, meta: dict | None = None) -> Path:
        import numpy as np
        pfad = Path(pfad)
        pfad.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            pfad, t=np.array(self.t, dtype=np.float64), body_q=np.stack(self.body_q),
            phase=np.array(self.phase), body_label=np.array([str(x) for x in body_label]),
            fps=np.float64(self.fps), meta_json=np.array(json.dumps(meta or {})))
        return pfad


def laden(pfad) -> dict:
    import numpy as np
    with np.load(pfad, allow_pickle=False) as z:
        d = {k: z[k] for k in z.files}
    d["meta"] = json.loads(str(d.pop("meta_json")))
    d["fps"] = float(d["fps"])
    d["phase"] = [str(p) for p in d["phase"]]
    d["body_label"] = [str(x) for x in d["body_label"]]
    return d
