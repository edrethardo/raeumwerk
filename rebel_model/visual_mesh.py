"""Visual-Meshes des ReBeL aus iRC_ROS (nur lokal geladen, nicht im Repo).

Die Meshes ``Joint0.dae`` … ``Joint6.dae`` stammen aus
CommonplaceRobotics/iRC_ROS (``irc_ros_description/meshes/igus_rebel_6dof_00``,
Apache-2.0, Quelle und Pruefsummen in ``docs/robotermodell.md``) und werden
von ``scripts/fetch_assets.sh`` nach ``$RAEUMWERK_ASSETS/irc_ros/meshes/…``
geholt. Sie sind reine Optik: Physik und Kollision bleiben bei den Quadern aus
``urdf_gen`` (``build_urdf(cfg)`` ohne ``mesh_dir`` ist unveraendert).

Ausrichtung: Die Linkframes von iRC_ROS liegen in den Gelenken und haben bei
gleicher Pose dieselbe Orientierung wie unsere (Nullpunkt-Umrechnung siehe
``docs/robotermodell.md`` §2), also keine Drehung. Die Gelenkabstaende weichen
aber ab (Datenblatt gegen iRC_ROS). Deshalb wird jedes Mesh entlang seiner
Gliedachse (z) so skaliert/verschoben, dass seine Gelenkgehaeuse auf unseren
Gelenken sitzen. ``ausrichtung()`` misst das nach (``tests/test_visual_mesh.py``).

Nur numpy (und die Standardbibliothek), kein trimesh.
"""
from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

MESH_UNTERORDNER = "irc_ros/meshes/igus_rebel_6dof_00"
MESH_DATEIEN = [f"Joint{i}.dae" for i in range(7)]

# Masse der iRC_ROS-Meshes in ihrem eigenen Linkframe (gemessen an den Dateien
# mit den Pruefsummen aus scripts/fetch_assets.sh; Laengen in m).
CPR_J1_HOEHE = 0.100       # Joint0: Fuss 0..0,100 (= J1)
CPR_J2_AB_J1 = 0.149       # Joint1: Gehaeuse J2 bei z = 0,149
CPR_OBERARM = 0.2384       # Joint2: J2 -> J3
CPR_J3_MESH_OBEN = 0.149   # Joint3: Teilfuge zum Unterarm bei z = 0,149 ab J3
CPR_J4_MESH_UNTEN = 0.030  # Joint4: beginnt 0,030 ueber seinem Frame (iRC_ROS Issue 15)
CPR_J4_AB_J5 = 0.170       # Joint4: J4-Frame -> J5
CPR_J6_AB_J5 = 0.1208      # Joint5: J5 -> J6
CPR_FLANSCH_DICKE = 0.0012  # Joint6: Flanschscheibe 0..0,0012


@dataclass(frozen=True)
class Visual:
    link: str
    datei: str
    xyz: Tuple[float, float, float]
    skala: Tuple[float, float, float]


def zuordnung(cfg) -> List[Visual]:
    """Glied -> Mesh mit Lage (xyz) und Skalierung, aus den Werten in ``cfg``."""
    a = cfg.arm
    j1 = a["j1_hoehe_m"]
    l1 = a["j2_hoehe_m"] - j1
    j4 = a["j4_ab_j3_m"]
    l4 = a["unterarm_m"] - j4
    l6 = a["hand_m"] - a["j6_ab_j5_m"]
    off4 = l4 - CPR_J4_AB_J5                       # J5 des Meshes auf unser J5
    s3 = (j4 + off4 + CPR_J4_MESH_UNTEN) / CPR_J3_MESH_OBEN  # Fuge J3-/J4-Mesh schliessen
    return [
        Visual("base_link", "Joint0.dae", (0.0, 0.0, 0.0), (1.0, 1.0, j1 / CPR_J1_HOEHE)),
        Visual("link_1", "Joint1.dae", (0.0, 0.0, 0.0), (1.0, 1.0, l1 / CPR_J2_AB_J1)),
        Visual("link_2", "Joint2.dae", (0.0, 0.0, 0.0), (1.0, 1.0, a["oberarm_m"] / CPR_OBERARM)),
        Visual("link_3", "Joint3.dae", (0.0, 0.0, 0.0), (1.0, 1.0, s3)),
        Visual("link_4", "Joint4.dae", (0.0, 0.0, off4), (1.0, 1.0, 1.0)),
        Visual("link_5", "Joint5.dae", (0.0, 0.0, 0.0), (1.0, 1.0, a["j6_ab_j5_m"] / CPR_J6_AB_J5)),
        Visual("link_6", "Joint6.dae", (0.0, 0.0, l6 - CPR_FLANSCH_DICKE), (1.0, 1.0, 1.0)),
    ]


