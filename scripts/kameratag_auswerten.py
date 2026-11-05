#!/usr/bin/env python3
"""Auswertung des ersten Kameratags: Messdatei + Vorhersagekatalog -> Abweichung, Urteil, Konsequenz.

Aufruf::

    scripts/kameratag_auswerten.py MESSDATEI [--katalog KATALOG] [--basis ORDNER] [--out ORDNER]
    scripts/kameratag_auswerten.py --demo ORDNER      # schreibt synthetische Aufnahmen (ohne Kamera)

* Eingabe: eine YAML-Messdatei (Aufbau siehe ``beispiele/kameratag-messung-beispiel.yaml`` und
  ``docs/kameratag-messprotokoll.md``) und der eingefrorene Katalog ``config/kameratag_vorhersagen.yaml``.
* Aufnahmen sind relativ zu ``--basis`` (Standard: Ordner der Messdatei). Punktwolken: ``.npz`` mit ``xyz``
  (H, W, 3) organisiert oder (N, 3), Millimeter im Kamerarahmen, NaN = ungültig, optional ``maske`` (bool, H x W);
  oder ``.ply`` (ASCII oder binary_little_endian, Punkte x y z in mm, unorganisiert).
* Ausgabe: ``kameratag_ergebnis.md`` und ``kameratag_ergebnis.json`` in ``--out`` (Standard: Ordner der Messdatei).
* Nicht gemessene Zeilen werden als solche ausgewiesen, nicht geraten.
* Urteile: ``stimmt`` / ``zu_optimistisch`` (Wirklichkeit schlechter als das Modell) / ``zu_pessimistisch``
  (Wirklichkeit besser) / ``unbekannt`` (Einordnung ohne Vorhersage) / ``nicht_gemessen``.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import yaml

WURZEL = Path(__file__).resolve().parents[1]
KATALOG_STANDARD = WURZEL / "config" / "kameratag_vorhersagen.yaml"

STIMMT, OPT, PESS, UNBEK, NICHT = "stimmt", "zu_optimistisch", "zu_pessimistisch", "unbekannt", "nicht_gemessen"
GRUPPEN_PRAEFIX = {"glas": "glas", "teller_ober": "oberteller", "teller_unter": "unterteller"}


# --------------------------------------------------------------------------------------------------
# Einlesen: Katalog, Punktwolken
# --------------------------------------------------------------------------------------------------

def lade_yaml(pfad) -> Dict[str, Any]:
    with open(pfad, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def lade_katalog(pfad=KATALOG_STANDARD) -> Dict[str, Any]:
    kat = lade_yaml(pfad)
    kat["_zeilen"] = {int(z["id"]): z for z in kat["zeilen"]}
    kat["_unbekannt"] = {u["id"]: u for u in kat["unbekannt"]}
    return kat


_PLY_TYPEN = {"char": "i1", "uchar": "u1", "short": "i2", "ushort": "u2", "int": "i4", "uint": "u4",
              "float": "f4", "double": "f8", "int8": "i1", "uint8": "u1", "int16": "i2", "uint16": "u2",
              "int32": "i4", "uint32": "u4", "float32": "f4", "float64": "f8"}


def lese_ply(pfad) -> np.ndarray:
    """Punkte (N, 3) aus einer PLY-Datei (ASCII oder binary_little_endian); nur Eckpunkt-Eigenschaften x, y, z."""
    with open(pfad, "rb") as f:
        roh = f.read()
    ende = roh.find(b"end_header")
    if ende < 0:
        raise ValueError(f"{pfad}: kein PLY-Kopf")
    nl = roh.find(b"\n", ende)
    kopf = roh[:ende].decode("ascii", "replace").splitlines()
    daten = roh[nl + 1:]
    fmt, n, eig, im_vertex = None, 0, [], False
    for z in kopf:
        t = z.split()
        if not t:
            continue
        if t[0] == "format":
            fmt = t[1]
        elif t[0] == "element":
            im_vertex = t[1] == "vertex"
            if im_vertex:
                n = int(t[2])
            elif n:
                break                                     # weitere Elemente (Flächen) werden nicht gelesen
        elif t[0] == "property" and im_vertex:
            if t[1] == "list":
                raise ValueError("PLY: Listen-Eigenschaften im Eckpunkt-Element nicht unterstützt")
            eig.append((t[2], _PLY_TYPEN[t[1]]))
    namen = [e[0] for e in eig]
    if not all(k in namen for k in "xyz"):
        raise ValueError("PLY ohne x, y, z")
    if fmt == "ascii":
        zeilen = daten.decode("ascii", "replace").splitlines()[:n]
        a = np.array([[float(v) for v in z.split()[:len(eig)]] for z in zeilen], float)
        return a[:, [namen.index("x"), namen.index("y"), namen.index("z")]]
    if fmt == "binary_little_endian":
        dt = np.dtype([(nm, "<" + t) for nm, t in eig])
        a = np.frombuffer(daten, dtype=dt, count=n)
        return np.stack([a["x"], a["y"], a["z"]], axis=1).astype(float)
    raise ValueError(f"PLY-Format nicht unterstützt: {fmt}")


def lade_wolke(pfad) -> Dict[str, Any]:
    p = Path(pfad)
    if not p.exists():
        raise FileNotFoundError(str(p))
    if p.suffix.lower() == ".npz":
        d = np.load(p)
        xyz = np.asarray(d["xyz"], float)
        maske = np.asarray(d["maske"], bool) if "maske" in d.files else None
        return {"xyz": xyz, "maske": maske, "organisiert": xyz.ndim == 3}
    if p.suffix.lower() == ".ply":
        return {"xyz": lese_ply(p), "maske": None, "organisiert": False}
    raise ValueError(f"{p.name}: Format nicht unterstützt (npz oder ply)")


def gueltig(xyz: np.ndarray) -> np.ndarray:
    """Maske der gültigen Punkte (endlich, z > 0)."""
    return np.isfinite(xyz).all(axis=-1) & (xyz[..., 2] > 0)


def roi_punkte(w: Dict[str, Any], roi_px=None, roi_mm=None, maske=None) -> np.ndarray:
    """Gültige Punkte (N, 3) im Bereich: roi_px [u0, v0, u1, v1] (organisiert) oder roi_mm [xmin, xmax, ymin, ymax]."""
    xyz = w["xyz"]
    if maske is None and roi_px is None and roi_mm is None:
        maske = w["maske"]
    if xyz.ndim == 3:
        gv = gueltig(xyz)
        if roi_px is not None:
            u0, v0, u1, v1 = [int(v) for v in roi_px]
            sel = np.zeros_like(gv)
            sel[v0:v1, u0:u1] = True
            gv = gv & sel
        if maske is not None:
            gv = gv & np.asarray(maske, bool)
        pts = xyz[gv]
    else:
        pts = xyz[gueltig(xyz)]
    if roi_mm is not None:
        x0, x1, y0, y1 = roi_mm
        pts = pts[(pts[:, 0] >= x0) & (pts[:, 0] <= x1) & (pts[:, 1] >= y0) & (pts[:, 1] <= y1)]
    return pts


# --------------------------------------------------------------------------------------------------
# Rechnen (Punktwolken -> Zahlen); alles reines numpy, ohne Kamera
# --------------------------------------------------------------------------------------------------

def ebene_fit(pts: np.ndarray, trimmen: bool = True) -> Dict[str, Any]:
    """Ebene durch Punkte (N, 3): Schwerpunkt, Normale (z > 0), sigma der Normalabstände (mm, ddof = 3)."""
    p = np.asarray(pts, float)
    if len(p) < 10:
        raise ValueError(f"zu wenige Punkte für die Ebene: {len(p)}")
    for _ in range(2 if trimmen else 1):
        c = p.mean(axis=0)
        n = np.linalg.svd(p - c, full_matrices=False)[2][2]
        if n[2] < 0:
            n = -n
        r = (p - c) @ n
        s = math.sqrt(float((r ** 2).sum()) / max(len(p) - 3, 1))
        if not trimmen or s == 0:
            break
        keep = np.abs(r) < 4 * s
        if keep.all():
            break
        p = p[keep]
    return {"schwerpunkt": c, "normale": n, "sigma_mm": s, "n": int(len(p)), "z_mm": float(c[2])}


def sigma_aus_wolke(pfad, roi_px=None, roi_mm=None) -> Tuple[float, float, int]:
    """(z in m, sigma der Ebenenresiduen in mm, Punktzahl) einer Aufnahme einer ebenen Platte."""
    f = ebene_fit(roi_punkte(lade_wolke(pfad), roi_px, roi_mm))
    return f["z_mm"] / 1000.0, f["sigma_mm"], f["n"]


def abdeckung_pct(w: Dict[str, Any], maske: Optional[np.ndarray] = None) -> float:
    """Anteil der Pixel der Objektmaske mit gültigem Tiefenwert in Prozent (organisierte Wolke + Maske)."""
    m = maske if maske is not None else w["maske"]
    if m is None or w["xyz"].ndim != 3:
        raise ValueError("Punktabdeckung braucht eine organisierte Wolke (H, W, 3) und eine Maske")
    m = np.asarray(m, bool)
    if m.sum() == 0:
        raise ValueError("leere Maske")
    return 100.0 * float((gueltig(w["xyz"]) & m).sum()) / float(m.sum())


def punkt_streuung(wolken: List[Dict[str, Any]], roi_px=None, min_anteil: float = 0.8) -> Dict[str, float]:
    """Streuung von z je Pixel über mehrere Aufnahmen derselben Szene (organisiert, gleiche Form)."""
    if len(wolken) < 3:
        raise ValueError("mindestens 3 Aufnahmen nötig")
    if not all(w["xyz"].ndim == 3 and w["xyz"].shape == wolken[0]["xyz"].shape for w in wolken):
        raise ValueError("Punktstreuung braucht organisierte Wolken gleicher Form")
    z = np.stack([np.where(gueltig(w["xyz"]), w["xyz"][..., 2], np.nan) for w in wolken])
    if roi_px is not None:
        u0, v0, u1, v1 = [int(v) for v in roi_px]
        z = z[:, v0:v1, u0:u1]
    ok = np.isfinite(z).sum(axis=0) >= max(3, int(min_anteil * len(wolken)))
    if ok.sum() < 20:
        raise ValueError("zu wenige Pixel in allen Aufnahmen gültig")
    sd = np.nanstd(z, axis=0, ddof=1)
    return {"sigma_median_mm": float(np.median(sd[ok])), "z_m": float(np.nanmean(z[:, ok])) / 1000.0,
            "pixel": int(ok.sum()), "aufnahmen": len(wolken)}


def kabsch(a, b) -> Dict[str, float]:
    """Starre Anpassung b ~ R a + t. Versatz = Abstand der Schwerpunkte, Drehung = Winkel von R, Rest = RMS."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    if a.shape != b.shape or a.ndim != 2 or a.shape[1] != 3 or len(a) < 3:
        raise ValueError("Kabsch: gleich viele (>= 3) Punkte (N, 3) nötig")
    ca, cb = a.mean(axis=0), b.mean(axis=0)
    U, _, Vt = np.linalg.svd((a - ca).T @ (b - cb))
    d = np.sign(np.linalg.det(Vt.T @ U.T)) or 1.0
    R = Vt.T @ np.diag([1.0, 1.0, d]) @ U.T
    winkel = math.degrees(math.acos(max(-1.0, min(1.0, (np.trace(R) - 1.0) / 2.0))))
    rest = float(np.sqrt((((a - ca) @ R.T + cb - b) ** 2).sum(axis=1).mean()))
    return {"versatz_mm": float(np.linalg.norm(ca - cb)), "dreh_grad": winkel, "rest_rms_mm": rest, "n": int(len(a))}


