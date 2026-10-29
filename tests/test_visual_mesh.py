"""Visual-Meshes des ReBeL (rebel_model/visual_mesh.py, urdf_gen mit mesh_dir).

Ohne Assets laufen nur die Tests mit selbst erzeugten Daten; der
Ausrichtungstest gegen die echten iRC_ROS-Meshes braucht
``scripts/fetch_assets.sh`` und ``RAEUMWERK_ASSETS`` (sonst skip).
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("yaml")

from rebel_model import visual_mesh as vm  # noqa: E402
from rebel_model.config import load  # noqa: E402
from rebel_model.urdf_gen import build_urdf  # noqa: E402

TOLERANZ_M = 0.005

WUERFEL_DAE = """<?xml version="1.0" encoding="utf-8"?>
<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">
 <asset><unit meter="{unit}"/></asset>
 <library_geometries><geometry id="g"><mesh>
  <source id="g-pos"><float_array id="g-pos-a" count="24">{pos}</float_array></source>
  <source id="g-nrm"><float_array id="g-nrm-a" count="3">0 0 1</float_array></source>
  <vertices id="g-v"><input semantic="POSITION" source="#g-pos"/></vertices>
  <triangles count="12"><input offset="0" semantic="VERTEX" source="#g-v"/>
   <input offset="1" semantic="NORMAL" source="#g-nrm"/><p>{p}</p></triangles>
 </mesh></geometry></library_geometries>
 <library_visual_scenes><visual_scene id="s"><node id="n">{knoten}<instance_geometry url="#g"/></node>
 </visual_scene></library_visual_scenes>