def mesh_verzeichnis(root: Optional[str | Path] = None) -> Optional[Path]:
    """Ordner mit allen sieben Meshes oder None (dann Quader-Optik).

    Reihenfolge: Argument, ``$RAEUMWERK_ASSETS``, ``$RAEUMWERK_HOME/assets``.
    """
    kandidaten = [root] if root else [os.environ.get("RAEUMWERK_ASSETS"),
                                      os.environ.get("RAEUMWERK_HOME") and
                                      str(Path(os.environ["RAEUMWERK_HOME"]) / "assets")]
    for k in kandidaten:
        if not k:
            continue
        d = Path(k) / MESH_UNTERORDNER
        if all((d / f).is_file() for f in MESH_DATEIEN):
            return d
    return None


# --- COLLADA lesen ----------------------------------------------------------

def dae_laden(path: str | Path):
    """Ecken (n, 3) und Dreiecke (m, 3) einer einfachen COLLADA-Datei.

    Unterstuetzt ``<triangles>`` ohne Knotentransformationen (so liegen die
    iRC_ROS-Meshes vor) und ``<unit meter=…>``. Alles andere wird abgelehnt,
    damit nichts still falsch ausgerichtet wird.
    """
    import numpy as np

    root = ET.parse(str(path)).getroot()
    ns = root.tag[: root.tag.index("}") + 1] if root.tag.startswith("{") else ""
    unit = root.find(f"{ns}asset/{ns}unit")
    faktor = float(unit.get("meter", "1")) if unit is not None else 1.0
    up = root.find(f"{ns}asset/{ns}up_axis")
    if up is not None and (up.text or "").strip() != "Z_UP":
        raise ValueError(f"{path}: up_axis {up.text} nicht unterstuetzt")
    for tag in ("matrix", "translate", "rotate", "scale"):
        if root.find(f".//{ns}visual_scene//{ns}{tag}") is not None:
            raise ValueError(f"{path}: Knotentransformation <{tag}> nicht unterstuetzt")
    if root.find(f".//{ns}polylist") is not None or root.find(f".//{ns}polygons") is not None:
        raise ValueError(f"{path}: nur <triangles> unterstuetzt")
    alle_v, alle_f, basis = [], [], 0
    for geo in root.iter(f"{ns}geometry"):
        mesh = geo.find(f"{ns}mesh")
        quellen = {s.get("id"): s for s in mesh.findall(f"{ns}source")}
        vert = mesh.find(f"{ns}vertices")
        pos_id = vert.find(f"{ns}input[@semantic='POSITION']").get("source").lstrip("#")
        arr = quellen[pos_id].find(f"{ns}float_array")
        v = np.array(arr.text.split(), float).reshape(-1, 3) * faktor
        for tri in mesh.findall(f"{ns}triangles"):
            inputs = tri.findall(f"{ns}input")
            stride = max(int(i.get("offset", "0")) for i in inputs) + 1
            voff = int(next(i for i in inputs if i.get("semantic") == "VERTEX").get("offset", "0"))
            p = np.array(tri.find(f"{ns}p").text.split(), int).reshape(-1, stride)[:, voff]
            alle_f.append(p.reshape(-1, 3) + basis)
        alle_v.append(v)
        basis += len(v)
    if not alle_f:
        raise ValueError(f"{path}: keine Dreiecke")
    return np.concatenate(alle_v), np.concatenate(alle_f)