def wilson(k: float, n: float, z: float = 1.96) -> Tuple[float, float]:
    """Wilson-Intervall 95 % für eine Rate k/n."""
    if n <= 0:
        return 0.0, 1.0
    p = k / n
    nenner = 1 + z * z / n
    mitte = (p + z * z / (2 * n)) / nenner
    halb = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / nenner
    return max(0.0, mitte - halb), min(1.0, mitte + halb)


# --------------------------------------------------------------------------------------------------
# Urteilsbausteine
# --------------------------------------------------------------------------------------------------

def urteil_intervall(wert: float, lo: float, hi: float, groesser_ist_schlechter: bool = True) -> str:
    # Gleitkomma-Rest an der Schwelle abfangen (z. B. -20,000000000000018 mm bei Soll-Abweichung -20 mm)
    wert, lo, hi = round(wert, 9), round(lo, 9), round(hi, 9)
    if lo <= wert <= hi:
        return STIMMT
    ueber = wert > hi
    return OPT if ueber == groesser_ist_schlechter else PESS


def zusammen(urteile: List[str]) -> str:
    """Zeilenurteil: ein 'zu_optimistisch' gewinnt (vorsichtig), dann 'zu_pessimistisch'."""
    u = [x for x in urteile if x in (STIMMT, OPT, PESS)]
    if not u:
        return NICHT
    if OPT in u:
        return OPT
    if PESS in u:
        return PESS
    return STIMMT


