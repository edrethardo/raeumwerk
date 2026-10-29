#!/usr/bin/env python3
"""Rendert eine Aufzeichnung der Greifdemo offscreen zu einem MP4 (H.264).

    render_video.py AUFZEICHNUNG.npz --out video.mp4 [--standbild mitte.png]
                    [--breite 1280 --hoehe 720] [--tempo auto|0.7] [--halten 4]
                    [--optik auto|mesh|quader] [--jobs N]

Die Aufzeichnung kommt aus ``scripts/demo_greifen.py --aufzeichnen DATEI.npz``
(greifen/aufzeichnung.py). Gezeichnet wird ohne Display mit matplotlib (Agg):
die Visuals aus der URDF (rebel_model.urdf_gen, gleiche Konfiguration wie die
Simulation) an den aufgezeichneten Koerperposen, das Glas als Zylinder, Tisch,
Boden und Start-/Zielmarke. Oben links die Ablaufphase, am Ende das Ergebnis
der Bewertung (Zielfehler, Kippung). ffmpeg kodiert mit libx264, yuv420p und
``+faststart`` (spielt auf iPhone/iPad).

Optik: Liegen die ReBeL-Meshes aus iRC_ROS lokal vor (``scripts/fetch_assets.sh``,
``$RAEUMWERK_ASSETS``), zeigt der Arm sie dezimiert in den ReBeL-Farben
(anthrazit, orange Ringe an den Gelenken); sonst die Quader der URDF. Die
Physik der Aufzeichnung ist in beiden Faellen dieselbe (Kollision = Quader).
Gerendert wird in ``--jobs`` Prozessen je ein Abschnitt, ffmpeg fuegt die
Abschnitte verlustfrei zusammen.

Braucht numpy, pyyaml, matplotlib und ffmpeg im PATH, kein Newton.
"""
from __future__ import annotations

import argparse
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

PHASE_TEXT = {"start": "Anfahrt", "vorposition": "Anfahrt", "anfahrt": "Anfahrt", "greifen": "Greifen",
              "anheben": "Heben", "verfahren": "Verfahren", "absetzen": "Absetzen", "loesen": "Absetzen",
              "rueckzug": "Rückzug", "nachlauf": "Rückzug", "ende": "Rückzug"}
FARBE = {"rail": "#9aa1a9", "carriage": "#c3c8ce", "gripper_base": "#232528", "finger_left": "#3a3d42",
         "finger_right": "#3a3d42", "payload": None, "glas": "#6cc4ea", "tisch": "#b88a5c"}
FARBE_ARM = "#3a3d42"      # ReBeL: anthrazit
FARBE_RING = "#f07d00"     # igus-Orange an den Gelenkfugen
LICHT = (0.35, 0.55, 0.76)
MAX_DREIECKE_JE_MESH = 1100


# --- Geometrie ---------------------------------------------------------------

def urdf_quader(urdf_text: str) -> dict:
    """Linkname -> Liste (Kantenlaengen, Mittelpunkt im Linksystem) der Kollisionsquader."""
    out = {}
    for link in ET.fromstring(urdf_text).iter("link"):
        boxes = []
        for col in link.iter("collision"):
            box = col.find("geometry/box")
            if box is None:
                continue
            org = col.find("origin")
            xyz = [float(x) for x in (org.get("xyz") if org is not None else "0 0 0").split()]
            boxes.append(([float(x) for x in box.get("size").split()], xyz))
        out[link.get("name")] = boxes
    return out


def _rot(q):
    import numpy as np
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def quader_flaechen(size, mitte):
    """Sechs Flaechen (je 4 Ecken) eines achsparallelen Quaders im lokalen System."""
    import numpy as np
    h = np.asarray(size, float) / 2.0
    c = np.asarray(mitte, float)
    e = np.array([[sx, sy, sz] for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]) * h + c
    idx = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    return [e[list(i)] for i in idx]


