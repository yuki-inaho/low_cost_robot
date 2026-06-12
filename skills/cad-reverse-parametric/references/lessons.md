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

## Session 3 (agent-team workdoc execution: XL430 migration)

Run via start-work-audit-pattern (coordinator + persistent worker + auditor) against the
XL430 migration workdoc. Findings worth feeding back into the skills:
- **F-1 (`check_simulation.py --json`)**: numpy scalar comparisons (`x <= LIMIT`) yield
  `numpy.bool_`, which `json.dumps` rejects (`TypeError: ... bool not serializable`; the name
  reads as plain "bool" in numpy 2.x, misleading). FIX/RULE: any JSON-emitting tool must pass
  `json.dumps(..., default=lambda o: o.item() if hasattr(o,"item") else str(o))`. Consider
  baking this into a `cadre` JSON helper so new tools inherit it.
- **F-5 (intent vs reality drift)**: a `<part>.yaml` declared `motor_body_bore.through: true`
  while the implementation/`inspect` showed a blind 3 mm counterbore (φ26 = 2 wall faces, φ10
  single axis). The C-B8 through/blind *declaration* must be cross-checked against the built
  geometry — a declaration the part doesn't honour is worse than none. TIP: add an automated
  check that the YAML `through` flag matches the recovered axes/faces topology.
- **C-A2 is the right gate for organic parts; C-A1 is not.** Mesh-distance equivalence (C-A1)
  fails on Fusion-organic originals (surface max ~19 mm here) AND `volume_delta` is `None`
  because the shipped `hardware/follower/stl/*.stl` are **non-watertight**. Feature-level
  equivalence (C-A2: hole families, dia Δ, center NN) passed exactly (NN=0.0). RULE: gate on
  C-A2; document the C-A1 gap; don't trust volume on these STLs (repair or compare STEP).
- **C-A2 compares the in-plane pattern only** (families keyed by radius+axis-dir; axial
  position is NOT compared — that belongs to C-B5/C-B7). State this in any equivalence report
  so "NN=0" is not over-read as full 3D coincidence.
- **Counterbore modeling**: a φ26 seat tangent to a wall edge produces a degenerate
  (non-manifold) mesh; give the wall ≥ seat+6 mm. And a seat depth (3 mm) into a thin wall
  (4 mm) leaves 1 mm floor < typical 2.5 mm min-wall — counterbore depth must be checked
  against wall thickness (manufacturability).
- **Tip (agent team)**: persistent subagents are resumed by **agentId** (from the spawn
  result), not by the `name=` — SendMessage to the name fails once the task completes.
- **F-6 (silent no-op on resume)**: a SendMessage to a persistent auditor returned
  "resumed in background" but produced **no output** (its transcript stayed at the
  previous task). Before depending on a delegated result, **verify progress** (output
  file mtime / last event); on a silent no-op, do NOT wait implicitly — run the check
  directly and record the delegation failure explicitly. Coverage rule that worked:
  spend the auditor's independent eye on *substantive* artifacts (the 2 real swaps +
  the regression); peripheral NO-OP / not-applicable parts can be coordinator-verified
  (tests + md5 identity) when delegation is flaky.
- **Section measurement is a bug detector.** The cq `section()`/BREP ray measurement done
  "merely" to confirm the C-B4 floor (workdoc_Jun12 completion pass) exposed two REAL
  implementation bugs in `shoulder_to_elbow.py`: a sign error in the wall placement
  (`sx*wx - sx*wall_t/2` put the -X wall at x=-13.5 instead of the symmetric ±19, leaving
  its φ26 seat ~outside the material) and the counterbore being cut from a nominal plane
  rather than each wall's actual outer face. RULE: actually *measuring* a dimensional DoD
  (instead of trusting the parameter arithmetic, wall−depth=floor) is implementation
  verification, not box-ticking — budget for it on every min-wall / seat-depth claim.

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