def stufe(stufen, wert: float) -> str:
    """Letzte Stufe mit ab <= wert; fehlt eine passende, die erste. ``stufen`` ist Liste von {ab, text} oder ein Text."""
    if isinstance(stufen, str):
        return stufen
    wahl = stufen[0]
    for s in stufen:
        if wert >= float(s["ab"]):
            wahl = s
    return wahl["text"]


def teil(schluessel: str, text: str, gemessen, vorhersage, urteil: str, hinweis: str = "", einheit: str = "") -> Dict[str, Any]:
    return {"schluessel": schluessel, "text": text, "gemessen": gemessen, "vorhersage": vorhersage,
            "urteil": urteil, "hinweis": hinweis, "einheit": einheit}


def zeile(kat, zid, teile: List[Dict[str, Any]], konsequenz: str, hinweise: Optional[List[str]] = None,
          urteil: Optional[str] = None) -> Dict[str, Any]:
    z = kat["_zeilen"][zid]
    u = urteil or zusammen([t["urteil"] for t in teile])
    return {"id": zid, "name": z["name"], "einheit": z["einheit"], "urteil": u, "teile": teile,
            "konsequenz": konsequenz, "hinweise": hinweise or []}


def nicht_gemessen(kat, zid) -> Dict[str, Any]:
    z = kat["_zeilen"][zid] if isinstance(zid, int) else kat["_unbekannt"][zid]
    return {"id": zid, "name": z["name"], "einheit": z.get("einheit", ""), "urteil": NICHT, "teile": [],
            "konsequenz": "keine Messwerte in der Messdatei", "hinweise": []}


def _pfad(basis: Path, rel) -> Path:
    p = Path(str(rel))
    return p if p.is_absolute() else basis / p


def _liste(v) -> List[float]:
    if v is None:
        return []
    return [float(x) for x in (v if isinstance(v, (list, tuple)) else [v])]


def _maxabs(v) -> Optional[float]:
    v = _liste(v)
    return max(abs(x) for x in v) if v else None


# --------------------------------------------------------------------------------------------------
# Zeilen 1 bis 13
# --------------------------------------------------------------------------------------------------

def z01(kat, m, basis) -> Dict[str, Any]:
    z = kat["_zeilen"][1]
    P = z["parameter"]
    teile, hinw, d405_opt, stufenwert = [], [], False, 0.0
    for kamera, bez in (("ensenso", "Ensenso"), ("d405", "D405")):
        k = P[kamera]["k_mm_pro_m2"]
        for i, e in enumerate(m.get(kamera) or [], 1):
            if "sigma_mm" in e:
                zm, sg, n = float(e["z_m"]), float(e["sigma_mm"]), None
            else:
                zm, sg, n = sigma_aus_wolke(_pfad(basis, e["aufnahme"]), e.get("roi_px"), e.get("roi_mm"))
            soll = k * zm ** 2
            faktor = sg / soll
            u = urteil_intervall(faktor, P[kamera]["faktor_tief"], P[kamera]["faktor_hoch"], True)
            teile.append(teil(f"{kamera}_{i}", f"{bez}: sigma bei z = {zm:.3f} m", round(sg, 4), round(soll, 4), u,
                              f"Faktor {faktor:.2f} gegenüber Modell" + (f", {n} Punkte" if n else ""), "mm"))
            if kamera == "ensenso":
                stufenwert = max(stufenwert, faktor)
            elif u == OPT:
                d405_opt = True
    if not teile:
        return nicht_gemessen(kat, 1)
    u = zusammen([t["urteil"] for t in teile])
    if u == STIMMT:
        k = z["konsequenz"]["stimmt"]
    elif u == OPT:
        k = stufe(z["konsequenz"]["zu_optimistisch"], stufenwert) if any(
            t["urteil"] == OPT and t["schluessel"].startswith("ensenso") for t in teile) else ""
        if d405_opt:
            k = (k + " " if k else "") + z["konsequenz_d405"]
    else:
        k = z["konsequenz"]["zu_pessimistisch"]
    hinw.append("Rauschen ist die Streuung der Ebenenresiduen einer matten, ebenen Platte; die Unebenheit der Platte geht in die Messung ein (obere Schranke).")
    return zeile(kat, 1, teile, k, hinw)


def z02(kat, m, basis) -> Dict[str, Any]:
    z = kat["_zeilen"][2]
    tol = z["parameter"]["tol_mm"]
    teile, hinw = [], []
    for pos, werte in (m or {}).items():
        if pos not in kat["positionen"]:
            hinw.append(f"Position '{pos}' ist nicht im Katalog")
            continue
        for r, v in werte.items():
            soll = kat["positionen"][pos]["referenz"][r]["abstand_m"]
            ab = (float(v) - soll) * 1000.0
            u = urteil_intervall(ab, -tol, tol, True)
            h = f"Abweichung {ab:+.0f} mm"
            if float(v) < 0.75:
                h += "; unter dem Betriebsabstand 0,75 m (nicht messbar)"
            teile.append(teil(f"{pos}_{r}", f"{pos}: Abstand zu {r}", float(v), soll, u, h, "m"))
    if not teile:
        return nicht_gemessen(kat, 2)
    u = zusammen([t["urteil"] for t in teile])
    return zeile(kat, 2, teile, z["konsequenz"][{STIMMT: "stimmt", OPT: "zu_optimistisch", PESS: "zu_pessimistisch"}[u]], hinw)


