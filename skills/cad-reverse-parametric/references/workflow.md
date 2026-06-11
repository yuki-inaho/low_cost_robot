# Equivalent-shape-first parametric reconstruction workflow

The safe way to migrate a CAD part (e.g. XL330 → XL430 servo) is **not** to model
the new part from scratch. It is:

> rebuild the *existing* shape parametrically → prove it is geometrically
> equivalent to the original → only then change the driving parameter.

This keeps every change auditable: at step 3 you have a parametric model that
provably reproduces the original, so any later difference is attributable to the
parameter you intentionally changed.

## Stages and gates

| Stage | Action | Tool | Pass gate |
|------|--------|------|-----------|
| 0 Measure | Extract envelope, hole families, axes, bores from the original STEP | `cadre.cli probe --brep` / `brep_probe` | report produced; hole families look physical |
| 1 Reconstruct | Rebuild the part parametrically with the **original** spec | `cadre.parametric` + part script | model builds, exports STEP/STL |
| 2 Equivalence | Compare reconstruction vs original | `cadre.cli equiv` | `verdict.equivalent == true` (bbox ≤0.5mm, surface max ≤0.5mm, vol ≤2%) |
| 3 Swap | Change the `Envelope`/spec to the new servo, re-export | part script | builds; parameters propagate |
| 4 Interference | Check the new envelope proxy against neighbours | `cadre.parametric.envelope_proxy` + boolean | no overlap with adjacent links |
| 5 Print check | Wall thickness, screw seats, axis alignment | `stl_geometry_probe` + manual | physical fit on the bench |

## What "measure" recovers (real data from this repo)

`brep_probe` on `hardware/follower/step/shoulder_to_elbow.step`
(the part whose STEP PRODUCT name is literally `XL430 to XL330 new connector`):

| family | diameter | screw | axes | faces | axis dir | meaning |
|---|---|---|---|---|---|---|
| 1 | ~2.4 mm | M2 | 4 | 8 | X | motor mounting cross, 4 axis lines across two walls |
| 2 | ~2.3 mm | M2 | 2 | 4 | X | second mounting set (through both walls) |
| 3 | ~26 mm | — | 1 | 2 | X | motor-body-facing bore / boss |
| 4 | ~10 mm | — | 1 | 2 | X | horn / idler shaft bore |

`axes` = distinct axis lines (sign-normalised, face-splitting collapsed); `faces`
= raw cylindrical faces. **One axis line may be a single through-hole OR two
coaxial blind holes on opposing walls — cylinder geometry alone can't decide, so
the physical hole count is in `[axes, faces]`.** These families ARE the parametric
drivers. Re-creating the part means parameterising: `motor_face_hole_pattern`,
`hole_diameter`, `body_bore`, `horn_bore`, `axis_spacing`, `link_length`, `wall`.

## Mapping the drivers to a servo swap

Because hole pattern, bore and axis offset were *measured*, swapping XL330→XL430
is a parameter edit, not a redesign:

- `body_bore`, `clearance_pocket` ← new `Envelope(28.5, 46.5, 34.0)`
- `hole_diameter`, `hole_pattern` ← XL430 mount screw (verify M2.5 vs M2) and pitch
- `horn_bore`, `axis_offset` ← XL430 horn/idler interface
- `wall`, `link_length` ← re-check against the ×3.18 mass / ×3.57 torque increase

## Why equivalence is checked on the mesh, not the B-rep

Two independently-built B-reps are almost never topologically identical (face
counts differ), so exact CAD equality is the wrong test. Sampled **surface
distance + bbox + volume** is robust to remeshing and tessellation and answers
the real question: *does it occupy the same space to within print tolerance?*

## Reuse

Stages 0, 2, 4, 5 are generic (`cadre`). Only stage 1/3 part scripts and the
servo numbers are study-specific (`studies/xl430_lowcost/domain.py`).
