#!/usr/bin/env python3
"""Rendert eine Aufzeichnung der Greifdemo offscreen zu einem MP4 (H.264).

    render_video.py AUFZEICHNUNG.npz --out video.mp4 [--standbild mitte.png]
                    [--breite 1280 --hoehe 720] [--tempo auto|0.7] [--halten 4]

Die Aufzeichnung kommt aus ``scripts/demo_greifen.py --aufzeichnen DATEI.npz``
(greifen/aufzeichnung.py). Gezeichnet wird ohne Display mit matplotlib (Agg):
die Kollisionsquader aus der URDF (rebel_model.urdf_gen, gleiche Konfiguration
wie die Simulation) an den aufgezeichneten Koerperposen, das Glas als Zylinder,
Tisch, Boden und Start-/Zielmarke. Oben links die Ablaufphase, am Ende das
Ergebnis der Bewertung (Zielfehler, Kippung). ffmpeg kodiert mit libx264,
yuv420p und ``+faststart`` (spielt auf iPhone/iPad).

Braucht numpy, pyyaml, matplotlib und ffmpeg im PATH, kein Newton.
"""
from __future__ import annotations

import argparse
import math
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

PHASE_TEXT = {"start": "Anfahrt", "vorposition": "Anfahrt", "anfahrt": "Anfahrt", "greifen": "Greifen",
              "anheben": "Heben", "verfahren": "Verfahren", "absetzen": "Absetzen", "loesen": "Absetzen",
              "rueckzug": "Rückzug", "nachlauf": "Rückzug", "ende": "Rückzug"}
FARBE = {"rail": "#5a5f66", "carriage": "#7d838c", "gripper_base": "#2f3338", "finger_left": "#464b52",
         "finger_right": "#464b52", "payload": None, "glas": "#6cc4ea", "tisch": "#b88a5c"}
FARBE_ARM = "#e4e7eb"
LICHT = (0.35, 0.55, 0.76)


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


class Szene3D:
    def __init__(self, rec: dict, urdf_text: str, breite: int, hoehe: int):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.colors import to_rgb
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection

        import numpy as np
        self.np, self.to_rgb, self.Poly = np, to_rgb, Poly3DCollection
        self.rec, self.meta = rec, rec["meta"]
        quader = urdf_quader(urdf_text)
        self.teile = []  # (Koerperindex, lokale Flaechen, Farbe, alpha)
        hinten = []      # Schiene: steht still und liegt aus Kamerasicht hinter dem Tisch
        for bi, name in enumerate(rec["body_label"]):
            if name == "glas":
                f = zylinder_flaechen(self.meta["glas_radius_m"], self.meta["glas_hoehe_m"])
                self.teile.append((bi, f, FARBE["glas"], 0.85))
                continue
            farbe = FARBE.get(name, FARBE_ARM)
            if farbe is None:
                continue
            f = [fl for size, c in quader.get(name, []) for fl in quader_flaechen(size, c)]
            if f and name == "rail":
                q0 = np.asarray(rec["body_q"][0], float)[bi]
                hinten += [(fl @ _rot(q0[3:7]).T + q0[:3], farbe) for fl in f]
            elif f:
                self.teile.append((bi, f, farbe, 1.0))
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
        self.ax.view_init(elev=40, azim=68)
        # Boden, Schiene, Tisch, Marken (unbewegt, in dieser Reihenfolge zuerst gezeichnet)
        boden = np.array([[-0.1, -0.3, 0], [1.4, -0.3, 0], [1.4, 0.85, 0], [-0.1, 0.85, 0]])
        self.ax.add_collection3d(Poly3DCollection([boden], facecolors="#dfe2e6", edgecolors="none", zorder=0))
        if hinten:
            self.ax.add_collection3d(Poly3DCollection(
                [f for f, _ in hinten], facecolors=[self._schattiert(f, c) for f, c in hinten],
                edgecolors=(0.15, 0.16, 0.18, 0.35), linewidths=0.4, zorder=0.5))
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
        self.coll = None

    def _schattiert(self, flaeche, farbe):
        np = self.np
        n = np.cross(flaeche[1] - flaeche[0], flaeche[2] - flaeche[0])
        nn = np.linalg.norm(n)
        k = 0.55 + 0.45 * abs(float(n @ np.asarray(LICHT)) / nn) if nn > 1e-12 else 0.8
        return tuple(min(1.0, c * k) for c in self.to_rgb(farbe))

    def bild(self, body_q, phase: str, t: float, ergebnis: str | None = None):
        np = self.np
        polys, farben = [], []
        for bi, flaechen, farbe, alpha in self.teile:
            R, p = _rot(body_q[bi, 3:7]), body_q[bi, :3]
            for fl in flaechen:
                w = fl @ R.T + p
                polys.append(w)
                farben.append(self._schattiert(w, farbe) + (alpha,))
        if self.coll is not None:
            self.coll.remove()
        self.coll = self.Poly(polys, facecolors=farben, edgecolors=(0.15, 0.16, 0.18, 0.35), linewidths=0.4,
                              zorder=2)
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


def rendern(rec: dict, urdf_text: str, out: Path, breite=1280, hoehe=720, fps=30, tempo=None, halten=4.0,
            standbild: Path | None = None, crf=23) -> dict:
    import numpy as np
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg fehlt im PATH")
    t_rec, q_rec, ph = np.asarray(rec["t"]), np.asarray(rec["body_q"]), rec["phase"]
    sim_dauer = float(t_rec[-1])
    tempo = tempo or tempo_auto(sim_dauer, halten)
    n_lauf = int(round(sim_dauer / tempo * fps)) + 1
    n_halten = int(round(halten * fps))
    szene = Szene3D(rec, urdf_text, breite, hoehe)
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{breite}x{hoehe}",
           "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
           "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.0", "-movflags", "+faststart", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    mitte = n_lauf // 2
    try:
        for i in range(n_lauf + n_halten):
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
    return {"bilder": n_lauf + n_halten, "tempo": tempo, "dauer_s": (n_lauf + n_halten) / fps,
            "groesse_bytes": out.stat().st_size}


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
    args = ap.parse_args()
    if args.breite % 2 or args.hoehe % 2:
        ap.error("Breite und Hoehe muessen gerade sein (yuv420p)")

    from greifen.aufzeichnung import laden
    from rebel_model.config import load
    from rebel_model.urdf_gen import build_urdf

    rec = laden(args.aufzeichnung)
    info = rendern(rec, build_urdf(load()), Path(args.out), args.breite, args.hoehe, args.fps,
                   None if args.tempo == "auto" else float(args.tempo), args.halten,
                   Path(args.standbild) if args.standbild else None)
    print("VIDEO", args.out, info, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