def zylinder_flaechen(r, h, n=28):
    import numpy as np
    a = np.linspace(0, 2 * math.pi, n, endpoint=False)
    ring = np.stack([r * np.cos(a), r * np.sin(a)], 1)
    unten = np.column_stack([ring, np.full(n, -h / 2)])
    oben = np.column_stack([ring, np.full(n, h / 2)])
    f = [np.array([unten[i], unten[(i + 1) % n], oben[(i + 1) % n], oben[i]]) for i in range(n)]
    return f + [unten[::-1], oben]


def dreiecke(flaechen):
    """Konvexe Polygone (Liste von (k, 3)) -> Ecken (n, 3) und Dreiecke (m, 3) (Faecher)."""
    import numpy as np
    v, f, b = [], [], 0
    for p in flaechen:
        p = np.asarray(p, float)
        v.append(p)
        f += [(b, b + i, b + i + 1) for i in range(1, len(p) - 1)]
        b += len(p)
    return np.concatenate(v), np.array(f, int)


def ring_maske(name: str, p, cfg):
    """Punkte (n, 3) im Linkframe, die an einer Gelenkfuge des ReBeL liegen
    (dort sitzen orange Ringe).

    Lage aus ``cfg`` und den Gehaeuseradien der Meshes (52,5 mm Arm, 40 mm
    Hand): Fugen der y-Gelenke als Band in y am Gehaeuserand, Fugen der
    z-Gelenke als Band in z am Mantel.
    """
    import numpy as np
    from rebel_model.visual_mesh import CPR_J4_AB_J5, CPR_J4_MESH_UNTEN
    a = cfg.arm
    l1 = a["j2_hoehe_m"] - a["j1_hoehe_m"]
    l4 = a["unterarm_m"] - a["j4_ab_j3_m"]
    c = np.asarray(p, float)

    def band_y(y0, y1, z, r):
        return (c[:, 1] >= y0) & (c[:, 1] <= y1) & (np.hypot(c[:, 0], c[:, 2] - z) > r)

    def band_z(z0, z1, r):
        return (c[:, 2] >= z0) & (c[:, 2] <= z1) & (np.hypot(c[:, 0], c[:, 1]) > r)

    z4 = l4 - CPR_J4_AB_J5 + CPR_J4_MESH_UNTEN  # Unterkante des J4-Meshes
    m = {
        "link_1": lambda: band_z(0.0, 0.008, 0.046) | band_y(0.021, 0.029, l1, 0.045),
        "link_2": lambda: band_y(-0.031, -0.023, 0.0, 0.045) | band_y(0.021, 0.029, a["oberarm_m"], 0.045),
        "link_3": lambda: band_y(-0.031, -0.023, 0.0, 0.045),
        "link_4": lambda: band_z(z4, z4 + 0.008, 0.046) | band_y(0.024, 0.032, l4, 0.034),
        "link_5": lambda: band_y(-0.034, -0.026, 0.0, 0.034),
    }.get(name)
    return m() if m else np.zeros(len(c), bool)


def ringe_einfaerben(name: str, v, f, cfg, stufen: int = 2):
    """Dreiecke, die eine Ringkante schneiden, ``stufen``-mal vierteln (die
    Kante wird so 4**stufen-mal feiner) und alle Dreiecke im Ring markieren.

    Liefert Ecken (3m, 3), Dreiecke (m, 3) als Dreieckssuppe und Maske (m,).
    """
    import numpy as np
    tri = v[f]
    for _ in range(stufen):
        # Stichproben je Dreieck: Ecken, Kantenmitten, Schwerpunkt (ein Band kann
        # zwischen den Ecken liegen)
        a, b, c = tri[:, 0], tri[:, 1], tri[:, 2]
        proben = np.stack([a, b, c, (a + b) / 2, (b + c) / 2, (c + a) / 2, (a + b + c) / 3], 1)
        innen = ring_maske(name, proben.reshape(-1, 3), cfg).reshape(-1, 7)
        quer = innen.any(1) & ~innen.all(1)
        if not quer.any():
            break
        s = tri[quer]
        a, b, c = s[:, 0], s[:, 1], s[:, 2]
        ab, bc, ca = (a + b) / 2, (b + c) / 2, (c + a) / 2
        neu = np.concatenate([np.stack(x, 1) for x in ((a, ab, ca), (ab, b, bc), (ca, bc, c), (ab, bc, ca))])
        tri = np.concatenate([tri[~quer], neu])
    maske = ring_maske(name, tri.mean(axis=1), cfg)
    return tri.reshape(-1, 3), np.arange(3 * len(tri)).reshape(-1, 3), maske


