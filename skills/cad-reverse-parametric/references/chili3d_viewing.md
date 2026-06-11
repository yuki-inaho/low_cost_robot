# Viewing STEP in chili3d (browser CAD) + navigation controls

chili3d (https://github.com/xiangechen/chili3d) is a browser-based CAD (OCCT
compiled to WASM + Three.js). It's a convenient viewer to *visually* inspect a
reconstructed or original STEP from this skill, and it can be driven headlessly
with `playwright-cli`. All facts below were verified against the source.

## Setup

```bash
git clone --depth 1 https://github.com/xiangechen/chili3d.git
cd chili3d
npm install            # prebuilt WASM ships in packages/wasm/lib (15 MB) — no Emscripten needed
```

> **Node ≥ 20.11 required.** rspack 2.x uses `import.meta.dirname`, which is
> `undefined` on Node 20.9 and crashes `npm run dev`/`build` with
> `TypeError: path argument must be of type string`. Use e.g. nvm v20.20.0:
> `PATH=$HOME/.nvm/versions/node/v20.20.0/bin:$PATH npm run dev`

## Load a STEP and render it

The dev server serves `public/` at the web root, and the web entry reads a
`?url=` / `?model=` param → `loadFileFromUrl` → `importFiles`.

```bash
cp my_part.step chili3d/public/            # served at /my_part.step
PATH=$HOME/.nvm/versions/node/v20.20.0/bin:$PATH npm run dev   # → http://localhost:8080
```

Open `http://localhost:8080/?url=/my_part.step`. Import formats (OCCT):
`.step .stp .iges .igs .brep .stl`. An assembly STEP (e.g. `arm.step`) loads as a
nested tree and renders fully assembled.

### Headless via playwright-cli

```bash
playwright-cli open "http://localhost:8080/?url=/my_part.step"
sleep 10                                   # WASM init + STEP parse + tessellation
playwright-cli console                     # expect 0 errors (activeView/ReadPixels warnings are benign)
playwright-cli screenshot --filename=view.png
```

## Navigation controls (how to rotate / pan / zoom)

All **mouse** view-nav requires the **middle (wheel) button held** — left/right
drag does NOT orbit. pan-vs-rotate depends on `Config.instance.navigation3D`:

| style | pan | rotate |
|---|---|---|
| **Chili3d (default)** / Revit | Middle drag | **Shift + Middle drag** |
| Blender / Creo | Shift + Middle drag | **Middle drag** |
| Solidworks | Ctrl + Middle drag | Middle drag |

- **Easiest rotate (no middle button):** left-drag the **axis gizmo** at the
  top-right corner — `viewGizmo` orbits the camera on left-drag. Works on trackpads.
- **Zoom:** mouse wheel. **Touch:** 3 fingers = rotate, 2 fingers = pan/zoom.
- Right-side viewport toolbar (top→bottom): solid / wireframe / **fit-to-frame** /
  zoom-in / zoom-out.

Driving rotate headlessly (gizmo left-drag) with playwright-cli:

```bash
playwright-cli mousemove 1210 235      # over the top-right axis gizmo
playwright-cli mousedown
for p in "1180 260" "1150 285" "1120 305"; do playwright-cli mousemove $p; done
playwright-cli mouseup
playwright-cli screenshot --filename=rotated.png
```

## Structured (DOM) inspection via playwright-cli

The 3D shapes live in canvas/WASM (not the DOM) and chili3d exposes no `window`
app handle, so `eval` only reaches the **UI chrome** (the Items tree, ribbon,
properties). For geometry, use the B-rep probe on the STEP instead.

**eval gotcha + robust form.** `playwright-cli eval "<expr>"` misparses any bare
expression that contains an arrow `=>` (e.g. `.map(x => x)`) as a function and
fails with `TypeError: result is not a function`. **Always wrap as a no-arg
function** so the inner arrows are safe:

```bash
# WRONG (inner => breaks it):
playwright-cli eval "document.body.innerText.split('\n').map(s=>s.trim())"
# RIGHT — wrap as () => (...):
playwright-cli eval "() => document.title"
playwright-cli eval "() => { const L=document.body.innerText.split(String.fromCharCode(10)).map(s=>s.trim()).filter(Boolean); const i=L.indexOf('Items'); return JSON.stringify(L.slice(i+1,i+11)); }"
# -> ["assembled_arm.step","Robot Arm v14","XL-430_new v1","DC11_A01_DUMMY",...]
```

Rule of thumb: pass `() => (<expression>)` (or `() => { ...; return x; }`); use
`String.fromCharCode(10)` instead of a literal `\n` in the shell; check
`() => Object.keys(window)` first (it's `[]` here — no exposed app handle).

**Use a dedicated session.** The shared `default` session can collide with other
projects' browsers — drive chili3d with `playwright-cli -s=chili ...`.

## Visual verification recipe (does my geometry claim hold?)

To confirm a claim about holes/recesses against the actual model:

1. Load the **isolated part**, not the assembly (`?url=/<part>.step`) — neighbours
   occlude and the Solid+Wireframe overlay shows back-side circles through the
   solid, which reads as "clipped/extra" geometry.
2. Snap to an axis: left-click the matching ball on the **top-right view gizmo**
   (looking down the hole axis shows the bolt circle + bores face-on).
3. Screenshot, then **cross-check against numbers**: `cadre.cli inspect <part>.step`
   gives bbox + every hole's absolute center. Eyeball ⇄ B-rep must agree.

Worked example: the "XL430 to XL330 connector" face-on showed φ10 bore + φ26 seat
+ a 4× M2 cross at radius 8 — matching `inspect` exactly. The "clipped counterbore"
was just the φ26 seat spanning the full 26 mm thickness + the wireframe see-through,
not a defect.

## Why this matters here

Closes the reconstruction loop: build a parametric STEP with `cadre.parametric`
→ drop it in `chili3d/public/` → eyeball it (and the original) in chili3d
alongside the numeric `cadre.cli equiv` gate. See also `workflow.md`.
