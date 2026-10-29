#!/usr/bin/env python3
"""Rendert einen Renderauftrag (isaac_render/auftrag.py) mit Isaac Sim 6.2 RTX, headless.

    <isaacsim-venv>/bin/python scripts/isaac_render.py AUFTRAG.npz --out ORDNER \
        [--breite 1280 --hoehe 720] [--von 0 --bis N] [--modus rt|pt] [--subframes 8] \
        [--spp 64] [--roboter importer|eigen] [--assets DIR] [--usd-export DATEI.usda]

Ablauf:
1. URDF aus ``rebel_model.urdf_gen`` mit den ReBeL-Visual-Meshes (lokal unter
   ``$RAEUMWERK_ASSETS``) schreiben und mit dem URDF-Importer von Isaac Sim
   (Bibliothek ``urdf_usd_converter``) nach USD wandeln (``--roboter importer``,
   Standard). ``--roboter eigen`` baut die Glieder stattdessen direkt aus den
   COLLADA-Dateien (Rueckfallweg).
2. Physik aus: RigidBody-/Articulation-APIs werden entfernt, es gibt keine
   PhysicsScene; Kollisionsquader sind unsichtbar. Nur gerendert wird.
3. Materialien (MDL): OmniPBR fuer Arm (igus-Anthrazit, orange Ringe an den
   Gelenkfugen als GeomSubset), Schiene (Alu), Tisch/Arbeitsplatte (hell),
   OmniGlass fuer die Glaeser (geschlossene Wand, bricht Licht).
4. Licht: Kuppel + Sonne mit weichem Schatten + Fuelllicht, ACES-Tonemapping.
5. Je Bild: Weltposen der Koerper als lokale Transformationen setzen (die
   Glieder sind im Importer verschachtelt), Kamera setzen,
   ``rep.orchestrator.step(rt_subframes=…)``, RGB vom Replicator-Annotator als
   PNG speichern.

Schreibt ``ORDNER/bild_00000.png`` …, ``ORDNER/render.json`` (Zeiten,
Replay-Fehler) und ``ORDNER/prims.txt`` (Primbaum des Roboters).
Kein Livestream, kein Fenster, keine Netzwerkschnittstelle.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def args_lesen(argv=None):
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("auftrag")
    ap.add_argument("--out", required=True)
    ap.add_argument("--breite", type=int, default=1280)
    ap.add_argument("--hoehe", type=int, default=720)
    ap.add_argument("--von", type=int, default=0)
    ap.add_argument("--bis", type=int, default=None, help="erstes Bild, das NICHT mehr gerendert wird")
    ap.add_argument("--jedes", type=int, default=1, help="nur jedes n-te Bild (Probe)")
    ap.add_argument("--modus", choices=("rt", "pt"), default="rt", help="rt: RTX Real-Time, pt: Path Tracing")
    ap.add_argument("--subframes", type=int, default=8, help="RTX-Subframes je Bild (Konvergenz)")
    ap.add_argument("--spp", type=int, default=64, help="Path Tracing: Samples je Subframe")
    ap.add_argument("--einschwingen", type=int, default=60, help="app.update() vor dem ersten Bild")
    ap.add_argument("--fortsetzen", action="store_true", help="Bilder ueberspringen, deren PNG schon da ist")
    ap.add_argument("--max-minuten", type=float, default=None,
                    help="nach so vielen Minuten Renderzeit sauber aufhoeren (Exit 3, mit --fortsetzen weiter)")
    ap.add_argument("--roboter", choices=("importer", "eigen"), default="importer")
    ap.add_argument("--assets", default=None)
    ap.add_argument("--film-iso", type=float, default=100.0)
    ap.add_argument("--usd-export", default=None, help="Szene nach dem ersten Bild als .usda speichern")
    ap.add_argument("--kamera", default=None,
                    help="JSON-Liste von Kameras [{auge, ziel, brennweite_mm}] statt der aus dem Auftrag")
    return ap.parse_args(argv)


def main(argv=None) -> int:
    args = args_lesen(argv)
    os.environ.setdefault("OMNI_KIT_ACCEPT_EULA", "YES")
    import numpy as np

    from isaac_render import auftrag as A
    from isaac_render import geometrie as G

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    auf = A.laden(args.auftrag)
    fehler = A.pruefen(auf)
    if fehler:
        print("AUFTRAG_FEHLER", fehler, file=sys.stderr)
        return 2
    if args.kamera:
        auf["kamera"] = json.loads(args.kamera)
    n_bilder = len(auf["posen"])
    bis = min(args.bis if args.bis is not None else n_bilder, n_bilder)
    bilder = list(range(args.von, bis, max(1, args.jedes)))
    if args.kamera and len(auf["kamera"]) > 1:
        bilder = list(range(len(auf["kamera"])))   # Kamera-Probe: ein Bild je Kamera (Pose 0)
    if args.fortsetzen:
        bilder = [k for k in bilder if not (out / f"bild_{k:05d}.png").is_file()]
        if not bilder:
            print("ISAAC_RENDER alle Bilder schon da", flush=True)
            return 0
    info: dict = {"auftrag": Path(args.auftrag).name, "szene": auf["szene"], "modus": args.modus,
                  "aufloesung": [args.breite, args.hoehe], "subframes": args.subframes, "bilder": [],
                  "roboter": args.roboter}
    t0 = time.monotonic()
    app = None
    rc = 1
    try:
        from isaacsim import SimulationApp
        app = SimulationApp({"headless": True, "hide_ui": True, "width": args.breite, "height": args.hoehe,
                             "renderer": "PathTracing" if args.modus == "pt" else "RaytracedLighting"})
        info["start_s"] = round(time.monotonic() - t0, 2)

        import carb
        import omni.replicator.core as rep
        import omni.usd
        from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux, UsdPhysics, UsdShade, Vt

        try:
            import importlib.metadata as md
            info["isaacsim_version"] = md.version("isaacsim")
        except Exception:  # noqa: BLE001
            pass

        ctx = omni.usd.get_context()
        ctx.new_stage()
        stage = ctx.get_stage()
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
        UsdGeom.SetStageMetersPerUnit(stage, 1.0)
        world = UsdGeom.Xform.Define(stage, "/World")
        stage.SetDefaultPrim(world.GetPrim())

        def gf_matrix(m):
            return Gf.Matrix4d(np.asarray(m, float).T.tolist())   # Spalten- -> Zeilenkonvention

        # --- Materialien --------------------------------------------------
        looks = {}

        def material(name: str):
            if name in looks:
                return looks[name]
            p = A.MATERIALIEN[name]
            pfad = f"/World/Looks/{name}"
            mat = UsdShade.Material.Define(stage, pfad)
            sh = UsdShade.Shader.Define(stage, pfad + "/Shader")
            sh.CreateImplementationSourceAttr(UsdShade.Tokens.sourceAsset)
            mdl = "OmniGlass" if p.get("glas") else "OmniPBR"
            sh.SetSourceAsset(Sdf.AssetPath(f"{mdl}.mdl"), "mdl")
            sh.SetSourceAssetSubIdentifier(mdl, "mdl")
            o = sh.CreateOutput("out", Sdf.ValueTypeNames.Token)
            mat.CreateSurfaceOutput("mdl").ConnectToSource(o)
            mat.CreateVolumeOutput("mdl").ConnectToSource(o)
            mat.CreateDisplacementOutput("mdl").ConnectToSource(o)
            if p.get("glas"):
                sh.CreateInput("glass_color", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*p["farbe"]))
                sh.CreateInput("glass_ior", Sdf.ValueTypeNames.Float).Set(float(p["ior"]))
                sh.CreateInput("thin_walled", Sdf.ValueTypeNames.Bool).Set(False)
                sh.CreateInput("frosting_roughness", Sdf.ValueTypeNames.Float).Set(0.0)
            else:
                sh.CreateInput("diffuse_color_constant", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*p["farbe"]))
                sh.CreateInput("reflection_roughness_constant", Sdf.ValueTypeNames.Float).Set(float(p["rauheit"]))
                sh.CreateInput("metallic_constant", Sdf.ValueTypeNames.Float).Set(float(p["metall"]))
            looks[name] = mat
            return mat

        def binden(prim, name):
            api = UsdShade.MaterialBindingAPI.Apply(prim)
            api.Bind(material(name))

        def mesh_anlegen(pfad, v, f, mat, normalen=None):
            m = UsdGeom.Mesh.Define(stage, pfad)
            m.CreatePointsAttr(Vt.Vec3fArray.FromNumpy(np.asarray(v, np.float32)))
            m.CreateFaceVertexCountsAttr(Vt.IntArray.FromNumpy(np.full(len(f), 3, np.int32)))
            m.CreateFaceVertexIndicesAttr(Vt.IntArray.FromNumpy(np.asarray(f, np.int32).reshape(-1)))
            if normalen is None:
                normalen = G.normalen(v, f)
            m.CreateNormalsAttr(Vt.Vec3fArray.FromNumpy(np.asarray(normalen, np.float32)))
            m.SetNormalsInterpolation(UsdGeom.Tokens.faceVarying)
            m.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
            m.CreateDoubleSidedAttr(False)
            if mat:
                binden(m.GetPrim(), mat)
            return m

        def ring_subset(mesh, maske):
            idx = np.nonzero(np.asarray(maske, bool))[0].astype(np.int32)
            if len(idx) == 0:
                return 0
            sub = UsdGeom.Subset.CreateGeomSubset(mesh, "igus_ring", UsdGeom.Tokens.face,
                                                  Vt.IntArray.FromNumpy(idx), "materialBind")
            binden(sub.GetPrim(), "igus_orange")
            return int(len(idx))

        # --- Roboter ------------------------------------------------------
        from rebel_model.config import load as load_robot
        from rebel_model.urdf_gen import build_urdf
        from rebel_model.visual_mesh import dae_laden, mesh_verzeichnis

        cfg = load_robot()
        meshes = mesh_verzeichnis(args.assets)
        if meshes is None:
            raise RuntimeError("ReBeL-Meshes fehlen (scripts/fetch_assets.sh, RAEUMWERK_ASSETS)")
        urdf_text = build_urdf(cfg, mesh_dir=str(meshes))
        robot_links = [k for k in auf["koerper"] if k not in auf["glaeser"]]
        link_prim: dict = {}
        ringe = {}
        if args.roboter == "importer":
            import urdf_usd_converter
            (out / "robot.urdf").write_text(urdf_text, encoding="utf-8")
            t_k = time.monotonic()
            asset = urdf_usd_converter.Converter().convert(str(out / "robot.urdf"), str(out / "robot_usd"))
            info["urdf_import_s"] = round(time.monotonic() - t_k, 2)
            rp = stage.DefinePrim("/World/Robot", "Xform")
            rp.GetReferences().AddReference(asset.path)
            for p in Usd.PrimRange(rp):
                if p.GetName() in robot_links and p.IsA(UsdGeom.Xform) and p.GetName() not in link_prim:
                    link_prim[p.GetName()] = p
            # Physik aus: nur rendern
            alle = list(Usd.PrimRange(rp))
            for p in alle:
                if p.IsInstanceable():
                    p.SetInstanceable(False)
            alle = list(Usd.PrimRange(rp))
            for p in alle:
                for api in (UsdPhysics.RigidBodyAPI, UsdPhysics.ArticulationRootAPI, UsdPhysics.MassAPI):
                    if p.HasAPI(api):
                        p.RemoveAPI(api)
                if p.HasAPI(UsdPhysics.CollisionAPI):
                    UsdGeom.Imageable(p).MakeInvisible()
            for p in [p for p in alle if p.GetName() == "Physics" and p.GetParent() == rp]:
                p.SetActive(False)
            info["physik_prims_aktiv"] = sum(1 for p in Usd.PrimRange(rp)
                                             if p.HasAPI(UsdPhysics.RigidBodyAPI) or p.IsA(UsdPhysics.Joint))
            # Materialien und Ringe je Glied (nur direkte Geometrie-Kinder)
            xc = UsdGeom.XformCache()
            for name, lp in link_prim.items():
                matname = A.link_material(name)
                for kind in lp.GetChildren():
                    if kind.GetName() in robot_links or not kind.IsA(UsdGeom.Gprim):
                        continue
                    if kind.HasAPI(UsdPhysics.CollisionAPI) or not matname:
                        continue
                    binden(kind, matname)
                    if name in A.ARM_LINKS and kind.IsA(UsdGeom.Mesh):
                        mesh = UsdGeom.Mesh(kind)
                        pts = np.array(mesh.GetPointsAttr().Get(), float)
                        cnt = np.array(mesh.GetFaceVertexCountsAttr().Get(), int)
                        ind = np.array(mesh.GetFaceVertexIndicesAttr().Get(), int)
                        if not np.all(cnt == 3):
                            raise RuntimeError(f"{kind.GetPath()}: nur Dreiecke unterstuetzt")
                        f = ind.reshape(-1, 3)
                        # Mesh -> Linkframe (Zeilenkonvention in USD)
                        m_ml = np.array(xc.ComputeRelativeTransform(kind, lp)[0], float).T
                        v_link = pts @ m_ml[:3, :3].T + m_ml[:3, 3]
                        v2, f2, _, maske = G.arm_teil(name, v_link, f, cfg)
                        inv = np.linalg.inv(m_ml)
                        v_mesh = v2 @ inv[:3, :3].T + inv[:3, 3]
                        mesh.GetPointsAttr().Set(Vt.Vec3fArray.FromNumpy(v_mesh.astype(np.float32)))
                        mesh.GetFaceVertexCountsAttr().Set(Vt.IntArray.FromNumpy(np.full(len(f2), 3, np.int32)))
                        mesh.GetFaceVertexIndicesAttr().Set(Vt.IntArray.FromNumpy(f2.reshape(-1).astype(np.int32)))
                        mesh.GetNormalsAttr().Set(Vt.Vec3fArray.FromNumpy(G.normalen(v_mesh, f2).astype(np.float32)))
                        mesh.SetNormalsInterpolation(UsdGeom.Tokens.faceVarying)
                        for pv in UsdGeom.PrimvarsAPI(mesh).GetPrimvars():
                            if pv.GetPrimvarName() in ("normals", "st", "st0", "UVMap"):
                                pv.GetAttr().Block()
                        mesh.CreateSubdivisionSchemeAttr().Set(UsdGeom.Tokens.none)
                        ringe[name] = (ring_subset(mesh, maske), int(len(f2)))
        else:
            import xml.etree.ElementTree as ET
            UsdGeom.Xform.Define(stage, "/World/Robot")
            for link in ET.fromstring(urdf_text).iter("link"):
                name = link.get("name")
                if name not in robot_links:
                    continue
                lp = UsdGeom.Xform.Define(stage, f"/World/Robot/{name}").GetPrim()
                link_prim[name] = lp
                matname = A.link_material(name)
                for i, vis in enumerate(link.iter("visual")):
                    org = vis.find("origin")
                    xyz = np.array([float(x) for x in (org.get("xyz") if org is not None else "0 0 0").split()])
                    box, mesh_el = vis.find("geometry/box"), vis.find("geometry/mesh")
                    if box is not None:
                        c = UsdGeom.Cube.Define(stage, f"{lp.GetPath()}/box_{i}")
                        c.CreateSizeAttr(1.0)
                        xf = UsdGeom.Xformable(c)
                        xf.AddTranslateOp().Set(Gf.Vec3d(*xyz))
                        xf.AddScaleOp().Set(Gf.Vec3f(*[float(x) for x in box.get("size").split()]))
                        if matname:
                            binden(c.GetPrim(), matname)
                    elif mesh_el is not None:
                        pfad = mesh_el.get("filename").replace("file://", "")
                        skala = np.array([float(x) for x in (mesh_el.get("scale") or "1 1 1").split()])
                        v, f = dae_laden(pfad)
                        v = v * skala + xyz
                        v2, f2, nrm, maske = G.arm_teil(name, v, f, cfg)
                        m = mesh_anlegen(f"{lp.GetPath()}/mesh_{i}", v2, f2, matname, nrm)
                        ringe[name] = (ring_subset(m, maske), int(len(f2)))
        fehlend = [k for k in robot_links if k not in link_prim]
        if fehlend:
            raise RuntimeError(f"Glieder ohne Prim: {fehlend}")
        info["ring_dreiecke"] = ringe
        with open(out / "prims.txt", "w", encoding="utf-8") as fh:
            for p in Usd.PrimRange(stage.GetPrimAtPath("/World/Robot")):
                fh.write(f"{p.GetPath()} {p.GetTypeName()}\n")

        # --- Glaeser (bewegt) und statische Koerper ------------------------
        dyn = {}
        for name, g in auf["glaeser"].items():
            xp = UsdGeom.Xform.Define(stage, f"/World/Dyn/{name}")
            v, f = G.glas_mesh(g["radius"], g["hoehe"])
            mesh_anlegen(f"/World/Dyn/{name}/mesh", v, f, "glas", G.normalen(v, f, 40.0))
            dyn[name] = xp.GetPrim()

        UsdGeom.Xform.Define(stage, "/World/Szene")
        for i, s in enumerate(auf["statisch"]):
            pfad = f"/World/Szene/{s['name']}".replace("-", "_")
            if stage.GetPrimAtPath(pfad):
                pfad += f"_{i}"
            pose = G.pose_matrix([*s["pos"], *s["quat"]])
            if s["form"] == "quader":
                c = UsdGeom.Cube.Define(stage, pfad)
                c.CreateSizeAttr(1.0)
                xf = UsdGeom.Xformable(c)
                xf.AddTransformOp().Set(gf_matrix(pose))
                xf.AddScaleOp().Set(Gf.Vec3f(*[2.0 * h for h in s["halb"]]))
                binden(c.GetPrim(), s["material"])
                continue
            if s["form"] == "glas":
                v, f = G.glas_mesh(s["radius"], s["hoehe"])
            elif s["form"] == "scheibe":
                v, f = G.scheibe(s["radius"])
            elif s["form"] == "ring":
                v, f = G.ring(s["r_innen"], s["r_aussen"])
            else:
                raise ValueError(f"unbekannte Form {s['form']}")
            m = mesh_anlegen(pfad, v, f, s["material"], G.normalen(v, f, 40.0))
            UsdGeom.Xformable(m).AddTransformOp().Set(gf_matrix(pose))

        # --- Licht ---------------------------------------------------------
        dome = UsdLux.DomeLight.Define(stage, "/World/Licht/Kuppel")
        dome.CreateIntensityAttr(220.0)
        dome.CreateColorAttr(Gf.Vec3f(0.92, 0.95, 1.0))
        sonne = UsdLux.DistantLight.Define(stage, "/World/Licht/Sonne")
        sonne.CreateIntensityAttr(1700.0)
        sonne.CreateAngleAttr(2.5)              # weiche Schattenkante
        sonne.CreateColorAttr(Gf.Vec3f(1.0, 0.96, 0.9))
        sonne_dir = G.blick_matrix((1.2, 2.0, 3.2), (0.0, 0.0, 0.0))
        UsdGeom.Xformable(sonne).AddTransformOp().Set(gf_matrix(sonne_dir))
        fuell = UsdLux.RectLight.Define(stage, "/World/Licht/Fuell")
        fuell.CreateIntensityAttr(900.0)
        fuell.CreateWidthAttr(1.2)
        fuell.CreateHeightAttr(0.8)
        UsdGeom.Xformable(fuell).AddTransformOp().Set(gf_matrix(G.blick_matrix((-0.8, 1.8, 1.6), (0.6, 0.3, 0.4))))

        # --- Kamera / Replicator --------------------------------------------
        cam = UsdGeom.Camera.Define(stage, "/World/Kamera")
        cam.CreateHorizontalApertureAttr(36.0)
        cam.CreateVerticalApertureAttr(36.0 * args.hoehe / args.breite)
        cam.CreateClippingRangeAttr(Gf.Vec2f(0.01, 100.0))
        cam_op = UsdGeom.Xformable(cam).AddTransformOp()
        focal = cam.CreateFocalLengthAttr(30.0)

        s = carb.settings.get_settings()
        s.set("/rtx/post/tonemap/op", 4)                 # ACES
        s.set("/rtx/post/tonemap/filmIso", float(args.film_iso))
        s.set("/rtx/post/tonemap/whitepoint", 6500.0)
        s.set("/rtx/post/tonemap/enabled", True)
        s.set("/rtx/translucency/enabled", True)
        s.set("/rtx/reflections/enabled", True)
        s.set("/rtx/directLighting/sampledLighting/enabled", True)
        if args.modus == "pt":
            s.set("/rtx/rendermode", "PathTracing")
            s.set("/rtx/pathtracing/spp", int(args.spp))
            s.set("/rtx/pathtracing/totalSpp", int(args.spp) * max(1, args.subframes))
            s.set("/rtx/pathtracing/maxBounces", 8)
            s.set("/rtx/pathtracing/optixDenoiser/enabled", True)
        else:
            s.set("/rtx/rendermode", "RayTracedLighting")
            s.set("/rtx/post/aa/op", 3)
        try:
            rep.orchestrator.set_capture_on_play(False)
        except Exception:  # noqa: BLE001
            pass
        rp_ = rep.create.render_product("/World/Kamera", (args.breite, args.hoehe))
        rgb = rep.AnnotatorRegistry.get_annotator("rgb")
        rgb.attach([rp_])

        def pose_setzen(k: int):
            q = auf["posen"][min(k, n_bilder - 1)]
            welt = {name: G.pose_matrix(q[i]) for i, name in enumerate(auf["koerper"])}
            cache = UsdGeom.XformCache()
            # Eltern zuerst (Tiefe im Primbaum), lokale = inv(Eltern-Welt) * Welt
            for name in sorted(link_prim, key=lambda n: len(str(link_prim[n].GetPath()))):
                prim = link_prim[name]
                eltern = np.array(cache.GetLocalToWorldTransform(prim.GetParent()), float).T
                lokal = np.linalg.inv(eltern) @ welt[name]
                xf = UsdGeom.Xformable(prim)
                op = xf.GetOrderedXformOps()
                if len(op) != 1 or op[0].GetOpName() != "xformOp:transform:replay":
                    xf.ClearXformOpOrder()
                    op = [xf.AddTransformOp(opSuffix="replay")]
                op[0].Set(gf_matrix(lokal))
                cache.Clear()
            for name, prim in dyn.items():
                xf = UsdGeom.Xformable(prim)
                op = xf.GetOrderedXformOps()
                if not op:
                    op = [xf.AddTransformOp()]
                op[0].Set(gf_matrix(welt[name]))
            kk = auf["kamera"][min(k, len(auf["kamera"]) - 1)]
            cam_op.Set(gf_matrix(G.blick_matrix(kk["auge"], kk["ziel"])))
            focal.Set(float(kk.get("brennweite_mm", 30.0)))
            return welt

        def replay_fehler(welt) -> float:
            cache = UsdGeom.XformCache()
            fe = 0.0
            for name, prim in link_prim.items():
                m = np.array(cache.GetLocalToWorldTransform(prim), float).T
                fe = max(fe, float(np.abs(m[:3, 3] - welt[name][:3, 3]).max()))
            return fe

        from PIL import Image

        welt0 = pose_setzen(bilder[0] if not args.kamera or len(auf["kamera"]) == 1 else 0)
        t_e = time.monotonic()
        for _ in range(max(0, args.einschwingen)):
            app.update()
        info["einschwingen_s"] = round(time.monotonic() - t_e, 2)
        info["replay_fehler_mm"] = round(replay_fehler(welt0) * 1e3, 6)
        if args.usd_export:
            stage.GetRootLayer().Export(args.usd_export)

        t_r = time.monotonic()
        mittel = []
        for j, k in enumerate(bilder):
            t_b = time.monotonic()
            if args.kamera and len(auf["kamera"]) > 1:
                pose_setzen(0)
                kk = auf["kamera"][k]
                cam_op.Set(gf_matrix(G.blick_matrix(kk["auge"], kk["ziel"])))
                focal.Set(float(kk.get("brennweite_mm", 30.0)))
            else:
                pose_setzen(k)
            rep.orchestrator.step(rt_subframes=max(1, args.subframes), delta_time=0.0)
            data = np.asarray(rgb.get_data())
            if data.ndim != 3 or data.shape[0] != args.hoehe or data.shape[1] != args.breite:
                raise RuntimeError(f"Bild {k}: Form {data.shape}")
            img = data[:, :, :3].astype(np.uint8)
            Image.fromarray(img).save(out / f"bild_{k:05d}.png")
            mittel.append(float(img.mean()))
            if j < 3 or j % 100 == 0:
                print(f"BILD {k} {time.monotonic() - t_b:.2f}s mittel={img.mean():.1f}", flush=True)
            if args.max_minuten and time.monotonic() - t_r > 60.0 * args.max_minuten and j < len(bilder) - 1:
                info["abgebrochen_nach_bild"] = k
                bilder = bilder[: j + 1]
                break
        info["render_s"] = round(time.monotonic() - t_r, 2)
        info["bilder"] = [bilder[0], bilder[-1], len(bilder)]
        info["s_je_bild"] = round(info["render_s"] / max(1, len(bilder)), 3)
        info["helligkeit_mittel"] = [round(min(mittel), 1), round(max(mittel), 1)]
        rc = 3 if "abgebrochen_nach_bild" in info else 0
    except Exception as e:  # noqa: BLE001
        info["error"] = f"{type(e).__name__}: {e}"
        info["traceback"] = traceback.format_exc()[-4000:]
    finally:
        info["gesamt_s"] = round(time.monotonic() - t0, 2)
        with open(out / "render.json", "w", encoding="utf-8") as fh:
            json.dump(info, fh, indent=2)
        with open(out / "render-laeufe.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps({k: v for k, v in info.items() if k != "traceback"}) + "\n")
        print("ISAAC_RENDER", json.dumps({k: v for k, v in info.items() if k != "traceback"}), flush=True)
        if "traceback" in info:
            print(info["traceback"], file=sys.stderr, flush=True)
        if app is not None:
            app.close()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