def urdf_teile(urdf_text: str, cfg=None, max_dreiecke: int = MAX_DREIECKE_JE_MESH) -> dict:
    """Linkname -> Liste (Ecken, Dreiecke, Farbe, geschlossen) der Visuals im Linkframe.

    ``<box>`` wird zu 12 Dreiecken, ``<mesh>`` (file://, COLLADA) wird geladen,
    skaliert, verschoben und dezimiert. Farbe ist ein Farbname oder ein Array
    (m, 3) je Dreieck: mit ``cfg`` bekommen die Meshes orange Ringe an den
    Gelenkfugen.
    """
    import numpy as np
    from matplotlib.colors import to_rgb
    from rebel_model.visual_mesh import dae_laden, dezimieren_bis
    out = {}
    for link in ET.fromstring(urdf_text).iter("link"):
        name = link.get("name")
        teile = []
        for vis in link.iter("visual"):
            org = vis.find("origin")
            xyz = np.array([float(x) for x in (org.get("xyz") if org is not None else "0 0 0").split()])
            rpy = (org.get("rpy") if org is not None else "0 0 0").split()
            if any(float(r) != 0.0 for r in rpy):
                raise ValueError(f"{name}: rpy im Visual nicht unterstuetzt")
            box, mesh = vis.find("geometry/box"), vis.find("geometry/mesh")
            if box is not None:
                v, f = dreiecke(quader_flaechen([float(x) for x in box.get("size").split()], xyz))
                teile.append((v, f, FARBE.get(name, FARBE_ARM), False))
            elif mesh is not None:
                pfad = mesh.get("filename")
                pfad = pfad[len("file://"):] if pfad.startswith("file://") else pfad
                skala = np.array([float(x) for x in (mesh.get("scale") or "1 1 1").split()])
                v, f = dae_laden(pfad)
                v, f, _ = dezimieren_bis(v, f, max_dreiecke)
                v = v * skala + xyz
                farbe = FARBE.get(name, FARBE_ARM)
                if cfg is not None:
                    v, f, ring = ringe_einfaerben(name, v, f, cfg)
                    rgb = np.tile(np.asarray(to_rgb(farbe)), (len(f), 1))
                    rgb[ring] = to_rgb(FARBE_RING)
                    farbe = rgb
                teile.append((v, f, farbe, True))
        out[name] = teile
    return out


def interpoliere(t_rec, q_rec, t):
    """Pose aller Koerper zur Simzeit t (linear, Quaternion normiert)."""
    import numpy as np
    i = int(np.searchsorted(t_rec, t, side="right")) - 1
    if i < 0:
        return q_rec[0]
    if i >= len(t_rec) - 1:
        return q_rec[-1]
    a = (t - t_rec[i]) / max(t_rec[i + 1] - t_rec[i], 1e-9)
    q0, q1 = q_rec[i].astype(float), q_rec[i + 1].astype(float)
    q1q = q1[:, 3:7] * np.where(np.sum(q0[:, 3:7] * q1[:, 3:7], 1) < 0, -1.0, 1.0)[:, None]
    out = q0 * (1 - a)
    out[:, :3] += a * q1[:, :3]
    qq = q0[:, 3:7] * (1 - a) + a * q1q
    out[:, 3:7] = qq / np.linalg.norm(qq, axis=1, keepdims=True)
    return out


def _aussen_orientiert(v, f) -> bool:
    """True, wenn das Mesh geschlossen genug ist und die Dreiecke nach aussen zeigen
    (positives Volumen) - nur dann darf die Rueckseite weggelassen werden."""
    import numpy as np
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    vol = float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)
    ext = v.max(0) - v.min(0)
    return vol > 0.05 * float(np.prod(ext))


