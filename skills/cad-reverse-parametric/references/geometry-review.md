# Reviewing geometry with executable evidence

Use this when reviewing a reconstruction or diagnosing a discrepancy between
passing tests and a browser view. Start from the source STEP, its generated
candidate, the part driver, and its intent file. Keep source files unchanged and
put review exports in a separate output directory so old artifacts do not become
evidence for new code.

## Surface geometry is not design intent

`cadre.cli inspect part.step` reports:

- `surface_sense`: concave, convex, or unknown, using face orientation on an
  outward-oriented solid. Convex cylinders include external bosses and rounded
  plate tops; concave cylinders are candidate bores or concave fillets.
- `axial_range_mm`: endpoints projected onto the sign-normalized cylinder axis
  through the global origin. Compare these to find separated coaxial features.
- `angular_span_deg`: extent of the trimmed surface; a partial cylindrical
  outside profile is not automatically a circular hole.
- `bore_families` and `outer_cylinder_families`: sense-separated summaries.
- `hole_families`: the older, unclassified summary, retained for compatibility.
  A matching result here does not prove that either model contains the same holes.

The cylinder's `axis_pt` may be far from the actual face. Family `centers` are
projected onto a perpendicular plane, intentionally discarding axial position.
Never use either as evidence of pocket depth or of a bore's entry face. Two faces
on one axis can be split faces, separate tabs, blind bores, or outside profiles.
Likewise a diameter-band label such as `M2-tap` is not evidence of a thread.

## Check an actual opening

For a proposed blind recess, verify all three against the B-rep:

1. A point just inside the stated entry face is void.
2. Points through the intended depth remain void.
3. Points behind the intended floor are material, with the required remaining wall.

Use cross-sections or rays for more complex shapes. Checking only a cylindrical
face's length can accept a completely buried cavity. For through features, checking
only the two endpoints can miss an intervening plug; inspect the complete path.

CadQuery's named `XZ` plane has normal **-Y**. Positive extrusion follows this
normal, not global +Y. When a helper accepts a world-axis direction, translate
that sign to the workplane normal. Test both directions on X, Y and Z with a
simple known solid before using the helper in a part.
Source: [CadQuery plane definitions](https://cadquery.readthedocs.io/en/latest/_modules/cadquery/occ_impl/geom.html).

## Browser verification

Use the dedicated Playwright session and local Chili3D workflow in
`chili3d_viewing.md`. Load the source, previous candidate and revised candidate
separately. Fit the content after setting a consistent viewport; compare the same
axis directions as well as an oblique view. Wait for the model tree entry and
canvases, not merely the page title or the end of a fixed sleep.

The DOM confirms loading and controls, not solid geometry. Inspect rendered views
and cross-check any claimed holes or seats against the numerical STEP evidence.
Treat smooth rendering, closed meshes, and zero browser errors as separate from
shape preservation, fit, and fabrication acceptance.

## Stop a false success

Run the existing tests before changing code, then add a regression that expresses
the physical failure. For a CLI, run the documented command in a fresh subprocess
without an inherited `PYTHONPATH`; tests that modify `sys.path` can hide broken
standalone execution.

Make a failed prerequisite visible in JSON and the exit code. Missing references
must not silently skip validation. Do not export a normal replacement when source
equivalence fails. An explicit diagnostic-export option may produce a distinctly
named prototype, but its failed status must remain failed. Mesh-printability checks
alone do not promote that prototype to a validated replacement.

## XL430 study example, 2026-09-18

The source `elbow_to_wrist.step` has convex phi18.124 rounded tops in two tabs at
Y[6.5,9.5] and Y[39,42]. The old driver interpreted these as one blind seat, while
its family comparison discarded the axial locations and material side. Its original
specification model was about 279% larger in volume than the source.

The corrected driver still contains that exploratory design hypothesis; it is
not an approved shape-preserving redesign. Review it with:

```bash
uv run python studies/xl430_lowcost/parts/elbow_to_wrist.py \
  --out outputs/review/elbow --samples 1000
# Expected today: status=blocked_non_equivalent, exit 2, no XL430 export.

uv run python studies/xl430_lowcost/parts/elbow_to_wrist.py \
  --out outputs/review/elbow-prototype --samples 1000 --export-prototype
# Still exit 2; emits *_xl430_prototype.step/stl for diagnosis only.

uv run pytest -q tests/test_geometry_review.py
```

These cases teach why family agreement and watertightness must not replace source
preservation. A later migration needs the actual mounting interfaces and an explicit
local change mask, followed by source-preservation and assembly-fit checks.
