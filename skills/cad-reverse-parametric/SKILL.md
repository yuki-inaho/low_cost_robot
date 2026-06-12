---
name: cad-reverse-parametric
description: >-
  Reverse-engineer STEP/STL CAD parts and reconstruct them parametrically with a
  uv + Python toolchain (CadQuery/OCP, trimesh). Use when asked to investigate
  CAD impact of a hardware change (e.g. swapping a servo/motor/bearing), recover
  mounting-hole patterns / axes / envelopes from STEP files without the original
  parametric source, build an equivalent-shape-first parametric model, or check
  geometric equivalence between an original and a reconstructed part. Triggers:
  "CAD逆エンジニアリング", "STEPをパース", "パラメトリック再構成", "CAD影響範囲",
  "穴パターン抽出", "同等性チェック", reverse engineer a STEP, parametric CAD swap.
---

# CAD Reverse-Parametric Toolkit (`cadre`)

Reverse-engineer existing CAD (STEP/STL) and rebuild it as a parametric model,
using only open Python libraries in a `uv` environment. Built for the workflow:
**measure the original → reconstruct an equivalent parametric shape → prove
equivalence → then change the parameter** (e.g. swap a servo).

## Architecture (SOLID / KISS / DRY)

Two layers. Keep them separate; never let domain terms leak into the core.

- **`src/cadre/` — generic core.** File-agnostic, domain-agnostic, reusable,
  portable. Knows geometry, not servos.
  - `geometry.py` — `Envelope`, `Component`, fit test, screw classification.
  - `probes.py` — 3 tiers: `step_text_probe` (no kernel), `stl_geometry_probe`
    (trimesh), `brep_probe` (CadQuery/OCP). Keyword policy is **injected**.
  - `parametric.py` — `envelope_proxy`, `clearance_pocket`, `adapter_plate`
    driven by `Envelope` + hole lists; STEP/STL export.
  - `equivalence.py` — mesh bbox/volume/surface-distance compare + verdict.
  - `checks.py` — functional/characterization checks: `axes_collinear`,
    `hole_pattern_match`, `envelope_clearance`.
  - `intent.py` — `PartIntent`/`Feature`: a human-readable YAML **design-intent
    layer** (the "latent": what each feature is for, what to preserve).
  - `descriptor.py` — compact structured descriptor + prompt for LLM intent
    labelling (extract with code, label intent with an LLM — not raw STEP).
  - `impact.py` — `analyze_tree` orchestrator; classifier is **injected**
    (`RuleClassifier`), dependency-inverted.
  - `report.py` — CSV + Markdown writers (title/intro injected).
  - `cli.py` — `python -m cadre.cli {probe,inspect,edges,edge-match,equiv,scaffold}`,
    works on ANY file. `inspect` dumps bbox (min/max) + every cylindrical face
    with its ABSOLUTE center — use it to answer placement questions ("is the bolt
    hole on the frame?") that the canonicalized `hole_families` centers can't.
    `edges`/`edge-match` bridge viewer selections back to B-rep edges.
- **`studies/<name>/` — specialized layer.** Thin. Supplies the domain: specs,
  keyword policy, classifier rules, drivers. `studies/xl430_lowcost/` targets the
  Dynamixel XL330→XL430 swap on this repo's `hardware/` tree.

> Rule of thumb: if a function names a servo or a part file, it belongs in a
> study, not in `cadre`.

## Setup

```bash
cd skills/cad-reverse-parametric
uv sync          # installs cadre (editable) + cadquery/OCP, trimesh, rtree, ezdxf
```

## The 3-tier probe (cheap → precise)

```bash
# Tier 1+3 on any STEP (text products/keywords + B-rep holes/axes/bbox):
uv run python -m cadre.cli probe path/to/part.step --brep

# Tier 2 on any STL (envelope, volume, watertight):
uv run python -m cadre.cli probe path/to/part.stl
```

Tier 1 (text) needs no CAD kernel — use it to triage hundreds of files fast.
Tier 3 (B-rep) recovers **mounting-hole families**: each is a (diameter, screw
class, axis direction, `axes`, `faces`, centers) group — the parametric drivers
for rebuilding the interface. `axes` = distinct axis lines (B-rep sign normalised,
split faces collapsed); `faces` = raw cylindrical faces. A single axis line can be
one through-hole or two coaxial blind holes, so the true hole count sits in
`[axes, faces]` — resolve from intent. Probes degrade gracefully without CadQuery.

## Resolve viewer-selected edges to B-rep meaning

When a browser/CAD viewer reports selected edge metadata (edge indexes, lengths,
endpoints, or an owning node), do not stop at the UI label. Resolve the selection
against STEP topology:

```bash
# Print specific edge records: length, curve type, endpoints, circle data,
# and adjacent face types (plane/cylinder/etc.).
uv run python -m cadre.cli edges path/to/part.step --indexes 48,49,0

# When viewer edge indexes do not match the standalone STEP traversal, match by
# measured lengths first, then confirm by coordinates and curve/surface type.
uv run python -m cadre.cli edge-match path/to/part.step \
  --lengths 9.146160652,2.265450228,3.091413309 --tolerance 0.01
```

Use this workflow for selection interpretation:

1. Record the viewer owner path/id, selected indexes, lengths, and endpoints.
2. If the selection came from an assembly, identify duplicate display names by
   owner id, tree order, STEP occurrence lines, and coordinate range. Never rely
   on a repeated display name such as `connector` alone.
3. Run `inspect` on candidate standalone STEP files to identify nearby hole
   families and absolute centers.
4. Run `edges` when viewer indexes map directly; otherwise run `edge-match`.
5. Classify each selected edge:
   - `circle` adjacent to `cylinder` = hole/seat rim.
   - `line`/`bspline` adjacent to a cylinder and a plane/surface = cut boundary
     or blend around a bore/seat.
   - `line`/`bspline` on only outer faces = outer profile/outline.
6. Report the conclusion as: selected owner, assembly occurrence, actual part
   STEP, local coordinate range, related hole family, edge classification, and
   design implication.

## Equivalent-shape-first reconstruction

1. **Measure** the original (tier 3) → hole pattern, axes, envelope.
2. **Reconstruct** parametrically with the *original* spec using `cadre.parametric`.
3. **Prove equivalence** before changing anything:
   ```bash
   uv run python -m cadre.cli equiv original.stl reconstructed.stl
   # verdict.equivalent must be true (bbox ≤0.5mm, surface max ≤0.5mm, vol ≤2%)
   ```
4. **Swap the parameter** (new `Envelope`/spec) and re-export STEP/STL.
5. **Interference-check** the new envelope proxy against neighbours.

See `references/workflow.md` for the full procedure and `references/servo_specs.md`
for the XL330/XL430 driver values (verify against the ROBOTIS e-Manual). To
visually inspect a STEP (reconstruction or original) in the browser CAD chili3d —
including how to rotate/pan/zoom and drive it headlessly — see
`references/chili3d_viewing.md`.

## Run an impact study

```bash
PYTHONPATH=studies/xl430_lowcost \
  uv run python studies/xl430_lowcost/run.py <parts_dir> --out outputs/impact
# -> step_impact.csv, stl_stats.csv, brep.json, IMPACT_REPORT.md
```

## Retargeting to another change

Copy `studies/xl430_lowcost/` to a new study, edit `domain.py` (the two
`Component`s, the `KeywordPolicy`, the classifier rules). The core is untouched.