# --- Szene -------------------------------------------------------------------

class Szene3D:
    def __init__(self, rec: dict, teile_je_link: dict, breite: int, hoehe: int, optik_text: str = ""):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.colors import to_rgb
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection

        import numpy as np
        self.np, self.to_rgb, self.Poly = np, to_rgb, Poly3DCollection
        self.rec, self.meta = rec, rec["meta"]
        # dynamische Teile als Dreiecke: (Koerperindex, Ecken, Dreiecke, RGB, alpha, Rueckseiten weglassen)
        self.teile = []
        hinten = []      # Schiene: steht still und liegt aus Kamerasicht hinter dem Tisch
        for bi, name in enumerate(rec["body_label"]):
            if name == "glas":
                v, f = dreiecke(zylinder_flaechen(self.meta["glas_radius_m"], self.meta["glas_hoehe_m"]))
                self.teile.append((bi, v, f, to_rgb(FARBE["glas"]), 0.85, False))
                continue
            if FARBE.get(name, FARBE_ARM) is None:
                continue
            for v, f, farbe, geschlossen in teile_je_link.get(name, []):
                if name == "rail":
                    q0 = np.asarray(rec["body_q"][0], float)[bi]
                    w = v @ _rot(q0[3:7]).T + q0[:3]
                    hinten += [(w[tri], farbe) for tri in f]
                else:
                    rgb = to_rgb(farbe) if isinstance(farbe, str) else np.asarray(farbe, float)
                    self.teile.append((bi, v, f, rgb, 1.0, geschlossen and _aussen_orientiert(v, f)))
        tm, tg = self.meta["tisch_mitte_xy_m"], self.meta["tisch_groesse_m"]
        self.statisch = [quader_flaechen(tg, (tm[0], tm[1], tg[2] / 2.0))]
        self.fig = plt.figure(figsize=(breite / 100.0, hoehe / 100.0), dpi=100)
        self.fig.patch.set_facecolor("#f4f5f7")
        self.ax = self.fig.add_axes([-0.05, -0.08, 1.1, 1.0], projection="3d")
        self.ax.computed_zorder = False
        self.ax.set_facecolor("#f4f5f7")
        self.ax.set_axis_off()
        lim = ((0.0, 1.3), (-0.15, 0.75), (0.0, 0.75))
        self.ax.set_xlim(*lim[0])
        self.ax.set_ylim(*lim[1])
        self.ax.set_zlim(*lim[2])
        self.ax.set_box_aspect([b - a for a, b in lim], zoom=1.45)
        # Kamera schraeg von vorn (Tischseite, +y), erhoeht: Tischoberflaeche und
        # Glas frei, Schiene liegt im Bild oberhalb der hinteren Tischkante
        elev, azim = 40, 68
        self.ax.view_init(elev=elev, azim=azim)
        e, z = math.radians(elev), math.radians(azim)
        self.auge = np.array([math.cos(e) * math.cos(z), math.cos(e) * math.sin(z), math.sin(e)])
        # Boden, Schiene, Tisch, Marken (unbewegt, in dieser Reihenfolge zuerst gezeichnet)
        boden = np.array([[-0.1, -0.3, 0], [1.4, -0.3, 0], [1.4, 0.85, 0], [-0.1, 0.85, 0]])
        self.ax.add_collection3d(Poly3DCollection([boden], facecolors="#dfe2e6", edgecolors="none", zorder=0))
        if hinten:
            fc = [self._schattiert(f, c) for f, c in hinten]
            self.ax.add_collection3d(Poly3DCollection(
                [f for f, _ in hinten], facecolors=fc, edgecolors=fc, linewidths=0.3, zorder=0.5))
        tisch = self.statisch[0]
        self.ax.add_collection3d(Poly3DCollection(
            tisch, facecolors=[self._schattiert(f, FARBE["tisch"]) for f in tisch],
            edgecolors=(0.3, 0.2, 0.1, 0.5), linewidths=0.5, zorder=1))
        top = tg[2] + 0.0005
        a = np.linspace(0, 2 * math.pi, 60)
        r = self.meta["glas_radius_m"] * 1.25
        for xy, farbe, ls in ((self.meta["ziel_xy_m"], "#1d9a4b", "-"), (self.meta["start_xy_m"], "#5f646b", "--")):
            self.ax.plot(xy[0] + r * np.cos(a), xy[1] + r * np.sin(a), np.full_like(a, top),
                         color=farbe, lw=2.5, ls=ls, zorder=1.5)
        self.titel = self.fig.text(0.02, 0.955, "Räumwerk · Glas-Greifdemo (Newton-Simulation)",
                                   fontsize=hoehe / 36, weight="bold", color="#1f2328", va="center")
        self.phase_txt = self.fig.text(0.02, 0.885, "", fontsize=hoehe / 30, color="#0b5cad",
                                       weight="bold", va="center")
        self.zeit_txt = self.fig.text(0.98, 0.955, "", fontsize=hoehe / 40, color="#57606a",
                                      ha="right", va="center")
        self.ergebnis_txt = self.fig.text(0.5, 0.79, "", fontsize=hoehe / 40, ha="center", va="center",
                                          color="#1f2328", bbox=dict(boxstyle="round,pad=0.6", fc="white",
                                                                     ec="#1d9a4b", lw=2), visible=False)
        self.legende = self.fig.text(0.98, 0.885, "grün: Ziel · grau gestrichelt: Start", fontsize=hoehe / 50,
                                     color="#57606a", ha="right", va="center")
        if optik_text:
            self.fig.text(0.98, 0.03, optik_text, fontsize=hoehe / 60, color="#8b949e", ha="right", va="center")
        self.coll = None

    def _schattiert(self, flaeche, farbe):
        np = self.np
        n = np.cross(flaeche[1] - flaeche[0], flaeche[2] - flaeche[0])
        nn = np.linalg.norm(n)
        k = 0.55 + 0.45 * abs(float(n @ np.asarray(LICHT)) / nn) if nn > 1e-12 else 0.8
        return tuple(min(1.0, c * k) for c in self.to_rgb(farbe))

    def polygone(self, body_q):
        """Alle sichtbaren Dreiecke (m, 3, 3) mit RGBA-Farben (m, 4) fuer eine Pose."""
        np = self.np
        polys, farben = [], []
        for bi, v, f, rgb, alpha, cull in self.teile:
            w = v @ _rot(body_q[bi, 3:7]).T + body_q[bi, :3]
            tri = w[f]
            rgb = np.broadcast_to(np.asarray(rgb, float), (len(f), 3))
            n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
            nn = np.linalg.norm(n, axis=1)
            nn[nn < 1e-15] = 1e-15
            n /= nn[:, None]
            if cull:
                sicht = n @ self.auge > -0.1
                tri, n, rgb = tri[sicht], n[sicht], rgb[sicht]
            k = 0.55 + 0.45 * np.abs(n @ np.asarray(LICHT))
            c = np.empty((len(tri), 4))
            c[:, :3] = np.minimum(1.0, rgb * k[:, None])
            c[:, 3] = alpha
            polys.append(tri)
            farben.append(c)
        return np.concatenate(polys), np.concatenate(farben)

    def bild(self, body_q, phase: str, t: float, ergebnis: str | None = None):
        np = self.np
        polys, farben = self.polygone(body_q)
        if self.coll is not None:
            self.coll.remove()
        self.coll = self.Poly(polys, facecolors=farben, edgecolors=farben, linewidths=0.3, zorder=2)
        self.ax.add_collection3d(self.coll)
        self.phase_txt.set_text(f"Phase: {PHASE_TEXT.get(phase, phase)}")
        self.zeit_txt.set_text(f"Simzeit {t:5.1f} s")
        self.ergebnis_txt.set_visible(bool(ergebnis))
        if ergebnis:
            self.ergebnis_txt.set_text(ergebnis)
            self.ergebnis_txt.get_bbox_patch().set_edgecolor(
                "#1d9a4b" if self.meta.get("erfolg") else "#c62828")
        self.fig.canvas.draw()
        return np.asarray(self.fig.canvas.buffer_rgba())