def dezimieren(v, f, zelle: float):
    """Vertex-Clustering auf einem Gitter der Kantenlaenge ``zelle`` (m).

    Jede Zelle wird zum Mittelwert ihrer Ecken; entartete und doppelte
    Dreiecke fallen weg. Grob, aber schnell und ohne Zusatzpakete.
    """
    import numpy as np

    key = np.floor(v / zelle).astype(np.int64)
    _, inv = np.unique(key, axis=0, return_inverse=True)
    inv = np.asarray(inv).reshape(-1)
    n = int(inv.max()) + 1
    nv = np.zeros((n, 3))
    np.add.at(nv, inv, v)
    nv /= np.bincount(inv, minlength=n)[:, None]
    nf = inv[f]
    ok = (nf[:, 0] != nf[:, 1]) & (nf[:, 1] != nf[:, 2]) & (nf[:, 0] != nf[:, 2])
    nf = nf[ok]
    _, keep = np.unique(np.sort(nf, axis=1), axis=0, return_index=True)
    return nv, nf[np.sort(keep)]


def dezimieren_bis(v, f, max_dreiecke: int, start: float = 0.001):
    """Zellgroesse ab ``start`` verdoppeln (Faktor 1,25), bis hoechstens ``max_dreiecke`` bleiben."""
    if len(f) <= max_dreiecke:
        return v, f, 0.0
    zelle = start
    while True:
        nv, nf = dezimieren(v, f, zelle)
        if len(nf) <= max_dreiecke or zelle > 0.05:
            return nv, nf, zelle
        zelle *= 1.25


def transformiert(vis: Visual, v):
    """Mesh-Ecken im Linkframe (erst skalieren, dann verschieben wie URDF)."""
    import numpy as np
    return v * np.asarray(vis.skala) + np.asarray(vis.xyz)


# --- Ausrichtung messen -------------------------------------------------------

def _kreis_aus_huelle(p, z_gelenk: float, unten: bool):
    """Kreismitte (x, z) aus der konvexen Huelle der xz-Projektion jenseits
    des Gelenks (Kasa-Fit an die Huellpunkte mit Abstand >= 1,5 cm vom Gelenk)."""
    import numpy as np
    pts = np.unique(np.round(p, 6), axis=0)
    pts = pts[np.lexsort((pts[:, 1], pts[:, 0]))]

    def kette(seq):
        h = []
        for q in seq:
            while len(h) >= 2 and ((h[-1][0] - h[-2][0]) * (q[1] - h[-2][1])
                                   - (h[-1][1] - h[-2][1]) * (q[0] - h[-2][0])) <= 0:
                h.pop()
            h.append(q)
        return h

    huelle = np.array(kette(pts)[:-1] + kette(pts[::-1])[:-1])
    m = huelle[:, 1] < z_gelenk - 0.015 if unten else huelle[:, 1] > z_gelenk + 0.015
    h = huelle[m]
    A = np.column_stack([2 * h[:, 0], 2 * h[:, 1], np.ones(len(h))])
    (cx, cz, _), *_ = np.linalg.lstsq(A, (h ** 2).sum(1), rcond=None)
    return float(cx), float(cz), len(h)


def _gehaeuse_y(v, unten: bool, z_gelenk: float):
    """Abstand der Mitte des Gelenkgehaeuses um eine y-Achse vom Gelenk:
    Kreis an die Aussenkontur (xz) des Teils jenseits des Gelenks."""
    import numpy as np
    m = v[:, 2] < z_gelenk if unten else v[:, 2] > z_gelenk
    cx, cz, n = _kreis_aus_huelle(v[m][:, [0, 2]], z_gelenk, unten)
    if n < 5:
        raise ValueError("zu wenige Huellpunkte fuer den Kreis-Fit")
    return float(np.hypot(cx, cz - z_gelenk))


