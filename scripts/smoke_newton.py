#!/usr/bin/env python3
"""Smoke-Test Newton (Isaac-Lab-3.0-Backend, ohne Isaac Sim): Boden + fallender Wuerfel.

Gleiches Szenario wie ``smoke_isaacsim.py``; gestartet vom ``smoke_runner.py``
mit dem Python des Isaac-Lab-venv. Ergebnis als JSON nach ``--result``.
Rein headless (kein Viewer), keine Netzwerkschnittstelle.

Solver: ``SolverXPBD`` (Standard) oder ``SolverMuJoCo`` per
``RAEUMWERK_NEWTON_SOLVER=mujoco``. Substeps per ``RAEUMWERK_NEWTON_SUBSTEPS``.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import traceback

DEFAULT = {"steps": 300, "dt": 1.0 / 60.0, "cube_size": 0.1, "start_height": 1.0}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", required=True)
    args = ap.parse_args()
    sc = {**DEFAULT, **json.loads(os.environ.get("RAEUMWERK_SCENARIO", "{}"))}
    solver_name = os.environ.get("RAEUMWERK_NEWTON_SOLVER", "xpbd")
    substeps = int(os.environ.get("RAEUMWERK_NEWTON_SUBSTEPS", "10"))
    out: dict = {"backend": "newton", "steps": 0, "solver": solver_name, "substeps": substeps}
    t0 = time.monotonic()
    try:
        import warp as wp
        import newton
        import importlib.metadata as md

        for p in ("newton", "warp-lang", "isaaclab"):
            try:
                out[f"{p}_version"] = md.version(p)
            except md.PackageNotFoundError:
                out[f"{p}_version"] = None
        # Isaac Lab 3.0 muss importierbar sein (Backend-Nachweis), auch wenn der
        # Smoke die Newton-API direkt nutzt.
        import isaaclab  # noqa: F401

        wp.init()
        device = "cuda:0" if wp.is_cuda_available() else "cpu"
        out["device"] = device
        out["startup_s"] = round(time.monotonic() - t0, 2)

        half = float(sc["cube_size"]) / 2.0
        builder = newton.ModelBuilder()  # Z oben
        builder.add_ground_plane()
        body = builder.add_body(xform=wp.transform(wp.vec3(0.0, 0.0, float(sc["start_height"])), wp.quat_identity()))
        builder.add_shape_box(body, hx=half, hy=half, hz=half)
        model = builder.finalize(device=device)

        if solver_name == "mujoco":
            solver = newton.solvers.SolverMuJoCo(model)
        else:
            solver = newton.solvers.SolverXPBD(model, iterations=5)

        s0, s1 = model.state(), model.state()
        control = model.control()
        pipeline = newton.CollisionPipeline(model)
        contacts = pipeline.contacts()
        dt = float(sc["dt"]) / substeps

        heights = []
        t_sim = time.monotonic()
        for i in range(int(sc["steps"])):
            for _ in range(substeps):
                s0.clear_forces()
                pipeline.collide(s0, contacts)
                solver.step(s0, s1, control, contacts, dt)
                s0, s1 = s1, s0
            if i % 50 == 49:
                heights.append(round(float(s0.body_q.numpy()[body][2]), 4))
        wp.synchronize()
        out["sim_s"] = round(time.monotonic() - t_sim, 3)
        out["final_height"] = float(s0.body_q.numpy()[body][2])
        out["height_every_50"] = heights
        out["steps"] = int(sc["steps"])
    except Exception as e:  # noqa: BLE001
        out["error"] = f"{type(e).__name__}: {e}"
        out["traceback"] = traceback.format_exc()[-4000:]
    finally:
        out["total_in_process_s"] = round(time.monotonic() - t0, 2)
        with open(args.result, "w") as f:
            json.dump(out, f, indent=2)
        print("SMOKE_RESULT", json.dumps({k: v for k, v in out.items() if k != "traceback"}), flush=True)
    return 0 if "error" not in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