def ergebnis_text(meta: dict) -> str:
    if "zielfehler_xy_m" not in meta:
        return "Ergebnis: keine Bewertung in der Aufzeichnung"
    ok = "Erfolg" if meta.get("erfolg") else "Fehlversuch (" + ", ".join(meta.get("gruende", [])) + ")"
    zf = meta["zielfehler_xy_m"] * 1e3
    tol = meta.get("ziel_toleranz_m", float("nan")) * 1e3
    return (f"Ergebnis: {ok}\n"
            f"Zielfehler {zf:.1f} mm (Toleranz {tol:.0f} mm) · "
            f"Kippung am Ende {meta['kippung_end_grad']:.2f}°, max. {meta['kippung_max_grad']:.2f}° "
            f"(Grenze {meta.get('kippung_grenze_grad', float('nan')):.0f}°)")


def tempo_auto(sim_dauer: float, halten: float, ziel_s: float = 24.0) -> float:
    """Wiedergabetempo: Echtzeit, ausser das Video wuerde kuerzer als ``ziel_s``."""
    return min(1.0, sim_dauer / max(ziel_s - halten, 1.0))


# --- Rendern -----------------------------------------------------------------

def _ffmpeg_cmd(ffmpeg, breite, hoehe, fps, crf, out):
    return [ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{breite}x{hoehe}",
            "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
            "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.0", str(out)]


