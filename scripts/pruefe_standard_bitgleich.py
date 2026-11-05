#!/usr/bin/env python3
"""Prueft, dass der Standardaufruf von ``wahrnehmung.griffpose.schaetzen`` (ohne ``neu_hinsehen``/``prior``)
gegenueber ``main`` bitgleich ist.

Es werden 4 Faelle (Glas/Teller x Seed 1, 2), je ohne und mit festem Drift (20 mm / 15 Grad) gerechnet, das
ganze Ergebnis-Dict als JSON serialisiert und per SHA-256 verglichen. Die Referenz kommt aus einem
``git archive``-Export von ``main`` in einem Temp-Verzeichnis (Aufruf von diesem Skript mit ``--dump``).

Aufruf:  python scripts/pruefe_standard_bitgleich.py [--ref main]      (Exit 0 = alle Hashes gleich)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _json(o):
    import numpy as np
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (np.floating, np.integer, np.bool_)):
        return o.item()
    raise TypeError(type(o))


def dump(wurzel: Path) -> dict:
    """Hash je Fall, gerechnet mit dem Code unter ``wurzel`` (Standardaufruf, keine neuen Schalter)."""
    sys.path.insert(0, str(wurzel))
    sys.path.insert(0, str(wurzel / "tests"))
    import numpy as np
    from test_robustheit import _nenn_glas, _nenn_teller, _welt_glas, _welt_teller
    from wahrnehmung import griffpose as WG
    from wahrnehmung import robustheit as RB

    assert Path(WG.__file__).resolve().is_relative_to(wurzel.resolve()), WG.__file__
    out = {}
    for art in ("glas", "teller"):
        w = _welt_glas() if art == "glas" else _welt_teller()
        nenn = _nenn_glas() if art == "glas" else _nenn_teller()
        skala = 2.0 if art == "glas" else 2.5
        for seed in (1, 2):
            for drift in (False, True):
                kw = dict(seed=seed, skala_ensenso=skala, skala_d405=1.5)
                if drift:
                    extra = {} if art == "glas" else {"achse": [0.0, 0.0, 1.0]}
                    kw["posedrift"] = RB.drift_fest(np.random.default_rng(9000 + seed), 0.020, 15.0, **extra)
                r = WG.schaetzen(art, w, 0, nenn, **kw)
                s = json.dumps(r, sort_keys=True, default=_json)
                out[f"{art}/seed{seed}/{'drift' if drift else 'ohne'}"] = hashlib.sha256(s.encode()).hexdigest()
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default="main", help="Git-Ref der Referenz (Standard main)")
    ap.add_argument("--dump", metavar="WURZEL", help="intern: Hashes fuer den Code unter WURZEL als JSON ausgeben")
    a = ap.parse_args()
    if a.dump:
        print(json.dumps(dump(Path(a.dump))))
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        tar = Path(tmp) / "ref.tar"
        subprocess.run(["git", "-C", str(REPO), "archive", "--format=tar", "-o", str(tar), a.ref], check=True)
        ref_dir = Path(tmp) / "ref"
        ref_dir.mkdir()
        subprocess.run(["tar", "-xf", str(tar), "-C", str(ref_dir)], check=True)
        res = {}
        for name, wurzel in (("ref", ref_dir), ("branch", REPO)):
            p = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--dump", str(wurzel)],
                               capture_output=True, text=True, cwd=wurzel)
            if p.returncode:
                print(p.stderr, file=sys.stderr)
                return 2
            res[name] = json.loads(p.stdout.strip().splitlines()[-1])
    schlecht = [k for k in res["ref"] if res["ref"][k] != res["branch"].get(k)]
    for k in res["ref"]:
        print(f"{k:24s} {'gleich' if k not in schlecht else 'ABWEICHUNG'}  {res['branch'].get(k, '-')[:16]}")
    print(f"{len(res['ref']) - len(schlecht)}/{len(res['ref'])} Faelle bitgleich zu {a.ref}")
    return 1 if schlecht else 0


if __name__ == "__main__":
    sys.exit(main())
