"""Kinematik-, Grenzen- und Selbstkollisionstests des ReBeL-Modells (ohne GPU).

Laeuft mit ``uvx -p 3.10 --with numpy --with pyyaml pytest -q tests``.
Ohne numpy/PyYAML werden die Tests uebersprungen.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("yaml")

from rebel_model.collision import SelfCollision  # noqa: E402
from rebel_model.config import load  # noqa: E402
from rebel_model.kinematics import Chain, rot_log  # noqa: E402
from rebel_model.urdf_gen import ARM_JOINTS, build_urdf  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
D = math.radians


@pytest.fixture(scope="module")
def cfg():
    return load()


@pytest.fixture(scope="module")
def chain(cfg):
    return Chain(build_urdf(cfg))


def _flange(chain, q):
    """Flanschlage relativ zum Roboterfuss (Unterseite)."""
    poses = chain.fk_all(q)
    base = poses["base_link"]
    return np.linalg.inv(base) @ poses["gripper_base"]


# --- Konfiguration -----------------------------------------------------------

def test_config_every_value_has_source(cfg):
    quellen = set(cfg.raw["quellen"])
    for sect in ("arm", "achse7", "greifer"):
        for key, node in cfg.raw[sect].items():
            if key == "gelenke":
                for g in node:
                    assert g["src"] in quellen | {"annahme"}, (sect, g)
                continue
            assert isinstance(node, dict) and node.get("src") in quellen | {"annahme"}, (sect, key)


def test_config_masses_and_payload(cfg):
    assert sum(cfg.massen.values()) == pytest.approx(cfg.arm["masse_gesamt_kg"], abs=1e-9)
    assert cfg.arm["masse_gesamt_kg"] == 8.2 and cfg.arm["nutzlast_max_kg"] == 2.0
    assert 0 < cfg.greifer_masse < cfg.arm["nutzlast_max_kg"]
    assert cfg.nutzlast_test == pytest.approx(cfg.arm["nutzlast_max_kg"] - cfg.greifer_masse)


def test_config_derived_values_consistent(cfg):
    a, s, g = cfg.arm, cfg.achse7, cfg.greifer
    # Datenblatt: 252 + 237 + 297 + 126 = 912, 237 + 297 + 126 = 660
    assert a["j2_hoehe_m"] + a["oberarm_m"] + a["unterarm_m"] + a["hand_m"] == pytest.approx(a["hoehe_kerze_m"])
    assert a["oberarm_m"] + a["unterarm_m"] + a["hand_m"] == pytest.approx(a["reichweite_m"])
    assert s["laenge_m"] >= s["hub_m"] + s["schlitten_laenge_m"]
    assert g["tcp_ab_flansch_m"] == pytest.approx(g["koerper_laenge_m"] + g["finger_laenge_m"] / 2)
    assert g["koerper_breite_m"] >= g["max_oeffnung_m"] + 2 * g["finger_dicke_m"]
    assert cfg.min_oeffnung == pytest.approx(0.005)


# --- URDF --------------------------------------------------------------------

def test_urdf_structure(chain, cfg):
    assert chain.active == ["axis7"] + ARM_JOINTS + ["finger_left"]
    assert chain.by_name["axis7"].type == "prismatic"
    assert chain.by_name["axis7"].parent == "rail" and chain.by_name["axis7"].child == "carriage"
    fr = chain.by_name["finger_right"]
    assert fr.type == "prismatic" and fr.mimic == ("finger_left", 1.0, 0.0)
    assert np.allclose(fr.axis, -chain.by_name["finger_left"].axis)  # gespiegelt
    arm_mass = sum(chain.links[n].mass for n in ["base_link"] + [f"link_{i}" for i in range(1, 7)])
    assert arm_mass == pytest.approx(8.2)
    for name, link in chain.links.items():
        assert link.mass > 0, name
        assert link.boxes, f"{name} ohne Kollisionsquader"


def test_kette_kennt_schwerpunkt(chain, cfg):
    """Der Schwerpunkt jedes Glieds kommt aus ``<inertial><origin>`` (Standard: Quadermitte)."""
    a, g = cfg.arm, cfg.greifer
    assert chain.links["link_2"].com == pytest.approx([0, 0, a["oberarm_m"] / 2])
    assert chain.links["base_link"].com == pytest.approx([0, 0, a["j1_hoehe_m"] / 2])
    assert chain.links["gripper_base"].com == pytest.approx([0, 0, g["koerper_laenge_m"] / 2])
    assert chain.links["finger_left"].com == pytest.approx([0, 0, g["finger_laenge_m"] / 2])
    c = Chain('<robot name="r"><link name="a"><inertial><mass value="1"/></inertial></link></robot>')
    assert c.links["a"].com == pytest.approx([0, 0, 0])  # ohne origin: Link-Ursprung


def test_urdf_payload_link():
    cfg = load()
    c = Chain(build_urdf(cfg, payload_kg=cfg.nutzlast_test))
    assert c.links["payload"].mass == pytest.approx(cfg.nutzlast_test)
    assert not c.links["payload"].boxes
    tcp = np.linalg.inv(c.fk(c.zero(), "gripper_base")) @ c.fk(c.zero(), "payload")
    assert tcp[:3, 3] == pytest.approx([0, 0, cfg.greifer["tcp_ab_flansch_m"]])


def test_joint_limits_match_datasheet(chain):
    ds = {"joint1": (-179, 179), "joint2": (-80, 140), "joint3": (-80, 140),
          "joint4": (-179, 179), "joint5": (-95, 95), "joint6": (-179, 179)}
    for n, (lo, hi) in ds.items():
        j = chain.by_name[n]
        assert math.degrees(j.lower) == pytest.approx(lo) and math.degrees(j.upper) == pytest.approx(hi)
    assert (chain.by_name["axis7"].lower, chain.by_name["axis7"].upper) == (0.0, 1.0)
    assert chain.by_name["finger_left"].upper == pytest.approx(0.05)


# --- Vorwaertskinematik gegen Datenblattmasse --------------------------------

DS_POSES = [
    # (Name, Gelenkwerte, erwartete Flanschposition relativ zum Fuss [m]); Masse: Datenblatt
    ("Kerze: Gesamthoehe 912 mm", {}, (0.0, 0.0, 0.912)),
    ("J2 = 90 Grad: Reichweite 660 mm ab Gelenk 2 (Hoehe 252 mm)", {"joint2": D(90)}, (0.660, 0.0, 0.252)),
    ("J2 = 90, J3 = -90: Oberarm 237 waagrecht, Unterarm + Hand 423 senkrecht",
     {"joint2": D(90), "joint3": D(-90)}, (0.237, 0.0, 0.252 + 0.297 + 0.126)),
    ("J2 = 90, J5 = 90: Hand 126 senkrecht nach unten", {"joint2": D(90), "joint5": D(90)},
     (0.237 + 0.297, 0.0, 0.252 - 0.126)),
    ("J1 = 90, J2 = 90: Achse J1 zeigt nach -z (wie cpr_urdf)", {"joint1": D(90), "joint2": D(90)},
     (0.0, -0.660, 0.252)),
    ("J4/J6 drehen den gestreckten Arm nur um sich selbst", {"joint4": D(77), "joint6": D(-120)},
     (0.0, 0.0, 0.912)),
]


@pytest.mark.parametrize("name,vals,expect", DS_POSES, ids=[p[0][:20] for p in DS_POSES])
def test_fk_datasheet_poses(chain, name, vals, expect):
    t = _flange(chain, chain.q_from(vals))
    assert np.allclose(t[:3, 3], expect, atol=1e-6), (name, t[:3, 3])


def test_fk_axis7_moves_base_along_rail(chain):
    q0, q1 = chain.zero(), chain.q_from({"axis7": 0.73})
    d = chain.fk(q1, "gripper_base")[:3, 3] - chain.fk(q0, "gripper_base")[:3, 3]
    assert np.allclose(d, [0.73, 0, 0], atol=1e-9)


def test_fk_gripper_opening(chain, cfg):
    def opening(q):
        p = chain.fk_all(q)
        yl = p["finger_left"][1, 3] - cfg.greifer["finger_dicke_m"] / 2
        yr = p["finger_right"][1, 3] + cfg.greifer["finger_dicke_m"] / 2
        return yl - yr
    assert opening(chain.zero()) == pytest.approx(0.005)
    assert opening(chain.q_from({"finger_left": 0.05})) == pytest.approx(0.105)
    assert opening(chain.q_from({"finger_left": 0.02})) == pytest.approx(0.045)


# --- Abgleich mit der Hersteller-URDF (cpr_urdf) -----------------------------

# Werte aus igus_rebel_6dof_00.description.xacro (iRC_ROS @41701e6), Positionen
# der Gelenke im Elternframe und Nullpunktversatz gegen die Kerzenpose.
CPR = [  # (Gelenk, z [m], Nickwinkel im Ursprung [Grad], Achse)
    ("joint1", 0.100, 0.0, "0 0 -1"),
    ("joint2", 0.149, 30.0, "0 1 0"),
    ("joint3", 0.2384, 30.0, "0 1 0"),
    ("joint4", 0.119, 0.0, "0 0 1"),
    ("joint5", 0.170, -7.5, "0 1 0"),
    ("joint6", 0.1208, 0.0, "0 0 1"),
]
CPR_FLANGE_Z = 0.0012


def _cpr_urdf() -> str:
    parts = ['<robot name="cpr">', '<link name="l0"/>']
    for i, (n, z, pitch, ax) in enumerate(CPR, start=1):
        parts += [f'<link name="l{i}"/>',
                  f'<joint name="{n}" type="revolute"><parent link="l{i-1}"/><child link="l{i}"/>'
                  f'<origin xyz="0 0 {z}" rpy="0 {math.radians(pitch)} 0"/><axis xyz="{ax}"/>'
                  f'<limit lower="-7" upper="7" effort="1" velocity="1"/></joint>']
    parts += ['<link name="flange"/>',
              f'<joint name="f" type="fixed"><parent link="l6"/><child link="flange"/>'
              f'<origin xyz="0 0 {CPR_FLANGE_Z}"/></joint>', "</robot>"]
    return "".join(parts)


def _ds_to_cpr(q_arm):
    off = np.array([0.0, -30.0, -30.0, 0.0, 7.5, 0.0])
    return np.asarray(q_arm) + np.radians(off)


def test_cpr_limits_match_datasheet_after_offset():
    # cpr_urdf: J2/J3 +-110 Grad (11/18 pi), J5 -95+7,5 .. 95+7,5 Grad
    lo = _ds_to_cpr(np.radians([-179, -80, -80, -179, -95, -179]))
    hi = _ds_to_cpr(np.radians([179, 140, 140, 179, 95, 179]))
    assert np.degrees(lo[1:3]) == pytest.approx([-110, -110])
    assert np.degrees(hi[1:3]) == pytest.approx([110, 110])
    assert np.degrees([lo[4], hi[4]]) == pytest.approx([-95 + 7.5, 95 + 7.5])


def test_fk_deviation_against_cpr_urdf(chain, tmp_path):
    """Gleiche Pose (Kerzenkonvention -> cpr-Nullpunkt) in beiden Modellen.

    Abweichung kommt aus den Laengen (Datenblatt 252/237/297/126 gegen
    cpr 249/238,4/289/122); erwartet <= 14 mm, gemessen wird sie protokolliert.
    """
    cpr = Chain(_cpr_urdf())
    rng = np.random.default_rng(7)
    devs = []
    poses = [np.zeros(6)] + [np.array([rng.uniform(chain.lower[i], chain.upper[i]) for i in range(1, 7)])
                             for _ in range(200)]
    for qa in poses:
        q = chain.zero()
        q[1:7] = qa
        ours = _flange(chain, q)[:3, 3]
        theirs = cpr.fk(_ds_to_cpr(qa), "flange")[:3, 3]
        devs.append(float(np.linalg.norm(ours - theirs)))
    candle = devs[0]
    assert candle == pytest.approx(0.912 - 0.8984, abs=1e-6)  # 13,6 mm in der Kerze
    assert max(devs) < 0.016
    out = Path(os.environ.get("RAEUMWERK_TEST_OUT", tmp_path))
    out.mkdir(parents=True, exist_ok=True)
    (out / "fk_vs_cpr.json").write_text(json.dumps(
        {"kerze_mm": candle * 1e3, "max_mm": max(devs) * 1e3, "mittel_mm": float(np.mean(devs)) * 1e3,
         "posen": len(devs)}, indent=2))


def test_cpr_numbers_in_fetched_asset():
    """Nur wenn scripts/fetch_assets.sh gelaufen ist (RAEUMWERK_ASSETS)."""
    root = os.environ.get("RAEUMWERK_ASSETS")
    f = Path(root or "/nonexistent") / "irc_ros" / "urdf" / "igus_rebel_6dof_00.description.xacro"
    if not f.is_file():
        pytest.skip("Assets nicht geholt (scripts/fetch_assets.sh)")
    text = f.read_text()
    for s in ('xyz="0.0 0 0.100"', 'xyz="0.0 0 0.149"', 'xyz="0.0 0.0 0.2384"', "0.149 - 0.03",
              "0.14 + 0.03", 'xyz="0.0 0 0.1208"', 'xyz="0.0 0 0.0012"', "rpy=\"0.0 ${pi/6} 0.0\"",
              "rpy=\"0.0 ${-pi/24} 0.0\""):
        assert s in text, s


# --- Grenzen -----------------------------------------------------------------

def test_random_samples_respect_limits(chain):
    rng = np.random.default_rng(3)
    for _ in range(500):
        q = chain.random_q(rng)
        assert chain.within_limits(q)
    assert not chain.within_limits(chain.q_from({"joint2": D(141)}))
    assert not chain.within_limits(chain.q_from({"axis7": -0.001}))


# --- Inverse Kinematik -------------------------------------------------------

def _reachable_targets(chain, sc, n, seed, joints):
    rng = np.random.default_rng(seed)
    out = []
    while len(out) < n:
        q = chain.random_q(rng, joints)
        if sc.collisions(q):
            continue
        out.append(q)
    return out


def test_ik_roundtrip_6dof_pose(chain, cfg, tmp_path):
    """60 erreichbare, kollisionsfreie Zufallsposen (Lage + Orientierung des TCP)."""
    sc = SelfCollision(chain)
    tcp = (0.0, 0.0, cfg.greifer["tcp_ab_flansch_m"])
    rng = np.random.default_rng(11)
    errs, rots = [], []
    for q_true in _reachable_targets(chain, sc, 60, seed=5, joints=ARM_JOINTS):
        target = chain.fk(q_true, "gripper_base", tcp)
        q, pe, re, ok = chain.ik(target, "gripper_base", chain.zero(), ARM_JOINTS, offset=tcp, rng=rng)
        assert ok, (pe, re)
        assert chain.within_limits(q)
        t = chain.fk(q, "gripper_base", tcp)  # unabhaengig nachgerechnet
        errs.append(float(np.linalg.norm(t[:3, 3] - target[:3, 3])))
        rots.append(float(np.linalg.norm(rot_log(target[:3, :3] @ t[:3, :3].T))))
    assert max(errs) < 1e-3
    assert math.degrees(max(rots)) < 0.1
    out = Path(os.environ.get("RAEUMWERK_TEST_OUT", tmp_path))
    out.mkdir(parents=True, exist_ok=True)
    (out / "ik_6dof.json").write_text(json.dumps(
        {"punkte": len(errs), "max_pos_mm": max(errs) * 1e3, "max_rot_grad": math.degrees(max(rots))}, indent=2))


def test_ik_roundtrip_7axis_position(chain, cfg):
    """50 Zufallspunkte mit 7. Achse (redundant, nur Position)."""
    sc = SelfCollision(chain)
    tcp = (0.0, 0.0, cfg.greifer["tcp_ab_flansch_m"])
    use = ["axis7"] + ARM_JOINTS
    rng = np.random.default_rng(12)
    worst = 0.0
    for q_true in _reachable_targets(chain, sc, 50, seed=6, joints=use):
        target = chain.fk(q_true, "gripper_base", tcp)
        q, pe, _, ok = chain.ik(target, "gripper_base", chain.zero(), use, offset=tcp,
                                orientation=False, rng=rng)
        assert ok and chain.within_limits(q)
        worst = max(worst, float(np.linalg.norm(chain.fk(q, "gripper_base", tcp)[:3, 3] - target[:3, 3])))
    assert worst < 1e-3


# --- Reichweite als Huelle ---------------------------------------------------

def test_reach_envelope(chain, cfg):
    rng = np.random.default_rng(21)
    shoulder = chain.fk(chain.zero(), "link_2")[:3, 3]  # Gelenk 2 bei J1 beliebig auf der z-Achse
    r = []
    for _ in range(20000):
        q = chain.random_q(rng, ARM_JOINTS)
        r.append(np.linalg.norm(chain.fk(q, "gripper_base")[:3, 3] - shoulder))
    r = np.array(r)
    reach = cfg.arm["reichweite_m"]
    assert r.max() <= reach + 1e-9
    assert r.max() > 0.97 * reach  # Stichprobe kommt nah an den Rand
    # Ausserhalb der Huelle: IK findet nichts (Fehler >= Abstand zur Huelle)
    target = np.eye(4)
    target[:3, 3] = shoulder + np.array([0.70, 0.0, 0.0])
    _, pe, _, ok = chain.ik(target, "gripper_base", chain.zero(), ARM_JOINTS, orientation=False, restarts=5)
    assert not ok and pe == pytest.approx(0.70 - reach, abs=2e-3)
    # Am Rand (650 mm) erreichbar
    target[:3, 3] = shoulder + np.array([0.0, 0.65, 0.0])
    _, pe, _, ok = chain.ik(target, "gripper_base", chain.zero(), ARM_JOINTS, orientation=False)
    assert ok and pe < 1e-3


def test_reach_envelope_with_axis7(chain, cfg):
    use = ["axis7"] + ARM_JOINTS
    hub, reach = cfg.achse7["hub_m"], cfg.arm["reichweite_m"]
    shoulder_end = chain.fk(chain.q_from({"axis7": hub}), "link_2")[:3, 3]
    target = np.eye(4)
    target[:3, 3] = shoulder_end + np.array([0.64, 0.0, 0.0])
    _, pe, _, ok = chain.ik(target, "gripper_base", chain.zero(), use, orientation=False)
    assert ok and pe < 1e-3
    target[:3, 3] = shoulder_end + np.array([0.70, 0.0, 0.0])
    _, pe, _, ok = chain.ik(target, "gripper_base", chain.zero(), use, orientation=False, restarts=5)
    assert not ok and pe == pytest.approx(0.70 - reach, abs=2e-3)


# --- Selbstkollision ---------------------------------------------------------

SELF_COLLIDING = [
    # (Name, Gelenkwerte, Paar, das kollidieren muss)
    ("Unterarm zurueckgeklappt, Hand abgewinkelt: Greifer trifft link_1",
     {"joint3": D(140), "joint5": D(95)}, ("link_1", "gripper_base")),
    ("Oberarm waagrecht, Unterarm 140 Grad zurueck: Handgelenk im Fuss",
     {"joint2": D(90), "joint3": D(140)}, ("base_link", "link_5")),
]


def test_self_collision_free_poses(chain):
    sc = SelfCollision(chain)
    for vals in ({}, {"joint2": D(90)}, {"joint2": D(90), "joint3": D(-90)}, {"joint3": D(140)},
                 {"joint5": D(95)}, {"axis7": 1.0, "finger_left": 0.05}):
        assert sc.collisions(chain.q_from(vals)) == [], vals


@pytest.mark.parametrize("name,vals,pair", SELF_COLLIDING, ids=["greifer-link1", "hand-fuss"])
def test_self_collision_detected(chain, name, vals, pair):
    q = chain.q_from(vals)
    assert chain.within_limits(q)  # innerhalb der Grenzen, trotzdem Kollision
    hits = {(a, b): d for a, b, d in SelfCollision(chain).collisions(q)}
    assert pair in hits and hits[pair] > 0.005, (name, hits)


def test_self_collision_excludes_only_adjacent(chain):
    sc = SelfCollision(chain)
    assert ("link_1", "link_2") not in sc.pairs and ("link_1", "link_3") in sc.pairs
    assert ("finger_left", "finger_right") in sc.pairs  # Geschwister, nicht benachbart
    assert ("rail", "base_link") in sc.pairs