def _abschnitt(args) -> int:
    """Rendert die Bilder ``von`` .. ``bis``-1 in eine eigene MP4-Datei (Arbeitsprozess)."""
    (rec, teile, breite, hoehe, fps, crf, tempo, n_lauf, von, bis, standbild, mitte, ffmpeg, out, optik_text) = args
    import numpy as np
    t_rec, q_rec, ph = np.asarray(rec["t"]), np.asarray(rec["body_q"]), rec["phase"]
    szene = Szene3D(rec, teile, breite, hoehe, optik_text)
    proc = subprocess.Popen(_ffmpeg_cmd(ffmpeg, breite, hoehe, fps, crf, out), stdin=subprocess.PIPE)
    try:
        for i in range(von, bis):
            t = min(i, n_lauf - 1) / fps * tempo
            k = min(int(np.searchsorted(t_rec, t, side="right")) - 1, len(ph) - 1)
            img = szene.bild(interpoliere(t_rec, q_rec, t), ph[max(k, 0)], t,
                             ergebnis_text(rec["meta"]) if i >= n_lauf else None)
            if img.shape[:2] != (hoehe, breite):
                raise RuntimeError(f"Bildgroesse {img.shape} statt {hoehe}x{breite}")
            proc.stdin.write(img.tobytes())
            if standbild and i == mitte:
                import matplotlib.image as mpimg
                Path(standbild).parent.mkdir(parents=True, exist_ok=True)
                mpimg.imsave(str(standbild), img)
    finally:
        proc.stdin.close()
        rc = proc.wait()
    if rc != 0:
        raise RuntimeError(f"ffmpeg rc={rc}")
    return bis - von


