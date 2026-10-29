#!/usr/bin/env python3
"""Kodiert die PNG-Bilder von scripts/isaac_render.py zu einem MP4 (H.264).

    isaac_render_video.py BILDORDNER --auftrag auftrag.npz --out video.mp4 [--ohne-text]

libx264, yuv420p, ``+faststart``, Bildrate aus dem Auftrag (spielt auf
iPhone/iPad). Mit Pillow wird eine schmale Einblendung gezeichnet: Titel,
Ablaufphase, Simzeit, unten rechts "Isaac Sim RTX · Physik: Newton" und am Ende
das Ergebnis der Bewertung. Braucht numpy, ffmpeg im PATH, optional Pillow.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PHASE_TEXT = {"start": "Anfahrt", "vorposition": "Anfahrt", "anfahrt": "Anfahrt", "greifen": "Greifen",
              "anheben": "Heben", "verfahren": "Verfahren", "absetzen": "Absetzen", "loesen": "Absetzen",
              "rueckzug": "Rückzug", "nachlauf": "Rückzug", "ende": "Rückzug"}
# Ausraeumen: Phase "<glas>:<schritt>"
SCHRITT = {"anfahrt_korb": "Anfahrt Korb", "runter_korb": "Anfahrt Korb", "greifen_korb": "Greifen (von oben)",
           "aushub": "Aus dem Halter heben", "zur_zwischenablage": "Zur Zwischenablage",
           "absetzen_zw": "Kopfüber absetzen", "loesen_zw": "Loslassen", "hoch_zw": "Umgreifen",
           "anfahrt_seite": "Umgreifen", "zu_seite": "Umgreifen", "greifen_seite": "Greifen (seitlich)",
           "anheben": "Anheben", "umdrehen": "Umdrehen", "zur_ablage": "Zur Ablage",
           "absetzen": "Aufrecht absetzen", "loesen": "Loslassen", "rueckzug": "Rückzug"}


def phase_text(ph: str, n_glas: int = 0) -> str:
    if ":" in ph:
        k, s = ph.split(":", 1)
        return f"Glas {k}/{n_glas} · {SCHRITT.get(s, s)}" if n_glas else f"Glas {k} · {SCHRITT.get(s, s)}"
    return "Phase: " + {"start": "Start", "heim": "Zurück in die Ruhepose", "hoch_heim": "Zurück in die Ruhepose"}.get(
        ph, PHASE_TEXT.get(ph, ph))


def ffmpeg_befehl(ffmpeg: str, breite: int, hoehe: int, fps: float, crf: int, out) -> list:
    return [ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{breite}x{hoehe}",
            "-r", f"{fps:g}", "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", str(crf),
            "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.1", "-movflags", "+faststart", str(out)]


def _schrift(groesse: int):
    from PIL import ImageFont
    for name in ("DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, groesse)
        except OSError:
            continue
    return ImageFont.load_default()


def einblenden(img, titel: str, zeile: str, rechts: str, unten: str, ergebnis: str = ""):
    """Text auf ein RGB-Bild (PIL.Image) zeichnen, halbtransparente Leisten."""
    from PIL import Image, ImageDraw
    b, h = img.size
    s = max(12, h // 32)
    over = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    d.rectangle([0, 0, b, int(s * 2.9)], fill=(15, 18, 22, 150))
    d.text((s, int(s * 0.35)), titel, font=_schrift(s), fill=(255, 255, 255, 255))
    d.text((s, int(s * 1.55)), zeile, font=_schrift(int(s * 0.85)), fill=(255, 180, 90, 255))
    if rechts:
        w = d.textlength(rechts, font=_schrift(int(s * 0.8)))
        d.text((b - s - w, int(s * 0.4)), rechts, font=_schrift(int(s * 0.8)), fill=(220, 225, 230, 255))
    if unten:
        f = _schrift(int(s * 0.6))
        w = d.textlength(unten, font=f)
        d.rectangle([b - w - 1.6 * s, h - 1.5 * s, b, h], fill=(15, 18, 22, 120))
        d.text((b - w - 0.8 * s, h - 1.2 * s), unten, font=f, fill=(230, 232, 235, 255))
    if ergebnis:
        f = _schrift(int(s * 0.95))
        w = d.textlength(ergebnis, font=f)
        x0, y0 = (b - w) / 2 - s, h * 0.80
        d.rounded_rectangle([x0, y0, x0 + w + 2 * s, y0 + 2 * s], radius=s // 2, fill=(255, 255, 255, 225),
                            outline=(29, 154, 75, 255), width=max(2, s // 8))
        d.text((x0 + s, y0 + 0.45 * s), ergebnis, font=f, fill=(25, 30, 35, 255))
    return Image.alpha_composite(img.convert("RGBA"), over).convert("RGB")


def kodieren(ordner: Path, auf: dict, out: Path, crf: int = 18, text: bool = True) -> dict:
    import numpy as np
    from PIL import Image
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg fehlt im PATH")
    dateien = sorted(ordner.glob("bild_*.png"))
    if not dateien:
        raise RuntimeError(f"keine bild_*.png in {ordner}")
    nummern = [int(p.stem.split("_")[1]) for p in dateien]
    if nummern != list(range(nummern[0], nummern[0] + len(nummern))):
        raise RuntimeError("Bildfolge hat Luecken")
    b, h = Image.open(dateien[0]).size
    if b % 2 or h % 2:
        raise RuntimeError("Breite/Hoehe muessen gerade sein (yuv420p)")
    out.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(ffmpeg_befehl(ffmpeg, b, h, float(auf["fps"]), crf, out), stdin=subprocess.PIPE)
    try:
        for k, p in zip(nummern, dateien):
            img = Image.open(p).convert("RGB")
            if img.size != (b, h):
                raise RuntimeError(f"{p.name}: Groesse {img.size}")
            if text:
                ph = auf["phase"][min(k, len(auf["phase"]) - 1)]
                t = float(auf["simzeit"][min(k, len(auf["simzeit"]) - 1)])
                erg = auf.get("ergebnis", "") if k >= int(auf.get("ergebnis_ab_bild", 10 ** 9)) else ""
                img = einblenden(img, auf.get("titel", ""), phase_text(ph, len(auf.get("glaeser", {})) if
                                                                       len(auf.get("glaeser", {})) > 1 else 0),
                                 f"Simzeit {t:4.1f} s", "Isaac Sim 6.2 RTX · Physik: Newton 1.6", erg)
            proc.stdin.write(np.asarray(img, np.uint8).tobytes())
    finally:
        proc.stdin.close()
        rc = proc.wait()
    if rc != 0:
        raise RuntimeError(f"ffmpeg rc={rc}")
    return {"bilder": len(dateien), "groesse_bytes": out.stat().st_size, "aufloesung": [b, h]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("ordner")
    ap.add_argument("--auftrag", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--crf", type=int, default=18)
    ap.add_argument("--ohne-text", action="store_true")
    a = ap.parse_args(argv)
    from isaac_render.auftrag import laden
    info = kodieren(Path(a.ordner), laden(a.auftrag), Path(a.out), a.crf, not a.ohne_text)
    print("VIDEO", a.out, info)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