def z03(kat, m, basis) -> Dict[str, Any]:
    z = kat["_zeilen"][3]
    P = z["parameter"]
    teile, hinw = [], []
    for pos, w in (m or {}).items():
        if pos not in kat["positionen"]:
            hinw.append(f"Position '{pos}' ist nicht im Katalog")
            continue
        if w.get("fov_1m_mm") or w.get("fov_mm"):
            fov = [float(v) for v in (w.get("fov_1m_mm") or w["fov_mm"])]
            if w.get("fov_mm"):                                   # bei Abstand z gemessen -> auf 1 m umrechnen
                fov = [v / float(w["z_m"]) for v in fov]
            for ach, g, s in zip("xy", fov, P["fov_1m_mm"]):
                rel = g / s - 1.0
                u = urteil_intervall(rel, -P["tol_rel"], P["tol_rel"], False)
                teile.append(teil(f"{pos}_fov_{ach}", f"{pos}: Sichtfeld {ach} bei 1 m", round(g, 1), s, u,
                                  f"{100 * rel:+.1f} %", "mm"))
        for ak, n in (w.get("ecken") or {}).items():
            soll = P["ecken_im_bild"][pos][ak]
            d = int(n) - soll
            u = STIMMT if abs(d) <= P["ecken_tol"] else (OPT if d < 0 else PESS)
            teile.append(teil(f"{pos}_ecken_{ak}", f"{pos}: Korbecken im Bild ({ak})", int(n), soll, u, f"Differenz {d:+d} von 8", "Ecken"))
    if not teile:
        return nicht_gemessen(kat, 3)
    u = zusammen([t["urteil"] for t in teile])
    return zeile(kat, 3, teile, z["konsequenz"][{STIMMT: "stimmt", OPT: "zu_optimistisch", PESS: "zu_pessimistisch"}[u]], hinw)


def _platz_nutzbar(name: str, e, min_punkte: int) -> Tuple[bool, Optional[float]]:
    if isinstance(e, bool):
        return e, None
    if "nutzbar" in e:
        return bool(e["nutzbar"]), (float(e["sichtbar_pct"]) if "sichtbar_pct" in e else None)
    if "punkte" in e:
        grenze = min_punkte if name.startswith(("oberteller", "unterteller")) else 0
        return int(e["punkte"]) >= grenze, (float(e["sichtbar_pct"]) if "sichtbar_pct" in e else None)
    raise ValueError(f"Platz {name}: nutzbar oder punkte angeben")


def z04(kat, m, basis) -> Dict[str, Any]:
    z = kat["_zeilen"][4]
    P = z["parameter"]
    teile, hinw, fehlende = [], [], []
    for pos, ausz in (m or {}).items():
        if pos not in kat["positionen"]:
            hinw.append(f"Position '{pos}' ist nicht im Katalog")
            continue
        K = kat["positionen"][pos]["plaetze"]
        for ak, plaetze in ausz.items():
            if ak not in ("a225", "a450", "a0"):
                hinw.append(f"Auszug '{ak}' unbekannt (a0, a225, a450)")
                continue
            for g, pre in GRUPPEN_PRAEFIX.items():
                sel = {p: e for p, e in plaetze.items() if p.startswith(pre + "_")}
                if not sel:
                    continue
                gemessen, vorher, sicht = 0, 0, []
                for p, e in sel.items():
                    if p not in K:
                        hinw.append(f"Platz '{p}' ist nicht im Katalog")
                        continue
                    nutz, sp = _platz_nutzbar(p, e, P["min_punkte_teller"])
                    gemessen += int(nutz)
                    vorher += int(K[p][ak][3])
                    if sp is not None and K[p][ak][1] is not None:
                        sicht.append(sp - K[p][ak][0])
                    if nutz != bool(K[p][ak][3]):
                        fehlende.append(f"{pos} {ak} {p}: gemessen {'nutzbar' if nutz else 'nicht nutzbar'}, vorhergesagt {'nutzbar' if K[p][ak][3] else 'nicht nutzbar'}")
                d = gemessen - vorher
                if ak == "a0":
                    u, h = UNBEK, "Auszug 0 wird nicht gewertet (Information)"
                else:
                    u = STIMMT if abs(d) <= P["tol_zahl"] else (OPT if d < 0 else PESS)
                    h = f"Differenz {d:+d} bei {len(sel)} Plätzen"
                teile.append(teil(f"{pos}_{ak}_{g}", f"{pos}, Auszug {ak}, {g}: nutzbare Plätze", gemessen, vorher, u, h, "Plätze"))
                if sicht and ak != "a0":
                    mw = sum(sicht) / len(sicht)
                    us = urteil_intervall(mw, -P["tol_sichtbar_pp"], P["tol_sichtbar_pp"], False)
                    teile.append(teil(f"{pos}_{ak}_{g}_sichtbar", f"{pos}, Auszug {ak}, {g}: mittlere Abweichung der sichtbaren Fläche",
                                      round(mw, 1), 0.0, us, f"{len(sicht)} Plätze", "Prozentpunkte"))
    if not teile:
        return nicht_gemessen(kat, 4)
    u = zusammen([t["urteil"] for t in teile])
    if u == NICHT:                                  # nur Auszug 0: Information, kein Urteil
        return zeile(kat, 4, teile, "Auszug 0 (Korb drin) wird nicht gewertet; nur zur Information.", hinw, urteil=UNBEK)
    k = z["konsequenz"][{STIMMT: "stimmt", OPT: "zu_optimistisch", PESS: "zu_pessimistisch"}[u]]
    if fehlende:
        hinw.append("Abweichende Plätze: " + "; ".join(fehlende[:30]) + (" ..." if len(fehlende) > 30 else ""))
    return zeile(kat, 4, teile, k, hinw)


def z05(kat, m, basis) -> Dict[str, Any]:
    z = kat["_zeilen"][5]
    P = z["parameter"]
    teile, hinw = [], []
    for klasse in ("glas", "teller"):
        e = (m or {}).get(klasse)
        if not e:
            continue
        werte = _liste(e.get("abdeckung_pct"))
        for o in e.get("objekte") or []:
            w = lade_wolke(_pfad(basis, o["aufnahme"]))
            mk = None
            if o.get("maske"):
                mk = np.load(_pfad(basis, o["maske"]))["maske"]
            werte.append(abdeckung_pct(w, mk))
        if not werte:
            continue
        mw = float(np.mean(werte))
        lo, hi = P[klasse]["fenster"]
        u = urteil_intervall(mw, lo, hi, False)
        h = f"{len(werte)} Objekte"
        if len(werte) < P["min_objekte"]:
            h += f" (weniger als {P['min_objekte']}: Urteil schwach)"
        teile.append(teil(f"{klasse}_mittel", f"{klasse}: mittlere Punktabdeckung", round(mw, 1), P[klasse]["mittel"], u, h, "%"))
    if not teile:
        return nicht_gemessen(kat, 5)
    u = zusammen([t["urteil"] for t in teile])
    return zeile(kat, 5, teile, z["konsequenz"][{STIMMT: "stimmt", OPT: "zu_optimistisch", PESS: "zu_pessimistisch"}[u]],
                 ["Glas nass wird nicht vorhergesagt: siehe u1 und u3."])


