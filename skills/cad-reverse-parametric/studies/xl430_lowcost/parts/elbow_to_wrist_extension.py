"""Parametric reconstruction of follower/elbow_to_wrist_extension (the "connector"
extension link for the longer-arm build / joint6 reach).

A long beam (Y -73.046..17.054 = 90.1) bridging two interfaces along X. Upstream end
(Y~2..15): 4x phi1.8 tap diamond + 2x phi8 idler bores (blind, +X face). Downstream end
(Y~-69): 2x M2 clearance through (axis X). The XL330 -> XL430 swap grows the end
interface clearance; the LINK LENGTH (90.1) is preserved. Frame: X[-17.5,17.5] Z[0,23].

    uv run python studies/xl430_lowcost/parts/elbow_to_wrist_extension.py --out outputs/parts
"""
from __future__ import annotations
import sys
import argparse
from pathlib import Path

import cadquery as cq

from cadre import PartIntent
from cadre.geometry import Component
_PARTS_DIR = Path(__file__).resolve().parent
_STUDY_DIR = _PARTS_DIR.parent
for _p in (_STUDY_DIR, _PARTS_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
import _partlib as P
import domain

INTENT = Path(__file__).resolve().parents[1] / "intent" / "elbow_to_wrist_extension.yaml"
_SERVOS = {"XL330-M288-T": domain.XL330, "XL430-W250-T": domain.XL430}


def make_extension(servo: Component, intent: PartIntent | None = None) -> cq.Workplane:
    intent = intent or PartIntent.load(INTENT)
    feat = {f.name: f for f in intent.features}
    horn = feat["upstream_horn_mount"].constraints
    idler = feat["idler_bores"].constraints
    down = feat["downstream_mount"].constraints
    beam = feat["link_beam"].constraints
    flange = feat.get("upstream_round_flange")

    # beam over the bbox; X width grows a touch with the servo so the larger XL430 horn
    # interface clears, but link length (Y 90.1) is PRESERVED.
    mw, mh, md = servo.envelope.as_tuple()
    width_x = max(35.0, mw + 6)
    body = (cq.Workplane("XY")
            .box(width_x, float(beam["link_length_y_mm"]), 23.0,
                 centered=(True, False, False))
            .translate((0, -73.046, 0)))
    face_x = float(beam["upstream_face_x_mm"])

    if flange is not None:
        fc = flange.constraints
        cy, cz = [float(v) for v in fc["center_yz_mm"]]
        support = (cq.Workplane("YZ")
                   .center(cy, cz)
                   .ellipse(float(fc["radius_y_mm"]), float(fc["radius_z_mm"]))
                   .extrude(width_x / 2.0, both=True))
        body = body.union(support)

    # upstream: 4x phi1.8 tap diamond (blind into -X from the +X face)
    for (yy, zz) in horn["diamond_centers_yz_mm"]:
        body = P.blind_seat(body, (0.0, yy, zz), float(horn["hole_diameter_mm"]),
                            float(horn["blind_depth_mm"]), face=face_x, axis="X", into=-1)
    # upstream: 2x phi8 idler bores (blind into -X)
    for (yy, zz) in idler["centers_yz_mm"]:
        body = P.blind_seat(body, (0.0, yy, zz), float(idler["diameter_mm"]),
                            float(idler["blind_depth_mm"]), face=face_x, axis="X", into=-1)
    # downstream: 2x M2 clearance through (axis X)
    body = P.drill(body, [tuple(c) for c in down["mount_centers_mm"]],
                   float(down["hole_diameter_mm"]), "X")
    return body


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("outputs/parts"))
    ap.add_argument("--samples", type=int, default=8000)
    a = ap.parse_args(argv)
    intent = PartIntent.load(INTENT)
    servo_name = {f.name: f for f in intent.features}["upstream_horn_mount"].servo
    P.report_main("elbow_to_wrist_extension",
                  lambda: make_extension(_SERVOS[servo_name], intent),
                  swap_build=lambda: make_extension(domain.XL430, intent),
                  samples=a.samples, out=a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
