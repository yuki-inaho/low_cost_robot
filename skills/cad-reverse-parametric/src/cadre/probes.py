"""Generic, file-driven probes. Domain-agnostic: nothing about servos here.

Three tiers, increasing cost / increasing fidelity:
  1. step_text  - parse STEP as ISO-10303 text (no CAD kernel)
  2. stl_mesh   - mesh stats via trimesh
  3. brep       - B-rep faces / cylinders via CadQuery+OCP (optional dependency)

A `KeywordPolicy` (category -> regex) is *injected*, so the same probe serves
any domain. The XL430 study supplies a Dynamixel policy; nothing is hard-coded.
"""
from __future__ import annotations
import re
from pathlib import Path
from dataclasses import dataclass

from .geometry import classify_screw, DEFAULT_SCREW_BANDS

# ---------------------------------------------------------------- tier 1: text

# ISO 10303-21 permits whitespace between tokens; tolerate it for portability
# across STEP exporters (Fusion is tight, others are not).
_PRODUCT = re.compile(r"PRODUCT\s*\(\s*'([^']*)'")
_CYL_RADIUS = re.compile(
    r"CYLINDRICAL_SURFACE\s*\(\s*'[^']*'\s*,\s*#?\d+\s*,\s*([0-9.eE+-]+)\s*\)")


@dataclass(frozen=True)
class KeywordPolicy:
    """Maps a category label to a regex; injected into text probing/classification."""
    patterns: dict[str, str]

    def compiled(self) -> dict[str, re.Pattern]:
        return {k: re.compile(v, re.I) for k, v in self.patterns.items()}


def step_text_probe(path: Path, policy: KeywordPolicy | None = None) -> dict:
    text = Path(path).read_text(errors="replace")
    products = sorted(set(_PRODUCT.findall(text)))
    radii: dict[float, int] = {}
    for r in _CYL_RADIUS.findall(text):
        v = round(float(r), 3)
        radii[v] = radii.get(v, 0) + 1
    keywords = {}
    if policy:
        keywords = {k: len(rx.findall(text)) for k, rx in policy.compiled().items()}
    return {
        "file": str(path),
        "name": Path(path).stem,
        "products": products,
        "keywords": keywords,
        "counts": {
            "advanced_face": text.count("ADVANCED_FACE"),
            "cylindrical_surface": text.count("CYLINDRICAL_SURFACE"),
            "closed_shell": text.count("CLOSED_SHELL"),
            "circle": len(re.findall(r"\bCIRCLE\(", text)),
        },
        "cylinder_radii": sorted(radii.items()),
    }


# ---------------------------------------------------------------- tier 2: mesh

def stl_geometry_probe(path: Path) -> dict:
    import trimesh
    mesh = trimesh.load(path, force="mesh")
    ext = mesh.bounding_box.extents
    return {
        "file": str(path),
        "name": Path(path).stem,
        "bbox_mm": [round(float(x), 3) for x in ext],
        "volume_mm3": round(float(mesh.volume), 2) if mesh.is_volume else None,
        "area_mm2": round(float(mesh.area), 2),
        "triangles": int(len(mesh.faces)),
        "watertight": bool(mesh.is_watertight),
        "centroid_mm": [round(float(x), 3) for x in mesh.centroid],
    }


# ---------------------------------------------------------------- tier 3: brep

def brep_available() -> bool:
    try:
        import cadquery  # noqa: F401
        from OCP.BRepAdaptor import BRepAdaptor_Surface  # noqa: F401
        return True
    except Exception:
        return False


def _round3(v) -> list[float]:
    return [round(float(x), 3) for x in v]


def _canonical_dir(d, tol: float = 1e-6) -> tuple[float, ...]:
    """B-rep cylinder axis sign is arbitrary; canonicalize so ±dir compare equal."""
    dd = list(d)
    for x in dd:
        if abs(x) > tol:
            if x < 0:
                dd = [-c for c in dd]
            break
    return tuple(round(c, 3) for c in dd)


def _perp_foot(pt, u) -> tuple[float, ...]:
    """Component of pt perpendicular to unit axis u — identifies the axis *line*
    independent of where along it a (possibly split) face sits."""
    dot = sum(p * c for p, c in zip(pt, u))
    return tuple(round(p - dot * c, 1) for p, c in zip(pt, u))