def z06(kat, m, basis) -> Dict[str, Any]:
    z = kat["_zeilen"][6]
    R = z["parameter"]["raten"]
    teile, hinw = [], []
    for schl, e in (m or {}).items():
        if schl not in R:
            hinw.append(f"Rate '{schl}' ist nicht im Katalog")
            continue
        k, n = float(e["k"]), float(e["n"])
        lo, hi = wilson(k, n)
        p = R[schl]["p"]
        if lo <= p <= hi:
            u = STIMMT
        elif hi < p:
            u = OPT if R[schl]["besser"] == "hoeher" else PESS
        else:
            u = PESS if R[schl]["besser"] == "hoeher" else OPT
        h = f"k/n = {int(k)}/{int(n)} = {100 * k / n:.0f} %, Wilson 95 %: {100 * lo:.0f} bis {100 * hi:.0f} %"
        if n < 30:
            h += "; n < 30, Intervall breit"
        teile.append(teil(schl, schl.replace("_", " "), round(k / n, 3), p, u, h, "Anteil"))
    if not teile:
        return nicht_gemessen(kat, 6)
    u = zusammen([t["urteil"] for t in teile])
    return zeile(kat, 6, teile, z["konsequenz"][{STIMMT: "stimmt", OPT: "zu_optimistisch", PESS: "zu_pessimistisch"}[u]], hinw)


def _fehler_liste(e) -> List[float]:
    if e.get("fehler_mm") is not None:
        return _liste(e["fehler_mm"])
    s, r = np.asarray(e["geschaetzt_mm"], float), np.asarray(e["referenz_mm"], float)
    if s.shape != r.shape:
        raise ValueError("geschaetzt_mm und referenz_mm müssen gleich lang sein")
    return [float(v) for v in np.linalg.norm(s - r, axis=-1)]


def z07(kat, m, basis) -> Dict[str, Any]:
    z = kat["_zeilen"][7]
    P = z["parameter"]
    teile = []
    for klasse in ("glas", "teller"):
        e = (m or {}).get(klasse)
        if not e:
            continue
        f = _fehler_liste(e)
        med, p90 = float(np.median(f)), float(np.percentile(f, 90))
        u = urteil_intervall(med, P["faktor_tief"] * P[klasse]["median"], P["schwelle_mm"], True)
        teile.append(teil(f"{klasse}_median", f"{klasse}: Median des Lagefehlers", round(med, 2), P[klasse]["median"], u,
                          f"P90 {p90:.2f} mm (Modell {P[klasse]['p90']}), n = {len(f)}", "mm"))
    if not teile:
        return nicht_gemessen(kat, 7)
    u = zusammen([t["urteil"] for t in teile])
    return zeile(kat, 7, teile, z["konsequenz"][{STIMMT: "stimmt", OPT: "zu_optimistisch", PESS: "zu_pessimistisch"}[u]],
                 ["Das Modell gilt für wahre Maske; mit erkannter Maske sind nur 14 % (Glas) bzw. 3 % (Teller) freigegeben."])


def z08(kat, m, basis) -> Dict[str, Any]:
    z = kat["_zeilen"][8]
    P = z["parameter"]
    teile, hinw = [], []
    pk = (m or {}).get("punkt")
    if pk:
        wolken = [lade_wolke(_pfad(basis, a)) for a in pk["aufnahmen"]]
        s = punkt_streuung(wolken, pk.get("roi_px"))
        soll = P["punkt_k_mm_pro_m2"] * s["z_m"] ** 2
        faktor = s["sigma_median_mm"] / soll
        u = urteil_intervall(faktor, P["faktor_tief"], P["faktor_hoch"], True)
        teile.append(teil("punkt_sigma", f"Streuung je Punkt über {s['aufnahmen']} Aufnahmen bei z = {s['z_m']:.3f} m",
                          round(s["sigma_median_mm"], 4), round(soll, 4), u, f"Faktor {faktor:.2f}, {s['pixel']} Pixel", "mm"))
    for klasse in ("glas", "teller"):
        pose = ((m or {}).get("pose") or {}).get(klasse)
        if pose is None:
            continue
        a = np.asarray(pose, float)
        if len(a) < 5:
            hinw.append(f"{klasse}: weniger als 5 Posen")
        sd = a.std(axis=0, ddof=1)
        betrag = float(np.linalg.norm(sd[:2]))
        u = urteil_intervall(betrag / P["pose_streuung_mm"][klasse], P["faktor_tief"], P["faktor_hoch"], True)
        teile.append(teil(f"pose_{klasse}", f"{klasse}: Streuung der Schätzpose (x, y)", round(betrag, 3), P["pose_streuung_mm"][klasse], u,
                          f"x {sd[0]:.2f} / y {sd[1]:.2f} mm über {len(a)} Aufnahmen", "mm"))
    g = ((m or {}).get("pose") or {}).get("teller_gier_grad")
    if g is not None and len(g) > 2:
        sg = float(np.std(np.asarray(g, float), ddof=1))
        u = urteil_intervall(sg / P["gier_streuung_grad"], P["faktor_tief"], P["faktor_hoch"], True)
        teile.append(teil("pose_gier", "Teller: Streuung der Gier", round(sg, 3), P["gier_streuung_grad"], u, f"n = {len(g)}", "Grad"))
    if not teile:
        return nicht_gemessen(kat, 8)
    u = zusammen([t["urteil"] for t in teile])
    hinw.append("Modellstreuung enthält den je Aufnahme neu gezogenen Kalibrierfehler: obere Schranke, erwartet zu_pessimistisch.")
    return zeile(kat, 8, teile, z["konsequenz"][{STIMMT: "stimmt", OPT: "zu_optimistisch", PESS: "zu_pessimistisch"}[u]], hinw)