def rendern(rec: dict, urdf_text: str, out: Path, breite=1280, hoehe=720, fps=30, tempo=None, halten=4.0,
            standbild: Path | None = None, crf=23, cfg=None, jobs: int | None = None, optik_text: str = "") -> dict:
    import numpy as np
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg fehlt im PATH")
    t0 = time.monotonic()
    t_rec = np.asarray(rec["t"])
    sim_dauer = float(t_rec[-1])
    tempo = tempo or tempo_auto(sim_dauer, halten)
    n_lauf = int(round(sim_dauer / tempo * fps)) + 1
    n_halten = int(round(halten * fps))
    n = n_lauf + n_halten
    teile = urdf_teile(urdf_text, cfg)
    n_dreiecke = sum(len(f) for ts in teile.values() for _, f, _, _ in ts)
    jobs = max(1, min(jobs or min(os.cpu_count() or 1, 6), n))
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    grenzen = [round(n * j / jobs) for j in range(jobs + 1)]
    with tempfile.TemporaryDirectory(prefix="render-", dir=str(out.parent)) as tmp:
        teile_mp4 = [Path(tmp) / f"teil-{j:02d}.mp4" for j in range(jobs)]
        auftraege = [(rec, teile, breite, hoehe, fps, crf, tempo, n_lauf, grenzen[j], grenzen[j + 1],
                      standbild, n_lauf // 2, ffmpeg, teile_mp4[j], optik_text) for j in range(jobs)]
        if jobs == 1:
            gerendert = [_abschnitt(auftraege[0])]
        else:
            import multiprocessing as mp
            with mp.get_context("spawn").Pool(jobs) as pool:
                gerendert = pool.map(_abschnitt, auftraege)
        if sum(gerendert) != n:
            raise RuntimeError(f"{sum(gerendert)} statt {n} Bildern")
        liste = Path(tmp) / "teile.txt"
        liste.write_text("".join(f"file '{p.name}'\n" for p in teile_mp4), encoding="utf-8")
        r = subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(liste),
                            "-c", "copy", "-movflags", "+faststart", str(out)])
        if r.returncode != 0:
            raise RuntimeError(f"ffmpeg concat rc={r.returncode}")
    return {"bilder": n, "tempo": tempo, "dauer_s": n / fps, "groesse_bytes": out.stat().st_size,
            "jobs": jobs, "dreiecke_je_bild": n_dreiecke, "renderzeit_s": round(time.monotonic() - t0, 1)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("aufzeichnung")
    ap.add_argument("--out", required=True)
    ap.add_argument("--standbild", default=None, help="PNG des mittleren Bildes")
    ap.add_argument("--breite", type=int, default=1280)
    ap.add_argument("--hoehe", type=int, default=720)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--tempo", default="auto", help="Simsekunden je Videosekunde (auto: Video >= 24 s)")
    ap.add_argument("--halten", type=float, default=4.0, help="Sekunden Ergebnisbild am Ende")
    ap.add_argument("--optik", choices=("auto", "mesh", "quader"), default="auto",
                    help="auto: ReBeL-Meshes, wenn lokal vorhanden (scripts/fetch_assets.sh), sonst Quader")
    ap.add_argument("--assets", default=None, help="Asset-Ordner (Standard: $RAEUMWERK_ASSETS)")
    ap.add_argument("--jobs", type=int, default=None, help="Render-Prozesse (Standard: CPU-Kerne, hoechstens 6)")
    args = ap.parse_args()
    if args.breite % 2 or args.hoehe % 2:
        ap.error("Breite und Hoehe muessen gerade sein (yuv420p)")

    from greifen.aufzeichnung import laden
    from rebel_model.config import load
    from rebel_model.urdf_gen import build_urdf
    from rebel_model.visual_mesh import mesh_verzeichnis

    cfg = load()
    meshes = None if args.optik == "quader" else mesh_verzeichnis(args.assets)
    if args.optik == "mesh" and meshes is None:
        ap.error("--optik mesh: keine Meshes gefunden (scripts/fetch_assets.sh, RAEUMWERK_ASSETS)")
    optik = ("Optik: ReBeL-Meshes (iRC_ROS) · Physik/Kollision: Quader" if meshes
             else "Optik: Kollisionsquader")
    print("OPTIK", "mesh" if meshes else "quader", flush=True)
    rec = laden(args.aufzeichnung)
    info = rendern(rec, build_urdf(cfg, mesh_dir=str(meshes) if meshes else None), Path(args.out),
                   args.breite, args.hoehe, args.fps, None if args.tempo == "auto" else float(args.tempo),
                   args.halten, Path(args.standbild) if args.standbild else None, cfg=cfg, jobs=args.jobs,
                   optik_text=optik)
    print("VIDEO", args.out, info, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
