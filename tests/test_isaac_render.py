"""Isaac-Sim-RTX-Rendering: Auftrag, Geometrie, Kodierung (ohne Isaac Sim).

Der echte Render-Test (``test_isaac_render_echt``) laeuft nur mit
``RAEUMWERK_RUN_GPU_SMOKE=1`` und dem Isaac-Sim-venv unter
``$RAEUMWERK_HOME/venvs/isaacsim``, sonst wird er uebersprungen.
"""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("yaml")

from isaac_render import auftrag as A  # noqa: E402
from isaac_render import geometrie as G  # noqa: E402

REPO = Path(__file__).resolve().parents[1]


def _aufzeichnung(dauer=2.0, fps=30.0):
    import xml.etree.ElementTree as ET
    from rebel_model.config import load
    from rebel_model.urdf_gen import build_urdf
    labels = [link.get("name") for link in ET.fromstring(build_urdf(load())).iter("link")] + ["glas"]
    n = int(dauer * fps) + 1
    t = np.arange(n) / fps
    q = np.zeros((n, len(labels), 7))
    q[..., 6] = 1.0
    q[:, -1, 0] = np.linspace(0.6, 0.9, n)      # Glas faehrt 30 cm
    q[:, -1, 2] = 0.21
    phase = ["anfahrt"] * (n // 2) + ["verfahren"] * (n - n // 2)
    meta = {"tisch_mitte_xy_m": [0.7, 0.42], "tisch_groesse_m": [1.0, 0.4, 0.16], "glas_radius_m": 0.035,
            "glas_hoehe_m": 0.1, "start_xy_m": [0.6, 0.4], "ziel_xy_m": [0.9, 0.4], "erfolg": True,
            "zielfehler_xy_m": 0.00088, "kippung_end_grad": 0.1}
    return {"t": t, "body_q": q, "phase": phase, "body_label": labels, "fps": fps, "meta": meta}


# --- Geometrie ----------------------------------------------------------------

def test_glas_geschlossen_und_aussen_orientiert():
    r, h, w, b = 0.035, 0.1, 0.0025, 0.008
    v, f = G.glas_mesh(r, h, w, b, n=256)
    soll = math.pi * (r * r * h - (r - w) ** 2 * (h - b))
    assert G.volumen(v, f) == pytest.approx(soll, rel=0.02)
    # geschlossen: jede Kante genau zweimal, gegenlaeufig
    kanten = np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
    vor = {tuple(k) for k in kanten}
    assert len(vor) == len(kanten)
    assert all((b_, a_) in vor for a_, b_ in vor)
    assert v[:, 2].min() == pytest.approx(-h / 2) and v[:, 2].max() == pytest.approx(h / 2)


def test_scheibe_und_ring_volumen():
    v, f = G.scheibe(0.04, 0.001, n=256)
    assert G.volumen(v, f) == pytest.approx(math.pi * 0.04 ** 2 * 0.001, rel=0.01)
    v, f = G.ring(0.03, 0.04, 0.001, n=256)
    assert G.volumen(v, f) == pytest.approx(math.pi * (0.04 ** 2 - 0.03 ** 2) * 0.001, rel=0.01)


def test_normalen_scharf_am_wuerfel_glatt_am_zylinder():
    # Wuerfel: 90-Grad-Kanten bleiben scharf -> Eckennormale = Flaechennormale
    e = np.array([[x, y, z] for x in (0, 1) for y in (0, 1) for z in (0, 1)], float)
    quads = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    f = np.array([t for a, b, c, d in quads for t in ((a, b, c), (a, c, d))])
    n = G.normalen(e, f, 35.0)
    fn = np.cross(e[f[:, 1]] - e[f[:, 0]], e[f[:, 2]] - e[f[:, 0]])
    fn /= np.linalg.norm(fn, axis=1)[:, None]
    assert np.allclose(n, np.repeat(fn, 3, axis=0), atol=1e-9)
    # Zylindermantel fein: Normalen zeigen radial (glatt)
    v, f = G.rotationskoerper([(0.05, 0.0), (0.05, 0.1)], n=64)
    n = G.normalen(v, f, 35.0)
    p = v[f.reshape(-1)]
    radial = np.column_stack([p[:, 0], p[:, 1], np.zeros(len(p))])
    radial /= np.linalg.norm(radial, axis=1)[:, None]
    assert np.min(np.einsum("ij,ij->i", n, radial)) > 0.999


def test_verschweissen_fasst_dreieckssuppe_zusammen():
    v, f = G.glas_mesh(0.03, 0.08, n=32)
    soup = v[f].reshape(-1, 3)
    v2, f2, gut = G.verschweissen(soup, np.arange(len(soup)).reshape(-1, 3))
    assert gut.all() and len(v2) == len(v)
    assert G.volumen(v2, f2) == pytest.approx(G.volumen(v, f))


def test_quaternion_hin_und_zurueck():
    rng = np.random.default_rng(7)
    for _ in range(20):
        q = rng.normal(size=4)
        q /= np.linalg.norm(q)
        q = -q if q[3] < 0 else q
        assert np.allclose(G.matrix_quat(G.quat_matrix(q)), q, atol=1e-9)
    assert np.allclose(G.quat_matrix([1, 0, 0, 0]), np.diag([1, -1, -1]))


def test_blick_matrix_schaut_aufs_ziel():
    m = G.blick_matrix((2.0, 1.0, 1.5), (0.5, 0.2, 0.3))
    r = m[:3, :3]
    assert np.allclose(r.T @ r, np.eye(3), atol=1e-12) and np.linalg.det(r) == pytest.approx(1.0)
    vor = -r[:, 2]
    soll = np.array([0.5, 0.2, 0.3]) - np.array([2.0, 1.0, 1.5])
    assert np.allclose(vor, soll / np.linalg.norm(soll))
    assert r[2, 1] > 0   # Bild-oben zeigt nach Welt-oben


def test_arm_teil_ringe_an_gelenkfuge():
    """Synthetisches Gelenkgehaeuse von link_2 (Zylinder um y, r = 52,5 mm): der Ring an
    der J2-Fuge (y = -31 .. -23 mm) wird markiert, verfeinert, Normalen je Ecke."""
    from rebel_model.config import load
    mantel = [(0.0525, float(y)) for y in np.linspace(-0.05, 0.05, 11)]   # 1-cm-Raster wie ein CAD-Gehaeuse
    v, f = G.rotationskoerper([(0.0, -0.05)] + mantel + [(0.0, 0.05)], n=48)
    v = v[:, [0, 2, 1]] * np.array([1.0, 1.0, 1.0])     # Achse z -> y
    f = f[:, [0, 2, 1]]                                   # Orientierung nach dem Achstausch erhalten
    v2, f2, nrm, maske = G.arm_teil("link_2", v, f, load())
    assert maske.any() and not maske.all()
    y = v2[f2[maske]].mean(axis=1)[:, 1]
    # nur das J2-Band (y -31..-23 mm): das J3-Band liegt um J3 (z = Oberarm), weit weg
    assert np.all((y > -0.0325) & (y < -0.0215))
    # Gegenprobe: dieselbe Seitenflaeche weiter vom Gelenk (Abstand > Gehaeuse) wird nicht orange
    weit = G.ring_maske("link_2", np.array([[0.0, -0.027, 0.12], [0.0, -0.027, 0.05]]), load())
    assert list(weit) == [False, True]
    assert len(f2) > len(f) and nrm.shape == (3 * len(f2), 3)
    assert G.volumen(v2, f2) == pytest.approx(G.volumen(v, f), rel=1e-6)


# --- Auftrag ------------------------------------------------------------------

def test_zeitplan_wie_matplotlib_video():
    t = A.zeitplan(16.6, 30.0, 0.7, 3.0)
    assert len(t) == int(round(16.6 / 0.7 * 30)) + 1 + 90
    assert t[0] == 0.0 and t[-1] == pytest.approx(16.6, abs=0.03)
    assert np.all(np.diff(t) >= 0)
    assert A.tempo_auto(16.6, 3.0) == pytest.approx(16.6 / 21.0)


def test_interpoliere_endpunkte_und_mitte():
    rec = _aufzeichnung()
    q = A.interpoliere(rec["t"], rec["body_q"], 1.0)
    assert q[-1, 0] == pytest.approx(0.75, abs=1e-9)
    assert np.allclose(A.interpoliere(rec["t"], rec["body_q"], -1)[-1], rec["body_q"][0, -1])
    assert np.allclose(A.interpoliere(rec["t"], rec["body_q"], 99)[-1], rec["body_q"][-1, -1])


def test_auftrag_aus_aufzeichnung_rundreise(tmp_path):
    rec = _aufzeichnung()
    auf = A.aus_aufzeichnung(rec, fps=30.0, halten=1.0)
    assert A.pruefen(auf) == []
    assert auf["koerper"][-1] == "glas" and "glas" in auf["glaeser"]
    assert len(auf["kamera"]) == len(auf["posen"])
    assert auf["ergebnis"].startswith("Erfolg")
    assert {s["material"] for s in auf["statisch"]} <= set(A.MATERIALIEN)
    pfad = A.speichern(auf, tmp_path / "a.npz")
    z = A.laden(pfad)
    assert A.pruefen(z) == []
    assert np.allclose(z["posen"], auf["posen"], atol=1e-6)
    assert z["phase"] == auf["phase"] and z["kamera"] == auf["kamera"]


def test_auftrag_spuelmaschine_greifpose():
    auf = A.aus_spuelmaschine(1)
    assert A.pruefen(auf) == []
    assert auf["quelle"]["erreichbar"] and auf["quelle"]["ik_fehler_max_m"] < 1e-3
    assert len(auf["posen"]) == 1 and "gripper_base" in auf["koerper"]
    formen = {s["form"] for s in auf["statisch"]}
    assert {"quader", "glas", "ring"} <= formen
    kopfueber = [s for s in auf["statisch"] if s["form"] == "glas"]
    assert len(kopfueber) == 4 and all(s["quat"] == [1.0, 0.0, 0.0, 0.0] for s in kopfueber)


def test_auftrag_ausraeumen_aus_meta():
    rec = _aufzeichnung(4.0)
    rec["body_label"] = rec["body_label"][:-1] + ["glas_1"]
    rec["meta"].update({"statisch": [{"name": "korpus_links", "gruppe": "korpus", "mitte": [0.0, 0.0, 0.4],
                                      "halb": [0.01, 0.3, 0.4], "rot": np.eye(3).tolist()},
                                     {"name": "matte_1", "gruppe": "zwischenablage", "mitte": [0.5, 0.5, 0.9],
                                      "halb": [0.05, 0.05, 0.005], "rot": np.eye(3).tolist()}],
                        "ablage_m": [[0.8, 0.5, 0.95]], "erfolge": 1})
    auf = A.aus_ausraeumen(rec, fps=30.0, video_s=3.0, halten=1.0)
    assert A.pruefen(auf) == []
    assert auf["tempo"] == pytest.approx(2.0) and list(auf["glaeser"]) == ["glas_1"]
    assert {s["material"] for s in auf["statisch"]} >= {"edelstahl", "matte", "marke_ziel"}
    assert auf["ergebnis"].startswith("1/1")


def test_pruefen_findet_fehler():
    auf = A.aus_aufzeichnung(_aufzeichnung(), halten=0.0)
    auf["koerper"] = auf["koerper"][:-1]
    auf["statisch"][0]["material"] = "gibtsnicht"
    fehler = A.pruefen(auf)
    assert any("Koerpernamen" in x for x in fehler) and any("Material" in x for x in fehler)


def test_auftrag_cli(tmp_path):
    from greifen.aufzeichnung import Aufzeichner
    rec = _aufzeichnung(1.0)
    a = Aufzeichner(1 / 30.0, 30.0)
    for t, q, p in zip(rec["t"], rec["body_q"], rec["phase"]):
        a.add(t, q, p)
    npz = a.speichern(tmp_path / "rec.npz", rec["body_label"], rec["meta"])
    r = subprocess.run([sys.executable, str(REPO / "scripts/isaac_render_auftrag.py"), "greifdemo", str(npz),
                        "--out", str(tmp_path / "auf.npz")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "AUFTRAG" in r.stdout and (tmp_path / "auf.npz").is_file()


# --- Isaac-Skript ohne Isaac ----------------------------------------------------

def test_isaac_render_ohne_isaacsim_meldet_fehler(tmp_path):
    try:
        import isaacsim  # noqa: F401
        pytest.skip("isaacsim installiert: echter Test unten")
    except ImportError:
        pass
    auf = A.speichern(A.aus_aufzeichnung(_aufzeichnung(0.2), halten=0.0), tmp_path / "a.npz")
    r = subprocess.run([sys.executable, str(REPO / "scripts/isaac_render.py"), str(auf), "--out",
                        str(tmp_path / "o")], capture_output=True, text=True, timeout=120)
    assert r.returncode == 1
    info = json.loads((tmp_path / "o" / "render.json").read_text())
    assert "isaacsim" in info["error"] and info["szene"] == "greifdemo"


def test_isaac_render_sh_prueft_namen(tmp_path):
    env = {**os.environ, "RAEUMWERK_HOME": str(tmp_path), "RAEUMWERK_ISAAC_RENDER_RUNS": str(tmp_path)}
    r = subprocess.run(["bash", str(REPO / "scripts/isaac_render.sh"), "a.npz", "x;y"], capture_output=True,
                       text=True, env=env)
    assert r.returncode == 2 and "ungueltiger Name" in r.stderr
    r = subprocess.run(["bash", str(REPO / "scripts/isaac_render.sh"), "fehlt.npz", "probe"], capture_output=True,
                       text=True, env=env)
    assert r.returncode == 2 and "Auftrag fehlt" in r.stderr


def test_messen_schreibt_json(tmp_path):
    j = tmp_path / "m.json"
    r = subprocess.run([sys.executable, str(REPO / "scripts/isaac_render_messen.py"), "--json", str(j), "--",
                        sys.executable, "-c", "x = bytearray(30 * 2**20); import time; time.sleep(1.2)"],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    m = json.loads(j.read_text())
    assert m["rc"] == 0 and m["ram_peak_mib"] >= 25 and m["neue_listener_nicht_lokal"] == []


# --- Kodierung -----------------------------------------------------------------

def test_video_kodierung_h264_yuv420p_faststart(tmp_path):
    Image = pytest.importorskip("PIL.Image")
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("ffmpeg/ffprobe fehlt")
    sys.path.insert(0, str(REPO / "scripts"))
    import isaac_render_video as V
    auf = A.aus_aufzeichnung(_aufzeichnung(0.5), halten=0.2)
    ordner = tmp_path / "bilder"
    ordner.mkdir()
    for k in range(len(auf["posen"])):
        Image.fromarray(np.full((72, 128, 3), (k * 7) % 255, np.uint8)).save(ordner / f"bild_{k:05d}.png")
    out = tmp_path / "v.mp4"
    info = V.kodieren(ordner, auf, out)
    assert info["bilder"] == len(auf["posen"])
    p = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(out)],
                                  capture_output=True, text=True).stdout)["streams"][0]
    assert p["codec_name"] == "h264" and p["pix_fmt"] == "yuv420p" and (p["width"], p["height"]) == (128, 72)
    daten = out.read_bytes()
    assert 0 < daten.find(b"moov") < daten.find(b"mdat")      # +faststart
    (ordner / f"bild_{2:05d}.png").unlink()
    with pytest.raises(RuntimeError, match="Luecken"):
        V.kodieren(ordner, auf, tmp_path / "w.mp4")


# --- Oeffentliches Repo -----------------------------------------------------------

def test_keine_rechnernamen_oder_absoluten_pfade():
    dateien = list((REPO / "isaac_render").glob("*.py")) + list((REPO / "scripts").glob("isaac_render*"))
    assert len(dateien) >= 6
    verboten = re.compile(r"[\"'](/home|/mnt|/data|/srv)/|\bWB-\d+", re.I)
    # Rechnername nur aus der lokalen, nicht eingecheckten Konfiguration
    env = REPO / "config" / "local.env"
    namen = []
    if env.is_file():
        namen = [z.split("=", 1)[1].strip().strip("\"'") for z in env.read_text().splitlines()
                 if z.startswith("GPU_HOST=")]
    for d in dateien:
        text = d.read_text(encoding="utf-8")
        assert not verboten.search(text), d.name
        assert not any(n and n.lower() in text.lower() for n in namen), d.name


# --- echter Lauf (GPU-Rechner) -----------------------------------------------------

@pytest.mark.skipif(os.environ.get("RAEUMWERK_RUN_GPU_SMOKE") != "1", reason="nur mit RAEUMWERK_RUN_GPU_SMOKE=1")
def test_isaac_render_echt(tmp_path):
    home = Path(os.environ.get("RAEUMWERK_HOME", Path.home() / "raeumwerk"))
    if not (home / "venvs/isaacsim/bin/python").exists():
        pytest.skip("Isaac-Sim-venv fehlt")
    auf = A.speichern(A.aus_spuelmaschine(1), tmp_path / "s.npz")
    env = {**os.environ, "RAEUMWERK_ISAAC_RENDER_RUNS": str(tmp_path)}
    r = subprocess.run(["bash", str(REPO / "scripts/isaac_render.sh"), str(auf), "echt", "--breite", "320",
                        "--hoehe", "180", "--subframes", "2"], capture_output=True, text=True, env=env, timeout=1500)
    assert r.returncode == 0, r.stdout + r.stderr
    info = json.loads((tmp_path / "echt/render.json").read_text())
    assert info["replay_fehler_mm"] < 0.01 and (tmp_path / "echt/bild_00000.png").is_file()
    assert info["helligkeit_mittel"][0] > 10