def z09(kat, m, basis) -> Dict[str, Any]:
    z = kat["_zeilen"][9]
    P = z["parameter"]
    teile, ks = [], []
    g = _maxabs((m or {}).get("gier_grad"))
    l = _maxabs((m or {}).get("lage_mm"))
    if g is None and l is None:
        return nicht_gemessen(kat, 9)
    if g is not None:
        if g > P["gier"]["schwelle_grad"]:
            u = OPT
        elif g <= P["gier"]["aufloesung_grad"] and (l is None or l <= P["lage_xy"]["prior_mm"] / 2):
            u = PESS
        else:
            u = STIMMT
        teile.append(teil("gier_max", "größter Betrag der Teller-Gier", round(g, 2), P["gier"]["prior_grad"], u,
                          f"Schwelle {P['gier']['schwelle_grad']} Grad; n = {len(_liste(m['gier_grad']))}", "Grad"))
        if u == OPT:
            ks.append(stufe(z["konsequenz"]["zu_optimistisch"], g))
        elif u == PESS:
            ks.append(z["konsequenz"]["zu_pessimistisch"])
    if l is not None:
        u = OPT if l > P["lage_xy"]["prior_mm"] else STIMMT
        teile.append(teil("lage_max", "größte Lageabweichung x/y", round(l, 2), P["lage_xy"]["prior_mm"], u,
                          f"n = {len(_liste(m['lage_mm']))}", "mm"))
        if u == OPT:
            ks.append(stufe(z["konsequenz_lage"], l))
    if not ks:
        ks = [z["konsequenz"]["stimmt"]]
    return zeile(kat, 9, teile, " ".join(ks))


def z10(kat, m, basis) -> Dict[str, Any]:
    z = kat["_zeilen"][10]
    P = z["parameter"]
    l = _maxabs((m or {}).get("lage_mm"))
    nk = _maxabs((m or {}).get("neigung_grad"))
    if l is None and nk is None:
        return nicht_gemessen(kat, 10)
    teile, ks = [], []
    if l is not None:
        u = OPT if l > P["lage_mm"]["schwelle"] else STIMMT
        teile.append(teil("lage_max", "größte Abweichung der Glasmitte", round(l, 2), P["lage_mm"]["prior"], u,
                          f"Schwelle {P['lage_mm']['schwelle']} mm", "mm"))
        if u == OPT:
            ks.append(stufe(z["konsequenz"]["zu_optimistisch"], l))
    if nk is not None:
        u = OPT if nk > P["neigung_grad"]["prior"] else STIMMT
        teile.append(teil("neigung_max", "größte Neigung des Glases", round(nk, 2), P["neigung_grad"]["prior"], u, "", "Grad"))
        if u == OPT:
            ks.append("Neigung über dem Prior: Prior-Neigung auf den gemessenen Wert weiten; Greifer-Anfahrt auf die Neigung prüfen.")
    alle_klein = (l is None or l <= P["lage_mm"]["unter"]) and (nk is None or nk <= P["neigung_grad"]["unter"])
    if all(t["urteil"] == STIMMT for t in teile) and alle_klein:
        for t in teile:
            t["urteil"] = PESS
        ks = [z["konsequenz"]["zu_pessimistisch"]]
    if not ks:
        ks = [z["konsequenz"]["stimmt"]]
    return zeile(kat, 10, teile, " ".join(ks))


def z11(kat, m, basis) -> Dict[str, Any]:
    z = kat["_zeilen"][11]
    P = z["parameter"]
    d = _liste((m or {}).get("dicke_mm"))
    pose = (m or {}).get("pose")
    if not d and not pose:
        return nicht_gemessen(kat, 11)
    teile, hinw, k = [], [], None
    if d:
        mx, mn = max(d), min(d)
        if mx > P["dicke_mm"]["baut_bis"]:
            u = OPT
        elif mx < P["dicke_mm"]["spanne_min"]:
            u = PESS
        else:
            u = STIMMT
        h = f"n = {len(d)}, Mittel {sum(d) / len(d):.2f} mm, kleinste {mn:.2f} mm"
        if P["dicke_mm"]["baut_bis"] < mx < P["dicke_mm"]["grenze_ab"]:
            h += "; Grenzbereich 6 bis 8 mm"
        teile.append(teil("dicke_max", "größte Randdicke", round(mx, 2), P["dicke_mm"]["plan"], u, h, "mm"))
        k = z["konsequenz"]["stimmt"] if u == STIMMT else (stufe(z["konsequenz"]["zu_optimistisch"], mx) if u == OPT else z["konsequenz"]["zu_pessimistisch"])
    if pose:
        kk, n = float(pose["k"]), float(pose["n"])
        lo, hi = wilson(kk, n)
        p = P["pose_ausbeute"]["p"]
        u = STIMMT if lo <= p <= hi else (OPT if hi < p else PESS)
        teile.append(teil("pose_ausbeute", "Teller-Pose aus der Ensenso gelungen", round(kk / n, 3), round(p, 3), u,
                          f"k/n = {int(kk)}/{int(n)}, Wilson 95 %: {100 * lo:.0f} bis {100 * hi:.0f} %", "Anteil"))
        hinw.append("Die Modell-Ausbeute 96/131 gilt für die Bestandsposition und wahre Maske; die Richtung ist übertragbar, die Höhe nicht.")
        if k is None:
            k = z["konsequenz"]["stimmt"] if u == STIMMT else (z["konsequenz"]["zu_optimistisch"][1]["text"] if u == OPT else z["konsequenz"]["zu_pessimistisch"])
    u_all = zusammen([t["urteil"] for t in teile])
    if u_all == OPT and k == z["konsequenz"]["stimmt"]:
        k = z["konsequenz"]["zu_optimistisch"][0]["text"]
    return zeile(kat, 11, teile, k, hinw)


def z12(kat, m, basis) -> Dict[str, Any]:
    z = kat["_zeilen"][12]
    P = z["parameter"]
    if not m:
        return nicht_gemessen(kat, 12)
    hinw = []
    if "station" in m:
        kb = kabsch(m["station"], m["referenz"])
        v, dr = kb["versatz_mm"], kb["dreh_grad"]
        hinw.append(f"aus {kb['n']} Punktpaaren (Kabsch); Rest-RMS nach Anpassung {kb['rest_rms_mm']:.2f} mm")
    else:
        v, dr = float(m["versatz_mm"]), float(m["dreh_grad"])
    PV, PD = P["versatz_mm"], P["dreh_grad"]
    if v > PV["plan"] or dr > PD["plan"]:
        u = OPT
    elif v < PV["unter"] and dr < PD["unter"]:
        u = PESS
    else:
        u = STIMMT
    teile = [teil("versatz", "Versatz der Station (nach Kalibrierung)", round(v, 2), PV["plan"],
                  OPT if v > PV["plan"] else STIMMT, f"Kette K trägt bis {PV['k_traegt_bis']} mm", "mm"),
             teil("drehung", "Drehung der Station (nach Kalibrierung)", round(dr, 2), PD["plan"],
                  OPT if dr > PD["plan"] else STIMMT, f"Kette K und A tragen bis 5 Grad, ab {PD['k_tot_ab']:.0f} Grad nicht", "Grad")]
    if u == PESS:
        teile[0]["urteil"] = teile[1]["urteil"] = PESS
    if u == OPT:
        k = stufe(z["konsequenz"]["zu_optimistisch"], max(v, 0.75 * dr))            # 10 Grad entspricht 7,5 mm, 20 Grad 15 mm
    elif u == PESS:
        k = z["konsequenz"]["zu_pessimistisch"]
    else:
        k = z["konsequenz"]["stimmt"]
    return zeile(kat, 12, teile, k, hinw)