def group_cylinder_holes(cylinders: list[dict],
                         screw_bands=DEFAULT_SCREW_BANDS) -> list[dict]:
    """Group raw cylindrical *faces* into distinct *axis lines*, then into families
    by (radius, canonical axis direction).

    Reports the only invariant we can extract reliably:
      - `axes`  : distinct axis lines (radius + direction + perpendicular foot),
                  collapsing the arbitrary B-rep sign and any face splitting.
      - `faces` : raw cylindrical-face tally (transparency).

    NOTE: one axis line may be a single through-hole OR two coaxial blind holes on
    opposing walls — cylinder geometry alone cannot tell them apart. So physical
    hole count lies in [axes, faces]; resolve it from intent/solid analysis.
    """
    axes: dict[tuple, dict] = {}
    for c in cylinders:
        u = _canonical_dir(c["axis_dir"])
        foot = _perp_foot(c["axis_pt"], u)
        key = (c["radius"], u, foot)
        # center = canonical foot of the axis line (frame-stable: independent of
        # which wall / split face we hit), so two probes of the same pattern match.
        a = axes.setdefault(key, {"radius": c["radius"], "axis_dir": list(u),
                                  "center": list(foot), "faces": 0})
        a["faces"] += 1
    families: dict[tuple, list] = {}
    for a in axes.values():
        families.setdefault((a["radius"], tuple(a["axis_dir"])), []).append(a)
    return [
        {"radius": r, "diameter": round(2 * r, 3),
         "screw": classify_screw(2 * r, screw_bands), "axis_dir": list(u),
         "axes": len(group), "faces": sum(a["faces"] for a in group),
         "centers": [a["center"] for a in group]}
        for (r, u), group in sorted(families.items(), key=lambda kv: -len(kv[1]))
    ]


def _open_solids(path: Path):
    import cadquery as cq
    return cq.importers.importStep(str(path)).solids().vals()


def _bbox_minmax(solids) -> dict:
    bb = solids[0].BoundingBox()                 # bbox over ALL solids (wp.val() = first only)
    for s in solids[1:]:
        bb.add(s.BoundingBox())
    return {"xmin": round(bb.xmin, 3), "xmax": round(bb.xmax, 3),
            "ymin": round(bb.ymin, 3), "ymax": round(bb.ymax, 3),
            "zmin": round(bb.zmin, 3), "zmax": round(bb.zmax, 3),
            "xlen": round(bb.xlen, 3), "ylen": round(bb.ylen, 3), "zlen": round(bb.zlen, 3)}


def _raw_cylinders(solids, screw_bands) -> tuple[list[dict], int, int]:
    """Per-face cylinders with ABSOLUTE axis points (placement-truth, not collapsed)."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Plane
    cylinders, planes, faces = [], 0, 0
    for solid in solids:
        for face in solid.Faces():
            faces += 1
            ad = BRepAdaptor_Surface(face.wrapped)
            t = ad.GetType()
            if t == GeomAbs_Plane:
                planes += 1
            elif t == GeomAbs_Cylinder:
                cyl = ad.Cylinder(); loc = cyl.Axis().Location(); d = cyl.Axis().Direction()
                r = float(cyl.Radius())
                cylinders.append({
                    "radius": round(r, 3), "diameter": round(2 * r, 3),
                    "axis_dir": _round3((d.X(), d.Y(), d.Z())),
                    "axis_pt": _round3((loc.X(), loc.Y(), loc.Z())),
                    "screw": classify_screw(2 * r, screw_bands),
                })
    return cylinders, faces, planes


def brep_probe(path: Path, screw_bands=DEFAULT_SCREW_BANDS) -> dict:
    if not brep_available():
        return {"file": str(path), "name": Path(path).stem, "available": False}
    solids = _open_solids(path)
    if not solids:                       # surface-only STEP — degrade, don't crash
        return {"file": str(path), "name": Path(path).stem, "available": True,
                "solids": 0, "faces": 0, "planes": 0, "cylindrical_faces": 0,
                "bbox_mm": None, "hole_families": []}
    cylinders, faces, planes = _raw_cylinders(solids, screw_bands)
    bb = _bbox_minmax(solids)
    return {
        "file": str(path), "name": Path(path).stem, "available": True,
        "solids": len(solids), "faces": faces, "planes": planes,
        "cylindrical_faces": len(cylinders),
        "bbox_mm": [bb["xlen"], bb["ylen"], bb["zlen"]],
        "hole_families": group_cylinder_holes(cylinders, screw_bands),
    }


def cylinder_faces(path: Path, screw_bands=DEFAULT_SCREW_BANDS) -> dict:
    """Inspection view: bbox (min/max), every cylindrical face with its ABSOLUTE
    center, plus the collapsed family summary. Use this to answer placement
    questions ('is the bolt hole on the frame?') that the canonicalized
    `hole_families` centers cannot, without writing a one-off script."""
    if not brep_available():
        return {"file": str(path), "name": Path(path).stem, "available": False}
    solids = _open_solids(path)
    if not solids:
        return {"file": str(path), "name": Path(path).stem, "available": True,
                "solids": 0, "bbox": None, "cylinders": [], "hole_families": []}
    cylinders, faces, planes = _raw_cylinders(solids, screw_bands)
    return {
        "file": str(path), "name": Path(path).stem, "available": True,
        "solids": len(solids), "faces": faces, "planes": planes,
        "bbox": _bbox_minmax(solids),
        "cylinders": sorted(cylinders, key=lambda c: (c["diameter"], c["axis_pt"])),
        "hole_families": group_cylinder_holes(cylinders, screw_bands),
    }
