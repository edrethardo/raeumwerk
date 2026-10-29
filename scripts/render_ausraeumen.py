#!/usr/bin/env python3
"""Rendert eine Aufzeichnung des Ausraeumens offscreen zu einem MP4 (H.264).

    render_ausraeumen.py AUFZEICHNUNG.npz --out video.mp4 [--standbild bild.png]
                         [--standbild-t 120] [--tempo auto|4] [--halten 5]
                         [--optik auto|mesh|quader] [--jobs N]

Die Aufzeichnung kommt aus ``scripts/demo_ausraeumen.py --aufzeichnen
DATEI.npz``. Wie ``scripts/render_video.py`` (gleiche Mesh-Optik des ReBeL:
anthrazit mit orangen Ringen, wenn die iRC_ROS-Meshes lokal liegen), dazu
die Spuelmaschine aus den Kollisionsquadern der Aufzeichnung (Korpus, offene
Tuer, Koerbe, Glashalter, Arbeitsplatte, Zwischenablage, Podest), vier
Glaeser und gruene Ablagemarken. Die Szene wird einmal (in Kacheln, in sich
tiefensortiert) gezeichnet, darueber die Marken und je Bild Roboter und
Glaeser (wie ``render_video.py``: aus dieser Kamera liegt der Arm vor bzw.
ueber der Szene). ffmpeg: libx264, yuv420p, ``+faststart``.
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
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import render_video as rv  # noqa: E402

SCHRITT = {"anfahrt_korb": "Anfahrt Korb", "runter_korb": "Anfahrt Korb", "greifen_korb": "Greifen (von oben)",
           "aushub": "Aus dem Halter heben", "zur_zwischenablage": "Zur Zwischenablage",
           "absetzen_zw": "Kopfüber absetzen", "loesen_zw": "Loslassen", "hoch_zw": "Umgreifen",
           "anfahrt_seite": "Umgreifen", "zu_seite": "Umgreifen", "greifen_seite": "Greifen (seitlich)",
           "anheben": "Anheben", "umdrehen": "Umdrehen", "zur_ablage": "Zur Ablage",
           "absetzen": "Aufrecht absetzen", "loesen": "Loslassen", "rueckzug": "Rückzug"}
FARBE_STATISCH = {"korpus": "#c9ccd1", "tuer": "#e6e8eb", "oberkorb": "#5c6168", "unterkorb": "#7d828a",
                  "glashalter": "#8a8f96", "arbeitsplatte": "#c49a6c", "schrank": "#d9d4cc",
                  "zwischenablage": "#3b8ec2", "podest": "#9aa1a9", "klemmbacke": "#c62828"}
KACHEL_M = 0.04
# Kamera (Hoehenwinkel, Azimut in Grad, wie matplotlib view_init): Arm, Glas in
# der Hand, Korb mit Glaesern, Tuer und Platte mit Ablage im Bild
KAMERA = (35.0, 150.0)
GRENZEN = ((-0.15, 1.2), (-0.6, 1.0), (0.0, 1.6))


def phase_text(ph: str, n_glas: int) -> str:
    if ":" in ph:
        k, s = ph.split(":", 1)
        return f"Glas {k}/{n_glas} · {SCHRITT.get(s, s)}"
    return {"start": "Start", "heim": "Zurück in die Ruhepose", "hoch_heim": "Zurück in die Ruhepose",
            "nachlauf": "Fertig", "ende": "Fertig"}.get(ph, ph)


def kacheln(ecken, kante=KACHEL_M):
    """Viereck (4, 3) in Kacheln von hoechstens ``kante`` zerlegen."""
    import numpy as np
    a, b, c, d = (np.asarray(e, float) for e in ecken)
    nu = max(1, int(math.ceil(np.linalg.norm(b - a) / kante)))
    nv = max(1, int(math.ceil(np.linalg.norm(d - a) / kante)))
    out = []
    for i in range(nu):
        for j in range(nv):
            u0, u1, v0, v1 = i / nu, (i + 1) / nu, j / nv, (j + 1) / nv

            def p(u, v):
                return a + (b - a) * u + (d - a) * v
            out.append(np.array([p(u0, v0), p(u1, v0), p(u1, v1), p(u0, v1)]))
    return out


class SzeneSpuele(rv.Szene3D):
    def __init__(self, rec, teile_je_link, breite, hoehe, optik_text="", kamera=None):  # noqa: C901
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
        from matplotlib.colors import to_rgb
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection

        self.np, self.to_rgb, self.Poly = np, to_rgb, Poly3DCollection
        self.rec, self.meta = rec, rec["meta"]
        self.n_glas = sum(1 for n in rec["body_label"] if n.startswith("glas_"))
        elev, azim = kamera or KAMERA
        e, z = math.radians(elev), math.radians(azim)
        self.auge = np.array([math.cos(e) * math.cos(z), math.cos(e) * math.sin(z), math.sin(e)])
        self.teile = []
        for bi, name in enumerate(rec["body_label"]):
            if name.startswith("glas_"):
                v, f = rv.dreiecke(rv.zylinder_flaechen(self.meta["glas_radius_m"], self.meta["glas_hoehe_m"]))
                self.teile.append((bi, v, f, to_rgb(rv.FARBE["glas"]), 0.9, False))
                continue
            if rv.FARBE.get(name, rv.FARBE_ARM) is None:
                continue
            for v, f, farbe, geschlossen in teile_je_link.get(name, []):
                rgb = to_rgb(farbe) if isinstance(farbe, str) else np.asarray(farbe, float)
                self.teile.append((bi, v, f, rgb, 1.0, geschlossen and rv._aussen_orientiert(v, f)))
        # statische Szene als Kacheln (nur zur Kamera gewandte Flaechen)
        stat, stat_c = [], []
        for k in self.meta["statisch"]:
            farbe = FARBE_STATISCH.get(k["gruppe"], "#b0b4ba")
            R = np.asarray(k["rot"], float)
            m = np.asarray(k["mitte"], float)
            for fl in rv.quader_flaechen(2.0 * np.asarray(k["halb"], float), (0.0, 0.0, 0.0)):
                w = fl @ R.T + m
                n = np.cross(w[1] - w[0], w[2] - w[0])
                c = w.mean(0)
                if float(n @ (c - m)) < 0:
                    n = -n
                if float(n @ self.auge) <= 0:
                    continue  # Rueckseite
                for t in kacheln(w):
                    stat.append(t)
                    stat_c.append(self._schattiert(t, farbe) + (1.0,))
        # Ablagemarken (gruen) auf der Platte: als Linien zwischen Szene und Roboter gezeichnet
        a = np.linspace(0, 2 * math.pi, 49)
        r = self.meta["glas_radius_m"] * 1.25
        self.ringe = []
        for p in self.meta["ablage_m"]:
            z0 = p[2] - self.meta["glas_hoehe_m"] / 2.0 + 0.001
            self.ringe.append((p[0] + r * np.cos(a), p[1] + r * np.sin(a), np.full_like(a, z0)))
        self.stat = np.array(stat)
        self.stat_c = np.array(stat_c)
        self.fig = plt.figure(figsize=(breite / 100.0, hoehe / 100.0), dpi=100)
        self.fig.patch.set_facecolor("#f4f5f7")
        self.ax = self.fig.add_axes([-0.12, -0.12, 1.24, 1.16], projection="3d")
        self.ax.computed_zorder = False
        self.ax.set_facecolor("#f4f5f7")
        self.ax.set_axis_off()
        lim = GRENZEN
        self.ax.set_xlim(*lim[0])
        self.ax.set_ylim(*lim[1])
        self.ax.set_zlim(*lim[2])
        self.ax.set_box_aspect([b - a_ for a_, b in lim], zoom=1.25)
        self.ax.view_init(elev=elev, azim=azim)
        # Szene einmal (in sich tiefensortiert), dann Marken, dann je Bild Roboter + Glaeser
        self.ax.add_collection3d(Poly3DCollection(list(self.stat), facecolors=self.stat_c, edgecolors=self.stat_c,
                                                  linewidths=0.25, zorder=1))
        for x, y, z in self.ringe:
            self.ax.plot(x, y, z, color="#1d9a4b", lw=2.5, zorder=1.5)
        boden = np.array([[-0.6, -0.6, 0], [1.5, -0.6, 0], [1.5, 1.5, 0], [-0.6, 1.5, 0]])
        self.ax.add_collection3d(Poly3DCollection([boden], facecolors="#dfe2e6", edgecolors="none", zorder=0))
        self.titel = self.fig.text(0.02, 0.955, "Räumwerk · Spülmaschine ausräumen (Newton-Simulation)",
                                   fontsize=hoehe / 36, weight="bold", color="#1f2328", va="center")
        self.phase_txt = self.fig.text(0.02, 0.89, "", fontsize=hoehe / 30, color="#0b5cad", weight="bold", va="center")
        self.zeit_txt = self.fig.text(0.98, 0.955, "", fontsize=hoehe / 40, color="#57606a", ha="right", va="center")
        self.ergebnis_txt = self.fig.text(0.5, 0.2, "", fontsize=hoehe / 44, ha="center", va="center", color="#1f2328",
                                          family="monospace", bbox=dict(boxstyle="round,pad=0.6", fc="white",
                                                                        ec="#1d9a4b", lw=2), visible=False)
        self.legende = self.fig.text(0.98, 0.89, "grün: Ablageziel · blau: Zwischenablage zum Umgreifen",
                                     fontsize=hoehe / 52, color="#57606a", ha="right", va="center")
        if optik_text:
            self.fig.text(0.98, 0.03, optik_text, fontsize=hoehe / 60, color="#8b949e", ha="right", va="center")
        self.coll = None

    def bild(self, body_q, phase: str, t: float, ergebnis: str | None = None):
        np = self.np
        polys, farben = self.polygone(body_q)
        if self.coll is not None:
            self.coll.remove()
        self.coll = self.Poly(list(polys), facecolors=farben, edgecolors=farben, linewidths=0.25, zorder=2)
        self.ax.add_collection3d(self.coll)
        self.phase_txt.set_text(phase_text(phase, self.n_glas))
        self.zeit_txt.set_text(f"Simzeit {t:5.1f} s")
        self.ergebnis_txt.set_visible(bool(ergebnis))
        if ergebnis:
            self.ergebnis_txt.set_text(ergebnis)
            self.ergebnis_txt.get_bbox_patch().set_edgecolor("#1d9a4b" if self.meta.get("erfolg") else "#c62828")
        self.fig.canvas.draw()
        return np.asarray(self.fig.canvas.buffer_rgba())


def ergebnis_text(meta: dict) -> str:
    z = [f"Ergebnis: {meta.get('erfolge', 0)}/{len(meta.get('glaeser', []))} Gläser aufrecht am Ziel"]
    for g in meta.get("glaeser", []):
        if g.get("zielfehler_xy_m") is None:
            z.append(f"{g['glas']}: Fehlversuch ({', '.join(g['gruende'])})")
            continue
        ok = "ok" if g["erfolg"] else "Fehlversuch (" + ", ".join(g["gruende"]) + ")"
        z.append(f"{g['glas']}: {ok} · Zielfehler {g['zielfehler_xy_m'] * 1e3:4.1f} mm · Kippung {g['kippung_end_grad']:4.2f}°")
    z.append(f"Grenzen: {meta.get('ziel_toleranz_m', 0.01) * 1e3:.0f} mm, {meta.get('kippung_grenze_grad', 10):.0f}°")
    return "\n".join(z)


def _abschnitt(args) -> int:
    (rec, teile, breite, hoehe, fps, crf, tempo, n_lauf, von, bis, standbild, st_i, ffmpeg, out, optik_text,
     kamera) = args
    import numpy as np
    t_rec, q_rec, ph = np.asarray(rec["t"]), np.asarray(rec["body_q"]), rec["phase"]
    szene = SzeneSpuele(rec, teile, breite, hoehe, optik_text, kamera)
    proc = subprocess.Popen(rv._ffmpeg_cmd(ffmpeg, breite, hoehe, fps, crf, out), stdin=subprocess.PIPE)
    try:
        for i in range(von, bis):
            t = min(i, n_lauf - 1) / fps * tempo
            k = min(int(np.searchsorted(t_rec, t, side="right")) - 1, len(ph) - 1)
            img = szene.bild(rv.interpoliere(t_rec, q_rec, t), ph[max(k, 0)], t,
                             ergebnis_text(rec["meta"]) if i >= n_lauf else None)
            if img.shape[:2] != (hoehe, breite):
                raise RuntimeError(f"Bildgroesse {img.shape} statt {hoehe}x{breite}")
            proc.stdin.write(img.tobytes())
            if standbild and i == st_i:
                import matplotlib.image as mpimg
                Path(standbild).parent.mkdir(parents=True, exist_ok=True)
                mpimg.imsave(str(standbild), img)
    finally:
        proc.stdin.close()
        rc = proc.wait()
    if rc != 0:
        raise RuntimeError(f"ffmpeg rc={rc}")
    return bis - von


def rendern(rec, urdf_text, out: Path, breite=1280, hoehe=720, fps=30, tempo=None, halten=5.0, standbild=None,
            standbild_t=None, crf=23, cfg=None, jobs=None, optik_text="", ziel_s=50.0, kamera=None,
            nur_standbild=False) -> dict:
    import numpy as np
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg fehlt im PATH")
    t0 = time.monotonic()
    sim_dauer = float(np.asarray(rec["t"])[-1])
    tempo = tempo or max(1.0, sim_dauer / max(ziel_s - halten, 1.0))
    n_lauf = int(round(sim_dauer / tempo * fps)) + 1
    n = n_lauf + int(round(halten * fps))
    teile = rv.urdf_teile(urdf_text, cfg)
    if nur_standbild:
        import matplotlib.image as mpimg
        t_rec, q_rec, ph = np.asarray(rec["t"]), np.asarray(rec["body_q"]), rec["phase"]
        t = float(standbild_t if standbild_t is not None else sim_dauer / 2)
        k = max(0, min(int(np.searchsorted(t_rec, t, side="right")) - 1, len(ph) - 1))
        img = SzeneSpuele(rec, teile, breite, hoehe, optik_text, kamera).bild(rv.interpoliere(t_rec, q_rec, t), ph[k], t)
        Path(standbild).parent.mkdir(parents=True, exist_ok=True)
        mpimg.imsave(str(standbild), img)
        return {"standbild": str(standbild), "t": t}
    jobs = max(1, min(jobs or min(os.cpu_count() or 1, 6), n))
    st_i = n_lauf // 2 if standbild_t is None else int(round(standbild_t / tempo * fps))
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    grenzen = [round(n * j / jobs) for j in range(jobs + 1)]
    with tempfile.TemporaryDirectory(prefix="render-", dir=str(out.parent)) as tmp:
        teile_mp4 = [Path(tmp) / f"teil-{j:02d}.mp4" for j in range(jobs)]
        auftraege = [(rec, teile, breite, hoehe, fps, crf, tempo, n_lauf, grenzen[j], grenzen[j + 1], standbild, st_i,
                      ffmpeg, teile_mp4[j], optik_text, kamera) for j in range(jobs)]
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
    return {"bilder": n, "tempo": round(tempo, 3), "dauer_s": n / fps, "groesse_bytes": out.stat().st_size,
            "jobs": jobs, "renderzeit_s": round(time.monotonic() - t0, 1)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("aufzeichnung")
    ap.add_argument("--out", required=True)
    ap.add_argument("--standbild", default=None)
    ap.add_argument("--standbild-t", type=float, default=None, help="Simzeit des Standbilds (Standard: Mitte)")
    ap.add_argument("--breite", type=int, default=1280)
    ap.add_argument("--hoehe", type=int, default=720)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--tempo", default="auto", help="Simsekunden je Videosekunde (auto: Video etwa 50 s)")
    ap.add_argument("--halten", type=float, default=5.0)
    ap.add_argument("--optik", choices=("auto", "mesh", "quader"), default="auto")
    ap.add_argument("--assets", default=None)
    ap.add_argument("--jobs", type=int, default=None)
    ap.add_argument("--elev", type=float, default=KAMERA[0], help="Kamera: Hoehenwinkel in Grad")
    ap.add_argument("--azim", type=float, default=KAMERA[1], help="Kamera: Azimut in Grad")
    ap.add_argument("--nur-standbild", action="store_true", help="nur das Standbild (--standbild, --standbild-t)")
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
    optik = ("Optik: ReBeL-Meshes (iRC_ROS) · Physik/Kollision: Quader" if meshes else "Optik: Kollisionsquader")
    print("OPTIK", "mesh" if meshes else "quader", flush=True)
    rec = laden(args.aufzeichnung)
    if rec["meta"].get("szene") != "spuelmaschine":
        ap.error("keine Ausraeum-Aufzeichnung (meta.szene != spuelmaschine)")
    info = rendern(rec, build_urdf(cfg, mesh_dir=str(meshes) if meshes else None), Path(args.out), args.breite,
                   args.hoehe, args.fps, None if args.tempo == "auto" else float(args.tempo), args.halten,
                   Path(args.standbild) if args.standbild else None, args.standbild_t, cfg=cfg, jobs=args.jobs,
                   optik_text=optik, kamera=(args.elev, args.azim), nur_standbild=args.nur_standbild)
    print("VIDEO", args.out, info, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
