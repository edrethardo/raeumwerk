"""Erkennung auf Renderbildern (Kameratag P3): klassische Baseline, vortrainiertes Instanzmodell, Bewertung.

* ``baseline``: Kanten + Ellipsenanpassung (OpenCV), Klasse nach Groesse; Masken aus dem projizierten Koerper
  (Glas: Huelle aus Deckel- und Bodenellipse, Teller: gefuellte Ellipse). Nutzt nur das RGB-Bild und die Kamera-/
  Groessenannahmen der Station (keine Tiefe, keine Nennlage).
* ``maskrcnn``: torchvision Mask R-CNN (COCO). Gewichte per ``scripts/p3_modell_holen.sh``, nicht im Repo.
* ``bewerten``: Zuordnung Erkennung <-> Instanzkarte (IoU), Treffer, Verwechslung, Verpasst, Fehldetektion.

Definitionen (je sichtbarem Objekt, Sichtbarkeit >= ``MIN_PX`` Pixel in der Instanzkarte):
  treffer      eine Erkennung der richtigen Klasse mit IoU >= 0,5, die nicht mehrere Objekte verschmilzt (jede
               Erkennung nur einmal vergeben)
  klassenfrei  eine Erkennung beliebiger Klasse mit IoU >= 0,5
  klassenfehler beste Erkennung mit IoU >= 0,5 hat die falsche Klasse (Glas <-> Teller)
  nachbar      kein Treffer, und die Erkennung verschmilzt >= 2 Objekte (je >= 30 % von deren Flaeche) oder die
               beste Erkennung (IoU >= 0,3) liegt mit groesserem IoU auf einem anderen Objekt (Nachbarverwechslung)
  ungenau      beste Erkennung mit IoU 0,3..0,5 (nicht verwechselt, aber unter der Treffer-Schwelle)
  verpasst     keine Erkennung mit IoU >= 0,3
Fehldetektion: Erkennung (Score >= Schwelle), die kein Objekt mit IoU >= 0,1 beruehrt (liegt auf Korb/Hintergrund).
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence

import numpy as np

MIN_PX = 1500                    # kleinste auswertbare Sichtbarkeit (Pixel bei 2472 x 2064)
COCO_GLAS = (46, 47)             # wine glass, cup
COCO_TELLER = (51,)              # bowl (COCO kennt keinen Teller)


# --- Region of interest -----------------------------------------------------------------------

def roi_aus_szene(d: Dict, cam, rand_px: int = 60, hw=None) -> tuple:
    """Pixel-Rechteck (x0, y0, x1, y1) um den Korb der Szene (aus der Korbgeometrie, nicht aus dem Bild)."""
    gruppen = ("oberkorb",) if d["korb"] == "ober" else ("unterkorb",)
    pts = []
    for k in d["statisch"]:
        if k["gruppe"] in gruppen:
            c, h, R = np.asarray(k["mitte"], float), np.asarray(k["halb"], float), np.asarray(k["rot"], float)
            for sx in (-1, 1):
                for sy in (-1, 1):
                    for sz in (-1, 1):
                        pts.append(c + R @ (np.array([sx, sy, sz]) * h))
    u, v, _ = cam.projiziere(np.array(pts))
    h_, w_, _, _ = cam.raster()
    x0, x1 = int(max(0, u.min() - rand_px)), int(min(w_, u.max() + rand_px))
    y0, y1 = int(max(0, v.min() - rand_px)), int(min(h_, v.max() + rand_px))
    return x0, y0, x1, y1


# --- Baseline ---------------------------------------------------------------------------------

def kreis_vorlage(cam, mitte, radius: float, normale, n: int = 72) -> np.ndarray:
    """Bildumriss (n, 2) eines Kreises im Raum (Mitte, Radius, Ebenennormale) relativ zum Bild der Mitte, in Pixeln."""
    nv = np.asarray(normale, float)
    nv = nv / np.linalg.norm(nv)
    t = np.cross(nv, [0.0, 0.0, 1.0] if abs(nv[2]) < 0.9 else [1.0, 0.0, 0.0])
    t /= np.linalg.norm(t)
    u_ = np.cross(nv, t)
    a = np.linspace(0, 2 * math.pi, n, endpoint=False)
    P = np.asarray(mitte, float) + radius * (np.outer(np.cos(a), t) + np.outer(np.sin(a), u_))
    u, v, _ = cam.projiziere(np.vstack([P, np.asarray(mitte, float)[None]]))
    return np.stack([u[:-1] - u[-1], v[:-1] - v[-1]], 1)


def vorlagen_aus_szene(d: Dict, cam) -> Dict:
    """Erwartete Bildumrisse (relativ zur Objektmitte) aus Kamerapose und Nennmassen: Glasdeckel (geschlossener
    Boden oben), Dessert- und Essteller. Referenzort: Mittel der Objekte der Szene (die Station kennt den Korb,
    nicht die einzelnen Plaetze)."""
    ob = d["objekte"]
    gl = [np.asarray(o["mitte"], float) for o in ob if o["klasse"] == "glas"]
    te = [np.asarray(o["mitte"], float) for o in ob if o["klasse"] == "teller"]
    cg = np.mean(gl, 0) if gl else np.array([0.30, 0.15, 0.475])
    ct = np.mean(te, 0) if te else np.array([0.30, 0.15, 0.52])
    z = np.array([0.0, 0.0, 1.0])
    lid = kreis_vorlage(cam, cg + 0.055 * z, 0.0375, z)
    uv = cam.projiziere(np.array([cg + 0.055 * z, cg - 0.055 * z]))
    ny = np.array([0.0, -1.0, 0.0])
    return {"glas": {"lid": lid, "versatz": (float(uv[0][1] - uv[0][0]), float(uv[1][1] - uv[1][0]))},
            "teller": {"dessert": kreis_vorlage(cam, ct, 0.095, ny), "essteller": kreis_vorlage(cam, ct, 0.13, ny)}}


def _ring(poly, s, dicke=3):
    import cv2
    p = poly * s
    x0, y0 = np.floor(p.min(0)).astype(int) - 6
    x1, y1 = np.ceil(p.max(0)).astype(int) + 6
    img = np.zeros((y1 - y0, x1 - x0), np.float32)
    cv2.polylines(img, [np.round(p - [x0, y0]).astype(np.int32)], True, 1.0, dicke)
    return img, p.mean(0) - [x0, y0]       # Vorlage und Ankerpunkt (Mitte)


def baseline(rgb: np.ndarray, roi: tuple, vorlagen: Dict, schwelle: Optional[Dict] = None, arbeits_skala: float = 0.5,
             massstaebe=(0.85, 1.0, 1.15)) -> List[Dict]:
    """Klassische Erkennung per Kantenabgleich: Canny-Kanten, Vorlage = projizierter Umriss der Nennform,
    ``matchTemplate`` bei mehreren Massstaeben, Maximumsuche. Score = mittlere Kantendichte laengs des Umrisses
    (0..1). Rueckgabe: Liste {maske, klasse, score, unter} im Vollbild."""
    import cv2
    schwelle = schwelle or {"glas": 0.75, "teller": 0.45}   # an den Tuning-Szenen (t_*) eingestellt, siehe docs/kameratag-p3.md
    x0, y0, x1, y1 = roi
    s = arbeits_skala
    g = cv2.cvtColor(cv2.resize(rgb[y0:y1, x0:x1], None, fx=s, fy=s, interpolation=cv2.INTER_AREA), cv2.COLOR_RGB2GRAY)
    g = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(cv2.GaussianBlur(g, (5, 5), 0))
    e = cv2.Canny(g, 30, 90).astype(np.float32) / 255.0
    ef = np.minimum(1.0, cv2.GaussianBlur(e, (0, 0), 1.6) * 6.0)
    shape = rgb.shape[:2]
    cand = []
    arten = [("glas", "glas", vorlagen["glas"]["lid"])] + [("teller", k, p) for k, p in vorlagen["teller"].items()]
    for klasse, unter, poly in arten:
        for ms in massstaebe:
            tm, anker = _ring(poly * ms, s)
            if tm.shape[0] >= ef.shape[0] or tm.shape[1] >= ef.shape[1]:
                continue
            res = cv2.matchTemplate(ef, tm, cv2.TM_CCORR) / max(1.0, float((tm > 0).sum()))
            r = int(0.45 * min(tm.shape))
            mx = cv2.dilate(res, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1)))
            ys, xs = np.where((res >= mx) & (res >= schwelle[klasse]))
            for yy, xx in zip(ys, xs):
                cand.append((float(res[yy, xx]), klasse, unter, (xx + anker[0]) / s + x0, (yy + anker[1]) / s + y0, ms))
    cand.sort(key=lambda t: -t[0])
    cand = cand[:120]
    out: List[Dict] = []
    klein, kz = [], 0.25
    sh_k = (int(shape[0] * kz) + 1, int(shape[1] * kz) + 1)
    for score, klasse, unter, cx, cy, ms in cand:
        poly = vorlagen["glas"]["lid"] if klasse == "glas" else vorlagen["teller"][unter]
        pts = poly * ms + [cx, cy]
        if klasse == "glas":
            vx, vy = vorlagen["glas"]["versatz"]
            pts = cv2.convexHull(np.vstack([pts, pts + [vx * ms, vy * ms]]).astype(np.float32))[:, 0, :]
        mk = np.zeros(sh_k, np.uint8)
        cv2.fillPoly(mk, [np.round(pts * kz).astype(np.int32)], 1)
        mk = mk.astype(bool)
        if any(_iou(mk, o) > 0.4 for o in klein):
            continue
        klein.append(mk)
        m = np.zeros(shape, np.uint8)
        cv2.fillPoly(m, [np.round(pts).astype(np.int32)], 1)
        out.append({"maske": m.astype(bool), "klasse": klasse, "score": score, "unter": unter})
    return out



# --- Mask R-CNN -------------------------------------------------------------------------------

def maskrcnn_laden(pfad: str, device: str = "cuda"):
    import torch
    import torchvision
    m = torchvision.models.detection.maskrcnn_resnet50_fpn(weights=None, weights_backbone=None)
    m.load_state_dict(torch.load(pfad, map_location="cpu"))
    m.transform.min_size = (1000,)
    m.transform.max_size = 1800
    m.roi_heads.detections_per_img = 100
    m.roi_heads.score_thresh = 0.2
    return m.to(device).eval()


def maskrcnn(modell, rgb: np.ndarray, roi: tuple, device: str = "cuda") -> List[Dict]:
    """Erkennung im Ausschnitt ``roi``; Masken (Schwelle 0,5) ins Vollbild gesetzt. ``coco`` = COCO-Klassen-ID."""
    import torch
    x0, y0, x1, y1 = roi
    crop = np.ascontiguousarray(rgb[y0:y1, x0:x1])
    t = torch.from_numpy(crop).permute(2, 0, 1).float().div(255.0).to(device)
    with torch.no_grad():
        o = modell([t])[0]
    out = []
    for k in range(len(o["scores"])):
        m = np.zeros(rgb.shape[:2], bool)
        m[y0:y1, x0:x1] = (o["masks"][k, 0] > 0.5).cpu().numpy()
        coco = int(o["labels"][k])
        klasse = "glas" if coco in COCO_GLAS else "teller" if coco in COCO_TELLER else "andere"
        out.append({"maske": m, "klasse": klasse, "coco": coco, "score": float(o["scores"][k])})
    return out


# --- Bewertung --------------------------------------------------------------------------------

def _iou(a: np.ndarray, b: np.ndarray) -> float:
    u = int((a | b).sum())
    return float((a & b).sum()) / u if u else 0.0


def bewerten(inst: np.ndarray, namen: Sequence[str], klassen: Dict[str, str], erk: List[Dict],
             schwelle: float = 0.5, min_px: int = MIN_PX) -> Dict:
    """Je Objekt Treffer/IoU/Verwechslung (Definitionen im Modulkopf); Erkennungen ``erk`` mit Score >= ``schwelle``."""
    erk = [e for e in erk if e["score"] >= schwelle]
    gt = {n: inst == (i + 1) for i, n in enumerate(namen)}
    gt = {n: m for n, m in gt.items() if int(m.sum()) >= min_px}
    n_e, n_g = len(erk), len(gt)
    gnamen = list(gt)
    iou = np.zeros((n_g, n_e))
    for i, n in enumerate(gnamen):
        for j, e in enumerate(erk):
            iou[i, j] = _iou(gt[n], e["maske"])
    ergeb: Dict[str, Dict] = {}
    # Verschmelzung: eine Erkennung deckt >= 2 Objekte mit je >= 30 % von deren Flaeche
    verschm = [False] * n_e
    for j in range(n_e):
        ueber = [n2 for n2 in gnamen if (gt[n2] & erk[j]["maske"]).sum() >= 0.3 * gt[n2].sum()]
        verschm[j] = len(ueber) >= 2
    belegt: set = set()
    # Treffer: klassenrichtig, groesster IoU zuerst (jede Erkennung nur einmal), nicht verschmolzen
    paare = sorted(((iou[i, j], i, j) for i in range(n_g) for j in range(n_e) if iou[i, j] >= 0.5 and not verschm[j]),
                   reverse=True)
    zug: Dict[int, int] = {}
    for v, i, j in paare:
        if i in zug or j in belegt:
            continue
        if erk[j]["klasse"] == klassen[gnamen[i]]:
            zug[i] = j
            belegt.add(j)
    for i, n in enumerate(gnamen):
        res = {"klasse": klassen[n], "px": int(gt[n].sum()), "iou": 0.0, "treffer": False, "klassenfrei": False,
               "klassenfehler": False, "nachbar": False, "ungenau": False, "verpasst": False, "best_iou": 0.0}
        jb = int(np.argmax(iou[i])) if n_e else -1
        if n_e:
            res["best_iou"] = float(iou[i, jb])
        if i in zug:
            res["treffer"] = res["klassenfrei"] = True
            res["iou"] = float(iou[i, zug[i]])
        elif n_e and res["best_iou"] >= 0.5 and not verschm[jb]:
            res["klassenfrei"] = True
            res["iou"] = res["best_iou"]
            res["klassenfehler"] = erk[jb]["klasse"] != klassen[n]
            if not res["klassenfehler"]:
                res["ungenau"] = True             # richtige Klasse, aber die Erkennung gehoert schon einem anderen Objekt
        else:
            nb = bool(n_e) and any(verschm[j] and (gt[n] & erk[j]["maske"]).sum() >= 0.3 * gt[n].sum()
                                   for j in range(n_e))
            if not nb and n_e and res["best_iou"] >= 0.3:
                nb = int(np.argmax(iou[:, jb])) != i
            res["nachbar"] = bool(nb)
            res["ungenau"] = (not nb) and res["best_iou"] >= 0.3
            res["verpasst"] = (not nb) and res["best_iou"] < 0.3
        ergeb[n] = res
    fehl = []
    for j, e in enumerate(erk):
        if n_g == 0 or iou[:, j].max() < 0.1:
            fehl.append({"klasse": e["klasse"], "coco": e.get("coco"), "score": e["score"], "px": int(e["maske"].sum())})
    return {"objekte": ergeb, "fehldetektionen": fehl, "n_erkennungen": n_e, "n_sichtbar": n_g,
            "unsichtbar": sorted(n for n, i in zip(namen, range(len(namen))) if n not in gt)}


# --- Ablage der Erkennungen -------------------------------------------------------------------

def erk_speichern(pfad, erk: List[Dict], roi: tuple, hw: tuple) -> None:
    """Erkennungen (Masken nur im ROI, bitweise gepackt) in eine .npz schreiben."""
    x0, y0, x1, y1 = roi
    packed = [np.packbits(e["maske"][y0:y1, x0:x1].ravel()) for e in erk]
    np.savez_compressed(pfad, roi=np.array(roi), hw=np.array(hw), n=len(erk),
                        packed=np.array(packed) if packed else np.zeros((0, 1), np.uint8),
                        klasse=np.array([e["klasse"] for e in erk] or [""]),
                        coco=np.array([e.get("coco", -1) for e in erk] or [-1]),
                        score=np.array([e["score"] for e in erk] or [0.0]))


def erk_laden(pfad, f: int = 1) -> List[Dict]:
    """Erkennungen laden; ``f`` > 1: Masken nur an jedem f-ten Pixel (wie ``inst[::f, ::f]``), schneller auszuwerten."""
    z = np.load(pfad)
    x0, y0, x1, y1 = (int(v) for v in z["roi"])
    h, w = (int(v) for v in z["hw"])
    ys = np.arange(-(-y0 // f) * f, y1, f)
    xs = np.arange(-(-x0 // f) * f, x1, f)
    out = []
    for k in range(int(z["n"])):
        m = np.zeros((-(-h // f), -(-w // f)), bool)
        if len(ys) and len(xs):
            crop = np.unpackbits(z["packed"][k])[: (y1 - y0) * (x1 - x0)].reshape(y1 - y0, x1 - x0)
            m[ys[0] // f:ys[-1] // f + 1, xs[0] // f:xs[-1] // f + 1] = crop[np.ix_(ys - y0, xs - x0)].astype(bool)
        out.append({"maske": m, "klasse": str(z["klasse"][k]), "coco": int(z["coco"][k]), "score": float(z["score"][k])})
    return out
