"""Geometrie-Helfer fuer das RTX-Rendering (nur numpy).

* ``glas_mesh``: Trinkglas als geschlossener Rotationskoerper mit Wand und
  Boden (RTX-Glas bricht Licht nur an Koerpern mit Dicke richtig).
* ``scheibe``: flache Kreisscheibe (Start-/Zielmarke).
* ``normalen``: Normalen je Dreiecksecke mit Knickwinkel (CAD-Meshes: glatte
  Gehaeuse, scharfe Kanten bleiben scharf).
* ``verschweissen``: doppelte Ecken einer Dreieckssuppe zusammenfassen.
* ``arm_teil``: ReBeL-Mesh eines Glieds aufbereiten: orange Ringe an den
  Gelenkfugen (gleiche Lage wie im matplotlib-Video, ``scripts/render_video.py``),
  verschweissen, Normalen.
* ``pose_matrix``/``blick_matrix``: 4x4-Matrizen (Spaltenkonvention, x' = M x).
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]


# --- Matrizen -----------------------------------------------------------------

def quat_matrix(q) -> np.ndarray:
    """Rotationsmatrix aus Quaternion (x, y, z, w)."""
    x, y, z, w = (float(c) for c in q)
    n = math.sqrt(x * x + y * y + z * z + w * w) or 1.0
    x, y, z, w = x / n, y / n, z / n, w / n
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def matrix_quat(r) -> np.ndarray:
    """Quaternion (x, y, z, w) aus Rotationsmatrix (w >= 0)."""
    r = np.asarray(r, float)
    t = np.trace(r)
    if t > 0:
        s = math.sqrt(t + 1.0) * 2
        q = [(r[2, 1] - r[1, 2]) / s, (r[0, 2] - r[2, 0]) / s, (r[1, 0] - r[0, 1]) / s, 0.25 * s]
    else:
        i = int(np.argmax(np.diag(r)))
        j, k = (i + 1) % 3, (i + 2) % 3
        s = math.sqrt(1.0 + r[i, i] - r[j, j] - r[k, k]) * 2
        q = [0.0, 0.0, 0.0, (r[k, j] - r[j, k]) / s]
        q[i] = 0.25 * s
        q[j] = (r[j, i] + r[i, j]) / s
        q[k] = (r[k, i] + r[i, k]) / s
    q = np.array(q, float)
    q /= np.linalg.norm(q)
    return -q if q[3] < 0 else q


def pose_matrix(q7) -> np.ndarray:
    """4x4 aus (x, y, z, qx, qy, qz, qw)."""
    m = np.eye(4)
    m[:3, :3] = quat_matrix(q7[3:7])
    m[:3, 3] = np.asarray(q7[:3], float)
    return m


def blick_matrix(auge, ziel, oben=(0.0, 0.0, 1.0)) -> np.ndarray:
    """Kamera-zu-Welt (4x4) fuer eine USD-Kamera (blickt entlang -z, +y oben)."""
    auge, ziel, oben = (np.asarray(a, float) for a in (auge, ziel, oben))
    vor = ziel - auge
    vor /= np.linalg.norm(vor)
    if abs(float(vor @ oben)) > 0.99:
        oben = np.array([0.0, 1.0, 0.0])
    rechts = np.cross(vor, oben)
    rechts /= np.linalg.norm(rechts)
    hoch = np.cross(rechts, vor)
    m = np.eye(4)
    m[:3, 0], m[:3, 1], m[:3, 2], m[:3, 3] = rechts, hoch, -vor, auge
    return m


# --- Meshes -------------------------------------------------------------------

def rotationskoerper(profil, n: int = 48):
    """Profil [(r, z), ...] um die z-Achse drehen. Punkte mit r = 0 werden Pole.

    Liefert Ecken (k, 3) und Dreiecke (m, 3); bei einem Profil, das gegen den
    Uhrzeigersinn um das Material laeuft (aussen hoch, innen runter), zeigen
    die Normalen nach aussen.
    """
    a = np.linspace(0.0, 2 * math.pi, n, endpoint=False)
    ca, sa = np.cos(a), np.sin(a)
    v, idx = [], []
    for r, z in profil:
        if r <= 1e-12:
            idx.append([len(v)] * n)
            v.append((0.0, 0.0, z))
        else:
            idx.append(list(range(len(v), len(v) + n)))
            v += [(r * ca[i], r * sa[i], z) for i in range(n)]
    f = []
    for p in range(len(profil) - 1):
        u, o = idx[p], idx[p + 1]
        for i in range(n):
            j = (i + 1) % n
            for tri in ((u[i], u[j], o[j]), (u[i], o[j], o[i])):
                if len(set(tri)) == 3:
                    f.append(tri)
    return np.array(v, float), np.array(f, int)


def glas_mesh(radius: float, hoehe: float, wand: float = 0.0025, boden: float = 0.008, n: int = 64):
    """Trinkglas, Mitte im Ursprung (z = -h/2 .. h/2), offen oben, mit Wand und Boden."""
    h2 = hoehe / 2.0
    ri = radius - wand
    profil = [(0.0, -h2), (radius * 0.97, -h2), (radius, -h2 + 0.002), (radius, h2),
              (ri, h2), (ri, -h2 + boden), (0.0, -h2 + boden)]
    return rotationskoerper(profil, n)


def teller_mesh(radius: float, rand_hoehe: float = None, wand: float = 0.004, n: int = 96):
    """Flacher Teller (Mulde), Achse z, Mulde zeigt nach +z, Mitte des Koerpers im Ursprung."""
    hr = rand_hoehe if rand_hoehe is not None else 0.11 * radius
    z0 = -hr / 2.0
    profil = [(0.0, z0), (0.62 * radius, z0), (0.97 * radius, z0 + hr), (radius, z0 + hr),
              (radius - wand, z0 + hr), (0.62 * radius, z0 + wand), (0.0, z0 + wand)]
    return rotationskoerper(profil, n)


def tropfen_mesh(zentren, normalen, radien, n: int = 10, flach: float = 0.55):
    """Viele Wassertropfen (abgeflachte Halbkugeln) als ein Mesh. ``zentren``/``normalen`` (k, 3), ``radien`` (k,)."""
    v_all, f_all = [], []
    prof = [(0.0, 0.0), (0.7, 0.0), (0.95, 0.25), (1.0, 0.5), (0.9, 0.8), (0.6, 1.0), (0.0, 1.1)]
    v0, f0 = rotationskoerper([(r, z * flach) for r, z in prof], n)
    for c, nz, a in zip(np.asarray(zentren, float), np.asarray(normalen, float), np.asarray(radien, float)):
        nz = nz / np.linalg.norm(nz)
        t = np.array([0.0, 0.0, 1.0]) if abs(nz[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
        x = np.cross(t, nz)
        x /= np.linalg.norm(x)
        y = np.cross(nz, x)
        R = np.column_stack([x, y, nz])
        v_all.append((v0 * a) @ R.T + c - nz * 0.0002)
        f_all.append(f0 + sum(len(v) for v in v_all[:-1]))
    return np.vstack(v_all), np.vstack(f_all)


def scheibe(radius: float, dicke: float = 0.001, n: int = 64):
    """Flache Kreisscheibe, Unterseite bei z = 0."""
    return rotationskoerper([(0.0, 0.0), (radius, 0.0), (radius, dicke), (0.0, dicke)], n)


def ring(r_innen: float, r_aussen: float, dicke: float = 0.0012, n: int = 64):
    """Flacher Kreisring (Marke), Unterseite bei z = 0."""
    return rotationskoerper([(r_innen, 0.0), (r_aussen, 0.0), (r_aussen, dicke), (r_innen, dicke),
                             (r_innen, 0.0)], n)


def volumen(v, f) -> float:
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)


def verschweissen(v, f, raster: float = 1e-7):
    """Gleiche Ecken (auf ``raster`` gerundet) zusammenfassen, entartete Dreiecke weg."""
    v = np.asarray(v, float)
    schluessel = np.round(v / raster).astype(np.int64)
    _, erst, inv = np.unique(schluessel, axis=0, return_index=True, return_inverse=True)
    inv = inv.reshape(-1)
    f2 = inv[np.asarray(f, int)]
    gut = (f2[:, 0] != f2[:, 1]) & (f2[:, 1] != f2[:, 2]) & (f2[:, 0] != f2[:, 2])
    return v[erst], f2, gut


def normalen(v, f, knick_grad: float = 35.0) -> np.ndarray:
    """Normalen je Dreiecksecke (3m, 3), flaechengewichtet ueber Nachbardreiecke
    derselben Ecke, deren Normale um hoechstens ``knick_grad`` abweicht."""
    v, f = np.asarray(v, float), np.asarray(f, int)
    n = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
    flaeche = np.linalg.norm(n, axis=1)
    einheit = n / np.maximum(flaeche, 1e-20)[:, None]
    m = len(f)
    ecke_v = f.reshape(-1)                      # Ecke c -> Vertex
    ecke_f = np.repeat(np.arange(m), 3)         # Ecke c -> Dreieck
    # Vertex -> Dreiecke (CSR)
    ordnung = np.argsort(ecke_v, kind="stable")
    anzahl = np.bincount(ecke_v, minlength=len(v))
    start = np.concatenate([[0], np.cumsum(anzahl)])
    nachbarn = ecke_f[ordnung]
    # jede Ecke gegen jedes Dreieck an ihrem Vertex
    val = anzahl[ecke_v]
    wdh = np.repeat(np.arange(3 * m), val)
    versatz = np.arange(len(wdh)) - np.repeat(np.cumsum(val) - val, val)
    g = nachbarn[start[ecke_v][wdh] + versatz]
    ok = np.einsum("ij,ij->i", einheit[ecke_f[wdh]], einheit[g]) >= math.cos(math.radians(knick_grad))
    summe = np.zeros((3 * m, 3))
    np.add.at(summe, wdh[ok], n[g[ok]])
    laenge = np.linalg.norm(summe, axis=1)
    leer = laenge < 1e-20
    summe[leer] = einheit[ecke_f[leer]]
    laenge[leer] = 1.0
    return summe / laenge[:, None]


# --- ReBeL-Glieder -------------------------------------------------------------

def ring_maske(name: str, p, cfg) -> np.ndarray:
    """Punkte (n, 3) im Linkframe, die auf einem orangen Ring an einer Gelenkfuge liegen.

    Gleiche Lage wie im matplotlib-Video (``scripts/render_video.py``: Band in y
    bzw. z am Gehaeuserand, Gehaeuseradius 52,5 mm am Arm, 40 mm an der Hand),
    aber zusaetzlich auf den Gehaeuseradius begrenzt: sonst faerbt das y-Band
    auch die Seitenflaeche des langen Glieds als Streifen.
    """
    from rebel_model.visual_mesh import CPR_J4_AB_J5, CPR_J4_MESH_UNTEN
    a = cfg.arm
    l1 = a["j2_hoehe_m"] - a["j1_hoehe_m"]
    l4 = a["unterarm_m"] - a["j4_ab_j3_m"]
    c = np.asarray(p, float)

    def band_y(y0, y1, z, r, r_max):
        d = np.hypot(c[:, 0], c[:, 2] - z)
        return (c[:, 1] >= y0) & (c[:, 1] <= y1) & (d > r) & (d < r_max)

    def band_z(z0, z1, r, r_max):
        d = np.hypot(c[:, 0], c[:, 1])
        return (c[:, 2] >= z0) & (c[:, 2] <= z1) & (d > r) & (d < r_max)

    arm, hand = 0.060, 0.047
    z4 = l4 - CPR_J4_AB_J5 + CPR_J4_MESH_UNTEN  # Unterkante des J4-Meshes
    m = {
        "link_1": lambda: band_z(0.0, 0.008, 0.046, arm) | band_y(0.021, 0.029, l1, 0.045, arm),
        "link_2": lambda: band_y(-0.031, -0.023, 0.0, 0.045, arm) | band_y(0.021, 0.029, a["oberarm_m"], 0.045, arm),
        "link_3": lambda: band_y(-0.031, -0.023, 0.0, 0.045, arm),
        "link_4": lambda: band_z(z4, z4 + 0.008, 0.046, arm) | band_y(0.024, 0.032, l4, 0.034, hand),
        "link_5": lambda: band_y(-0.034, -0.026, 0.0, 0.034, hand),
    }.get(name)
    return m() if m else np.zeros(len(c), bool)


def ringe_einfaerben(name: str, v, f, cfg, stufen: int = 2):
    """Dreiecke an Ringkanten ``stufen``-mal vierteln, Ringdreiecke markieren.
    Liefert Dreieckssuppe (3m, 3), Dreiecke (m, 3), Maske (m,)."""
    tri = np.asarray(v, float)[np.asarray(f, int)]
    for _ in range(stufen):
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


def arm_teil(name: str, v_link, f, cfg=None, stufen: int = 2):
    """ReBeL-Mesh eines Glieds (Ecken im Linkframe) fuer RTX aufbereiten.

    Mit ``cfg`` werden die Dreiecke an den Ringkanten verfeinert und die
    Dreiecke im Ring markiert. Liefert Ecken (k, 3), Dreiecke (m, 3),
    Normalen je Ecke (3m, 3) und Ringmaske (m,).
    """
    v_link, f = np.asarray(v_link, float), np.asarray(f, int)
    if cfg is not None:
        soup_v, soup_f, maske = ringe_einfaerben(name, v_link, f, cfg, stufen)
    else:
        soup_v, soup_f, maske = v_link[f].reshape(-1, 3), np.arange(3 * len(f)).reshape(-1, 3), np.zeros(len(f), bool)
    v2, f2, gut = verschweissen(soup_v, soup_f)
    f2, maske = f2[gut], np.asarray(maske, bool)[gut]
    return v2, f2, normalen(v2, f2), maske
