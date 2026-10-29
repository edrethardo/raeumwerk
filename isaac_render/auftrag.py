"""Renderauftrag: was Isaac Sim zeichnen soll, unabhaengig von Isaac Sim.

Ein Auftrag ist eine ``.npz`` mit
    posen        (F, B, 7)  Weltposen der Koerper je Bild (x, y, z, qx, qy, qz, qw)
    koerper      (B,)       Koerpernamen (URDF-Linkname oder Glasname)
    simzeit      (F,)       Simzeit je Bild in s (Einblendung)
    phase        (F,)       Ablaufphase je Bild
    json         ()         alles Uebrige (siehe ``Auftrag``): statische Koerper
                            mit Material, Glaeser (Radius, Hoehe), Kamera je
                            Bild, Szene, Titel, Bildrate, Ergebnistext

Gebaut wird er aus einer Newton-Aufzeichnung (``aus_aufzeichnung``, Format
``greifen/aufzeichnung.py``) oder aus der statischen Spuelmaschinen-Szene mit
dem Roboter in der Greifpose eines Slots (``aus_spuelmaschine``).
Er enthaelt keine Meshes: die ReBeL-Meshes liest erst das Isaac-Skript auf dem
Rechner, auf dem sie liegen (``scripts/fetch_assets.sh``).
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from .geometrie import matrix_quat

# Materialien (Name -> Parameter fuer OmniPBR bzw. OmniGlass im Isaac-Skript)
MATERIALIEN: Dict[str, dict] = {
    "igus_anthrazit": {"farbe": [0.155, 0.165, 0.175], "rauheit": 0.42, "metall": 0.0},
    "igus_orange": {"farbe": [0.94, 0.42, 0.02], "rauheit": 0.38, "metall": 0.0},
    "greifer": {"farbe": [0.09, 0.095, 0.10], "rauheit": 0.5, "metall": 0.0},
    "finger": {"farbe": [0.75, 0.76, 0.78], "rauheit": 0.3, "metall": 0.8},
    "schiene_alu": {"farbe": [0.80, 0.82, 0.85], "rauheit": 0.28, "metall": 1.0},
    "schlitten_alu": {"farbe": [0.62, 0.64, 0.67], "rauheit": 0.35, "metall": 1.0},
    "tisch_hell": {"farbe": [0.86, 0.80, 0.70], "rauheit": 0.55, "metall": 0.0},
    "arbeitsplatte_hell": {"farbe": [0.88, 0.86, 0.82], "rauheit": 0.4, "metall": 0.0},
    "boden": {"farbe": [0.40, 0.41, 0.43], "rauheit": 0.75, "metall": 0.0},
    "edelstahl": {"farbe": [0.78, 0.79, 0.80], "rauheit": 0.32, "metall": 1.0},
    "korb": {"farbe": [0.55, 0.57, 0.60], "rauheit": 0.45, "metall": 0.2},
    "korb_kunststoff": {"farbe": [0.88, 0.89, 0.90], "rauheit": 0.5, "metall": 0.0},
    "schrank_weiss": {"farbe": [0.93, 0.93, 0.92], "rauheit": 0.6, "metall": 0.0},
    "podest": {"farbe": [0.25, 0.26, 0.28], "rauheit": 0.6, "metall": 0.0},
    "matte": {"farbe": [0.12, 0.35, 0.55], "rauheit": 0.85, "metall": 0.0},
    "marke_ziel": {"farbe": [0.10, 0.62, 0.30], "rauheit": 0.5, "metall": 0.0},
    "marke_start": {"farbe": [0.35, 0.37, 0.40], "rauheit": 0.5, "metall": 0.0},
    "glas": {"glas": True, "farbe": [0.97, 0.99, 1.0], "ior": 1.5},
}

# URDF-Link -> Material (ReBeL-Glieder: anthrazit mit orangen Ringen)
LINK_MATERIAL = {
    "rail": "schiene_alu", "carriage": "schlitten_alu", "gripper_base": "greifer",
    "finger_left": "finger", "finger_right": "finger", "payload": None,
}
ARM_LINKS = ("base_link", "link_1", "link_2", "link_3", "link_4", "link_5", "link_6")

GRUPPE_MATERIAL = {
    "korpus": "edelstahl", "tuer": "edelstahl", "oberkorb": "korb", "unterkorb": "korb",
    "glashalter": "korb_kunststoff", "arbeitsplatte": "arbeitsplatte_hell", "schrank": "schrank_weiss",
    "podest": "podest", "boden": "boden",
}


def link_material(name: str) -> Optional[str]:
    if name in ARM_LINKS:
        return "igus_anthrazit"
    return LINK_MATERIAL.get(name, "igus_anthrazit")


def statisch_quader(name: str, mitte, halb, rot=None, material: str = "boden") -> dict:
    rot = np.eye(3) if rot is None else np.asarray(rot, float)
    return {"name": name, "form": "quader", "pos": [float(x) for x in mitte],
            "quat": [float(x) for x in matrix_quat(rot)], "halb": [float(x) for x in halb], "material": material}


def statisch_form(name: str, form: str, pos, material: str, **groessen) -> dict:
    """form: glas (radius, hoehe, kopfueber), scheibe (radius), ring (r_innen, r_aussen)."""
    d = {"name": name, "form": form, "pos": [float(x) for x in pos], "quat": [0.0, 0.0, 0.0, 1.0],
         "material": material}
    d.update({k: (bool(v) if isinstance(v, bool) else float(v)) for k, v in groessen.items()})
    if d.pop("kopfueber", False):
        d["quat"] = [1.0, 0.0, 0.0, 0.0]   # 180 Grad um x
    return d


# --- Kamera -------------------------------------------------------------------

def kamera_bahn(ziel, abstand: float, hoehe_grad: float, azimut_grad, brennweite_mm: float = 30.0) -> List[dict]:
    """Kamera je Bild auf einer Kugel um ``ziel`` (Azimut von +x gegen den Uhrzeigersinn)."""
    out = []
    e = math.radians(hoehe_grad)
    for az in np.atleast_1d(np.asarray(azimut_grad, float)):
        a = math.radians(float(az))
        auge = np.asarray(ziel, float) + abstand * np.array([math.cos(e) * math.cos(a), math.cos(e) * math.sin(a),
                                                             math.sin(e)])
        out.append({"auge": [float(x) for x in auge], "ziel": [float(x) for x in ziel], "brennweite_mm": brennweite_mm})
    return out


# --- Zeit ---------------------------------------------------------------------

def tempo_auto(sim_dauer: float, halten: float, ziel_s: float = 24.0) -> float:
    """Wie ``scripts/render_video.py``: Echtzeit, ausser das Video wuerde kuerzer als ``ziel_s``."""
    return min(1.0, sim_dauer / max(ziel_s - halten, 1.0))


def zeitplan(sim_dauer: float, fps: float, tempo: float, halten: float) -> np.ndarray:
    """Simzeit je Videobild: Ablauf mit ``tempo``, danach ``halten`` s Standbild."""
    n_lauf = int(round(sim_dauer / tempo * fps)) + 1
    n_halten = int(round(halten * fps))
    t = np.minimum(np.arange(n_lauf + n_halten), n_lauf - 1) / fps * tempo
    return np.minimum(t, sim_dauer)


def interpoliere(t_rec, q_rec, t: float) -> np.ndarray:
    """Posen aller Koerper zur Simzeit t (Ort linear, Quaternion normiert, kuerzester Weg)."""
    t_rec, q_rec = np.asarray(t_rec, float), np.asarray(q_rec, float)
    i = int(np.searchsorted(t_rec, t, side="right")) - 1
    if i < 0:
        return q_rec[0].copy()
    if i >= len(t_rec) - 1:
        return q_rec[-1].copy()
    a = (t - t_rec[i]) / max(t_rec[i + 1] - t_rec[i], 1e-12)
    q0, q1 = q_rec[i], q_rec[i + 1]
    vz = np.where(np.sum(q0[:, 3:7] * q1[:, 3:7], 1) < 0, -1.0, 1.0)[:, None]
    out = q0 * (1 - a) + a * q1
    qq = q0[:, 3:7] * (1 - a) + a * q1[:, 3:7] * vz
    out[:, 3:7] = qq / np.linalg.norm(qq, axis=1, keepdims=True)
    return out


# --- Auftraege ----------------------------------------------------------------

def ergebnis_text(meta: dict) -> str:
    if "zielfehler_xy_m" not in meta:
        return ""
    ok = "Erfolg" if meta.get("erfolg") else "Fehlversuch (" + ", ".join(meta.get("gruende", [])) + ")"
    return (f"{ok} · Zielfehler {meta['zielfehler_xy_m'] * 1e3:.1f} mm · "
            f"Kippung {meta.get('kippung_end_grad', float('nan')):.2f}°")


def aus_aufzeichnung(rec: dict, fps: float = 30.0, tempo: Optional[float] = None, halten: float = 3.0,
                     bis_bild: Optional[int] = None, kamerafahrt_grad: float = 14.0) -> dict:
    """Auftrag fuer die Glas-Greifdemo aus einer Aufzeichnung (``greifen.aufzeichnung.laden``)."""
    meta = rec["meta"]
    t_rec = np.asarray(rec["t"], float)
    q_rec = np.asarray(rec["body_q"], float)
    sim_dauer = float(t_rec[-1])
    tempo = tempo or tempo_auto(sim_dauer, halten)
    zeiten = zeitplan(sim_dauer, fps, tempo, halten)
    if bis_bild is not None:
        zeiten = zeiten[:bis_bild]
    posen = np.stack([interpoliere(t_rec, q_rec, t) for t in zeiten]).astype(np.float32)
    phasen = [rec["phase"][max(0, min(int(np.searchsorted(t_rec, t, side="right")) - 1, len(rec["phase"]) - 1))]
              for t in zeiten]

    tm, tg = meta["tisch_mitte_xy_m"], meta["tisch_groesse_m"]
    top = float(tg[2])
    r, h = float(meta["glas_radius_m"]), float(meta["glas_hoehe_m"])
    statisch = [
        statisch_quader("boden", (0.6, 0.3, -0.01), (4.0, 4.0, 0.01), material="boden"),
        statisch_quader("tisch", (tm[0], tm[1], top / 2.0), (tg[0] / 2.0, tg[1] / 2.0, top / 2.0),
                        material="tisch_hell"),
        statisch_form("marke_start", "ring", (*meta["start_xy_m"], top), "marke_start",
                      r_innen=r * 1.18, r_aussen=r * 1.32),
        statisch_form("marke_ziel", "ring", (*meta["ziel_xy_m"], top), "marke_ziel",
                      r_innen=r * 1.18, r_aussen=r * 1.32),
    ]
    mitte = (np.asarray(meta["start_xy_m"], float) + np.asarray(meta["ziel_xy_m"], float)) / 2.0
    ziel = (float(mitte[0]), float(mitte[1]) - 0.12, top + 0.12)
    n = len(zeiten)
    azimut = 62.0 + kamerafahrt_grad * (0.5 - 0.5 * np.cos(np.pi * np.arange(n) / max(n - 1, 1)))
    return {
        "szene": "greifdemo",
        "titel": "Räumwerk · Glas-Greifdemo",
        "fps": float(fps), "tempo": float(tempo),
        "koerper": list(rec["body_label"]),
        "posen": posen, "simzeit": zeiten.astype(np.float64), "phase": phasen,
        "glaeser": {"glas": {"radius": r, "hoehe": h}},
        "statisch": statisch,
        "kamera": kamera_bahn(ziel, 1.5, 28.0, azimut, 32.0),
        "ergebnis": ergebnis_text(meta),
        "ergebnis_ab_bild": int(round(sim_dauer / tempo * fps)) + 1,
        "quelle": {k: meta[k] for k in ("erfolg", "zielfehler_xy_m", "kippung_end_grad") if k in meta},
    }


def aus_spuelmaschine(slot: int = 1) -> dict:
    """Standbild-Auftrag: Spuelmaschine (Tuer offen, Oberkorb ausgezogen, Glaeser
    kopfueber), Arbeitsplatte, Podest und der ReBeL in der Greifpose von ``slot``
    (Erreichbarkeitsanalyse aus ``spuelmaschine.erreichbarkeit``)."""
    from spuelmaschine import erreichbarkeit, masse

    sc = masse.load_szene()
    lage = erreichbarkeit.lage_aus_szene(sc)
    pr = erreichbarkeit.Pruefer(lage, sc)
    ziel = [z for z in pr.ziele() if z.name == f"slot_{slot}"][0]
    e = pr.pruefe_ziel(ziel, int(sc["raster"]["seed"]))
    if e.q_greif is None:
        raise RuntimeError(f"Slot {slot}: keine Greifpose ({e.grund})")
    q = np.array(e.q_greif, float)
    welt = {name: pr.T @ m for name, m in pr.chain.fk_all(q).items()}
    koerper = list(welt)
    posen = np.array([[*welt[k][:3, 3], *matrix_quat(welt[k][:3, :3])] for k in koerper], np.float32)[None]

    statisch = [statisch_quader("boden", (0.5, 0.4, -0.01), (4.0, 4.0, 0.01), material="boden")]
    for k in pr.szene.koerper:
        statisch.append(statisch_quader(k.name, k.mitte, k.halb, k.rot, GRUPPE_MATERIAL.get(k.gruppe, "korb")))
    if pr.podest is not None:
        p = pr.podest
        statisch.append(statisch_quader("podest", p.mitte, p.halb, p.rot, "podest"))
    for g in pr.glaeser_korb:
        statisch.append(statisch_form(g.name, "glas", g.mitte, "glas", radius=g.halb[0], hoehe=2 * g.halb[2],
                                      kopfueber=True))
    for g in pr.glaeser_ablage:
        unten = g.mitte[2] - g.halb[2]
        statisch.append(statisch_form(g.name, "ring", (g.mitte[0], g.mitte[1], unten), "marke_ziel",
                                      r_innen=g.halb[0] * 1.1, r_aussen=g.halb[0] * 1.25))
    # Blick schraeg aus dem Raum auf Maschine und Roboter
    ziel_cam = (0.55, 0.45, 0.72)
    return {
        "szene": "spuelmaschine",
        "titel": "Räumwerk · Spülmaschine",
        "fps": 30.0, "tempo": 1.0,
        "koerper": koerper, "posen": posen, "simzeit": np.zeros(1), "phase": ["greifen"],
        "glaeser": {},
        "statisch": statisch,
        "kamera": kamera_bahn(ziel_cam, 2.9, 22.0, [112.0], 26.0),
        "ergebnis": "",
        "ergebnis_ab_bild": 10 ** 9,
        "quelle": {"slot": slot, "erreichbar": bool(e.ok), "ik_fehler_max_m": float(e.ik_fehler_max_m),
                   "kollisionen": list(e.kollisionen)},
    }


def aus_ausraeumen(rec: dict, fps: float = 30.0, video_s: float = 50.0, halten: float = 3.0,
                   bis_bild: Optional[int] = None) -> dict:
    """Auftrag fuer das Ausraeumen der Spuelmaschine (4 Glaeser) aus einer Aufzeichnung
    im Format von ``scripts/demo_ausraeumen.py --aufzeichnen``: ``meta`` enthaelt die
    statischen Kollisionsquader (``statisch``: name, gruppe, mitte, halb, rot), Glasmasse
    und Ablagepunkte; die Glaeser sind Koerper ``glas_*``."""
    meta = rec["meta"]
    t_rec = np.asarray(rec["t"], float)
    q_rec = np.asarray(rec["body_q"], float)
    sim_dauer = float(t_rec[-1])
    tempo = max(1.0, sim_dauer / max(video_s - halten, 1.0))
    zeiten = zeitplan(sim_dauer, fps, tempo, halten)
    if bis_bild is not None:
        zeiten = zeiten[:bis_bild]
    posen = np.stack([interpoliere(t_rec, q_rec, t) for t in zeiten]).astype(np.float32)
    phasen = [rec["phase"][max(0, min(int(np.searchsorted(t_rec, t, side="right")) - 1, len(rec["phase"]) - 1))]
              for t in zeiten]
    r, h = float(meta["glas_radius_m"]), float(meta["glas_hoehe_m"])
    statisch = [statisch_quader("boden", (0.5, 0.3, -0.01), (4.0, 4.0, 0.01), material="boden")]
    gruppen = {**GRUPPE_MATERIAL, "zwischenablage": "matte", "klemmbacke": "marke_ziel"}
    for k in meta["statisch"]:
        statisch.append(statisch_quader(k["name"], k["mitte"], k["halb"], k["rot"],
                                        gruppen.get(k["gruppe"], "korb")))
    for i, p in enumerate(meta.get("ablage_m", [])):
        statisch.append(statisch_form(f"ablage_{i + 1}", "ring", (p[0], p[1], p[2] - h / 2.0 + 0.0005),
                                      "marke_ziel", r_innen=r * 1.18, r_aussen=r * 1.32))
    glaeser = {n: {"radius": r, "hoehe": h} for n in rec["body_label"] if n.startswith("glas")}
    n = len(zeiten)
    azimut = 140.0 + 16.0 * (0.5 - 0.5 * np.cos(np.pi * np.arange(n) / max(n - 1, 1)))
    ergebnis = ""
    if "erfolge" in meta:
        ergebnis = f"{meta['erfolge']}/{len(glaeser)} Gläser aufrecht abgestellt"
    return {
        "szene": "ausraeumen",
        "titel": "Räumwerk · Spülmaschine ausräumen",
        "fps": float(fps), "tempo": float(tempo),
        "koerper": list(rec["body_label"]), "posen": posen, "simzeit": zeiten.astype(np.float64), "phase": phasen,
        "glaeser": glaeser, "statisch": statisch,
        "kamera": kamera_bahn((0.5, 0.2, 0.78), 2.5, 30.0, azimut, 26.0),
        "ergebnis": ergebnis,
        "ergebnis_ab_bild": int(round(sim_dauer / tempo * fps)) + 1,
        "quelle": {"sim_dauer_s": sim_dauer},
    }


# --- Datei --------------------------------------------------------------------

_ARRAYS = ("posen", "simzeit")


def speichern(auftrag: dict, pfad) -> Path:
    pfad = Path(pfad)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    rest = {k: v for k, v in auftrag.items() if k not in _ARRAYS + ("koerper", "phase")}
    np.savez_compressed(pfad, posen=np.asarray(auftrag["posen"], np.float32),
                        simzeit=np.asarray(auftrag["simzeit"], np.float64),
                        koerper=np.array([str(k) for k in auftrag["koerper"]]),
                        phase=np.array([str(p) for p in auftrag["phase"]]),
                        json=np.array(json.dumps(rest)))
    return pfad


def laden(pfad) -> dict:
    with np.load(pfad, allow_pickle=False) as z:
        d = json.loads(str(z["json"]))
        d["posen"] = z["posen"].astype(np.float64)
        d["simzeit"] = z["simzeit"]
        d["koerper"] = [str(k) for k in z["koerper"]]
        d["phase"] = [str(p) for p in z["phase"]]
    return d


def pruefen(a: dict) -> List[str]:
    """Konsistenz eines Auftrags; leere Liste = in Ordnung."""
    fehler = []
    f, b = a["posen"].shape[:2]
    if a["posen"].shape[2] != 7:
        fehler.append("posen: letzte Achse muss 7 sein")
    if len(a["koerper"]) != b:
        fehler.append(f"{len(a['koerper'])} Koerpernamen fuer {b} Koerper")
    if len(a["phase"]) != f or len(a["simzeit"]) != f:
        fehler.append("phase/simzeit passen nicht zur Bildzahl")
    if len(a["kamera"]) not in (1, f):
        fehler.append(f"{len(a['kamera'])} Kameras fuer {f} Bilder")
    nq = np.linalg.norm(a["posen"][..., 3:7], axis=-1)
    if not np.allclose(nq, 1.0, atol=1e-3):
        fehler.append("Quaternionen nicht normiert")
    for s in a["statisch"]:
        if s["material"] not in MATERIALIEN:
            fehler.append(f"{s['name']}: unbekanntes Material {s['material']}")
    return fehler
