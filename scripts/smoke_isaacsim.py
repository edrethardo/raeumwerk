#!/usr/bin/env python3
"""Smoke-Test Isaac Sim (PhysX): Bodenplatte + fallender Wuerfel, headless.

Wird vom ``smoke_runner.py`` mit dem Python des Isaac-Sim-venv gestartet und
schreibt das Physik-Ergebnis als JSON nach ``--result``. Kein Livestream,
keine Fenster, keine Netzwerkschnittstelle.

Szenario (aus ``RAEUMWERK_SCENARIO``): Wuerfel mit Kantenlaenge ``cube_size``
startet mit dem Mittelpunkt auf ``start_height`` und faellt ``steps`` Schritte
mit ``dt`` auf eine statische Bodenplatte (Z oben, Meter).
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
    os.environ.setdefault("OMNI_KIT_ACCEPT_EULA", "YES")
    out: dict = {"backend": "isaacsim", "steps": 0}
    t0 = time.monotonic()
    app = None
    try:
        from isaacsim import SimulationApp

        # headless, ohne Livestream; Standard-Experience fuer Python-Apps
        app = SimulationApp({"headless": True, "hide_ui": True, "renderer": "RaytracedLighting"})
        out["startup_s"] = round(time.monotonic() - t0, 2)

        import omni.usd
        from omni.physx import get_physx_interface
        from pxr import Gf, UsdGeom, UsdPhysics

        ctx = omni.usd.get_context()
        ctx.new_stage()
        stage = ctx.get_stage()
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
        UsdGeom.SetStageMetersPerUnit(stage, 1.0)
        UsdGeom.Xform.Define(stage, "/World")

        scene = UsdPhysics.Scene.Define(stage, "/World/physicsScene")
        scene.CreateGravityDirectionAttr(Gf.Vec3f(0.0, 0.0, -1.0))
        scene.CreateGravityMagnitudeAttr(9.81)

        # Bodenplatte: statischer Quader 10 x 10 x 0.1 m, Oberkante bei z = 0
        ground = UsdGeom.Cube.Define(stage, "/World/ground")
        ground.CreateSizeAttr(1.0)
        gx = UsdGeom.Xformable(ground)
        gx.AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, -0.05))
        gx.AddScaleOp().Set(Gf.Vec3f(10.0, 10.0, 0.1))
        UsdPhysics.CollisionAPI.Apply(ground.GetPrim())

        # Wuerfel: dynamischer Starrkoerper
        cube = UsdGeom.Cube.Define(stage, "/World/cube")
        cube.CreateSizeAttr(float(sc["cube_size"]))
        UsdGeom.Xformable(cube).AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, float(sc["start_height"])))
        UsdPhysics.CollisionAPI.Apply(cube.GetPrim())
        UsdPhysics.RigidBodyAPI.Apply(cube.GetPrim())
        UsdPhysics.MassAPI.Apply(cube.GetPrim()).CreateMassAttr(1.0)

        app.update()
        physx = get_physx_interface()
        physx.start_simulation()
        physx.force_load_physics_from_usd()

        dt = float(sc["dt"])
        heights = []
        t_sim = time.monotonic()
        for i in range(int(sc["steps"])):
            physx.update_simulation(elapsedStep=dt, currentTime=i * dt)
            if i % 50 == 49:
                heights.append(round(float(physx.get_rigidbody_transformation("/World/cube")["position"][2]), 4))
        out["sim_s"] = round(time.monotonic() - t_sim, 3)
        pose = physx.get_rigidbody_transformation("/World/cube")
        out["final_height"] = float(pose["position"][2])
        out["height_every_50"] = heights
        out["steps"] = int(sc["steps"])
        try:
            import importlib.metadata as md
            out["isaacsim_version"] = md.version("isaacsim")
        except Exception:  # noqa: BLE001
            pass
    except Exception as e:  # noqa: BLE001
        out["error"] = f"{type(e).__name__}: {e}"
        out["traceback"] = traceback.format_exc()[-4000:]
    finally:
        out["total_in_process_s"] = round(time.monotonic() - t0, 2)
        with open(args.result, "w") as f:
            json.dump(out, f, indent=2)
        print("SMOKE_RESULT", json.dumps({k: v for k, v in out.items() if k != "traceback"}), flush=True)
        if app is not None:
            app.close()  # beendet den Prozess bei Kit oft direkt
    return 0 if "error" not in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
