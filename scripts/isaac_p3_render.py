#!/usr/bin/env python3
"""Kameratag P3: Spuelmaschinen-Szenen mit der Ensenso-C57-6-S-Pose rendern (RGB, Tiefe, Instanz-ID).

    <isaacsim-venv>/bin/python scripts/isaac_p3_render.py SZENEN.json --out ORDNER \
        [--breite 2472 --hoehe 2064] [--modus rt|pt] [--subframes 12] [--spp 32] [--von 0 --bis N] \
        [--ids id1,id2] [--fortsetzen] [--max-minuten M] [--glas-opak]

``SZENEN.json``: Liste von Szenen aus ``wahrnehmung.p3_szenen.baue_szene`` (siehe ``scripts/p3_szenen.py``).
Je Szene entstehen ``<id>_rgb.png``, ``<id>_tiefe.npz`` (uint16, mm; 0 = kein Wert), ``<id>_inst.npz``
(uint16 Objektindex, 0 = Hintergrund, plus ``namen``) und ``<id>.json`` (Zeiten, Helligkeit).
``--glas-opak`` rendert zusaetzlich die Instanzkarte mit undurchsichtigen Glaesern (``inst_opak`` in der
.npz): Glas ist in der echten Instanzkarte sonst nur dann drin, wenn RTX es als Treffer fuehrt.

Kamera: Lochkamera mit den Katalogwerten des C57-6-S (Brennweite 2591/2381 px, 2472 x 2064 px) und der Pose
aus ``wahrnehmung.griffpose`` (Mast 0,55/0,50/1,35 m, 60 Grad). Das Projektormuster der Ensenso wird NICHT
simuliert. Kein Roboterarm im Bild. Kein Livestream, kein Fenster, keine Netzwerkschnittstelle.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

LICHT_PLAENE = {
    # (Kuppel-Intensitaet, Farbe), Sonne (Intensitaet, Farbe) oder None, Flaechenlichter [(Intensitaet, Farbe, Breite, Hoehe, Ort, Ziel)]
    "tag": dict(dome=(300.0, (0.92, 0.95, 1.0)), sonne=(1700.0, (1.0, 0.96, 0.9)),
                flaechen=[(900.0, (1, 1, 1), 1.2, 0.8, (-0.8, 1.8, 1.6), (0.6, 0.3, 0.4))]),
    "kueche": dict(dome=(40.0, (1.0, 0.9, 0.8)), sonne=None,
                   flaechen=[(2600.0, (1.0, 0.84, 0.66), 1.0, 0.5, (0.15, 0.20, 2.4), (0.3, 0.2, 0.5)),
                             (2600.0, (1.0, 0.84, 0.66), 1.0, 0.5, (0.55, 0.60, 2.4), (0.3, 0.2, 0.5))]),
    "dunkel": dict(dome=(6.0, (0.8, 0.85, 1.0)), sonne=None,
                   flaechen=[(260.0, (1.0, 0.8, 0.6), 0.3, 0.3, (0.9, 1.2, 1.6), (0.3, 0.2, 0.5))]),
}


def args_lesen(argv=None):
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("szenen")
    ap.add_argument("--out", required=True)
    ap.add_argument("--breite", type=int, default=2472)
    ap.add_argument("--hoehe", type=int, default=2064)
    ap.add_argument("--modus", choices=("rt", "pt"), default="rt")
    ap.add_argument("--subframes", type=int, default=12)
    ap.add_argument("--spp", type=int, default=32)
    ap.add_argument("--von", type=int, default=0)
    ap.add_argument("--bis", type=int, default=None)
    ap.add_argument("--ids", default=None, help="nur diese Szenen-IDs (Komma)")
    ap.add_argument("--einschwingen", type=int, default=30)
    ap.add_argument("--fortsetzen", action="store_true")
    ap.add_argument("--max-minuten", type=float, default=None)
    ap.add_argument("--glas-opak", action="store_true")
    ap.add_argument("--film-iso", type=float, default=100.0)
    return ap.parse_args(argv)


def main(argv=None) -> int:
    args = args_lesen(argv)
    os.environ.setdefault("OMNI_KIT_ACCEPT_EULA", "YES")
    import numpy as np

    from isaac_render import auftrag as A
    from isaac_render import geometrie as G
    from wahrnehmung import griffpose as WG
    from wahrnehmung import p3_szenen as P3
    from wahrnehmung.strahlen import ENSENSO

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    szenen = json.loads(Path(args.szenen).read_text(encoding="utf-8"))
    if args.ids:
        want = set(args.ids.split(","))
        szenen = [s for s in szenen if s["id"] in want]
    else:
        szenen = szenen[args.von:args.bis]
    if args.fortsetzen:
        szenen = [s for s in szenen if not (out / f"{s['id']}.json").is_file()]
    info: dict = {"szenen_datei": Path(args.szenen).name, "modus": args.modus, "aufloesung": [args.breite, args.hoehe],
                  "subframes": args.subframes, "szenen": []}
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
        from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux, UsdShade, Vt
        from PIL import Image

        ctx = omni.usd.get_context()
        ctx.new_stage()
        stage = ctx.get_stage()
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
        UsdGeom.SetStageMetersPerUnit(stage, 1.0)
        world = UsdGeom.Xform.Define(stage, "/World")
        stage.SetDefaultPrim(world.GetPrim())

        def gf_matrix(m):
            return Gf.Matrix4d(np.asarray(m, float).T.tolist())

        looks: dict = {}

        def material(name):
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
            UsdShade.MaterialBindingAPI.Apply(prim).Bind(material(name))

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

        # --- Semantik (Instanz-ID): Label je Objekt-Xform -------------------------------------
        sem_weg = {"name": None}

        def label(prim, name):
            for weg in ("labels", "update", "api"):
                try:
                    if weg == "labels":
                        from isaacsim.core.utils.semantics import add_labels
                        add_labels(prim, [name], instance_name="class")
                    elif weg == "update":
                        from isaacsim.core.utils.semantics import add_update_semantics
                        add_update_semantics(prim, name, "class")
                    else:
                        from pxr import Semantics
                        sem = Semantics.SemanticsAPI.Apply(prim, "Semantics_class")
                        sem.CreateSemanticTypeAttr().Set("class")
                        sem.CreateSemanticDataAttr().Set(name)
                    sem_weg["name"] = weg
                    return
                except Exception:  # noqa: BLE001
                    continue
            raise RuntimeError("keine Semantik-API gefunden")

        # --- Kamera (C57-6-S) ----------------------------------------------------------------
        W, H = args.breite, args.hoehe
        f_mm = 24.0
        cam = UsdGeom.Camera.Define(stage, "/World/Kamera")
        cam.CreateHorizontalApertureAttr(f_mm * W / ENSENSO["f"])
        cam.CreateVerticalApertureAttr(f_mm * H / ENSENSO["fy"])
        cam.CreateFocalLengthAttr(f_mm)
        cam.CreateClippingRangeAttr(Gf.Vec2f(0.05, 20.0))
        auge, ziel = WG.ensenso_pose_aus(szenen[0]["mast_m"] if szenen else WG.ENSENSO_POSE[0])
        UsdGeom.Xformable(cam).AddTransformOp().Set(gf_matrix(G.blick_matrix(auge, ziel)))
        info["kamera"] = {"auge": list(map(float, auge)), "ziel": list(map(float, ziel)),
                          "f_px": [ENSENSO["f"], ENSENSO["fy"]], "mdl": "C57-6-S (Katalog)"}

        s = carb.settings.get_settings()
        s.set("/rtx/post/tonemap/op", 4)
        s.set("/rtx/post/tonemap/filmIso", float(args.film_iso))
        s.set("/rtx/post/tonemap/whitepoint", 6500.0)
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
        rp_ = rep.create.render_product("/World/Kamera", (W, H))
        rgb = rep.AnnotatorRegistry.get_annotator("rgb")
        rgb.attach([rp_])
        tiefe = rep.AnnotatorRegistry.get_annotator("distance_to_image_plane")
        tiefe.attach([rp_])
        inst = rep.AnnotatorRegistry.get_annotator("instance_id_segmentation", init_params={"colorize": False})
        inst.attach([rp_])

        def licht_setzen(name):
            if stage.GetPrimAtPath("/World/Licht"):
                stage.RemovePrim("/World/Licht")
            p = LICHT_PLAENE[name]
            UsdGeom.Xform.Define(stage, "/World/Licht")
            dome = UsdLux.DomeLight.Define(stage, "/World/Licht/Kuppel")
            dome.CreateIntensityAttr(p["dome"][0])
            dome.CreateColorAttr(Gf.Vec3f(*p["dome"][1]))
            if p["sonne"]:
                sonne = UsdLux.DistantLight.Define(stage, "/World/Licht/Sonne")
                sonne.CreateIntensityAttr(p["sonne"][0])
                sonne.CreateAngleAttr(2.5)
                sonne.CreateColorAttr(Gf.Vec3f(*p["sonne"][1]))
                UsdGeom.Xformable(sonne).AddTransformOp().Set(gf_matrix(G.blick_matrix((1.2, 2.0, 3.2), (0.0, 0.0, 0.0))))
            for i, (inten, farbe, b, h, ort, zl) in enumerate(p["flaechen"]):
                r = UsdLux.RectLight.Define(stage, f"/World/Licht/Flaeche{i}")
                r.CreateIntensityAttr(inten)
                r.CreateWidthAttr(b)
                r.CreateHeightAttr(h)
                r.CreateColorAttr(Gf.Vec3f(*farbe))
                UsdGeom.Xformable(r).AddTransformOp().Set(gf_matrix(G.blick_matrix(ort, zl)))

        def szene_bauen(d, rng):
            for pf in ("/World/Szene", "/World/Obj"):
                if stage.GetPrimAtPath(pf):
                    stage.RemovePrim(pf)
            UsdGeom.Xform.Define(stage, "/World/Szene")
            UsdGeom.Xform.Define(stage, "/World/Obj")
            nass = bool(d["nass"])
            for i, k in enumerate(d["statisch"]):
                c = UsdGeom.Cube.Define(stage, f"/World/Szene/{re.sub('[^A-Za-z0-9_]', '_', k['name'])}_{i}")
                c.CreateSizeAttr(1.0)
                pose = np.eye(4)
                pose[:3, :3] = np.asarray(k["rot"], float)
                pose[:3, 3] = k["mitte"]
                xf = UsdGeom.Xformable(c)
                xf.AddTransformOp().Set(gf_matrix(pose))
                xf.AddScaleOp().Set(Gf.Vec3f(*[2.0 * h for h in k["halb"]]))
                mat = P3.GRUPPE_MATERIAL.get(k["gruppe"], "korb")
                if nass and k["gruppe"] in ("oberkorb", "unterkorb"):
                    mat = "korb_nass"
                binden(c.GetPrim(), mat)
            glas_prims = []
            tropfen_prims = []
            for o in d["objekte"]:
                xp = UsdGeom.Xform.Define(stage, f"/World/Obj/{o['name']}")
                pose = np.eye(4)
                pose[:3, :3] = np.asarray(o["rot"], float)
                pose[:3, 3] = o["mitte"]
                UsdGeom.Xformable(xp).AddTransformOp().Set(gf_matrix(pose))
                label(xp.GetPrim(), o["name"])
                r, h = o["radius"], o["hoehe"]
                if o["klasse"] == "glas":
                    v, f = G.glas_mesh(r, h)
                    m = mesh_anlegen(f"/World/Obj/{o['name']}/mesh", v, f, "glas", G.normalen(v, f, 40.0))
                    glas_prims.append(m.GetPrim())
                    if nass:
                        n_t = int(rng.integers(25, 60))
                        ang = rng.uniform(0, 2 * np.pi, n_t)
                        seite = rng.random(n_t) < 0.7
                        zz = np.where(seite, rng.uniform(-h / 2 + 0.006, h / 2 - 0.006, n_t), -h / 2)
                        rr = np.where(seite, r, rng.uniform(0, r * 0.85, n_t))
                        cx = np.where(seite, r * np.cos(ang), rr * np.cos(ang))
                        cy = np.where(seite, r * np.sin(ang), rr * np.sin(ang))
                        z_n = np.where(seite, 0.0, -1.0)
                        nrm = np.stack([np.where(seite, np.cos(ang), 0.0), np.where(seite, np.sin(ang), 0.0), z_n], 1)
                        vt, ft = G.tropfen_mesh(np.stack([cx, cy, zz], 1), nrm, rng.uniform(0.0014, 0.0035, n_t))
                        tm = mesh_anlegen(f"/World/Obj/{o['name']}/tropfen", vt, ft, "glas", G.normalen(vt, ft, 40.0))
                        tropfen_prims.append(tm.GetPrim())
                else:
                    v, f = G.teller_mesh(r)
                    mat = o["farbe"] + ("_nass" if nass else "")
                    mesh_anlegen(f"/World/Obj/{o['name']}/mesh", v, f, mat, G.normalen(v, f, 40.0))
                    if nass:
                        n_t = int(rng.integers(20, 45))
                        rr = np.sqrt(rng.uniform(0, 1, n_t)) * r * 0.85
                        ang = rng.uniform(0, 2 * np.pi, n_t)
                        zt = -0.11 * r / 2 + 0.004 + np.maximum(rr - 0.62 * r, 0) / (0.35 * r) * 0.11 * r
                        vt, ft = G.tropfen_mesh(np.stack([rr * np.cos(ang), rr * np.sin(ang), zt], 1),
                                                np.tile([0.0, 0.0, 1.0], (n_t, 1)), rng.uniform(0.0015, 0.004, n_t))
                        tm = mesh_anlegen(f"/World/Obj/{o['name']}/tropfen", vt, ft, "glas", G.normalen(vt, ft, 40.0))
                        tropfen_prims.append(tm.GetPrim())
            return glas_prims + tropfen_prims

        def inst_karte(data, namen):
            """Instanzkarte -> (uint16 Objektindex 0 = Hintergrund, id->Name)."""
            arr = np.asarray(data["data"]) if isinstance(data, dict) else np.asarray(data)
            inf = data.get("info", {}) if isinstance(data, dict) else {}
            id2l = inf.get("idToLabels") or inf.get("idToSemantics") or {}
            idx = {n: i + 1 for i, n in enumerate(namen)}
            lut = {}
            for k, v in id2l.items():
                txt = json.dumps(v) if not isinstance(v, str) else v
                hit = re.findall(r"(?:glas|teller)_\d+", txt)
                if hit and hit[-1] in idx:
                    lut[int(k)] = idx[hit[-1]]
            out_ = np.zeros(arr.shape[:2], np.uint16)
            for k, v in lut.items():
                out_[arr == k] = v
            return out_, {str(k): v for k, v in id2l.items()}

        t_r = time.monotonic()
        for j, d in enumerate(szenen):
            t_b = time.monotonic()
            rng = np.random.default_rng(int(d["seed"]) + 17)
            glas_prims = szene_bauen(d, rng)
            licht_setzen(d["licht"])
            for _ in range(max(0, args.einschwingen if j == 0 else 3)):
                app.update()
            t_s = time.monotonic()
            rep.orchestrator.step(rt_subframes=max(1, args.subframes), delta_time=0.0)
            im = np.asarray(rgb.get_data())[:, :, :3].astype(np.uint8)
            z = np.asarray(tiefe.get_data(), dtype=np.float32)
            idat = inst.get_data()
            namen = [o["name"] for o in d["objekte"]]
            ik, id2l = inst_karte(idat, namen)
            extra = {}
            if args.glas_opak and glas_prims:
                mo = material("opak_maske")
                alt = {}
                for p in glas_prims:
                    api = UsdShade.MaterialBindingAPI(p)
                    alt[p] = api.GetDirectBinding().GetMaterial()
                    api.Bind(mo)
                rep.orchestrator.step(rt_subframes=1, delta_time=0.0)
                ik2, _ = inst_karte(inst.get_data(), namen)
                extra["inst_opak"] = ik2
                for p, mt in alt.items():
                    UsdShade.MaterialBindingAPI(p).Bind(mt)
            render_s = time.monotonic() - t_s
            Image.fromarray(im).save(out / f"{d['id']}_rgb.png")
            zmm = np.where(np.isfinite(z) & (z < 20.0), np.round(z * 1000.0), 0).clip(0, 65535).astype(np.uint16)
            np.savez_compressed(out / f"{d['id']}_tiefe.npz", tiefe_mm=zmm)
            np.savez_compressed(out / f"{d['id']}_inst.npz", inst=ik, namen=np.array(namen), **extra)
            rec = {"id": d["id"], "korb": d["korb"], "licht": d["licht"], "nass": d["nass"],
                   "auszug_m": d["auszug_m"], "objekte": len(namen), "render_s": round(render_s, 2),
                   "szene_gesamt_s": round(time.monotonic() - t_b, 2), "helligkeit": round(float(im.mean()), 1),
                   "inst_px_je_objekt": {n: int((ik == i + 1).sum()) for i, n in enumerate(namen)},
                   "semantik_weg": sem_weg["name"], "idToLabels_probe": dict(list(id2l.items())[:4]),
                   "tiefe_gueltig_%": round(100.0 * float((zmm > 0).mean()), 1)}
            (out / f"{d['id']}.json").write_text(json.dumps(rec, indent=1), encoding="utf-8")
            info["szenen"].append({k: rec[k] for k in ("id", "render_s", "szene_gesamt_s", "helligkeit")})
            print(f"SZENE {d['id']} {rec['szene_gesamt_s']:.1f}s (Render {rec['render_s']:.1f}s) hell={rec['helligkeit']} "
                  f"objekte={rec['objekte']} sem={sem_weg['name']}", flush=True)
            if args.max_minuten and time.monotonic() - t_r > 60.0 * args.max_minuten and j < len(szenen) - 1:
                info["abgebrochen_nach"] = d["id"]
                break
        info["render_s"] = round(time.monotonic() - t_r, 2)
        rc = 3 if "abgebrochen_nach" in info else 0
    except Exception as e:  # noqa: BLE001
        info["error"] = f"{type(e).__name__}: {e}"
        info["traceback"] = traceback.format_exc()[-4000:]
    finally:
        info["gesamt_s"] = round(time.monotonic() - t0, 2)
        with open(out / "render-laeufe.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps({k: v for k, v in info.items() if k != "traceback"}) + "\n")
        print("ISAAC_P3", json.dumps({k: v for k, v in info.items() if k not in ("traceback", "szenen")}), flush=True)
        if "traceback" in info:
            print(info["traceback"], file=sys.stderr, flush=True)
        if app is not None:
            app.close()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
