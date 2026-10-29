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


META = {"tisch_mitte_xy_m": [0.7, 0.42], "tisch_groesse_m": [1.0, 0.4, 0.16], "glas_radius_m": 0.0375,
        "glas_hoehe_m": 0.11, "start_xy_m": [0.55, 0.35], "ziel_xy_m": [0.85, 0.33], "erfolg": True,
        "gruende": [], "zielfehler_xy_m": 0.002, "kippung_end_grad": 0.1, "kippung_max_grad": 0.4,
        "ziel_toleranz_m": 0.01, "kippung_grenze_grad": 10.0}


def _fake_meshes(root):
    """Sieben kleine COLLADA-Wuerfel (5 cm) als Ersatz fuer die iRC_ROS-Meshes."""
    from rebel_model import visual_mesh as vm
    d = root / vm.MESH_UNTERORDNER
    d.mkdir(parents=True)
    ecken = [(x, y, z) for x in (-0.025, 0.025) for y in (-0.025, 0.025) for z in (0.0, 0.05)]
    dreiecke = [(0, 1, 3), (0, 3, 2), (4, 6, 7), (4, 7, 5), (0, 4, 5), (0, 5, 1),
                (2, 3, 7), (2, 7, 6), (0, 2, 6), (0, 6, 4), (1, 5, 7), (1, 7, 3)]
    pos = " ".join(str(c) for e in ecken for c in e)
    p = " ".join(str(i) for t in dreiecke for i in t)
    text = ('<?xml version="1.0"?><COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">'
            '<library_geometries><geometry id="g"><mesh><source id="g-p"><float_array id="a" count="24">'
            f'{pos}</float_array></source><vertices id="g-v"><input semantic="POSITION" source="#g-p"/></vertices>'
            f'<triangles count="12"><input offset="0" semantic="VERTEX" source="#g-v"/><p>{p}</p></triangles>'
            '</mesh></geometry></library_geometries></COLLADA>')
    for f in vm.MESH_DATEIEN:
        (d / f).write_text(text, encoding="utf-8")
    return d


def test_urdf_teile_quader_und_mesh(tmp_path):
    pytest.importorskip("matplotlib")
    import render_video
    cfg = load()
    quader = render_video.urdf_teile(build_urdf(cfg), cfg)
    assert all(isinstance(fb, str) for ts in quader.values() for _, _, fb, _ in ts)
    assert len(quader["link_2"]) == 1 and len(quader["link_2"][0][1]) == 12
    d = _fake_meshes(tmp_path)
    mesh = render_video.urdf_teile(build_urdf(cfg, mesh_dir=str(d)), cfg)
    v, f, farbe, geschlossen = mesh["link_2"][0]
    assert geschlossen and farbe.shape == (len(f), 3)
    assert render_video._aussen_orientiert(v, f)
    # Greifer und Schiene bleiben Quader
    assert isinstance(mesh["gripper_base"][0][2], str) and isinstance(mesh["rail"][0][2], str)


def test_ringe_einfaerben_teilt_nur_kantendreiecke():
    pytest.importorskip("matplotlib")
    import render_video
    cfg = load()
    # Zylindermantel r = 52,5 mm um y bei z = 0 (wie das J3-Gehaeuse von link_3), grob trianguliert
    n = 24
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    ring_xz = np.stack([0.0525 * np.cos(a), 0.0525 * np.sin(a)], 1)
    v = np.concatenate([np.column_stack([ring_xz[:, 0], np.full(n, y), ring_xz[:, 1]]) for y in (-0.05, 0.0)])
    i = np.arange(n)
    j = (i + 1) % n
    f = np.concatenate([np.stack([i, j, n + j], 1), np.stack([i, n + j, n + i], 1)])
    v2, f2, ring = render_video.ringe_einfaerben("link_3", v, f, cfg)
    assert ring.any() and not ring.all()
    flaeche = lambda vv, ff: np.linalg.norm(np.cross(vv[ff[:, 1]] - vv[ff[:, 0]], vv[ff[:, 2]] - vv[ff[:, 0]]), axis=1).sum()
    assert abs(flaeche(v2, f2) - flaeche(v, f)) < 1e-9
    # alle orangen Dreiecke liegen im Band der J3-Fuge (y -31..-23 mm)
    c = v2[f2[ring]].mean(axis=1)
    assert np.all((c[:, 1] >= -0.031) & (c[:, 1] <= -0.023))


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg fehlt")
def test_render_mesh_optik_parallel(tmp_path):
    pytest.importorskip("matplotlib")
    import render_video
    cfg = load()
    rec, labels = _aufzeichnung(0.5)
    d = laden(rec.speichern(tmp_path / "a.npz", labels, META))
    out = tmp_path / "m.mp4"
    info = render_video.rendern(d, build_urdf(cfg, mesh_dir=str(_fake_meshes(tmp_path / "assets"))), out,
                                breite=320, hoehe=180, tempo=1.0, halten=0.5, standbild=tmp_path / "s.png",
                                cfg=cfg, jobs=2)
    assert info["bilder"] == 31 and info["jobs"] == 2 and (tmp_path / "s.png").exists()
    assert not list(tmp_path.glob("render-*"))  # Abschnitte aufgeraeumt
    if shutil.which("ffprobe"):
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries",
                            "stream=codec_name,pix_fmt,nb_read_frames", "-of", "json", str(out)],
                           capture_output=True, text=True, check=True)
        s = json.loads(r.stdout)["streams"][0]
        assert (s["codec_name"], s["pix_fmt"], int(s["nb_read_frames"])) == ("h264", "yuv420p", 31)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg fehlt")
def test_cli_ohne_assets_faellt_auf_quader_zurueck(tmp_path):
    pytest.importorskip("matplotlib")
    rec, labels = _aufzeichnung(0.2)
    npz = rec.speichern(tmp_path / "a.npz", labels, META)
    env = {k: v for k, v in os.environ.items() if k not in ("RAEUMWERK_ASSETS", "RAEUMWERK_HOME")}
    env["RAEUMWERK_HOME"] = str(tmp_path / "leer")
    r = subprocess.run([sys.executable, str(REPO / "scripts" / "render_video.py"), str(npz), "--out",
                        str(tmp_path / "q.mp4"), "--breite", "160", "--hoehe", "90", "--tempo", "1",
                        "--halten", "0.1", "--jobs", "1"], capture_output=True, text=True, env=env, timeout=300)
    assert r.returncode == 0, r.stderr
    assert "OPTIK quader" in r.stdout and (tmp_path / "q.mp4").stat().st_size > 500
    r = subprocess.run([sys.executable, str(REPO / "scripts" / "render_video.py"), str(npz), "--out",
                        str(tmp_path / "x.mp4"), "--optik", "mesh"], capture_output=True, text=True, env=env,
                       timeout=300)
    assert r.returncode == 2 and "keine Meshes" in r.stderr


@pytest.mark.skipif(not os.environ.get("RAEUMWERK_AUFZEICHNUNG"), reason="keine echte Aufzeichnung angegeben")
def test_echte_aufzeichnung():
    d = laden(os.environ["RAEUMWERK_AUFZEICHNUNG"])
    dauer = max(b for a, b in d["meta"]["phasen_s"].values())
    assert d["body_q"].shape[1] == len(_labels()) == len(d["body_label"])
    assert abs(d["body_q"].shape[0] - anzahl_bilder(dauer, 30.0)) <= 1
    assert np.all(np.isfinite(d["body_q"]))
    for name in ("rail", "carriage", "link_1", "finger_left", "finger_right", "glas"):
        assert name in d["body_label"]