def _achse_z(v, z0: float, z1: float):
    """Abstand der Mitte (x, y) der Scheibe z0..z1 von der z-Achse."""
    import numpy as np
    m = (v[:, 2] >= z0) & (v[:, 2] <= z1)
    w = v[m]
    return float(np.hypot((w[:, 0].max() + w[:, 0].min()) / 2.0, (w[:, 1].max() + w[:, 1].min()) / 2.0))


def ausrichtung(cfg, mesh_dir: str | Path) -> Dict[str, Dict[str, float]]:
    """Fehler (m) jedes Glied-Meshes gegen die Gelenklagen unseres Modells.

    Je Glied: Gelenke um y (J2, J3, J5) ueber die Mitte des Gehaeuses,
    Gelenke um z (J1, J4, J6) ueber die Lage der Querschnittsmitte zur Achse,
    dazu Stirnflaechen (Fuss unten/oben, Flansch) und die Fuge J3-/J4-Mesh.
    """
    a = cfg.arm
    vis = {x.link: x for x in zuordnung(cfg)}
    v = {k: transformiert(x, dae_laden(Path(mesh_dir) / x.datei)[0]) for k, x in vis.items()}
    j1 = a["j1_hoehe_m"]
    l1 = a["j2_hoehe_m"] - j1
    l2 = a["oberarm_m"]
    j4 = a["j4_ab_j3_m"]
    l4 = a["unterarm_m"] - j4
    l5 = a["j6_ab_j5_m"]
    l6 = a["hand_m"] - l5
    out = {
        "base_link": {"J1_achse": _achse_z(v["base_link"], j1 - 0.02, j1),
                      "fuss_unten": abs(float(v["base_link"][:, 2].min())),
                      "J1_stirn": abs(float(v["base_link"][:, 2].max()) - j1)},
        "link_1": {"J1_achse": _achse_z(v["link_1"], 0.0, 0.03),
                   "J1_stirn": abs(float(v["link_1"][:, 2].min())),
                   "J2_gehaeuse": _gehaeuse_y(v["link_1"], False, l1)},
        "link_2": {"J2_gehaeuse": _gehaeuse_y(v["link_2"], True, 0.0),
                   "J3_gehaeuse": _gehaeuse_y(v["link_2"], False, l2)},
        "link_3": {"J3_gehaeuse": _gehaeuse_y(v["link_3"], True, 0.0),
                   "J4_achse": _achse_z(v["link_3"], j4 - 0.03, j4 + 0.02),
                   "fuge_J3_J4": abs(float(v["link_3"][:, 2].max()) - (j4 + float(v["link_4"][:, 2].min())))},
        "link_4": {"J4_achse": _achse_z(v["link_4"], 0.0, 0.05),
                   "J5_gehaeuse": _gehaeuse_y(v["link_4"], False, l4)},
        "link_5": {"J5_gehaeuse": _gehaeuse_y(v["link_5"], True, 0.0),
                   "J6_achse": _achse_z(v["link_5"], l5 - 0.02, l5),
                   "J6_stirn": abs(float(v["link_5"][:, 2].max()) - l5)},
        "link_6": {"J6_achse": _achse_z(v["link_6"], -1.0, 1.0),
                   "flansch": abs(float(v["link_6"][:, 2].max()) - l6)},
    }
    return out


def urdf_visual_xml(vis: Visual, mesh_dir: str | Path, farbe: Sequence[float] = (0.17, 0.18, 0.19, 1.0)) -> str:
    """``<visual>`` mit Mesh fuer die URDF (absoluter file://-Pfad, nur lokal)."""
    f = Path(mesh_dir).resolve() / vis.datei
    xyz = " ".join(f"{x:.12g}" for x in vis.xyz)
    sk = " ".join(f"{x:.12g}" for x in vis.skala)
    rgba = " ".join(f"{x:.3g}" for x in farbe)
    return (f'    <visual><origin xyz="{xyz}" rpy="0 0 0"/><geometry><mesh filename="file://{f}" scale="{sk}"/>'
            f'</geometry><material name="rebel_anthrazit"><color rgba="{rgba}"/></material></visual>')