def z13(kat, m, basis) -> Dict[str, Any]:
    z = kat["_zeilen"][13]
    P = z["parameter"]["grenze_grad"]
    s = _maxabs((m or {}).get("spiel_grad"))
    if s is None:
        return nicht_gemessen(kat, 13)
    if s <= P["ok"]:
        k, klasse = z["konsequenz"]["stimmt"], "Spiel <= 3 Grad"
    elif s <= P["fehlgriff"]:
        k, klasse = z["konsequenz"]["zu_optimistisch"][0]["text"], "Spiel 3 bis 7 Grad"
    else:
        k, klasse = z["konsequenz"]["zu_optimistisch"][1]["text"], "Spiel über 7 Grad"
    t = teil("spiel_max", "größtes mechanisches Spiel (Gier) im Ständer", round(s, 2), "Grenze zwischen 3 und 7", UNBEK, klasse, "Grad")
    return zeile(kat, 13, [t], k, ["Die Grenze selbst misst der Kameratag nicht (kein Greifversuch); eingeordnet wird nur das Spiel."], urteil=UNBEK)


def _unbekannt(kat, uid, wert: Optional[float], einheit: str, extra: Optional[List[str]] = None) -> Dict[str, Any]:
    u = kat["_unbekannt"][uid]
    if wert is None:
        return nicht_gemessen(kat, uid)
    klasse = next(c for c in u["klassen"] if wert <= float(c["bis"]))
    t = teil(u["klassen_gruppe"], u["messgroesse"], round(wert, 2), "keine Vorhersage", UNBEK, f"Ausgang {klasse['name']}", einheit)
    return {"id": uid, "name": u["name"], "einheit": einheit, "urteil": UNBEK, "ausgang": klasse["name"], "teile": [t],
            "konsequenz": klasse["text"], "hinweise": [u["begruendung"]] + (extra or [])}


def u1(kat, m, basis):
    if not m:
        return nicht_gemessen(kat, "u1")
    if "delta_erkennung_pp" in m:
        d = float(m["delta_erkennung_pp"])
    else:
        d = 100.0 * (float(m["erkennung_nass"]["k"]) / float(m["erkennung_nass"]["n"]) - float(m["erkennung_trocken"]["k"]) / float(m["erkennung_trocken"]["n"]))
    return _unbekannt(kat, "u1", d, "Prozentpunkte")


def u2(kat, m, basis):
    if not m:
        return nicht_gemessen(kat, "u2")
    if "ausreisser_pct" in m:
        a = float(m["ausreisser_pct"])
    else:                                                          # aus einer Aufnahme der ebenen Fläche im Korb
        pts = roi_punkte(lade_wolke(_pfad(basis, m["aufnahme"])), m.get("roi_px"), m.get("roi_mm"))
        f = ebene_fit(pts, trimmen=False)
        # robuste Ebene: Median der Normalabstände nach einem Fit auf die zentralen 80 %
        r = np.abs((pts - f["schwerpunkt"]) @ f["normale"])
        kern = pts[r <= np.percentile(r, 80)]
        f = ebene_fit(kern, trimmen=False)
        r = np.abs((pts - f["schwerpunkt"]) @ f["normale"])
        a = 100.0 * float((r > m.get("schwelle_mm", 10.0)).mean())
    return _unbekannt(kat, "u2", a, "%")


def u3(kat, m, basis):
    if not m:
        return nicht_gemessen(kat, "u3")
    werte = _liste(m.get("abdeckung_glas_pct"))
    for o in m.get("objekte") or []:
        mk = np.load(_pfad(basis, o["maske"]))["maske"] if o.get("maske") else None
        werte.append(abdeckung_pct(lade_wolke(_pfad(basis, o["aufnahme"])), mk))
    if not werte:
        return nicht_gemessen(kat, "u3")
    ex = [f"{len(werte)} Gläser" + (" (weniger als 8: schwach)" if len(werte) < 8 else "")]
    return _unbekannt(kat, "u3", float(np.mean(werte)), "%", ex)


HANDLER = [(1, z01), (2, z02), (3, z03), (4, z04), (5, z05), (6, z06), (7, z07), (8, z08), (9, z09), (10, z10),
           (11, z11), (12, z12), (13, z13)]
UNBEKANNT_HANDLER = [("u1", u1), ("u2", u2), ("u3", u3)]


# --------------------------------------------------------------------------------------------------
# Gesamtauswertung und Ausgabe
# --------------------------------------------------------------------------------------------------

def auswerten(kat: Dict[str, Any], mess: Dict[str, Any], basis: Path) -> Dict[str, Any]:
    ms = mess.get("messungen") or {}
    erg, fehler = [], []
    for zid, h in HANDLER + UNBEKANNT_HANDLER:
        key = f"z{zid:02d}" if isinstance(zid, int) else zid
        try:
            r = h(kat, ms.get(key), basis) if ms.get(key) else nicht_gemessen(kat, zid)
        except Exception as e:                                    # eine kaputte Zeile darf den Rest nicht verhindern
            r = nicht_gemessen(kat, zid)
            r["konsequenz"] = f"FEHLER bei der Auswertung: {type(e).__name__}: {e}"
            r["urteil"] = "fehler"
            fehler.append(key)
        erg.append(r)
    zaehl = {}
    for r in erg:
        zaehl[r["urteil"]] = zaehl.get(r["urteil"], 0) + 1
    return {"katalog_version": kat.get("katalog_version"), "katalog_stand": kat.get("stand"), "kopf": mess.get("kopf") or {},
            "zeilen": erg, "zaehlung": zaehl, "fehler": fehler}


def _fmt(v) -> str:
    return "-" if v is None else str(v)


