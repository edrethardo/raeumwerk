"""Demo-Video: Aufzeichnung der Koerperposen und Offscreen-Render zu MP4.

Ohne Newton. Der Render-Test braucht matplotlib und ffmpeg (sonst skip).
Mit ``RAEUMWERK_AUFZEICHNUNG=<datei.npz>`` (aus ``demo_greifen.py
--aufzeichnen``) wird zusaetzlich eine echte Aufzeichnung geprueft.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("yaml")

from greifen.aufzeichnung import Aufzeichner, anzahl_bilder, laden  # noqa: E402
from rebel_model.config import load  # noqa: E402
from rebel_model.urdf_gen import build_urdf  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))


def _labels():
    import xml.etree.ElementTree as ET
    return [l.get("name") for l in ET.fromstring(build_urdf(load())).iter("link")] + ["glas"]


def _aufzeichnung(dauer, dt=0.002, fps=30.0):
    """Faehrt die Aufzeichnungslogik wie sim_newton.fahren (Schritte + Endbild)."""
    labels = _labels()
    rec = Aufzeichner(dt, fps)
    nsteps = int(np.ceil(dauer / dt))
    q = np.zeros((len(labels), 7))
    q[:, 6] = 1.0
    for step in range(nsteps + 1):
        if rec.faellig(step):
            qq = q.copy()
            qq[-1, :3] = (0.55 + 0.3 * step / nsteps, 0.35, 0.215)
            rec.add(step * dt, qq, "greifen" if step < nsteps // 2 else "verfahren")
    return rec, labels


def test_aufzeichnung_bilder_und_koerper(tmp_path):
    rec, labels = _aufzeichnung(2.0)
    assert len(rec.t) == anzahl_bilder(2.0, 30.0) == 61
    assert np.allclose(np.diff(rec.t), 1 / 30, atol=0.002 + 1e-9)
    p = rec.speichern(tmp_path / "a.npz", labels, {"erfolg": True})
    d = laden(p)
    assert d["body_q"].shape == (61, len(labels), 7)
    assert d["body_label"] == labels and d["meta"] == {"erfolg": True} and d["fps"] == 30.0
    assert len(d["phase"]) == 61


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg fehlt")
def test_render_kleines_mp4(tmp_path):
    pytest.importorskip("matplotlib")
    import render_video

    rec, labels = _aufzeichnung(0.5)
    meta = {"tisch_mitte_xy_m": [0.7, 0.42], "tisch_groesse_m": [1.0, 0.4, 0.16], "glas_radius_m": 0.0375,
            "glas_hoehe_m": 0.11, "start_xy_m": [0.55, 0.35], "ziel_xy_m": [0.85, 0.33], "erfolg": True,
            "gruende": [], "zielfehler_xy_m": 0.002, "kippung_end_grad": 0.1, "kippung_max_grad": 0.4,
            "ziel_toleranz_m": 0.01, "kippung_grenze_grad": 10.0}
    d = laden(rec.speichern(tmp_path / "a.npz", labels, meta))
    out = tmp_path / "v.mp4"
    info = render_video.rendern(d, build_urdf(load()), out, breite=320, hoehe=180, tempo=1.0, halten=0.5,
                                standbild=tmp_path / "s.png")
    assert out.stat().st_size > 1000 and (tmp_path / "s.png").exists()
    assert info["bilder"] == 16 + 15
    assert out.read_bytes()[4:8] == b"ftyp"
    if shutil.which("ffprobe"):
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=codec_name,pix_fmt,width,height,nb_frames", "-of", "json", str(out)],
                           capture_output=True, text=True, check=True)
        s = json.loads(r.stdout)["streams"][0]
        assert (s["codec_name"], s["pix_fmt"], s["width"], s["height"]) == ("h264", "yuv420p", 320, 180)
        assert int(s["nb_frames"]) == 31


def test_tempo_auto():
    import render_video
    assert render_video.tempo_auto(30.0, 4.0) == 1.0
    assert abs(render_video.tempo_auto(10.0, 4.0) - 0.5) < 1e-9


@pytest.mark.skipif(not os.environ.get("RAEUMWERK_AUFZEICHNUNG"), reason="keine echte Aufzeichnung angegeben")
def test_echte_aufzeichnung():
    d = laden(os.environ["RAEUMWERK_AUFZEICHNUNG"])
    dauer = max(b for a, b in d["meta"]["phasen_s"].values())
    assert d["body_q"].shape[1] == len(_labels()) == len(d["body_label"])
    assert abs(d["body_q"].shape[0] - anzahl_bilder(dauer, 30.0)) <= 1
    assert np.all(np.isfinite(d["body_q"]))
    for name in ("rail", "carriage", "link_1", "finger_left", "finger_right", "glas"):
        assert name in d["body_label"]
