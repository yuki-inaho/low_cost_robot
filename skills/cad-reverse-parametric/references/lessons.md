# Lessons: building & using this skill (struggles / findings / tips / improvements)

Captured from the first real run (XL330→XL430 impact on low_cost_robot) so the
skill keeps improving itself.

## Struggles (what bit us)

1. **Python/OCP wheels.** CadQuery's OCP has no cp3.13 wheels; the host project
   env was 3.13. Fix: pin this skill to `>=3.11,<3.13` (`.python-version` 3.12).
   Lesson: a portable CAD skill must pin Python, not inherit the caller's.
2. **Hidden runtime dep.** `trimesh.nearest.on_surface` needs `rtree`, not pulled
   in by `trimesh` core — equivalence crashed only at call time. Declare it.
3. **B-rep grouping is deceptively hard.** First version grouped cylinders by
   `(radius, raw_axis_dir)` and reported face counts as hole counts. Wrong on two
   axes: (a) the B-rep axis sign is arbitrary → one bolt circle can split in two;
   (b) a through-hole becomes several collinear faces → counts inflate (verified:
   `elbow_to_wrist` d=2.0 → 8 faces but 4 axis lines). Adversarial review caught it.
4. **Spec drift.** Hard-coded values were off: XL330 stall torque 0.42 (correct
   0.52 N·m @5V), XL430 mount screw "M2.5" (case mounting is **M2**; M2.5 is the
   frame/horn kit), XL430 torque 1.5 (that's @12V; @11.1V nominal it's 1.4).
5. **Wrong metric for the shape.** "Does the servo fit *inside* the part bbox" is
   ~always False for open brackets and is NOT the swap criterion — confusing until
   reframed as an enclosure-only signal.
6. **Layering crept.** First cut mixed generic probing with servo specifics in
   flat scripts; had to refactor into `cadre` core + `studies/` after the
   generic-first instruction. Cheaper to separate from the start.

## Findings (what's true about this data)

- STEP is plain text: `PRODUCT(...)`, keyword hits and `CYLINDRICAL_SURFACE`
  radii are greppable with no CAD kernel. This alone confirmed the key fact —
  `follower/shoulder_to_elbow.step` PRODUCT name is literally
  `XL430 to XL330 new connector` — making it the unique **direct**-impact part.
- B-rep radii/axes/centers are exact and reproducible (re-run matched byte-for-byte).
  The trustworthy invariant is the **axis line**, not a "hole count".
- Same-named parts differ: follower vs leader `shoulder_to_elbow.step` are
  different geometries (44×132×26 "connector" vs 15.6×35×120 "Servo Connector
  redesign"). Never reason by filename alone — use path + PRODUCT + bbox.
- Envelope grows ×1.3–1.4/axis (+8…+12.5 mm); mass ×3.18; the height +12.5 mm is
  the tightest constraint on short links.

## Tips (what worked, reuse these)

- **3-tier triage**: text (free) → mesh (cheap) → B-rep (kernel). Classify
  hundreds of files by text first; only B-rep the suspects.
- **Equivalence on the mesh**, not exact B-rep equality: bbox + sampled surface
  distance + volume is robust to remeshing/tessellation and answers the real
  question (same space within print tolerance).
- **Inject the domain**: keyword policy + classifier + specs live in the study,
  never in `cadre`. Same primitives emit XL330 *or* XL430 by swapping a `Component`
  (proven: 29×54.5×39 vs 37.5×68.75×51.5).
- **Adversarially verify** your own extraction (independent re-run + skeptical
  reading). It found a real bug and three spec errors here — highest ROI step.

## Design-intent layer (added after the advisory review)

The robust methodology is **semi-automatic refactoring**, framed like an
autoencoder but with a *human-readable* latent: B-rep extraction → a YAML
design-intent graph (`cadre.intent.PartIntent`) → CadQuery reconstruction →
TDD diff/function checks (`cadre.checks`). LLMs label *intent* from a structured
descriptor (`cadre.descriptor`), never from raw STEP. See `research_context.md`
for the related work (DeepCAD, CAD-Recode, UV-Net, SolidGen, Vitruvion, …) and
why fully-automatic STEP→clean-parametric is still hard (intent isn't in the
geometry; constraints are hard; B-rep topology is unstable).

## Session 2 (browser viewing + placement verification)

Struggles → fixes that became skill features:
- **Canonical centers lose absolute position.** The M-1 perp-foot fix made
  `hole_families.centers` great for *matching* but unable to answer "is this bolt
  hole on the frame / where is it?" — I had to write a throwaway script. Fixed by
  adding `cylinder_faces()` + `cadre.cli inspect`: bbox min/max + every face's
  ABSOLUTE center + the family summary. Verified on the real connector
  (M2 cross at ±8 around the φ10 bore inside the φ26 horn seat, on the wall ring).
- **No B-rep integration test.** Added one: generate a holed plate → recover the
  4 holes' absolute centers. Closes the long-standing gap.
- **chili3d exposes no JS app handle** (`window` has no app/view) — 3D geometry is
  canvas/WASM, not DOM. So geometry questions must go through B-rep on the STEP,
  not the browser; the DOM only yields the part-name tree.
- **playwright-cli `eval` misparses `=>`** — wrap as `() => (...)`. Documented in
  `chili3d_viewing.md`.
- **playwright-cli sessions collide across projects** (a shared `default` picked up
  another project's `sam2-cvat` profile). Use a dedicated `-s=<name>` session.
- **Visual verification recipe that worked:** load the *isolated* part (not the
  assembly — neighbours occlude + wireframe see-through confuses), snap to an axis
  via the gizmo, screenshot, and cross-check the circles/holes against
  `cadre.cli inspect` numbers. A "counterbore that looks clipped" was just the
  φ26 seat spanning the full 26 mm thickness + Solid+Wireframe see-through — not a
  defect.

## Improvement backlog (next iterations)

- [x] Design-intent layer + functional checks + LLM descriptor (intent/checks/descriptor).
- [x] `make_connector(upstream, downstream)` — equivalent-shape then swap, one arg.
- [ ] Resolve through-hole vs coaxial-blind ambiguity by ray-casting the axis
      against solid walls (count boundary crossings) → true physical hole count.
- [ ] Independent 2D cross-check: reuse the sandbox `export_dxf` + `parse_dxf` to
      confirm hole centers from sections against the 3D B-rep families.
- [x] Visual inspection of STEP (reconstruction + original) in browser CAD chili3d,
      driven headlessly via playwright-cli — see `chili3d_viewing.md` (incl. the
      Node ≥20.11 gotcha and rotate/pan/zoom controls).
- [ ] Automated visual diff (overlay original vs reconstruction) for the gate.
- [ ] `min_wall_thickness` check (medial-axis / ray sampling) — currently a named
      test in intent YAML but not yet implemented in `cadre.checks`.
- [ ] Replace the assembly size heuristic with a real check (count
      `NEXT_ASSEMBLY_USAGE_OCCURRENCE` / `PRODUCT` entities).
- [ ] Auto-compute hole pitch/spacing (we expose centers; derive pitch).
- [ ] Close the loop empirically: a full stage-1 reconstruction of one real part
      passing the equivalence gate (not just the interface primitive).