def bericht(erg: Dict[str, Any]) -> str:
    k = erg["kopf"]
    L = ["# Kameratag: Ergebnis gegen den Vorhersagekatalog", "",
         f"Katalog Version {erg['katalog_version']} (Stand {erg['katalog_stand']}); Datum der Messung: {_fmt(k.get('datum'))}; Mastposition: {_fmt(k.get('mast'))}.", ""]
    z = erg["zaehlung"]
    L.append("Zählung: " + ", ".join(f"{u} {n}" for u, n in sorted(z.items())) + ".")
    L += ["", "| Zeile | Größe | Urteil |", "|---|---|---|"]
    for r in erg["zeilen"]:
        extra = f" (Ausgang {r['ausgang']})" if r.get("ausgang") else ""
        L.append(f"| {r['id']} | {r['name']} | {r['urteil']}{extra} |")
    for r in erg["zeilen"]:
        L += ["", f"## Zeile {r['id']}: {r['name']} - {r['urteil']}"]
        if r["teile"]:
            L += ["", "| Größe | gemessen | Modell | Urteil | Hinweis |", "|---|---:|---:|---|---|"]
            for t in r["teile"]:
                L.append(f"| {t['text']} | {_fmt(t['gemessen'])} {t['einheit']} | {_fmt(t['vorhersage'])} | {t['urteil']} | {t['hinweis']} |")
        L += ["", f"Konsequenz: {r['konsequenz']}"]
        for h in r["hinweise"]:
            L.append(f"\nHinweis: {h}")
    L += ["", "Urteil 'zu_optimistisch': die Wirklichkeit ist schlechter als das Modell sagt; 'zu_pessimistisch': besser; 'unbekannt': keine Vorhersage, nur Einordnung."]
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------------------------------
# Synthetische Aufnahmen (Demo/Tests, ohne Kamera)
# --------------------------------------------------------------------------------------------------

def synth_ebene(z_mm: float, sigma_mm: float, hw=(120, 160), rng=None, pitch_mm: float = 0.4,
                kippung_grad: float = 0.0) -> np.ndarray:
    """Organisierte Punktwolke (H, W, 3) einer Ebene bei z_mm mit Rauschen entlang z; Pixelabstand pitch_mm."""
    rng = rng or np.random.default_rng(0)
    h, w = hw
    u = (np.arange(w) - w / 2) * pitch_mm
    v = (np.arange(h) - h / 2) * pitch_mm
    X, Y = np.meshgrid(u, v)
    Z = z_mm + np.tan(math.radians(kippung_grad)) * X + rng.normal(0.0, sigma_mm, X.shape)
    return np.stack([X, Y, Z], axis=-1).astype(np.float32)


def synth_objekt(deckung: float, hw=(120, 160), z_mm: float = 900.0, rng=None):
    """Wolke mit rechteckiger Objektmaske, in der ein Anteil ``deckung`` der Pixel gültig ist."""
    rng = rng or np.random.default_rng(1)
    xyz = synth_ebene(z_mm, 0.2, hw, rng)
    maske = np.zeros(hw, bool)
    maske[30:90, 40:120] = True
    zufall = rng.random(hw) >= deckung
    xyz[maske & zufall] = np.nan
    return xyz, maske


def demo_schreiben(ordner) -> List[Path]:
    """Schreibt die in beispiele/kameratag-messung-beispiel.yaml genannten synthetischen Aufnahmen."""
    o = Path(ordner)
    rng = np.random.default_rng(42)
    geschrieben = []

    def ablegen(rel, **arrays):
        p = o / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(p, **arrays)
        geschrieben.append(p)

    ablegen("kameratag/beispiel/m6_rauschen/001_ensenso.npz", xyz=synth_ebene(1000.0, 0.23, rng=rng))
    ablegen("kameratag/beispiel/m6_rauschen/002_ensenso.npz", xyz=synth_ebene(820.0, 0.34, rng=rng))
    for i in range(1, 21):
        ablegen(f"kameratag/beispiel/m6_wiederholung/{i:03d}_ensenso.npz", xyz=synth_ebene(1000.0, 0.21, rng=np.random.default_rng(100 + i)))
    for i, d in enumerate((0.34, 0.30, 0.36, 0.33), 1):
        xyz, mk = synth_objekt(d, rng=np.random.default_rng(200 + i))
        ablegen(f"kameratag/beispiel/m3_erkennung/glas_{i:03d}_ensenso.npz", xyz=xyz, maske=mk)
    for i, d in enumerate((0.20, 0.25, 0.18, 0.30, 0.22, 0.27, 0.19, 0.31), 1):
        xyz, mk = synth_objekt(d, rng=np.random.default_rng(300 + i), z_mm=1000.0)
        ablegen(f"kameratag/beispiel/m3_erkennung/teller_{i:03d}_ensenso.npz", xyz=xyz, maske=mk)
    return geschrieben


# --------------------------------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("messdatei", nargs="?", help="YAML-Messdatei")
    ap.add_argument("--katalog", default=str(KATALOG_STANDARD))
    ap.add_argument("--basis", help="Ordner, relativ zu dem die Aufnahmen stehen (Standard: Ordner der Messdatei)")
    ap.add_argument("--out", help="Ausgabeordner (Standard: Ordner der Messdatei)")
    ap.add_argument("--demo", metavar="ORDNER", help="synthetische Aufnahmen für das Beispiel schreiben und beenden")
    a = ap.parse_args(argv)
    if a.demo:
        p = demo_schreiben(a.demo)
        print(f"{len(p)} synthetische Aufnahmen unter {a.demo}")
        return 0
    if not a.messdatei:
        ap.error("Messdatei fehlt")
    mf = Path(a.messdatei)
    kat = lade_katalog(a.katalog)
    mess = lade_yaml(mf)
    basis = Path(a.basis) if a.basis else mf.resolve().parent
    out = Path(a.out) if a.out else mf.resolve().parent
    out.mkdir(parents=True, exist_ok=True)
    erg = auswerten(kat, mess, basis)
    (out / "kameratag_ergebnis.json").write_text(json.dumps(erg, indent=1, ensure_ascii=False, default=float), encoding="utf-8")
    (out / "kameratag_ergebnis.md").write_text(bericht(erg), encoding="utf-8")
    print("Zählung:", erg["zaehlung"], "| Fehler:", erg["fehler"] or "keine", "|", out / "kameratag_ergebnis.md")
    return 1 if erg["fehler"] else 0


if __name__ == "__main__":
    sys.exit(main())
