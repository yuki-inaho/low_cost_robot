"""TDD tests for the study parts (studies/xl430_lowcost/parts).

Run: uv run pytest -q tests/test_parts.py

These pin the part-reconstruction behaviour. Per part <p> (shoulder_to_elbow,
elbow_to_wrist):
  - test_<p>_builds          : generates a watertight solid (手順5)
  - test_<p>_family_match     : C-A2 hole families == real part — in-face pattern
                                (count, dia Δ≤0.1mm, in-face center NN≤0.15mm). NOTE:
                                C-A2 compares the per-family in-FACE pattern; the axial
                                seat position is a separate concern (checked in the part
                                module's own inspect output), so this gate is in-plane.
  - test_<p>_xl430_clearance  : XL430 body clears its pocket/cradle (手順7, C-B1)

The study layer (`import domain`, part modules) is not an installed package, so we
inject its directory onto sys.path here (a conftest would also work).
"""
import sys
import importlib.util
import math
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parents[1]                                   # cad-reverse-parametric
_STUDY = _ROOT / "studies" / "xl430_lowcost"
_HW_STEP = _ROOT.parents[1] / "hardware/follower/step"

# Make `import domain` (used inside the part module) resolvable.
if str(_STUDY) not in sys.path:
    sys.path.insert(0, str(_STUDY))


