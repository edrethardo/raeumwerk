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

def _hue_ellipse(cx, cy, a, b, ang, shape):
    import cv2
    m = np.zeros(shape, np.uint8)
    cv2.ellipse(m, ((float(cx), float(cy)), (float(2 * a), float(2 * b)), float(ang)), 1, -1)
    return m.astype(bool)


def baseline(rgb: np.ndarray, roi: tuple, px_glas: float, px_teller: Sequence[float], hoehe_vec: Sequence[float],
             schwelle: float = 0.0, arbeits_skala: float = 0.5) -> List[Dict]:
    """Klassische Erkennung. ``px_glas``: Durchmesser des Glasdeckels im Bild (px), ``px_teller``: erwartete
    Tellerdurchmesser (px, z. B. Dessert-, Essteller), ``hoehe_vec``: Bildverschiebung (dx, dy) Deckel -> Boden
    eines Glases (px). Rueckgabe: Liste {maske, klasse, score} im Vollbild."""
    import cv2
    x0, y0, x1, y1 = roi
    crop = rgb[y0:y1, x0:x1]
    s = arbeits_skala
    g = cv2.cvtColor(cv2.resize(crop, None, fx=s, fy=s, interpolation=cv2.INTER_AREA), cv2.COLOR_RGB2GRAY)
    g = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(cv2.GaussianBlur(g, (5, 5), 0))
    e = cv2.Canny(g, 35, 100)
    e = cv2.dilate(e, np.ones((3, 3), np.uint8))
    cs, _ = cv2.findContours(e, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    cand = []
    shape = rgb.shape[:2]
    d_g = px_glas * s
    d_t = [t * s for t in px_teller]
    for c in cs:
        if len(c) < 50:
            continue
        (cx, cy), (w, h), ang = cv2.fitEllipse(c)
        major, minor = max(w, h), min(w, h)
        if minor < 0.45 * major:
            continue
        # Abweichung der Kontur von der Ellipse (algebraisch, normiert)
        pts = c[:, 0, :].astype(float)
        th = math.radians(ang)
        ct, st = math.cos(th), math.sin(th)
        dx, dy = pts[:, 0] - cx, pts[:, 1] - cy
        xr, yr = dx * ct + dy * st, -dx * st + dy * ct
        r = np.sqrt((xr / (w / 2)) ** 2 + (yr / (h / 2)) ** 2)
        res = float(np.mean(np.abs(r - 1.0)))
        if res > 0.08:
            continue
        cover = len(np.unique(np.round(np.degrees(np.arctan2(yr, xr)) / 20))) / 18.0
        if cover < 0.45:
            continue
        for klasse, dref in [("glas", [d_g])] + [("teller", d_t)]:
            if any(0.75 * dr <= major <= 1.3 * dr for dr in dref):
                score = (1.0 - res / 0.08) * 0.5 + cover * 0.5
                cand.append((score, klasse, cx / s + x0, cy / s + y0, major / s / 2, minor / s / 2,
                             ang if w >= h else ang + 90.0))
                break
    cand.sort(key=lambda t: -t[0])
    out: List[Dict] = []
    for score, klasse, cx, cy, a, b, ang in cand:
        if score < schwelle:
            continue
        m = _hue_ellipse(cx, cy, a, b, ang, shape)
        if klasse == "glas":
            m2 = _hue_ellipse(cx + hoehe_vec[0], cy + hoehe_vec[1], a, b, ang, shape)
            hull = cv2.convexHull(np.argwhere(m | m2)[:, ::-1].astype(np.int32))
            mm = np.zeros(shape, np.uint8)
            cv2.fillConvexPoly(mm, hull, 1)
            m = mm.astype(bool)
        if any((m & o["maske"]).sum() / max(1, (m | o["maske"]).sum()) > 0.5 for o in out if o["klasse"] == klasse):
            continue
        out.append({"maske": m, "klasse": klasse, "score": float(score)})
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


def erk_laden(pfad) -> List[Dict]:
    z = np.load(pfad)
    x0, y0, x1, y1 = (int(v) for v in z["roi"])
    h, w = (int(v) for v in z["hw"])
    out = []
    for k in range(int(z["n"])):
        m = np.zeros((h, w), bool)
        m[y0:y1, x0:x1] = np.unpackbits(z["packed"][k])[: (y1 - y0) * (x1 - x0)].reshape(y1 - y0, x1 - x0).astype(bool)
        out.append({"maske": m, "klasse": str(z["klasse"][k]), "coco": int(z["coco"][k]), "score": float(z["score"][k])})
    return out
