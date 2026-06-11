"""Generic, domain-agnostic command line. Useful on ANY STEP/STL, no servo terms.

    python -m cadre.cli probe   <file.step|file.stl> [...]
    python -m cadre.cli inspect <file.step>           # bbox + abs hole positions
    python -m cadre.cli equiv   <original> <candidate> [--samples N]
    python -m cadre.cli scaffold --w 28.5 --h 46.5 --d 34 --out OUT
"""
from __future__ import annotations
import sys
import json
import argparse
from pathlib import Path

from .probes import (step_text_probe, stl_geometry_probe, brep_probe,
                     brep_available, cylinder_faces)
from .equivalence import compare, verdict, EquivalenceThresholds
from .geometry import Envelope


def _probe(args) -> int:
    out = []
    for a in args.files:
        p = Path(a)
        if not p.exists():
            continue
        if p.suffix.lower() == ".stl":
            out.append({"tier": "stl", **stl_geometry_probe(p)})
        elif p.suffix.lower() == ".step":
            rec = {"tier": "step_text", **step_text_probe(p)}
            if args.brep and brep_available():
                rec["brep"] = brep_probe(p)
            out.append(rec)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def _inspect(args) -> int:
    r = cylinder_faces(Path(args.file))
    if args.json or not r.get("available") or not r.get("cylinders"):
        print(json.dumps(r, indent=2, ensure_ascii=False))
        return 0
    bb = r["bbox"]
    print(f"{r['name']}  solids={r['solids']} faces={r['faces']}")
    print(f"bbox  X[{bb['xmin']},{bb['xmax']}]={bb['xlen']}  "
          f"Y[{bb['ymin']},{bb['ymax']}]={bb['ylen']}  "
          f"Z[{bb['zmin']},{bb['zmax']}]={bb['zlen']}")
    print("cylindrical faces (dia, screw, axis dir, ABS center):")
    for c in r["cylinders"]:
        print(f"  d={c['diameter']:6.2f}  {str(c['screw'] or '-'):8s} "
              f"dir={c['axis_dir']}  center={c['axis_pt']}")
    print("families (axes/faces):")
    for f in r["hole_families"]:
        print(f"  d={f['diameter']:6.2f} {str(f['screw'] or '-'):8s} "
              f"axes={f['axes']} faces={f['faces']} dir={f['axis_dir']}")
    return 0


def _equiv(args) -> int:
    cmp = compare(Path(args.original), Path(args.candidate), args.samples)
    cmp["verdict"] = verdict(cmp, EquivalenceThresholds(
        args.max_bbox_mm, args.max_surf_mm, args.max_vol_pct))
    print(json.dumps(cmp, indent=2, ensure_ascii=False))
    return 0


def _scaffold(args) -> int:
    from . import parametric
    env = Envelope(args.w, args.h, args.d)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    files = []
    files += parametric.export(parametric.envelope_proxy(env), out / "envelope")
    files += parametric.export(parametric.clearance_pocket(env), out / "pocket")
    print(json.dumps({"envelope_mm": env.as_tuple(), "files": files}, indent=2))
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="cadre")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("probe"); p.add_argument("files", nargs="+")
    p.add_argument("--brep", action="store_true"); p.set_defaults(fn=_probe)

    i = sub.add_parser("inspect"); i.add_argument("file")
    i.add_argument("--json", action="store_true"); i.set_defaults(fn=_inspect)

    e = sub.add_parser("equiv")
    e.add_argument("original"); e.add_argument("candidate")
    e.add_argument("--samples", type=int, default=20000)
    e.add_argument("--max-bbox-mm", type=float, default=0.5)
    e.add_argument("--max-surf-mm", type=float, default=0.5)
    e.add_argument("--max-vol-pct", type=float, default=2.0)
    e.set_defaults(fn=_equiv)

    s = sub.add_parser("scaffold")
    for dim in ("w", "h", "d"):
        s.add_argument(f"--{dim}", type=float, required=True)
    s.add_argument("--out", default="outputs/scaffold"); s.set_defaults(fn=_scaffold)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