def _load_part_module(name: str):
    spec = importlib.util.spec_from_file_location(
        f"{name}_part", _STUDY / "parts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _family_match(real_step: Path, recon_step: Path):
    """C-A2: family set equal, diameter Δ≤0.1mm, axis-line count equal, in-face center
    NN match ≤0.15mm. Returns (ok, report-list).

    Keys by (diameter@2dp, axis_dir@1dp) and GROUPS families per key into a list, so
    two near-equal-diameter families on the same axis (e.g. phi2.30 + phi2.34 along Z)
    are NEITHER merged nor silently dropped — a 1dp key would collide and a dict would
    overwrite, hiding a family (a false pass). Per key, families are matched greedily by
    axis-line count + center pattern."""
    from collections import defaultdict
    from cadre import cylinder_faces, checks
    real = cylinder_faces(real_step)["hole_families"]
    recon = cylinder_faces(recon_step)["hole_families"]

    def key(f):
        return (round(f["diameter"], 2), tuple(round(x, 1) for x in f["axis_dir"]))
    rb, cb = defaultdict(list), defaultdict(list)
    for f in real:
        rb[key(f)].append(f)
    for f in recon:
        cb[key(f)].append(f)

    report = []
    ok = set(rb) == set(cb)
    if not ok:
        report.append(f"family key set mismatch real={sorted(rb)} recon={sorted(cb)}")
    for k in rb:
        rfs, cfs = rb[k], cb.get(k, [])
        if len(rfs) != len(cfs):
            report.append(f"{k}: family count {len(rfs)} vs {len(cfs)}"); ok = False; continue
        remaining = list(cfs)
        for rf in rfs:
            best, bi = None, -1
            for i, cf in enumerate(remaining):
                if cf["axes"] != rf["axes"]:
                    continue
                m = checks.hole_pattern_match(rf["centers"], cf["centers"], tol_mm=0.15)
                if m.passed and (best is None or m.value < best.value):
                    best, bi = m, i
            if best is None:
                report.append(f"{k} axes={rf['axes']}: no center-matching recon family")
                ok = False
            else:
                dd = abs(rf["diameter"] - remaining[bi]["diameter"])
                fok = dd <= 0.1
                ok = ok and fok
                report.append(f"{k} axes={rf['axes']}: diaΔ={dd:.3f} centerNN={best.value} "
                              f"pass={fok}")
                remaining.pop(bi)
    return ok, report


def _brep_or_skip():
    from cadre import brep_available
    if not brep_available():
        pytest.skip("cadquery/OCP not available")


def _to_trimesh(model):
    """Tessellate a cadquery Workplane to a watertight trimesh.Trimesh via STL."""
    import tempfile
    import trimesh
    from cadre import parametric
    with tempfile.TemporaryDirectory() as td:
        stem = Path(td) / "m"
        parametric.export(model, stem, formats=("stl",))
        return trimesh.load(f"{stem}.stl", force="mesh")


def _export_step(model):
    """Export a model to a temp STEP and return the path (kept alive by caller's tmp)."""
    import tempfile
    from cadre import parametric
    td = tempfile.mkdtemp()
    stem = Path(td) / "recon"
    parametric.export(model, stem, formats=("step",))
    return Path(f"{stem}.step")


def _extension_features(mod):
    intent = mod.PartIntent.load(mod.INTENT)
    return {f.name: f for f in intent.features}


def _extension_profile_contains(feat, y: float, z: float) -> bool:
    beam = feat["link_beam"].constraints
    y0 = -73.046
    y1 = y0 + float(beam["link_length_y_mm"])
    in_beam = y0 <= y <= y1 and 0.0 <= z <= 23.0
    flange = feat.get("upstream_round_flange")
    if flange is None:
        return in_beam

    fc = flange.constraints
    cy, cz = [float(v) for v in fc["center_yz_mm"]]
    ry, rz = float(fc["radius_y_mm"]), float(fc["radius_z_mm"])
    in_flange = ((y - cy) / ry) ** 2 + ((z - cz) / rz) ** 2 <= 1.0 + 1e-9
    return in_beam or in_flange


def _extension_feature_specs(feat):
    horn = feat["upstream_horn_mount"].constraints
    idler = feat["idler_bores"].constraints
    specs = []
    for y, z in horn["diamond_centers_yz_mm"]:
        specs.append(("tap", float(y), float(z), float(horn["hole_diameter_mm"]) / 2.0))
    for y, z in idler["centers_yz_mm"]:
        specs.append(("idler", float(y), float(z), float(idler["diameter_mm"]) / 2.0))
    return specs


def _assert_functional_family(report, label, diameter, expected_centers, expected_axes):
    from cadre import checks

    families = [
        f for f in report["hole_families"]
        if abs(float(f["diameter"]) - diameter) <= 0.05
        and tuple(round(x, 1) for x in f["axis_dir"]) == (1.0, 0.0, 0.0)
    ]
    assert len(families) == 1, (
        f"{label}: expected one functional family d={diameter}, got {families}; "
        f"all_families={report['hole_families']}"
    )
    family = families[0]
    match = checks.hole_pattern_match(expected_centers, family["centers"], tol_mm=0.15)
    assert family["axes"] == expected_axes and match.passed, (
        f"{label}: axes/centers changed; expected_axes={expected_axes} "
        f"actual_axes={family['axes']} centerNN={match.value} faces={family['faces']} "
        f"expected_centers={expected_centers} actual_centers={family['centers']}"
    )
    assert family["faces"] >= family["axes"], (
        f"{label}: face count should remain auditable; family={family}"
    )


def test_shoulder_to_elbow_builds():
    """手順5: stage-1 reconstruction generates a watertight solid."""
    _brep_or_skip()
    import domain
    mod = _load_part_module("shoulder_to_elbow")
    model = mod.make_shoulder_to_elbow(domain.XL430, domain.XL330)
    mesh = _to_trimesh(model)
    assert mesh.is_watertight, "stage-1 reconstruction must be a closed solid"
    assert mesh.volume > 0


def test_shoulder_to_elbow_family_match():
    """手順6 / C-A2: reconstructed hole families == the real part's families
    (count, diameter Δ≤0.1mm, in-face center ≤0.15mm). Mesh-equiv C-A1 is NOT expected
    to pass (organic surface) — feature-level equivalence is the gate."""
    _brep_or_skip()
    real_step = _HW_STEP / "shoulder_to_elbow.step"
    if not real_step.exists():
        pytest.skip(f"real part missing: {real_step}")
    import domain
    mod = _load_part_module("shoulder_to_elbow")
    recon = _export_step(mod.make_shoulder_to_elbow(domain.XL430, domain.XL330))
    ok, report = _family_match(real_step, recon)
    assert ok, "C-A2 family mismatch:\n  " + "\n  ".join(report)


def test_shoulder_to_elbow_xl430_clearance():
    """手順7 / C-B1: after the XL430 swap, the downstream XL430 servo body clears the
    bracket (checks.envelope_clearance == 0 material inside the keepout).

    Geometry of THIS bracket (from the real part): the downstream tail is a flat tab
    X[-14.8,14.8], holes at x=-14.75 along X. The downstream servo (joint3) bolts onto
    the -X face of the tab and its body extends further -X — it is NOT cradled inside
    the bracket. So the keepout is the XL430 envelope placed on the -X side of the
    mount plane (offset outward by half the servo X-extent + the swap clearance). The
    bracket must not protrude into that body volume."""
    _brep_or_skip()
    import domain
    from cadre import checks, parametric
    mod = _load_part_module("shoulder_to_elbow")
    swapped = mod.make_shoulder_to_elbow(domain.XL430, domain.XL430)
    part_mesh = _to_trimesh(swapped)

    intent = mod.PartIntent.load(mod.INTENT)
    dn = {f.name: f for f in intent.features}["downstream_servo_mount"].constraints
    centers = dn["mount_centers_mm"]
    x_face = centers[0][0]                                 # -14.75 mount plane (along X)
    ys = [c[1] for c in centers]
    zs = [c[2] for c in centers]
    y_c, z_c = (min(ys) + max(ys)) / 2.0, (min(zs) + max(zs)) / 2.0
    env = domain.XL430.envelope
    clr = float(dn["clearance_mm"])
    # envelope_proxy maps env to box(w, d, h): X-extent = env.w (28.5). Servo body
    # extends -X from the mount face -> center it at x_face - clr - w/2.
    x_body = x_face - clr - env.w / 2.0
    keepout = parametric.envelope_proxy(env, clearance=0.0).translate((x_body, y_c, z_c))
    keep_mesh = _to_trimesh(keepout)

    res = checks.envelope_clearance(part_mesh, keep_mesh, samples=4000)
    assert res.passed, f"XL430 body intrudes into the bracket: {res.detail}"


# ---- elbow_to_wrist (joint3 motor cradle — the real XL330->XL430 swap) ----

def test_elbow_to_wrist_builds():
    """手順5: stage-1 reconstruction generates a watertight solid."""
    _brep_or_skip()
    import domain
    mod = _load_part_module("elbow_to_wrist")
    mesh = _to_trimesh(mod.make_elbow_to_wrist(domain.XL330))
    assert mesh.is_watertight, "stage-1 reconstruction must be a closed solid"
    assert mesh.volume > 0


def test_elbow_to_wrist_family_match():
    """手順6 / C-A2: reconstructed hole families == the real part (in-face pattern:
    count, dia Δ≤0.1mm, in-face center NN≤0.15mm). C-A1 mesh-equiv NOT expected."""
    _brep_or_skip()
    real_step = _HW_STEP / "elbow_to_wrist.step"
    if not real_step.exists():
        pytest.skip(f"real part missing: {real_step}")
    import domain
    mod = _load_part_module("elbow_to_wrist")
    recon = _export_step(mod.make_elbow_to_wrist(domain.XL330))
    ok, report = _family_match(real_step, recon)
    assert ok, "C-A2 family mismatch:\n  " + "\n  ".join(report)


def test_elbow_to_wrist_xl430_clearance():
    """手順7 / C-B1: after the XL330->XL430 swap, the XL430 motor body fits in the
    cradle cavity with zero bracket-material intrusion (envelope_clearance == 0 inside).

    Geometry: the motor is cradled between the two X side-rails, above the base plate
    (Z=0), output axis = Y. The keepout is the XL430 envelope placed in the cavity:
    centered in X over the footprint, lifted above the base plate, set back from the
    Y=42 end wall. The grown bracket must not pinch the (now larger) XL430 body."""
    _brep_or_skip()
    import domain
    from cadre import checks, parametric
    mod = _load_part_module("elbow_to_wrist")
    swapped = mod.make_elbow_to_wrist(domain.XL430)
    part_mesh = _to_trimesh(swapped)

    intent = mod.PartIntent.load(mod.INTENT)
    cr = {f.name: f for f in intent.features}["motor_cradle"].constraints
    clr = float(cr["clearance_mm"])
    wall = float(cr["wall_mm"])
    env = domain.XL430.envelope
    mw, mh, md = env.as_tuple()
    # envelope_proxy maps env(w,h,d) -> box(w, d, h): X-extent=w, Y-extent=d, Z-extent=h.
    foot_x = max(22.0, mw + 2 * (clr + wall))
    x_c = foot_x / 2.0                          # X centered in the footprint
    z_c = mod.BASE_T + clr + mh / 2.0           # Z-extent = h, lifted above base plate
    y_c = (mod.FACE_Y - mod.END_WALL_T) - clr - md / 2.0   # Y-extent = d, back off wall
    keepout = parametric.envelope_proxy(env, clearance=0.0).translate((x_c, y_c, z_c))
    keep_mesh = _to_trimesh(keepout)

    res = checks.envelope_clearance(part_mesh, keep_mesh, samples=4000)
    assert res.passed, f"XL430 motor body intrudes into the bracket: {res.detail}"


# ---- batch: the 4 peripheral parts (gripper static/moving, extension, rotation) ----
#
# Finding (honest): these parts mount on the servo HORN or are already wider than the
# servo body (and shoulder_rotation holds joint1 = XL430 already), so the XL330->XL430
# swap is a GEOMETRIC NO-OP for them — verified, not assumed. The real geometric swap
# burden was on shoulder_to_elbow (mixed connector) and elbow_to_wrist (joint3 cradle).
# Hence the per-part gates here are: builds + C-A2 family_match (the kinematic interface),
# plus, for swap-applicable parts, a recorded swap-effect (no silent change).

def _build_via(part_name, builder_attr, *args):
    import domain  # noqa: F401
    mod = _load_part_module(part_name)
    return mod, getattr(mod, builder_attr)(*args)


def test_gripper_static_part_builds():
    _brep_or_skip()
    import domain
    mod, model = _build_via("gripper_static_part", "make_gripper_static", domain.XL330)
    mesh = _to_trimesh(model)
    assert mesh.is_watertight and mesh.volume > 0


def test_gripper_static_part_family_match():
    _brep_or_skip()
    real = _HW_STEP / "gripper_static_part.step"
    if not real.exists():
        pytest.skip("real part missing")
    import domain
    mod, model = _build_via("gripper_static_part", "make_gripper_static", domain.XL330)
    ok, report = _family_match(real, _export_step(model))
    assert ok, "C-A2 mismatch:\n  " + "\n  ".join(report)


def test_gripper_static_part_swap_recorded():
    """C-B (swap evidence): the XL430 variant is generated; its geometric effect is
    measured. For this horn/jaw part the swap is a documented NO-OP (footprint already
    clears the XL430 body) — asserted explicitly so it cannot be silently misreported."""
    _brep_or_skip()
    import domain
    mod = _load_part_module("gripper_static_part")
    o = _to_trimesh(mod.make_gripper_static(domain.XL330))
    x = _to_trimesh(mod.make_gripper_static(domain.XL430))
    assert o.is_watertight and x.is_watertight
    assert abs(x.volume - o.volume) < 1.0, "swap unexpectedly changed geometry; update finding"


def test_gripper_moving_part_family_match():
    """gripper_moving reproduces the real OPEN-recess part (phi31 breaches the side
    walls, exactly as the real part's single open phi31 face) -> not watertight by
    design; family match (B-rep) is still the gate."""
    _brep_or_skip()
    real = _HW_STEP / "gripper_moving_part.step"
    if not real.exists():
        pytest.skip("real part missing")
    import domain
    mod, model = _build_via("gripper_moving_part", "make_gripper_moving", domain.XL330)
    ok, report = _family_match(real, _export_step(model))
    assert ok, "C-A2 mismatch:\n  " + "\n  ".join(report)


def test_gripper_moving_part_swap_recorded():
    _brep_or_skip()
    import domain
    mod = _load_part_module("gripper_moving_part")
    o = _to_trimesh(mod.make_gripper_moving(domain.XL330))
    x = _to_trimesh(mod.make_gripper_moving(domain.XL430))
    assert o.volume > 0 and x.volume > 0
    assert abs(x.volume - o.volume) < 1.0, "horn-only part: swap must be a no-op"


def test_elbow_to_wrist_extension_builds():
    _brep_or_skip()
    import domain
    mod, model = _build_via("elbow_to_wrist_extension", "make_extension", domain.XL330)
    mesh = _to_trimesh(model)
    assert mesh.is_watertight and mesh.volume > 0


def test_elbow_to_wrist_extension_family_match():
    _brep_or_skip()
    real = _HW_STEP / "elbow_to_wrist_extension.step"
    if not real.exists():
        pytest.skip("real part missing")
    import domain
    mod, model = _build_via("elbow_to_wrist_extension", "make_extension", domain.XL330)
    ok, report = _family_match(real, _export_step(model))
    assert ok, "C-A2 mismatch:\n  " + "\n  ".join(report)


def test_elbow_to_wrist_extension_upstream_flange_min_edge_distance():
    """The upstream support profile must contain a safety circle around each cut.

    This is intentionally a 2D YZ profile test: the upstream support is symmetric
    across X, while the blind seats are still cut from the existing +X source face.
    """
    mod = _load_part_module("elbow_to_wrist_extension")
    feat = _extension_features(mod)
    min_wall = float(feat["link_beam"].constraints["min_wall_mm"])
    failures = []
    samples = 144
    for kind, cy, cz, feature_r in _extension_feature_specs(feat):
        required_r = feature_r + min_wall
        misses = []
        for i in range(samples):
            a = 2.0 * math.pi * i / samples
            y = cy + required_r * math.cos(a)
            z = cz + required_r * math.sin(a)
            if not _extension_profile_contains(feat, y, z):
                misses.append((y, z))
        if misses:
            beam = feat["link_beam"].constraints
            y0, y1 = -73.046, -73.046 + float(beam["link_length_y_mm"])
            rect_margin = min(cy - y0 - feature_r, y1 - cy - feature_r,
                              cz - feature_r, 23.0 - cz - feature_r)
            my, mz = misses[0]
            failures.append(
                f"{kind} center_yz=({cy:.3f},{cz:.3f}) feature_r={feature_r:.3f} "
                f"required_radius={required_r:.3f} min_wall_threshold={min_wall:.3f} "
                f"current_rect_margin={rect_margin:.3f} "
                f"deficit_vs_threshold={min_wall - rect_margin:.3f} "
                f"first_outside=({my:.3f},{mz:.3f})"
            )
    assert not failures, "upstream flange/support min edge failures:\n  " + "\n  ".join(failures)

    flange = feat.get("upstream_round_flange")
    if flange is not None:
        import domain
        fc = flange.constraints
        cy, cz = [float(v) for v in fc["center_yz_mm"]]
        ry, rz = float(fc["radius_y_mm"]), float(fc["radius_z_mm"])
        solid = mod.make_extension(domain.XL330).val()
        bb = solid.BoundingBox()
        assert bb.ymax >= cy + ry - 0.05 and bb.zmin <= cz - rz + 0.05, (
            "upstream support profile is present in intent but not reflected in geometry; "
            f"bbox_ymax={bb.ymax:.3f} expected_at_least={cy + ry:.3f} "
            f"bbox_zmin={bb.zmin:.3f} expected_at_most={cz - rz:.3f}"
        )
        probe_x = 0.0
        solid_failures = []
        for kind, fy, fz, feature_r in _extension_feature_specs(feat):
            required_r = feature_r + min_wall
            for i in range(samples):
                a = 2.0 * math.pi * i / samples
                y = fy + required_r * math.cos(a)
                z = fz + required_r * math.sin(a)
                if not solid.isInside((probe_x, y, z), 1e-5):
                    solid_failures.append(
                        f"{kind} center_yz=({fy:.3f},{fz:.3f}) "
                        f"required_radius={required_r:.3f} "
                        f"outside_point=({y:.3f},{z:.3f}) probe_x={probe_x:.3f}"
                    )
                    break
        assert not solid_failures, (
            "upstream support safety circle is not inside actual solid geometry:\n  "
            + "\n  ".join(solid_failures)
        )


def test_elbow_to_wrist_extension_functional_families_preserved():
    """Functional cut families are checked separately from any new outer support profile."""
    _brep_or_skip()
    import domain
    from cadre import cylinder_faces

    mod = _load_part_module("elbow_to_wrist_extension")
    feat = _extension_features(mod)
    _, model = _build_via("elbow_to_wrist_extension", "make_extension", domain.XL330)
    report = cylinder_faces(_export_step(model))

    horn = feat["upstream_horn_mount"].constraints
    idler = feat["idler_bores"].constraints
    down = feat["downstream_mount"].constraints
    expected_diameters = {
        round(float(horn["hole_diameter_mm"]), 2),
        round(float(idler["diameter_mm"]), 2),
        round(float(down["hole_diameter_mm"]), 2),
    }
    actual_diameters = {round(float(f["diameter"]), 2) for f in report["hole_families"]}
    assert actual_diameters <= expected_diameters, (
        "unexpected cylindrical hole family appeared; "
        f"expected_diameters={sorted(expected_diameters)} "
        f"actual_diameters={sorted(actual_diameters)} "
        f"all_families={report['hole_families']}"
    )
    _assert_functional_family(
        report, "upstream taps", float(horn["hole_diameter_mm"]),
        [[0.0, float(y), float(z)] for y, z in horn["diamond_centers_yz_mm"]],
        expected_axes=4,
    )
    _assert_functional_family(
        report, "upstream idler seats", float(idler["diameter_mm"]),
        [[0.0, float(y), float(z)] for y, z in idler["centers_yz_mm"]],
        expected_axes=2,
    )
    _assert_functional_family(
        report, "downstream M2 through holes", float(down["hole_diameter_mm"]),
        [[float(x), float(y), float(z)] for x, y, z in down["mount_centers_mm"]],
        expected_axes=2,
    )


def test_elbow_to_wrist_extension_link_length_preserved():
    """C-B5: preserve the 90.1mm functional link dimension across the swap.

    The upstream support may intentionally grow the outer bbox in +Y/+Z; this gate
    pins the configured link length and the downstream/start-side functional extent.
    """
    _brep_or_skip()
    import domain
    mod = _load_part_module("elbow_to_wrist_extension")
    feat = _extension_features(mod)
    link_length = float(feat["link_beam"].constraints["link_length_y_mm"])
    o = _to_trimesh(mod.make_extension(domain.XL330))
    x = _to_trimesh(mod.make_extension(domain.XL430))
    assert abs(link_length - 90.1) < 0.001
    assert abs(o.bounds[0][1] - -73.046) < 0.2
    assert abs(x.bounds[0][1] - o.bounds[0][1]) < 0.2
    assert abs(x.bounding_box.extents[1] - o.bounding_box.extents[1]) < 0.2


def test_shoulder_rotation_builds_and_no_swap():
    """shoulder_rotation holds joint1 = XL430 already -> SWAP NOT APPLICABLE. Build
    stage-1 and assert the intent records swap_applicable: false (explicit, not silent)."""
    _brep_or_skip()
    import yaml
    mod = _load_part_module("shoulder_rotation")
    mesh = _to_trimesh(mod.make_shoulder_rotation())
    assert mesh.is_watertight and mesh.volume > 0
    doc = yaml.safe_load(Path(mod.INTENT).read_text())
    assert doc.get("swap_applicable") is False, "must explicitly mark swap not applicable"


def test_shoulder_rotation_family_match():
    _brep_or_skip()
    real = _HW_STEP / "shoulder_rotation.step"
    if not real.exists():
        pytest.skip("real part missing")
    mod, model = _build_via("shoulder_rotation", "make_shoulder_rotation")
    ok, report = _family_match(real, _export_step(model))
    assert ok, "C-A2 mismatch:\n  " + "\n  ".join(report)