</COLLADA>
"""
_ECKEN = [(x, y, z) for x in (0, 1) for y in (0, 1) for z in (0, 1)]
_DREIECKE = [(0, 1, 3), (0, 3, 2), (4, 6, 7), (4, 7, 5), (0, 4, 5), (0, 5, 1),
             (2, 3, 7), (2, 7, 6), (0, 2, 6), (0, 6, 4), (1, 5, 7), (1, 7, 3)]


def _wuerfel(tmp_path, unit="1", knoten=""):
    pos = " ".join(f"{c}" for e in _ECKEN for c in e)
    p = " ".join(f"{i} 0" for t in _DREIECKE for i in t)
    f = tmp_path / "w.dae"
    f.write_text(WUERFEL_DAE.format(unit=unit, pos=pos, p=p, knoten=knoten), encoding="utf-8")
    return f


def test_dae_laden_einheit_und_dreiecke(tmp_path):
    v, f = vm.dae_laden(_wuerfel(tmp_path, unit="0.001"))
    assert v.shape == (8, 3) and f.shape == (12, 3)
    assert np.isclose(v.max(), 0.001) and f.max() == 7


def test_dae_laden_lehnt_knotentransformation_ab(tmp_path):
    with pytest.raises(ValueError, match="matrix"):
        vm.dae_laden(_wuerfel(tmp_path, knoten="<matrix>1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1</matrix>"))


def test_dezimieren_kugel():
    # feine Kugel: Clustering reduziert stark, Form (Radius) bleibt auf Zellgroesse genau
    n = 80
    th, ph = np.meshgrid(np.linspace(0, np.pi, n), np.linspace(0, 2 * np.pi, n, endpoint=False), indexing="ij")
    v = np.stack([np.sin(th) * np.cos(ph), np.sin(th) * np.sin(ph), np.cos(th)], -1).reshape(-1, 3) * 0.05
    idx = np.arange(n * n).reshape(n, n)
    a, b = idx[:-1, :], idx[1:, :]
    c, d = np.roll(a, -1, 1), np.roll(b, -1, 1)
    f = np.concatenate([np.stack([a, b, d], -1).reshape(-1, 3), np.stack([a, d, c], -1).reshape(-1, 3)])
    nv, nf, zelle = vm.dezimieren_bis(v, f, 1500)
    assert len(nf) <= 1500 < len(f)
    assert nf.max() < len(nv)
    r = np.linalg.norm(nv, axis=1)
    assert np.all(np.abs(r - 0.05) < zelle)


def _ohne_visuals(urdf: str) -> str:
    return re.sub(r"\s*<visual>.*?</visual>", "", urdf, flags=re.S)


def test_urdf_mit_meshes_aendert_nur_visuals(tmp_path):
    """Physik und Kollision bleiben gleich: ohne <visual> sind beide URDFs identisch."""
    cfg = load()
    ohne = build_urdf(cfg)
    mit = build_urdf(cfg, mesh_dir=tmp_path)
    assert "<mesh" not in ohne
    assert mit.count("<mesh") == 7
    assert _ohne_visuals(mit) == _ohne_visuals(ohne)
    # Standardaufruf (Simulation) ist unveraendert: Quader-Visuals wie Kollisionen
    root = ET.fromstring(ohne)
    for link in root.iter("link"):
        assert len(link.findall("visual")) == len(link.findall("collision"))


def test_urdf_mesh_visuals_tragen_zuordnung(tmp_path):
    cfg = load()
    root = ET.fromstring(build_urdf(cfg, mesh_dir=tmp_path))
    erwartet = {x.link: x for x in vm.zuordnung(cfg)}
    for link in root.iter("link"):
        meshes = link.findall("visual/geometry/mesh")
        if link.get("name") not in erwartet:
            assert not meshes
            continue
        (m,) = meshes
        x = erwartet[link.get("name")]
        assert m.get("filename").endswith("/" + x.datei)
        assert np.allclose([float(s) for s in m.get("scale").split()], x.skala)
        org = link.find("visual/origin")
        assert np.allclose([float(s) for s in org.get("xyz").split()], x.xyz) and org.get("rpy") == "0 0 0"
        # Skalierung nur entlang der Gliedachse und hoechstens 6 %
        assert x.skala[:2] == (1.0, 1.0) and abs(x.skala[2] - 1.0) < 0.06


def test_mesh_verzeichnis_ohne_assets(tmp_path, monkeypatch):
    monkeypatch.delenv("RAEUMWERK_ASSETS", raising=False)
    monkeypatch.delenv("RAEUMWERK_HOME", raising=False)
    assert vm.mesh_verzeichnis() is None
    assert vm.mesh_verzeichnis(tmp_path) is None
    d = tmp_path / vm.MESH_UNTERORDNER
    d.mkdir(parents=True)
    for f in vm.MESH_DATEIEN[:-1]:
        (d / f).write_text("x")
    assert vm.mesh_verzeichnis(tmp_path) is None  # unvollstaendig -> Quader
    (d / vm.MESH_DATEIEN[-1]).write_text("x")
    monkeypatch.setenv("RAEUMWERK_ASSETS", str(tmp_path))
    assert vm.mesh_verzeichnis() == d


def _assets():
    import os
    d = vm.mesh_verzeichnis(os.environ.get("RAEUMWERK_ASSETS")) if os.environ.get("RAEUMWERK_ASSETS") else None
    if d is None:
        pytest.skip("keine Meshes: scripts/fetch_assets.sh und RAEUMWERK_ASSETS setzen")
    return d


def test_ausrichtung_mesh_zu_gelenken():
    """Jedes Glied-Mesh sitzt <= 5 mm auf den Gelenken unseres Modells."""
    d = _assets()
    fehler = vm.ausrichtung(load(), d)
    assert set(fehler) == {"base_link", "link_1", "link_2", "link_3", "link_4", "link_5", "link_6"}
    zeilen = [f"{l}: " + ", ".join(f"{k} {v * 1e3:.2f} mm" for k, v in m.items()) for l, m in fehler.items()]
    print("\n".join(zeilen))
    schlecht = {f"{l}.{k}": v for l, m in fehler.items() for k, v in m.items() if not v <= TOLERANZ_M}
    assert not schlecht, schlecht


def test_ausrichtung_erkennt_versatz(monkeypatch):
    """Gegenprobe: ein um 8 mm verschobenes Mesh faellt durch."""
    d = _assets()
    echt = vm.zuordnung

    def verschoben(cfg):
        out = echt(cfg)
        x = out[2]
        out[2] = vm.Visual(x.link, x.datei, (0.008, 0.0, 0.0), x.skala)
        return out

    monkeypatch.setattr(vm, "zuordnung", verschoben)
    f = vm.ausrichtung(load(), d)
    assert max(f["link_2"].values()) > TOLERANZ_M


def test_meshes_dezimiert_klein_genug():
    d = _assets()
    for x in vm.zuordnung(load()):
        v, f = vm.dae_laden(d / x.datei)
        nv, nf, _ = vm.dezimieren_bis(v, f, 1500)
        assert 0 < len(nf) <= 1500
        # Huelle bleibt: Ausdehnung aendert sich um hoechstens 5 mm
        assert np.all(np.abs((nv.max(0) - nv.min(0)) - (v.max(0) - v.min(0))) < 0.005)
